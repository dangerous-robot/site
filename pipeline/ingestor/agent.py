"""PydanticAI agent definition for the Ingestor."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from pydantic_ai import Agent, RunContext

from common.instructions import load_instructions
from ingestor.models import SourceFile
from ingestor.tools.wayback import check_wayback, save_to_wayback
from ingestor.tools.web_fetch import extract_page_data

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_instructions(Path(__file__).resolve().parent)


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
    system_prompt=_SYSTEM_PROMPT,
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
