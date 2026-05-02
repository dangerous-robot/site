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
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import click

from common.content_loader import list_claims
from common.frontmatter import parse_frontmatter
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
    sources = sidecar.get("sources_consulted") or []
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
        sources_count=len(sources),
        sources_ingested=sum(1 for s in sources if isinstance(s, dict) and s.get("ingested")),
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

_ACTIONS = ["a", "d", "s", "p", "o", "q"]
_PROMPT = "[a]pprove  [d]elete  [s]kip  [p]review  [o]pen in editor  [q]uit"
_EMPTY = click.style("—", dim=True)


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
