"""Tests for `dr review-queue` and the underlying `find_publication_queue` helper.

Two layers:
- Unit tests on `find_publication_queue` confirm queue-membership rules.
- CliRunner tests on the `dr review-queue` command exercise --format text/json
  and the interactive single-key actions (a/s/p/q) by piping stdin.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import orchestrator.review_queue as review_queue_mod
from orchestrator.cli import main
from orchestrator.review_queue import _delete_files, find_publication_queue


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
    fm_sources: list[str] | None = None,
) -> Path:
    """Write a claim .md with the specified frontmatter. Returns its Path."""
    entity_dir = repo_root / "research" / "claims" / entity
    entity_dir.mkdir(parents=True, exist_ok=True)
    if fm_sources:
        sources_block = "sources:\n" + "\n".join(f"- {s}" for s in fm_sources)
    else:
        sources_block = "sources: []"
    fm_lines = [
        "---",
        f"title: {title}",
        f"entity: companies/{entity}",
        "topics: [test]",
        f"verdict: '{verdict}'",
        "confidence: high",
        "as_of: 2026-04-01",
        sources_block,
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
        c = _write_claim(
            tmp_path,
            entity="ent-a",
            slug="juliet",
            verdict="mixed",
            fm_sources=["s1", "s2", "s3"],
        )
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

    def test_sources_count_falls_back_to_fm_when_sidecar_empty(self, tmp_path):
        """Pipeline paths that leave sources_consulted empty should still
        report the claim's cited sources, since they are what the site renders."""
        c = _write_claim(
            tmp_path,
            entity="ent-a",
            slug="kilo-empty-sidecar",
            fm_sources=["a", "b", "c"],
        )
        _write_sidecar(c, sources=[])

        item = find_publication_queue(tmp_path)[0]

        assert item.sources_count == 3
        assert item.sources_ingested == 3

    def test_sources_zero_when_both_empty(self, tmp_path):
        c = _write_claim(tmp_path, entity="ent-a", slug="lima-no-sources")
        _write_sidecar(c, sources=[])

        item = find_publication_queue(tmp_path)[0]

        assert item.sources_count == 0
        assert item.sources_ingested == 0


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

    def test_delete_confirmed_removes_files(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="sierra")
        _write_sidecar(c)
        sidecar = c.with_name(c.stem + ".audit.yaml")

        deleted: list[tuple[Path, Path]] = []

        def fake_delete(claim_path, sidecar_path, trash_dir=None):
            deleted.append((claim_path, sidecar_path))
            claim_path.unlink(missing_ok=True)
            sidecar_path.unlink(missing_ok=True)

        monkeypatch.setattr(review_queue_mod, "_delete_files", fake_delete)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="d\ny\n",
        )

        assert result.exit_code == 0, result.output
        assert not c.exists()
        assert not sidecar.exists()
        assert "Deleted: ent-a/sierra" in result.output
        assert len(deleted) == 1

    def test_delete_declined_leaves_files(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="tango")
        _write_sidecar(c)

        deleted: list = []
        monkeypatch.setattr(review_queue_mod, "_delete_files", lambda *a, **kw: deleted.append(a))

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="d\nn\nq\n",
        )

        assert result.exit_code == 0, result.output
        assert c.exists()
        assert not deleted


# --------------------------------------------------------------------------- #
# CLI: `e` (edit fields) action                                                #
# --------------------------------------------------------------------------- #

def _stub_editor(monkeypatch, fn):
    """Replace `_run_editor_blocking` with `fn(path) -> int`."""
    monkeypatch.setattr(review_queue_mod, "_run_editor_blocking", fn)


