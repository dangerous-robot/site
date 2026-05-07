"""Shape-only tests for the research_planner_agent over a curated claim corpus.

These tests use TestModel with pre-built ResearchPlan outputs. They verify the
plan-shape invariants (sub-question count, query tagging, sub-question id
references, environmental-domain heuristic) the orchestrator depends on.
Real-LLM behavior tests live under -m acceptance and are out of scope here.
"""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from common.models import SubQuestion
from researcher.planner import PlannedQuery, ResearchPlan, research_planner_agent


def _plan_payload(sub_questions: list[dict], queries: list[dict], rationale: str = "ok") -> dict:
    return {
        "sub_questions": sub_questions,
        "queries": queries,
        "rationale": rationale,
    }


# Curated corpus. Each entry mirrors the kind of decomposition the planner is
# expected to produce on the live model; here we hand-write the payload and
# assert shape invariants. Domain hints (env / privacy / industry) drive a
# soft check that environmental claims include a sustainability-related axis.
_CORPUS = [
    {
        "id": "env_disclosure_compound",
        "claim": "Brave Leo discloses the energy sourcing for its hosted models.",
        "expected_min_sq": 3,
        "domain": "env",
        "payload": _plan_payload(
            sub_questions=[
                {"id": "sq1", "question": "Does Brave publish energy sourcing data for Leo?", "rationale": "Direct restatement of the claim's central assertion."},
                {"id": "sq2", "question": "Do third-party ESG databases profile Brave Software?", "rationale": "Independent corroboration channel."},
                {"id": "sq3", "question": "Which provider hosts Brave Leo's models, and does that provider disclose energy?", "rationale": "Underlying technical mechanism."},
            ],
            queries=[
                {"text": "Brave transparency report energy", "sub_question_id": "sq1"},
                {"text": "Brave Software ESG sustainability", "sub_question_id": "sq2"},
                {"text": "Brave Leo hosting provider", "sub_question_id": "sq3"},
            ],
        ),
    },
    {
        "id": "env_disclosure_single_axis",
        "claim": "Ecosia publishes an annual sustainability report.",
        "expected_min_sq": 2,
        "domain": "env",
        "payload": _plan_payload(
            sub_questions=[
                {"id": "sq1", "question": "Does Ecosia publish a sustainability report?", "rationale": "Direct restatement."},
                {"id": "sq2", "question": "Do third-party sources confirm the existence of an Ecosia sustainability report?", "rationale": "Independent corroboration."},
            ],
            queries=[
                {"text": "Ecosia sustainability report", "sub_question_id": "sq1"},
                {"text": "Ecosia financial reports independent", "sub_question_id": "sq2"},
            ],
        ),
    },
    {
        "id": "privacy_compound",
        "claim": "Anthropic does not train Claude models on user conversations by default.",
        "expected_min_sq": 3,
        "domain": "privacy",
        "payload": _plan_payload(
            sub_questions=[
                {"id": "sq1", "question": "Does Anthropic's published policy state that user conversations are not used for training by default?", "rationale": "First-party policy statement."},
                {"id": "sq2", "question": "Do model cards or technical documentation describe the training pipeline's data sources?", "rationale": "Technical mechanism axis."},
                {"id": "sq3", "question": "Have independent investigations or regulators corroborated the policy?", "rationale": "Independent corroboration."},
            ],
            queries=[
                {"text": "Anthropic privacy policy training", "sub_question_id": "sq1"},
                {"text": "Claude model card training data", "sub_question_id": "sq2"},
                {"text": "Anthropic training data investigation", "sub_question_id": "sq3"},
            ],
        ),
    },
    {
        "id": "industry_structure_single_axis",
        "claim": "Microsoft has a publicly-traded corporate structure.",
        "expected_min_sq": 2,
        "domain": "industry",
        "payload": _plan_payload(
            sub_questions=[
                {"id": "sq1", "question": "Is Microsoft listed on a public stock exchange?", "rationale": "Direct restatement."},
                {"id": "sq2", "question": "What does Microsoft's regulatory filings say about its corporate structure?", "rationale": "Authoritative regulatory record."},
            ],
            queries=[
                {"text": "Microsoft NASDAQ listing", "sub_question_id": "sq1"},
                {"text": "Microsoft 10-K filing structure", "sub_question_id": "sq2"},
            ],
        ),
    },
    {
        "id": "regulation_compound",
        "claim": "OpenAI complies with the EU AI Act for general-purpose AI models.",
        "expected_min_sq": 3,
        "domain": "regulation",
        "payload": _plan_payload(
            sub_questions=[
                {"id": "sq1", "question": "Has OpenAI publicly committed to EU AI Act compliance?", "rationale": "First-party commitment."},
                {"id": "sq2", "question": "Has the EU AI Office or another regulator assessed OpenAI's compliance?", "rationale": "Regulator assessment."},
                {"id": "sq3", "question": "What technical safeguards has OpenAI documented for general-purpose AI obligations?", "rationale": "Technical mechanism."},
            ],
            queries=[
                {"text": "OpenAI EU AI Act compliance", "sub_question_id": "sq1"},
                {"text": "EU AI Office OpenAI assessment", "sub_question_id": "sq2"},
                {"text": "OpenAI GPAI safeguards", "sub_question_id": "sq3"},
            ],
        ),
    },
    {
        "id": "consumer_guide_single_axis",
        "claim": "ChatGPT lets users disable chat history through a settings toggle.",
        "expected_min_sq": 2,
        "domain": "consumer",
        "payload": _plan_payload(
            sub_questions=[
                {"id": "sq1", "question": "Does ChatGPT expose a chat history toggle in user settings?", "rationale": "Direct restatement."},
                {"id": "sq2", "question": "Has the toggle behavior been independently documented?", "rationale": "Independent corroboration."},
            ],
            queries=[
                {"text": "ChatGPT chat history toggle settings", "sub_question_id": "sq1"},
                {"text": "ChatGPT history disable review", "sub_question_id": "sq2"},
            ],
        ),
    },
]


@pytest.mark.parametrize("entry", _CORPUS, ids=[e["id"] for e in _CORPUS])
@pytest.mark.asyncio
async def test_planner_output_shape(entry) -> None:
    payload = entry["payload"]
    with research_planner_agent.override(model=TestModel(custom_output_args=payload)):
        result = await research_planner_agent.run(f"Claim: {entry['claim']}")
    plan = result.output

    assert isinstance(plan, ResearchPlan)
    assert 2 <= len(plan.sub_questions) <= 5
    assert len(plan.sub_questions) >= entry["expected_min_sq"]

    sq_ids = {sq.id for sq in plan.sub_questions}
    for sq in plan.sub_questions:
        assert sq.id and sq.question and sq.rationale
        assert isinstance(sq, SubQuestion)

    assert plan.queries, "planner returned no queries"
    for q in plan.queries:
        assert isinstance(q, PlannedQuery)
        assert q.sub_question_id in sq_ids, (
            f"query {q.text!r} references unknown sub-question {q.sub_question_id!r}"
        )

    if entry["domain"] == "env":
        env_keywords = ("transparency", "esg", "sustainab", "energy", "emission", "carbon")
        joined = " ".join(sq.question.lower() for sq in plan.sub_questions)
        assert any(kw in joined for kw in env_keywords), (
            f"env-domain plan lacks transparency/ESG/sustainability axis: {joined!r}"
        )
