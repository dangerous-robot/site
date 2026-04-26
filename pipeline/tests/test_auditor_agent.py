"""Tests for the auditor agent using PydanticAI TestModel."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from auditor.agent import auditor_agent, build_auditor_prompt
from auditor.models import ClaimBundle, EntityContext, IndependentAssessment, SourceContext
from common.models import Category, Confidence, Verdict


def _sample_bundle() -> ClaimBundle:
    return ClaimBundle(
        claim_id="test/sample-claim",
        entity=EntityContext(
            name="TestCorp",
            type="company",
            description="A fictional company for testing.",
        ),
        topics=[Category.AI_SAFETY],
        narrative="TestCorp has implemented safety measures that meet industry standards.",
        sources=[
            SourceContext(
                id="2025/test-source",
                title="TestCorp Safety Audit",
                publisher="Independent Safety Org",
                summary="Audit of TestCorp safety practices.",
                key_quotes=["TestCorp meets baseline safety requirements."],
                body="The audit found that TestCorp has adequate safety measures in place.",
            )
        ],
    )


class TestAgentRoundTrip:
    @pytest.mark.asyncio
    async def test_produces_valid_assessment(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)

        with auditor_agent.override(model=TestModel()):
            result = await auditor_agent.run(prompt)

        assessment = result.output
        assert isinstance(assessment, IndependentAssessment)
        assert isinstance(assessment.verdict, Verdict)
        assert isinstance(assessment.confidence, Confidence)
        assert len(assessment.reasoning) > 0


class TestBuildAuditorPrompt:
    def test_prompt_contains_entity_info(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)
        assert "TestCorp" in prompt
        assert "company" in prompt
        assert "A fictional company for testing." in prompt

    def test_prompt_contains_topic(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)
        assert "ai-safety" in prompt

    def test_prompt_contains_narrative(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)
        assert "TestCorp has implemented safety measures" in prompt

    def test_prompt_contains_source_details(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)
        assert "TestCorp Safety Audit" in prompt
        assert "Independent Safety Org" in prompt
        assert "TestCorp meets baseline safety requirements." in prompt

    def test_prompt_no_sources(self) -> None:
        bundle = ClaimBundle(
            claim_id="test/no-sources",
            entity=EntityContext(name="X", type="company", description="Desc."),
            topics=[Category.AI_SAFETY],
            narrative="A claim.",
            sources=[],
        )
        prompt = build_auditor_prompt(bundle)
        assert "No sources provided." in prompt


class TestBundleNeverLeaksVerdict:
    def test_prompt_excludes_verdict(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)
        assert "verdict:" not in prompt.lower()

    def test_prompt_excludes_confidence(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)
        assert "confidence:" not in prompt.lower()

    def test_prompt_excludes_title(self) -> None:
        bundle = _sample_bundle()
        prompt = build_auditor_prompt(bundle)
        assert "title:" not in prompt.lower()

    def test_bundle_model_has_no_verdict_field(self) -> None:
        fields = set(ClaimBundle.model_fields.keys())
        assert "verdict" not in fields
        assert "confidence" not in fields
        assert "title" not in fields

    def test_real_claim_verdict_not_in_prompt(self) -> None:
        bundle = ClaimBundle(
            claim_id="ecosia/renewable-energy-hosting",
            entity=EntityContext(
                name="Ecosia",
                type="company",
                description="Search engine that plants trees.",
            ),
            topics=[Category.ENVIRONMENTAL_IMPACT],
            narrative="Ecosia's AI chat uses GPT-4 mini on Azure infrastructure.",
            sources=[],
        )
        prompt = build_auditor_prompt(bundle)
        assert "verdict:" not in prompt.lower()
        assert "confidence:" not in prompt.lower()
