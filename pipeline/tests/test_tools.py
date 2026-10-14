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
from ingestor.tools.wayback import (
    check_archive_org_timegate,
    find_or_save_archive,
    save_to_wayback,
)
from ingestor.tools.web_fetch import extract_page_data
from loop import VerifyConfig, ingest_urls
from loop.errors import StepError
from common.timeouts import RATE_LIMIT_RETRY_S

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


@pytest.fixture
def no_sleep(monkeypatch) -> list[float]:
    """Record rate-limit waits instead of sleeping."""
    waits: list[float] = []

    async def _wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("ingestor.tools.wayback._wait", _wait)
    return waits


class TestTimeGateRateLimit:
    @pytest.mark.asyncio
    async def test_429_then_redirect_finds_the_snapshot(self, no_sleep) -> None:
        archived = "https://web.archive.org/web/20250315000000/https://example.com/"
        with respx.mock:
            route = respx.get(_TIMEGATE_URL_RE).mock(
                side_effect=[
                    httpx.Response(429, headers={"Retry-After": "3600"}),
                    httpx.Response(302, headers={"location": archived}),
                ]
            )
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result == {"available": True, "archived_url": archived}
        assert route.call_count == 2
        # Retry-After is honoured but capped.
        assert no_sleep == [RATE_LIMIT_RETRY_S]

    @pytest.mark.asyncio
    async def test_429_twice_is_an_error_not_a_silent_miss(self, no_sleep) -> None:
        with respx.mock:
            route = respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(429))
            async with httpx.AsyncClient() as client:
                result = await check_archive_org_timegate(client, "https://example.com")
        assert result["available"] is False
        assert result["error"] == "archive.org TimeGate check failed (HTTP 429)"
        assert route.call_count == 2

    @pytest.mark.parametrize(
        ("header", "expected"),
        [("0", 0.0), ("1.5", 1.5), ("soon", RATE_LIMIT_RETRY_S), ("nan", RATE_LIMIT_RETRY_S),
         ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0), ("Wed, 21 Oct 2015 07:28:00 -0000", 0.0)],
    )
    @pytest.mark.asyncio
    async def test_retry_after_forms(self, no_sleep, header: str, expected: float) -> None:
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(
                side_effect=[httpx.Response(429, headers={"Retry-After": header}), httpx.Response(404)]
            )
            async with httpx.AsyncClient() as client:
                await check_archive_org_timegate(client, "https://example.com")
        assert no_sleep == [expected]


class TestFindOrSaveArchive:
    URL = "https://example.com/article"
    SAVE_RE = re.compile(r"https://web\.archive\.org/save/.+")

    @pytest.mark.asyncio
    async def test_no_save_after_a_timegate_429(self, no_sleep) -> None:
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(429))
            save = respx.get(self.SAVE_RE).mock(return_value=httpx.Response(200))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, self.URL)
        assert lookup.archived_url is None
        assert lookup.errors == ["archive.org TimeGate check failed (HTTP 429)"]
        assert lookup.incomplete is True
        assert save.called is False

    @pytest.mark.asyncio
    async def test_miss_then_save(self, mock_capture_replay) -> None:
        archived = "https://web.archive.org/web/20260509000000/https://example.com/article"
        with respx.mock:
            mock_capture_replay()
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(404))
            respx.get(self.SAVE_RE).mock(
                return_value=httpx.Response(200, headers={"content-location": archived})
            )
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, self.URL)
        assert lookup.archived_url == archived
        assert lookup.found_existing is False
        assert lookup.errors == []

    @pytest.mark.asyncio
    async def test_miss_without_save_sends_no_capture(self) -> None:
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(404))
            save = respx.get(self.SAVE_RE).mock(return_value=httpx.Response(200))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, self.URL, allow_save=False)
        assert lookup.archived_url is None
        assert save.called is False


