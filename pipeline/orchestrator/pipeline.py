"""Orchestrator-owned claim verification pipeline.

Chains the per-claim flow:

    research -> ingest -> [threshold check] -> analyze -> evaluate

Checkpoints sit between major steps (source review after ingest;
disagreement review after the Evaluator runs). Post-ingest, the
Orchestrator calls ``below_threshold`` and, when fewer than two usable
sources are available, halts the claim by setting ``status: blocked`` with
a ``blocked_reason`` (``insufficient_sources`` or ``terminal_fetch_error``)
instead of invoking the Analyst.

The ``Evaluator`` step is implemented by the ``pipeline/auditor/`` package
(directory name retained for v1 per
``docs/plans/v0.1.0-vocab-workflow-landing.md``).

See ``AGENTS.md`` ``## How the system works`` for the canonical narrative.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import click
import httpx
import openai
from pydantic import BaseModel, ConfigDict, Field, computed_field

import dataclasses

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior

from analyst.agent import AnalystOutput, VerdictAssessment, analyst_agent, build_analyst_prompt, verdict_only_agent
from analyst.agent import EntityResolution
from orchestrator.entity_resolution import ResolvedEntity, SearchHints
from auditor.agent import auditor_agent, build_auditor_prompt
from common.blocklist import normalised_host, filter_urls, load_blocklist
from common.content_loader import resolve_repo_root
from common.logging_setup import bind_run_id, hr, new_run_id, progress, run_id_var
from common.models import BlockedReason, Category, Confidence, EntityType, Verdict
from common.templates import VOCABULARY_HINT_PREFIX, blocked_title_message, get_template, load_templates, render_blocked_title, render_claim_text, templates_for_entity_type, validate_analyst_title
from common.timeouts import ingest_budget_with_wayback_s
from common.utils import slug_from_url, slugify
from auditor.bundle import build_bundle
from auditor.compare import compare
from auditor.models import ComparisonResult
from common.models import DEFAULT_MODEL, AgentName, resolve_model
from ingestor.agent import IngestorDeps, ingestor_agent
from ingestor.models import SourceFile
from ingestor.tools.web_fetch import TerminalFetchError
from orchestrator.checkpoints import AutoApproveCheckpointHandler, CheckpointHandler, StepError
from common.models import SubQuestion
from common.source_classification import classify_source_type, independence_for_source_type
from orchestrator.persistence import build_source_url_index, load_source_dict
from researcher.decomposed import ResearchOutput

logger = logging.getLogger(__name__)

_NULL_RESPONSE_MSG = "Invalid response from"
_NULL_BODY_RETRIES = 2
_NULL_BODY_RETRY_DELAY_S = 45.0
_RATE_LIMIT_RETRY_DELAY_S = 90.0


class VerificationResult(BaseModel):
    """Full output of an end-to-end claim verification."""

    entity: str
    claim_text: str
    urls_found: list[str]
    urls_ingested: list[str]
    urls_failed: list[str]
    sources: list[dict]
    analyst_output: AnalystOutput | None = None
    consistency: ComparisonResult | None = None
    errors: list[str] = field(default_factory=list)
    # Set when the Orchestrator halts the claim post-ingest because fewer
    # than two usable sources were obtained. Callers that persist claim
    # files (research_claim, onboard_entity) inspect this to write a
    # blocked claim file instead of skipping.
    blocked_reason: BlockedReason | None = None
    # Repo-relative path of the written claim file (e.g.
    # "research/claims/microsoft/renewable-energy-pledges.md"). Set by
    # research_claim after the claim file lands; left None for in-memory
    # verify_claim runs that don't persist.
    claim_path: str | None = None
    source_files: list[tuple[str, SourceFile]] = Field(default_factory=list, exclude=True)
    # Cache-hit sources reused via URL dedup; without these the audit sidecar's
    # sources_consulted is empty when every URL was already on disk.
    cached_sources: list[tuple[str, str, dict]] = Field(default_factory=list, exclude=True)
    # Researcher-step trace: planner queries+rationale and scorer rationale.
    # Persisted to the audit sidecar so reviewers can see how the source set
    # was assembled.
    research_trace: dict | None = None
    # Sub-question decomposition the planner emitted for this claim.
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    # Map SubQuestion.id -> list of source_ids that addressed it after ingest
    # (sources whose ScoredCandidate.addresses included this id AND that
    # ingested successfully). An empty list signals an uncovered axis.
    sub_question_coverage: dict[str, list[str]] = Field(default_factory=dict)
    # Per-sub-question queries from the planner. Used to render the audit
    # sidecar's `sub_questions:` block; not part of the on-disk claim file.
    queries_by_sub_question: dict[str, list[str]] = Field(default_factory=dict, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @computed_field
    @property
    def cached_source_ids(self) -> list[str]:
        return [sid for _url, sid, _sd in self.cached_sources]


def below_threshold(usable_sources: list) -> bool:
    """True when fewer than four usable sources are available.

    A "usable" source is one that ingested successfully (parsed body,
    not blocked, not a terminal HTTP error). The Orchestrator calls this
    after the Ingestor returns and halts the claim with status='blocked'
    when it returns True. See docs/plans/claim-lifecycle-states.md.
    """
    return len(usable_sources) < 4


def _classify_blocked_reason(ingest_errors: list[StepError]) -> BlockedReason:
    """Pick the right blocked_reason given the post-ingest error list.

    If every recorded ingest error is a non-retryable terminal fetch
    (HTTP 401/403/etc. surfaced by TerminalFetchError), the cause is
    classified as ``terminal_fetch_error``. Otherwise (mix of timeouts,
    parse failures, or simply too few URLs found) it defaults to
    ``insufficient_sources``.
    """
    ingest_only = [e for e in ingest_errors if e.step == "ingest"]
    if ingest_only and all(
        (e.retryable is False) and e.error_type.startswith("http_")
        for e in ingest_only
    ):
        return BlockedReason.TERMINAL_FETCH_ERROR
    return BlockedReason.INSUFFICIENT_SOURCES


def _summarize_terminal_fetch(ingest_errors: list[StepError]) -> str:
    """Format terminal fetch failures as ``"4 URLs (3× http_403, 1× http_404)"``."""
    counts = Counter(e.error_type for e in ingest_errors if e.step == "ingest")
    parts = ", ".join(
        f"{n}× {code}" for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    return f"{counts.total()} URLs ({parts})"


def _record_threshold_block(
    result: VerificationResult, ingest_errors: list[StepError]
) -> None:
    """Mark `result` as blocked by the < 4 source threshold and emit logs."""
    result.blocked_reason = _classify_blocked_reason(ingest_errors)
    if result.blocked_reason == BlockedReason.TERMINAL_FETCH_ERROR:
        result.errors.insert(0, _summarize_terminal_fetch(ingest_errors))
    msg = (
        f"Claim halted: < 4 usable sources "
        f"(blocked_reason={result.blocked_reason.value})"
    )
    click.echo(msg, err=True)
    logger.warning(msg)


# Timeout chain invariant: the ingestor agent wrapper (``ingest_timeout_s``)
# must cover HTTP fetch + optional 429 retry + optional wayback endpoints +
# LLM tool-dispatch turns. With ``skip_wayback=False`` the budget is derived
# from ``common.timeouts.ingest_budget_with_wayback_s`` so tuning the
# HTTP/wayback constants flows through automatically.
@dataclass
class VerifyConfig:
    model: str = DEFAULT_MODEL
    # Per-agent overrides; each falls back to ``model`` when None. Keeps the
    # single-model path unchanged while letting `dr` mix providers per agent.
    researcher_model: str | None = None
    analyst_model: str | None = None
    auditor_model: str | None = None
    ingestor_model: str | None = None
    # target successes to pass to the analyst
    max_sources: int = 8
    candidate_pool_size: int = 32
    # Interim default: wayback ON. The wayback-archive-job plan envisions
    # archival as a background job with skip_wayback=True in-pipeline, but
    # until that job lands we want primary sources behind paywalls/blocks
    # rescued via web.archive.org during the synchronous run.
    skip_wayback: bool = False
    # Per-claim list of acquisition origins to attempt during research.
    # Default ['tavily']; Brave remains available via search_backend for
    # per-query fallback. Tier1 paths add 'arxiv', 's2', 'openalex', 'edgar'.
    # Values mirror the schema enum on
    # audit.sources_consulted[].acquisition.origin. See
    # docs/plans/source-pool-expansion-tier1.md § Rollout order.
    research_origins: list[str] = field(default_factory=lambda: ["tavily"])
    # Search backend used by the decomposed researcher's `execute_searches`
    # step. Today: 'tavily' (default) or 'brave'. Read once from
    # RESEARCH_SEARCH_BACKEND at construction time; tests can override by
    # passing `search_backend=...` directly. Unknown values fall back to
    # 'brave' with a warning logged in `execute_searches`. See
    # docs/plans/source-pool-expansion-tier1-search-backend.md.
    search_backend: str = field(
        default_factory=lambda: os.environ.get("RESEARCH_SEARCH_BACKEND", "tavily")
    )
    repo_root: str = ""
    # ``ingest_timeout_s`` is ``None`` when the caller hasn't set it, so
    # ``__post_init__`` can pick a default based on ``skip_wayback``. Callers
    # that pass any float (including 60.0) keep that value verbatim.
    ingest_timeout_s: float | None = None
    research_timeout_s: float = 120.0
    analyst_timeout_s: float = 120.0
    auditor_timeout_s: float = 120.0
    force_overwrite: bool = False
    # Effort lever for decomposed researcher: more queries = wider net.
    max_initial_queries: int = 7
    # Integer cap for the shared asyncio.Semaphore created at each call site.
    # Never store the Semaphore itself here — it is loop-bound.
    llm_concurrency: int = 8
    # When True, verify_claim emits stderr progress lines at step boundaries
    # via progress(). Off for onboard (which has its own per-claim progress);
    # on for single-claim CLI paths (claim-refresh, claim-probe) where the
    # run otherwise looks hung.
    show_progress: bool = False
    # Correlates every log record (and future token-usage record) emitted
    # during one top-level pipeline invocation. Inherits a CLI-bound id if
    # set; onboard's per-template loop overrides via dataclasses.replace.
    run_id: str = field(default_factory=lambda: run_id_var.get() or new_run_id())

    def __post_init__(self) -> None:
        if self.ingest_timeout_s is None:
            self.ingest_timeout_s = (
                ingest_budget_with_wayback_s() if not self.skip_wayback else 60.0
            )
        if self.candidate_pool_size < self.max_sources:
            raise ValueError(
                f"candidate_pool_size ({self.candidate_pool_size}) must be >= max_sources ({self.max_sources})"
            )

    def model_for(self, agent: AgentName) -> str:
        """Resolve the model spec for a given agent, falling back to ``model``."""
        return getattr(self, f"{agent}_model") or self.model


async def verify_claim(
    entity_name: str,
    claim_text: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    sem: asyncio.Semaphore | None = None,
    resolved_entity: ResolvedEntity | None = None,
    url_index: dict[str, str] | None = None,
) -> VerificationResult:
    """Run the full verification pipeline.

    1. Researcher: search for relevant sources
    2. Ingestor: fetch and structure each source
    3. [Checkpoint] Review sources before analysis
    4. Analyst: synthesize sources into a claim with verdict
    5. Auditor: independently assess the claim
    6. [Checkpoint on disagreement] Review conflict

    Returns a VerificationResult with all intermediate outputs.
    """
    cfg = config or VerifyConfig()
    gate = checkpoint or AutoApproveCheckpointHandler()
    # Semaphore MUST be created inside the coroutine driven by asyncio.run (loop-bound).
    _sem = sem if sem is not None else asyncio.Semaphore(cfg.llm_concurrency)

    result = VerificationResult(
        entity=entity_name,
        claim_text=claim_text,
        urls_found=[],
        urls_ingested=[],
        urls_failed=[],
        sources=[],
        errors=[],
    )

    research_entity = resolved_entity.entity_name if resolved_entity is not None else entity_name

    # Console-only emit (no file-log mirror) — paired logger.info calls below
    # carry the structured "Step N/M: ..." line for info.log/debug.log.
    if cfg.show_progress:
        say = lambda m, *a: progress(m, *a, log=False)
    else:
        say = lambda *a, **kw: None

    with bind_run_id(cfg.run_id):
        logger.info("verify_claim entry: entity=%s claim=%s", entity_name, claim_text)
        async with httpx.AsyncClient() as client:
            # Step 1: Research
            say("  › Searching")
            logger.info("Step 1/4: Searching for sources...")
            ro = await _research(client, research_entity, claim_text, cfg, _sem, resolved_entity=resolved_entity)
            urls = ro.urls
            research_errors = ro.errors
            result.urls_found = urls
            result.research_trace = ro.trace
            result.sub_questions = ro.sub_questions
            result.queries_by_sub_question = ro.queries_by_sub_question

            result.errors.extend(e.message for e in research_errors)
            if cfg.show_progress:
                for e in research_errors:
                    progress("  ! research: %s", e.message)
            if not urls:
                result.errors.append(_NO_URLS_ERR)
                if any(e.error_type == "scorer_dropped_all" for e in research_errors):
                    result.blocked_reason = BlockedReason.INSUFFICIENT_SOURCES
                return result

            # Step 2: Ingest
            say("  › Ingesting")
            logger.info("Step 2/4: Ingesting %d candidate URLs...", len(urls))
            repo_root = Path(cfg.repo_root or str(resolve_repo_root()))
            if url_index is None:
                url_index = build_source_url_index(repo_root)
            urls_to_ingest, cached_sources = _apply_url_dedup(urls, url_index, repo_root)

            remaining = max(0, cfg.max_sources - len(cached_sources))
            if remaining > 0:
                source_files, ingest_errors = await _ingest_urls(
                    client, urls_to_ingest, cfg, _sem,
                    target=remaining,
                    prefetched_bodies=ro.prefetched_bodies,
                )
            else:
                source_files, ingest_errors = [], []

            for url, sid, sd in cached_sources:
                sd["addresses"] = list(ro.url_addresses.get(url, []))
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.cached_sources.append((url, sid, sd))

            for url, sf in source_files:
                sd = _build_source_dict(sf)
                sd["addresses"] = list(ro.url_addresses.get(url, []))
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.source_files.append((url, sf))

            ingested_set = set(result.urls_ingested)
            result.urls_failed = [u for u in urls if u not in ingested_set]
            all_errors = research_errors + ingest_errors

            # Build per-sub-question coverage from the post-ingest source set.
            # Inverts url -> [sq_id] into sq_id -> [source_id]; sub-questions
            # with zero addressing sources keep an empty list to surface the
            # gap to the analyst and the audit sidecar.
            result.sub_question_coverage = _invert_addresses(
                ro.sub_questions, ro.url_addresses, result.sources
            )

            if cfg.show_progress:
                progress(
                    "  ingested %d/%d (cached=%d, fetched=%d, failed=%d)",
                    len(result.urls_ingested),
                    len(urls),
                    len(cached_sources),
                    len(source_files),
                    len(result.urls_failed),
                )
                for e in ingest_errors:
                    progress("  ! ingest: %s", e.message)
                for sq in ro.sub_questions:
                    progress("  %s: %d sources", sq.id, len(result.sub_question_coverage.get(sq.id, [])))

            # Checkpoint: review sources
            proceed = await gate.review_sources(
                urls_found=len(result.urls_found),
                urls_ingested=len(result.urls_ingested),
                errors=all_errors,
                sub_question_coverage=result.sub_question_coverage,
            )
            if not proceed:
                result.errors.append("Halted at source review checkpoint")
                return result

            # Threshold gate: Orchestrator halts the claim before invoking the
            # Analyst when fewer than two usable sources were obtained. See
            # docs/plans/claim-lifecycle-states.md § Behavior change.
            if below_threshold(result.sources):
                _record_threshold_block(result, ingest_errors)
                if cfg.show_progress:
                    progress(
                        "  ! blocked before analyst: %s",
                        result.blocked_reason.value if result.blocked_reason else "below_threshold",
                    )
                return result

            # Step 3: Analyst
            say("  › Analysing")
            logger.info("Step 3/4: Analysing claim from %d sources...", len(result.sources))
            analyst_out = await _analyse_claim(
                entity_name, claim_text, result.sources, cfg,
                resolved_entity=resolved_entity,
                sub_questions=result.sub_questions,
            )
            result.analyst_output = analyst_out

            if not analyst_out:
                result.errors.append("Analyst failed to produce an assessment")
                if cfg.show_progress:
                    progress("  ! analyst failed to produce an assessment")
                return result

            # Step 4: Auditor
            say("  › Auditing")
            logger.info("Step 4/4: Running auditor check...")
            comparison = await _audit_claim(
                entity_name, claim_text, analyst_out, result.sources, cfg
            )
            result.consistency = comparison

            # Checkpoint: review disagreement
            if comparison and comparison.needs_review:
                accept = await gate.review_disagreement(comparison)
                if not accept:
                    result.errors.append("Flagged for human review: analyst/auditor disagree")
                    if cfg.show_progress:
                        progress("  ! analyst/auditor disagree: flagged for review")

            if cfg.show_progress:
                progress("Pipeline complete.")

    return result


def _build_sub_questions_block(
    sub_questions: list[SubQuestion],
    coverage: dict[str, list[str]],
    queries_by_sub_question: dict[str, list[str]],
) -> list[dict] | None:
    """Render the sidecar's ``sub_questions:`` block, or None if empty.

    Each entry has ``id``, ``question``, ``rationale``, ``queries``, and
    ``citations`` (list of source-ids that addressed it post-ingest).
    Returns None when the planner emitted no sub-questions, so the
    sidecar writer can omit the key.
    """
    if not sub_questions:
        return None
    block: list[dict] = []
    for sq in sub_questions:
        block.append({
            "id": sq.id,
            "question": sq.question,
            "rationale": sq.rationale,
            "queries": list(queries_by_sub_question.get(sq.id, [])),
            "citations": list(coverage.get(sq.id, [])),
        })
    return block


def _invert_addresses(
    sub_questions: list[SubQuestion],
    url_addresses: dict[str, list[str]],
    sources: list[dict],
) -> dict[str, list[str]]:
    """Build a sq_id -> [source_id] map from per-URL addresses + ingested sources.

    Sub-questions with no addressing source keep an empty list so the
    coverage gap is observable. ``sources`` is the post-ingest list of
    source dicts (cached + fresh combined); each must carry ``url`` and
    ``source_id``.
    """
    coverage: dict[str, list[str]] = {sq.id: [] for sq in sub_questions}
    for sd in sources:
        url = sd.get("url")
        sid = sd.get("source_id")
        if not url or not sid:
            continue
        for sq_id in url_addresses.get(url, []):
            if sq_id in coverage and sid not in coverage[sq_id]:
                coverage[sq_id].append(sid)
    return coverage


def _apply_blocklist_cap(
    raw_urls: list[str],
    cfg: VerifyConfig,
    errors: list[StepError] | None = None,
) -> tuple[list[str], list[StepError]]:
    """Filter raw_urls through the blocklist, cap at max_sources, and append
    blocked_host / all_blocked errors. Returns (kept_urls, error_list)."""
    out_errors: list[StepError] = list(errors) if errors else []
    repo_root_str = cfg.repo_root or str(resolve_repo_root())
    entries = load_blocklist(Path(repo_root_str))
    kept, dropped = filter_urls(raw_urls, entries)
    urls = kept[: cfg.candidate_pool_size]
    for d in dropped:
        out_errors.append(
            StepError(
                step="research",
                url=d.url,
                error_type="blocked_host",
                message=f"Dropped by blocklist (host={d.host}): {d.reason}",
                retryable=False,
            )
        )
    if not urls and dropped:
        out_errors.insert(
            0,
            StepError(
                step="research",
                error_type="all_blocked",
                message=f"All {len(dropped)} researcher URLs matched blocklist; returning empty.",
            ),
        )
    return urls, out_errors


def _apply_url_dedup(
    urls: list[str],
    url_index: dict[str, str],
    repo_root: Path,
) -> tuple[list[str], list[tuple[str, str, dict]]]:
    """Partition urls into those to ingest and those already on disk.

    Returns (to_ingest, cached) where cached is a list of
    (url, source_id, source_dict) triples.
    """
    to_ingest: list[str] = []
    cached: list[tuple[str, str, dict]] = []
    for url in urls:
        source_id = url_index.get(url)
        if source_id:
            sd = load_source_dict(source_id, repo_root)
            if sd is not None:
                logger.info("dedup-hit: %s -> %s", url, source_id)
                cached.append((url, source_id, sd))
                continue
        to_ingest.append(url)
    return to_ingest, cached


async def _research(
    client: httpx.AsyncClient,
    entity_name: str,
    claim_text: str,
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    resolved_entity: "ResolvedEntity | None" = None,
) -> "ResearchOutput":
    """Run the decomposed researcher and return a ``ResearchOutput``.

    The returned ``trace`` dict is suitable for the audit sidecar's
    ``research:`` block. Always populated with at least ``mode``; further
    fields depend on how far the researcher got before any error.
    """
    from researcher.decomposed import decomposed_research
    out = await decomposed_research(
        claim_text, entity_name, cfg, sem, client, resolved_entity=resolved_entity
    )
    urls, errors = _apply_blocklist_cap(out.urls, cfg, out.errors)
    logger.info("Decomposed research: %d kept (cap=%d)", len(urls), cfg.candidate_pool_size)
    out.urls = urls
    out.errors = errors
    out.url_addresses = {u: out.url_addresses.get(u, []) for u in urls}
    out.trace["urls_after_blocklist"] = len(urls)
    return out


async def _ingest_one(
    client: httpx.AsyncClient,
    url: str,
    cfg: VerifyConfig,
    today: datetime.date,
    sem: asyncio.Semaphore,
    prefetched_body: str | None = None,
) -> tuple[str, SourceFile] | StepError:
    """Ingest a single URL. Returns a (url, SourceFile) tuple on success or a StepError."""
    deps = IngestorDeps(
        http_client=client,
        repo_root=cfg.repo_root,
        skip_wayback=cfg.skip_wayback,
        today=today,
        prefetched_bodies={url: prefetched_body} if prefetched_body else {},
    )
    prompt = (
        f"Ingest this URL and produce a SourceFile:\n\n"
        f"URL: {url}\n"
        f"Today's date: {today.isoformat()}\n"
    )
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
        logger.info("Ingested: %s -> %s", url, sf.frontmatter.title)
        return (url, sf)
    except asyncio.TimeoutError:
        logger.warning("Ingest timed out: %s", url)
        return StepError(step="ingest", url=url, error_type="timeout", message="Ingest timed out")
    except TerminalFetchError as exc:
        logger.info("Skipped terminal fetch (%d): %s", exc.status_code, url)
        return StepError(
            step="ingest",
            url=url,
            error_type=f"http_{exc.status_code}",
            message=exc.reason,
            retryable=False,
        )
    except Exception as exc:
        error_type = "http_error" if "HTTP" in type(exc).__name__ else "model_error"
        logger.warning("Failed to ingest %s: %s", url, exc)
        return StepError(step="ingest", url=url, error_type=error_type, message=str(exc))


async def _ingest_urls(
    client: httpx.AsyncClient,
    urls: list[str],
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    *,
    target: int | None = None,
    prefetched_bodies: dict[str, str] | None = None,
) -> tuple[list[tuple[str, SourceFile]], list[StepError]]:
    """Waterfall: attempt up to candidate_pool_size URLs in score order,
    stopping once max_sources successes are collected (~2 concurrent).

    When ``prefetched_bodies`` is supplied, each URL's body (if present)
    is threaded into ``IngestorDeps`` so ``web_fetch`` returns it without
    issuing an httpx GET. Missing/empty entries fall through to a live
    fetch.
    """
    today = datetime.date.today()
    target = target if target is not None else cfg.max_sources
    pool = urls[: cfg.candidate_pool_size]
    dispatch_sem = asyncio.Semaphore(2)
    bodies = prefetched_bodies or {}

    results: list[tuple[str, SourceFile]] = []
    errors: list[StepError] = []
    stop = asyncio.Event()

    async def _worker(url: str) -> None:
        if stop.is_set():
            return
        async with dispatch_sem:
            if stop.is_set():
                return
            outcome = await _ingest_one(
                client, url, cfg, today, sem, prefetched_body=bodies.get(url)
            )
            if isinstance(outcome, tuple):
                results.append(outcome)
                if len(results) >= target:
                    logger.info(
                        "Reached target %d successes; stopping waterfall", target
                    )
                    stop.set()
            else:
                errors.append(outcome)

    tasks = [asyncio.create_task(_worker(url)) for url in pool]
    await asyncio.gather(*tasks, return_exceptions=True)
    return results[:target], errors


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


async def _run_with_null_retry(
    agent,
    prompt: str,
    timeout_s: float,
    *,
    retries: int = _NULL_BODY_RETRIES,
    delay_s: float = _NULL_BODY_RETRY_DELAY_S,
) -> tuple:
    """Run an agent, retrying on Infomaniak null-body responses.

    Returns (output, messages). output is None on final failure.
    The retry loop sits outside asyncio.wait_for so each call gets its own
    timeout and the retry window is additive — no timeout budget conflict.
    """
    for attempt in range(retries + 1):
        with capture_run_messages() as messages:
            try:
                res = await asyncio.wait_for(agent.run(prompt), timeout=timeout_s)
                return res.output, messages
            except Exception as exc:
                if (
                    isinstance(exc, UnexpectedModelBehavior)
                    and _NULL_RESPONSE_MSG in str(exc)
                    and attempt < retries
                ):
                    logger.warning(
                        "null-body response (attempt %d/%d); retrying in %.0fs",
                        attempt + 1, retries + 1, delay_s,
                    )
                    await asyncio.sleep(delay_s)
                    continue
                if isinstance(exc, openai.RateLimitError) and attempt < retries:
                    header_val = exc.response.headers.get("retry-after")
                    try:
                        wait = float(header_val) if header_val else _RATE_LIMIT_RETRY_DELAY_S
                    except ValueError:
                        wait = _RATE_LIMIT_RETRY_DELAY_S
                    logger.warning(
                        "rate limit (attempt %d/%d); retrying in %.0fs",
                        attempt + 1, retries + 1, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.exception("Agent failed: %s", exc)
                for i, msg in enumerate(messages):
                    logger.error("Agent run message [%d]: %r", i, msg)
                return None, messages


async def _analyse_claim(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
    cfg: VerifyConfig,
    resolved_entity: ResolvedEntity | None = None,
    sub_questions: list[SubQuestion] | None = None,
) -> AnalystOutput | None:
    prompt = build_analyst_prompt(
        entity_name,
        claim_text,
        sources,
        resolved_entity=resolved_entity,
        sub_questions=sub_questions,
    )
    if resolved_entity is not None:
        with verdict_only_agent.override(model=resolve_model(cfg.model_for("analyst"))):
            verdict_assessment, _ = await _run_with_null_retry(
                verdict_only_agent, prompt, cfg.analyst_timeout_s
            )
        if verdict_assessment is None:
            return None
        entity_resolution = EntityResolution(
            entity_name=resolved_entity.entity_name,
            entity_type=resolved_entity.entity_type,
            entity_description=resolved_entity.entity_description,
            aliases=resolved_entity.aliases,
        )
        return AnalystOutput(entity=entity_resolution, verdict=verdict_assessment)
    else:
        with analyst_agent.override(model=resolve_model(cfg.model_for("analyst"))):
            output, _ = await _run_with_null_retry(analyst_agent, prompt, cfg.analyst_timeout_s)
        return output


async def _audit_claim(
    entity_name: str,
    claim_text: str,
    analyst_out: AnalystOutput,
    sources: list[dict],
    cfg: VerifyConfig,
) -> ComparisonResult | None:
    bundle = build_bundle(
        entity_name=analyst_out.entity.entity_name,
        entity_type=analyst_out.entity.entity_type,
        description=analyst_out.entity.entity_description,
        topics=analyst_out.verdict.topics,
        narrative=analyst_out.verdict.narrative,
        sources=sources,
    )

    prompt = build_auditor_prompt(bundle)

    with auditor_agent.override(model=resolve_model(cfg.model_for("auditor"))):
        assessment, _ = await _run_with_null_retry(auditor_agent, prompt, cfg.auditor_timeout_s)

    if assessment is None:
        return None

    return compare(
        analyst_out.verdict.verdict,
        analyst_out.verdict.confidence,
        assessment,
        bundle.claim_id,
        "(draft -- not yet saved)",
    )


async def research_claim(
    claim_text: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    sem: asyncio.Semaphore | None = None,
    resolved_entity: ResolvedEntity | None = None,
) -> VerificationResult:
    """Research a claim, persist sources/entity/claim to disk, and run auditor.

    Unlike verify_claim, this function:
    - Does not require an entity name (the analyst identifies it)
    - Writes source files to research/sources/
    - Creates entity file in research/entities/ if needed
    - Writes the claim file to research/claims/
    """
    from orchestrator.persistence import (
        _build_sources_consulted,
        _write_audit_sidecar,
        _write_claim_file,
        _write_entity_file,
        _write_source_files,
        verdict_write_kwargs,
    )

    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        cfg.repo_root = str(resolve_repo_root())

    gate = checkpoint or AutoApproveCheckpointHandler()
    _sem = sem if sem is not None else asyncio.Semaphore(cfg.llm_concurrency)
    repo_root = Path(cfg.repo_root)

    result = VerificationResult(
        entity="(pending)",
        claim_text=claim_text,
        urls_found=[],
        urls_ingested=[],
        urls_failed=[],
        sources=[],
        errors=[],
    )

    research_entity_hint = resolved_entity.entity_name if resolved_entity is not None else ""

    with bind_run_id(cfg.run_id):
        logger.info("research_claim entry: claim=%s", claim_text)
        async with httpx.AsyncClient() as client:
            # Step 1: Research
            progress("  › Searching", log=False)
            logger.info("Step 1/5: Searching for sources...")
            ro = await _research(client, research_entity_hint, claim_text, cfg, _sem, resolved_entity=resolved_entity)
            urls = ro.urls
            research_errors = ro.errors
            result.urls_found = urls
            result.research_trace = ro.trace
            result.sub_questions = ro.sub_questions
            result.queries_by_sub_question = ro.queries_by_sub_question

            result.errors.extend(e.message for e in research_errors)
            if not urls:
                result.errors.append(_NO_URLS_ERR)
                if any(e.error_type == "scorer_dropped_all" for e in research_errors):
                    result.blocked_reason = BlockedReason.INSUFFICIENT_SOURCES
                return result

            # Step 2: Ingest
            progress("  › Ingesting", log=False)
            logger.info("Step 2/5: Ingesting %d sources...", len(urls))
            url_index = build_source_url_index(repo_root)
            urls_to_ingest, cached_sources = _apply_url_dedup(urls, url_index, repo_root)

            remaining = max(0, cfg.max_sources - len(cached_sources))
            if remaining > 0:
                source_files, ingest_errors = await _ingest_urls(
                    client, urls_to_ingest, cfg, _sem,
                    target=remaining,
                    prefetched_bodies=ro.prefetched_bodies,
                )
            else:
                source_files, ingest_errors = [], []

            cached_map = {url: sid for url, sid, _ in cached_sources}

            for url, sid, sd in cached_sources:
                sd["addresses"] = list(ro.url_addresses.get(url, []))
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.cached_sources.append((url, sid, sd))

            for url, sf in source_files:
                sd = _build_source_dict(sf)
                sd["addresses"] = list(ro.url_addresses.get(url, []))
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.source_files.append((url, sf))

            ingested_set = set(result.urls_ingested)
            result.urls_failed = [u for u in urls if u not in ingested_set]
            all_errors = research_errors + ingest_errors

            result.sub_question_coverage = _invert_addresses(
                ro.sub_questions, ro.url_addresses, result.sources
            )

            # Checkpoint: review sources
            proceed = await gate.review_sources(
                urls_found=len(result.urls_found),
                urls_ingested=len(result.urls_ingested),
                errors=all_errors,
                sub_question_coverage=result.sub_question_coverage,
            )
            if not proceed:
                result.errors.append("Halted at source review checkpoint")
                return result

            # Threshold gate: persist any usable sources we did get and signal
            # blocked back to the caller. The Analyst is not invoked.
            if below_threshold(result.sources):
                if source_files:
                    _write_source_files(source_files, repo_root)
                _record_threshold_block(result, ingest_errors)
                return result

            # Step 3: Write sources to disk
            progress("  › Writing sources", log=False)
            logger.info("Step 3/5: Writing %d source files...", len(source_files))
            fresh_ids = _write_source_files(source_files, repo_root)
            fresh_map = {url: sid for (url, _sf), sid in zip(source_files, fresh_ids)}
            seen: set[str] = set()
            source_ids = []
            for url in urls:
                sid = cached_map.get(url) or fresh_map.get(url)
                if sid and sid not in seen:
                    source_ids.append(sid)
                    seen.add(sid)

            # Step 4: Analyse claim (analyst identifies entity)
            progress("  › Analysing", log=False)
            logger.info("Step 4/5: Analysing claim...")
            analyst_out = await _analyse_claim(
                None, claim_text, result.sources, cfg,
                resolved_entity=resolved_entity,
                sub_questions=result.sub_questions,
            )
            result.analyst_output = analyst_out

            if not analyst_out:
                result.errors.append("Analyst failed to produce an assessment")
                return result

            result.entity = analyst_out.entity.entity_name

            # Write entity and claim to disk
            # Skip when entity is pre-resolved (file already exists on disk).
            if resolved_entity is None:
                entity_ref = _write_entity_file(
                    entity_name=analyst_out.entity.entity_name,
                    entity_type=analyst_out.entity.entity_type,
                    entity_description=analyst_out.entity.entity_description,
                    repo_root=repo_root,
                    aliases=analyst_out.entity.aliases or None,
                )
            else:
                entity_ref = resolved_entity.entity_ref
            claim_slug = slugify(analyst_out.verdict.title)
            claim_path = _write_claim_file(
                title=analyst_out.verdict.title,
                entity_name=analyst_out.entity.entity_name,
                entity_ref=entity_ref,
                topics=analyst_out.verdict.topics,
                verdict=analyst_out.verdict.verdict,
                confidence=analyst_out.verdict.confidence,
                narrative=analyst_out.verdict.narrative,
                claim_slug=claim_slug,
                source_ids=source_ids,
                repo_root=repo_root,
                force=cfg.force_overwrite,
                seo_title=analyst_out.verdict.seo_title,
                takeaway=analyst_out.verdict.takeaway,
                **verdict_write_kwargs(analyst_out.verdict),
            )
            try:
                result.claim_path = str(claim_path.relative_to(Path(repo_root)))
            except ValueError:
                # Claim path lies outside repo_root (unusual but possible
                # in tests with mocked roots); fall back to the absolute path.
                result.claim_path = str(claim_path)

            # Step 5: Auditor check
            progress("  › Auditing", log=False)
            logger.info("Step 5/5: Running auditor check...")
            comparison = await _audit_claim(
                analyst_out.entity.entity_name, claim_text, analyst_out, result.sources, cfg
            )
            result.consistency = comparison

            # Write audit sidecar after auditor step
            sidecar_sources = _build_sources_consulted(
                result.source_files, cached_sources=result.cached_sources
            )
            agents_run = ["researcher", "ingestor", "analyst", "auditor"]
            _write_audit_sidecar(
                claim_path=claim_path,
                comparison=comparison,
                model=cfg.model,
                ran_at=datetime.datetime.now(datetime.timezone.utc),
                sources_consulted=sidecar_sources,
                agents_run=agents_run,
                models_used={a: cfg.model_for(a) for a in agents_run},
                research_trace=result.research_trace,
                sub_questions_block=_build_sub_questions_block(
                    result.sub_questions,
                    result.sub_question_coverage,
                    result.queries_by_sub_question,
                ),
            )

            # Checkpoint: review disagreement
            if comparison and comparison.needs_review:
                accept = await gate.review_disagreement(comparison)
                if not accept:
                    result.errors.append("Flagged for human review: analyst/auditor disagree")

    return result


_NO_URLS_ERR = "Researcher agent found no relevant URLs"


def _blocked_reason_label(
    reason_value: str,
    vr_errors: list[str],
    extra: str | None = None,
) -> str:
    """Format a BlockedReason value with the most informative upstream cause.

    Prefers ``extra`` if provided, otherwise the first non-noise message
    from ``vr_errors``, otherwise the first error, otherwise the bare
    reason. The "no relevant URLs" string is treated as noise because it
    is downstream of the real cause (planner timeout, search failure,
    etc.) and obscures it.
    """
    cause = extra
    if cause is None:
        non_noise = [e for e in vr_errors if not e.startswith(_NO_URLS_ERR)]
        cause = non_noise[0] if non_noise else (vr_errors[0] if vr_errors else None)
    return f"{reason_value}: {cause}" if cause else reason_value


@dataclass
class OnboardResult:
    """Summary of an entity onboarding run."""

    entity_name: str
    entity_type: str
    status: Literal["accepted", "rejected"]
    entity_ref: str | None
    claims_created: list[str] = field(default_factory=list)
    claims_skipped: list[str] = field(default_factory=list)
    claims_failed: list[str] = field(default_factory=list)
    # Each entry is (relative_claim_path, reason_label). reason_label is the
    # BlockedReason value plus the upstream cause when available, e.g.
    # "analyst_error: research planner timed out".
    claims_blocked: list[tuple[str, str]] = field(default_factory=list)
    templates_applied: list[str] = field(default_factory=list)
    templates_excluded: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _screen_templates(
    entity_description: str,
    templates: list,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Screen templates for applicability. MVP: all core templates pass."""
    applicable = [t.slug for t in templates]
    excluded: list[tuple[str, str]] = []
    return applicable, excluded


