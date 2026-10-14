"""Prompt and instruction anchors for the Analyst, the Evaluator and the ingestor.

These cases pin prompt wording through the public agent functions and the
loop's public ``audit_claim``; other edits to the instruction files must keep
the wording (rewrapping is fine). Collected here from ``test_auditor_agent.py``,
``test_analyst.py`` and ``test_ingest_validation.py`` so they stay together
whichever pipeline path is removed.
"""

from __future__ import annotations

import pytest

from analyst.agent import VerdictAssessment, build_analyst_prompt
from auditor.agent import auditor_agent, build_auditor_prompt
from auditor.models import ClaimBundle, EntityContext, IndependentAssessment
from common.models import Category, SubQuestion


_CLAIM = "ChatGPTree is hosted on renewable energy"
_NARRATIVE = (
    "No source names the data centers behind the product or their energy mix. "
    "The evidence for renewable hosting is missing."
)


def _claim_bundle(claim_text: str = _CLAIM) -> ClaimBundle:
    return ClaimBundle(
        claim_id="chatgptree/renewable-energy-hosting",
        claim_text=claim_text,
        entity=EntityContext(name="ChatGPTree", type="product", description="A chatbot."),
        topics=[Category.ENVIRONMENTAL_IMPACT],
        narrative=_NARRATIVE,
        sources=[],
    )


class TestEvaluatorGradesTheClaim:
    def test_prompt_puts_claim_text_before_narrative(self) -> None:
        prompt = build_auditor_prompt(_claim_bundle())
        assert f"## Claim\n{_CLAIM}" in prompt
        assert prompt.index(_CLAIM) < prompt.index(_NARRATIVE)

    def test_instructions_grade_the_claim(self) -> None:
        from auditor.agent import _INSTRUCTIONS

        assert "ONLY on the narrative" not in _INSTRUCTIONS
        assert "an accurate narrative is not evidence for the claim" in _INSTRUCTIONS.lower()
        assert "narrative" not in IndependentAssessment.model_fields["verdict"].description


def _analyst_output(title: str, verdict: str = "unverified", confidence: str = "low"):
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment

    return AnalystOutput(
        entity=EntityResolution(
            entity_name="ChatGPTree", entity_type="product", entity_description="A chatbot."
        ),
        verdict=VerdictAssessment(
            title=title,
            verdict=verdict,
            confidence=confidence,
            narrative=_NARRATIVE,
            topics=["environmental-impact"],
            verification_level="claimed",
            cap_rationale="Only the entity's own pages address the claim.",
            seo_title="ChatGPTree renewable hosting claim",
        ),
    )


def _capturing_auditor(captured: list[str], verdict: str = "unverified", confidence: str = "low"):
    """Swap in an Evaluator model that records the user prompt and returns a scripted assessment."""
    from contextlib import contextmanager, nullcontext
    from unittest.mock import patch

    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    def _fn(messages, info):
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, UserPromptPart):
                    captured.append(str(part.content))
        args = {"verdict": verdict, "confidence": confidence, "reasoning": "Scripted.",
                "evidence_gaps": []}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    @contextmanager
    def _ctx():
        with auditor_agent.override(model=FunctionModel(_fn)):
            # Keep this model: callers enter their own override with the configured one.
            with patch.object(auditor_agent, "override", side_effect=lambda **kw: nullcontext()):
                yield

    return _ctx()


class TestAuditClaimSendsTheClaim:
    @pytest.mark.asyncio
    async def test_audit_claim_sends_claim_text(self) -> None:
        """The prompt assertion is the point; verdict_agrees and needs_review are wiring
        checks only, since the assessment is scripted."""
        from loop import VerifyConfig, audit_claim

        captured: list[str] = []
        analyst_out = _analyst_output(title="Renewable hosting for the chatbot")
        with _capturing_auditor(captured):
            result = await audit_claim(
                "ChatGPTree", _CLAIM, analyst_out, [], VerifyConfig(model="test")
            )

        assert any(_CLAIM in p for p in captured)
        assert result is not None
        assert result.verdict_agrees is True
        assert result.needs_review is False

    @pytest.mark.asyncio
    async def test_audit_claim_grades_the_statement_it_is_given(self) -> None:
        """The caller picks the statement (_graded_statement); _audit_claim never swaps it,
        even for text containing the vocabulary hint prefix."""
        from loop import VerifyConfig, audit_claim

        captured: list[str] = []
        claim = "Acme is one of (if not the) largest AI labs"
        title = "Acme ranks among the largest labs"
        analyst_out = _analyst_output(title=title)
        with _capturing_auditor(captured):
            await audit_claim("Acme", claim, analyst_out, [], VerifyConfig(model="test"))

        prompt = "\n".join(captured)
        assert claim in prompt
        assert title not in prompt


_NOTES = "Verdict encodes degree: mixed = offsets only"


