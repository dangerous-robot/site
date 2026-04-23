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
from orchestrator.persistence import _build_sources_consulted, _write_audit_sidecar


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


# ---------------------------------------------------------------------------
# dr review CLI
# ---------------------------------------------------------------------------

class TestDrReviewCli:
    def _write_minimal_sidecar(self, path: Path) -> None:
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

    def test_sets_reviewed_at_to_today(self, tmp_path):
        # Set up a fake claims directory
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True)
        claim_md = entity_dir / "test-claim.md"
        claim_md.write_text("---\ntitle: Test\n---\n", encoding="utf-8")
        sidecar = entity_dir / "test-claim.audit.yaml"
        self._write_minimal_sidecar(sidecar)

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
        self._write_minimal_sidecar(sidecar)

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
