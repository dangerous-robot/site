"""Acceptance tests for RE-AU (Restate inside the loop).

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ SP3 (Restate inside the loop), "Tests that prove it", § Run rules "Content
judgment (restatement)" and "Restater fails", and the absorbed design
``docs/plans/completed/claim-restate_superseded.md`` D3, D4, D7, D9, D10,
D14, D17). Every case
drives behaviour through a public entry: ``loop.run`` or ``loop.rerun`` with
the agents on scripted models (``tests/loop_harness.py``), the ``dr`` CLI
under ``CliRunner``, or a public writer or review function. Nothing here
patches a private name under ``pipeline/loop/``.

Covered:

- wiring: the restater is a named agent on the Evaluator's model slot
  (``--restater-model``, env ``DR_RESTATER_MODEL``, falling back to the
  auditor's slot, then ``--model``); its ``instructions.md`` carries the
  polarity guard verbatim and no thesis; the ``why_unverified`` enum has the
  five D10 values;
- the trigger set: a draft whose pipeline verdict is ``unverified``, ``mixed``
  or ``not-applicable``, or that went to the tie-breaker, gets a block; a
  ``true`` agreed draft gets none and the restater is never called; two
  evidence gaps alone never trigger it; ``rerun`` never restates;
- the polarity guard: the prompt carries the original statement and its
  pipeline verdict, the cited marker and the independence labels, and neither
  the Evaluator's nor the tie-breaker's reasoning nor any expected verdict;
  candidates rank by decisiveness in either direction, the model's order is
  discarded, and the code-side checks apply (unknown source ids dropped,
  quotes verified, decisiveness caps, the confidence cap);
- the same-entity rule: a candidate that names neither the entity (name,
  legal name or alias) nor an entity file the original statement names is
  dropped and listed with its reason; a proposal with every candidate
  dropped is invalid output (asked again, then a ``partial`` finding);
- the pool: the run's consulted sources plus the ranked ``research/sources/``
  pool, consulted first, capped at ``restate_pool_size``;
- one ``restatement`` block per sidecar: written by the full run, carried
  forward unchanged by ``dr step-audit --write``, replaced by a later full
  run (dropped when that run did not restate), and removed on approve or
  archive like ``refresh``; ``restates`` survives approve;
- ``dr draft --restates <ref> --pick <n>``: reads candidate ``<n>`` from the
  sidecar (the sentence is never retyped), runs it as a new claim at its own
  ad hoc path with ``restates:`` in the new sidecar, records
  ``restatement.picked`` on the original only after the new claim is written
  (never on a dry run or an abandoned run), and refuses a missing block, an
  out-of-range ``<n>``, a SENTENCE, ``--pick`` without ``--restates`` and a
  second mode flag;
- a restater failure after a valid pipeline verdict: the claim is written
  without a block, the finding has ``step: restate`` and ``outcome:
  partial`` (a tie-broken run keeps its split in ``retries``), the draft
  report says the restatement is unavailable, and the review queue's JSON
  carries ``restatement_unavailable: <run-id>``;
- carried from RE-BA (Source pool rules): ``--max-initial-queries`` below 1 is
  a usage error (BA-2); ``analyst_record``, ``restatement`` and ``restates``
  are declared in ``src/content.config.ts`` (BA-3); the shared-word coverage
  clause is in both architecture docs (BA-1);
- the docs: the absorbed plan moved with its banner, the runbook section,
  and the shared grep for ``claim-restate`` over the operator set.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest
import yaml
from click.testing import CliRunner

from common.frontmatter import parse_frontmatter
from common.models import Verdict
from common.utils import slugify
from tests.loop_harness import (
    ENTITY_NAME,
    ENTITY_REF,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    candidate,
    capturing_model,
    claim_dir,
    claim_spec,
    expected_restatement_block,
    failing_model,
    flaky_model,
    loop_config,
    restater_args,
    scripted_agents,
    write_entity,
    written_claims,
    written_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
AGENT_FLAGS = ("researcher", "analyst", "auditor", "ingestor", "tiebreaker", "restater")

# The polarity guard, verbatim from the absorbed plan's instructions outline
# (docs/plans/completed/claim-restate_superseded.md, "instructions.md outline" item 3).
POLARITY_GUARD = "A candidate the sources refute is as valuable as one they confirm."
WHY_UNVERIFIED_VALUES = {"quantifier-unsupported", "term-mismatch", "upstream-provider", "entity-silent", "other"}

# Candidates with the punctuation card C8 carries, so the sentence is never retyped at a shell.
PICK_TEXTS = [
    f"{ENTITY_NAME}'s \"100% renewable\" figure rests on certificates, not hourly supply.",
    f"{ENTITY_NAME} buys renewable certificates to match its data centers' annual use.",
    f"{ENTITY_NAME} reports its data centers' electricity use every year.",
]


# --------------------------------------------------------------------------- #
# Helpers                                                                          #
# --------------------------------------------------------------------------- #


def _config(tmp_path, **overrides):
    overrides.setdefault("transport_backoff_s", (0.0, 0.0))
    return loop_config(tmp_path, **overrides)


async def _run(tmp_path, *, analyst=None, auditor=None, tiebreaker=None, config=None, **kw):
    import loop

    with scripted_agents(analyst=analyst, auditor=auditor, tiebreaker=tiebreaker, **kw):
        return await loop.run(claim_spec(tmp_path), config or _config(tmp_path))


def _models() -> list[str]:
    # Every agent named on the command line, so a developer's .env (DR_*_MODEL) cannot leak in.
    return ["--model", "test", *[x for a in AGENT_FLAGS for x in (f"--{a}-model", "test")]]


def _dr(tmp_path, *args: str):
    from orchestrator.cli import main

    return CliRunner().invoke(main, [*_models(), *args, "--repo-root", str(tmp_path)])


def _draft(tmp_path, *extra: str, dry_run: bool = False, sentence: str = SENTENCE, mode=("--entity", ENTITY_REF)):
    args = ["draft", *mode, sentence, "--skip-wayback"]
    if dry_run:
        args.insert(1, "--dry-run")
    return _dr(tmp_path, *args, *extra)


def _sidecar_of(claim_path: Path) -> dict:
    return yaml.safe_load(claim_path.with_suffix(".audit.yaml").read_text(encoding="utf-8"))


def _sidecar(tmp_path, ref: str = ENTITY_REF) -> dict:
    claims = written_claims(tmp_path, ref)
    assert len(claims) == 1, claims
    return _sidecar_of(claims[0])


def _findings(tmp_path) -> list[dict]:
    d = tmp_path / "research" / "findings"
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(d.rglob("*.yaml"))] if d.exists() else []


def _tripwire(monkeypatch) -> list[str]:
    """Make the public loop entry fail if a command reaches it."""
    import loop

    called: list[str] = []

    async def _run_(*args, **kwargs):
        called.append("run")
        raise AssertionError("loop.run must not be called here")

    monkeypatch.setattr(loop, "run", _run_)
    return called


def _write_source(
    repo_root: Path,
    source_id: str,
    *,
    url: str,
    title: str,
    body: str,
    publisher: str = "Example Publisher",
    summary: str = "A stored page.",
    key_quotes: list[str] | None = None,
    independence: str = "independent",
    kind: str = "article",
) -> Path:
    path = repo_root / "research" / "sources" / f"{source_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "url": url, "title": title, "publisher": publisher, "accessed_date": "2026-01-01",
        "kind": kind, "independence": independence, "summary": summary,
    }
    if key_quotes:
        fm["key_quotes"] = list(key_quotes)
    path.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\n{body}\n", encoding="utf-8")
    return path


def _block(candidates: list[str] | None = None, *, picked=None) -> dict:
    """A hand-written ``restatement`` block as a full run writes it."""
    texts = candidates if candidates is not None else PICK_TEXTS
    return {
        "schema_version": 1,
        "model": "test",
        "trigger": "weak-verdict",
        "original": {"statement": SENTENCE, "verdict": "unverified", "confidence": "medium"},
        "pool": {"consulted": 4, "on_disk": 0, "sent": 4},
        "why_unverified": "term-mismatch",
        "why_unverified_note": "The sources say matched, the claim says runs on.",
        "candidates": [
            {
                "rank": i + 1, "text": t, "frame": "narrowed", "expected_verdict": "true",
                "expected_confidence": "medium", "verification_level_estimate": "independently-verified",
                "decisiveness": 3 - i if i < 3 else 0, "needs_new_research": False,
                "supporting": [], "contradicting": [], "rationale": "Report 1 says so.",
            }
            for i, t in enumerate(texts)
        ],
        "dropped": [],
        "picked": picked,
    }


def _write_claim(
    repo_root: Path,
    *,
    ref: str = ENTITY_REF,
    stem: str,
    statement: str = SENTENCE,
    status: str = "draft",
    verdict: str = "unverified",
    criteria_slug: str | None = None,
    restatement: dict | None = None,
    restates: str | None = None,
    reviewer: str | None = None,
) -> tuple[Path, Path]:
    """A claim file plus a valid sidecar at ``<entity-dir>/<stem>.md``; return both paths."""
    fm: dict = {
        "title": statement, "statement": statement, "entity": ref, "topics": ["environmental-impact"],
        "verdict": verdict, "confidence": "medium", "verification_level": "partially-verified",
    }
    if criteria_slug:
        fm["criteria_slug"] = criteria_slug
    fm.update({"status": status, "as_of": "2026-10-01", "sources": []})
    claim_path = claim_dir(repo_root, ref) / f"{stem}.md"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text(
        f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nThe stored narrative.\n", encoding="utf-8",
    )
    sidecar: dict = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst", "auditor"],
                         "run_id": "0" * 32},
        "models_used": {"analyst": "m", "auditor": "m"},
        "sources_consulted": [],
        "audit": {
            "analyst_verdict": verdict, "auditor_verdict": verdict, "analyst_confidence": "medium",
            "auditor_confidence": "medium", "verdict_agrees": True, "confidence_agrees": True,
            "needs_review": False, "pipeline_verdict": verdict, "pipeline_confidence": "medium",
            "rule_applied": "agreed",
        },
        "human_review": {
            "reviewed_at": "2026-10-02" if reviewer else None, "reviewer": reviewer, "notes": None, "pr_url": None,
        },
    }
    if restatement is not None:
        sidecar["restatement"] = restatement
    if restates is not None:
        sidecar["restates"] = restates
    sidecar_path = claim_path.with_suffix(".audit.yaml")
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return claim_path, sidecar_path


def _claim_ref(path: Path, repo_root: Path) -> str:
    return str(path.relative_to(repo_root / "research" / "claims").with_suffix(""))


def _evidence_keyed(c: dict) -> dict:
    """``c`` as ``gpt-oss-120b`` answered in the RE-AU (Restate inside the loop) probe: quotes under ``evidence``."""
    out = {k: v for k, v in c.items() if k not in ("supporting", "contradicting")}
    out["evidence"] = [{"source": "2026/grid", "quote": "gas supplied most of its power in 2024"}]
    return out


def _answers_in_turn(answers: list[dict], *, calls: list[str], retry_messages: list[str]):
    """A restater model that gives ``answers`` one per request (the last one repeats)."""
    from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    async def _fn(messages, info):
        retry_messages.extend(
            str(p.model_response()) for m in messages for p in getattr(m, "parts", [])
            if isinstance(p, RetryPromptPart)
        )
        calls.append("restater")
        args = answers[min(len(calls), len(answers)) - 1]
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(_fn)


def _capturing_restater(args: dict | None = None):
    prompts: list[str] = []
    calls: list[str] = []
    model = capturing_model(prompts, args or restater_args(), calls=calls, name="restater")
    return model, prompts, calls


# --------------------------------------------------------------------------- #
# Wiring                                                                           #
# --------------------------------------------------------------------------- #


def test_restater_is_a_named_agent_on_the_evaluators_model_slot() -> None:
    """D7: the restater runs on the Evaluator's slot unless its own override is set."""
    from common.models import AGENT_NAMES
    from loop import VerifyConfig

    assert "restater" in AGENT_NAMES
    assert VerifyConfig(model="base").model_for("restater") == "base"
    assert VerifyConfig(model="base", auditor_model="eval").model_for("restater") == "eval"
    assert VerifyConfig(model="base", auditor_model="eval", restater_model="own").model_for("restater") == "own"


