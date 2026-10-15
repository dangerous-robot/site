"""Pydantic models for the auditor agent."""

from __future__ import annotations

from pydantic import BaseModel, Field

from common.models import Category, Confidence, Verdict, VerdictSeverity


class SourceContext(BaseModel):
    """Projection of source data for LLM context."""

    id: str
    title: str
    publisher: str
    summary: str
    key_quotes: list[str] = Field(default_factory=list)
    body: str


class EntityContext(BaseModel):
    """Basic entity info for LLM context."""

    name: str
    type: str
    description: str


class ClaimBundle(BaseModel):
    """Everything the LLM sees -- no analyst verdict or confidence."""

    claim_id: str
    # The claim under test, with any vocabulary slot resolved to one value.
    # The Evaluator grades this statement; the narrative is the analyst's
    # argument and is never the thing graded.
    claim_text: str
    entity: EntityContext
    topics: list[Category] = Field(min_length=1, max_length=3)
    narrative: str  # Markdown body stripped of frontmatter
    sources: list[SourceContext]
    # The criterion's template notes, the same text the analyst received, so a
    # verdict that follows a note's mapping is not graded as a scale mismatch.
    criterion_notes: str | None = None


class IndependentAssessment(BaseModel):
    """Structured output from the LLM."""

    verdict: Verdict = Field(
        description="Your independent verdict on the claim statement, judged against the source materials only."
    )
    confidence: Confidence = Field(
        description="How confident you are in the evidence supporting this verdict."
    )
    reasoning: str = Field(
        description="2-4 sentences explaining your verdict. Reference specific sources."
    )
    evidence_gaps: list[str] = Field(
        default_factory=list,
        description="Gaps in the evidence that limit your confidence.",
    )


class ComparisonResult(BaseModel):
    """Result of comparing the auditor assessment against the primary claim."""

    claim_id: str
    claim_file: str
    primary_verdict: Verdict
    assessed_verdict: Verdict
    primary_confidence: Confidence
    assessed_confidence: Confidence
    reasoning: str
    evidence_gaps: list[str]
    verdict_agrees: bool
    confidence_agrees: bool
    verdict_severity: VerdictSeverity
    needs_review: bool
    # The settled verdict (``compare.settle_verdict``). An agreement is settled
    # at compare time; a disagreement stays None until the tie-breaker runs.
    tiebreaker_verdict: Verdict | None = None
    tiebreaker_confidence: Confidence | None = None
    tiebreaker_reasoning: str | None = None
    pipeline_verdict: Verdict | None = None
    pipeline_confidence: Confidence | None = None
    rule_applied: str | None = None
