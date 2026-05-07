"""Review-queue: discover draft claims awaiting human sign-off and walk through them.

Phase 1 surfaces a single queue type, "publication" — claims at ``status: draft``
whose research is complete (sidecar exists) but that have not yet been approved
by a human (``human_review.reviewed_at`` is null/missing).

Future phases will introduce a queue-type protocol so the same interactive
loop can drive other queues (blocked claims, stale claims, etc.).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import click
import yaml

from common.content_loader import list_claims
from common.frontmatter import FlowList, parse_frontmatter, serialize_frontmatter
from common.sidecar import read_sidecar


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


def _slug_for(claim_path: Path, claims_root: Path) -> str:
    rel = claim_path.relative_to(claims_root).with_suffix("")
    return str(rel).replace("\\", "/")


def _build_item(claim_path: Path, claims_root: Path, repo_root: Path) -> QueueItem | None:
    """Return a QueueItem if `claim_path` belongs in the publication queue, else None."""
    try:
        fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    status = fm.get("status") or ""
    # In queue: draft (or legacy status-absent).
    if status not in ("", "draft"):
        return None

    sidecar = read_sidecar(claim_path)
    if sidecar is None:
        # Research not yet run; not our queue's concern.
        return None

    review = sidecar.get("human_review") or {}
    if review.get("reviewed_at"):
        # Already reviewed; not in queue.
        return None

    audit = sidecar.get("audit") or {}
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
    )


def find_publication_queue(
    repo_root: Path,
    *,
    filter_entity: str | None = None,
) -> list[QueueItem]:
    """Return all draft claims with a sidecar but no human review yet."""
    claims_root = repo_root / "research" / "claims"
    items: list[QueueItem] = []
    for path in list_claims(repo_root, entity=filter_entity):
        item = _build_item(path, claims_root, repo_root)
        if item is not None:
            items.append(item)
    return items


# --------------------------------------------------------------------------- #
# Interactive loop                                                            #
# --------------------------------------------------------------------------- #

_ACTIONS = ["a", "d", "e", "s", "p", "o", "q"]
_PROMPT = (
    "[a]pprove  [d]elete  [e]dit fields  [s]kip  [p]review  "
    "[o]pen in editor  [q]uit"
)
_EMPTY = click.style("—", dim=True)

_EDITABLE_FIELDS = ("title", "takeaway", "seo_title", "tags", "verdict")
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


def _format_header(item: QueueItem, index: int, total: int) -> str:
    prefix = f"── [{index}/{total}] {item.claim_slug} "
    sep = prefix + "─" * max(4, 72 - len(prefix))

    verdict_upper = item.verdict.upper()
    agreement = ""
    if item.analyst_verdict or item.auditor_verdict:
        agreement = f"  (analyst: {item.analyst_verdict} / auditor: {item.auditor_verdict})"
    flag = click.style("  ⚠ needs review", fg="yellow") if item.needs_review else ""
    verdict_line = click.style(verdict_upper, bold=True) + agreement + flag

    def row(label: str, value: str) -> str:
        return f"  {label:<9} {value}"

    return "\n".join([
        "",
        sep,
        row("Verdict", verdict_line),
        row("Title", item.title),
        row("Takeaway", item.takeaway or _EMPTY),
        row("SEO title", item.seo_title or _EMPTY),
        row("Tags", ", ".join(item.tags) if item.tags else _EMPTY),
        row("Sources", f"{item.sources_count} cited · {item.sources_ingested} ingested"),
        "",
    ])


def _resolve_editor() -> list[str]:
    """Editor command for the `o` action. Honors $VISUAL, then $EDITOR, then `code`."""
    for env_var in ("VISUAL", "EDITOR"):
        value = os.environ.get(env_var)
        if value:
            return value.split()
    if shutil.which("code"):
        return ["code"]
    return []


def _preview(claim_path: Path) -> None:
    """Print the claim file to stdout, paged through `less` if the terminal is tall enough."""
    text = claim_path.read_text(encoding="utf-8")
    pager = os.environ.get("PAGER") or ("less" if shutil.which("less") else None)
    if pager and sys.stdout.isatty():
        try:
            proc = subprocess.run([pager], input=text, text=True, check=False)
            if proc.returncode == 0:
                return
        except FileNotFoundError:
            pass
    click.echo(text)


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
    for key in _EDITABLE_FIELDS:
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
    unknown = set(data) - set(_EDITABLE_FIELDS)
    if unknown:
        raise ValueError(
            f"Unknown fields not allowed: {sorted(unknown)}. "
            f"Editable: {list(_EDITABLE_FIELDS)}."
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


def _apply_edits(claim_path: Path, edits: dict) -> None:
    text = claim_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    for key in _EDITABLE_FIELDS:
        if key not in edits:
            continue
        if key == "tags":
            fm[key] = FlowList(edits[key])
        else:
            fm[key] = edits[key]
    claim_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")


def _preview_item(original: QueueItem, edits: dict) -> QueueItem:
    return replace(
        original,
        title=edits.get("title", original.title),
        takeaway=edits.get("takeaway", original.takeaway),
        seo_title=edits.get("seo_title", original.seo_title),
        tags=list(edits.get("tags", original.tags)),
        verdict=edits.get("verdict", original.verdict),
    )


def _edit_fields(
    item: QueueItem,
    claim_path: Path,
    index: int,
    total: int,
) -> QueueItem | None:
    """Drive the edit -> preview -> save loop. Returns updated item on save, None on discard."""
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
        click.echo(_format_header(updated, index, total))
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

        _apply_edits(claim_path, edits)
        return updated


def run_interactive(
    items: list[QueueItem],
    repo_root: Path,
    *,
    trash_dir: Path | None = None,
) -> None:
    """Walk the operator through the queue. Returns when they quit or the queue empties."""
    from common.sidecar import sidecar_path_for
    from orchestrator.review import approve_claim

    if not items:
        click.echo("Queue is empty: no draft claims awaiting review.")
        return

    total = len(items)
    i = 0
    while i < total:
        item = items[i]
        click.echo(_format_header(item, i + 1, total))
        action = click.prompt(
            _PROMPT + "  ",
            type=click.Choice(_ACTIONS, case_sensitive=False),
            show_choices=False,
            default="s",
        ).lower()

        claim_path = repo_root / item.path

        if action == "q":
            return
        if action == "s":
            i += 1
            continue
        if action == "p":
            _preview(claim_path)
            continue  # re-prompt the same item
        if action == "o":
            _open_in_editor(claim_path)
            continue  # re-prompt; operator returns when ready
        if action == "e":
            updated = _edit_fields(item, claim_path, i + 1, total)
            if updated is not None:
                items[i] = updated
                click.echo(f"Saved edits to {item.claim_slug}")
            continue
        if action == "a":
            try:
                approve_claim(claim_path, mode="approve")
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


# --------------------------------------------------------------------------- #
# Non-interactive output helpers                                              #
# --------------------------------------------------------------------------- #

def format_table(items: list[QueueItem]) -> str:
    """Tab-separated rows: slug, status, verdict, needs_review, path. One header line."""
    lines = ["slug\tstatus\tverdict\tneeds_review\tpath"]
    for item in items:
        lines.append(
            f"{item.claim_slug}\t{item.status}\t{item.verdict}\t"
            f"{'yes' if item.needs_review else 'no'}\t{item.path}"
        )
    return "\n".join(lines)


def to_json_records(items: list[QueueItem]) -> list[dict]:
    """Return JSON-serializable dicts (one per queue item)."""
    return [asdict(item) for item in items]
