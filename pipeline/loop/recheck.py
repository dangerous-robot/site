"""A recheck's look at the cached sources older than the claim's cadence."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import httpx

from common.frontmatter import parse_frontmatter
from common.timeouts import default_httpx_timeout
from ingestor.tools.wayback import check_capture
from ingestor.tools.web_fetch import extract_page_data
from ingestor.validation import check_quotes
from loop.spec import VerifyConfig

logger = logging.getLogger(__name__)


def _accessed_on(value: object) -> datetime.date | None:
    """A source file's ``accessed_date``, written as a quoted string or a YAML date."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


async def _recheck_cached_sources(
    client: httpx.AsyncClient,
    cached_sources: list[tuple[str, str, dict]],
    prefetched_bodies: dict[str, str],
    cfg: VerifyConfig,
    repo_root: Path,
    today: datetime.date | None = None,
) -> dict[str, dict]:
    """Re-check each cached source older than ``cfg.refetch_cached_older_than_days``; source id -> record.

    Check-only: nothing is ingested and the source file is never rewritten.
    The page text is the search's ``raw_content`` for the URL when it has
    one, else one GET; no model is called. The source file's key quotes are
    checked against that text, and its ``archived_url`` with ``check_capture``
    (never a save), which also accepts a capture redirecting to where the
    GET ended. A failed fetch records ``refetched: false`` and the
    reason, and the quotes stay unchecked. A source whose ``accessed_date``
    is missing or unreadable counts as old.
    """
    days = cfg.refetch_cached_older_than_days
    if days is None:
        return {}
    today = today or datetime.date.today()
    cutoff = today - datetime.timedelta(days=days)
    records: dict[str, dict] = {}
    for url, sid, _sd in cached_sources:
        if sid in records:
            continue
        try:
            fm, _ = parse_frontmatter((repo_root / "research" / "sources" / f"{sid}.md").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Could not read cached source %s for its recheck: %s", sid, exc)
            continue
        accessed = _accessed_on(fm.get("accessed_date"))
        if accessed is not None and accessed >= cutoff:
            continue
        stored_url = str(fm.get("url") or url)
        text = prefetched_bodies.get(url) or prefetched_bodies.get(stored_url)
        reason: str | None = None
        # Where the live fetch ended, so a capture that redirects there still
        # counts as the page, as `dr recheck --sources` checks it.
        final_url: str | None = None
        if text is None:
            try:
                resp = await client.get(stored_url, follow_redirects=True, timeout=default_httpx_timeout())
                if resp.is_success:
                    final_url = str(resp.url)
                content_type = resp.headers.get("content-type", "text/html").lower()
                if resp.is_success and "html" not in content_type and not content_type.startswith("text/"):
                    # A PDF or other binary page would mark every quote not found;
                    # the quotes stay unchecked instead, as dr recheck --sources does.
                    reason = f"not an HTML page ({content_type.split(';')[0]})"
                elif resp.is_success:
                    text = extract_page_data(resp.text, str(resp.url))["text"]
                else:
                    reason = f"HTTP {resp.status_code}"
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                reason = f"{type(exc).__name__}: {exc}"
        quotes: list[dict] = []
        if text is not None:
            key_quotes = [q for q in fm.get("key_quotes") or [] if isinstance(q, str)]
            for check in check_quotes(key_quotes, text, with_passage=True):
                record = {"text": check.text, "found": check.found, "checked_against": "page",
                          "passage": check.passage}
                if not check.found:
                    record["reason"] = check.reason
                quotes.append(record)
        archived_url = fm.get("archived_url")
        if cfg.skip_wayback:
            archive = "skipped"
        elif not archived_url:
            archive = "none"
        else:
            capture = await check_capture(client, str(archived_url), stored_url, also_same_as=final_url)
            archive = "ok" if capture.ok else "unverified" if capture.unverified else "bad"
            if not capture.ok and reason is None:
                reason = capture.reason
        records[sid] = {
            "refetched": text is not None,
            "checked_at": today.isoformat(),
            "archive": archive,
            "reason": reason,
            "quotes": quotes,
        }
        logger.info("Rechecked cached source %s: refetched=%s archive=%s", sid, text is not None, archive)
    return records
