"""The claim run: ``run`` (research, ingest, analyse, evaluate, tie-break, restate) and ``rerun`` (one agent).

Every step runs under the error policy (``loop/policy.py``): a failed step is
retried by its rule with the earlier steps' outputs kept in memory, and a
run that is abandoned, recovered or settled by the tie-breaker leaves a
finding on ``VerificationResult.finding``. A restater that fails after the
verdict is settled costs only the restatement: the finding's outcome is
``partial`` and the run is not abandoned. No step asks a person anything.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import click
import httpx

from analyst.agent import AnalystOutput
from analyst.citations import uncited_by_title
from auditor.compare import needs_tiebreak, settle_verdict
from common.findings import Finding, claim_spec_record, config_record
from common.logging_setup import bind_run_id, progress
from common.models import BlockedReason, FailureInfo
from loop.analyse import _apply_cited_filter, _audit_claim_with_failure, _tiebreak, analyse_claim
from loop.coverage import confirm_coverage
from loop.errors import StepError
from loop.fit import fit_verdict_to_written_pool
from loop.ingest import _addresses_with_aliases, _build_source_dict, _ingest_claim_sources
from loop.recheck import _recheck_cached_sources
from loop.policy import STEP_ON_EXHAUSTION, Rule, classify_exception, is_http_status, rule_for
from loop.restate import needs_restatement, restate_step
from loop.research import _apply_url_dedup, _research, _warn_uncovered
from loop.spec import ClaimSpec, VerificationResult, VerifyConfig, _cfg_repo_root
from orchestrator.entity_resolution import entity_identity_for
from orchestrator.persistence import build_source_url_index

logger = logging.getLogger(__name__)

MIN_USABLE_SOURCES = 4


def below_threshold(usable_sources: list) -> bool:
    """True when fewer than four usable sources are available.

    A "usable" source is one that ingested successfully (parsed body,
    not blocked, not a terminal HTTP error). The loop checks this after
    the ingest step; below the line the step fails, is retried by its
    rule, and an abandoned run stops before the analyst, so the writer is
    never called.
    """
    return len(usable_sources) < MIN_USABLE_SOURCES


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
        # ``http_{status}`` only: ``http_error`` (a provider 5xx, a dropped
        # connection) is a transport failure, not a terminal fetch.
        (e.retryable is False) and is_http_status(e.error_type)
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
    """Mark `result` as blocked by the usable-source threshold and emit logs."""
    result.blocked_reason = _classify_blocked_reason(ingest_errors)
    if result.blocked_reason == BlockedReason.TERMINAL_FETCH_ERROR:
        result.errors.insert(0, _summarize_terminal_fetch(ingest_errors))
    msg = (
        f"Claim halted: < {MIN_USABLE_SOURCES} usable sources "
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


@dataclass
class _StepFailure:
    """One failed attempt of a step: its vocabulary literal, a message and the agent's failure record."""

    error_type: str
    message: str
    failure: FailureInfo | None = None
    # The exception's class, when one escaped the step outside an agent call.
    error_class: str | None = None


def _rule_of(error_type: str) -> Rule:
    """The rule for a literal; a literal outside the table is treated as a model error (a flaw)."""
    try:
        return rule_for(error_type)
    except KeyError:
        return Rule.FLAW_RETRY


def _agent_failure(failure: FailureInfo | None) -> _StepFailure:
    """The step failure for an agent that produced no output."""
    if failure is None:
        return _StepFailure(error_type="model_error", message="the agent returned no output")
    return _StepFailure(
        error_type=failure.error_type or "model_error",
        message=f"{failure.error_class}: {failure.error_message}",
        failure=failure,
    )


def _research_failure(errors: list[StepError]) -> _StepFailure:
    """Why research found no URL: a configuration error first, then a transport error, then a flaw."""
    first: dict[Rule, StepError] = {}
    for e in errors:
        try:
            first.setdefault(rule_for(e.error_type), e)
        except KeyError:
            continue
    flaw = next((e for e in errors if e.error_type == "scorer_dropped_all"), None) or first.get(Rule.FLAW_RETRY)
    chosen = first.get(Rule.CONFIG_FATAL) or first.get(Rule.TRANSPORT_RETRY) or flaw
    if chosen is None:
        return _StepFailure(error_type="no_results", message=_NO_URLS_ERR)
    return _StepFailure(error_type=chosen.error_type, message=chosen.message)


