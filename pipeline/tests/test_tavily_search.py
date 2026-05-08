"""Tests for the Tavily search backend wrapper.

Mirrors the Brave-search test layout in ``test_brave_search.py``.
Coverage: success path with field mapping, missing API key raises,
single 429 retry honours ``Retry-After``, double 429 raises
``TavilyRateLimitError``.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from common import throttle as throttle_mod
from researcher.tools.tavily import TavilyRateLimitError, search_tavily

_TAVILY_URL = "https://api.tavily.com/search"

# Minimal Tavily success body. Mirrors the schema documented at
# https://docs.tavily.com/documentation/api-reference/endpoint/search.
_RESULT = {
    "query": "test query",
    "results": [
        {
            "url": "https://example.com",
            "title": "Ex",
            "content": "tavily-content-snippet",
            "score": 0.9,
        },
    ],
}


@pytest.fixture(autouse=True)
def _tavily_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _reset_throttle():
    """Drop the module-level tavily bucket between tests so timing-sensitive
    asserts don't depend on previous-test token state."""
    yield
    throttle_mod.reset("tavily")


class TestTavilySuccess:
    @pytest.mark.asyncio
    async def test_returns_brave_compatible_shape(self) -> None:
        """Tavily's ``content`` field maps onto ``snippet``."""
        with respx.mock:
            respx.post(_TAVILY_URL).mock(
                return_value=httpx.Response(200, json=_RESULT),
            )
            async with httpx.AsyncClient() as client:
                results = await search_tavily(client, "test query")

        assert results == [
            {
                "url": "https://example.com",
                "title": "Ex",
                "snippet": "tavily-content-snippet",
            }
        ]

    @pytest.mark.asyncio
    async def test_authorization_header_uses_bearer(self) -> None:
        """The wrapper sends ``Authorization: Bearer <key>``."""
        with respx.mock:
            route = respx.post(_TAVILY_URL).mock(
                return_value=httpx.Response(200, json=_RESULT),
            )
            async with httpx.AsyncClient() as client:
                await search_tavily(client, "q")
        sent = route.calls.last.request
        assert sent.headers.get("authorization") == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_query_in_post_body(self) -> None:
        """The query is sent in the POST body, not the URL."""
        import json

        with respx.mock:
            route = respx.post(_TAVILY_URL).mock(
                return_value=httpx.Response(200, json=_RESULT),
            )
            async with httpx.AsyncClient() as client:
                await search_tavily(client, "carbon footprint")
        body = json.loads(route.calls.last.request.content)
        assert body["query"] == "carbon footprint"

    @pytest.mark.asyncio
    async def test_drops_results_with_empty_url(self) -> None:
        """Defensive: a result with no ``url`` is skipped, not returned."""
        body = {"results": [{"url": "", "title": "x", "content": "y"}]}
        with respx.mock:
            respx.post(_TAVILY_URL).mock(
                return_value=httpx.Response(200, json=body),
            )
            async with httpx.AsyncClient() as client:
                results = await search_tavily(client, "q")
        assert results == []


class TestTavilyAuth:
    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        async with httpx.AsyncClient() as client:
            with pytest.raises(RuntimeError, match="TAVILY_API_KEY is not set"):
                await search_tavily(client, "q")


class TestTavily429Handling:
    @pytest.mark.asyncio
    async def test_single_429_then_recover(self) -> None:
        """One 429 is retried once after honouring Retry-After."""
        with respx.mock:
            route = respx.post(_TAVILY_URL).mock(
                side_effect=[
                    httpx.Response(429, headers={"retry-after": "12"}),
                    httpx.Response(200, json=_RESULT),
                ],
            )
            async with httpx.AsyncClient() as client:
                with patch(
                    "researcher.tools.tavily.asyncio.sleep", autospec=True
                ) as sleep_mock:
                    sleep_mock.return_value = None
                    results = await search_tavily(client, "q")
        assert route.call_count == 2
        assert sleep_mock.await_count == 1
        assert sleep_mock.await_args.args[0] == 12.0
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_double_429_raises_typed_error(self) -> None:
        """Two 429s in a row raise TavilyRateLimitError; the dispatcher
        catches it and falls back to Brave."""
        with respx.mock:
            respx.post(_TAVILY_URL).mock(
                side_effect=[httpx.Response(429), httpx.Response(429)],
            )
            async with httpx.AsyncClient() as client:
                with patch(
                    "researcher.tools.tavily.asyncio.sleep", autospec=True
                ) as sleep_mock:
                    sleep_mock.return_value = None
                    with pytest.raises(TavilyRateLimitError):
                        await search_tavily(client, "q")

    @pytest.mark.asyncio
    async def test_500_propagates_as_http_error(self) -> None:
        """Non-429 server errors raise HTTPStatusError so the dispatcher
        falls back per-query without classifying as rate-limit."""
        with respx.mock:
            respx.post(_TAVILY_URL).mock(
                return_value=httpx.Response(500, text="boom"),
            )
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await search_tavily(client, "q")
