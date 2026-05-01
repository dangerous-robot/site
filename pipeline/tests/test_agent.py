"""Integration tests for the ingestor agent using TestModel, and unit tests for the analyst prompt builder."""

from __future__ import annotations

import datetime

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from ingestor.agent import IngestorDeps, ingestor_agent
from ingestor.models import SourceFile, SourceFrontmatter
from common.models import EntityType, SourceKind
from analyst.agent import build_analyst_prompt
from orchestrator.entity_resolution import ResolvedEntity


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


class TestBuildAnalystPrompt:
    def _make_resolved(self) -> ResolvedEntity:
        return ResolvedEntity(
            entity_ref="products/chatgpt",
            entity_name="ChatGPT",
            entity_type=EntityType.PRODUCT,
            entity_description="A conversational AI product.",
            aliases=["GPT"],
            parent_company="OpenAI",
        )

    def test_with_resolved_entity_emits_pre_resolved_block(self) -> None:
        resolved = self._make_resolved()
        prompt = build_analyst_prompt(None, "ChatGPT is safe", [], resolved_entity=resolved)
        assert "## Entity (pre-resolved — do not infer)" in prompt
        assert "Name: ChatGPT" in prompt
        assert "Type: product" in prompt
        assert "Description: A conversational AI product." in prompt
        assert "Aliases: GPT" in prompt
        assert "Parent company: OpenAI" in prompt

    def test_with_resolved_entity_no_inference_instruction(self) -> None:
        resolved = self._make_resolved()
        prompt = build_analyst_prompt(None, "ChatGPT is safe", [], resolved_entity=resolved)
        assert "Produce only a VerdictAssessment" in prompt
        assert "## Entity: " not in prompt

    def test_without_resolved_entity_output_unchanged(self) -> None:
        prompt_with_name = build_analyst_prompt("ChatGPT", "ChatGPT is safe", [])
        assert "## Entity: ChatGPT" in prompt_with_name
        assert "pre-resolved" not in prompt_with_name

        prompt_no_name = build_analyst_prompt(None, "Something is safe", [])
        assert "## Entity:" not in prompt_no_name
        assert "pre-resolved" not in prompt_no_name
