"""Pipeline: chains researcher -> ingestor -> analyst -> auditor."""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from analyst.agent import AnalystOutput, analyst_agent, build_analyst_prompt
from auditor.agent import auditor_agent, build_auditor_prompt
from common.models import EntityType
from common.templates import get_template, load_templates, render_claim_text, templates_for_entity_type
from common.utils import slugify
from auditor.bundle import build_bundle
from auditor.compare import compare
from auditor.models import ComparisonResult
from common.models import DEFAULT_MODEL
from ingestor.agent import IngestorDeps, ingestor_agent
from ingestor.models import SourceFile
from orchestrator.checkpoints import AutoApproveCheckpointHandler, CheckpointHandler, StepError
from researcher.agent import ResearchDeps, research_agent

logger = logging.getLogger(__name__)


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

    model_config = ConfigDict(arbitrary_types_allowed=True)


@dataclass
class VerifyConfig:
    model: str = DEFAULT_MODEL
    max_sources: int = 4
    skip_wayback: bool = True  # default True for faster POC runs
    repo_root: str = ""


async def verify_claim(
    entity_name: str,
    claim_text: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
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

    result = VerificationResult(
        entity=entity_name,
        claim_text=claim_text,
        urls_found=[],
        urls_ingested=[],
        urls_failed=[],
        sources=[],
        errors=[],
    )

    async with httpx.AsyncClient() as client:
        # Step 1: Research
        logger.info("Step 1/4: Searching for sources...")
        urls, research_errors = await _research(client, entity_name, claim_text, cfg)
        result.urls_found = urls

        if not urls:
            result.errors.append("Researcher agent found no relevant URLs")
            return result

        # Step 2: Ingest
        logger.info("Step 2/4: Ingesting %d sources...", len(urls))
        source_files, ingest_errors = await _ingest_urls(client, urls, cfg)

        for url, sf in source_files:
            result.urls_ingested.append(url)
            result.sources.append(_build_source_dict(sf))

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

        if not result.sources:
            result.errors.append("All source URLs failed to ingest")
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


async def _research(
    client: httpx.AsyncClient,
    entity_name: str,
    claim_text: str,
    cfg: VerifyConfig,
) -> tuple[list[str], list[StepError]]:
    deps = ResearchDeps(http_client=client)
    prompt = f"Entity: {entity_name}\nClaim to verify: {claim_text}"

    try:
        with research_agent.override(model=cfg.model):
            res = await asyncio.wait_for(
                research_agent.run(prompt, deps=deps), timeout=60
            )
        urls = res.output.urls[:cfg.max_sources]
        logger.info("Research found %d URLs: %s", len(urls), res.output.reasoning)
        return urls, []
    except asyncio.TimeoutError:
        err = StepError(step="research", error_type="timeout", message="Research timed out")
        logger.error("Researcher timed out")
        return [], [err]
    except Exception as exc:
        error_type = "api_key_missing" if "API key" in str(exc) else "model_error"
        err = StepError(step="research", error_type=error_type, message=str(exc))
        logger.error("Researcher agent failed: %s", exc)
        return [], [err]


async def _ingest_one(
    client: httpx.AsyncClient,
    url: str,
    cfg: VerifyConfig,
    today: datetime.date,
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
        with ingestor_agent.override(model=cfg.model):
            res = await asyncio.wait_for(
                ingestor_agent.run(prompt, deps=deps), timeout=90
            )
        logger.info("Ingested: %s -> %s", url, res.output.frontmatter.title)
        return (url, res.output)
    except asyncio.TimeoutError:
        logger.warning("Ingest timed out: %s", url)
        return StepError(step="ingest", url=url, error_type="timeout", message="Ingest timed out")
    except Exception as exc:
        error_type = "http_error" if "HTTP" in type(exc).__name__ else "model_error"
        logger.warning("Failed to ingest %s: %s", url, exc)
        return StepError(step="ingest", url=url, error_type=error_type, message=str(exc))


async def _ingest_urls(
    client: httpx.AsyncClient,
    urls: list[str],
    cfg: VerifyConfig,
) -> tuple[list[tuple[str, SourceFile]], list[StepError]]:
    """Run the ingestor agent on all URLs concurrently. Returns (successes, errors)."""
    today = datetime.date.today()
    outcomes = await asyncio.gather(
        *[_ingest_one(client, url, cfg, today) for url in urls]
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


async def _analyse_claim(
    entity_name: str,
    claim_text: str,
    sources: list[dict],
    cfg: VerifyConfig,
) -> AnalystOutput | None:
    prompt = build_analyst_prompt(entity_name, claim_text, sources)

    try:
        with analyst_agent.override(model=cfg.model):
            res = await asyncio.wait_for(
                analyst_agent.run(prompt), timeout=60
            )
        return res.output
    except Exception as exc:
        logger.error("Analyst failed: %s", exc)
        return None


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
        category=analyst_out.verdict.category,
        narrative=analyst_out.verdict.narrative,
        sources=sources,
    )

    prompt = build_auditor_prompt(bundle)

    try:
        with auditor_agent.override(model=cfg.model):
            res = await asyncio.wait_for(
                auditor_agent.run(prompt), timeout=60
            )
        assessment = res.output

        return compare(
            analyst_out.verdict.verdict,
            analyst_out.verdict.confidence,
            assessment,
            bundle.claim_id,
            "(draft -- not yet saved)",
        )
    except Exception as exc:
        logger.error("Auditor check failed: %s", exc)
        return None


async def research_claim(
    claim_text: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
) -> VerificationResult:
    """Research a claim, persist sources/entity/claim to disk, and run auditor.

    Unlike verify_claim, this function:
    - Does not require an entity name (the analyst identifies it)
    - Writes source files to research/sources/
    - Creates entity file in research/entities/ if needed
    - Writes the claim file to research/claims/
    """
    from orchestrator.persistence import _write_claim_file, _write_entity_file, _write_source_files

    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        from common.content_loader import resolve_repo_root
        cfg.repo_root = str(resolve_repo_root())

    gate = checkpoint or AutoApproveCheckpointHandler()
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

    async with httpx.AsyncClient() as client:
        # Step 1: Research
        logger.info("Step 1/5: Searching for sources...")
        urls, research_errors = await _research(client, "", claim_text, cfg)
        result.urls_found = urls

        if not urls:
            result.errors.append("Researcher agent found no relevant URLs")
            return result

        # Step 2: Ingest
        logger.info("Step 2/5: Ingesting %d sources...", len(urls))
        source_files, ingest_errors = await _ingest_urls(client, urls, cfg)

        for url, sf in source_files:
            result.urls_ingested.append(url)
            result.sources.append(_build_source_dict(sf))

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

        if not result.sources:
            result.errors.append("All source URLs failed to ingest")
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
        )
        claim_slug = slugify(analyst_out.verdict.title)
        _write_claim_file(
            title=analyst_out.verdict.title,
            entity_name=analyst_out.entity.entity_name,
            entity_ref=entity_ref,
            category=analyst_out.verdict.category,
            verdict=analyst_out.verdict.verdict,
            confidence=analyst_out.verdict.confidence,
            narrative=analyst_out.verdict.narrative,
            claim_slug=claim_slug,
            source_ids=source_ids,
            repo_root=repo_root,
        )

        # Step 5: Auditor check
        logger.info("Step 5/5: Running auditor check...")
        comparison = await _audit_claim(
            analyst_out.entity.entity_name, claim_text, analyst_out, result.sources, cfg
        )
        result.consistency = comparison

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
        _write_claim_file,
        _write_draft_entity_file,
        _write_entity_file,
        _write_source_files,
    )

    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        from common.content_loader import resolve_repo_root
        cfg.repo_root = str(resolve_repo_root())

    gate = checkpoint or AutoApproveCheckpointHandler()
    repo_root = Path(cfg.repo_root)
    et = EntityType(entity_type)

    result = OnboardResult(
        entity_name=entity_name,
        entity_type=entity_type,
        status="accepted",
        entity_ref=None,
    )

    # Step 1: Light research for entity context
    logger.info("Onboard step 1: light research for %s", entity_name)
    entity_description = entity_name
    try:
        async with httpx.AsyncClient() as client:
            query = f"{entity_name} official website"
            urls, _ = await _research(client, entity_name, query, cfg)
            if urls:
                source_files, _ = await _ingest_urls(client, urls[:1], cfg)
                if source_files:
                    _url, sf = source_files[0]
                    entity_description = sf.frontmatter.summary or entity_name
    except Exception as exc:
        logger.warning("Light research failed, using entity name as description: %s", exc)

    # Step 2: Template screening
    logger.info("Onboard step 2: screening templates")
    all_templates = load_templates(repo_root)
    typed_templates = templates_for_entity_type(all_templates, entity_type)

    if not typed_templates:
        result.errors.append(f"No core templates found for entity_type={entity_type}")
        result.status = "rejected"
        return result

    applicable_slugs, excluded = _screen_templates(entity_description, typed_templates)
    result.templates_excluded = excluded

    # Step 3: Checkpoint
    logger.info("Onboard step 3: checkpoint review")
    decision = await gate.review_onboard(
        entity_name, entity_type, applicable_slugs, excluded
    )

    if decision == "reject":
        result.status = "rejected"
        draft_ref = _write_draft_entity_file(
            entity_name=entity_name,
            entity_type=et,
            entity_description=entity_description,
            repo_root=repo_root,
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
    )
    result.entity_ref = entity_ref

    # Step 5: Per-template research pipeline (sequential)
    for slug in applicable_slugs:
        template = get_template(all_templates, slug)
        if not template:
            result.errors.append(f"Template not found: {slug}")
            result.claims_failed.append(slug)
            continue

        claim_text = render_claim_text(template, entity_name)
        logger.info("Onboard: researching template %s -> %s", slug, claim_text)

        try:
            vr = await verify_claim(entity_name, claim_text, cfg, gate)

            if vr.errors:
                result.errors.extend(vr.errors)

            if not vr.analyst_output:
                result.claims_failed.append(slug)
                continue

            # Write sources
            source_tuples = []
            async with httpx.AsyncClient() as client:
                urls, _ = await _research(client, entity_name, claim_text, cfg)
                if urls:
                    source_tuples, _ = await _ingest_urls(client, urls, cfg)

            source_ids = _write_source_files(source_tuples, repo_root) if source_tuples else []

            # Write claim file
            ao = vr.analyst_output
            claim_path = _write_claim_file(
                title=ao.verdict.title,
                entity_name=entity_name,
                entity_ref=entity_ref,
                category=ao.verdict.category,
                verdict=ao.verdict.verdict,
                confidence=ao.verdict.confidence,
                narrative=ao.verdict.narrative,
                claim_slug=slug,
                source_ids=source_ids,
                repo_root=repo_root,
            )
            result.claims_created.append(str(claim_path.relative_to(repo_root)))
        except Exception as exc:
            logger.error("Template %s failed: %s", slug, exc)
            result.errors.append(f"Template {slug}: {exc}")
            result.claims_failed.append(slug)

    return result
