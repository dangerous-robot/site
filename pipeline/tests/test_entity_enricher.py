"""Tests for the entity enricher agent."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from common.models import EntityType
from orchestrator.pipeline import LightResearchBundle
from researcher.entity_enricher import (
    EnrichmentDraft,
    build_entity_enricher_prompt,
    entity_enricher_agent,
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
    def test_company_section_solicits_founded(self) -> None:
        bundle = _bundle(EntityType.COMPANY, entity_name="Anthropic")
        prompt = build_entity_enricher_prompt(bundle)
        assert "Per-type guidance (company):" in prompt
        assert "Per-type guidance (product):" not in prompt
        assert "Per-type guidance (subject):" not in prompt
        assert "Solicit ``founded``" in prompt
        # The legal-name carve-out is part of the company section per the
        # operator-set lazy-backfill rule.
        assert "legal name" in prompt.lower()

    def test_product_section_solicits_founded_and_maker(self) -> None:
        bundle = _bundle(EntityType.PRODUCT, entity_name="Claude Code")
        prompt = build_entity_enricher_prompt(bundle)
        assert "Per-type guidance (product):" in prompt
        assert "Per-type guidance (company):" not in prompt
        assert "Per-type guidance (subject):" not in prompt
        assert "year the product first launched" in prompt

    def test_subject_section_omits_founded(self) -> None:
        bundle = _bundle(EntityType.SUBJECT, entity_name="generative AI")
        prompt = build_entity_enricher_prompt(bundle)
        assert "Per-type guidance (subject):" in prompt
        assert "Per-type guidance (company):" not in prompt
        assert "Per-type guidance (product):" not in prompt
        # Subject section explicitly tells the model to leave founded null.
        assert "leave ``founded`` null" in prompt

    def test_prompt_carries_inputs(self) -> None:
        bundle = _bundle(
            EntityType.COMPANY,
            entity_name="Acme",
            entity_website="https://acme.example.com",
            probe_excludes=["acmestores.com", "acme-records.example"],
        )
        prompt = build_entity_enricher_prompt(bundle)
        assert "Entity name: Acme" in prompt
        assert "Website: https://acme.example.com" in prompt
        assert "Avoid confusion with: acmestores.com, acme-records.example" in prompt
        assert "Webpage summary:" in prompt
        assert "Acme Corp is a company that makes things." in prompt

    def test_prompt_handles_empty_summary(self) -> None:
        bundle = _bundle(EntityType.COMPANY, raw_description="")
        prompt = build_entity_enricher_prompt(bundle)
        assert "(no webpage summary collected)" in prompt


# --------------------------------------------------------------------------- #
# Recorded-fixture integration: TestModel yields a canned EnrichmentDraft       #
# --------------------------------------------------------------------------- #

class TestEnricherAgentRoundtrip:
    @pytest.mark.asyncio
    async def test_test_model_yields_canned_draft(self) -> None:
        canned = {
            "founded": 2021,
            "description": "Anthropic is an AI safety lab.",
            "history_markdown": (
                "Anthropic was founded in 2021 by former OpenAI researchers.\n\n"
                "It develops the Claude family of models with a focus on safety."
            ),
        }
        with entity_enricher_agent.override(
            model=TestModel(custom_output_args=canned),
        ):
            res = await entity_enricher_agent.run("ignored prompt; TestModel returns canned output")

        draft = res.output
        assert isinstance(draft, EnrichmentDraft)
        assert draft.founded == 2021
        assert draft.description.startswith("Anthropic is")
        assert "safety" in draft.history_markdown


# --------------------------------------------------------------------------- #
# Subsumption: enricher's `description` is non-empty for a normal bundle        #
# --------------------------------------------------------------------------- #

class TestEnricherSubsumesTightening:
    @pytest.mark.asyncio
    async def test_description_is_non_empty_for_typical_bundle(self) -> None:
        """The enricher takes over from the standalone tightening agent.

        Sanity check: a typical light-research bundle (a webpage summary
        already populated) flows through to a non-empty ``description``
        in the draft. The actual one-sentence shape is the model's job;
        TestModel's canned output proxies for "model returned something".
        """
        bundle = _bundle(
            EntityType.COMPANY,
            entity_name="Anthropic",
            raw_description=(
                "Anthropic is an AI safety company. Our mission is to "
                "build reliable, interpretable AI systems."
            ),
        )
        canned = {
            "founded": 2021,
            "description": "Anthropic is an AI safety company.",
            "history_markdown": (
                "Anthropic was founded in 2021.\n\n"
                "It builds the Claude family of models."
            ),
        }
        prompt = build_entity_enricher_prompt(bundle)
        with entity_enricher_agent.override(
            model=TestModel(custom_output_args=canned),
        ):
            res = await entity_enricher_agent.run(prompt)
        assert res.output.description.strip(), "enricher must yield non-empty description"
