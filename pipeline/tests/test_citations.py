"""Tests for analyst.citations.clean_citations."""

from __future__ import annotations

import re
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel

from analyst.agent import verdict_only_agent
from analyst.citations import clean_citations
from common.models import EntityType
from orchestrator.entity_resolution import ResolvedEntity
from orchestrator.pipeline import VerifyConfig, _analyse_claim

NBSP = " "


def _sources(n: int = 6) -> list[dict]:
    return [
        {"title": f"Title {i}", "source_id": f"2026/source-{i}", "slug": f"source-{i}"}
        for i in range(1, n + 1)
    ]


def test_bracket_token_replaced_with_title() -> None:
    sources = [{"title": "2025 AI Safety Index", "source_id": "2025/ai-safety-index-summer-2025"}]
    text, unresolved = clean_citations(
        "...or lower【2025/ai-safety-index-summer-2025】.", sources
    )
    assert text == "...or lower (*2025 AI Safety Index*)."
    assert "【" not in text
    assert unresolved == []


def test_adjacent_bracket_tokens() -> None:
    text, unresolved = clean_citations(
        "same report and the article【2026/source-1】【2026/source-2】.", _sources()
    )
    assert text == "same report and the article (*Title 1* and *Title 2*)."
    assert unresolved == []


def test_unknown_bracket_id_removed_and_reported() -> None:
    text, unresolved = clean_citations("A finding【2026/nope】.", _sources())
    assert text == "A finding."
    assert unresolved == ["【2026/nope】"]


def test_source_n_with_nbsp() -> None:
    text, unresolved = clean_citations(f"as reported in Source{NBSP}1.", _sources())
    assert text == "as reported in *Title 1*."
    assert unresolved == []


def test_source_n_colon_title_keeps_one_title() -> None:
    sources = [{"title": "Where are Brave's sync servers located?", "source_id": "2026/sync"}]
    text, unresolved = clean_citations(
        "(Source 1: *Where are Brave's sync servers located?*)", sources
    )
    assert text == "(*Where are Brave's sync servers located?*)"
    assert unresolved == []


def test_sources_list() -> None:
    text, unresolved = clean_citations(
        "renewable (Sources 2, 4); Sources 6 and 7 disagree.", _sources(7)
    )
    assert text == "renewable (*Title 2* and *Title 4*); *Title 6* and *Title 7* disagree."
    assert unresolved == []


def test_out_of_range_left_and_reported() -> None:
    text, unresolved = clean_citations("see Source 9 and Sources 4, 8.", _sources(6))
    assert text == "see Source 9 and Sources 4, 8."
    assert unresolved == ["Source 9", "Sources 4, 8"]


def test_open_source_3d_untouched() -> None:
    text, unresolved = clean_citations("an open Source 3D printer", _sources())
    assert text == "an open Source 3D printer"
    assert unresolved == []


# --- T5: _analyse_claim returns cleaned narrative and takeaway --------------


@contextmanager
def _noop_ctx():
    yield


@pytest.mark.asyncio
async def test_analyse_claim_returns_clean_narrative(tmp_path) -> None:
    sources = [
        {**s, "publisher": "Example", "summary": "A page.", "url": f"https://example.org/{s['slug']}"}
        for s in _sources(2)
    ]
    model = TestModel(
        custom_output_args={
            "title": "Brave hosts on renewable energy",
            "verdict": "unverified",
            "confidence": "low",
            "narrative": f"Brave says so【2026/source-1】 and Source{NBSP}1 agrees.",
            "topics": ["environmental-impact"],
            "verification_level": "claimed",
            "cap_rationale": "Only the company's own pages address the claim.",
            "seo_title": "Brave renewable hosting claim",
            "takeaway": "See Source 1.",
        }
    )
    resolved = ResolvedEntity(
        entity_ref="products/brave-browser",
        entity_name="Brave Browser",
        entity_type=EntityType.PRODUCT,
        entity_description="",
    )
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path))

    with verdict_only_agent.override(model=model):
        # Keep our TestModel: neutralize the orchestrator's own override.
        with patch(
            "orchestrator.pipeline.verdict_only_agent.override",
            side_effect=lambda **kw: _noop_ctx(),
        ):
            out, failure = await _analyse_claim(
                "Brave Browser", "Brave is hosted on renewable energy", sources, cfg,
                resolved_entity=resolved,
            )

    assert failure is None
    narrative = out.verdict.narrative
    takeaway = out.verdict.takeaway
    for text in (narrative, takeaway):
        assert "【" not in text
        assert not re.search(r"Source\s+1", text)
    assert narrative == "Brave says so (*Title 1*) and *Title 1* agrees."
    assert takeaway == "See *Title 1*."
