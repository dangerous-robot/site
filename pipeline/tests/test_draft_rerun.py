"""Acceptance tests for `dr draft --claim <ref> --rerun analyst|evaluator` (RE-AX, Fold side tools).

Written before the implementation (plan ``docs/plans/completed/pipeline-rebuild.md``
§ SP7 (Fold side tools), "Tests that prove it"; design
``handoff/2026-10-15-re-ax-design.md``). They replace ``dr step-analyze
--write`` and ``dr step-audit --write``: the cases are mined from
``test_cli.py`` (step-analyze and step-audit tests), ``test_loop_rerun.py``
(the step-audit carry-forward case) and ``test_recheck.py`` (the step-audit
live-claim refusals), with the published-to-draft expectations replaced by
the § Run rules rule: a rerun of a published or archived claim writes a
pending draft under ``research/pending/`` and never touches the live pair.

Every case drives the ``dr`` CLI under ``CliRunner`` with the agents on
scripted models (``tests/loop_harness.py``). ``loop.run`` and ``loop.rerun``
are public names; nothing here patches a private name under ``pipeline/loop/``.

Shapes pinned here (the design's § 2):

- ``--rerun`` goes with ``--claim`` only, takes no SENTENCE, ``--criterion``,
  ``--restates``, ``--source`` or ``--force``, and writes unless ``--dry-run`` or ``--paid-dry-run``;
- a draft is rewritten in place; a published or archived claim gets a
  pending pair at ``research/pending/<ref>.md`` plus ``.audit.yaml``;
- ``--rerun analyst`` nulls ``audit``, replaces the analyst's
  ``models_used`` entry and ``pipeline_run`` (agents ``["analyst"]``), and
  carries ``research``, ``sub_questions``, each ``sources_consulted`` entry's
  ``acquisition`` and ``archive``, the other agents' models and unknown keys;
- ``--rerun evaluator`` rewrites the sidecar only (agents ``["auditor"]``,
  plus ``tiebreaker`` when it ran) unless the tie-breaker settles on a
  verdict other than the claim's: then the claim's ``verdict`` and
  ``confidence`` become ``audit.pipeline_verdict`` and
  ``audit.pipeline_confidence`` (the orchestrator's default while Brandon's
  decision is pending; running note, "Decisions pending from Brandon").
"""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from common.frontmatter import parse_frontmatter, serialize_frontmatter
from tests.loop_harness import (
    ENTITY_REF,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    capturing_model,
    failing_model,
    scripted_agents,
    write_entity,
)

STEM = "probe-claim"
REF = f"{ENTITY_REF}/{STEM}"
OLD_RAN_AT = "2026-10-01T00:00:00+00:00"
FIT_NOTE = "verification_level independently-verified lowered to partially-verified: the written sources include 0"
REVIEWER = "reviewer@example.org"
SOURCE_IDS = [f"2026/report-{i}" for i in range(1, 5)]
OLD_MODELS = {
    "researcher": "old:researcher-model",
    "ingestor": "old:ingestor-model",
    "analyst": "old:analyst-model",
    "auditor": "old:auditor-model",
}
RESEARCH = {"mode": "decomposed", "queries": ["probe query"]}
SUB_QUESTIONS = [{"id": "sq1", "question": "Q?", "rationale": "r", "queries": ["probe query"], "citations": []}]
ACQUISITION = {"stage": "research", "origin": "tavily", "outcome": "matched"}
ARCHIVE = {"status": "failed", "error": "archive.org TimeGate check failed (HTTP 429)"}
RESTATEMENT = {
    "trigger": "mixed",
    "candidates": [{"rank": 1, "text": "Probe Subject used about 4% of US electricity in 2024",
                    "decisiveness": 3, "expected_verdict": "true", "expected_confidence": "medium"}],
}


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _claim_path(root, base: str = "claims"):
    return root / "research" / base / ENTITY_REF / f"{STEM}.md"


def _sidecar_path(claim_path):
    return claim_path.with_suffix(".audit.yaml")


def _write_sources(root) -> None:
    for i, (sid, url) in enumerate(zip(SOURCE_IDS, URLS), start=1):
        path = root / "research" / "sources" / f"{sid}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        fm = {
            "url": url, "title": f"Report {i}", "publisher": f"Publisher {i}",
            "accessed_date": "2026-10-01", "kind": "report", "independence": "independent",
            "summary": "Probe Subject data centers used more than 4% of US electricity in 2024.",
        }
        path.write_text(serialize_frontmatter(fm, "Body.\n"), encoding="utf-8")


def _repo(
    root,
    *,
    status: str = "draft",
    verdict: str = "mixed",
    confidence: str = "medium",
    statement: str | None = SENTENCE,
    title: str = SENTENCE,
    criteria_slug: str | None = "probe-criterion",
    templates: list | None = None,
    fm_extra: dict | None = None,
    sidecar_extra: dict | None = None,
):
    """A claim about the harness subject citing four stored sources, with a full sidecar; return its path."""
    write_entity(root)
    _write_sources(root)
    fm: dict = {"title": title}
    if statement is not None:
        fm["statement"] = statement
    fm.update({
        "entity": ENTITY_REF, "topics": ["environmental-impact"], "verdict": verdict,
        "confidence": confidence, "verification_level": "partially-verified", "status": status,
        "as_of": "2026-10-01", "sources": list(SOURCE_IDS),
        "seo_title": "Probe Subject electricity share",
    })
    if criteria_slug is not None:
        fm["criteria_slug"] = criteria_slug
    fm.update(fm_extra or {})
    claim = _claim_path(root)
    claim.parent.mkdir(parents=True, exist_ok=True)
    claim.write_text(serialize_frontmatter(fm, "The stored narrative.\n"), encoding="utf-8")
    reviewed = status in ("published", "archived")
    sidecar = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": OLD_RAN_AT, "model": "old:model",
                         "agents": ["researcher", "ingestor", "analyst", "auditor"], "level_clamp": FIT_NOTE},
        "models_used": dict(OLD_MODELS),
        "research": dict(RESEARCH),
        "sub_questions": [dict(sq) for sq in SUB_QUESTIONS],
        "sources_consulted": [
            {"id": sid, "url": url, "title": f"Report {i}", "ingested": True,
             "acquisition": dict(ACQUISITION), "archive": dict(ARCHIVE)}
            for i, (sid, url) in enumerate(zip(SOURCE_IDS, URLS), start=1)
        ],
        "audit": {
            "analyst_verdict": verdict, "auditor_verdict": verdict, "analyst_confidence": confidence,
            "auditor_confidence": confidence, "verdict_agrees": True, "confidence_agrees": True,
            "needs_review": False, "auditor_reasoning": "Agreed.", "evidence_gaps": [],
            "needs_review_reasons": [], "pipeline_verdict": verdict, "pipeline_confidence": confidence,
            "rule_applied": "agreed",
        },
        "human_review": {
            "reviewed_at": "2026-10-02" if reviewed else None,
            "reviewer": REVIEWER if reviewed else None,
            "notes": None, "pr_url": None,
        },
        "restatement": RESTATEMENT,
        "custom_note": {"kept": True},
    }
    sidecar.update(sidecar_extra or {})
    _sidecar_path(claim).write_text(yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True), encoding="utf-8")
    if templates is not None:
        (root / "research" / "templates.yaml").write_text(yaml.safe_dump({"templates": templates}), encoding="utf-8")
    return claim


def _dr(root, *args: str):
    from orchestrator.cli import main

    # Every agent slot is named so a DR_*_MODEL in the developer's .env cannot
    # send a test to a live model.
    return CliRunner().invoke(main, [
        "--model", "test", "--analyst-model", "test", "--auditor-model", "test",
        "--tiebreaker-model", "test", "--restater-model", "test",
        *args, "--repo-root", str(root),
    ])


