"""Tests for analyst.citations.clean_citations."""

from __future__ import annotations

from analyst.citations import clean_citations

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
