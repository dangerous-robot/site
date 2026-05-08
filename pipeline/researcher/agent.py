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
    client: httpx.AsyncClient, query: str, max_results: int = 10
) -> list[dict]:
    """Search using the Brave Web Search API.

    Requires BRAVE_WEB_SEARCH_API_KEY in the environment.

    If a quoted query returns zero results, retries once with all quote
    characters stripped. The Haiku-class planner sometimes wraps descriptive
    phrases (e.g. ``"Anthropic sustainability report"``) that don't match
    any document verbatim; without this fallback those queries silently
    yield no candidates.
    """
    api_key = os.environ.get("BRAVE_WEB_SEARCH_API_KEY")
    if not api_key:
        raise RuntimeError("BRAVE_WEB_SEARCH_API_KEY is not set")

    async def _fetch(q: str) -> httpx.Response:
        return await client.get(
            _BRAVE_SEARCH_URL,
            params={"q": q, "count": max_results},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=15.0,
        )

    async def _fetch_with_429_retry(q: str) -> httpx.Response:
        resp = await _fetch(q)
        if resp.status_code == 429:
            header_val = resp.headers.get("retry-after")
            try:
                wait = float(header_val) if header_val else _BRAVE_RATE_LIMIT_RETRY_DELAY_S
            except ValueError:
                wait = _BRAVE_RATE_LIMIT_RETRY_DELAY_S
            logger.warning("Brave 429 rate limit; retrying in %.0fs", wait)
            await asyncio.sleep(wait)
            resp = await _fetch(q)
        resp.raise_for_status()
        return resp

    def _extract(resp: httpx.Response) -> list[dict]:
        data = resp.json()
        return [
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": item.get("description", ""),
            }
            for item in data.get("web", {}).get("results", [])
        ]

    resp = await _fetch_with_429_retry(query)
    results = _extract(resp)

    if not results and ('"' in query or "'" in query):
        unquoted = query.replace('"', "").replace("'", "").strip()
        if unquoted and unquoted != query:
            logger.warning(
                "Brave returned 0 results for quoted query %r; retrying unquoted as %r",
                query, unquoted,
            )
            resp = await _fetch_with_429_retry(unquoted)
            results = _extract(resp)

    return results
