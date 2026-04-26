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
    """Everything the LLM sees -- no verdict, confidence, or title."""

    claim_id: str
    entity: EntityContext
    topics: list[Category] = Field(min_length=1, max_length=3)
    narrative: str  # Markdown body stripped of frontmatter
    sources: list[SourceContext]
    # title deliberately excluded -- often encodes the verdict


class IndependentAssessment(BaseModel):
    """Structured output from the LLM."""

    verdict: Verdict = Field(
        description="Your independent verdict based solely on the narrative and source evidence."
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
