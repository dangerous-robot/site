"""Tests for `dr review-queue` and the underlying `find_publication_queue` helper.

Two layers:
- Unit tests on `find_publication_queue` confirm queue-membership rules.
- CliRunner tests on the `dr review-queue` command exercise --format text/json
  and the interactive single-key actions (a/s/p/q) by piping stdin.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from orchestrator.cli import main
from orchestrator.review_queue import find_publication_queue


# --------------------------------------------------------------------------- #
# Fixture helpers                                                              #
# --------------------------------------------------------------------------- #

CLAIM_BODY = "Body text here.\n"


def _write_claim(
    repo_root: Path,
    *,
    entity: str,
    slug: str,
    status: str | None = "draft",
    title: str = "Test claim",
    verdict: str = "true",
    blocked_reason: str | None = None,
    criteria_slug: str | None = "test-criterion",
) -> Path:
    """Write a claim .md with the specified frontmatter. Returns its Path."""
    entity_dir = repo_root / "research" / "claims" / entity
    entity_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = [
        "---",
        f"title: {title}",
        f"entity: companies/{entity}",
        "topics: [test]",
        f"verdict: '{verdict}'",
        "confidence: high",
        "as_of: 2026-04-01",
        "sources: []",
    ]
    if status is not None:
        fm_lines.append(f"status: {status}")
    if blocked_reason is not None:
        fm_lines.append(f"blocked_reason: {blocked_reason}")
    if criteria_slug is not None:
        fm_lines.append(f"criteria_slug: {criteria_slug}")
    fm_lines.extend(["---", "", CLAIM_BODY])
    path = entity_dir / f"{slug}.md"
    path.write_text("\n".join(fm_lines), encoding="utf-8")
    return path


def _write_sidecar(
    claim_path: Path,
    *,
    reviewed_at: str | None = None,
    reviewer: str | None = None,
    analyst_verdict: str = "true",
    auditor_verdict: str = "true",
    needs_review: bool = False,
    sources: list[dict] | None = None,
) -> Path:
    """Write a `.audit.yaml` sidecar next to the claim. Returns its Path."""
    sidecar_path = claim_path.with_name(claim_path.stem + ".audit.yaml")
    data = {
        "schema_version": 1,
        "pipeline_run": {
            "ran_at": "2026-04-22T14:32:00+00:00",
            "model": "claude-haiku-4-5",
            "agents": ["researcher", "ingestor", "analyst", "auditor"],
        },
        "sources_consulted": sources if sources is not None else [],
        "audit": {
            "analyst_verdict": analyst_verdict,
            "auditor_verdict": auditor_verdict,
            "analyst_confidence": "high",
            "auditor_confidence": "high",
            "verdict_agrees": analyst_verdict == auditor_verdict,
            "confidence_agrees": True,
            "needs_review": needs_review,
        },
        "human_review": {
            "reviewed_at": reviewed_at,
            "reviewer": reviewer,
            "notes": None,
            "pr_url": None,
        },
    }
    sidecar_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return sidecar_path


def _patch_git_email(monkeypatch, email: str = "queue-test@example.com") -> None:
    """Stub `git config user.email` so approve_claim's reviewer fallback is deterministic."""
    import orchestrator.review as review_mod

    def _fake_run(cmd, *args, **kwargs):
        class _Proc:
            stdout = f"{email}\n"
        return _Proc()

    monkeypatch.setattr(review_mod.subprocess, "run", _fake_run)


# --------------------------------------------------------------------------- #
# find_publication_queue — membership rules                                    #
# --------------------------------------------------------------------------- #

class TestFindPublicationQueue:
    def test_includes_draft_with_sidecar_and_no_review(self, tmp_path):
        claim = _write_claim(tmp_path, entity="ent-a", slug="alpha")
        _write_sidecar(claim)

        items = find_publication_queue(tmp_path)

        assert [i.claim_slug for i in items] == ["ent-a/alpha"]

    def test_excludes_published(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="bravo", status="published")
        _write_sidecar(c)

        assert find_publication_queue(tmp_path) == []

    def test_excludes_archived(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="charlie", status="archived")
        _write_sidecar(c)

        assert find_publication_queue(tmp_path) == []

    def test_excludes_blocked(self, tmp_path):
        c = _write_claim(
            tmp_path,
            entity="ent-a",
            slug="delta",
            status="blocked",
            blocked_reason="insufficient_sources",
        )
        _write_sidecar(c)

        assert find_publication_queue(tmp_path) == []

    def test_excludes_draft_without_sidecar(self, tmp_path):
        _write_claim(tmp_path, entity="ent-a", slug="echo")  # no sidecar

        assert find_publication_queue(tmp_path) == []

    def test_excludes_already_reviewed_draft(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="foxtrot")
        _write_sidecar(c, reviewed_at="2026-04-20", reviewer="bob@example.com")

        assert find_publication_queue(tmp_path) == []

    def test_legacy_claim_without_status_field_is_included(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="golf", status=None)
        _write_sidecar(c)

        items = find_publication_queue(tmp_path)

        assert [i.claim_slug for i in items] == ["ent-a/golf"]
        # status field absent -> displayed as 'draft'
        assert items[0].status == "draft"

    def test_filter_entity(self, tmp_path):
        c1 = _write_claim(tmp_path, entity="ent-a", slug="hotel")
        _write_sidecar(c1)
        c2 = _write_claim(tmp_path, entity="ent-b", slug="india")
        _write_sidecar(c2)

        only_a = find_publication_queue(tmp_path, filter_entity="ent-a")

        assert [i.claim_slug for i in only_a] == ["ent-a/hotel"]

    def test_item_carries_audit_and_source_counts(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="juliet", verdict="mixed")
        _write_sidecar(
            c,
            analyst_verdict="mixed",
            auditor_verdict="false",
            needs_review=True,
            sources=[
                {"id": "s1", "url": "https://a.example", "title": "A", "ingested": True},
                {"id": "s2", "url": "https://b.example", "title": "B", "ingested": True},
                {"id": "s3", "url": "https://c.example", "title": "C", "ingested": False},
            ],
        )

        item = find_publication_queue(tmp_path)[0]

        assert item.verdict == "mixed"
        assert item.analyst_verdict == "mixed"
        assert item.auditor_verdict == "false"
        assert item.needs_review is True
        assert item.sources_count == 3
        assert item.sources_ingested == 2


