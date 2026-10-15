"""Ingest step: fetch each candidate URL and turn it into a checked source."""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from common.canonical_url import canonical_key
from common.models import Independence, resolve_model
from common.source_classification import classify_source_type, independence_for_source_type
from common.utils import slug_from_url
from ingestor.agent import (
    IngestorDeps,
    archive_after_ingest,
    fetch_failure_reason,
    ingestor_agent,
    requested_page_kind,
    requested_page_text,
)
from ingestor.arxiv_affiliation import arxiv_corporate_lab
from ingestor.models import SourceFile
from ingestor.tools.web_fetch import TerminalFetchError
from ingestor.validation import apply_quote_checks, validate_source_file
from loop.errors import StepError
from loop.policy import Rule, classify_exception, retry_after_s
from loop.research import _order_by_coverage
from loop.spec import VerificationResult, VerifyConfig, _cfg_repo_root
from orchestrator.persistence import load_source_dict, resolve_source_slugs

if TYPE_CHECKING:
    from researcher.decomposed import ResearchOutput

logger = logging.getLogger(__name__)


@dataclass
class IngestNotes:
    """What one ``ingest_urls`` call learned about its URLs beyond the SourceFiles."""

    # Requested URL -> URL its live fetch ended on after redirects.
    final_urls: dict[str, str] = field(default_factory=dict)
    # Requested URL dropped because it reached a page already kept -> the kept URL.
    aliases: dict[str, str] = field(default_factory=dict)
    # Requested URL -> sidecar ``archive`` record ({status, error?}).
    archive: dict[str, dict] = field(default_factory=dict)
    # Requested URL -> the page text its ingest fetched (the text the quote
    # check trusts); the coverage check reads it.
    page_text: dict[str, str] = field(default_factory=dict)
    # Requested URL -> one check record per key quote the ingest model
    # returned (``IngestorDeps.quote_checks``); the sidecar stores them.
    quote_checks: dict[str, list[dict]] = field(default_factory=dict)


def _reuse_stored_redirect_targets(
    source_files: list[tuple[str, SourceFile]],
    cached_sources: list[tuple[str, str, dict]],
    notes: IngestNotes,
    url_index: dict[str, str],
    repo_root: Path,
) -> list[tuple[str, SourceFile]]:
    """Return the fresh sources to write; move redirects to a stored page into ``cached_sources``.

    The dedup index only knows requested URLs before the fetch, so a request
    that redirects to a page stored under its final URL arrives here as a
    fresh source. A stored page already cached for this claim becomes an
    alias of the cached URL instead of a second entry.
    """
    cached_by_id = {sid: url for url, sid, _sd in cached_sources}
    fresh: list[tuple[str, SourceFile]] = []
    for url, sf in source_files:
        final = notes.final_urls.get(url)
        sid = url_index.get(canonical_key(final)) if final else None
        sd = load_source_dict(sid, repo_root) if sid else None
        if sd is None:
            fresh.append((url, sf))
            continue
        logger.info("dedup-hit (redirect): %s -> %s", url, sid)
        if sid in cached_by_id:
            notes.aliases[url] = cached_by_id[sid]
        else:
            cached_sources.append((url, sid, sd))
            cached_by_id[sid] = url
    return fresh


