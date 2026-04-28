"""Decomposed researcher pipeline: planner -> search executor -> URL scorer."""
from __future__ import annotations

import asyncio
import logging

import httpx

from common.models import resolve_model
from orchestrator.checkpoints import StepError
from researcher.agent import search_brave
from researcher.planner import QueryPlan, query_planner_agent
from researcher.scorer import SearchCandidate, ScoredURLs, url_scorer_agent

logger = logging.getLogger(__name__)


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
                ))
    return candidates


async def decomposed_research(
    claim_text: str,
    entity_name: str,
    cfg,  # VerifyConfig — imported locally to avoid circular imports
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
) -> tuple[list[str], list[StepError]]:
    """Run the 3-step decomposed researcher and return (urls, errors)."""
    errors: list[StepError] = []

    # Step 1: Query Planner (LLM call, guarded by semaphore)
    planner_prompt = (
        f"Entity: {entity_name or '(unknown)'}\n"
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
        logger.info("Query planner: %d queries (rationale: %s)", len(queries), plan.rationale)
    except asyncio.TimeoutError:
        errors.append(StepError(step="research", error_type="timeout", message="Query planner timed out"))
        return [], errors
    except Exception as exc:
        errors.append(StepError(step="research", error_type="model_error", message=str(exc)))
        logger.error("Query planner failed: %s", exc)
        return [], errors

    if not queries:
        errors.append(StepError(step="research", error_type="no_queries", message="Query planner returned no queries"))
        return [], errors

    # Step 2: Search Executor (pure HTTP, no semaphore)
    candidates = await execute_searches(queries, client)
    logger.info("Search executor: %d unique candidates from %d queries", len(candidates), len(queries))

    if not candidates:
        errors.append(StepError(step="research", error_type="no_results", message="Search returned no results"))
        return [], errors

    # Step 3: URL Scorer (LLM call, guarded by semaphore)
    candidate_text = "\n".join(
        f"URL: {c.url}\nTitle: {c.title}\nSnippet: {c.snippet}\n"
        for c in candidates
    )
    scorer_prompt = (
        f"Entity: {entity_name or '(unknown)'}\n"
        f"Claim: {claim_text}\n\n"
        f"Candidates:\n{candidate_text}"
    )
    try:
        async with sem:
            with url_scorer_agent.override(model=resolve_model(cfg.model_for("researcher"))):
                scorer_res = await asyncio.wait_for(
                    url_scorer_agent.run(scorer_prompt),
                    timeout=cfg.research_timeout_s,
                )
        scored: ScoredURLs = scorer_res.output
        logger.info(
            "URL scorer: %d kept, %d dropped (rationale: %s)",
            len(scored.kept), len(scored.dropped), scored.rationale,
        )
        return scored.kept, errors
    except asyncio.TimeoutError:
        errors.append(StepError(step="research", error_type="timeout", message="URL scorer timed out"))
        # Fall back to all candidates rather than returning nothing
        return [c.url for c in candidates], errors
    except Exception as exc:
        errors.append(StepError(step="research", error_type="model_error", message=str(exc)))
        logger.error("URL scorer failed: %s", exc)
        return [c.url for c in candidates], errors
