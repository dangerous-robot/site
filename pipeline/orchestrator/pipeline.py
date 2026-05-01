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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import click
import httpx
import openai
from pydantic import BaseModel, ConfigDict, Field

import dataclasses

from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior

from analyst.agent import AnalystOutput, analyst_agent, build_analyst_prompt
from auditor.agent import auditor_agent, build_auditor_prompt
from common.blocklist import filter_urls, load_blocklist
from common.content_loader import resolve_repo_root
from common.logging_setup import bind_run_id, new_run_id, progress, run_id_var
from common.models import BlockedReason, Category, Confidence, EntityType, Verdict
from common.templates import VOCABULARY_HINT_PREFIX, get_template, load_templates, render_blocked_title, render_claim_text, templates_for_entity_type
from common.timeouts import ingest_budget_with_wayback_s
from common.utils import slugify
from auditor.bundle import build_bundle
from auditor.compare import compare
from auditor.models import ComparisonResult
from common.models import AGENT_NAMES, DEFAULT_MODEL, AgentName, resolve_model
from ingestor.agent import IngestorDeps, ingestor_agent
from ingestor.models import SourceFile
from ingestor.tools.web_fetch import TerminalFetchError
from orchestrator.checkpoints import AutoApproveCheckpointHandler, CheckpointHandler, StepError
from researcher.agent import ResearchDeps, research_agent

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
    # Researcher-step trace: planner queries+rationale and scorer rationale
    # for the decomposed mode; just the classic researcher's reasoning string
    # for classic mode. Persisted to the audit sidecar so reviewers can see
    # how the source set was assembled.
    research_trace: dict | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


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


