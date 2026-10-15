"""Acceptance tests for RE-AT (Rules, findings file, tie-breaker): the findings file and ``dr findings``.

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ End state, The findings file, and § SP2 (Rules, findings file, tie-breaker)).
The record is ``common.findings.Finding``; the writer and readers are public
functions in ``orchestrator.persistence``; the command is ``dr findings``
under ``CliRunner``.

Covered:

- ``write_finding`` writes ``research/findings/<yyyy>/<run-id>.yaml`` with the
  plan's keys in the plan's order; ``load_findings`` reads open records (and
  closed ones on request); ``close_finding`` records a hand triage;
- ``dr findings`` lists open findings, ``--all`` includes closed ones,
  ``--summary`` counts by step, rule and outcome, ``--close <id> --note``
  records the note (``--note`` required; an unknown id is an error; a unique
  prefix is accepted);
- ``dr findings`` lists half-claims: claims without a sidecar and subject
  records with no claim, and deletes nothing.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from click.testing import CliRunner

RUN_A = "a06d7a7e3fea4120b0d1f879bec059e1"
RUN_B = "b16d7a7e3fea4120b0d1f879bec059e2"
RUN_C = "c26d7a7e3fea4120b0d1f879bec059e3"


def _finding(run_id: str = RUN_A, **overrides):
    from common.findings import Finding

    fields = dict(
        run_id=run_id,
        date=datetime.date(2026, 10, 20),
        command="dr draft",
        claim_spec={
            "statement": "In 2024, US data centers got more electricity from gas than renewables.",
            "entity": "subjects/us-data-centers",
            "criteria_slug": None,
            "topics": ["environmental-impact"],
            "grading_rule": None,
        },
        claim_ref=None,
        config={"max_sources": 8, "candidate_pool_size": 32, "max_initial_queries": 7,
                "search_backend": "tavily", "research_origins": ["tavily", "arxiv"], "model": "test",
                "skip_wayback": True},
        models_used={"researcher": "test", "ingestor": "test"},
        step="ingest",
        rule="flaw-retry",
        error={"error_type": "insufficient_sources", "message": "3 usable sources, 4 needed"},
        attempts=2,
        outcome="abandoned",
    )
    fields.update(overrides)
    return Finding(**fields)


def _findings_cli(tmp_path: Path, *args: str):
    from orchestrator.cli import main

    return CliRunner().invoke(main, ["findings", "--repo-root", str(tmp_path), *args])


# --------------------------------------------------------------------------- #
# The record and the writer                                                        #
# --------------------------------------------------------------------------- #


def test_write_finding_lands_at_the_plan_path_with_the_plan_keys(tmp_path) -> None:
    from orchestrator.persistence import write_finding

    path = write_finding(_finding(), tmp_path)
    assert path == tmp_path / "research" / "findings" / "2026" / f"{RUN_A}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    expected_order = [
        "run_id", "date", "command", "claim_spec", "claim_ref", "config", "models_used",
        "step", "rule", "error", "attempts", "outcome", "closed",
    ]
    assert [k for k in data if k in expected_order] == expected_order
    assert data["run_id"] == RUN_A
    assert str(data["date"]) == "2026-10-20"
    assert data["command"] == "dr draft"
    assert data["claim_spec"]["entity"] == "subjects/us-data-centers"
    assert data["claim_ref"] is None
    assert data["error"] == {"error_type": "insufficient_sources", "message": "3 usable sources, 4 needed"}
    assert data["attempts"] == 2
    assert data["outcome"] == "abandoned"
    assert data["closed"] is None


def test_write_finding_takes_the_command_from_the_caller(tmp_path) -> None:
    from orchestrator.persistence import write_finding

    path = write_finding(_finding(command=None), tmp_path, command="dr recheck")
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["command"] == "dr recheck"


def test_load_and_close_findings(tmp_path) -> None:
    from orchestrator.persistence import close_finding, load_findings, write_finding

    write_finding(_finding(RUN_A), tmp_path)
    write_finding(_finding(RUN_B, step="analyse", outcome="recovered", attempts=2), tmp_path)
    assert [f.run_id for f in load_findings(tmp_path)] == [RUN_A, RUN_B]

    path = close_finding(tmp_path, RUN_A, note="model variance; replay later")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["closed"]["by"] == "hand"
    assert data["closed"]["note"] == "model variance; replay later"
    assert str(data["closed"]["date"]) == datetime.date.today().isoformat()

    assert [f.run_id for f in load_findings(tmp_path)] == [RUN_B]
    assert [f.run_id for f in load_findings(tmp_path, include_closed=True)] == [RUN_A, RUN_B]
    assert load_findings(tmp_path / "nowhere") == []


def test_finding_round_trips_through_its_dict(tmp_path) -> None:
    from common.findings import Finding

    original = _finding(claim_ref="subjects/us-data-centers/gas-vs-renewables")
    assert Finding.from_dict(original.to_dict()) == original


# --------------------------------------------------------------------------- #
# dr findings                                                                       #
# --------------------------------------------------------------------------- #


def test_dr_findings_with_nothing_recorded(tmp_path) -> None:
    (tmp_path / "research" / "claims").mkdir(parents=True)
    result = _findings_cli(tmp_path)
    assert result.exit_code == 0, result.output
    assert "no open findings" in result.output.lower()


def test_dr_findings_lists_open_records_and_all_includes_closed(tmp_path) -> None:
    from orchestrator.persistence import close_finding, write_finding

    (tmp_path / "research" / "claims").mkdir(parents=True)
    write_finding(_finding(RUN_A), tmp_path)
    write_finding(_finding(RUN_B, step="analyse", rule="transport-retry", outcome="recovered",
                           error={"error_type": "timeout", "message": "Analyst timed out"}), tmp_path)
    write_finding(_finding(RUN_C, step="tiebreak", rule="tiebreaker", outcome="split",
                           error={"error_type": "verdict_split", "message": "analyst mixed, evaluator true, tie-breaker true"}),
                  tmp_path)
    close_finding(tmp_path, RUN_C, note="seen")

    result = _findings_cli(tmp_path)
    assert result.exit_code == 0, result.output
    assert RUN_A in result.output and RUN_B in result.output
    assert RUN_C not in result.output
    for word in ("2026-10-20", "dr draft", "ingest", "flaw-retry", "abandoned", "insufficient_sources",
                 "3 usable sources, 4 needed", "analyse", "transport-retry", "recovered", "timeout"):
        assert word in result.output, word

    everything = _findings_cli(tmp_path, "--all")
    assert everything.exit_code == 0
    assert RUN_C in everything.output
    assert "seen" in everything.output


def test_dr_findings_summary_counts_by_step_rule_and_outcome(tmp_path) -> None:
    from orchestrator.persistence import close_finding, write_finding

    (tmp_path / "research" / "claims").mkdir(parents=True)
    write_finding(_finding(RUN_A), tmp_path)
    write_finding(_finding(RUN_B, step="ingest", rule="transport-retry", outcome="abandoned"), tmp_path)
    write_finding(_finding(RUN_C, step="analyse", rule="flaw-retry", outcome="recovered"), tmp_path)
    close_finding(tmp_path, RUN_C, note="seen")

    result = _findings_cli(tmp_path, "--summary")
    assert result.exit_code == 0, result.output
    out = result.output
    assert "open: 2" in out and "closed: 1" in out
    assert "ingest: 2" in out
    assert "flaw-retry: 1" in out and "transport-retry: 1" in out
    assert "abandoned: 2" in out


def test_dr_findings_close_records_the_note(tmp_path) -> None:
    from orchestrator.persistence import write_finding

    (tmp_path / "research" / "claims").mkdir(parents=True)
    write_finding(_finding(RUN_A), tmp_path)

    missing_note = _findings_cli(tmp_path, "--close", RUN_A)
    assert missing_note.exit_code == 2
    assert "--note" in missing_note.output

    unknown = _findings_cli(tmp_path, "--close", "f" * 32, "--note", "x")
    assert unknown.exit_code == 1
    assert "f" * 32 in unknown.output

    closed = _findings_cli(tmp_path, "--close", RUN_A[:8], "--note", "replayed by hand, fine")
    assert closed.exit_code == 0, closed.output
    data = yaml.safe_load((tmp_path / "research" / "findings" / "2026" / f"{RUN_A}.yaml").read_text(encoding="utf-8"))
    assert data["closed"]["note"] == "replayed by hand, fine"
    assert data["closed"]["by"] == "hand"

    again = _findings_cli(tmp_path, "--close", RUN_A, "--note", "twice")
    assert again.exit_code == 1
    assert "closed" in again.output.lower()


# --------------------------------------------------------------------------- #
# Half-claims                                                                        #
# --------------------------------------------------------------------------- #


def _half_claim_tree(tmp_path: Path) -> None:
    claims = tmp_path / "research" / "claims"
    (claims / "subjects" / "probe-sp2").mkdir(parents=True)
    (claims / "subjects" / "probe-sp2" / "half.md").write_text(
        "---\ntitle: Half\nentity: subjects/probe-sp2\nstatus: draft\n---\nBody.\n", encoding="utf-8",
    )
    (claims / "subjects" / "whole").mkdir(parents=True)
    (claims / "subjects" / "whole" / "whole.md").write_text(
        "---\ntitle: Whole\nentity: subjects/whole\nstatus: draft\n---\nBody.\n", encoding="utf-8",
    )
    (claims / "subjects" / "whole" / "whole.audit.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    subjects = tmp_path / "research" / "entities" / "subjects"
    subjects.mkdir(parents=True)
    for slug in ("probe-sp2", "whole", "orphan"):
        (subjects / f"{slug}.md").write_text(f"---\nname: {slug}\ntype: subject\ndescription: d\n---\n", encoding="utf-8")


def test_half_claims_lists_claims_without_a_sidecar_and_subjects_without_a_claim(tmp_path) -> None:
    from orchestrator.persistence import half_claims

    _half_claim_tree(tmp_path)
    found = half_claims(tmp_path)
    assert found["claims_without_sidecar"] == ["subjects/probe-sp2/half"]
    assert found["subjects_without_claim"] == ["subjects/orphan"]


def test_dr_findings_lists_half_claims_and_deletes_nothing(tmp_path) -> None:
    _half_claim_tree(tmp_path)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())

    result = _findings_cli(tmp_path)
    assert result.exit_code == 0, result.output
    assert "subjects/probe-sp2/half" in result.output
    assert "dr draft --claim subjects/probe-sp2/half --force" in result.output
    assert "subjects/orphan" in result.output
    assert "whole" not in result.output.replace("subjects/whole", "")
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert after == before