def _wrong_entity_source(
    source_url: str | None, entity_website: str | None
) -> bool:
    """True when the source URL's registered domain differs from the canonical."""
    if not (entity_website and source_url):
        return False
    canon = normalised_host(entity_website)
    src = normalised_host(source_url)
    if not (canon and src):
        return False
    return canon != src and not src.endswith("." + canon)


class _EntityDescription(BaseModel):
    description: str = Field(
        description="One sentence describing the organization (not the webpage)."
    )


_ENTITY_DESCRIPTION_INSTRUCTIONS = """\
You rewrite a webpage summary into a one-sentence description of the organization the page is about.

Rules:
- Output a single sentence.
- The subject is the organization, not the webpage. Do not start with "Landing page", "Homepage", "Website", etc.
- Preserve concrete facts from the source (what the organization does, key products or focus). Do not invent new facts.
- If the source summary does not actually describe an organization, return an empty string.
"""


_entity_description_agent = Agent(
    "test",
    output_type=_EntityDescription,
    system_prompt=_ENTITY_DESCRIPTION_INSTRUCTIONS,
    retries=1,
)


async def _tighten_entity_description(
    description: str,
    entity_name: str,
    source_url: str | None,
    entity_website: str | None,
    cfg: VerifyConfig,
) -> str:
    """Rewrite the source-derived summary into a one-sentence org description.

    Blanks the description when the source URL belongs to a different registered
    domain than the canonical website (a wrong-entity blurb is worse than none).
    Otherwise calls a small LLM to recast the page summary as an organization
    description; falls back to the raw summary if the call fails.
    """
    description = (description or "").strip()
    if not description:
        return ""
    if _wrong_entity_source(source_url, entity_website):
        logger.info(
            "Onboard: source domain mismatches canonical website; blanking description"
        )
        return ""
    prompt = f"Entity name: {entity_name}\nWebpage summary: {description}"
    try:
        with _entity_description_agent.override(model=resolve_model(cfg.model_for("ingestor"))):
            res = await asyncio.wait_for(
                _entity_description_agent.run(prompt),
                timeout=cfg.research_timeout_s,
            )
        rewritten = (res.output.description or "").strip()
        return rewritten or description
    except Exception as exc:
        logger.warning("Entity description rewrite failed (%s); using raw summary", exc)
        return description


