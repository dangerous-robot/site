"""Tests for the decomposed researcher pipeline."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from researcher.planner import PlannedQuery, ResearchPlan, research_planner_agent
from researcher.scorer import ScoredCandidate, ScoredURLs, SearchCandidate, url_scorer_agent
from researcher.decomposed import execute_searches, decomposed_research
from orchestrator.checkpoints import StepError
from orchestrator.entity_resolution import ResolvedEntity
from common.models import BlockedReason, EntityType, SubQuestion


class _AgentResult:
    """Minimal stand-in for pydantic_ai RunResult when patching agent.run."""
    def __init__(self, output):
        self.output = output


def _stub_sub_questions() -> list[SubQuestion]:
    return [
        SubQuestion(id="sq1", question="First sub-question?", rationale="covers axis 1"),
        SubQuestion(id="sq2", question="Second sub-question?", rationale="covers axis 2"),
    ]


def _plan(queries: list[str], rationale: str = "ok") -> ResearchPlan:
    return ResearchPlan(
        sub_questions=_stub_sub_questions(),
        queries=[PlannedQuery(text=q, sub_question_id="sq1") for q in queries],
        rationale=rationale,
    )


def _make_cfg(
    max_initial_queries: int = 3,
    llm_concurrency: int = 8,
    max_sources: int = 12,
    research_timeout_s: float = 60.0,
):
    """Build a minimal VerifyConfig-like object for unit tests."""
    from orchestrator.pipeline import VerifyConfig
    return VerifyConfig(
        max_initial_queries=max_initial_queries,
        llm_concurrency=llm_concurrency,
        max_sources=max_sources,
        research_timeout_s=research_timeout_s,
    )


# --------------------------------------------------------------------------- #
# Test 1: Research planner output shape                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_research_planner_output_shape() -> None:
    with research_planner_agent.override(
        model=TestModel(
            custom_output_args={
                "sub_questions": [
                    {"id": "sq1", "question": "Q1?", "rationale": "axis 1"},
                    {"id": "sq2", "question": "Q2?", "rationale": "axis 2"},
                ],
                "queries": [
                    {"text": "q1", "sub_question_id": "sq1"},
                    {"text": "q2", "sub_question_id": "sq2"},
                ],
                "rationale": "test rationale",
            },
        )
    ):
        result = await research_planner_agent.run("test prompt")

    plan = result.output
    assert isinstance(plan, ResearchPlan)
    assert len(plan.queries) > 0
    assert len(plan.sub_questions) >= 2
    assert isinstance(plan.rationale, str)
    assert len(plan.rationale) > 0


# --------------------------------------------------------------------------- #
# Test 2: Research planner cap enforcement                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_research_planner_cap_enforcement() -> None:
    """decomposed_research must truncate to max_initial_queries even if the model
    returns more queries."""
    six_queries = [f"query_{i}" for i in range(6)]
    cfg = _make_cfg(max_initial_queries=3)

    six_plan = _plan(six_queries, "many queries")

    captured_queries: list[list[str]] = []

    async def fake_execute_searches(queries, client, **_kwargs):
        captured_queries.append(list(queries))
        return []

    with (
        patch.object(research_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(six_plan))),
        patch("researcher.decomposed.execute_searches", side_effect=fake_execute_searches),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            ro = await decomposed_research("test claim", "TestEntity", cfg, sem, client)
        kept = ro.urls
        errors = ro.errors

    # The planner returned 6 queries; hard-truncation must cap them at 3.
    assert len(captured_queries) == 1
    assert len(captured_queries[0]) == 3, (
        f"Expected 3 queries after truncation, got {len(captured_queries[0])}"
    )
    assert isinstance(kept, list)
    assert isinstance(errors, list)


# --------------------------------------------------------------------------- #
# Test 3: URL scorer output shape                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_url_scorer_output_shape() -> None:
    with url_scorer_agent.override(
        model=TestModel(
            custom_output_args={
                "kept": [{"url": "https://a.com", "addresses": ["sq1"]}],
                "dropped": ["https://b.com"],
                "rationale": "test scoring",
            },
        )
    ):
        result = await url_scorer_agent.run("test prompt")

    scored = result.output
    assert isinstance(scored, ScoredURLs)
    assert all(isinstance(c, ScoredCandidate) for c in scored.kept)
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
    """decomposed_research returns the scorer's kept ScoredCandidate list."""
    cfg = _make_cfg(max_initial_queries=3)

    fake_candidates = [
        SearchCandidate(url="https://a.com", title="A", snippet="a", from_query="q1"),
        SearchCandidate(url="https://b.com", title="B", snippet="b", from_query="q1"),
        SearchCandidate(url="https://c.com", title="C", snippet="c", from_query="q2"),
    ]
    kept = [
        ScoredCandidate(url="https://a.com", addresses=["sq1"]),
        ScoredCandidate(url="https://b.com", addresses=["sq1", "sq2"]),
    ]

    fake_plan = _plan(["q1", "q2"], "good queries")
    fake_scored = ScoredURLs(kept=kept, dropped=["https://c.com"], rationale="a and b are better")

    with (
        patch.object(research_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_plan))),
        patch.object(url_scorer_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_scored))),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            ro = await decomposed_research("test claim", "TestEntity", cfg, sem, client)

    assert isinstance(ro.urls, list)
    assert set(ro.urls) == {"https://a.com", "https://b.com"}
    assert ro.url_addresses["https://b.com"] == ["sq1", "sq2"]
    assert ro.errors == []


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

    fake_plan = _plan(["q1", "q2"], "ok")
    fake_scored = ScoredURLs(
        kept=[ScoredCandidate(url="https://x.com", addresses=["sq1"])],
        dropped=[],
        rationale="good",
    )
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
        patch.object(research_planner_agent, "run", side_effect=counting_planner_run),
        patch.object(url_scorer_agent, "run", side_effect=counting_scorer_run),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        await asyncio.gather(*[run_one() for _ in range(10)])

    assert max_concurrent <= 3, (
        f"Expected at most 3 concurrent LLM calls, observed {max_concurrent}"
    )