class TestArchiveBudgets:
    def test_lookup_cost_covers_every_archive_request_and_the_retry_waits(self) -> None:
        from common import timeouts as t

        assert t.archive_lookup_cost_s() == (
            t.WAYBACK_CHECK_S + 2 * t.WAYBACK_VERIFY_S + t.WAYBACK_CDX_S
            + t.WAYBACK_SAVE_S + 3 * t.RATE_LIMIT_RETRY_S
        )

    def test_lookup_budget_is_the_lookup_cost(self) -> None:
        from common import timeouts as t

        assert t.archive_lookup_budget_s() == t.archive_lookup_cost_s()

    def test_ingest_budget_includes_the_recovery_lookup(self) -> None:
        from common import timeouts as t

        assert t.ingest_budget_with_wayback_s() == (
            t.HTTP_CONNECT_S + t.HTTP_READ_S
            + t.RATE_LIMIT_RETRY_S + t.HTTP_CONNECT_S + t.HTTP_READ_S
            + t.archive_lookup_cost_s()
            + t.LLM_BUDGET_S
        )


class TestSaveToWayback:
    @pytest.mark.asyncio
    async def test_save_success_with_location(self):
        with respx.mock:
            respx.get("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(
                    200,
                    headers={
                        "content-location": "/web/20250315000000/https://example.com"
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result == {
                "archived_url": "https://web.archive.org/web/20250315000000/https://example.com"
            }

    @pytest.mark.asyncio
    async def test_save_redirect_to_a_dated_snapshot_succeeds(self):
        # Observed live: GET /save/<url> answers 302 to the new capture.
        snapshot = "https://web.archive.org/web/20261007123641/https://example.com/"
        with respx.mock:
            route = respx.get("https://web.archive.org/save/https://example.com/").mock(
                return_value=httpx.Response(302, headers={"location": snapshot})
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com/")
        assert result == {"archived_url": snapshot}
        assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_save_with_no_snapshot_location_is_an_error(self):
        # Observed live: an anonymous POST answered 200 with no location and
        # no capture existed afterwards; an undated link is not a snapshot.
        with respx.mock:
            respx.get("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(200)
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
        assert result == {
            "archived_url": None,
            "error": "Wayback save returned no snapshot (HTTP 200)",
        }

    @pytest.mark.asyncio
    async def test_save_with_an_undated_location_is_an_error(self):
        with respx.mock:
            respx.get("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(
                    302, headers={"location": "https://web.archive.org/web/https://example.com"}
                )
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
        assert result["archived_url"] is None
        assert result["error"] == "Wayback save returned no snapshot (HTTP 302)"

    @pytest.mark.asyncio
    async def test_save_rate_limited_twice_returns_the_reason(self, no_sleep):
        with respx.mock:
            route = respx.get("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(429)
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
        assert result["archived_url"] is None
        assert "429" in result["error"]
        assert route.call_count == 2
        assert no_sleep == [RATE_LIMIT_RETRY_S]

    @pytest.mark.asyncio
    async def test_save_retries_once_after_429(self, no_sleep):
        archived = "https://web.archive.org/web/20250315000000/https://example.com"
        with respx.mock:
            respx.get("https://web.archive.org/save/https://example.com").mock(
                side_effect=[
                    httpx.Response(429, headers={"Retry-After": "1"}),
                    httpx.Response(200, headers={"content-location": archived}),
                ]
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
        assert result == {"archived_url": archived}
        assert no_sleep == [1.0]

    @pytest.mark.asyncio
    async def test_save_network_error(self):
        with respx.mock:
            respx.get("https://web.archive.org/save/https://example.com").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result["archived_url"] is None
            assert "ConnectError" in result["error"]


def _make_ingest_ctx(
    client: httpx.AsyncClient, *, skip_wayback: bool = True
) -> RunContext[IngestorDeps]:
    deps = IngestorDeps(
        http_client=client,
        repo_root="/tmp",
        requested_url="https://example.com/",
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


class TestWebFetchRefusesCaptureRequests:
    """``web_fetch`` never sends a GET to archive.org's /save/ path.

    A GET to ``/save/<url>`` asks Save Page Now to capture the page. The
    model chose such a URL on its own in a live ``dr draft --dry-run``;
    the tool refuses it on every path, dry run or not.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [
        "https://web.archive.org/save/https://example.com/article",
        "http://web.archive.org/save/https://example.com/article",
        "https://WEB.archive.org/save/example.com",
        "https://archive.org/save/https://example.com/article",
        "https://web.archive.org/save?url=https://example.com/article",
    ])
    async def test_save_url_is_refused_and_never_sent(self, url: str) -> None:
        with respx.mock(assert_all_called=False) as router:
            save = router.route(host__regex=r"(^|\.)archive\.org$").mock(
                return_value=httpx.Response(200, text="<html><body>captured</body></html>")
            )
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client, skip_wayback=False)
                result = await web_fetch(ctx, url)
            save_calls = save.call_count
        assert save_calls == 0
        assert "error" in result and "Refused" in result["error"]
        assert ctx.deps.fetched_text == {}

    @pytest.mark.asyncio
    async def test_save_url_is_refused_even_when_prefetched(self) -> None:
        url = "https://web.archive.org/save/https://example.com/"
        async with httpx.AsyncClient() as client:
            ctx = _make_ingest_ctx(client)
            ctx.deps.prefetched_bodies[url] = "body"
            result = await web_fetch(ctx, url)
        assert "Refused" in result["error"]
        assert ctx.deps.requested_fetched is False

    @pytest.mark.asyncio
    async def test_archive_copy_is_still_fetched(self) -> None:
        """Positive control: a /web/ snapshot URL is a page fetch and goes through."""
        url = "https://web.archive.org/web/20250315000000/https://example.com/"
        with respx.mock:
            route = respx.get(url).mock(return_value=httpx.Response(
                200, text="<html><head><title>T</title></head><body><p>Archived page text.</p></body></html>",
                headers={"content-type": "text/html"},
            ))
            async with httpx.AsyncClient() as client:
                ctx = _make_ingest_ctx(client)
                result = await web_fetch(ctx, url)
        assert route.called is True
        assert "error" not in result


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
        respx.get(re.compile(r"https://web\.archive\.org/save/.+")).mock(
            return_value=httpx.Response(404)
        )

    @pytest.mark.asyncio
    async def test_timegate_hit_skips_save(self, mock_capture_replay) -> None:
        """TimeGate 302 → acquisition=archive_org; save endpoint must not be called."""
        with respx.mock:
            mock_capture_replay()
            self._mock_timegate_hit()
            save_route = respx.get(
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
    async def test_timegate_miss_then_save_succeeds(self, mock_capture_replay) -> None:
        """TimeGate 404 → save captures live URL; no acquisition write
        (save is fresh capture, not recovery), no failure recorded."""
        save_archived = "https://web.archive.org/web/20260509000000/https://example.com/article"
        with respx.mock:
            mock_capture_replay()
            self._mock_timegate_miss()
            respx.get(re.compile(r"https://web\.archive\.org/save/.+")).mock(
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
        messages = [f["message"] for f in ctx.deps.wayback_failures]
        assert [f["error_type"] for f in ctx.deps.wayback_failures] == ["wayback_unavailable"] * 2
        assert "TimeGate" in messages[0] and "HTTP 503" in messages[0]
        assert "save" in messages[1] and "HTTP 404" in messages[1]
        assert ctx.deps.acquisition_writes == {}


class TestMergeAcquisitionWrites:
    """The ingest-stage drain must merge into the research-stage map, not
    overwrite — the Astro schema requires ``origin`` on every acquisition
    entry, and a plain ``dict.update`` would drop it whenever the same URL
    was both discovered (research) and recovered (ingest)."""

    def test_research_stage_origin_survives_ingest_stage_write(self) -> None:
        from loop import merge_acquisition_writes

        url = "https://example.com/recovered"
        acquisition_out = {
            url: {"stage": "research", "origin": "tavily", "query": "x"}
        }
        merge_acquisition_writes(
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
        from loop import merge_acquisition_writes

        url = "https://example.com/fresh"
        acquisition_out: dict[str, dict] = {}
        write = {"stage": "ingest", "recovered_via": "archive_org", "outcome": "recovered"}
        merge_acquisition_writes(acquisition_out, {url: write})
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
        import loop.ingest as ingest_mod
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
            acquisition_out=None, failures_out=None, **_,
        ):
            if acquisition_out is not None:
                acquisition_out[u] = {
                    "stage": "ingest",
                    "recovered_via": "archive_org",
                    "outcome": "recovered",
                }
            return (u, sf)

        monkeypatch.setattr(ingest_mod, "ingest_one", _fake)

        cfg = VerifyConfig(model="test", repo_root="/tmp")
        acquisition_out: dict[str, dict] = {}
        results, errors = await ingest_urls(
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
        import loop.ingest as ingest_mod
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
            acquisition_out=None, failures_out=None, **_,
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

        monkeypatch.setattr(ingest_mod, "ingest_one", _fake)

        cfg = VerifyConfig(model="test", repo_root="/tmp")
        results, errors = await ingest_urls(
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


# --------------------------------------------------------------------------- #
# Capture checks: only a 200 capture of the same page is recorded             #
# --------------------------------------------------------------------------- #

_CDX_RE = re.compile(r"https://web\.archive\.org/cdx/search/cdx.*")
_SAVE_RE = re.compile(r"https://web\.archive\.org/save/.+")
_CDX_HEADER = ["timestamp", "original", "statuscode"]
_ARTICLE = "https://example.com/article"


def _ts(days_ago: float) -> str:
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return when.strftime("%Y%m%d%H%M%S")


def _snap(ts: str, original: str) -> str:
    return f"https://web.archive.org/web/{ts}/{original}"


def _replay(ts: str, original: str) -> str:
    return f"https://web.archive.org/web/{ts}id_/{original}"


def _replayed(status: int, **headers: str) -> httpx.Response:
    return httpx.Response(
        status, headers={"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT", **headers}
    )


def _timegate_to(link: str) -> None:
    respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(302, headers={"location": link}))


def _cdx(*rows: list[str]):
    return respx.get(_CDX_RE).mock(return_value=httpx.Response(200, json=[_CDX_HEADER, *rows]))


def _save_to(link: str):
    return respx.get(_SAVE_RE).mock(
        return_value=httpx.Response(200, headers={"content-location": link})
    )


class TestCaptureLookup:
    @pytest.mark.asyncio
    async def test_rejects_capture_of_differently_cased_url(self) -> None:
        cased = "https://example.com/Article"
        older, newer = _ts(5), _ts(1)
        with respx.mock:
            _timegate_to(_snap(newer, cased))
            # The newer row is a 200 too: only the same-page rule skips it.
            _cdx([older, _ARTICLE, "200"], [newer, cased, "200"])
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE, allow_save=False)
        assert lookup.archived_url == _snap(older, _ARTICLE)
        assert lookup.found_existing is True
        assert lookup.errors == []

    @pytest.mark.asyncio
    async def test_rejects_404_capture_of_same_url(self) -> None:
        bad, good = _ts(1), _ts(30)
        with respx.mock:
            _timegate_to(_snap(bad, _ARTICLE))
            respx.head(_replay(bad, _ARTICLE)).mock(return_value=_replayed(404))
            _cdx([good, _ARTICLE, "200"])
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE)
        assert lookup.archived_url == _snap(good, _ARTICLE)
        assert lookup.errors == []

    @pytest.mark.asyncio
    async def test_bad_capture_no_cdx_row_without_save_records_none_with_reason(self) -> None:
        bad = _ts(1)
        with respx.mock:
            _timegate_to(_snap(bad, _ARTICLE))
            respx.head(_replay(bad, _ARTICLE)).mock(return_value=_replayed(404))
            _cdx([_ts(3), _ARTICLE, "404"], [_ts(2), "https://example.com/Article", "200"])
            save = respx.get(_SAVE_RE).mock(return_value=httpx.Response(200))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE, allow_save=False)
        assert lookup.archived_url is None
        assert "archive.org capture is an error page (HTTP 404)" in lookup.errors
        assert lookup.incomplete is False
        assert save.called is False

    @pytest.mark.asyncio
    async def test_cdx_timeout_records_none_never_the_bad_capture(self) -> None:
        bad = _ts(1)
        with respx.mock:
            _timegate_to(_snap(bad, _ARTICLE))
            respx.head(_replay(bad, _ARTICLE)).mock(return_value=_replayed(404))
            respx.get(_CDX_RE).mock(side_effect=httpx.ReadTimeout("cdx timeout"))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE, allow_save=False)
        assert lookup.archived_url is None
        assert any("CDX" in e and "ReadTimeout" in e for e in lookup.errors)
        assert lookup.incomplete is True

    @pytest.mark.asyncio
    async def test_no_save_after_a_replay_429(self, no_sleep) -> None:
        ts = _ts(1)
        with respx.mock:
            _timegate_to(_snap(ts, _ARTICLE))
            replay = respx.head(_replay(ts, _ARTICLE)).mock(return_value=httpx.Response(429))
            _cdx()
            save = respx.get(_SAVE_RE).mock(return_value=httpx.Response(200))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE)
        assert replay.call_count == 2
        assert save.called is False
        assert lookup.archived_url is None
        assert lookup.errors == ["archive.org replay check failed (HTTP 429)"]
        assert lookup.incomplete is True

    @pytest.mark.asyncio
    async def test_bad_capture_then_verified_save(self) -> None:
        bad, fresh = _ts(1), _ts(0)
        with respx.mock:
            _timegate_to(_snap(bad, _ARTICLE))
            respx.head(_replay(bad, _ARTICLE)).mock(return_value=_replayed(404))
            respx.head(_replay(fresh, _ARTICLE)).mock(return_value=_replayed(200))
            _cdx()
            _save_to(_snap(fresh, _ARTICLE))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE)
        assert lookup.archived_url == _snap(fresh, _ARTICLE)
        assert lookup.found_existing is False
        assert lookup.errors == []

    @pytest.mark.asyncio
    async def test_save_of_error_page_records_none(self) -> None:
        fresh = _ts(0)
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(404))
            respx.head(_replay(fresh, _ARTICLE)).mock(return_value=_replayed(403))
            _save_to(_snap(fresh, _ARTICLE))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE)
        assert lookup.archived_url is None
        assert lookup.errors == ["Save Page Now captured an error page (HTTP 403)"]

    @pytest.mark.asyncio
    async def test_save_unverified_records_none(self) -> None:
        fresh = _ts(0)
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(404))
            respx.head(_replay(fresh, _ARTICLE)).mock(side_effect=httpx.ConnectError("down"))
            _save_to(_snap(fresh, _ARTICLE))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE)
        assert lookup.archived_url is None
        assert len(lookup.errors) == 1
        assert lookup.errors[0].startswith("could not verify the Save Page Now capture (")

    @pytest.mark.asyncio
    async def test_port_80_original_matches(self) -> None:
        ts, original = _ts(1), "http://example.com:80/article"
        with respx.mock:
            _timegate_to(_snap(ts, original))
            respx.head(_replay(ts, original)).mock(return_value=_replayed(200))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE)
        assert lookup.archived_url == _snap(ts, original)


class TestCheckCapture:
    async def _check(self, link: str, url: str = _ARTICLE, **kwargs):
        from ingestor.tools.wayback import check_capture

        async with httpx.AsyncClient() as client:
            return await check_capture(client, link, url, **kwargs)

    @pytest.mark.asyncio
    async def test_200_replay_is_ok_and_records_the_plain_link(self) -> None:
        ts = _ts(1)
        with respx.mock:
            respx.head(_replay(ts, _ARTICLE)).mock(return_value=_replayed(200))
            check = await self._check(_replay(ts, _ARTICLE))
        assert check.ok is True
        assert check.link == _snap(ts, _ARTICLE)

    @pytest.mark.asyncio
    async def test_404_replay_is_bad(self) -> None:
        ts = _ts(1)
        with respx.mock:
            respx.head(_replay(ts, _ARTICLE)).mock(return_value=_replayed(404))
            check = await self._check(_snap(ts, _ARTICLE))
        assert check.ok is False and check.unverified is False
        assert check.status == 404
        assert check.reason == "archive.org capture is an error page (HTTP 404)"

    @pytest.mark.asyncio
    async def test_5xx_without_memento_is_unverified(self) -> None:
        ts = _ts(1)
        with respx.mock:
            respx.head(_replay(ts, _ARTICLE)).mock(return_value=httpx.Response(503))
            check = await self._check(_snap(ts, _ARTICLE))
        assert check.ok is False and check.unverified is True

    @pytest.mark.asyncio
    async def test_429_twice_is_unverified(self, no_sleep) -> None:
        ts = _ts(1)
        with respx.mock:
            route = respx.head(_replay(ts, _ARTICLE)).mock(return_value=httpx.Response(429))
            check = await self._check(_snap(ts, _ARTICLE))
        assert check.unverified is True
        assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_hop_to_trailing_slash_then_200_is_ok_with_the_first_link(self) -> None:
        ts = _ts(1)
        page, slashed = "https://example.com/docs", "https://example.com/docs/"
        with respx.mock:
            respx.head(_replay(ts, page)).mock(
                return_value=_replayed(302, location=_replay(ts, slashed))
            )
            respx.head(_replay(ts, slashed)).mock(return_value=_replayed(200))
            check = await self._check(_snap(ts, page), page)
        assert check.ok is True
        assert check.link == _snap(ts, page)

    @pytest.mark.asyncio
    async def test_hop_to_another_page_is_bad_unless_it_is_the_fetched_page(self) -> None:
        ts = _ts(1)
        root, moved = "https://docs.python.org./", "https://docs.python.org/3/"
        with respx.mock:
            respx.head(_replay(ts, root)).mock(
                return_value=_replayed(302, location=f"/web/{ts}id_/{moved}")
            )
            respx.head(_replay(ts, moved)).mock(return_value=_replayed(200))
            bad = await self._check(_snap(ts, root), "https://docs.python.org/")
            ok = await self._check(
                _snap(ts, root), "https://docs.python.org/", also_same_as=moved
            )
        assert bad.ok is False and bad.unverified is False
        assert bad.reason == f"archive.org capture redirects to {moved}"
        assert ok.ok is True
        assert ok.link == _snap(ts, root)

    @pytest.mark.asyncio
    async def test_more_than_three_hops_is_bad(self) -> None:
        ts = _ts(1)
        page, slashed = "https://example.com/a", "https://example.com/a/"
        with respx.mock:
            first = respx.head(_replay(ts, page)).mock(
                return_value=_replayed(302, location=_replay(ts, slashed))
            )
            second = respx.head(_replay(ts, slashed)).mock(
                return_value=_replayed(302, location=_replay(ts, page))
            )
            check = await self._check(_snap(ts, page), page)
        assert check.ok is False and check.unverified is False
        assert first.call_count + second.call_count == 3

    @pytest.mark.asyncio
    async def test_trailing_dot_host_matches(self) -> None:
        ts, original = _ts(1), "https://docs.python.org./"
        with respx.mock:
            respx.head(_replay(ts, original)).mock(return_value=_replayed(200))
            check = await self._check(_snap(ts, original), "https://docs.python.org/")
        assert check.ok is True

    @pytest.mark.asyncio
    async def test_undated_link_is_bad_without_a_request(self) -> None:
        with respx.mock:
            check = await self._check("https://web.archive.org/web/2025/https://example.com/article")
        assert check.ok is False and check.unverified is False
        assert "not a dated" in check.reason

    @pytest.mark.asyncio
    async def test_capture_of_another_url_is_bad_without_a_request(self) -> None:
        with respx.mock:
            check = await self._check(_snap(_ts(1), "https://example.com/Article"))
        assert check.reason == "capture is of a different URL (https://example.com/Article)"


class TestFreshness:
    MAX_AGE = datetime.timedelta(days=90)

    @pytest.mark.asyncio
    async def test_stale_capture_triggers_verified_save(self, mock_capture_replay) -> None:
        stale, fresh = _ts(120), _ts(0)
        with respx.mock:
            mock_capture_replay()
            _timegate_to(_snap(stale, _ARTICLE))
            save = _save_to(_snap(fresh, _ARTICLE))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE, max_age=self.MAX_AGE)
        assert save.called is True
        assert lookup.archived_url == _snap(fresh, _ARTICLE)
        assert lookup.found_existing is False

    @pytest.mark.asyncio
    async def test_capture_before_published_date_triggers_save(self, mock_capture_replay) -> None:
        older, fresh = _ts(10), _ts(0)
        published = datetime.date.today() - datetime.timedelta(days=5)
        with respx.mock:
            mock_capture_replay()
            _timegate_to(_snap(older, _ARTICLE))
            _save_to(_snap(fresh, _ARTICLE))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(
                    client, _ARTICLE, max_age=self.MAX_AGE, not_before=published
                )
        assert lookup.archived_url == _snap(fresh, _ARTICLE)

    @pytest.mark.asyncio
    async def test_recent_capture_is_kept_without_a_save(self, mock_capture_replay) -> None:
        recent = _ts(10)
        with respx.mock:
            mock_capture_replay()
            _timegate_to(_snap(recent, _ARTICLE))
            save = respx.get(_SAVE_RE).mock(return_value=httpx.Response(200))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE, max_age=self.MAX_AGE)
        assert lookup.archived_url == _snap(recent, _ARTICLE)
        assert save.called is False

    @pytest.mark.asyncio
    async def test_stale_capture_kept_when_save_is_error_page(self, mock_capture_replay) -> None:
        stale, fresh = _ts(120), _ts(0)
        with respx.mock:
            respx.head(_replay(fresh, _ARTICLE)).mock(return_value=_replayed(403))
            mock_capture_replay()
            _timegate_to(_snap(stale, _ARTICLE))
            _save_to(_snap(fresh, _ARTICLE))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE, max_age=self.MAX_AGE)
        assert lookup.archived_url == _snap(stale, _ARTICLE)
        assert lookup.found_existing is True

    @pytest.mark.asyncio
    async def test_stale_capture_kept_when_save_fails(self, mock_capture_replay) -> None:
        stale = _ts(120)
        with respx.mock:
            mock_capture_replay()
            _timegate_to(_snap(stale, _ARTICLE))
            respx.get(_SAVE_RE).mock(return_value=httpx.Response(503))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE, max_age=self.MAX_AGE)
        assert lookup.archived_url == _snap(stale, _ARTICLE)

    @pytest.mark.asyncio
    async def test_stale_capture_kept_without_save(self, mock_capture_replay) -> None:
        stale = _ts(120)
        with respx.mock:
            mock_capture_replay()
            _timegate_to(_snap(stale, _ARTICLE))
            save = respx.get(_SAVE_RE).mock(return_value=httpx.Response(200))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(
                    client, _ARTICLE, allow_save=False, max_age=self.MAX_AGE
                )
        assert lookup.archived_url == _snap(stale, _ARTICLE)
        assert save.called is False


class TestLatestOkCapture:
    async def _latest(self, url: str = _ARTICLE) -> dict:
        from ingestor.tools.wayback import latest_ok_capture

        async with httpx.AsyncClient() as client:
            return await latest_ok_capture(client, url)

    @pytest.mark.asyncio
    async def test_429_is_retried_once(self, no_sleep) -> None:
        ts = _ts(2)
        with respx.mock:
            route = respx.get(_CDX_RE).mock(
                side_effect=[
                    httpx.Response(429, headers={"Retry-After": "1.5"}),
                    httpx.Response(200, json=[_CDX_HEADER, [ts, _ARTICLE, "200"]]),
                ]
            )
            result = await self._latest()
        assert result == {"archived_url": _snap(ts, _ARTICLE)}
        assert route.call_count == 2
        assert no_sleep == [1.5]

    @pytest.mark.asyncio
    async def test_5xx_is_an_error(self) -> None:
        with respx.mock:
            respx.get(_CDX_RE).mock(return_value=httpx.Response(502))
            result = await self._latest()
        assert result["archived_url"] is None
        assert "HTTP 502" in result["error"]

    @pytest.mark.asyncio
    async def test_transport_error_is_an_error(self) -> None:
        with respx.mock:
            respx.get(_CDX_RE).mock(side_effect=httpx.ConnectError("refused"))
            result = await self._latest()
        assert result["archived_url"] is None
        assert "ConnectError" in result["error"]

    @pytest.mark.parametrize("body", [[], [_CDX_HEADER]])
    @pytest.mark.asyncio
    async def test_empty_answers_are_silent_misses(self, body) -> None:
        with respx.mock:
            respx.get(_CDX_RE).mock(return_value=httpx.Response(200, json=body))
            result = await self._latest()
        assert result == {"archived_url": None}

    @pytest.mark.asyncio
    async def test_unreadable_answer_is_an_error(self) -> None:
        with respx.mock:
            respx.get(_CDX_RE).mock(return_value=httpx.Response(200, text="<html>busy</html>"))
            result = await self._latest()
        assert result["archived_url"] is None
        assert "CDX" in result["error"]

    @pytest.mark.asyncio
    async def test_rows_are_filtered_by_status_and_page(self) -> None:
        good, error_row, cased = _ts(9), _ts(3), _ts(1)
        with respx.mock:
            route = respx.get(_CDX_RE).mock(
                return_value=httpx.Response(
                    200,
                    json=[
                        _CDX_HEADER,
                        [good, "http://www.example.com/article/", "200"],
                        [error_row, _ARTICLE, "404"],
                        [cased, "https://example.com/Article", "200"],
                    ],
                )
            )
            result = await self._latest()
        assert result == {"archived_url": _snap(good, "http://www.example.com/article/")}
        params = route.calls.last.request.url.params
        assert params["url"] == _ARTICLE
        assert params["filter"] == "statuscode:200"


class TestReplayWithoutMemento:
    @pytest.mark.asyncio
    async def test_archive_org_own_404_leaves_a_save_unverified(self) -> None:
        """A capture saved moments ago may not replay yet; that is not an error page."""
        fresh = _ts(0)
        with respx.mock:
            respx.get(_TIMEGATE_URL_RE).mock(return_value=httpx.Response(404))
            respx.head(_replay(fresh, _ARTICLE)).mock(return_value=httpx.Response(404))
            _save_to(_snap(fresh, _ARTICLE))
            async with httpx.AsyncClient() as client:
                lookup = await find_or_save_archive(client, _ARTICLE)
        assert lookup.archived_url is None
        assert lookup.errors == [
            "could not verify the Save Page Now capture (archive.org replay check failed (HTTP 404))"
        ]
