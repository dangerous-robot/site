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

TimeGate answers with the nearest capture whatever it holds: a replay of a
404 page, a captured redirect, or a capture of a differently cased URL
(Wayback matches URLs ignoring case and trailing slash). So no link is
recorded until ``check_capture`` has seen archive.org replay it with HTTP
200 for the same page. When the TimeGate capture fails that check,
``latest_ok_capture`` asks the CDX index for the newest 200 capture of the
URL instead.

``save_to_wayback`` asks the Wayback Machine to capture the live URL when
no good capture exists, or when the one found is older than the caller
allows; the saved capture is checked the same way. ``find_or_save_archive``
runs these in order and is shared by the ``wayback_check`` tool, the lookup
the pipeline runs in code after each ingest, and ``dr wayback-backfill``;
``archive_with_time_limit`` adds that lookup's own wall-clock limit.
"""

from __future__ import annotations

import asyncio
import datetime
import email.utils
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin

import httpx

from common.canonical_url import same_page_any_scheme
from common.timeouts import (
    RATE_LIMIT_RETRY_S,
    WAYBACK_CDX_S,
    WAYBACK_CHECK_S,
    WAYBACK_SAVE_S,
    WAYBACK_VERIFY_S,
    archive_lookup_budget_s,
)

logger = logging.getLogger(__name__)

_TIMEGATE_URL_TEMPLATE = "https://web.archive.org/web/{datetime}/{url}"
_SAVE_URL = "https://web.archive.org/save/"
_TIMEGATE_LABEL = "archive.org TimeGate check"
TIMEGATE_RATE_LIMITED = f"{_TIMEGATE_LABEL} failed (HTTP 429)"
_CDX_URL = "https://web.archive.org/cdx/search/cdx"
_CDX_LABEL = "archive.org CDX lookup"
_CDX_RATE_LIMITED = f"{_CDX_LABEL} failed (HTTP 429)"
_REPLAY_LABEL = "archive.org replay check"
# A captured redirect chain longer than this is treated as a different page.
_MAX_REPLAY_REQUESTS = 3
# A refresh is worth a Save Page Now request once a capture is this old: a
# proposed value, not one measured against how fast cited pages change.
SNAPSHOT_MAX_AGE = datetime.timedelta(days=90)

# Statuses where the snapshot URL is in the ``Location`` header.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
# A capture's link carries its 14-digit timestamp; ``/web/<url>`` does not
# name a capture.
_DATED_SNAPSHOT = re.compile(r"https://web\.archive\.org/web/\d{14}[a-z_]*/.+")
_SNAPSHOT_PARTS = re.compile(r"https://web\.archive\.org/web/(\d{14})[a-z_]*/(.+)")


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
        if when.tzinfo is None:  # "-0000" parses as naive; HTTP dates are UTC
            when = when.replace(tzinfo=datetime.timezone.utc)
        seconds = (when - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if not math.isfinite(seconds):
        return RATE_LIMIT_RETRY_S
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


def _dated_snapshot(location: str | None) -> str | None:
    """``location`` as an absolute snapshot link, or None unless it names a dated capture."""
    if not location:
        return None
    if location.startswith("/"):
        location = f"https://web.archive.org{location}"
    location = _normalize_archive_url(location)
    return location if _DATED_SNAPSHOT.match(location) else None


async def save_to_wayback(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Request the Wayback Machine to save a URL. Best-effort.

    Returns ``{archived_url}`` on success, or ``{archived_url: None, error}``
    with the reason on failure. A 429 is retried once.

    Success needs a dated snapshot link in ``Location`` or
    ``Content-Location``. An anonymous POST was seen to answer 200 with
    neither and make no capture, while a GET answers 302 to the new snapshot;
    the redirect is not followed, since the link is all that is needed.
    """
    label = "Wayback save"
    try:
        resp = await _send_with_429_retry(
            lambda: client.get(f"{_SAVE_URL}{url}", timeout=WAYBACK_SAVE_S, follow_redirects=False),
            label,
            url,
        )
    except httpx.HTTPError as exc:
        cls = type(exc).__name__
        logger.warning("%s failed (%s) for %s: %s", label, cls, url, exc)
        return {"archived_url": None, "error": f"{label} failed ({cls}): {exc}"}

    if resp.status_code == 200 or resp.status_code in _REDIRECT_STATUSES:
        for header in ("location", "content-location"):
            snapshot = _dated_snapshot(resp.headers.get(header))
            if snapshot:
                return {"archived_url": snapshot}
        logger.warning("%s returned no snapshot (HTTP %d) for %s", label, resp.status_code, url)
        return {
            "archived_url": None,
            "error": f"{label} returned no snapshot (HTTP {resp.status_code})",
        }
    logger.warning("%s returned status %d for %s", label, resp.status_code, url)
    return {"archived_url": None, "error": f"{label} failed (HTTP {resp.status_code})"}


