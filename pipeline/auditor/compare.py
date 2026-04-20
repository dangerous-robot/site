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

    needs_review = (
        severity in (VerdictSeverity.MAJOR, VerdictSeverity.OPPOSITE)
        or (severity == VerdictSeverity.ADJACENT and conf_dist >= 2)
        or len(assessment.evidence_gaps) > 1
    )

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
    )
