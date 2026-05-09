"""Tests for ingestor tools: web_fetch and wayback."""

from __future__ import annotations

import asyncio
import datetime
import re
from pathlib import Path

import httpx
import pytest
import respx
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from ingestor.agent import IngestorDeps, wayback_check, web_fetch
from ingestor.tools.wayback import check_archive_org_timegate, save_to_wayback
from ingestor.tools.web_fetch import extract_page_data
from orchestrator.checkpoints import StepError
from orchestrator.pipeline import VerifyConfig, _ingest_urls

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestExtractPageData:
    def test_title_from_og_tag(self):
        html = (
            '<html><head>'
            '<meta property="og:title" content="OG Title">'
            '<title>Fallback Title - SiteName</title>'
            '</head><body><p>Hello</p></body></html>'
        )
        data = extract_page_data(html, "https://example.com")
        assert data["title"] == "OG Title"

    def test_title_from_title_tag(self):
        html = "<html><head><title>Page Title</title></head><body><p>Hello</p></body></html>"
        data = extract_page_data(html, "https://example.com")
        assert data["title"] == "Page Title"

    def test_strips_nav_footer_script(self):
        html = (
            "<html><body>"
            "<nav>Navigation</nav>"
            "<p>Main content</p>"
            "<footer>Footer</footer>"
            "<script>var x = 1;</script>"
            "</body></html>"
        )
        data = extract_page_data(html, "https://example.com")
        assert "Navigation" not in data["text"]
        assert "Footer" not in data["text"]
        assert "var x" not in data["text"]
        assert "Main content" in data["text"]

    def test_truncates_long_text(self):
        long_body = "<p>" + "x" * 60_000 + "</p>"
        html = f"<html><body>{long_body}</body></html>"
        data = extract_page_data(html, "https://example.com")
        assert len(data["text"]) <= 50_100  # 50k + truncation marker
        assert data["text"].endswith("[truncated]")

    def test_extracts_meta_description(self):
        html = (
            '<html><head>'
            '<meta name="description" content="A page description.">'
            '</head><body><p>Content</p></body></html>'
        )
        data = extract_page_data(html, "https://example.com")
        assert data["description"] == "A page description."

    def test_extracts_published_time(self):
        html = (
            '<html><head>'
            '<meta property="article:published_time" content="2025-03-15">'
            '</head><body><p>Content</p></body></html>'
        )
        data = extract_page_data(html, "https://example.com")
        assert data["published_time"] == "2025-03-15"

    def test_url_passthrough(self):
        html = "<html><body><p>Content</p></body></html>"
        data = extract_page_data(html, "https://example.com/page")
        assert data["url"] == "https://example.com/page"

    def test_sample_fixture(self):
        html = (FIXTURES_DIR / "sample_page.html").read_text()
        data = extract_page_data(html, "https://example.com/ai-water-usage-2025")
        assert data["title"] == "AI Water Usage Report 2025"
        assert data["author"] == "Jane Smith"
        assert data["published_time"] == "2025-03-15"
        assert "1.7 billion gallons" in data["text"]
        # Nav/footer/script should be stripped
        assert "analytics" not in data["text"]
        assert "Copyright" not in data["text"]


_TIMEGATE_URL_RE = re.compile(
    r"https://web\.archive\.org/web/\d{14}/.+"
)


