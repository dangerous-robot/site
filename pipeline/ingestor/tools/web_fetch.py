"""Fetch a web page and extract structured metadata."""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_STRIP_TAGS = {"nav", "footer", "script", "style", "header", "aside"}
_MAX_TEXT_LENGTH = 50_000

# HTTP status codes that indicate a permanent/terminal fetch failure.
# Retrying, following redirects, or checking Wayback will not help:
# - 401: auth required (origin wants credentials)
# - 402: payment required (paywall)
# - 403: forbidden (bot block / geo / Cloudflare)
# - 404: resource does not exist at this URL (researcher found a dead link)
# - 451: legally unavailable
TERMINAL_STATUS_CODES = frozenset({401, 402, 403, 404, 451})


class TerminalFetchError(Exception):
    """Raised when a fetch hits a terminal HTTP status (no point retrying).

    Not an httpx.HTTPError subclass on purpose: the ingestor agent's
    ``except httpx.HTTPError`` branch must NOT swallow this. It is allowed
    to propagate out of the agent run so the orchestrator can record a
    skipped source and move on without burning the agent retry budget
    or calling ``wayback_check``.
    """

    def __init__(self, url: str, status_code: int, reason: str) -> None:
        self.url = url
        self.status_code = status_code
        self.reason = reason
        super().__init__(
            f"Terminal fetch failure: {status_code} {reason} for {url}"
        )


def extract_page_data(html: str, url: str) -> dict[str, Any]:
    """Parse HTML and extract title, meta, and text content.

    Returns a dict with keys: title, description, author, published_time,
    text, url.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strip noisy elements
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    title = _extract_title(soup)
    description = _extract_meta(soup, "description")
    author = _extract_meta(soup, "author")
    published_time = (
        _extract_meta(soup, "article:published_time")
        or _extract_meta(soup, "datePublished")
    )

    text = soup.get_text(separator="\n", strip=True)
    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH] + "\n[truncated]"

    return {
        "title": title,
        "description": description,
        "author": author,
        "published_time": published_time,
        "text": text,
        "url": url,
    }


def _extract_title(soup: BeautifulSoup) -> str | None:
    """Extract title from OG tag or <title>."""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


def _extract_meta(soup: BeautifulSoup, name: str) -> str | None:
    """Extract a meta tag value by name or property."""
    tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    tag = soup.find("meta", attrs={"property": name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None
