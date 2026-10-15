"""Post-generation semantic validation for ingestor output."""

from __future__ import annotations

import datetime
import html
import re
import unicodedata
from dataclasses import dataclass, field

from ingestor.models import SourceFile


@dataclass
class ValidationResult:
    """Collects validation warnings and errors."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def validate_source_file(
    source: SourceFile,
    input_url: str,
    repo_root: str,
) -> ValidationResult:
    """Run semantic checks on an ingestor-produced SourceFile.

    Args:
        source: The agent output.
        input_url: The URL the user originally provided.
        repo_root: Path to the repo root.
    """
    result = ValidationResult()

    _check_url_match(source, input_url, result)
    _check_slug_format(source, result)
    _check_year_plausibility(source, result)
    _check_archived_url_domain(source, result)

    return result


def _check_url_match(
    source: SourceFile, input_url: str, result: ValidationResult
) -> None:
    if source.frontmatter.url != input_url:
        result.errors.append(
            f"URL mismatch: output '{source.frontmatter.url}' != input '{input_url}'"
        )


def _check_slug_format(source: SourceFile, result: ValidationResult) -> None:
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", source.slug):
        result.errors.append(f"Invalid slug format: '{source.slug}'")


def _check_year_plausibility(source: SourceFile, result: ValidationResult) -> None:
    current_year = datetime.date.today().year
    if not (2000 <= source.year <= current_year):
        result.errors.append(
            f"Year {source.year} outside plausible range (2000-{current_year})"
        )


def _check_archived_url_domain(source: SourceFile, result: ValidationResult) -> None:
    url = source.frontmatter.archived_url
    if url and not url.startswith("https://web.archive.org"):
        result.errors.append(
            f"archived_url domain must be web.archive.org, got: {url}"
        )


# Quotation marks are folded to the two ASCII marks before a quote is
# unwrapped, so a mismatched pair (curly open, straight close) or a German
# low-9 pair still unwraps.
_QUOTE_MARKS = ('"', "'")
# What may follow a quote's closing mark and still leave only the marked text
# claimed verbatim: nothing, a trailing period or comma, or a dash attribution.
# Dashes are already folded to "-" when this runs.
_AFTER_CLOSING_MARK = re.compile(r"^[.,]?\s*$|^\s*-{1,2}\s*\S")
# An ellipsis, bare or in brackets ("[...]", "(...)"); NFKC has already
# turned the ellipsis character into three periods.
_ELISION = re.compile(r"\s*[\[(]?\s*\.\.\.\s*[\])]?\s*")
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|<>~])")
_MARKDOWN_EMPHASIS = re.compile(r"[*_`]")
_WORD = re.compile(r"\w")
_CHAR_MAP = str.maketrans({
    **{c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"},
    **{c: "'" for c in "\u2018\u2019\u201a\u201b\u2039\u203a"},
    **{c: '"' for c in "\u201c\u201d\u201e\u201f\u00ab\u00bb"},
})
# A quote with an ellipsis must read as one excerpt, not words picked from
# across the page: the elided page text is capped, every fragment between two
# ellipses needs this many words, and one fragment needs at least two.
_MAX_ELIDED_CHARS = 300
_MIN_INTERIOR_FRAGMENT_WORDS = 3

# The passage the review packet prints beside a found quote: the sentence or
# sentences holding the match plus this much context on each side, cut at
# word boundaries and never longer than the cap.
PASSAGE_CONTEXT_CHARS = 120
PASSAGE_MAX_CHARS = 600

NOT_FOUND_REASON = "not found in the fetched page text"
TOO_FAR_APART_REASON = "ellipsis fragments too far apart"


@dataclass(frozen=True)
class QuoteCheck:
    """One key quote checked against the page text it claims to come from.

    ``text`` is the quote as it is kept (wrapping marks removed, see
    ``_unwrapped``) when found, else as given. ``passage`` is the page's own
    text around the match; ``reason`` says why a quote was not found.
    """

    text: str
    found: bool
    passage: str | None = None
    reason: str | None = None


def check_quote(quote: str, page_text: str) -> QuoteCheck:
    """The one quote rule: whether ``quote`` is on ``page_text``, and where.

    The ingest check (``apply_quote_checks``), the restater's evidence
    check (``quote_in_text``) and the review packet all read this.
    """
    return check_quotes([quote], page_text, with_passage=True)[0]


def quote_in_text(quote: str, text: str) -> bool:
    """``check_quote(quote, text).found``, without building the passage."""
    return check_quotes([quote], text)[0].found


def apply_quote_checks(source: SourceFile, page_text: str, *, with_passage: bool = False) -> list[QuoteCheck]:
    """Check each key quote against the page, keep the found ones, and return every check.

    Sets ``key_quotes`` to the kept quotes, or None when none are kept; a
    source with no key quotes is left as it is. A kept quote wrapped in
    quotation marks, with or without an attribution after the closing mark,
    is stored as the text inside the marks (see ``_unwrapped``).
    """
    quotes = source.frontmatter.key_quotes or []
    if not quotes:
        return []
    checks = check_quotes(quotes, page_text, with_passage=with_passage)
    source.frontmatter.key_quotes = [c.text for c in checks if c.found] or None
    return checks


def drop_unfound_quotes(source: SourceFile, page_text: str) -> list[str]:
    """``apply_quote_checks``, returning the dropped quotes as given."""
    return [c.text for c in apply_quote_checks(source, page_text) if not c.found]


def check_quotes(quotes: list[str], page_text: str, *, with_passage: bool = False) -> list[QuoteCheck]:
    """``check_quote`` for each quote, normalizing the page once."""
    if not quotes:
        return []
    page = _normalize_page(page_text)
    located: tuple[str, list[int]] | None = None
    out: list[QuoteCheck] = []
    for quote in quotes:
        span, reason = _find_on_page(_match_text(_fold(quote)), page)
        if span is None:
            out.append(QuoteCheck(text=quote, found=False, reason=reason))
            continue
        passage = None
        if with_passage:
            located = located or _passage_locator(page_text, page)
            passage = _passage(*located, span)
        out.append(QuoteCheck(text=_unwrapped(quote, page), found=True, passage=passage))
    return out


def _unwrapped(quote: str, normalized_page: str) -> str:
    """The text inside a quote's wrapping marks, or the quote unchanged.

    The source page shows each quote in a blockquote, so wrapping marks would
    show twice, and an attribution is not page text. The marks stay when they
    belong to the page text itself, or when the inner text alone is not on
    the page.
    """
    text = quote.strip()
    end = _wrapping_end(text)
    if end is None:
        return quote
    inner = text[1:end].strip()
    folded = _fold(inner)
    if not _inner_marks_pair(folded, _fold(text[0])):
        return quote
    if not _text_on_page(folded, normalized_page):
        return quote
    return inner


def _wrapping_end(text: str) -> int | None:
    """Index of the mark closing a quote that opens with a quotation mark.

    None when the text does not open with a mark, has no closing mark of the
    same kind, or has something other than an attribution after it. Each
    character is folded on its own, so the index points into ``text`` as given
    even when folding the whole string would change its length.
    """
    marks = [_fold(ch) for ch in text]
    if not marks or marks[0] not in _QUOTE_MARKS:
        return None
    for end in range(len(text) - 1, 0, -1):
        if marks[end] == marks[0]:
            return end if _AFTER_CLOSING_MARK.match(_fold(text[end + 1:])) else None
    return None


def _inner_marks_pair(text: str, mark: str) -> bool:
    """Whether every ``mark`` inside a wrapped quote's text pairs within it.

    In page text such as ``"Green" is our motto, they say "always"`` the first
    and last marks are not a pair: a closing mark comes before any opening
    one. A mark between two word characters is an apostrophe, not a mark.
    """
    depth = 0
    for i, ch in enumerate(text):
        if ch != mark:
            continue
        before = text[i - 1] if i else " "
        after = text[i + 1] if i + 1 < len(text) else " "
        if before.isspace() or before in "([{-":
            depth += 1
        elif not _WORD.match(after):
            if depth == 0:
                return False
            depth -= 1
    return depth == 0


def _text_on_page(text: str, normalized_page: str) -> bool:
    """Whether folded quote text, taken as is, appears on the normalized page."""
    return _find_on_page(text, normalized_page)[0] is not None


def _find_on_page(text: str, normalized_page: str) -> tuple[tuple[int, int] | None, str | None]:
    """Where folded quote text appears on the normalized page, as ``((start, end), None)``.

    ``(None, reason)`` when it does not; the reason says whether the
    fragments of an elided quote matched but too far apart.
    """
    text = _strip_markup(text)
    fragments = [
        f for f in _ELISION.split(" ".join(text.split())) if _WORD.search(f)
    ]
    if not fragments or not _fragments_read_as_excerpt(fragments):
        return None, NOT_FOUND_REASON
    patterns = [_fragment_pattern(f) for f in fragments]
    reason = NOT_FOUND_REASON
    for first in patterns[0].finditer(normalized_page):
        elided = 0
        position = first.end()
        for pattern in patterns[1:]:
            found = pattern.search(normalized_page, position)
            if found is None:
                return None, reason
            elided += found.start() - position
            position = found.end()
        # Matching each later fragment at its earliest place keeps the elided
        # text as short as it can be for this start.
        if elided <= _MAX_ELIDED_CHARS:
            return (first.start(), position), None
        reason = TOO_FAR_APART_REASON
    return None, reason


def _fragments_read_as_excerpt(fragments: list[str]) -> bool:
    if len(fragments) == 1:
        return True
    words = [len([w for w in f.split() if _WORD.search(w)]) for f in fragments]
    return max(words) >= 2 and all(
        n >= _MIN_INTERIOR_FRAGMENT_WORDS for n in words[1:-1]
    )


def _fragment_pattern(fragment: str) -> re.Pattern[str]:
    # Page text has a newline wherever an inline tag started or ended, which
    # can split a word ("CO\n2") or put a break before punctuation; a page
    # newline may therefore match nothing, and a space in the quote matches a
    # page space or newline. A page space must match a quote space, so words
    # never run together ("the rapist" is not in "the therapist").
    parts = ["[ \n]" if ch == " " else re.escape(ch) for ch in fragment]
    pattern = "\n?".join(parts)
    if _WORD.match(fragment[0]):
        pattern = r"(?<!\w)" + pattern
    if _WORD.match(fragment[-1]):
        pattern += r"(?!\w)"
    return re.compile(pattern)


def _match_text(quote: str) -> str:
    """The part of a folded quote that must appear on the page.

    Quotes from the model are often wrapped in quotation marks, sometimes with
    an attribution after the closing mark; neither is page text.
    """
    text = quote.strip()
    end = _wrapping_end(text)
    return text if end is None else text[1:end]


def _fold(text: str) -> str:
    # NFKC folds no-break spaces, full-width marks and the ellipsis character.
    return unicodedata.normalize("NFKC", html.unescape(text)).translate(_CHAR_MAP)


def _strip_markup(text: str) -> str:
    # Markdown markup comes from prefetched bodies. Emphasis marks and
    # underscores are removed from both sides, so "data\_center" on the page
    # matches "data_center" in the quote.
    text = _MARKDOWN_ESCAPE.sub(r"\1", text)
    text = _MARKDOWN_IMAGE.sub("", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    return _MARKDOWN_EMPHASIS.sub("", text).casefold()


def _normalize_page(text: str) -> str:
    # Each run of whitespace becomes one newline if it holds a line break,
    # else one space; see _fragment_pattern for how each is matched.
    text = _strip_markup(_fold(text))
    return re.sub(r"\s+", lambda m: "\n" if "\n" in m.group() else " ", text)


# --------------------------------------------------------------------------- #
# The passage around a match                                                   #
# --------------------------------------------------------------------------- #

# A sentence ends at ., ! or ? (with any closing marks) before whitespace,
# or at a blank line.
_SENTENCE_END = re.compile(r"[.!?][\"')\]]*(?=\s)|\n\s*\n")


def _sub_mapped(
    pattern: re.Pattern[str], text: str, index: list[int], group: int | None,
) -> tuple[str, list[int]]:
    """``pattern.sub`` that keeps, for each output character, its index in the folded page.

    Each match is replaced by its ``group`` (or nothing), as the
    substitutions in ``_strip_markup`` do.
    """
    out: list[str] = []
    out_index: list[int] = []
    position = 0
    for m in pattern.finditer(text):
        out.append(text[position:m.start()])
        out_index.extend(index[position:m.start()])
        if group is not None:
            start, end = m.span(group)
            out.append(text[start:end])
            out_index.extend(index[start:end])
        position = m.end()
    out.append(text[position:])
    out_index.extend(index[position:])
    return "".join(out), out_index


def _normalize_mapped(folded: str) -> tuple[str, list[int]]:
    """``_normalize_page`` of an already folded page, with each character's index in ``folded``."""
    text, index = folded, list(range(len(folded)))
    text, index = _sub_mapped(_MARKDOWN_ESCAPE, text, index, 1)
    text, index = _sub_mapped(_MARKDOWN_IMAGE, text, index, None)
    text, index = _sub_mapped(_MARKDOWN_LINK, text, index, 1)
    text, index = _sub_mapped(_MARKDOWN_EMPHASIS, text, index, None)
    cased: list[str] = []
    cased_index: list[int] = []
    for ch, i in zip(text, index):
        lowered = ch.casefold()
        cased.append(lowered)
        cased_index.extend([i] * len(lowered))
    text, index = "".join(cased), cased_index
    out: list[str] = []
    out_index: list[int] = []
    position = 0
    for m in re.finditer(r"\s+", text):
        out.append(text[position:m.start()])
        out_index.extend(index[position:m.start()])
        out.append("\n" if "\n" in m.group() else " ")
        out_index.append(index[m.start()])
        position = m.end()
    out.append(text[position:])
    out_index.extend(index[position:])
    return "".join(out), out_index