def _rerun(root, agent: str, *extra: str):
    return _dr(root, "draft", "--claim", REF, "--rerun", agent, *extra)


def _fm(path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8"))[0]


def _sidecar(claim_path) -> dict:
    return yaml.safe_load(_sidecar_path(claim_path).read_text(encoding="utf-8"))


def _snapshot(root) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _findings(root) -> list[dict]:
    d = root / "research" / "findings"
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(d.rglob("*.yaml"))] if d.exists() else []


@pytest.fixture
def entry_spy(monkeypatch):
    """``loop.run`` fails if reached; ``loop.rerun`` is wrapped by a spy that records the agent."""
    import loop

    calls: list[str] = []
    real_rerun = loop.rerun

    async def _run(*args, **kwargs):
        calls.append("run")
        raise AssertionError("loop.run must not be called by --rerun")

    async def _rerun_spy(spec, config, sources, agent, *args, **kwargs):
        calls.append(f"rerun:{agent}")
        return await real_rerun(spec, config, sources, agent, *args, **kwargs)

    monkeypatch.setattr(loop, "run", _run)
    monkeypatch.setattr(loop, "rerun", _rerun_spy)
    return calls


def _never_search(calls: list):
    async def _search(queries, client, **kwargs):
        calls.append("search")
        raise AssertionError("execute_searches must not run on a rerun")

    return _search


# --------------------------------------------------------------------------- #
# Both forms: the public rerun entry, never the full run                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent,expected", [("analyst", "rerun:analyst"), ("evaluator", "rerun:evaluator")])
def test_rerun_calls_loop_rerun_and_never_loop_run(tmp_path, entry_spy, agent, expected) -> None:
    _repo(tmp_path)
    searched: list[str] = []

    with scripted_agents(search=_never_search(searched)):
        result = _rerun(tmp_path, agent)

    assert result.exit_code == 0, result.output
    assert entry_spy == [expected]
    assert searched == []


@pytest.mark.parametrize(
    "args",
    [
        ["draft", "--entity", ENTITY_REF, SENTENCE, "--rerun", "analyst"],
        ["draft", "--subject", "probe-subject", SENTENCE, "--rerun", "evaluator"],
        ["draft", "--claim", REF, SENTENCE, "--rerun", "analyst"],
        ["draft", "--claim", REF, "--criterion", "new-slug", "--rerun", "analyst"],
        ["draft", "--claim", REF, "--rerun", "analyst", "--force"],
        ["draft", "--restates", REF, "--pick", "1", "--rerun", "analyst"],
        ["draft", "--source", URLS[0], "--rerun", "analyst"],
        ["draft", "--claim", REF, "--rerun", "researcher"],
    ],
    ids=["entity", "subject", "sentence", "criterion", "force", "restates", "source", "unknown-agent"],
)
def test_rerun_grammar_is_a_usage_error_before_any_model_call(tmp_path, entry_spy, args) -> None:
    claim = _repo(tmp_path)
    before = _snapshot(tmp_path)

    with scripted_agents():
        result = _dr(tmp_path, *args)

    assert result.exit_code == 2, result.output
    assert entry_spy == []
    assert _snapshot(tmp_path) == before
    assert claim.exists()


def test_cli_still_imports_only_public_loop_names() -> None:
    """``check_ingested_source`` now serves ``--source`` and ``rerun`` serves ``--rerun``; both stay public."""
    import ast
    from pathlib import Path

    from tests.test_loop_probe_safety import PUBLIC_LOOP_NAMES

    cli = Path(__file__).resolve().parents[1] / "orchestrator" / "cli.py"
    tree = ast.parse(cli.read_text(encoding="utf-8"))
    names = {
        a.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "loop"
        for a in node.names
    }
    assert {"rerun", "check_ingested_source"} <= names
    assert names <= PUBLIC_LOOP_NAMES


# --------------------------------------------------------------------------- #
# --rerun analyst                                                              #
# --------------------------------------------------------------------------- #


def test_rerun_analyst_rewrites_a_draft_in_place_with_audit_nulled(tmp_path) -> None:
    """Mined from test_cli.py step-analyze --write cases (draft reset, audit cleared, analyst fields
    taken) and the backlog row "`dr step-analyze` leaves the old analyst model in the sidecar"."""
    claim = _repo(tmp_path, verdict="mixed")

    with scripted_agents(analyst=analyst_args(verdict="false", confidence="low")):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert not _claim_path(tmp_path, "pending").exists()
    fm = _fm(claim)
    assert fm["status"] == "draft"
    assert fm["verdict"] == "false"
    assert fm["criteria_slug"] == "probe-criterion"
    assert fm["statement"] == SENTENCE
    assert fm["title"] == SENTENCE
    sidecar = _sidecar(claim)
    assert sidecar["audit"] is None
    assert sidecar["pipeline_run"]["agents"] == ["analyst"]
    assert sidecar["pipeline_run"]["ran_at"] != OLD_RAN_AT
    assert sidecar["models_used"]["analyst"] == "test"
    assert sidecar["models_used"]["researcher"] == OLD_MODELS["researcher"]
    assert sidecar["models_used"]["ingestor"] == OLD_MODELS["ingestor"]
    assert "auditor" not in sidecar["models_used"], "audit is null, so no Evaluator model is named"
    assert sidecar["research"] == RESEARCH
    assert sidecar["sub_questions"][0]["id"] == "sq1"
    entries = {e["id"]: e for e in sidecar["sources_consulted"]}
    assert set(entries) == set(SOURCE_IDS)
    assert all(e["acquisition"] == ACQUISITION and e["archive"] == ARCHIVE for e in entries.values())
    assert sidecar["custom_note"] == {"kept": True}
    assert sidecar["analyst_record"]["verdict"] == "false"


def test_rerun_analyst_on_a_draft_keeps_its_sign_off_fields(tmp_path) -> None:
    """A draft's human_review is not reset by a rerun (running note, decision Q1 default)."""
    claim = _repo(tmp_path)
    sidecar = _sidecar(claim)
    sidecar["human_review"] = {"reviewed_at": "2026-10-03", "reviewer": REVIEWER, "notes": "n", "pr_url": None}
    _sidecar_path(claim).write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")

    with scripted_agents(analyst=analyst_args(verdict="false")):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _sidecar(claim)["human_review"]["reviewer"] == REVIEWER


@pytest.mark.parametrize("status", ["published", "archived"])
def test_rerun_analyst_on_a_live_claim_writes_a_pending_draft_and_leaves_the_live_pair(tmp_path, status) -> None:
    """Mined from test_cli.py test_step_analyze_write_refuses_a_live_claim and
    test_step_analyze_write_returns_a_non_draft_claim_to_draft: the published-to-draft
    reset is replaced by the § Run rules pending draft."""
    live = _repo(tmp_path, status=status, verdict="mixed")
    before = (live.read_bytes(), _sidecar_path(live).read_bytes())

    with scripted_agents(analyst=analyst_args(verdict="false", confidence="low")):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert (live.read_bytes(), _sidecar_path(live).read_bytes()) == before
    pending = _claim_path(tmp_path, "pending")
    assert pending.exists() and _sidecar_path(pending).exists()
    fm = _fm(pending)
    assert fm["status"] == "draft"
    assert fm["verdict"] == "false"
    assert fm["criteria_slug"] == "probe-criterion"
    assert fm["statement"] == SENTENCE
    sidecar = _sidecar(pending)
    assert sidecar["audit"] is None
    assert sidecar["human_review"]["reviewed_at"] is None
    assert "refresh" not in sidecar
    assert sidecar["research"] == RESEARCH
    assert sidecar["models_used"]["analyst"] == "test"
    assert sidecar["models_used"]["researcher"] == OLD_MODELS["researcher"]


