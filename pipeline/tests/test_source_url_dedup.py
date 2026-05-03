"""Unit tests for source URL deduplication."""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.persistence import build_source_url_index, load_source_dict
from orchestrator.pipeline import VerifyConfig, _apply_url_dedup, _ingest_urls
from common.utils import slug_from_url


# --- Helpers ---

def _write_source_md(path: Path, url: str, title: str = "Test Title") -> None:
    """Write a minimal source markdown file with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\n"
        f"url: {url}\n"
        f"title: {title}\n"
        f"publisher: Test Publisher\n"
        f"accessed_date: 2026-01-01\n"
        f"kind: article\n"
        f"summary: A short test summary here.\n"
        f"---\n"
        f"Body content.\n",
        encoding="utf-8",
    )


def _make_source_file(url: str, slug: str) -> SourceFile:
    return SourceFile(
        frontmatter=SourceFrontmatter(
            url=url,
            title=slug.upper(),
            publisher="Test Publisher",
            accessed_date=datetime.date(2026, 5, 1),
            kind="article",
            summary="A test summary.",
        ),
        body="Body content.",
        slug=slug,
        year=2026,
    )


def _make_cfg(max_sources: int = 6) -> VerifyConfig:
    return VerifyConfig(
        model="test",
        repo_root="/tmp",
        max_sources=max_sources,
        candidate_pool_size=24,
        skip_wayback=True,
    )


# --- build_source_url_index tests ---

class TestBuildSourceUrlIndex:
    def test_index_builder_maps_url_to_source_id(self, tmp_path: Path) -> None:
        """Two source files are indexed correctly as {year}/{slug}."""
        _write_source_md(
            tmp_path / "research" / "sources" / "2024" / "report-one.md",
            url="https://example.com/report-one",
            title="Report One",
        )
        _write_source_md(
            tmp_path / "research" / "sources" / "2025" / "report-two.md",
            url="https://example.com/report-two",
            title="Report Two",
        )

        index = build_source_url_index(tmp_path)

        assert index.get("https://example.com/report-one") == "2024/report-one"
        assert index.get("https://example.com/report-two") == "2025/report-two"

    def test_index_builder_skips_missing_url_field(self, tmp_path: Path) -> None:
        """Source file without a url field is not included in the index."""
        path = tmp_path / "research" / "sources" / "2024" / "no-url.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntitle: No URL\npublisher: Pub\n---\nBody.\n",
            encoding="utf-8",
        )

        index = build_source_url_index(tmp_path)

        assert "2024/no-url" not in index.values()
        assert len(index) == 0

    def test_index_builder_skips_bad_frontmatter(self, tmp_path: Path) -> None:
        """File with no frontmatter delimiters does not crash the builder."""
        path = tmp_path / "research" / "sources" / "2024" / "no-fm.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Just plain text, no frontmatter.\n", encoding="utf-8")

        index = build_source_url_index(tmp_path)

        assert len(index) == 0

    def test_index_builder_skips_yaml_error(self, tmp_path: Path) -> None:
        """File with delimiters but invalid YAML does not crash the builder."""
        path = tmp_path / "research" / "sources" / "2024" / "bad-yaml.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\nkey: [\nbadly: unclosed bracket\n---\nBody.\n",
            encoding="utf-8",
        )

        index = build_source_url_index(tmp_path)

        assert len(index) == 0

    def test_index_builder_missing_sources_dir(self, tmp_path: Path) -> None:
        """Returns empty dict when research/sources/ does not exist."""
        index = build_source_url_index(tmp_path)

        assert index == {}


# --- load_source_dict tests ---

class TestLoadSourceDict:
    def test_load_source_dict_roundtrip(self, tmp_path: Path) -> None:
        """Fields written to disk are read back correctly."""
        _write_source_md(
            tmp_path / "research" / "sources" / "2024" / "my-report.md",
            url="https://example.com/my-report",
            title="My Report",
        )

        result = load_source_dict("2024/my-report", tmp_path)

        assert result is not None
        assert result["url"] == "https://example.com/my-report"
        assert result["title"] == "My Report"
        assert result["publisher"] == "Test Publisher"
        assert result["summary"] == "A short test summary here."
        assert result["slug"] == "my-report"
        assert "Body content." in result["body"]
        assert isinstance(result["key_quotes"], list)

    def test_load_source_dict_missing_file(self, tmp_path: Path) -> None:
        """Returns None without raising when the file does not exist."""
        result = load_source_dict("2024/nonexistent-slug", tmp_path)

        assert result is None


# --- _apply_url_dedup tests ---

class TestApplyUrlDedup:
    def test_apply_url_dedup_splits_correctly(self, tmp_path: Path) -> None:
        """One cached URL goes to cached list; uncached URL goes to to_ingest."""
        _write_source_md(
            tmp_path / "research" / "sources" / "2024" / "cached-report.md",
            url="https://example.com/cached",
        )
        url_index = {"https://example.com/cached": "2024/cached-report"}
        urls = ["https://example.com/cached", "https://example.com/new"]

        to_ingest, cached = _apply_url_dedup(urls, url_index, tmp_path)

        assert to_ingest == ["https://example.com/new"]
        assert len(cached) == 1
        url, source_id, sd = cached[0]
        assert url == "https://example.com/cached"
        assert source_id == "2024/cached-report"
        assert sd is not None

    def test_apply_url_dedup_falls_back_on_bad_file(self, tmp_path: Path) -> None:
        """URL in index but unreadable file falls back to to_ingest."""
        url_index = {"https://example.com/missing": "2024/missing-file"}
        urls = ["https://example.com/missing"]

        to_ingest, cached = _apply_url_dedup(urls, url_index, tmp_path)

        assert to_ingest == ["https://example.com/missing"]
        assert cached == []

    def test_apply_url_dedup_returns_source_id_in_triple(self, tmp_path: Path) -> None:
        """The source_id in the cached triple matches url_index[url]."""
        _write_source_md(
            tmp_path / "research" / "sources" / "2025" / "known-source.md",
            url="https://example.com/known",
        )
        url_index = {"https://example.com/known": "2025/known-source"}
        urls = ["https://example.com/known"]

        _to_ingest, cached = _apply_url_dedup(urls, url_index, tmp_path)

        assert len(cached) == 1
        _url, source_id, _sd = cached[0]
        assert source_id == url_index["https://example.com/known"]


# --- target cap tests ---

class TestTargetCap:
    @pytest.mark.asyncio
    async def test_ingest_urls_respects_target_param(self) -> None:
        """When target=1 is passed, only one SourceFile is returned."""
        urls = [f"https://example.com/{i}" for i in range(10)]
        cfg = _make_cfg(max_sources=6)
        sem = asyncio.Semaphore(8)
        call_count = 0

        async def _fake_ingest_one(client, url, cfg, today, sem):
            nonlocal call_count
            call_count += 1
            return (url, _make_source_file(url, f"source-{call_count}"))

        with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
            results, errors = await _ingest_urls(None, urls, cfg, sem, target=1)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_dedup_skips_ingest_when_all_cached(self, tmp_path: Path) -> None:
        """When all URLs are cache hits, _ingest_one is never called."""
        for i in range(4):
            _write_source_md(
                tmp_path / "research" / "sources" / "2025" / f"source-{i}.md",
                url=f"https://example.com/{i}",
            )

        url_index = build_source_url_index(tmp_path)
        urls = [f"https://example.com/{i}" for i in range(4)]
        cfg = _make_cfg(max_sources=4)
        sem = asyncio.Semaphore(8)

        ingest_one_called = False

        async def _fake_ingest_one(client, url, cfg, today, sem):
            nonlocal ingest_one_called
            ingest_one_called = True
            return (url, _make_source_file(url, "should-not-run"))

        urls_to_ingest, cached_sources = _apply_url_dedup(urls, url_index, tmp_path)
        remaining = max(0, cfg.max_sources - len(cached_sources))

        with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
            if remaining > 0:
                await _ingest_urls(None, urls_to_ingest, cfg, sem, target=remaining)

        assert ingest_one_called is False
        assert len(cached_sources) == 4
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_dedup_reduces_target_by_cache_count(self, tmp_path: Path) -> None:
        """With 2 cached and max_sources=4, _ingest_urls is called with target=2."""
        for i in range(2):
            _write_source_md(
                tmp_path / "research" / "sources" / "2025" / f"cached-{i}.md",
                url=f"https://cached.example.com/{i}",
            )

        url_index = build_source_url_index(tmp_path)
        cached_urls = [f"https://cached.example.com/{i}" for i in range(2)]
        new_urls = [f"https://new.example.com/{i}" for i in range(4)]
        all_urls = cached_urls + new_urls

        cfg = _make_cfg(max_sources=4)
        sem = asyncio.Semaphore(8)
        call_count = 0

        async def _fake_ingest_one(client, url, cfg, today, sem):
            nonlocal call_count
            call_count += 1
            return (url, _make_source_file(url, f"source-{call_count}"))

        urls_to_ingest, cached_sources = _apply_url_dedup(all_urls, url_index, tmp_path)
        remaining = max(0, cfg.max_sources - len(cached_sources))

        assert len(cached_sources) == 2
        assert remaining == 2

        with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
            results, _errors = await _ingest_urls(None, urls_to_ingest, cfg, sem, target=remaining)

        assert len(results) == 2


# --- slug_from_url tests ---

class TestSlugFromUrl:
    def test_slug_from_url_last_segment(self) -> None:
        result = slug_from_url("https://example.com/reports/annual-2024")
        assert result == "annual-2024"

    def test_slug_from_url_root_path(self) -> None:
        result = slug_from_url("https://example.com/")
        assert result is None

    def test_slug_from_url_slugifies_segment(self) -> None:
        result = slug_from_url("https://example.com/Annual_Report_2024.pdf")
        assert result == "annualreport2024pdf"
