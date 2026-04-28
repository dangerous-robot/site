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
"""

query_planner_agent = Agent(
    "test",
    output_type=QueryPlan,
    system_prompt=_PLANNER_INSTRUCTIONS,
    retries=2,
)