class TestReviewQueueEditFields:
    def test_save_round_trip_updates_only_edited_fields(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="alpha", title="Original title")
        _write_sidecar(c)
        original_text = c.read_text(encoding="utf-8")

        def fake_edit(path):
            path.write_text(
                "title: New title\n"
                "takeaway: New takeaway\n"
                "seo_title: ''\n"
                "tags: []\n"
                "verdict: 'true'\n",
                encoding="utf-8",
            )
            return 0

        _stub_editor(monkeypatch, fake_edit)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\ns\nq\n",
        )

        assert result.exit_code == 0, result.output
        new_text = c.read_text(encoding="utf-8")
        assert "title: New title" in new_text
        assert "takeaway: New takeaway" in new_text
        # Body untouched
        assert CLAIM_BODY.strip() in new_text
        # Unrelated fm keys untouched
        assert "criteria_slug: test-criterion" in new_text
        assert "entity: companies/ent-a" in new_text
        # Status not flipped (only an edit, not approve)
        assert "status: draft" in new_text
        # Original differed from new
        assert new_text != original_text

    def test_tags_preserve_flow_style(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="bravo")
        _write_sidecar(c)

        def fake_edit(path):
            path.write_text(
                "title: T\n"
                "takeaway: ''\n"
                "seo_title: ''\n"
                "tags:\n  - highlight\n  - featured\n"
                "verdict: 'true'\n",
                encoding="utf-8",
            )
            return 0

        _stub_editor(monkeypatch, fake_edit)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\ns\nq\n",
        )

        assert result.exit_code == 0, result.output
        new_text = c.read_text(encoding="utf-8")
        assert "tags: [highlight, featured]" in new_text

    def test_invalid_verdict_reedits_with_broken_text(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="charlie")
        _write_sidecar(c)
        before = c.read_bytes()

        seen_buffers: list[str] = []
        attempt = {"n": 0}

        def fake_edit(path):
            seen_buffers.append(path.read_text(encoding="utf-8"))
            attempt["n"] += 1
            if attempt["n"] == 1:
                path.write_text(
                    "title: T\ntakeaway: ''\nseo_title: ''\n"
                    "tags: []\nverdict: 'yes'\n",
                    encoding="utf-8",
                )
            else:
                path.write_text(
                    "title: T\ntakeaway: ''\nseo_title: ''\n"
                    "tags: []\nverdict: 'yes'\n",
                    encoding="utf-8",
                )
            return 0

        _stub_editor(monkeypatch, fake_edit)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\nr\nd\nq\n",  # edit, re-edit on validation fail, then discard, then quit
        )

        assert result.exit_code == 0, result.output
        assert "verdict must be one of" in result.output
        # On the second open, the buffer should contain the operator's broken text,
        # not the original (no comment header).
        assert len(seen_buffers) >= 2
        assert "verdict: 'yes'" in seen_buffers[1]
        # File on disk unchanged
        assert c.read_bytes() == before

    def test_yaml_parse_error_offers_reedit(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="delta")
        _write_sidecar(c)
        before = c.read_bytes()

        def fake_edit(path):
            path.write_text("title: : :\n  bad yaml\n", encoding="utf-8")
            return 0

        _stub_editor(monkeypatch, fake_edit)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\nd\nq\n",  # edit, then discard at error prompt, then quit
        )

        assert result.exit_code == 0, result.output
        assert "Edit rejected" in result.output
        assert c.read_bytes() == before

    def test_discard_at_preview_leaves_file_unchanged(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="echo")
        _write_sidecar(c)
        before = c.read_bytes()

        def fake_edit(path):
            path.write_text(
                "title: Should not save\ntakeaway: ''\nseo_title: ''\n"
                "tags: []\nverdict: 'true'\n",
                encoding="utf-8",
            )
            return 0

        _stub_editor(monkeypatch, fake_edit)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\nd\nq\n",  # edit, discard at preview, quit
        )

        assert result.exit_code == 0, result.output
        assert c.read_bytes() == before

    def test_no_editor_available_surfaces_error(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="foxtrot")
        _write_sidecar(c)
        before = c.read_bytes()

        _stub_editor(monkeypatch, lambda path: -1)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\nq\n",
        )

        assert result.exit_code == 0, result.output
        assert "No editor found" in result.output
        assert c.read_bytes() == before

    def test_unmodified_buffer_is_treated_as_discard(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="golf")
        _write_sidecar(c)
        before = c.read_bytes()

        def fake_edit(path):
            # Don't write; simulate `:q` without changes
            return 0

        _stub_editor(monkeypatch, fake_edit)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\nq\n",
        )

        assert result.exit_code == 0, result.output
        assert c.read_bytes() == before

    def test_mtime_conflict_aborts_save(self, tmp_path, monkeypatch):
        c = _write_claim(tmp_path, entity="ent-a", slug="hotel")
        _write_sidecar(c)

        def fake_edit(path):
            path.write_text(
                "title: New\ntakeaway: ''\nseo_title: ''\n"
                "tags: []\nverdict: 'true'\n",
                encoding="utf-8",
            )
            # Simulate external write to the claim while the buffer was open.
            external = c.read_text(encoding="utf-8") + "\nexternal append\n"
            c.write_text(external, encoding="utf-8")
            # Force an mtime bump even if writes coalesce in the same nanosecond.
            future = c.stat().st_mtime_ns + 1_000_000
            os.utime(c, ns=(future, future))
            return 0

        _stub_editor(monkeypatch, fake_edit)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input="e\ns\nd\nq\n",  # edit, save (aborted), discard at retry, quit
        )

        assert result.exit_code == 0, result.output
        assert "changed externally" in result.output
        # External append survived; our edits did NOT write over it
        text = c.read_text(encoding="utf-8")
        assert "external append" in text
        assert "title: New" not in text


class TestDeleteFiles:
    def test_on_macos_moves_to_trash_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        claim = tmp_path / "claim.md"
        sidecar = tmp_path / "claim.audit.yaml"
        claim.write_text("content")
        sidecar.write_text("sidecar")
        trash = tmp_path / "trash"

        _delete_files(claim, sidecar, trash_dir=trash)

        assert not claim.exists()
        assert not sidecar.exists()
        assert (trash / "claim.md").exists()
        assert (trash / "claim.audit.yaml").exists()

    def test_on_non_macos_hard_deletes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        claim = tmp_path / "claim.md"
        sidecar = tmp_path / "claim.audit.yaml"
        claim.write_text("content")
        sidecar.write_text("sidecar")

        _delete_files(claim, sidecar)

        assert not claim.exists()
        assert not sidecar.exists()

    def test_skips_missing_sidecar(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        claim = tmp_path / "claim.md"
        claim.write_text("content")
        missing_sidecar = tmp_path / "claim.audit.yaml"
        trash = tmp_path / "trash"

        _delete_files(claim, missing_sidecar, trash_dir=trash)

        assert not claim.exists()
        assert (trash / "claim.md").exists()

    def test_macos_deduplicates_on_name_collision(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        claim = tmp_path / "claim.md"
        claim.write_text("first")
        trash = tmp_path / "trash"
        trash.mkdir()
        (trash / "claim.md").write_text("already there")

        _delete_files(claim, tmp_path / "no-sidecar.yaml", trash_dir=trash)

        assert not claim.exists()
        trashed = list(trash.glob("claim*.md"))
        assert len(trashed) == 2
