"""Shared `approve_claim` helper used by `dr review --claim` and the `a` key of the `dr review` walkthrough."""
from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path
from typing import Literal

import click
import yaml

from common.frontmatter import has_criterion, parse_frontmatter
from common.sidecar import pipeline_verdict_of, read_sidecar, sidecar_path_for
from orchestrator.persistence import (
    is_pending,
    live_path_for,
    pending_path_for,
    promote_pending,
    promotion_half_done,
    set_claim_corrections,
    set_claim_status,
)

ReviewMode = Literal["review", "approve", "archive"]

_CONFIRM_VERB: dict[str, str] = {
    "review": "Sign off",
    "approve": "Approve and publish",
    "archive": "Archive",
}


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _prompt_slug(verb: str, slug: str) -> str:
    return click.prompt(
        f"{verb} {slug}: type the claim slug to confirm", default="", show_default=False
    )


def claim_slug_for(claim_path: Path) -> str:
    """``<entity>/<claim>`` (or the nested path under ``research/claims``) for a claim file.

    A pending recheck under ``research/pending`` has its live claim's ref.
    """
    for ancestor in claim_path.parents:
        if ancestor.name in ("claims", "pending") and ancestor.parent.name == "research":
            return claim_path.relative_to(ancestor).with_suffix("").as_posix()
    return f"{claim_path.parent.name}/{claim_path.stem}"


def _repo_root_of(claim_path: Path) -> Path | None:
    """The repo root above ``research/claims`` or ``research/pending``, or None."""
    for ancestor in claim_path.parents:
        if ancestor.name in ("claims", "pending") and ancestor.parent.name == "research":
            return ancestor.parent.parent
    return None


def recheck_pair(claim_path: Path) -> tuple[Path, Path | None]:
    """``(live path, pending path)`` for a live or pending claim path; the pending path is None when no pending recheck exists."""
    root = _repo_root_of(claim_path)
    if root is None:
        return claim_path, None
    if is_pending(claim_path, root):
        live = live_path_for(claim_path, root)
        return live, claim_path if claim_path.exists() else None
    pending = pending_path_for(claim_path, root)
    return claim_path, pending if pending.exists() else None


def _pick_awaits_restatement(claim_path: Path, sidecar: dict) -> bool:
    """True when the sidecar records a pick and no claim restating this one exists yet.

    ``dr draft --restates <ref> --pick <n>`` reads the candidate from this
    claim's ``restatement`` block, so approving or archiving must not remove
    the block between the ``r`` key and that run.
    """
    block = sidecar.get("restatement")
    if not isinstance(block, dict) or block.get("picked") is None:
        return False
    claims_root = next(
        (a for a in claim_path.parents if a.name == "claims" and a.parent.name == "research"),
        None,
    )
    if claims_root is None:
        return True
    ref = claim_slug_for(claim_path)
    for path in claims_root.rglob("*.audit.yaml"):
        text = path.read_text(encoding="utf-8")
        if "restates:" not in text:
            continue
        try:
            other = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            continue
        if isinstance(other, dict) and other.get("restates") == ref:
            return False
    return True


def require_terminal() -> None:
    """Raise unless stdin is a tty. A piped command is not a person."""
    if not _stdin_is_tty():
        raise click.ClickException(
            "a sign-off needs a person at a terminal (stdin is not a tty); nothing changed"
        )


def confirm_person_present(claim_path: Path, mode: ReviewMode) -> None:
    """Refuse a sign-off unless a person at a terminal types the claim slug back.

    The reviewer name written here is what the site shows as "Reviewed". An
    agent session runs commands with stdin piped, so without this check one
    could record a human review that never happened. Raises ClickException
    before anything is written.
    """
    require_terminal()
    slug = claim_slug_for(claim_path)
    typed = _prompt_slug(_CONFIRM_VERB[mode], slug).strip()
    if typed != slug:
        raise click.ClickException(
            f"the typed slug did not match {slug!r}; nothing changed"
        )