# --------------------------------------------------------------------------- #
# Item A tests: scorer fallback behavior                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_scorer_drops_all_returns_empty() -> None:
    """When the scorer returns kept=[], decomposed_research returns ([], errors, trace)
    with a scorer_dropped_all StepError and trace["scorer_dropped_all"] == True."""
    cfg = _make_cfg(max_initial_queries=3)

    fake_candidates = [
        SearchCandidate(url="https://a.com", title="A", snippet="a", from_query="q1"),
        SearchCandidate(url="https://b.com", title="B", snippet="b", from_query="q1"),
    ]
    fake_plan = _plan(["q1"], "ok")
    fake_scored = ScoredURLs(kept=[], dropped=["https://a.com", "https://b.com"], rationale="all irrelevant")

    with (
        patch.object(research_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_plan))),
        patch.object(url_scorer_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_scored))),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            ro = await decomposed_research("test claim", "TestEntity", cfg, sem, client)

    assert ro.urls == [], f"Expected empty urls list, got {ro.urls}"
    assert ro.trace.get("scorer_dropped_all") is True, "trace['scorer_dropped_all'] should be True"
    scorer_drop_errors = [e for e in ro.errors if e.error_type == "scorer_dropped_all"]
    assert len(scorer_drop_errors) == 1, f"Expected one scorer_dropped_all error, got {scorer_drop_errors}"
    assert "2" in scorer_drop_errors[0].message, "Error message should reference candidate count"


@pytest.mark.asyncio
async def test_scorer_drops_all_sets_blocked_reason() -> None:
    """When _research returns an empty ResearchOutput with scorer_dropped_all,
    verify_claim sets blocked_reason=INSUFFICIENT_SOURCES."""
    from orchestrator.pipeline import verify_claim, VerifyConfig
    from researcher.decomposed import ResearchOutput

    scorer_error = StepError(step="research", error_type="scorer_dropped_all", message="URL scorer dropped all 5 candidates")
    empty = ResearchOutput(urls=[], errors=[scorer_error], trace={})

    async def _fake_research(*args, **kwargs):
        return empty

    with patch("orchestrator.pipeline._research", side_effect=_fake_research):
        result = await verify_claim("TestEntity", "test claim", VerifyConfig())

    assert result.blocked_reason == BlockedReason.INSUFFICIENT_SOURCES, (
        f"Expected INSUFFICIENT_SOURCES, got {result.blocked_reason}"
    )


