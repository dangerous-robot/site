"""Brave Web Search client used by the decomposed researcher."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_RATE_LIMIT_RETRY_DELAY_S = 30.0


async def search_brave(
    client: httpx.AsyncClient, query: str, max_results: int = 8
) -> list[dict]:
    """Search using the Brave Web Search API.

    Requires BRAVE_WEB_SEARCH_API_KEY in the environment.
    """
    api_key = os.environ.get("BRAVE_WEB_SEARCH_API_KEY")
    if not api_key:
        raise RuntimeError("BRAVE_WEB_SEARCH_API_KEY is not set")

    async def _fetch() -> httpx.Response:
        return await client.get(
            _BRAVE_SEARCH_URL,
            params={"q": query, "count": max_results},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=15.0,
        )

    resp = await _fetch()
    if resp.status_code == 429:
        header_val = resp.headers.get("retry-after")
        try:
            wait = float(header_val) if header_val else _BRAVE_RATE_LIMIT_RETRY_DELAY_S
        except ValueError:
            wait = _BRAVE_RATE_LIMIT_RETRY_DELAY_S
        logger.warning("Brave 429 rate limit; retrying in %.0fs", wait)
        await asyncio.sleep(wait)
        resp = await _fetch()
    resp.raise_for_status()

    data = resp.json()
    results: list[dict] = []

    for item in data.get("web", {}).get("results", []):
        results.append({
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "snippet": item.get("description", ""),
        })

    return results
