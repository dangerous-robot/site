"""Integration tests for the ingestor agent using TestModel."""

from __future__ import annotations

import datetime

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from ingestor.agent import IngestorDeps, ingestor_agent
from ingestor.models import SourceFile, SourceFrontmatter
from common.models import SourceKind


@pytest.fixture
def test_deps(tmp_path) -> IngestorDeps:
    """Create test dependencies with a temporary repo root."""
    return IngestorDeps(
        http_client=httpx.AsyncClient(),
        repo_root=str(tmp_path),
        today=datetime.date(2026, 4, 19),
    )


def _valid_source_file_args() -> dict:
    """Return args that produce a valid SourceFile when used as custom_output_args."""
    return {
        "frontmatter": {
            "url": "https://example.com/test",
            "title": "Test Article",
            "publisher": "Example Publisher",
            "accessed_date": "2026-04-19",
            "kind": "article",
            "summary": "A short factual summary of the test article.",
        },
        "body": "Additional context about the article.",
        "slug": "test-article",
        "year": 2026,
    }


class TestIngestorAgent:
    @pytest.mark.asyncio
    async def test_agent_produces_valid_source_file(self, test_deps):
        """The agent with TestModel should produce a valid SourceFile."""
        with ingestor_agent.override(
            model=TestModel(
                custom_output_args=_valid_source_file_args(),
                call_tools=[],
            )
        ):
            result = await ingestor_agent.run(
                "Ingest this URL: https://example.com/test\nToday's date: 2026-04-19",
                deps=test_deps,
            )
            source_file = result.output
            assert isinstance(source_file, SourceFile)
            assert source_file.frontmatter.url == "https://example.com/test"
            assert source_file.slug == "test-article"
            assert source_file.year == 2026

    @pytest.mark.asyncio
    async def test_agent_output_type(self, test_deps):
        """Verify the agent's output_type is SourceFile."""
        assert ingestor_agent.output_type is SourceFile

    @pytest.mark.asyncio
    async def test_agent_has_tools(self):
        """Agent should have web_fetch and wayback_check tools registered."""
        tool_names = set(ingestor_agent._function_toolset.tools.keys())
        assert "web_fetch" in tool_names
        assert "wayback_check" in tool_names
