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
                        "seo_title": "Test claim about renewable energy",
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


class TestSeoTitleField:
    """seo_title is required on every claim, 1-42 chars, no mid-word
    truncation. The model itself enforces length; the analyst's
    instructions tell the LLM to always supply a complete phrase.
    """

    def _va(self, title: str, seo_title: str) -> VerdictAssessment:
        return VerdictAssessment(
            title=title,
            verdict=Verdict.TRUE,
            confidence=Confidence.MEDIUM,
            narrative="Some narrative.",
            topics=[Category.ENVIRONMENTAL_IMPACT],
            verification_level=VerificationLevel.INDEPENDENTLY_VERIFIED,
            seo_title=seo_title,
        )

    def test_keeps_seo_title_when_full_title_fits(self) -> None:
        v = self._va("Anthropic donates to environmental causes", "Anthropic Donates to Env. Causes")
        assert v.seo_title == "Anthropic Donates to Env. Causes"

    def test_keeps_seo_title_when_title_is_long(self) -> None:
        long_title = "Anthropic publishes a comprehensive sustainability report covering scope 1 2 and 3 emissions"
        v = self._va(long_title, "Anthropic Publishes Sustainability Report")
        assert v.seo_title == "Anthropic Publishes Sustainability Report"

    def test_seo_title_is_required(self) -> None:
        with pytest.raises(ValueError):
            VerdictAssessment(
                title="Short title",
                verdict=Verdict.TRUE,
                confidence=Confidence.MEDIUM,
                narrative="Some narrative.",
                topics=[Category.ENVIRONMENTAL_IMPACT],
                verification_level=VerificationLevel.INDEPENDENTLY_VERIFIED,
            )

    def test_empty_seo_title_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._va("Short title", "")

    def test_seo_title_over_42_chars_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._va("Some title", "A" * 43)

    @pytest.mark.parametrize(
        "bad_seo_title",
        [
            "Brave Software's Environmental Impact: A '",  # trailing standalone quote
            "GreenPT claims 100% renewable energy for A",  # dangling article "A"
            "ChatGPT's Image Generation: Official,",       # trailing comma
            "Brave's stance on AI ethics (e.g.",           # unbalanced paren
            "Anthropic's Sustainability Report:",          # trailing colon
        ],
    )
    def test_truncated_seo_title_rejected(self, bad_seo_title: str) -> None:
        with pytest.raises(ValueError):
            self._va("Some title", bad_seo_title)

    def test_complete_seo_title_accepted(self) -> None:
        v = self._va("Anthropic donates", "Anthropic Donates to Env. Causes")
        assert v.seo_title == "Anthropic Donates to Env. Causes"


class TestTakeawayField:
    """takeaway is optional; when provided it must be a complete sentence
    (no mid-clause truncation, ends in '.', '!', or '?').
    """

    def _va(self, takeaway: str | None) -> VerdictAssessment:
        return VerdictAssessment(
            title="Some title",
            verdict=Verdict.TRUE,
            confidence=Confidence.MEDIUM,
            narrative="Some narrative.",
            topics=[Category.ENVIRONMENTAL_IMPACT],
            verification_level=VerificationLevel.INDEPENDENTLY_VERIFIED,
            seo_title="Some SEO Title",
            takeaway=takeaway,
        )

    def test_omitted_takeaway_accepted(self) -> None:
        assert self._va(None).takeaway is None

    def test_complete_takeaway_accepted(self) -> None:
        v = self._va("Anthropic publishes detailed reports yearly.")
        assert v.takeaway == "Anthropic publishes detailed reports yearly."

    @pytest.mark.parametrize(
        "bad_takeaway",
        [
            "Their actions mirror industry trends (e.g., E",       # unbalanced paren
            "Anthropic publishes reports about energy and",        # dangling conjunction, no end
            "GreenPT claims 100% renewable energy for the",        # dangling article, no end
            "Brave promotes energy-efficient tech, but lacks",     # no sentence terminator
        ],
    )
    def test_truncated_takeaway_rejected(self, bad_takeaway: str) -> None:
        with pytest.raises(ValueError):
            self._va(bad_takeaway)


class TestNarrativeListNormalization:
    """Narrative bulleted/numbered lists must be surrounded by blank lines
    (markdownlint MD032). The analyst instructions ask for it but the LLM
    occasionally forgets, so the model normalizes on construction.
    """

    def _va(self, narrative: str) -> VerdictAssessment:
        return VerdictAssessment(
            title="Some title",
            verdict=Verdict.TRUE,
            confidence=Confidence.MEDIUM,
            narrative=narrative,
            topics=[Category.ENVIRONMENTAL_IMPACT],
            verification_level=VerificationLevel.INDEPENDENTLY_VERIFIED,
            seo_title="Some SEO Title",
        )

    def test_inserts_blank_line_before_list(self) -> None:
        v = self._va("These include:\n- one\n- two")
        assert v.narrative == "These include:\n\n- one\n- two"

    def test_inserts_blank_line_after_list(self) -> None:
        v = self._va("- one\n- two\nHowever, the evidence is mixed.")
        assert v.narrative == "- one\n- two\n\nHowever, the evidence is mixed."

    def test_inserts_blanks_on_both_sides(self) -> None:
        v = self._va("Intro paragraph.\n- one\n- two\nClosing paragraph.")
        assert v.narrative == "Intro paragraph.\n\n- one\n- two\n\nClosing paragraph."

    def test_leaves_well_formed_lists_alone(self) -> None:
        original = "Intro.\n\n- one\n- two\n\nOutro."
        assert self._va(original).narrative == original

    def test_handles_numbered_lists(self) -> None:
        v = self._va("Steps:\n1. first\n2. second\nDone.")
        assert v.narrative == "Steps:\n\n1. first\n2. second\n\nDone."

    def test_preserves_indented_continuation(self) -> None:
        original = "Intro.\n\n- item one\n  continuation of one\n- item two\n\nOutro."
        assert self._va(original).narrative == original

    def test_preserves_fenced_code_block(self) -> None:
        # `- foo` inside a fence is content, not a list marker; don't inject blanks.
        original = "Intro.\n\n```\n- not a list\n- still not\n```\n\nOutro."
        assert self._va(original).narrative == original
