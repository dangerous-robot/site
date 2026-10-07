"""Shared `approve_claim` helper used by `dr review` and `dr review-queue`."""
from __future__ import annotations

import datetime
import subprocess
from pathlib import Path
from typing import Literal

import click
import yaml

from common.frontmatter import has_criterion, parse_frontmatter
from common.sidecar import sidecar_path_for
from orchestrator.persistence import set_claim_corrections, set_claim_status

ReviewMode = Literal["review", "approve", "archive"]


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


def _verdict_override(fm: dict, sidecar: dict) -> dict | None:
    """Record a reviewer verdict that differs from the analyst's, so lint can tell it from drift."""
    audit = sidecar.get("audit")
    if not isinstance(audit, dict):
        return None
    analyst = audit.get("analyst_verdict")
    current = fm.get("verdict")
    if analyst is None or current is None or str(analyst) == str(current):
        return None
    return {"from": str(analyst), "to": str(current)}


def _add_correction(claim_path: Path, fm: dict, previous_verdict: str, summary: str) -> None:
    """Prepend a correction (newest first), skipping it if a retry already wrote it."""
    existing = list(fm.get("corrections") or [])
    for entry in existing:
        if (
            isinstance(entry, dict)
            and str(entry.get("previous_verdict")) == previous_verdict
            and entry.get("summary") == summary
        ):
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

    Approving a refreshed claim closes its sidecar ``refresh`` block. If the
    refresh changed the published verdict, ``correction_summary`` is required
    and becomes a public ``corrections`` entry.

    The audit sidecar at ``<claim>.audit.yaml`` must already exist. If
    ``reviewer`` is None, falls back to ``git config user.email``. Raises
    ``click.ClickException`` on validation errors so CLI callers surface a
    clean message.
    """
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
    if mode == "approve":
        sidecar_data.pop("refresh", None)

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