async def _probe_collision_suggestions(
    client: httpx.AsyncClient,
    entity_name: str,
    entity_website: str | None,
) -> list[str]:
    """Probe Brave for the bare entity name; suggest exclude domains on collision.

    Skipped (returns []) when there is no canonical website to compare against.
    Returns up to 3 distinct registered domains that appear in the top results
    and don't match the canonical. Failures are non-fatal: the probe is best-
    effort disambiguation, not a gate.
    """
    if not entity_website:
        return []
    canon = normalised_host(entity_website)
    if not canon:
        return []
    try:
        from researcher.agent import search_brave
        results = await search_brave(client, entity_name, max_results=8)
    except Exception as exc:
        logger.warning("Collision probe failed: %s", exc)
        return []
    counts: Counter[str] = Counter()
    for r in results[:5]:
        host = normalised_host(r.get("url", "") or "")
        if not host:
            continue
        if host == canon or host.endswith("." + canon):
            continue
        counts[host] += 1
    suggestions = [host for host, _ in counts.most_common(3)]
    if suggestions:
        logger.info(
            "Collision probe for %r: canonical=%s, suggesting excludes=%s",
            entity_name, canon, suggestions,
        )
    return suggestions


def _merge_search_hints(
    cli_include: list[str] | None,
    cli_exclude: list[str] | None,
    probe_excludes: list[str],
) -> SearchHints | None:
    """Combine operator-supplied + probe-suggested hints.

    Returns None when nothing is set so the entity frontmatter can omit the key.
    Order is preserved per source; duplicates dropped.
    """
    include = _dedup(cli_include or [])
    exclude = _dedup((cli_exclude or []) + list(probe_excludes))
    if not include and not exclude:
        return None
    return SearchHints(include=include, exclude=exclude)


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        s = item.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