def test_restater_model_option_reaches_the_config(tmp_path, monkeypatch) -> None:
    from orchestrator.cli import main

    write_entity(tmp_path)
    assert "--restater-model" in CliRunner().invoke(main, ["--help"]).output
    seen: dict = {}

    async def _capture(spec, config, **kwargs):
        seen["config"] = config
        raise SystemExit(0)

    monkeypatch.setattr("loop.run", _capture)
    monkeypatch.setenv("DR_RESTATER_MODEL", "test")
    CliRunner().invoke(main, [
        "--model", "test", "draft", "--dry-run", "--entity", ENTITY_REF, SENTENCE, "--repo-root", str(tmp_path),
    ])
    assert seen["config"].restater_model == "test"

    seen.clear()
    monkeypatch.delenv("DR_RESTATER_MODEL")
    CliRunner().invoke(main, [
        "--model", "test", "--restater-model", "test", "draft", "--dry-run", "--entity", ENTITY_REF, SENTENCE,
        "--repo-root", str(tmp_path),
    ])
    assert seen["config"].restater_model == "test"


def test_restater_instructions_carry_the_polarity_guard_and_no_thesis() -> None:
    """D4: ranked by how decisively the evidence settles each candidate, never given a thesis."""
    text = (PIPELINE_DIR / "loop" / "restater" / "instructions.md").read_text(encoding="utf-8")
    assert POLARITY_GUARD in text
    assert "negative impact" not in text.lower()
    assert "verdict-scale.md" in text
    for value in WHY_UNVERIFIED_VALUES:
        assert f"`{value}`" in text, value


def test_restater_output_rejects_a_key_of_its_own_and_requires_both_evidence_lists() -> None:
    """D4: a quote under a key the model invented (``evidence``) is an error, never an empty ``supporting``."""
    from pydantic import ValidationError

    from loop.restater.models import RestatementCandidate

    good = candidate(f"{ENTITY_NAME} used 183 TWh of electricity in 2024.", decisiveness=4)
    keyed = _evidence_keyed(good)
    with pytest.raises(ValidationError, match="evidence"):
        RestatementCandidate.model_validate(keyed)
    with pytest.raises(ValidationError, match="evidence"):
        RestatementCandidate.model_validate({**good, "evidence": keyed["evidence"]})
    for key in ("supporting", "contradicting", "needs_new_research"):
        with pytest.raises(ValidationError, match=key):
            RestatementCandidate.model_validate({k: v for k, v in good.items() if k != key})
    assert RestatementCandidate.model_validate(good).supporting == []


