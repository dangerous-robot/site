"""Tests for comparison logic -- pure functions, no mocking."""

from __future__ import annotations

from common.models import Confidence, Verdict, VerdictSeverity

from consistency.compare import compare
from consistency.models import IndependentAssessment


def _make_assessment(
    verdict: Verdict,
    confidence: Confidence,
    gaps: list[str] | None = None,
) -> IndependentAssessment:
    return IndependentAssessment(
        verdict=verdict,
        confidence=confidence,
        reasoning="Test reasoning.",
        evidence_gaps=gaps or [],
    )


class TestExactMatch:
    def test_true_true(self) -> None:
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.TRUE, Confidence.HIGH),
            "test/exact-match", "research/claims/test/exact-match.md",
        )
        assert result.verdict_agrees is True
        assert result.confidence_agrees is True
        assert result.verdict_severity == VerdictSeverity.MATCH
        assert result.needs_review is False

    def test_false_false(self) -> None:
        result = compare(
            Verdict.FALSE, Confidence.LOW,
            _make_assessment(Verdict.FALSE, Confidence.LOW),
            "test/false-match", "research/claims/test/false-match.md",
        )
        assert result.verdict_severity == VerdictSeverity.MATCH
        assert result.needs_review is False


class TestAdjacentSameConfidence:
    def test_true_mostly_true(self) -> None:
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.MOSTLY_TRUE, Confidence.HIGH),
            "test/adjacent", "research/claims/test/adjacent.md",
        )
        assert result.verdict_agrees is False
        assert result.confidence_agrees is True
        assert result.verdict_severity == VerdictSeverity.ADJACENT
        assert result.needs_review is False

    def test_mixed_mostly_false(self) -> None:
        result = compare(
            Verdict.MIXED, Confidence.MEDIUM,
            _make_assessment(Verdict.MOSTLY_FALSE, Confidence.MEDIUM),
            "test/adjacent-2", "research/claims/test/adjacent-2.md",
        )
        assert result.verdict_severity == VerdictSeverity.ADJACENT
        assert result.needs_review is False


class TestAdjacentConfidenceGap:
    def test_adjacent_verdict_big_confidence_gap_triggers_review(self) -> None:
        """Adjacent verdict + 2-step confidence gap -> needs review."""
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.MOSTLY_TRUE, Confidence.LOW),
            "test/adj-conf-gap", "research/claims/test/adj-conf-gap.md",
        )
        assert result.verdict_severity == VerdictSeverity.ADJACENT
        assert result.confidence_agrees is False
        assert result.needs_review is True

    def test_adjacent_verdict_small_confidence_gap_no_review(self) -> None:
        """Adjacent verdict + 1-step confidence gap -> no review."""
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.MOSTLY_TRUE, Confidence.MEDIUM),
            "test/adj-small-gap", "research/claims/test/adj-small-gap.md",
        )
        assert result.verdict_severity == VerdictSeverity.ADJACENT
        assert result.needs_review is False


class TestMajorDisagreement:
    def test_true_mixed(self) -> None:
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.MIXED, Confidence.MEDIUM),
            "test/major", "research/claims/test/major.md",
        )
        assert result.verdict_severity == VerdictSeverity.MAJOR
        assert result.needs_review is True

    def test_mostly_true_mostly_false(self) -> None:
        result = compare(
            Verdict.MOSTLY_TRUE, Confidence.MEDIUM,
            _make_assessment(Verdict.MOSTLY_FALSE, Confidence.MEDIUM),
            "test/major-2", "research/claims/test/major-2.md",
        )
        assert result.verdict_severity == VerdictSeverity.MAJOR
        assert result.needs_review is True


class TestOppositeDisagreement:
    def test_true_false(self) -> None:
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.FALSE, Confidence.HIGH),
            "test/opposite", "research/claims/test/opposite.md",
        )
        assert result.verdict_severity == VerdictSeverity.OPPOSITE
        assert result.needs_review is True

    def test_true_mostly_false(self) -> None:
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.MOSTLY_FALSE, Confidence.LOW),
            "test/opposite-2", "research/claims/test/opposite-2.md",
        )
        assert result.verdict_severity == VerdictSeverity.OPPOSITE
        assert result.needs_review is True


class TestUnverified:
    def test_unverified_vs_ordinal(self) -> None:
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.UNVERIFIED, Confidence.LOW),
            "test/unverified", "research/claims/test/unverified.md",
        )
        assert result.verdict_severity == VerdictSeverity.MAJOR
        assert result.needs_review is True

    def test_ordinal_vs_unverified(self) -> None:
        result = compare(
            Verdict.UNVERIFIED, Confidence.LOW,
            _make_assessment(Verdict.MOSTLY_TRUE, Confidence.MEDIUM),
            "test/unverified-2", "research/claims/test/unverified-2.md",
        )
        assert result.verdict_severity == VerdictSeverity.MAJOR
        assert result.needs_review is True

    def test_both_unverified(self) -> None:
        result = compare(
            Verdict.UNVERIFIED, Confidence.LOW,
            _make_assessment(Verdict.UNVERIFIED, Confidence.LOW),
            "test/both-unverified", "research/claims/test/both-unverified.md",
        )
        assert result.verdict_severity == VerdictSeverity.MATCH
        assert result.needs_review is False


class TestEvidenceGapsTriggerReview:
    def test_match_with_many_gaps_triggers_review(self) -> None:
        """Even with matching verdict, >1 evidence gap triggers review."""
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.TRUE, Confidence.HIGH, gaps=[
                "No independent audit",
                "Self-reported data only",
            ]),
            "test/gaps", "research/claims/test/gaps.md",
        )
        assert result.verdict_agrees is True
        assert result.verdict_severity == VerdictSeverity.MATCH
        assert result.needs_review is True

    def test_match_with_one_gap_no_review(self) -> None:
        """Matching verdict with exactly one gap does not trigger review."""
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.TRUE, Confidence.HIGH, gaps=["Minor gap"]),
            "test/one-gap", "research/claims/test/one-gap.md",
        )
        assert result.needs_review is False

    def test_match_with_zero_gaps_no_review(self) -> None:
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.TRUE, Confidence.HIGH, gaps=[]),
            "test/no-gaps", "research/claims/test/no-gaps.md",
        )
        assert result.needs_review is False
