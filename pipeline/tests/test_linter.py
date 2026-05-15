"""Unit tests for dr lint check functions. No disk I/O — all inputs are fixture dicts."""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from linter.checks import (
    check_broken_criteria_slug,
    check_broken_source_refs,
    check_duplicate_entity_slugs,
    check_empty_required_strings,
    check_entity_type_dir_mismatch,
    check_future_as_of,
    check_legacy_field_name,
    check_missing_criteria_slug,
    check_missing_required_fields,
    check_missing_seo_title,
    check_orphaned_claims,
    check_placeholder_website,
    check_published_criterion,
    check_published_review_signoff,
    check_stale_recheck,
    check_unknown_frontmatter_keys,
    check_unreferenced_entities,
    check_unreferenced_sources,
)


def _p(path: str) -> Path:
    return Path(path)


class TestOrphanedClaims:
    def test_valid_entity_ref_no_issue(self):
        claim = _p("research/claims/ecosia/publishes-sustainability-report.md")
        fms = {str(claim): {"entity": "companies/ecosia"}}
        entity_index = {"companies/ecosia"}
        assert check_orphaned_claims([claim], fms, entity_index) == []

    def test_missing_entity_raises_error(self):
        claim = _p("research/claims/missing-co/some-claim.md")
        fms = {str(claim): {"entity": "companies/missing-co"}}
        issues = check_orphaned_claims([claim], fms, set())
        assert len(issues) == 1
        assert issues[0].check_id == "orphaned-claim"
        assert issues[0].severity == "error"

    def test_missing_entity_field_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {}}
        assert check_orphaned_claims([claim], fms, set()) == []


class TestMissingRequiredFields:
    def test_all_required_present_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {
            "title": "T", "entity": "companies/foo", "topics": ["ai-safety"],
            "verdict": "true", "confidence": "high", "as_of": datetime.date.today(),
            "sources": [],
        }}
        assert check_missing_required_fields([claim], fms) == []

    def test_missing_verdict_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"title": "T", "entity": "companies/foo", "topics": ["ai-safety"],
                             "confidence": "high", "as_of": datetime.date.today(), "sources": []}}
        issues = check_missing_required_fields([claim], fms)
        assert any(i.check_id == "missing-required-field" and "verdict" in i.message for i in issues)


class TestPublishedCriterion:
    def test_draft_without_criterion_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "draft"}}
        assert check_published_criterion([claim], fms) == []

    def test_published_with_criterion_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published", "criteria_slug": "renewable-energy-hosting"}}
        assert check_published_criterion([claim], fms) == []

    def test_published_without_criterion_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published"}}
        issues = check_published_criterion([claim], fms)
        assert len(issues) == 1
        assert issues[0].check_id == "published-without-criterion"
        assert issues[0].severity == "error"

    def test_published_with_empty_criterion_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published", "criteria_slug": "   "}}
        issues = check_published_criterion([claim], fms)
        assert len(issues) == 1
        assert issues[0].check_id == "published-without-criterion"

    def test_archived_status_not_checked(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "archived"}}
        assert check_published_criterion([claim], fms) == []


class TestPublishedReviewSignoff:
    def test_draft_with_no_sidecar_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "draft"}}
        sidecars = {str(claim): None}
        assert check_published_review_signoff([claim], fms, sidecars) == []

    def test_published_with_reviewed_at_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published"}}
        sidecars = {str(claim): {"human_review": {"reviewed_at": datetime.date.today()}}}
        assert check_published_review_signoff([claim], fms, sidecars) == []

    def test_published_without_sidecar_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published"}}
        sidecars = {str(claim): None}
        issues = check_published_review_signoff([claim], fms, sidecars)
        assert len(issues) == 1
        assert issues[0].check_id == "published-without-review"
        assert issues[0].severity == "error"
        assert "no audit sidecar" in issues[0].message

    def test_published_with_null_reviewed_at_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published"}}
        sidecars = {str(claim): {"human_review": {"reviewed_at": None}}}
        issues = check_published_review_signoff([claim], fms, sidecars)
        assert len(issues) == 1
        assert issues[0].check_id == "published-without-review"
        assert issues[0].severity == "error"
        assert "human_review.reviewed_at" in issues[0].message

    def test_published_with_missing_human_review_block_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published"}}
        sidecars = {str(claim): {"schema_version": 1}}
        issues = check_published_review_signoff([claim], fms, sidecars)
        assert len(issues) == 1
        assert issues[0].check_id == "published-without-review"
        assert issues[0].severity == "error"

    def test_archived_published_status_not_checked(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "archived"}}
        sidecars = {str(claim): None}
        assert check_published_review_signoff([claim], fms, sidecars) == []


