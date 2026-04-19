"""Orchestrator: chains research -> ingest -> draft -> consistency check."""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, ConfigDict

from common.models import DEFAULT_MODEL, Confidence, Verdict, VerdictSeverity
from consistency.agent import ConsistencyDeps, build_user_prompt, consistency_agent
from consistency.compare import compare
from consistency.models import (
    ClaimBundle,
    ComparisonResult,
    EntityContext,
    IndependentAssessment,
    SourceContext,
)
from ingestor.agent import IngestorDeps, ingestor_agent
from ingestor.models import SourceFile

from .drafter import ClaimDraft, DrafterDeps, build_drafter_prompt, drafter_agent
from .researcher import ResearchDeps, research_agent

logger = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    """Full output of an end-to-end claim verification."""

    entity: str
    claim_text: str
    urls_found: list[str]
    urls_ingested: list[str]
    urls_failed: list[str]
    sources: list[dict]
    draft: ClaimDraft | None = None
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
) -> VerificationResult:
    """Run the full verification pipeline.

    1. Research: search for relevant sources
    2. Ingest: fetch and structure each source
    3. Draft: synthesize sources into a claim with verdict
    4. Consistency: independently assess the claim

    Returns a VerificationResult with all intermediate outputs.
    """
    cfg = config or VerifyConfig()
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
        urls = await _research(client, entity_name, claim_text, cfg)
        result.urls_found = urls

        if not urls:
            result.errors.append("Research agent found no relevant URLs")
            return result

        # Step 2: Ingest
        logger.info("Step 2/4: Ingesting %d sources...", len(urls))
        source_files = await _ingest_urls(client, urls, cfg)

        for url, sf in source_files:
            result.urls_ingested.append(url)
            result.sources.append({
                "title": sf.frontmatter.title,
                "publisher": sf.frontmatter.publisher,
                "summary": sf.frontmatter.summary,
                "key_quotes": sf.frontmatter.key_quotes or [],
                "body": sf.body,
                "slug": sf.slug,
                "url": sf.frontmatter.url,
            })

        result.urls_failed = [u for u in urls if u not in result.urls_ingested]

        if not result.sources:
            result.errors.append("All source URLs failed to ingest")
            return result

        # Step 3: Draft claim
        logger.info("Step 3/4: Drafting claim from %d sources...", len(result.sources))
        draft = await _draft_claim(entity_name, claim_text, result.sources, cfg)
        result.draft = draft

        if not draft:
            result.errors.append("Claim drafter failed to produce a draft")
            return result

        # Step 4: Consistency check
        logger.info("Step 4/4: Running consistency check...")
        consistency = await _consistency_check(
            entity_name, claim_text, draft, result.sources, cfg
        )
        result.consistency = consistency

    return result


async def _research(
    client: httpx.AsyncClient,
    entity_name: str,
    claim_text: str,
    cfg: VerifyConfig,
) -> list[str]:
    """Run the research agent to find relevant URLs."""
    deps = ResearchDeps(http_client=client)
    prompt = f"Entity: {entity_name}\nClaim to verify: {claim_text}"

    try:
        with research_agent.override(model=cfg.model):
            res = await asyncio.wait_for(
                research_agent.run(prompt, deps=deps), timeout=60
            )
        urls = res.output.urls[:cfg.max_sources]
        logger.info("Research found %d URLs: %s", len(urls), res.output.reasoning)
        return urls
    except Exception as exc:
        logger.error("Research agent failed: %s", exc)
        return []


async def _ingest_urls(
    client: httpx.AsyncClient,
    urls: list[str],
    cfg: VerifyConfig,
) -> list[tuple[str, SourceFile]]:
    """Run the ingestor agent on each URL. Returns (url, SourceFile) pairs."""
    results: list[tuple[str, SourceFile]] = []
    today = datetime.date.today()

    for url in urls:
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
            results.append((url, res.output))
            logger.info("Ingested: %s -> %s", url, res.output.frontmatter.title)
        except Exception as exc:
            logger.warning("Failed to ingest %s: %s", url, exc)

    return results


async def _draft_claim(
    entity_name: str,
    claim_text: str,
    sources: list[dict],
    cfg: VerifyConfig,
) -> ClaimDraft | None:
    """Run the drafter agent to produce a claim."""
    deps = DrafterDeps()
    prompt = build_drafter_prompt(entity_name, claim_text, sources)

    try:
        with drafter_agent.override(model=cfg.model):
            res = await asyncio.wait_for(
                drafter_agent.run(prompt, deps=deps), timeout=60
            )
        return res.output
    except Exception as exc:
        logger.error("Drafter failed: %s", exc)
        return None


async def _consistency_check(
    entity_name: str,
    claim_text: str,
    draft: ClaimDraft,
    sources: list[dict],
    cfg: VerifyConfig,
) -> ComparisonResult | None:
    """Run the consistency check against the draft claim."""
    entity = EntityContext(
        name=entity_name,
        type="company",
        description=f"Entity being evaluated: {entity_name}",
    )

    source_contexts = [
        SourceContext(
            id=src["slug"],
            title=src["title"],
            publisher=src["publisher"],
            summary=src["summary"],
            key_quotes=src.get("key_quotes", []),
            body=src.get("body", ""),
        )
        for src in sources
    ]

    bundle = ClaimBundle(
        claim_id=f"verify/{entity_name.lower().replace(' ', '-')}",
        entity=entity,
        category=draft.category,
        narrative=draft.narrative,
        sources=source_contexts,
    )

    prompt = build_user_prompt(bundle)
    deps = ConsistencyDeps(repo_root=cfg.repo_root)

    try:
        with consistency_agent.override(model=cfg.model):
            res = await asyncio.wait_for(
                consistency_agent.run(prompt, deps=deps), timeout=60
            )
        assessment = res.output

        return compare(
            draft.verdict,
            draft.confidence,
            assessment,
            bundle.claim_id,
            "(draft -- not yet saved)",
        )
    except Exception as exc:
        logger.error("Consistency check failed: %s", exc)
        return None