def test_rerun_analyst_keeps_corrections_and_tags(tmp_path) -> None:
    """RE-AK (Published fields survive the pipeline): `corrections` and `tags` are always kept."""
    corrections = [{"date": "2026-10-05", "summary": "Fixed.", "previous_verdict": "true"}]
    claim = _repo(tmp_path, fm_extra={"corrections": corrections, "tags": ["energy"]})

    with scripted_agents(analyst=analyst_args(verdict="false")):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    fm = _fm(claim)
    assert fm["corrections"] == corrections
    assert fm["tags"] == ["energy"]


def test_rerun_analyst_keeps_the_entity_match_override(tmp_path) -> None:
    """Mined from test_cli.py test_step_analyze_write_keeps_the_entity_match_override (RE-AE,
    Source pool independence): the Off-entity relabel is recorded and the level fitted to it."""
    research = tmp_path / "research"
    (research / "entities" / "products").mkdir(parents=True)
    (research / "entities" / "products" / "acme.md").write_text(
        serialize_frontmatter({"name": "Acme", "type": "product", "description": "A product.",
                               "website": "https://acme.com"}, "Body.\n"),
        encoding="utf-8",
    )
    claim = research / "claims" / "acme" / "green.md"
    claim.parent.mkdir(parents=True)
    claim.write_text(serialize_frontmatter(
        {"title": "Acme is green", "statement": "Acme is green", "entity": "products/acme",
         "topics": ["environmental-impact"], "verdict": "mixed", "confidence": "low",
         "status": "draft", "sources": ["2026/grid-news"]}, "Body.\n"), encoding="utf-8")
    (research / "sources" / "2026").mkdir(parents=True)
    (research / "sources" / "2026" / "grid-news.md").write_text(serialize_frontmatter(
        {"url": "https://news.example.com/grid", "title": "Grid News", "publisher": "Daily News",
         "kind": "article", "independence": "independent", "summary": "Data centers use more power."},
        "Data centers use more power.\n"), encoding="utf-8")

    with scripted_agents(analyst={
        "title": "Acme is green", "verdict": "true", "confidence": "high", "narrative": "Grid News says so.",
        "topics": ["environmental-impact"], "verification_level": "independently-verified",
        "seo_title": "Acme green claim",
    }):
        result = _dr(tmp_path, "draft", "--claim", "acme/green", "--rerun", "analyst")

    assert result.exit_code == 0, result.output
    fm = _fm(claim)
    [override] = fm["source_overrides"]
    assert override["source"] == "2026/grid-news"
    assert override["independence"] == "unknown"
    assert override["reason"].startswith("Off-entity:")
    assert fm["verification_level"] == "claimed"


def test_rerun_analyst_takes_the_analysts_seo_title_and_takeaway(tmp_path) -> None:
    """Mined from test_cli.py test_step_analyze_write_takes_the_analysts_seo_title_and_takeaway:
    values the analyst last wrote are replaced and the record follows the new run."""
    claim = _repo(tmp_path, fm_extra={"seo_title": "Old analyst seo", "takeaway": "Old takeaway."},
                  sidecar_extra={"analyst_record": {
                      "title": SENTENCE, "seo_title": "Old analyst seo", "verdict": "mixed",
                      "takeaway": "Old takeaway.", "cap_rationale": None,
                  }})
    args = analyst_args(verdict="false")
    args["takeaway"] = "A new takeaway."

    with scripted_agents(analyst=args):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    fm = _fm(claim)
    assert fm["title"] == fm["statement"] == SENTENCE
    assert fm["seo_title"] == args["seo_title"]
    assert fm["takeaway"] == "A new takeaway."
    record = _sidecar(claim)["analyst_record"]
    assert record["seo_title"] == args["seo_title"]
    assert record["takeaway"] == "A new takeaway."


def test_approval_after_rerun_analyst_records_no_override(tmp_path, human_at_terminal) -> None:
    """Mined from test_cli.py test_approval_after_step_analyze_records_no_override."""
    from orchestrator.review import approve_claim

    claim = _repo(tmp_path, verdict="true")

    with scripted_agents(analyst=analyst_args(verdict="false")):
        result = _rerun(tmp_path, "analyst")
    assert result.exit_code == 0, result.output
    approve_claim(claim, reviewer=REVIEWER, mode="approve")

    assert _sidecar(claim)["human_review"]["verdict_override"] is None


def test_rerun_analyst_dry_run_prints_the_level_and_resolved_citations_and_writes_nothing(tmp_path) -> None:
    """Mined from test_cli.py test_step_analyze_gives_analyst_source_ids_so_year_slug_citations_resolve."""
    _repo(tmp_path)
    before = _snapshot(tmp_path)
    captured: list[str] = []
    model = capturing_model(captured, analyst_args(
        verdict="unverified", confidence="low", level="claimed",
        narrative="Report 1 says so 【2026/report-1】.", cap_rationale="Only one report addresses it.",
    ))

    with scripted_agents(analyst_model=model):
        result = _rerun(tmp_path, "analyst", "--paid-dry-run")

    assert result.exit_code == 0, result.output
    assert _snapshot(tmp_path) == before
    assert any("2026/report-1" in p for p in captured)
    assert "*Report 1*" in result.output
    assert "【" not in result.output
    assert "Level:      claimed" in result.output


def test_a_failed_rerun_writes_nothing_but_its_finding(tmp_path) -> None:
    """§ Run rules: a failed rerun leaves the claim and its sidecar untouched; only a finding is written."""
    claim = _repo(tmp_path)
    before = (claim.read_bytes(), _sidecar_path(claim).read_bytes())

    with scripted_agents(analyst_model=failing_model()):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 1, result.output
    assert (claim.read_bytes(), _sidecar_path(claim).read_bytes()) == before
    assert not _claim_path(tmp_path, "pending").exists()
    [finding] = _findings(tmp_path)
    assert finding["outcome"] == "abandoned"
    assert finding["claim_ref"] == REF


# --------------------------------------------------------------------------- #
# --rerun evaluator                                                            #
# --------------------------------------------------------------------------- #


def test_rerun_evaluator_keeps_the_rest_of_the_sidecar_and_leaves_an_agreeing_claim_alone(tmp_path) -> None:
    """Mined from test_cli.py step-audit --write keep tests (archive record, other agents' models,
    the level fit note) and test_loop_rerun.py's carry-forward case."""
    claim = _repo(tmp_path, verdict="mixed")
    claim_before = claim.read_bytes()

    with scripted_agents(auditor=auditor_args(verdict="mixed")):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    assert claim.read_bytes() == claim_before
    sidecar = _sidecar(claim)
    assert sidecar["pipeline_run"]["agents"] == ["auditor"]
    assert sidecar["pipeline_run"]["level_clamp"] == FIT_NOTE
    assert sidecar["models_used"] == {**OLD_MODELS, "auditor": "test"}
    assert sidecar["research"] == RESEARCH
    assert sidecar["sub_questions"][0]["id"] == "sq1"
    entries = {e["id"]: e for e in sidecar["sources_consulted"]}
    assert all(e["acquisition"] == ACQUISITION and e["archive"] == ARCHIVE for e in entries.values())
    assert sidecar["restatement"] == RESTATEMENT
    assert sidecar["custom_note"] == {"kept": True}
    assert sidecar["audit"]["auditor_verdict"] == "mixed"


def test_rerun_evaluator_grades_the_stored_statement(tmp_path) -> None:
    """Mined from test_cli.py test_step_audit_sends_claim_title (RE-AD, Evaluator grades the claim)."""
    _repo(tmp_path)
    captured: list[str] = []

    with scripted_agents(auditor_model=capturing_model(captured, auditor_args())):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    assert any(SENTENCE in p for p in captured)