async def onboard_entity(
    entity_name: str,
    entity_type: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    seed_url: str | None = None,
    only: list[str] | None = None,
    entity_ref: str | None = None,
    search_hints_include: list[str] | None = None,
    search_hints_exclude: list[str] | None = None,
) -> OnboardResult:
    """Onboard an entity by running claim templates through the research pipeline.

    1. Light research to gather entity context
    2. Screen templates (deterministic MVP, LLM screening TBD)
    3. Checkpoint for operator review
    4. Per-template research pipeline (sequential; parallelism TBD per orchestrator config)
    5. Write entity file
    6. Return OnboardResult summary
    """
    from orchestrator.persistence import (
        _build_sources_consulted,
        _claim_dir_for,
        _write_audit_sidecar,
        _write_claim_file,
        _write_draft_entity_file,
        _write_entity_file,
        _write_source_files,
        verdict_write_kwargs,
    )

    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        cfg.repo_root = str(resolve_repo_root())

    gate = checkpoint or AutoApproveCheckpointHandler()
    repo_root = Path(cfg.repo_root)
    et = EntityType(entity_type)
    # One semaphore shared across light research AND all per-template verify_claim calls.
    sem = asyncio.Semaphore(cfg.llm_concurrency)

    result = OnboardResult(
        entity_name=entity_name,
        entity_type=entity_type,
        status="accepted",
        entity_ref=None,
    )

    with bind_run_id(cfg.run_id):
        logger.info(
            "onboard_entity entry: name=%s type=%s seed_url=%s",
            entity_name,
            entity_type,
            seed_url,
        )

        # Step 1: Light research for entity context
        hr()
        logger.info("Onboard step 1: light research for %s", entity_name)
        entity_description = ""
        entity_website: str | None = None
        description_source_url: str | None = None
        probe_excludes: list[str] = []
        try:
            async with httpx.AsyncClient() as client:
                if seed_url:
                    _url = seed_url if seed_url.startswith(("http://", "https://")) else f"https://{seed_url}"
                    entity_website = _url
                    logger.info("Onboard step 1: ingesting seed URL %s", _url)
                    source_files, _ = await _ingest_urls(client, [_url], cfg, sem)
                else:
                    query = f"{entity_name} official website"
                    light_ro = await _research(client, entity_name, query, cfg, sem)
                    urls = light_ro.urls
                    if urls:
                        entity_website = urls[0]
                    source_files, _ = (
                        await _ingest_urls(
                            client, urls[:1], cfg, sem,
                            prefetched_bodies=light_ro.prefetched_bodies,
                        )
                        if urls
                        else ([], [])
                    )
                if source_files:
                    src_url, sf = source_files[0]
                    entity_description = sf.frontmatter.summary or ""
                    description_source_url = src_url
                # Probe (Brave) and description rewrite (LLM) have no mutual
                # data dependency; run them concurrently.
                probe_excludes, entity_description = await asyncio.gather(
                    _probe_collision_suggestions(client, entity_name, entity_website),
                    _tighten_entity_description(
                        entity_description, entity_name,
                        description_source_url, entity_website, cfg,
                    ),
                )
        except Exception as exc:
            logger.warning("Light research failed: %s", exc)

        merged_search_hints = _merge_search_hints(
            search_hints_include, search_hints_exclude, probe_excludes,
        )
        if probe_excludes:
            progress(
                "Name-collision probe suggested excludes: %s",
                ", ".join(probe_excludes),
            )

        # Step 2: Template screening
        hr()
        logger.info("Onboard step 2: screening templates")
        all_templates = load_templates(repo_root)
        typed_templates = templates_for_entity_type(all_templates, entity_type)

        if not typed_templates:
            result.errors.append(f"No core templates found for entity_type={entity_type}")
            result.status = "rejected"
            return result

        applicable_slugs, excluded = _screen_templates(entity_description, typed_templates)

        if only:
            unknown = [s for s in only if s not in {t.slug for t in typed_templates}]
            if unknown:
                result.errors.append(
                    f"Unknown template slug(s) for entity_type={entity_type}: {', '.join(unknown)}"
                )
                result.status = "rejected"
                return result
            applicable_slugs = [s for s in applicable_slugs if s in set(only)]

        result.templates_excluded = excluded

        # Step 3: Checkpoint
        hr()
        logger.info("Onboard step 3: checkpoint review")
        decision = await gate.review_onboard(
            entity_name, entity_type, applicable_slugs, excluded,
            entity_description=entity_description,
        )

        if decision == "reject":
            result.status = "rejected"
            draft_ref = _write_draft_entity_file(
                entity_name=entity_name,
                entity_type=et,
                entity_description=entity_description,
                repo_root=repo_root,
                website=entity_website,
                search_hints=merged_search_hints,
            )
            result.entity_ref = draft_ref
            return result

        if isinstance(decision, list):
            applicable_slugs = decision

        result.templates_applied = applicable_slugs

        if entity_ref is None:
            entity_ref = _write_entity_file(
                entity_name=entity_name,
                entity_type=et,
                entity_description=entity_description,
                repo_root=repo_root,
                website=entity_website,
                search_hints=merged_search_hints,
            )
        result.entity_ref = entity_ref

        # Without this resolved entity, the just-persisted search_hints would
        # not reach the per-template researcher on the run that wrote them.
        onboard_resolved_entity = ResolvedEntity(
            entity_ref=entity_ref,
            entity_name=entity_name,
            entity_type=et,
            entity_description=entity_description,
            website=entity_website,
            search_hints=merged_search_hints,
        )

        # Step 5: Per-template research pipeline. Each template gets its own
        # run_id so the per-claim agent runs (researcher/ingestor/analyst/
        # auditor) in verify_claim group cleanly under one id. Token-usage
        # records inherit this id via cfg.run_id.
        onboard_url_index = build_source_url_index(repo_root)
        total = len(applicable_slugs)
        hr()
        logger.info("Onboard step 4: per-template research (%d templates)", total)
        for idx, slug in enumerate(applicable_slugs, 1):
            iter_cfg = dataclasses.replace(cfg, run_id=new_run_id())
            with bind_run_id(iter_cfg.run_id):
                progress("[%d/%d] Researching: %s ...", idx, total, slug, glyph="▶")
                template = get_template(all_templates, slug)
                if not template:
                    progress("[%d/%d] ERROR: template not found: %s", idx, total, slug)
                    # Invariant: every entry in result.claims_failed must
                    # have at least one matching entry in result.errors of
                    # the form f"{slug}: <reason>". The CLI renders them as
                    # a unified "Failed:" block; an unattributed failure
                    # would silently disappear from operator output.
                    result.errors.append(f"{slug}: template not found")
                    result.claims_failed.append(slug)
                    continue

                claim_text = render_claim_text(template, entity_name)
                logger.info("Onboard: researching template %s -> %s", slug, claim_text)

                # Skip before running the pipeline if a claim file already
                # exists for this entity + criterion. Avoids duplicate claims
                # and wasted pipeline compute on re-onboards.
                existing_claim_path = (
                    _claim_dir_for(entity_ref, entity_name, repo_root) / f"{slugify(slug)}.md"
                )
                if existing_claim_path.exists() and not iter_cfg.force_overwrite:
                    progress("[%d/%d] Skipped (exists): %s", idx, total, slug)
                    result.claims_skipped.append(str(existing_claim_path.relative_to(repo_root)))
                    continue

                try:
                    vr = await verify_claim(
                        entity_name, claim_text, iter_cfg, gate,
                        sem=sem, url_index=onboard_url_index,
                        resolved_entity=onboard_resolved_entity,
                    )

                    if vr.errors:
                        result.errors.extend(f"{slug}: {e}" for e in vr.errors)

                    # Threshold-blocked branch: persist a placeholder claim
                    # file with status='blocked' so the operator can see
                    # (and later re-run or archive) the halted work.
                    # Sources that did ingest are still written out.
                    if vr.blocked_reason is not None:
                        source_ids = (
                            _write_source_files(vr.source_files, repo_root)
                            if vr.source_files
                            else []
                        )
                        try:
                            inherited_topics = [Category(t) for t in template.topics]
                        except ValueError:
                            inherited_topics = []
                        blocked_body = (
                            f"This claim is blocked: `{vr.blocked_reason.value}`. "
                            f"The pipeline halted before the Analyst could produce a "
                            f"verdict. Re-run the pipeline once more usable sources "
                            f"are available, or archive this claim if it cannot be "
                            f"verified.\n"
                        )
                        blocked_path = _write_claim_file(
                            title=render_blocked_title(template, entity_name),
                            entity_name=entity_name,
                            entity_ref=entity_ref,
                            topics=inherited_topics,
                            verdict=Verdict.UNVERIFIED,
                            confidence=Confidence.LOW,
                            narrative=blocked_body,
                            claim_slug=slug,
                            source_ids=source_ids,
                            repo_root=repo_root,
                            force=iter_cfg.force_overwrite,
                            status="blocked",
                            blocked_reason=vr.blocked_reason,
                            criteria_slug=slug,
                        )
                        reason_label = _blocked_reason_label(vr.blocked_reason.value, vr.errors)
                        result.claims_blocked.append((str(blocked_path.relative_to(repo_root)), reason_label))
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=_build_sources_consulted(
                                vr.source_files, cached_sources=vr.cached_sources
                            ),
                            agents_run=["researcher", "ingestor"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor"]},
                            research_trace=vr.research_trace,
                            sub_questions_block=_build_sub_questions_block(
                                vr.sub_questions,
                                vr.sub_question_coverage,
                                vr.queries_by_sub_question,
                            ),
                        )
                        progress(
                            "[%d/%d] Blocked: %s (%s)",
                            idx,
                            total,
                            slug,
                            reason_label,
                        )
                        continue

                    # Analyst-failure branch: persist a placeholder so the
                    # operator has a discoverable artifact to re-run or archive.
                    if not vr.analyst_output:
                        source_ids = (
                            _write_source_files(vr.source_files, repo_root)
                            if vr.source_files
                            else []
                        )
                        try:
                            inherited_topics = [Category(t) for t in template.topics]
                        except ValueError:
                            inherited_topics = []
                        blocked_body = (
                            f"This claim is blocked: `{BlockedReason.ANALYST_ERROR.value}`. "
                            f"The Analyst agent failed to produce a valid assessment after "
                            f"exhausting retries. Re-run the pipeline to attempt again, "
                            f"or archive this claim if it consistently fails.\n"
                        )
                        blocked_path = _write_claim_file(
                            title=render_blocked_title(template, entity_name),
                            entity_name=entity_name,
                            entity_ref=entity_ref,
                            topics=inherited_topics,
                            verdict=Verdict.UNVERIFIED,
                            confidence=Confidence.LOW,
                            narrative=blocked_body,
                            claim_slug=slug,
                            source_ids=source_ids,
                            repo_root=repo_root,
                            force=iter_cfg.force_overwrite,
                            status="blocked",
                            blocked_reason=BlockedReason.ANALYST_ERROR,
                            criteria_slug=slug,
                        )
                        reason_label = _blocked_reason_label(BlockedReason.ANALYST_ERROR.value, vr.errors)
                        result.claims_blocked.append((str(blocked_path.relative_to(repo_root)), reason_label))
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=_build_sources_consulted(vr.source_files, cached_sources=vr.cached_sources),
                            agents_run=["researcher", "ingestor", "analyst"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor", "analyst"]},
                            research_trace=vr.research_trace,
                            sub_questions_block=_build_sub_questions_block(
                                vr.sub_questions,
                                vr.sub_question_coverage,
                                vr.queries_by_sub_question,
                            ),
                        )
                        progress(
                            "[%d/%d] Blocked: %s (%s)",
                            idx,
                            total,
                            slug,
                            reason_label,
                        )
                        continue

                    ao = vr.analyst_output
                    title_ok, title_reason = validate_analyst_title(template, entity_name, ao.verdict.title)
                    if not title_ok:
                        source_ids = (
                            _write_source_files(vr.source_files, repo_root)
                            if vr.source_files
                            else []
                        )
                        try:
                            inherited_topics = [Category(t) for t in template.topics]
                        except ValueError:
                            inherited_topics = []
                        blocked_body, extra_label = blocked_title_message(
                            template, ao.verdict.title, title_reason, BlockedReason.ANALYST_ERROR.value
                        )
                        blocked_path = _write_claim_file(
                            title=render_blocked_title(template, entity_name),
                            entity_name=entity_name,
                            entity_ref=entity_ref,
                            topics=inherited_topics,
                            verdict=Verdict.UNVERIFIED,
                            confidence=Confidence.LOW,
                            narrative=blocked_body,
                            claim_slug=slug,
                            source_ids=source_ids,
                            repo_root=repo_root,
                            force=iter_cfg.force_overwrite,
                            status="blocked",
                            blocked_reason=BlockedReason.ANALYST_ERROR,
                            criteria_slug=slug,
                        )
                        reason_label = _blocked_reason_label(BlockedReason.ANALYST_ERROR.value, vr.errors, extra=extra_label)
                        result.claims_blocked.append((str(blocked_path.relative_to(repo_root)), reason_label))
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=_build_sources_consulted(vr.source_files, cached_sources=vr.cached_sources),
                            agents_run=["researcher", "ingestor", "analyst"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor", "analyst"]},
                            research_trace=vr.research_trace,
                            sub_questions_block=_build_sub_questions_block(
                                vr.sub_questions,
                                vr.sub_question_coverage,
                                vr.queries_by_sub_question,
                            ),
                        )
                        progress(
                            "[%d/%d] Blocked: %s (%s)",
                            idx,
                            total,
                            slug,
                            reason_label,
                        )
                        continue

                    # Write sources (reuse verify_claim's already-ingested sources)
                    source_ids = _write_source_files(vr.source_files, repo_root) if vr.source_files else []

                    # Write claim file. The claim inherits the source
                    # criterion's full `topics` set by default (per
                    # docs/plans/multi-topic.md §"Pipeline output"). The
                    # operator can hand-edit a claim's topics
                    # post-pipeline if specialization is needed.
                    try:
                        inherited_topics = [Category(t) for t in template.topics]
                    except ValueError as exc:
                        logger.warning(
                            "Template %s has invalid topic; falling back to analyst topics: %s",
                            slug,
                            exc,
                        )
                        inherited_topics = list(ao.verdict.topics)

                    claim_path = _write_claim_file(
                        title=ao.verdict.title,
                        entity_name=entity_name,
                        entity_ref=entity_ref,
                        topics=inherited_topics,
                        verdict=ao.verdict.verdict,
                        confidence=ao.verdict.confidence,
                        narrative=ao.verdict.narrative,
                        claim_slug=slug,
                        source_ids=source_ids,
                        repo_root=repo_root,
                        force=iter_cfg.force_overwrite,
                        criteria_slug=slug,
                        seo_title=ao.verdict.seo_title,
                        takeaway=ao.verdict.takeaway,
                        **verdict_write_kwargs(ao.verdict),
                    )
                    result.claims_created.append(str(claim_path.relative_to(repo_root)))

                    # Write audit sidecar after auditor step
                    sidecar_sources = _build_sources_consulted(vr.source_files, cached_sources=vr.cached_sources)
                    agents_run = ["researcher", "ingestor", "analyst", "auditor"]
                    _write_audit_sidecar(
                        claim_path=claim_path,
                        comparison=vr.consistency,
                        model=iter_cfg.model,
                        ran_at=datetime.datetime.now(datetime.timezone.utc),
                        sources_consulted=sidecar_sources,
                        agents_run=agents_run,
                        models_used={a: iter_cfg.model_for(a) for a in agents_run},
                        research_trace=vr.research_trace,
                        sub_questions_block=_build_sub_questions_block(
                            vr.sub_questions,
                            vr.sub_question_coverage,
                            vr.queries_by_sub_question,
                        ),
                    )

                    progress("[%d/%d] Done: %s", idx, total, slug)
                except Exception as exc:
                    progress("[%d/%d] FAILED: %s: %s", idx, total, slug, exc)
                    logger.error("Template %s failed: %s", slug, exc)
                    result.errors.append(f"{slug}: {exc}")
                    result.claims_failed.append(slug)

    return result
