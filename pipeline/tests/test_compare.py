"""Tests for comparison logic -- pure functions, no mocking."""

from __future__ import annotations

import pytest

from auditor.compare import compare
from auditor.models import IndependentAssessment
from common.models import Confidence, Verdict, VerdictSeverity


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
        result = compare(
            Verdict.TRUE, Confidence.HIGH,
            _make_assessment(Verdict.MOSTLY_TRUE, Confidence.LOW),
            "test/adj-conf-gap", "research/claims/test/adj-conf-gap.md",
        )
        assert result.verdict_severity == VerdictSeverity.ADJACENT
        assert result.confidence_agrees is False
        assert result.needs_review is True

    def test_adjacent_verdict_small_confidence_gap_no_review(self) -> None:
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


class TestNeedsReviewReasons:
    def _reasons(self, primary: Verdict, p_conf: Confidence, assessed: Verdict, a_conf: Confidence, gaps: int = 0):
        from auditor.compare import needs_review_reasons

        result = compare(
            primary, p_conf,
            _make_assessment(assessed, a_conf, [f"gap {i}" for i in range(gaps)]),
            "test/x", "research/claims/test/x.md",
        )
        return needs_review_reasons(result)

    def test_major_gap_is_verdict_disagreement(self) -> None:
        assert self._reasons(Verdict.TRUE, Confidence.HIGH, Verdict.MIXED, Confidence.HIGH) == ["verdict disagreement"]

    def test_opposite_gap_is_verdict_disagreement(self) -> None:
        assert self._reasons(Verdict.TRUE, Confidence.HIGH, Verdict.FALSE, Confidence.HIGH) == ["verdict disagreement"]

    def test_adjacent_with_wide_confidence_gap(self) -> None:
        assert self._reasons(Verdict.TRUE, Confidence.HIGH, Verdict.MOSTLY_TRUE, Confidence.LOW) == ["confidence gap"]

    def test_two_evidence_gaps(self) -> None:
        assert self._reasons(Verdict.TRUE, Confidence.HIGH, Verdict.TRUE, Confidence.HIGH, gaps=2) == ["2+ evidence gaps"]

    def test_reasons_combine(self) -> None:
        assert self._reasons(Verdict.TRUE, Confidence.HIGH, Verdict.FALSE, Confidence.LOW, gaps=3) == [
            "verdict disagreement", "2+ evidence gaps",
        ]

    def test_no_reasons_when_not_flagged(self) -> None:
        assert self._reasons(Verdict.TRUE, Confidence.HIGH, Verdict.MOSTLY_TRUE, Confidence.MEDIUM, gaps=1) == []


# --------------------------------------------------------------------------- #
# RE-AT (Rules, findings file, tie-breaker): the settled verdict                   #
# --------------------------------------------------------------------------- #


class TestNeedsTiebreak:
    """The tie-breaker's trigger is "verdicts differ" only, never the gaps reason."""

    def _compare(self, primary: Verdict, assessed: Verdict, gaps: int = 0):
        return compare(
            primary, Confidence.HIGH,
            _make_assessment(assessed, Confidence.HIGH, [f"gap {i}" for i in range(gaps)]),
            "test/x", "research/claims/test/x.md",
        )

    def test_differing_verdicts_need_the_tiebreaker(self) -> None:
        from auditor.compare import needs_tiebreak

        assert needs_tiebreak(self._compare(Verdict.TRUE, Verdict.MOSTLY_TRUE)) is True
        assert needs_tiebreak(self._compare(Verdict.TRUE, Verdict.FALSE)) is True
        assert needs_tiebreak(self._compare(Verdict.UNVERIFIED, Verdict.TRUE)) is True

    def test_agreement_with_many_gaps_needs_no_tiebreaker(self) -> None:
        from auditor.compare import needs_tiebreak

        result = self._compare(Verdict.TRUE, Verdict.TRUE, gaps=3)
        assert result.needs_review is True, "needs_review keeps its meaning for the packet"
        assert needs_tiebreak(result) is False

    def test_agreement_settles_at_compare_time(self) -> None:
        result = self._compare(Verdict.MIXED, Verdict.MIXED)
        assert result.pipeline_verdict == Verdict.MIXED
        assert result.pipeline_confidence == Confidence.HIGH
        assert result.rule_applied == "agreed"
        assert result.tiebreaker_verdict is None

    def test_disagreement_is_unsettled_until_the_tiebreaker(self) -> None:
        result = self._compare(Verdict.MIXED, Verdict.TRUE)
        assert result.pipeline_verdict is None
        assert result.pipeline_confidence is None
        assert result.rule_applied is None


