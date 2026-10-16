"""Acceptance tests for RE-AT (Rules, findings file, tie-breaker): the tie-breaker.

Written before the implementation (plan ``docs/plans/completed/pipeline-rebuild.md``
§ SP2 (Rules, findings file, tie-breaker), § Run rules "Analyst and Evaluator
disagree" and Q-B5 (tie-breaker)). Every case drives ``loop.run`` or
``loop.rerun`` with scripted agents, the ``dr`` CLI under ``CliRunner``, or the
public agent and compare functions. Nothing here patches a private name under
``pipeline/loop/``.

Covered:

- the package is wired like the other agents: ``instructions.md`` loaded with
  the verdict scale, its own ``AGENT_NAMES`` slot, ``--tiebreaker-model``
  (env ``DR_TIEBREAKER_MODEL``), recorded in ``models_used``;
- a disagreement runs the tie-breaker blind: its prompt carries no verdict,
  no confidence and neither earlier opinion (mirrors
  ``test_auditor_agent.py`` ``TestBundleNeverLeaksVerdict``);
- a tie-breaker verdict matching either side becomes ``pipeline_verdict``
  with that side's confidence; a three-way split takes the weakest by the
  Q-B5 ordering with that side's confidence;
- an agreeing pair with two evidence gaps runs no tie-breaker (the
  ``needs_review`` reason survives for the packet);
- a tie-breaker failure abandons the run with a finding at ``step: tiebreak``;
- the sidecar records all three sides, ``pipeline_verdict``, ``rule_applied``,
  and the claim file carries the pipeline verdict; an agreed run writes
  ``rule_applied: agreed`` and no tie-breaker keys;
- ``rerun(agent="evaluator")`` settles through the same rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from pydantic_ai.exceptions import UnexpectedModelBehavior

from common.models import Confidence, Verdict
from tests.loop_harness import (
    ENTITY_REF,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    capturing_model,
    claim_spec,
    failing_model,
    loop_config,
    scripted_agents,
    write_entity,
    written_claims,
)

NARRATIVE = "Sources describe the subject's electricity use without settling the share."


def _config(tmp_path, **overrides):
    overrides.setdefault("transport_backoff_s", (0.0, 0.0))
    return loop_config(tmp_path, **overrides)


async def _run(tmp_path, *, analyst: dict, auditor: dict, tiebreaker: dict | None = None, **kw):
    import loop

    with scripted_agents(analyst=analyst, auditor=auditor, tiebreaker=tiebreaker, **kw):
        return await loop.run(claim_spec(tmp_path), _config(tmp_path))


def _draft(tmp_path, *extra: str):
    from orchestrator.cli import main

    # Every agent named on the command line, so a developer's .env (DR_*_MODEL) cannot leak in.
    models = [x for a in ("researcher", "analyst", "auditor", "ingestor", "tiebreaker") for x in (f"--{a}-model", "test")]
    return CliRunner().invoke(main, [
        "--model", "test", *models, "draft", "--entity", ENTITY_REF, SENTENCE, "--skip-wayback",
        "--repo-root", str(tmp_path), *extra,
    ])


def _sidecar(tmp_path) -> dict:
    claims = written_claims(tmp_path)
    assert len(claims) == 1
    return yaml.safe_load(claims[0].with_suffix(".audit.yaml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Wiring                                                                           #
# --------------------------------------------------------------------------- #


def test_tiebreaker_is_a_named_agent_with_its_own_model() -> None:
    """Its instruction wiring is pinned in tests/test_instructions.py with the other agents."""
    from common.models import AGENT_NAMES
    from loop import VerifyConfig

    assert "tiebreaker" in AGENT_NAMES
    assert VerifyConfig(model="m", tiebreaker_model="t").model_for("tiebreaker") == "t"
    assert VerifyConfig(model="m").model_for("tiebreaker") == "m"


def test_tiebreaker_prompt_is_the_evaluators_bundle_with_no_opinion(monkeypatch) -> None:
    from auditor.models import ClaimBundle, EntityContext, SourceContext
    from common.models import Category
    from loop.tiebreaker.agent import build_tiebreaker_prompt

    bundle = ClaimBundle(
        claim_id="test/sample-claim",
        claim_text="TestCorp meets industry safety standards",
        entity=EntityContext(name="TestCorp", type="company", description="A fictional company."),
        topics=[Category.AI_SAFETY],
        narrative="TestCorp has implemented safety measures.",
        sources=[SourceContext(id="2025/t", title="Audit", publisher="Org", summary="s", key_quotes=[], body="b")],
    )
    prompt = build_tiebreaker_prompt(bundle)
    assert "verdict:" not in prompt.lower()
    assert "confidence:" not in prompt.lower()
    assert "## Claim\nTestCorp meets industry safety standards\n" in prompt
    assert prompt.index("## Claim") < prompt.index("## Analyst narrative")


def test_tiebreaker_model_option_reaches_the_config(tmp_path, monkeypatch) -> None:
    from orchestrator.cli import main

    write_entity(tmp_path)
    top_help = CliRunner().invoke(main, ["--help"]).output
    assert "--tiebreaker-model" in top_help
    seen: dict = {}

    async def _capture(spec, config, **kwargs):
        seen["config"] = config
        raise SystemExit(0)

    monkeypatch.setattr("loop.run", _capture)
    monkeypatch.setenv("DR_TIEBREAKER_MODEL", "test")
    CliRunner().invoke(main, [
        "--model", "test", "draft", "--paid-dry-run", "--entity", ENTITY_REF, SENTENCE, "--repo-root", str(tmp_path),
    ])
    assert seen["config"].tiebreaker_model == "test"
    assert seen["config"].model_for("tiebreaker") == "test"

    seen.clear()
    monkeypatch.delenv("DR_TIEBREAKER_MODEL")
    CliRunner().invoke(main, [
        "--model", "test", "--tiebreaker-model", "test", "draft", "--paid-dry-run", "--entity", ENTITY_REF, SENTENCE,
        "--repo-root", str(tmp_path),
    ])
    assert seen["config"].tiebreaker_model == "test"


# --------------------------------------------------------------------------- #
# Blind third pass                                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_disagreement_runs_the_tiebreaker_blind(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    prompts: list[str] = []
    calls: list[str] = []
    with scripted_agents(
        analyst=analyst_args(verdict="mixed", confidence="medium", narrative=NARRATIVE),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker_model=capturing_model(prompts, auditor_args(verdict="true", confidence="low"), calls=calls, name="tb"),
    ):
        result = await loop.run(claim_spec(tmp_path), _config(tmp_path))

    assert calls == ["tb"], "the tie-breaker runs once"
    assert len(prompts) == 1
    prompt = prompts[0]
    assert "verdict:" not in prompt.lower()
    assert "confidence:" not in prompt.lower()
    assert "Analyst:" not in prompt and "Evaluator:" not in prompt and "Auditor:" not in prompt
    assert "mixed" not in prompt, "the analyst's verdict is not in the prompt"
    assert f"## Claim\n{SENTENCE}\n" in prompt
    assert NARRATIVE in prompt, "the same bundle the Evaluator saw"
    assert result.consistency is not None
    assert result.consistency.tiebreaker_verdict == Verdict.TRUE


@pytest.mark.asyncio
async def test_agreeing_pair_with_two_evidence_gaps_runs_no_tiebreaker(tmp_path) -> None:
    """Replaces the RE-AR pin ``test_a_rejected_review_names_the_real_flag_reason``."""
    import loop
    from auditor.compare import needs_review_reasons

    write_entity(tmp_path)
    calls: list[str] = []
    with scripted_agents(
        analyst=analyst_args(verdict="mixed"),
        auditor=auditor_args(verdict="mixed", evidence_gaps=["g1", "g2"]),
        tiebreaker_model=failing_model(calls=calls),
    ):
        result = await loop.run(claim_spec(tmp_path), _config(tmp_path))

    assert calls == [], "no tie-breaker on an agreeing pair"
    c = result.consistency
    assert c.needs_review is True
    assert needs_review_reasons(c) == ["2+ evidence gaps"]
    assert c.pipeline_verdict == Verdict.MIXED
    assert c.rule_applied == "agreed"
    assert c.tiebreaker_verdict is None
    assert result.finding is None
    assert not any("Flagged for human review" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# The rule                                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tiebreaker_matching_the_analyst_sets_the_pipeline_verdict(tmp_path) -> None:
    write_entity(tmp_path)
    result = await _run(
        tmp_path,
        analyst=analyst_args(verdict="mixed", confidence="medium"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="mixed", confidence="low"),
    )
    c = result.consistency
    assert c.tiebreaker_verdict == Verdict.MIXED
    assert c.tiebreaker_confidence == Confidence.LOW
    assert c.tiebreaker_reasoning
    assert c.pipeline_verdict == Verdict.MIXED
    assert c.pipeline_confidence == Confidence.MEDIUM, "the matched side's confidence"
    assert c.rule_applied == "tiebreaker-matched-analyst"
    finding = result.finding
    assert finding is not None
    assert finding.outcome == "split"
    assert finding.step == "tiebreak"
    assert finding.rule == "tiebreaker"
    assert finding.error["error_type"] == "verdict_split"
    assert "mixed" in finding.error["message"] and "true" in finding.error["message"]


@pytest.mark.asyncio
async def test_tiebreaker_matching_the_evaluator_sets_the_pipeline_verdict(tmp_path) -> None:
    write_entity(tmp_path)
    result = await _run(
        tmp_path,
        analyst=analyst_args(verdict="mixed", confidence="medium"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="low"),
    )
    c = result.consistency
    assert c.pipeline_verdict == Verdict.TRUE
    assert c.pipeline_confidence == Confidence.HIGH
    assert c.rule_applied == "tiebreaker-matched-evaluator"
    assert result.finding.outcome == "split"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "analyst, evaluator, tiebreak, expected, expected_confidence",
    [
        (("true", "high"), ("false", "high"), ("unverified", "low"), "unverified", "low"),
        (("mostly-true", "high"), ("false", "medium"), ("mixed", "high"), "mixed", "high"),
        (("true", "high"), ("mostly-false", "medium"), ("not-applicable", "medium"), "not-applicable", "medium"),
        (("mixed", "low"), ("true", "high"), ("mostly-false", "medium"), "mixed", "low"),
        # A rank tie (mostly-true, mostly-false) goes to the tie-breaker's side, then the Evaluator's.
        (("true", "high"), ("mostly-true", "medium"), ("mostly-false", "low"), "mostly-false", "low"),
        (("mostly-true", "medium"), ("mostly-false", "high"), ("true", "high"), "mostly-true", "medium"),
    ],
)
async def test_three_way_split_takes_the_weakest_by_the_ordering(
    tmp_path, analyst, evaluator, tiebreak, expected, expected_confidence,
) -> None:
    write_entity(tmp_path)
    result = await _run(
        tmp_path,
        analyst=analyst_args(verdict=analyst[0], confidence=analyst[1]),
        auditor=auditor_args(verdict=evaluator[0], confidence=evaluator[1]),
        tiebreaker=auditor_args(verdict=tiebreak[0], confidence=tiebreak[1]),
    )
    c = result.consistency
    assert c.pipeline_verdict == Verdict(expected)
    assert c.pipeline_confidence == Confidence(expected_confidence)
    assert c.rule_applied == "three-way-split-weakest"
    assert result.finding.outcome == "split"


def test_verdict_strength_ordering_is_the_q_b5_default() -> None:
    from auditor.compare import VERDICT_STRENGTH

    rank = {Verdict(v): r for v, r in VERDICT_STRENGTH.items()} if isinstance(
        next(iter(VERDICT_STRENGTH)), str
    ) else dict(VERDICT_STRENGTH)
    assert rank[Verdict.NOT_APPLICABLE] < rank[Verdict.UNVERIFIED] < rank[Verdict.MIXED]
    assert rank[Verdict.MIXED] < rank[Verdict.MOSTLY_TRUE] == rank[Verdict.MOSTLY_FALSE]
    assert rank[Verdict.MOSTLY_TRUE] < rank[Verdict.TRUE] == rank[Verdict.FALSE]
    assert set(rank) == set(Verdict)


# --------------------------------------------------------------------------- #
# Tie-breaker failure                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tiebreaker_failure_abandons_with_a_finding(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    calls: list[str] = []
    with scripted_agents(
        analyst=analyst_args(verdict="mixed"),
        auditor=auditor_args(verdict="true"),
        tiebreaker_model=failing_model(UnexpectedModelBehavior("Exceeded maximum retries"), calls=calls),
    ):
        result = await loop.run(claim_spec(tmp_path), _config(tmp_path))

    assert calls == ["run", "run"], "a flaw: one retry, then abandon"
    finding = result.finding
    assert finding.outcome == "abandoned"
    assert finding.step == "tiebreak"
    assert finding.rule == "flaw-retry"
    assert finding.attempts == 2
    assert result.consistency is None or result.consistency.pipeline_verdict is None


def test_tiebreaker_failure_writes_nothing(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(
        analyst=analyst_args(verdict="mixed"),
        auditor=auditor_args(verdict="true"),
        tiebreaker_model=failing_model(UnexpectedModelBehavior("Exceeded maximum retries")),
    ):
        result = _draft(tmp_path)
    assert result.exit_code == 1
    assert written_claims(tmp_path) == []
    assert "tiebreak" in result.output
    findings = sorted((tmp_path / "research" / "findings").rglob("*.yaml"))
    assert len(findings) == 1
    assert yaml.safe_load(findings[0].read_text(encoding="utf-8"))["outcome"] == "abandoned"


# --------------------------------------------------------------------------- #
# The sidecar and the claim                                                        #
# --------------------------------------------------------------------------- #


def test_sidecar_records_all_three_sides_and_the_claim_takes_the_pipeline_verdict(tmp_path) -> None:
    from common.frontmatter import parse_frontmatter

    write_entity(tmp_path)
    with scripted_agents(
        analyst=analyst_args(verdict="mixed", confidence="medium"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="medium"),
    ):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    claim = written_claims(tmp_path)[0]
    fm, _ = parse_frontmatter(claim.read_text(encoding="utf-8"))
    assert fm["verdict"] == "true"
    assert fm["confidence"] == "high"
    audit = _sidecar(tmp_path)["audit"]
    assert audit["analyst_verdict"] == "mixed"
    assert audit["auditor_verdict"] == "true"
    assert audit["tiebreaker_verdict"] == "true"
    assert audit["tiebreaker_confidence"] == "medium"
    assert audit["tiebreaker_reasoning"]
    assert audit["pipeline_verdict"] == "true"
    assert audit["pipeline_confidence"] == "high"
    assert audit["rule_applied"] == "tiebreaker-matched-evaluator"
    assert audit["verdict_agrees"] is False
    sidecar = _sidecar(tmp_path)
    assert sidecar["models_used"]["tiebreaker"] == "test"
    assert "tiebreaker" in sidecar["pipeline_run"]["agents"]
    findings = sorted((tmp_path / "research" / "findings").rglob("*.yaml"))
    assert len(findings) == 1
    assert yaml.safe_load(findings[0].read_text(encoding="utf-8"))["outcome"] == "split"


def test_agreed_run_writes_the_pipeline_verdict_and_no_tiebreaker_keys(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(analyst=analyst_args(verdict="mixed"), auditor=auditor_args(verdict="mixed")):
        result = _draft(tmp_path)
    assert result.exit_code == 0, result.output
    sidecar = _sidecar(tmp_path)
    audit = sidecar["audit"]
    assert audit["pipeline_verdict"] == "mixed"
    assert audit["pipeline_confidence"] == "medium"
    assert audit["rule_applied"] == "agreed"
    assert "tiebreaker_verdict" not in audit
    assert "tiebreaker" not in sidecar["models_used"]
    assert "tiebreaker" not in sidecar["pipeline_run"]["agents"]
    assert not (tmp_path / "research" / "findings").exists()


def test_a_capped_level_still_caps_the_pipeline_confidence(tmp_path) -> None:
    """The level fit's confidence cap applies whichever side won."""
    from common.frontmatter import parse_frontmatter
    from tests.loop_harness import ingest_model

    write_entity(tmp_path)
    with scripted_agents(
        analyst=analyst_args(verdict="mixed", confidence="medium", level="independently-verified"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="high"),
        ingestor=ingest_model(publisher="Probe Subject"),
    ):
        result = _draft(tmp_path)
    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(written_claims(tmp_path)[0].read_text(encoding="utf-8"))
    assert fm["verdict"] == "true"
    assert fm["verification_level"] in ("self-reported", "claimed")
    assert fm["confidence"] == "low"


