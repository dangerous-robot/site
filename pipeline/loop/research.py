"""Research step: the decomposed researcher, the blocklist cap and the coverage pool."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Container
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from common.blocklist import filter_urls, load_blocklist
from common.canonical_url import canonical_key
from common.content_loader import resolve_repo_root
from common.models import SubQuestion
from common.source_classification import EntityIdentity, profile_url_names_entity
from loop.errors import StepError
from loop.spec import VerifyConfig, _cfg_repo_root
from orchestrator.entity_resolution import ResolvedEntity, entity_identity_for
from orchestrator.persistence import load_source_dict

if TYPE_CHECKING:
    from researcher.decomposed import ResearchOutput

logger = logging.getLogger(__name__)


def _warn_uncovered(
    sub_questions: list[SubQuestion],
    coverage: dict[str, list[str]],
) -> None:
    """Log a warning for each sub-question that no ingested source addresses.

    The console shows warnings, so no separate progress line. Not a
    ``result.errors`` entry: the first such entry names a blocked claim's
    cause, and the sidecar's ``sub_questions[].citations: []`` already
    records the gap.
    """
    for sq in sub_questions:
        if not coverage.get(sq.id):
            logger.warning("sub-question %s has no ingested source: %s", sq.id, sq.question)


def _first_url_for(
    sq: str,
    urls: list[str],
    url_addresses: dict[str, list[str]],
    taken: Container[str],
) -> str | None:
    """The first URL in ``urls``, not in ``taken``, that addresses sub-question ``sq``."""
    return next((u for u in urls if u not in taken and sq in url_addresses.get(u, [])), None)


def _order_by_coverage(
    urls: list[str],
    url_addresses: dict[str, list[str]],
    sub_question_ids: list[str],
    current_counts: dict[str, int],
) -> list[str]:
    """Reorder ``urls`` so the sub-question with the fewest sources is filled first.

    Greedy: take the sub-question with the lowest projected count (ties by
    sub-question order), take its first untaken URL in input order, and add
    one to every sub-question that URL addresses. A thin sub-question's
    second URL also comes early, so a failed fetch of its first still leaves
    another near the front. URLs that address no known sub-question follow
    in input order.
    """
    projected = {sq: current_counts.get(sq, 0) for sq in sub_question_ids}
    taken: set[str] = set()
    ordered: list[str] = []
    while True:
        pick = None
        for sq in sorted(sub_question_ids, key=lambda q: projected[q]):
            pick = _first_url_for(sq, urls, url_addresses, taken)
            if pick is not None:
                break
        if pick is None:
            break
        taken.add(pick)
        ordered.append(pick)
        for sq in url_addresses.get(pick, []):
            if sq in projected:
                projected[sq] += 1
    return ordered + [u for u in urls if u not in taken]


def _coverage_pool(
    urls: list[str],
    url_addresses: dict[str, list[str]],
    sub_question_ids: list[str],
    size: int,
) -> list[str]:
    """The first ``size`` of ``urls``, except each sub-question's first two URLs always stay.

    Two, to match ``_order_by_coverage``, which tries a thin sub-question's
    second URL early in case the first fetch fails. The rest of the pool
    fills in input order, so a high-ranked URL that addresses no
    sub-question (a cached source, say) is not pushed out. The result keeps
    input order.
    """
    if len(urls) <= size:
        return list(urls)
    reserved: dict[str, None] = {}
    for _round in range(2):
        for sq in sub_question_ids:
            pick = _first_url_for(sq, urls, url_addresses, reserved)
            if pick is not None:
                reserved[pick] = None
    keep = set(list(reserved)[:size])
    for u in urls:
        if len(keep) >= size:
            break
        keep.add(u)
    return [u for u in urls if u in keep]


def _apply_blocklist_cap(
    raw_urls: list[str],
    cfg: VerifyConfig,
    errors: list[StepError] | None = None,
    url_addresses: dict[str, list[str]] | None = None,
    sub_question_ids: list[str] | None = None,
    identity: EntityIdentity | None = None,
    prefetched_bodies: dict[str, str] | None = None,
    trace: dict | None = None,
) -> tuple[list[str], list[StepError]]:
    """Filter raw_urls through the blocklist, cap at candidate_pool_size, and
    append blocked_host / all_blocked errors. Returns (kept_urls, error_list).

    With sub-questions, the cap keeps each sub-question's first two URLs
    (``_coverage_pool``), so they stay in the pool even when they rank low.

    A blocklisted URL that is the entity's own profile post
    (``profile_url_names_entity``) and has non-empty page text in
    ``prefetched_bodies`` is kept and listed under ``trace["blocklist_spared"]``.
    """
    out_errors: list[StepError] = list(errors) if errors else []
    repo_root_str = cfg.repo_root or str(resolve_repo_root())
    entries = load_blocklist(Path(repo_root_str))
    kept, dropped = filter_urls(raw_urls, entries)
    spared_records: list[dict[str, str]] = []
    if identity is not None and dropped:
        # Blocklist entries exist because those hosts refuse anonymous fetches;
        # with the search's page text in hand no fetch is needed, and the
        # entity's own post may be its only first-party statement.
        bodies = prefetched_bodies or {}
        spared = [
            d for d in dropped
            if (bodies.get(d.url) or "").strip() and profile_url_names_entity(d.url, identity)
        ]
        if spared:
            spared_records = [
                {
                    "url": d.url,
                    "host": d.host,
                    "reason": f"entity's own {d.host} post; page text came with the search result",
                }
                for d in spared
            ]
            logger.info("Blocklist spared the entity's own post(s): %s", [d.url for d in spared])
            spared_urls = {d.url for d in spared}
            dropped = [d for d in dropped if d.url not in spared_urls]
            kept_set = set(kept) | spared_urls
            kept = [u for u in raw_urls if u in kept_set]
    urls = _coverage_pool(
        kept, url_addresses or {}, sub_question_ids or [], cfg.candidate_pool_size
    )
    if spared_records and trace is not None:
        # The cap can still cut a spared post; the sidecar lists only posts that reached the pool.
        in_pool = [r for r in spared_records if r["url"] in urls]
        if in_pool:
            trace["blocklist_spared"] = in_pool
    for d in dropped:
        out_errors.append(
            StepError(
                step="research",
                url=d.url,
                error_type="blocked_host",
                message=f"Dropped by blocklist (host={d.host}): {d.reason}",
                retryable=False,
            )
        )
    if not urls and dropped:
        out_errors.insert(
            0,
            StepError(
                step="research",
                error_type="all_blocked",
                message=f"All {len(dropped)} researcher URLs matched blocklist; returning empty.",
            ),
        )
    return urls, out_errors


def _apply_url_dedup(
    urls: list[str],
    url_index: dict[str, str],
    repo_root: Path,
) -> tuple[list[str], list[tuple[str, str, dict]]]:
    """Partition urls into those to ingest and those already on disk.

    ``url_index`` is keyed by ``canonical_key`` (see
    ``build_source_url_index``), so ``www.``, trailing-slash and
    tracking-param variants match the file on disk.

    Returns (to_ingest, cached) where cached is a list of
    (url, source_id, source_dict) triples.
    """
    to_ingest: list[str] = []
    cached: list[tuple[str, str, dict]] = []
    for url in urls:
        source_id = url_index.get(canonical_key(url))
        if source_id:
            sd = load_source_dict(source_id, repo_root)
            if sd is not None:
                logger.info("dedup-hit: %s -> %s", url, source_id)
                cached.append((url, source_id, sd))
                continue
        to_ingest.append(url)
    return to_ingest, cached


async def _research(
    client: httpx.AsyncClient,
    entity_name: str,
    claim_text: str,
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    resolved_entity: "ResolvedEntity | None" = None,
    topics: list[str] | None = None,
) -> "ResearchOutput":
    """Run the decomposed researcher and return a ``ResearchOutput``.

    The returned ``trace`` dict is suitable for the audit sidecar's
    ``research:`` block. Always populated with at least ``mode``; further
    fields depend on how far the researcher got before any error.

    ``topics`` is the criterion's topic list (per ``template.topics``);
    threaded through to ``decomposed_research`` so the academic-API
    selector (Path 2 arXiv, future S2/OpenAlex) can decide whether to
    fire. Empty / ``None`` keeps academic dispatch off.
    """
    from researcher.decomposed import decomposed_research
    out = await decomposed_research(
        claim_text, entity_name, cfg, sem, client,
        resolved_entity=resolved_entity, topics=topics,
    )
    identity = (
        entity_identity_for(resolved_entity, _cfg_repo_root(cfg))
        if resolved_entity is not None
        else None
    )
    urls, errors = _apply_blocklist_cap(
        out.urls, cfg, out.errors,
        url_addresses=out.url_addresses,
        sub_question_ids=[sq.id for sq in out.sub_questions],
        identity=identity,
        prefetched_bodies=out.prefetched_bodies,
        trace=out.trace,
    )
    logger.info("Decomposed research: %d kept (cap=%d)", len(urls), cfg.candidate_pool_size)
    out.urls = urls
    out.errors = errors
    out.url_addresses = {u: out.url_addresses.get(u, []) for u in urls}
    out.prefetched_bodies = {
        u: out.prefetched_bodies[u] for u in urls if u in out.prefetched_bodies
    }
    out.trace["urls_after_blocklist"] = len(urls)
    return out
