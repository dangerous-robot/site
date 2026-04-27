"""Tests for the `dr publish` bulk auto-publish CLI.

`dr publish` flips draft claims to published WITHOUT recording human review:
- sidecar `human_review.reviewer` stays null (badge renders "Unreviewed")
- sidecar `human_review.reviewed_at` is set to today (satisfies lint)
- sidecar `human_review.notes` carries the canonical "[auto-publish] " prefix

Mirrors the `TestDrReviewPromotion` patterns in test_audit_trail.py.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml
from click.testing import CliRunner

from orchestrator.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _setup_claim(
    tmp_path: Path,
    *,
    entity: str = "test-entity",
    slug: str = "test-claim",
    status: str | None = "draft",
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


# ---------------------------------------------------------------------------
# Single-claim publish path
# ---------------------------------------------------------------------------


class TestPublishSingleClaim:
    def test_flips_draft_to_published_with_null_reviewer(self, tmp_path):
        claim_md, sidecar = _setup_claim(tmp_path, status="draft")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--claim", "test-entity/test-claim",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        assert "status: published" in claim_md.read_text(encoding="utf-8")

        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        # Reviewer stays null — this is the load-bearing invariant.
        assert data["human_review"]["reviewer"] is None
        # reviewed_at is set so the linter accepts the published status.
        assert data["human_review"]["reviewed_at"] == datetime.date.today().isoformat()
        # Notes carries the canonical [auto-publish] prefix.
        assert data["human_review"]["notes"].startswith("[auto-publish] ")
        assert "bulk publish, no human review" in data["human_review"]["notes"]
        assert data["human_review"]["pr_url"] is None

    def test_custom_note_appends_after_prefix(self, tmp_path):
        _setup_claim(tmp_path, status="draft")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--claim", "test-entity/test-claim",
            "--yes",
            "--note", "v1.0.0 backfill",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        sidecar = tmp_path / "research" / "claims" / "test-entity" / "test-claim.audit.yaml"
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        # The "[auto-publish] " prefix is fixed; the user note is the suffix.
        assert data["human_review"]["notes"] == "[auto-publish] v1.0.0 backfill"

    def test_resolves_bare_slug_when_unique(self, tmp_path):
        _setup_claim(tmp_path, slug="uniq-claim", status="draft")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--claim", "uniq-claim",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output

    def test_publish_on_claim_without_status_field_succeeds(self, tmp_path):
        """Missing status field is treated as draft (parity with dr review)."""
        claim_md, _ = _setup_claim(tmp_path, status=None)

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--claim", "test-entity/test-claim",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        assert "status: published" in claim_md.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Bulk publish — mixed-status entity fixture
# ---------------------------------------------------------------------------


class TestPublishBulk:
    def test_only_drafts_flip(self, tmp_path):
        # Mixed-status entity: draft, published, archived, blocked, plus a
        # second draft for good measure.
        d1, _ = _setup_claim(tmp_path, slug="claim-a", status="draft")
        d2, _ = _setup_claim(tmp_path, slug="claim-b", status="draft")
        p1, _ = _setup_claim(tmp_path, slug="claim-c", status="published")
        a1, _ = _setup_claim(tmp_path, slug="claim-d", status="archived")
        # blocked claim with a blocked_reason field
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        b1 = entity_dir / "claim-e.md"
        b1.write_text(
            "---\ntitle: Test\nstatus: blocked\n"
            "blocked_reason: insufficient_sources\n---\nBody.\n",
            encoding="utf-8",
        )
        _write_minimal_sidecar(entity_dir / "claim-e.audit.yaml")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        # Only the two drafts flipped.
        assert "status: published" in d1.read_text(encoding="utf-8")
        assert "status: published" in d2.read_text(encoding="utf-8")
        # Pre-published claim untouched.
        assert "status: published" in p1.read_text(encoding="utf-8")
        # Archived stays archived.
        assert "status: archived" in a1.read_text(encoding="utf-8")
        # Blocked stays blocked.
        assert "status: blocked" in b1.read_text(encoding="utf-8")
        # Output mentions the skips.
        assert "archived" in result.output.lower()
        assert "blocked" in result.output.lower()

    def test_skipped_blocked_surfaces_blocked_reason(self, tmp_path):
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        entity_dir.mkdir(parents=True)
        b1 = entity_dir / "blocked-claim.md"
        b1.write_text(
            "---\ntitle: Test\nstatus: blocked\n"
            "blocked_reason: insufficient_sources\n---\nBody.\n",
            encoding="utf-8",
        )
        _write_minimal_sidecar(entity_dir / "blocked-claim.audit.yaml")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        # No drafts to publish, but classification was clean -> exit 0.
        assert result.exit_code == 0, result.output
        assert "insufficient_sources" in result.output

    def test_strict_aborts_on_first_error_after_partial_progress(self, tmp_path):
        """--strict (opt-out of continue-on-error) must fail-fast on first error.

        A sidecar with a null human_review block raises KeyError when the
        publish loop tries the naked subscript assignment. Place the bad
        claim alphabetically AFTER a healthy draft so we can assert
        partial progress: the first claim is published, the bad one
        aborts the batch, any subsequent draft is left untouched.
        """
        # claim-a: healthy draft (will publish first).
        good_claim, _ = _setup_claim(tmp_path, slug="claim-a", status="draft")
        # claim-b: draft whose sidecar has null human_review; KeyError on write.
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        bad_claim = entity_dir / "claim-b.md"
        bad_claim.write_text(
            "---\ntitle: Test\nstatus: draft\n---\nBody.\n",
            encoding="utf-8",
        )
        bad_sidecar = entity_dir / "claim-b.audit.yaml"
        bad_sidecar.write_text(
            yaml.safe_dump({
                "schema_version": 1,
                "pipeline_run": {"ran_at": "2026-04-22T00:00:00+00:00", "model": "x", "agents": []},
                "sources_consulted": [],
                "audit": None,
                "human_review": None,  # forces KeyError on subscript assignment
            }),
            encoding="utf-8",
        )
        # claim-c: another healthy draft that should NOT be published when strict aborts.
        untouched_claim, _ = _setup_claim(tmp_path, slug="claim-c", status="draft")
        untouched_before = untouched_claim.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--strict",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 1
        # First claim was published before the abort.
        assert "status: published" in good_claim.read_text(encoding="utf-8")
        # Bad claim was not flipped.
        assert "status: draft" in bad_claim.read_text(encoding="utf-8")
        # Third claim was never reached.
        assert untouched_claim.read_bytes() == untouched_before
        assert "Aborted on first error" in result.output

    def test_single_claim_idempotency(self, tmp_path):
        """Re-running --claim on an already-published claim is a no-op exit 0."""
        claim_md, sidecar = _setup_claim(tmp_path, status="published")
        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--claim", "test-entity/test-claim",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        assert "Nothing to publish" in result.output
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_missing_sidecar_skipped_with_warning_batch_continues(self, tmp_path):
        # One draft with sidecar, one draft without.
        d1, _ = _setup_claim(tmp_path, slug="claim-with-sidecar", status="draft")
        # Draft missing its sidecar.
        entity_dir = tmp_path / "research" / "claims" / "test-entity"
        d2 = entity_dir / "claim-no-sidecar.md"
        d2.write_text("---\ntitle: Test\nstatus: draft\n---\nBody.\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        # Exit 0: sidecar-missing is a clean skip, not an error.
        assert result.exit_code == 0, result.output
        # The good draft was published, the sidecar-less one was not.
        assert "status: published" in d1.read_text(encoding="utf-8")
        assert "status: draft" in d2.read_text(encoding="utf-8")
        assert "missing sidecar" in result.output


# ---------------------------------------------------------------------------
# Selector validation
# ---------------------------------------------------------------------------


class TestPublishSelectors:
    def test_zero_match_exits_nonzero(self, tmp_path):
        # Repo has a claims dir but no claims for this entity slug.
        (tmp_path / "research" / "claims").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "no-such-entity",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 1
        assert "No claims matched" in result.output

    def test_no_selector_errors_out(self, tmp_path):
        (tmp_path / "research" / "claims").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "exactly one" in result.output.lower()

    def test_claim_and_all_mutually_exclusive(self, tmp_path):
        (tmp_path / "research" / "claims").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--claim", "x/y",
            "--all",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_entity_and_all_mutually_exclusive(self, tmp_path):
        (tmp_path / "research" / "claims").mkdir(parents=True)

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--all",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()


# ---------------------------------------------------------------------------
# Idempotency and dry-run
# ---------------------------------------------------------------------------


class TestPublishIdempotency:
    def test_rerun_on_already_published_is_noop_exit_zero(self, tmp_path):
        # Two published claims, no drafts.
        p1, _ = _setup_claim(tmp_path, slug="claim-a", status="published")
        p2, _ = _setup_claim(tmp_path, slug="claim-b", status="published")
        before_a = p1.read_bytes()
        before_b = p2.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--yes",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        assert "Nothing to publish" in result.output
        # Files untouched.
        assert p1.read_bytes() == before_a
        assert p2.read_bytes() == before_b

    def test_dry_run_makes_no_writes(self, tmp_path):
        claim_md, sidecar = _setup_claim(tmp_path, status="draft")
        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--dry-run",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output
        # Both files byte-identical to before.
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_dry_run_lists_planned_transitions(self, tmp_path):
        _setup_claim(tmp_path, slug="claim-a", status="draft")
        _setup_claim(tmp_path, slug="claim-b", status="draft")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--entity", "test-entity",
            "--dry-run",
            "--repo-root", str(tmp_path),
        ])

        assert result.exit_code == 0
        assert "draft -> published" in result.output
        assert "claim-a" in result.output
        assert "claim-b" in result.output


# ---------------------------------------------------------------------------
# Confirmation prompt and reversibility
# ---------------------------------------------------------------------------


class TestPublishConfirmation:
    def test_no_yes_aborts_on_n(self, tmp_path):
        claim_md, sidecar = _setup_claim(tmp_path, status="draft")
        md_before = claim_md.read_bytes()
        sidecar_before = sidecar.read_bytes()

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "publish",
                "--entity", "test-entity",
                "--repo-root", str(tmp_path),
            ],
            input="n\n",
        )

        assert result.exit_code != 0
        # No writes happened — confirmation aborted before the publish loop.
        assert claim_md.read_bytes() == md_before
        assert sidecar.read_bytes() == sidecar_before

    def test_reversibility_via_dr_review(self, tmp_path):
        """An auto-published claim can be retroactively human-reviewed.

        After dr publish, reviewer is null. A subsequent dr review (no
        --approve flag) sets reviewer; the badge would then flip to
        "Reviewed". This is the documented reversibility path.
        """
        _setup_claim(tmp_path, status="draft")

        runner = CliRunner()
        result = runner.invoke(main, [
            "publish",
            "--claim", "test-entity/test-claim",
            "--yes",
            "--repo-root", str(tmp_path),
        ])
        assert result.exit_code == 0, result.output

        result = runner.invoke(main, [
            "review",
            "--claim", "test-entity/test-claim",
            "--reviewer", "alice@example.com",
            "--notes", "post-hoc review",
            "--repo-root", str(tmp_path),
        ])
        assert result.exit_code == 0, result.output

        sidecar = tmp_path / "research" / "claims" / "test-entity" / "test-claim.audit.yaml"
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewer"] == "alice@example.com"
        # The dr review path overwrites notes with whatever the reviewer
        # passed (acceptable: by reviewing, the operator takes ownership).
        assert data["human_review"]["notes"] == "post-hoc review"
