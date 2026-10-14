"""Unit tests for source URL deduplication."""

from __future__ import annotations

import asyncio
import dataclasses
import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.persistence import build_source_url_index, load_source_dict
from common.canonical_url import canonical_key
from loop import VerificationResult, VerifyConfig, ingest_urls
from orchestrator.persistence import persist_sources
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


# --- target cap tests (dedup through the loop: test_beta7_pins.py) ---

class TestTargetCap:
    @pytest.mark.asyncio
    async def test_ingest_urls_respects_target_param(self) -> None:
        """When target=1 is passed, only one SourceFile is returned."""
        urls = [f"https://example.com/{i}" for i in range(10)]
        cfg = _make_cfg(max_sources=6)
        sem = asyncio.Semaphore(8)
        call_count = 0

        async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
            nonlocal call_count
            call_count += 1
            return (url, _make_source_file(url, f"source-{call_count}"))

        with patch("loop.ingest.ingest_one", side_effect=_fake_ingest_one):
            results, errors = await ingest_urls(None, urls, cfg, sem, target=1)

        assert len(results) == 1


# --- VerificationResult.cached_sources end-to-end tests ---


class TestPersistSources:
    def _result(self, cached_ids: list[str], fresh: list[tuple[str, SourceFile]]) -> VerificationResult:
        return VerificationResult(
            entity="E", claim_text="C", urls_found=[], urls_ingested=[], urls_failed=[], sources=[],
            source_files=fresh,
            cached_sources=[(f"https://example.com/{sid}", sid, {}) for sid in cached_ids],
        )

    def test_returns_cached_then_fresh_ids_without_repeats(self, tmp_path: Path) -> None:
        sf = _make_source_file("https://example.com/fresh", "fresh")
        vr = self._result(["2025/old", "2026/fresh"], [("https://example.com/fresh", sf)])
        assert persist_sources(vr, tmp_path) == ["2025/old", "2026/fresh"]
        assert (tmp_path / "research" / "sources" / "2026" / "fresh.md").exists()

    def test_adds_requested_and_stored_urls_to_the_index(self, tmp_path: Path) -> None:
        # A redirect leaves the requested URL and the stored one different;
        # a later claim may find either form.
        sf = _make_source_file("https://example.com/final", "final")
        vr = self._result([], [("https://example.com/start", sf)])
        index: dict[str, str] = {}
        persist_sources(vr, tmp_path, index)
        assert index[canonical_key("https://www.example.com/start/")] == "2026/final"
        assert index[canonical_key("https://example.com/final")] == "2026/final"


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


@dataclasses.dataclass
class _Notes:
    """What ``ingest_urls`` records beyond the sources (the shape of its ``notes`` argument)."""

    final_urls: dict = dataclasses.field(default_factory=dict)
    aliases: dict = dataclasses.field(default_factory=dict)
    archive: dict = dataclasses.field(default_factory=dict)


# --- Redirects to a page already stored ---

_OLD = "https://example.org/old"
_NEW = "https://example.org/new"
_PAGE = "<html><head><title>New</title></head><body><p>The stored page.</p></body></html>"


def _mock_redirect(respx_mock) -> None:
    import httpx

    respx_mock.get(_OLD).mock(return_value=httpx.Response(301, headers={"Location": "/new"}))
    respx_mock.get(_NEW).mock(return_value=httpx.Response(200, html=_PAGE))


class TestWebFetchRecordsFinalUrl:
    @pytest.mark.asyncio
    async def test_live_fetch_of_requested_url_records_where_it_ended(self) -> None:
        import httpx
        import respx

        from ingestor.agent import IngestorDeps, web_fetch
        from pydantic_ai import RunContext
        from pydantic_ai.models.test import TestModel
        from pydantic_ai.usage import RunUsage

        archive = "https://web.archive.org/web/2025/https://example.org/old"
        with respx.mock as mock:
            _mock_redirect(mock)
            mock.get(archive).mock(return_value=httpx.Response(200, html=_PAGE))
            async with httpx.AsyncClient() as client:
                def ctx(prefetched=None):
                    deps = IngestorDeps(
                        http_client=client, repo_root="/tmp", requested_url=_OLD,
                        skip_wayback=True, prefetched_bodies=prefetched or {},
                    )
                    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())

                live = ctx()
                await web_fetch(live, _OLD)
                from_archive = ctx()
                await web_fetch(from_archive, archive)
                prefetched = ctx({_OLD: "Body from Tavily."})
                await web_fetch(prefetched, _OLD)

        assert live.deps.final_url == _NEW
        assert from_archive.deps.final_url is None
        assert prefetched.deps.final_url is None


class TestSameBatchRedirects:
    @pytest.mark.asyncio
    async def test_two_urls_redirecting_to_one_page_give_one_result(self) -> None:

        a, b, c = "https://example.org/a", "https://example.org/b", "https://example.org/c"
        final = {a: _NEW, b: _NEW, c: c}

        async def _fake_ingest_one(client, url, cfg, today, sem, notes=None, **_):
            notes.final_urls[url] = final[url]
            return (url, _make_source_file(url, url.rsplit("/", 1)[1]))

        notes = _Notes()
        with patch("loop.ingest.ingest_one", side_effect=_fake_ingest_one):
            results, _errors = await ingest_urls(
                None, [a, b, c], _make_cfg(), asyncio.Semaphore(8), target=2, notes=notes
            )

        kept = [u for u, _sf in results]
        assert len(kept) == 2 and c in kept
        (first,) = [u for u in (a, b) if u in kept]
        (dropped,) = [u for u in (a, b) if u not in kept]
        assert notes.aliases == {dropped: first}


class TestRedirectToACachedSourceDoesNotCount:
    """A fresh fetch that lands on a source the claim already has is an alias, not a success."""

    @pytest.mark.asyncio
    async def test_waterfall_keeps_going_past_it(self) -> None:
        from common.canonical_url import canonical_key

        cached, a, c = "https://example.org/cached", "https://example.org/a", "https://example.org/c"
        final = {a: _NEW, c: c}

        async def _fake_ingest_one(client, url, cfg, today, sem, notes=None, **_):
            notes.final_urls[url] = final[url]
            return (url, _make_source_file(url, url.rsplit("/", 1)[1]))

        notes = _Notes()
        with patch("loop.ingest.ingest_one", side_effect=_fake_ingest_one):
            results, _errors = await ingest_urls(
                None, [a, c], _make_cfg(), asyncio.Semaphore(8), target=1, notes=notes,
                known_pages={canonical_key(_NEW): cached},
            )

        assert [u for u, _sf in results] == [c]
        assert notes.aliases == {a: cached}