# --------------------------------------------------------------------------- #
# CLI: --list and --json                                                       #
# --------------------------------------------------------------------------- #

class TestReviewQueueNonInteractive:
    def test_text_format_prints_header_and_one_row(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="kilo")
        _write_sidecar(c)

        result = CliRunner().invoke(
            main, ["review-queue", "--format", "text", "--repo-root", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        lines = result.output.strip().splitlines()
        assert lines[0] == "slug\tstatus\tverdict\tneeds_review\tpath"
        assert lines[1].startswith("ent-a/kilo\tdraft\t")

    def test_json_format_returns_array(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="lima")
        _write_sidecar(c)

        result = CliRunner().invoke(
            main, ["review-queue", "--format", "json", "--repo-root", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        records = json.loads(result.output)
        assert len(records) == 1
        assert records[0]["claim_slug"] == "ent-a/lima"
        assert records[0]["status"] == "draft"
        assert records[0]["needs_review"] is False

    def test_empty_queue_returns_zero_exit(self, tmp_path):
        (tmp_path / "research" / "claims").mkdir(parents=True)

        result = CliRunner().invoke(
            main, ["review-queue", "--format", "json", "--repo-root", str(tmp_path)]
        )

        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_invalid_format_rejected(self, tmp_path):
        (tmp_path / "research" / "claims").mkdir(parents=True)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--format", "yaml", "--repo-root", str(tmp_path)],
        )

        assert result.exit_code != 0
        assert "yaml" in result.output.lower()


# --------------------------------------------------------------------------- #
# CLI: interactive single-key actions                                          #
# --------------------------------------------------------------------------- #

class TestReviewQueueInteractive:
    def test_quit_exits_without_changes(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="mike")
        _write_sidecar(c)
        before = c.read_bytes()

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="q\n",
        )

        assert result.exit_code == 0, result.output
        assert c.read_bytes() == before  # claim untouched
        # sidecar reviewed_at still null
        sidecar = c.with_name(c.stem + ".audit.yaml")
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewed_at"] is None

    def test_skip_advances_without_changes(self, tmp_path):
        c1 = _write_claim(tmp_path, entity="ent-a", slug="november")
        _write_sidecar(c1)
        c2 = _write_claim(tmp_path, entity="ent-a", slug="oscar")
        _write_sidecar(c2)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="s\ns\n",  # skip both
        )

        assert result.exit_code == 0, result.output
        # Neither sidecar got a reviewed_at.
        for c in (c1, c2):
            data = yaml.safe_load(
                c.with_name(c.stem + ".audit.yaml").read_text(encoding="utf-8")
            )
            assert data["human_review"]["reviewed_at"] is None
        assert "Queue done" in result.output

    def test_approve_writes_sidecar_and_flips_status(self, tmp_path, monkeypatch):
        _patch_git_email(monkeypatch)
        c = _write_claim(tmp_path, entity="ent-a", slug="papa")
        _write_sidecar(c)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="a\n",  # only one item; loop ends after approve
        )

        assert result.exit_code == 0, result.output
        # Status flipped
        assert "status: published" in c.read_text(encoding="utf-8")
        # Sidecar populated
        sidecar = c.with_name(c.stem + ".audit.yaml")
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewer"] == "queue-test@example.com"
        assert data["human_review"]["reviewed_at"] is not None
        assert "Approved ent-a/papa" in result.output

    def test_approve_without_criterion_surfaces_gate_and_reprompts(self, tmp_path, monkeypatch):
        """Pressing `a` on a draft missing criteria_slug shows the gate error and re-prompts."""
        _patch_git_email(monkeypatch)
        c = _write_claim(tmp_path, entity="ent-a", slug="romeo", criteria_slug=None)
        _write_sidecar(c)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="a\nq\n",  # try to approve, then quit on the re-prompt
        )

        assert result.exit_code == 0, result.output
        # Claim was NOT promoted.
        assert "status: draft" in c.read_text(encoding="utf-8")
        # Gate message surfaced to operator.
        assert "criteria_slug" in result.output
        sidecar = c.with_name(c.stem + ".audit.yaml")
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewed_at"] is None

    def test_preview_emits_claim_text_then_reprompts(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="quebec", title="Distinctive Title XYZ")
        _write_sidecar(c)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="p\nq\n",  # preview then quit
        )

        assert result.exit_code == 0, result.output
        # Title appears twice: once in the queue header, once in the previewed claim file.
        assert result.output.count("Distinctive Title XYZ") >= 2
        # State unchanged
        sidecar = c.with_name(c.stem + ".audit.yaml")
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewed_at"] is None
