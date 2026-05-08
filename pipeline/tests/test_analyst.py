"""Tests for the analyst agent."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from analyst.agent import AnalystOutput, VerdictAssessment, analyst_agent, build_analyst_prompt
from common.models import Category, Confidence, SubQuestion, Verdict, VerificationLevel


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
                        "topics": ["environmental-impact"],
                        "verdict": "mixed",
                        "confidence": "medium",
                        "narrative": "The evidence is mixed on this claim.",
                        "verification_level": "partially-verified",
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
            assert out.verdict.topics == [Category.ENVIRONMENTAL_IMPACT]
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

    def test_renders_sub_questions_block(self) -> None:
        sub_questions = [
            SubQuestion(id="sq1", question="Does Ecosia publish energy data?", rationale="direct"),
            SubQuestion(id="sq2", question="Do third parties confirm it?", rationale="independent"),
        ]
        prompt = build_analyst_prompt(
            "Ecosia",
            "Ecosia runs on renewable energy",
            [],
            sub_questions=sub_questions,
        )
        assert "## Sub-questions" in prompt
        assert "sq1: Does Ecosia publish energy data?" in prompt
        assert "sq2: Do third parties confirm it?" in prompt
        assert "Rationale: direct" in prompt

    def test_renders_addresses_per_source(self) -> None:
        sub_questions = [
            SubQuestion(id="sq1", question="A?", rationale="r1"),
            SubQuestion(id="sq2", question="B?", rationale="r2"),
        ]
        sources = [
            {
                "title": "First",
                "publisher": "Pub",
                "summary": "Summary",
                "body": "Body",
                "addresses": ["sq1", "sq2"],
            },
            {
                "title": "Second",
                "publisher": "Pub",
                "summary": "Summary",
                "body": "Body",
                "addresses": [],
            },
        ]
        prompt = build_analyst_prompt(
            "Ecosia",
            "Some claim",
            sources,
            sub_questions=sub_questions,
        )
        assert "Addresses: sq1, sq2" in prompt
        assert "Addresses: (none)" in prompt


class TestSeoTitleNormalization:
    def _va(self, title: str, seo_title: str | None) -> VerdictAssessment:
        return VerdictAssessment(
            title=title,
            verdict=Verdict.TRUE,
            confidence=Confidence.MEDIUM,
            narrative="Some narrative.",
            topics=[Category.ENVIRONMENTAL_IMPACT],
            verification_level=VerificationLevel.INDEPENDENTLY_VERIFIED,
            seo_title=seo_title,
        )

    def test_drops_seo_title_when_full_title_fits(self) -> None:
        v = self._va("Anthropic donates to environmental causes", "Anthropic Donates to Env. Causes")
        assert v.seo_title is None

    def test_keeps_seo_title_when_title_is_long(self) -> None:
        long_title = "Anthropic publishes a comprehensive sustainability report covering scope 1 2 and 3 emissions"
        v = self._va(long_title, "Anthropic Publishes Sustainability Report")
        assert v.seo_title == "Anthropic Publishes Sustainability Report"

    def test_drops_truncated_seo_title(self) -> None:
        long_title = "Anthropic publishes a comprehensive sustainability report covering scope 1 2 and 3 emissions"
        v = self._va(long_title, "Anthropic's Environmental Giving: Mixed, L")
        assert v.seo_title is None

    def test_keeps_short_known_abbreviation(self) -> None:
        long_title = "Anthropic operates major data centers in the United States and the European Union markets"
        v = self._va(long_title, "Anthropic Data Centers in the US and EU")
        assert v.seo_title == "Anthropic Data Centers in the US and EU"

    def test_none_seo_title_is_unchanged(self) -> None:
        v = self._va("Short title", None)
        assert v.seo_title is None
