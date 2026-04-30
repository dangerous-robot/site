"""Tests for 429 retry behavior in search_brave."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from researcher.agent import search_brave

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_RESULT = {"web": {"results": [{"url": "https://example.com", "title": "Ex", "description": "d"}]}}


@pytest.fixture(autouse=True)
def _brave_key(monkeypatch):
    monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "test-key")


class TestBrave429Handling:
    @pytest.mark.asyncio
    async def test_429_single_retry_then_raise(self) -> None:
        """Two consecutive 429s: retries once then raises HTTPStatusError."""
        with respx.mock:
            route = respx.get(_BRAVE_URL).mock(
                side_effect=[httpx.Response(429), httpx.Response(429)]
            )
            async with httpx.AsyncClient() as client:
                with patch("researcher.agent.asyncio.sleep", autospec=True) as sleep_mock:
                    sleep_mock.return_value = None
                    with pytest.raises(httpx.HTTPStatusError) as exc_info:
                        await search_brave(client, "test query")
        assert route.call_count == 2
        assert sleep_mock.await_count == 1
        assert exc_info.value.response.status_code == 429

    @pytest.mark.asyncio
    async def test_429_recovers_on_second_try(self) -> None:
        """429 then 200: retries once and returns results."""
        with respx.mock:
            route = respx.get(_BRAVE_URL).mock(
                side_effect=[
                    httpx.Response(429),
                    httpx.Response(200, json=_RESULT),
                ]
            )
            async with httpx.AsyncClient() as client:
                with patch("researcher.agent.asyncio.sleep", autospec=True) as sleep_mock:
                    sleep_mock.return_value = None
                    results = await search_brave(client, "test query")
        assert route.call_count == 2
        assert sleep_mock.await_count == 1
        assert results == [{"url": "https://example.com", "title": "Ex", "snippet": "d"}]

    @pytest.mark.asyncio
    async def test_retry_after_header_honored(self) -> None:
        """Retry-After header value is used as sleep duration."""
        with respx.mock:
            respx.get(_BRAVE_URL).mock(
                side_effect=[
                    httpx.Response(429, headers={"retry-after": "45"}),
                    httpx.Response(200, json=_RESULT),
                ]
            )
            async with httpx.AsyncClient() as client:
                with patch("researcher.agent.asyncio.sleep", autospec=True) as sleep_mock:
                    sleep_mock.return_value = None
                    await search_brave(client, "test query")
        assert sleep_mock.await_args.args[0] == 45.0
