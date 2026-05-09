"""Decomposed researcher pipeline: planner -> search executor -> URL scorer."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict, Field

from common.blocklist import BlocklistEntry, filter_urls
from common.canonical_url import canonicalize
from common.models import ACADEMIC_ORIGINS, ACADEMIC_TOPICS, SubQuestion, resolve_model
from common.publisher_quality import classify_url_publisher_quality
from orchestrator.checkpoints import StepError
from orchestrator.entity_resolution import ResolvedEntity, build_entity_context, resolve_parent_name
from researcher.agent import search_brave
from researcher.planner import ResearchPlan, research_planner_agent
from researcher.scorer import (
    ScoredCandidate,
    ScoredURLs,
    SearchCandidate,
    build_scorer_prompt,
    url_scorer_agent,
)
from researcher.tools.arxiv import search_arxiv
from researcher.tools.tavily import TavilyRateLimitError, search_tavily

# Backends that ``execute_searches`` knows how to dispatch to. Unknown
# values fall back to Brave with a logged warning so a typo can't silently
# stop the pipeline. Keep in sync with VerifyConfig.search_backend.
_KNOWN_BACKENDS: frozenset[str] = frozenset({"brave", "tavily"})

if TYPE_CHECKING:
    from orchestrator.pipeline import VerifyConfig

logger = logging.getLogger(__name__)


class ResearchOutput(BaseModel):
    urls: list[str]
    url_addresses: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map url -> SubQuestion.id values this URL was scored as addressing.",
    )
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    errors: list[StepError] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)
    # Per-sub-question queries from the planner; sourced from ResearchPlan.queries
    # before truncation/blocklist filtering. Used by the orchestrator to render
    # the audit sidecar's `sub_questions:` block.
    queries_by_sub_question: dict[str, list[str]] = Field(default_factory=dict)
    # Map url -> pre-extracted body the search backend supplied
    # (currently Tavily only). The orchestrator passes this into
    # ``IngestorDeps`` so ``web_fetch`` can short-circuit. Empty/missing
    # entries fall through to a live fetch.
    prefetched_bodies: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _research_err(error_type: str, message: str) -> StepError:
    return StepError(step="research", error_type=error_type, message=message)


def _select_research_origins(
    cfg: "VerifyConfig", topics: list[str]
) -> list[str]:
    """Subset of ``cfg.research_origins`` to dispatch as academic origins.

    Returns ``[]`` unless ``topics`` intersects ``ACADEMIC_TOPICS``.
    The general-web spine (Brave/Tavily, selected by
    ``cfg.search_backend``) is dispatched independently and is never
    part of the returned list.
    """
    if not topics:
        return []
    if not (set(topics) & ACADEMIC_TOPICS):
        return []
    return [
        origin
        for origin in cfg.research_origins
        if origin in ACADEMIC_ORIGINS
    ]


async def _dispatch_arxiv_one_query(
    client: httpx.AsyncClient,
    query: str,
    errors_out: list[StepError] | None,
    tool_outcomes_out: list[dict] | None,
) -> list[dict]:
    """Run a single arXiv query; map failures to existing StepError vocab.

    No fallback (contrast Tavily->Brave at ``_dispatch_one_query``).
    Timeouts -> ``timeout``; everything else (HTTPStatusError, transport
    errors, unexpected exceptions) -> ``http_error``. Lumped because
    arXiv is a non-LLM transport and a finer split would force a new
    StepError literal without giving the operator a meaningfully
    different action.

    A clean miss (HTTP 200, zero entries) is not an error: it appends
    ``{tool: 'arxiv', query, outcome: 'no_results'}`` and returns ``[]``.
    """
    try:
        results = await search_arxiv(client, query)
    except Exception as exc:
        error_type = "timeout" if isinstance(exc, httpx.TimeoutException) else "http_error"
        logger.warning("arXiv search %s for %r: %s", error_type, query, exc)
        if errors_out is not None:
            errors_out.append(
                _research_err(
                    error_type,
                    f"arXiv search failed for query {query!r}: {exc}",
                )
            )
        return []

    if not results and tool_outcomes_out is not None:
        tool_outcomes_out.append(
            {"tool": "arxiv", "query": query, "outcome": "no_results"}
        )
    return results


async def _dispatch_one_query(
    client: httpx.AsyncClient,
    query: str,
    backend: str,
    errors_out: list[StepError] | None,
) -> tuple[list[dict], str]:
    """Run a single query against ``backend`` with per-query Brave fallback.

    Returns ``(results, origin_used)`` where ``origin_used`` is the
    backend that actually produced the results (so the acquisition
    trace reflects reality when Tavily falls back to Brave).

    The Tavily path falls back to Brave for that query when
    ``TAVILY_API_KEY`` is unset, when the call raises, or when Tavily
    is rate-limited. ``StepError(error_type="tavily_rate_limited")``
    is appended to ``errors_out`` so the orchestrator can surface the
    quota event without halting the run.
    """
    if backend == "tavily":
        try:
            results = await search_tavily(client, query)
            return results, "tavily"
        except TavilyRateLimitError as exc:
            logger.warning("Tavily rate-limited for %r; falling back to Brave", query)
            if errors_out is not None:
                errors_out.append(
                    _research_err(
                        "tavily_rate_limited",
                        f"Tavily rate-limited for query {query!r}: {exc}",
                    )
                )
        except RuntimeError as exc:
            # Most commonly: TAVILY_API_KEY is not set. We've already
            # logged that condition once at startup; per-query log is
            # debug to avoid noise across N queries.
            logger.debug("Tavily unavailable for %r (%s); falling back to Brave", query, exc)
        except Exception as exc:
            logger.warning("Tavily search failed for %r (%s); falling back to Brave", query, exc)

        # Per-query fallback to Brave. Stamp acquisition.origin="brave"
        # for these results so the audit trail shows the actual origin.
        results = await search_brave(client, query)
        return results, "brave"

    # Default / "brave" path.
    results = await search_brave(client, query)
    return results, "brave"


async def execute_searches(
    queries: list[str],
    client: httpx.AsyncClient,
    *,
    backend: str = "brave",
    extra_origins: list[str] | None = None,
    acquisition_out: dict[str, dict] | None = None,
    errors_out: list[StepError] | None = None,
    tool_outcomes_out: list[dict] | None = None,
) -> list[SearchCandidate]:
    """Fan out web searches for all queries; deduplicate by canonical URL.

    The dedup key is the canonical form (lowercased host, default ports
    stripped, sorted query, dropped tracking params and fragment) so
    obvious duplicates (``http`` vs ``https`` aside) collapse to one
    candidate. The original URL is preserved on the SearchCandidate.
    Unparseable URLs are skipped rather than raising.

    ``backend`` selects between ``"brave"`` (default) and ``"tavily"``
    for the always-on general-web spine. Unknown values log a warning
    and fall back to Brave. When the backend is ``"tavily"``, individual
    queries fall back to Brave on Tavily failures; the per-URL
    ``acquisition`` map records which backend actually produced each
    kept URL.

    ``extra_origins`` is the selector-decided list of academic origins
    (currently just ``"arxiv"``; Tier 2 will add ``"s2"`` and
    ``"openalex"``). They are dispatched alongside the general-web spine
    and merged into the same dedup'd candidate list. The first origin
    to contribute a URL claims its ``acquisition`` entry -- subsequent
    origins seeing the same canonical URL within the same call do not
    overwrite the entry (matches the "one acquisition per URL"
    invariant the audit sidecar relies on).

    When ``acquisition_out`` is provided, the dispatcher writes one
    entry per kept URL: ``{stage: "research", origin, query, ...}``.
    arXiv entries also carry ``paper_id``. The caller is the
    audit-sidecar producer (``decomposed_research``).

    When ``tool_outcomes_out`` is provided, per-tool clean misses
    (e.g., arXiv returns zero entries for a query) append
    ``{tool, query, outcome: 'no_results'}`` so the audit trail can
    distinguish "fired but found nothing" from "did not fire".
    """
    selected = backend
    if selected not in _KNOWN_BACKENDS:
        logger.warning(
            "Unknown RESEARCH_SEARCH_BACKEND=%r; falling back to 'brave'",
            selected,
        )
        selected = "brave"

    if selected == "tavily" and not os.environ.get("TAVILY_API_KEY"):
        # One log line at the boundary, not one per query.
        logger.warning(
            "RESEARCH_SEARCH_BACKEND=tavily but TAVILY_API_KEY is unset; "
            "every query will fall back to Brave"
        )

    extra = list(extra_origins or [])

    # General-web spine: one task per query, returning (items, origin_used).
    spine_tasks = [
        _dispatch_one_query(client, q, selected, errors_out) for q in queries
    ]

    # Academic origins: one task per (origin, query) returning a flat dict list
    # whose origin is known by position (academic_origin_by_index below).
    academic_tasks: list = []
    academic_origin_by_index: list[str] = []
    academic_query_by_index: list[str] = []
    for origin in extra:
        if origin == "arxiv":
            for q in queries:
                academic_tasks.append(
                    _dispatch_arxiv_one_query(
                        client, q, errors_out, tool_outcomes_out,
                    )
                )
                academic_origin_by_index.append(origin)
                academic_query_by_index.append(q)
        else:
            # Tier 2 will add s2/openalex; logging an unknown academic
            # origin keeps a typo from silently disabling academic
            # dispatch without surfacing a signal.
            logger.warning(
                "Unknown academic research origin %r; skipping", origin,
            )

    spine_results, academic_results = await asyncio.gather(
        asyncio.gather(*spine_tasks, return_exceptions=True),
        asyncio.gather(*academic_tasks, return_exceptions=True),
    )

    seen: set[str] = set()
    candidates: list[SearchCandidate] = []

    def _ingest_items(
        items: list[dict],
        query: str,
        origin: str,
    ) -> None:
        """Merge an origin's per-query results into ``candidates`` /
        ``acquisition_out`` under the shared dedup ``seen`` set."""
        for item in items:
            url = item.get("url", "")
            if not url:
                continue
            try:
                key = canonicalize(url)
            except ValueError as exc:
                logger.debug("Skipping unparseable URL %r: %s", url, exc)
                continue
            if key in seen:
                # First contributor wins. The acquisition entry already
                # stamped by an earlier origin (spine or another
                # academic origin within this call) is the authoritative
                # one for the audit trail.
                continue
            seen.add(key)
            candidates.append(SearchCandidate(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                from_query=query,
                publisher_quality=classify_url_publisher_quality(url),
                raw_content=item.get("raw_content"),
            ))
            if acquisition_out is not None:
                entry: dict = {
                    "stage": "research",
                    "origin": origin,
                    "query": query,
                }
                paper_id = item.get("paper_id")
                if paper_id:
                    entry["paper_id"] = paper_id
                acquisition_out[url] = entry

    # Spine first so it claims the acquisition slot for any URL also
    # surfaced by an academic origin in this call. (Within the same
    # call ordering is deterministic; across calls dispatch order is
    # by query, then tool within query, per the plan.)
    for query, result in zip(queries, spine_results):
        if isinstance(result, Exception):
            logger.warning("Search failed for query %r: %s", query, result)
            continue
        items, origin_used = result
        _ingest_items(items, query, origin_used)

    for idx, result in enumerate(academic_results):
        query = academic_query_by_index[idx]
        origin = academic_origin_by_index[idx]
        if isinstance(result, Exception):
            # _dispatch_arxiv_one_query already converts known transport
            # exceptions to StepError entries; reaching here means the
            # dispatcher itself blew up unexpectedly. Log and continue
            # so a single bad academic call doesn't stop the spine
            # results from being processed.
            logger.warning(
                "%s search dispatcher failed for query %r: %s",
                origin, query, result,
            )
            continue
        _ingest_items(result, query, origin)

    return candidates


async def decomposed_research(
    claim_text: str,
    entity_name: str,
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    resolved_entity: ResolvedEntity | None = None,
    topics: list[str] | None = None,
) -> ResearchOutput:
    """Run the 3-step decomposed researcher.

    Returns a ``ResearchOutput`` with the kept URLs, the sub-question
    decomposition, the per-URL ``addresses`` map, and a trace dict
    suitable for direct YAML serialisation into the audit sidecar's
    ``research:`` block. Trace fields are populated as each step
    succeeds; partial outputs are returned on early-exit error paths.
    """
    # Pre-init `acquisition` (url -> dict, grafted by _write_audit_sidecar)
    # and `tool_outcomes` so producers can append without checking presence.
    out = ResearchOutput(
        urls=[],
        trace={"mode": "decomposed", "acquisition": {}, "tool_outcomes": []},
    )

    entity_ctx = build_entity_context(resolved_entity, entity_name)
    planner_prompt = (
        f"{entity_ctx}"
        f"Claim: {claim_text}\n"
        f"Generate up to {cfg.max_initial_queries} search queries."
    )
    try:
        async with sem:
            with research_planner_agent.override(model=resolve_model(cfg.model_for("researcher"))):
                planner_res = await asyncio.wait_for(
                    research_planner_agent.run(planner_prompt),
                    timeout=cfg.research_timeout_s,
                )
        plan: ResearchPlan = planner_res.output
        out.sub_questions = list(plan.sub_questions)
        # Belt-and-suspenders: hard-truncate even if the model ignores the prompt cap
        planned = plan.queries[: cfg.max_initial_queries]
        queries = [pq.text for pq in planned]
        out.queries_by_sub_question = _group_queries_by_sq(planned)
        out.trace["queries"] = list(queries)
        out.trace["planner_rationale"] = plan.rationale
        logger.info(
            "Research planner: %d queries across %d sub-questions (rationale: %s)",
            len(queries), len(out.sub_questions), plan.rationale,
        )
    except asyncio.TimeoutError:
        out.errors.append(_research_err("timeout", "Research planner timed out"))
        return out
    except Exception as exc:
        out.errors.append(_research_err("model_error", str(exc)))
        logger.error("Research planner failed: %s", exc)
        return out

    if not queries:
        out.errors.append(_research_err("no_queries", "Research planner returned no queries"))
        return out

    extra_origins = _select_research_origins(cfg, list(topics or []))
    candidates = await execute_searches(
        queries,
        client,
        backend=cfg.search_backend,
        extra_origins=extra_origins,
        acquisition_out=out.trace["acquisition"],
        errors_out=out.errors,
        tool_outcomes_out=out.trace["tool_outcomes"],
    )
    out.trace["candidates_seen"] = len(candidates)
    logger.info("Search executor: %d unique candidates from %d queries", len(candidates), len(queries))

    if not candidates:
        out.errors.append(_research_err("no_results", "Search returned no results"))
        return out

    parent_name = resolve_parent_name(resolved_entity.parent_company if resolved_entity else None)
    entity_website = resolved_entity.website if resolved_entity else None
    avoid_topics = (
        list(resolved_entity.search_hints.exclude)
        if resolved_entity and resolved_entity.search_hints
        else []
    )
    scorer_prompt = build_scorer_prompt(
        entity_name,
        claim_text,
        candidates,
        out.sub_questions,
        parent_company=parent_name,
        website=entity_website,
        avoid=avoid_topics or None,
    )
    def _fallback_to_candidates() -> tuple[list[str], dict[str, list[str]]]:
        # Without scorer output we have no per-URL addresses; tag every
        # candidate as addressing every sub-question so downstream
        # invariants (non-empty addresses) still hold.
        fallback_addrs = [sq.id for sq in out.sub_questions] or ["sq1"]
        urls = [c.url for c in candidates]
        return urls, {url: list(fallback_addrs) for url in urls}

    raw_by_url: dict[str, str] = {
        c.url: c.raw_content for c in candidates if c.raw_content
    }

    def _commit(urls: list[str], addresses: dict[str, list[str]]) -> ResearchOutput:
        urls, addresses = _apply_entity_exclude(urls, addresses, avoid_topics, out.trace)
        out.urls = urls
        out.url_addresses = addresses
        out.prefetched_bodies = {u: raw_by_url[u] for u in urls if u in raw_by_url}
        return out

    try:
        async with sem:
            with url_scorer_agent.override(model=resolve_model(cfg.model_for("researcher"))):
                scorer_res = await asyncio.wait_for(
                    url_scorer_agent.run(scorer_prompt),
                    timeout=cfg.research_timeout_s,
                )
        scored: ScoredURLs = scorer_res.output
        out.trace["urls_kept"] = len(scored.kept)
        out.trace["urls_dropped"] = len(scored.dropped)
        out.trace["scorer_rationale"] = scored.rationale
        logger.info(
            "URL scorer: %d kept, %d dropped (rationale: %s)",
            len(scored.kept), len(scored.dropped), scored.rationale,
        )
        if not scored.kept and candidates:
            logger.warning("URL scorer dropped all %d candidates; returning empty", len(candidates))
            out.trace["scorer_dropped_all"] = True
            out.errors.append(_research_err("scorer_dropped_all", f"URL scorer dropped all {len(candidates)} candidates"))
            return out
        return _commit(
            [c.url for c in scored.kept],
            {c.url: list(c.addresses) for c in scored.kept},
        )
    except asyncio.TimeoutError:
        out.errors.append(_research_err("timeout", "URL scorer timed out"))
        return _commit(*_fallback_to_candidates())
    except Exception as exc:
        out.errors.append(_research_err("model_error", str(exc)))
        logger.error("URL scorer failed: %s", exc)
        return _commit(*_fallback_to_candidates())


def _group_queries_by_sq(planned) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for pq in planned:
        out.setdefault(pq.sub_question_id, []).append(pq.text)
    return out


def _apply_entity_exclude(
    urls: list[str],
    addresses: dict[str, list[str]],
    avoid: list[str],
    trace: dict,
) -> tuple[list[str], dict[str, list[str]]]:
    """Drop URLs whose host matches a domain-shaped entry in `avoid`.

    Topical avoid entries (free text without a `.`) are left to the LLM scorer.
    """
    domain_excludes = [a.strip().lower() for a in avoid if "." in a and " " not in a]
    if not domain_excludes:
        return urls, addresses
    entries = [BlocklistEntry(host=d, reason="entity_exclude") for d in domain_excludes]
    kept, dropped = filter_urls(urls, entries)
    if dropped:
        trace["entity_exclude_dropped"] = [d.url for d in dropped]
        logger.info(
            "Entity-exclude filter dropped %d URL(s): %s",
            len(dropped), [d.url for d in dropped],
        )
    return kept, {u: addresses[u] for u in kept if u in addresses}
