"""Research agent: searches the web for sources relevant to a claim."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from common.instructions import load_instructions

logger = logging.getLogger(__name__)


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
    client: httpx.AsyncClient, query: str, max_results: int = 8
) -> list[dict]:
    """Search using the Brave Web Search API.

    Requires BRAVE_WEB_SEARCH_API_KEY in the environment.
    """
    api_key = os.environ.get("BRAVE_WEB_SEARCH_API_KEY")
    if not api_key:
        raise RuntimeError("BRAVE_WEB_SEARCH_API_KEY is not set")

    resp = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max_results},
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
        timeout=15.0,
    )
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