async def _ingest_claim_sources(
    client: httpx.AsyncClient,
    urls_to_ingest: list[str],
    cached_sources: list[tuple[str, str, dict]],
    ro: ResearchOutput,
    result: "VerificationResult",
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    url_index: dict[str, str],
    repo_root: Path,
) -> tuple[list[tuple[str, SourceFile]], list[StepError], IngestNotes]:
    """Ingest up to ``max_sources`` fresh sources; return fresh sources, errors and notes.

    Cached sources steer the order (a sub-question they already cover goes
    later) and never shrink the target: ``max_sources`` fresh candidates are
    still tried. Redirects to a stored page move into ``cached_sources``, and
    ``result`` gains the final URLs, archive records and fetched page text
    the sidecar, index and coverage check need.
    """
    notes = IngestNotes()
    remaining = cfg.max_sources
    if remaining > 0:
        # Ingest stops at ``remaining`` successes in list order, so a thin
        # sub-question's URLs go first; dedup hits on disk count as coverage.
        cached_counts: Counter[str] = Counter(
            sq for url, _sid, _sd in cached_sources for sq in ro.url_addresses.get(url, [])
        )
        urls_to_ingest = _order_by_coverage(
            urls_to_ingest, ro.url_addresses,
            [sq.id for sq in ro.sub_questions], cached_counts,
        )
        # Every indexed URL of a source the claim already has, so a fetch that
        # redirects to one does not count toward ``remaining``.
        cached_by_id = {sid: url for url, sid, _sd in cached_sources}
        known_pages = {
            key: cached_by_id[sid] for key, sid in url_index.items() if sid in cached_by_id
        }
        source_files, ingest_errors = await ingest_urls(
            client, urls_to_ingest, cfg, sem,
            target=remaining,
            prefetched_bodies=ro.prefetched_bodies,
            acquisition_out=_trace_acquisition_sink(result.research_trace),
            notes=notes,
            known_pages=known_pages,
        )
    else:
        source_files, ingest_errors = [], []
    source_files = _reuse_stored_redirect_targets(
        source_files, cached_sources, notes, url_index, repo_root
    )
    result.final_urls = notes.final_urls
    result.archive = notes.archive
    result.page_text = notes.page_text
    result.quote_checks = notes.quote_checks
    return source_files, ingest_errors, notes


def _addresses_with_aliases(
    url: str, url_addresses: dict[str, list[str]], aliases: dict[str, str]
) -> list[str]:
    """Sub-questions ``url`` addresses, plus those of URLs that reached the same page."""
    out = list(url_addresses.get(url, []))
    for alias, kept in aliases.items():
        if kept == url:
            out.extend(sq for sq in url_addresses.get(alias, []) if sq not in out)
    return out


_WAYBACK_FAILURE_TAGS = frozenset({"wayback_unavailable"})


def merge_acquisition_writes(
    acquisition_out: dict[str, dict], writes: dict[str, dict]
) -> None:
    """Merge per-URL ingest-stage writes into a research-stage map in place.

    Preserves research-stage fields (``origin``, ``query``) when an
    ingest-stage write supplies ``stage``/``recovered_via``/``outcome``.
    The Astro schema requires ``origin`` on every acquisition entry; a
    plain ``dict.update`` would drop it whenever the same URL was both
    discovered (research) and recovered (ingest).
    """
    for url, write in writes.items():
        existing = acquisition_out.get(url) or {}
        acquisition_out[url] = {**existing, **write}


def _trace_acquisition_sink(research_trace: object) -> dict | None:
    """Return the ``acquisition`` map on ``research_trace`` for ``ingest_urls``.

    Acts as ``setdefault`` so repeated calls return the same dict.
    Returns ``None`` if ``research_trace`` isn't a dict (defensive against
    error variants of ``ResearchOutput``); in that case ``ingest_urls``
    drops acquisition writes silently rather than blowing up the run.
    """
    if not isinstance(research_trace, dict):
        return None
    return research_trace.setdefault("acquisition", {})


