"""Tests for ingestor Pydantic models."""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from common.models import SourceKind
from ingestor.models import SourceFile, SourceFrontmatter


def _valid_frontmatter(**overrides) -> dict:
    """Return a valid frontmatter dict with optional overrides."""
    base = {
        "url": "https://example.com/article",
        "title": "Test Article",
        "publisher": "Test Publisher",
        "accessed_date": datetime.date(2026, 4, 19),
        "kind": SourceKind.ARTICLE,
        "summary": "A short factual summary of the article.",
    }
    base.update(overrides)
    return base


class TestSourceFrontmatter:
    def test_valid_minimal(self):
        fm = SourceFrontmatter(**_valid_frontmatter())
        assert fm.url == "https://example.com/article"
        assert fm.archived_url is None
        assert fm.published_date is None
        assert fm.key_quotes is None

    def test_valid_full(self):
        fm = SourceFrontmatter(
            **_valid_frontmatter(
                archived_url="https://web.archive.org/web/2026/https://example.com/article",
                published_date=datetime.date(2026, 1, 15),
                key_quotes=["A direct quote from the source."],
            )
        )
        assert fm.archived_url is not None
        assert fm.published_date == datetime.date(2026, 1, 15)
        assert len(fm.key_quotes) == 1

    def test_invalid_url_no_scheme(self):
        with pytest.raises(ValidationError, match="Invalid URL"):
            SourceFrontmatter(**_valid_frontmatter(url="not-a-url"))

    def test_invalid_archived_url(self):
        with pytest.raises(ValidationError, match="Invalid URL"):
            SourceFrontmatter(**_valid_frontmatter(archived_url="ftp://bad"))

    def test_summary_max_200_chars(self):
        long_summary = "A " * 100  # 200 chars but many words
        with pytest.raises(ValidationError, match="words"):
            SourceFrontmatter(**_valid_frontmatter(summary=long_summary))

    def test_summary_over_30_words(self):
        wordy = " ".join(["word"] * 31)
        with pytest.raises(ValidationError, match="31 words"):
            SourceFrontmatter(**_valid_frontmatter(summary=wordy))

    def test_summary_exactly_30_words(self):
        exactly_30 = " ".join(["word"] * 30)
        fm = SourceFrontmatter(**_valid_frontmatter(summary=exactly_30))
        assert len(fm.summary.split()) == 30

    def test_summary_over_200_chars_field_constraint(self):
        # 201 chars, but short word count
        long_char = "x" * 201
        with pytest.raises(ValidationError):
            SourceFrontmatter(**_valid_frontmatter(summary=long_char))

    def test_invalid_kind(self):
        with pytest.raises(ValidationError):
            SourceFrontmatter(**_valid_frontmatter(kind="podcast"))

    def test_all_valid_kinds(self):
        for kind in SourceKind:
            fm = SourceFrontmatter(**_valid_frontmatter(kind=kind))
            assert fm.kind == kind


class TestSourceFile:
    def test_valid_source_file(self):
        sf = SourceFile(
            frontmatter=SourceFrontmatter(**_valid_frontmatter()),
            body="Additional context about the article.",
            slug="test-article",
            year=2026,
        )
        assert sf.slug == "test-article"
        assert sf.year == 2026

    def test_invalid_slug_uppercase(self):
        with pytest.raises(ValidationError, match="pattern"):
            SourceFile(
                frontmatter=SourceFrontmatter(**_valid_frontmatter()),
                body="Body.",
                slug="Test-Article",
                year=2026,
            )

    def test_invalid_slug_spaces(self):
        with pytest.raises(ValidationError, match="pattern"):
            SourceFile(
                frontmatter=SourceFrontmatter(**_valid_frontmatter()),
                body="Body.",
                slug="test article",
                year=2026,
            )

    def test_invalid_slug_trailing_hyphen(self):
        with pytest.raises(ValidationError, match="pattern"):
            SourceFile(
                frontmatter=SourceFrontmatter(**_valid_frontmatter()),
                body="Body.",
                slug="test-article-",
                year=2026,
            )

    def test_valid_single_word_slug(self):
        sf = SourceFile(
            frontmatter=SourceFrontmatter(**_valid_frontmatter()),
            body="Body.",
            slug="article",
            year=2026,
        )
        assert sf.slug == "article"