def _set_takeaway(claim: Path, text: str) -> None:
    from common.frontmatter import parse_frontmatter, serialize_frontmatter

    fm, body = parse_frontmatter(claim.read_text(encoding="utf-8"))
    fm["takeaway"] = text
    claim.write_text(serialize_frontmatter(fm, body), encoding="utf-8")


@pytest.mark.parametrize("analyst_verdict", ["true", "mixed"], ids=["agreed", "tie-broken"])
def test_operator_takeaway_survives_a_forced_rerun_on_the_same_verdict(tmp_path, analyst_verdict) -> None:
    """The first sidecar records the verdict written, not the analyst's losing one.

    Otherwise a tie-broken claim's next write reads a verdict change that
    never happened on the claim and replaces the operator's takeaway.
    """
    from common.frontmatter import parse_frontmatter

    write_entity(tmp_path)

    def draft(takeaway: str, *extra: str):
        with scripted_agents(
            analyst={**analyst_args(verdict=analyst_verdict), "takeaway": takeaway},
            auditor=auditor_args(verdict="true", confidence="high"),
            tiebreaker=auditor_args(verdict="true", confidence="high"),
        ):
            result = _draft(tmp_path, *extra)
        assert result.exit_code == 0, result.output

    draft("The analyst wrote this first.")
    claim = written_claims(tmp_path)[0]
    assert _sidecar(tmp_path)["analyst_record"]["verdict"] == "true"
    _set_takeaway(claim, "The operator wrote this.")

    draft("The analyst wrote this second.", "--force")
    fm, _ = parse_frontmatter(claim.read_text(encoding="utf-8"))
    assert fm["verdict"] == "true"
    assert fm["takeaway"] == "The operator wrote this."