# --------------------------------------------------------------------------- #
# Item C tests: parent_company injected into prompts                            #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_parent_company_injected_into_prompts() -> None:
    """When resolved_entity has parent_company='companies/anthropic', both the
    planner prompt and scorer prompt should contain 'Anthropic' (not the raw ref)."""
    cfg = _make_cfg(max_initial_queries=2)

    resolved = ResolvedEntity(
        entity_ref="products/claude",
        entity_name="Claude",
        entity_type=EntityType.PRODUCT,
        entity_description="An AI assistant by Anthropic",
        parent_company="companies/anthropic",
    )

    fake_candidates = [
        SearchCandidate(url="https://anthropic.com/claude", title="Claude", snippet="info", from_query="q1"),
    ]
    fake_plan = _plan(["q1", "q2"], "ok")
    fake_scored = ScoredURLs(
        kept=[ScoredCandidate(url="https://anthropic.com/claude", addresses=["sq1"])],
        dropped=[],
        rationale="relevant",
    )

    captured: dict = {}

    async def capture_planner(prompt, *args, **kwargs):
        captured["planner"] = prompt
        return _AgentResult(fake_plan)

    async def capture_scorer(prompt, *args, **kwargs):
        captured["scorer"] = prompt
        return _AgentResult(fake_scored)

    with (
        patch.object(research_planner_agent, "run", side_effect=capture_planner),
        patch.object(url_scorer_agent, "run", side_effect=capture_scorer),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            await decomposed_research("test claim", "Claude", cfg, sem, client, resolved_entity=resolved)

    assert "Anthropic" in captured.get("planner", ""), (
        f"'Anthropic' not found in planner prompt: {captured.get('planner', '')!r}"
    )
    assert "Anthropic" in captured.get("scorer", ""), (
        f"'Anthropic' not found in scorer prompt: {captured.get('scorer', '')!r}"
    )
    assert "companies/anthropic" not in captured.get("planner", ""), "Raw ref should not appear in planner prompt"
    assert "companies/anthropic" not in captured.get("scorer", ""), "Raw ref should not appear in scorer prompt"


# --------------------------------------------------------------------------- #
# Item B tests: publisher quality hints                                         #
# --------------------------------------------------------------------------- #

def test_forum_domain_scores_low() -> None:
    """classify_url_publisher_quality returns 'forum' for a Reddit URL."""
    from common.publisher_quality import classify_url_publisher_quality
    result = classify_url_publisher_quality("https://reddit.com/r/MachineLearning/comments/abc123")
    assert result == "forum", f"Expected 'forum', got {result!r}"


# --------------------------------------------------------------------------- #
# Entity-exclude post-scorer filter (search_hints.exclude domain entries)      #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_entity_exclude_drops_matching_domain_post_scorer() -> None:
    """A URL kept by the LLM scorer is still dropped when its host matches
    a domain-shaped entry in resolved_entity.search_hints.exclude."""
    from orchestrator.entity_resolution import SearchHints

    cfg = _make_cfg(max_initial_queries=2)
    resolved = ResolvedEntity(
        entity_ref="companies/treadlightlyai",
        entity_name="TreadLightly AI",
        entity_type=EntityType.COMPANY,
        entity_description="AI thinking tool.",
        website="https://treadlightly.ai",
        search_hints=SearchHints(include=[], exclude=["treadlightly.org", "off-roading"]),
    )

    fake_candidates = [
        SearchCandidate(url="https://treadlightly.ai/about", title="Canonical", snippet="", from_query="q1"),
        SearchCandidate(url="https://treadlightly.org/team", title="Wrong entity", snippet="", from_query="q1"),
    ]
    fake_plan = _plan(["q1"], "ok")
    fake_scored = ScoredURLs(
        kept=[
            ScoredCandidate(url="https://treadlightly.ai/about", addresses=["sq1"]),
            ScoredCandidate(url="https://treadlightly.org/team", addresses=["sq1"]),
        ],
        dropped=[],
        rationale="LLM didn't catch the collision",
    )

    with (
        patch.object(research_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_plan))),
        patch.object(url_scorer_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_scored))),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            ro = await decomposed_research(
                "test claim", "TreadLightly AI", cfg, sem, client, resolved_entity=resolved,
            )

    assert ro.urls == ["https://treadlightly.ai/about"]
    assert "https://treadlightly.org/team" not in ro.url_addresses
    assert ro.trace.get("entity_exclude_dropped") == ["https://treadlightly.org/team"]


