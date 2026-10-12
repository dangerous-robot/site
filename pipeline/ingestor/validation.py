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


def drop_unfound_quotes(source: SourceFile, page_text: str) -> list[str]:
    """Remove key quotes whose text is not on the page; return the dropped ones.

    Sets ``key_quotes`` to the kept quotes, or None when none are kept. A kept
    quote wrapped in quotation marks, with or without an attribution after the
    closing mark, is stored as the text inside the marks (see ``_unwrapped``).
    """
    quotes = source.frontmatter.key_quotes or []
    if not quotes:
        return []
    page = _normalize_page(page_text)
    kept: list[str] = []
    dropped: list[str] = []
    for quote in quotes:
        if _quote_on_page(quote, page):
            kept.append(_unwrapped(quote, page))
        else:
            dropped.append(quote)
    source.frontmatter.key_quotes = kept or None
    return dropped


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


def _quote_on_page(quote: str, normalized_page: str) -> bool:
    return _text_on_page(_match_text(_fold(quote)), normalized_page)


def _text_on_page(text: str, normalized_page: str) -> bool:
    """Whether folded quote text, taken as is, appears on the normalized page."""
    text = _strip_markup(text)
    fragments = [
        f for f in _ELISION.split(" ".join(text.split())) if _WORD.search(f)
    ]
    if not fragments or not _fragments_read_as_excerpt(fragments):
        return False
    patterns = [_fragment_pattern(f) for f in fragments]
    for first in patterns[0].finditer(normalized_page):
        elided = 0
        position = first.end()
        for pattern in patterns[1:]:
            found = pattern.search(normalized_page, position)
            if found is None:
                return False
            elided += found.start() - position
            position = found.end()
        # Matching each later fragment at its earliest place keeps the elided
        # text as short as it can be for this start.
        if elided <= _MAX_ELIDED_CHARS:
            return True
    return False


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