def _snapshot_parts(link: str | None) -> tuple[str, str] | None:
    """``(timestamp, original URL)`` of a dated capture link, or None."""
    dated = _dated_snapshot(link)
    if dated is None:
        return None
    match = _SNAPSHOT_PARTS.match(dated)
    return (match.group(1), match.group(2)) if match else None


def _plain_link(timestamp: str, original: str) -> str:
    return f"https://web.archive.org/web/{timestamp}/{original}"


@dataclass
class CaptureCheck:
    ok: bool
    # The plain (no ``id_``) link to record; set only when ``ok``.
    link: str | None = None
    reason: str | None = None
    # archive.org failed to answer, so nothing is known about the capture.
    unverified: bool = False
    # The captured status when the capture is an error page.
    status: int | None = None


def _bad(reason: str, status: int | None = None) -> CaptureCheck:
    return CaptureCheck(ok=False, reason=reason, status=status)


def _unverified(reason: str) -> CaptureCheck:
    return CaptureCheck(ok=False, reason=reason, unverified=True)


async def _follow_replay(
    client: httpx.AsyncClient, timestamp: str, original: str, pages: tuple[str, ...]
) -> CaptureCheck:
    first = _plain_link(timestamp, original)
    for _ in range(_MAX_REPLAY_REQUESTS):
        replay = f"https://web.archive.org/web/{timestamp}id_/{original}"
        try:
            resp = await _send_with_429_retry(
                lambda: client.head(replay, follow_redirects=False), _REPLAY_LABEL, replay
            )
        except httpx.HTTPError as exc:
            return _unverified(f"{_REPLAY_LABEL} failed ({type(exc).__name__}): {exc}")
        status = resp.status_code
        # Memento-Datetime marks a replay, whose status is the captured one;
        # without it the status is archive.org's own.
        replayed = "memento-datetime" in resp.headers
        if status in _REDIRECT_STATUSES:
            target = resp.headers.get("location", "")
            parts = _snapshot_parts(urljoin(replay, target)) if target else None
            if parts is None:
                return _bad(f"archive.org capture redirects to {target or 'nowhere'}")
            timestamp, original = parts
            if not any(same_page_any_scheme(original, page) for page in pages):
                return _bad(f"archive.org capture redirects to {original}")
            continue
        if not replayed or status == 429:
            # archive.org's own answer, e.g. a capture saved moments ago that
            # does not replay yet: nothing is known about the capture.
            return _unverified(f"{_REPLAY_LABEL} failed (HTTP {status})")
        if status == 200:
            return CaptureCheck(ok=True, link=first)
        if status >= 400:
            return _bad(f"archive.org capture is an error page (HTTP {status})", status)
        return _bad(f"archive.org capture is not a page (HTTP {status})")
    return _bad(f"archive.org capture redirects more than {_MAX_REPLAY_REQUESTS - 1} times")


