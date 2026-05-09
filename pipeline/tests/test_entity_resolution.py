"""Tests for orchestrator.entity_resolution.parse_entity_ref."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.entity_resolution import ResolvedEntity, parse_entity_ref
from common.models import EntityType


def _write_entity(tmp_path: Path, type_dir: str, slug: str, content: str) -> Path:
    entity_dir = tmp_path / "research" / "entities" / type_dir
    entity_dir.mkdir(parents=True, exist_ok=True)
    path = entity_dir / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    return path


_MINIMAL = """\
---
name: Test Entity
type: product
description: A test entity.
---
"""

_WITH_ALIASES = """\
---
name: Test Entity
type: product
description: A test entity.
aliases:
  - TE
  - TestE
---
"""

_WITH_PARENT = """\
---
name: Test Entity
type: product
description: A test entity.
parent_company: Acme Corp
---
"""


class TestParseEntityRef:
    def test_valid_company_ref(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "companies", "acme", "---\nname: Acme\ntype: company\ndescription: Acme Corp.\n---\n")
        result = parse_entity_ref("companies/acme", tmp_path)
        assert result.entity_name == "Acme"
        assert result.entity_type == EntityType.COMPANY
        assert result.entity_ref == "companies/acme"

    def test_valid_product_ref(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "widget", _MINIMAL)
        result = parse_entity_ref("products/widget", tmp_path)
        assert result.entity_name == "Test Entity"
        assert result.entity_type == EntityType.PRODUCT

    def test_valid_subject_ref(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "subjects", "ai-llm", "---\nname: AI LLM\ntype: subject\ndescription: LLM subject.\n---\n")
        result = parse_entity_ref("subjects/ai-llm", tmp_path)
        assert result.entity_type == EntityType.SUBJECT

    def test_missing_slash_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="expected '\\{type_dir\\}/\\{slug\\}'"):
            parse_entity_ref("productswidget", tmp_path)

    def test_unknown_type_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown entity type dir 'badtype'"):
            parse_entity_ref("badtype/foo", tmp_path)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Entity file not found"):
            parse_entity_ref("products/nonexistent", tmp_path)

    def test_frontmatter_parse_failure_raises(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "bad", "not: valid: yaml: ---\n{{{{")
        with pytest.raises(ValueError, match="Failed to parse entity frontmatter"):
            parse_entity_ref("products/bad", tmp_path)

    def test_missing_name_raises(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "noname", "---\ntype: product\ndescription: No name.\n---\n")
        with pytest.raises(ValueError, match="missing required field 'name'"):
            parse_entity_ref("products/noname", tmp_path)

    def test_aliases_defaults_to_empty_list(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "widget", _MINIMAL)
        result = parse_entity_ref("products/widget", tmp_path)
        assert result.aliases == []

    def test_parent_company_none_when_absent(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "widget", _MINIMAL)
        result = parse_entity_ref("products/widget", tmp_path)
        assert result.parent_company is None

    def test_aliases_populated_when_present(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "widget", _WITH_ALIASES)
        result = parse_entity_ref("products/widget", tmp_path)
        assert result.aliases == ["TE", "TestE"]

    def test_parent_company_populated_when_present(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "widget", _WITH_PARENT)
        result = parse_entity_ref("products/widget", tmp_path)
        assert result.parent_company == "Acme Corp"

    def test_resolved_entity_legal_name_populated(self, tmp_path: Path) -> None:
        _write_entity(
            tmp_path,
            "companies",
            "openai",
            "---\nname: OpenAI\ntype: company\nlegal_name: 'OpenAI, LLC'\ndescription: AI lab.\n---\n",
        )
        result = parse_entity_ref("companies/openai", tmp_path)
        assert result.legal_name == "OpenAI, LLC"

    def test_resolved_entity_legal_name_absent(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "widget", _MINIMAL)
        result = parse_entity_ref("products/widget", tmp_path)
        assert result.legal_name is None

    def test_resolved_entity_verification_status_default(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "products", "widget", _MINIMAL)
        result = parse_entity_ref("products/widget", tmp_path)
        # Absent field defaults to "verified" so analyst/render layers can
        # branch on a single string without a None check.
        assert result.verification_status == "verified"

    def test_resolved_entity_verification_status_explicit(self, tmp_path: Path) -> None:
        _write_entity(
            tmp_path,
            "products",
            "newco",
            "---\nname: Newco\ntype: product\ndescription: Demo.\nverification_status: unverified-startup\n---\n",
        )
        result = parse_entity_ref("products/newco", tmp_path)
        assert result.verification_status == "unverified-startup"


class TestCanonicalEntityKeysLockstep:
    """Guard the linter set against drift from the Zod schema and writer."""

    def test_canonical_entity_keys_lockstep(self) -> None:
        from linter.checks import CANONICAL_ENTITY_KEYS

        # Keys this plan adds (legal_name, verification_status) plus the
        # drive-by fixes (sec_cik shipped via source-pool-expansion-tier1.md;
        # status emitted by _entity_frontmatter for drafts).
        for key in ("legal_name", "verification_status", "sec_cik", "status"):
            assert key in CANONICAL_ENTITY_KEYS, (
                f"{key!r} missing from CANONICAL_ENTITY_KEYS — drift from "
                f"writer / Zod schema. See docs/plans/entity-metadata-surface.md."
            )


class TestVerificationStatusEnumLockstep:
    """Drift guard: the writer's suppression branch and analyst-prompt branch
    compare against literal strings; if those strings drift from the Zod enum
    in src/content.config.ts, the discrepancy goes silent. Re-read the Zod
    source and check the three literals are present."""

    def test_verification_status_enum_lockstep(self) -> None:
        # tests dir -> pipeline -> site root -> src/content.config.ts
        site_root = Path(__file__).resolve().parents[2]
        zod_source = (site_root / "src" / "content.config.ts").read_text(encoding="utf-8")
        # The Zod enum lives inline; checking literal presence is sufficient
        # without parsing TypeScript. Any rename will fail the test.
        for literal in ("'verified'", "'unverified-startup'", "'unverified-other'"):
            assert literal in zod_source, (
                f"Zod enum literal {literal} missing from src/content.config.ts — "
                f"verification_status branches in writer/analyst will drift silently."
            )
