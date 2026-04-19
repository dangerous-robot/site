"""PydanticAI agent definition for the Ingestor."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

import httpx
from pydantic_ai import Agent, RunContext

from common.models import DEFAULT_MODEL
from ingestor.models import SourceFile
from ingestor.tools.wayback import check_wayback, save_to_wayback
from ingestor.tools.web_fetch import extract_page_data

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Ingestor agent for dangerousrobot.org. Your job is to read a web page
and produce a structured source file for the research archive.

## Output format

You must return a SourceFile with these fields:

### frontmatter (all required unless noted):
- url: the original URL provided by the user (do NOT change it)
- archived_url: Wayback Machine URL if available (optional)
- title: the page's title, cleaned of site-name suffixes
- publisher: the organization that published the content
- published_date: date originally published (optional, omit if unknown)
- accessed_date: today's date (provided in context)
- kind: one of: report, article, documentation, dataset, blog, video, index
- summary: factual summary, MAX 30 words and MAX 200 characters.
  Do NOT editorialize. State what the source contains, not what you think of it.
- key_quotes: 0-5 notable direct quotes from the source (optional)

### body:
- 1-3 sentences of additional context. Factual, not evaluative.

### slug:
- Lowercase kebab-case. Derived from the title or topic.

### year:
- Publication year if published_date is known, otherwise access year.

## Content rules (from AGENTS.md):
1. Summaries must NOT paraphrase beyond 30 words.
2. Every source SHOULD have an archived_url when possible.
3. Key quotes must be EXACT text from the source -- never fabricate quotes.

## What NOT to do:
- Do not make claims or verdicts about the source content.
- Do not invent quotes. If you cannot find notable quotes, omit key_quotes.
- Do not include the site name in the title.\
"""


@dataclass
class IngestorDeps:
    """Runtime dependencies for the ingestor agent."""

    http_client: httpx.AsyncClient
    repo_root: str
    skip_wayback: bool = False
    today: datetime.date = field(default_factory=datetime.date.today)

ingestor_agent = Agent(
    "test",
    output_type=SourceFile,
    deps_type=IngestorDeps,
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)


@ingestor_agent.tool
async def web_fetch(ctx: RunContext[IngestorDeps], url: str) -> dict:
    """Fetch a web page and extract its title, metadata, and text content."""
    try:
        resp = await ctx.deps.http_client.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        return extract_page_data(resp.text, url)
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        return {"error": str(exc), "url": url}


@ingestor_agent.tool
async def wayback_check(ctx: RunContext[IngestorDeps], url: str) -> dict:
    """Check Wayback Machine availability and optionally save the URL."""
    if ctx.deps.skip_wayback:
        return {"available": False, "archived_url": None, "skipped": True}
    result = await check_wayback(ctx.deps.http_client, url)
    if not result["available"]:
        archived_url = await save_to_wayback(ctx.deps.http_client, url)
        if archived_url:
            return {"available": True, "archived_url": archived_url}
    return result