def check_ingested_source(
    url: str,
    sf: SourceFile,
    deps: IngestorDeps,
    repo_root: Path,
    corporate_lab: str | None = None,
) -> tuple[str, SourceFile] | StepError:
    """Accept the ingest model's SourceFile only if ``url`` was fetched and it validates.

    The model can return a SourceFile after every fetch failed, or without
    calling ``web_fetch`` at all; its summary is then invented.

    ``corporate_lab`` (from ``arxiv_corporate_lab``) makes the lab the
    publisher and the paper ``first-party``: a lab's own paper is its
    self-report, whichever arXiv page was ingested.
    """
    message = fetch_failure_reason(deps)
    if message is not None:
        logger.warning("Rejected ingest (no page text fetched): %s: %s", url, message)
        return StepError(step="ingest", url=url, error_type="fetch_failed", message=message)

    # The dedup index keys on the requested URL; a model echoing a redirect
    # target would otherwise fail the URL-match check and drop a good source.
    if sf.frontmatter.url != url:
        logger.info(
            "Ingest model returned url %s for %s; keeping the requested url",
            sf.frontmatter.url, url,
        )
        sf.frontmatter.url = url
    # Only a link ``wayback_check`` returned is trusted; the lookup in code
    # sets the rest after this check, so a link the model made up must not
    # fail validation first.
    if sf.frontmatter.archived_url and sf.frontmatter.archived_url != deps.wayback_link:
        logger.info(
            "Dropping model-written archived_url %s for %s", sf.frontmatter.archived_url, url
        )
        sf.frontmatter.archived_url = None
    checks = apply_quote_checks(sf, requested_page_text(deps), with_passage=True)
    checked_against = requested_page_kind(deps)
    deps.quote_checks = []
    for check in checks:
        record = {"text": check.text, "found": check.found, "checked_against": checked_against,
                  "passage": check.passage}
        if not check.found:
            logger.warning("Dropping key quote not found on the page for %s: %r", url, check.text)
            record["reason"] = check.reason
        deps.quote_checks.append(record)
    if corporate_lab:
        logger.info("arXiv paper %s has a %s author; labelling it first-party", url, corporate_lab)
        # The exact lab name: the entity match compares publishers by equality.
        sf.frontmatter.publisher = corporate_lab
        sf.frontmatter.independence = Independence.FIRST_PARTY
    validation = validate_source_file(sf, url, str(repo_root))
    for warning in validation.warnings:
        logger.warning("Ingest validation warning for %s: %s", url, warning)
    if not validation.ok:
        message = "; ".join(validation.errors)
        logger.warning("Rejected ingest (invalid source): %s: %s", url, message)
        return StepError(step="ingest", url=url, error_type="invalid_source", message=message)

    logger.info("Ingested: %s -> %s", url, sf.frontmatter.title)
    return (url, sf)


