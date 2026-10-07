"""Unit tests for source URL deduplication."""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.persistence import build_source_url_index, load_source_dict
from common.models import SubQuestion
from common.canonical_url import canonical_key
from orchestrator.pipeline import (
    VerificationResult,
    VerifyConfig,
    _apply_url_dedup,
    _ingest_urls,
    _invert_addresses,
)
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

    def test_apply_url_dedup_matches_canonical_form(self, tmp_path: Path) -> None:
        """www., trailing slash and tracking params still hit the file on disk."""
        _write_source_md(
            tmp_path / "research" / "sources" / "2026" / "a.md",
            url="https://x.com/a",
        )
        url_index = build_source_url_index(tmp_path)
        urls = ["https://www.x.com/a/?utm_source=y"]

        to_ingest, cached = _apply_url_dedup(urls, url_index, tmp_path)

        assert to_ingest == []
        assert [(u, sid) for u, sid, _ in cached] == [(urls[0], "2026/a")]

    def test_apply_url_dedup_matches_any_form_of_an_arxiv_paper(self, tmp_path: Path) -> None:
        """The committed arXiv html source is reused for the search tool's abs id URL."""
        repo_root = Path(__file__).resolve().parents[2]
        committed = repo_root / "research" / "sources" / "2025" / "250212447v1.md"
        dest = tmp_path / "research" / "sources" / "2025" / "250212447v1.md"
        dest.parent.mkdir(parents=True)
        dest.write_text(committed.read_text(encoding="utf-8"), encoding="utf-8")
        url_index = build_source_url_index(tmp_path)
        urls = ["http://arxiv.org/abs/2502.12447v1"]

        to_ingest, cached = _apply_url_dedup(urls, url_index, tmp_path)

        assert to_ingest == []
        assert [(u, sid) for u, sid, _ in cached] == [(urls[0], "2025/250212447v1")]


def test_invert_addresses_uses_source_addresses_over_disk_url() -> None:
    """A cached source's on-disk url can differ from the researcher's URL."""
    sub_questions = [SubQuestion(id="sq1", question="q?", rationale="r.")]
    sources = [{"url": "https://x.com/a", "source_id": "2026/a", "addresses": ["sq1"]}]

    coverage = _invert_addresses(sub_questions, sources)

    assert coverage == {"sq1": ["2026/a"]}


# --- target cap tests ---

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

        async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
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

        async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
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


# --- VerificationResult.cached_sources end-to-end tests ---

class TestVerifyClaimSurfacesCachedSources:
    """verify_claim records cache-hit sources on cached_sources so the audit
    sidecar's sources_consulted block lists them."""

    @pytest.mark.asyncio
    async def test_all_cached_urls_populate_cached_sources(self, tmp_path: Path) -> None:
        from orchestrator.persistence import _build_sources_consulted
        from orchestrator.pipeline import verify_claim

        for i in range(4):
            _write_source_md(
                tmp_path / "research" / "sources" / "2026" / f"cached-{i}.md",
                url=f"https://example.com/cached-{i}",
                title=f"Cached Source {i}",
            )

        urls = [f"https://example.com/cached-{i}" for i in range(4)]

        from researcher.decomposed import ResearchOutput

        async def _fake_research(*args, **kwargs):
            return ResearchOutput(
                urls=list(urls),
                trace={"mode": "decomposed", "urls_kept": len(urls)},
            )

        async def _fail_ingest(*args, **kwargs):
            raise AssertionError("_ingest_urls must not run when every URL is cached")

        async def _fake_analyse(*args, **kwargs):
            return None, None  # short-circuits before auditor; we only care about cached_sources

        async def _fake_audit(*args, **kwargs):
            return None

        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )

        with (
            patch("orchestrator.pipeline._research", side_effect=_fake_research),
            patch("orchestrator.pipeline._ingest_urls", side_effect=_fail_ingest),
            patch("orchestrator.pipeline._analyse_claim", side_effect=_fake_analyse),
            patch("orchestrator.pipeline._audit_claim", side_effect=_fake_audit),
        ):
            result = await verify_claim("Example", "claim text", config=cfg)

        assert len(result.cached_sources) == 4
        assert result.source_files == []
        ids = [sid for _u, sid, _sd in result.cached_sources]
        assert ids == [f"2026/cached-{i}" for i in range(4)]

        consulted = _build_sources_consulted(
            result.source_files, cached_sources=result.cached_sources
        )
        assert len(consulted) == 4
        assert consulted[0]["id"] == "2026/cached-0"
        assert consulted[0]["title"] == "Cached Source 0"
        assert consulted[0]["url"] == "https://example.com/cached-0"
        assert all(entry["ingested"] is True for entry in consulted)


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
        assert vr.persist_sources(tmp_path) == ["2025/old", "2026/fresh"]
        assert (tmp_path / "research" / "sources" / "2026" / "fresh.md").exists()

    def test_adds_requested_and_stored_urls_to_the_index(self, tmp_path: Path) -> None:
        # A redirect leaves the requested URL and the stored one different;
        # a later claim may find either form.
        sf = _make_source_file("https://example.com/final", "final")
        vr = self._result([], [("https://example.com/start", sf)])
        index: dict[str, str] = {}
        vr.persist_sources(tmp_path, index)
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


