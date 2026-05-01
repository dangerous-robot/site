"""Research agent: searches the web for sources relevant to a claim."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from common.instructions import load_instructions

logger = logging.getLogger(__name__)

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_RATE_LIMIT_RETRY_DELAY_S = 30.0


class ResearchResult(BaseModel):
    """URLs the research agent found, with reasoning."""

    urls: list[str] = Field(description="URLs to investigate, ordered by relevance")
    reasoning: str = Field(description="Why these sources were selected")


@dataclass
class ResearchDeps:
    http_client: httpx.AsyncClient


_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent)

research_agent = Agent(
    "test",
    output_type=ResearchResult,
    deps_type=ResearchDeps,
    system_prompt=_INSTRUCTIONS,
    retries=2,
)


@research_agent.tool
async def web_search(ctx: RunContext[ResearchDeps], query: str) -> list[dict]:
    """Search the web and return results with title, url, and snippet."""
    try:
        return await search_brave(ctx.deps.http_client, query)
    except Exception as exc:
        logger.warning("Search failed for '%s': %s", query, exc)
        return [{"error": f"Search failed: {exc}"}]


async def search_brave(
    client: httpx.AsyncClient, query: str, max_results: int = 10
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