def _resolve_reviewer(reviewer: str | None) -> str:
    if reviewer:
        return reviewer
    proc = subprocess.run(
        ["git", "config", "user.email"],
        capture_output=True,
        text=True,
        check=False,
    )
    git_email = proc.stdout.strip()
    if git_email:
        return git_email
    raise click.ClickException(
        "reviewer not provided and git config user.email is empty"
    )


def _read_claim_frontmatter(claim_path: Path) -> dict:
    try:
        fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise click.ClickException(f"claim file not found: {claim_path}") from exc
    except ValueError as exc:
        raise click.ClickException(
            f"malformed frontmatter in {claim_path}: {exc}"
        ) from exc
    return fm


def _preflight_status(
    claim_path: Path, fm: dict, mode: ReviewMode
) -> tuple[str | None, str | None]:
    """Validate the requested transition; return (expected_current, new_status)."""
    if mode == "review":
        return None, None

    current_status = fm.get("status")

    if mode == "approve":
        effective_current = current_status if current_status is not None else "draft"
        if effective_current == "archived":
            raise click.ClickException("cannot approve an archived claim")
        if effective_current == "blocked":
            blocked_reason = fm.get("blocked_reason", "<unset>")
            raise click.ClickException(
                f"Cannot approve blocked claim {claim_path}; "
                f"address blocked_reason={blocked_reason!r} first."
            )
        if effective_current != "draft":
            raise click.ClickException(
                f"claim already {effective_current}; use --archive to retire"
            )
        if not has_criterion(fm):
            raise click.ClickException(
                f"cannot approve {claim_path}: missing `criteria_slug`. "
                "Set it in the claim frontmatter (a slug from research/templates.yaml) "
                "before publishing."
            )
        return current_status, "published"

    # archive
    if current_status is None:
        raise click.ClickException(
            "cannot archive: claim has no status field; publish first or edit the file manually"
        )
    if current_status not in ("published", "blocked"):
        raise click.ClickException(
            f"cannot archive a claim with status {current_status!r}; "
            f"only published or blocked claims can be archived"
        )
    return current_status, "archived"


def refresh_verdict_change(fm: dict, sidecar: dict | None) -> tuple[str, str] | None:
    """Return (previous, current) verdicts when a refresh changed a published verdict, else None."""
    refresh = (sidecar or {}).get("refresh")
    if not isinstance(refresh, dict):
        return None
    previous = (refresh.get("previous") or {}).get("verdict")
    current = fm.get("verdict")
    if previous is None or current is None or str(previous) == str(current):
        return None
    return str(previous), str(current)


