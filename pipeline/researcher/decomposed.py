"""Decomposed researcher pipeline: planner -> search executor -> URL scorer."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict, Field

from common.blocklist import BlocklistEntry, filter_urls
from common.canonical_url import canonicalize
from common.models import SubQuestion, resolve_model
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

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _research_err(error_type: str, message: str) -> StepError:
    return StepError(step="research", error_type=error_type, message=message)


async def execute_searches(
    queries: list[str],
    client: httpx.AsyncClient,
) -> list[SearchCandidate]:
    """Fan out Brave searches for all queries; deduplicate by canonical URL.

    The dedup key is the canonical form (lowercased host, default ports
    stripped, sorted query, dropped tracking params and fragment) so
    obvious duplicates (``http`` vs ``https`` aside) collapse to one
    candidate. The original URL is preserved on the SearchCandidate.
    Unparseable URLs are skipped rather than raising.
    """
    raw_results = await asyncio.gather(
        *[search_brave(client, q) for q in queries],
        return_exceptions=True,
    )
    seen: set[str] = set()
    candidates: list[SearchCandidate] = []
    for query, result in zip(queries, raw_results):
        if isinstance(result, Exception):
            logger.warning("Search failed for query %r: %s", query, result)
            continue
        for item in result:
            url = item.get("url", "")
            if not url:
                continue
            try:
                key = canonicalize(url)
            except ValueError as exc:
                logger.debug("Skipping unparseable URL %r: %s", url, exc)
                continue
            if key in seen:
                continue
            seen.add(key)
            candidates.append(SearchCandidate(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                from_query=query,
                publisher_quality=classify_url_publisher_quality(url),
            ))
    return candidates


async def decomposed_research(
    claim_text: str,
    entity_name: str,
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    resolved_entity: ResolvedEntity | None = None,
) -> ResearchOutput:
    """Run the 3-step decomposed researcher.

    Returns a ``ResearchOutput`` with the kept URLs, the sub-question
    decomposition, the per-URL ``addresses`` map, and a trace dict
    suitable for direct YAML serialisation into the audit sidecar's
    ``research:`` block. Trace fields are populated as each step
    succeeds; partial outputs are returned on early-exit error paths.
    """
    # `acquisition` is a per-URL map (url -> acquisition payload) consumed by
    # `_write_audit_sidecar` and grafted onto matching `sources_consulted[]`
    # entries. `tool_outcomes` is a runtime "tool fired but found nothing"
    # log (arxiv_no_results, edgar_no_match, …). Both are pre-initialized so
    # producers landing in later commits can append without checking presence.
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

    candidates = await execute_searches(queries, client)
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

    def _commit(urls: list[str], addresses: dict[str, list[str]]) -> ResearchOutput:
        urls, addresses = _apply_entity_exclude(urls, addresses, avoid_topics, out.trace)
        out.urls = urls
        out.url_addresses = addresses
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
