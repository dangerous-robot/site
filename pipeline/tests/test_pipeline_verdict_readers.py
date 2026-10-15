"""Acceptance tests for RE-AT (Rules, findings file, tie-breaker): readers of ``pipeline_verdict``.

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ SP2 (Rules, findings file, tie-breaker)). Lint ``verdict-sidecar-mismatch``,
``dr review --approve``'s override logic, the claim page and the site schema
are re-anchored on ``audit.pipeline_verdict`` with one fallback: absent means
``analyst_verdict``. A pre-RE-AT sidecar (a fixture copy of the one on disk
for ``ecosia-ai/renewable-energy-hosting``, which carries no
``pipeline_verdict``) lints clean, approves at the patched tty gate and holds
only keys the schema declares. ``dr lint`` ignores ``research/findings/``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from common.frontmatter import parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "pre_sp2" / "research"
CLAIM_REL = Path("research/claims/ecosia-ai/renewable-energy-hosting.md")
NEW_AUDIT_KEYS = {
    "pipeline_verdict", "pipeline_confidence", "rule_applied",
    "tiebreaker_verdict", "tiebreaker_confidence", "tiebreaker_reasoning",
}


def _p(path: str) -> Path:
    return Path("/tmp/fixtures") / path


def _sidecar(analyst_verdict: str, pipeline_verdict: str | None, override: dict | None = None) -> dict:
    audit: dict = {"analyst_verdict": analyst_verdict}
    if pipeline_verdict is not None:
        audit["pipeline_verdict"] = pipeline_verdict
    return {"audit": audit, "human_review": {"reviewed_at": "2026-10-04", "verdict_override": override}}


def _copy_fixture(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "research")
    return tmp_path / CLAIM_REL


def _declared_audit_keys() -> dict[str, bool]:
    """The ``audit:`` object keys in ``src/content.config.ts`` and whether each is optional."""
    source = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    start = source.index("  audit: z.object({")
    end = source.index("}).nullable()", start)
    block = source[start:end]
    keys: dict[str, bool] = {}
    for line in block.splitlines()[1:]:
        m = re.match(r"\s*(\w+):\s*z\.", line)
        if m:
            keys[m.group(1)] = ".optional()" in line
    assert "analyst_verdict" in keys, "the parse missed the audit block"
    return keys


# --------------------------------------------------------------------------- #
# The one fallback rule                                                            #
# --------------------------------------------------------------------------- #


def test_pipeline_verdict_of_falls_back_to_the_analyst_verdict() -> None:
    from common.sidecar import pipeline_verdict_of

    assert pipeline_verdict_of({"analyst_verdict": "mixed", "pipeline_verdict": "true"}) == "true"
    assert pipeline_verdict_of({"analyst_verdict": "mixed"}) == "mixed"
    assert pipeline_verdict_of(None) is None
    assert pipeline_verdict_of({}) is None


class TestLintReadsPipelineVerdict:
    claim = _p("research/claims/brave/renewable-energy-hosting.md")

    def _issues(self, fm: dict, sidecar: dict | None):
        from linter.checks import check_verdict_sidecar_mismatch

        return check_verdict_sidecar_mismatch([self.claim], {str(self.claim): fm}, {str(self.claim): sidecar})

    def test_published_verdict_equal_to_the_pipeline_verdict_is_clean(self):
        assert self._issues({"status": "published", "verdict": "true"}, _sidecar("mixed", "true")) == []

    def test_published_verdict_equal_to_the_analysts_but_not_the_pipelines_is_an_error(self):
        issues = self._issues({"status": "published", "verdict": "mixed"}, _sidecar("mixed", "true"))
        assert len(issues) == 1
        assert issues[0].check_id == "verdict-sidecar-mismatch"
        assert '"true"' in issues[0].message

    def test_override_from_the_pipeline_verdict_is_accepted(self):
        override = {"from": "true", "to": "mixed"}
        assert self._issues({"status": "published", "verdict": "mixed"}, _sidecar("mixed", "true", override)) == []

    def test_absent_pipeline_verdict_means_the_analysts(self):
        assert self._issues({"status": "published", "verdict": "mixed"}, _sidecar("mixed", None)) == []
        assert len(self._issues({"status": "published", "verdict": "true"}, _sidecar("mixed", None))) == 1


class TestApproveReadsPipelineVerdict:
    def _write(self, tmp_path: Path, verdict: str, sidecar_audit: dict) -> Path:
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True, exist_ok=True)
        claim_md = entity_dir / "test-claim.md"
        claim_md.write_text(
            "---\ntitle: Test\nentity: companies/test-entity\ntopics: [test]\n"
            f"verdict: '{verdict}'\nconfidence: high\nas_of: 2026-04-01\nsources: []\n"
            "status: draft\ncriteria_slug: test-criterion\n---\nBody.\n",
            encoding="utf-8",
        )
        claim_md.with_name("test-claim.audit.yaml").write_text(
            yaml.safe_dump({
                "schema_version": 1,
                "pipeline_run": {"ran_at": "2026-04-22T14:32:00+00:00", "model": "m", "agents": []},
                "sources_consulted": [],
                "audit": sidecar_audit,
                "human_review": {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None},
            }, sort_keys=False),
            encoding="utf-8",
        )
        return claim_md

    def _audit(self, pipeline: str | None) -> dict:
        audit = {
            "analyst_verdict": "mixed", "auditor_verdict": "true", "analyst_confidence": "medium",
            "auditor_confidence": "high", "verdict_agrees": False, "confidence_agrees": False,
            "needs_review": True,
        }
        if pipeline is not None:
            audit["pipeline_verdict"] = pipeline
        return audit

    def test_approving_the_pipeline_verdict_records_no_override(self, tmp_path, human_at_terminal):
        from orchestrator.review import approve_claim

        claim_md = self._write(tmp_path, "true", self._audit("true"))
        approve_claim(claim_md, reviewer="r@example.org", mode="approve")
        data = yaml.safe_load(claim_md.with_name("test-claim.audit.yaml").read_text(encoding="utf-8"))
        assert data["human_review"]["verdict_override"] is None
        assert parse_frontmatter(claim_md.read_text(encoding="utf-8"))[0]["status"] == "published"

    def test_approving_another_verdict_records_the_override_from_the_pipeline_verdict(self, tmp_path, human_at_terminal):
        from orchestrator.review import approve_claim

        claim_md = self._write(tmp_path, "mixed", self._audit("true"))
        approve_claim(claim_md, reviewer="r@example.org", mode="approve")
        data = yaml.safe_load(claim_md.with_name("test-claim.audit.yaml").read_text(encoding="utf-8"))
        assert data["human_review"]["verdict_override"] == {"from": "true", "to": "mixed"}

    def test_without_pipeline_verdict_the_analysts_is_the_anchor(self, tmp_path, human_at_terminal):
        from orchestrator.review import approve_claim

        claim_md = self._write(tmp_path, "mixed", self._audit(None))
        approve_claim(claim_md, reviewer="r@example.org", mode="approve")
        data = yaml.safe_load(claim_md.with_name("test-claim.audit.yaml").read_text(encoding="utf-8"))
        assert data["human_review"]["verdict_override"] is None


# --------------------------------------------------------------------------- #
# A pre-RE-AT sidecar keeps working                                                #
# --------------------------------------------------------------------------- #


class TestPreRebuildSidecar:
    def test_fixture_is_a_pre_rebuild_sidecar(self):
        data = yaml.safe_load((FIXTURE / CLAIM_REL.relative_to("research").with_suffix(".audit.yaml")).read_text(encoding="utf-8"))
        assert "pipeline_verdict" not in data["audit"]
        assert data["audit"]["analyst_verdict"] == "mixed"

    def test_lints_clean(self, tmp_path):
        from linter.runner import run_all_checks

        _copy_fixture(tmp_path)
        issues, files_checked = run_all_checks(tmp_path)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], [f"{i.check_id}: {i.message}" for i in errors]
        assert files_checked >= 10

    def test_approves_at_the_tty_gate(self, tmp_path, human_at_terminal):
        from orchestrator.persistence import set_claim_status
        from orchestrator.review import approve_claim

        claim_md = _copy_fixture(tmp_path)
        set_claim_status(claim_md, "draft", "published")
        approve_claim(claim_md, reviewer="r@example.org", mode="approve")
        fm, _ = parse_frontmatter(claim_md.read_text(encoding="utf-8"))
        assert fm["status"] == "published"
        data = yaml.safe_load(claim_md.with_suffix(".audit.yaml").read_text(encoding="utf-8"))
        assert data["human_review"]["verdict_override"] is None
        assert data["human_review"]["reviewer"] == "r@example.org"

    def test_holds_only_declared_audit_keys(self):
        declared = _declared_audit_keys()
        data = yaml.safe_load((FIXTURE / CLAIM_REL.relative_to("research").with_suffix(".audit.yaml")).read_text(encoding="utf-8"))
        assert set(data["audit"]) <= set(declared)


def test_site_schema_declares_the_new_audit_keys_as_optional() -> None:
    declared = _declared_audit_keys()
    missing = sorted(NEW_AUDIT_KEYS - set(declared))
    assert missing == [], f"src/content.config.ts audit block lacks {missing}"
    required = sorted(k for k in NEW_AUDIT_KEYS if not declared[k])
    assert required == [], f"new keys must be optional so the sidecars on disk validate: {required}"
    assert "analyst_verdict" in declared and not declared["analyst_verdict"], "analyst_verdict keeps its name"


def test_every_sidecar_on_disk_holds_only_declared_audit_keys() -> None:
    declared = set(_declared_audit_keys())
    for path in sorted((REPO_ROOT / "research" / "claims").rglob("*.audit.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        audit = data.get("audit")
        if isinstance(audit, dict):
            assert set(audit) <= declared, f"{path}: {set(audit) - declared}"


def test_claim_page_reads_the_pipeline_verdict_with_the_fallback() -> None:
    page = (REPO_ROOT / "src" / "pages" / "research" / "claims" / "[...slug].astro").read_text(encoding="utf-8")
    assert "pipeline_verdict" in page
    assert "analyst_verdict" in page, "the fallback and the analyst's own line stay"
    assert "tiebreaker_verdict" in page
    assert "tiebreaker" in page.lower()


def test_the_writer_declares_every_audit_key_it_writes() -> None:
    """Every key the sidecar writer puts under ``audit`` is in the Zod schema."""
    import inspect

    from orchestrator import persistence

    source = inspect.getsource(persistence)
    start = source.index("audit_block = {")
    end = source.index("}", start)
    written = set(re.findall(r'"(\w+)":', source[start:end]))
    assert "analyst_verdict" in written
    assert written <= set(_declared_audit_keys()), written - set(_declared_audit_keys())
    assert {"pipeline_verdict", "pipeline_confidence", "rule_applied"} <= written


# --------------------------------------------------------------------------- #
# dr lint ignores research/findings/                                               #
# --------------------------------------------------------------------------- #


def test_lint_ignores_the_findings_directory(tmp_path) -> None:
    from click.testing import CliRunner

    from linter.runner import run_all_checks
    from orchestrator.cli import main

    _copy_fixture(tmp_path)
    before, checked_before = run_all_checks(tmp_path)
    findings_dir = tmp_path / "research" / "findings" / "2026"
    findings_dir.mkdir(parents=True)
    (findings_dir / "a06d7a7e3fea4120b0d1f879bec059e1.yaml").write_text(
        "run_id: a06d7a7e3fea4120b0d1f879bec059e1\ndate: 2026-10-20\ncommand: dr draft\n"
        "step: ingest\nrule: flaw-retry\noutcome: abandoned\nclosed: null\n",
        encoding="utf-8",
    )
    (tmp_path / "research" / "findings" / ".gitkeep").write_text("", encoding="utf-8")
    after, checked_after = run_all_checks(tmp_path)
    assert checked_after == checked_before
    assert [(i.check_id, i.path) for i in after] == [(i.check_id, i.path) for i in before]
    assert not any("research/findings" in i.path for i in after)
    result = CliRunner().invoke(main, ["lint", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "research/findings" not in result.output


def test_findings_directory_is_tracked_in_the_repo() -> None:
    findings = REPO_ROOT / "research" / "findings"
    assert findings.is_dir()
    assert (findings / ".gitkeep").exists() or any(findings.rglob("*.yaml"))
