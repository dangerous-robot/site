"""Acceptance tests for RE-AZ (Findings replay): `dr findings --replay [--finding <id>]`.

Written before the implementation (plan ``docs/plans/completed/pipeline-rebuild.md``
§ SP9 (Findings replay), "Tests that prove it"; design
``handoff/2026-10-15-re-az-design.md``). Every case drives behaviour through a
public entry: the ``dr`` CLI under ``CliRunner`` with the agents on scripted
models (``tests/loop_harness.py``), ``loop.run`` wrapped by a spy that
delegates to it, or the public findings writer in ``orchestrator.persistence``.
Nothing here patches a private name under ``pipeline/loop/``.

Shapes pinned here (the design's § 1 and § 2):

- every finding a replay looks at gets one stdout line that starts with
  ``<run_id>: `` followed by ``closed``, ``failed``, ``skipped`` or
  ``not replayed``;
- a replay runs with a new run id and the recorded ``config``; a successful
  replay closes the finding with ``closed: {date, by: replay, note}``; a
  failed one leaves it open and its new finding carries ``replays: <old id>``
  and the original ``command``;
- only ``abandoned`` and ``half-claim`` findings of ``dr draft`` and
  ``dr recheck`` are replayed; the batch replays only the newest finding of a
  ``replays:`` chain and a success closes the whole chain.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from common.frontmatter import parse_frontmatter
from common.utils import slugify
from tests.loop_harness import (
    ENTITY_REF,
    SENTENCE,
    analyst_args,
    auditor_args,
    capturing_model,
    claim_dir,
    failing_model,
    scripted_agents,
    write_entity,
    written_claims,
)

TODAY = datetime.date.today()

# Run ids sort in the opposite order to their dates (see the batch-order
# test), so path order and date order differ.
RUN_OLD = "f0aa000000000000000000000000000a"
RUN_1 = "f1cc000000000000000000000000000c"
RUN_2 = "f1bb000000000000000000000000000b"
RUN_3 = "f1aa000000000000000000000000000a"

CONFIG = {
    "max_sources": 4,
    "candidate_pool_size": 12,
    "max_initial_queries": 3,
    "search_backend": "tavily",
    "research_origins": ["tavily"],
    "model": "test",
    "skip_wayback": True,
}

BATCH = {
    RUN_1: ("2026-10-01", "Probe Subject data centers used more than 4% of US electricity in 2024"),
    RUN_2: ("2026-10-02", "Probe Subject data centers used more than 5% of US electricity in 2024"),
    RUN_3: ("2026-10-03", "Probe Subject data centers used more than 6% of US electricity in 2024"),
}


# --------------------------------------------------------------------------- #
# Fixtures                                                                         #
# --------------------------------------------------------------------------- #


def _write_finding(
    root: Path,
    run_id: str = RUN_OLD,
    *,
    date: str = "2026-10-01",
    statement: str = SENTENCE,
    entity: str = ENTITY_REF,
    command: str = "dr draft",
    outcome: str = "abandoned",
    step: str = "analyse",
    rule: str = "flaw-retry",
    claim_ref: str | None = None,
    closed: dict | None = None,
    replays: str | None = None,
    criteria_slug: str | None = None,
) -> Path:
    """Write a finding through the public writer; ``replays`` is added to the file afterwards.

    ``replays`` is set on the YAML, not on the ``Finding``, so the fixture
    does not depend on the field the implementation adds.
    """
    from common.findings import Finding
    from orchestrator.persistence import write_finding

    finding = Finding(
        run_id=run_id,
        date=datetime.date.fromisoformat(date),
        command=command,
        claim_spec={
            "statement": statement, "entity": entity, "criteria_slug": criteria_slug,
            "topics": [], "grading_rule": None,
        },
        claim_ref=claim_ref,
        config=dict(CONFIG),
        models_used={"researcher": "test", "ingestor": "test", "analyst": "test"},
        step=step,
        rule=rule,
        error={"error_type": "model_error", "message": "scripted failure"},
        attempts=2,
        outcome=outcome,
        closed=closed,
    )
    path = write_finding(finding, root)
    if replays is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["replays"] = replays
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _dr(root: Path, *args: str):
    from orchestrator.cli import main

    return CliRunner().invoke(main, ["--model", "test", *args, "--repo-root", str(root)])


def _replay(root: Path, *args: str):
    return _dr(root, "findings", "--replay", *args)


def _findings(root: Path) -> dict[str, dict]:
    d = root / "research" / "findings"
    if not d.exists():
        return {}
    records = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(d.rglob("*.yaml"))]
    return {r["run_id"]: r for r in records}


def _lines_for(stdout: str, run_id: str) -> list[str]:
    return [line for line in stdout.splitlines() if line.startswith(f"{run_id}: ")]


def _spy_run(monkeypatch, *, raise_on: str | None = None) -> list[tuple]:
    """Wrap ``loop.run``: record (spec, config, sem) per call and delegate, or raise for one statement."""
    import loop

    calls: list[tuple] = []
    real_run = loop.run

    async def _spy(spec, config, *args, **kwargs):
        calls.append((spec, config, kwargs.get("sem")))
        if raise_on is not None and spec.statement == raise_on:
            raise RuntimeError("scripted failure outside the loop's steps")
        return await real_run(spec, config, *args, **kwargs)

    monkeypatch.setattr(loop, "run", _spy)
    return calls


def _tripwire(monkeypatch) -> list[str]:
    import loop

    called: list[str] = []

    async def _run(*args, **kwargs):
        called.append("run")
        raise AssertionError("loop.run must not be called here")

    monkeypatch.setattr(loop, "run", _run)
    return called


def _analyst_failing_on(statement: str) -> FunctionModel:
    """An analyst that answers every claim but raises on the one whose prompt carries ``statement``."""
    args = analyst_args()

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        prompt = "\n".join(
            str(p.content) for m in messages for p in getattr(m, "parts", []) if isinstance(p, UserPromptPart)
        )
        if statement in prompt:
            raise RuntimeError("scripted analyst failure for one claim")
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(_fn)


def _write_claim(
    root: Path,
    stem: str,
    *,
    statement: str = SENTENCE,
    status: str = "draft",
    cadence: int | None = None,
    sidecar: bool = True,
) -> Path:
    """A claim file (and a valid sidecar) under ``research/claims/<ENTITY_REF>/``."""
    write_entity(root)
    fm: dict = {
        "title": statement, "statement": statement, "entity": ENTITY_REF,
        "topics": ["environmental-impact"], "verdict": "mixed", "confidence": "medium",
        "criteria_slug": "probe-criterion", "status": status,
        "as_of": (TODAY - datetime.timedelta(days=90)).isoformat(),
        "sources": ["2026/old"],
    }
    if cadence is not None:
        fm["recheck_cadence_days"] = cadence
    path = claim_dir(root) / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)}---\n\nBody.\n", encoding="utf-8")
    if sidecar:
        reviewed = status in ("published", "archived")
        data = {
            "schema_version": 1,
            "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst", "auditor"]},
            "sources_consulted": [],
            "audit": {
                "analyst_verdict": "mixed", "auditor_verdict": "mixed", "analyst_confidence": "medium",
                "auditor_confidence": "medium", "verdict_agrees": True, "confidence_agrees": True,
                "needs_review": False, "auditor_reasoning": "Agreed.", "evidence_gaps": [],
                "needs_review_reasons": [], "pipeline_verdict": "mixed", "pipeline_confidence": "medium",
                "rule_applied": "agreed",
            },
            "human_review": {
                "reviewed_at": "2026-10-02" if reviewed else None,
                "reviewer": "reviewer@example.org" if reviewed else None,
                "notes": None, "pr_url": None,
            },
        }
        path.with_suffix(".audit.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8",
        )
    return path


def _fm(path: Path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8"))[0]


def _date(value) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


# --------------------------------------------------------------------------- #
# The record                                                                       #
# --------------------------------------------------------------------------- #


def test_the_finding_record_carries_replays_and_reads_it_back(tmp_path) -> None:
    from common.findings import Finding
    from orchestrator.persistence import load_findings, write_finding

    finding = Finding(
        run_id=RUN_1, date=datetime.date(2026, 10, 15), command="dr draft",
        claim_spec={"statement": SENTENCE, "entity": ENTITY_REF, "criteria_slug": None,
                    "topics": [], "grading_rule": None},
        config=dict(CONFIG), step="analyse", rule="flaw-retry",
        error={"error_type": "model_error", "message": "m"}, attempts=2, outcome="abandoned",
        replays=RUN_OLD,
    )
    assert finding.to_dict()["replays"] == RUN_OLD
    path = write_finding(finding, tmp_path)
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["replays"] == RUN_OLD
    (loaded,) = load_findings(tmp_path)
    assert loaded.replays == RUN_OLD
    # A record written before the field existed reads as None.
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    del data["replays"]
    assert Finding.from_dict(data).replays is None


# --------------------------------------------------------------------------- #
# One finding: success, failure                                                    #
# --------------------------------------------------------------------------- #


def test_replay_of_an_abandoned_finding_that_now_succeeds_writes_the_claim_and_closes_the_finding(
    tmp_path, monkeypatch,
) -> None:
    write_entity(tmp_path)
    _write_finding(tmp_path)
    calls = _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 0, result.output
    # The claim lands where the original dr draft would have written it.
    (claim,) = written_claims(tmp_path)
    assert claim == claim_dir(tmp_path) / f"{slugify(SENTENCE)}.md"
    assert claim.with_suffix(".audit.yaml").exists()
    fm = _fm(claim)
    assert fm["status"] == "draft"
    assert fm["statement"] == SENTENCE
    # The run used the recorded claim spec and config, under a new run id.
    ((spec, config, _sem),) = calls
    assert spec.statement == SENTENCE
    assert spec.entity.entity_ref == ENTITY_REF
    assert (config.max_sources, config.candidate_pool_size, config.max_initial_queries) == (4, 12, 3)
    assert config.research_origins == ["tavily"]
    assert config.skip_wayback is True
    assert config.model == "test"
    assert config.run_id != RUN_OLD
    # The finding is closed by the replay; the run itself left no finding.
    records = _findings(tmp_path)
    assert list(records) == [RUN_OLD]
    closed = records[RUN_OLD]["closed"]
    assert closed["by"] == "replay"
    assert _date(closed["date"]) == TODAY
    assert config.run_id in closed["note"]
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: closed"), line

    # dr findings reflects it: nothing open, and --all shows the replay close.
    listing = _dr(tmp_path, "findings")
    assert listing.exit_code == 0, listing.output
    assert RUN_OLD not in listing.stdout
    everything = _dr(tmp_path, "findings", "--all")
    assert RUN_OLD in everything.stdout
    assert "by replay" in everything.stdout


def test_replay_that_fails_again_records_a_new_linked_finding_and_leaves_the_old_one_open(
    tmp_path, monkeypatch,
) -> None:
    write_entity(tmp_path)
    old_path = _write_finding(tmp_path)
    old_bytes = old_path.read_bytes()
    _spy_run(monkeypatch)

    with scripted_agents(analyst_model=failing_model()):
        result = _replay(tmp_path, "--finding", RUN_OLD)

    # A single replay that does not close its finding exits 1.
    assert result.exit_code == 1, result.output
    assert written_claims(tmp_path) == []
    # The old finding is untouched and still open.
    assert old_path.read_bytes() == old_bytes
    records = _findings(tmp_path)
    assert records[RUN_OLD]["closed"] is None
    # One new finding, at its own path, linked to the old one.
    new_ids = [rid for rid in records if rid != RUN_OLD]
    assert len(new_ids) == 1, records
    new = records[new_ids[0]]
    assert new["replays"] == RUN_OLD
    assert new["command"] == "dr draft"
    assert new["outcome"] == "abandoned"
    assert new["claim_spec"]["statement"] == SENTENCE
    assert new["closed"] is None
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: failed"), line
    assert new_ids[0] in line

    # dr findings lists both open findings and names the link.
    listing = _dr(tmp_path, "findings")
    assert listing.exit_code == 0, listing.output
    assert new_ids[0] in listing.stdout and RUN_OLD in listing.stdout
    assert f"replays: {RUN_OLD}" in listing.stdout


# --------------------------------------------------------------------------- #
# The batch                                                                        #
# --------------------------------------------------------------------------- #


def test_replay_without_finding_runs_every_open_finding_in_date_order_and_never_stops_the_batch(
    tmp_path, monkeypatch,
) -> None:
    write_entity(tmp_path)
    for run_id, (date, statement) in BATCH.items():
        _write_finding(tmp_path, run_id, date=date, statement=statement)
    calls = _spy_run(monkeypatch)
    failing = BATCH[RUN_2][1]

    with scripted_agents(analyst_model=_analyst_failing_on(failing)):
        result = _replay(tmp_path)

    # A batch exits 0 unless the command failed to start.
    assert result.exit_code == 0, result.output
    # Date order (RUN_1, RUN_2, RUN_3), not path order (RUN_3 sorts first).
    assert [spec.statement for spec, _c, _s in calls] == [BATCH[r][1] for r in (RUN_1, RUN_2, RUN_3)]
    # One LLM semaphore for the whole batch, and a fresh run id per replay.
    sems = [s for _sp, _c, s in calls]
    assert sems[0] is not None and all(s is sems[0] for s in sems), sems
    assert len({c.run_id for _sp, c, _s in calls} | set(BATCH)) == 6
    records = _findings(tmp_path)
    assert records[RUN_1]["closed"]["by"] == "replay"
    assert records[RUN_3]["closed"]["by"] == "replay"
    assert records[RUN_2]["closed"] is None
    linked = [r for r in records.values() if r.get("replays") == RUN_2]
    assert len(linked) == 1 and linked[0]["outcome"] == "abandoned", records
    statements = {_fm(p)["statement"] for p in written_claims(tmp_path)}
    assert statements == {BATCH[RUN_1][1], BATCH[RUN_3][1]}
    for run_id in BATCH:
        assert len(_lines_for(result.stdout, run_id)) == 1, (run_id, result.stdout)


def test_a_findings_file_error_after_one_replay_does_not_stop_the_batch(tmp_path, monkeypatch) -> None:
    """An OSError while linking or closing findings fails that replay; the next one still runs."""
    import orchestrator.replay as replay_mod

    write_entity(tmp_path)
    for run_id, (date, statement) in BATCH.items():
        _write_finding(tmp_path, run_id, date=date, statement=statement)
    calls = _spy_run(monkeypatch)
    real_link = replay_mod._link

    def _link_failing_once(root, old, config, **kwargs):
        if old.run_id == RUN_1:
            raise PermissionError("findings directory is read-only")
        return real_link(root, old, config, **kwargs)

    monkeypatch.setattr(replay_mod, "_link", _link_failing_once)

    with scripted_agents():
        result = _replay(tmp_path)

    assert result.exit_code == 0, result.output
    assert len(calls) == 3
    assert _lines_for(result.stdout, RUN_1)[0].startswith(f"{RUN_1}: failed"), result.stdout
    assert _lines_for(result.stdout, RUN_2)[0].startswith(f"{RUN_2}: closed"), result.stdout
    assert _lines_for(result.stdout, RUN_3)[0].startswith(f"{RUN_3}: closed"), result.stdout
    records = _findings(tmp_path)
    assert records[RUN_1]["closed"] is None
    assert records[RUN_2]["closed"]["by"] == "replay"


def test_a_batch_replay_whose_run_raises_records_a_linked_finding_and_the_rest_run(tmp_path, monkeypatch) -> None:
    write_entity(tmp_path)
    for run_id, (date, statement) in BATCH.items():
        _write_finding(tmp_path, run_id, date=date, statement=statement)
    calls = _spy_run(monkeypatch, raise_on=BATCH[RUN_2][1])

    with scripted_agents():
        result = _replay(tmp_path)

    assert result.exit_code == 0, result.output
    assert len(calls) == 3
    records = _findings(tmp_path)
    assert records[RUN_1]["closed"] is not None and records[RUN_3]["closed"] is not None
    assert records[RUN_2]["closed"] is None
    (linked,) = [r for r in records.values() if r.get("replays") == RUN_2]
    assert (linked["rule"], linked["outcome"]) == ("replay", "abandoned")
    assert linked["error"]["error_class"] == "RuntimeError"
    assert linked["command"] == "dr draft"
    assert _lines_for(result.stdout, RUN_2)[0].startswith(f"{RUN_2}: failed")


def test_a_closed_finding_is_skipped(tmp_path, monkeypatch) -> None:
    write_entity(tmp_path)
    closed = {"date": datetime.date(2026, 10, 5), "by": "hand", "note": "triaged"}
    closed_path = _write_finding(tmp_path, RUN_1, date="2026-10-01", statement=BATCH[RUN_1][1], closed=closed)
    closed_bytes = closed_path.read_bytes()
    _write_finding(tmp_path, RUN_2, date="2026-10-02", statement=BATCH[RUN_2][1])
    calls = _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path)

    assert result.exit_code == 0, result.output
    assert [spec.statement for spec, _c, _s in calls] == [BATCH[RUN_2][1]]
    assert closed_path.read_bytes() == closed_bytes
    assert _findings(tmp_path)[RUN_2]["closed"]["by"] == "replay"


def test_replay_of_a_named_closed_finding_is_refused_before_any_run(tmp_path, monkeypatch) -> None:
    write_entity(tmp_path)
    closed = {"date": datetime.date(2026, 10, 5), "by": "hand", "note": "triaged"}
    path = _write_finding(tmp_path, closed=closed)
    before = path.read_bytes()
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 1, result.output
    assert "already closed" in result.output
    assert called == []
    assert path.read_bytes() == before


def test_replay_of_an_unknown_finding_id_is_an_error(tmp_path, monkeypatch) -> None:
    write_entity(tmp_path)
    _write_finding(tmp_path)
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path, "--finding", "deadbeef")

    assert result.exit_code == 1, result.output
    assert "no finding with id deadbeef" in result.output
    assert called == []


def test_a_replay_chain_runs_once_and_a_success_closes_every_finding_in_it(tmp_path, monkeypatch) -> None:
    """A failed replay leaves two open findings for one claim; the next batch runs it once."""
    write_entity(tmp_path)
    _write_finding(tmp_path, RUN_1, date="2026-10-01")
    _write_finding(tmp_path, RUN_2, date="2026-10-02", replays=RUN_1)
    calls = _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path)

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    records = _findings(tmp_path)
    assert records[RUN_1]["closed"]["by"] == "replay"
    assert records[RUN_2]["closed"]["by"] == "replay"
    assert len(written_claims(tmp_path)) == 1


def test_replay_of_a_superseded_finding_runs_the_newest_and_closes_the_whole_chain(tmp_path, monkeypatch) -> None:
    """--finding on an older finding of a chain replays through the newest, so none is left open."""
    write_entity(tmp_path)
    _write_finding(tmp_path, RUN_1, date="2026-10-01")
    _write_finding(tmp_path, RUN_2, date="2026-10-02", replays=RUN_1)
    calls = _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_1)

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    records = _findings(tmp_path)
    assert records[RUN_1]["closed"]["by"] == "replay"
    assert records[RUN_2]["closed"]["by"] == "replay"
    assert _lines_for(result.stdout, RUN_2)[0].startswith(f"{RUN_2}: closed"), result.stdout
    assert _lines_for(result.stdout, RUN_1) == [f"{RUN_1}: closed (through {RUN_2})"]


# --------------------------------------------------------------------------- #
# What a replay writes, and what it does not replay                                #
# --------------------------------------------------------------------------- #


def test_replay_of_a_recheck_finding_writes_a_pending_draft_and_leaves_the_live_claim_alone(
    tmp_path, monkeypatch,
) -> None:
    live = _write_claim(tmp_path, "live-claim", status="published", cadence=45)
    live_before = (live.read_bytes(), live.with_suffix(".audit.yaml").read_bytes())
    ref = f"{ENTITY_REF}/live-claim"
    _write_finding(
        tmp_path, command="dr recheck", claim_ref=ref, step="research", rule="config-fatal",
    )
    calls = _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 0, result.output
    pending = tmp_path / "research" / "pending" / ENTITY_REF / "live-claim.md"
    assert pending.exists() and pending.with_suffix(".audit.yaml").exists()
    assert (live.read_bytes(), live.with_suffix(".audit.yaml").read_bytes()) == live_before
    # The recheck's cadence comes from the live claim, as dr recheck sets it.
    ((_spec, config, _sem),) = calls
    assert config.refetch_cached_older_than_days == 45
    assert _findings(tmp_path)[RUN_OLD]["closed"]["by"] == "replay"
    # No draft was written over the live path.
    assert [p.name for p in written_claims(tmp_path)] == ["live-claim.md"]


def test_replay_of_a_recheck_finding_grades_the_live_claim_with_its_criterion_rule(
    tmp_path, monkeypatch,
) -> None:
    """A recheck finding that could not start records no grading rule and may hold an old statement.

    The replay builds its spec from the live claim, as ``dr recheck --claim``
    does, so the criterion's grading rule reaches the analyst and the
    Evaluator and the claim's current statement is the one graded.
    """
    rule = "RULE-SENTINEL: mixed means offsets only"
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research" / "templates.yaml").write_text(
        "templates:\n"
        "  - slug: probe-criterion\n"
        '    text: "ENTITY data centers used more than 4% of US electricity in 2024"\n'
        "    entity_type: subject\n"
        f"    subjects: [{ENTITY_REF}]\n"
        "    topics: [environmental-impact]\n"
        "    core: true\n"
        f'    grading_rule: "{rule}"\n',
        encoding="utf-8",
    )
    _write_claim(tmp_path, "live-claim", status="published")
    _write_finding(
        tmp_path, command="dr recheck", claim_ref=f"{ENTITY_REF}/live-claim",
        statement="An older wording of the claim", step="research", rule="config-fatal",
    )
    assert _findings(tmp_path)[RUN_OLD]["claim_spec"]["grading_rule"] is None
    calls = _spy_run(monkeypatch)
    analyst_prompts: list[str] = []
    auditor_prompts: list[str] = []

    with scripted_agents(
        analyst_model=capturing_model(analyst_prompts, analyst_args()),
        auditor_model=capturing_model(auditor_prompts, auditor_args()),
    ):
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 0, result.output
    ((spec, _config, _sem),) = calls
    assert spec.statement == SENTENCE
    assert spec.grading_rule == rule
    assert spec.topics == ["environmental-impact"]
    assert analyst_prompts and any(rule in p for p in analyst_prompts)
    assert auditor_prompts and any(rule in p for p in auditor_prompts)
    assert _findings(tmp_path)[RUN_OLD]["closed"]["by"] == "replay"


def test_replay_of_a_draft_rerun_finding_rewrites_the_draft_in_place(tmp_path, monkeypatch) -> None:
    """An abandoned dr draft --claim <ref> --force recorded claim_ref; the replay writes back to that path."""
    stem = "a-stem-that-is-not-the-statement-slug"
    existing = _write_claim(tmp_path, stem, status="draft")
    _write_finding(tmp_path, claim_ref=f"{ENTITY_REF}/{stem}")
    _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 0, result.output
    assert written_claims(tmp_path) == [existing]
    assert existing.read_text(encoding="utf-8") != ""
    sidecar = yaml.safe_load(existing.with_suffix(".audit.yaml").read_text(encoding="utf-8"))
    # The rerun replaced the stub sidecar with the run's own.
    assert sidecar["pipeline_run"]["ran_at"] != "2026-10-01T00:00:00+00:00"
    assert _findings(tmp_path)[RUN_OLD]["closed"]["by"] == "replay"


def test_replay_of_a_half_claim_finding_writes_the_missing_sidecar_in_place(tmp_path, monkeypatch) -> None:
    """A writer crash between claim and sidecar: the replay is dr draft --claim <ref> --force."""
    stem = slugify(SENTENCE)
    claim = _write_claim(tmp_path, stem, status="draft", sidecar=False)
    _write_finding(
        tmp_path, outcome="half-claim", step="write", rule="half-claim", claim_ref=f"{ENTITY_REF}/{stem}",
    )
    _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 0, result.output
    assert written_claims(tmp_path) == [claim]
    assert claim.with_suffix(".audit.yaml").exists()
    assert _fm(claim)["status"] == "draft"
    assert _findings(tmp_path)[RUN_OLD]["closed"]["by"] == "replay"


def test_replay_of_a_half_claim_finding_whose_claim_file_was_never_written_writes_it(tmp_path, monkeypatch) -> None:
    """dr draft records claim_ref from the planned path even when the writer died before the claim file."""
    write_entity(tmp_path)
    stem = slugify(SENTENCE)
    _write_finding(
        tmp_path, outcome="half-claim", step="write", rule="half-claim", claim_ref=f"{ENTITY_REF}/{stem}",
    )
    _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 0, result.output
    (claim,) = written_claims(tmp_path)
    assert claim == claim_dir(tmp_path) / f"{stem}.md"
    assert claim.with_suffix(".audit.yaml").exists()
    assert _findings(tmp_path)[RUN_OLD]["closed"]["by"] == "replay"


def test_replay_of_a_draft_finding_whose_claim_is_now_published_is_not_replayed(tmp_path, monkeypatch) -> None:
    live = _write_claim(tmp_path, "live-claim", status="published")
    before = (live.read_bytes(), live.with_suffix(".audit.yaml").read_bytes())
    ref = f"{ENTITY_REF}/live-claim"
    _write_finding(tmp_path, claim_ref=ref)
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path)

    assert result.exit_code == 0, result.output
    assert called == []
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: not replayed"), line
    assert f"dr recheck --claim {ref}" in line
    assert (live.read_bytes(), live.with_suffix(".audit.yaml").read_bytes()) == before
    assert list(_findings(tmp_path)) == [RUN_OLD]
    assert not (tmp_path / "research" / "pending").exists()


def test_a_draft_finding_whose_claim_file_now_exists_is_not_replayed_and_writes_no_finding(
    tmp_path, monkeypatch,
) -> None:
    existing = _write_claim(tmp_path, slugify(SENTENCE), status="draft")
    before = existing.read_bytes()
    _write_finding(tmp_path)
    called = _tripwire(monkeypatch)

    batch = _replay(tmp_path)
    single = _replay(tmp_path, "--finding", RUN_OLD)

    assert batch.exit_code == 0, batch.output
    assert single.exit_code == 1, single.output
    assert called == []
    (line,) = _lines_for(batch.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: not replayed"), line
    assert existing.read_bytes() == before
    records = _findings(tmp_path)
    assert list(records) == [RUN_OLD] and records[RUN_OLD]["closed"] is None


def test_replay_of_a_subject_finding_without_an_entity_file_writes_the_subject_record_with_the_claim(
    tmp_path, monkeypatch,
) -> None:
    """Only dr draft --subject runs on a subject with no file, so the replay writes the record as it would."""
    ref = "subjects/probe-replay"
    _write_finding(tmp_path, entity=ref)
    _spy_run(monkeypatch)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 0, result.output
    record = tmp_path / "research" / "entities" / "subjects" / "probe-replay.md"
    assert record.exists()
    assert _fm(record)["type"] == "subject"
    (claim,) = written_claims(tmp_path, ref)
    assert claim.name == f"{slugify(SENTENCE)}.md"
    assert _findings(tmp_path)[RUN_OLD]["closed"]["by"] == "replay"


def test_a_product_finding_without_an_entity_file_is_not_replayed(tmp_path, monkeypatch) -> None:
    _write_finding(tmp_path, entity="products/no-such-product")
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path)

    assert result.exit_code == 0, result.output
    assert called == []
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: not replayed"), line
    assert list(_findings(tmp_path)) == [RUN_OLD]


@pytest.mark.parametrize(
    "outcome, command",
    [
        ("split", "dr draft"),
        ("recovered", "dr draft"),
        ("partial", "dr draft"),
        ("abandoned", "dr draft --rerun evaluator"),
        ("half-claim", "dr draft --rerun analyst"),
        ("abandoned", "dr step-audit"),
    ],
)
def test_findings_a_replay_cannot_reproduce_are_skipped_and_stay_open(
    tmp_path, monkeypatch, outcome, command,
) -> None:
    write_entity(tmp_path)
    path = _write_finding(tmp_path, outcome=outcome, command=command, claim_ref=f"{ENTITY_REF}/some-claim")
    before = path.read_bytes()
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path)

    assert result.exit_code == 0, result.output
    assert called == []
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: skipped"), line
    assert path.read_bytes() == before


def test_a_failed_recheck_replay_records_a_linked_recheck_finding_and_writes_no_pending_draft(
    tmp_path, monkeypatch,
) -> None:
    live = _write_claim(tmp_path, "live-claim", status="published", cadence=45)
    live_before = (live.read_bytes(), live.with_suffix(".audit.yaml").read_bytes())
    ref = f"{ENTITY_REF}/live-claim"
    old_path = _write_finding(tmp_path, command="dr recheck", claim_ref=ref, step="research", rule="config-fatal")
    old_bytes = old_path.read_bytes()
    _spy_run(monkeypatch)

    with scripted_agents(analyst_model=failing_model()):
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 1, result.output
    assert not (tmp_path / "research" / "pending").exists()
    assert (live.read_bytes(), live.with_suffix(".audit.yaml").read_bytes()) == live_before
    assert old_path.read_bytes() == old_bytes
    records = _findings(tmp_path)
    (new,) = [r for r in records.values() if r["run_id"] != RUN_OLD]
    assert (new["replays"], new["command"], new["claim_ref"]) == (RUN_OLD, "dr recheck", ref)
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line == f"{RUN_OLD}: failed (finding {new['run_id']})"


def test_a_replay_whose_write_finds_the_path_taken_records_a_write_step_finding(tmp_path, monkeypatch) -> None:
    """The loop returned but nothing was written and no finding recorded: the replay records one at the write step."""
    import orchestrator.persistence as persistence

    write_entity(tmp_path)
    _write_finding(tmp_path)
    _spy_run(monkeypatch)

    def _taken(*args, **kwargs):
        raise FileExistsError("claim file already exists")

    monkeypatch.setattr(persistence, "write_claim_run", _taken)

    with scripted_agents():
        result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 1, result.output
    assert written_claims(tmp_path) == []
    records = _findings(tmp_path)
    assert records[RUN_OLD]["closed"] is None
    (new,) = [r for r in records.values() if r["run_id"] != RUN_OLD]
    assert (new["replays"], new["rule"], new["step"], new["outcome"]) == (RUN_OLD, "replay", "write", "abandoned")
    assert new["error"]["error_type"] == "run_failed"


@pytest.mark.parametrize(
    "slug, reason",
    [
        ("no-such-criterion", "no active criterion"),
        ("probe-criterion", "does not list subjects/probe-subject"),
    ],
)
def test_a_criterion_draft_finding_the_criterion_no_longer_allows_is_not_replayed(
    tmp_path, monkeypatch, slug, reason,
) -> None:
    """dr draft --criterion checks the criterion before any model call; a replay makes the same checks."""
    write_entity(tmp_path)
    templates = {
        "templates": [{
            "slug": "probe-criterion", "text": "SUBJECT is a probe", "entity_type": "subject",
            "topics": ["environmental-impact"], "core": True, "subjects": ["subjects/other-subject"],
        }],
    }
    (tmp_path / "research" / "templates.yaml").write_text(yaml.safe_dump(templates), encoding="utf-8")
    _write_finding(tmp_path, criteria_slug=slug)
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 1, result.output
    assert called == []
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: not replayed: criterion {slug}"), line
    assert reason in line
    assert written_claims(tmp_path) == []
    assert list(_findings(tmp_path)) == [RUN_OLD]


@pytest.mark.parametrize("entity", ["companies/probe-co", "products/../Companies/probe-co"])
def test_a_draft_finding_on_a_company_is_not_replayed(tmp_path, monkeypatch, entity) -> None:
    """dr draft refuses a company in every mode RE-AY (Companies out), so its replay does too."""
    from orchestrator.cli import _COMPANY_REFUSAL

    write_entity(tmp_path, "companies/probe-co", "Probe Co")
    write_entity(tmp_path, "products/probe-product", "Probe Product")
    _write_finding(tmp_path, entity=entity, statement="Probe Co publishes an annual energy report")
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 1, result.output
    assert called == []
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line == f"{RUN_OLD}: not replayed: {_COMPANY_REFUSAL}", line
    assert written_claims(tmp_path) == []
    assert list(_findings(tmp_path)) == [RUN_OLD]


def test_a_criterion_draft_finding_whose_criterion_is_now_inactive_is_not_replayed(tmp_path, monkeypatch) -> None:
    """dr draft --criterion takes active criteria only; ``inactive: true`` keeps one loadable by slug."""
    write_entity(tmp_path)
    templates = {
        "templates": [{
            "slug": "probe-criterion", "text": "SUBJECT is a probe", "entity_type": "subject",
            "topics": ["environmental-impact"], "core": True, "subjects": [ENTITY_REF], "inactive": True,
        }],
    }
    (tmp_path / "research" / "templates.yaml").write_text(yaml.safe_dump(templates), encoding="utf-8")
    _write_finding(tmp_path, criteria_slug="probe-criterion")
    called = _tripwire(monkeypatch)

    result = _replay(tmp_path, "--finding", RUN_OLD)

    assert result.exit_code == 1, result.output
    assert called == []
    (line,) = _lines_for(result.stdout, RUN_OLD)
    assert line.startswith(f"{RUN_OLD}: not replayed: criterion probe-criterion"), line
    assert "no active criterion" in line
    assert written_claims(tmp_path) == []


# --------------------------------------------------------------------------- #
# Grammar                                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "args, message",
    [
        (["--finding", RUN_OLD], "--finding goes with --replay"),
        (["--replay", "--summary"], "--replay cannot be combined"),
        (["--replay", "--all"], "--replay cannot be combined"),
        (["--replay", "--close", RUN_OLD, "--note", "x"], "--replay cannot be combined"),
    ],
)
def test_replay_grammar_is_checked_before_any_run(tmp_path, monkeypatch, args, message) -> None:
    write_entity(tmp_path)
    path = _write_finding(tmp_path)
    before = path.read_bytes()
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, "findings", *args)

    assert result.exit_code == 2, result.output
    assert message in result.output
    assert called == []
    assert path.read_bytes() == before


def test_dr_findings_help_names_replay() -> None:
    from orchestrator.cli import main

    result = CliRunner().invoke(main, ["findings", "--help"])
    assert result.exit_code == 0, result.output
    assert "--replay" in result.output and "--finding" in result.output
