"""Tests for frontmatter parse/strip/serialize utilities."""

from __future__ import annotations

import datetime

from common.frontmatter import parse_frontmatter, serialize_frontmatter, strip_frontmatter
from common.models import Verdict, Confidence, SourceKind


class TestParseFrontmatter:
    def test_basic_parse(self, sample_frontmatter_text: str) -> None:
        data, body = parse_frontmatter(sample_frontmatter_text)
        assert data["title"] == "Test Claim"
        assert data["verdict"] == "false"
        assert "Body content here." in body

    def test_empty_body(self) -> None:
        text = "---\ntitle: No Body\n---\n"
        data, body = parse_frontmatter(text)
        assert data["title"] == "No Body"
        assert body == ""

    def test_multiline_body(self) -> None:
        text = "---\nkey: value\n---\nLine 1\n\nLine 3\n"
        data, body = parse_frontmatter(text)
        assert data["key"] == "value"
        assert "Line 1" in body
        assert "Line 3" in body

    def test_missing_frontmatter_raises(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="No YAML frontmatter found"):
            parse_frontmatter("Just some text without frontmatter")

    def test_yaml_list_values(self) -> None:
        text = '---\nsources:\n  - "2025/item-a"\n  - "2025/item-b"\n---\nBody\n'
        data, _ = parse_frontmatter(text)
        assert data["sources"] == ["2025/item-a", "2025/item-b"]

    def test_date_values_parsed(self) -> None:
        text = "---\npublished_date: 2025-12-13\n---\nBody\n"
        data, _ = parse_frontmatter(text)
        assert data["published_date"] == datetime.date(2025, 12, 13)


class TestStripFrontmatter:
    def test_returns_body_only(self, sample_frontmatter_text: str) -> None:
        body = strip_frontmatter(sample_frontmatter_text)
        assert "---" not in body
        assert "Body content here." in body
        assert "title" not in body


class TestSerializeFrontmatter:
    def test_basic_serialize(self) -> None:
        data = {"title": "My Claim", "verdict": "true"}
        body = "\nSome body text.\n"
        result = serialize_frontmatter(data, body)
        assert result.startswith("---\n")
        assert "title: My Claim" in result
        assert "verdict: 'true'" in result
        assert result.endswith("---\n\nSome body text.\n")

    def test_date_serialized_as_iso(self) -> None:
        data = {"published_date": datetime.date(2025, 12, 13)}
        result = serialize_frontmatter(data, "\n")
        assert "2025-12-13" in result
        # Should not include a time component
        assert "00:00:00" not in result

    def test_none_values_omitted(self) -> None:
        data = {"title": "Present", "optional_field": None}
        result = serialize_frontmatter(data, "\n")
        assert "title: Present" in result
        assert "optional_field" not in result

    def test_nested_none_values_omitted(self) -> None:
        data = {"outer": {"keep": "value", "drop": None}}
        result = serialize_frontmatter(data, "\n")
        assert "keep: value" in result
        assert "drop" not in result

    def test_enum_serialized_as_value(self) -> None:
        data = {
            "verdict": Verdict.FALSE,
            "confidence": Confidence.MEDIUM,
            "kind": SourceKind.INDEX,
        }
        result = serialize_frontmatter(data, "\n")
        assert "'false'" in result or "false" in result
        assert "medium" in result
        assert "index" in result
        # Should not contain Python repr like Verdict.FALSE
        assert "Verdict" not in result
        assert "Confidence" not in result
        assert "SourceKind" not in result

    def test_url_serialized_as_plain_string(self) -> None:
        data = {"url": "https://example.com/path?q=1"}
        result = serialize_frontmatter(data, "\n")
        assert "https://example.com/path?q=1" in result
        # Should not be tagged
        assert "!!python" not in result

    def test_round_trip(self) -> None:
        original_data = {
            "title": "Round Trip Test",
            "published_date": datetime.date(2025, 6, 15),
            "sources": ["2025/source-a", "2025/source-b"],
        }
        original_body = "\nThis is the body.\n"
        serialized = serialize_frontmatter(original_data, original_body)
        parsed_data, parsed_body = parse_frontmatter(serialized)
        assert parsed_data["title"] == "Round Trip Test"
        assert parsed_data["published_date"] == "2025-06-15"
        assert parsed_data["sources"] == ["2025/source-a", "2025/source-b"]
        assert "This is the body." in parsed_body

    def test_round_trip_with_enum(self) -> None:
        original_data = {"verdict": Verdict.MOSTLY_TRUE}
        serialized = serialize_frontmatter(original_data, "\n")
        parsed_data, _ = parse_frontmatter(serialized)
        assert parsed_data["verdict"] == "mostly-true"