async def check_capture(
    client: httpx.AsyncClient, link: str, url: str, *, also_same_as: str | None = None
) -> CaptureCheck:
    """Whether ``link`` is a capture of ``url`` that archive.org replays with HTTP 200.

    The capture's own URL must be ``url`` (scheme, default port and a
    trailing-dot host aside; path case counts). A captured redirect is
    followed only while each hop stays on ``url`` or ``also_same_as`` (where
    the live fetch ended), and the first link is recorded, since it replays
    through. Transport errors, timeouts, a repeated 429 and archive.org's own
    5xx leave the capture unverified rather than bad.
    """
    parts = _snapshot_parts(link)
    if parts is None:
        return _bad(f"not a dated archive.org capture link ({link})")
    timestamp, original = parts
    if not same_page_any_scheme(original, url):
        return _bad(f"capture is of a different URL ({original})")
    pages = (url,) if also_same_as is None else (url, also_same_as)
    try:
        return await asyncio.wait_for(
            _follow_replay(client, timestamp, original, pages), timeout=WAYBACK_VERIFY_S
        )
    except asyncio.TimeoutError:
        return _unverified(f"{_REPLAY_LABEL} timed out after {WAYBACK_VERIFY_S:.0f}s")


async def latest_ok_capture(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """The newest capture of ``url`` the CDX index lists with HTTP 200.

    Returns ``{archived_url}``, with ``error`` on transport failures,
    unreadable answers, 5xx and a 429 after one retry. CDX rows carry the
    captured status, so no replay check follows. The index matches URLs
    loosely, so rows are filtered to the same page here.
    """
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,statuscode",
        "filter": "statuscode:200",
        "limit": "-25",
        "fastLatest": "true",
    }
    try:
        resp = await _send_with_429_retry(
            lambda: client.get(_CDX_URL, params=params, timeout=WAYBACK_CDX_S),
            _CDX_LABEL,
            url,
        )
    except httpx.HTTPError as exc:
        cls = type(exc).__name__
        logger.warning("%s failed (%s) for %s: %s", _CDX_LABEL, cls, url, exc)
        return {"archived_url": None, "error": f"{_CDX_LABEL} failed ({cls}): {exc}"}
    if resp.status_code == 429 or 500 <= resp.status_code < 600:
        logger.warning("%s failed (HTTP %d) for %s", _CDX_LABEL, resp.status_code, url)
        return {"archived_url": None, "error": f"{_CDX_LABEL} failed (HTTP {resp.status_code})"}
    if resp.status_code != 200:
        return {"archived_url": None}
    try:
        rows = resp.json()
    except ValueError:
        return {"archived_url": None, "error": f"{_CDX_LABEL} returned an unreadable answer"}
    if not isinstance(rows, list):
        return {"archived_url": None, "error": f"{_CDX_LABEL} returned an unreadable answer"}
    good = [
        (row[0], row[1])
        for row in rows[1:]
        if isinstance(row, list)
        and len(row) >= 3
        and str(row[2]) == "200"
        and re.fullmatch(r"\d{14}", str(row[0]))
        and same_page_any_scheme(str(row[1]), url)
    ]
    if not good:
        return {"archived_url": None}
    timestamp, original = max(good)
    return {"archived_url": _dated_snapshot(_plain_link(timestamp, original))}


async def _save_and_check(
    client: httpx.AsyncClient, url: str, also_same_as: str | None
) -> tuple[str | None, str | None]:
    """Save Page Now, then the same capture check; ``(link, error)``."""
    saved = await save_to_wayback(client, url)
    if not saved["archived_url"]:
        return None, saved.get("error")
    check = await check_capture(client, saved["archived_url"], url, also_same_as=also_same_as)
    if check.ok:
        return check.link, None
    if check.unverified:
        return None, f"could not verify the Save Page Now capture ({check.reason})"
    if check.status is not None:
        return None, f"Save Page Now captured an error page (HTTP {check.status})"
    return None, f"Save Page Now capture rejected: {check.reason}"


def _is_stale(
    link: str, max_age: datetime.timedelta | None, not_before: datetime.date | None
) -> bool:
    parts = _snapshot_parts(link)
    if parts is None:
        return False
    captured = datetime.datetime.strptime(parts[0], "%Y%m%d%H%M%S").replace(
        tzinfo=datetime.timezone.utc
    )
    if max_age is not None and captured < datetime.datetime.now(datetime.timezone.utc) - max_age:
        return True
    return not_before is not None and captured.date() < not_before


