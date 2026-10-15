"""Which published claims are due for a recheck, and what a pending recheck changed.

Reads only, except ``run_batch``. ``dr recheck --due`` selects with
``due_claims``; the review packet's header row of a pending recheck comes from
``recheck_counts``; ``dr recheck`` and ``dr findings --replay`` run their
claims through ``run_batch``.
"""
from __future__ import annotations

import asyncio
import datetime
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from common.frontmatter import parse_frontmatter
from common.sidecar import read_sidecar
from orchestrator.persistence import (
    CLAIMS_BASE,
    DEFAULT_RECHECK_CADENCE_DAYS,
    build_source_url_index,
    pending_path_for,
)


@dataclass(frozen=True)
class DueClaim:
    """A published claim whose recheck is due."""

    ref: str
    path: Path
    due: datetime.date
    # Which field set the date: ``next_recheck_due``, or ``as_of`` plus the cadence.
    reason: Literal["next_recheck_due", "as_of"]


def _as_date(value: object) -> datetime.date | None:
    """A frontmatter date, written as a quoted string or a YAML date."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def cadence_days(fm: dict) -> int:
    """The claim's ``recheck_cadence_days``, or the site's default."""
    cadence = fm.get("recheck_cadence_days")
    if isinstance(cadence, int) and not isinstance(cadence, bool) and cadence > 0:
        return cadence
    return DEFAULT_RECHECK_CADENCE_DAYS


def due_date(fm: dict) -> tuple[datetime.date, Literal["next_recheck_due", "as_of"]] | None:
    """When the claim is due and which field says so; None when neither date reads.

    ``next_recheck_due`` wins when set; otherwise ``as_of`` plus
    ``recheck_cadence_days`` (default 60).
    """
    due = _as_date(fm.get("next_recheck_due")) if fm.get("next_recheck_due") is not None else None
    if due is not None:
        return due, "next_recheck_due"
    as_of = _as_date(fm.get("as_of"))
    if as_of is None:
        return None
    return as_of + datetime.timedelta(days=cadence_days(fm)), "as_of"


def due_claims(repo_root: Path, today: datetime.date | None = None) -> list[DueClaim]:
    """Published claims whose due date is today or earlier, in path order.

    Drafts and archived claims are not selected, nor is a claim
    whose pending recheck already awaits review.
    """
    today = today or datetime.date.today()
    claims_root = repo_root / CLAIMS_BASE
    if not claims_root.exists():
        return []
    out: list[DueClaim] = []
    for path in sorted(claims_root.rglob("*.md")):
        try:
            fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError):
            # Lint reports a claim that does not parse; the other claims still run.
            continue
        if fm.get("status") != "published":
            continue
        if pending_path_for(path, repo_root).exists():
            continue
        found = due_date(fm)
        if found is None or found[0] > today:
            continue
        ref = path.relative_to(claims_root).with_suffix("").as_posix()
        out.append(DueClaim(ref=ref, path=path, due=found[0], reason=found[1]))
    return out


def recheck_counts(pending_path: Path, live_path: Path) -> dict:
    """The header record of a pending recheck against its live claim.

    Over the pending sidecar's ``sources_consulted`` entries the pending
    claim cites: ``quotes_checked`` counts the quotes with a found or not-found
    result, ``quotes_found`` the found ones, ``quotes_not_rechecked`` the rest
    (a cached source inside its cadence keeps its stored quotes unchecked),
    ``refetched`` the entries whose cached source was fetched again.
    """
    def verdict_of(path: Path) -> str | None:
        try:
            fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError):
            return None
        verdict = fm.get("verdict")
        return str(getattr(verdict, "value", verdict)) if verdict is not None else None

    try:
        pending_fm, _ = parse_frontmatter(pending_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        pending_fm = {}
    try:
        sidecar = read_sidecar(pending_path) or {}
    except (OSError, ValueError, yaml.YAMLError):
        sidecar = {}
    cited = {str(s) for s in pending_fm.get("sources") or []}
    entries = [
        e for e in sidecar.get("sources_consulted") or []
        if isinstance(e, dict) and str(e.get("id")) in cited
    ]
    quotes = [q for e in entries for q in e.get("quotes") or [] if isinstance(q, dict)]
    live_verdict = verdict_of(live_path)
    pending_verdict = verdict_of(pending_path)
    return {
        "live_verdict": live_verdict,
        "pending_verdict": pending_verdict,
        "verdict_changed": live_verdict != pending_verdict,
        "quotes_found": sum(1 for q in quotes if q.get("found") is True),
        "quotes_checked": sum(1 for q in quotes if q.get("found") in (True, False)),
        "quotes_not_rechecked": sum(1 for q in quotes if q.get("found") not in (True, False)),
        "refetched": sum(1 for e in entries if (e.get("recheck") or {}).get("refetched") is True),
    }


# One claim's run in a batch: given the batch's LLM semaphore and source URL
# index, run the claim, write what it writes and return its outcome word.
BatchJob = Callable[[asyncio.Semaphore, dict], Awaitable[str]]


def run_batch(jobs: Sequence[BatchJob], *, llm_concurrency: int, repo_root: Path) -> list[str]:
    """Run each job one after another inside one event loop; return their outcomes in order.

    Every job shares one LLM semaphore and one source URL index, so a batch
    never runs more model calls at once than ``llm_concurrency``. Each job
    contains its own failures (records its finding and returns an outcome),
    so one claim's failure never stops the next.
    """
    async def _batch() -> list[str]:
        sem = asyncio.Semaphore(llm_concurrency)
        url_index = build_source_url_index(repo_root)
        return [await job(sem, url_index) for job in jobs]

    return asyncio.run(_batch())
