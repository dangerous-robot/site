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


_GOOGLE = "Google will reach 100% renewable energy for its data centers by 2030."
_BRAVE = "Brave publishes a transparency report."


@pytest.mark.parametrize(
    "quote, stored",
    [
        (f'"{_GOOGLE}"', _GOOGLE),
        (f"\u201c{_GOOGLE}\u201d", _GOOGLE),
        (f"'{_BRAVE}'", _BRAVE),
        (f"\u2018{_BRAVE}\u2019", _BRAVE),
        ('"Brave publishes a transparency report".', "Brave publishes a transparency report"),
        ('"Life is about making things" \u2014 Boris', "Life is about making things"),
        ('"Life is about making things" - Boris, interview', "Life is about making things"),
        (f"\u00ab{_BRAVE}\u00bb", _BRAVE),
        (f'  "{_BRAVE}"  ', _BRAVE),
    ],
    ids=[
        "straight", "curly", "single", "single-curly", "trailing-period", "em-dash-tail",
        "hyphen-tail", "guillemets", "surrounding-space",
    ],
)
def test_wrapped_verbatim_quote_stored_bare(quote: str, stored: str) -> None:
    assert _kept([quote]) == [stored]


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


def test_bare_kept_quote_string_unchanged() -> None:
    quote = "  Brave publishes a transparency report.  "
    assert _kept([quote]) == [quote]


def test_unwrapped_quote_keeps_its_original_characters() -> None:
    # Folding turns the ellipsis into three periods; the stored text must not.
    assert _kept(["\u201cGoogle will reach 100%\u2026by 2030.\u201d"]) == [
        "Google will reach 100%\u2026by 2030."
    ]


@pytest.mark.parametrize(
    "quote",
    ["Google will reach [...] by 2030.", "Google will reach […] by 2030.", "Google will reach (...) by 2030."],
    ids=["brackets", "brackets-ellipsis-char", "parentheses"],
)
def test_bracketed_elision_kept(quote: str) -> None:
    assert _kept([quote], "Google will reach net zero by 2030.") == [quote]


def test_short_edge_fragment_kept_when_another_has_two_words() -> None:
    assert _kept(["Google [...] by 2030."], "Google will reach net zero by 2030.") == [
        "Google [...] by 2030."
    ]


@pytest.mark.parametrize(
    "quote, page",
    [
        ("AWS ... renewable ... 2025", "AWS sells cloud. Wind is renewable. In 2025 prices rose."),
        ("AWS ... 2025", "AWS sells cloud. In 2025 prices rose."),
        (
            "Google will reach ... by 2030.",
            "Google will reach new markets. " + "Filler text here. " * 20 + "Emissions fall by 2030.",
        ),
    ],
    ids=["one-word-interior-fragment", "one-word-fragments", "elided-text-too-long"],
)
def test_ellipsis_quote_stitched_from_scattered_words_dropped(quote: str, page: str) -> None:
    assert _kept([quote], page) is None


def test_ellipsis_match_uses_the_nearest_start() -> None:
    # The first "Google will reach" is too far from "by 2030."; the second is not.
    page = "Google will reach new markets. " + "Filler text here. " * 20 + "Google will reach net zero by 2030."
    assert _kept(["Google will reach ... by 2030."], page) == ["Google will reach ... by 2030."]


@pytest.mark.parametrize(
    "quote, page",
    [
        ("renewable energy for its data centers", "renewable energy for its *data centers* by 2030"),
        ("data_center plan", "the data\\_center plan"),
        ("its data centers run on wind", "its data centers ![a wind farm](https://x.example/w.png)run on wind"),
        ("emissions fell -5%", "emissions fell −5%"),
        ("total CO2 emissions", "total CO\n2\nemissions"),
    ],
    ids=["single-emphasis", "escaped-underscore", "image", "unicode-minus", "word-split-by-inline-tag"],
)
def test_more_normalized_matches_kept(quote: str, page: str) -> None:
    assert _kept([quote], page) == [quote]


@pytest.mark.parametrize(
    "quote",
    [
        "“Google will reach 100% renewable energy\"",
        "„Brave publishes a transparency report.“",
        "‘Brave publishes a transparency report.'",
    ],
    ids=["curly-open-straight-close", "german-low-9", "single-curly-open-straight-close"],
)
def test_mismatched_or_unlisted_quotation_marks_unwrapped(quote: str) -> None:
    assert _kept([quote]) == [quote[1:-1]]


@pytest.mark.parametrize(
    "quote, page",
    [("the rapist", "the therapist said"), ("rapist said", "the therapist said")],
    ids=["across-word-boundary", "inside-word"],
)
def test_quote_does_not_match_across_or_inside_words(quote: str, page: str) -> None:
    assert _kept([quote], page) is None


def test_inner_quoted_phrase_does_not_block_unwrapping() -> None:
    page = 'They sell the so-called "green" cloud to buyers.'
    assert _kept(['"The so-called "green" cloud"'], page) == ['The so-called "green" cloud']


def test_apostrophe_does_not_block_unwrapping() -> None:
    page = "We're talking about it. So said Alex."
    assert _kept(["'We're talking about it.' \u2014 Alex"], page) == ["We're talking about it."]


@pytest.mark.parametrize(
    "quote, page",
    [
        ('"Green" is our motto, they say "always"', 'Our line: "Green" is our motto, they say "always".'),
        ("\u201cGreen\u201d is our motto, they say \u201calways\u201d", 'Our line: "Green" is our motto, they say "always".'),
        ('"Silent diffusion" of AI energy use', 'The "Silent diffusion" of AI energy use grows.'),
        ('"Brave publishes', 'Text: "Brave publishes a report.'),
    ],
    ids=["outer-marks-belong-to-page-text", "curly-outer-marks-belong-to-page-text", "no-closing-pair", "opening-mark-only"],
)
def test_quote_whose_page_text_starts_with_a_mark_kept_as_is(quote: str, page: str) -> None:
    assert _kept([quote], page) == [quote]


def test_quote_kept_as_is_when_its_characters_hold_no_mark_pair() -> None:
    # The entity-encoded marks fold to a pair, so the quote matches on its
    # inner text, but the stored characters hold no mark to strip.
    quote = "&quot;Brave publishes a transparency report.&quot;"
    assert _kept([quote]) == [quote]