def _passage_locator(page_text: str, normalized_page: str) -> tuple[str, list[int]]:
    """The folded page and, for each normalized character, its index there.

    The map only locates a match in the page's own text; if it ever
    disagrees with the matcher's text, the passage is cut from the
    normalized text rather than from the wrong place.
    """
    folded = _fold(page_text)
    mapped, index = _normalize_mapped(folded)
    if mapped != normalized_page:
        return normalized_page, list(range(len(normalized_page)))
    return folded, index


def _passage(folded: str, index: list[int], span: tuple[int, int]) -> str:
    """The page's own text around a match at ``span`` in the normalized page.

    The sentence or sentences holding the match, plus up to
    ``PASSAGE_CONTEXT_CHARS`` on each side, cut at word boundaries and at
    most ``PASSAGE_MAX_CHARS`` long, with whitespace runs made one space.
    """
    start = index[span[0]]
    end = index[span[1] - 1] + 1

    window_start = max(0, start - PASSAGE_MAX_CHARS)
    ends = [m.end() for m in _SENTENCE_END.finditer(folded, window_start, start)]
    sentence_start = ends[-1] if ends else window_start
    after = _SENTENCE_END.search(folded, max(start, end - 1), min(len(folded), end + PASSAGE_MAX_CHARS))
    sentence_end = after.end() if after else min(len(folded), end + PASSAGE_MAX_CHARS)

    lo = max(0, sentence_start - PASSAGE_CONTEXT_CHARS)
    hi = min(len(folded), sentence_end + PASSAGE_CONTEXT_CHARS)
    if hi - lo > PASSAGE_MAX_CHARS:
        room = max(0, PASSAGE_MAX_CHARS - (end - start))
        lo = max(lo, start - room // 2)
        hi = min(hi, lo + PASSAGE_MAX_CHARS)
        lo = max(lo, hi - PASSAGE_MAX_CHARS)
    # Cut at word boundaries, never into the match itself.
    while lo < start and lo > 0 and not folded[lo - 1].isspace():
        lo += 1
    while hi > end and hi < len(folded) and not folded[hi].isspace():
        hi -= 1
    return " ".join(folded[lo:hi].split())[:PASSAGE_MAX_CHARS]
