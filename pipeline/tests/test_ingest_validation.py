"""Key quotes are kept only when their text is on the fetched page."""

from __future__ import annotations

import pytest

from ingestor.models import SourceFile
from ingestor.validation import drop_unfound_quotes

_PAGE = (
    "Brave publishes a transparency report.\n"
    "Google will reach 100% renewable energy\nfor its data centers by 2030.\n"
    "Life is about making things, said Boris.\n"
)


def _source(quotes: list[str] | None) -> SourceFile:
    return SourceFile(
        frontmatter={
            "url": "https://example.com/report",
            "title": "Report",
            "publisher": "Example",
            "accessed_date": "2026-10-04",
            "kind": "report",
            "summary": "A report.",
            "key_quotes": quotes,
        },
        body="Body.",
        slug="report",
        year=2025,
    )


def _kept(quotes: list[str], page: str = _PAGE) -> list[str] | None:
    source = _source(quotes)
    drop_unfound_quotes(source, page)
    return source.frontmatter.key_quotes


def test_paraphrase_dropped() -> None:
    verbatim = "Brave publishes a transparency report."
    paraphrase = "Brave releases an annual transparency document."
    source = _source([verbatim, paraphrase])

    dropped = drop_unfound_quotes(source, _PAGE)

    assert source.frontmatter.key_quotes == [verbatim]
    assert dropped == [paraphrase]


def test_all_quotes_dropped_gives_none() -> None:
    source = _source(["Nothing like this is on the page."])
    drop_unfound_quotes(source, _PAGE)
    assert source.frontmatter.key_quotes is None


def test_no_quotes_is_a_no_op() -> None:
    source = _source(None)
    assert drop_unfound_quotes(source, _PAGE) == []
    assert source.frontmatter.key_quotes is None


@pytest.mark.parametrize(
    "quote",
    [
        '"Google will reach 100% renewable energy for its data centers by 2030."',
        "“Google will reach 100% renewable energy for its data centers by 2030.”",
        "'Brave publishes a transparency report.'",
        '"Brave publishes a transparency report".',
        '"Life is about making things" — Boris',
        '"Life is about making things" - Boris, interview',
        "«Brave publishes a transparency report.»",
    ],
    ids=["straight", "curly", "single", "trailing-period", "em-dash-tail", "hyphen-tail", "guillemets"],
)
def test_wrapped_verbatim_quote_kept(quote: str) -> None:
    assert _kept([quote]) == [quote]


def test_attribution_tail_dropped_when_inner_text_missing() -> None:
    assert _kept(['"Boris never said this" — Google report.']) is None


def test_text_after_closing_mark_that_is_not_attribution_uses_whole_string() -> None:
    # "and more" is not on the page, so the whole string does not match.
    assert _kept(['"Brave publishes a transparency report." and more']) is None


def test_single_opening_mark_is_matched_whole() -> None:
    assert _kept(['"Brave publishes']) is None
    assert _kept(['"Brave publishes'], page='Text: "Brave publishes a report.') == ['"Brave publishes']


@pytest.mark.parametrize(
    "quote, page",
    [
        ("Brave publishes a transparency report.", _PAGE),
        ("Brave publishes a transparency report.", "Brave publishes a transparency report."),
        ("a non-renewable grid", "on a non‑renewable grid"),
        ("a non‑renewable grid", "on a non-renewable grid"),
        ("the company’s “green” pledge", "the company's \"green\" pledge"),
        ("research & development", "Spend on research &amp; development rose."),
        ("Brave publishes a transparency report.", "**Brave publishes** a [transparency report](https://x.example)."),
        ("uses `renewable` power", "uses renewable power"),
        ("the renewable, low-carbon grid", "the\nrenewable\n, low-carbon grid"),
        ("BRAVE PUBLISHES a transparency report.", _PAGE),
    ],
    ids=[
        "nbsp-quote", "narrow-nbsp-page", "nb-hyphen-page", "nb-hyphen-quote", "curly-inside",
        "html-entity", "markdown-bold-link", "backticks", "punctuation-after-inline-tag", "case",
    ],
)
def test_normalized_match_kept(quote: str, page: str) -> None:
    assert _kept([quote], page) == [quote]


def test_ellipsis_excerpt_kept() -> None:
    quote = "Google will reach 100%…by 2030."
    assert _kept([quote]) == [quote]
    assert _kept(["Google will reach 100% ... data centers by 2030."]) == [
        "Google will reach 100% ... data centers by 2030."
    ]


def test_ellipsis_fragments_must_appear_in_order() -> None:
    assert _kept(["by 2030 ... Google will reach"]) is None


def test_trailing_ellipsis_paraphrase_dropped() -> None:
    assert _kept(["Google pledges to go fully green..."]) is None


@pytest.mark.parametrize("quote", ["", "   ", "...", '"…"'])
def test_quote_with_no_text_dropped(quote: str) -> None:
    assert _kept([quote]) is None


def test_kept_quote_string_unchanged() -> None:
    quote = '  "Brave publishes a transparency report."  '
    assert _kept([quote]) == [quote]
