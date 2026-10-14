"""The claim run: ``run`` (research, ingest, analyse, evaluate) and ``rerun`` (one agent)."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

import click
import httpx

from analyst.agent import AnalystOutput
from auditor.compare import needs_review_reasons
from common.logging_setup import bind_run_id, progress
from common.models import BlockedReason, FailureInfo
from loop.analyse import _apply_cited_filter, analyse_claim, audit_claim
from loop.errors import StepError
from loop.ingest import _addresses_with_aliases, _build_source_dict, _ingest_claim_sources
from loop.research import _apply_url_dedup, _invert_addresses, _research, _warn_uncovered
from loop.spec import ClaimSpec, VerificationResult, VerifyConfig, _cfg_repo_root
from orchestrator.checkpoints import AutoApproveCheckpointHandler, CheckpointHandler
from orchestrator.persistence import build_source_url_index

logger = logging.getLogger(__name__)


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


_NO_URLS_ERR = "Researcher agent found no relevant URLs"


def blocked_reason_label(
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


async def run(
    spec: ClaimSpec,
    config: VerifyConfig,
    *,
    checkpoint: CheckpointHandler | None = None,
    sem: asyncio.Semaphore | None = None,
    url_index: dict[str, str] | None = None,
) -> VerificationResult:
    """Run the full verification pipeline.

    1. Researcher: search for relevant sources
    2. Ingestor: fetch and structure each source
    3. Analyst: synthesize sources into a claim with verdict
    4. Auditor: independently assess the claim
    5. [Checkpoint on disagreement] Review conflict

    The auditor grades ``spec.statement``; ``spec.grading_rule`` reaches
    both agents.

    Returns a VerificationResult with all intermediate outputs.
    """
    entity_name = spec.entity.entity_name
    claim_text = spec.statement
    resolved_entity = spec.entity
    topics = spec.topics
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
            result.url_aliases = notes.aliases

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
            criterion_notes = spec.grading_rule
            analyst_out, analyst_failure = await analyse_claim(
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
            cited_sources = _apply_cited_filter(result, analyst_out, entity_name)
            say("  › Auditing")
            logger.info("Step 4/4: Running auditor check...")
            comparison = await audit_claim(
                entity_name, claim_text, analyst_out, cited_sources, cfg,
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


async def rerun(
    spec: ClaimSpec,
    config: VerifyConfig,
    sources: list[dict],
    agent: str,
    analyst_output: AnalystOutput | None = None,
    *,
    checkpoint: CheckpointHandler | None = None,
) -> VerificationResult:
    """Run one agent over stored sources: no research, no ingest, no write.

    ``agent`` is ``"analyst"`` (assess ``spec.statement`` from ``sources``;
    ``consistency`` stays None) or ``"evaluator"`` (grade ``analyst_output``
    against ``sources``). Each agent goes through the same null retry as in
    ``run``. The Evaluator grades ``spec.statement``, as in ``run``.
    """
    if agent not in ("analyst", "evaluator"):
        raise ValueError(f"rerun agent must be 'analyst' or 'evaluator', not {agent!r}")
    if agent == "evaluator" and analyst_output is None:
        raise ValueError("rerun(agent='evaluator') needs the analyst output it grades")

    entity_name = spec.entity.entity_name
    result = VerificationResult(
        entity=entity_name,
        claim_text=spec.statement,
        urls_found=[],
        urls_ingested=[sd["url"] for sd in sources if sd.get("url")],
        urls_failed=[],
        sources=list(sources),
    )

    with bind_run_id(config.run_id):
        logger.info("rerun entry: agent=%s entity=%s claim=%s", agent, entity_name, spec.statement)
        if agent == "analyst":
            analyst_out, analyst_failure = await analyse_claim(
                entity_name, spec.statement, result.sources, config,
                resolved_entity=spec.entity,
                sub_questions=None,
                repo_root=_cfg_repo_root(config),
                criterion_notes=spec.grading_rule,
            )
            result.analyst_output = analyst_out
            if not analyst_out:
                result.errors.append("Analyst failed to produce an assessment")
                result.failure = analyst_failure
            return result

        result.analyst_output = analyst_output
        statement = spec.statement
        comparison = await audit_claim(
            entity_name, statement, analyst_output, result.sources, config,
            criterion_notes=spec.grading_rule,
        )
        result.consistency = comparison
        if comparison is None:
            result.errors.append("Evaluator failed to produce an assessment")
        elif comparison.needs_review and checkpoint is not None:
            accept = await checkpoint.review_disagreement(comparison)
            if not accept:
                result.errors.append(
                    f"Flagged for human review: {', '.join(needs_review_reasons(comparison))}"
                )
    return result
