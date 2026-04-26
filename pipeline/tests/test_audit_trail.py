"""Tests for audit sidecar infrastructure.

Covers _write_audit_sidecar, _build_sources_consulted, and dr review CLI.
"""

from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from auditor.models import ComparisonResult
from common.models import Confidence, Verdict, VerdictSeverity
from ingestor.models import SourceFile, SourceFrontmatter
from common.models import SourceKind
from orchestrator.cli import main
from common.models import Category
from common.frontmatter import parse_frontmatter
from common.models import BlockedReason, Phase
from orchestrator.persistence import (
    _build_sources_consulted,
    _write_audit_sidecar,
    _write_claim_file,
    set_claim_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_comparison(
    primary_verdict: Verdict = Verdict.TRUE,
    assessed_verdict: Verdict = Verdict.TRUE,
    primary_confidence: Confidence = Confidence.HIGH,
    assessed_confidence: Confidence = Confidence.HIGH,
) -> ComparisonResult:
    return ComparisonResult(
        claim_id="test/renewable-energy",
        claim_file="research/claims/test/renewable-energy.md",
        primary_verdict=primary_verdict,
        assessed_verdict=assessed_verdict,
        primary_confidence=primary_confidence,
        assessed_confidence=assessed_confidence,
        reasoning="Test reasoning.",
        evidence_gaps=[],
        verdict_agrees=(primary_verdict == assessed_verdict),
        confidence_agrees=(primary_confidence == assessed_confidence),
        verdict_severity=VerdictSeverity.MATCH,
        needs_review=False,
    )


def _make_source_file(slug: str = "test-source", year: int = 2026, title: str = "Test Source") -> SourceFile:
    fm = SourceFrontmatter(
        url="https://example.com",
        title=title,
        publisher="Example Publisher",
        accessed_date=datetime.date(2026, 4, 22),
        kind=SourceKind.ARTICLE,
        summary="A brief test summary here.",
    )
    return SourceFile(frontmatter=fm, body="Body text.", slug=slug, year=year)


def _write_minimal_sidecar(path: Path) -> None:
    data = {
        "schema_version": 1,
        "pipeline_run": {
            "ran_at": "2026-04-22T14:32:00+00:00",
            "model": "claude-haiku-4-5",
            "agents": ["researcher", "ingestor", "analyst", "auditor"],
        },
        "sources_consulted": [],
        "audit": {
            "analyst_verdict": "true",
            "auditor_verdict": "true",
            "analyst_confidence": "high",
            "auditor_confidence": "high",
            "verdict_agrees": True,
            "confidence_agrees": True,
            "needs_review": False,
        },
        "human_review": {
            "reviewed_at": None,
            "reviewer": None,
            "notes": None,
            "pr_url": None,
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


FIXED_TS = datetime.datetime(2026, 4, 22, 14, 32, 0, tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------------------
# _build_sources_consulted
# ---------------------------------------------------------------------------

class TestBuildSourcesConsulted:
    def test_none_returns_empty(self):
        assert _build_sources_consulted(None) == []

    def test_empty_list_returns_empty(self):
        assert _build_sources_consulted([]) == []

    def test_single_source(self):
        sf = _make_source_file("ecosia-homepage", 2026, "Ecosia")
        result = _build_sources_consulted([("https://ecosia.org", sf)])
        assert len(result) == 1
        assert result[0]["id"] == "2026/ecosia-homepage"
        assert result[0]["url"] == "https://ecosia.org"
        assert result[0]["title"] == "Ecosia"
        assert result[0]["ingested"] is True

    def test_multiple_sources(self):
        sf1 = _make_source_file("source-one", 2026, "Source One")
        sf2 = _make_source_file("source-two", 2025, "Source Two")
        result = _build_sources_consulted([
            ("https://example.com/one", sf1),
            ("https://example.com/two", sf2),
        ])
        assert len(result) == 2
        assert result[1]["id"] == "2025/source-two"


# ---------------------------------------------------------------------------
# _write_audit_sidecar — valid ComparisonResult
# ---------------------------------------------------------------------------

class TestWriteAuditSidecar:
    def test_sidecar_path_derived_correctly(self, tmp_path):
        claim_path = tmp_path / "renewable-energy-hosting.md"
        claim_path.touch()

        sidecar_path = _write_audit_sidecar(
            claim_path=claim_path,
            comparison=_make_comparison(),
            model="claude-haiku-4-5",
            ran_at=FIXED_TS,
            sources_consulted=[],
            agents_run=["researcher", "ingestor", "analyst", "auditor"],
        )

        expected = tmp_path / "renewable-energy-hosting.audit.yaml"
        assert sidecar_path == expected
        assert sidecar_path.exists()

    def test_all_fields_written(self, tmp_path):
        claim_path = tmp_path / "test-claim.md"
        claim_path.touch()
        sf = _make_source_file("ecosia-homepage", 2026, "Ecosia")

        comparison = _make_comparison(
            primary_verdict=Verdict.TRUE,
            assessed_verdict=Verdict.TRUE,
            primary_confidence=Confidence.HIGH,
            assessed_confidence=Confidence.HIGH,
        )
        sources = _build_sources_consulted([("https://ecosia.org", sf)])

        sidecar_path = _write_audit_sidecar(
            claim_path=claim_path,
            comparison=comparison,
            model="claude-haiku-4-5",
            ran_at=FIXED_TS,
            sources_consulted=sources,
            agents_run=["researcher", "ingestor", "analyst", "auditor"],
        )

        data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))

        assert data["schema_version"] == 1
        assert data["pipeline_run"]["model"] == "claude-haiku-4-5"
        assert data["pipeline_run"]["agents"] == ["researcher", "ingestor", "analyst", "auditor"]
        assert len(data["sources_consulted"]) == 1
        assert data["sources_consulted"][0]["id"] == "2026/ecosia-homepage"
        assert data["audit"]["analyst_verdict"] == "true"
        assert data["audit"]["auditor_verdict"] == "true"
        assert data["audit"]["analyst_confidence"] == "high"
        assert data["audit"]["auditor_confidence"] == "high"
        assert data["audit"]["verdict_agrees"] is True
        assert data["audit"]["confidence_agrees"] is True
        assert data["audit"]["needs_review"] is False
        assert data["human_review"]["reviewed_at"] is None
        assert data["human_review"]["reviewer"] is None
        assert data["human_review"]["notes"] is None
        assert data["human_review"]["pr_url"] is None

    def test_comparison_none_writes_audit_null(self, tmp_path):
        claim_path = tmp_path / "test-claim.md"
        claim_path.touch()

        sidecar_path = _write_audit_sidecar(
            claim_path=claim_path,
            comparison=None,
            model="claude-haiku-4-5",
            ran_at=FIXED_TS,
            sources_consulted=[],
            agents_run=["researcher", "ingestor", "analyst", "auditor"],
        )

        data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        # audit key must be present and explicitly null
        assert "audit" in data
        assert data["audit"] is None

    def test_timestamp_round_trips(self, tmp_path):
        claim_path = tmp_path / "ts-claim.md"
        claim_path.touch()

        sidecar_path = _write_audit_sidecar(
            claim_path=claim_path,
            comparison=None,
            model="claude-haiku-4-5",
            ran_at=FIXED_TS,
            sources_consulted=[],
            agents_run=["researcher"],
        )

        data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
        stored = data["pipeline_run"]["ran_at"]
        # yaml.safe_load parses ISO datetime strings into datetime objects
        if isinstance(stored, datetime.datetime):
            # Strip tz and compare UTC
            stored_utc = stored.replace(tzinfo=datetime.timezone.utc) if stored.tzinfo is None else stored.astimezone(datetime.timezone.utc)
            assert stored_utc == FIXED_TS
        else:
            # Stored as string — verify it starts with the expected prefix
            assert str(stored).startswith("2026-04-22")

    def test_preserves_human_review_on_rerun(self, tmp_path):
        # An operator-reviewed sidecar must survive a pipeline rerun. The
        # pipeline_run and audit blocks refresh; human_review carries forward.
        claim_path = tmp_path / "reviewed-claim.md"
        claim_path.touch()
        sidecar_path = tmp_path / "reviewed-claim.audit.yaml"
        existing = {
            "schema_version": 1,
            "pipeline_run": {"ran_at": "2026-04-01T00:00:00+00:00", "model": "old", "agents": []},
            "sources_consulted": [],
            "audit": None,
            "human_review": {
                "reviewed_at": "2026-04-15",
                "reviewer": "reviewer@example.com",
                "notes": "approved",
                "pr_url": "https://github.com/org/repo/pull/42",
            },
        }
        sidecar_path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")

        _write_audit_sidecar(
            claim_path=claim_path,
            comparison=_make_comparison(),
            model="claude-haiku-4-5",
            ran_at=FIXED_TS,
            sources_consulted=[],
            agents_run=["researcher", "ingestor", "analyst", "auditor"],
        )

        data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewed_at"] == "2026-04-15"
        assert data["human_review"]["reviewer"] == "reviewer@example.com"
        assert data["human_review"]["notes"] == "approved"
        assert data["human_review"]["pr_url"] == "https://github.com/org/repo/pull/42"
        # pipeline_run refreshed
        assert data["pipeline_run"]["model"] == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# _write_claim_file — overwrite protection
# ---------------------------------------------------------------------------


class TestWriteClaimFile:
    def _call(self, repo_root: Path, force: bool = False, narrative: str = "initial narrative"):
        return _write_claim_file(
            title="Test Claim",
            entity_name="Test Entity",
            entity_ref="companies/test-entity",
            topics=[Category.ENVIRONMENTAL_IMPACT],
            verdict=Verdict.TRUE,
            confidence=Confidence.HIGH,
            narrative=narrative,
            claim_slug="test-claim",
            source_ids=[],
            repo_root=repo_root,
            force=force,
        )

    def test_writes_new_file(self, tmp_path):
        path = self._call(tmp_path)
        assert path.exists()
        assert "initial narrative" in path.read_text(encoding="utf-8")

    def test_refuses_overwrite_without_force(self, tmp_path):
        self._call(tmp_path, narrative="original")
        with pytest.raises(FileExistsError, match="force=True"):
            self._call(tmp_path, narrative="replacement")

        # Original content must remain intact.
        path = tmp_path / "research" / "claims" / "test-entity" / "test-claim.md"
        assert "original" in path.read_text(encoding="utf-8")
        assert "replacement" not in path.read_text(encoding="utf-8")

    def test_overwrites_with_force(self, tmp_path):
        self._call(tmp_path, narrative="original")
        self._call(tmp_path, force=True, narrative="replacement")

        path = tmp_path / "research" / "claims" / "test-entity" / "test-claim.md"
        assert "replacement" in path.read_text(encoding="utf-8")
        assert "original" not in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# dr review CLI
# ---------------------------------------------------------------------------

class TestDrReviewCli:
    def test_sets_reviewed_at_to_today(self, tmp_path):
        # Set up a fake claims directory
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True)
        claim_md = entity_dir / "test-claim.md"
        claim_md.write_text("---\ntitle: Test\n---\n", encoding="utf-8")
        sidecar = entity_dir / "test-claim.audit.yaml"
        _write_minimal_sidecar(sidecar)

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output

        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        today = datetime.date.today().isoformat()
        assert data["human_review"]["reviewed_at"] == today
        assert data["human_review"]["reviewer"] == "test@example.com"

    def test_preserves_existing_fields(self, tmp_path):
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True)
        claim_md = entity_dir / "test-claim.md"
        claim_md.write_text("---\ntitle: Test\n---\n", encoding="utf-8")
        sidecar = entity_dir / "test-claim.audit.yaml"
        _write_minimal_sidecar(sidecar)

        runner = CliRunner()
        runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--notes", "Looks good",
            "--pr-url", "https://github.com/example/repo/pull/1",
            "--repo-root", str(tmp_path),
        ])

        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        # Pipeline fields must be preserved
        assert data["schema_version"] == 1
        assert data["pipeline_run"]["model"] == "claude-haiku-4-5"
        assert data["audit"]["analyst_verdict"] == "true"
        # Human review fields set correctly
        assert data["human_review"]["notes"] == "Looks good"
        assert data["human_review"]["pr_url"] == "https://github.com/example/repo/pull/1"

    def test_exits_nonzero_on_missing_sidecar(self, tmp_path):
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True)
        claim_md = entity_dir / "no-sidecar.md"
        claim_md.write_text("---\ntitle: Test\n---\n", encoding="utf-8")
        # No .audit.yaml written

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/no-sidecar",
            "--reviewer", "test@example.com",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "No audit sidecar found" in (result.output + result.stderr if hasattr(result, 'stderr') else result.output)

    def test_exits_nonzero_on_missing_claim_file(self, tmp_path):
        # Claims directory exists but the requested slug does not.
        (tmp_path / "research" / "claims").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "missing-entity/no-such-claim",
            "--reviewer", "test@example.com",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "Claim file not found" in result.output

    def test_resolves_bare_slug_when_unique(self, tmp_path):
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True)
        claim_md = entity_dir / "uniq-claim.md"
        claim_md.write_text("---\ntitle: Test\n---\n", encoding="utf-8")
        sidecar = entity_dir / "uniq-claim.audit.yaml"
        _write_minimal_sidecar(sidecar)

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "uniq-claim",
            "--reviewer", "test@example.com",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewer"] == "test@example.com"

    def test_rejects_ambiguous_bare_slug(self, tmp_path):
        for entity in ("entity-a", "entity-b"):
            d = tmp_path / "research" / "claims" / entity
            d.mkdir(parents=True)
            (d / "shared-slug.md").write_text("---\ntitle: T\n---\n", encoding="utf-8")
            _write_minimal_sidecar(d / "shared-slug.audit.yaml")

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "shared-slug",
            "--reviewer", "test@example.com",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "Ambiguous" in result.output
        assert "entity-a/shared-slug" in result.output
        assert "entity-b/shared-slug" in result.output


