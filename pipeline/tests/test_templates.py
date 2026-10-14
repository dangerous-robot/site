"""Tests for claim template loading and querying."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
import yaml

from common.templates import (
    TemplateRecord,
    get_template,
    load_templates,
    render_statement,
    templates_for_entity_type,
)
from linter.checks import check_broken_criteria_slug
from linter.runner import load_templates as load_template_slugs
from orchestrator.persistence import append_template_entry

# A copy of research/templates.yaml (taken after the grading_rule seed), so
# these cases do not move when an operator adds or edits a criterion.
TEMPLATES_FIXTURE = Path(__file__).parent / "fixtures" / "templates" / "templates.yaml"


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    (tmp_path / "research").mkdir()
    shutil.copy(TEMPLATES_FIXTURE, tmp_path / "research" / "templates.yaml")
    return tmp_path


class TestLoadTemplates:
    def test_loads_active_templates_from_yaml(self, fixture_root: Path) -> None:
        templates = load_templates(fixture_root)
        assert len(templates) == 16

    def test_returns_template_records(self, fixture_root: Path) -> None:
        templates = load_templates(fixture_root)
        assert all(isinstance(t, TemplateRecord) for t in templates)

    def test_first_template_matches_yaml_order(self, fixture_root: Path) -> None:
        templates = load_templates(fixture_root)
        first = templates[0]
        assert first.slug == "publishes-sustainability-report"
        assert first.entity_type == "company"
        assert first.topics == ["environmental-impact"]
        assert first.core is True

    def test_load_templates_excludes_inactive(self, fixture_root: Path) -> None:
        """load_templates returns only the 'templates' list, not 'inactive_templates'."""
        templates = load_templates(fixture_root)
        slugs = {t.slug for t in templates}
        assert "data-jurisdiction" not in slugs

    def test_grading_rule_loads_and_vocabulary_is_not_a_field(self, fixture_root: Path) -> None:
        template = get_template(load_templates(fixture_root), "renewable-energy-hosting")
        assert template is not None
        assert template.grading_rule.startswith("Verdict encodes degree")
        assert "vocabulary" not in {f.name for f in dataclasses.fields(TemplateRecord)}


class TestResponsibleAIPageCriteria:
    """The Responsible AI chatbots page's claim rows need these criteria active.

    Reads the live registry on purpose: the guard is on the file the page builds from.
    """

    @pytest.mark.parametrize("slug", ["financial-transparency", "open-source-models-only"])
    def test_claim_with_page_criterion_passes_lint(self, repo_root: Path, slug: str) -> None:
        claim = repo_root / "research" / "claims" / "fixture" / f"{slug}.md"
        fms = {str(claim): {"criteria_slug": slug}}
        assert check_broken_criteria_slug([claim], fms, load_template_slugs(repo_root)) == []

    def test_open_weight_wording(self, repo_root: Path) -> None:
        template = get_template(load_templates(repo_root), "open-source-models-only")
        assert template is not None
        assert template.text == "PRODUCT uses only open-weight models"


class TestTemplatesForEntityType:
    def test_product_filter_returns_active_product_templates(
        self, fixture_root: Path
    ) -> None:
        templates = load_templates(fixture_root)
        product_templates = templates_for_entity_type(templates, "product")
        assert len(product_templates) == 8

    def test_company_filter_returns_active_company_templates(
        self, fixture_root: Path
    ) -> None:
        templates = load_templates(fixture_root)
        company_templates = templates_for_entity_type(templates, "company")
        assert len(company_templates) == 5

    def test_unknown_type_returns_empty(self, fixture_root: Path) -> None:
        templates = load_templates(fixture_root)
        result = templates_for_entity_type(templates, "unknown-type")
        assert result == []

    def test_only_returns_core_templates(self, fixture_root: Path) -> None:
        templates = load_templates(fixture_root)
        for entity_type in ("product", "company"):
            filtered = templates_for_entity_type(templates, entity_type)
            assert all(t.core for t in filtered)


class TestGetTemplate:
    def test_returns_correct_record(self, fixture_root: Path) -> None:
        templates = load_templates(fixture_root)
        t = get_template(templates, "no-training-on-user-data")
        assert t is not None
        assert t.slug == "no-training-on-user-data"
        assert t.entity_type == "product"
        assert t.topics == ["data-privacy"]

    def test_returns_none_for_unknown_slug(self, fixture_root: Path) -> None:
        templates = load_templates(fixture_root)
        assert get_template(templates, "nonexistent-slug") is None


class TestRenderStatement:
    def test_replaces_the_entity_types_placeholder(self) -> None:
        template = TemplateRecord(
            slug="renewable-energy-hosting", text="PRODUCT is hosted on renewable energy",
            entity_type="product", topics=["environmental-impact"], core=True,
        )
        assert render_statement(template, "Ecosia") == "Ecosia is hosted on renewable energy"

    def test_text_without_a_placeholder_is_unchanged(self) -> None:
        template = TemplateRecord(
            slug="corporate-structure", text="Every lab has STRUCTURE corporate structure",
            entity_type="company", topics=["industry-analysis"], core=True,
        )
        assert render_statement(template, "OpenAI") == "Every lab has STRUCTURE corporate structure"


class TestAppendTemplateEntry:
    ENTRY = {
        "slug": "probe-new-criterion", "text": "PRODUCT says \"hello\": twice",
        "entity_type": "product", "topics": ["data-privacy"], "core": False,
    }

    def test_duplicate_slug_raises_and_leaves_the_file(self, fixture_root: Path) -> None:
        path = fixture_root / "research" / "templates.yaml"
        before = path.read_bytes()
        for slug in ("renewable-energy-hosting", "data-jurisdiction"):  # active, inactive
            with pytest.raises(ValueError, match=slug):
                append_template_entry(fixture_root, {**self.ENTRY, "slug": slug})
        assert path.read_bytes() == before

    def test_entry_lands_in_templates_before_inactive_templates(self, fixture_root: Path) -> None:
        path = fixture_root / "research" / "templates.yaml"
        before_text = path.read_text(encoding="utf-8")
        before = yaml.safe_load(before_text)
        append_template_entry(fixture_root, dict(self.ENTRY))
        after_text = path.read_text(encoding="utf-8")
        after = yaml.safe_load(after_text)
        assert after["templates"][:-1] == before["templates"]
        assert after["templates"][-1] == self.ENTRY
        assert after["inactive_templates"] == before["inactive_templates"]
        assert after_text.index("probe-new-criterion") < after_text.index("inactive_templates:")
        for line in before_text.splitlines():
            if line.lstrip().startswith("#"):
                assert line in after_text, line
        assert get_template(load_templates(fixture_root), "probe-new-criterion") is not None

    def test_entry_appends_when_templates_is_the_last_key(self, tmp_path: Path) -> None:
        path = tmp_path / "research" / "templates.yaml"
        path.parent.mkdir()
        path.write_text(
            "templates:\n  - slug: first\n    text: PRODUCT is first\n    entity_type: product\n"
            "    topics: [ai-safety]\n    core: true\n",
            encoding="utf-8",
        )
        append_template_entry(tmp_path, dict(self.ENTRY))
        assert [t["slug"] for t in yaml.safe_load(path.read_text())["templates"]] == [
            "first", "probe-new-criterion",
        ]


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


class TestSubjectTemplateSchema:
    """Validate the subjects: field on Template.

    Required-iff-subject and forbidden-otherwise. Each subject ref must match
    ``^subjects/[a-z0-9-]+$``.

    TODO: gate this test in CI on changes to research/templates.yaml so a
    malformed subjects: list can't merge undetected. Until per-path CI exists,
    this test runs with the rest of pytest.
    """

    def test_subject_template_with_valid_subjects_passes(self) -> None:
        template = TemplateRecord(
            slug="x",
            text="ENTITY does Y",
            entity_type="subject",
            topics=["ai-safety"],
            core=True,
            subjects=["subjects/ai-model-producers"],
        )
        assert template.subjects == ["subjects/ai-model-producers"]

    def test_subject_template_missing_subjects_fails(self) -> None:
        with pytest.raises(ValueError, match="subjects required"):
            TemplateRecord(
                slug="x",
                text="ENTITY does Y",
                entity_type="subject",
                topics=["ai-safety"],
                core=True,
            )

    def test_subject_template_empty_subjects_fails(self) -> None:
        with pytest.raises(ValueError, match="subjects required"):
            TemplateRecord(
                slug="x",
                text="ENTITY does Y",
                entity_type="subject",
                topics=["ai-safety"],
                core=True,
                subjects=[],
            )

    def test_non_subject_template_with_subjects_fails(self) -> None:
        with pytest.raises(ValueError, match="subjects forbidden"):
            TemplateRecord(
                slug="x",
                text="COMPANY does Y",
                entity_type="company",
                topics=["ai-safety"],
                core=True,
                subjects=["subjects/whatever"],
            )

    def test_subject_template_invalid_ref_fails(self) -> None:
        with pytest.raises(ValueError, match="invalid subject ref"):
            TemplateRecord(
                slug="x",
                text="ENTITY does Y",
                entity_type="subject",
                topics=["ai-safety"],
                core=True,
                subjects=["companies/foo"],
            )


class TestTemplatesForEntityTypeSubjectFanOut:
    """Subject fan-out filters by template.subjects: list membership."""

    @staticmethod
    def _mk(slug: str, subjects: list[str]) -> TemplateRecord:
        return TemplateRecord(
            slug=slug,
            text="ENTITY does Y",
            entity_type="subject",
            topics=["ai-safety"],
            core=True,
            subjects=subjects,
        )

    def test_returns_only_templates_naming_the_subject(self) -> None:
        templates = [
            self._mk("a", ["subjects/foo"]),
            self._mk("b", ["subjects/bar"]),
            self._mk("c", ["subjects/foo", "subjects/bar"]),
        ]
        out = templates_for_entity_type(templates, "subject", entity_slug="foo")
        slugs = sorted(t.slug for t in out)
        assert slugs == ["a", "c"]

    def test_subject_with_no_matching_template_returns_empty(self) -> None:
        templates = [self._mk("a", ["subjects/foo"])]
        out = templates_for_entity_type(templates, "subject", entity_slug="unreferenced")
        assert out == []

    def test_subject_with_none_slug_returns_empty(self) -> None:
        """entity_slug=None for subject is undefined; conservative: return [].

        Returning all subject templates would silently break N:M filtering.
        """
        templates = [self._mk("a", ["subjects/foo"])]
        out = templates_for_entity_type(templates, "subject", entity_slug=None)
        assert out == []

    def test_company_ignores_entity_slug(self) -> None:
        company_t = TemplateRecord(
            slug="ct",
            text="COMPANY does X",
            entity_type="company",
            topics=["ai-safety"],
            core=True,
        )
        out = templates_for_entity_type([company_t], "company", entity_slug="anything")
        assert [t.slug for t in out] == ["ct"]