# --------------------------------------------------------------------------- #
# rerun                                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_rerun_evaluator_settles_through_the_tiebreaker(tmp_path) -> None:
    import loop
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment
    from common.models import Category, EntityType, VerificationLevel

    write_entity(tmp_path)
    sources = [
        {"source_id": f"2026/s{i}", "slug": f"s{i}", "url": u, "title": f"S{i}", "publisher": "P",
         "summary": "s", "key_quotes": [], "body": "b", "kind": "article", "independence": "independent"}
        for i, u in enumerate(URLS)
    ]
    analysis = AnalystOutput(
        entity=EntityResolution(entity_name="Probe Subject", entity_type=EntityType.SUBJECT, entity_description="d"),
        verdict=VerdictAssessment(
            title=SENTENCE, topics=[Category.ENVIRONMENTAL_IMPACT], verdict=Verdict.MIXED,
            confidence=Confidence.MEDIUM, narrative=NARRATIVE,
            verification_level=VerificationLevel.PARTIALLY_VERIFIED, seo_title="Probe",
        ),
    )
    with scripted_agents(auditor=auditor_args(verdict="true"), tiebreaker=auditor_args(verdict="true", confidence="low")):
        result = await loop.rerun(claim_spec(tmp_path), _config(tmp_path), sources, agent="evaluator", analyst_output=analysis)

    c = result.consistency
    assert c.pipeline_verdict == Verdict.TRUE
    assert c.rule_applied == "tiebreaker-matched-evaluator"
    assert c.tiebreaker_verdict == Verdict.TRUE
    assert result.finding is not None and result.finding.outcome == "split"


