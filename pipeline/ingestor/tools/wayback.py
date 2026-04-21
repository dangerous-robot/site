"""Wayback Machine availability check and save API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from common.timeouts import WAYBACK_CHECK_S, WAYBACK_SAVE_S

logger = logging.getLogger(__name__)

_AVAILABILITY_URL = "https://archive.org/wayback/available"
_SAVE_URL = "https://web.archive.org/save/"


async def check_wayback(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Check if a URL is available in the Wayback Machine.

    Returns a dict with 'available' (bool) and 'archived_url' (str or None).
    """
    try:
        resp = await client.get(
            _AVAILABILITY_URL,
            params={"url": url},
            timeout=WAYBACK_CHECK_S,
        )
        resp.raise_for_status()
        data = resp.json()
        snapshot = data.get("archived_snapshots", {}).get("closest")
        if snapshot and snapshot.get("available"):
            return {
                "available": True,
                "archived_url": snapshot.get("url"),
            }
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Wayback availability check failed for %s: %s", url, exc)

    return {"available": False, "archived_url": None}


async def save_to_wayback(client: httpx.AsyncClient, url: str) -> str | None:
    """Request the Wayback Machine to save a URL. Best-effort.

    Returns the archived URL on success, None on failure.
    """
    try:
        resp = await client.post(
            f"{_SAVE_URL}{url}",
            timeout=WAYBACK_SAVE_S,
            follow_redirects=True,
        )
        if resp.status_code in (200, 302):
            location = resp.headers.get("content-location") or resp.headers.get(
                "location"
            )
            if location:
                archived = (
                    location
                    if location.startswith("http")
                    else f"https://web.archive.org{location}"
                )
                return archived
            # Fallback: construct URL from the save endpoint
            return f"https://web.archive.org/web/{url}"
        logger.warning(
            "Wayback save returned status %d for %s", resp.status_code, url
        )
    except httpx.HTTPError as exc:
        logger.warning("Wayback save failed for %s: %s", url, exc)

    return None
