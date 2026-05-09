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

from common import throttle as throttle_mod
from ingestor.agent import IngestorDeps, wayback_check, web_fetch
from ingestor.tools.wayback import check_memento, check_wayback, save_to_wayback
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


class TestCheckWayback:
    @pytest.mark.asyncio
    async def test_available(self):
        with respx.mock:
            respx.get("https://archive.org/wayback/available").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "archived_snapshots": {
                            "closest": {
                                "available": True,
                                "url": "https://web.archive.org/web/2025/https://example.com",
                                "timestamp": "20250315",
                            }
                        }
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await check_wayback(client, "https://example.com")
            assert result["available"] is True
            assert result["archived_url"] == "https://web.archive.org/web/2025/https://example.com"

    @pytest.mark.asyncio
    async def test_not_available(self):
        with respx.mock:
            respx.get("https://archive.org/wayback/available").mock(
                return_value=httpx.Response(
                    200,
                    json={"archived_snapshots": {}},
                )
            )
            async with httpx.AsyncClient() as client:
                result = await check_wayback(client, "https://example.com")
            assert result["available"] is False
            assert result["archived_url"] is None

    @pytest.mark.asyncio
    async def test_api_error(self):
        with respx.mock:
            respx.get("https://archive.org/wayback/available").mock(
                return_value=httpx.Response(500)
            )
            async with httpx.AsyncClient() as client:
                result = await check_wayback(client, "https://example.com")
            assert result["available"] is False


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


# Match the Memento Time Travel API path regardless of the dynamic
# ``YYYYMMDDHHMMSS`` segment the helper computes at call time.
_MEMENTO_URL_RE = re.compile(
    r"http://timetravel\.mementoweb\.org/api/json/\d{14}/.+"
)


@pytest.fixture
def _reset_memento_throttle():
    """Drop the module-level memento bucket between tests so import-order
    quirks (e.g. a previous reset() that re-creates buckets on next call)
    don't bleed state across tests. Mirrors ``test_tavily_search.py``."""
    yield
    throttle_mod.reset("memento")


class TestCheckMemento:
    """Helper-level tests for ``check_memento``.

    Mirrors the ``TestCheckWayback`` pattern: respx mocks, no on-disk
    fixtures. The five-case integration matrix lives in
    ``TestWaybackCheckTool``; this class verifies the helper's return
    contract in isolation.
    """

    @pytest.mark.asyncio
    async def test_returns_archived_url_on_hit(
        self, _reset_memento_throttle
    ) -> None:
        with respx.mock:
            respx.get(_MEMENTO_URL_RE).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "mementos": {
                            "closest": {
                                "uri": "https://web.archive.example/2025/example.com",
                                "datetime": "Wed, 15 Mar 2025 00:00:00 GMT",
                            }
                        }
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await check_memento(client, "https://example.com")
        assert result["available"] is True
        assert result["archived_url"] == "https://web.archive.example/2025/example.com"
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_accepts_uri_as_list(self, _reset_memento_throttle) -> None:
        """Some Memento deployments return ``uri`` as a list of mirrors."""
        with respx.mock:
            respx.get(_MEMENTO_URL_RE).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "mementos": {
                            "closest": {
                                "uri": [
                                    "https://web.archive.example/m1/example.com",
                                    "https://web.archive.example/m2/example.com",
                                ],
                            }
                        }
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await check_memento(client, "https://example.com")
        assert result["available"] is True
        assert result["archived_url"] == "https://web.archive.example/m1/example.com"

    @pytest.mark.asyncio
    async def test_empty_mementos_is_silent_miss(
        self, _reset_memento_throttle
    ) -> None:
        """An HTTP 200 with no closest snapshot is *not* a transport error."""
        with respx.mock:
            respx.get(_MEMENTO_URL_RE).mock(
                return_value=httpx.Response(200, json={"mementos": {}}),
            )
            async with httpx.AsyncClient() as client:
                result = await check_memento(client, "https://example.com")
        assert result["available"] is False
        assert result["archived_url"] is None
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_5xx_sets_error_key(self, _reset_memento_throttle) -> None:
        with respx.mock:
            respx.get(_MEMENTO_URL_RE).mock(return_value=httpx.Response(503))
            async with httpx.AsyncClient() as client:
                result = await check_memento(client, "https://example.com")
        assert result["available"] is False
        assert result.get("error"), "5xx should set the transport-failure error key"

    @pytest.mark.asyncio
    async def test_timeout_sets_error_key(self, _reset_memento_throttle) -> None:
        with respx.mock:
            respx.get(_MEMENTO_URL_RE).mock(
                side_effect=httpx.ReadTimeout("memento timeout")
            )
            async with httpx.AsyncClient() as client:
                result = await check_memento(client, "https://example.com")
        assert result["available"] is False
        assert result.get("error"), "timeout should set the transport-failure error key"

    @pytest.mark.asyncio
    async def test_malformed_json_is_silent_miss(
        self, _reset_memento_throttle
    ) -> None:
        """Garbage payload counts as 'no snapshot', not transport failure."""
        with respx.mock:
            respx.get(_MEMENTO_URL_RE).mock(
                return_value=httpx.Response(200, content=b"not json"),
            )
            async with httpx.AsyncClient() as client:
                result = await check_memento(client, "https://example.com")
        assert result["available"] is False
        assert "error" not in result


