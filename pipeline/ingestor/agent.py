"""PydanticAI agent definition for the Ingestor."""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from pydantic_ai import Agent, RunContext

from common.canonical_url import same_page_any_scheme
from common.instructions import load_instructions
from common.timeouts import RATE_LIMIT_RETRY_S, default_httpx_timeout
from ingestor.models import SourceFile
from ingestor.tools.wayback import (
    SNAPSHOT_MAX_AGE,
    archive_with_time_limit,
    find_or_save_archive,
)
from ingestor.tools.web_fetch import (
    TERMINAL_STATUS_CODES,
    TerminalFetchError,
    extract_page_data,
)

logger = logging.getLogger(__name__)

_BINARY_CONTENT_TYPES = ("application/pdf", "application/octet-stream", "application/msword")

_SYSTEM_PROMPT = load_instructions(Path(__file__).resolve().parent)


@dataclass
class IngestorDeps:
    """Runtime dependencies for the ingestor agent."""

    http_client: httpx.AsyncClient
    repo_root: str
    # The URL being ingested. A fetch of it, or of its archive.org copy, is
    # what ``fetch_failure_reason`` requires.
    requested_url: str
    skip_wayback: bool = False
    # False for commands that write nothing (``dr draft --source --dry-run``,
    # ``dr draft --dry-run``): archive lookups then use existing captures only
    # and never ask Save Page Now to capture a page.
    allow_save: bool = True
    today: datetime.date = field(default_factory=datetime.date.today)
    # url -> body string supplied by the researcher (e.g., Tavily's
    # ``raw_content``). When set, ``web_fetch`` returns the body
    # directly instead of issuing an httpx GET, sidestepping
    # Cloudflare-shielded publishers that 403 anonymous fetches.
    prefetched_bodies: dict[str, str] = field(default_factory=dict)
    # Drained by the orchestrator post-run; see ``wayback_check`` docstring.
    wayback_failures: list[dict] = field(default_factory=list)
    acquisition_writes: dict[str, dict] = field(default_factory=dict)
    # Filled by ``web_fetch`` so the orchestrator can reject a SourceFile
    # whose page never loaded: the tool returns error dicts (not raises) on
    # transport failures so the model can still reach ``wayback_check``,
    # which leaves the model free to invent a summary. ``fetched_text`` is
    # keyed by the URL the tool was called with and kept for key-quote
    # checks; the ``requested_*`` fields cover only ``requested_url``.
    fetched_text: dict[str, str] = field(default_factory=dict)
    fetch_errors: list[str] = field(default_factory=list)
    requested_fetched: bool = False
    requested_errors: list[str] = field(default_factory=list)
    # Where a live fetch of ``requested_url`` ended after redirects, so the
    # orchestrator can match it to a source already stored under that URL.
    # Unset for archive.org copies and prefetched bodies (no redirect info).
    final_url: str | None = None
    # The archive link ``wayback_check`` returned for ``requested_url``; the
    # lookup run in code after the ingest reuses it when the live fetch
    # failed, instead of repeating it.
    wayback_link: str | None = None
    # One record per key quote the model returned, in its order, filled by
    # the ingest check (``loop.ingest.check_ingested_source``):
    # ``{text, found, checked_against, passage}`` plus ``reason`` when not found.
    quote_checks: list[dict] = field(default_factory=list)


# Any timestamp segment (including suffixes like "id_") or none at all, then
# the archived page's own URL, with or without its scheme.
_ARCHIVE_COPY = re.compile(r"https?://web\.archive\.org/web/(?:[0-9*]+[a-z_]*/)?(.+)")
# A GET to archive.org's /save/ path asks Save Page Now to capture a page.
# The model can name such a URL on its own (seen in a live dry run), and the
# only sanctioned capture path is ``wayback._save_and_check``, which honours
# ``allow_save``.
_ARCHIVE_SAVE = re.compile(r"https?://(?:[a-z0-9-]+\.)*archive\.org(?::\d+)?/save(?:[/?#]|$)", re.IGNORECASE)


def _is_page_or_archive_copy(fetched: str, url: str) -> bool:
    # Scheme is ignored: Wayback often holds only the http capture, and the
    # live fetch of an http:// URL may be upgraded to https.
    archived = _ARCHIVE_COPY.match(fetched)
    page = archived.group(1) if archived else fetched
    return same_page_any_scheme(page, url)


def requested_page_text(deps: IngestorDeps) -> str:
    """The fetched text of ``deps.requested_url`` and its archive.org copies.

    Text from any other page the model fetched is left out, so it cannot
    vouch for a key quote.
    """
    return "\n".join(
        text for url, text in deps.fetched_text.items()
        if _is_page_or_archive_copy(url, deps.requested_url)
    )