class TestEmptyRequiredStrings:
    def test_empty_title_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"title": "   ", "entity": "companies/foo", "verdict": "true",
                             "topics": ["ai-safety"], "confidence": "high"}}
        issues = check_empty_required_strings([claim], fms, [], {})
        assert any(i.check_id == "empty-required-string" and "title" in i.message for i in issues)

    def test_empty_entity_description_raises_error(self):
        entity = _p("research/entities/companies/foo.md")
        efms = {str(entity): {"name": "Foo", "description": ""}}
        issues = check_empty_required_strings([], {}, [entity], efms)
        assert any(i.check_id == "empty-required-string" and "description" in i.message for i in issues)


class TestBrokenCriteriaSlug:
    def test_valid_slug_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"criteria_slug": "publishes-sustainability-report"}}
        assert check_broken_criteria_slug([claim], fms, {"publishes-sustainability-report"}) == []

    def test_unknown_slug_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"criteria_slug": "nonexistent-slug"}}
        issues = check_broken_criteria_slug([claim], fms, {"other-slug"})
        assert len(issues) == 1
        assert issues[0].check_id == "broken-criteria-slug"

    def test_absent_slug_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {}}
        assert check_broken_criteria_slug([claim], fms, set()) == []


class TestBrokenSourceRefs:
    def test_valid_source_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"sources": ["2025/some-source"]}}
        assert check_broken_source_refs([claim], fms, {"2025/some-source"}) == []

    def test_missing_source_raises_error(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"sources": ["2025/nonexistent"]}}
        issues = check_broken_source_refs([claim], fms, set())
        assert len(issues) == 1
        assert issues[0].check_id == "broken-source-ref"


class TestDuplicateEntitySlugs:
    def test_no_duplicates_no_issue(self):
        files = [_p("research/entities/companies/foo.md"), _p("research/entities/products/bar.md")]
        assert check_duplicate_entity_slugs(files) == []

    def test_same_slug_across_types_allowed(self):
        files = [_p("research/entities/companies/greenpt.md"), _p("research/entities/products/greenpt.md")]
        assert check_duplicate_entity_slugs(files) == []

    def test_same_slug_within_type_raises_error(self):
        files = [_p("research/entities/companies/foo.md"), _p("research/entities/companies/foo.md")]
        issues = check_duplicate_entity_slugs(files)
        assert len(issues) == 1
        assert issues[0].check_id == "duplicate-entity-slug"


class TestPlaceholderWebsite:
    def test_login_url_raises_warning(self):
        entity = _p("research/entities/companies/foo.md")
        efms = {str(entity): {"website": "https://www.foo.ai/login"}}
        issues = check_placeholder_website([entity], efms)
        assert len(issues) == 1
        assert issues[0].check_id == "placeholder-website"

    def test_real_url_no_issue(self):
        entity = _p("research/entities/companies/foo.md")
        efms = {str(entity): {"website": "https://www.foo.ai"}}
        assert check_placeholder_website([entity], efms) == []


class TestLegacyFieldName:
    def test_standard_slug_raises_warning(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"standard_slug": "some-slug"}}
        issues = check_legacy_field_name([claim], fms)
        assert len(issues) == 1
        assert issues[0].check_id == "legacy-field-name"

    def test_criteria_slug_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"criteria_slug": "some-slug"}}
        assert check_legacy_field_name([claim], fms) == []


class TestMissingCriteriaSlug:
    def test_missing_slug_raises_info(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {}}
        issues = check_missing_criteria_slug([claim], fms)
        assert len(issues) == 1
        assert issues[0].severity == "info"

    def test_present_slug_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"criteria_slug": "some-slug"}}
        assert check_missing_criteria_slug([claim], fms) == []


class TestMissingSeoTitle:
    def test_published_without_seo_title_raises_info(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published"}}
        issues = check_missing_seo_title([claim], fms)
        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].check_id == "missing-seo-title"

    def test_published_with_seo_title_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "published", "seo_title": "Short title"}}
        assert check_missing_seo_title([claim], fms) == []

    def test_draft_without_seo_title_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"status": "draft"}}
        assert check_missing_seo_title([claim], fms) == []


