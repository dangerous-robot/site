"""Tests for analyst.citations.clean_citations."""

from __future__ import annotations

import re
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from analyst.agent import VerdictAssessment, verdict_only_agent
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


def test_singular_source_takes_one_number() -> None:
    text, unresolved = clean_citations(
        "Per Source 1, 3 data centers run on coal.", _sources(3)
    )
    assert text == "Per *Title 1*, 3 data centers run on coal."
    assert unresolved == []


def test_singular_source_followed_by_year() -> None:
    text, unresolved = clean_citations("Per Source 2, 2024 emissions rose.", _sources(3))
    assert text == "Per *Title 2*, 2024 emissions rose."
    assert unresolved == []


@pytest.mark.parametrize("title", ["Open Source 1 Report", "Source 1 Report"])
def test_inserted_title_not_rescanned(title: str) -> None:
    sources = [{"title": title, "source_id": "2026/report"}, {"title": "Other"}]
    text, unresolved = clean_citations("A finding【2026/report】.", sources)
    assert text == f"A finding (*{title}*)."
    assert unresolved == []


def test_lowercase_sources_list() -> None:
    text, unresolved = clean_citations("as sources 2 and 4 show", _sources())
    assert text == "as *Title 2* and *Title 4* show"
    assert unresolved == []


@pytest.mark.parametrize(
    "prose",
    ["the source 2 weeks ago said", "built on open source 2.0 tools", "one of the sources 3 years on"],
)
def test_lowercase_prose_untouched(prose: str) -> None:
    text, unresolved = clean_citations(prose, _sources())
    assert text == prose
    assert unresolved == []


def test_resources_not_matched() -> None:
    text, unresolved = clean_citations("water resources 2 and 3 are scarce", _sources())
    assert text == "water resources 2 and 3 are scarce"
    assert unresolved == []


def _verdict(**overrides) -> VerdictAssessment:
    args = {
        "title": "Brave hosts on renewable energy",
        "verdict": "unverified",
        "confidence": "low",
        "narrative": "A narrative.",
        "topics": ["environmental-impact"],
        "verification_level": "claimed",
        "seo_title": "Brave renewable hosting claim",
    }
    args.update(overrides)
    return VerdictAssessment(**args)


@pytest.mark.parametrize("field", ["takeaway", "cap_rationale"])
@pytest.mark.parametrize("text", ["See Source 1.", "Only the company's pages address it【2026/source-1】."])
def test_short_fields_reject_citations(field: str, text: str) -> None:
    with pytest.raises(ValidationError, match="without citing sources"):
        _verdict(**{field: text})


@pytest.mark.parametrize("field", ["takeaway", "cap_rationale"])
@pytest.mark.parametrize("text", ["Only the company's own pages address the claim.", "It runs on an open Source 3D printer."])
def test_short_fields_accept_clean_text(field: str, text: str) -> None:
    assert getattr(_verdict(**{field: text}), field) == text


# --- T5: _analyse_claim returns a cleaned narrative -------------------------


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
            "seo_title": "Brave renewable hosting claim",
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
    assert "【" not in narrative
    assert not re.search(r"Source\s+1", narrative)
    assert narrative == "Brave says so (*Title 1*) and *Title 1* agrees."
