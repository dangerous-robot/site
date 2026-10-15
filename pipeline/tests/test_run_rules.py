"""Acceptance tests for RE-AT (Rules, findings file, tie-breaker): the run rules.

Written before the implementation (plan ``docs/plans/completed/pipeline-rebuild.md``
§ SP2 (Rules, findings file, tie-breaker), "Tests that prove it"). Every case
drives behaviour through a public entry: ``loop.run`` or ``loop.rerun`` with
the agents on scripted models (``tests/loop_harness.py``), the ``dr`` CLI under
``CliRunner``, or a public writer function. Nothing here patches a private
name under ``pipeline/loop/``; the two writer crashes patch private names in
``orchestrator/persistence.py``, as the RE-AR acceptance test does.

Covered:

- the error policy table: every ``StepError`` literal maps to one rule; the
  per-step rule on exhaustion (``tiebreak`` abandons, ``restate`` is partial,
  ``write`` is a half-claim);
- a flaw at the analyst step retries N(flaw) times with the research and
  ingest outputs kept, then abandons with nothing on disk and one finding;
- a recovered retry writes the claim and a finding with ``outcome: recovered``;
- a transport error retries with backoff N(transport) times; ``api_key_missing``
  and ``all_blocked`` abandon at once;
- the threshold cases carried from the RE-AR review (three sources is below
  the line, four is not; the terminal-fetch histogram; every page timing out
  is a transport failure, not a flaw);
- ``dr draft --dry-run`` prints the finding and writes nothing; an abandoned
  ``dr draft`` writes only the finding;
- a writer crash leaves a half-claim finding and ``dr findings`` lists the
  half-claim (and a subject record with no claim) without deleting anything;
- an unexpected exception is a finding, never a traceback;
- ``run`` and ``rerun`` take no checkpoint; ``checkpoints.py`` and
  ``--interactive`` are gone; the loop carries no old-path names.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from pydantic_ai.exceptions import UnexpectedModelBehavior

from common.models import BlockedReason
from tests.loop_harness import (
    ENTITY_REF,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    claim_dir,
    claim_spec,
    counting_ingest_model,
    counting_search,
    failing_model,
    flaky_model,
    loop_config,
    scorer_args,
    scripted_agents,
    write_entity,
    written_claims,
    written_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
LOOP_DIR = PIPELINE_DIR / "loop"

INVALID_OUTPUT = UnexpectedModelBehavior("Exceeded maximum retries (2) for output validation")
NULL_BODY = UnexpectedModelBehavior("Invalid response from openai chat completions endpoint: 4 validation errors")


def _config(tmp_path, **overrides):
    """The harness config with no transport backoff, so retry cases run fast."""
    overrides.setdefault("transport_backoff_s", (0.0, 0.0))
    return loop_config(tmp_path, **overrides)


async def _run(tmp_path, **config_overrides):
    import loop

    return await loop.run(claim_spec(tmp_path), _config(tmp_path, **config_overrides))


def _draft(tmp_path, *extra: str, dry_run: bool = False, sentence: str = SENTENCE, mode=("--entity", ENTITY_REF)):
    from orchestrator.cli import main

    # Every agent named on the command line, so a developer's .env (DR_*_MODEL) cannot leak in.
    agents = [f"--{a}-model" for a in ("researcher", "analyst", "auditor", "ingestor", "tiebreaker")]
    models = [x for flag in agents for x in (flag, "test")]
    args = ["--model", "test", *models, "draft", *mode, sentence, "--skip-wayback", "--repo-root", str(tmp_path)]
    if dry_run:
        args.insert(args.index("draft") + 1, "--dry-run")
    return CliRunner().invoke(main, [*args, *extra])


def _findings(tmp_path) -> list[Path]:
    d = tmp_path / "research" / "findings"
    return sorted(d.rglob("*.yaml")) if d.exists() else []


def _one_finding(tmp_path) -> dict:
    files = _findings(tmp_path)
    assert len(files) == 1, f"expected one finding file, found {files}"
    return yaml.safe_load(files[0].read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# The error policy table                                                         #
# --------------------------------------------------------------------------- #


def test_error_policy_maps_every_step_error_literal_to_exactly_one_rule() -> None:
    from loop import ERROR_POLICY, Rule, rule_for
    from tests.test_step_error_vocab import DOCUMENTED_LITERALS

    missing = sorted(lit for lit in DOCUMENTED_LITERALS if lit not in ERROR_POLICY)
    assert missing == [], f"StepError literals with no policy row: {missing}"
    assert "http_" in ERROR_POLICY, "the http_{status} pattern needs a row"
    assert all(isinstance(rule, Rule) for rule in ERROR_POLICY.values())

    flaws = {
        "no_queries", "no_results", "scorer_dropped_all", "model_error", "invalid_output",
        "insufficient_sources", "terminal_fetch_error", "fetch_failed", "invalid_source",
        "blocked_host",
    }
    transport = {
        "timeout", "http_error", "rate_limited", "null_body", "sources_unreachable",
        "tavily_rate_limited", "wayback_unavailable", "edgar_rate_limited",
    }
    fatal = {"api_key_missing", "all_blocked", "edgar_ua_missing"}
    for literal in flaws:
        assert rule_for(literal) is Rule.FLAW_RETRY, literal
    for literal in transport:
        assert rule_for(literal) is Rule.TRANSPORT_RETRY, literal
    for literal in fatal:
        assert rule_for(literal) is Rule.CONFIG_FATAL, literal
    assert rule_for("write_failed") is Rule.HALF_CLAIM
    assert rule_for("verdict_split") is Rule.TIEBREAKER
    # The http_{status} pattern: a rate limit is transport, any other status a flaw.
    assert rule_for("http_429") is Rule.TRANSPORT_RETRY
    assert rule_for("http_403") is Rule.FLAW_RETRY
    with pytest.raises(KeyError):
        rule_for("not_a_literal")


def test_rules_and_outcomes_are_the_findings_file_vocabulary() -> None:
    from common.findings import OUTCOMES, RULES, STEPS
    from loop import Rule

    assert set(RULES) == {"flaw-retry", "transport-retry", "config-fatal", "half-claim", "tiebreaker", "replay"}
    assert set(OUTCOMES) == {"recovered", "abandoned", "split", "half-claim", "partial"}
    assert STEPS == ("research", "ingest", "analyse", "evaluate", "tiebreak", "restate", "write")
    assert {rule.value for rule in Rule} <= set(RULES)


def test_step_exhaustion_rows_name_tiebreak_as_abandon_and_restate_as_partial() -> None:
    from common.findings import OUTCOMES, STEPS
    from loop import STEP_ON_EXHAUSTION

    assert set(STEP_ON_EXHAUSTION) == set(STEPS)
    assert STEP_ON_EXHAUSTION["tiebreak"] == "abandoned"
    assert STEP_ON_EXHAUSTION["restate"] == "partial"
    assert STEP_ON_EXHAUSTION["write"] == "half-claim"
    for step in ("research", "ingest", "analyse", "evaluate"):
        assert STEP_ON_EXHAUSTION[step] == "abandoned"
    assert set(STEP_ON_EXHAUSTION.values()) <= set(OUTCOMES)


def test_exception_classes_map_to_the_vocabulary() -> None:
    import httpx

    from loop import Rule, classify_exception

    assert classify_exception(asyncio.TimeoutError()) == ("timeout", Rule.TRANSPORT_RETRY)
    assert classify_exception(httpx.ReadTimeout("slow")) == ("timeout", Rule.TRANSPORT_RETRY)
    assert classify_exception(httpx.ConnectError("down")) == ("http_error", Rule.TRANSPORT_RETRY)
    assert classify_exception(NULL_BODY) == ("null_body", Rule.TRANSPORT_RETRY)
    assert classify_exception(INVALID_OUTPUT) == ("invalid_output", Rule.FLAW_RETRY)
    assert classify_exception(RuntimeError("GreenPT provider requires GREENPT_API_KEY")) == (
        "api_key_missing", Rule.CONFIG_FATAL,
    )
    assert classify_exception(KeyError("boom")) == ("model_error", Rule.FLAW_RETRY)


def test_retry_counts_default_to_the_q_b4_policy() -> None:
    from loop import VerifyConfig

    cfg = VerifyConfig(model="test")
    assert cfg.flaw_retries == 1
    assert cfg.transport_retries == 2
    assert len(cfg.transport_backoff_s) == cfg.transport_retries


# --------------------------------------------------------------------------- #
# Flaw at the analyst: retry once with research and ingest kept, then abandon   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_analyst_flaw_retries_once_keeping_research_and_ingest_then_abandons(tmp_path) -> None:
    write_entity(tmp_path)
    searches: list[str] = []
    ingests: list[str] = []
    analyst_calls: list[str] = []

    with scripted_agents(
        analyst_model=failing_model(INVALID_OUTPUT, calls=analyst_calls),
        ingestor=counting_ingest_model(ingests),
        search=counting_search(calls=searches),
    ):
        result = await _run(tmp_path)

    assert analyst_calls == ["run", "run"], "N(flaw) = 1: the analyst step runs twice"
    assert searches == ["search"], "research is kept in memory, not re-run"
    assert len(ingests) == len(URLS), "ingest is kept in memory, not re-run"
    assert result.analyst_output is None
    assert result.blocked_reason == BlockedReason.ANALYST_ERROR
    finding = result.finding
    assert finding is not None
    assert finding.outcome == "abandoned"
    assert finding.step == "analyse"
    assert finding.rule == "flaw-retry"
    assert finding.attempts == 2
    assert finding.error["error_type"] == "invalid_output"
    assert finding.claim_spec["statement"] == SENTENCE
    assert finding.claim_spec["entity"] == ENTITY_REF
    assert finding.models_used["analyst"] == "test"
    assert finding.run_id == _config(tmp_path).run_id or len(finding.run_id) == 32


@pytest.mark.asyncio
async def test_flaw_retry_count_is_configurable(tmp_path) -> None:
    write_entity(tmp_path)
    analyst_calls: list[str] = []
    with scripted_agents(analyst_model=failing_model(INVALID_OUTPUT, calls=analyst_calls)):
        result = await _run(tmp_path, flaw_retries=0)
    assert analyst_calls == ["run"]
    assert result.finding.attempts == 1


def test_recovered_retry_writes_the_claim_and_a_recovered_finding(tmp_path) -> None:
    write_entity(tmp_path)
    analyst_calls: list[str] = []

    with scripted_agents(
        analyst_model=flaky_model(analyst_args(), fail_times=1, exc=INVALID_OUTPUT, calls=analyst_calls),
    ):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    assert analyst_calls == ["run", "run"]
    claims = written_claims(tmp_path)
    assert len(claims) == 1
    sidecar = yaml.safe_load(claims[0].with_suffix(".audit.yaml").read_text(encoding="utf-8"))
    finding = _one_finding(tmp_path)
    assert finding["outcome"] == "recovered"
    assert finding["step"] == "analyse"
    assert finding["rule"] == "flaw-retry"
    assert finding["attempts"] == 2
    assert finding["command"] == "dr draft"
    assert finding["run_id"] == sidecar["pipeline_run"]["run_id"]
    assert _findings(tmp_path)[0].name == f"{finding['run_id']}.yaml"
    assert finding["claim_ref"], "a written claim is named on its finding"
    assert "recovered" in result.output


# --------------------------------------------------------------------------- #
# Transport errors retry with backoff; configuration errors abandon at once      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("transport_retries", [2, 0])
async def test_transport_error_retries_with_backoff_then_abandons(tmp_path, caplog, transport_retries) -> None:
    import logging

    write_entity(tmp_path)
    analyst_calls: list[str] = []
    with (
        scripted_agents(analyst_model=failing_model(asyncio.TimeoutError(), calls=analyst_calls)),
        caplog.at_level(logging.WARNING),
    ):
        result = await _run(tmp_path, transport_retries=transport_retries,
                            transport_backoff_s=(0.0,) * transport_retries)

    assert len(analyst_calls) == transport_retries + 1
    finding = result.finding
    assert finding.outcome == "abandoned"
    assert finding.rule == "transport-retry"
    assert finding.error["error_type"] == "timeout"
    assert finding.attempts == transport_retries + 1
    retry_lines = [r.getMessage() for r in caplog.records if "retry" in r.getMessage().lower()]
    assert len(retry_lines) == transport_retries, retry_lines


@pytest.mark.asyncio
async def test_null_body_is_a_transport_error(tmp_path) -> None:
    write_entity(tmp_path)
    analyst_calls: list[str] = []
    with scripted_agents(analyst_model=failing_model(NULL_BODY, calls=analyst_calls)):
        result = await _run(tmp_path)
    assert len(analyst_calls) == 3
    assert result.finding.error["error_type"] == "null_body"
    assert result.finding.rule == "transport-retry"


@pytest.mark.asyncio
async def test_api_key_missing_abandons_at_once(tmp_path) -> None:
    write_entity(tmp_path)
    analyst_calls: list[str] = []
    exc = RuntimeError("GreenPT provider requires GREENPT_API_KEY")
    with scripted_agents(analyst_model=failing_model(exc, calls=analyst_calls)):
        result = await _run(tmp_path)
    assert analyst_calls == ["run"]
    finding = result.finding
    assert finding.outcome == "abandoned"
    assert finding.rule == "config-fatal"
    assert finding.error["error_type"] == "api_key_missing"
    assert finding.attempts == 1


@pytest.mark.asyncio
async def test_all_blocked_abandons_at_once(tmp_path) -> None:
    write_entity(tmp_path)
    (tmp_path / "research" / "blocklist.yaml").write_text(
        "hosts:\n  - host: example.org\n    reason: test\n", encoding="utf-8",
    )
    searches: list[str] = []
    with scripted_agents(search=counting_search(calls=searches)):
        result = await _run(tmp_path)
    assert searches == ["search"], "config-fatal: no retry"
    finding = result.finding
    assert finding.outcome == "abandoned"
    assert finding.step == "research"
    assert finding.rule == "config-fatal"
    assert finding.error["error_type"] == "all_blocked"
    assert finding.attempts == 1
    assert result.analyst_output is None


@pytest.mark.asyncio
async def test_scorer_dropping_everything_is_a_flaw_retried_once(tmp_path) -> None:
    write_entity(tmp_path)
    searches: list[str] = []
    with scripted_agents(scorer=scorer_args(kept=False), search=counting_search(calls=searches)):
        result = await _run(tmp_path)
    assert searches == ["search", "search"]
    assert result.finding.step == "research"
    assert result.finding.error["error_type"] == "scorer_dropped_all"
    assert result.finding.rule == "flaw-retry"
    assert result.finding.attempts == 2
    assert result.blocked_reason == BlockedReason.INSUFFICIENT_SOURCES


# --------------------------------------------------------------------------- #
# Threshold cases carried from the RE-AR review (finding E)                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_three_usable_sources_is_below_the_line_and_retries_ingest_only(tmp_path) -> None:
    from tests.loop_harness import fake_execute_searches

    write_entity(tmp_path)
    three = URLS[:3]
    searches: list[str] = []
    ingests: list[str] = []
    inner = fake_execute_searches(three)

    async def _search(queries, client, **kwargs):
        searches.append("search")
        return await inner(queries, client, **kwargs)

    with scripted_agents(scorer=scorer_args(three), search=_search, ingestor=counting_ingest_model(ingests)):
        result = await _run(tmp_path)

    assert searches == ["search"], "the research output is kept"
    assert len(ingests) == 2 * len(three), "the ingest step ran twice over the same three URLs"
    assert result.blocked_reason == BlockedReason.INSUFFICIENT_SOURCES
    assert result.analyst_output is None
    finding = result.finding
    assert finding.step == "ingest"
    assert finding.error["error_type"] == "insufficient_sources"
    assert "3 usable" in finding.error["message"] and "4" in finding.error["message"]
    assert finding.rule == "flaw-retry"
    assert finding.attempts == 2


@pytest.mark.asyncio
async def test_four_usable_sources_reach_the_analyst_with_no_finding(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents():
        result = await _run(tmp_path)
    assert result.analyst_output is not None
    assert result.consistency is not None
    assert result.finding is None
    assert result.blocked_reason is None


@pytest.mark.asyncio
async def test_every_fetch_refused_is_a_terminal_fetch_block_with_the_histogram(tmp_path) -> None:
    import httpx
    import respx

    from tests.loop_harness import fake_execute_searches

    write_entity(tmp_path)
    with scripted_agents(search=fake_execute_searches(URLS, {})), respx.mock as mock:
        for url in URLS:
            mock.get(url).mock(return_value=httpx.Response(403))
        result = await _run(tmp_path)

    assert result.blocked_reason == BlockedReason.TERMINAL_FETCH_ERROR
    finding = result.finding
    assert finding.step == "ingest"
    assert finding.error["error_type"] == "terminal_fetch_error"
    assert "4 URLs (4× http_403)" in finding.error["message"]
    assert finding.rule == "flaw-retry"
    assert finding.attempts == 2


@pytest.mark.asyncio
async def test_every_page_timing_out_is_a_transport_failure_of_the_ingest_step(tmp_path) -> None:
    write_entity(tmp_path)
    ingests: list[str] = []
    with scripted_agents(ingestor=counting_ingest_model(ingests, fail=asyncio.TimeoutError())):
        result = await _run(tmp_path, transport_retries=1, transport_backoff_s=(0.0,))

    assert len(ingests) == 2 * len(URLS)
    finding = result.finding
    assert finding.step == "ingest"
    assert finding.error["error_type"] == "sources_unreachable"
    assert finding.rule == "transport-retry"
    assert finding.attempts == 2
    assert result.blocked_reason == BlockedReason.INSUFFICIENT_SOURCES


# --------------------------------------------------------------------------- #
# dr draft: the finding on disk, the dry run, the abandoned run                   #
# --------------------------------------------------------------------------- #


def test_dry_run_prints_the_finding_and_writes_nothing(tmp_path) -> None:
    from tests.loop_harness import fake_execute_searches

    write_entity(tmp_path)
    three = URLS[:3]
    with scripted_agents(scorer=scorer_args(three), search=fake_execute_searches(three)):
        result = _draft(tmp_path, dry_run=True)

    assert "abandoned" in result.output
    assert "insufficient_sources" in result.output
    assert _findings(tmp_path) == []
    assert written_claims(tmp_path) == []
    assert written_sources(tmp_path) == []


def test_abandoned_draft_writes_only_the_finding(tmp_path) -> None:
    from tests.loop_harness import fake_execute_searches

    write_entity(tmp_path)
    three = URLS[:3]
    with scripted_agents(scorer=scorer_args(three), search=fake_execute_searches(three)):
        result = _draft(tmp_path, "--max-sources", "3", "--candidate-pool-size", "6")

    assert result.exit_code == 1, result.output
    assert written_claims(tmp_path) == []
    assert written_sources(tmp_path) == []
    finding = _one_finding(tmp_path)
    assert finding["outcome"] == "abandoned"
    assert finding["command"] == "dr draft"
    assert finding["step"] == "ingest"
    assert finding["rule"] == "flaw-retry"
    assert finding["claim_ref"] is None
    assert finding["claim_spec"] == {
        "statement": SENTENCE, "entity": ENTITY_REF, "criteria_slug": None, "topics": [], "grading_rule": None,
    }
    assert finding["config"]["max_sources"] == 3
    assert finding["config"]["candidate_pool_size"] == 6
    assert finding["config"]["skip_wayback"] is True
    assert set(finding["config"]) >= {
        "max_sources", "candidate_pool_size", "max_initial_queries", "search_backend", "research_origins", "model",
    }
    assert finding["models_used"]["researcher"] == "test"
    assert finding["models_used"]["ingestor"] == "test"
    assert "analyst" not in finding["models_used"], "only the agents that ran are recorded"
    assert finding["closed"] is None
    assert re.fullmatch(r"[0-9a-f]{32}", finding["run_id"])
    assert str(finding["date"]) == str(finding["date"])[:10]
    assert finding["run_id"] in result.output


def test_abandoned_subject_draft_leaves_no_subject_record(tmp_path) -> None:
    """The record is written with the claim, so an abandoned run leaves none (OPEN-7, OPEN-8)."""
    from tests.loop_harness import fake_execute_searches

    three = URLS[:3]
    record = tmp_path / "research" / "entities" / "subjects" / "probe-sp2.md"
    with scripted_agents(scorer=scorer_args(three), search=fake_execute_searches(three)):
        abandoned = _draft(tmp_path, mode=("--subject", "probe-sp2"))
        dry = _draft(tmp_path, dry_run=True, mode=("--subject", "probe-sp2"))
    assert abandoned.exit_code == 1
    assert dry.exit_code == 0, dry.output
    assert not record.exists()
    assert len(_findings(tmp_path)) == 1


def test_unexpected_exception_is_a_finding_not_a_traceback(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(analyst_model=failing_model(KeyError("boom"))):
        result = _draft(tmp_path)

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert "Traceback" not in result.output
    finding = _one_finding(tmp_path)
    assert finding["outcome"] == "abandoned"
    assert finding["error"]["error_type"] == "model_error"
    assert "boom" in finding["error"]["message"]
    assert finding["run_id"] in result.output


# --------------------------------------------------------------------------- #
# Half-claims: a writer crash leaves a finding; dr findings lists what is left     #
# --------------------------------------------------------------------------- #


def test_writer_crash_after_the_claim_leaves_a_half_claim_finding(tmp_path, monkeypatch) -> None:
    import orchestrator.persistence as persistence

    write_entity(tmp_path)

    def _boom(*args, **kwargs):
        raise OSError("simulated sidecar write failure")

    monkeypatch.setattr(persistence, "_write_audit_sidecar", _boom)
    with scripted_agents():
        result = _draft(tmp_path)

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    claims = written_claims(tmp_path)
    assert len(claims) == 1, "the claim stays on disk; nothing is deleted automatically"
    assert not claims[0].with_suffix(".audit.yaml").exists()
    finding = _one_finding(tmp_path)
    assert finding["step"] == "write"
    assert finding["rule"] == "half-claim"
    assert finding["outcome"] == "half-claim"
    assert finding["error"]["error_type"] == "write_failed"
    assert "simulated sidecar write failure" in finding["error"]["message"]
    assert finding["claim_ref"] and finding["claim_ref"].endswith(claims[0].stem)

    from orchestrator.cli import main

    listed = CliRunner().invoke(main, ["findings", "--repo-root", str(tmp_path)])
    assert listed.exit_code == 0, listed.output
    assert finding["run_id"] in listed.output
    assert claims[0].stem in listed.output
    assert "dr draft --claim" in listed.output and "--force" in listed.output
    assert len(written_claims(tmp_path)) == 1


def test_writer_crash_after_a_tie_broken_run_keeps_the_split_in_the_finding(tmp_path, monkeypatch) -> None:
    import orchestrator.persistence as persistence

    write_entity(tmp_path)

    def _boom(*args, **kwargs):
        raise OSError("simulated sidecar write failure")

    monkeypatch.setattr(persistence, "_write_audit_sidecar", _boom)
    with scripted_agents(
        analyst=analyst_args(verdict="mixed"),
        auditor=auditor_args(verdict="true", confidence="high"),
        tiebreaker=auditor_args(verdict="true", confidence="high"),
    ):
        result = _draft(tmp_path)

    assert result.exit_code == 1
    finding = _one_finding(tmp_path)
    assert finding["outcome"] == "half-claim"
    assert "tiebreaker" in finding["models_used"]
    split = [r for r in finding["retries"] if r["error_type"] == "verdict_split"]
    assert len(split) == 1
    assert split[0]["step"] == "tiebreak"
    assert split[0]["message"] == "analyst mixed, evaluator true, tie-breaker true"


def test_subject_record_left_by_a_crash_is_listed_and_kept(tmp_path, monkeypatch) -> None:
    """OPEN-8: a crash between the subject record and the claim leaves the record; it is listed, not deleted."""
    import orchestrator.persistence as persistence

    def _boom(*args, **kwargs):
        raise OSError("simulated claim write failure")

    monkeypatch.setattr(persistence, "_write_claim_file", _boom)
    with scripted_agents():
        result = _draft(tmp_path, mode=("--subject", "probe-sp2"))

    assert result.exit_code == 1
    record = tmp_path / "research" / "entities" / "subjects" / "probe-sp2.md"
    assert record.exists()
    assert written_claims(tmp_path, "subjects/probe-sp2") == []
    finding = _one_finding(tmp_path)
    assert finding["outcome"] == "half-claim"

    from orchestrator.cli import main

    listed = CliRunner().invoke(main, ["findings", "--repo-root", str(tmp_path)])
    assert listed.exit_code == 0, listed.output
    assert "subjects/probe-sp2" in listed.output
    assert record.exists(), "dr findings deletes nothing"


# --------------------------------------------------------------------------- #
# rerun follows the same policy                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_rerun_analyst_applies_the_same_retry_policy(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    sources = [
        {"source_id": f"2026/s{i}", "slug": f"s{i}", "url": u, "title": f"S{i}", "publisher": "P",
         "summary": "s", "key_quotes": [], "body": "b", "kind": "article", "independence": "independent"}
        for i, u in enumerate(URLS)
    ]
    calls: list[str] = []
    with scripted_agents(analyst_model=failing_model(INVALID_OUTPUT, calls=calls)):
        result = await loop.rerun(claim_spec(tmp_path), _config(tmp_path), sources, agent="analyst")
    assert calls == ["run", "run"]
    assert result.analyst_output is None
    assert result.finding is not None
    assert result.finding.step == "analyse"
    assert result.finding.outcome == "abandoned"
    assert result.finding.attempts == 2


# --------------------------------------------------------------------------- #
# The old path is gone                                                            #
# --------------------------------------------------------------------------- #


def test_run_and_rerun_take_no_checkpoint_and_the_handlers_are_gone() -> None:
    import loop

    assert "checkpoint" not in inspect.signature(loop.run).parameters
    assert "checkpoint" not in inspect.signature(loop.rerun).parameters
    assert not (PIPELINE_DIR / "orchestrator" / "checkpoints.py").exists()
    assert not (PIPELINE_DIR / "tests" / "test_checkpoints.py").exists()

    from orchestrator.cli import main

    draft_help = CliRunner().invoke(main, ["draft", "--help"]).output
    assert "--interactive" not in draft_help
    assert "--no-interactive" not in draft_help
    top_help = CliRunner().invoke(main, ["--help"]).output
    assert "findings" in top_help


def test_loop_carries_no_old_path_names_in_code_comments_or_logs() -> None:
    """Finding F from the RE-AR review: moved bodies still named the old entry points."""
    stale = re.compile(r"verify_claim|research_claim|claim-probe|review_sources|checkpoint", re.IGNORECASE)
    offenders: list[str] = []
    for path in sorted(LOOP_DIR.rglob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if stale.search(line):
                offenders.append(f"{path.relative_to(PIPELINE_DIR)}:{n}: {line.strip()}")
    assert offenders == []


def test_pipeline_diagram_stub_names_the_four_source_threshold() -> None:
    text = (REPO_ROOT / "docs" / "plans" / "pipeline-diagram_stub.md").read_text(encoding="utf-8")
    assert "fewer than 2 usable sources" not in text
    assert "fewer than 4 usable sources" in text
