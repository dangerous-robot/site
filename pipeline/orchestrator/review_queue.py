"""The `dr review` walkthrough: find draft claims awaiting sign-off and walk through them.

The queue holds claims at ``status: draft`` whose research is complete
(sidecar exists) but that a person has not yet approved
(``human_review.reviewed_at`` is null or missing), under ``research/claims``
and, for a recheck of a published claim, ``research/pending`` (listed under
the live claim's ref; approving it promotes it). Each queued draft is shown
as its review packet (``orchestrator/packet.py``); the edits a reviewer makes
here are written by ``orchestrator.persistence``.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

import click
import yaml

from common.content_loader import list_claims
from common.frontmatter import parse_frontmatter
from common.sidecar import pipeline_verdict_of, read_sidecar
from orchestrator.persistence import REVIEW_EDITABLE_FIELDS, record_restatement_pick, set_claim_fields


@dataclass
class QueueItem:
    """One item in the publication queue."""

    claim_slug: str          # e.g. "openai/gpt-5-energy-claim"
    path: str                # repo-relative path, e.g. "research/claims/openai/gpt-5-energy-claim.md"
    title: str
    status: str              # "draft" or "" (legacy: status field absent)
    verdict: str             # frontmatter verdict ("true"/"false"/"mixed"/"unverifiable")
    analyst_verdict: str
    auditor_verdict: str
    needs_review: bool       # auditor flagged disagreement / quality concerns
    sources_count: int       # number of sources_consulted in sidecar
    sources_ingested: int    # number where ingested=True
    tags: list[str]          # operator tags, e.g. ["highlight"]
    takeaway: str            # one-sentence reader takeaway (empty if not yet written)
    seo_title: str           # short title for SERP (empty if not yet written)
    previous_verdict: str = ""      # published verdict before a pending refresh ("" if none)
    previous_reviewed_at: str = ""  # sign-off date of that published version
    restatement: dict | None = None  # the sidecar's restatement block, when one was written
    # Run id of the run's ``partial`` restate finding, when the restater failed; else None.
    restatement_unavailable: str | None = None
    # The verdict the pipeline settled on (the analyst's, for a sidecar from
    # before the tie-breaker existed).
    pipeline_verdict: str = ""
    # ``{from, to}`` when the claim's verdict differs from the pipeline's with
    # no reviewer override recorded; approving records it as the reviewer's.
    unreviewed_override: dict | None = None
    # For a pending recheck (``orchestrator.recheck.recheck_counts``): the live
    # and pending verdicts, whether they differ, the quote counts and the
    # number of re-fetched sources; None for any other claim.
    recheck: dict | None = None


def _pending_root(claims_root: Path) -> Path:
    return claims_root.parent / "pending"


def _slug_for(claim_path: Path, claims_root: Path) -> str:
    """The claim ref: the path under ``research/claims``, or under ``research/pending`` for a pending recheck."""
    try:
        rel = claim_path.relative_to(claims_root).with_suffix("")
    except ValueError:
        rel = claim_path.relative_to(_pending_root(claims_root)).with_suffix("")
    return str(rel).replace("\\", "/")


def _partial_restate_runs(repo_root: Path) -> set[str]:
    """Run ids of every finding, open or closed, whose restater failed after the verdict settled."""
    from orchestrator.persistence import load_findings

    return {
        f.run_id for f in load_findings(repo_root, include_closed=True)
        if f.step == "restate" and f.outcome == "partial"
    }


def _build_item(
    claim_path: Path,
    claims_root: Path,
    repo_root: Path,
    partial_restate_runs: set[str] | None = None,
) -> QueueItem | None:
    """Return a QueueItem if `claim_path` belongs in the publication queue, else None.

    ``partial_restate_runs`` are the run ids from ``_partial_restate_runs``;
    a claim whose sidecar names one of them gets ``restatement_unavailable``.
    """
    item = item_for(claim_path, claims_root, repo_root, partial_restate_runs)
    # In queue: draft (or legacy status-absent, which item_for reads as draft).
    if item is None or item.status != "draft":
        return None
    review = (read_sidecar(claim_path) or {}).get("human_review") or {}
    if review.get("reviewed_at"):
        # Already reviewed; not in queue.
        return None
    return item


def item_for(
    claim_path: Path,
    claims_root: Path,
    repo_root: Path,
    partial_restate_runs: set[str] | None = None,
) -> QueueItem | None:
    """The QueueItem fields of any claim with a readable frontmatter and a sidecar, queued or not.

    None when the frontmatter does not parse or the research has not run
    (no sidecar).
    """
    from orchestrator.review import unreviewed_verdict_change

    try:
        fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    status = fm.get("status") or ""

    sidecar = read_sidecar(claim_path)
    if sidecar is None:
        # Research not yet run; not our queue's concern.
        return None

    audit = sidecar.get("audit") or {}
    refresh = sidecar.get("refresh") if isinstance(sidecar.get("refresh"), dict) else {}
    previous = refresh.get("previous") or {}
    fm_sources = fm.get("sources") or []
    sidecar_sources = sidecar.get("sources_consulted") or []
    sources_count = len(fm_sources)
    if sidecar_sources:
        sources_ingested = sum(
            1 for s in sidecar_sources
            if isinstance(s, dict) and s.get("ingested")
        )
    else:
        # Defensive fallback for sidecars written before _build_sources_consulted
        # learned about cache-hit sources (every URL was deduped, so source_files
        # was empty and the sidecar got an empty list). Newly-written sidecars
        # populate sources_consulted from both fresh and cached records, so this
        # branch is mostly hit by claims awaiting their next refresh.
        sources_ingested = sources_count
    rel_path = claim_path.relative_to(repo_root)
    restatement = sidecar.get("restatement") if isinstance(sidecar.get("restatement"), dict) else None
    run_id = str((sidecar.get("pipeline_run") or {}).get("run_id") or "")
    unavailable = run_id if run_id and run_id in (partial_restate_runs or set()) else None
    override = unreviewed_verdict_change(fm, sidecar)
    recheck = None
    pending_root = _pending_root(claims_root)
    if pending_root in claim_path.parents:
        from orchestrator.recheck import recheck_counts

        recheck = recheck_counts(claim_path, claims_root / claim_path.relative_to(pending_root))

    return QueueItem(
        claim_slug=_slug_for(claim_path, claims_root),
        path=str(rel_path).replace("\\", "/"),
        title=str(fm.get("title") or ""),
        status=status or "draft",
        verdict=str(fm.get("verdict") or ""),
        analyst_verdict=str(audit.get("analyst_verdict") or ""),
        auditor_verdict=str(audit.get("auditor_verdict") or ""),
        needs_review=bool(audit.get("needs_review")),
        sources_count=sources_count,
        sources_ingested=sources_ingested,
        tags=list(fm.get("tags") or []),
        takeaway=str(fm.get("takeaway") or ""),
        seo_title=str(fm.get("seo_title") or ""),
        previous_verdict=str(previous.get("verdict") or ""),
        previous_reviewed_at=str(previous.get("reviewed_at") or ""),
        restatement=restatement,
        restatement_unavailable=unavailable,
        pipeline_verdict=str(pipeline_verdict_of(audit) or ""),
        unreviewed_override={"from": override[0], "to": override[1]} if override else None,
        recheck=recheck,
    )


def find_publication_queue(
    repo_root: Path,
    *,
    filter_entity: str | None = None,
) -> list[QueueItem]:
    """Return all draft claims with a sidecar but no human review yet, pending rechecks included."""
    claims_root = repo_root / "research" / "claims"
    items: list[QueueItem] = []
    partial_runs = _partial_restate_runs(repo_root)
    pending_root = _pending_root(claims_root)
    pending = sorted(pending_root.rglob("*.md")) if pending_root.exists() else []
    if filter_entity is not None:
        pending = [p for p in pending if p.parent.name == filter_entity]
    for path in [*list_claims(repo_root, entity=filter_entity), *pending]:
        item = _build_item(path, claims_root, repo_root, partial_runs)
        if item is not None:
            items.append(item)
    return items


# --------------------------------------------------------------------------- #
# Interactive loop                                                            #
# --------------------------------------------------------------------------- #

_ACTIONS = ["a", "d", "e", "s", "p", "o", "r", "v", "q"]
_PROMPT = (
    "[a]pprove  [d]elete  [e]dit fields  [s]kip  [p]review  "
    "[o]pen in editor  [r]estate  [v]iew packet  [q]uit"
)

_ALLOWED_VERDICTS = frozenset({
    "true", "mostly-true", "mixed", "mostly-false",
    "false", "unverified", "not-applicable", "",
})
_BUFFER_HEADER = (
    "# Edit fields below; save and exit to preview, or quit "
    "without saving to discard.\n"
    "# Allowed verdict values: true, mostly-true, mixed, mostly-false,\n"
    "#   false, unverified, not-applicable, '' (clear).\n"
    "# The `highlight` tag controls homepage scatter inclusion (per AGENTS.md).\n"
    "# Editing `verdict` overrides analyst/auditor research output.\n"
    "\n"
)


def _delete_files(claim_path: Path, sidecar_path: Path, trash_dir: Path | None = None) -> None:
    """Delete claim and sidecar. On macOS, moves to Trash; elsewhere, hard-deletes."""
    if sys.platform == "darwin":
        dest = trash_dir if trash_dir is not None else Path.home() / ".Trash"
        dest.mkdir(parents=True, exist_ok=True)
        for path in (claim_path, sidecar_path):
            target = dest / path.name
            if target.exists():
                target = dest / f"{path.stem}_{time.time_ns()}{path.suffix}"
            try:
                shutil.move(str(path), target)
            except FileNotFoundError:
                pass
    else:
        for path in (claim_path, sidecar_path):
            path.unlink(missing_ok=True)


def _resolve_editor() -> list[str]:
    """Editor command for the `o` action. Honors $VISUAL, then $EDITOR, then `code`."""
    for env_var in ("VISUAL", "EDITOR"):
        value = os.environ.get(env_var)
        if value:
            return value.split()
    if shutil.which("code"):
        return ["code"]
    return []


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def _page_text(text: str) -> None:
    """Show ``text`` through ``$PAGER`` (else ``less``) at a terminal; print it otherwise or when the pager fails."""
    if _stdout_is_tty():
        try:
            proc = subprocess.run(shlex.split(os.environ.get("PAGER") or "less"), input=text, text=True, check=False)
            if proc.returncode == 0:
                return
        except (FileNotFoundError, ValueError):
            pass
    click.echo(text)


def _preview(claim_path: Path) -> None:
    """Show the claim file, paged at a terminal."""
    _page_text(claim_path.read_text(encoding="utf-8"))


def _open_in_editor(claim_path: Path) -> None:
    cmd = _resolve_editor()
    if not cmd:
        click.echo(
            "No editor found: set $VISUAL or $EDITOR, or install VSCode CLI (`code`).",
            err=True,
        )
        return
    try:
        subprocess.Popen([*cmd, str(claim_path)])
    except (FileNotFoundError, OSError) as exc:
        click.echo(f"Could not launch editor {cmd[0]!r}: {exc}", err=True)


def _resolve_blocking_editor() -> list[str]:
    """Editor argv for `_run_editor_blocking`. Appends `--wait` for `code`
    so the call blocks until the operator closes the buffer."""
    cmd = _resolve_editor()
    if cmd and Path(cmd[0]).name == "code":
        return [*cmd, "--wait"]
    return cmd


def _run_editor_blocking(path: Path) -> int:
    """Open `path` in a blocking editor; return exit code, or -1 if no editor."""
    cmd = _resolve_blocking_editor()
    if not cmd:
        return -1
    try:
        proc = subprocess.run([*cmd, str(path)], check=False)
    except (FileNotFoundError, OSError) as exc:
        click.echo(f"Could not launch editor {cmd[0]!r}: {exc}", err=True)
        return -1
    return proc.returncode


def _build_edit_buffer(fm: dict) -> str:
    subset: dict = {}
    for key in REVIEW_EDITABLE_FIELDS:
        value = fm.get(key, "")
        if key == "tags":
            value = list(value) if isinstance(value, list) else []
        subset[key] = value
    yaml_str = yaml.safe_dump(subset, sort_keys=False, allow_unicode=True)
    return _BUFFER_HEADER + yaml_str


def _parse_edit_buffer(text: str) -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML parse error: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Edited buffer must be a YAML mapping (key: value).")
    return data


def _validate_edit(data: dict) -> None:
    unknown = set(data) - set(REVIEW_EDITABLE_FIELDS)
    if unknown:
        raise ValueError(
            f"Unknown fields not allowed: {sorted(unknown)}. "
            f"Editable: {list(REVIEW_EDITABLE_FIELDS)}."
        )
    verdict = data.get("verdict", "")
    if not isinstance(verdict, str) or verdict not in _ALLOWED_VERDICTS:
        raise ValueError(
            f"verdict must be one of: {sorted(_ALLOWED_VERDICTS)}; "
            f"got {verdict!r}."
        )
    for key in ("title", "takeaway", "seo_title"):
        val = data.get(key, "")
        if not isinstance(val, str):
            raise ValueError(
                f"{key} must be a string; got {type(val).__name__}."
            )
    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError("tags must be a list of strings.")


def _preview_item(original: QueueItem, edits: dict) -> QueueItem:
    return replace(
        original,
        title=edits.get("title", original.title),
        takeaway=edits.get("takeaway", original.takeaway),
        seo_title=edits.get("seo_title", original.seo_title),
        tags=list(edits.get("tags", original.tags)),
        verdict=edits.get("verdict", original.verdict),
    )


def _edit_fields(item: QueueItem, claim_path: Path) -> QueueItem | None:
    """Drive the edit -> preview -> save loop. Returns updated item on save, None on discard."""
    from orchestrator.packet import render_header_facts

    initial_text = claim_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(initial_text)
    pre_mtime = claim_path.stat().st_mtime_ns
    buffer_text = _build_edit_buffer(fm)

    while True:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(buffer_text)
            tmp_path = Path(tf.name)
        try:
            tmp_pre = tmp_path.stat().st_mtime_ns
            rc = _run_editor_blocking(tmp_path)
            if rc < 0:
                click.echo(
                    "No editor found: set $VISUAL or $EDITOR, or install "
                    "VS Code's `code` CLI.",
                    err=True,
                )
                return None
            if rc != 0:
                return None
            tmp_post = tmp_path.stat().st_mtime_ns
            if tmp_post == tmp_pre:
                return None
            edited_text = tmp_path.read_text(encoding="utf-8")
        finally:
            tmp_path.unlink(missing_ok=True)

        try:
            edits = _parse_edit_buffer(edited_text)
            _validate_edit(edits)
        except ValueError as exc:
            click.echo(f"Edit rejected: {exc}", err=True)
            choice = click.prompt(
                "[r]e-edit  [d]iscard",
                type=click.Choice(["r", "d"], case_sensitive=False),
                default="d",
            ).lower()
            if choice == "d":
                return None
            buffer_text = edited_text
            continue

        updated = _preview_item(item, edits)
        click.echo("\n".join(["", *render_header_facts(updated, styled=True), ""]))
        choice = click.prompt(
            "[s]ave  [r]e-edit  [d]iscard",
            type=click.Choice(["s", "r", "d"], case_sensitive=False),
            default="d",
        ).lower()
        if choice == "d":
            return None
        if choice == "r":
            buffer_text = edited_text
            continue

        if claim_path.stat().st_mtime_ns != pre_mtime:
            click.echo(
                f"File changed externally; aborting save: {claim_path}",
                err=True,
            )
            choice = click.prompt(
                "[r]e-edit  [d]iscard",
                type=click.Choice(["r", "d"], case_sensitive=False),
                default="d",
            ).lower()
            if choice == "d":
                return None
            buffer_text = edited_text
            pre_mtime = claim_path.stat().st_mtime_ns
            continue

        set_claim_fields(claim_path, edits)
        return updated


def _pick_restatement(item: QueueItem, claim_path: Path) -> None:
    """The ``r`` key: list the restatement candidates and record the reviewer's pick.

    Runs nothing: it prints the ``dr draft --restates`` command to run after
    the walkthrough.
    """
    if item.restatement_unavailable:
        click.echo(f"Restatement unavailable (finding {item.restatement_unavailable})")
        return
    candidates = [c for c in (item.restatement or {}).get("candidates") or [] if isinstance(c, dict)]
    if not candidates:
        click.echo("No restatement candidates for this claim.")
        return
    for c in candidates:
        click.echo(
            f"  #{c.get('rank')} {c.get('expected_verdict', '')} ({c.get('expected_confidence', '')}) "
            f"decisiveness {c.get('decisiveness', '?')}/4  {c.get('text', '')}"
        )
    answer = click.prompt("Candidate number (blank to cancel)", default="", show_default=False).strip()
    if not answer:
        return
    ranks = {str(c.get("rank")): c.get("rank") for c in candidates}
    if answer not in ranks:
        click.echo(f"No candidate {answer}.")
        return
    n = ranks[answer]
    try:
        record_restatement_pick(claim_path, n)
    except ValueError as exc:
        click.echo(f"Could not record the pick: {exc}", err=True)
        return
    click.echo(f"Picked {n}. After the walkthrough, run: dr draft --restates {item.claim_slug} --pick {n}")


def run_interactive(
    items: list[QueueItem],
    repo_root: Path,
    *,
    trash_dir: Path | None = None,
) -> None:
    """Walk the operator through the queue. Returns when they quit or the queue empties.

    Each draft prints its review packet: parts 2 to 4 first, then the item
    line, the verdict chain and the header facts directly above the key
    prompt. After a key that returns to the same draft, only that bottom
    block is printed again, rebuilt from disk.
    """
    from common.sidecar import sidecar_path_for
    from orchestrator.packet import build_packet, item_line, render_bottom, render_full, render_upper
    from orchestrator.review import approve_claim, require_terminal, verdict_change_on_approve

    if not items:
        click.echo("Queue is empty: no draft claims awaiting review.")
        return

    claims_root = repo_root / "research" / "claims"
    partial_runs = _partial_restate_runs(repo_root)
    total = len(items)
    i = 0
    shown = -1
    while i < total:
        item = items[i]
        claim_path = repo_root / item.path
        try:
            packet = build_packet(claim_path, repo_root, partial_restate_runs=partial_runs)
        except (ValueError, OSError) as exc:
            # The claim changed under the walkthrough (the `o` editor returns
            # at once): say so and still take a key, so it can be fixed or skipped.
            packet = None
            click.echo(f"\n{item_line(item.claim_slug, i + 1, total)}")
            click.echo(f"Could not read the packet: {exc}; [o]pen it to fix or [s]kip")
        if packet is not None:
            if shown != i:
                click.echo(render_upper(packet))
                shown = i
            click.echo(render_bottom(packet, i + 1, total))
        action = click.prompt(
            _PROMPT + "  ",
            type=click.Choice(_ACTIONS, case_sensitive=False),
            show_choices=False,
            default="s",
        ).lower()

        if action == "q":
            return
        if action == "s":
            i += 1
            continue
        if action == "p":
            _preview(claim_path)
            continue  # re-prompt the same item
        if action == "v":
            if packet is None:
                click.echo("No packet to view: the claim does not read.")
            else:
                _page_text(render_full(packet))
            continue
        if action == "o":
            _open_in_editor(claim_path)
            continue  # re-prompt; operator returns when ready
        if action == "r":
            _pick_restatement(item, claim_path)
            items[i] = item_for(claim_path, claims_root, repo_root, partial_runs) or item
            continue
        if action == "e":
            updated = _edit_fields(item, claim_path)
            if updated is not None:
                items[i] = item_for(claim_path, claims_root, repo_root, partial_runs) or updated
                click.echo(f"Saved edits to {item.claim_slug}")
            continue
        if action == "a":
            # Refuse before the correction prompt, and let the error end the
            # queue: with piped stdin a re-prompt would loop forever.
            require_terminal()
            correction = None
            # Read from disk, not the item: `o` can change the verdict in an
            # external editor without updating the queue item. A file that no
            # longer parses skips the prompt; approve_claim reports the error.
            # A pending recheck compares its verdict with the live one.
            change = verdict_change_on_approve(claim_path)
            if change is not None:
                correction = click.prompt(
                    f"Verdict changed from {change[0]} to {change[1]} since publication. "
                    "Correction (one line for readers)",
                    default="",
                    show_default=False,
                )
            try:
                approve_claim(claim_path, mode="approve", correction_summary=correction)
            except click.ClickException as exc:
                click.echo(f"Could not approve: {exc.message}", err=True)
                continue  # re-prompt the same item
            click.echo(f"Approved {item.claim_slug}")
            i += 1
            continue
        if action == "d":
            confirmed = click.confirm(
                f"Delete? {item.path} (+ .audit.yaml)",
                default=False,
            )
            if not confirmed:
                continue  # re-prompt the same item
            _delete_files(claim_path, sidecar_path_for(claim_path), trash_dir)
            click.echo(f"Deleted: {item.claim_slug}")
            i += 1
            continue

    click.echo("\nQueue done.")
