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
import traceback
from collections import Counter
from collections.abc import Container
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
from analyst.agent import EntityResolution, SourceOverride
from analyst.citations import cited_source_ids, clean_citations
from orchestrator.entity_resolution import ResolvedEntity, SearchHints, entity_identity_for, parse_entity_ref
from auditor.agent import auditor_agent, build_auditor_prompt
from common.blocklist import normalised_host, filter_urls, load_blocklist
from common.canonical_url import canonical_key
from common.content_loader import resolve_repo_root
from common.logging_setup import bind_run_id, hr, new_run_id, progress, run_id_var
from common.models import BlockedReason, Category, Confidence, EntityType, Independence, Verdict
from common.templates import TemplateRecord, blocked_title_message, get_template, load_templates, render_blocked_title, render_claim_text, templates_for_entity_type, validate_analyst_title
from common.timeouts import ingest_budget_with_wayback_s
from common.utils import host_matches, slug_from_url, slugify, url_host
from auditor.bundle import build_bundle
from auditor.compare import compare, needs_review_reasons
from auditor.models import ComparisonResult
from common.models import DEFAULT_MODEL, AgentName, FailureInfo, FailureStep, resolve_model
from ingestor.agent import (
    IngestorDeps,
    archive_after_ingest,
    fetch_failure_reason,
    ingestor_agent,
    requested_page_text,
)
from ingestor.arxiv_affiliation import arxiv_corporate_lab
from ingestor.models import SourceFile
from ingestor.validation import drop_unfound_quotes, validate_source_file
from ingestor.tools.web_fetch import TerminalFetchError
from orchestrator.checkpoints import AutoApproveCheckpointHandler, CheckpointHandler, StepError
from common.models import SubQuestion
from common.source_classification import (
    classify_source_type,
    EntityIdentity,
    entity_affiliated,
    entity_first_party_reason,
    independence_for_source_type,
    SHARED_PLATFORM_HOSTS,
    profile_url_names_entity,
    publisher_named_in_claim,
    source_engages_entity,
)
from orchestrator.persistence import build_source_url_index, load_source_dict, resolve_source_slugs, shorten
from researcher.decomposed import ResearchOutput

logger = logging.getLogger(__name__)

_NULL_RESPONSE_MSG = "Invalid response from"
_NULL_BODY_RETRIES = 2
_NULL_BODY_RETRY_DELAY_S = 45.0
_RATE_LIMIT_RETRY_DELAY_S = 90.0


def _failure_from_exc(
    exc: BaseException,
    *,
    step: FailureStep,
    agent: str | None,
    model: str | None,
    timeout_s: float | None,
) -> FailureInfo:
    """Build a FailureInfo from an exception, capturing a short traceback head."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    head_lines = tb.splitlines()[:12]
    return FailureInfo(
        step=step,
        agent=agent,
        model=model,
        error_class=type(exc).__name__,
        error_message=str(exc) or type(exc).__name__,
        timeout_s=timeout_s,
        traceback_head="\n".join(head_lines) if head_lines else None,
    )


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
    # First fatal agent failure observed during the run, if any. Persisted to
    # the audit sidecar (pipeline_run.failure) so blocked runs can be triaged
    # without grepping logs.
    failure: FailureInfo | None = Field(default=None, exclude=True)
    # Requested URL -> URL its live fetch ended on, for fresh sources.
    final_urls: dict[str, str] = Field(default_factory=dict, exclude=True)
    # Requested URL -> archive lookup record, for fresh sources.
    archive: dict[str, dict] = Field(default_factory=dict, exclude=True)
    # Ingested URLs (cached or fresh) of sources the analyst did not cite;
    # kept out of the claim's ``sources:`` and not written. Keyed by URL so
    # a slug renamed at write time cannot desync it.
    uncited_urls: set[str] = Field(default_factory=set, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @computed_field
    @property
    def cached_source_ids(self) -> list[str]:
        return [sid for _url, sid, _sd in self.cached_sources]

    def sources_consulted(self) -> list[dict]:
        """The audit sidecar's ``sources_consulted`` block for this run."""
        from orchestrator.persistence import _build_sources_consulted

        return _build_sources_consulted(
            self.source_files, cached_sources=self.cached_sources, archive=self.archive
        )

    def persist_sources(self, repo_root: Path, url_index: dict[str, str] | None = None) -> list[str]:
        """Write the fresh sources and return every source id for the claim.

        Sources in ``uncited_urls`` are neither written nor returned. A
        cached and a fresh source can still name the same file, so each id
        appears once. ``url_index`` gains the written sources under the
        requested, stored and redirect-target URLs, so later claims in the
        same run reuse them instead of fetching again.
        """
        from orchestrator.persistence import _write_source_files

        to_write = [(url, sf) for url, sf in self.source_files if url not in self.uncited_urls]
        fresh_ids = _write_source_files(to_write, repo_root)
        if url_index is not None:
            for (url, sf), sid in zip(to_write, fresh_ids):
                url_index.setdefault(canonical_key(url), sid)
                url_index.setdefault(canonical_key(sf.frontmatter.url), sid)
                if url in self.final_urls:
                    url_index.setdefault(canonical_key(self.final_urls[url]), sid)
        cached_ids = [
            sid for url, sid, _sd in self.cached_sources if url not in self.uncited_urls
        ]
        return list(dict.fromkeys(cached_ids + fresh_ids))


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
    # False when the run writes nothing (``dr claim-probe``): archive lookups
    # check TimeGate only and never ask Save Page Now to capture a page.
    allow_save: bool = True
    # Per-claim list of acquisition origins to attempt during research.
    # Default ['tavily', 'arxiv']; Brave remains available via search_backend
    # for per-query fallback. arXiv only fires when the claim's topics
    # intersect ACADEMIC_TOPICS (see _select_research_origins). Values mirror
    # the schema enum on audit.sources_consulted[].acquisition.origin.
    research_origins: list[str] = field(default_factory=lambda: ["tavily", "arxiv"])
    # Search backend used by the decomposed researcher's `execute_searches`
    # step. Today: 'tavily' (default) or 'brave'. Read once from
    # RESEARCH_SEARCH_BACKEND at construction time; tests can override by
    # passing `search_backend=...` directly. Unknown values fall back to
    # 'brave' with a warning logged in `execute_searches`.
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


def _cfg_repo_root(cfg: VerifyConfig) -> Path:
    return Path(cfg.repo_root) if cfg.repo_root else resolve_repo_root()


