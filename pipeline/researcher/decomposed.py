"""Decomposed researcher pipeline: planner -> search executor -> URL scorer."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from common.models import resolve_model
from common.publisher_quality import classify_url_publisher_quality
from orchestrator.checkpoints import StepError
from orchestrator.entity_resolution import ResolvedEntity, build_entity_context, _resolve_parent_name
from researcher.agent import search_brave
from researcher.planner import QueryPlan, query_planner_agent
from researcher.scorer import SearchCandidate, ScoredURLs, build_scorer_prompt, url_scorer_agent

if TYPE_CHECKING:
    from orchestrator.pipeline import VerifyConfig

logger = logging.getLogger(__name__)


def _research_err(error_type: str, message: str) -> StepError:
    return StepError(step="research", error_type=error_type, message=message)


async def execute_searches(
    queries: list[str],
    client: httpx.AsyncClient,
) -> list[SearchCandidate]:
    """Fan out Brave searches for all queries; deduplicate by exact URL string."""
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
            if url and url not in seen:
                seen.add(url)
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
) -> tuple[list[str], list[StepError], dict]:
    """Run the 3-step decomposed researcher.

    Returns ``(urls, errors, trace)`` where ``trace`` is a dict suitable
    for direct YAML serialisation into the audit sidecar's ``research:``
    block. Trace fields are populated as each step succeeds; partial
    traces are returned on early-exit error paths.
    """
    errors: list[StepError] = []
    trace: dict = {"mode": "decomposed"}

    entity_ctx = build_entity_context(resolved_entity, entity_name)
    planner_prompt = (
        f"{entity_ctx}"
        f"Claim: {claim_text}\n"
        f"Generate up to {cfg.max_initial_queries} search queries."
    )
    try:
        async with sem:
            with query_planner_agent.override(model=resolve_model(cfg.model_for("researcher"))):
                planner_res = await asyncio.wait_for(
                    query_planner_agent.run(planner_prompt),
                    timeout=cfg.research_timeout_s,
                )
        plan: QueryPlan = planner_res.output
        # Belt-and-suspenders: hard-truncate even if the model ignores the prompt cap
        queries = plan.queries[: cfg.max_initial_queries]
        trace["queries"] = list(queries)
        trace["planner_rationale"] = plan.rationale
        logger.info("Query planner: %d queries (rationale: %s)", len(queries), plan.rationale)
    except asyncio.TimeoutError:
        errors.append(_research_err("timeout", "Query planner timed out"))
        return [], errors, trace
    except Exception as exc:
        errors.append(_research_err("model_error", str(exc)))
        logger.error("Query planner failed: %s", exc)
        return [], errors, trace

    if not queries:
        errors.append(_research_err("no_queries", "Query planner returned no queries"))
        return [], errors, trace

    candidates = await execute_searches(queries, client)
    trace["candidates_seen"] = len(candidates)
    logger.info("Search executor: %d unique candidates from %d queries", len(candidates), len(queries))

    if not candidates:
        errors.append(_research_err("no_results", "Search returned no results"))
        return [], errors, trace

    parent_name = _resolve_parent_name(resolved_entity.parent_company if resolved_entity else None)
    scorer_prompt = build_scorer_prompt(entity_name, claim_text, candidates, parent_company=parent_name)
    try:
        async with sem:
            with url_scorer_agent.override(model=resolve_model(cfg.model_for("researcher"))):
                scorer_res = await asyncio.wait_for(
                    url_scorer_agent.run(scorer_prompt),
                    timeout=cfg.research_timeout_s,
                )
        scored: ScoredURLs = scorer_res.output
        trace["urls_kept"] = len(scored.kept)
        trace["urls_dropped"] = len(scored.dropped)
        trace["scorer_rationale"] = scored.rationale
        logger.info(
            "URL scorer: %d kept, %d dropped (rationale: %s)",
            len(scored.kept), len(scored.dropped), scored.rationale,
        )
        if not scored.kept and candidates:
            logger.warning("URL scorer dropped all %d candidates; returning empty", len(candidates))
            trace["scorer_dropped_all"] = True
            errors.append(_research_err("scorer_dropped_all", f"URL scorer dropped all {len(candidates)} candidates"))
            return [], errors, trace
        return scored.kept, errors, trace
    except asyncio.TimeoutError:
        errors.append(_research_err("timeout", "URL scorer timed out"))
        # Fall back to all candidates rather than returning nothing
        return [c.url for c in candidates], errors, trace
    except Exception as exc:
        errors.append(_research_err("model_error", str(exc)))
        logger.error("URL scorer failed: %s", exc)
        return [c.url for c in candidates], errors, trace