def test_restater_instructions_name_every_output_field_and_value() -> None:
    """The model is told the exact keys and enum values it must answer with."""
    from common.models import Confidence, VerificationLevel
    from loop.restater.models import EvidenceRef, Frame, RestatementCandidate, RestatementProposal

    text = (PIPELINE_DIR / "loop" / "restater" / "instructions.md").read_text(encoding="utf-8")
    for model in (RestatementProposal, RestatementCandidate, EvidenceRef):
        for name in model.model_fields:
            assert f"`{name}`" in text, f"{model.__name__}.{name}"
    for enum in (Frame, Verdict, Confidence, VerificationLevel):
        for value in enum:
            assert f"`{value.value}`" in text, f"{enum.__name__}.{value.value}"


def test_why_unverified_enum_has_the_five_d10_values() -> None:
    from loop.restater.models import RestatementProposal, WhyUnverified

    assert {v.value for v in WhyUnverified} == WHY_UNVERIFIED_VALUES
    assert RestatementProposal.model_fields["candidates"].metadata, "candidates carry a length bound"


# --------------------------------------------------------------------------- #
# The trigger set                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("analyst", "auditor", "tiebreaker", "trigger"),
    [
        (analyst_args(verdict="true"), auditor_args(verdict="true"), None, None),
        (analyst_args(verdict="true"), auditor_args(verdict="true", evidence_gaps=["a", "b"]), None, None),
        (analyst_args(verdict="mostly-false"), auditor_args(verdict="mostly-false"), None, None),
        (analyst_args(verdict="unverified"), auditor_args(verdict="unverified"), None, "weak-verdict"),
        (analyst_args(verdict="mixed"), auditor_args(verdict="mixed"), None, "weak-verdict"),
        (analyst_args(verdict="not-applicable"), auditor_args(verdict="not-applicable"), None, "weak-verdict"),
        # Tie-broken to a polar verdict: still restated, because the verdict was contested.
        (analyst_args(verdict="mixed"), auditor_args(verdict="true", confidence="high"),
         auditor_args(verdict="true", confidence="high"), "tie-broken"),
        # Tie-broken to a weak verdict: the weak verdict is the reason recorded.
        (analyst_args(verdict="unverified"), auditor_args(verdict="true"),
         auditor_args(verdict="unverified"), "weak-verdict"),
    ],
    ids=["true-agreed", "true-with-two-gaps", "mostly-false-agreed", "unverified", "mixed", "not-applicable",
         "tie-broken-polar", "tie-broken-weak"],
)
async def test_restater_runs_only_on_the_trigger_set(tmp_path, analyst, auditor, tiebreaker, trigger) -> None:
    write_entity(tmp_path)
    model, _prompts, calls = _capturing_restater()
    result = await _run(tmp_path, analyst=analyst, auditor=auditor, tiebreaker=tiebreaker, restater_model=model)

    assert result.analyst_output is not None and result.consistency is not None
    if trigger is None:
        assert calls == [], "a polar agreed verdict has nothing to restate"
        assert result.restatement is None
        assert result.finding is None or result.finding.outcome == "split"
    else:
        assert calls == ["restater"]
        block = result.restatement
        assert block is not None
        assert block["trigger"] == trigger
        assert block["original"] == {
            "statement": SENTENCE,
            "verdict": result.consistency.pipeline_verdict.value,
            "confidence": result.consistency.pipeline_confidence.value,
        }
        assert [c["rank"] for c in block["candidates"]] == [1, 2]


@pytest.mark.asyncio
async def test_restater_runs_after_the_tie_break_and_sees_the_settled_verdict(tmp_path) -> None:
    write_entity(tmp_path)
    model, prompts, _calls = _capturing_restater()
    result = await _run(
        tmp_path,
        analyst=analyst_args(verdict="mixed"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="high"),
        restater_model=model,
    )
    assert result.consistency.rule_applied == "tiebreaker-matched-evaluator"
    assert result.restatement["original"]["verdict"] == "true"
    (prompt,) = prompts
    assert "true" in prompt and SENTENCE in prompt
    # The finding of a tie-broken run stays the split; the restater's success adds nothing.
    assert result.finding is not None and result.finding.outcome == "split"


@pytest.mark.asyncio
async def test_rerun_never_restates(tmp_path) -> None:
    """``dr step-audit --write`` and ``dr step-analyze --write`` carry a block forward; only the full run writes one."""
    import loop
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment

    write_entity(tmp_path)
    spec = claim_spec(tmp_path)
    sources = [{
        "source_id": "2026/stored", "slug": "stored", "url": URLS[0], "title": "Stored report",
        "publisher": "Example Publisher", "summary": "Stored.", "key_quotes": [], "body": "Body.",
        "kind": "article", "independence": "independent",
    }]
    analysis = AnalystOutput(
        entity=EntityResolution(entity_name=ENTITY_NAME, entity_type="subject", entity_description="A test entity."),
        verdict=VerdictAssessment(**analyst_args(verdict="unverified"), cited_sources=["2026/stored"]),
    )
    model, _prompts, calls = _capturing_restater()
    with scripted_agents(
        analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"), restater_model=model,
    ):
        evaluated = await loop.rerun(spec, _config(tmp_path), sources, agent="evaluator", analyst_output=analysis)
        analysed = await loop.rerun(spec, _config(tmp_path), sources, agent="analyst")

    assert evaluated.consistency.pipeline_verdict == Verdict.UNVERIFIED
    assert evaluated.restatement is None and analysed.restatement is None
    assert calls == []


# --------------------------------------------------------------------------- #
# The polarity guard: the prompt and the ranking                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_restater_prompt_carries_the_original_and_no_opinion(tmp_path) -> None:
    """R6 and D4: the agent explains a gap; it never sees a verdict to defend or the reviewers' reasoning."""
    write_entity(tmp_path)
    model, prompts, _calls = _capturing_restater()
    gaps = ["no source names the denominator", "no source gives 2024 figures"]
    await _run(
        tmp_path,
        analyst=analyst_args(verdict="unverified", narrative="The pool circles the share."),
        auditor=auditor_args(verdict="true", evidence_gaps=gaps),
        tiebreaker=auditor_args(verdict="unverified"),
        restater_model=model,
    )
    (prompt,) = prompts
    assert SENTENCE in prompt
    assert f"Entity: {ENTITY_NAME}" in prompt.splitlines(), "the name candidates must use, on a line of its own"
    assert "unverified" in prompt, "the pipeline verdict is shown: the agent explains a gap, not a thesis"
    assert "The pool circles the share." in prompt, "the narrative is context"
    assert all(g in prompt for g in gaps), "the Evaluator's evidence gaps are inputs"
    assert "Independent assessment." not in prompt, "neither the Evaluator's nor the tie-breaker's reasoning"
    assert "expected" not in prompt.lower()
    assert "[cited]" in prompt, "a source the claim lists is marked"
    assert "independence: independent" in prompt.lower()
    assert "candidates" in prompt.lower()