# --- Redirects to a page already stored ---

_OLD = "https://example.org/old"
_NEW = "https://example.org/new"
_PAGE = "<html><head><title>New</title></head><body><p>The stored page.</p></body></html>"


def _mock_redirect(respx_mock) -> None:
    import httpx

    respx_mock.get(_OLD).mock(return_value=httpx.Response(301, headers={"Location": "/new"}))
    respx_mock.get(_NEW).mock(return_value=httpx.Response(200, html=_PAGE))


def _sources_on_disk(root: Path) -> list[str]:
    return sorted(
        str(p.relative_to(root / "research" / "sources"))
        for p in (root / "research" / "sources").glob("*/*.md")
    )


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


def _analyst_output():
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment

    return AnalystOutput(
        entity=EntityResolution(
            entity_name="Example", entity_type="company", entity_description="A company."
        ),
        verdict=VerdictAssessment(
            title="Example claim",
            verdict="unverified",
            confidence="low",
            narrative="Not enough evidence.",
            topics=["environmental-impact"],
            verification_level="claimed",
            cap_rationale="Only one kind of source.",
            seo_title="Example claim",
        ),
    )


class TestRedirectToStoredSource:
    def _repo(self, tmp_path: Path, extra: int = 0) -> None:
        _write_source_md(tmp_path / "research" / "sources" / "2025" / "new.md", url=_NEW)
        for i in range(extra):
            _write_source_md(
                tmp_path / "research" / "sources" / "2025" / f"other-{i}.md",
                url=f"https://example.com/other-{i}",
            )

    @pytest.mark.asyncio
    async def test_verify_claim_reuses_the_stored_redirect_target(
        self, tmp_path: Path, stub_ingest_model
    ) -> None:
        import respx

        from orchestrator.pipeline import verify_claim
        from researcher.decomposed import ResearchOutput

        self._repo(tmp_path)

        async def _fake_research(*args, **kwargs):
            return ResearchOutput(
                urls=[_OLD], url_addresses={_OLD: ["sq1"]}, trace={"mode": "decomposed"}
            )

        cfg = VerifyConfig(model="test", max_sources=4, skip_wayback=True, repo_root=str(tmp_path))
        with respx.mock as mock, patch("orchestrator.pipeline._research", side_effect=_fake_research):
            _mock_redirect(mock)
            result = await verify_claim("Example", "claim text", config=cfg)

        assert result.cached_source_ids == ["2025/new"]
        assert result.source_files == []
        assert result.urls_failed == []
        assert result.sources[0]["addresses"] == ["sq1"]
        assert result.persist_sources(tmp_path) == ["2025/new"]
        assert _sources_on_disk(tmp_path) == ["2025/new.md"]

    @pytest.mark.asyncio
    async def test_research_claim_reuses_the_stored_redirect_target(
        self, tmp_path: Path, stub_ingest_model, monkeypatch
    ) -> None:
        import respx

        from common.frontmatter import parse_frontmatter
        from orchestrator.pipeline import research_claim
        from researcher.decomposed import ResearchOutput

        self._repo(tmp_path, extra=3)
        others = [f"https://example.com/other-{i}" for i in range(3)]

        async def _fake_research(*args, **kwargs):
            return ResearchOutput(urls=[*others, _OLD], trace={"mode": "decomposed"})

        async def _fake_run(agent, prompt, timeout_s, **kwargs):
            return _analyst_output(), [], None

        async def _fake_audit(*args, **kwargs):
            return None

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline.build_analyst_prompt", lambda *a, **k: "prompt")
        monkeypatch.setattr("orchestrator.pipeline._run_with_null_retry", _fake_run)
        monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)
        cfg = VerifyConfig(model="test", max_sources=8, skip_wayback=True, repo_root=str(tmp_path))
        with respx.mock as mock:
            _mock_redirect(mock)
            result = await research_claim("claim text", cfg)

        claim_fm, _ = parse_frontmatter((tmp_path / result.claim_path).read_text())
        assert claim_fm["sources"] == [*(f"2025/other-{i}" for i in range(3)), "2025/new"]
        assert _sources_on_disk(tmp_path) == [
            "2025/new.md", *(f"2025/other-{i}.md" for i in range(3))
        ]

    @pytest.mark.asyncio
    async def test_a_url_that_does_not_redirect_still_writes_a_file(
        self, tmp_path: Path, stub_ingest_model
    ) -> None:
        import httpx
        import respx

        from orchestrator.pipeline import verify_claim
        from researcher.decomposed import ResearchOutput

        self._repo(tmp_path)
        other = "https://example.org/page"

        async def _fake_research(*args, **kwargs):
            return ResearchOutput(urls=[other], trace={"mode": "decomposed"})

        cfg = VerifyConfig(model="test", max_sources=4, skip_wayback=True, repo_root=str(tmp_path))
        with respx.mock as mock, patch("orchestrator.pipeline._research", side_effect=_fake_research):
            mock.get(other).mock(return_value=httpx.Response(200, html=_PAGE))
            result = await verify_claim("Example", "claim text", config=cfg)

        assert result.cached_sources == []
        assert result.persist_sources(tmp_path) == ["2026/page"]
        assert _sources_on_disk(tmp_path) == ["2025/new.md", "2026/page.md"]


