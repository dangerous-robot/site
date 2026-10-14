"""Analyse and evaluate steps: the Analyst, the entity match, the cited filter, the Evaluator."""

from __future__ import annotations

import asyncio
import logging
import traceback
from pathlib import Path

import openai
from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior

from analyst.agent import (
    AnalystOutput,
    EntityResolution,
    SourceOverride,
    VerdictAssessment,
    build_analyst_prompt,
    verdict_only_agent,
)
from analyst.citations import cited_source_ids, clean_citations
from auditor.agent import auditor_agent, build_auditor_prompt
from auditor.bundle import build_bundle
from auditor.compare import compare
from auditor.models import ComparisonResult
from common.models import EntityType, FailureInfo, FailureStep, Independence, SubQuestion, resolve_model
from common.source_classification import (
    entity_affiliated,
    entity_first_party_reason,
    publisher_named_in_claim,
    source_engages_entity,
)
from common.utils import url_host
from loop.spec import VerificationResult, VerifyConfig, _cfg_repo_root
from orchestrator.entity_resolution import ResolvedEntity, entity_identity_for
from orchestrator.persistence import shorten

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


def apply_entity_match(
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
        override.code_relabel = True
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


async def analyse_claim(
    entity_name: str,
    claim_text: str,
    sources: list[dict],
    cfg: VerifyConfig,
    resolved_entity: ResolvedEntity,
    sub_questions: list[SubQuestion] | None = None,
    repo_root: Path | None = None,
    criterion_notes: str | None = None,
) -> tuple[AnalystOutput | None, FailureInfo | None]:
    """Run the analyst agent. Returns (output, failure) — failure is set
    only when output is None, so callers can persist structured failure
    detail into the audit sidecar and progress line.

    ``apply_entity_match`` relabels ``sources`` in place (so the auditor and
    sidecar see the same labels) and the changes are recorded on the
    verdict's ``source_overrides``.
    """
    entity_overrides = apply_entity_match(
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


def _clean_verdict_citations(verdict: VerdictAssessment, sources: list[dict]) -> None:
    """Replace citation tokens and "Source N" references in the narrative with source titles.

    ``takeaway`` and ``cap_rationale`` reject citations at validation time.
    ``sources`` must be the list, in order, that the analyst prompt was built
    from: "Source N" means the Nth source listed there.
    """
    verdict.narrative, unresolved = clean_citations(verdict.narrative, sources)
    if unresolved:
        logger.warning("Analyst output has unresolved citation references: %s", unresolved)


async def audit_claim(
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
    analyst_overrides = [o for o in verdict.source_overrides or [] if not o.code_relabel]
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