async def ingest_one(
    client: httpx.AsyncClient,
    url: str,
    cfg: VerifyConfig,
    today: datetime.date,
    sem: asyncio.Semaphore,
    prefetched_body: str | None = None,
    acquisition_out: dict[str, dict] | None = None,
    failures_out: list[dict] | None = None,
    repo_root: Path | None = None,
    notes: IngestNotes | None = None,
) -> tuple[str, SourceFile] | StepError:
    """Ingest a single URL. Returns a (url, SourceFile) tuple on success or a StepError.

    ``acquisition_out`` and ``failures_out`` are optional output sinks
    populated from the ``wayback_check`` tool's side-channel on
    ``IngestorDeps``. Both sinks are optional; a caller that does not
    need archive provenance omits them.

    * ``acquisition_out`` (dict): per-URL recovery writes shaped
      ``{recovered_via, stage, outcome}``. Merged into the caller's map.
    * ``failures_out`` (list): wayback transport-failure dicts
      ``{stage, error_type, message}``. The caller decides whether to
      promote these to ``StepError`` (see ``ingest_urls`` — only for
      URLs whose ingest itself failed terminally).
    * ``notes``: gains, for a successful ingest, the URL its live fetch
      ended on and the sidecar record of the archive lookup.

    A successful ingest also gets its ``archived_url`` from that lookup.

    A transport failure on this URL (``classify_exception``: a null body, a
    rate limit, a dropped connection; not a timeout, which already spent
    ``ingest_timeout_s``) is retried ``cfg.url_retries`` times, each after
    the provider's ``retry-after`` or ``cfg.url_retry_delay_s``. Every
    attempt starts from fresh ``IngestorDeps``.
    """
    repo_root = repo_root or _cfg_repo_root(cfg)
    prompt = (
        f"Ingest this URL and produce a SourceFile:\n\n"
        f"URL: {url}\n"
        f"Today's date: {today.isoformat()}\n"
    )
    attempts = 1 + max(0, cfg.url_retries)
    for attempt in range(1, attempts + 1):
        deps = IngestorDeps(
            http_client=client,
            repo_root=str(repo_root),
            requested_url=url,
            skip_wayback=cfg.skip_wayback,
            allow_save=cfg.allow_save,
            today=today,
            prefetched_bodies={url: prefetched_body} if prefetched_body else {},
        )
        retry_in: float | None = None
        try:
            with ingestor_agent.override(model=resolve_model(cfg.model_for("ingestor"))):
                async with sem:
                    res = await asyncio.wait_for(
                        ingestor_agent.run(prompt, deps=deps), timeout=cfg.ingest_timeout_s
                    )
            sf = res.output
            derived = slug_from_url(url)
            if derived:
                sf.slug = derived
            # Outside the LLM semaphore and time limit; never raises.
            corporate_lab = await arxiv_corporate_lab(client, url)
            outcome: tuple[str, SourceFile] | StepError = check_ingested_source(
                url, sf, deps, repo_root, corporate_lab
            )
        except asyncio.TimeoutError:
            logger.warning("Ingest timed out: %s", url)
            outcome = StepError(
                step="ingest", url=url, error_type="timeout", message="Ingest timed out"
            )
        except TerminalFetchError as exc:
            logger.info("Skipped terminal fetch (%d): %s", exc.status_code, url)
            outcome = StepError(
                step="ingest",
                url=url,
                error_type=f"http_{exc.status_code}",
                message=exc.reason,
                retryable=False,
            )
        except Exception as exc:
            error_type, rule = classify_exception(exc)
            outcome = StepError(
                step="ingest", url=url, error_type=error_type, message=str(exc) or type(exc).__name__,
            )
            if rule is Rule.TRANSPORT_RETRY and error_type != "timeout" and attempt < attempts:
                retry_in = retry_after_s(exc) or cfg.url_retry_delay_s
                logger.warning(
                    "Ingest of %s failed (%s); retrying in %.1fs: %s", url, error_type, retry_in, exc,
                )
            else:
                logger.warning("Failed to ingest %s: %s", url, exc)
        if retry_in is None:
            break
        await asyncio.sleep(retry_in)

    if isinstance(outcome, tuple):
        # Outside the LLM semaphore and the ingest time limit: a slow
        # archive.org must not turn a good ingest into a timeout.
        record = await archive_after_ingest(outcome[1], deps)
        if notes is not None:
            notes.archive[url] = record
        if notes is not None and deps.final_url:
            notes.final_urls[url] = deps.final_url
        if notes is not None:
            notes.page_text[url] = requested_page_text(deps)
            notes.quote_checks[url] = list(deps.quote_checks)

    if acquisition_out is not None:
        merge_acquisition_writes(acquisition_out, deps.acquisition_writes)
    if failures_out is not None:
        failures_out.extend(deps.wayback_failures)

    return outcome