def _record_threshold_block(
    result: VerificationResult, ingest_errors: list[StepError]
) -> None:
    """Mark `result` as blocked by the < 4 source threshold and emit logs."""
    result.blocked_reason = _classify_blocked_reason(ingest_errors)
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
    # single-model path unchanged while letting `dr` mix providers per agent
    # (e.g. analyst on Infomaniak gpt-oss, auditor on Mistral-Small).
    researcher_model: str | None = None
    analyst_model: str | None = None
    auditor_model: str | None = None
    ingestor_model: str | None = None
    max_sources: int = 8
    # Interim default: wayback ON. The wayback-archive-job plan envisions
    # archival as a background job with skip_wayback=True in-pipeline, but
    # until that job lands we want primary sources behind paywalls/blocks
    # rescued via web.archive.org during the synchronous run.
    skip_wayback: bool = False
    repo_root: str = ""
    # ``ingest_timeout_s`` is ``None`` when the caller hasn't set it, so
    # ``__post_init__`` can pick a default based on ``skip_wayback``. Callers
    # that pass any float (including 60.0) keep that value verbatim.
    ingest_timeout_s: float | None = None
    research_timeout_s: float = 120.0
    analyst_timeout_s: float = 120.0
    auditor_timeout_s: float = 120.0
    force_overwrite: bool = False
    # Temporary validation scaffold: switches between "classic" tool-using agent
    # and the new 3-step decomposed pipeline. Removed post-validation.
    researcher_mode: Literal["classic", "decomposed"] = "decomposed"
    # Effort lever for decomposed researcher: more queries = wider net.
    max_initial_queries: int = 4
    # Integer cap for the shared asyncio.Semaphore created at each call site.
    # Never store the Semaphore itself here — it is loop-bound.
    llm_concurrency: int = 8
    # Correlates every log record (and future token-usage record) emitted
    # during one top-level pipeline invocation. Inherits a CLI-bound id if
    # set; onboard's per-template loop overrides via dataclasses.replace.
    run_id: str = field(default_factory=lambda: run_id_var.get() or new_run_id())

    def __post_init__(self) -> None:
        if self.ingest_timeout_s is None:
            self.ingest_timeout_s = (
                ingest_budget_with_wayback_s() if not self.skip_wayback else 60.0
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

    with bind_run_id(cfg.run_id):
        logger.info("verify_claim entry: entity=%s claim=%s", entity_name, claim_text)
        async with httpx.AsyncClient() as client:
            # Step 1: Research
            logger.info("Step 1/4: Searching for sources...")
            urls, research_errors, trace = await _research(client, entity_name, claim_text, cfg, _sem)
            result.urls_found = urls
            result.research_trace = trace

            if not urls:
                result.errors.append("Researcher agent found no relevant URLs")
                return result

            # Step 2: Ingest
            logger.info("Step 2/4: Ingesting %d sources...", len(urls))
            source_files, ingest_errors = await _ingest_urls(client, urls, cfg, _sem)

            for url, sf in source_files:
                result.urls_ingested.append(url)
                result.sources.append(_build_source_dict(sf))
                result.source_files.append((url, sf))

            ingested_set = set(result.urls_ingested)
            result.urls_failed = [u for u in urls if u not in ingested_set]
            all_errors = research_errors + ingest_errors

            # Checkpoint: review sources
            proceed = await gate.review_sources(
                urls_found=len(result.urls_found),
                urls_ingested=len(result.urls_ingested),
                errors=all_errors,
            )
            if not proceed:
                result.errors.append("Halted at source review checkpoint")
                return result

            # Threshold gate: Orchestrator halts the claim before invoking the
            # Analyst when fewer than two usable sources were obtained. See
            # docs/plans/claim-lifecycle-states.md § Behavior change.
            if below_threshold(result.sources):
                _record_threshold_block(result, ingest_errors)
                return result

            # Step 3: Analyst
            logger.info("Step 3/4: Analysing claim from %d sources...", len(result.sources))
            analyst_out = await _analyse_claim(entity_name, claim_text, result.sources, cfg)
            result.analyst_output = analyst_out

            if not analyst_out:
                result.errors.append("Analyst failed to produce an assessment")
                return result

            # Step 4: Auditor
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

    return result


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
    urls = kept[: cfg.max_sources]
    # DEBUG
    for u in kept[cfg.max_sources:]:
        click.echo(f"[drop:cap] {u}  reason: over max_sources={cfg.max_sources}", err=True)
    # END DEBUG
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


async def _research(
    client: httpx.AsyncClient,
    entity_name: str,
    claim_text: str,
    cfg: VerifyConfig,
    sem: asyncio.Semaphore,
) -> tuple[list[str], list[StepError], dict]:
    """Run the configured researcher and return ``(urls, errors, trace)``.

    ``trace`` is a dict suitable for the audit sidecar's ``research:`` block.
    Always populated with at least ``mode``; further fields depend on the
    researcher path and how far it got before any error.
    """
    if cfg.researcher_mode == "decomposed":
        from researcher.decomposed import decomposed_research
        raw_urls, errors, trace = await decomposed_research(claim_text, entity_name, cfg, sem, client)
        urls, errors = _apply_blocklist_cap(raw_urls, cfg, errors)
        logger.info("Decomposed research: %d kept (cap=%d)", len(urls), cfg.max_sources)
        trace["urls_after_blocklist"] = len(urls)
        return urls, errors, trace

    # Classic path
    deps = ResearchDeps(http_client=client)
    prompt = f"Entity: {entity_name}\nClaim to verify: {claim_text}"
    trace: dict = {"mode": "classic"}

    try:
        async with sem:
            with research_agent.override(model=resolve_model(cfg.model_for("researcher"))):
                res = await asyncio.wait_for(
                    research_agent.run(prompt, deps=deps), timeout=cfg.research_timeout_s
                )
        raw_urls = res.output.urls
        urls, errors = _apply_blocklist_cap(raw_urls, cfg)
        trace["urls_raw"] = len(raw_urls)
        trace["urls_after_blocklist"] = len(urls)
        trace["reasoning"] = res.output.reasoning
        logger.info(
            "Research: %d raw, %d blocked, %d kept (cap=%d). Reasoning: %s",
            len(raw_urls),
            len(raw_urls) - len(urls),
            len(urls),
            cfg.max_sources,
            res.output.reasoning,
        )
        return urls, errors, trace
    except asyncio.TimeoutError:
        err = StepError(step="research", error_type="timeout", message="Research timed out")
        logger.error("Researcher timed out")
        trace["timed_out"] = True
        return [], [err], trace
    except Exception as exc:
        error_type = "api_key_missing" if "API key" in str(exc) else "model_error"
        err = StepError(step="research", error_type=error_type, message=str(exc))
        logger.error("Researcher agent failed: %s", exc)
        return [], [err], trace


async def _ingest_one(
    client: httpx.AsyncClient,
    url: str,
    cfg: VerifyConfig,
    today: datetime.date,
    sem: asyncio.Semaphore,
) -> tuple[str, SourceFile] | StepError:
    """Ingest a single URL. Returns a (url, SourceFile) tuple on success or a StepError."""
    deps = IngestorDeps(
        http_client=client,
        repo_root=cfg.repo_root,
        skip_wayback=cfg.skip_wayback,
        today=today,
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
        logger.info("Ingested: %s -> %s", url, res.output.frontmatter.title)
        return (url, res.output)
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
) -> tuple[list[tuple[str, SourceFile]], list[StepError]]:
    """Run the ingestor agent on all URLs concurrently. Returns (successes, errors)."""
    today = datetime.date.today()
    outcomes = await asyncio.gather(
        *[_ingest_one(client, url, cfg, today, sem) for url in urls]
    )
    results = [o for o in outcomes if isinstance(o, tuple)]
    errors = [o for o in outcomes if isinstance(o, StepError)]
    return results, errors


def _build_source_dict(sf: SourceFile) -> dict:
    return {
        "title": sf.frontmatter.title,
        "publisher": sf.frontmatter.publisher,
        "summary": sf.frontmatter.summary,
        "key_quotes": sf.frontmatter.key_quotes or [],
        "body": sf.body,
        "slug": sf.slug,
        "url": sf.frontmatter.url,
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
    entity_name: str,
    claim_text: str,
    sources: list[dict],
    cfg: VerifyConfig,
) -> AnalystOutput | None:
    prompt = build_analyst_prompt(entity_name, claim_text, sources)
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

    with bind_run_id(cfg.run_id):
        logger.info("research_claim entry: claim=%s", claim_text)
        async with httpx.AsyncClient() as client:
            # Step 1: Research
            logger.info("Step 1/5: Searching for sources...")
            urls, research_errors, trace = await _research(client, "", claim_text, cfg, _sem)
            result.urls_found = urls
            result.research_trace = trace

            if not urls:
                result.errors.append("Researcher agent found no relevant URLs")
                return result

            # Step 2: Ingest
            logger.info("Step 2/5: Ingesting %d sources...", len(urls))
            source_files, ingest_errors = await _ingest_urls(client, urls, cfg, _sem)

            for url, sf in source_files:
                result.urls_ingested.append(url)
                result.sources.append(_build_source_dict(sf))
                result.source_files.append((url, sf))

            ingested_set = set(result.urls_ingested)
            result.urls_failed = [u for u in urls if u not in ingested_set]
            all_errors = research_errors + ingest_errors

            # Checkpoint: review sources
            proceed = await gate.review_sources(
                urls_found=len(result.urls_found),
                urls_ingested=len(result.urls_ingested),
                errors=all_errors,
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
            logger.info("Step 3/5: Writing %d source files...", len(source_files))
            source_ids = _write_source_files(source_files, repo_root)

            # Step 4: Analyse claim (analyst identifies entity)
            logger.info("Step 4/5: Analysing claim...")
            analyst_out = await _analyse_claim(None, claim_text, result.sources, cfg)
            result.analyst_output = analyst_out

            if not analyst_out:
                result.errors.append("Analyst failed to produce an assessment")
                return result

            result.entity = analyst_out.entity.entity_name

            # Write entity and claim to disk
            entity_ref = _write_entity_file(
                entity_name=analyst_out.entity.entity_name,
                entity_type=analyst_out.entity.entity_type,
                entity_description=analyst_out.entity.entity_description,
                repo_root=repo_root,
                aliases=analyst_out.entity.aliases or None,
            )
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
            )
            try:
                result.claim_path = str(claim_path.relative_to(Path(repo_root)))
            except ValueError:
                # Claim path lies outside repo_root (unusual but possible
                # in tests with mocked roots); fall back to the absolute path.
                result.claim_path = str(claim_path)

            # Step 5: Auditor check
            logger.info("Step 5/5: Running auditor check...")
            comparison = await _audit_claim(
                analyst_out.entity.entity_name, claim_text, analyst_out, result.sources, cfg
            )
            result.consistency = comparison

            # Write audit sidecar after auditor step
            sidecar_sources = _build_sources_consulted(result.source_files)
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
            )

            # Checkpoint: review disagreement
            if comparison and comparison.needs_review:
                accept = await gate.review_disagreement(comparison)
                if not accept:
                    result.errors.append("Flagged for human review: analyst/auditor disagree")

    return result


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


