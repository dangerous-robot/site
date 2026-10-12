"""scripts/backfill_analyst_record.py: the sidecar's analyst record from git.

The record must come from the claim's last pipeline-written version, so an
approval or a hand edit committed later is not mistaken for the analyst's
text, and the dry run must write nothing.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_analyst_record.py"

CLAIM_REL = "research/claims/acme/green.md"
SIDECAR_REL = "research/claims/acme/green.audit.yaml"


def _load_script():
    spec = importlib.util.spec_from_file_location("backfill_analyst_record", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the module through sys.modules while the class is built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.org")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def _claim(status="draft", takeaway="Analyst takeaway.", seo_title="Analyst seo",
           cap_rationale="Analyst cap.", verdict="true", title="Acme is green") -> str:
    fm = {
        "title": title, "entity": "companies/acme", "verdict": verdict,
        "confidence": "low", "verification_level": "claimed",
        "cap_rationale": cap_rationale, "takeaway": takeaway, "seo_title": seo_title,
        "status": status,
    }
    return "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\nBody.\n"


def _sidecar(ran_at="2026-10-10T00:00:00+00:00", agents=("researcher", "ingestor", "analyst", "auditor"),
             reviewed_at=None) -> str:
    return yaml.safe_dump({
        "schema_version": 1,
        "pipeline_run": {"ran_at": ran_at, "model": "m", "agents": list(agents)},
        "models_used": {a: "m" for a in agents},
        "sources_consulted": [],
        "audit": None,
        "human_review": {"reviewed_at": reviewed_at, "reviewer": None, "notes": None, "pr_url": None},
    }, sort_keys=False)


def _commit(repo: Path, message: str, claim: str | None = None, sidecar: str | None = None) -> str:
    for rel, text in ((CLAIM_REL, claim), (SIDECAR_REL, sidecar)):
        if text is not None:
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "--short", "HEAD").strip()


def _rows(repo: Path):
    return _load_script().plan(repo)


def test_skips_approval_and_hand_edit_commits(repo):
    pipeline = _commit(repo, "drafts", _claim(), _sidecar())
    _commit(repo, "publish", _claim(status="published"), _sidecar(reviewed_at="2026-10-11"))
    _commit(repo, "hand edit", _claim(status="published", takeaway="Operator takeaway."))

    [row] = _rows(repo)

    assert row.claim == CLAIM_REL
    assert row.commit == pipeline
    assert row.record == {
        "title": "Acme is green", "seo_title": "Analyst seo", "verdict": "true",
        "takeaway": "Analyst takeaway.", "cap_rationale": "Analyst cap.",
    }
    assert row.differs == ["takeaway"]


def test_a_new_pipeline_run_in_a_later_commit_is_chosen(repo):
    _commit(repo, "first run", _claim(), _sidecar())
    second = _commit(
        repo, "rerun and publish", _claim(status="published", takeaway="Second takeaway."),
        _sidecar(ran_at="2026-10-11T00:00:00+00:00"),
    )

    [row] = _rows(repo)

    assert row.commit == second
    assert row.record["takeaway"] == "Second takeaway."
    assert row.differs == []


@pytest.mark.parametrize("agents", [("auditor",), ("researcher", "ingestor")])
def test_runs_without_the_analyst_are_not_pipeline_written(repo, agents):
    first = _commit(repo, "first run", _claim(), _sidecar())
    # A re-audit or a blocked run rewrites the sidecar, not the analyst's text.
    _commit(repo, "rerun", _claim(takeaway="Edited."), _sidecar(ran_at="2026-10-12T00:00:00+00:00", agents=agents))

    [row] = _rows(repo)

    assert row.commit == first


def test_a_blocked_version_is_not_pipeline_written(repo):
    first = _commit(repo, "first run", _claim(), _sidecar())
    _commit(
        repo, "blocked", _claim(status="blocked"),
        _sidecar(ran_at="2026-10-12T00:00:00+00:00", agents=("researcher", "ingestor", "analyst")),
    )

    [row] = _rows(repo)

    assert row.commit == first


def test_claim_with_no_pipeline_written_version_is_reported_and_skipped(repo):
    _commit(repo, "hand-written claim, then a re-audit", _claim(), _sidecar(agents=("auditor",)))

    [row] = _rows(repo)

    assert row.commit is None
    assert row.record is None
    assert row.skip == "no pipeline-written version in git"


def test_claim_whose_sidecar_has_a_record_is_skipped(repo):
    sidecar = yaml.safe_load(_sidecar())
    sidecar["analyst_record"] = {"title": "Acme is green", "seo_title": "Analyst seo"}
    _commit(repo, "run", _claim(), yaml.safe_dump(sidecar))

    [row] = _rows(repo)

    assert row.skip and "already" in row.skip


def test_missing_takeaway_and_cap_rationale_are_recorded_as_the_analyst_left_them(repo):
    _commit(repo, "run", _claim(takeaway=None, cap_rationale=None), _sidecar())

    [row] = _rows(repo)

    assert "takeaway" not in row.record
    assert row.record["cap_rationale"] is None


def test_dry_run_writes_nothing_and_prints_one_row_per_claim(repo, capsys, monkeypatch):
    _commit(repo, "run", _claim(), _sidecar())
    before = (repo / SIDECAR_REL).read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["backfill_analyst_record.py", "--repo-root", str(repo)])

    assert _load_script().main() == 0

    assert (repo / SIDECAR_REL).read_text(encoding="utf-8") == before
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith(CLAIM_REL)]
    assert len(lines) == 1


def test_write_adds_only_the_record(repo, monkeypatch):
    _commit(repo, "run", _claim(), _sidecar())
    _commit(repo, "hand edit", _claim(takeaway="Operator takeaway."))
    before = yaml.safe_load((repo / SIDECAR_REL).read_text(encoding="utf-8"))
    monkeypatch.setattr(sys, "argv", ["backfill_analyst_record.py", "--repo-root", str(repo), "--write"])

    assert _load_script().main() == 0

    after = yaml.safe_load((repo / SIDECAR_REL).read_text(encoding="utf-8"))
    assert after.pop("analyst_record")["takeaway"] == "Analyst takeaway."
    assert after == before


def test_write_leaves_the_rest_of_the_sidecar_text_unchanged(repo, monkeypatch):
    # A re-dump would turn this block scalar into a quoted string.
    sidecar = _sidecar() + "research:\n  scorer_rationale: |-\n    Line one.\n    Line two.\n"
    _commit(repo, "run", _claim(), sidecar)
    monkeypatch.setattr(sys, "argv", ["backfill_analyst_record.py", "--repo-root", str(repo), "--write"])

    assert _load_script().main() == 0

    text = (repo / SIDECAR_REL).read_text(encoding="utf-8")
    assert text.startswith(sidecar)
    assert yaml.safe_load(text[len(sidecar):]) == {"analyst_record": {
        "title": "Acme is green", "seo_title": "Analyst seo", "verdict": "true",
        "takeaway": "Analyst takeaway.", "cap_rationale": "Analyst cap.",
    }}