def _rerun_repo(tmp_path) -> Path:
    """A repo with one subject and one draft claim about it, with a sidecar; return the claim directory."""
    from common.frontmatter import serialize_frontmatter

    subjects = tmp_path / "research" / "entities" / "subjects"
    subjects.mkdir(parents=True)
    (subjects / "example.md").write_text(
        serialize_frontmatter({"name": "Example", "type": "subject", "description": "A subject."}, "Body.\n"),
        encoding="utf-8",
    )
    claim_dir = tmp_path / "research" / "claims" / "subjects" / "example"
    claim_dir.mkdir(parents=True)
    fm = {"title": "Example claim", "statement": "Example claim", "entity": "subjects/example",
          "verdict": "mixed", "confidence": "medium", "topics": ["environmental-impact"], "sources": [],
          "status": "draft"}
    (claim_dir / "claim.md").write_text(serialize_frontmatter(fm, "Body.\n"), encoding="utf-8")
    (claim_dir / "claim.audit.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "sources_consulted": [],
        "models_used": {"researcher": "r-model", "ingestor": "i-model", "analyst": "a-model",
                        "auditor": "old-auditor"},
    }), encoding="utf-8")
    return claim_dir


def _rerun_evaluator(tmp_path, ref: str):
    from orchestrator.cli import main

    with scripted_agents(
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="high"),
    ):
        return CliRunner().invoke(main, [
            "--model", "test", "--auditor-model", "test", "--tiebreaker-model", "test",
            "draft", "--claim", ref, "--rerun", "evaluator", "--repo-root", str(tmp_path),
        ])


