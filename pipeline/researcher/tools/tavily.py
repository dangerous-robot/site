"""Tavily Search client used by the decomposed researcher.

Selectable as the search backend via ``RESEARCH_SEARCH_BACKEND=tavily``;
default remains Brave. See
``docs/plans/source-pool-expansion-tier1-search-backend.md``.

Auth: ``TAVILY_API_KEY`` (sent as ``Authorization: Bearer ...``).
Endpoint: ``POST https://api.tavily.com/search`` with a JSON body.
On a 429 we honour ``Retry-After`` once, mirroring the Brave behaviour
in ``researcher/agent.py``; a second 429 raises so the caller can map
it to a ``StepError(error_type="tavily_rate_limited")``.

Throttle: a single token-bucket named ``"tavily"`` is registered at
import time (idempotent). 5 req/s is conservative for the free
"research" tier; bump if/when we move to a paid tier with a documented
budget.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from common.throttle import acquire as throttle_acquire
from common.throttle import is_registered as throttle_is_registered
from common.throttle import register as throttle_register

logger = logging.getLogger(__name__)

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_TAVILY_RATE_LIMIT_RETRY_DELAY_S = 30.0

# 5 req/s steady-state, burst of 5. Conservative for the free research
# tier (no published per-second cap; this leaves headroom for ad-hoc
# usage outside the pipeline). Revisit on tier change.
_TAVILY_RATE_PER_SEC = 5.0
_TAVILY_BURST = 5.0


class TavilyRateLimitError(RuntimeError):
    """Raised when the Tavily endpoint returns 429 after a single retry.

    The dispatcher in ``researcher/decomposed.py`` catches this and emits a
    ``StepError(error_type="tavily_rate_limited")`` per the StepError vocab
    in ``orchestrator/checkpoints.py``.
    """


def _ensure_throttle_registered() -> None:
    """Register the ``tavily`` bucket on the module-level throttle.

    Idempotent for matching params; safe to call from concurrent tasks.
    Tests that ``reset()`` the throttle re-register on the next call.
    """
    if not throttle_is_registered("tavily"):
        throttle_register(
            "tavily",
            rate_per_sec=_TAVILY_RATE_PER_SEC,
            burst=_TAVILY_BURST,
        )


# Register at import so concurrent first calls under asyncio.gather
# don't race the registration check.
_ensure_throttle_registered()


async def search_tavily(
    client: httpx.AsyncClient, query: str, max_results: int = 10
) -> list[dict]:
    """Search using the Tavily Search API.

    Requires ``TAVILY_API_KEY`` in the environment. Returns a list of
    dicts shaped ``{url, title, snippet, raw_content}``; Tavily's
    per-result ``content`` field maps onto ``snippet`` (parallel to
    Brave's ``description``), and ``raw_content`` carries the full
    pre-extracted body when Tavily provided one (Markdown/plain text
    per the verification call). Empty/missing ``raw_content`` is
    returned as an empty string so the ingestor short-circuit falls
    through to a live fetch.

    On a single 429, sleeps per ``Retry-After`` (or a 30 s default) and
    retries once. A second 429 raises ``TavilyRateLimitError`` so the
    caller can fall back to Brave for that query and emit
    ``StepError(error_type="tavily_rate_limited")``.
    """
    logger.info("Tavily search: %s", query)
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")

    _ensure_throttle_registered()

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        # Ask Tavily for the full extracted body so the ingestor can
        # skip an httpx fetch (and the publisher's Cloudflare shield)
        # when raw_content is present. See docs/plans/ingestor-tavily-prefetch.md.
        "include_raw_content": True,
    }

    async def _fetch() -> httpx.Response:
        await throttle_acquire("tavily")
        return await client.post(
            _TAVILY_SEARCH_URL,
            json=body,
            headers=headers,
            timeout=15.0,
        )

    resp = await _fetch()
    if resp.status_code == 429:
        header_val = resp.headers.get("retry-after")
        try:
            wait = float(header_val) if header_val else _TAVILY_RATE_LIMIT_RETRY_DELAY_S
        except ValueError:
            wait = _TAVILY_RATE_LIMIT_RETRY_DELAY_S
        logger.warning("Tavily 429 rate limit; retrying in %.0fs", wait)
        await asyncio.sleep(wait)
        resp = await _fetch()
        if resp.status_code == 429:
            raise TavilyRateLimitError(
                f"Tavily rate-limited twice for query {query!r}"
            )
    resp.raise_for_status()

    data = resp.json()
    results = data.get("results") or []
    out: list[dict] = []
    for item in results:
        url = item.get("url") or ""
        if not url:
            continue
        out.append(
            {
                "url": url,
                "title": item.get("title") or "",
                # Map Tavily's `content` onto `snippet` to match the
                # shape returned by `search_brave`.
                "snippet": item.get("content") or "",
                # Full pre-extracted body when Tavily supplied it;
                # empty string when it didn't (some publishers block
                # Tavily's crawler too).
                "raw_content": item.get("raw_content") or "",
            }
        )
    return out