async def verify_claim(
    entity_name: str,
    claim_text: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    sem: asyncio.Semaphore | None = None,
    resolved_entity: ResolvedEntity | None = None,
    url_index: dict[str, str] | None = None,
    topics: list[str] | None = None,
    template: TemplateRecord | None = None,
) -> VerificationResult:
    """Run the full verification pipeline.

    1. Researcher: search for relevant sources
    2. Ingestor: fetch and structure each source
    3. [Checkpoint] Review sources before analysis
    4. Analyst: synthesize sources into a claim with verdict
    5. Auditor: independently assess the claim
    6. [Checkpoint on disagreement] Review conflict

    ``template`` is the criterion a template-backed caller rendered
    ``claim_text`` from; it decides which statement the auditor grades
    (``_graded_statement``) and supplies the analyst's criterion notes.

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
            ro = await _research(
                client, research_entity, claim_text, cfg, _sem,
                resolved_entity=resolved_entity, topics=topics,
            )
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
            repo_root = _cfg_repo_root(cfg)
            if url_index is None:
                url_index = build_source_url_index(repo_root)
            urls_to_ingest, cached_sources = _apply_url_dedup(urls, url_index, repo_root)

            source_files, ingest_errors, notes = await _ingest_claim_sources(
                client, urls_to_ingest, cached_sources, ro, result, cfg, _sem,
                url_index, repo_root,
            )

            for url, sid, sd in cached_sources:
                sd["addresses"] = _addresses_with_aliases(url, ro.url_addresses, notes.aliases)
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.cached_sources.append((url, sid, sd))

            for url, sf in source_files:
                sd = _build_source_dict(sf)
                sd["addresses"] = _addresses_with_aliases(url, ro.url_addresses, notes.aliases)
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.source_files.append((url, sf))

            ingested_set = set(result.urls_ingested) | set(notes.aliases)
            result.urls_failed = [u for u in urls if u not in ingested_set]
            all_errors = research_errors + ingest_errors

            # Build per-sub-question coverage from the post-ingest source set.
            # Inverts url -> [sq_id] into sq_id -> [source_id]; sub-questions
            # with zero addressing sources keep an empty list to surface the
            # gap to the analyst and the audit sidecar.
            result.sub_question_coverage = _invert_addresses(
                ro.sub_questions, result.sources
            )
            _warn_uncovered(ro.sub_questions, result.sub_question_coverage)

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
            # One value for both agents: the Evaluator must judge against the
            # same notes the analyst followed.
            criterion_notes = template.notes if template else None
            analyst_out, analyst_failure = await _analyse_claim(
                entity_name, claim_text, result.sources, cfg,
                resolved_entity=resolved_entity,
                sub_questions=result.sub_questions,
                repo_root=repo_root,
                criterion_notes=criterion_notes,
            )
            result.analyst_output = analyst_out

            if not analyst_out:
                result.errors.append("Analyst failed to produce an assessment")
                if analyst_failure is not None and result.failure is None:
                    result.failure = analyst_failure
                if cfg.show_progress:
                    progress("  ! analyst failed to produce an assessment")
                return result

            # Step 4: Auditor
            statement = _graded_statement(
                template, entity_name, claim_text, analyst_out.verdict.title
            )
            if statement is None:
                # The caller blocks this claim, and a blocked claim lists every
                # ingested source: no cited filter from a rejected analyst output.
                say("  › Auditor skipped: the title fails the template, so the claim will be blocked")
                logger.info("Step 4/4: Auditor skipped; analyst title fails template %s", template.slug)
                comparison = None
            else:
                cited_sources = _apply_cited_filter(result, analyst_out, entity_name)
                say("  › Auditing")
                logger.info("Step 4/4: Running auditor check...")
                comparison = await _audit_claim(
                    entity_name, statement, analyst_out, cited_sources, cfg,
                    criterion_notes=criterion_notes,
                )
            result.consistency = comparison

            # Checkpoint: review disagreement
            if comparison and comparison.needs_review:
                accept = await gate.review_disagreement(comparison)
                if not accept:
                    reasons = ", ".join(needs_review_reasons(comparison))
                    result.errors.append(f"Flagged for human review: {reasons}")
                    if cfg.show_progress:
                        progress("  ! flagged for review: %s", reasons)

            if cfg.show_progress:
                progress("Pipeline complete.")

    return result


def _apply_entity_match(
    sources: list[dict],
    resolved_entity: ResolvedEntity,
    repo_root: Path,
    claim_text: str = "",
) -> list[SourceOverride]:
    """Relabel sources in place for this claim's entity; return the overrides.

    A source's file-level ``independence`` is entity-agnostic (a brave.com
    page can be independent evidence on an AWS claim), so the correction is
    per claim: the analyst sees the corrected label, and the returned
    overrides are recorded on the claim's ``source_overrides`` so the site's
    source counts agree with the level.

    - The entity's own source (``entity_first_party_reason``) is ``first-party``.
    - Any other ``first-party`` source is another organization's self-report.
      It stays ``first-party`` when the claim names its publisher (a provider
      the entity relies on), or when it names the entity and looks published
      by the entity or its parent on another host or under another name
      (``entity_affiliated``: Anthropic's platform.claude.com docs on a Claude
      claim). Otherwise it becomes ``unknown``, even when it mentions the
      entity.
    - Any other ``independent`` source stays ``independent`` only when it
      names the entity (``source_engages_entity``) or the claim names its
      publisher; otherwise it becomes ``unknown``.
    - ``unknown`` sources are left alone.

    A subject entity is a topic, not an organization, so only the first
    rule applies to it.
    """
    identity = entity_identity_for(resolved_entity, repo_root)
    entity_name = shorten(resolved_entity.entity_name)
    check_off_entity = resolved_entity.entity_type != EntityType.SUBJECT
    overrides: list[SourceOverride] = []
    for sd in sources:
        label = sd.get("independence")
        publisher = sd.get("publisher") or ""
        url = sd.get("url") or ""
        reason = entity_first_party_reason(publisher, url, identity)
        if reason is not None:
            if label == Independence.FIRST_PARTY.value:
                continue
            new_label, note = Independence.FIRST_PARTY, f"Entity match: {reason}."
        elif not check_off_entity or publisher_named_in_claim(publisher, claim_text):
            continue
        elif label == Independence.FIRST_PARTY.value:
            if source_engages_entity(sd, identity) and entity_affiliated(publisher, url, identity):
                continue
            owner = publisher or url_host(url) or "another organization"
            new_label = Independence.UNKNOWN
            note = (
                f"Off-entity: first-party for {shorten(owner)}, not {entity_name}, "
                "and the claim does not name it."
            )
        elif label == Independence.INDEPENDENT.value and not source_engages_entity(sd, identity):
            new_label = Independence.UNKNOWN
            note = (
                f"Off-entity: the source does not mention {entity_name}, "
                "and the claim does not name its publisher."
            )
        else:
            continue
        sd["independence"] = new_label.value
        logger.info("%s -> %s (%s)", sd["source_id"], new_label.value, note)
        override = SourceOverride(source=sd["source_id"], independence=new_label, reason=note)
        override._code_relabel = True
        overrides.append(override)
    return overrides


def _merge_entity_overrides(
    verdict: VerdictAssessment, overrides: list[SourceOverride]
) -> None:
    """Add the entity-match overrides to the analyst's, one entry per source.

    The code's label beats the analyst's: an analyst override for the same
    source with a different ``independence`` is corrected rather than
    duplicated, and stays the analyst's for the cited filter. When they
    agree, the analyst's reason is kept.
    """
    if not overrides:
        return
    merged = list(verdict.source_overrides or [])
    by_source = {o.source: o for o in merged}
    for override in overrides:
        prior = by_source.get(override.source)
        if prior is None:
            merged.append(override)
        elif prior.independence != override.independence:
            prior.independence = override.independence
            prior.reason = override.reason
    verdict.source_overrides = merged


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
    sources: list[dict],
) -> dict[str, list[str]]:
    """Build a sq_id -> [source_id] map from the ingested sources' addresses.

    Sub-questions with no addressing source keep an empty list so the
    coverage gap is observable. ``sources`` is the post-ingest list of
    source dicts (cached + fresh combined); each carries ``source_id`` and
    the ``addresses`` of the researcher URL it came from.
    """
    coverage: dict[str, list[str]] = {sq.id: [] for sq in sub_questions}
    for sd in sources:
        sid = sd.get("source_id")
        if not sid:
            continue
        # Read ``addresses`` rather than re-looking up by ``url``: a cached
        # source's url is the one on disk, which can differ in form from the
        # researcher's URL.
        for sq_id in sd.get("addresses", []):
            if sq_id in coverage and sid not in coverage[sq_id]:
                coverage[sq_id].append(sid)
    return coverage


def _warn_uncovered(
    sub_questions: list[SubQuestion],
    coverage: dict[str, list[str]],
) -> None:
    """Log a warning for each sub-question that no ingested source addresses.

    The console shows warnings, so no separate progress line. Not a
    ``result.errors`` entry: the first such entry names a blocked claim's
    cause, and the sidecar's ``sub_questions[].citations: []`` already
    records the gap.
    """
    for sq in sub_questions:
        if not coverage.get(sq.id):
            logger.warning("sub-question %s has no ingested source: %s", sq.id, sq.question)


def _first_url_for(
    sq: str,
    urls: list[str],
    url_addresses: dict[str, list[str]],
    taken: Container[str],
) -> str | None:
    """The first URL in ``urls``, not in ``taken``, that addresses sub-question ``sq``."""
    return next((u for u in urls if u not in taken and sq in url_addresses.get(u, [])), None)


def _order_by_coverage(
    urls: list[str],
    url_addresses: dict[str, list[str]],
    sub_question_ids: list[str],
    current_counts: dict[str, int],
) -> list[str]:
    """Reorder ``urls`` so the sub-question with the fewest sources is filled first.

    Greedy: take the sub-question with the lowest projected count (ties by
    sub-question order), take its first untaken URL in input order, and add
    one to every sub-question that URL addresses. A thin sub-question's
    second URL also comes early, so a failed fetch of its first still leaves
    another near the front. URLs that address no known sub-question follow
    in input order.
    """
    projected = {sq: current_counts.get(sq, 0) for sq in sub_question_ids}
    taken: set[str] = set()
    ordered: list[str] = []
    while True:
        pick = None
        for sq in sorted(sub_question_ids, key=lambda q: projected[q]):
            pick = _first_url_for(sq, urls, url_addresses, taken)
            if pick is not None:
                break
        if pick is None:
            break
        taken.add(pick)
        ordered.append(pick)
        for sq in url_addresses.get(pick, []):
            if sq in projected:
                projected[sq] += 1
    return ordered + [u for u in urls if u not in taken]


def _coverage_pool(
    urls: list[str],
    url_addresses: dict[str, list[str]],
    sub_question_ids: list[str],
    size: int,
) -> list[str]:
    """The first ``size`` of ``urls``, except each sub-question's first two URLs always stay.

    Two, to match ``_order_by_coverage``, which tries a thin sub-question's
    second URL early in case the first fetch fails. The rest of the pool
    fills in input order, so a high-ranked URL that addresses no
    sub-question (a cached source, say) is not pushed out. The result keeps
    input order.
    """
    if len(urls) <= size:
        return list(urls)
    reserved: dict[str, None] = {}
    for _round in range(2):
        for sq in sub_question_ids:
            pick = _first_url_for(sq, urls, url_addresses, reserved)
            if pick is not None:
                reserved[pick] = None
    keep = set(list(reserved)[:size])
    for u in urls:
        if len(keep) >= size:
            break
        keep.add(u)
    return [u for u in urls if u in keep]


def _apply_blocklist_cap(
    raw_urls: list[str],
    cfg: VerifyConfig,
    errors: list[StepError] | None = None,
    url_addresses: dict[str, list[str]] | None = None,
    sub_question_ids: list[str] | None = None,
    identity: EntityIdentity | None = None,
    prefetched_bodies: dict[str, str] | None = None,
    trace: dict | None = None,
) -> tuple[list[str], list[StepError]]:
    """Filter raw_urls through the blocklist, cap at candidate_pool_size, and
    append blocked_host / all_blocked errors. Returns (kept_urls, error_list).

    With sub-questions, the cap keeps each sub-question's first two URLs
    (``_coverage_pool``), so they stay in the pool even when they rank low.

    A blocklisted URL that is the entity's own profile post
    (``profile_url_names_entity``) and has non-empty page text in
    ``prefetched_bodies`` is kept and listed under ``trace["blocklist_spared"]``.
    """
    out_errors: list[StepError] = list(errors) if errors else []
    repo_root_str = cfg.repo_root or str(resolve_repo_root())
    entries = load_blocklist(Path(repo_root_str))
    kept, dropped = filter_urls(raw_urls, entries)
    spared_records: list[dict[str, str]] = []
    if identity is not None and dropped:
        # Blocklist entries exist because those hosts refuse anonymous fetches;
        # with the search's page text in hand no fetch is needed, and the
        # entity's own post may be its only first-party statement.
        bodies = prefetched_bodies or {}
        spared = [
            d for d in dropped
            if (bodies.get(d.url) or "").strip() and profile_url_names_entity(d.url, identity)
        ]
        if spared:
            spared_records = [
                {
                    "url": d.url,
                    "host": d.host,
                    "reason": f"entity's own {d.host} post; page text came with the search result",
                }
                for d in spared
            ]
            logger.info("Blocklist spared the entity's own post(s): %s", [d.url for d in spared])
            spared_urls = {d.url for d in spared}
            dropped = [d for d in dropped if d.url not in spared_urls]
            kept_set = set(kept) | spared_urls
            kept = [u for u in raw_urls if u in kept_set]
    urls = _coverage_pool(
        kept, url_addresses or {}, sub_question_ids or [], cfg.candidate_pool_size
    )
    if spared_records and trace is not None:
        # The cap can still cut a spared post; the sidecar lists only posts that reached the pool.
        in_pool = [r for r in spared_records if r["url"] in urls]
        if in_pool:
            trace["blocklist_spared"] = in_pool
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

    ``url_index`` is keyed by ``canonical_key`` (see
    ``build_source_url_index``), so ``www.``, trailing-slash and
    tracking-param variants match the file on disk.

    Returns (to_ingest, cached) where cached is a list of
    (url, source_id, source_dict) triples.
    """
    to_ingest: list[str] = []
    cached: list[tuple[str, str, dict]] = []
    for url in urls:
        source_id = url_index.get(canonical_key(url))
        if source_id:
            sd = load_source_dict(source_id, repo_root)
            if sd is not None:
                logger.info("dedup-hit: %s -> %s", url, source_id)
                cached.append((url, source_id, sd))
                continue
        to_ingest.append(url)
    return to_ingest, cached


