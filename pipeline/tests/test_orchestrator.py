"""Tests for the verification orchestrator result type."""

from __future__ import annotations

import datetime
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.pipeline import (
    VerificationResult,
    VerifyConfig,
    _research,
)
from researcher.agent import research_agent


class TestVerificationResult:
    def test_construction(self) -> None:
        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=["https://example.com"],
            urls_ingested=["https://example.com"],
            urls_failed=[],
            sources=[],
        )
        assert result.entity == "TestCorp"
        assert result.analyst_output is None
        assert result.consistency is None


class TestVerificationResultCarriesSourceFiles:
    def test_defaults_empty_when_omitted(self) -> None:
        """Construction without source_files yields an empty list (backward compat)."""
        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=[],
            urls_ingested=[],
            urls_failed=[],
            sources=[],
        )
        assert result.source_files == []

    def test_round_trip_source_files(self) -> None:
        """A fabricated (url, SourceFile) tuple round-trips through the field."""
        sf = SourceFile(
            frontmatter=SourceFrontmatter(
                url="https://example.com/report",
                title="Test Report",
                publisher="Example Publisher",
                accessed_date=datetime.date(2026, 4, 19),
                kind="article",
                summary="A concise test summary.",
            ),
            body="Body content.",
            slug="test-report",
            year=2026,
        )
        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=["https://example.com/report"],
            urls_ingested=["https://example.com/report"],
            urls_failed=[],
            sources=[],
            source_files=[("https://example.com/report", sf)],
        )
        assert len(result.source_files) == 1
        url, stored = result.source_files[0]
        assert url == "https://example.com/report"
        assert stored is sf
        assert stored.frontmatter.title == "Test Report"
        # exclude=True keeps source_files out of serialization
        dumped = result.model_dump()
        assert "source_files" not in dumped


@contextmanager
def _noop(**kwargs):
    """No-op context manager to neutralize inner agent overrides."""
    yield


def _researcher_returning(urls: list[str]) -> TestModel:
    return TestModel(
        custom_output_args={
            "urls": urls,
            "reasoning": "fake",
        },
        call_tools=[],
    )


def _write_blocklist(tmp_path) -> None:
    research = tmp_path / "research"
    research.mkdir(parents=True, exist_ok=True)
    (research / "blocklist.yaml").write_text(
        """
hosts:
  - host: linkedin.com
    reason: "403s on anonymous fetch"
""",
        encoding="utf-8",
    )


class TestResearchBlocklist:
    @pytest.mark.asyncio
    async def test_blocklist_drops_linkedin_url(self, tmp_path) -> None:
        _write_blocklist(tmp_path)
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        async with httpx.AsyncClient() as client:
            with (
                research_agent.override(
                    model=_researcher_returning(
                        ["https://linkedin.com/a", "https://example.com/b"]
                    )
                ),
                patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            ):
                urls, errors = await _research(client, "Ent", "claim", cfg)

        assert urls == ["https://example.com/b"]
        blocked = [e for e in errors if e.error_type == "blocked_host"]
        assert len(blocked) == 1
        assert blocked[0].url == "https://linkedin.com/a"
        assert blocked[0].retryable is False
        # No all_blocked when at least one URL was kept
        assert not any(e.error_type == "all_blocked" for e in errors)

    @pytest.mark.asyncio
    async def test_all_blocked_adds_summary_error(self, tmp_path) -> None:
        _write_blocklist(tmp_path)
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        async with httpx.AsyncClient() as client:
            with (
                research_agent.override(
                    model=_researcher_returning(
                        ["https://linkedin.com/a", "https://uk.linkedin.com/b"]
                    )
                ),
                patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            ):
                urls, errors = await _research(client, "Ent", "claim", cfg)

        assert urls == []
        assert errors[0].error_type == "all_blocked"
        blocked = [e for e in errors if e.error_type == "blocked_host"]
        assert len(blocked) == 2

    @pytest.mark.asyncio
    async def test_no_blocklist_file_passes_through(self, tmp_path) -> None:
        # No research/blocklist.yaml written
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        async with httpx.AsyncClient() as client:
            with (
                research_agent.override(
                    model=_researcher_returning(
                        ["https://linkedin.com/a", "https://example.com/b"]
                    )
                ),
                patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            ):
                urls, errors = await _research(client, "Ent", "claim", cfg)

        assert urls == ["https://linkedin.com/a", "https://example.com/b"]
        assert errors == []