class TestStaleRecheck:
    def test_past_due_raises_info(self):
        claim = _p("research/claims/foo/bar.md")
        past = datetime.date(2020, 1, 1)
        fms = {str(claim): {"next_recheck_due": past}}
        issues = check_stale_recheck([claim], fms, datetime.date.today())
        assert len(issues) == 1
        assert issues[0].check_id == "stale-recheck"

    def test_future_due_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        future = datetime.date(2099, 1, 1)
        fms = {str(claim): {"next_recheck_due": future}}
        assert check_stale_recheck([claim], fms, datetime.date.today()) == []


class TestFutureAsOf:
    def test_future_as_of_raises_info(self):
        claim = _p("research/claims/foo/bar.md")
        future = datetime.date(2099, 1, 1)
        fms = {str(claim): {"as_of": future}}
        issues = check_future_as_of([claim], fms, datetime.date.today())
        assert len(issues) == 1
        assert issues[0].check_id == "future-as-of"

    def test_past_as_of_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        past = datetime.date(2020, 1, 1)
        fms = {str(claim): {"as_of": past}}
        assert check_future_as_of([claim], fms, datetime.date.today()) == []


class TestEntityTypeDirMismatch:
    def test_type_matches_dir_no_issue(self):
        entity = _p("research/entities/companies/foo.md")
        efms = {str(entity): {"type": "company"}}
        assert check_entity_type_dir_mismatch([entity], efms) == []

    def test_type_mismatches_dir_raises_warning(self):
        entity = _p("research/entities/companies/foo.md")
        efms = {str(entity): {"type": "product"}}
        issues = check_entity_type_dir_mismatch([entity], efms)
        assert len(issues) == 1
        assert issues[0].check_id == "entity-type-dir-mismatch"


class TestUnknownFrontmatterKeys:
    def test_canonical_keys_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"title": "T", "entity": "companies/foo", "criteria_slug": "x"}}
        assert check_unknown_frontmatter_keys([claim], fms, [], {}) == []

    def test_unknown_key_raises_warning(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"title": "T", "extra_field": "value"}}
        issues = check_unknown_frontmatter_keys([claim], fms, [], {})
        assert any(i.check_id == "unknown-frontmatter-key" and "extra_field" in i.message for i in issues)


class TestUnreferencedSources:
    def test_all_sources_referenced_no_issue(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"sources": ["2025/foo"]}}
        src = _p("research/sources/2025/foo.md")
        assert check_unreferenced_sources([claim], fms, {"2025/foo": src}) == []

    def test_unreferenced_source_warns(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {"sources": ["2025/foo"]}}
        src_used = _p("research/sources/2025/foo.md")
        src_orphan = _p("research/sources/2025/orphan.md")
        issues = check_unreferenced_sources(
            [claim], fms, {"2025/foo": src_used, "2025/orphan": src_orphan}
        )
        assert len(issues) == 1
        assert issues[0].check_id == "unreferenced-source"
        assert issues[0].severity == "warning"
        assert "2025/orphan" in issues[0].message

    def test_no_claims_all_sources_flagged(self):
        src = _p("research/sources/2025/foo.md")
        issues = check_unreferenced_sources([], {}, {"2025/foo": src})
        assert len(issues) == 1
        assert issues[0].check_id == "unreferenced-source"

    def test_sources_list_not_present_treats_as_empty(self):
        claim = _p("research/claims/foo/bar.md")
        fms = {str(claim): {}}  # no sources key
        src = _p("research/sources/2025/foo.md")
        issues = check_unreferenced_sources([claim], fms, {"2025/foo": src})
        assert len(issues) == 1


class TestUnreferencedEntities:
    def test_all_entities_referenced_no_issue(self):
        claim = _p("research/claims/ecosia/some-claim.md")
        fms = {str(claim): {"entity": "companies/ecosia"}}
        ent = _p("research/entities/companies/ecosia.md")
        assert check_unreferenced_entities([claim], fms, {"companies/ecosia": ent}) == []

    def test_unreferenced_entity_info(self):
        claim = _p("research/claims/ecosia/some-claim.md")
        fms = {str(claim): {"entity": "companies/ecosia"}}
        ent_used = _p("research/entities/companies/ecosia.md")
        ent_orphan = _p("research/entities/companies/ghost-corp.md")
        issues = check_unreferenced_entities(
            [claim], fms, {"companies/ecosia": ent_used, "companies/ghost-corp": ent_orphan}
        )
        assert len(issues) == 1
        assert issues[0].check_id == "unreferenced-entity"
        assert issues[0].severity == "info"
        assert "ghost-corp" in issues[0].message

    def test_no_claims_all_entities_flagged(self):
        ent = _p("research/entities/companies/foo.md")
        issues = check_unreferenced_entities([], {}, {"companies/foo": ent})
        assert len(issues) == 1