@dataclass
class IngestNotes:
    """What one ``_ingest_urls`` call learned about its URLs beyond the SourceFiles."""

    # Requested URL -> URL its live fetch ended on after redirects.
    final_urls: dict[str, str] = field(default_factory=dict)
    # Requested URL dropped because it reached a page already kept -> the kept URL.
    aliases: dict[str, str] = field(default_factory=dict)
    # Requested URL -> sidecar ``archive`` record ({status, error?}).
    archive: dict[str, dict] = field(default_factory=dict)


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
    """Ingest up to the claim's remaining source count; return fresh sources, errors and notes.

    Redirects to a stored page move into ``cached_sources``, and ``result``
    gains the final URLs and archive records the sidecar and index need.
    """
    notes = IngestNotes()
    remaining = max(0, cfg.max_sources - len(cached_sources))
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
        source_files, ingest_errors = await _ingest_urls(
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


async def _research(
    client: httpx.AsyncClient,
    entity_name: str,
    claim_text: str,
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    resolved_entity: "ResolvedEntity | None" = None,
    topics: list[str] | None = None,
) -> "ResearchOutput":
    """Run the decomposed researcher and return a ``ResearchOutput``.

    The returned ``trace`` dict is suitable for the audit sidecar's
    ``research:`` block. Always populated with at least ``mode``; further
    fields depend on how far the researcher got before any error.

    ``topics`` is the criterion's topic list (per ``template.topics``);
    threaded through to ``decomposed_research`` so the academic-API
    selector (Path 2 arXiv, future S2/OpenAlex) can decide whether to
    fire. Empty / ``None`` keeps academic dispatch off.
    """
    from researcher.decomposed import decomposed_research
    out = await decomposed_research(
        claim_text, entity_name, cfg, sem, client,
        resolved_entity=resolved_entity, topics=topics,
    )
    identity = (
        entity_identity_for(resolved_entity, _cfg_repo_root(cfg))
        if resolved_entity is not None
        else None
    )
    urls, errors = _apply_blocklist_cap(
        out.urls, cfg, out.errors,
        url_addresses=out.url_addresses,
        sub_question_ids=[sq.id for sq in out.sub_questions],
        identity=identity,
        prefetched_bodies=out.prefetched_bodies,
        trace=out.trace,
    )
    logger.info("Decomposed research: %d kept (cap=%d)", len(urls), cfg.candidate_pool_size)
    out.urls = urls
    out.errors = errors
    out.url_addresses = {u: out.url_addresses.get(u, []) for u in urls}
    out.prefetched_bodies = {
        u: out.prefetched_bodies[u] for u in urls if u in out.prefetched_bodies
    }
    out.trace["urls_after_blocklist"] = len(urls)
    return out


_WAYBACK_FAILURE_TAGS = frozenset({"wayback_unavailable"})


def _merge_acquisition_writes(
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
    """Return the ``acquisition`` map on ``research_trace`` for ``_ingest_urls``.

    Acts as ``setdefault`` so repeated calls return the same dict.
    Returns ``None`` if ``research_trace`` isn't a dict (defensive against
    error variants of ``ResearchOutput``); in that case ``_ingest_urls``
    drops acquisition writes silently rather than blowing up the run.
    """
    if not isinstance(research_trace, dict):
        return None
    return research_trace.setdefault("acquisition", {})


def _check_ingested_source(
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
    for quote in drop_unfound_quotes(sf, requested_page_text(deps)):
        logger.warning("Dropping key quote not found on the page for %s: %r", url, quote)
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


async def _ingest_one(
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
    archive: bool = True,
) -> tuple[str, SourceFile] | StepError:
    """Ingest a single URL. Returns a (url, SourceFile) tuple on success or a StepError.

    ``acquisition_out`` and ``failures_out`` are optional output sinks
    populated from the ``wayback_check`` tool's side-channel on
    ``IngestorDeps``. Defaults preserve the historical signature for
    direct callers (e.g., ``test_terminal_fetch.py``) that don't care
    about wayback provenance.

    * ``acquisition_out`` (dict): per-URL recovery writes shaped
      ``{recovered_via, stage, outcome}``. Merged into the caller's map.
    * ``failures_out`` (list): wayback transport-failure dicts
      ``{stage, error_type, message}``. The caller decides whether to
      promote these to ``StepError`` (see ``_ingest_urls`` — only for
      URLs whose ingest itself failed terminally).
    * ``notes``: gains, for a successful ingest, the URL its live fetch
      ended on and the sidecar record of the archive lookup.

    A successful ingest also gets its ``archived_url`` from that lookup,
    unless ``archive`` is False (the caller discards the source).
    """
    repo_root = repo_root or _cfg_repo_root(cfg)
    deps = IngestorDeps(
        http_client=client,
        repo_root=str(repo_root),
        requested_url=url,
        skip_wayback=cfg.skip_wayback,
        allow_save=cfg.allow_save,
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
        # Outside the LLM semaphore and time limit; never raises.
        corporate_lab = await arxiv_corporate_lab(client, url)
        outcome: tuple[str, SourceFile] | StepError = _check_ingested_source(
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
        error_type = "http_error" if "HTTP" in type(exc).__name__ else "model_error"
        logger.warning("Failed to ingest %s: %s", url, exc)
        outcome = StepError(step="ingest", url=url, error_type=error_type, message=str(exc))

    if isinstance(outcome, tuple):
        if archive:
            # Outside the LLM semaphore and the ingest time limit: a slow
            # archive.org must not turn a good ingest into a timeout.
            record = await archive_after_ingest(outcome[1], deps)
            if notes is not None:
                notes.archive[url] = record
        if notes is not None and deps.final_url:
            notes.final_urls[url] = deps.final_url

    if acquisition_out is not None:
        _merge_acquisition_writes(acquisition_out, deps.acquisition_writes)
    if failures_out is not None:
        failures_out.extend(deps.wayback_failures)

    return outcome


async def _ingest_urls(
    client: httpx.AsyncClient,
    urls: list[str],
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
    *,
    target: int | None = None,
    prefetched_bodies: dict[str, str] | None = None,
    acquisition_out: dict[str, dict] | None = None,
    notes: IngestNotes | None = None,
    archive: bool = True,
    known_pages: dict[str, str] | None = None,
) -> tuple[list[tuple[str, SourceFile]], list[StepError]]:
    """Waterfall: attempt up to candidate_pool_size URLs in the order given,
    stopping once max_sources successes are collected (~2 concurrent).

    Two URLs that reach one page (by redirect) give one result: the later
    one is dropped, does not count toward ``target``, and is recorded in
    ``notes.aliases``. ``known_pages`` (canonical key -> requested URL) names
    pages the claim already has from the dedup index; a URL that reaches one
    is dropped the same way. ``notes.final_urls`` maps each requested URL to the
    URL its live fetch ended on. ``archive=False`` skips the archive lookup
    for callers that keep only the summary.

    When ``prefetched_bodies`` is supplied, each URL's body (if present)
    is threaded into ``IngestorDeps`` so ``web_fetch`` returns it without
    issuing an httpx GET. Missing/empty entries fall through to a live
    fetch.

    ``acquisition_out`` is an optional output map: when supplied, the
    per-URL ``{recovered_via, ...}`` writes drained from the
    ``wayback_check`` side-channel are merged into it. Mirrors the
    ``acquisition_out`` parameter on ``researcher.execute_searches`` —
    the orchestrator passes ``research_trace["acquisition"]`` so the
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
            outcome = await _ingest_one(
                client, url, cfg, today, sem,
                prefetched_body=bodies.get(url),
                acquisition_out=acquisition_out,
                failures_out=url_failures,
                repo_root=repo_root,
                notes=notes,
                archive=archive,
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


async def _run_with_null_retry(
    agent,
    prompt: str,
    timeout_s: float,
    *,
    retries: int = _NULL_BODY_RETRIES,
    delay_s: float = _NULL_BODY_RETRY_DELAY_S,
) -> tuple:
    """Run an agent, retrying on Infomaniak null-body responses.

    Returns (output, messages, last_exc). output is None on final failure;
    last_exc is None on success and the final raised exception otherwise so
    callers can build a structured FailureInfo. The retry loop sits outside
    asyncio.wait_for so each call gets its own timeout and the retry window
    is additive — no timeout budget conflict.
    """
    for attempt in range(retries + 1):
        with capture_run_messages() as messages:
            try:
                res = await asyncio.wait_for(agent.run(prompt), timeout=timeout_s)
                return res.output, messages, None
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
                return None, messages, exc


async def _analyse_claim(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
    cfg: VerifyConfig,
    resolved_entity: ResolvedEntity | None = None,
    sub_questions: list[SubQuestion] | None = None,
    repo_root: Path | None = None,
    criterion_notes: str | None = None,
) -> tuple[AnalystOutput | None, FailureInfo | None]:
    """Run the analyst agent. Returns (output, failure) — failure is set
    only when output is None, so callers can persist structured failure
    detail into the audit sidecar and progress line.

    With a ``resolved_entity``, ``_apply_entity_match`` relabels ``sources``
    in place (so the auditor and sidecar see the same labels) and the
    changes are recorded on the verdict's ``source_overrides``.
    """
    entity_overrides: list[SourceOverride] = []
    if resolved_entity is not None:
        entity_overrides = _apply_entity_match(
            sources, resolved_entity, repo_root or _cfg_repo_root(cfg), claim_text
        )
    prompt = build_analyst_prompt(
        entity_name,
        claim_text,
        sources,
        resolved_entity=resolved_entity,
        sub_questions=sub_questions,
        criterion_notes=criterion_notes,
    )
    model_spec = cfg.model_for("analyst")

    def _analyst_failure(exc: BaseException | None) -> FailureInfo | None:
        if exc is None:
            return None
        return _failure_from_exc(
            exc, step="analyst", agent="analyst",
            model=model_spec, timeout_s=cfg.analyst_timeout_s,
        )

    if resolved_entity is not None:
        with verdict_only_agent.override(model=resolve_model(model_spec)):
            verdict_assessment, _, exc = await _run_with_null_retry(
                verdict_only_agent, prompt, cfg.analyst_timeout_s
            )
        if verdict_assessment is None:
            return None, _analyst_failure(exc)
        _merge_entity_overrides(verdict_assessment, entity_overrides)
        _clean_verdict_citations(verdict_assessment, sources)
        entity_resolution = EntityResolution(
            entity_name=resolved_entity.entity_name,
            entity_type=resolved_entity.entity_type,
            entity_description=resolved_entity.entity_description,
            aliases=resolved_entity.aliases,
        )
        return AnalystOutput(entity=entity_resolution, verdict=verdict_assessment), None

    with analyst_agent.override(model=resolve_model(model_spec)):
        output, _, exc = await _run_with_null_retry(analyst_agent, prompt, cfg.analyst_timeout_s)
    if output is None:
        return None, _analyst_failure(exc)
    _clean_verdict_citations(output.verdict, sources)
    return output, None


def _clean_verdict_citations(verdict: VerdictAssessment, sources: list[dict]) -> None:
    """Replace citation tokens and "Source N" references in the narrative with source titles.

    ``takeaway`` and ``cap_rationale`` reject citations at validation time.
    ``sources`` must be the list, in order, that the analyst prompt was built
    from: "Source N" means the Nth source listed there.
    """
    verdict.narrative, unresolved = clean_citations(verdict.narrative, sources)
    if unresolved:
        logger.warning("Analyst output has unresolved citation references: %s", unresolved)


def _graded_statement(
    template: TemplateRecord | None,
    entity_name: str,
    claim_text: str,
    analyst_title: str,
) -> str | None:
    """The claim statement the auditor grades, or None to skip the audit.

    A template-backed claim is written under the analyst's title, and a title
    that fails the template blocks the claim; auditing it would spend an
    auditor call, and possibly an operator prompt, on a claim that never
    ships. A passing title also resolves any vocabulary slot that the
    rendered ``claim_text`` holds as a "one of (...)" hint. Without a
    template (``dr claim-probe``, which writes nothing) the operator's text
    is graded.
    """
    if template is None:
        return claim_text
    title_ok, _ = validate_analyst_title(template, entity_name, analyst_title)
    return analyst_title if title_ok else None


async def _audit_claim(
    entity_name: str,
    statement: str,
    analyst_out: AnalystOutput,
    sources: list[dict],
    cfg: VerifyConfig,
    criterion_notes: str | None = None,
) -> ComparisonResult | None:
    """Grade ``statement`` against ``sources``; the caller picks the statement."""
    bundle = build_bundle(
        entity_name=analyst_out.entity.entity_name,
        claim_text=statement,
        entity_type=analyst_out.entity.entity_type,
        description=analyst_out.entity.entity_description,
        topics=analyst_out.verdict.topics,
        narrative=analyst_out.verdict.narrative,
        sources=sources,
        criterion_notes=criterion_notes,
    )

    prompt = build_auditor_prompt(bundle)

    with auditor_agent.override(model=resolve_model(cfg.model_for("auditor"))):
        assessment, _, _exc = await _run_with_null_retry(auditor_agent, prompt, cfg.auditor_timeout_s)

    if assessment is None:
        return None

    return compare(
        analyst_out.verdict.verdict,
        analyst_out.verdict.confidence,
        assessment,
        bundle.claim_id,
        "(draft -- not yet saved)",
    )


def _apply_cited_filter(
    result: VerificationResult, analyst_out: AnalystOutput, entity_name: str
) -> list[dict]:
    """Narrow the claim's listed sources to those the analyst relied on; return them.

    Cited is ``cited_source_ids`` over the analyst's own overrides (the
    entity-match relabels do not count). Sets ``result.uncited_urls`` to the
    ingested URLs of every other source. The full list is kept, with a
    warning, when nothing is cited (that means unknown, not none) or when
    the cited subset would fit a lower ``verification_level`` than the full
    list: both sides go through ``fit_verdict_to_written_pool`` on a copy,
    so the counting rules are the write-time fit's and the linter's.
    ``result.sources`` stays whole, since the write-time fit and the
    sidecar read it.
    """
    from orchestrator.persistence import fit_verdict_to_written_pool

    verdict = analyst_out.verdict
    analyst_overrides = [o for o in verdict.source_overrides or [] if not o._code_relabel]
    cited = set(cited_source_ids(verdict, result.sources, analyst_overrides))
    if not cited:
        logger.warning("Analyst cited no source by id or title; the claim lists every ingested source")
        return result.sources

    all_ids = [sd["source_id"] for sd in result.sources if sd.get("source_id")]

    def fitted_level(ids: list[str]) -> object:
        trial = verdict.model_copy(deep=True)
        fit_verdict_to_written_pool(trial, result.sources, ids, entity_name, log=False)
        return trial.verification_level

    if fitted_level([sid for sid in all_ids if sid in cited]) != fitted_level(all_ids):
        logger.warning(
            "Cited sources do not support verification_level %s; the claim lists every ingested source",
            getattr(verdict.verification_level, "value", verdict.verification_level),
        )
        return result.sources

    url_ids = [(url, sid) for url, sid, _sd in result.cached_sources] + [
        (url, f"{sf.year}/{sf.slug}") for url, sf in result.source_files
    ]
    result.uncited_urls = {url for url, sid in url_ids if sid not in cited}
    if result.uncited_urls:
        logger.info("Uncited sources left off the claim: %s", sorted(result.uncited_urls))
    return [sd for sd in result.sources if sd.get("source_id") in cited]


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
        _claim_path_for,
        _write_audit_sidecar,
        _write_claim_file,
        _write_entity_file,
        _write_source_files,
        analyst_record_for,
        fit_verdict_to_written_pool,
        mark_forced_rewrite,
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

            source_files, ingest_errors, notes = await _ingest_claim_sources(
                client, urls_to_ingest, cached_sources, ro, result, cfg, _sem,
                url_index, repo_root,
            )

            for url, sid, sd in cached_sources:
                sd["addresses"] = _addresses_with_aliases(url, ro.url_addresses, notes.aliases)
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.cached_sources.append((url, sid, sd))

            for url, sf in source_files:
                sd = _build_source_dict(sf)
                sd["addresses"] = _addresses_with_aliases(url, ro.url_addresses, notes.aliases)
                result.urls_ingested.append(url)
                result.sources.append(sd)
                result.source_files.append((url, sf))

            ingested_set = set(result.urls_ingested) | set(notes.aliases)
            result.urls_failed = [u for u in urls if u not in ingested_set]
            all_errors = research_errors + ingest_errors

            result.sub_question_coverage = _invert_addresses(
                ro.sub_questions, result.sources
            )
            _warn_uncovered(ro.sub_questions, result.sub_question_coverage)

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

            # Step 3: Analyse claim (analyst identifies entity)
            progress("  › Analysing", log=False)
            logger.info("Step 3/5: Analysing claim...")
            analyst_out, analyst_failure = await _analyse_claim(
                None, claim_text, result.sources, cfg,
                resolved_entity=resolved_entity,
                sub_questions=result.sub_questions,
                repo_root=repo_root,
            )
            result.analyst_output = analyst_out

            if not analyst_out:
                result.errors.append("Analyst failed to produce an assessment")
                if analyst_failure is not None and result.failure is None:
                    result.failure = analyst_failure
                if source_files:
                    _write_source_files(source_files, repo_root)
                return result

            result.entity = analyst_out.entity.entity_name
            cited_sources = _apply_cited_filter(
                result, analyst_out, analyst_out.entity.entity_name
            )

            # Step 4: Write the cited sources to disk. Ids come from the
            # write, keyed by URL, since a write can rename a colliding slug.
            cited_files = [
                (url, sf) for url, sf in source_files if url not in result.uncited_urls
            ]
            progress("  › Writing sources", log=False)
            logger.info("Step 4/5: Writing %d source files...", len(cited_files))
            fresh_ids = _write_source_files(cited_files, repo_root)
            id_by_url = {
                url: sid for url, sid, _ in cached_sources if url not in result.uncited_urls
            }
            id_by_url.update(
                {url: sid for (url, _sf), sid in zip(cited_files, fresh_ids)}
            )
            source_ids = list(dict.fromkeys(
                id_by_url[u] for u in (notes.aliases.get(url, url) for url in urls)
                if u in id_by_url
            ))

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
            level_clamp = fit_verdict_to_written_pool(
                analyst_out.verdict, result.sources, source_ids,
                analyst_out.entity.entity_name,
            )
            if cfg.force_overwrite:
                mark_forced_rewrite(
                    _claim_path_for(entity_ref, analyst_out.entity.entity_name, claim_slug, repo_root),
                    source_ids, datetime.datetime.now(datetime.timezone.utc),
                )
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
            # Grade the title the claim file carries, which is what a later
            # dr step-audit on that file grades, so the two runs agree.
            comparison = await _audit_claim(
                analyst_out.entity.entity_name, analyst_out.verdict.title,
                analyst_out, cited_sources, cfg,
            )
            result.consistency = comparison

            # Write audit sidecar after auditor step
            sidecar_sources = result.sources_consulted()
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
                analyst_record=analyst_record_for(analyst_out.verdict),
                level_clamp=level_clamp,
            )

            # Checkpoint: review disagreement
            if comparison and comparison.needs_review:
                accept = await gate.review_disagreement(comparison)
                if not accept:
                    reasons = ", ".join(needs_review_reasons(comparison))
                    result.errors.append(f"Flagged for human review: {reasons}")

    return result


_NO_URLS_ERR = "Researcher agent found no relevant URLs"


def _blocked_reason_label(
    reason_value: str,
    vr_errors: list[str],
    extra: str | None = None,
    failure: FailureInfo | None = None,
) -> str:
    """Format a BlockedReason value with the most informative upstream cause.

    When a structured ``failure`` is available it dominates, producing a
    triage-friendly label that names the error class, the model that ran,
    and the timeout budget it was given:

        analyst_error: TimeoutError on infomaniak:openai/gpt-oss-120b after 120.0s

    Otherwise prefers ``extra`` if provided, then the first non-noise
    message from ``vr_errors``, then the first error, then the bare
    reason. The "no relevant URLs" string is treated as noise because it
    is downstream of the real cause (planner timeout, search failure,
    etc.) and obscures it.
    """
    if failure is not None:
        parts = [failure.error_class]
        if failure.model:
            parts.append(f"on {failure.model}")
        if failure.timeout_s is not None and failure.error_class == "TimeoutError":
            parts.append(f"after {failure.timeout_s:g}s")
        return f"{reason_value}: " + " ".join(parts)
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
    # Non-fatal advisories surfaced in the report without halting the
    # run. Currently used for "subject onboarded, no template
    # subjects: hit"; reserved for similar advisory rows.
    warnings: list[str] = field(default_factory=list)


@dataclass
class EnrichmentResult:
    """Outcome of running the enricher against one entity.

    ``status``:
        - ``"accepted"``  – operator accepted the draft; entity file updated.
        - ``"rejected"``  – operator rejected the draft; nothing written.
        - ``"failed"``    – no page summary to enrich from, or the enricher
          agent or write step raised; see ``errors``.

    ``founded`` / ``description`` / ``history_markdown`` capture the
    fields that were actually persisted (only populated for ``accepted``).
    """

    entity_ref: str
    entity_name: str
    status: Literal["accepted", "rejected", "failed"]
    founded: int | None = None
    description: str | None = None
    history_markdown: str | None = None
    errors: list[str] = field(default_factory=list)


def _screen_templates(
    entity_description: str,
    templates: list,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Screen templates for applicability. MVP: all core templates pass."""
    applicable = [t.slug for t in templates]
    excluded: list[tuple[str, str]] = []
    return applicable, excluded


@dataclass(frozen=True)
class LightResearchBundle:
    """Shared input for the entity verifier and enricher agents.

    ``raw_description`` is the untightened webpage summary; the enricher
    produces the tightened one-sentence ``description``. ``fetch_errors``
    says why no summary was collected (fetch, search or ingest failures),
    so callers that refuse to enrich can report the reason.
    """

    entity_name: str
    entity_type: EntityType
    raw_description: str
    entity_website: str | None
    probe_excludes: list[str]
    fetch_errors: list[str] = field(default_factory=list)

    @property
    def has_page_summary(self) -> bool:
        """Whether a page summary was collected. Without one the enricher
        could only write from model memory, so callers skip it."""
        return bool(self.raw_description.strip())


def _describe_step_error(e: StepError) -> str:
    return f"{e.url or '-'}: {e.error_type}: {e.message}"


async def gather_light_research(
    entity_name: str,
    entity_type: EntityType,
    cfg: "VerifyConfig",
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    seed_url: str | None = None,
) -> LightResearchBundle:
    """Run the orchestrator's light-research pass and return a bundle.

    Errors during search/fetch/probe are non-fatal so onboarding can still
    proceed with whatever signals were collected; search and fetch errors
    are returned in ``fetch_errors``. Returns the raw webpage summary; the
    enricher produces the tightened one-sentence ``description``.
    """
    raw_description = ""
    entity_website: str | None = None
    probe_excludes: list[str] = []
    fetch_errors: list[str] = []

    try:
        if seed_url:
            url = seed_url if seed_url.startswith(("http://", "https://")) else f"https://{seed_url}"
            entity_website = url
            logger.info("Light research: ingesting seed URL %s", url)
            source_files, ingest_errors = await _ingest_urls(
                client, [url], cfg, sem, archive=False,
            )
            fetch_errors.extend(_describe_step_error(e) for e in ingest_errors)
        else:
            query = f"{entity_name} official website"
            light_ro = await _research(client, entity_name, query, cfg, sem)
            # Only an http(s) URL may become the entity's website link on the site.
            urls = [u for u in light_ro.urls if u.startswith(("http://", "https://"))]
            if urls:
                entity_website = urls[0]
                source_files, ingest_errors = await _ingest_urls(
                    client, urls[:1], cfg, sem,
                    prefetched_bodies=light_ro.prefetched_bodies,
                    archive=False,
                )
                fetch_errors.extend(_describe_step_error(e) for e in ingest_errors)
            else:
                source_files = []
                fetch_errors.extend(
                    _describe_step_error(e) for e in light_ro.errors
                )
                if not fetch_errors:
                    fetch_errors.append("search found no website")
        if source_files:
            _src_url, sf = source_files[0]
            raw_description = sf.frontmatter.summary or ""
        # A blank summary with no recorded error happens when the page was
        # ingested with an empty summary, or when an ingest worker raised
        # (``_ingest_urls`` gathers with ``return_exceptions=True``).
        if not raw_description.strip() and not fetch_errors:
            fetch_errors.append(
                f"{entity_website or '-'}: empty_summary: "
                + ("page fetched but summary empty" if source_files
                   else "page not ingested and no error recorded")
            )
        probe_excludes = await _probe_collision_suggestions(
            client, entity_name, entity_website
        )
    except Exception as exc:
        logger.warning("Light research failed: %s", exc)
        fetch_errors.append(f"light research failed: {exc}")

    return LightResearchBundle(
        entity_name=entity_name,
        entity_type=entity_type,
        raw_description=raw_description,
        entity_website=entity_website,
        probe_excludes=probe_excludes,
        fetch_errors=fetch_errors,
    )


# Second-level labels under which country-code domains are registered
# (example.co.uk). No public-suffix list is installed; where this guess is
# wrong (shared hosts such as github.io), two sites look like one, so the
# probe suggests one exclude fewer rather than dropping first-party pages.
_CC_SECOND_LEVEL = frozenset({"ac", "co", "com", "edu", "go", "gov", "ne", "net", "or", "org"})


def _site_domain(host: str) -> str:
    """The registered domain of ``host``, guessed: ``help.viro.app`` gives
    ``viro.app``, ``shop.example.co.uk`` gives ``example.co.uk``."""
    labels = host.split(".")
    keep = 2
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _CC_SECOND_LEVEL:
        keep = 3
    return ".".join(labels[-keep:])


async def _probe_collision_suggestions(
    client: httpx.AsyncClient,
    entity_name: str,
    entity_website: str | None,
) -> list[str]:
    """Probe Brave for the bare entity name; suggest exclude domains on collision.

    Skipped (returns []) when there is no canonical website to compare against.
    Returns up to 3 distinct registered domains that appear in the top results
    and are not under the canonical host's own site domain (``_site_domain``)
    or a shared platform (``SHARED_PLATFORM_HOSTS``).
    Failures are non-fatal: the probe is best-
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
        # Anything under the entity's own site domain (viro.app, help.viro.app
        # for ai.viro.app): excluding one would drop first-party pages, since
        # the blocklist also matches subdomains.
        if _site_domain(host) == _site_domain(canon):
            continue
        # LinkedIn, the App Store and the like host the entity's own account
        # as readily as a collider's, so a whole-host exclude is never right.
        if any(host_matches(host, shared) for shared in SHARED_PLATFORM_HOSTS):
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


async def enrich_entity(
    entity_ref: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
) -> EnrichmentResult:
    """Re-run the enricher against an existing entity file.

    Loads the entity, runs ``gather_light_research``, calls the
    enricher agent, surfaces the draft via the ``review_entity_enrichment``
    checkpoint, and on accept splices ``founded`` / ``description`` /
    ``history_markdown`` into the file in place. Other fields
    (aliases, parent_company, search_hints, etc.) are preserved untouched.

    Refuses (status ``failed``, nothing written) when light research
    collected no page summary. Only ``dr entity-enrich`` calls this
    helper; ``onboard_entity`` runs its own enricher step with the same
    refusal.
    """
    from common.models import resolve_model
    from orchestrator.entity_resolution import parse_entity_ref
    from orchestrator.persistence import update_entity_enrichment
    from researcher.entity_enricher import (
        build_entity_enricher_prompt,
        entity_enricher_agent,
    )

    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        cfg.repo_root = str(resolve_repo_root())
    repo_root = Path(cfg.repo_root)
    gate = checkpoint or AutoApproveCheckpointHandler()

    try:
        resolved = parse_entity_ref(entity_ref, repo_root)
    except ValueError as exc:
        return EnrichmentResult(
            entity_ref=entity_ref,
            entity_name=entity_ref,
            status="failed",
            errors=[f"could not load entity: {exc}"],
        )

    entity_path = (
        repo_root / "research" / "entities" / f"{entity_ref}.md"
    )

    sem = asyncio.Semaphore(cfg.llm_concurrency)
    with bind_run_id(cfg.run_id):
        logger.info("enrich_entity entry: ref=%s", entity_ref)

        # Phase A (shared with onboard_entity): light research.
        async with httpx.AsyncClient() as client:
            bundle = await gather_light_research(
                resolved.entity_name,
                resolved.entity_type,
                cfg,
                sem,
                client,
                seed_url=resolved.website,
            )

        # Auto-approve would persist a model-memory guess as fact.
        if not bundle.has_page_summary:
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="failed",
                errors=[
                    "not enriched: light research collected no page summary",
                    *bundle.fetch_errors,
                ],
            )

        # Phase C: enricher agent.
        prompt = build_entity_enricher_prompt(bundle)
        try:
            with entity_enricher_agent.override(
                model=resolve_model(cfg.model_for("researcher")),
            ):
                run_res = await asyncio.wait_for(
                    entity_enricher_agent.run(prompt),
                    timeout=cfg.research_timeout_s,
                )
            draft = run_res.output
        except Exception as exc:
            logger.warning("Enricher failed: %s", exc)
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="failed",
                errors=[f"enricher failed: {exc}"],
            )

        decision = await gate.review_entity_enrichment(
            resolved.entity_name, draft,
        )
        if decision == "reject":
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="rejected",
            )

        try:
            update_entity_enrichment(
                entity_path,
                description=draft.description,
                founded=draft.founded,
                history_markdown=draft.history_markdown,
            )
        except Exception as exc:
            logger.warning("Entity write failed: %s", exc)
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="failed",
                errors=[f"write failed: {exc}"],
            )

    return EnrichmentResult(
        entity_ref=entity_ref,
        entity_name=resolved.entity_name,
        status="accepted",
        founded=draft.founded,
        description=draft.description,
        history_markdown=draft.history_markdown,
    )


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
        _claim_dir_for,
        _write_audit_sidecar,
        _write_claim_file,
        _write_draft_entity_file,
        _write_entity_file,
        analyst_record_for,
        entity_ref_for,
        fit_verdict_to_written_pool,
        mark_forced_rewrite,
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

    # A ref names a hand-written entity file. That file, not the enricher's
    # draft, is what the analyst and auditor are told is authoritative, and
    # its website seeds light research so the collision probe compares
    # against the entity's real domain rather than a search hit.
    file_entity: ResolvedEntity | None = None
    if entity_ref is not None:
        try:
            file_entity = parse_entity_ref(entity_ref, repo_root)
        except ValueError as exc:
            result.status = "rejected"
            result.errors.append(f"could not load entity: {exc}")
            return result
        if seed_url is None:
            seed_url = file_entity.website

    with bind_run_id(cfg.run_id):
        logger.info(
            "onboard_entity entry: name=%s type=%s seed_url=%s",
            entity_name,
            entity_type,
            seed_url,
        )

        # Phase A: Light research for entity context
        hr()
        logger.info("Onboard phase A: light research for %s", entity_name)
        async with httpx.AsyncClient() as client:
            bundle = await gather_light_research(
                entity_name, et, cfg, sem, client, seed_url=seed_url,
            )
        entity_website = bundle.entity_website
        probe_excludes = bundle.probe_excludes

        # Phase B: verifier — gate against name collisions before the
        # enricher burns compute on the wrong entity.
        # ``verified`` proceeds to Phase C with the default
        # ``verification_status`` (verified). ``needs-disambiguation``
        # surfaces candidates to the operator; ``reject`` halts the run
        # with the candidates in errors, ``accept`` uses the first
        # candidate, a free-text ``str`` renames to that pick. The
        # ``unverified`` outcome reuses the same checkpoint with the
        # two ``verification_status`` enum values as candidates; the
        # operator's pick becomes the persisted status.
        from researcher.entity_verifier import (
            build_entity_verifier_prompt,
            entity_verifier_agent,
        )

        verification_status: str | None = None
        try:
            prompt = build_entity_verifier_prompt(bundle)
            with entity_verifier_agent.override(
                model=resolve_model(cfg.model_for("researcher")),
            ):
                vr_run = await asyncio.wait_for(
                    entity_verifier_agent.run(prompt),
                    timeout=cfg.research_timeout_s,
                )
            outcome = vr_run.output
        except Exception as exc:
            logger.warning(
                "Verifier failed; proceeding without disambiguation gate: %s",
                exc,
            )
            outcome = None

        if outcome is not None and outcome.status == "needs-disambiguation":
            decision = await gate.review_entity_disambiguation(
                entity_name, list(outcome.candidates),
            )
            if decision == "reject":
                result.status = "rejected"
                cands = ", ".join(outcome.candidates) or "(none)"
                result.errors.append(
                    f"verifier flagged needs-disambiguation; candidates: {cands}"
                )
                return result
            if decision == "accept":
                if outcome.candidates:
                    entity_name = outcome.candidates[0]
                    result.entity_name = entity_name
            elif isinstance(decision, str):
                entity_name = decision
                result.entity_name = entity_name
            # Re-run light research under the operator-picked name so
            # downstream prompts (enricher, scorer, analyst) align with
            # the resolved entity rather than the original ambiguous one.
            async with httpx.AsyncClient() as client:
                bundle = await gather_light_research(
                    entity_name, et, cfg, sem, client, seed_url=seed_url,
                )
            entity_website = bundle.entity_website
            probe_excludes = bundle.probe_excludes
        elif outcome is not None and outcome.status == "unverified":
            statuses = ["unverified-startup", "unverified-other"]
            decision = await gate.review_verification_status(
                entity_name, entity_website, outcome.reasoning, statuses,
            )
            if decision in statuses:
                verification_status = decision
            else:
                # "reject", or a value outside the schema enum: never
                # write a non-schema verification_status.
                result.status = "rejected"
                result.errors.append(
                    "verifier flagged unverified; operator declined to "
                    "pick a verification_status"
                    if decision == "reject"
                    else f"verifier flagged unverified; operator pick "
                    f"{decision!r} is not a valid verification_status"
                )
                return result

        # Phase C: enricher (operator-review checkpoint)
        # The enricher subsumes the previous standalone tightening agent:
        # ``EnrichmentDraft.description`` is the new one-sentence
        # description; ``founded`` and ``history_markdown`` populate
        # surfaces the renderer learned about in Step 2.
        from researcher.entity_enricher import (
            build_entity_enricher_prompt,
            entity_enricher_agent,
        )

        enrichment_draft = None
        entity_description = (
            file_entity.entity_description if file_entity is not None
            else bundle.raw_description
        )
        founded_year: int | None = None
        history_markdown: str | None = None
        # Without --force nothing would use a draft for an entity file on disk.
        # Without a page summary the draft could only come from model memory.
        wants_draft = file_entity is None or cfg.force_overwrite
        run_enricher = wants_draft and bundle.has_page_summary
        if wants_draft and not run_enricher:
            progress(
                "Enricher skipped: light research collected no page summary%s",
                "".join(f"\n  ! {e}" for e in bundle.fetch_errors),
            )
        try:
            if run_enricher:
                prompt = build_entity_enricher_prompt(bundle)
                with entity_enricher_agent.override(
                    model=resolve_model(cfg.model_for("researcher")),
                ):
                    run_res = await asyncio.wait_for(
                        entity_enricher_agent.run(prompt),
                        timeout=cfg.research_timeout_s,
                    )
                enrichment_draft = run_res.output
        except Exception as exc:
            logger.warning(
                "Enricher failed; falling back to raw page summary: %s", exc
            )

        if enrichment_draft is not None:
            decision = await gate.review_entity_enrichment(
                entity_name, enrichment_draft,
            )
            if decision == "accept":
                # Empty description means the enricher judged the inputs
                # not to describe the entity — keep the raw summary
                # rather than ship a blank field through the writer.
                if enrichment_draft.description.strip():
                    entity_description = enrichment_draft.description.strip()
                founded_year = enrichment_draft.founded
                history_markdown = (
                    enrichment_draft.history_markdown
                    if enrichment_draft.history_markdown
                    and enrichment_draft.history_markdown.strip()
                    else None
                )
            else:
                logger.info("Enricher draft rejected; keeping raw summary")

        # A name-based run over an entity file on disk has no file_entity;
        # with no page summary, the file's description stands in for the
        # blank one in screening, the checkpoint and the analyst.
        if file_entity is None and not bundle.has_page_summary:
            try:
                entity_description = parse_entity_ref(
                    entity_ref_for(entity_name, et), repo_root,
                ).entity_description or ""
            except ValueError:
                pass

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
        onboard_entity_slug: str | None = None
        if entity_type == "subject" and entity_ref and "/" in entity_ref:
            onboard_entity_slug = entity_ref.split("/", 1)[1]
        elif entity_type == "subject":
            from common.utils import slugify as _slugify
            onboard_entity_slug = _slugify(entity_name)
        typed_templates = templates_for_entity_type(
            all_templates, entity_type, entity_slug=onboard_entity_slug
        )

        if not typed_templates:
            # Subjects without a matching ``subjects:`` entry are
            # legitimate first-class onboards — the entity file should
            # still land. Emit a warning row and fall through so the
            # entity gets verified, enriched, and persisted with zero
            # claims fanned out. Company / product have no per-entity
            # template gating, so an empty set there is still an error.
            if entity_type == "subject":
                slug_for_warning = onboard_entity_slug or slugify(entity_name)
                result.warnings.append(
                    f"No template's subjects: list references "
                    f"subjects/{slug_for_warning}; "
                    f"entity will be onboarded with zero claims."
                )
            else:
                result.errors.append(
                    f"No core templates found for entity_type={entity_type}"
                )
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

        # Per-call ``verification_status`` only flows through when the
        # verifier returned ``unverified`` and the operator picked an
        # enum value. ``verified`` (the default) leaves frontmatter
        # absent of the field, matching ``entity-metadata-surface``.
        write_kwargs: dict = {}
        if verification_status is not None:
            write_kwargs["verification_status"] = verification_status

        if decision == "reject":
            result.status = "rejected"
            draft_ref = _write_draft_entity_file(
                entity_name=entity_name,
                entity_type=et,
                entity_description=entity_description,
                repo_root=repo_root,
                website=entity_website,
                search_hints=merged_search_hints,
                founded=founded_year,
                history_markdown=history_markdown,
                **write_kwargs,
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
                founded=founded_year,
                history_markdown=history_markdown,
                **write_kwargs,
            )
        result.entity_ref = entity_ref

        # _write_entity_file early-returns on existing files. When --force
        # is in play and the enricher produced a draft this run, splice
        # it into the existing file so onboard --force actually persists
        # the new founded / description / history rather than dropping
        # them on the floor. Spares a redundant Phase A + Phase C in the
        # CLI's `enrich_entity` follow-up.
        if cfg.force_overwrite and enrichment_draft is not None:
            from orchestrator.persistence import update_entity_enrichment
            entity_path = (
                repo_root / "research" / "entities" / f"{entity_ref}.md"
            )
            if entity_path.exists():
                update_entity_enrichment(
                    entity_path,
                    description=entity_description,
                    founded=founded_year,
                    history_markdown=history_markdown,
                )

        # Without this resolved entity, the just-persisted search_hints,
        # founded year, and verification_status would not reach the
        # per-template researcher on the run that wrote them.
        if file_entity is not None:
            # Re-read: --force may have just spliced an enrichment into it.
            on_disk = parse_entity_ref(entity_ref, repo_root)
            file_hints = on_disk.search_hints or SearchHints()
            onboard_resolved_entity = dataclasses.replace(
                on_disk,
                search_hints=_merge_search_hints(
                    list(file_hints.include) + list(search_hints_include or []),
                    list(file_hints.exclude) + list(search_hints_exclude or []),
                    probe_excludes,
                ),
                verification_status=verification_status or on_disk.verification_status,
            )
        else:
            onboard_resolved_entity = ResolvedEntity(
                entity_ref=entity_ref,
                entity_name=entity_name,
                entity_type=et,
                entity_description=entity_description,
                website=entity_website,
                search_hints=merged_search_hints,
                founded=founded_year,
                verification_status=verification_status,
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
                        topics=list(template.topics or []),
                        template=template,
                    )

                    if vr.errors:
                        result.errors.extend(f"{slug}: {e}" for e in vr.errors)

                    # Every branch below writes a claim, so sources go to disk first.
                    source_ids = vr.persist_sources(repo_root, onboard_url_index)
                    if iter_cfg.force_overwrite:
                        mark_forced_rewrite(
                            existing_claim_path, source_ids,
                            datetime.datetime.now(datetime.timezone.utc),
                        )

                    # Threshold-blocked branch: persist a placeholder claim
                    # file with status='blocked' so the operator can see
                    # (and later re-run or archive) the halted work.
                    # Sources that did ingest are still written out.
                    if vr.blocked_reason is not None:
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
                        reason_label = _blocked_reason_label(vr.blocked_reason.value, vr.errors, failure=vr.failure)
                        result.claims_blocked.append((str(blocked_path.relative_to(repo_root)), reason_label))
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=vr.sources_consulted(),
                            agents_run=["researcher", "ingestor"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor"]},
                            research_trace=vr.research_trace,
                            sub_questions_block=_build_sub_questions_block(
                                vr.sub_questions,
                                vr.sub_question_coverage,
                                vr.queries_by_sub_question,
                            ),
                            failure=vr.failure,
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
                        reason_label = _blocked_reason_label(BlockedReason.ANALYST_ERROR.value, vr.errors, failure=vr.failure)
                        result.claims_blocked.append((str(blocked_path.relative_to(repo_root)), reason_label))
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=vr.sources_consulted(),
                            agents_run=["researcher", "ingestor", "analyst"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor", "analyst"]},
                            research_trace=vr.research_trace,
                            sub_questions_block=_build_sub_questions_block(
                                vr.sub_questions,
                                vr.sub_question_coverage,
                                vr.queries_by_sub_question,
                            ),
                            failure=vr.failure,
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
                            sources_consulted=vr.sources_consulted(),
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

                    level_clamp = fit_verdict_to_written_pool(
                        ao.verdict, vr.sources, source_ids, entity_name
                    )
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
                    sidecar_sources = vr.sources_consulted()
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
                        analyst_record=analyst_record_for(ao.verdict),
                        level_clamp=level_clamp,
                    )

                    progress("[%d/%d] Done: %s", idx, total, slug)
                except Exception as exc:
                    progress("[%d/%d] FAILED: %s: %s", idx, total, slug, exc)
                    logger.error("Template %s failed: %s", slug, exc)
                    result.errors.append(f"{slug}: {exc}")
                    result.claims_failed.append(slug)

    return result