def test_rerun_evaluator_grades_the_title_of_a_claim_without_a_statement(tmp_path) -> None:
    title = "Probe Subject data centers drew over four percent of US power in 2024"
    _repo(tmp_path, statement=None, title=title)
    captured: list[str] = []

    with scripted_agents(auditor_model=capturing_model(captured, auditor_args())):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    assert any(title in p for p in captured)


def test_rerun_evaluator_on_a_draft_takes_the_tiebreakers_verdict_when_it_sides_with_the_evaluator(
    tmp_path, human_at_terminal,
) -> None:
    """The orchestrator's default (Brandon's decision pending): the claim carries the pipeline
    verdict, so approval records no override nobody chose."""
    from orchestrator.review import approve_claim

    claim = _repo(tmp_path, verdict="true", confidence="high")

    with scripted_agents(auditor=auditor_args(verdict="false", confidence="medium"),
                         tiebreaker=auditor_args(verdict="false", confidence="medium")):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    sidecar = _sidecar(claim)
    assert sidecar["audit"]["pipeline_verdict"] == "false"
    assert "tiebreaker" in sidecar["pipeline_run"]["agents"]
    fm = _fm(claim)
    assert fm["verdict"] == "false"
    assert fm["confidence"] == sidecar["audit"]["pipeline_confidence"]
    # The record moves to the new verdict; no takeaway on disk, so none is tied to the old one.
    assert sidecar["analyst_record"]["verdict"] == "false"
    assert sidecar["analyst_record"]["takeaway_verdict"] is None
    approve_claim(claim, reviewer=REVIEWER, mode="approve")
    assert _sidecar(claim)["human_review"]["verdict_override"] is None


def test_an_operator_seo_title_survives_a_verdict_changing_evaluator_rerun_then_an_analyst_rerun(tmp_path) -> None:
    """A sidecar with no analyst_record: the Evaluator rerun that rewrites the verdict must not
    build a record that makes the operator's seo_title look like the analyst's."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"seo_title": "Operator seo"})
    assert "analyst_record" not in _sidecar(claim)

    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
        result = _rerun(tmp_path, "evaluator")
    assert result.exit_code == 0, result.output
    assert _fm(claim)["verdict"] == "false"
    record = _sidecar(claim)["analyst_record"]
    assert record["verdict"] == "false"
    assert record["title"] == SENTENCE
    assert record["seo_title"] is None

    with scripted_agents(analyst=analyst_args(verdict="false")):
        result = _rerun(tmp_path, "analyst")
    assert result.exit_code == 0, result.output
    assert _fm(claim)["seo_title"] == "Operator seo"


def test_rerun_evaluator_leaves_the_claim_when_the_tiebreaker_sides_with_the_analyst(tmp_path) -> None:
    claim = _repo(tmp_path, verdict="true", confidence="high")
    claim_before = claim.read_bytes()

    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="true")):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    assert claim.read_bytes() == claim_before
    assert _sidecar(claim)["audit"]["pipeline_verdict"] == "true"


@pytest.mark.parametrize("status", ["published", "archived"])
def test_rerun_evaluator_on_a_live_claim_writes_a_pending_draft_and_leaves_the_live_pair(tmp_path, status) -> None:
    """Mined from test_recheck.py test_step_audit_write_on_a_live_claim_is_a_usage_error_naming_recheck:
    the refusal becomes a pending draft that carries the pipeline verdict."""
    live = _repo(tmp_path, status=status, verdict="true", confidence="high")
    before = (live.read_bytes(), _sidecar_path(live).read_bytes())

    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    assert (live.read_bytes(), _sidecar_path(live).read_bytes()) == before
    pending = _claim_path(tmp_path, "pending")
    fm = _fm(pending)
    assert fm["status"] == "draft"
    assert fm["verdict"] == "false"
    sidecar = _sidecar(pending)
    assert sidecar["audit"]["pipeline_verdict"] == "false"
    assert sidecar["human_review"]["reviewed_at"] is None
    assert "refresh" not in sidecar
    assert sidecar["models_used"] == {**OLD_MODELS, "auditor": "test", "tiebreaker": "test"}
    assert sidecar["research"] == RESEARCH


# --------------------------------------------------------------------------- #
# The criterion's grading rule reaches both agents (RE-AG)                      #
# --------------------------------------------------------------------------- #

_SENTINEL = "SENTINEL-GRADING: mixed = offsets only"


def _criterion(**extra) -> dict:
    return {"slug": "probe-criterion", "text": "SUBJECT used more than 4% of US electricity in 2024",
            "entity_type": "subject", "subjects": [ENTITY_REF], "topics": ["environmental-impact"],
            "core": False, **extra}


@pytest.mark.parametrize("agent", ["analyst", "evaluator"])
def test_rerun_sends_the_grading_rule_and_not_notes(tmp_path, agent) -> None:
    """Mined from test_cli.py TestStepAnalyzeCriterion and test_step_audit_sends_the_grading_rule_and_not_notes."""
    _repo(tmp_path, templates=[_criterion(notes="NOTES-ONLY reader text", grading_rule=_SENTINEL)])
    captured: list[str] = []
    if agent == "analyst":
        agents = scripted_agents(analyst_model=capturing_model(captured, analyst_args()))
    else:
        agents = scripted_agents(auditor_model=capturing_model(captured, auditor_args()))

    with agents:
        result = _rerun(tmp_path, agent, "--paid-dry-run")

    assert result.exit_code == 0, result.output
    prompt = "\n".join(captured)
    assert f"## Criterion notes\n{_SENTINEL}" in prompt
    assert "NOTES-ONLY" not in prompt


def test_rerun_analyst_on_a_claim_without_a_statement_sends_and_writes_its_title(tmp_path) -> None:
    """Mined from test_cli.py TestStepAnalyzeCriterion: the claim's own text reaches the analyst,
    the rendered criterion text never does, and the title becomes both title and statement."""
    title = "Probe Subject title fallback"
    criterion = _criterion(text="ENTITY is hosted on renewable energy", grading_rule=_SENTINEL)
    claim = _repo(tmp_path, statement=None, title=title, templates=[criterion])
    captured: list[str] = []

    with scripted_agents(analyst_model=capturing_model(captured, analyst_args())):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    prompt = "\n".join(captured)
    assert title in prompt
    assert f"## Criterion notes\n{_SENTINEL}" in prompt, "the criterion was not loaded"
    assert "hosted on renewable energy" not in prompt
    fm = _fm(claim)
    assert fm["title"] == fm["statement"] == title


@pytest.mark.parametrize("agent", ["analyst", "evaluator"])
@pytest.mark.parametrize(
    "criteria_slug,templates",
    [
        ("probe-criterion", [_criterion(notes=_SENTINEL)]),
        (None, [_criterion(grading_rule=_SENTINEL)]),
        ("not-a-criterion", [_criterion(grading_rule=_SENTINEL)]),
        ("probe-criterion", None),
    ],
    ids=["notes-without-grading-rule", "no-criteria-slug", "unknown-slug", "no-templates-file"],
)
def test_rerun_without_a_grading_rule_sends_none(tmp_path, agent, criteria_slug, templates) -> None:
    """Mined from test_cli.py test_step_audit_without_a_grading_rule_sends_none and the
    TestStepAnalyzeCriterion fallbacks."""
    _repo(tmp_path, criteria_slug=criteria_slug, templates=templates)
    captured: list[str] = []
    if agent == "analyst":
        agents = scripted_agents(analyst_model=capturing_model(captured, analyst_args()))
    else:
        agents = scripted_agents(auditor_model=capturing_model(captured, auditor_args()))

    with agents:
        result = _rerun(tmp_path, agent, "--paid-dry-run")

    assert result.exit_code == 0, result.output
    assert captured, "the agent never ran"
    prompt = "\n".join(captured)
    assert SENTENCE in prompt, "the claim's statement reached the agent"
    assert "## Criterion notes" not in prompt


# --------------------------------------------------------------------------- #
# RE-AX (Fold side tools) fix pass: published claims, existing pending drafts    #
# (departure X9, rerun from the pending draft) and unknown statuses              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent,failing", [("analyst", "analyst_model"), ("evaluator", "auditor_model")])
def test_a_failed_rerun_of_a_published_claim_creates_no_pending_draft(tmp_path, agent, failing) -> None:
    """§ Run rules "Failed rerun of a claim that is published or archived": nothing is written
    but the finding; the live pair is byte-identical and no pending pair appears."""
    live = _repo(tmp_path, status="published")
    before = (live.read_bytes(), _sidecar_path(live).read_bytes())

    with scripted_agents(**{failing: failing_model()}):
        result = _rerun(tmp_path, agent)

    assert result.exit_code == 1, result.output
    assert (live.read_bytes(), _sidecar_path(live).read_bytes()) == before
    assert not (tmp_path / "research" / "pending").exists()
    [finding] = _findings(tmp_path)
    assert finding["claim_ref"] == REF


@pytest.mark.parametrize("agent", ["analyst", "evaluator"])
def test_a_writer_stop_on_a_published_claims_rerun_leaves_the_live_pair_and_no_pending_draft(
    tmp_path, monkeypatch, agent,
) -> None:
    """The pending pair is staged and moved only after every write, so a writer stop leaves the
    live pair byte-identical and nothing under research/pending/. The finding uses rule
    half-claim, as `dr recheck` does for the same stop."""
    import orchestrator.persistence as persistence

    live = _repo(tmp_path, status="published", verdict="true", confidence="high")
    before = (live.read_bytes(), _sidecar_path(live).read_bytes())

    def stop(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(persistence, "_write_audit_sidecar", stop)
    agents = ({"analyst": analyst_args(verdict="false")} if agent == "analyst"
              else {"auditor": auditor_args(verdict="false"), "tiebreaker": auditor_args(verdict="false")})
    with scripted_agents(**agents):
        result = _rerun(tmp_path, agent)

    assert result.exit_code == 1, result.output
    assert (live.read_bytes(), _sidecar_path(live).read_bytes()) == before
    pending = tmp_path / "research" / "pending"
    assert not pending.exists() or not any(pending.rglob("*.md"))
    assert not list(tmp_path.glob(".dr-*"))
    [finding] = _findings(tmp_path)
    assert (finding["outcome"], finding["step"], finding["claim_ref"]) == ("half-claim", "write", REF)


def test_rerun_evaluator_dry_run_on_a_published_claim_writes_nothing(tmp_path) -> None:
    _repo(tmp_path, status="published")
    before = _snapshot(tmp_path)

    with scripted_agents(auditor=auditor_args(verdict="false")):
        result = _rerun(tmp_path, "evaluator", "--paid-dry-run")

    assert result.exit_code == 0, result.output
    assert _snapshot(tmp_path) == before


def test_rerun_analyst_from_an_existing_pending_draft_rewrites_the_pending_draft(tmp_path) -> None:
    """Departure X9 (rerun from the pending draft): a second `--rerun analyst` on a published claim reruns the pending draft, keeping its seed record."""
    live = _repo(tmp_path, status="published", verdict="mixed", fm_extra={"takeaway": "Operator takeaway."})
    before = (live.read_bytes(), _sidecar_path(live).read_bytes())
    with scripted_agents(analyst=analyst_args(verdict="false")):
        assert _rerun(tmp_path, "analyst").exit_code == 0
    pending = _claim_path(tmp_path, "pending")
    seeded = _sidecar(pending)["seeded_live"]

    with scripted_agents(analyst=analyst_args(verdict="mostly-false", narrative="The second analysis.")):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert (live.read_bytes(), _sidecar_path(live).read_bytes()) == before
    assert _fm(pending)["verdict"] == "mostly-false"
    assert "The second analysis." in pending.read_text(encoding="utf-8")
    assert _sidecar(pending)["seeded_live"] == seeded == {
        "takeaway": "Operator takeaway.", "seo_title": "Probe Subject electricity share", "cap_rationale": None,
        "corrections": None, "tags": None, "analyst_title": SENTENCE,
        "pending": {"takeaway": "Operator takeaway.", "seo_title": "Probe Subject electricity share",
                    "cap_rationale": None},
    }


def test_rerun_evaluator_from_an_existing_pending_draft_grades_the_pending_analysis(tmp_path) -> None:
    """Departure X9 (rerun from the pending draft): the Evaluator grades the pending draft's verdict (false), not the live one (mixed)."""
    live = _repo(tmp_path, status="published", verdict="mixed")
    before = (live.read_bytes(), _sidecar_path(live).read_bytes())
    with scripted_agents(analyst=analyst_args(verdict="false")):
        assert _rerun(tmp_path, "analyst").exit_code == 0
    pending = _claim_path(tmp_path, "pending")
    seeded = _sidecar(pending)["seeded_live"]

    with scripted_agents(auditor=auditor_args(verdict="false")):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    assert (live.read_bytes(), _sidecar_path(live).read_bytes()) == before
    audit = _sidecar(pending)["audit"]
    assert audit["analyst_verdict"] == "false"
    assert audit["auditor_verdict"] == "false"
    assert _fm(pending)["verdict"] == "false"
    assert _sidecar(pending)["seeded_live"] == seeded, "the Evaluator's sidecar write keeps the seed record"


