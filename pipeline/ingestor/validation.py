"""Post-generation semantic validation for ingestor output."""

from __future__ import annotations

import datetime
import re
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
    page_text: str | None = None,
) -> ValidationResult:
    """Run semantic checks on an ingestor-produced SourceFile.

    Args:
        source: The agent output.
        input_url: The URL the user originally provided.
        repo_root: Path to the repo root.
        page_text: The fetched page text, for quote verification.
    """
    result = ValidationResult()

    _check_url_match(source, input_url, result)
    _check_slug_format(source, result)
    _check_year_plausibility(source, result)
    _check_archived_url_domain(source, result)

    if page_text:
        _check_key_quotes(source, page_text, result)

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


def _check_key_quotes(
    source: SourceFile, page_text: str, result: ValidationResult
) -> None:
    quotes = source.frontmatter.key_quotes or []
    for quote in quotes:
        if quote not in page_text:
            result.warnings.append(
                f"Key quote not found in page text: '{quote[:80]}...'"
                if len(quote) > 80
                else f"Key quote not found in page text: '{quote}'"
            )