def _findings(tmp_path) -> list[dict]:
    return [yaml.safe_load(p.read_text(encoding="utf-8"))
            for p in sorted((tmp_path / "research" / "findings").rglob("*.yaml"))]


def test_rerun_evaluator_records_a_tie_broken_disagreement(tmp_path) -> None:
    from common.frontmatter import parse_frontmatter

    claim_dir = _rerun_repo(tmp_path)
    result = _rerun_evaluator(tmp_path, "subjects/example/claim")

    assert result.exit_code == 0, result.output
    data = yaml.safe_load((claim_dir / "claim.audit.yaml").read_text(encoding="utf-8"))
    audit = data["audit"]
    assert audit["analyst_verdict"] == "mixed"
    assert audit["auditor_verdict"] == "true"
    assert audit["tiebreaker_verdict"] == "true"
    assert audit["pipeline_verdict"] == "true"
    assert audit["rule_applied"] == "tiebreaker-matched-evaluator"
    assert data["pipeline_run"]["agents"] == ["auditor", "tiebreaker"]
    assert data["models_used"] == {
        "researcher": "r-model", "ingestor": "i-model", "analyst": "a-model",
        "auditor": "test", "tiebreaker": "test",
    }
    # The claim takes the verdict the tie-breaker settled on (a draft rerun in place).
    fm, _ = parse_frontmatter((claim_dir / "claim.md").read_text(encoding="utf-8"))
    assert fm["verdict"] == "true"
    (finding,) = _findings(tmp_path)
    assert finding["outcome"] == "split"
    assert finding["command"] == "dr draft --rerun evaluator"
    assert finding["claim_ref"] == "subjects/example/claim"


