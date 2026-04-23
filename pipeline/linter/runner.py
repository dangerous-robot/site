"""Path collection, template loading, and check orchestration."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import yaml

from common.frontmatter import parse_frontmatter
from .checks import (
    check_broken_criteria_slug,
    check_broken_source_refs,
    check_duplicate_entity_slugs,
    check_empty_required_strings,
    check_entity_type_dir_mismatch,
    check_future_as_of,
    check_legacy_field_name,
    check_missing_criteria_slug,
    check_missing_required_fields,
    check_orphaned_claims,
    check_placeholder_website,
    check_stale_recheck,
    check_unknown_frontmatter_keys,
)
from .models import LintIssue


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        return fm
    except Exception:
        return {}


def load_templates(repo_root: Path) -> set[str]:
    templates_path = repo_root / "research" / "templates.yaml"
    try:
        data = yaml.safe_load(templates_path.read_text(encoding="utf-8")) or {}
        slugs = set()
        for t in data.get("templates", []):
            if isinstance(t, dict) and "slug" in t:
                slugs.add(t["slug"])
        return slugs
    except Exception:
        return set()


def collect_all_paths(
    repo_root: Path,
    entity_filter: str | None = None,
) -> tuple[list[Path], list[Path], list[Path]]:
    claims_root = repo_root / "research" / "claims"
    entities_root = repo_root / "research" / "entities"
    sources_root = repo_root / "research" / "sources"

    claim_files = [
        p for p in claims_root.rglob("*.md")
        if (entity_filter is None or p.parent.name == entity_filter)
    ]
    entity_files = list(entities_root.rglob("*.md"))
    source_files = list(sources_root.rglob("*.md"))

    return sorted(claim_files), sorted(entity_files), sorted(source_files)


def run_all_checks(
    repo_root: Path,
    entity_filter: str | None = None,
    today: datetime.date | None = None,
) -> list[LintIssue]:
    if today is None:
        today = datetime.date.today()

    claim_files, entity_files, source_files = collect_all_paths(repo_root, entity_filter)
    template_slugs = load_templates(repo_root)

    claim_fms = {str(p): _read_frontmatter(p) for p in claim_files}
    entity_fms = {str(p): _read_frontmatter(p) for p in entity_files}

    # Build entity index: "companies/ecosia" style refs
    entity_index: set[str] = set()
    for p in entity_files:
        # Derive the entity ref from path relative to entities root
        rel = p.relative_to(repo_root / "research" / "entities")
        entity_index.add(str(rel.with_suffix("")).replace("\\", "/"))

    # Build source ID set: "2025/fli-safety-index" style
    source_ids: set[str] = set()
    for p in source_files:
        rel = p.relative_to(repo_root / "research" / "sources")
        source_ids.add(str(rel.with_suffix("")).replace("\\", "/"))

    issues: list[LintIssue] = []
    issues += check_orphaned_claims(claim_files, claim_fms, entity_index)
    issues += check_missing_required_fields(claim_files, claim_fms)
    issues += check_empty_required_strings(claim_files, claim_fms, entity_files, entity_fms)
    issues += check_broken_criteria_slug(claim_files, claim_fms, template_slugs)
    issues += check_broken_source_refs(claim_files, claim_fms, source_ids)
    issues += check_duplicate_entity_slugs(entity_files)
    issues += check_placeholder_website(entity_files, entity_fms)
    issues += check_legacy_field_name(claim_files, claim_fms)
    issues += check_unknown_frontmatter_keys(claim_files, claim_fms, entity_files, entity_fms)
    issues += check_missing_criteria_slug(claim_files, claim_fms)
    issues += check_stale_recheck(claim_files, claim_fms, today)
    issues += check_future_as_of(claim_files, claim_fms, today)
    issues += check_entity_type_dir_mismatch(entity_files, entity_fms)

    return issues