def requested_page_kind(deps: IngestorDeps) -> str:
    """Which texts ``requested_page_text`` joins: ``page``, ``archive`` or ``page-and-archive``.

    ``page`` is the live page (or a prefetched body for it); ``archive`` an
    archive.org copy. A key quote's ``checked_against`` records this.
    """
    kinds = {
        "archive" if _ARCHIVE_COPY.match(url) else "page"
        for url in deps.fetched_text
        if _is_page_or_archive_copy(url, deps.requested_url)
    }
    if kinds == {"archive"}:
        return "archive"
    return "page-and-archive" if kinds == {"page", "archive"} else "page"


def fetch_failure_reason(deps: IngestorDeps) -> str | None:
    """Why ``deps.requested_url`` yielded no text, or None when it (or its archive.org copy) did.

    Text from any other page does not count: the model can fetch an unrelated
    page after the requested one fails and summarize that instead.
    """
    if deps.requested_fetched:
        return None
    if deps.requested_errors:
        return deps.requested_errors[-1]
    if deps.fetched_text:
        return f"no text fetched for {deps.requested_url}; only other pages were fetched: " + ", ".join(
            deps.fetched_text
        )
    return "model returned a source without fetching the page"


ingestor_agent = Agent(
    "test",
    output_type=SourceFile,
    deps_type=IngestorDeps,
    system_prompt=_SYSTEM_PROMPT,
    retries=2,
)


def _raise_if_terminal(resp: httpx.Response, url: str) -> None:
    if resp.status_code in TERMINAL_STATUS_CODES:
        raise TerminalFetchError(url, resp.status_code, resp.reason_phrase)


@ingestor_agent.tool
async def web_fetch(ctx: RunContext[IngestorDeps], url: str) -> dict:
    """Fetch a web page and extract its title, metadata, and text content.

    When ``ctx.deps.prefetched_bodies[url]`` is set, returns that body
    directly (Markdown/plain text from Tavily's ``raw_content``) and
    skips the httpx GET, sidestepping Cloudflare-shielded publishers
    that 403 anonymous fetches.

    Terminal statuses (401/402/403/404/451) raise ``TerminalFetchError`` so the
    agent run short-circuits without calling ``wayback_check`` or consuming
    the agent retry budget. 429 gets one in-tool retry after a short sleep;
    still-429 also raises. All other HTTP errors fall through to the
    existing error-dict behavior so the LLM can try ``wayback_check``.
    """
    if not url.startswith(("http://", "https://")):
        return {"error": f"Invalid URL: {url!r} (must start with http:// or https://)", "url": url}
    deps = ctx.deps
    if _ARCHIVE_SAVE.match(url):
        logger.warning("Refused an archive.org capture request from web_fetch: %s", url)
        deps.fetch_errors.append(f"{url}: refused, an archive.org /save/ URL asks for a capture")
        return {
            "error": "Refused: a web.archive.org/save/ URL asks archive.org to capture a page. "
            "Fetch the page itself, or use wayback_check to find an archived copy.",
            "url": url,
        }
    is_requested = _is_page_or_archive_copy(url, deps.requested_url)

    def record_text(text: str) -> None:
        deps.fetched_text[url] = text
        deps.requested_fetched = deps.requested_fetched or is_requested

    def record_error(message: str) -> None:
        entry = f"{url}: {message}"
        deps.fetch_errors.append(entry)
        if is_requested:
            deps.requested_errors.append(entry)

    prefetched = deps.prefetched_bodies.get(url)
    if prefetched:
        logger.info("Prefetch hit (Tavily raw_content): %s", url)
        record_text(prefetched)
        return {
            "title": "",
            "description": "",
            "author": None,
            "published_time": None,
            "text": prefetched,
            "url": url,
        }
    try:
        resp = await deps.http_client.get(
            url, timeout=default_httpx_timeout(), follow_redirects=True
        )
        _raise_if_terminal(resp, url)

        if resp.status_code == 429:
            logger.info(
                "429 from %s; sleeping %.1fs and retrying once", url, RATE_LIMIT_RETRY_S
            )
            await asyncio.sleep(RATE_LIMIT_RETRY_S)
            resp = await deps.http_client.get(
                url, timeout=default_httpx_timeout(), follow_redirects=True
            )
            if resp.status_code == 429:
                raise TerminalFetchError(url, 429, resp.reason_phrase)
            _raise_if_terminal(resp, url)

        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if any(t in ct for t in _BINARY_CONTENT_TYPES):
            record_error(f"unsupported content type {ct}")
            return {"error": f"Unsupported content type: {ct}", "url": url}
        page = extract_page_data(resp.text, url)
        if page.get("text"):
            # The model is shown the title and description too, so a key
            # quote copied from either is on the page.
            record_text("\n".join(
                part for part in (page.get("title"), page.get("description"), page["text"]) if part
            ))
            if is_requested and not _ARCHIVE_COPY.match(url):
                deps.final_url = str(resp.url)
        else:
            record_error("page returned no text")
        return page
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        record_error(str(exc))
        return {"error": str(exc), "url": url}


