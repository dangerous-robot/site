"""archive.org TimeGate lookup and Save Page Now capture.

The ``check_archive_org_timegate`` helper queries archive.org's TimeGate
endpoint (``https://web.archive.org/web/{datetime}/{url}``) which returns
a 302 to the snapshot closest to the requested datetime, or 404 if no
snapshot exists. This is the CDX-indexed lookup, materially more reliable
than the legacy ``/wayback/available`` API (which has been observed to
return ``archived_snapshots: {}`` for URLs that have thousands of
snapshots).

Return shape: ``{available: bool, archived_url: str | None, error?: str}``.
``error`` is set on transport failures (``httpx.HTTPError`` family), 5xx,
and HTTP 429 after one retry; 404 and other statuses are silent misses
so the orchestrator drain doesn't mint a ``StepError`` for routine
"no snapshot" outcomes.

``save_to_wayback`` asks the Wayback Machine to capture the live URL when
TimeGate has no snapshot. ``find_or_save_archive`` runs the two in order and
is shared by the ``wayback_check`` tool and the lookup the pipeline runs in
code after each ingest; ``archive_with_time_limit`` adds that lookup's own
wall-clock limit.
"""

from __future__ import annotations

import asyncio
import datetime
import email.utils
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from common.timeouts import (
    RATE_LIMIT_RETRY_S,
    WAYBACK_CHECK_S,
    WAYBACK_SAVE_S,
    archive_lookup_budget_s,
)

logger = logging.getLogger(__name__)

_TIMEGATE_URL_TEMPLATE = "https://web.archive.org/web/{datetime}/{url}"
_SAVE_URL = "https://web.archive.org/save/"
_TIMEGATE_LABEL = "archive.org TimeGate check"
TIMEGATE_RATE_LIMITED = f"{_TIMEGATE_LABEL} failed (HTTP 429)"

# Statuses where the snapshot URL is in the ``Location`` header.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


async def _wait(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _retry_after_s(resp: httpx.Response) -> float:
    """Seconds to wait before retrying a 429, from ``Retry-After``, capped.

    archive.org can ask for minutes; one short wait keeps an ingest slot from
    stalling, and a second 429 is recorded as a failure instead.
    """
    header = resp.headers.get("retry-after", "").strip()
    try:
        seconds = float(header)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(header)
        except (TypeError, ValueError):
            return RATE_LIMIT_RETRY_S
        seconds = (when - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    return min(max(seconds, 0.0), RATE_LIMIT_RETRY_S)


async def _send_with_429_retry(
    send: Callable[[], Awaitable[httpx.Response]], label: str, url: str
) -> httpx.Response:
    resp = await send()
    if resp.status_code != 429:
        return resp
    wait_s = _retry_after_s(resp)
    logger.info("%s got HTTP 429 for %s; retrying once in %.1fs", label, url, wait_s)
    await _wait(wait_s)
    return await send()


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
    ``{available, archived_url, error?}``. The ``error`` key is set on
    transport failures (``httpx.HTTPError`` family), 5xx, and a 429 that
    persists after one retry. 404, redirect-without-Location, and
    unexpected 2xx are silent misses.
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    request_url = _TIMEGATE_URL_TEMPLATE.format(datetime=now, url=url)
    try:
        resp = await _send_with_429_retry(
            lambda: client.get(request_url, timeout=WAYBACK_CHECK_S, follow_redirects=False),
            _TIMEGATE_LABEL,
            url,
        )
    except httpx.HTTPError as exc:
        cls = type(exc).__name__
        logger.warning("%s failed (%s) for %s: %s", _TIMEGATE_LABEL, cls, url, exc)
        return {
            "available": False,
            "archived_url": None,
            "error": f"{_TIMEGATE_LABEL} failed ({cls}): {exc}",
        }

    if resp.status_code in _REDIRECT_STATUSES:
        location = resp.headers.get("location")
        if location:
            return {
                "available": True,
                "archived_url": _normalize_archive_url(location),
            }
        return {"available": False, "archived_url": None}

    if resp.status_code == 429 or 500 <= resp.status_code < 600:
        logger.warning("%s failed (HTTP %d) for %s", _TIMEGATE_LABEL, resp.status_code, url)
        return {
            "available": False,
            "archived_url": None,
            "error": f"{_TIMEGATE_LABEL} failed (HTTP {resp.status_code})",
        }

    return {"available": False, "archived_url": None}


async def save_to_wayback(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Request the Wayback Machine to save a URL. Best-effort.

    Returns ``{archived_url}`` on success, or ``{archived_url: None, error}``
    with the reason on failure. A 429 is retried once.
    """
    label = "Wayback save"
    try:
        resp = await _send_with_429_retry(
            lambda: client.post(f"{_SAVE_URL}{url}", timeout=WAYBACK_SAVE_S, follow_redirects=True),
            label,
            url,
        )
    except httpx.HTTPError as exc:
        cls = type(exc).__name__
        logger.warning("%s failed (%s) for %s: %s", label, cls, url, exc)
        return {"archived_url": None, "error": f"{label} failed ({cls}): {exc}"}

    if resp.status_code in (200, 302):
        location = resp.headers.get("content-location") or resp.headers.get("location")
        if location:
            archived = (
                location
                if location.startswith("http")
                else f"https://web.archive.org{location}"
            )
            return {"archived_url": _normalize_archive_url(archived)}
        return {"archived_url": f"https://web.archive.org/web/{url}"}
    logger.warning("%s returned status %d for %s", label, resp.status_code, url)
    return {"archived_url": None, "error": f"{label} failed (HTTP {resp.status_code})"}


@dataclass
class ArchiveLookup:
    archived_url: str | None = None
    # True when TimeGate found an existing snapshot (vs a fresh capture).
    from_timegate: bool = False
    errors: list[str] = field(default_factory=list)


async def find_or_save_archive(
    client: httpx.AsyncClient, url: str, *, allow_save: bool = True
) -> ArchiveLookup:
    """TimeGate first, then Save Page Now on a miss.

    No save follows a TimeGate 429: archive.org is already rate-limiting us.
    ``allow_save=False`` runs the TimeGate check only, so no capture is made.
    """
    lookup = ArchiveLookup()
    timegate = await check_archive_org_timegate(client, url)
    if timegate["available"]:
        lookup.archived_url = timegate["archived_url"]
        lookup.from_timegate = True
        return lookup
    if timegate.get("error"):
        lookup.errors.append(timegate["error"])
    if not allow_save or timegate.get("error") == TIMEGATE_RATE_LIMITED:
        return lookup
    saved = await save_to_wayback(client, url)
    lookup.archived_url = saved["archived_url"]
    if saved.get("error"):
        lookup.errors.append(saved["error"])
    return lookup


async def archive_with_time_limit(
    client: httpx.AsyncClient, url: str, *, allow_save: bool = True
) -> ArchiveLookup:
    """``find_or_save_archive`` under ``archive_lookup_budget_s()``; a timeout is an error."""
    limit = archive_lookup_budget_s()
    try:
        return await asyncio.wait_for(
            find_or_save_archive(client, url, allow_save=allow_save), timeout=limit
        )
    except asyncio.TimeoutError:
        logger.warning("archive.org lookup timed out after %.0fs for %s", limit, url)
        return ArchiveLookup(errors=[f"archive.org lookup timed out after {limit:.0f}s"])
