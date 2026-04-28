"""Tests for the decomposed researcher pipeline."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from researcher.agent import ResearchResult, research_agent
from researcher.planner import QueryPlan, query_planner_agent
from researcher.scorer import SearchCandidate, ScoredURLs, url_scorer_agent
from researcher.decomposed import execute_searches, decomposed_research


class _AgentResult:
    """Minimal stand-in for pydantic_ai RunResult when patching agent.run."""
    def __init__(self, output):
        self.output = output


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _make_cfg(
    researcher_mode: str = "decomposed",
    max_initial_queries: int = 3,
    llm_concurrency: int = 8,
    max_sources: int = 12,
    research_timeout_s: float = 60.0,
):
    """Build a minimal VerifyConfig-like object for unit tests."""
    from orchestrator.pipeline import VerifyConfig
    return VerifyConfig(
        researcher_mode=researcher_mode,
        max_initial_queries=max_initial_queries,
        llm_concurrency=llm_concurrency,
        max_sources=max_sources,
        research_timeout_s=research_timeout_s,
    )


# --------------------------------------------------------------------------- #
# Test 1: Query planner output shape                                            #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_query_planner_output_shape() -> None:
    with query_planner_agent.override(
        model=TestModel(
            custom_output_args={"queries": ["q1", "q2"], "rationale": "test rationale"},
        )
    ):
        result = await query_planner_agent.run("test prompt")

    plan = result.output
    assert isinstance(plan, QueryPlan)
    assert isinstance(plan.queries, list)
    assert len(plan.queries) > 0
    assert isinstance(plan.rationale, str)
    assert len(plan.rationale) > 0


# --------------------------------------------------------------------------- #
# Test 2: Query planner cap enforcement (hard-truncation in decomposed_research)#
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_query_planner_cap_enforcement() -> None:
    """decomposed_research must truncate to max_initial_queries even if the model
    returns more queries."""
    six_queries = [f"query_{i}" for i in range(6)]
    cfg = _make_cfg(max_initial_queries=3)

    six_plan = QueryPlan(queries=six_queries, rationale="many queries")

    # Track how many queries were passed to execute_searches.
    captured_queries: list[list[str]] = []

    async def fake_execute_searches(queries, client):
        captured_queries.append(list(queries))
        return []  # no candidates; keeps the test focused on truncation

    with (
        patch.object(query_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(six_plan))),
        patch("researcher.decomposed.execute_searches", side_effect=fake_execute_searches),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            urls, errors, _trace = await decomposed_research("test claim", "TestEntity", cfg, sem, client)

    # The planner returned 6 queries; hard-truncation must cap them at 3.
    assert len(captured_queries) == 1
    assert len(captured_queries[0]) == 3, (
        f"Expected 3 queries after truncation, got {len(captured_queries[0])}"
    )
    assert isinstance(urls, list)
    assert isinstance(errors, list)


# --------------------------------------------------------------------------- #
# Test 3: URL scorer output shape                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_url_scorer_output_shape() -> None:
    with url_scorer_agent.override(
        model=TestModel(
            custom_output_args={
                "kept": ["https://a.com"],
                "dropped": ["https://b.com"],
                "rationale": "test scoring",
            },
        )
    ):
        result = await url_scorer_agent.run("test prompt")

    scored = result.output
    assert isinstance(scored, ScoredURLs)
    assert isinstance(scored.kept, list)
    assert isinstance(scored.dropped, list)
    assert isinstance(scored.rationale, str)
    assert len(scored.rationale) > 0


# --------------------------------------------------------------------------- #
# Test 4: execute_searches deduplication                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_execute_searches_deduplication() -> None:
    """Same URL returned by two queries appears only once in the result."""
    shared_result = [{"url": "https://shared.com/article", "title": "Shared", "snippet": "snippet"}]

    with patch("researcher.decomposed.search_brave", new=AsyncMock(return_value=shared_result)):
        async with httpx.AsyncClient() as client:
            candidates = await execute_searches(["q1", "q2"], client)

    assert len(candidates) == 1
    assert candidates[0].url == "https://shared.com/article"
    assert isinstance(candidates[0], SearchCandidate)


# --------------------------------------------------------------------------- #
# Test 5: decomposed_research step sequencing                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_decomposed_research_step_sequencing() -> None:
    """decomposed_research returns a list[str] of kept URLs from the scorer."""
    cfg = _make_cfg(max_initial_queries=3)

    fake_candidates = [
        SearchCandidate(url="https://a.com", title="A", snippet="a", from_query="q1"),
        SearchCandidate(url="https://b.com", title="B", snippet="b", from_query="q1"),
        SearchCandidate(url="https://c.com", title="C", snippet="c", from_query="q2"),
    ]
    kept_urls = ["https://a.com", "https://b.com"]

    # decomposed_research applies its own agent.override internally, so patch .run directly.
    fake_plan = QueryPlan(queries=["q1", "q2"], rationale="good queries")
    fake_scored = ScoredURLs(kept=kept_urls, dropped=["https://c.com"], rationale="a and b are better")

    with (
        patch.object(query_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_plan))),
        patch.object(url_scorer_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_scored))),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            urls, errors, _trace = await decomposed_research("test claim", "TestEntity", cfg, sem, client)

    assert isinstance(urls, list)
    assert all(isinstance(u, str) for u in urls)
    assert set(urls) == set(kept_urls)
    assert errors == []


# --------------------------------------------------------------------------- #
# Test 6: Semaphore bounds concurrency                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_semaphore_bounds_concurrency() -> None:
    """No more than 3 LLM calls (planner + scorer) execute simultaneously
    when using Semaphore(3) across 10 concurrent decomposed_research calls."""
    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    fake_plan = QueryPlan(queries=["q1", "q2"], rationale="ok")
    fake_scored = ScoredURLs(kept=["https://x.com"], dropped=[], rationale="good")
    fake_candidates = [
        SearchCandidate(url="https://x.com", title="X", snippet="x", from_query="q1"),
    ]

    async def counting_planner_run(*args, **kwargs):
        nonlocal max_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent
        await asyncio.sleep(0.05)  # hold so concurrent entries overlap
        async with lock:
            current_concurrent -= 1
        return _AgentResult(fake_plan)

    async def counting_scorer_run(*args, **kwargs):
        nonlocal max_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent
        await asyncio.sleep(0.05)
        async with lock:
            current_concurrent -= 1
        return _AgentResult(fake_scored)

    cfg = _make_cfg(max_initial_queries=2)
    sem = asyncio.Semaphore(3)

    async def run_one():
        async with httpx.AsyncClient() as client:
            return await decomposed_research("claim", "Entity", cfg, sem, client)

    with (
        patch.object(query_planner_agent, "run", side_effect=counting_planner_run),
        patch.object(url_scorer_agent, "run", side_effect=counting_scorer_run),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        await asyncio.gather(*[run_one() for _ in range(10)])

    assert max_concurrent <= 3, (
        f"Expected at most 3 concurrent LLM calls, observed {max_concurrent}"
    )


# --------------------------------------------------------------------------- #
# Test 7: Classic researcher still importable and intact                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_existing_researcher_tests_still_pass() -> None:
    """research_agent and ResearchResult remain importable; output_type is correct."""
    assert research_agent.output_type is ResearchResult
