"""Pure check functions. No disk I/O — all indexes are pre-built by runner.py."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import LintIssue

REQUIRED_CLAIM_FIELDS = {"title", "entity", "topics", "verdict", "confidence", "as_of", "sources"}
CANONICAL_ENTITY_KEYS = {"name", "type", "website", "aliases", "description", "parent_company", "search_hints"}
CANONICAL_CLAIM_KEYS = {
    "title", "entity", "topics", "verdict", "confidence",
    "takeaway", "criteria_slug", "status", "phase", "blocked_reason",
    "as_of", "sources", "recheck_cadence_days", "next_recheck_due",
    "audit", "seo_title",
}
PLACEHOLDER_PATHS = {"/login", "/signup", "/register"}
PLACEHOLDER_DOMAINS = {"example.com", "example.org"}
ENTITY_DIR_TO_TYPE = {
    "companies": "company",
    "products": "product",
    "topics": "topic",
    "sectors": "sector",
}


def check_orphaned_claims(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    entity_index: set[str],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        entity_ref = fm.get("entity", "")
        if entity_ref and entity_ref not in entity_index:
            issues.append(LintIssue(
                path=str(path),
                check_id="orphaned-claim",
                severity="error",
                message=f'entity "{entity_ref}" has no matching file in research/entities/',
                hint=(
                    f'if the entity is missing, run `dr onboard "{entity_ref}" --type <type>`; '
                    f'if it exists under a different path, correct the `entity:` field'
                ),
            ))
    return issues


def check_missing_required_fields(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        for field in sorted(REQUIRED_CLAIM_FIELDS):
            if field not in fm:
                issues.append(LintIssue(
                    path=str(path),
                    check_id="missing-required-field",
                    severity="error",
                    message=f'required field "{field}" is absent',
                    hint=f'add `{field}:` to the claim frontmatter',
                ))
    return issues


def check_published_criterion(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    """Published claims must declare a `criteria_slug`.

    A criterion is the join key for cross-entity comparison, criterion-driven
    re-evaluation, and onboard-time propagation. Drafts may carry no criterion
    (operator may still be exploring); published claims may not.
    """
    from common.frontmatter import has_criterion

    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        if fm.get("status") != "published":
            continue
        if not has_criterion(fm):
            issues.append(LintIssue(
                path=str(path),
                check_id="published-without-criterion",
                severity="error",
                message="published claim has no `criteria_slug`",
                hint=(
                    "set `criteria_slug:` in the claim frontmatter to a slug from "
                    "research/templates.yaml (or add a new template entry first)"
                ),
            ))
    return issues


def check_published_review_signoff(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    claim_sidecars: dict[str, dict[str, Any] | None],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        if fm.get("status") != "published":
            continue
        sidecar = claim_sidecars.get(str(path))
        if sidecar is None:
            issues.append(LintIssue(
                path=str(path),
                check_id="published-without-review",
                severity="warning",
                message="published claim has no audit sidecar; reviewer sign-off is missing",
                hint="run `dr review --approve <claim>` to record sign-off, or set `status: draft`",
            ))
            continue
        review = sidecar.get("human_review") or {}
        if not review.get("reviewed_at"):
            issues.append(LintIssue(
                path=str(path),
                check_id="published-without-review",
                severity="warning",
                message="published claim's audit sidecar has no `human_review.reviewed_at`",
                hint="run `dr review --approve <claim>` to record sign-off, or set `status: draft`",
            ))
    return issues


def check_empty_required_strings(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    entity_files: list[Path],
    entity_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    issues = []
    # `topics` is a list, not a string field, so it is not in this set.
    string_fields = {"title", "entity", "verdict", "confidence"}
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        for field in string_fields:
            val = fm.get(field)
            if isinstance(val, str) and not val.strip():
                issues.append(LintIssue(
                    path=str(path),
                    check_id="empty-required-string",
                    severity="error",
                    message=f'required string field "{field}" is empty or whitespace',
                ))
    for path in entity_files:
        fm = entity_frontmatters.get(str(path), {})
        for field in ("name", "description"):
            val = fm.get(field)
            if isinstance(val, str) and not val.strip():
                issues.append(LintIssue(
                    path=str(path),
                    check_id="empty-required-string",
                    severity="error",
                    message=f'required string field "{field}" is empty or whitespace',
                ))
    return issues


def check_broken_criteria_slug(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    template_slugs: set[str],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        slug = fm.get("criteria_slug")
        if slug and slug not in template_slugs:
            issues.append(LintIssue(
                path=str(path),
                check_id="broken-criteria-slug",
                severity="error",
                message=f'criteria_slug "{slug}" not found in research/templates.yaml',
                hint='check the slug spelling or add the template to templates.yaml',
            ))
    return issues


def check_broken_source_refs(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    source_ids: set[str],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        sources = fm.get("sources") or []
        if not isinstance(sources, list):
            continue
        for src_id in sources:
            if isinstance(src_id, str) and src_id not in source_ids:
                issues.append(LintIssue(
                    path=str(path),
                    check_id="broken-source-ref",
                    severity="error",
                    message=f'source id "{src_id}" has no matching file in research/sources/',
                    hint=f'expected file at research/sources/{src_id}.md',
                ))
    return issues


def check_duplicate_entity_slugs(
    entity_files: list[Path],
) -> list[LintIssue]:
    seen: dict[str, str] = {}
    issues = []
    for path in entity_files:
        slug = path.stem
        if slug in seen:
            issues.append(LintIssue(
                path=str(path),
                check_id="duplicate-entity-slug",
                severity="error",
                message=f'slug "{slug}" duplicates {seen[slug]}',
                hint='rename one of the entity files to resolve the conflict',
            ))
        else:
            seen[slug] = str(path)
    return issues


def check_placeholder_website(
    entity_files: list[Path],
    entity_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    issues = []
    for path in entity_files:
        fm = entity_frontmatters.get(str(path), {})
        website = fm.get("website", "")
        if not isinstance(website, str) or not website:
            continue
        parsed = urlparse(website)
        is_placeholder = (
            parsed.netloc in PLACEHOLDER_DOMAINS
            or (not parsed.netloc and parsed.path.rstrip("/") in PLACEHOLDER_PATHS)
            or any(parsed.path.startswith(p) for p in PLACEHOLDER_PATHS)
        )
        if is_placeholder:
            issues.append(LintIssue(
                path=str(path),
                check_id="placeholder-website",
                severity="warning",
                message=f'website "{website}" looks like a placeholder or login page',
                hint='update to the product or company homepage',
            ))
    return issues


def check_legacy_field_name(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    """Flag standard_slug as legacy after the Standards→Criteria rename."""
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        if "standard_slug" in fm:
            issues.append(LintIssue(
                path=str(path),
                check_id="legacy-field-name",
                severity="warning",
                message='field "standard_slug" is the pre-rename name; use "criteria_slug"',
                hint='rename `standard_slug:` to `criteria_slug:` in this file',
            ))
    return issues


def check_unknown_frontmatter_keys(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    entity_files: list[Path],
    entity_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        unknown = set(fm.keys()) - CANONICAL_CLAIM_KEYS
        for key in sorted(unknown):
            issues.append(LintIssue(
                path=str(path),
                check_id="unknown-frontmatter-key",
                severity="warning",
                message=f'unrecognized claim field "{key}"',
            ))
    for path in entity_files:
        fm = entity_frontmatters.get(str(path), {})
        unknown = set(fm.keys()) - CANONICAL_ENTITY_KEYS
        for key in sorted(unknown):
            issues.append(LintIssue(
                path=str(path),
                check_id="unknown-frontmatter-key",
                severity="warning",
                message=f'unrecognized entity field "{key}"',
            ))
    return issues


def check_missing_criteria_slug(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        if not fm.get("criteria_slug"):
            issues.append(LintIssue(
                path=str(path),
                check_id="missing-criteria-slug",
                severity="info",
                message='no criteria_slug set — claim is matched by filename stem only',
                hint='add `criteria_slug:` to improve traceability',
            ))
    return issues


def check_missing_seo_title(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        if fm.get("status") != "published":
            continue
        if not fm.get("seo_title"):
            issues.append(LintIssue(
                path=str(path),
                check_id="missing-seo-title",
                severity="info",
                message="published claim has no `seo_title`; SERP title falls back to the full claim title",
                hint="add `seo_title:` (max 42 chars) to control how this claim appears in search results",
            ))
    return issues


def check_stale_recheck(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    today: datetime.date,
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        due = fm.get("next_recheck_due")
        if due is None:
            continue
        if isinstance(due, datetime.datetime):
            due = due.date()
        if isinstance(due, datetime.date) and due < today:
            issues.append(LintIssue(
                path=str(path),
                check_id="stale-recheck",
                severity="info",
                message=f'next_recheck_due {due} is in the past',
                hint='run the pipeline to recheck this claim',
            ))
    return issues


def check_future_as_of(
    claim_files: list[Path],
    claim_frontmatters: dict[str, dict[str, Any]],
    today: datetime.date,
) -> list[LintIssue]:
    issues = []
    for path in claim_files:
        fm = claim_frontmatters.get(str(path), {})
        as_of = fm.get("as_of")
        if as_of is None:
            continue
        if isinstance(as_of, datetime.datetime):
            as_of = as_of.date()
        if isinstance(as_of, datetime.date) and as_of > today:
            issues.append(LintIssue(
                path=str(path),
                check_id="future-as-of",
                severity="info",
                message=f'as_of date {as_of} is in the future — likely a paste error',
            ))
    return issues


def check_entity_type_dir_mismatch(
    entity_files: list[Path],
    entity_frontmatters: dict[str, dict[str, Any]],
) -> list[LintIssue]:
    issues = []
    for path in entity_files:
        fm = entity_frontmatters.get(str(path), {})
        declared_type = fm.get("type", "")
        dir_name = path.parent.name
        expected = ENTITY_DIR_TO_TYPE.get(dir_name)
        if expected and declared_type and declared_type != expected:
            issues.append(LintIssue(
                path=str(path),
                check_id="entity-type-dir-mismatch",
                severity="warning",
                message=f'entity type "{declared_type}" is in directory "{dir_name}/"',
                hint=f'move file to research/entities/{declared_type}s/ or correct the type field',
            ))
    return issues