# --------------------------------------------------------------------------- #
# Thinking level on the wire                                                       #
# --------------------------------------------------------------------------- #


async def _wire_bodies(tmp_path, monkeypatch, **config) -> tuple[list[dict], list[dict]]:
    """Run a disagreement with the Evaluator and the tie-breaker on ``greenpt:gpt-oss-120b``.

    respx answers every chat request, so nothing leaves the machine; the
    PydanticAI settings only show their effect in the JSON the client sends.
    Returns the (Evaluator, tie-breaker) request bodies.
    """
    import json

    import httpx
    import respx

    import loop
    from common.models import resolve_model

    monkeypatch.setenv("GREENPT_API_KEY", "test-key")
    resolve_model.cache_clear()
    write_entity(tmp_path)
    reply = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-oss-120b",
        "choices": [{
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "final_result", "arguments": json.dumps(auditor_args(verdict="true", confidence="high"))},
            }]},
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    try:
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post("https://api.greenpt.ai/v1/chat/completions").mock(return_value=httpx.Response(200, json=reply))
            with scripted_agents(
                analyst=analyst_args(verdict="mixed", confidence="medium", narrative=NARRATIVE),
                auditor_model=resolve_model("greenpt:gpt-oss-120b"),
                tiebreaker_model=resolve_model("greenpt:gpt-oss-120b"),
            ):
                await loop.run(claim_spec(tmp_path), _config(tmp_path, **config))
    finally:
        resolve_model.cache_clear()

    bodies = [json.loads(call.request.content) for call in route.calls]
    tiebreaker = [b for b in bodies if "deciding reviewer" in b["messages"][0]["content"]]
    evaluator = [b for b in bodies if b not in tiebreaker]
    return evaluator, tiebreaker


