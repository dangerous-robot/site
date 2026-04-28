"""URL Scorer: scores search candidates by relevance to a claim (tool-free, Haiku)."""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent


class SearchCandidate(BaseModel):
    url: str
    title: str
    snippet: str
    from_query: str


class ScoredURLs(BaseModel):
    kept: list[str] = Field(description="URLs with relevance score >= 3, ordered best-first")
    dropped: list[str] = Field(description="URLs with relevance score < 3")
    rationale: str = Field(description="Brief explanation of scoring decisions")


_SCORER_INSTRUCTIONS = """\
You are a source relevance scorer. Given a claim, entity name, and a list of search result candidates (title + snippet only), score each candidate for relevance to the claim.

Scoring scale:
- 5: Directly addresses the claim with likely primary-source or independent evidence
- 4: Clearly relevant, likely to contain useful facts or data
- 3: Possibly relevant; worth fetching to check
- 2: Tangentially related; unlikely to contain claim-specific evidence
- 1: Not relevant; about a different topic, entity, or time period

Rules:
- Score only on the title and snippet — do not assume body content.
- Keep all candidates with score >= 3 in the `kept` list.
- Put candidates with score < 3 in the `dropped` list.
- Every input URL must appear in either `kept` or `dropped` (no omissions).
- Return URLs as-is (exact strings from input).
- Include a brief `rationale` summarizing the scoring decisions.
"""

url_scorer_agent = Agent(
    "test",
    output_type=ScoredURLs,
    system_prompt=_SCORER_INSTRUCTIONS,
    retries=2,
)