class TestCheckArchiveOrgTimeGate:
    """Helper-level tests for ``check_archive_org_timegate``.

    Mocks the TimeGate endpoint with respx; verifies the helper's return
    contract in isolation. The integration matrix lives in
    ``TestWaybackCheckTool``.
    """

    @pytest.mark.asyncio
    async def test_redirect_with_location_returns_archived_url(self) -> None:
        archived = "https://web.archive.org/web/20250315000000/https://example.com/"
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(
                return_value=httpx.Response(302, headers={"location": archived})
            )
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["available"] is True
        assert result["archived_url"] == archived
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_http_location_is_normalized_to_https(self) -> None:
        """archive.org occasionally returns ``http://`` Locations; the helper
        canonicalizes to ``https://`` so committed sidecars never carry
        plaintext archive URLs."""
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(
                return_value=httpx.Response(
                    302,
                    headers={
                        "location": "http://web.archive.org/web/20250315000000/https://example.com/"
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["archived_url"] == (
            "https://web.archive.org/web/20250315000000/https://example.com/"
        )

    @pytest.mark.asyncio
    async def test_redirect_without_location_is_silent_miss(self) -> None:
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(302))
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["available"] is False
        assert result["archived_url"] is None
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_404_is_silent_miss(self) -> None:
        """No snapshot is *not* a transport error."""
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(404))
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["available"] is False
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_unexpected_200_is_silent_miss(self) -> None:
        """A 200 (rather than 302) means the request didn't redirect to
        a snapshot; treat as miss without raising."""
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(200, text=""))
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["available"] is False
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_5xx_sets_error_key(self) -> None:
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(503))
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["available"] is False
        assert result.get("error"), "5xx should set the transport-failure error key"

    @pytest.mark.asyncio
    async def test_timeout_sets_error_key(self) -> None:
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(
                side_effect=httpx.ReadTimeout("timegate timeout")
            )
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["available"] is False
        assert result.get("error"), "timeout should set the transport-failure error key"

    @pytest.mark.asyncio
    async def test_connect_error_includes_class_in_error(self) -> None:
        """Empty-message transport exceptions still produce a diagnosable
        error string — class name is logged so we can tell ConnectError
        from ReadTimeout."""
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(side_effect=httpx.ConnectError(""))
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert "ConnectError" in result.get("error", "")