def _threshold_failure(usable: int, ingest_errors: list[StepError]) -> _StepFailure:
    """The ingest step's failure below the four-source line."""
    if _classify_blocked_reason(ingest_errors) == BlockedReason.TERMINAL_FETCH_ERROR:
        return _StepFailure(error_type="terminal_fetch_error", message=_summarize_terminal_fetch(ingest_errors))
    needed = f"{usable} usable sources, {MIN_USABLE_SOURCES} needed"
    ingest_only = [e for e in ingest_errors if e.step == "ingest"]
    if ingest_only and all(_rule_of(e.error_type) is Rule.TRANSPORT_RETRY for e in ingest_only):
        # Every page failed in transit: infrastructure, not a thin candidate list.
        return _StepFailure(
            error_type="sources_unreachable",
            message=f"{needed}; {_summarize_terminal_fetch(ingest_errors)}",
        )
    return _StepFailure(error_type="insufficient_sources", message=needed)


def _retry_entry(step: str, failure: _StepFailure, rule: Rule, attempts: int) -> dict:
    """One recovered step as the finding's ``retries`` records it."""
    return {"step": step, "error_type": failure.error_type, "rule": rule.value, "attempts": attempts}


def _note_abandoned(result: VerificationResult, failed: _StepFailure, message: str) -> None:
    """Record an abandoned step on ``result``; the first agent failure record wins."""
    result.errors.append(message)
    if failed.failure is not None and result.failure is None:
        result.failure = failed.failure


# The agent each step runs, for the finding's ``models_used``.
_STEP_AGENTS = {
    "research": "researcher",
    "ingest": "ingestor",
    "analyse": "analyst",
    "evaluate": "auditor",
    "tiebreak": "tiebreaker",
    "restate": "restater",
}