@pytest.mark.asyncio
async def test_candidates_rank_by_decisiveness_in_either_direction(tmp_path) -> None:
    """The model's order is discarded; a refuted candidate ranks above a confirmed one when the evidence is stronger."""
    write_entity(tmp_path)
    proposal = restater_args(candidates=[
        candidate(f"{ENTITY_NAME} ran on renewable power in 2024.", expected_verdict="true", decisiveness=2),
        candidate(f"{ENTITY_NAME} ran on gas-fired power in 2024.", expected_verdict="false", decisiveness=4,
                  supporting=[{"source": "2026/grid", "quote": "gas supplied most of its power in 2024", "note": "states it"}]),
        candidate(f"{ENTITY_NAME} certified its data centers as renewable.", expected_verdict="unverified", decisiveness=4),
    ])
    _write_source(
        tmp_path, "2026/grid", url="https://grid.example/mix", title=f"{ENTITY_NAME} grid mix",
        body=f"In 2024 gas supplied most of its power in 2024, says the {ENTITY_NAME} report.",
    )
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater=proposal,
    )
    ranked = result.restatement["candidates"]
    assert [c["expected_verdict"] for c in ranked] == ["false", "true", "unverified"]
    assert [c["rank"] for c in ranked] == [1, 2, 3]
    assert ranked[0]["decisiveness"] == 4 and ranked[0]["supporting"][0]["quote_verified"] is True
    assert ranked[2]["decisiveness"] <= 1 and ranked[2]["needs_new_research"] is True


@pytest.mark.asyncio
async def test_code_side_checks_cap_decisiveness_verify_quotes_and_drop_unknown_sources(tmp_path) -> None:
    write_entity(tmp_path)
    _write_source(
        tmp_path, "2026/known", url="https://known.example/report", title=f"{ENTITY_NAME} energy figures",
        body=f"{ENTITY_NAME} used 183 TWh in 2024. Its share of the grid is not given.",
    )
    verified = {"source": "2026/known", "quote": "used 183  twh in 2024", "note": "states the figure"}
    invented = {"source": "2026/known", "quote": "ran entirely on wind power", "note": "not on the page"}
    unknown = {"source": "2026/nowhere", "quote": "used 183 TWh in 2024", "note": "no such file"}
    proposal = restater_args(candidates=[
        candidate(f"{ENTITY_NAME} used 183 TWh of electricity in 2024.", decisiveness=4, supporting=[verified]),
        candidate(f"{ENTITY_NAME} ran entirely on wind power in 2024.", decisiveness=4, supporting=[invented]),
        candidate(f"{ENTITY_NAME} used 183 TWh in 2024 by one count.", decisiveness=4, supporting=[unknown]),
        candidate(f"{ENTITY_NAME} discloses its grid share.", expected_verdict="unverified", decisiveness=3),
        candidate(f"{ENTITY_NAME} says it matches its use with certificates.", frame="disclosure",
                  expected_confidence="high", level="claimed", decisiveness=3, supporting=[verified]),
    ])
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater=proposal,
    )
    by_text = {c["text"]: c for c in result.restatement["candidates"]}

    direct = by_text[f"{ENTITY_NAME} used 183 TWh of electricity in 2024."]
    assert direct["decisiveness"] == 4, "whitespace and case do not break a verified quote"
    assert direct["supporting"][0]["quote_verified"] is True

    unfound = by_text[f"{ENTITY_NAME} ran entirely on wind power in 2024."]
    assert unfound["supporting"][0]["quote_verified"] is False
    assert unfound["decisiveness"] == 2, "no verified supporting quote caps decisiveness at 2"

    dropped_ref = by_text[f"{ENTITY_NAME} used 183 TWh in 2024 by one count."]
    assert dropped_ref["supporting"] == [], "an unknown source id drops the ref"
    assert dropped_ref["decisiveness"] == 2

    unverified = by_text[f"{ENTITY_NAME} discloses its grid share."]
    assert unverified["decisiveness"] <= 1 and unverified["needs_new_research"] is True

    capped = by_text[f"{ENTITY_NAME} says it matches its use with certificates."]
    assert capped["expected_confidence"] == "low", "the confidence cap applies to a claimed or self-reported level"


# --------------------------------------------------------------------------- #
# The same-entity rule                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_candidate_naming_another_entity_is_dropped_and_listed(tmp_path) -> None:
    """D14: every candidate is about the entity shown; an alias counts as its name."""
    path = tmp_path / "research" / "entities" / "subjects" / "probe-subject.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {ENTITY_NAME}\ntype: subject\naliases:\n  - PS Facilities\ndescription: A test entity.\n---\n",
        encoding="utf-8",
    )
    proposal = restater_args(candidates=[
        candidate(f"{ENTITY_NAME} used 183 TWh of electricity in 2024.", decisiveness=3),
        candidate("Other Corp supplies the gas-fired power behind the servers.", frame="supplier", decisiveness=4),
        candidate("PS Facilities buy renewable certificates to match their annual use.", frame="disclosure", decisiveness=2),
    ])
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater=proposal,
    )
    block = result.restatement
    texts = [c["text"] for c in block["candidates"]]
    assert f"{ENTITY_NAME} used 183 TWh of electricity in 2024." in texts
    assert "PS Facilities buy renewable certificates to match their annual use." in texts, "an alias names the entity"
    assert "Other Corp supplies the gas-fired power behind the servers." not in texts
    assert [c["rank"] for c in block["candidates"]] == [1, 2], "ranks are renumbered after the drop"
    (dropped,) = block["dropped"]
    assert dropped["text"] == "Other Corp supplies the gas-fired power behind the servers."
    assert ENTITY_NAME in dropped["reason"]


@pytest.mark.asyncio
async def test_a_name_the_original_statement_uses_counts_as_the_claims_own(tmp_path) -> None:
    """Card C3 names products in a subject claim; a narrowed candidate about them is not another entity.

    Allowed names: the entity's name, legal name and aliases, plus the name or
    alias of any entity file the original statement itself names. Matching is
    whole words, case-insensitive, and a trailing "s" on a word is ignored
    ("US data center operators" names "US Data Centers").
    """
    import loop

    write_entity(tmp_path)
    write_entity(tmp_path, "products/widget-cloud", "Widget Cloud")
    write_entity(tmp_path, "products/other-corp", "Other Corp")
    sentence = "A typical Widget Cloud prompt uses about a third of a watt-hour of electricity"
    proposal = restater_args(candidates=[
        candidate("A typical Widget Cloud prompt uses 0.24 watt-hours of electricity.", decisiveness=3),
        candidate("A typical Other Corp prompt uses 0.34 watt-hours of electricity.", decisiveness=3),
        candidate(f"{ENTITY_NAME.lower()}s serve each prompt from one data center.", decisiveness=2),
    ])
    with scripted_agents(
        analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"), restater=proposal,
    ):
        result = await loop.run(claim_spec(tmp_path, sentence=sentence), _config(tmp_path))
    block = result.restatement
    assert {c["text"] for c in block["candidates"]} == {
        "A typical Widget Cloud prompt uses 0.24 watt-hours of electricity.",
        f"{ENTITY_NAME.lower()}s serve each prompt from one data center.",
    }, "a name from the original counts; case and a trailing s do not matter"
    assert [c["rank"] for c in block["candidates"]] == [1, 2]
    assert [d["text"] for d in block["dropped"]] == ["A typical Other Corp prompt uses 0.34 watt-hours of electricity."]


