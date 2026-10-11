"""Tests for CheckpointHandler implementations."""

from __future__ import annotations

import pytest

import orchestrator.checkpoints as checkpoints_mod
from orchestrator.checkpoints import (
    AutoApproveCheckpointHandler,
    CheckpointHandler,
    CLICheckpointHandler,
)
from researcher.entity_enricher import EnrichmentDraft


def _draft() -> EnrichmentDraft:
    return EnrichmentDraft(
        founded=2021,
        description="Test entity description.",
        history_markdown="Some history paragraph one.\n\nParagraph two.",
    )


class TestAutoApproveReviewEntityEnrichment:
    @pytest.mark.asyncio
    async def test_returns_accept(self) -> None:
        handler = AutoApproveCheckpointHandler()
        result = await handler.review_entity_enrichment(
            entity_name="Acme",
            draft=_draft(),
        )
        assert result == "accept"

    @pytest.mark.asyncio
    async def test_records_call_in_calls(self) -> None:
        handler = AutoApproveCheckpointHandler()
        await handler.review_entity_enrichment(
            entity_name="Acme",
            draft=_draft(),
        )
        assert "review_entity_enrichment" in handler.calls

    def test_protocol_satisfied_by_auto_approve(self) -> None:
        # Runtime-checkable Protocol smoke check: a handler missing the
        # new method would fail isinstance against CheckpointHandler.
        handler = AutoApproveCheckpointHandler()
        assert isinstance(handler, CheckpointHandler)


class TestAutoApproveReviewEntityDisambiguation:
    @pytest.mark.asyncio
    async def test_returns_reject(self) -> None:
        """Auto-approve in the disambiguation case is conservative: aborts."""
        handler = AutoApproveCheckpointHandler()
        result = await handler.review_entity_disambiguation(
            entity_name="Apple",
            candidates=["Apple Inc.", "Apple Records"],
        )
        assert result == "reject"

    @pytest.mark.asyncio
    async def test_records_call_in_calls(self) -> None:
        handler = AutoApproveCheckpointHandler()
        await handler.review_entity_disambiguation(
            entity_name="Apple",
            candidates=["Apple Inc.", "Apple Records"],
        )
        assert "review_entity_disambiguation" in handler.calls


STATUSES = ["unverified-startup", "unverified-other"]


class TestAutoApproveReviewVerificationStatus:
    @pytest.mark.asyncio
    async def test_returns_reject_and_records_call(self) -> None:
        handler = AutoApproveCheckpointHandler()
        result = await handler.review_verification_status(
            entity_name="Ecosia AI", website="https://www.ecosia.org",
            reasoning="site returned 403", statuses=STATUSES,
        )
        assert result == "reject"
        assert "review_verification_status" in handler.calls
        assert isinstance(handler, CheckpointHandler)


class TestCLIReviewVerificationStatus:
    """The prompt says what is being decided: a status label for a settled entity."""

    def _run(self, monkeypatch, capsys, answers: list[str]):
        import asyncio
        replies = iter(answers)
        monkeypatch.setattr(
            checkpoints_mod.click, "prompt", lambda *a, **k: next(replies),
        )
        result = asyncio.run(
            CLICheckpointHandler().review_verification_status(
                entity_name="Ecosia AI", website="https://www.ecosia.org",
                reasoning="No strong public signal: the site returned 403.",
                statuses=STATUSES,
            )
        )
        return result, capsys.readouterr().out

    def test_prompt_names_the_entity_the_field_and_each_meaning(self, monkeypatch, capsys):
        _, out = self._run(monkeypatch, capsys, ["2"])
        assert "Ecosia AI (https://www.ecosia.org) could not be verified" in out
        assert "the site returned 403" in out
        assert "verification_status" in out
        assert "name and file stay as they are" in out
        assert "1. unverified-startup: a young company" in out
        assert "2. unverified-other: any other reason" in out
        assert "Candidates" not in out and "verbatim" not in out

    def test_number_or_status_returns_that_status(self, monkeypatch, capsys):
        assert self._run(monkeypatch, capsys, ["2"])[0] == "unverified-other"
        assert self._run(monkeypatch, capsys, ["unverified-startup"])[0] == "unverified-startup"

    def test_reject_aborts(self, monkeypatch, capsys):
        assert self._run(monkeypatch, capsys, ["reject"])[0] == "reject"

    def test_a_company_name_is_not_accepted_as_a_status(self, monkeypatch, capsys):
        result, out = self._run(monkeypatch, capsys, ["ecosia", "1"])
        assert result == "unverified-startup"
        assert "'ecosia' is not a verification status" in out