@pytest.mark.asyncio
async def test_website_and_avoid_render_in_scorer_prompt() -> None:
    """When resolved_entity has website + search_hints.exclude, both surface in the
    scorer prompt as disambiguation anchors."""
    from orchestrator.entity_resolution import SearchHints

    cfg = _make_cfg(max_initial_queries=2)
    resolved = ResolvedEntity(
        entity_ref="companies/treadlightlyai",
        entity_name="TreadLightly AI",
        entity_type=EntityType.COMPANY,
        entity_description="AI thinking tool.",
        website="https://treadlightly.ai",
        search_hints=SearchHints(include=[], exclude=["treadlightly.org"]),
    )
    fake_candidates = [
        SearchCandidate(url="https://x.example", title="x", snippet="x", from_query="q1"),
    ]
    fake_plan = _plan(["q1"], "ok")
    fake_scored = ScoredURLs(
        kept=[ScoredCandidate(url="https://x.example", addresses=["sq1"])],
        dropped=[],
        rationale="ok",
    )

    captured: dict = {}

    async def capture_scorer(prompt, *args, **kwargs):
        captured["scorer"] = prompt
        return _AgentResult(fake_scored)

    with (
        patch.object(research_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_plan))),
        patch.object(url_scorer_agent, "run", side_effect=capture_scorer),
        patch("researcher.decomposed.execute_searches", new=AsyncMock(return_value=fake_candidates)),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            await decomposed_research(
                "test claim", "TreadLightly AI", cfg, sem, client, resolved_entity=resolved,
            )

    prompt = captured.get("scorer", "")
    assert "Official website: https://treadlightly.ai" in prompt
    assert "treadlightly.org" in prompt


def test_primary_domain_classification() -> None:
    """classify_url_publisher_quality returns 'primary' for anthropic.com."""
    from common.publisher_quality import classify_url_publisher_quality
    result = classify_url_publisher_quality("https://anthropic.com/news/something")
    assert result == "primary", f"Expected 'primary', got {result!r}"


def test_publisher_quality_in_scorer_prompt() -> None:
    """build_scorer_prompt includes publisher_quality in the per-candidate text."""
    from researcher.scorer import build_scorer_prompt

    candidates = [
        SearchCandidate(url="https://reddit.com/r/ml/abc", title="Reddit post", snippet="discussion", from_query="q1", publisher_quality="forum"),
        SearchCandidate(url="https://anthropic.com/paper", title="Anthropic paper", snippet="research", from_query="q1", publisher_quality="primary"),
    ]
    prompt = build_scorer_prompt("TestEntity", "test claim", candidates, _stub_sub_questions())
    assert "publisher_quality" not in prompt.lower() or "Publisher quality:" in prompt, \
        "Expected the literal 'Publisher quality:' label in prompt"
    assert "Publisher quality: forum" in prompt, f"Expected 'Publisher quality: forum' in prompt:\n{prompt}"
    assert "Publisher quality: primary" in prompt, f"Expected 'Publisher quality: primary' in prompt:\n{prompt}"


# --------------------------------------------------------------------------- #
# Search-backend dispatch (RESEARCH_SEARCH_BACKEND)                             #
# --------------------------------------------------------------------------- #