@pytest.mark.asyncio
async def test_every_candidate_dropped_asks_the_restater_again_then_records_a_partial_finding(tmp_path) -> None:
    """A proposal with no candidate about the entity is invalid output: the agent is told why and asked again.

    The restater's own output check names the entity and asks for new
    candidates (PydanticAI's retries inside one step attempt); past those the
    step fails as ``invalid_output``, the flaw rule retries the step once, and
    the claim keeps its verdict with a ``partial`` finding.
    """
    write_entity(tmp_path)
    prompts: list[str] = []
    calls: list[str] = []
    off_entity = restater_args(candidates=[
        candidate("Other Corp supplies the gas-fired power behind the servers.", decisiveness=4),
        candidate("Another Org buys renewable certificates.", decisiveness=3),
    ])
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater_model=capturing_model(prompts, off_entity, calls=calls, name="restater"),
    )
    assert len(calls) > 2, "within one step attempt the model was asked again, not only by the step retry"
    assert result.restatement is None
    assert result.consistency.pipeline_verdict == Verdict.UNVERIFIED
    finding = result.finding
    assert (finding.step, finding.outcome, finding.rule, finding.attempts) == ("restate", "partial", "flaw-retry", 2)
    assert finding.error["error_type"] == "invalid_output"


_GAS = f"{ENTITY_NAME} ran on gas-fired power in 2024."
_RENEWABLE = f"{ENTITY_NAME} ran on renewable power in 2024."


def _grid_source(tmp_path) -> None:
    _write_source(
        tmp_path, "2026/grid", url="https://grid.example/mix", title=f"{ENTITY_NAME} grid mix",
        body=f"In 2024 gas supplied most of its power in 2024, says the {ENTITY_NAME} report.",
    )


@pytest.mark.asyncio
async def test_an_answer_with_an_evidence_key_is_asked_again_then_records_a_partial_finding(tmp_path) -> None:
    """A restater that keeps putting its quotes under ``evidence`` never gets a block with empty refs."""
    write_entity(tmp_path)
    _grid_source(tmp_path)
    calls: list[str] = []
    retry_messages: list[str] = []
    keyed = restater_args(candidates=[
        _evidence_keyed(candidate(_GAS, decisiveness=4)),
        _evidence_keyed(candidate(_RENEWABLE, expected_verdict="false", decisiveness=4)),
    ])
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater_model=_answers_in_turn([keyed], calls=calls, retry_messages=retry_messages),
    )
    assert len(calls) > 2, "within one step attempt the model was asked again"
    assert any("evidence" in m for m in retry_messages), "the re-ask names the key that is not allowed"
    assert result.restatement is None
    finding = result.finding
    assert (finding.step, finding.outcome, finding.rule, finding.attempts) == ("restate", "partial", "flaw-retry", 2)
    assert finding.error["error_type"] == "invalid_output"


@pytest.mark.asyncio
async def test_an_answer_with_an_evidence_key_then_a_valid_one_keeps_the_refs_and_ranks_by_them(tmp_path) -> None:
    write_entity(tmp_path)
    _grid_source(tmp_path)
    calls: list[str] = []
    retry_messages: list[str] = []
    quote = {"source": "2026/grid", "quote": "gas supplied most of its power in 2024", "note": "states it"}
    keyed = restater_args(candidates=[
        _evidence_keyed(candidate(_RENEWABLE, decisiveness=4)),
        _evidence_keyed(candidate(_GAS, decisiveness=4)),
    ])
    valid = restater_args(candidates=[
        candidate(_RENEWABLE, expected_verdict="false", decisiveness=4, supporting=[quote]),
        candidate(_GAS, decisiveness=4, supporting=[quote]),
        candidate(f"{ENTITY_NAME} certified its data centers as renewable.", decisiveness=4),
    ])
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater_model=_answers_in_turn([keyed, valid], calls=calls, retry_messages=retry_messages),
    )
    assert len(calls) == 2 and any("evidence" in m for m in retry_messages)
    ranked = result.restatement["candidates"]
    assert [c["decisiveness"] for c in ranked] == [4, 4, 2], "a verified ref, not the text, decides the order"
    assert ranked[2]["text"] == f"{ENTITY_NAME} certified its data centers as renewable."
    assert all(c["supporting"][0]["quote_verified"] is True for c in ranked[:2])
    assert result.finding is None


@pytest.mark.asyncio
async def test_a_restater_retry_after_a_tie_break_is_recorded_on_the_split_finding(tmp_path) -> None:
    """The split finding is built before the restater runs; a restater that succeeds on its retry still shows."""
    write_entity(tmp_path)
    calls: list[str] = []
    result = await _run(
        tmp_path,
        analyst=analyst_args(verdict="mixed"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="high"),
        restater_model=flaky_model(restater_args(), fail_times=1, calls=calls),
    )
    assert calls == ["run", "run"]
    assert result.restatement is not None
    finding = result.finding
    assert (finding.step, finding.outcome) == ("tiebreak", "split")
    assert "restater" in finding.models_used
    assert [r for r in finding.retries if r["step"] == "restate"] == [
        {"step": "restate", "error_type": "model_error", "rule": "flaw-retry", "attempts": 2},
    ]


# --------------------------------------------------------------------------- #
# The pool: consulted sources plus the ranked research/sources/ pool               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pool_is_the_consulted_sources_plus_the_ranked_disk_pool(tmp_path) -> None:
    """D3: the whole ``research/sources/`` pool, ranked by entity, statement and sub-question terms, consulted first."""
    write_entity(tmp_path)
    _write_source(
        tmp_path, "2026/probe-report", url="https://archive.example/probe", title=f"{ENTITY_NAME} energy report",
        body=f"{ENTITY_NAME} data centers and their electricity use in 2024.",
    )
    _write_source(
        tmp_path, "2026/gardening", url="https://archive.example/gardening", title="Spring planting tips",
        body="Plant tomatoes after the last frost and water them in the morning.",
    )
    model, prompts, _calls = _capturing_restater()
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater_model=model,
    )
    (prompt,) = prompts
    assert f"{ENTITY_NAME} energy report" in prompt
    assert "[archive]" in prompt, "a pool source the run did not consult is marked as from the archive"
    assert "Spring planting tips" not in prompt, "a source that scores zero is not sent"
    assert prompt.index("[cited]") < prompt.index("[archive]"), "consulted sources come first"
    assert result.restatement["pool"] == {"consulted": 4, "on_disk": 1, "sent": 5}


@pytest.mark.asyncio
async def test_pool_cap_keeps_consulted_sources_and_cuts_the_disk_pool(tmp_path) -> None:
    write_entity(tmp_path)
    for i in range(3):
        _write_source(
            tmp_path, f"2026/probe-{i}", url=f"https://archive.example/probe-{i}",
            title=f"{ENTITY_NAME} report {i}", body=f"{ENTITY_NAME} electricity figures for 2024, part {i}.",
        )
    model, prompts, _calls = _capturing_restater()
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater_model=model, config=_config(tmp_path, restate_pool_size=5),
    )
    (prompt,) = prompts
    assert result.restatement["pool"] == {"consulted": 4, "on_disk": 3, "sent": 5}
    assert prompt.count("[cited]") == 4
    assert prompt.count("[archive]") == 1