@pytest.mark.asyncio
async def test_tiebreaker_thinking_level_reaches_the_request(tmp_path, monkeypatch) -> None:
    evaluator, tiebreaker = await _wire_bodies(tmp_path, monkeypatch)

    assert len(tiebreaker) == 1 and evaluator, "both agents reached the gateway"
    assert tiebreaker[0]["reasoning_effort"] == "high"
    assert all("reasoning_effort" not in b for b in evaluator), "the Evaluator keeps the model's default"
    # gpt-oss answers in prose unless the output tool is forced, so the effort must change nothing else.
    assert tiebreaker[0]["tool_choice"] == evaluator[0]["tool_choice"] == "required"
    assert set(tiebreaker[0]) - {"reasoning_effort"} == set(evaluator[0])


@pytest.mark.asyncio
async def test_tiebreaker_thinking_none_sends_no_reasoning_effort(tmp_path, monkeypatch) -> None:
    _, tiebreaker = await _wire_bodies(tmp_path, monkeypatch, tiebreaker_thinking=None)

    assert len(tiebreaker) == 1
    assert "reasoning_effort" not in tiebreaker[0]


@pytest.mark.parametrize(("model", "warned"), [("greenpt:some-chat-model", True), ("greenpt:gpt-oss-120b", False)])
@pytest.mark.asyncio
async def test_a_tiebreaker_model_that_drops_thinking_logs_a_warning(tmp_path, monkeypatch, caplog, model, warned) -> None:
    """PydanticAI drops ``thinking`` silently for a model whose profile declares no reasoning support."""
    import logging

    import loop
    from common.models import resolve_model

    monkeypatch.setenv("GREENPT_API_KEY", "test-key")
    resolve_model.cache_clear()
    write_entity(tmp_path)
    try:
        with caplog.at_level(logging.WARNING, logger="loop.analyse"), scripted_agents(
            analyst=analyst_args(verdict="mixed"), auditor=auditor_args(verdict="true"),
        ):
            await loop.run(claim_spec(tmp_path), _config(tmp_path, tiebreaker_model=model))
    finally:
        resolve_model.cache_clear()

    assert any("thinking" in r.getMessage() and model in r.getMessage() for r in caplog.records) is warned