@dataclass
class ArchiveLookup:
    archived_url: str | None = None
    # True when an existing capture was recorded (vs a fresh Save Page Now one).
    found_existing: bool = False
    errors: list[str] = field(default_factory=list)


async def find_or_save_archive(
    client: httpx.AsyncClient,
    url: str,
    *,
    allow_save: bool = True,
    max_age: datetime.timedelta | None = None,
    not_before: datetime.date | None = None,
    also_same_as: str | None = None,
) -> ArchiveLookup:
    """Record a capture of ``url`` that replays with HTTP 200, saving one when needed.

    TimeGate's capture is checked first; if it fails the check, the CDX
    index's newest 200 capture is used, and the failed capture is never
    recorded. With no good capture, Save Page Now is asked for one, which
    is checked too. A good capture older than ``max_age`` or dated before
    ``not_before`` is replaced by a fresh checked save when one succeeds,
    and kept otherwise. No save follows a 429 from TimeGate or CDX:
    archive.org is already rate-limiting us. ``allow_save=False`` makes no
    capture. ``also_same_as`` is where the live fetch ended, so a captured
    redirect to it still counts as the page.
    """
    lookup = ArchiveLookup()
    rate_limited = False
    candidate: str | None = None
    # Why the TimeGate capture was not used; reported only if no link results.
    rejected: list[str] = []
    timegate = await check_archive_org_timegate(client, url)
    if timegate.get("error"):
        lookup.errors.append(timegate["error"])
        rate_limited = timegate["error"] == TIMEGATE_RATE_LIMITED
    elif timegate["available"]:
        check = await check_capture(
            client, timegate["archived_url"], url, also_same_as=also_same_as
        )
        if check.ok:
            candidate = check.link
        else:
            logger.info("TimeGate capture %s rejected: %s", timegate["archived_url"], check.reason)
            cdx = await latest_ok_capture(client, url)
            candidate = cdx["archived_url"]
            if candidate is None:
                rejected.append(check.reason or "archive.org capture failed its check")
                if cdx.get("error"):
                    rejected.append(cdx["error"])
                    rate_limited = cdx["error"] == _CDX_RATE_LIMITED
    can_save = allow_save and not rate_limited

    if candidate is not None:
        lookup.archived_url = candidate
        lookup.found_existing = True
        if can_save and _is_stale(candidate, max_age, not_before):
            fresh, error = await _save_and_check(client, url, also_same_as)
            if fresh:
                lookup.archived_url = fresh
                lookup.found_existing = False
            else:
                logger.warning(
                    "kept capture %s of %s: the refresh save failed (%s)", candidate, url, error
                )
        return lookup

    error = None
    if can_save:
        lookup.archived_url, error = await _save_and_check(client, url, also_same_as)
    if lookup.archived_url is None:
        lookup.errors.extend(rejected)
        if error:
            lookup.errors.append(error)
    return lookup


async def archive_with_time_limit(
    client: httpx.AsyncClient,
    url: str,
    *,
    allow_save: bool = True,
    max_age: datetime.timedelta | None = None,
    not_before: datetime.date | None = None,
    also_same_as: str | None = None,
) -> ArchiveLookup:
    """``find_or_save_archive`` under ``archive_lookup_budget_s()``; a timeout is an error."""
    limit = archive_lookup_budget_s()
    try:
        return await asyncio.wait_for(
            find_or_save_archive(
                client,
                url,
                allow_save=allow_save,
                max_age=max_age,
                not_before=not_before,
                also_same_as=also_same_as,
            ),
            timeout=limit,
        )
    except asyncio.TimeoutError:
        logger.warning("archive.org lookup timed out after %.0fs for %s", limit, url)
        return ArchiveLookup(errors=[f"archive.org lookup timed out after {limit:.0f}s"])