class TestEvaluatorGetsCriterionNotes:
    def test_notes_follow_the_claim_and_precede_the_narrative(self) -> None:
        bundle = _claim_bundle().model_copy(update={"criterion_notes": _NOTES})
        prompt = build_auditor_prompt(bundle)
        assert f"## Criterion notes\n{_NOTES}" in prompt
        assert (
            prompt.index("## Claim")
            < prompt.index("## Criterion notes")
            < prompt.index("## Analyst narrative")
        )

    @pytest.mark.parametrize("notes", [None, "", "   "])
    def test_empty_notes_add_no_section(self, notes) -> None:
        bundle = _claim_bundle().model_copy(update={"criterion_notes": notes})
        assert "## Criterion notes" not in build_auditor_prompt(bundle)

    def test_instructions_say_a_note_is_not_a_scale_mismatch(self) -> None:
        from auditor.agent import _INSTRUCTIONS

        text = " ".join(_INSTRUCTIONS.split())
        assert "CRITERION NOTES: a `## Criterion notes` section" in text
        assert (
            "A verdict that follows a note's mapping is not a scale mismatch: grade by "
            "the note's mapping, not by the verdict scale alone." in text
        )
        assert "do not move away" not in text
        assert "Where a note names nothing about a point, the verdict scale applies" in text
        assert (
            "A note may map a pool that is silent on a point to a verdict only when "
            "the note names that case." in text
        )
        assert (
            "A note that points to a definition not in the prompt (for example, "
            "\"See controlled vocabulary\") adds nothing, and a note that carries no "
            "guidance (commentary or provenance text) is ignored." in text
        )

    @pytest.mark.asyncio
    async def test_audit_claim_sends_criterion_notes(self) -> None:
        from loop import VerifyConfig, audit_claim

        captured: list[str] = []
        with _capturing_auditor(captured):
            await audit_claim(
                "ChatGPTree", _CLAIM, _analyst_output(title=_CLAIM), [],
                VerifyConfig(model="test"), criterion_notes=_NOTES,
            )
        assert f"## Criterion notes\n{_NOTES}" in "\n".join(captured)

    @pytest.mark.asyncio
    async def test_audit_claim_without_notes_sends_none(self) -> None:
        from loop import VerifyConfig, audit_claim

        captured: list[str] = []
        with _capturing_auditor(captured):
            await audit_claim(
                "ChatGPTree", _CLAIM, _analyst_output(title=_CLAIM), [],
                VerifyConfig(model="test"),
            )
        assert captured
        assert "## Criterion notes" not in "\n".join(captured)


def _words(text: str) -> str:
    return " ".join(text.split())


class TestAnalystInstructionAnchors:
    """Other edits to instructions.md must keep this wording; rewrapping is fine."""

    def test_criterion_notes_section(self) -> None:
        from analyst.agent import _INSTRUCTIONS

        text = _words(_INSTRUCTIONS)
        assert "CRITERION NOTES: a `## Criterion notes` section" in text
        assert _words(CRITERION_NOTES_PRECEDENCE_RULE) in text
        assert "PRECEDENCE (pending" not in text
        assert "So a note may map a pool" not in text

    def test_absence_rule_names_index_sources(self) -> None:
        from analyst.agent import _INSTRUCTIONS

        assert _words(ABSENCE_INDEX_SENTENCE) in _words(_INSTRUCTIONS)


CRITERION_NOTES_PRECEDENCE_RULE = (
    "PRECEDENCE: a note's verdict mapping wins for its criterion, over the verdict "
    "scale, over the ABSENCE OF EVIDENCE default above, and over the choice of "
    "`unverified` in SUB-QUESTION COVERAGE step 3. Step 3's confidence cap still "
    "applies: while a sub-question is uncovered, the verdict cannot be `true` or "
    "`false` at `high` confidence. The verdict scale governs everything the note "
    "does not name. A note may map a pool that is silent on a point to a verdict "
    "only when the note names that case. A condition in a note such as \"offsets "
    "only\" is judged on the pool as a whole, not source by source."
)

ABSENCE_INDEX_SENTENCE = (
    "A source with `Kind: index` supports no statement that a specific entity is "
    "absent from it unless its text in the prompt names comparable entities and "
    "the entity is visibly missing from that list."
)


class TestUncoveredSubQuestionMarker:
    SQS = [
        SubQuestion(id="sq1", question="Per-prompt energy?", rationale="r1"),
        SubQuestion(id="sq2", question="Web-search energy?", rationale="r2"),
    ]
    MARKER = "no source addresses this sub-question"

    @staticmethod
    def _source(addresses):
        src = {"title": "T", "source_id": "2026/t", "publisher": "P", "summary": "S"}
        if addresses is not None:
            src["addresses"] = addresses
        return src

    def _line(self, prompt: str, sq_id: str) -> str:
        return next(line for line in prompt.splitlines() if line.startswith(f"- {sq_id}:"))

    def test_marks_only_the_uncovered_sub_question(self) -> None:
        prompt = build_analyst_prompt(
            "X", "claim", [self._source(["sq1"])], sub_questions=self.SQS,
        )
        assert self.MARKER in self._line(prompt, "sq2")
        assert "never write the sub-question id" in self._line(prompt, "sq2")
        assert self.MARKER not in self._line(prompt, "sq1")

    def test_no_marker_when_sources_carry_no_addresses(self) -> None:
        # Sources loaded from disk have no `addresses`; coverage is unknown.
        prompt = build_analyst_prompt(
            "X", "claim", [self._source(None)], sub_questions=self.SQS,
        )
        assert self.MARKER not in prompt


class TestCoverageAndCitedSourcesInstructions:
    def test_uncovered_sub_question_described_in_plain_words(self) -> None:
        from analyst.agent import _INSTRUCTIONS

        text = _words(_INSTRUCTIONS)
        assert "MUST name the uncovered sub-question" not in text
        assert "never write a sub-question id such as sq2 in the narrative" in text

    def test_cited_sources_rule_present(self) -> None:
        from analyst.agent import _INSTRUCTIONS

        assert "`cited_sources`" in _INSTRUCTIONS

    def test_verdict_has_cited_sources_default_empty(self) -> None:
        assert "cited_sources" in VerdictAssessment.model_fields
        assert VerdictAssessment.model_fields["cited_sources"].default_factory() == []


def test_instructions_ask_for_bare_quotes() -> None:
    from ingestor.agent import _SYSTEM_PROMPT

    text = " ".join(_SYSTEM_PROMPT.split())
    assert (
        "Store each quote as the bare page text: no surrounding quotation marks "
        "and no attribution after it" in text
    )