class TestSettleVerdict:
    def _settle(self, primary, p_conf, assessed, a_conf, tiebreak, t_conf):
        from auditor.compare import settle_verdict

        comparison = compare(
            primary, p_conf, _make_assessment(assessed, a_conf), "test/x", "research/claims/test/x.md",
        )
        return settle_verdict(comparison, _make_assessment(tiebreak, t_conf, ["one gap"]))

    def test_match_with_the_analyst(self) -> None:
        settled = self._settle(Verdict.MIXED, Confidence.MEDIUM, Verdict.TRUE, Confidence.HIGH, Verdict.MIXED, Confidence.LOW)
        assert settled.pipeline_verdict == Verdict.MIXED
        assert settled.pipeline_confidence == Confidence.MEDIUM
        assert settled.rule_applied == "tiebreaker-matched-analyst"
        assert settled.tiebreaker_verdict == Verdict.MIXED
        assert settled.tiebreaker_confidence == Confidence.LOW
        assert settled.tiebreaker_reasoning == "Test reasoning."

    def test_match_with_the_evaluator(self) -> None:
        settled = self._settle(Verdict.MIXED, Confidence.MEDIUM, Verdict.TRUE, Confidence.HIGH, Verdict.TRUE, Confidence.LOW)
        assert settled.pipeline_verdict == Verdict.TRUE
        assert settled.pipeline_confidence == Confidence.HIGH
        assert settled.rule_applied == "tiebreaker-matched-evaluator"

    def test_three_way_split_takes_the_weakest_with_its_confidence(self) -> None:
        settled = self._settle(Verdict.TRUE, Confidence.HIGH, Verdict.FALSE, Confidence.HIGH, Verdict.UNVERIFIED, Confidence.LOW)
        assert settled.pipeline_verdict == Verdict.UNVERIFIED
        assert settled.pipeline_confidence == Confidence.LOW
        assert settled.rule_applied == "three-way-split-weakest"

    def test_three_way_split_can_land_on_the_analyst(self) -> None:
        settled = self._settle(Verdict.MIXED, Confidence.LOW, Verdict.TRUE, Confidence.HIGH, Verdict.FALSE, Confidence.HIGH)
        assert settled.pipeline_verdict == Verdict.MIXED
        assert settled.pipeline_confidence == Confidence.LOW

    def test_rank_tie_prefers_the_tiebreaker_then_the_evaluator(self) -> None:
        settled = self._settle(Verdict.TRUE, Confidence.HIGH, Verdict.MOSTLY_TRUE, Confidence.MEDIUM, Verdict.MOSTLY_FALSE, Confidence.LOW)
        assert settled.pipeline_verdict == Verdict.MOSTLY_FALSE
        assert settled.pipeline_confidence == Confidence.LOW
        settled = self._settle(Verdict.MOSTLY_TRUE, Confidence.MEDIUM, Verdict.MOSTLY_FALSE, Confidence.HIGH, Verdict.TRUE, Confidence.HIGH)
        assert settled.pipeline_verdict == Verdict.MOSTLY_TRUE
        assert settled.pipeline_confidence == Confidence.MEDIUM

    def test_settle_keeps_the_comparison_fields(self) -> None:
        settled = self._settle(Verdict.MIXED, Confidence.MEDIUM, Verdict.TRUE, Confidence.HIGH, Verdict.TRUE, Confidence.LOW)
        assert settled.primary_verdict == Verdict.MIXED
        assert settled.assessed_verdict == Verdict.TRUE
        assert settled.verdict_agrees is False
        assert settled.needs_review is True

    def test_settle_without_a_tiebreak_on_a_disagreement_is_refused(self) -> None:
        from auditor.compare import settle_verdict

        comparison = compare(
            Verdict.MIXED, Confidence.MEDIUM, _make_assessment(Verdict.TRUE, Confidence.HIGH),
            "test/x", "research/claims/test/x.md",
        )
        with pytest.raises(ValueError):
            settle_verdict(comparison, None)
