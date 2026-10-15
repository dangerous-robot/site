"""Research Planner: decomposes a claim into sub-questions and tagged queries (tool-free, Haiku)."""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent

from common.models import SubQuestion


class PlannedQuery(BaseModel):
    text: str
    sub_question_id: str = Field(
        description="Matches a SubQuestion.id within the same ResearchPlan."
    )


class ResearchPlan(BaseModel):
    sub_questions: list[SubQuestion] = Field(min_length=2, max_length=6)
    queries: list[PlannedQuery] = Field(
        description="Search queries, each tagged with the sub-question it serves.",
    )
    rationale: str = Field(
        description="One-line justification for why these sub-questions cover the claim.",
    )

    @model_validator(mode="after")
    def _one_counter_evidence_sub_question(self) -> "ResearchPlan":
        # A plan that never looks for what would falsify the claim is a flaw,
        # like a plan with no queries: raising makes PydanticAI retry the planner.
        counter = [sq.id for sq in self.sub_questions if sq.kind == "counter-evidence"]
        if len(counter) != 1:
            raise ValueError(
                f"the plan needs exactly one sub-question with kind 'counter-evidence', not {len(counter)}"
            )
        if not any(q.sub_question_id == counter[0] for q in self.queries):
            raise ValueError(f"the counter-evidence sub-question {counter[0]} needs at least one query")
        return self


_RESEARCH_PLANNER_INSTRUCTIONS = """\
You are a research planner. Given a claim and entity, decompose the claim into 2-5 sub-questions, then generate search queries per sub-question.

A good sub-question is independently answerable, factually framed, and covers one axis of the claim. The union of sub-questions should cover the whole claim. Sub-question ids are sequential (sq1, sq2, ...).

Besides the 2-5 coverage sub-questions (`kind: coverage`, the default), add exactly one sub-question with `kind: counter-evidence`: it asks what evidence would falsify the claim (a contrary measurement, a dispute, a retraction, a later change), and it gets at least one query of its own.

For environmental, privacy, and disclosure claims, sub-questions typically include: (1) the entity's own first-party publication channels (transparency reports, sustainability pages), (2) third-party databases (ESG aggregators, regulator filings, model cards), (3) the underlying technical or factual mechanism (e.g. hosting provider, training pipeline). Cover all three when applicable.

Then generate 2 to `max_initial_queries` total search queries, distributed across sub-questions. Each query is tagged with `sub_question_id`. Queries must follow Brave query format (no `site:`, no `intitle:`, no chained quoted phrases - see below).

Brave Search query format (important — these run on Brave, not Google):
- Do NOT use Google-specific operators: no `site:`, `source:`, `date:`, `filetype:`, `intitle:`, `inurl:`.
- Do NOT chain multiple quoted phrases. Use at most one short quoted phrase per query, reserved for exact proper nouns or document titles. Multiple quoted phrases chained together nearly always return zero results.
- Keep queries short: 3–7 words. Natural keyword combinations outperform complex boolean syntax on Brave.
- For subject-level or abstract entities (e.g. "AI/LLM producers", "cloud providers"), skip the entity name and query by the concrete subject matter directly (e.g. "Bletchley Park AI safety commitments" rather than "AI/LLM producers safety pledges").
"""

research_planner_agent = Agent(
    "test",
    output_type=ResearchPlan,
    system_prompt=_RESEARCH_PLANNER_INSTRUCTIONS,
    retries=2,
)
