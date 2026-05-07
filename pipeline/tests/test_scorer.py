"""Tests for the URL scorer's sub-question awareness."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from common.models import SubQuestion
from researcher.scorer import (
    ScoredCandidate,
    ScoredURLs,
    SearchCandidate,
    build_scorer_prompt,
    url_scorer_agent,
)


def _sub_questions() -> list[SubQuestion]:
    return [
        SubQuestion(id="sq1", question="Does the entity publish energy data?", rationale="first-party axis"),
        SubQuestion(id="sq2", question="Do third-party ESG sources profile the entity?", rationale="independent axis"),
        SubQuestion(id="sq3", question="Which provider hosts the models?", rationale="mechanism axis"),
    ]


def _candidates() -> list[SearchCandidate]:
    return [
        SearchCandidate(url="https://entity.example.com/transparency", title="Transparency report", snippet="Entity 2025 transparency report energy", from_query="q1"),
        SearchCandidate(url="https://esg-aggregator.example.com/entity", title="ESG aggregator profile", snippet="Independent ESG database profile of Entity", from_query="q2"),
        SearchCandidate(url="https://hosting.example.com/blog/entity", title="Cloud provider profile", snippet="Cloud hosting case study for Entity inference", from_query="q3"),
        SearchCandidate(url="https://news.example.com/dual", title="Dual-axis news article", snippet="News coverage with both ESG profile and cloud hosting details", from_query="q2"),
        SearchCandidate(url="https://random.example.com/recipes", title="Random off-topic", snippet="Pasta recipes for weeknight dinners", from_query="q4"),
        SearchCandidate(url="https://forum.example.com/discussion", title="Forum thread", snippet="Reddit discussion about Entity infrastructure", from_query="q3"),
    ]


@pytest.mark.asyncio
async def test_scorer_keeps_per_sub_question_addresses() -> None:
    """Each kept candidate's `addresses` list reflects which sub-questions it serves."""
    candidates = _candidates()
    sub_questions = _sub_questions()

    fixture = {
        "kept": [
            {"url": candidates[0].url, "addresses": ["sq1"]},
            {"url": candidates[1].url, "addresses": ["sq2"]},
            {"url": candidates[2].url, "addresses": ["sq3"]},
            {"url": candidates[3].url, "addresses": ["sq2", "sq3"]},
        ],
        "dropped": [candidates[4].url, candidates[5].url],
        "rationale": "Off-topic and forum posts excluded; news article addresses two axes.",
    }

    with url_scorer_agent.override(model=TestModel(custom_output_args=fixture)):
        prompt = build_scorer_prompt("Entity", "Entity discloses energy", candidates, sub_questions)
        result = await url_scorer_agent.run(prompt)

    scored: ScoredURLs = result.output
    by_url = {c.url: c for c in scored.kept}

    assert by_url[candidates[0].url].addresses == ["sq1"]
    assert by_url[candidates[1].url].addresses == ["sq2"]
    assert by_url[candidates[2].url].addresses == ["sq3"]
    assert by_url[candidates[3].url].addresses == ["sq2", "sq3"]

    for kept in scored.kept:
        assert isinstance(kept, ScoredCandidate)
        assert kept.addresses, "kept candidates must carry at least one sub-question id"
        for addr in kept.addresses:
            assert addr in {sq.id for sq in sub_questions}

    assert candidates[4].url in scored.dropped
    assert candidates[5].url in scored.dropped


def test_build_scorer_prompt_renders_sub_question_block() -> None:
    sub_questions = _sub_questions()
    candidates = _candidates()[:1]
    prompt = build_scorer_prompt("Entity", "test claim", candidates, sub_questions)

    assert "Sub-questions:" in prompt
    for sq in sub_questions:
        assert sq.id in prompt
        assert sq.question in prompt
    # Candidate listing still renders
    assert candidates[0].url in prompt