def verdict_change_on_approve(claim_path: Path) -> tuple[str, str] | None:
    """The (previous, new) verdicts an approval of ``claim_path`` would publish over, else None.

    For a pending recheck: the published live verdict and the pending one,
    when they differ (an archived live claim has no published verdict). For
    any other claim: ``refresh_verdict_change``. ``--approve`` needs
    ``--correction`` whenever this is not None.
    """
    live, pending = recheck_pair(claim_path)
    if pending is None:
        try:
            fm, _ = parse_frontmatter(live.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return refresh_verdict_change(fm, read_sidecar(live))
    try:
        live_fm, _ = parse_frontmatter(live.read_text(encoding="utf-8"))
        pending_fm, _ = parse_frontmatter(pending.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if live_fm.get("status") != "published":
        return None
    previous, current = live_fm.get("verdict"), pending_fm.get("verdict")
    if previous is None or current is None or str(previous) == str(current):
        return None
    return str(previous), str(current)


def _verdict_override(fm: dict, sidecar: dict) -> dict | None:
    """Record a reviewer verdict that differs from the pipeline's, so lint can tell it from drift."""
    audit = sidecar.get("audit")
    if not isinstance(audit, dict):
        return None
    analyst = pipeline_verdict_of(audit)
    current = fm.get("verdict")
    if analyst is None or current is None or str(analyst) == str(current):
        return None
    return {"from": str(analyst), "to": str(current)}


def unreviewed_verdict_change(fm: dict, sidecar: dict | None) -> tuple[str, str] | None:
    """Return (pipeline, current) when the verdict differs from the pipeline's with no matching recorded override.

    Published as is, such a claim fails lint's verdict-sidecar-mismatch check.
    """
    change = _verdict_override(fm, sidecar or {})
    if change is None:
        return None
    recorded = ((sidecar or {}).get("human_review") or {}).get("verdict_override") or {}
    if str(recorded.get("from")) == change["from"] and str(recorded.get("to")) == change["to"]:
        return None
    return change["from"], change["to"]


def _add_correction(claim_path: Path, fm: dict, previous_verdict: str, summary: str) -> None:
    """Prepend a correction (newest first), skipping it if a retry already wrote it.

    Only the newest entry can be this refresh's correction. Once one is approved
    the published verdict moves away from its ``previous_verdict``, so a later
    cycle never matches it; the summary is ignored so a reworded retry still dedupes.
    """
    existing = list(fm.get("corrections") or [])
    newest = existing[0] if existing else None
    if isinstance(newest, dict) and str(newest.get("previous_verdict")) == previous_verdict:
        return
    entry = {
        "date": datetime.date.today(),
        "summary": summary,
        "previous_verdict": previous_verdict,
    }
    set_claim_corrections(claim_path, [entry, *existing])


def approve_claim(
    claim_path: Path,
    *,
    reviewer: str | None = None,
    notes: str | None = None,
    pr_url: str | None = None,
    mode: ReviewMode = "review",
    correction_summary: str | None = None,
) -> None:
    """Write human-review sidecar; optionally flip claim status.

    ``mode="review"`` updates the sidecar only.
    ``mode="approve"`` additionally flips status ``draft`` → ``published``.
    ``mode="archive"`` additionally flips status ``published|blocked`` → ``archived``.

    Approving or archiving a refreshed claim closes its sidecar ``refresh``
    block. If an approved refresh changed the published verdict,
    ``correction_summary`` is required and becomes a public ``corrections`` entry.

    A claim with a pending recheck (``research/pending/``; ``claim_path`` may
    be the live or the pending path) is approved by promotion: the pending
    pair is checked as the draft, the correction is required when its
    verdict differs from the published one, the slug typed back is the live
    ref, ``promote_pending`` moves the pair over the live files with the
    refresh snapshot, and the approval below completes on the live path.
    ``mode="review"`` on a pending recheck is refused: only ``--approve``
    takes it. ``mode="archive"`` acts on the live claim and leaves the
    pending pair alone.

    The audit sidecar at ``<claim>.audit.yaml`` must already exist. If
    ``reviewer`` is None, falls back to ``git config user.email``. Raises
    ``click.ClickException`` on validation errors so CLI callers surface a
    clean message.

    Every mode asks a person at a terminal to type the claim slug back before
    the first write (see ``confirm_person_present``).
    """
    live, pending = recheck_pair(claim_path)
    if pending is not None and mode != "archive":
        if mode == "review":
            raise click.ClickException(
                f"{claim_slug_for(live)} has a pending recheck; sign it off with --approve, "
                "which promotes it over the live claim; nothing changed"
            )
        _promote_and_approve(live, pending, reviewer, notes, pr_url, correction_summary)
        return
    claim_path = live

    sidecar_path = sidecar_path_for(claim_path)
    if not claim_path.exists():
        raise click.ClickException(f"claim file not found: {claim_path}")
    if not sidecar_path.exists():
        raise click.ClickException(
            f"no audit sidecar at {sidecar_path}; run the pipeline first"
        )

    fm = _read_claim_frontmatter(claim_path)
    expected_current, new_status = _preflight_status(claim_path, fm, mode)
    effective_reviewer = _resolve_reviewer(reviewer)
    sidecar_data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))

    change = refresh_verdict_change(fm, sidecar_data) if mode == "approve" else None
    summary = (correction_summary or "").strip()
    if change is not None and not summary:
        previous, current = change
        raise click.ClickException(
            f"the verdict changed from {previous!r} to {current!r} since this claim "
            "was published; pass --correction TEXT with a one-line summary for readers"
        )

    # Last check before the first write, so a claim that fails preflight is
    # reported without asking the operator to type anything.
    confirm_person_present(claim_path, mode)
    _record_sign_off(claim_path, mode, effective_reviewer, notes, pr_url, summary)