class TestWaybackCheckTool:
    """Five-case matrix for the ``wayback_check`` tool side-channel.

    Each case asserts on ``deps.acquisition_writes`` and
    ``deps.wayback_failures`` after invoking the tool — these are what
    the orchestrator drains. The integration drain itself is exercised
    in ``TestIngestUrlsAcquisitionDrain`` below.
    """

    URL = "https://example.com/article"

    def _mock_archive_available(self) -> None:
        respx.get("https://archive.org/wayback/available").mock(
            return_value=httpx.Response(
                200,
                json={
                    "archived_snapshots": {
                        "closest": {
                            "available": True,
                            "url": "https://web.archive.org/web/2025/https://example.com/article",
                            "timestamp": "20250315",
                        }
                    }
                },
            )
        )

    def _mock_archive_empty(self) -> None:
        respx.get("https://archive.org/wayback/available").mock(
            return_value=httpx.Response(200, json={"archived_snapshots": {}})
        )

    def _mock_save_silent(self) -> None:
        """Mock the save endpoint as a benign 404 so 'no rescue at all' tests
        don't trip respx's unmatched-route guard. Save returns None on 404."""
        respx.post(re.compile(r"https://web\.archive\.org/save/.+")).mock(
            return_value=httpx.Response(404)
        )

    @pytest.mark.asyncio
    async def test_archive_only_success_no_memento_call(
        self, _reset_memento_throttle
    ) -> None:
        """Archive returns ``available: True`` → no Memento call, acquisition=archive_org."""
        with respx.mock:
            self._mock_archive_available()
            memento_route = respx.get(_MEMENTO_URL_RE).mock(
                return_value=httpx.Response(200, json={"mementos": {}})
            )
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                result = await wayback_check(ctx, self.URL)
        assert result["available"] is True
        assert ctx.deps.acquisition_writes[self.URL] == {
            "stage": "ingest",
            "recovered_via": "archive_org",
            "outcome": "recovered",
        }
        assert ctx.deps.wayback_failures == []
        assert memento_route.called is False, "Memento must not be called on archive hit"

    @pytest.mark.asyncio
    async def test_memento_rescue_when_archive_empty(
        self, _reset_memento_throttle
    ) -> None:
        """Archive empty + Memento hit → acquisition=memento, archived_url from Memento."""
        with respx.mock:
            self._mock_archive_empty()
            respx.get(_MEMENTO_URL_RE).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "mementos": {
                            "closest": {
                                "uri": "https://other-archive.example/2025/example.com/article",
                            }
                        }
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                result = await wayback_check(ctx, self.URL)
        assert result["available"] is True
        assert result["archived_url"] == "https://other-archive.example/2025/example.com/article"
        assert ctx.deps.acquisition_writes[self.URL] == {
            "stage": "ingest",
            "recovered_via": "memento",
            "outcome": "recovered",
        }
        assert ctx.deps.wayback_failures == []

    @pytest.mark.asyncio
    async def test_both_no_snapshot_silent_miss(
        self, _reset_memento_throttle
    ) -> None:
        """Archive empty + Memento empty → no acquisition write, no wayback_failure."""
        with respx.mock:
            self._mock_archive_empty()
            respx.get(_MEMENTO_URL_RE).mock(
                return_value=httpx.Response(200, json={"mementos": {}})
            )
            self._mock_save_silent()
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                result = await wayback_check(ctx, self.URL)
        assert result["available"] is False
        assert ctx.deps.acquisition_writes == {}
        assert ctx.deps.wayback_failures == []

    @pytest.mark.asyncio
    async def test_memento_aggregator_down_records_failure(
        self, _reset_memento_throttle
    ) -> None:
        """Archive empty + Memento 503 → memento_unavailable on the failure channel."""
        with respx.mock:
            self._mock_archive_empty()
            respx.get(_MEMENTO_URL_RE).mock(return_value=httpx.Response(503))
            self._mock_save_silent()
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                await wayback_check(ctx, self.URL)
        types = [f["error_type"] for f in ctx.deps.wayback_failures]
        assert types == ["memento_unavailable"]
        assert ctx.deps.acquisition_writes == {}

    @pytest.mark.asyncio
    async def test_both_unavailable_records_both_failures(
        self, _reset_memento_throttle
    ) -> None:
        """Archive 500 + Memento timeout → both error literals on the failure channel."""
        with respx.mock:
            respx.get("https://archive.org/wayback/available").mock(
                return_value=httpx.Response(500)
            )
            respx.get(_MEMENTO_URL_RE).mock(
                side_effect=httpx.ReadTimeout("memento timeout")
            )
            self._mock_save_silent()
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                await wayback_check(ctx, self.URL)
        types = [f["error_type"] for f in ctx.deps.wayback_failures]
        assert sorted(types) == ["memento_unavailable", "wayback_unavailable"]
        assert ctx.deps.acquisition_writes == {}


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
                "error_type": "memento_unavailable",
                "message": "Memento aggregator check failed (HTTP 503)",
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
        assert "memento_unavailable" in types_for_bad
        assert all(e.url != url_ok for e in errors), (
            "Successful ingest must not surface wayback failures as StepErrors"
        )