# ---------------------------------------------------------------------------
# dr review --approve / --archive (claim promotion)
# ---------------------------------------------------------------------------

class TestDrReviewPromotion:
    def _setup_claim(
        self,
        tmp_path: Path,
        *,
        status: str | None = "draft",
        slug: str = "test-claim",
        entity: str = "test-entity",
        include_sidecar: bool = True,
    ) -> tuple[Path, Path]:
        entity_dir = tmp_path / "research" / "claims" / entity
        entity_dir.mkdir(parents=True, exist_ok=True)
        claim_md = entity_dir / f"{slug}.md"
        if status is None:
            claim_md.write_text("---\ntitle: Test\n---\nBody.\n", encoding="utf-8")
        else:
            claim_md.write_text(
                f"---\ntitle: Test\nstatus: {status}\n---\nBody.\n",
                encoding="utf-8",
            )
        sidecar = entity_dir / f"{slug}.audit.yaml"
        if include_sidecar:
            _write_minimal_sidecar(sidecar)
        return claim_md, sidecar

    def test_approve_flips_draft_to_published(self, tmp_path):
        claim_md, sidecar = self._setup_claim(tmp_path, status="draft")

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--approve",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        fm_text = claim_md.read_text(encoding="utf-8")
        assert "status: published" in fm_text
        sidecar_data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert sidecar_data["human_review"]["reviewed_at"] == datetime.date.today().isoformat()
        assert "Marked reviewed and published" in result.output

    def test_approve_on_published_claim_fails_and_leaves_files_unchanged(self, tmp_path):
        claim_md, sidecar = self._setup_claim(tmp_path, status="published")
        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--approve",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_approve_on_claim_without_status_field_succeeds(self, tmp_path):
        claim_md, _ = self._setup_claim(tmp_path, status=None)

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--approve",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        fm_text = claim_md.read_text(encoding="utf-8")
        assert "status: published" in fm_text

    def test_archive_flips_published_to_archived(self, tmp_path):
        claim_md, _ = self._setup_claim(tmp_path, status="published")

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--archive",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        fm_text = claim_md.read_text(encoding="utf-8")
        assert "status: archived" in fm_text

    def test_archive_on_draft_claim_fails(self, tmp_path):
        claim_md, sidecar = self._setup_claim(tmp_path, status="draft")
        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--archive",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_archive_on_claim_without_status_field_fails(self, tmp_path):
        claim_md, _ = self._setup_claim(tmp_path, status=None)
        md_before = claim_md.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--archive",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert claim_md.read_bytes() == md_before

    def test_bare_review_does_not_touch_md(self, tmp_path):
        claim_md, _ = self._setup_claim(tmp_path, status="draft")
        md_before = claim_md.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        assert claim_md.read_bytes() == md_before

    def test_malformed_frontmatter_aborts_before_writes(self, tmp_path):
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True)
        claim_md = entity_dir / "test-claim.md"
        claim_md.write_text("no frontmatter here at all\n", encoding="utf-8")
        sidecar = entity_dir / "test-claim.audit.yaml"
        _write_minimal_sidecar(sidecar)

        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--approve",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_approve_and_archive_together_exits_nonzero_before_any_write(self, tmp_path):
        claim_md, sidecar = self._setup_claim(tmp_path, status="draft")
        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--approve",
            "--archive",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_approve_on_blocked_claim_fails_with_clear_error(self, tmp_path):
        """Blocked claims must not be promotable to published."""
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True, exist_ok=True)
        claim_md = entity_dir / "test-claim.md"
        claim_md.write_text(
            "---\ntitle: Test\nstatus: blocked\n"
            "blocked_reason: insufficient_sources\n---\nBody.\n",
            encoding="utf-8",
        )
        sidecar = entity_dir / "test-claim.audit.yaml"
        _write_minimal_sidecar(sidecar)
        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--approve",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "blocked" in result.output.lower()
        assert "insufficient_sources" in result.output
        # Files remain untouched; the gate fires pre-write.
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_archive_on_blocked_claim_succeeds(self, tmp_path):
        """blocked → archived is a valid transition (operator retires the claim)."""
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True, exist_ok=True)
        claim_md = entity_dir / "test-claim.md"
        claim_md.write_text(
            "---\ntitle: Test\nstatus: blocked\n"
            "blocked_reason: insufficient_sources\n---\nBody.\n",
            encoding="utf-8",
        )
        sidecar = entity_dir / "test-claim.audit.yaml"
        _write_minimal_sidecar(sidecar)

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--archive",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        fm_text = claim_md.read_text(encoding="utf-8")
        assert "status: archived" in fm_text

    def test_atomicity_md_write_failure_leaves_sidecar_updated(self, tmp_path, monkeypatch):
        """Sidecar is the commit point.

        If the ``.md`` write step raises mid-flight, the sidecar remains in
        its updated state. Operator guidance: rerun ``dr review --approve``,
        which re-detects the still-``draft`` status and completes the flip.
        """
        claim_md, sidecar = self._setup_claim(tmp_path, status="draft")
        sidecar_before_bytes = sidecar.read_bytes()

        def _boom(*args, **kwargs):
            raise OSError("simulated disk failure mid-flight")

        # Patch at the cli import site: `set_claim_status` is imported at
        # module top, so the cli function looks it up in its own module.
        import orchestrator.cli as cli_mod
        monkeypatch.setattr(cli_mod, "set_claim_status", _boom)

        runner = CliRunner()
        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "test@example.com",
            "--approve",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        # Sidecar was updated before the failure.
        sidecar_data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert sidecar_data["human_review"]["reviewed_at"] == datetime.date.today().isoformat()
        assert sidecar.read_bytes() != sidecar_before_bytes
        # .md was not modified (status still draft).
        assert "status: draft" in claim_md.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# set_claim_status — phase / blocked_reason kwargs (PR 2)
