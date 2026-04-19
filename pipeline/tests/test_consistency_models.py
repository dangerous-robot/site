"""Tests for consistency check models."""

from __future__ import annotations

from common.models import Category, Confidence, Verdict, VerdictSeverity

from consistency.models import (
    ClaimBundle,
    ComparisonResult,
    EntityContext,
    IndependentAssessment,
    SourceContext,
)


class TestClaimBundle:
    def test_valid_construction(self) -> None:
        bundle = ClaimBundle(
            claim_id="ecosia/renewable-energy-hosting",
            entity=EntityContext(
                name="Ecosia",
                type="company",
                description="Search engine that plants trees.",
            ),
            category=Category.ENVIRONMENTAL_IMPACT,
            narrative="Ecosia claims renewable energy for its servers.",
            sources=[
                SourceContext(
                    id="2025/earthday-chatgpt-prompt-cost",
                    title="The True Price of Every ChatGPT Prompt",
                    publisher="Earth Day",
                    summary="Analysis of environmental costs per AI query.",
                    key_quotes=[],
                    body="Details about energy costs.",
                )
            ],
        )
        assert bundle.claim_id == "ecosia/renewable-energy-hosting"
        assert bundle.entity.name == "Ecosia"
        assert bundle.category == Category.ENVIRONMENTAL_IMPACT
        assert len(bundle.sources) == 1

    def test_empty_sources(self) -> None:
        bundle = ClaimBundle(
            claim_id="test/no-sources",
            entity=EntityContext(name="Test", type="company", description="A test entity."),
            category=Category.AI_SAFETY,
            narrative="A claim with no sources.",
            sources=[],
        )
        assert bundle.sources == []

    def test_no_verdict_or_title_fields(self) -> None:
        """ClaimBundle must not have verdict, confidence, or title fields."""
        fields = set(ClaimBundle.model_fields.keys())
        assert "verdict" not in fields
        assert "confidence" not in fields
        assert "title" not in fields


class TestIndependentAssessment:
    def test_valid_construction(self) -> None:
        assessment = IndependentAssessment(
            verdict=Verdict.MOSTLY_TRUE,
            confidence=Confidence.MEDIUM,
            reasoning="The evidence largely supports the claim with minor gaps.",
            evidence_gaps=["No independent audit cited"],
        )
        assert assessment.verdict == Verdict.MOSTLY_TRUE
        assert assessment.confidence == Confidence.MEDIUM
        assert len(assessment.evidence_gaps) == 1

    def test_defaults(self) -> None:
        assessment = IndependentAssessment(
            verdict=Verdict.TRUE,
            confidence=Confidence.HIGH,
            reasoning="Strong evidence.",
        )
        assert assessment.evidence_gaps == []

    def test_all_verdicts_accepted(self) -> None:
        for v in Verdict:
            a = IndependentAssessment(
                verdict=v, confidence=Confidence.MEDIUM, reasoning="Test."
            )
            assert a.verdict == v


class TestComparisonResult:
    def test_valid_construction(self) -> None:
        result = ComparisonResult(
            claim_id="ecosia/renewable-energy-hosting",
            claim_file="research/claims/ecosia/renewable-energy-hosting.md",
            actual_verdict=Verdict.FALSE,
            assessed_verdict=Verdict.MOSTLY_FALSE,
            actual_confidence=Confidence.MEDIUM,
            assessed_confidence=Confidence.MEDIUM,
            reasoning="Evidence suggests the claim is mostly unsupported.",
            evidence_gaps=[],
            verdict_agrees=False,
            confidence_agrees=True,
            verdict_severity=VerdictSeverity.ADJACENT,
            needs_review=False,
        )
        assert result.claim_id == "ecosia/renewable-energy-hosting"
        assert result.verdict_agrees is False
        assert result.confidence_agrees is True
        assert result.verdict_severity == VerdictSeverity.ADJACENT
        assert result.needs_review is False