class TestSaveToWayback:
    @pytest.mark.asyncio
    async def test_save_success_with_location(self):
        with respx.mock:
            respx.post("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(
                    200,
                    headers={
                        "content-location": "/web/20250315/https://example.com"
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result == "https://web.archive.org/web/20250315/https://example.com"

    @pytest.mark.asyncio
    async def test_save_rate_limited(self):
        with respx.mock:
            respx.post("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(429)
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_save_network_error(self):
        with respx.mock:
            respx.post("https://web.archive.org/save/https://example.com").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result is None


def _make_ingest_ctx(
    client: httpx.AsyncClient, *, skip_wayback: bool = True
) -> RunContext[IngestorDeps]:
    deps = IngestorDeps(
        http_client=client,
        repo_root="/tmp",
        skip_wayback=skip_wayback,
        today=datetime.date(2026, 4, 19),
    )
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


class TestWebFetchTimeouts:
    """Verify the tightened httpx.Timeout honours connect/read budgets."""

    @pytest.mark.asyncio
    async def test_web_fetch_read_timeout_within_window(self) -> None:
        """A simulated ReadTimeout surfaces as an error dict without hanging.

        ``respx`` raises synchronously, so this exercises the error-handling
        branch without spending real wall time. The tightened ``httpx.Timeout``
        is what would enforce the 15s cap in a live run.
        """
        url = "https://slow.example.com/slow"
        with respx.mock:
            respx.get(url).mock(side_effect=httpx.ReadTimeout("read timeout"))
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client)
                result = await web_fetch(ctx, url)
        assert "error" in result
        assert result["url"] == url

    @pytest.mark.asyncio
    async def test_web_fetch_connect_timeout_fast_fail(self) -> None:
        """A ConnectTimeout fails fast and returns an error dict (no real network)."""
        url = "https://blackhole.example.com/"
        with respx.mock:
            respx.get(url).mock(side_effect=httpx.ConnectTimeout("connect timeout"))
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client)
                result = await web_fetch(ctx, url)
        assert "error" in result
        assert result["url"] == url


class TestWaybackCheckTool:
    """Three-case matrix for the ``wayback_check`` tool side-channel.

    Each case asserts on ``deps.acquisition_writes`` and
    ``deps.wayback_failures`` after invoking the tool — these are what
    the orchestrator drains. The integration drain itself is exercised
    in ``TestIngestUrlsAcquisitionDrain`` below.
    """

    URL = "https://example.com/article"
    ARCHIVED = "https://web.archive.org/web/20250315000000/https://example.com/article"

    def _mock_timegate_hit(self) -> None:
        respx.get(_TIMEGATE_URL_RE).mock(
            return_value=httpx.Response(302, headers={"location": self.ARCHIVED})
        )

    def _mock_timegate_miss(self) -> None:
        respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(404))

    def _mock_save_silent(self) -> None:
        """Mock the save endpoint as a benign 404 so 'no rescue at all' tests
        don't trip respx's unmatched-route guard. Save returns None on 404."""
        respx.post(re.compile(r"https://web\.archive\.org/save/.+")).mock(
            return_value=httpx.Response(404)
        )

    @pytest.mark.asyncio
    async def test_timegate_hit_skips_save(self) -> None:
        """TimeGate 302 → acquisition=archive_org; save endpoint must not be called."""
        with respx.mock:
            self._mock_timegate_hit()
            save_route = respx.post(
                re.compile(r"https://web\.archive\.org/save/.+")
            ).mock(return_value=httpx.Response(404))
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                result = await wayback_check(ctx, self.URL)
        assert result["available"] is True
        assert result["archived_url"] == self.ARCHIVED
        assert ctx.deps.acquisition_writes[self.URL] == {
            "stage": "ingest",
            "recovered_via": "archive_org",
            "outcome": "recovered",
        }
        assert ctx.deps.wayback_failures == []
        assert save_route.called is False, (
            "save must not be called when TimeGate already returned a snapshot"
        )

    @pytest.mark.asyncio
    async def test_timegate_miss_then_save_succeeds(self) -> None:
        """TimeGate 404 → save captures live URL; no acquisition write
        (save is fresh capture, not recovery), no failure recorded."""
        save_archived = "https://web.archive.org/web/20260509000000/https://example.com/article"
        with respx.mock:
            self._mock_timegate_miss()
            respx.post(re.compile(r"https://web\.archive\.org/save/.+")).mock(
                return_value=httpx.Response(
                    200, headers={"content-location": save_archived}
                )
            )
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                result = await wayback_check(ctx, self.URL)
        assert result["available"] is True
        assert result["archived_url"] == save_archived
        assert ctx.deps.acquisition_writes == {}
        assert ctx.deps.wayback_failures == []

    @pytest.mark.asyncio
    async def test_timegate_down_records_failure_and_save_fails(self) -> None:
        """TimeGate 5xx → wayback_unavailable on the failure channel; save
        also fails → no archived URL surfaced."""
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(503))
            self._mock_save_silent()
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                result = await wayback_check(ctx, self.URL)
        assert result["available"] is False
        types = [f["error_type"] for f in ctx.deps.wayback_failures]
        assert types == ["wayback_unavailable"]
        assert ctx.deps.acquisition_writes == {}


class TestMergeAcquisitionWrites:
    """The ingest-stage drain must merge into the research-stage map, not
    overwrite — the Astro schema requires ``origin`` on every acquisition
    entry, and a plain ``dict.update`` would drop it whenever the same URL
    was both discovered (research) and recovered (ingest)."""

    def test_research_stage_origin_survives_ingest_stage_write(self) -> None:
        from orchestrator.pipeline import _merge_acquisition_writes

        url = "https://example.com/recovered"
        acquisition_out = {
            url: {"stage": "research", "origin": "tavily", "query": "x"}
        }
        _merge_acquisition_writes(
            acquisition_out,
            {url: {"stage": "ingest", "recovered_via": "archive_org", "outcome": "recovered"}},
        )
        assert acquisition_out[url] == {
            "stage": "ingest",
            "origin": "tavily",
            "query": "x",
            "recovered_via": "archive_org",
            "outcome": "recovered",
        }

    def test_no_existing_entry_just_adds_the_write(self) -> None:
        from orchestrator.pipeline import _merge_acquisition_writes

        url = "https://example.com/fresh"
        acquisition_out: dict[str, dict] = {}
        write = {"stage": "ingest", "recovered_via": "archive_org", "outcome": "recovered"}
        _merge_acquisition_writes(acquisition_out, {url: write})
        assert acquisition_out[url] == write


