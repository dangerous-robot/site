"""Tests for content loading utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.content_loader import (
    list_claims,
    load_claim,
    load_entity,
    load_source,
    resolve_repo_root,
)


class TestResolveRepoRoot:
    def test_returns_path(self) -> None:
        root = resolve_repo_root()
        assert isinstance(root, Path)
        assert root.is_dir()

    def test_contains_expected_markers(self) -> None:
        root = resolve_repo_root()
        assert (root / "research").is_dir()
        assert (root / "src").is_dir()


class TestLoadSource:
    def test_load_existing_source(self, repo_root: Path) -> None:
        data, body = load_source("2026/anthropic-voluntary-commitments", repo_root)
        assert data["title"] == "Voluntary Commitments"
        assert data["publisher"] == "Anthropic"
        assert data["kind"] == "documentation"
        assert "url" in data
        assert len(body) > 0

    def test_load_missing_source_raises(self, repo_root: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_source("2025/nonexistent-source", repo_root)


class TestLoadClaim:
    def test_load_existing_claim(self, repo_root: Path) -> None:
        data, body = load_claim(
            "anthropic/publishes-sustainability-report", repo_root
        )
        assert data["entity"] == "companies/anthropic"
        assert data["category"] == "industry-analysis"
        assert data["verdict"] == "unverified"
        assert data["confidence"] == "high"
        assert len(body) > 0

    def test_load_missing_claim_raises(self, repo_root: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_claim("nonexistent/claim-slug", repo_root)


class TestLoadEntity:
    def test_load_existing_entity(self, repo_root: Path) -> None:
        data, _body = load_entity("companies/anthropic", repo_root)
        assert data["name"] == "Anthropic"
        assert data["type"] == "company"
        assert "website" in data

    def test_load_missing_entity_raises(self, repo_root: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_entity("companies/nonexistent-co", repo_root)


class TestListClaims:
    def test_list_all_claims(self, repo_root: Path) -> None:
        claims = list_claims(repo_root)
        assert len(claims) >= 1
        assert all(p.suffix == ".md" for p in claims)

    def test_filter_by_entity(self, repo_root: Path) -> None:
        claims = list_claims(repo_root, entity="anthropic")
        assert len(claims) >= 1
        assert all(p.parent.name == "anthropic" for p in claims)

    def test_filter_by_nonexistent_entity(self, repo_root: Path) -> None:
        claims = list_claims(repo_root, entity="nonexistent")
        assert claims == []

    def test_filter_by_category(self, repo_root: Path) -> None:
        claims = list_claims(repo_root, category="environmental-impact")
        assert len(claims) >= 1

    def test_filter_by_entity_and_category(self, repo_root: Path) -> None:
        claims = list_claims(
            repo_root, entity="anthropic", category="industry-analysis"
        )
        assert len(claims) >= 1

    def test_filter_by_nonexistent_category(self, repo_root: Path) -> None:
        claims = list_claims(repo_root, category="nonexistent-category")
        assert claims == []