class TestSameBatchRedirects:
    @pytest.mark.asyncio
    async def test_two_urls_redirecting_to_one_page_give_one_result(self) -> None:
        from orchestrator.pipeline import IngestNotes

        a, b, c = "https://example.org/a", "https://example.org/b", "https://example.org/c"
        final = {a: _NEW, b: _NEW, c: c}

        async def _fake_ingest_one(client, url, cfg, today, sem, notes=None, **_):
            notes.final_urls[url] = final[url]
            return (url, _make_source_file(url, url.rsplit("/", 1)[1]))

        notes = IngestNotes()
        with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
            results, _errors = await _ingest_urls(
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
        from orchestrator.pipeline import IngestNotes

        cached, a, c = "https://example.org/cached", "https://example.org/a", "https://example.org/c"
        final = {a: _NEW, c: c}

        async def _fake_ingest_one(client, url, cfg, today, sem, notes=None, **_):
            notes.final_urls[url] = final[url]
            return (url, _make_source_file(url, url.rsplit("/", 1)[1]))

        notes = IngestNotes()
        with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
            results, _errors = await _ingest_urls(
                None, [a, c], _make_cfg(), asyncio.Semaphore(8), target=1, notes=notes,
                known_pages={canonical_key(_NEW): cached},
            )

        assert [u for u, _sf in results] == [c]
        assert notes.aliases == {a: cached}

    @pytest.mark.asyncio
    async def test_claim_reaches_its_target(self, tmp_path: Path, stub_ingest_model) -> None:
        import httpx
        import respx

        from orchestrator.pipeline import verify_claim
        from researcher.decomposed import ResearchOutput

        _write_source_md(tmp_path / "research" / "sources" / "2025" / "new.md", url=_NEW)
        other = "https://example.org/page"

        async def _fake_research(*args, **kwargs):
            return ResearchOutput(
                urls=[_NEW, _OLD, other],
                url_addresses={_NEW: ["sq1"], _OLD: ["sq2"], other: ["sq3"]},
                trace={"mode": "decomposed"},
            )

        async def _slow_page(request):
            # Lets the redirect finish first, so it is the one that would count.
            await asyncio.sleep(0.05)
            return httpx.Response(200, html=_PAGE)

        cfg = VerifyConfig(model="test", max_sources=2, skip_wayback=True, repo_root=str(tmp_path))
        with respx.mock as mock, patch("orchestrator.pipeline._research", side_effect=_fake_research):
            _mock_redirect(mock)
            mock.get(other).mock(side_effect=_slow_page)
            result = await verify_claim("Example", "claim text", config=cfg)

        assert result.cached_source_ids == ["2025/new"]
        assert [u for u, _sf in result.source_files] == [other]
        assert result.urls_failed == []
        assert result.sources[0]["addresses"] == ["sq1", "sq2"]