# --------------------------------------------------------------------------- #
# One block per sidecar: written, carried, replaced, removed                       #
# --------------------------------------------------------------------------- #


def test_draft_writes_one_restatement_block_with_the_plan_shape(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified")):
        result = _draft(tmp_path)
    assert result.exit_code == 0, result.output

    sidecar = _sidecar(tmp_path)
    assert sidecar["restatement"] == expected_restatement_block(
        verdict="unverified", confidence="medium", trigger="weak-verdict", consulted=4,
    )
    assert "restater" in sidecar["pipeline_run"]["agents"]
    assert sidecar["models_used"]["restater"] == "test"
    assert list(sidecar).count("restatement") == 1
    assert "Restatement:" in result.output and "2 candidates" in result.output
    assert not (tmp_path / "research" / "findings").exists(), "a successful restatement is not a finding"


def test_dry_run_prints_the_candidates_and_writes_nothing(tmp_path) -> None:
    """The live probe and an operator's dry run see the candidates; probe safety holds."""
    from tests.loop_harness import RESTATER_CANDIDATES

    write_entity(tmp_path)
    with scripted_agents(analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified")):
        result = _draft(tmp_path, dry_run=True)
    assert result.exit_code == 0, result.output
    assert "Restatement:" in result.output
    for c in RESTATER_CANDIDATES:
        assert c["text"] in result.output
    assert written_claims(tmp_path) == []
    assert written_sources(tmp_path) == []
    assert _findings(tmp_path) == []


def test_a_polar_agreed_draft_writes_no_block_and_no_restater_entry(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(analyst=analyst_args(verdict="true"), auditor=auditor_args(verdict="true")):
        result = _draft(tmp_path)
    assert result.exit_code == 0, result.output
    sidecar = _sidecar(tmp_path)
    assert "restatement" not in sidecar
    assert "restater" not in sidecar["pipeline_run"]["agents"]
    assert "restater" not in sidecar["models_used"]


def test_step_audit_write_carries_the_block_forward_unchanged(tmp_path) -> None:
    write_entity(tmp_path)
    claim_path, sidecar_path = _write_claim(tmp_path, stem="weak-claim", restatement=_block(picked=2))
    before = _sidecar_of(claim_path)["restatement"]
    with scripted_agents(auditor=auditor_args(verdict="unverified")):
        result = _dr(tmp_path, "step-audit", "--claim", _claim_ref(claim_path, tmp_path), "--write")
    assert result.exit_code == 0, result.output
    after = _sidecar_of(claim_path)
    assert after["audit"]["auditor_verdict"] == "unverified"
    assert after["restatement"] == before, "an Evaluator rerun rewrites the sidecar but keeps the block and the pick"


def test_step_analyze_forced_write_keeps_the_block(tmp_path) -> None:
    """The third later write: ``mark_forced_rewrite`` and ``clear_audit`` edit the sidecar in place."""
    write_entity(tmp_path)
    claim_path, _ = _write_claim(tmp_path, stem="weak-claim", restatement=_block(picked=3))
    before = _sidecar_of(claim_path)["restatement"]
    with scripted_agents(analyst=analyst_args(verdict="unverified")):
        result = _dr(tmp_path, "step-analyze", "--claim", _claim_ref(claim_path, tmp_path), "--write", "--force")
    assert result.exit_code == 0, result.output
    assert _sidecar_of(claim_path)["restatement"] == before


def test_a_later_full_run_replaces_the_block_or_drops_it(tmp_path) -> None:
    """D9: one block per claim, the latest run's; a run that did not restate leaves none."""
    write_entity(tmp_path)
    claim_path, _ = _write_claim(tmp_path, stem=slugify(SENTENCE), restatement=_block(picked=1))
    ref = _claim_ref(claim_path, tmp_path)

    with scripted_agents(analyst=analyst_args(verdict="mixed"), auditor=auditor_args(verdict="mixed")):
        rerun = _dr(tmp_path, "draft", "--claim", ref, "--force", "--skip-wayback")
    assert rerun.exit_code == 0, rerun.output
    replaced = _sidecar_of(claim_path)["restatement"]
    assert replaced["original"]["verdict"] == "mixed"
    assert replaced["picked"] is None, "the pick belonged to the earlier candidates"
    assert [c["text"] for c in replaced["candidates"]] != PICK_TEXTS

    with scripted_agents(analyst=analyst_args(verdict="true"), auditor=auditor_args(verdict="true")):
        polar = _dr(tmp_path, "draft", "--claim", ref, "--force", "--skip-wayback")
    assert polar.exit_code == 0, polar.output
    assert "restatement" not in _sidecar_of(claim_path), "a block for a verdict the claim no longer has would mislead"


def test_approve_and_archive_remove_the_block_and_keep_restates(tmp_path, human_at_terminal) -> None:
    """Like ``refresh``: approving publishes the claim as it stands, archiving retires it; a bare sign-off leaves it."""
    from orchestrator.review import approve_claim

    write_entity(tmp_path)
    reviewed, _ = _write_claim(tmp_path, stem="reviewed", criteria_slug="x", restatement=_block(),
                               restates=f"{ENTITY_REF}/older")
    approve_claim(reviewed, reviewer="r@example.org", mode="review")
    after_review = _sidecar_of(reviewed)
    assert "restatement" in after_review and after_review["restates"] == f"{ENTITY_REF}/older"

    approve_claim(reviewed, reviewer="r@example.org", mode="approve")
    after_approve = _sidecar_of(reviewed)
    assert "restatement" not in after_approve
    assert after_approve["restates"] == f"{ENTITY_REF}/older", "D17: the link to the original stays"
    assert parse_frontmatter(reviewed.read_text(encoding="utf-8"))[0]["status"] == "published"

    archived, _ = _write_claim(tmp_path, stem="archived", status="published", restatement=_block())
    approve_claim(archived, reviewer="r@example.org", mode="archive")
    assert "restatement" not in _sidecar_of(archived)


def test_an_unreadable_finding_file_is_skipped_not_fatal(tmp_path) -> None:
    from orchestrator.persistence import load_findings

    d = tmp_path / "research" / "findings" / "2026"
    d.mkdir(parents=True)
    (d / "bad-yaml.yaml").write_text("run_id: [unclosed\n", encoding="utf-8")
    (d / "missing-keys.yaml").write_text("run_id: abc\n", encoding="utf-8")
    assert load_findings(tmp_path, include_closed=True) == []

    from orchestrator.cli import main

    queue = CliRunner().invoke(main, ["review", "--format", "json", "--repo-root", str(tmp_path)])
    assert queue.exit_code == 0, queue.output


# --------------------------------------------------------------------------- #
# dr draft --restates <ref> --pick <n>                                             #
# --------------------------------------------------------------------------- #


def _picked_fixture(tmp_path, *, block: dict | None = None) -> tuple[Path, str]:
    write_entity(tmp_path)
    claim_path, _ = _write_claim(tmp_path, stem="original", restatement=block if block is not None else _block())
    return claim_path, _claim_ref(claim_path, tmp_path)


def test_restates_pick_runs_the_candidate_as_a_new_claim_with_the_link(tmp_path) -> None:
    original, ref = _picked_fixture(tmp_path)
    text = PICK_TEXTS[1]
    prompts: list[str] = []
    with scripted_agents(
        analyst_model=capturing_model(prompts, analyst_args(verdict="true")),
        auditor=auditor_args(verdict="true"),
    ):
        result = _dr(tmp_path, "draft", "--restates", ref, "--pick", "2", "--skip-wayback")
    assert result.exit_code == 0, result.output

    new_path = claim_dir(tmp_path) / f"{slugify(text)}.md"
    assert new_path.exists(), written_claims(tmp_path)
    fm, _ = parse_frontmatter(new_path.read_text(encoding="utf-8"))
    assert fm["statement"] == text and fm["title"] == text, "the sentence is read from the sidecar, never retyped"
    assert fm["entity"] == ENTITY_REF
    assert "criteria_slug" not in fm, "a restatement is an ad hoc claim; a criterion is attached before sign-off"
    assert any(text in p for p in prompts), "the analyst assessed the candidate verbatim, quotes and apostrophe included"
    assert _sidecar_of(new_path)["restates"] == ref
    assert _sidecar_of(original)["restatement"]["picked"] == 2
    assert parse_frontmatter(original.read_text(encoding="utf-8"))[0]["statement"] == SENTENCE, "the original stays"
    assert "--restates" in result.output or "restates" in result.output


def test_restates_pick_dry_run_writes_nothing_and_records_no_pick(tmp_path) -> None:
    original, ref = _picked_fixture(tmp_path)
    with scripted_agents(analyst=analyst_args(verdict="true"), auditor=auditor_args(verdict="true")):
        result = _dr(tmp_path, "draft", "--restates", ref, "--pick", "1", "--dry-run", "--skip-wayback")
    assert result.exit_code == 0, result.output
    assert written_claims(tmp_path) == [original]
    assert written_sources(tmp_path) == []
    assert _sidecar_of(original)["restatement"]["picked"] is None
    assert PICK_TEXTS[0] in result.output


def test_restates_link_survives_a_forced_rerun_of_the_new_claim(tmp_path) -> None:
    _original, ref = _picked_fixture(tmp_path)
    with scripted_agents(analyst=analyst_args(verdict="true"), auditor=auditor_args(verdict="true")):
        first = _dr(tmp_path, "draft", "--restates", ref, "--pick", "3", "--skip-wayback")
    assert first.exit_code == 0, first.output
    new_path = claim_dir(tmp_path) / f"{slugify(PICK_TEXTS[2])}.md"
    with scripted_agents(analyst=analyst_args(verdict="true"), auditor=auditor_args(verdict="true")):
        again = _dr(tmp_path, "draft", "--claim", _claim_ref(new_path, tmp_path), "--force", "--skip-wayback")
    assert again.exit_code == 0, again.output
    assert _sidecar_of(new_path)["restates"] == ref


@pytest.mark.parametrize(
    ("args", "exit_code"),
    [
        (["--restates", "REF", "--pick", "1", SENTENCE], 2),                 # SENTENCE refused
        (["--restates", "REF"], 2),                                           # --pick required
        (["--pick", "1", "--entity", ENTITY_REF, SENTENCE], 2),               # --pick needs --restates
        (["--restates", "REF", "--pick", "1", "--entity", ENTITY_REF], 2),    # two mode flags
        (["--restates", "REF", "--pick", "1", "--claim", "REF", "--force"], 2),  # two mode flags
        (["--restates", "REF", "--pick", "1", "--criterion", "some-slug"], 2),  # no criterion on a restatement run
        (["--restates", "REF", "--pick", "0"], 2),                            # ranks start at 1
        (["--restates", "REF", "--pick", "4"], 1),                            # three candidates
        (["--restates", f"{ENTITY_REF}/no-such-claim", "--pick", "1"], 1),    # claim not found
        (["--restates", "BARE", "--pick", "1"], 1),                           # a claim with no block
    ],
    ids=["sentence", "no-pick", "pick-without-restates", "with-entity", "with-claim", "with-criterion",
         "pick-zero", "pick-out-of-range", "missing-claim", "missing-block"],
)
def test_restates_refusals_run_no_model_and_write_nothing(tmp_path, monkeypatch, args, exit_code) -> None:
    original, ref = _picked_fixture(tmp_path)
    bare, _ = _write_claim(tmp_path, stem="bare")
    args = [ref if a == "REF" else _claim_ref(bare, tmp_path) if a == "BARE" else a for a in args]
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, "draft", *args, "--skip-wayback")
    assert result.exit_code == exit_code, result.output
    assert "No such option" not in result.output, result.output
    assert called == []
    assert set(written_claims(tmp_path)) == {original, bare}
    assert _sidecar_of(original)["restatement"]["picked"] is None


def test_restates_pick_records_no_pick_when_the_run_is_abandoned(tmp_path) -> None:
    """``picked`` is written only after the new claim is: an abandoned run leaves the original untouched."""
    original, ref = _picked_fixture(tmp_path)
    before = original.with_suffix(".audit.yaml").read_bytes()
    with scripted_agents(analyst_model=failing_model(), auditor=auditor_args(verdict="true")):
        result = _dr(tmp_path, "draft", "--restates", ref, "--pick", "1", "--skip-wayback")
    assert result.exit_code == 1, result.output
    assert written_claims(tmp_path) == [original]
    assert original.with_suffix(".audit.yaml").read_bytes() == before
    (finding,) = _findings(tmp_path)
    assert finding["outcome"] == "abandoned" and finding["claim_spec"]["statement"] == PICK_TEXTS[0]


def test_restates_pick_refuses_an_existing_claim_at_the_candidates_stem_before_the_loop(tmp_path, monkeypatch) -> None:
    _original, ref = _picked_fixture(tmp_path)
    _write_claim(tmp_path, stem=slugify(PICK_TEXTS[0]), statement=PICK_TEXTS[0])
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, "draft", "--restates", ref, "--pick", "1", "--skip-wayback")
    assert result.exit_code == 1, result.output
    assert "--force" in result.output
    assert called == []


# --------------------------------------------------------------------------- #
# A restater failure after a valid verdict: outcome partial                        #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_restater_failure_is_a_partial_finding_that_keeps_the_verdict(tmp_path) -> None:
    write_entity(tmp_path)
    calls: list[str] = []
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater_model=failing_model(calls=calls),
    )
    assert calls == ["run", "run"], "a flaw: one retry, then the run goes on without a block"
    assert result.restatement is None
    assert result.analyst_output is not None
    assert result.consistency.pipeline_verdict == Verdict.UNVERIFIED
    finding = result.finding
    assert finding is not None
    assert (finding.step, finding.outcome, finding.rule, finding.attempts) == ("restate", "partial", "flaw-retry", 2)
    assert finding.error["error_type"] == "model_error"
    assert "restater" in finding.models_used