async def ingest_urls(
    client: httpx.AsyncClient,
    urls: list[str],
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    *,
    target: int | None = None,
    prefetched_bodies: dict[str, str] | None = None,
    acquisition_out: dict[str, dict] | None = None,
    notes: IngestNotes | None = None,
    known_pages: dict[str, str] | None = None,
) -> tuple[list[tuple[str, SourceFile]], list[StepError]]:
    """Waterfall: attempt up to candidate_pool_size URLs in the order given,
    stopping once max_sources successes are collected (~2 concurrent).

    Two URLs that reach one page (by redirect) give one result: the later
    one is dropped, does not count toward ``target``, and is recorded in
    ``notes.aliases``. ``known_pages`` (canonical key -> requested URL) names
    pages the claim already has from the dedup index; a URL that reaches one
    is dropped the same way. ``notes.final_urls`` maps each requested URL to the
    URL its live fetch ended on.

    When ``prefetched_bodies`` is supplied, each URL's body (if present)
    is threaded into ``IngestorDeps`` so ``web_fetch`` returns it without
    issuing an httpx GET. Missing/empty entries fall through to a live
    fetch.

    ``acquisition_out`` is an optional output map: when supplied, the
    per-URL ``{recovered_via, ...}`` writes drained from the
    ``wayback_check`` side-channel are merged into it. Mirrors the
    ``acquisition_out`` parameter on ``researcher.execute_searches`` —
    ``_ingest_claim_sources`` passes ``research_trace["acquisition"]`` so the
    audit sidecar can graft the provenance onto matching
    ``sources_consulted[]`` entries.

    ``errors`` includes any ``wayback_unavailable``
    ``StepError`` entries derived from the side-channel — but only for
    URLs whose ingest itself failed terminally. Successful ingests with a
    transient archive blip stay quiet.
    """
    today = datetime.date.today()
    repo_root = _cfg_repo_root(cfg)
    target = target if target is not None else cfg.max_sources
    pool = urls[: cfg.candidate_pool_size]
    dispatch_sem = asyncio.Semaphore(2)
    bodies = prefetched_bodies or {}

    notes = notes if notes is not None else IngestNotes()
    results: list[tuple[str, SourceFile]] = []
    errors: list[StepError] = []
    stop = asyncio.Event()
    # canonical key of each kept result's requested and final URL -> requested URL
    kept_pages: dict[str, str] = dict(known_pages or {})

    def _same_page_as_kept(url: str) -> str | None:
        for candidate in (url, notes.final_urls.get(url)):
            if candidate and canonical_key(candidate) in kept_pages:
                return kept_pages[canonical_key(candidate)]
        return None

    async def _worker(url: str) -> None:
        if stop.is_set():
            return
        async with dispatch_sem:
            if stop.is_set():
                return
            # Per-URL: only promote transport failures to StepError when
            # this URL also failed terminally.
            url_failures: list[dict] = []
            outcome = await ingest_one(
                client, url, cfg, today, sem,
                prefetched_body=bodies.get(url),
                acquisition_out=acquisition_out,
                failures_out=url_failures,
                repo_root=repo_root,
                notes=notes,
            )

            if isinstance(outcome, tuple):
                kept_url = _same_page_as_kept(url)
                if kept_url is not None:
                    logger.info("dedup-hit (redirect): %s -> %s", url, kept_url)
                    notes.aliases[url] = kept_url
                    return
                for page in (url, notes.final_urls.get(url)):
                    if page:
                        kept_pages.setdefault(canonical_key(page), url)
                results.append(outcome)
                if len(results) >= target:
                    logger.info(
                        "Reached target %d successes; stopping waterfall", target
                    )
                    stop.set()
            else:
                errors.append(outcome)
                for failure in url_failures:
                    tag = failure.get("error_type")
                    if tag not in _WAYBACK_FAILURE_TAGS:
                        continue
                    errors.append(StepError(
                        step=failure.get("stage", "ingest"),
                        url=url,
                        error_type=tag,
                        message=failure.get("message", ""),
                    ))

    tasks = [asyncio.create_task(_worker(url)) for url in pool]
    await asyncio.gather(*tasks, return_exceptions=True)
    kept = results[:target]
    kept_urls = {url for url, _sf in kept} | set((known_pages or {}).values())
    for alias, kept_url in list(notes.aliases.items()):
        if kept_url not in kept_urls:
            del notes.aliases[alias]
    # Source ids (year/slug) reach the analyst, coverage map and sidecar
    # before any file is written, so collisions are settled here.
    resolve_source_slugs([sf for _url, sf in kept], repo_root)
    return kept, errors


def _build_source_dict(sf: SourceFile) -> dict:
    source_type = classify_source_type(sf.frontmatter.publisher, sf.frontmatter.kind.value)
    independence = (
        sf.frontmatter.independence.value
        if sf.frontmatter.independence is not None
        else independence_for_source_type(source_type)
    )
    return {
        "title": sf.frontmatter.title,
        "publisher": sf.frontmatter.publisher,
        "summary": sf.frontmatter.summary,
        "key_quotes": sf.frontmatter.key_quotes or [],
        "body": sf.body,
        "slug": sf.slug,
        "url": sf.frontmatter.url,
        "source_id": f"{sf.year}/{sf.slug}",
        "kind": sf.frontmatter.kind.value,
        "independence": independence,
    }