@ingestor_agent.tool
async def wayback_check(ctx: RunContext[IngestorDeps], url: str) -> dict:
    """Check archival fallbacks for ``url`` and surface the recovered archive.

    Runs ``find_or_save_archive``: the archive.org capture closest to "now"
    counts only when it replays with HTTP 200 for the same page, else the
    newest such capture in the CDX index; with none, Save Page Now is asked
    to capture the live URL (unless ``allow_save`` is False, the run writes
    nothing) and that capture is checked the same way. No freshness limit
    applies here.

    Populates two side-channels on ``ctx.deps`` for the orchestrator to
    drain post-run:

    * ``acquisition_writes[url]``: ``{stage, recovered_via, outcome}``
      when an existing capture is found. ``save_to_wayback`` success does
      *not* write acquisition — save creates a fresh archive of a
      still-reachable URL, not a recovery of a lost one.
    * ``wayback_failures``: ``{stage, error_type, message}`` for each
      archive.org failure behind a missing link. The orchestrator promotes
      to ``StepError`` only when the ingest itself failed terminally.
    """
    if not url.startswith(("http://", "https://")):
        return {"available": False, "archived_url": None, "error": f"Invalid URL: {url!r}"}
    deps = ctx.deps
    if deps.skip_wayback:
        return {"available": False, "archived_url": None, "skipped": True}

    lookup = await find_or_save_archive(deps.http_client, url, allow_save=deps.allow_save)
    for message in lookup.errors:
        deps.wayback_failures.append(
            {"stage": "ingest", "error_type": "wayback_unavailable", "message": message}
        )
    if lookup.archived_url is None:
        return {"available": False, "archived_url": None}

    if lookup.found_existing:
        deps.acquisition_writes[url] = {
            "stage": "ingest",
            "recovered_via": "archive_org",
            "outcome": "recovered",
        }
    if _is_page_or_archive_copy(url, deps.requested_url):
        deps.wayback_link = lookup.archived_url
    return {"available": True, "archived_url": lookup.archived_url}


async def archive_after_ingest(sf: SourceFile, deps: IngestorDeps) -> dict:
    """Set ``sf``'s ``archived_url`` in code and return the sidecar ``archive`` record.

    The model's own ``archived_url`` is not trusted (``_check_ingested_source``
    already dropped any link ``wayback_check`` did not return): it is replaced
    by the lookup's link, or cleared when the lookup fails or raises.

    When the live fetch succeeded, the page is known to be up, so a capture
    older than ``SNAPSHOT_MAX_AGE`` or than the page's ``published_date`` is
    refreshed with a checked Save Page Now capture. Otherwise (the text came
    from an archive copy or a prefetched body) a link ``wayback_check``
    returned during this ingest is reused, so the lookup is not repeated.
    With ``skip_wayback`` nothing is looked up. With ``deps.allow_save``
    False no capture is made.
    """
    if deps.skip_wayback:
        return {"status": "not-attempted"}
    freshness: dict = {}
    if deps.final_url is not None:
        freshness = {
            "max_age": SNAPSHOT_MAX_AGE,
            "not_before": sf.frontmatter.published_date,
            "also_same_as": deps.final_url,
        }
    elif deps.wayback_link:
        sf.frontmatter.archived_url = deps.wayback_link
        return {"status": "found"}
    try:
        lookup = await archive_with_time_limit(
            deps.http_client, sf.frontmatter.url, allow_save=deps.allow_save, **freshness
        )
    except Exception as exc:
        # The helpers catch only httpx.HTTPError; anything else (e.g.
        # httpx.InvalidURL) would escape the ingest and silently drop a good
        # source, so a lookup error is recorded like any failed lookup.
        logger.warning("archive.org lookup raised for %s: %r", sf.frontmatter.url, exc)
        sf.frontmatter.archived_url = None
        return {"status": "failed", "error": f"archive.org lookup failed ({type(exc).__name__}): {exc}"}
    sf.frontmatter.archived_url = lookup.archived_url
    if lookup.archived_url:
        return {"status": "found"}
    return {"status": "failed", "error": "; ".join(lookup.errors) or "no archive.org snapshot"}
