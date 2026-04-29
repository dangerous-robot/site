"""Targeted live tests and one full-pipeline smoke test.

Stage tests (query_planner, scorer, analyst) call the LLM directly with
controlled inputs -- no web search, no fetch. Only ANTHROPIC_API_KEY required.

The smoke test requires both ANTHROPIC_API_KEY and BRAVE_WEB_SEARCH_API_KEY.

Model selection mirrors the CLI: DR_MODEL sets the base model for all agents;
DR_RESEARCHER_MODEL, DR_ANALYST_MODEL, DR_AUDITOR_MODEL, DR_INGESTOR_MODEL
override per-agent. Values are loaded from .env before tests run.

Run with: uv run pytest -m acceptance
Skipped by default in plain `uv run pytest`.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from analyst.agent import analyst_agent, build_analyst_prompt
from common.models import DEFAULT_MODEL, Confidence, Verdict, resolve_model
from orchestrator.checkpoints import AutoApproveCheckpointHandler
from orchestrator.pipeline import VerifyConfig, verify_claim
from researcher.planner import query_planner_agent
from researcher.scorer import SearchCandidate, build_scorer_prompt, url_scorer_agent

load_dotenv()

_has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
_has_all_keys = bool(_has_anthropic and os.environ.get("BRAVE_WEB_SEARCH_API_KEY"))

_skip_stage = pytest.mark.skipif(not _has_anthropic, reason="ANTHROPIC_API_KEY not set")
_skip_e2e = pytest.mark.skipif(
    not _has_all_keys,
    reason="ANTHROPIC_API_KEY and BRAVE_WEB_SEARCH_API_KEY required",
)


def _cfg_from_env(**overrides) -> VerifyConfig:
    """Build a VerifyConfig from DR_* env vars, mirroring CLI model selection.

    Keyword overrides take precedence over env-var defaults.
    """
    defaults: dict = dict(
        model=os.environ.get("DR_MODEL", DEFAULT_MODEL),
        researcher_model=os.environ.get("DR_RESEARCHER_MODEL"),
        analyst_model=os.environ.get("DR_ANALYST_MODEL"),
        auditor_model=os.environ.get("DR_AUDITOR_MODEL"),
        ingestor_model=os.environ.get("DR_INGESTOR_MODEL"),
    )
    defaults.update(overrides)
    return VerifyConfig(**defaults)


def _stage_model():
    """Model for stage tests (scorer, planner, analyst).

    Uses DR_STAGE_MODEL if set, otherwise DEFAULT_MODEL. Stage tests require
    structured output support -- don't inherit DR_RESEARCHER_MODEL or
    DR_ANALYST_MODEL, which may be set to models that don't support it.
    """
    return resolve_model(os.environ.get("DR_STAGE_MODEL", DEFAULT_MODEL))


# ---------------------------------------------------------------------------
# Stage: url_scorer_agent
# ---------------------------------------------------------------------------


@pytest.mark.acceptance
@_skip_stage
async def test_scorer_obvious_split() -> None:
    """Scorer puts clearly relevant candidates in kept and off-topic ones in dropped."""
    entity = "Google"
    claim = "Google publicly reports annual greenhouse gas emissions"

    relevant = [
        SearchCandidate(
            url="https://sustainability.google/reports/2023/",
            title="Google 2023 Environmental Report",
            snippet="Annual greenhouse gas emissions and carbon reduction targets for Google operations.",
            from_query="q1",
        ),
        SearchCandidate(
            url="https://alphabet.com/sustainability",
            title="Alphabet Sustainability Commitments",
            snippet="Detailed breakdown of Alphabet CO2 emissions and renewable energy procurement.",
            from_query="q1",
        ),
    ]
    irrelevant = [
        SearchCandidate(
            url="https://recipes.example.com/pasta",
            title="Best Italian Pasta Recipes",
            snippet="Easy weeknight dinner ideas for the whole family.",
            from_query="q2",
        ),
        SearchCandidate(
            url="https://sports.example.com/scores",
            title="Today's Sports Scores",
            snippet="Latest results from the NFL, NBA, and MLB.",
            from_query="q2",
        ),
    ]
    all_candidates = relevant + irrelevant

    prompt = build_scorer_prompt(entity, claim, all_candidates)

    with url_scorer_agent.override(model=_stage_model()):
        result = await url_scorer_agent.run(prompt)

    scored = result.output
    all_returned = set(scored.kept) | set(scored.dropped)
    all_input = {c.url for c in all_candidates}
    assert all_input == all_returned, f"URLs missing from output: {all_input - all_returned}"

    for c in relevant:
        assert c.url in scored.kept, f"Expected {c.url!r} in kept, got kept={scored.kept}"
    for c in irrelevant:
        assert c.url in scored.dropped, f"Expected {c.url!r} in dropped, got dropped={scored.dropped}"


# ---------------------------------------------------------------------------
# Stage: query_planner_agent
# ---------------------------------------------------------------------------


@pytest.mark.acceptance
@_skip_stage
async def test_query_planner_structure() -> None:
    """Query planner returns entity-grounded, non-duplicate queries with a rationale."""
    entity = "Google"
    claim = "Google publicly reports annual greenhouse gas emissions in a sustainability report"
    prompt = (
        f"Entity: {entity}\n"
        f"Claim: {claim}\n"
        "Generate up to 4 search queries."
    )

    with query_planner_agent.override(model=_stage_model()):
        result = await query_planner_agent.run(prompt)

    plan = result.output
    assert len(plan.queries) >= 2, f"Expected >= 2 queries, got {len(plan.queries)}"
    assert len(plan.queries) == len(set(plan.queries)), "Duplicate queries returned"
    assert plan.rationale.strip(), "Rationale is empty"

    entity_terms = {"google", "alphabet"}
    for q in plan.queries:
        assert any(t in q.lower() for t in entity_terms), (
            f"Query not entity-grounded: {q!r}"
        )


# ---------------------------------------------------------------------------
# Stage: analyst_agent -- unambiguous false verdict
# ---------------------------------------------------------------------------


@pytest.mark.acceptance
@_skip_stage
async def test_analyst_false_from_unambiguous_source() -> None:
    """Analyst returns false+high when a canned source directly contradicts the claim."""
    claim = "ExampleCorp runs all inference on 100% renewable energy"
    sources = [
        {
            "title": "ExampleCorp Annual Report 2024",
            "publisher": "ExampleCorp",
            "summary": "Details ExampleCorp data center energy sourcing.",
            "key_quotes": [
                "All ExampleCorp data centers operate exclusively on coal and natural gas.",
                "The company has no renewable energy procurement agreements in place.",
                "No net-zero or carbon-neutral commitments have been made.",
            ],
            "body": (
                "ExampleCorp Annual Report 2024: Energy & Infrastructure.\n\n"
                "All data center operations rely entirely on coal and natural gas supplied "
                "by regional utilities. ExampleCorp has not entered any power purchase "
                "agreements for renewable energy and has made no public commitments toward "
                "carbon neutrality or renewable energy procurement."
            ),
        }
    ]

    prompt = build_analyst_prompt("ExampleCorp", claim, sources)
    with analyst_agent.override(model=_stage_model()):
        result = await analyst_agent.run(prompt)

    out = result.output
    assert out.verdict.verdict == Verdict.FALSE, (
        f"Expected false, got {out.verdict.verdict!r}"
    )
    assert out.verdict.confidence == Confidence.HIGH, (
        f"Expected high confidence, got {out.verdict.confidence!r}"
    )


# ---------------------------------------------------------------------------
# Full pipeline smoke test
# ---------------------------------------------------------------------------


@pytest.mark.acceptance
@_skip_e2e
async def test_full_pipeline_false_claim_smoke() -> None:
    """A knowingly false claim should not produce a true or mostly-true verdict.

    Anthropic does not exclusively use models trained on 100% renewable energy.
    Assertions are loose: pipeline completes, finds sources, and doesn't call
    the claim true.
    """
    result = await verify_claim(
        entity_name="Anthropic",
        claim_text=(
            "Anthropic only uses models that were trained on 100% renewable energy"
        ),
        config=_cfg_from_env(max_sources=3),
        checkpoint=AutoApproveCheckpointHandler(),
    )

    assert not result.errors, f"Pipeline errors: {result.errors}"
    assert len(result.urls_found) > 0, "Research found no URLs"
    assert len(result.urls_ingested) > 0, "No sources ingested"
    assert result.analyst_output is not None, "No analyst output"
    assert result.analyst_output.verdict.verdict not in (
        Verdict.TRUE,
        Verdict.MOSTLY_TRUE,
    ), f"False claim rated as true: {result.analyst_output.verdict.verdict}"