@pytest.mark.asyncio
async def test_restater_transport_failure_follows_the_transport_rule(tmp_path) -> None:
    write_entity(tmp_path)
    calls: list[str] = []
    result = await _run(
        tmp_path, analyst=analyst_args(verdict="mixed"), auditor=auditor_args(verdict="mixed"),
        restater_model=failing_model(httpx.ConnectError("gateway down"), calls=calls),
        config=_config(tmp_path, transport_retries=2, transport_backoff_s=(0.0, 0.0)),
    )
    assert len(calls) == 3
    assert result.restatement is None
    assert result.finding.outcome == "partial" and result.finding.rule == "transport-retry"


@pytest.mark.asyncio
async def test_restater_failure_after_a_tie_break_keeps_the_split_in_the_finding(tmp_path) -> None:
    write_entity(tmp_path)
    result = await _run(
        tmp_path,
        analyst=analyst_args(verdict="mixed"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="high"),
        restater_model=failing_model(),
    )
    finding = result.finding
    assert finding.outcome == "partial" and finding.step == "restate"
    split = [r for r in finding.retries if r["error_type"] == "verdict_split"]
    assert len(split) == 1
    assert split[0]["step"] == "tiebreak"
    assert split[0]["message"] == "analyst mixed, evaluator true, tie-breaker true"
    assert result.consistency.pipeline_verdict == Verdict.TRUE


