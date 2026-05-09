"""Tests for the entity verifier agent."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from common.models import EntityType
from orchestrator.pipeline import LightResearchBundle
from researcher.entity_verifier import (
    VerificationOutcome,
    build_entity_verifier_prompt,
    entity_verifier_agent,
)


def _bundle(entity_type: EntityType, **overrides) -> LightResearchBundle:
    base = dict(
        entity_name="Acme Corp",
        entity_type=entity_type,
        raw_description="Acme Corp is a company that makes things.",
        entity_website="https://acme.example.com",
        probe_excludes=[],
    )
    base.update(overrides)
    return LightResearchBundle(**base)


# --------------------------------------------------------------------------- #
# Per-type prompt construction                                                 #
# --------------------------------------------------------------------------- #

class TestPromptPerType:
    def test_company_section_lists_company_signals(self) -> None:
        bundle = _bundle(EntityType.COMPANY, entity_name="Anthropic")
        prompt = build_entity_verifier_prompt(bundle)
        assert "Per-type guidance (company):" in prompt
        assert "Per-type guidance (product):" not in prompt
        assert "Per-type guidance (subject):" not in prompt
        # Company signals: at least one of the documented anchors.
        assert "SEC EDGAR" in prompt or "Companies House" in prompt
        assert "Wikipedia" in prompt
        assert "name collides" in prompt.lower() or "collides with" in prompt.lower()

    def test_product_section_carries_self_publication_carve_out(self) -> None:
        bundle = _bundle(EntityType.PRODUCT, entity_name="Claude Code")
        prompt = build_entity_verifier_prompt(bundle)
        assert "Per-type guidance (product):" in prompt
        assert "Per-type guidance (company):" not in prompt
        assert "Per-type guidance (subject):" not in prompt
        # Product signals.
        assert "parent company" in prompt.lower() or "official site" in prompt.lower()
        # Self-publication carve-out: same-name-as-parent is NOT a halt.
        assert "self-publication" in prompt.lower()
        assert "greenpt" in prompt.lower() or "treadlightlyai" in prompt.lower()

    def test_subject_section_lists_consensus_signals(self) -> None:
        bundle = _bundle(EntityType.SUBJECT, entity_name="generative AI")
        prompt = build_entity_verifier_prompt(bundle)
        assert "Per-type guidance (subject):" in prompt
        assert "Per-type guidance (company):" not in prompt
        assert "Per-type guidance (product):" not in prompt
        assert (
            "encyclopedic" in prompt.lower()
            or "academic" in prompt.lower()
            or "dictionary" in prompt.lower()
        )
        assert "multiple unrelated definitions" in prompt.lower()


# --------------------------------------------------------------------------- #
# Outcome routing: TestModel yields canned VerificationOutcome per status      #
# --------------------------------------------------------------------------- #

class TestVerifierAgentRoundtrip:
    @pytest.mark.asyncio
    async def test_test_model_yields_verified(self) -> None:
        canned = {
            "status": "verified",
            "candidates": [],
            "reasoning": "Wikipedia article and SEC filings name a single Anthropic.",
        }
        with entity_verifier_agent.override(
            model=TestModel(custom_output_args=canned),
        ):
            res = await entity_verifier_agent.run("ignored")
        outcome = res.output
        assert isinstance(outcome, VerificationOutcome)
        assert outcome.status == "verified"
        assert outcome.candidates == []

    @pytest.mark.asyncio
    async def test_test_model_yields_needs_disambiguation(self) -> None:
        canned = {
            "status": "needs-disambiguation",
            "candidates": ["Apple Inc.", "Apple Records"],
            "reasoning": "Two distinct entities named Apple in unrelated industries.",
        }
        with entity_verifier_agent.override(
            model=TestModel(custom_output_args=canned),
        ):
            res = await entity_verifier_agent.run("ignored")
        outcome = res.output
        assert outcome.status == "needs-disambiguation"
        assert outcome.candidates == ["Apple Inc.", "Apple Records"]
        # Alphabetical, distinct.
        assert outcome.candidates == sorted(outcome.candidates)
        assert len(set(outcome.candidates)) == len(outcome.candidates)

    @pytest.mark.asyncio
    async def test_test_model_yields_unverified(self) -> None:
        canned = {
            "status": "unverified",
            "candidates": [],
            "reasoning": "No public signals were found in the inputs.",
        }
        with entity_verifier_agent.override(
            model=TestModel(custom_output_args=canned),
        ):
            res = await entity_verifier_agent.run("ignored")
        outcome = res.output
        assert outcome.status == "unverified"
        assert outcome.candidates == []
