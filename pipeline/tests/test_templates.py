"""Tests for claim template loading and querying."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.templates import (
    TemplateRecord,
    get_template,
    load_templates,
    render_claim_text,
    templates_for_entity_type,
)


class TestLoadTemplates:
    def test_loads_all_19_templates(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        assert len(templates) == 19

    def test_returns_template_records(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        assert all(isinstance(t, TemplateRecord) for t in templates)

    def test_first_template_is_renewable_energy(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        first = templates[0]
        assert first.slug == "renewable-energy-hosting"
        assert first.entity_type == "product"
        assert first.category == "environmental-impact"
        assert first.core is True


class TestTemplatesForEntityType:
    def test_product_returns_13(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        product_templates = templates_for_entity_type(templates, "product")
        assert len(product_templates) == 13

    def test_company_returns_6(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        company_templates = templates_for_entity_type(templates, "company")
        assert len(company_templates) == 6

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
        t = get_template(templates, "data-jurisdiction")
        assert t is not None
        assert t.slug == "data-jurisdiction"
        assert t.entity_type == "product"
        assert t.category == "data-privacy"

    def test_returns_none_for_unknown_slug(self, repo_root: Path) -> None:
        templates = load_templates(repo_root)
        assert get_template(templates, "nonexistent-slug") is None


class TestRenderClaimText:
    def test_replaces_product_placeholder(self) -> None:
        template = TemplateRecord(
            slug="renewable-energy-hosting",
            text="PRODUCT is hosted on renewable energy",
            entity_type="product",
            category="environmental-impact",
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
            category="environmental-impact",
            core=True,
            notes="test",
        )
        result = render_claim_text(template, "Anthropic")
        assert result == "Anthropic publishes a sustainability or ESG report"

    def test_replaces_company_in_structure_template(self) -> None:
        template = TemplateRecord(
            slug="corporate-structure",
            text="COMPANY has STRUCTURE corporate structure",
            entity_type="company",
            category="industry-analysis",
            core=True,
            notes="test",
        )
        result = render_claim_text(template, "OpenAI")
        assert result == "OpenAI has STRUCTURE corporate structure"

    def test_template_is_frozen(self) -> None:
        template = TemplateRecord(
            slug="test",
            text="PRODUCT test",
            entity_type="product",
            category="test",
            core=True,
            notes="test",
        )
        with pytest.raises(AttributeError):
            template.slug = "modified"  # type: ignore[misc]
