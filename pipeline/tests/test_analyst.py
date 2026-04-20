"""Tests for the analyst agent."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from analyst.agent import AnalystOutput, analyst_agent, build_analyst_prompt
from common.models import Category, Confidence, Verdict


class TestAnalystAgent:
    @pytest.mark.asyncio
    async def test_output_type(self) -> None:
        assert analyst_agent.output_type is AnalystOutput

    @pytest.mark.asyncio
    async def test_produces_assessment(self) -> None:
        with analyst_agent.override(
            model=TestModel(
                custom_output_args={
                    "entity": {
                        "entity_name": "TestCorp",
                        "entity_type": "company",
                        "entity_description": "A test company",
                    },
                    "verdict": {
                        "title": "Test claim about renewable energy",
                        "category": "environmental-impact",
                        "verdict": "mixed",
                        "confidence": "medium",
                        "narrative": "The evidence is mixed on this claim.",
                    },
                },
            )
        ):
            prompt = build_analyst_prompt("TestCorp", "TestCorp uses renewables", [])
            result = await analyst_agent.run(prompt)

            out = result.output
            assert isinstance(out, AnalystOutput)
            assert out.verdict.verdict == Verdict.MIXED
            assert out.verdict.confidence == Confidence.MEDIUM
            assert out.verdict.category == Category.ENVIRONMENTAL_IMPACT
            assert out.entity.entity_name == "TestCorp"


class TestAnalystPrompt:
    def test_includes_entity_and_claim(self) -> None:
        prompt = build_analyst_prompt(
            "Ecosia",
            "Ecosia runs on renewable energy",
            [{"title": "Report", "publisher": "Org", "summary": "A report", "body": "Details"}],
        )
        assert "Ecosia" in prompt
        assert "Ecosia runs on renewable energy" in prompt
        assert "Report" in prompt
        assert "Org" in prompt

    def test_handles_no_sources(self) -> None:
        prompt = build_analyst_prompt("X", "Claim", [])
        assert "No sources were found" in prompt
