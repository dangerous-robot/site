"""A sign-off needs a person at a terminal.

`dr review` (every mode) and the `a` action of `dr review-queue` write a
reviewer name into the audit sidecar, which the site renders as "Reviewed".
An agent session runs commands with stdin piped, so the gate refuses when
stdin is not a tty and asks for the claim slug to be typed back before any
write. Every other test module that signs off patches the gate through the
`human_at_terminal` fixture; this module exercises the gate itself.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import orchestrator.review as review_mod
from orchestrator.cli import main
from orchestrator.review import approve_claim

SLUG = "test-entity/test-claim"


def _write_claim(repo_root: Path, *, status: str = "draft") -> tuple[Path, Path]:
    entity_dir = repo_root / "research" / "claims" / "test-entity"
    entity_dir.mkdir(parents=True, exist_ok=True)
    claim_md = entity_dir / "test-claim.md"
    claim_md.write_text(
        "---\ntitle: Test\nentity: companies/test-entity\ntopics: [test]\n"
        "verdict: 'true'\nconfidence: high\nas_of: 2026-04-01\nsources: []\n"
        f"status: {status}\ncriteria_slug: test-criterion\n---\nBody.\n",
        encoding="utf-8",
    )
    sidecar = entity_dir / "test-claim.audit.yaml"
    sidecar.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "pipeline_run": {"ran_at": "2026-04-22T14:32:00+00:00", "model": "m", "agents": []},
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
                "human_review": {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return claim_md, sidecar


def _review(tmp_path: Path, *flags: str, input: str | None = None):
    return CliRunner().invoke(
        main,
        ["review", "--claim", SLUG, "--reviewer", "test@example.com", "--repo-root", str(tmp_path), *flags],
        input=input,
    )


def _unchanged(claim_md: Path, sidecar: Path, md_before: bytes, sidecar_before: bytes) -> None:
    assert claim_md.read_bytes() == md_before
    assert sidecar.read_bytes() == sidecar_before


class TestDrReviewNeedsTerminal:
    @pytest.mark.parametrize(
        ("status", "flags"),
        [("draft", ()), ("draft", ("--approve",)), ("published", ("--archive",))],
        ids=["sign-off", "approve", "archive"],
    )
    def test_piped_stdin_is_refused_before_any_write(self, tmp_path, status, flags):
        claim_md, sidecar = _write_claim(tmp_path, status=status)
        md_before, sidecar_before = claim_md.read_bytes(), sidecar.read_bytes()

        # CliRunner's stdin is a stream, not a tty: the same shape as `echo | dr review`.
        result = _review(tmp_path, *flags, input=f"{SLUG}\n")

        assert result.exit_code != 0
        assert "terminal" in result.output
        _unchanged(claim_md, sidecar, md_before, sidecar_before)

    def test_wrong_slug_is_refused_before_any_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
        claim_md, sidecar = _write_claim(tmp_path)
        md_before, sidecar_before = claim_md.read_bytes(), sidecar.read_bytes()

        result = _review(tmp_path, "--approve", input="test-entity/other-claim\n")

        assert result.exit_code != 0
        assert "did not match" in result.output
        _unchanged(claim_md, sidecar, md_before, sidecar_before)

    def test_empty_answer_is_refused_before_any_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
        claim_md, sidecar = _write_claim(tmp_path)
        md_before, sidecar_before = claim_md.read_bytes(), sidecar.read_bytes()

        result = _review(tmp_path, "--approve", input="\n")

        assert result.exit_code != 0
        _unchanged(claim_md, sidecar, md_before, sidecar_before)

    def test_control_slug_typed_back_at_a_terminal_publishes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
        claim_md, sidecar = _write_claim(tmp_path)

        result = _review(tmp_path, "--approve", input=f"{SLUG}\n")

        assert result.exit_code == 0, result.output
        assert "status: published" in claim_md.read_text(encoding="utf-8")
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewer"] == "test@example.com"
        assert data["human_review"]["reviewed_at"] is not None

    def test_gate_runs_after_the_preflight_checks(self, tmp_path, monkeypatch):
        """A claim that cannot be approved is reported without asking for the slug."""
        monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
        claim_md, sidecar = _write_claim(tmp_path, status="published")

        result = _review(tmp_path, "--approve", input=f"{SLUG}\n")

        assert result.exit_code != 0
        assert "already published" in result.output
        assert "type the claim slug" not in result.output.lower()


class TestClaimSlugFor:
    def test_entity_and_nested_subject_paths(self, tmp_path):
        claims = tmp_path / "research" / "claims"
        assert review_mod.claim_slug_for(claims / "acme" / "x.md") == "acme/x"
        assert (
            review_mod.claim_slug_for(claims / "subjects" / "us-data-centers" / "x.md")
            == "subjects/us-data-centers/x"
        )

    def test_fallback_outside_a_claims_tree(self, tmp_path):
        assert review_mod.claim_slug_for(tmp_path / "elsewhere" / "ent" / "x.md") == "ent/x"


class TestApproveClaimCallableNeedsTerminal:
    def test_direct_call_without_a_terminal_is_refused(self, tmp_path):
        claim_md, sidecar = _write_claim(tmp_path)
        md_before, sidecar_before = claim_md.read_bytes(), sidecar.read_bytes()

        with pytest.raises(review_mod.click.ClickException, match="terminal"):
            approve_claim(claim_md, reviewer="test@example.com", mode="approve")

        _unchanged(claim_md, sidecar, md_before, sidecar_before)


class TestReviewQueueApproveNeedsTerminal:
    def test_piped_a_is_refused_and_the_claim_stays_draft(self, tmp_path):
        claim_md, sidecar = _write_claim(tmp_path)
        md_before, sidecar_before = claim_md.read_bytes(), sidecar.read_bytes()

        result = CliRunner().invoke(
            main, ["review-queue", "--repo-root", str(tmp_path)], input=f"a\n{SLUG}\nq\n",
        )

        assert "terminal" in result.output
        assert "Approved" not in result.output
        _unchanged(claim_md, sidecar, md_before, sidecar_before)

    def test_wrong_slug_reprompts_the_same_item(self, tmp_path, monkeypatch):
        monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
        _patch_git_email(monkeypatch)
        claim_md, sidecar = _write_claim(tmp_path)

        result = CliRunner().invoke(
            main,
            ["review-queue", "--repo-root", str(tmp_path)],
            input=f"a\ntest-entity/other-claim\na\n{SLUG}\n",
        )

        assert result.exit_code == 0, result.output
        assert "did not match" in result.output
        assert "Approved test-entity/test-claim" in result.output
        assert "status: published" in claim_md.read_text(encoding="utf-8")

    def test_control_slug_typed_back_at_a_terminal_approves(self, tmp_path, monkeypatch):
        monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
        _patch_git_email(monkeypatch)
        claim_md, sidecar = _write_claim(tmp_path)

        result = CliRunner().invoke(
            main, ["review-queue", "--repo-root", str(tmp_path)], input=f"a\n{SLUG}\n",
        )

        assert result.exit_code == 0, result.output
        assert "status: published" in claim_md.read_text(encoding="utf-8")
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        assert data["human_review"]["reviewer"] == "queue-test@example.com"


def _patch_git_email(monkeypatch, email: str = "queue-test@example.com") -> None:
    def _fake_run(cmd, *args, **kwargs):
        class _Proc:
            stdout = f"{email}\n"
        return _Proc()

    monkeypatch.setattr(review_mod.subprocess, "run", _fake_run)
