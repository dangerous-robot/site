"""Acceptance tests for the five-command `dr` set, `dr lint --prune`, the committed hook and
the end of the `blocked` claim status (RE-AX, Fold side tools).

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ SP7 (Fold side tools), "Tests that prove it"; design
``handoff/2026-10-15-re-ax-design.md``). Replaces ``test_cli_smoke.py``
(hard-coded cwd, hidden aliases) with ``CliRunner`` calls.

Shapes pinned here (the design's § 2):

- ``dr --help`` lists exactly ``draft``, ``recheck``, ``review``,
  ``findings`` and ``lint`` under Click's plain ``Commands:`` heading (no
  write-semantics groups); every removed name exits non-zero;
- ``dr lint --prune`` deletes every ``unreferenced-source`` file (and a year
  directory it empties) and nothing else; a source cited only by a pending
  draft under ``research/pending/`` is referenced;
- ``tasks.py`` reaches the linter only through ``dr lint``;
  ``scripts/git-hooks/pre-commit`` runs ``.venv/bin/dr lint`` and fails when
  ``dr`` is missing;
- ``status: blocked`` is not a claim status: ``ClaimStatus`` has no
  ``blocked`` member, ``dr lint`` reports it as an error
  (``invalid-claim-status``), and the site schema's status enum drops it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from common.frontmatter import serialize_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[2]
FIVE = ["draft", "findings", "lint", "recheck", "review"]
REMOVED = [
    "step-research", "step-ingest", "ingest", "step-analyze", "step-audit", "reassess", "stats",
    "claim-probe", "claim-draft", "claim-refresh", "claim-promote", "entity-enrich", "onboard",
    "review-queue", "publish", "wayback-backfill",
]


def _main():
    from orchestrator.cli import main

    return main


def _listed_commands(help_text: str) -> list[str]:
    """Command names under every section after ``Options:`` in ``dr --help``."""
    lines = help_text.splitlines()
    names: list[str] = []
    in_commands = False
    for line in lines:
        if re.match(r"^\S.*:$", line):
            in_commands = line.strip() != "Options:"
            continue
        if in_commands:
            m = re.match(r"^  (\S+)", line)
            if m:
                names.append(m.group(1))
    return sorted(names)


# --------------------------------------------------------------------------- #
# Five commands                                                                #
# --------------------------------------------------------------------------- #


def test_dr_help_lists_exactly_the_five_commands_under_one_heading() -> None:
    result = CliRunner().invoke(_main(), ["--help"])

    assert result.exit_code == 0, result.output
    assert _listed_commands(result.output) == FIVE
    headings = [ln for ln in result.output.splitlines() if re.match(r"^\S.*:$", ln)]
    assert headings == ["Options:", "Commands:"]


@pytest.mark.parametrize("name", FIVE)
def test_each_command_has_help(name: str) -> None:
    result = CliRunner().invoke(_main(), [name, "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


@pytest.mark.parametrize("name", REMOVED)
def test_a_removed_command_exits_non_zero(name: str) -> None:
    result = CliRunner().invoke(_main(), [name, "--help"])

    assert result.exit_code != 0, f"dr {name} still exists"


def test_dr_draft_help_names_rerun_and_source() -> None:
    result = CliRunner().invoke(_main(), ["draft", "--help"])

    assert result.exit_code == 0, result.output
    assert "--rerun [analyst|evaluator]" in result.output
    assert "--source" in result.output


def test_dr_lint_help_names_prune() -> None:
    result = CliRunner().invoke(_main(), ["lint", "--help"])

    assert result.exit_code == 0, result.output
    assert "--prune" in result.output


def test_the_side_tool_modules_are_gone() -> None:
    pipeline = REPO_ROOT / "pipeline"
    gone = [
        pipeline / "orchestrator" / "pipeline.py",
        pipeline / "orchestrator" / "stats.py",
        pipeline / "linter" / "__main__.py",
        pipeline / "linter" / "prune.py",
        REPO_ROOT / "scripts" / "backfill_analyst_record.py",
        REPO_ROOT / "scripts" / "rerun_v1_claims.py",
        REPO_ROOT / "research" / "QUEUE.md",
    ]
    assert [str(p.relative_to(REPO_ROOT)) for p in gone if p.exists()] == []


# --------------------------------------------------------------------------- #
# dr lint --prune                                                              #
# --------------------------------------------------------------------------- #


def _source(root: Path, sid: str) -> Path:
    path = root / "research" / "sources" / f"{sid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_frontmatter(
        {"url": f"https://example.org/{sid.replace('/', '-')}", "title": sid, "publisher": "Example",
         "accessed_date": "2026-10-01", "kind": "report", "independence": "independent",
         "summary": "A summary."}, "Body.\n"), encoding="utf-8")
    return path


def _claim(root: Path, base: str, sources: list[str]) -> Path:
    entity = root / "research" / "entities" / "subjects" / "probe-subject.md"
    entity.parent.mkdir(parents=True, exist_ok=True)
    entity.write_text("---\nname: Probe Subject\ntype: subject\ndescription: A test entity.\n---\n", encoding="utf-8")
    path = root / "research" / base / "subjects" / "probe-subject" / "probe-claim.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_frontmatter(
        {"title": "Probe claim", "statement": "Probe claim", "entity": "subjects/probe-subject",
         "topics": ["environmental-impact"], "verdict": "mixed", "confidence": "medium",
         "status": "draft", "as_of": "2026-10-01", "sources": sources}, "Body.\n"), encoding="utf-8")
    return path


def test_lint_prune_deletes_only_unreferenced_sources(tmp_path) -> None:
    cited = _source(tmp_path, "2026/cited")
    orphan = _source(tmp_path, "2026/orphan")
    lone = _source(tmp_path, "2024/lone-orphan")
    _claim(tmp_path, "claims", ["2026/cited"])

    result = CliRunner().invoke(_main(), ["lint", "--prune", "--repo-root", str(tmp_path)])

    assert cited.exists()
    assert not orphan.exists()
    assert not lone.exists()
    assert not lone.parent.exists(), "a year directory the prune emptied is removed"
    assert "2026/orphan" in result.output or str(orphan) in result.output


def test_lint_prune_keeps_a_source_cited_only_by_a_pending_draft(tmp_path) -> None:
    """RE-AW (Recheck) lint rule: a pending draft's sources are referenced."""
    live_only = _source(tmp_path, "2026/live-only")
    pending_only = _source(tmp_path, "2026/pending-only")
    orphan = _source(tmp_path, "2026/orphan")
    _claim(tmp_path, "claims", ["2026/live-only"])
    _claim(tmp_path, "pending", ["2026/pending-only"])

    CliRunner().invoke(_main(), ["lint", "--prune", "--repo-root", str(tmp_path)])

    assert not orphan.exists(), "control: the prune ran"
    assert live_only.exists()
    assert pending_only.exists()


