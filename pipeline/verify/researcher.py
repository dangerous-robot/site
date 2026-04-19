"""Research agent: searches the web for sources relevant to a claim."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

logger = logging.getLogger(__name__)


class ResearchResult(BaseModel):
    """URLs the research agent found, with reasoning."""

    urls: list[str] = Field(description="URLs to investigate, ordered by relevance")
    reasoning: str = Field(description="Why these sources were selected")


SYSTEM_PROMPT = """\
You are a research assistant for dangerousrobot.org. Given a claim about an
entity, your job is to find web sources that can help verify or refute it.

Use the web_search tool with 1-3 targeted search queries. Good queries are
specific and include the entity name plus key terms from the claim.

Return 2-5 URLs that are most relevant to evaluating the claim.

Prefer:
- Primary sources (official docs, reports, audits)
- Independent analyses from reputable outlets
- Recent content over older content

Avoid:
- Social media posts or forums
- Opinion pieces without citations
- Pure marketing pages\
"""


@dataclass
class ResearchDeps:
    http_client: httpx.AsyncClient


research_agent = Agent(
    "test",
    output_type=ResearchResult,
    deps_type=ResearchDeps,
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)


@research_agent.tool
async def web_search(ctx: RunContext[ResearchDeps], query: str) -> list[dict]:
    """Search the web and return results with title, url, and snippet."""
    try:
        results = await _search_duckduckgo(ctx.deps.http_client, query)
        return results
    except Exception as exc:
        logger.warning("Search failed for '%s': %s", query, exc)
        return [{"error": f"Search failed: {exc}"}]


async def _search_duckduckgo(
    client: httpx.AsyncClient, query: str, max_results: int = 8
) -> list[dict]:
    """Scrape DuckDuckGo HTML search results.

    POC implementation -- fragile HTML scraping. Replace with a proper
    search API (Brave, SerpAPI, etc.) for production use.
    """
    resp = await client.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (dangerousrobot-research/0.1)"},
        timeout=15.0,
        follow_redirects=True,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict] = []

    for div in soup.select(".result"):
        link = div.select_one(".result__a")
        snippet_el = div.select_one(".result__snippet")

        if not link or not link.get("href"):
            continue

        url = link["href"]
        # DDG wraps URLs in a redirect; extract the real URL
        if "uddg=" in url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "uddg" in params:
                url = params["uddg"][0]

        if not url.startswith("http"):
            continue

        results.append({
            "url": url,
            "title": link.get_text(strip=True),
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })

        if len(results) >= max_results:
            break

    return results
