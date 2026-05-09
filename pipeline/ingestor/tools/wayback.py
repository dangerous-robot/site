"""archive.org TimeGate lookup and Save Page Now capture.

The ``check_archive_org_timegate`` helper queries archive.org's TimeGate
endpoint (``https://web.archive.org/web/{datetime}/{url}``) which returns
a 302 to the snapshot closest to the requested datetime, or 404 if no
snapshot exists. This is the CDX-indexed lookup, materially more reliable
than the legacy ``/wayback/available`` API (which has been observed to
return ``archived_snapshots: {}`` for URLs that have thousands of
snapshots).

Return shape: ``{available: bool, archived_url: str | None, error?: str}``.
``error`` is set only on transport failures (``httpx.HTTPError`` family)
or 5xx; 404 and unexpected statuses are silent misses so the orchestrator
drain doesn't mint a ``StepError`` for routine "no snapshot" outcomes.

``save_to_wayback`` is the second-and-final fallback in the
``wayback_check`` waterfall: when TimeGate has no snapshot, it asks the
Wayback Machine to capture the live URL.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import httpx

from common.timeouts import WAYBACK_CHECK_S, WAYBACK_SAVE_S

logger = logging.getLogger(__name__)

_TIMEGATE_URL_TEMPLATE = "https://web.archive.org/web/{datetime}/{url}"
_SAVE_URL = "https://web.archive.org/save/"

# Statuses where the snapshot URL is in the ``Location`` header.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _normalize_archive_url(url: str) -> str:
    # Validation requires ``https://web.archive.org`` (see validation.py:
    # _check_archived_url_domain). TimeGate occasionally returns ``http://``
    # in the Location header; canonicalize the scheme so committed sidecars
    # never carry plaintext archive URLs.
    if url.startswith("http://web.archive.org"):
        return "https://" + url[len("http://"):]
    return url


async def check_archive_org_timegate(
    client: httpx.AsyncClient, url: str
) -> dict[str, Any]:
    """Query archive.org's TimeGate for the snapshot closest to "now".

    Same return shape as the rest of this module:
    ``{available, archived_url, error?}``. The ``error`` key is set only
    on transport failures (``httpx.HTTPError`` family) and 5xx. 404,
    redirect-without-Location, and unexpected 2xx are silent misses.
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    request_url = _TIMEGATE_URL_TEMPLATE.format(datetime=now, url=url)
    label = "archive.org TimeGate check"
    try:
        resp = await client.get(
            request_url, timeout=WAYBACK_CHECK_S, follow_redirects=False
        )
    except httpx.HTTPError as exc:
        cls = type(exc).__name__
        logger.warning("%s failed (%s) for %s: %s", label, cls, url, exc)
        return {
            "available": False,
            "archived_url": None,
            "error": f"{label} failed ({cls}): {exc}",
        }

    if resp.status_code in _REDIRECT_STATUSES:
        location = resp.headers.get("location")
        if location:
            return {
                "available": True,
                "archived_url": _normalize_archive_url(location),
            }
        return {"available": False, "archived_url": None}

    if 500 <= resp.status_code < 600:
        logger.warning("%s failed (HTTP %d) for %s", label, resp.status_code, url)
        return {
            "available": False,
            "archived_url": None,
            "error": f"{label} failed (HTTP {resp.status_code})",
        }

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
                return _normalize_archive_url(archived)
            return f"https://web.archive.org/web/{url}"
        logger.warning(
            "Wayback save returned status %d for %s", resp.status_code, url
        )
    except httpx.HTTPError as exc:
        cls = type(exc).__name__
        logger.warning("Wayback save failed (%s) for %s: %s", cls, url, exc)

    return None
