"""Tests for CheckpointHandler implementations."""

from __future__ import annotations

import pytest

from orchestrator.checkpoints import (
    AutoApproveCheckpointHandler,
    CheckpointHandler,
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
