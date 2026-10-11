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
        claim_text="TestCorp meets industry safety standards",
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
            claim_text="X does a thing",
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
            claim_text="Ecosia is hosted on renewable energy",
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


_CLAIM = "ChatGPTree is hosted on renewable energy"
_NARRATIVE = (
    "No source names the data centers behind the product or their energy mix. "
    "The evidence for renewable hosting is missing."
)


def _claim_bundle(claim_text: str = _CLAIM) -> ClaimBundle:
    return ClaimBundle(
        claim_id="chatgptree/renewable-energy-hosting",
        claim_text=claim_text,
        entity=EntityContext(name="ChatGPTree", type="product", description="A chatbot."),
        topics=[Category.ENVIRONMENTAL_IMPACT],
        narrative=_NARRATIVE,
        sources=[],
    )


class TestEvaluatorGradesTheClaim:
    def test_prompt_puts_claim_text_before_narrative(self) -> None:
        prompt = build_auditor_prompt(_claim_bundle())
        assert f"## Claim\n{_CLAIM}" in prompt
        assert prompt.index(_CLAIM) < prompt.index(_NARRATIVE)

    def test_instructions_grade_the_claim(self) -> None:
        from auditor.agent import _INSTRUCTIONS

        assert "ONLY on the narrative" not in _INSTRUCTIONS
        assert "an accurate narrative is not evidence for the claim" in _INSTRUCTIONS.lower()
        assert "narrative" not in IndependentAssessment.model_fields["verdict"].description


def _analyst_output(title: str, verdict: str = "unverified", confidence: str = "low"):
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment

    return AnalystOutput(
        entity=EntityResolution(
            entity_name="ChatGPTree", entity_type="product", entity_description="A chatbot."
        ),
        verdict=VerdictAssessment(
            title=title,
            verdict=verdict,
            confidence=confidence,
            narrative=_NARRATIVE,
            topics=["environmental-impact"],
            verification_level="claimed",
            cap_rationale="Only the entity's own pages address the claim.",
            seo_title="ChatGPTree renewable hosting claim",
        ),
    )


def _capturing_auditor(captured: list[str], verdict: str = "unverified", confidence: str = "low"):
    """Swap in an Evaluator model that records the user prompt and returns a scripted assessment."""
    from contextlib import contextmanager, nullcontext
    from unittest.mock import patch

    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    def _fn(messages, info):
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, UserPromptPart):
                    captured.append(str(part.content))
        args = {"verdict": verdict, "confidence": confidence, "reasoning": "Scripted.",
                "evidence_gaps": []}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    @contextmanager
    def _ctx():
        with auditor_agent.override(model=FunctionModel(_fn)):
            # Keep this model: callers enter their own override with the configured one.
            with patch.object(auditor_agent, "override", side_effect=lambda **kw: nullcontext()):
                yield

    return _ctx()


class TestAuditClaimSendsTheClaim:
    @pytest.mark.asyncio
    async def test_audit_claim_sends_claim_text(self) -> None:
        """The prompt assertion is the point; verdict_agrees and needs_review are wiring
        checks only, since the assessment is scripted."""
        from orchestrator.pipeline import VerifyConfig, _audit_claim

        captured: list[str] = []
        analyst_out = _analyst_output(title="Renewable hosting for the chatbot")
        with _capturing_auditor(captured):
            result = await _audit_claim(
                "ChatGPTree", _CLAIM, analyst_out, [], VerifyConfig(model="test")
            )

        assert any(_CLAIM in p for p in captured)
        assert result is not None
        assert result.verdict_agrees is True
        assert result.needs_review is False

    @pytest.mark.asyncio
    async def test_audit_claim_grades_the_statement_it_is_given(self) -> None:
        """The caller picks the statement (_graded_statement); _audit_claim never swaps it,
        even for text containing the vocabulary hint prefix."""
        from orchestrator.pipeline import VerifyConfig, _audit_claim

        captured: list[str] = []
        claim = "Acme is one of (if not the) largest AI labs"
        title = "Acme ranks among the largest labs"
        analyst_out = _analyst_output(title=title)
        with _capturing_auditor(captured):
            await _audit_claim("Acme", claim, analyst_out, [], VerifyConfig(model="test"))

        prompt = "\n".join(captured)
        assert claim in prompt
        assert title not in prompt