def test_draft_writes_the_claim_without_a_block_and_the_review_queue_names_the_finding(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(
        analyst=analyst_args(verdict="unverified"), auditor=auditor_args(verdict="unverified"),
        restater_model=failing_model(),
    ):
        result = _draft(tmp_path)
    assert result.exit_code == 0, result.output

    (claim_path,) = written_claims(tmp_path)
    sidecar = _sidecar_of(claim_path)
    assert "restatement" not in sidecar
    assert "restater" not in sidecar["pipeline_run"]["agents"], "no restater output is on disk"
    (finding,) = _findings(tmp_path)
    assert finding["step"] == "restate" and finding["outcome"] == "partial"
    assert finding["command"] == "dr draft"
    assert finding["claim_ref"] and finding["claim_ref"].endswith(claim_path.stem)
    assert finding["run_id"] == sidecar["pipeline_run"]["run_id"]
    assert "restater" in finding["models_used"]
    assert "unavailable" in result.output.lower() and finding["run_id"] in result.output

    from orchestrator.cli import main

    queue = CliRunner().invoke(main, ["review", "--format", "json", "--repo-root", str(tmp_path)])
    assert queue.exit_code == 0, queue.output
    (item,) = json.loads(queue.output)
    assert item["claim_slug"].endswith(claim_path.stem)
    assert item["restatement_unavailable"] == finding["run_id"]
    assert item["restatement"] is None


def test_review_json_carries_the_block_when_one_was_written(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(analyst=analyst_args(verdict="mixed"), auditor=auditor_args(verdict="mixed")):
        result = _draft(tmp_path)
    assert result.exit_code == 0, result.output

    from orchestrator.cli import main

    queue = CliRunner().invoke(main, ["review", "--format", "json", "--repo-root", str(tmp_path)])
    assert queue.exit_code == 0, queue.output
    (item,) = json.loads(queue.output)
    assert item["restatement_unavailable"] == ""
    assert [c["rank"] for c in item["restatement"]["candidates"]] == [1, 2]
    assert item["restatement"]["picked"] is None


# --------------------------------------------------------------------------- #
# Carried from RE-BA (Source pool rules): BA-1, BA-2, BA-3                         #
# --------------------------------------------------------------------------- #


def test_max_initial_queries_below_one_is_a_usage_error_before_the_loop(tmp_path, monkeypatch) -> None:
    """BA-2: ``--max-initial-queries 0`` used to plan nothing silently."""
    write_entity(tmp_path)
    called = _tripwire(monkeypatch)
    result = _draft(tmp_path, "--max-initial-queries", "0", dry_run=True)
    assert result.exit_code == 2, result.output
    assert called == []

    reached = _tripwire(monkeypatch)
    _draft(tmp_path, "--max-initial-queries", "1", dry_run=True)
    assert reached == ["run"], "1 is the lowest allowed value"


def _audit_schema_block() -> str:
    source = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    start = source.index("const auditSchema = z.object({")
    end = source.index("\n});", start)
    return source[start:end]


def _top_level_keys(block: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for line in block.splitlines()[1:]:
        m = re.match(r"  (\w+): (z\..*)$", line)
        if m:
            keys[m.group(1)] = m.group(2)
    return keys


def test_site_schema_declares_the_sidecar_keys_this_spike_writes() -> None:
    """BA-3 and the plan's one-sidecar-shape rule: every added key declared, optional, in the same commit."""
    block = _audit_schema_block()
    keys = _top_level_keys(block)
    for key in ("restatement", "restates", "analyst_record"):
        assert key in keys, f"auditSchema lacks {key}"
    restatement = block[block.index("  restatement:"):]
    for field in ("candidates", "picked", "why_unverified"):
        assert field in restatement, f"restatement declaration lacks {field}"
    record = block[block.index("  analyst_record:"):]
    assert "uncited_by_title" in record
    for key in ("restatement", "restates", "analyst_record"):
        assert ".optional()" in _declaration(block, key), f"{key} must be optional so the sidecars on disk validate"


def _declaration(block: str, key: str) -> str:
    """The text of one top-level key's declaration: from its line to the next top-level key."""
    lines = block.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"  {key}:"))
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"  \w+:", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def test_the_shared_word_coverage_clause_is_in_both_architecture_docs() -> None:
    """BA-1: the coverage rule's shared-word clause was recorded in the roadmap only."""
    for rel in ("docs/architecture/research-flow.md", "docs/architecture/content-model.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "two or more sub-questions" in text, rel


# --------------------------------------------------------------------------- #
# The docs                                                                          #
# --------------------------------------------------------------------------- #


def test_the_absorbed_plan_moved_with_its_banner() -> None:
    assert not (REPO_ROOT / "docs" / "plans" / "claim-restate.md").exists()
    moved = REPO_ROOT / "docs" / "plans" / "completed" / "claim-restate_superseded.md"
    assert moved.exists()
    head = "\n".join(moved.read_text(encoding="utf-8").splitlines()[:6])
    assert "Superseded" in head and "RE-AU (Restate inside the loop)" in head


def test_the_runbook_has_the_restatement_section_and_names_the_command() -> None:
    text = (REPO_ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    assert "## Picking a restatement" in text
    assert "dr draft --restates" in text and "--pick" in text
    assert "restatement unavailable" in text.lower()


def test_the_operator_docs_never_name_the_unbuilt_command() -> None:
    """The spike's shared grep: ``claim-restate`` over the operator set returns nothing but completed-plan paths."""
    files = [REPO_ROOT / "AGENTS.md", REPO_ROOT / "CONTRIBUTING.md", REPO_ROOT / "docs" / "runbook.md",
             REPO_ROOT / "pipeline" / "README.md", REPO_ROOT / "tasks.py"]
    files += sorted((REPO_ROOT / "docs" / "architecture").glob("*.md"))
    files += sorted((REPO_ROOT / ".claude" / "skills").rglob("*.md"))
    files += sorted((REPO_ROOT / "scripts").glob("*.sh"))
    files += [p for p in sorted((REPO_ROOT / "docs" / "plans").glob("*.md")) if p.name != "pipeline-rebuild.md"]
    hits = []
    for path in files:
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "claim-restate" in line and "docs/plans/completed/" not in line and "plans/completed/" not in line:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{n}: {line.strip()[:80]}")
    assert hits == [], hits
