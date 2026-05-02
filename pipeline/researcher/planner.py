"""Query Planner: generates search queries for a claim (tool-free, Haiku)."""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent


class QueryPlan(BaseModel):
    queries: list[str] = Field(description="Search queries to execute, ordered by expected relevance")
    rationale: str = Field(description="Why these queries cover the claim")


_PLANNER_INSTRUCTIONS = """\
You are a search query planner. Given a claim and entity name, generate targeted web search queries to find credible sources that could verify or refute the claim.

Rules:
- Generate between 2 and the cap given in the user prompt.
- Each query should be specific: include the entity name and key terms from the claim.
- Vary the angle: one query may target the entity directly, another may target an independent analysis, another a specific data point.
- Prefer queries that would surface primary sources or independent journalism over opinion pieces.
- Do not repeat the same query with minor word changes.
- Return queries in the `queries` field. Include a brief `rationale` explaining why these queries cover the claim.

Brave Search query format (important — these run on Brave, not Google):
- Do NOT use Google-specific operators: no `site:`, `source:`, `date:`, `filetype:`, `intitle:`, `inurl:`.
- Do NOT chain multiple quoted phrases. Use at most one short quoted phrase per query, reserved for exact proper nouns or document titles. Multiple quoted phrases chained together nearly always return zero results.
- Keep queries short: 3–7 words. Natural keyword combinations outperform complex boolean syntax on Brave.
- For sector-level or abstract entities (e.g. "AI/LLM producers", "cloud providers"), skip the entity name and query by the concrete subject matter directly (e.g. "Bletchley Park AI safety commitments" rather than "AI/LLM producers safety pledges").
"""

query_planner_agent = Agent(
    "test",
    output_type=QueryPlan,
    system_prompt=_PLANNER_INSTRUCTIONS,
    retries=2,
)
