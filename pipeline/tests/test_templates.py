"""Tests for claim template loading and querying."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.templates import (
    TemplateRecord,
    get_template,
    load_templates,
    render_blocked_title,
    render_claim_text,
    templates_for_entity_type,
    validate_analyst_title,
)


class TestLoadTemplates:
    def test_loads_active_templates_from_yaml(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        assert len(templates) == 14

    def test_returns_template_records(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        assert all(isinstance(t, TemplateRecord) for t in templates)

    def test_first_template_matches_yaml_order(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        first = templates[0]
        assert first.slug == "publishes-sustainability-report"
        assert first.entity_type == "company"
        assert first.topics == ["environmental-impact"]
        assert first.core is True

    def test_load_templates_excludes_inactive(self, repo_root: Path) -> None:
        """load_templates returns only the 'templates' list, not 'inactive_templates'."""
        templates = load_templates(repo_root)
        slugs = {t.slug for t in templates}
        assert "data-jurisdiction" not in slugs


class TestTemplatesForEntityType:
    def test_product_filter_returns_active_product_templates(
        self, repo_root: Path
    ) -> None:
        templates = load_templates(repo_root)
        product_templates = templates_for_entity_type(templates, "product")
        assert len(product_templates) == 7

    def test_company_filter_returns_active_company_templates(
        self, repo_root: Path
    ) -> None:
        templates = load_templates(repo_root)
        company_templates = templates_for_entity_type(templates, "company")
        assert len(company_templates) == 4

    def test_unknown_type_returns_empty(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        result = templates_for_entity_type(templates, "topic")
        assert result == []

    def test_only_returns_core_templates(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        for entity_type in ("product", "company"):
            filtered = templates_for_entity_type(templates, entity_type)
            assert all(t.core for t in filtered)


class TestGetTemplate:
    def test_returns_correct_record(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        t = get_template(templates, "no-training-on-user-data")
        assert t is not None
        assert t.slug == "no-training-on-user-data"
        assert t.entity_type == "product"
        assert t.topics == ["data-privacy"]

    def test_returns_none_for_unknown_slug(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        assert get_template(templates, "nonexistent-slug") is None


class TestRenderClaimText:
    def test_replaces_product_placeholder(self) -> None:
        template = TemplateRecord(
            slug="renewable-energy-hosting",
            text="PRODUCT is hosted on renewable energy",
            entity_type="product",
            topics=["environmental-impact"],
            core=True,
            notes="test",
        )
        result = render_claim_text(template, "Ecosia")
        assert result == "Ecosia is hosted on renewable energy"

    def test_replaces_company_placeholder(self) -> None:
        template = TemplateRecord(
            slug="publishes-sustainability-report",
            text="COMPANY publishes a sustainability or ESG report",
            entity_type="company",
            topics=["environmental-impact"],
            core=True,
            notes="test",
        )
        result = render_claim_text(template, "Anthropic")
        assert result == "Anthropic publishes a sustainability or ESG report"

    def test_expands_vocabulary_placeholder(self) -> None:
        template = TemplateRecord(
            slug="corporate-structure",
            text="COMPANY has STRUCTURE corporate structure",
            entity_type="company",
            topics=["industry-analysis"],
            core=True,
            notes="test",
            vocabulary={"STRUCTURE": ["publicly-traded", "non-profit", "B-corp"]},
        )
        result = render_claim_text(template, "OpenAI")
        assert result == (
            "OpenAI has one of (publicly-traded, non-profit, B-corp) corporate structure"
        )

    def test_expands_multiple_vocabulary_slots(self) -> None:
        template = TemplateRecord(
            slug="multi",
            text="PRODUCT stores data in JURISDICTION under STRUCTURE control",
            entity_type="product",
            topics=["data-privacy"],
            core=True,
            notes="test",
            vocabulary={
                "JURISDICTION": ["EU", "US"],
                "STRUCTURE": ["non-profit", "B-corp"],
            },
        )
        result = render_claim_text(template, "Ecosia")
        assert result == (
            "Ecosia stores data in one of (EU, US) under one of (non-profit, B-corp) control"
        )

    def test_vocabulary_defaults_to_empty(self) -> None:
        template = TemplateRecord(
            slug="renewable-energy-hosting",
            text="PRODUCT is hosted on renewable energy",
            entity_type="product",
            topics=["environmental-impact"],
            core=True,
            notes="test",
        )
        assert template.vocabulary == {}

    def test_corporate_structure_template_has_vocabulary(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        t = get_template(templates, "corporate-structure")
        assert t is not None
        assert "STRUCTURE" in t.vocabulary
        assert "B-corp" in t.vocabulary["STRUCTURE"]

class TestRenderBlockedTitle:
    def test_substitutes_entity_name(self) -> None:
        template = TemplateRecord(
            slug="corporate-structure",
            text="COMPANY has STRUCTURE corporate structure",
            entity_type="company",
            topics=["industry-analysis"],
            core=True,
            notes="test",
            vocabulary={"STRUCTURE": ["publicly-traded", "non-profit", "B-corp"]},
        )
        result = render_blocked_title(template, "Microsoft")
        assert result == "Microsoft has STRUCTURE corporate structure"

    def test_leaves_vocabulary_slot_unexpanded(self) -> None:
        template = TemplateRecord(
            slug="corporate-structure",
            text="COMPANY has STRUCTURE corporate structure",
            entity_type="company",
            topics=["industry-analysis"],
            core=True,
            notes="test",
            vocabulary={"STRUCTURE": ["publicly-traded", "non-profit"]},
        )
        result = render_blocked_title(template, "OpenAI")
        assert "one of" not in result
        assert "STRUCTURE" in result

    def test_no_vocabulary_behaves_like_render_claim_text(self) -> None:
        template = TemplateRecord(
            slug="publishes-sustainability-report",
            text="COMPANY publishes a sustainability or ESG report",
            entity_type="company",
            topics=["environmental-impact"],
            core=True,
            notes="test",
        )
        assert render_blocked_title(template, "Anthropic") == render_claim_text(template, "Anthropic")

    def test_product_entity_type(self) -> None:
        template = TemplateRecord(
            slug="renewable-energy-hosting",
            text="PRODUCT is hosted on renewable energy",
            entity_type="product",
            topics=["environmental-impact"],
            core=True,
            notes="test",
        )
        assert render_blocked_title(template, "ChatGPT") == "ChatGPT is hosted on renewable energy"


class TestValidateAnalystTitle:
    @pytest.fixture
    def vocab_template(self) -> TemplateRecord:
        return TemplateRecord(
            slug="corporate-structure",
            text="COMPANY has STRUCTURE corporate structure",
            entity_type="company",
            topics=["industry-analysis"],
            core=True,
            notes="test",
            vocabulary={"STRUCTURE": ["publicly-traded", "privately-held", "employee-owned"]},
        )

    @pytest.fixture
    def plain_template(self) -> TemplateRecord:
        return TemplateRecord(
            slug="publishes-sustainability-report",
            text="COMPANY publishes a sustainability or ESG report",
            entity_type="company",
            topics=["environmental-impact"],
            core=True,
            notes="test",
        )

    def test_plain_template_exact_match_passes(self, plain_template: TemplateRecord) -> None:
        ok, reason = validate_analyst_title(
            plain_template, "Anthropic", "Anthropic publishes a sustainability or ESG report"
        )
        assert ok and reason is None

    def test_plain_template_paraphrase_fails(self, plain_template: TemplateRecord) -> None:
        ok, reason = validate_analyst_title(
            plain_template, "Anthropic", "Anthropic publishes an ESG and sustainability report"
        )
        assert not ok and reason is not None

    def test_plain_template_added_qualifier_fails(self, plain_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            plain_template, "Anthropic", "Anthropic publishes a sustainability or ESG report annually"
        )
        assert not ok

    def test_vocab_resolved_value_passes(self, vocab_template: TemplateRecord) -> None:
        ok, reason = validate_analyst_title(
            vocab_template, "Microsoft", "Microsoft has publicly-traded corporate structure"
        )
        assert ok and reason is None

    def test_vocab_resolved_with_article_passes(self, vocab_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            vocab_template, "Microsoft", "Microsoft has a publicly-traded corporate structure"
        )
        assert ok

    def test_vocab_resolved_with_an_article_passes(self, vocab_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            vocab_template, "Mondragon", "Mondragon has an employee-owned corporate structure"
        )
        assert ok

    def test_vocab_unresolved_placeholder_fails(self, vocab_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            vocab_template,
            "Anthropic",
            "Anthropic has one of (publicly-traded, privately-held, employee-owned) corporate structure",
        )
        assert not ok

    def test_vocab_disjunction_fails(self, vocab_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            vocab_template,
            "Anthropic",
            "Anthropic's Corporate Structure: Publicly-Traded or Privately-Held?",
        )
        assert not ok

    def test_vocab_value_outside_set_fails(self, vocab_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            vocab_template, "OpenAI", "OpenAI has a for-profit Public Benefit Corporation structure"
        )
        assert not ok

    def test_case_insensitive(self, vocab_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            vocab_template, "Microsoft", "Microsoft Has A Publicly-Traded Corporate Structure"
        )
        assert ok

    def test_whitespace_normalization(self, plain_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            plain_template, "Anthropic", "Anthropic   publishes a  sustainability or ESG report"
        )
        assert ok

    def test_trailing_punctuation_fails(self, plain_template: TemplateRecord) -> None:
        ok, _ = validate_analyst_title(
            plain_template, "Anthropic", "Anthropic publishes a sustainability or ESG report."
        )
        assert not ok


class TestTemplateIsFrozen:
    def test_template_is_frozen(self) -> None:
        template = TemplateRecord(
            slug="test",
            text="PRODUCT test",
            entity_type="product",
            topics=["data-privacy"],
            core=True,
            notes="test",
        )
        with pytest.raises(AttributeError):
            template.slug = "modified"  # type: ignore[misc]