async def onboard_entity(
    entity_name: str,
    entity_type: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    seed_url: str | None = None,
    only: list[str] | None = None,
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
        _write_audit_sidecar,
        _write_claim_file,
        _write_draft_entity_file,
        _write_entity_file,
        _write_source_files,
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
        logger.info("Onboard step 1: light research for %s", entity_name)
        entity_description = ""
        entity_website: str | None = None
        try:
            async with httpx.AsyncClient() as client:
                if seed_url:
                    _url = seed_url if seed_url.startswith(("http://", "https://")) else f"https://{seed_url}"
                    entity_website = _url
                    logger.info("Onboard step 1: ingesting seed URL %s", _url)
                    source_files, _ = await _ingest_urls(client, [_url], cfg, sem)
                else:
                    query = f"{entity_name} official website"
                    urls, _, _ = await _research(client, entity_name, query, cfg, sem)
                    if urls:
                        entity_website = urls[0]
                    source_files, _ = await _ingest_urls(client, urls[:1], cfg, sem) if urls else ([], [])
                if source_files:
                    _u, sf = source_files[0]
                    entity_description = sf.frontmatter.summary or ""
        except Exception as exc:
            logger.warning("Light research failed: %s", exc)

        # Step 2: Template screening
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
            )
            result.entity_ref = draft_ref
            return result

        if isinstance(decision, list):
            applicable_slugs = decision

        result.templates_applied = applicable_slugs

        # Step 4: Write entity file
        entity_ref = _write_entity_file(
            entity_name=entity_name,
            entity_type=et,
            entity_description=entity_description,
            repo_root=repo_root,
            website=entity_website,
        )
        result.entity_ref = entity_ref

        # Step 5: Per-template research pipeline. Each template gets its own
        # run_id so the per-claim agent runs (researcher/ingestor/analyst/
        # auditor) in verify_claim group cleanly under one id. Token-usage
        # records inherit this id via cfg.run_id.
        total = len(applicable_slugs)
        for idx, slug in enumerate(applicable_slugs, 1):
            iter_cfg = dataclasses.replace(cfg, run_id=new_run_id())
            with bind_run_id(iter_cfg.run_id):
                progress("[%d/%d] Researching: %s ...", idx, total, slug)
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
                entity_slug = slugify(entity_name)
                existing_claim_path = (
                    repo_root / "research" / "claims" / entity_slug / f"{slugify(slug)}.md"
                )
                if existing_claim_path.exists() and not iter_cfg.force_overwrite:
                    progress("[%d/%d] Skipped (exists): %s", idx, total, slug)
                    result.claims_skipped.append(str(existing_claim_path.relative_to(repo_root)))
                    continue

                try:
                    vr = await verify_claim(entity_name, claim_text, iter_cfg, gate, sem=sem)

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
                        result.claims_created.append(str(blocked_path.relative_to(repo_root)))
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=_build_sources_consulted(vr.source_files),
                            agents_run=["researcher", "ingestor"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor"]},
                            research_trace=vr.research_trace,
                        )
                        progress(
                            "[%d/%d] Blocked: %s (%s)",
                            idx,
                            total,
                            slug,
                            vr.blocked_reason.value,
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
                        result.claims_created.append(
                            str(blocked_path.relative_to(repo_root))
                        )
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=_build_sources_consulted(vr.source_files),
                            agents_run=["researcher", "ingestor", "analyst"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor", "analyst"]},
                            research_trace=vr.research_trace,
                        )
                        progress(
                            "[%d/%d] Blocked: %s (%s)",
                            idx,
                            total,
                            slug,
                            BlockedReason.ANALYST_ERROR.value,
                        )
                        continue

                    ao = vr.analyst_output
                    if template.vocabulary and VOCABULARY_HINT_PREFIX in ao.verdict.title:
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
                            f"The Analyst did not resolve the vocabulary placeholder in the "
                            f"title. Re-run the pipeline with better sources, or resolve "
                            f"the vocabulary manually.\n"
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
                        result.claims_created.append(str(blocked_path.relative_to(repo_root)))
                        _write_audit_sidecar(
                            claim_path=blocked_path,
                            comparison=None,
                            model=iter_cfg.model,
                            ran_at=datetime.datetime.now(datetime.timezone.utc),
                            sources_consulted=_build_sources_consulted(vr.source_files),
                            agents_run=["researcher", "ingestor", "analyst"],
                            models_used={a: iter_cfg.model_for(a) for a in ["researcher", "ingestor", "analyst"]},
                            research_trace=vr.research_trace,
                        )
                        progress(
                            "[%d/%d] Blocked: %s (%s, unresolved vocabulary)",
                            idx,
                            total,
                            slug,
                            BlockedReason.ANALYST_ERROR.value,
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
                    )
                    result.claims_created.append(str(claim_path.relative_to(repo_root)))

                    # Write audit sidecar after auditor step
                    sidecar_sources = _build_sources_consulted(vr.source_files)
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
                    )

                    progress("[%d/%d] Done: %s", idx, total, slug)
                except Exception as exc:
                    progress("[%d/%d] FAILED: %s: %s", idx, total, slug, exc)
                    logger.error("Template %s failed: %s", slug, exc)
                    result.errors.append(f"{slug}: {exc}")
                    result.claims_failed.append(slug)

    return result
