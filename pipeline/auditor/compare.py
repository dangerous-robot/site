"""Comparison logic: verdict ordering, severity, needs_review."""

from __future__ import annotations

from common.models import Confidence, Verdict, VerdictSeverity

from .models import ComparisonResult, IndependentAssessment

VERDICT_ORDER: dict[Verdict, int] = {
    Verdict.TRUE: 0,
    Verdict.MOSTLY_TRUE: 1,
    Verdict.MIXED: 2,
    Verdict.MOSTLY_FALSE: 3,
    Verdict.FALSE: 4,
}
# Verdict.UNVERIFIED is off-scale -- handled separately

CONFIDENCE_ORDER: dict[Confidence, int] = {
    Confidence.HIGH: 0,
    Confidence.MEDIUM: 1,
    Confidence.LOW: 2,
}


def _verdict_severity(primary: Verdict, assessed: Verdict) -> VerdictSeverity:
    """Determine the severity of a verdict disagreement."""
    if primary == assessed:
        return VerdictSeverity.MATCH

    a_ordinal = VERDICT_ORDER.get(primary)
    b_ordinal = VERDICT_ORDER.get(assessed)

    if a_ordinal is None or b_ordinal is None:
        return VerdictSeverity.MAJOR

    distance = abs(a_ordinal - b_ordinal)
    if distance == 1:
        return VerdictSeverity.ADJACENT
    if distance == 2:
        return VerdictSeverity.MAJOR
    return VerdictSeverity.OPPOSITE


def _confidence_distance(primary: Confidence, assessed: Confidence) -> int:
    """Number of steps apart on the confidence scale."""
    return abs(CONFIDENCE_ORDER[primary] - CONFIDENCE_ORDER[assessed])


def _review_reasons(severity: VerdictSeverity, conf_dist: int, gap_count: int) -> list[str]:
    reasons = []
    if severity in (VerdictSeverity.MAJOR, VerdictSeverity.OPPOSITE):
        reasons.append("verdict disagreement")
    if severity == VerdictSeverity.ADJACENT and conf_dist >= 2:
        reasons.append("confidence gap")
    if gap_count > 1:
        reasons.append("2+ evidence gaps")
    return reasons


def needs_review_reasons(result: ComparisonResult) -> list[str]:
    """Why the evaluator flagged this claim for human review; empty when it did not."""
    return _review_reasons(
        result.verdict_severity,
        _confidence_distance(result.primary_confidence, result.assessed_confidence),
        len(result.evidence_gaps),
    )


def compare(
    primary_verdict: Verdict,
    primary_confidence: Confidence,
    assessment: IndependentAssessment,
    claim_id: str,
    claim_file: str,
) -> ComparisonResult:
    """Compare an auditor assessment against the primary claim metadata."""
    verdict_agrees = primary_verdict == assessment.verdict
    confidence_agrees = primary_confidence == assessment.confidence
    severity = _verdict_severity(primary_verdict, assessment.verdict)
    conf_dist = _confidence_distance(primary_confidence, assessment.confidence)

    needs_review = bool(_review_reasons(severity, conf_dist, len(assessment.evidence_gaps)))

    settled: dict = {}
    if verdict_agrees:
        settled = {
            "pipeline_verdict": primary_verdict,
            "pipeline_confidence": primary_confidence,
            "rule_applied": "agreed",
        }

    return ComparisonResult(
        claim_id=claim_id,
        claim_file=claim_file,
        primary_verdict=primary_verdict,
        assessed_verdict=assessment.verdict,
        primary_confidence=primary_confidence,
        assessed_confidence=assessment.confidence,
        reasoning=assessment.reasoning,
        evidence_gaps=assessment.evidence_gaps,
        verdict_agrees=verdict_agrees,
        confidence_agrees=confidence_agrees,
        verdict_severity=severity,
        needs_review=needs_review,
        **settled,
    )


# How strong a claim each verdict makes (Q-B5, the tie-breaker ordering): a
# three-way split settles on the weakest. Polarity does not count, so
# mostly-true and mostly-false rank together, as do true and false.
VERDICT_STRENGTH: dict[Verdict, int] = {
    Verdict.NOT_APPLICABLE: 0,
    Verdict.UNVERIFIED: 1,
    Verdict.MIXED: 2,
    Verdict.MOSTLY_TRUE: 3,
    Verdict.MOSTLY_FALSE: 3,
    Verdict.TRUE: 4,
    Verdict.FALSE: 4,
}


def needs_tiebreak(result: ComparisonResult) -> bool:
    """True when the verdicts differ; evidence gaps alone never call the tie-breaker."""
    return not result.verdict_agrees


def _polarity(verdict: Verdict) -> int:
    """-1 on the true side of the scale, 1 on the false side, 0 off it or in the middle."""
    order = VERDICT_ORDER.get(verdict)
    if order is None or order == VERDICT_ORDER[Verdict.MIXED]:
        return 0
    return -1 if order < VERDICT_ORDER[Verdict.MIXED] else 1


def settle_verdict(result: ComparisonResult, tiebreak: IndependentAssessment | None) -> ComparisonResult:
    """Settle a disagreement with the tie-breaker's blind assessment.

    A tie-breaker verdict equal to either side's is the pipeline verdict, with
    that side's confidence. Three distinct verdicts settle on the weakest by
    ``VERDICT_STRENGTH``, with its side's confidence. A rank tie (mostly-true
    against mostly-false) goes to the verdict on the tie-breaker's side of the
    scale, then to the Evaluator's.

    An agreement is returned unchanged; a disagreement with no assessment
    raises ``ValueError``.
    """
    if result.verdict_agrees:
        return result
    if tiebreak is None:
        raise ValueError("a verdict disagreement needs the tie-breaker's assessment to settle")
    update: dict = {
        "tiebreaker_verdict": tiebreak.verdict,
        "tiebreaker_confidence": tiebreak.confidence,
        "tiebreaker_reasoning": tiebreak.reasoning,
    }
    if tiebreak.verdict == result.primary_verdict:
        update.update(
            pipeline_verdict=result.primary_verdict,
            pipeline_confidence=result.primary_confidence,
            rule_applied="tiebreaker-matched-analyst",
        )
    elif tiebreak.verdict == result.assessed_verdict:
        update.update(
            pipeline_verdict=result.assessed_verdict,
            pipeline_confidence=result.assessed_confidence,
            rule_applied="tiebreaker-matched-evaluator",
        )
    else:
        # Preference order on a rank tie: the tie-breaker, the Evaluator, the analyst.
        sides = [
            (tiebreak.verdict, tiebreak.confidence),
            (result.assessed_verdict, result.assessed_confidence),
            (result.primary_verdict, result.primary_confidence),
        ]
        weakest = min(VERDICT_STRENGTH[v] for v, _c in sides)
        tied = [side for side in sides if VERDICT_STRENGTH[side[0]] == weakest]
        same_side = [s for s in tied if _polarity(s[0]) == _polarity(tiebreak.verdict) != 0]
        verdict, confidence = (same_side or tied)[0]
        update.update(
            pipeline_verdict=verdict,
            pipeline_confidence=confidence,
            rule_applied="three-way-split-weakest",
        )
    return result.model_copy(update=update)