class _Driver:
    """Runs each step of one run under the error policy and builds the run's finding."""

    def __init__(self, spec: ClaimSpec, cfg: VerifyConfig) -> None:
        self.spec = spec
        self.cfg = cfg
        self.agents: list[str] = []
        # Steps that failed and then succeeded: (step, last failure, rule, attempts).
        self.recovered: list[tuple[str, _StepFailure, Rule, int]] = []
        self.last_attempts = 0
        self.finding: Finding | None = None

    def _allowed_retries(self, rule: Rule) -> int:
        if rule is Rule.FLAW_RETRY:
            return self.cfg.flaw_retries
        if rule is Rule.TRANSPORT_RETRY:
            return self.cfg.transport_retries
        return 0

    def _delay(self, rule: Rule, failure: _StepFailure, retry: int) -> float:
        if rule is not Rule.TRANSPORT_RETRY:
            return 0.0
        if failure.failure is not None and failure.failure.retry_after_s is not None:
            return failure.failure.retry_after_s
        backoff = self.cfg.transport_backoff_s
        if not backoff:
            return 0.0
        return backoff[min(retry, len(backoff) - 1)]

    async def step(self, name: str, attempt: Callable[[], Awaitable[object]]) -> tuple[object, _StepFailure | None]:
        """Run ``attempt`` until it succeeds or its rule's retries run out.

        ``attempt`` returns the step's output, or a ``_StepFailure``; an
        exception it raises is classified like an agent's. Returns
        ``(output, None)`` or ``(None, last failure)``; on the second the
        run's finding is set.
        """
        agent = _STEP_AGENTS.get(name)
        if agent is not None and agent not in self.agents:
            self.agents.append(agent)
        attempts = 0
        last: _StepFailure | None = None
        while True:
            attempts += 1
            self.last_attempts = attempts
            try:
                out = await attempt()
            except Exception as exc:
                error_type, _rule = classify_exception(exc)
                logger.warning("The %s step failed: %s: %s", name, type(exc).__name__, exc)
                logger.debug("The %s step's traceback", name, exc_info=exc)
                out = _StepFailure(
                    error_type=error_type, message=str(exc) or type(exc).__name__,
                    error_class=type(exc).__name__,
                )
            if not isinstance(out, _StepFailure):
                if last is not None:
                    self.recovered.append((name, last, _rule_of(last.error_type), attempts))
                    logger.info("The %s step succeeded on attempt %d", name, attempts)
                return out, None
            last = out
            rule = _rule_of(out.error_type)
            allowed = self._allowed_retries(rule)
            if attempts > allowed:
                outcome = STEP_ON_EXHAUSTION[name]
                if outcome == "abandoned":
                    logger.warning(
                        "Run abandoned at the %s step after %d attempt(s): %s: %s",
                        name, attempts, out.error_type, out.message,
                    )
                else:
                    logger.warning(
                        "The %s step gave up after %d attempt(s); the run goes on (%s): %s: %s",
                        name, attempts, outcome, out.error_type, out.message,
                    )
                self.finding = self._finding(
                    step=name, rule=rule.value, failure=out, attempts=attempts,
                    outcome=outcome, retries=self.recovered,
                )
                return None, out
            delay = self._delay(rule, out, attempts - 1)
            logger.warning(
                "The %s step failed (%s); retry %d of %d in %.0fs",
                name, out.error_type, attempts, allowed, delay,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    def split(self, comparison) -> None:
        """Record the tie-breaker's settlement of a disagreement."""
        message = (
            f"analyst {comparison.primary_verdict.value}, evaluator {comparison.assessed_verdict.value}, "
            f"tie-breaker {comparison.tiebreaker_verdict.value}"
        )
        self.finding = self._finding(
            step="tiebreak", rule=Rule.TIEBREAKER.value,
            failure=_StepFailure(error_type="verdict_split", message=message),
            attempts=self.last_attempts, outcome="split",
            retries=[r for r in self.recovered if r[0] != "tiebreak"],
        )

    def finish(self, result: VerificationResult) -> VerificationResult:
        """Put the run's finding on ``result``: abandoned or split, else the last recovered step."""
        if self.finding is None and self.recovered:
            step, failure, rule, attempts = self.recovered[-1]
            self.finding = self._finding(
                step=step, rule=rule.value, failure=failure, attempts=attempts,
                outcome="recovered", retries=self.recovered[:-1],
            )
        result.finding = self.finding
        return result

    def _finding(
        self, *, step: str, rule: str, failure: _StepFailure, attempts: int, outcome: str,
        retries: list[tuple[str, _StepFailure, Rule, int]],
    ) -> Finding:
        error: dict = {"error_type": failure.error_type, "message": failure.message}
        if failure.failure is not None:
            error["error_class"] = failure.failure.error_class
        elif failure.error_class is not None:
            error["error_class"] = failure.error_class
        return Finding(
            run_id=self.cfg.run_id,
            date=datetime.date.today(),
            claim_spec=claim_spec_record(self.spec),
            config=config_record(self.cfg),
            models_used={a: self.cfg.model_for(a) for a in self.agents},
            step=step,
            rule=rule,
            error=error,
            attempts=attempts,
            outcome=outcome,
            retries=[_retry_entry(*r) for r in retries],
        )


def _keep_labels(sources: list[dict]) -> Callable[[], None]:
    """Snapshot each source's ``independence``; the returned call puts it back.

    The analyst step relabels sources in place for the entity, and the
    relabels become the claim's overrides, so a retried analyst step must
    start from the labels the first attempt saw.
    """
    labels = [(sd, "independence" in sd, sd.get("independence")) for sd in sources]

    def restore() -> None:
        for sd, had, label in labels:
            if had:
                sd["independence"] = label
            else:
                sd.pop("independence", None)

    return restore


async def _analyse_step(
    driver: _Driver,
    result: VerificationResult,
    spec: ClaimSpec,
    cfg: VerifyConfig,
    *,
    sub_questions,
    repo_root,
) -> bool:
    """The analyst step; False when it was abandoned."""
    restore = _keep_labels(result.sources)

    async def attempt():
        restore()
        out, failure = await analyse_claim(
            spec.entity.entity_name, spec.statement, result.sources, cfg,
            resolved_entity=spec.entity,
            sub_questions=sub_questions,
            repo_root=repo_root,
            criterion_notes=spec.grading_rule,
        )
        return out if out is not None else _agent_failure(failure)

    analyst_out, failed = await driver.step("analyse", attempt)
    result.analyst_output = analyst_out
    if failed is not None:
        _note_abandoned(result, failed, "Analyst failed to produce an assessment")
        return False
    result.uncited_by_title = uncited_by_title(analyst_out.verdict, result.sources)
    return True


async def _evaluate_and_settle(
    driver: _Driver,
    result: VerificationResult,
    spec: ClaimSpec,
    cfg: VerifyConfig,
    sources: list[dict],
    say: Callable[..., None],
) -> bool:
    """The Evaluator step, then the tie-breaker step on a disagreement; False when either was abandoned."""
    analyst_out = result.analyst_output

    async def evaluate():
        comparison, failure = await _audit_claim_with_failure(
            spec.statement, analyst_out, sources, cfg, criterion_notes=spec.grading_rule,
        )
        return comparison if comparison is not None else _agent_failure(failure)

    comparison, failed = await driver.step("evaluate", evaluate)
    if failed is not None:
        _note_abandoned(result, failed, "Evaluator failed to produce an assessment")
        return False
    result.consistency = comparison
    if not needs_tiebreak(comparison):
        return True

    say("  › Tie-breaking")
    logger.info(
        "Tie-break: analyst %s, Evaluator %s",
        comparison.primary_verdict.value, comparison.assessed_verdict.value,
    )

    async def tiebreak():
        assessment, failure = await _tiebreak(
            spec.statement, analyst_out, sources, cfg, criterion_notes=spec.grading_rule,
        )
        return assessment if assessment is not None else _agent_failure(failure)

    assessment, failed = await driver.step("tiebreak", tiebreak)
    if failed is not None:
        _note_abandoned(result, failed, "Tie-breaker failed to produce an assessment")
        return False
    result.consistency = settle_verdict(comparison, assessment)
    driver.split(result.consistency)
    return True


async def _restate(
    driver: _Driver,
    result: VerificationResult,
    spec: ClaimSpec,
    cfg: VerifyConfig,
    *,
    cited_ids: list[str],
    trigger: str,
) -> None:
    """The restate step; on failure the run goes on with no block and a ``partial`` finding.

    A failure after a tie-break replaces the run's ``split`` finding, so the
    split is carried in the new finding's ``retries`` with its message; a
    success after a tie-break adds the restater to the split finding, with
    the retry when the restater needed one.
    """
    split = driver.finding if driver.finding is not None and driver.finding.outcome == "split" else None

    async def attempt():
        block, failure = await restate_step(result, spec, cfg, cited_ids=cited_ids, trigger=trigger)
        return block if block is not None else _agent_failure(failure)

    block, failed = await driver.step("restate", attempt)
    if failed is None:
        result.restatement = block
        if split is not None:
            # The split finding was built before the restater ran, so it
            # names neither the restater's model nor a retry it needed.
            split.models_used.setdefault("restater", cfg.model_for("restater"))
            if driver.recovered and driver.recovered[-1][0] == "restate":
                split.retries.append(_retry_entry(*driver.recovered[-1]))
        return
    result.errors.append("Restater failed; the claim is written without a restatement")
    if split is not None and driver.finding is not None:
        driver.finding.retries.insert(0, {
            "step": "tiebreak", "error_type": "verdict_split", "rule": Rule.TIEBREAKER.value,
            "attempts": split.attempts, "message": split.error.get("message"),
        })


async def run(
    spec: ClaimSpec,
    config: VerifyConfig,
    *,
    sem: asyncio.Semaphore | None = None,
    url_index: dict[str, str] | None = None,
) -> VerificationResult:
    """Run the full verification pipeline.

    1. Researcher: search for relevant sources
    2. Ingestor: fetch and structure each source
    3. Analyst: synthesize sources into a claim with verdict
    4. Evaluator: independently assess the claim
    5. Tie-break a disagreement (``loop/tiebreaker/``)
    6. Restate a weak or tie-broken verdict (``loop/restater/``)

    The Evaluator and the tie-breaker grade ``spec.statement``;
    ``spec.grading_rule`` reaches every agent that grades. Each step follows
    the error policy; ``result.finding`` records a retried, abandoned or
    tie-broken run.

    Returns a VerificationResult with all intermediate outputs.
    """
    entity_name = spec.entity.entity_name
    claim_text = spec.statement
    resolved_entity = spec.entity
    topics = spec.topics
    cfg = config
    # Semaphore MUST be created inside the coroutine driven by asyncio.run (loop-bound).
    _sem = sem if sem is not None else asyncio.Semaphore(cfg.llm_concurrency)
    driver = _Driver(spec, cfg)

    result = VerificationResult(
        entity=entity_name,
        claim_text=claim_text,
        urls_found=[],
        urls_ingested=[],
        urls_failed=[],
        sources=[],
        errors=[],
    )

    # Console-only emit (no file-log mirror) — paired logger.info calls below
    # carry the structured "<step>: ..." line for info.log/debug.log.
    if cfg.show_progress:
        say = lambda m, *a: progress(m, *a, log=False)
    else:
        say = lambda *a, **kw: None

    with bind_run_id(cfg.run_id):
        logger.info("run entry: entity=%s claim=%s", entity_name, claim_text)
        async with httpx.AsyncClient() as client:
            # Step 1: Research
            say("  › Searching")
            logger.info("Research: searching for sources...")
            research: dict = {}

            async def research_attempt():
                ro = await _research(
                    client, entity_name, claim_text, cfg, _sem,
                    resolved_entity=resolved_entity, topics=topics,
                )
                research["errors"] = ro.errors
                result.urls_found = ro.urls
                result.research_trace = ro.trace
                result.sub_questions = ro.sub_questions
                result.queries_by_sub_question = ro.queries_by_sub_question
                # Research is the first step, so its errors are the run's so far.
                result.errors = [e.message for e in ro.errors]
                if cfg.show_progress:
                    for e in ro.errors:
                        progress("  ! research: %s", e.message)
                if not ro.urls:
                    return _research_failure(ro.errors)
                return ro

            ro, failed = await driver.step("research", research_attempt)
            if failed is not None:
                result.errors.append(_NO_URLS_ERR)
                if any(e.error_type == "scorer_dropped_all" for e in research.get("errors", [])):
                    result.blocked_reason = BlockedReason.INSUFFICIENT_SOURCES
                return driver.finish(result)
            urls = ro.urls

            # Step 2: Ingest
            say("  › Ingesting")
            logger.info("Ingest: ingesting %d candidate URLs...", len(urls))
            repo_root = _cfg_repo_root(cfg)
            if url_index is None:
                url_index = build_source_url_index(repo_root)
            ingest: dict = {}

            async def ingest_attempt():
                # Each attempt starts from the research output alone.
                result.urls_ingested = []
                result.sources = []
                result.cached_sources = []
                result.source_files = []
                result.page_text = {}
                result.snippet_only = {}
                result.source_rechecks = {}
                urls_to_ingest, cached_sources = _apply_url_dedup(urls, url_index, repo_root)

                source_files, ingest_errors, notes = await _ingest_claim_sources(
                    client, urls_to_ingest, cached_sources, ro, result, cfg, _sem,
                    url_index, repo_root,
                )
                ingest["errors"] = ingest_errors
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

                # Per-sub-question coverage from the post-ingest source set: a
                # scorer tag stands only when the source's text mentions the
                # sub-question's terms. Sub-questions with no confirmed source
                # keep an empty list to surface the gap to the analyst and the
                # audit sidecar.
                result.sub_question_coverage, result.snippet_only = confirm_coverage(
                    ro.sub_questions, ro.queries_by_sub_question, result.sources,
                    result.page_text, entity_identity_for(resolved_entity, repo_root),
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

                # Below four usable sources the step fails; the analyst never runs
                # on a thin pool.
                if below_threshold(result.sources):
                    return _threshold_failure(len(result.sources), ingest_errors)
                return True

            _ok, failed = await driver.step("ingest", ingest_attempt)
            if failed is not None:
                _record_threshold_block(result, ingest.get("errors", []))
                if cfg.show_progress:
                    progress(
                        "  ! blocked before analyst: %s",
                        result.blocked_reason.value if result.blocked_reason else "below_threshold",
                    )
                return driver.finish(result)

            # A recheck re-checks the cached sources older than its cadence,
            # once, after the step has settled which sources are cached.
            result.source_rechecks = await _recheck_cached_sources(
                client, result.cached_sources, ro.prefetched_bodies, cfg, repo_root,
            )

            # Step 3: Analyst
            say("  › Analysing")
            logger.info("Analyse: analysing claim from %d sources...", len(result.sources))
            if not await _analyse_step(
                driver, result, spec, cfg,
                sub_questions=result.sub_questions, repo_root=repo_root,
            ):
                result.blocked_reason = BlockedReason.ANALYST_ERROR
                if cfg.show_progress:
                    progress("  ! analyst failed to produce an assessment")
                return driver.finish(result)

            # Step 4: Evaluator, then the tie-breaker on a disagreement. The
            # level fit runs once, on the listed sources, so the Evaluator
            # grades the fitted verdict and the writer only records the note.
            cited_sources = _apply_cited_filter(result, result.analyst_output, entity_name)
            cited_ids = [sd["source_id"] for sd in cited_sources if sd.get("source_id")]
            result.level_clamp = fit_verdict_to_written_pool(
                result.analyst_output.verdict, result.sources, cited_ids, entity_name,
            )
            say("  › Auditing")
            logger.info("Evaluate: running the Evaluator...")
            if not await _evaluate_and_settle(driver, result, spec, cfg, cited_sources, say):
                if cfg.show_progress:
                    progress("  ! %s", result.errors[-1])
                return driver.finish(result)

            # Step 5: restate a weak or tie-broken verdict. A failure here
            # keeps the settled verdict; the claim is written without a block.
            trigger = needs_restatement(result.consistency)
            if trigger is not None:
                say("  › Restating")
                logger.info("Restating (%s)...", trigger)
                await _restate(
                    driver, result, spec, cfg,
                    cited_ids=cited_ids,
                    trigger=trigger,
                )
                if result.restatement is None and cfg.show_progress:
                    progress("  ! %s", result.errors[-1])

            if cfg.show_progress:
                progress("Pipeline complete.")

    return driver.finish(result)


async def rerun(
    spec: ClaimSpec,
    config: VerifyConfig,
    sources: list[dict],
    agent: str,
    analyst_output: AnalystOutput | None = None,
) -> VerificationResult:
    """Run one agent over stored sources: no research, no ingest, no write.

    ``agent`` is ``"analyst"`` (assess ``spec.statement`` from ``sources``,
    then fit the level to every stored source, the claim's listed sources;
    ``consistency`` stays None) or ``"evaluator"`` (grade ``analyst_output``
    against ``sources``, then settle a disagreement with the tie-breaker).
    Each step follows the same error policy as in ``run``, and
    ``result.finding`` records a retried, abandoned or tie-broken rerun. The
    Evaluator grades ``spec.statement``, as in ``run``.
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
    driver = _Driver(spec, config)

    with bind_run_id(config.run_id):
        logger.info("rerun entry: agent=%s entity=%s claim=%s", agent, entity_name, spec.statement)
        if agent == "analyst":
            if await _analyse_step(
                driver, result, spec, config,
                sub_questions=None, repo_root=_cfg_repo_root(config),
            ):
                result.level_clamp = fit_verdict_to_written_pool(
                    result.analyst_output.verdict, result.sources,
                    [sd["source_id"] for sd in result.sources if sd.get("source_id")], entity_name,
                )
            return driver.finish(result)

        result.analyst_output = analyst_output
        await _evaluate_and_settle(
            driver, result, spec, config, result.sources, lambda *a, **kw: None,
        )
    return driver.finish(result)