# ---------------------------------------------------------------------------

class TestSetClaimStatusBlocked:
    def test_blocked_round_trip_via_parse_frontmatter(self, tmp_path):
        """Writing status=blocked + blocked_reason round-trips through the parser."""
        claim_md = tmp_path / "claim.md"
        claim_md.write_text(
            "---\ntitle: Test\nstatus: draft\n---\nBody.\n",
            encoding="utf-8",
        )

        set_claim_status(
            claim_md,
            "blocked",
            expected_current="draft",
            blocked_reason=BlockedReason.INSUFFICIENT_SOURCES,
        )

        fm, body = parse_frontmatter(claim_md.read_text(encoding="utf-8"))
        assert fm["status"] == "blocked"
        assert fm["blocked_reason"] == "insufficient_sources"
        assert "Body." in body

    def test_phase_kwarg_writes_field(self, tmp_path):
        claim_md = tmp_path / "claim.md"
        claim_md.write_text(
            "---\ntitle: Test\nstatus: draft\n---\nBody.\n",
            encoding="utf-8",
        )

        set_claim_status(
            claim_md,
            "draft",
            expected_current="draft",
            phase=Phase.ANALYZING,
        )

        fm, _ = parse_frontmatter(claim_md.read_text(encoding="utf-8"))
        assert fm["phase"] == "analyzing"

    def test_phase_set_to_none_clears_field(self, tmp_path):
        """Passing phase=None must drop the key from the persisted frontmatter."""
        claim_md = tmp_path / "claim.md"
        claim_md.write_text(
            "---\ntitle: Test\nstatus: draft\nphase: analyzing\n---\nBody.\n",
            encoding="utf-8",
        )

        set_claim_status(
            claim_md,
            "blocked",
            expected_current="draft",
            phase=None,
            blocked_reason=BlockedReason.INSUFFICIENT_SOURCES,
        )

        text = claim_md.read_text(encoding="utf-8")
        assert "phase:" not in text
        assert "status: blocked" in text
        assert "blocked_reason: insufficient_sources" in text

    def test_default_kwargs_do_not_touch_phase_or_blocked_reason(self, tmp_path):
        """Existing draft → published callers omit kwargs and must not lose state."""
        claim_md = tmp_path / "claim.md"
        claim_md.write_text(
            "---\ntitle: Test\nstatus: draft\nphase: analyzing\n"
            "blocked_reason: insufficient_sources\n---\nBody.\n",
            encoding="utf-8",
        )

        set_claim_status(claim_md, "published", expected_current="draft")

        text = claim_md.read_text(encoding="utf-8")
        assert "status: published" in text
        # Untouched fields still present.
        assert "phase: analyzing" in text
        assert "blocked_reason: insufficient_sources" in text