def test_lint_format_summary_prints_the_summary_report(tmp_path) -> None:
    """`inv audit` printed `python -m linter`'s summary; it now runs `dr lint --format summary`
    (an added choice; CI's `--format json --severity error` is unchanged)."""
    from linter.report import format_summary_report
    from linter.runner import run_all_checks

    _source(tmp_path, "2026/orphan")
    _claim(tmp_path, "claims", [])
    issues, checked = run_all_checks(tmp_path)

    result = CliRunner().invoke(_main(), ["lint", "--format", "summary", "--repo-root", str(tmp_path)])

    assert result.output.strip() == format_summary_report(issues, checked, "info").strip()


def test_lint_without_prune_deletes_nothing(tmp_path) -> None:
    orphan = _source(tmp_path, "2026/orphan")
    _claim(tmp_path, "claims", [])

    result = CliRunner().invoke(_main(), ["lint", "--repo-root", str(tmp_path)])

    assert orphan.exists()
    assert "unreferenced-source" in result.output


# --------------------------------------------------------------------------- #
# One lint entry point: tasks.py and the committed hook                        #
# --------------------------------------------------------------------------- #


def test_tasks_py_reaches_the_linter_only_through_dr_lint() -> None:
    text = (REPO_ROOT / "tasks.py").read_text(encoding="utf-8")

    assert "python -m linter" not in text
    assert "dr lint" in text
    assert "dr lint --prune" in text


HOOK = REPO_ROOT / "scripts" / "git-hooks" / "pre-commit"


def test_the_pre_commit_hook_is_committed_and_calls_dr_lint_from_the_root_venv() -> None:
    assert HOOK.exists(), "scripts/git-hooks/pre-commit is not written yet"
    assert os.access(HOOK, os.X_OK), "the hook must be executable"
    text = HOOK.read_text(encoding="utf-8")
    assert ".venv/bin/dr" in text
    assert "pipeline/.venv" not in text
    assert re.search(r"\bdr\"?\s+lint\b|\$DR\"?\s+lint\b", text)