def _promote_and_approve(
    live: Path,
    pending: Path,
    reviewer: str | None,
    notes: str | None,
    pr_url: str | None,
    correction_summary: str | None,
) -> None:
    """``approve_claim`` for a pending recheck: check, confirm once, promote, then record the approval."""
    root = _repo_root_of(live)
    # A promotion that stopped after moving the sidecar is finished by this one.
    if not sidecar_path_for(pending).exists() and not promotion_half_done(live, root):
        raise click.ClickException(f"no audit sidecar at {sidecar_path_for(pending)}; nothing changed")
    _preflight_status(pending, _read_claim_frontmatter(pending), "approve")
    effective_reviewer = _resolve_reviewer(reviewer)
    summary = (correction_summary or "").strip()
    change = verdict_change_on_approve(live)
    if change is not None and not summary:
        previous, current = change
        raise click.ClickException(
            f"the recheck changed the verdict from {previous!r} to {current!r}; "
            "pass --correction TEXT with a one-line summary for readers"
        )

    confirm_person_present(live, "approve")

    # The files may have changed while the prompt waited: check again from disk.
    if not pending.exists():
        raise click.ClickException(f"the pending recheck {pending} went away while the prompt waited; nothing changed")
    _preflight_status(pending, _read_claim_frontmatter(pending), "approve")
    if verdict_change_on_approve(live) is not None and not summary:
        raise click.ClickException(
            "the verdict changed while the prompt waited; rerun with --correction TEXT"
        )
    try:
        promote_pending(live, root)
    except (OSError, ValueError) as exc:
        # The walkthrough no longer lists a pending claim whose sidecar moved,
        # so the way back is named here.
        raise click.ClickException(
            f"could not promote {pending}: {exc}; run the same --approve again to finish"
        ) from exc
    # The live pair is now a draft with a pending refresh: approve it as one.
    _record_sign_off(live, "approve", effective_reviewer, notes, pr_url, summary)


def _record_sign_off(
    claim_path: Path,
    mode: ReviewMode,
    effective_reviewer: str,
    notes: str | None,
    pr_url: str | None,
    summary: str,
) -> None:
    """The writes of a confirmed sign-off: correction, then sidecar, then status."""
    sidecar_path = sidecar_path_for(claim_path)
    # The operator may have edited the files while the prompt waited (the
    # queue's `o` action with an editor that returns at once): write from a
    # fresh read, with the preflight repeated on it.
    fm = _read_claim_frontmatter(claim_path)
    expected_current, new_status = _preflight_status(claim_path, fm, mode)
    sidecar_data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    change = refresh_verdict_change(fm, sidecar_data) if mode == "approve" else None
    if change is not None and not summary:
        raise click.ClickException(
            "the verdict changed while the prompt waited; rerun with --correction TEXT"
        )

    # Write order: correction, then sidecar, then status. The correction is
    # idempotent, so a rerun after a later failure completes without a duplicate.
    if change is not None:
        _add_correction(claim_path, fm, change[0], summary)

    review = sidecar_data["human_review"]
    review["reviewed_at"] = datetime.date.today().isoformat()
    review["reviewer"] = effective_reviewer
    review["notes"] = notes or ("archived" if mode == "archive" else None)
    review["pr_url"] = pr_url
    review["verdict_override"] = _verdict_override(fm, sidecar_data)
    # Approving or archiving ends the refresh and retires the restatement
    # candidates (the claim goes live or away as it stands); a sign-off alone
    # leaves both. A recorded pick keeps the candidates until a claim restates
    # this one. ``restates`` is the claim's link to its original and stays.
    if mode in ("approve", "archive"):
        sidecar_data.pop("refresh", None)
        if not _pick_awaits_restatement(claim_path, sidecar_data):
            sidecar_data.pop("restatement", None)

    sidecar_path.write_text(
        yaml.safe_dump(sidecar_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Sidecar is the commit point: if the .md flip raises, the sidecar is
    # already updated and rerunning the same flag re-detects the pre-flip
    # status to complete the transition.
    if new_status is not None:
        try:
            set_claim_status(claim_path, new_status, expected_current)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