class TestIngestUrlsAcquisitionDrain:
    """Verify the orchestrator drain hooks ``wayback_check`` side-channels
    into ``acquisition_out`` and ``ingest_errors`` with the right semantics.

    These tests stub out ``_ingest_one`` and use its ``acquisition_out`` /
    ``failures_out`` parameters to seed the side-channel data — that's the
    same contract production code uses, just without spinning up the LLM
    agent end-to-end.
    """

    @pytest.mark.asyncio
    async def test_acquisition_writes_merge_into_acquisition_out(
        self, monkeypatch
    ) -> None:
        """Successful ingest with archive_org rescue → acquisition_out populated."""
        from orchestrator import pipeline as pipeline_mod
        from ingestor.models import SourceFile, SourceFrontmatter

        url = "https://example.com/recovered"
        sf = SourceFile(
            frontmatter=SourceFrontmatter(
                url=url,
                title="Recovered",
                publisher="Example",
                accessed_date=datetime.date(2026, 4, 26),
                kind="article",
                summary="Rescued via archive.",
            ),
            body="body",
            slug="recovered",
            year=2026,
        )

        async def _fake(
            client, u, cfg, today, sem,
            prefetched_body=None,
            acquisition_out=None, failures_out=None,
        ):
            if acquisition_out is not None:
                acquisition_out[u] = {
                    "stage": "ingest",
                    "recovered_via": "archive_org",
                    "outcome": "recovered",
                }
            return (u, sf)

        monkeypatch.setattr(pipeline_mod, "_ingest_one", _fake)

        cfg = VerifyConfig(model="test", repo_root="/tmp")
        acquisition_out: dict[str, dict] = {}
        results, errors = await _ingest_urls(
            None, [url], cfg, asyncio.Semaphore(2),
            target=1,
            acquisition_out=acquisition_out,
        )
        assert len(results) == 1
        assert errors == []
        assert acquisition_out[url]["recovered_via"] == "archive_org"

    @pytest.mark.asyncio
    async def test_failures_become_step_errors_only_on_terminal_failure(
        self, monkeypatch
    ) -> None:
        """A wayback transport blip on a *successful* ingest stays quiet;
        the same blip on a *failed* ingest produces a StepError."""
        from orchestrator import pipeline as pipeline_mod
        from ingestor.models import SourceFile, SourceFrontmatter

        url_ok = "https://example.com/ok"
        url_bad = "https://example.com/bad"

        sf_ok = SourceFile(
            frontmatter=SourceFrontmatter(
                url=url_ok,
                title="OK",
                publisher="Example",
                accessed_date=datetime.date(2026, 4, 26),
                kind="article",
                summary="Success.",
            ),
            body="body",
            slug="ok",
            year=2026,
        )

        async def _fake(
            client, u, cfg, today, sem,
            prefetched_body=None,
            acquisition_out=None, failures_out=None,
        ):
            failure = {
                "stage": "ingest",
                "error_type": "wayback_unavailable",
                "message": "archive.org TimeGate check failed (HTTP 503)",
            }
            if failures_out is not None:
                failures_out.append(failure)
            if u == url_ok:
                return (u, sf_ok)
            return StepError(
                step="ingest", url=u, error_type="http_error", message="boom"
            )

        monkeypatch.setattr(pipeline_mod, "_ingest_one", _fake)

        cfg = VerifyConfig(model="test", repo_root="/tmp")
        results, errors = await _ingest_urls(
            None, [url_ok, url_bad], cfg, asyncio.Semaphore(2),
            target=2,
        )
        assert len(results) == 1
        # The bad URL contributes its own StepError + the wayback_failures
        # promoted to StepError. The ok URL stays silent.
        types_for_bad = [e.error_type for e in errors if e.url == url_bad]
        assert "http_error" in types_for_bad
        assert "wayback_unavailable" in types_for_bad
        assert all(e.url != url_ok for e in errors), (
            "Successful ingest must not surface wayback failures as StepErrors"
        )