def test_the_pre_commit_hook_fails_when_dr_is_missing(tmp_path) -> None:
    """The untracked hook exited 0 when `dr` was missing, so a venv move silently skipped lint
    (plan § Risks, two venvs row)."""
    assert HOOK.exists(), "scripts/git-hooks/pre-commit is not written yet"
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result = subprocess.run(["bash", str(HOOK)], cwd=tmp_path, env=env, capture_output=True, text=True,
                            timeout=60)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "dr" in (result.stdout + result.stderr)


# --------------------------------------------------------------------------- #
# status: blocked is not a claim status                                        #
# --------------------------------------------------------------------------- #


def test_claim_status_has_no_blocked_member() -> None:
    from common.models import ClaimStatus

    assert sorted(s.value for s in ClaimStatus) == ["archived", "draft", "published"]
    with pytest.raises(ValueError):
        ClaimStatus("blocked")


def test_lint_reports_a_blocked_claim_as_an_error(tmp_path) -> None:
    path = _claim(tmp_path, "claims", [])
    text = path.read_text(encoding="utf-8").replace("status: draft", "status: blocked")
    path.write_text(text, encoding="utf-8")

    result = CliRunner().invoke(_main(), ["lint", "--format", "json", "--severity", "error",
                                          "--repo-root", str(tmp_path)])

    assert result.exit_code == 1, result.output
    issues = yaml.safe_load(result.output)
    assert any(i["check_id"] == "invalid-claim-status" and i["path"].endswith("probe-claim.md") for i in issues)


def test_lint_accepts_the_three_claim_statuses(tmp_path) -> None:
    from linter.runner import run_all_checks

    path = _claim(tmp_path, "claims", [])
    for status in ("draft", "published", "archived"):
        path.write_text(path.read_text(encoding="utf-8").replace(
            re.search(r"status: \w+", path.read_text(encoding="utf-8")).group(0), f"status: {status}"),
            encoding="utf-8")
        issues, _ = run_all_checks(tmp_path)
        assert not [i for i in issues if i.check_id == "invalid-claim-status"], status


def test_the_site_schema_status_enum_drops_blocked() -> None:
    """Text check of `src/content.config.ts`; the build-level proof is the verify step's command."""
    text = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    # The claim status enum is the one defaulting to draft (the archive record has its own `status`).
    [enum] = re.findall(r"status: z\.enum\(\[([^\]]*)\]\)\.default\('draft'\)", text)
    assert sorted(v.strip().strip("'\"") for v in enum.split(",")) == ["archived", "draft", "published"]
    assert "blocked_reason" not in text


@pytest.mark.parametrize("args", [["--force"], ["--rerun", "analyst"], ["--rerun", "evaluator"]])
def test_a_claim_with_an_unknown_status_is_refused_before_any_model_call(tmp_path, monkeypatch, args) -> None:
    """The writer refuses a claim whose status is not draft, published or archived; the
    command refuses it first, so no paid run ends in a half-claim finding."""
    import loop

    called: list[str] = []

    async def _tripwire(*_a, **_kw):
        called.append("loop")
        raise AssertionError("no loop entry for a claim the writer refuses")

    monkeypatch.setattr(loop, "run", _tripwire)
    monkeypatch.setattr(loop, "rerun", _tripwire)
    path = _claim(tmp_path, "claims", [])
    path.write_text(path.read_text(encoding="utf-8").replace("status: draft", "status: blocked"), encoding="utf-8")
    before = path.read_bytes()

    result = CliRunner().invoke(_main(), [
        "--model", "test", "draft", "--claim", "subjects/probe-subject/probe-claim", *args,
        "--repo-root", str(tmp_path),
    ])

    assert result.exit_code == 1, result.output
    assert "not draft, published or archived" in result.output
    assert called == []
    assert path.read_bytes() == before
    assert not (tmp_path / "research" / "findings").exists()


def test_lint_prune_refuses_while_lint_reports_an_error(tmp_path) -> None:
    """A claim that does not parse cites nothing lint can see, so `--prune` deletes nothing
    while any error is reported; the control fixes the claim and the prune runs."""
    cited = _source(tmp_path, "2026/cited")
    orphan = _source(tmp_path, "2026/orphan")
    claim = _claim(tmp_path, "claims", ["2026/cited"])
    good = claim.read_text(encoding="utf-8")
    claim.write_text("Body with no frontmatter.\n", encoding="utf-8")

    result = CliRunner().invoke(_main(), ["lint", "--prune", "--repo-root", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "Not pruning" in result.output
    assert cited.exists() and orphan.exists()

    claim.write_text(good, encoding="utf-8")
    CliRunner().invoke(_main(), ["lint", "--prune", "--repo-root", str(tmp_path)])
    assert cited.exists() and not orphan.exists()
