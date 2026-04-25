"""Tests for shared model enums."""

from __future__ import annotations

import pytest

from common.models import Category, Confidence, EntityType, SourceKind, Verdict


class TestVerdict:
    def test_values(self) -> None:
        expected = {
            "true",
            "mostly-true",
            "mixed",
            "mostly-false",
            "false",
            "unverified",
            "not-applicable",
        }
        actual = {v.value for v in Verdict}
        assert actual == expected

    def test_string_access(self) -> None:
        assert Verdict("true") is Verdict.TRUE
        assert Verdict("mostly-false") is Verdict.MOSTLY_FALSE

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            Verdict("invalid")

    def test_str_behavior(self) -> None:
        assert Verdict.FALSE.value == "false"


class TestConfidence:
    def test_values(self) -> None:
        expected = {"high", "medium", "low"}
        actual = {c.value for c in Confidence}
        assert actual == expected

    def test_string_access(self) -> None:
        assert Confidence("high") is Confidence.HIGH

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            Confidence("very-high")


class TestCategory:
    def test_values(self) -> None:
        expected = {
            "ai-safety",
            "environmental-impact",
            "product-comparison",
            "consumer-guide",
            "ai-literacy",
            "data-privacy",
            "industry-analysis",
            "regulation-policy",
        }
        actual = {c.value for c in Category}
        assert actual == expected

    def test_count(self) -> None:
        assert len(Category) == 8

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            Category("unknown-category")


class TestSourceKind:
    def test_values(self) -> None:
        expected = {"report", "article", "documentation", "dataset", "blog", "video", "index"}
        actual = {k.value for k in SourceKind}
        assert actual == expected

    def test_string_access(self) -> None:
        assert SourceKind("index") is SourceKind.INDEX

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceKind("podcast")


class TestEntityType:
    def test_values(self) -> None:
        expected = {"company", "product", "topic", "sector"}
        actual = {e.value for e in EntityType}
        assert actual == expected

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityType("person")
