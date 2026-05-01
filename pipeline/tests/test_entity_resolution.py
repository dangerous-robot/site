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

    def test_valid_sector_ref(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "sectors", "ai-llm", "---\nname: AI LLM\ntype: sector\ndescription: LLM sector.\n---\n")
        result = parse_entity_ref("sectors/ai-llm", tmp_path)
        assert result.entity_type == EntityType.SECTOR

    def test_valid_topic_ref(self, tmp_path: Path) -> None:
        _write_entity(tmp_path, "topics", "ai-safety", "---\nname: AI Safety\ntype: topic\ndescription: Safety topic.\n---\n")
        result = parse_entity_ref("topics/ai-safety", tmp_path)
        assert result.entity_type == EntityType.TOPIC

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