class TestSearchBackendDispatch:
    """`execute_searches(..., backend=...)` routes to Brave or Tavily.

    Mirrors the contract laid out in
    ``docs/plans/source-pool-expansion-tier1-search-backend.md``.
    """

    @pytest.mark.asyncio
    async def test_default_backend_calls_brave(self) -> None:
        """No env var, no kw-arg: Brave is called; Tavily is not."""
        brave_results = [{"url": "https://b.example", "title": "B", "snippet": "from-brave"}]
        with (
            patch("researcher.decomposed.search_brave", new=AsyncMock(return_value=brave_results)) as brave_mock,
            patch("researcher.decomposed.search_tavily", new=AsyncMock(return_value=[])) as tavily_mock,
        ):
            async with httpx.AsyncClient() as client:
                candidates = await execute_searches(["q1"], client)
        assert brave_mock.await_count == 1
        assert tavily_mock.await_count == 0
        assert [c.url for c in candidates] == ["https://b.example"]

    @pytest.mark.asyncio
    async def test_tavily_backend_calls_tavily(self, monkeypatch) -> None:
        """`backend='tavily'` routes through search_tavily and stamps origin."""
        monkeypatch.setenv("TAVILY_API_KEY", "k")
        tavily_results = [{"url": "https://t.example", "title": "T", "snippet": "from-tavily"}]
        acquisition: dict[str, dict] = {}
        with (
            patch("researcher.decomposed.search_brave", new=AsyncMock(return_value=[])) as brave_mock,
            patch("researcher.decomposed.search_tavily", new=AsyncMock(return_value=tavily_results)) as tavily_mock,
        ):
            async with httpx.AsyncClient() as client:
                candidates = await execute_searches(
                    ["q1"], client, backend="tavily", acquisition_out=acquisition,
                )
        assert tavily_mock.await_count == 1
        assert brave_mock.await_count == 0
        assert [c.url for c in candidates] == ["https://t.example"]
        assert acquisition == {
            "https://t.example": {"stage": "research", "origin": "tavily", "query": "q1"},
        }

    @pytest.mark.asyncio
    async def test_unknown_backend_falls_back_to_brave(self) -> None:
        """An unrecognized value logs and uses Brave; doesn't crash the pipeline."""
        brave_results = [{"url": "https://b.example", "title": "B", "snippet": "ok"}]
        with (
            patch("researcher.decomposed.search_brave", new=AsyncMock(return_value=brave_results)) as brave_mock,
            patch("researcher.decomposed.search_tavily", new=AsyncMock(return_value=[])) as tavily_mock,
        ):
            async with httpx.AsyncClient() as client:
                candidates = await execute_searches(["q1"], client, backend="duckduckgo")
        assert brave_mock.await_count == 1
        assert tavily_mock.await_count == 0
        assert candidates and candidates[0].url == "https://b.example"

    @pytest.mark.asyncio
    async def test_tavily_failure_falls_back_to_brave_per_query(self, monkeypatch) -> None:
        """Tavily raising for one query: Brave is called for that query.
        The acquisition entry records the actual origin (`brave`)."""
        monkeypatch.setenv("TAVILY_API_KEY", "k")
        brave_results = [{"url": "https://b.example", "title": "B", "snippet": "fallback"}]
        acquisition: dict[str, dict] = {}
        with (
            patch(
                "researcher.decomposed.search_tavily",
                new=AsyncMock(side_effect=RuntimeError("simulated outage")),
            ),
            patch(
                "researcher.decomposed.search_brave",
                new=AsyncMock(return_value=brave_results),
            ) as brave_mock,
        ):
            async with httpx.AsyncClient() as client:
                candidates = await execute_searches(
                    ["q1"], client, backend="tavily", acquisition_out=acquisition,
                )
        # Brave handled the fallback; acquisition reflects that.
        assert brave_mock.await_count == 1
        assert [c.url for c in candidates] == ["https://b.example"]
        assert acquisition == {
            "https://b.example": {"stage": "research", "origin": "brave", "query": "q1"},
        }

    @pytest.mark.asyncio
    async def test_tavily_rate_limit_emits_step_error_and_falls_back(self, monkeypatch) -> None:
        """A TavilyRateLimitError appends a `tavily_rate_limited` StepError
        and falls back to Brave for that query."""
        from researcher.tools.tavily import TavilyRateLimitError

        monkeypatch.setenv("TAVILY_API_KEY", "k")
        brave_results = [{"url": "https://b.example", "title": "B", "snippet": "fallback"}]
        errors: list[StepError] = []
        with (
            patch(
                "researcher.decomposed.search_tavily",
                new=AsyncMock(side_effect=TavilyRateLimitError("limit hit")),
            ),
            patch(
                "researcher.decomposed.search_brave",
                new=AsyncMock(return_value=brave_results),
            ),
        ):
            async with httpx.AsyncClient() as client:
                candidates = await execute_searches(
                    ["q1"], client, backend="tavily", errors_out=errors,
                )
        assert [c.url for c in candidates] == ["https://b.example"]
        rate_errs = [e for e in errors if e.error_type == "tavily_rate_limited"]
        assert len(rate_errs) == 1
        assert rate_errs[0].step == "research"

    @pytest.mark.asyncio
    async def test_tavily_with_no_api_key_falls_back(self, monkeypatch) -> None:
        """`backend='tavily'` with no key: every query falls back to Brave."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        brave_results = [{"url": "https://b.example", "title": "B", "snippet": "ok"}]

        # search_tavily raises RuntimeError("TAVILY_API_KEY is not set")
        async def _real_tavily(*args, **kwargs):
            raise RuntimeError("TAVILY_API_KEY is not set")

        acquisition: dict[str, dict] = {}
        with (
            patch("researcher.decomposed.search_tavily", new=AsyncMock(side_effect=_real_tavily)),
            patch("researcher.decomposed.search_brave", new=AsyncMock(return_value=brave_results)) as brave_mock,
        ):
            async with httpx.AsyncClient() as client:
                candidates = await execute_searches(
                    ["q1", "q2"], client, backend="tavily", acquisition_out=acquisition,
                )
        # Both queries fell back to Brave.
        assert brave_mock.await_count == 2
        # All acquisition entries must reflect Brave as origin.
        assert candidates  # non-empty
        for entry in acquisition.values():
            assert entry["origin"] == "brave"


class TestVerifyConfigSearchBackend:
    """`VerifyConfig.search_backend` reads RESEARCH_SEARCH_BACKEND at construction."""

    def test_default_is_tavily(self, monkeypatch) -> None:
        monkeypatch.delenv("RESEARCH_SEARCH_BACKEND", raising=False)
        from orchestrator.pipeline import VerifyConfig
        assert VerifyConfig().search_backend == "tavily"

    def test_env_var_overrides_default(self, monkeypatch) -> None:
        monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", "brave")
        from orchestrator.pipeline import VerifyConfig
        assert VerifyConfig().search_backend == "brave"

    def test_explicit_kwarg_wins(self, monkeypatch) -> None:
        """Explicit kwarg should beat the env var (tests can pin behavior)."""
        monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", "brave")
        from orchestrator.pipeline import VerifyConfig
        assert VerifyConfig(search_backend="tavily").search_backend == "tavily"


@pytest.mark.asyncio
async def test_decomposed_research_writes_acquisition_trace() -> None:
    """`decomposed_research` populates `out.trace["acquisition"]` with one
    `{stage, origin, query}` entry per kept URL. Load-bearing for the
    audit-sidecar graft in `_write_audit_sidecar`."""
    cfg = _make_cfg(max_initial_queries=2)

    async def fake_execute(queries, client, *, backend, acquisition_out, errors_out):
        # Simulate the dispatcher writing into acquisition_out.
        acquisition_out["https://a.com"] = {"stage": "research", "origin": backend, "query": queries[0]}
        acquisition_out["https://b.com"] = {"stage": "research", "origin": backend, "query": queries[0]}
        return [
            SearchCandidate(url="https://a.com", title="A", snippet="a", from_query=queries[0]),
            SearchCandidate(url="https://b.com", title="B", snippet="b", from_query=queries[0]),
        ]

    fake_plan = _plan(["q1"], "ok")
    fake_scored = ScoredURLs(
        kept=[
            ScoredCandidate(url="https://a.com", addresses=["sq1"]),
            ScoredCandidate(url="https://b.com", addresses=["sq1"]),
        ],
        dropped=[],
        rationale="all good",
    )
    with (
        patch.object(research_planner_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_plan))),
        patch.object(url_scorer_agent, "run", new=AsyncMock(return_value=_AgentResult(fake_scored))),
        patch("researcher.decomposed.execute_searches", side_effect=fake_execute),
    ):
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient() as client:
            ro = await decomposed_research("test claim", "TestEntity", cfg, sem, client)

    acquisition = ro.trace.get("acquisition")
    assert isinstance(acquisition, dict)
    assert acquisition["https://a.com"] == {"stage": "research", "origin": "tavily", "query": "q1"}
    assert acquisition["https://b.com"] == {"stage": "research", "origin": "tavily", "query": "q1"}
