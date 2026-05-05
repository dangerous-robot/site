"""Pydantic models for ingestor agent output."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field, field_validator

from common.models import Independence, SourceKind


class SourceFrontmatter(BaseModel):
    """Mirrors the Zod source schema in content.config.ts."""

    url: str
    archived_url: str | None = None
    title: str
    publisher: str
    published_date: datetime.date | None = None
    accessed_date: datetime.date
    kind: SourceKind
    independence: Independence | None = None
    summary: str = Field(max_length=200)
    key_quotes: list[str] | None = None

    @field_validator("url", "archived_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {v}")
        return v

    @field_validator("summary")
    @classmethod
    def summary_word_count(cls, v: str) -> str:
        word_count = len(v.split())
        if word_count > 30:
            raise ValueError(f"Summary has {word_count} words; limit is 30")
        return v


class SourceFile(BaseModel):
    """Complete source file: frontmatter + Markdown body."""

    frontmatter: SourceFrontmatter
    body: str = Field(description="Markdown body with additional context")
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    year: int
