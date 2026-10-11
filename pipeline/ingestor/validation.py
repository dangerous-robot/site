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


_OPENING_MARKS = {'"': '"', "'": "'", "\u201c": "\u201d", "\u2018": "\u2019", "\u00ab": "\u00bb"}
# What may follow a quote's closing mark and still leave only the marked text
# claimed verbatim: nothing, a trailing period or comma, or a dash attribution.
_AFTER_CLOSING_MARK = re.compile(r"^[.,]?\s*$|^\s*(?:\u2014|\u2013|\u2015|--|-)\s*\S")
_ELLIPSIS = re.compile(r"\.\.\.")
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WHITESPACE = re.compile(r"\s+")
_CHAR_MAP = str.maketrans({
    **{c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015"},
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
})


def drop_unfound_quotes(source: SourceFile, page_text: str) -> list[str]:
    """Remove key quotes whose text is not on the page; return the dropped ones.

    Sets ``key_quotes`` to the kept quotes, or None when none are kept. A kept
    quote is stored unchanged; only the text it is matched by is derived.
    """
    quotes = source.frontmatter.key_quotes or []
    if not quotes:
        return []
    page = _normalize_for_match(page_text)
    kept: list[str] = []
    dropped: list[str] = []
    for quote in quotes:
        (kept if _quote_on_page(quote, page) else dropped).append(quote)
    source.frontmatter.key_quotes = kept or None
    return dropped


def _quote_on_page(quote: str, normalized_page: str) -> bool:
    fragments = [f for f in _ELLIPSIS.split(_normalize_for_match(_match_text(quote))) if f]
    if not fragments:
        return False
    position = 0
    for fragment in fragments:
        found = normalized_page.find(fragment, position)
        if found == -1:
            return False
        position = found + len(fragment)
    return True


def _match_text(quote: str) -> str:
    """The part of a stored quote that must appear on the page.

    Stored quotes are often wrapped in quotation marks, sometimes with an
    attribution after the closing mark; neither is page text.
    """
    text = quote.strip()
    closing = _OPENING_MARKS.get(text[:1])
    if closing is None:
        return text
    end = text.rfind(closing, 1)
    if end == -1 or not _AFTER_CLOSING_MARK.match(text[end + 1:]):
        return text
    return text[1:end]


def _normalize_for_match(text: str) -> str:
    # NFKC folds no-break spaces and the ellipsis character; Markdown markup
    # comes from prefetched bodies. All whitespace is removed, not collapsed,
    # because the page text has a newline wherever an inline tag ended, which
    # puts a space before punctuation that followed the tag.
    text = unicodedata.normalize("NFKC", html.unescape(text)).translate(_CHAR_MAP)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return _WHITESPACE.sub("", text).casefold()
