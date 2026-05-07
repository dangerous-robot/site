"""URL Scorer: scores search candidates by relevance to a claim (tool-free, Haiku)."""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from common.models import SubQuestion


class SearchCandidate(BaseModel):
    url: str
    title: str
    snippet: str
    from_query: str
    publisher_quality: str = "secondary"


class ScoredCandidate(BaseModel):
    url: str
    addresses: list[str] = Field(
        description=(
            "Sub-question ids (each matches a SubQuestion.id within the same "
            "ResearchPlan) this candidate is judged to address. Non-empty by "
            "construction; only kept candidates carry `addresses`."
        ),
    )


class ScoredURLs(BaseModel):
    kept: list[ScoredCandidate]
    dropped: list[str]
    rationale: str


_SCORER_INSTRUCTIONS = """\
You are a source relevance scorer. Given a claim, entity name, a list of sub-questions decomposing the claim, and a list of search result candidates (title + snippet only), score each candidate per sub-question for relevance.

Scoring scale (applied per sub-question):
- 5: Directly addresses this sub-question with likely primary-source or independent evidence
- 4: Clearly relevant to this sub-question, likely to contain useful facts or data
- 3: Possibly relevant; worth fetching to check
- 2: Tangentially related; unlikely to contain sub-question-specific evidence
- 1: Not relevant; about a different topic, entity, or time period

Rules:
- Score each candidate against EACH sub-question separately on the title and snippet only — do not assume body content.
- Keep a candidate (in the `kept` list) when it scores >= 4 on AT LEAST ONE sub-question.
- For each kept candidate, set `addresses` to the list of sub-question ids on which it scored >= 4. `addresses` must be non-empty.
- Drop a candidate (in the `dropped` list) only when it scores < 4 on EVERY sub-question.
- Every input URL must appear in either `kept` (as a ScoredCandidate) or `dropped` (as a URL string). No omissions.
- Return URLs as-is (exact strings from input).
- Include a brief `rationale` summarizing the scoring decisions across sub-questions.
- When parent company is provided, sources about the parent company are relevant to claims about the subsidiary.
- Each candidate has a `publisher_quality` label: `primary` (company or regulatory), `secondary` (academic, research, news), `tertiary` (advocacy, community), or `forum` (Reddit, Quora, HN, etc.).
- Use publisher quality as a per-sub-question tiebreaker: prefer primary > secondary > tertiary. Score forum candidates <= 3 unless no higher-quality alternatives exist in this candidate set.
- ENTITY DISAMBIGUATION: when an `Official website` is provided, the entity is the organization at that domain. Score candidates whose URL belongs to a *different* organization that merely shares a similar name as 1 (level: "different entity"), even if their snippet superficially matches a sub-question. The canonical website's own pages and well-known third-party coverage of the *same* organization (its press, regulator filings, profile databases) remain in scope.
- When `Avoid results about` is provided, candidates clearly about those topics or organizations score 1.
"""

url_scorer_agent = Agent(
    "test",
    output_type=ScoredURLs,
    system_prompt=_SCORER_INSTRUCTIONS,
    retries=2,
)


def build_scorer_prompt(
    entity: str | None,
    claim: str,
    candidates: list[SearchCandidate],
    sub_questions: list[SubQuestion],
    parent_company: str | None = None,
    website: str | None = None,
    avoid: list[str] | None = None,
) -> str:
    entity_block = f"Entity: {entity or '(unknown)'}\n"
    if parent_company:
        entity_block += f"Parent company: {parent_company}\n"
    if website:
        entity_block += f"Official website: {website}\n"
    if avoid:
        entity_block += f"Avoid results about: {', '.join(avoid)}\n"
    sub_question_block = "Sub-questions:\n" + "\n".join(
        f"- {sq.id}: {sq.question} (rationale: {sq.rationale})"
        for sq in sub_questions
    )
    candidate_text = "\n".join(
        f"URL: {c.url}\nTitle: {c.title}\nSnippet: {c.snippet}\nPublisher quality: {c.publisher_quality}\n"
        for c in candidates
    )
    return (
        entity_block
        + f"Claim: {claim}\n\n"
        + sub_question_block
        + f"\n\nCandidates:\n{candidate_text}"
    )
