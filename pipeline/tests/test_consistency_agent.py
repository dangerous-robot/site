"""Tests for the consistency agent using PydanticAI TestModel."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from common.models import Category, Confidence, Verdict

from consistency.agent import ConsistencyDeps, build_user_prompt, consistency_agent
from consistency.models import ClaimBundle, EntityContext, IndependentAssessment, SourceContext


def _sample_bundle() -> ClaimBundle:
    return ClaimBundle(
        claim_id="test/sample-claim",
        entity=EntityContext(
            name="TestCorp",
            type="company",
            description="A fictional company for testing.",
        ),
        category=Category.AI_SAFETY,
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
        """Agent round-trip with TestModel produces a valid IndependentAssessment."""
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)
        deps = ConsistencyDeps(repo_root="/tmp/fake-repo")

        with consistency_agent.override(model=TestModel()):
            result = await consistency_agent.run(prompt, deps=deps)

        assessment = result.output
        assert isinstance(assessment, IndependentAssessment)
        assert isinstance(assessment.verdict, Verdict)
        assert isinstance(assessment.confidence, Confidence)
        assert len(assessment.reasoning) > 0


class TestBuildUserPrompt:
    def test_prompt_contains_entity_info(self) -> None:
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)
        assert "TestCorp" in prompt
        assert "company" in prompt
        assert "A fictional company for testing." in prompt

    def test_prompt_contains_category(self) -> None:
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)
        assert "ai-safety" in prompt

    def test_prompt_contains_narrative(self) -> None:
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)
        assert "TestCorp has implemented safety measures" in prompt

    def test_prompt_contains_source_details(self) -> None:
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)
        assert "TestCorp Safety Audit" in prompt
        assert "Independent Safety Org" in prompt
        assert "TestCorp meets baseline safety requirements." in prompt

    def test_prompt_no_sources(self) -> None:
        bundle = ClaimBundle(
            claim_id="test/no-sources",
            entity=EntityContext(name="X", type="company", description="Desc."),
            category=Category.AI_SAFETY,
            narrative="A claim.",
            sources=[],
        )
        prompt = build_user_prompt(bundle)
        assert "No sources provided." in prompt


class TestBundleNeverLeaksVerdict:
    """Validate the information asymmetry design principle.

    The serialized prompt must NOT contain the claim's verdict value,
    confidence value, or title. This ensures the LLM forms an independent
    assessment.
    """

    def test_prompt_excludes_verdict(self) -> None:
        """The prompt string should not contain verdict keywords in a way
        that leaks the actual verdict assignment."""
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)

        # The prompt should not contain patterns like "verdict: true" or
        # "verdict: false" that would leak the actual claim verdict.
        # The word "verdict" may appear in instructions, but not as a
        # leaked frontmatter value assignment.
        assert "verdict:" not in prompt.lower()

    def test_prompt_excludes_confidence(self) -> None:
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)
        assert "confidence:" not in prompt.lower()

    def test_prompt_excludes_title(self) -> None:
        """Title is deliberately excluded from ClaimBundle."""
        bundle = _sample_bundle()
        prompt = build_user_prompt(bundle)
        # A title like "TestCorp safety practices are inadequate" could
        # encode a verdict, so it must not be present.
        # Since ClaimBundle has no title field, we verify no title-like
        # header is present beyond the structural headers.
        # The word "title" should not appear as a metadata key.
        assert "title:" not in prompt.lower()

    def test_bundle_model_has_no_verdict_field(self) -> None:
        fields = set(ClaimBundle.model_fields.keys())
        assert "verdict" not in fields
        assert "confidence" not in fields
        assert "title" not in fields

    def test_real_claim_verdict_not_in_prompt(self) -> None:
        """Build a bundle mimicking a real claim and verify its verdict
        string does not appear as a metadata assignment in the prompt."""
        bundle = ClaimBundle(
            claim_id="ecosia/renewable-energy-hosting",
            entity=EntityContext(
                name="Ecosia",
                type="company",
                description="Search engine that plants trees.",
            ),
            category=Category.ENVIRONMENTAL_IMPACT,
            narrative="Ecosia's AI chat uses GPT-4 mini on Azure infrastructure.",
            sources=[],
        )
        prompt = build_user_prompt(bundle)
        # Verify no verdict/confidence metadata leaks
        assert "verdict:" not in prompt.lower()
        assert "confidence:" not in prompt.lower()
