"""Tests for the research agent."""

from __future__ import annotations

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from researcher.agent import ResearchDeps, ResearchResult, research_agent


class TestResearchAgent:
    @pytest.mark.asyncio
    async def test_output_type(self) -> None:
        assert research_agent.output_type is ResearchResult

    @pytest.mark.asyncio
    async def test_produces_urls(self) -> None:
        with research_agent.override(
            model=TestModel(
                custom_output_args={
                    "urls": ["https://example.com/report"],
                    "reasoning": "Found a relevant report.",
                },
                call_tools=[],
            )
        ):
            async with httpx.AsyncClient() as client:
                deps = ResearchDeps(http_client=client)
                result = await research_agent.run("test query", deps=deps)

            assert isinstance(result.output, ResearchResult)
            assert len(result.output.urls) == 1
            assert result.output.urls[0] == "https://example.com/report"
