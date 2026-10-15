"""The restater's input bundle and output models.

Field shapes follow the absorbed design
(``docs/plans/completed/claim-restate_superseded.md`` § The agent). The bundle
carries the pipeline verdict, so the agent explains a gap rather than
re-judging the claim, and never the Evaluator's or the tie-breaker's
reasoning or a verdict any candidate should get.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analyst.citations import has_citation_reference
from common.models import Confidence, Verdict, VerificationLevel


class Frame(str, Enum):
    """What a candidate asserts; neutral names, none ranked above another."""

    NARROWED = "narrowed"          # same assertion, smaller scope (one service, one year, one site)
    DISCLOSURE = "disclosure"      # what the entity has or has not published
    SUPPLIER = "supplier"          # a named supplier's practice
    COMMITMENT = "commitment"      # a stated goal or pledge, not a practice
    MEASUREMENT = "measurement"    # a number a source reports
    OTHER = "other"


class WhyUnverified(str, Enum):
    """Why the original's verdict is weak, one value per recurring reason."""

    QUANTIFIER_UNSUPPORTED = "quantifier-unsupported"  # a count, threshold or population no source tallies
    TERM_MISMATCH = "term-mismatch"                    # the claim's word is not the sources' word
    UPSTREAM_PROVIDER = "upstream-provider"            # the fact belongs to a provider, named or not
    ENTITY_SILENT = "entity-silent"                    # the entity publishes nothing on it
    OTHER = "other"


# The restater's output models forbid unknown keys: a model that answers with
# a key of its own (``evidence`` for ``supporting``) is told the key is not
# allowed and asked again, rather than having its quotes silently dropped.


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str                                     # a source id from the bundle
    quote: str = Field(max_length=300)              # verbatim passage the candidate relies on
    note: str = Field(max_length=200)               # what the passage establishes


class RestatementCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # One affirmative sentence with the entity as subject; polarity lives in the verdict.
    text: str = Field(max_length=200)
    frame: Frame
    expected_verdict: Verdict
    expected_confidence: Confidence
    verification_level_estimate: VerificationLevel
    decisiveness: int = Field(ge=0, le=4)
    # ``supporting`` backs the expected verdict, whichever direction it is;
    # ``contradicting`` cuts against it. Both are required (an empty list is
    # an answer) so a missing key is re-asked, never defaulted.
    supporting: list[EvidenceRef]
    contradicting: list[EvidenceRef]
    needs_new_research: bool
    # Reader-facing: cites sources by title, never by id or "Source N".
    rationale: str = Field(max_length=400)

    @field_validator("rationale")
    @classmethod
    def _no_citations(cls, v: str) -> str:
        if has_citation_reference(v):
            raise ValueError("cites a source (【...】 token or \"Source N\"); name the source by its title")
        return v


class RestatementProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    why_unverified: WhyUnverified
    why_unverified_note: str = Field(max_length=400)
    candidates: list[RestatementCandidate] = Field(min_length=1, max_length=5)


class RestateSource(BaseModel):
    """One source as the restater sees it, with the marker saying where it came from."""

    id: str
    marker: str                                     # "cited", "consulted" or "archive"
    title: str = ""
    publisher: str = ""
    kind: str = ""
    independence: str = ""
    summary: str = ""
    key_quotes: list[str] = Field(default_factory=list)
    body: str = ""


class RestateBundle(BaseModel):
    """Everything the restater's prompt is built from."""

    statement: str
    pipeline_verdict: str
    pipeline_confidence: str
    # The tie-breaker's rule when it settled the verdict, else None.
    tiebreak_rule: str | None = None
    narrative: str = ""
    evidence_gaps: list[str] = Field(default_factory=list)
    entity_name: str
    entity_aliases: list[str] = Field(default_factory=list)
    entity_type: str = ""
    entity_description: str = ""
    max_candidates: int = 5
    sources: list[RestateSource] = Field(default_factory=list)


@dataclass(frozen=True)
class RestaterDeps:
    """What the restater's output check needs: the names a candidate may use."""

    allowed_names: tuple[str, ...]
