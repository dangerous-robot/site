"""Wayback Machine availability check, save API, and Memento fallback.

The ``check_wayback`` and ``check_memento`` helpers share a return shape:
``{available: bool, archived_url: str | None, error: str | None}``. The
``error`` key is set **only** for transport failures (``httpx.HTTPError``
family: timeouts, connection errors, 5xx via ``raise_for_status``). A
malformed-JSON response or an HTTP 200 with an empty ``mementos: {}``
payload is treated as a silent "no snapshot" — ``error`` stays absent so
the orchestrator drain doesn't mint a ``StepError`` for it.

Memento Time Travel (``timetravel.mementoweb.org``) is invoked by the
``wayback_check`` tool only when the archive.org leg returns no snapshot.
It aggregates across non-archive.org archives; ``mementos.closest.uri``
is the recovered URL.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import httpx

from common.timeouts import WAYBACK_CHECK_S, WAYBACK_SAVE_S
from common.throttle import acquire as throttle_acquire
from common.throttle import is_registered as throttle_is_registered
from common.throttle import register as throttle_register

logger = logging.getLogger(__name__)

_AVAILABILITY_URL = "https://archive.org/wayback/available"
_SAVE_URL = "https://web.archive.org/save/"
_MEMENTO_URL = "http://timetravel.mementoweb.org/api/json/{datetime}/{url}"

# Memento Time Travel aggregator. 5 req/s leaves headroom under
# Memento's documented ~10 rps ceiling and avoids serializing the
# ingestor's concurrent-URL hot path behind the bucket when many URLs
# fail and need the fallback.
_MEMENTO_RATE_PER_SEC = 5.0
_MEMENTO_BURST = 5.0


def _ensure_memento_throttle_registered() -> None:
    """Register the ``memento`` bucket on the module-level throttle.

    Idempotent for matching params; safe to call from concurrent tasks.
    Tests that ``reset()`` the throttle re-register on the next call.
    """
    if not throttle_is_registered("memento"):
        throttle_register(
            "memento",
            rate_per_sec=_MEMENTO_RATE_PER_SEC,
            burst=_MEMENTO_BURST,
        )


# Register at import so concurrent first calls don't race the check.
_ensure_memento_throttle_registered()


async def _fetch_archive_json(
    client: httpx.AsyncClient,
    *,
    request_url: str,
    label: str,
    target_url: str,
    params: dict | None = None,
) -> tuple[dict | None, str | None]:
    """GET ``request_url`` and return ``(parsed JSON, transport error)``.

    Returns ``(data, None)`` on success, ``(None, error)`` on transport
    failures (``httpx.HTTPError`` family — timeouts, connection errors,
    5xx), and ``(None, None)`` on malformed JSON. The malformed case is
    deliberately silent so the orchestrator doesn't mint a ``StepError``
    for upstream APIs that occasionally serve empty bodies.
    """
    try:
        resp = await client.get(request_url, params=params, timeout=WAYBACK_CHECK_S)
        resp.raise_for_status()
        return resp.json(), None
    except httpx.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", "?")
        logger.warning("%s failed (HTTP %s) for %s", label, status, target_url)
        return None, f"{label} failed (HTTP {status}): {exc}"
    except ValueError as exc:
        logger.warning("%s returned malformed payload for %s: %s", label, target_url, exc)
        return None, None


async def check_wayback(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Check if a URL is available in the Wayback Machine.

    Returns a dict with ``available`` (bool), ``archived_url`` (str or
    ``None``), and an optional ``error`` key set to a short string when
    the call failed at the transport layer (``httpx.HTTPError`` family —
    timeout, connection error, 5xx). Malformed JSON / missing keys are
    silent ("no snapshot"); ``error`` stays absent so the orchestrator
    drain doesn't mint a ``wayback_unavailable`` ``StepError`` for them.
    """
    data, error = await _fetch_archive_json(
        client,
        request_url=_AVAILABILITY_URL,
        label="archive.org availability check",
        target_url=url,
        params={"url": url},
    )
    if error:
        return {"available": False, "archived_url": None, "error": error}
    if data:
        snapshot = data.get("archived_snapshots", {}).get("closest")
        if snapshot and snapshot.get("available"):
            return {"available": True, "archived_url": snapshot.get("url")}
    return {"available": False, "archived_url": None}


async def check_memento(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Check the Memento Time Travel aggregator for a snapshot of ``url``.

    Asks ``timetravel.mementoweb.org`` for the closest snapshot to "now"
    across non-archive.org archives. Returns the same shape as
    ``check_wayback``: ``{available, archived_url, error?}``. Throttled
    through the module-level ``'memento'`` bucket.
    """
    _ensure_memento_throttle_registered()
    await throttle_acquire("memento")

    now = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    request_url = _MEMENTO_URL.format(datetime=now, url=url)
    data, error = await _fetch_archive_json(
        client,
        request_url=request_url,
        label="Memento aggregator check",
        target_url=url,
    )
    if error:
        return {"available": False, "archived_url": None, "error": error}
    if data:
        closest = (data.get("mementos") or {}).get("closest") or {}
        archived = closest.get("uri")
        # ``uri`` is documented as a list of mirror URIs; some deployments
        # return a single string. Accept either.
        if isinstance(archived, list):
            archived = archived[0] if archived else None
        if archived:
            return {"available": True, "archived_url": archived}
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
        status = getattr(getattr(exc, "response", None), "status_code", "?")
        logger.warning("Wayback save failed (HTTP %s) for %s", status, url)

    return None