@pytest.mark.parametrize("flags", [(), ("--dry-run",), ("--paid-dry-run",)], ids=["write", "dry-run", "paid-dry-run"])
def test_rerun_of_a_claim_with_an_unknown_status_is_refused_before_any_model_call(tmp_path, entry_spy, flags) -> None:
    _repo(tmp_path, status="blocked")
    before = _snapshot(tmp_path)

    result = _rerun(tmp_path, "evaluator", *flags)

    assert result.exit_code == 1, result.output
    assert entry_spy == []
    assert _snapshot(tmp_path) == before


def test_a_writer_stop_after_the_claim_write_leaves_no_stale_grade_and_records_a_half_claim(tmp_path, monkeypatch) -> None:
    """Hazard H15 (stale audit compared at approve): `--rerun analyst` nulls `audit` before the claim
    write, so a stop before the sidecar write leaves no old grade beside the new verdict, and the
    finding records the half-claim."""
    import orchestrator.persistence as persistence

    claim = _repo(tmp_path, verdict="mixed")

    def stop(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(persistence, "_write_audit_sidecar", stop)
    with scripted_agents(analyst=analyst_args(verdict="false")):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 1, result.output
    assert _fm(claim)["verdict"] == "false"
    assert _sidecar(claim)["audit"] is None
    [finding] = _findings(tmp_path)
    assert (finding["outcome"], finding["rule"], finding["step"]) == ("half-claim", "half-claim", "write")
    assert finding["claim_ref"] == REF
    assert finding["models_used"] == {"analyst": "test"}


def test_an_evaluator_rerun_stop_after_the_verdict_write_leaves_no_stale_grade(tmp_path, monkeypatch) -> None:
    """Hazard H15 on the Evaluator path: when the tie-breaker's verdict is written into the claim,
    the old grade (whose pipeline_verdict is the old verdict) is nulled first, so a stop before the
    sidecar write leaves no grade for approval to compare the new verdict against."""
    import orchestrator.persistence as persistence

    claim = _repo(tmp_path, verdict="true", confidence="high")
    assert _sidecar(claim)["audit"]["pipeline_verdict"] == "true"

    def stop(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(persistence, "_write_audit_sidecar", stop)
    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 1, result.output
    assert _fm(claim)["verdict"] == "false"
    assert _sidecar(claim)["audit"] is None
    [finding] = _findings(tmp_path)
    assert (finding["outcome"], finding["step"]) == ("half-claim", "write")
    assert finding["models_used"] == {"auditor": "test", "tiebreaker": "test"}


# --------------------------------------------------------------------------- #
# P1 (stale operator takeaway): an Evaluator rerun that rewrites the verdict     #
# ties the takeaway on disk to the verdict it was written for (takeaway_verdict) #
# --------------------------------------------------------------------------- #

OPERATOR_TAKEAWAY = "Operator takeaway for TRUE."
ANALYST_RECORD_TRUE = {
    "title": SENTENCE, "seo_title": "Probe Subject electricity share", "verdict": "true",
    "takeaway": "Analyst takeaway for TRUE.", "cap_rationale": None,
}


def _analyst_false_with_takeaway() -> dict:
    return {**analyst_args(verdict="false"), "takeaway": "Analyst takeaway for FALSE."}


@pytest.mark.parametrize("with_record", [True, False], ids=["record", "no-record"])
def test_an_evaluator_rerun_that_flips_the_verdict_then_an_analyst_rerun_replaces_the_old_operator_takeaway(
    tmp_path, with_record,
) -> None:
    """The operator wrote the takeaway for TRUE; the Evaluator rerun moves the verdict to false;
    an analyst rerun that agrees (false) must not keep the takeaway written for TRUE."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)} if with_record else None)

    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
        result = _rerun(tmp_path, "evaluator")
    assert result.exit_code == 0, result.output
    assert _fm(claim)["verdict"] == "false"
    record = _sidecar(claim)["analyst_record"]
    assert (record["verdict"], record["takeaway"], record["takeaway_verdict"]) == ("false", OPERATOR_TAKEAWAY, "true")

    with scripted_agents(analyst=_analyst_false_with_takeaway()):
        result = _rerun(tmp_path, "analyst")
    assert result.exit_code == 0, result.output
    fm = _fm(claim)
    assert fm["verdict"] == "false"
    assert fm["takeaway"] == "Analyst takeaway for FALSE."


def test_control_an_evaluator_rerun_that_keeps_the_verdict_leaves_the_operator_takeaway_kept(tmp_path) -> None:
    """Control for the P1 (stale operator takeaway) fix: with the verdict unchanged, the
    operator's takeaway still wins over the analyst's."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})

    with scripted_agents(auditor=auditor_args(verdict="true", confidence="high")):
        assert _rerun(tmp_path, "evaluator").exit_code == 0
    with scripted_agents(analyst={**analyst_args(verdict="true"), "takeaway": "Analyst takeaway, again TRUE."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == OPERATOR_TAKEAWAY


def test_on_a_published_claim_an_evaluator_rerun_then_an_analyst_rerun_promotes_the_new_takeaway(tmp_path) -> None:
    """P1 (stale operator takeaway) through the pending draft (departure X9, rerun from the
    pending draft) and promotion: the takeaway written for TRUE does not reach the live claim."""
    from orchestrator.persistence import promote_pending

    live = _repo(tmp_path, status="published", verdict="true", confidence="high",
                 fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                 sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})

    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
        assert _rerun(tmp_path, "evaluator").exit_code == 0
    pending = _claim_path(tmp_path, "pending")
    assert _fm(pending)["verdict"] == "false"
    with scripted_agents(analyst=_analyst_false_with_takeaway()):
        result = _rerun(tmp_path, "analyst")
    assert result.exit_code == 0, result.output
    assert _fm(pending)["takeaway"] == "Analyst takeaway for FALSE."

    promote_pending(live, tmp_path)
    fm = _fm(live)
    assert fm["verdict"] == "false"
    assert fm["takeaway"] == "Analyst takeaway for FALSE."


def test_an_evaluator_rerun_with_no_tie_break_drops_an_old_tiebreaker_model(tmp_path) -> None:
    """The new grade has no tie-breaker output, so an old tie-breaker's model entry would name
    output that is no longer on disk; the other agents' entries are kept."""
    claim = _repo(tmp_path, verdict="true", confidence="high",
                  sidecar_extra={"models_used": {**OLD_MODELS, "tiebreaker": "old:tiebreaker-model"}})

    with scripted_agents(auditor=auditor_args(verdict="true", confidence="high")):
        result = _rerun(tmp_path, "evaluator")

    assert result.exit_code == 0, result.output
    sidecar = _sidecar(claim)
    assert "tiebreaker_verdict" not in sidecar["audit"]
    assert sidecar["models_used"] == {**OLD_MODELS, "auditor": "test"}


# --------------------------------------------------------------------------- #
# A rerun's finding is never replayed as a full run (`dr findings --replay`)     #
# --------------------------------------------------------------------------- #


def _replay_tripwire(monkeypatch) -> list[str]:
    import loop

    called: list[str] = []

    async def _run(*args, **kwargs):
        called.append("run")
        raise AssertionError("loop.run must not be called by a replay of a --rerun finding")

    monkeypatch.setattr(loop, "run", _run)
    return called


@pytest.mark.parametrize("agent", ["analyst", "evaluator"])
@pytest.mark.parametrize("stop", ["writer", "model"])
def test_a_reruns_finding_names_the_rerun_and_replay_skips_it(tmp_path, monkeypatch, agent, stop) -> None:
    """A replay runs the full paid loop and force-writes a draft, which is not what a one-agent
    rerun did; the finding records `dr draft --rerun <agent>` and `dr findings --replay` skips it."""
    import orchestrator.persistence as persistence

    claim = _repo(tmp_path, verdict="true", confidence="high")
    if stop == "writer":
        def halt(*args, **kwargs):
            raise OSError("disk full")

        agents = ({"analyst": analyst_args(verdict="false")} if agent == "analyst"
                  else {"auditor": auditor_args(verdict="false"), "tiebreaker": auditor_args(verdict="false")})
        with monkeypatch.context() as m:
            m.setattr(persistence, "_write_audit_sidecar", halt)
            with scripted_agents(**agents):
                ran = _rerun(tmp_path, agent)
    else:
        failing = "analyst_model" if agent == "analyst" else "auditor_model"
        with scripted_agents(**{failing: failing_model()}):
            ran = _rerun(tmp_path, agent)
    assert ran.exit_code == 1, ran.output
    [finding] = _findings(tmp_path)
    assert finding["command"] == f"dr draft --rerun {agent}"
    assert finding["outcome"] in ("half-claim", "abandoned")
    after_rerun = _snapshot(tmp_path)
    called = _replay_tripwire(monkeypatch)

    result = _dr(tmp_path, "findings", "--replay")

    assert result.exit_code == 0, result.output
    assert called == []
    line = next(x for x in result.stdout.splitlines() if x.startswith(f"{finding['run_id']}: "))
    assert line.startswith(f"{finding['run_id']}: skipped"), line
    assert f"dr draft --claim {REF} --rerun {agent}" in line
    assert _snapshot(tmp_path) == after_rerun
    assert claim.exists()


def test_an_operator_takeaway_written_after_a_verdict_changing_evaluator_rerun_survives_an_agreeing_analyst_rerun(
    tmp_path,
) -> None:
    """The verdict did not change after the operator wrote the takeaway, so it is kept."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": "Analyst takeaway for TRUE."},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
        assert _rerun(tmp_path, "evaluator").exit_code == 0
    fm, body = parse_frontmatter(claim.read_text(encoding="utf-8"))
    claim.write_text(serialize_frontmatter({**fm, "takeaway": "Operator takeaway for FALSE."}, body), encoding="utf-8")

    with scripted_agents(analyst=_analyst_false_with_takeaway()):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == "Operator takeaway for FALSE."


def _flip(root, verdict: str) -> None:
    with scripted_agents(auditor=auditor_args(verdict=verdict), tiebreaker=auditor_args(verdict=verdict)):
        result = _rerun(root, "evaluator")
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("with_record", [True, False], ids=["record", "no-record"])
def test_an_operator_takeaway_survives_when_an_analyst_rerun_returns_the_verdict_it_was_written_for(
    tmp_path, with_record,
) -> None:
    """Operator takeaway for TRUE, the Evaluator moves the verdict to false, the analyst returns
    TRUE: the takeaway is judged against the verdict it was written for, and kept."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)} if with_record else None)
    _flip(tmp_path, "false")

    with scripted_agents(analyst={**analyst_args(verdict="true"), "takeaway": "Analyst takeaway, TRUE again."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == OPERATOR_TAKEAWAY


def test_an_operator_takeaway_survives_two_verdict_changing_evaluator_reruns_back_to_its_verdict(tmp_path) -> None:
    """The second rewrite finds the takeaway the record already ties to TRUE and keeps that tie."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    _flip(tmp_path, "false")
    _flip(tmp_path, "true")
    assert _fm(claim)["verdict"] == "true"
    assert _sidecar(claim)["analyst_record"]["takeaway_verdict"] == "true"

    with scripted_agents(analyst={**analyst_args(verdict="true"), "takeaway": "Analyst takeaway, TRUE again."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == OPERATOR_TAKEAWAY


def test_an_analyst_takeaway_is_replaced_by_the_next_analyst_rerun_after_a_verdict_rewrite(tmp_path) -> None:
    """Once the analyst writes a takeaway, the record no longer ties the old one to a verdict:
    the analyst's FALSE takeaway does not outlive a later TRUE verdict."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    _flip(tmp_path, "false")
    with scripted_agents(analyst=_analyst_false_with_takeaway()):
        assert _rerun(tmp_path, "analyst").exit_code == 0
    assert _fm(claim)["takeaway"] == "Analyst takeaway for FALSE."
    assert "takeaway_verdict" not in _sidecar(claim)["analyst_record"]

    with scripted_agents(analyst={**analyst_args(verdict="true"), "takeaway": "Analyst takeaway, TRUE again."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == "Analyst takeaway, TRUE again."


def test_an_evaluator_rerun_that_stops_after_the_verdict_rewrite_leaves_the_record_for_the_old_takeaway(
    tmp_path, monkeypatch,
) -> None:
    """No record on disk: the record is written with the audit drop, before the claim write, so a
    stop after the claim write cannot leave the fallback rebuilt from the new verdict."""
    import orchestrator.persistence as persistence

    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY})

    def halt(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as m:
        m.setattr(persistence, "_store_analyst_record", halt)
        m.setattr(persistence, "_write_audit_sidecar", halt)
        with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
            stopped = _rerun(tmp_path, "evaluator")
    assert stopped.exit_code == 1, stopped.output
    assert _fm(claim)["verdict"] == "false"

    with scripted_agents(analyst=_analyst_false_with_takeaway()):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == "Analyst takeaway for FALSE."


# --------------------------------------------------------------------------- #
# A verdict-changing `--rerun evaluator` stopped after each of its writes: an    #
# operator takeaway written in between is kept while the verdict it was written  #
# for holds (RE-AK (Published fields survive the pipeline)).                     #
# --------------------------------------------------------------------------- #

# Every write a verdict-changing Evaluator rerun makes to the claim files, and
# the one a rerun that leaves the verdict makes. The stop cases run once per
# entry; a new write fails the inventory test until its stop case is counted.
_CLAIM_DIR = "research/claims/subjects/probe-subject"
EVALUATOR_FLIP_WRITES = [
    ("write", f"{_CLAIM_DIR}/{STEM}.audit.yaml"),
    ("write", f"{_CLAIM_DIR}/{STEM}.md"),
    ("write", f"{_CLAIM_DIR}/{STEM}.audit.yaml"),
]
EVALUATOR_SAME_WRITES = [
    ("write", f"{_CLAIM_DIR}/{STEM}.audit.yaml"),
]
_ANALYST_TRUE_TAKEAWAY = ANALYST_RECORD_TRUE["takeaway"]


def _evaluator_rerun(root, verdict: str):
    if verdict == "true":
        agents = {"auditor": auditor_args(verdict="true", confidence="high")}
    else:
        agents = {"auditor": auditor_args(verdict=verdict), "tiebreaker": auditor_args(verdict=verdict)}
    with scripted_agents(**agents):
        return _rerun(root, "evaluator")


def _set_fm(claim, **edit) -> None:
    fm, body = parse_frontmatter(claim.read_text(encoding="utf-8"))
    claim.write_text(serialize_frontmatter({**fm, **edit}, body), encoding="utf-8")


@pytest.mark.parametrize(("flip", "expected"), [(True, EVALUATOR_FLIP_WRITES), (False, EVALUATOR_SAME_WRITES)],
                         ids=["verdict-changed", "verdict-kept"])
def test_the_evaluator_rerun_write_inventory_has_a_stop_case_per_write(tmp_path, flip, expected) -> None:
    from tests.write_faults import WriteFaults

    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    faults = WriteFaults(tmp_path)

    with faults.record():
        ran = _evaluator_rerun(tmp_path, "false" if flip else "true")

    assert ran.exit_code == 0, ran.output
    assert faults.writes == expected
    assert _fm(claim)["verdict"] == ("false" if flip else "true")


@pytest.mark.parametrize("then", ["retry-then-analyst", "analyst"])
@pytest.mark.parametrize("analyst_agrees", [True, False], ids=["analyst-agrees", "analyst-differs"])
@pytest.mark.parametrize("edit", [False, True], ids=["no-edit", "operator-edit"])
@pytest.mark.parametrize("start", ["operator", "analyst"], ids=["operator-takeaway", "analyst-takeaway"])
@pytest.mark.parametrize("stop", range(len(EVALUATOR_FLIP_WRITES)), ids=lambda n: f"stop{n}")
def test_an_evaluator_rerun_stopped_at_any_write_keeps_an_operator_takeaway_while_its_verdict_holds(
    tmp_path, stop, start, edit, analyst_agrees, then,
) -> None:
    """Stop the TRUE-to-FALSE rewrite at one write. The operator may then write a takeaway for
    the verdict the claim shows. Then either retry the Evaluator rerun and run the analyst, or
    run the analyst at once. An operator takeaway is kept when the analyst returns the verdict
    it was written for and replaced otherwise; an analyst takeaway is always replaced."""
    from tests.write_faults import WriteFaults

    claim = _repo(tmp_path, verdict="true", confidence="high",
                  fm_extra={"takeaway": OPERATOR_TAKEAWAY if start == "operator" else _ANALYST_TRUE_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    faults = WriteFaults(tmp_path)

    with faults.fail_at(stop):
        stopped = _evaluator_rerun(tmp_path, "false")
    assert faults.fired and stopped.exit_code == 1, stopped.output

    operator_takeaway, written_for = (OPERATOR_TAKEAWAY, "true") if start == "operator" else (None, None)
    if edit:
        written_for = _fm(claim)["verdict"]
        operator_takeaway = f"Later operator takeaway for {written_for}."
        _set_fm(claim, takeaway=operator_takeaway)
    if then == "retry-then-analyst":
        retried = _evaluator_rerun(tmp_path, "false")
        assert retried.exit_code == 0, retried.output
        assert _fm(claim)["verdict"] == "false"
        assert _sidecar(claim)["audit"]["pipeline_verdict"] == "false"

    analyst_verdict = (written_for or "true") if analyst_agrees else ("false" if written_for == "true" else "true")
    with scripted_agents(analyst={**analyst_args(verdict=analyst_verdict), "takeaway": "New analyst takeaway."}):
        ran = _rerun(tmp_path, "analyst")

    assert ran.exit_code == 0, ran.output
    fm = _fm(claim)
    assert fm["verdict"] == analyst_verdict
    kept = operator_takeaway is not None and analyst_verdict == written_for
    assert fm["takeaway"] == (operator_takeaway if kept else "New analyst takeaway.")


def test_a_verdict_hand_edited_back_to_the_one_an_evaluator_rewrite_replaced_keeps_an_operator_takeaway_for_it(
    tmp_path,
) -> None:
    """After a TRUE-to-FALSE rewrite the record names TRUE as the verdict it replaced. A claim
    showing TRUE again (a hand edit here, a stop before the claim write in the stop cases) is
    read with TRUE as the record's verdict, so a takeaway written for it is kept."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    _flip(tmp_path, "false")
    _set_fm(claim, verdict="true", takeaway="Hand-edited takeaway for TRUE.")

    with scripted_agents(analyst={**analyst_args(verdict="true"), "takeaway": "New analyst takeaway."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == "Hand-edited takeaway for TRUE."


def test_a_verdict_hand_edited_to_a_third_verdict_leaves_an_operator_takeaway_judged_against_the_recorded_verdict(
    tmp_path,
) -> None:
    """The record says FALSE and the rewrite replaced TRUE; a claim hand-edited to MIXED matches
    neither, so the usual rule holds: the operator's takeaway is kept only while the analyst
    returns the record's verdict (FALSE), and MIXED replaces it."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    _flip(tmp_path, "false")
    _set_fm(claim, verdict="mixed", takeaway="Hand-edited takeaway for MIXED.")

    with scripted_agents(analyst={**analyst_args(verdict="mixed"), "takeaway": "New analyst takeaway."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == "New analyst takeaway."


@pytest.mark.parametrize(("analyst_verdict", "kept"), [("false", False), ("true", True)])
def test_with_no_evaluator_rewrite_a_hand_edited_verdict_leaves_an_operator_takeaway_judged_against_the_recorded_verdict(
    tmp_path, analyst_verdict, kept,
) -> None:
    """The analyst recorded TRUE; an operator hand-edits the claim to FALSE and writes a takeaway.
    As before the Evaluator rewrite existed, the takeaway is kept while the analyst returns the
    recorded verdict (TRUE) and replaced when it returns the hand-edited one."""
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": _ANALYST_TRUE_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    _set_fm(claim, verdict="false", takeaway="Hand-edited takeaway for FALSE.")

    with scripted_agents(analyst={**analyst_args(verdict=analyst_verdict), "takeaway": "New analyst takeaway."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == ("Hand-edited takeaway for FALSE." if kept else "New analyst takeaway.")


def test_a_verdict_changing_evaluator_rerun_keeps_the_level_fit_note_and_the_other_agents_models(tmp_path) -> None:
    claim = _repo(tmp_path, verdict="true", confidence="high")

    _flip(tmp_path, "false")

    sidecar = _sidecar(claim)
    assert sidecar["pipeline_run"]["level_clamp"] == FIT_NOTE
    assert {"researcher", "ingestor", "analyst"} <= set(sidecar["models_used"])


def test_a_full_forced_rerun_after_a_verdict_changing_evaluator_rerun_replaces_the_old_takeaway(tmp_path) -> None:
    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    _flip(tmp_path, "false")
    assert _fm(claim)["takeaway"] == OPERATOR_TAKEAWAY

    with scripted_agents(analyst=_analyst_false_with_takeaway(), auditor=auditor_args(verdict="false")):
        result = _dr(tmp_path, "draft", "--claim", REF, "--force", "--skip-wayback")

    assert result.exit_code == 0, result.output
    assert (_fm(claim)["verdict"], _fm(claim)["takeaway"]) == ("false", "Analyst takeaway for FALSE.")


@pytest.mark.parametrize("promote_first", [False, True], ids=["pending", "promoted"])
def test_a_recheck_after_a_verdict_changing_evaluator_rerun_on_a_published_claim_replaces_the_old_takeaway(
    tmp_path, promote_first,
) -> None:
    from orchestrator.persistence import promote_pending

    live = _repo(tmp_path, status="published", verdict="true", confidence="high",
                 fm_extra={"takeaway": OPERATOR_TAKEAWAY},
                 sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    _flip(tmp_path, "false")
    pending = _claim_path(tmp_path, "pending")
    assert _fm(pending)["verdict"] == "false"
    if promote_first:
        promote_pending(live, tmp_path)
        _set_fm(live, status="published")

    with scripted_agents(analyst=_analyst_false_with_takeaway(), auditor=auditor_args(verdict="false")):
        result = _dr(tmp_path, "recheck", "--claim", REF, "--skip-wayback")

    assert result.exit_code == 0, result.output
    assert (_fm(pending)["verdict"], _fm(pending)["takeaway"]) == ("false", "Analyst takeaway for FALSE.")


@pytest.mark.parametrize("stop", range(len(EVALUATOR_SAME_WRITES)), ids=lambda n: f"stop{n}")
def test_an_evaluator_rerun_that_keeps_the_verdict_stopped_at_any_write_keeps_an_operator_takeaway(tmp_path, stop) -> None:
    from tests.write_faults import WriteFaults

    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": _ANALYST_TRUE_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    faults = WriteFaults(tmp_path)
    with faults.fail_at(stop):
        stopped = _evaluator_rerun(tmp_path, "true")
    assert faults.fired and stopped.exit_code == 1, stopped.output
    _set_fm(claim, takeaway="Later operator takeaway for TRUE.")
    assert _evaluator_rerun(tmp_path, "true").exit_code == 0

    with scripted_agents(analyst={**analyst_args(verdict="true"), "takeaway": "New analyst takeaway."}):
        ran = _rerun(tmp_path, "analyst")

    assert ran.exit_code == 0, ran.output
    assert _fm(claim)["takeaway"] == "Later operator takeaway for TRUE."


def test_an_operator_takeaway_is_lost_when_an_analyst_rerun_stopped_between_its_claim_and_record_writes(tmp_path) -> None:
    """Pins a loss outside the Evaluator fix (the same write order as before this item). The
    analyst rerun writes the claim (FALSE) and stops before the record (still TRUE); a takeaway
    the operator then writes for FALSE is replaced by the next analyst rerun that agrees."""
    from tests.write_faults import WriteFaults

    claim = _repo(tmp_path, verdict="true", confidence="high", fm_extra={"takeaway": _ANALYST_TRUE_TAKEAWAY},
                  sidecar_extra={"analyst_record": dict(ANALYST_RECORD_TRUE)})
    faults = WriteFaults(tmp_path)
    with faults.fail_at(2):
        with scripted_agents(analyst={**analyst_args(verdict="false"), "takeaway": "Analyst takeaway for FALSE."}):
            stopped = _rerun(tmp_path, "analyst")
    assert stopped.exit_code == 1, stopped.output
    assert faults.writes[-1] == ("write", f"{_CLAIM_DIR}/{STEM}.audit.yaml")
    assert (_fm(claim)["verdict"], _sidecar(claim)["analyst_record"]["verdict"]) == ("false", "true")
    _set_fm(claim, takeaway="Operator takeaway for FALSE.")

    with scripted_agents(analyst={**analyst_args(verdict="false"), "takeaway": "New analyst takeaway."}):
        result = _rerun(tmp_path, "analyst")

    assert result.exit_code == 0, result.output
    assert _fm(claim)["takeaway"] == "New analyst takeaway."
