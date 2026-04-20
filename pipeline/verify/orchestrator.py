"""Orchestrator: chains research -> ingest -> draft -> consistency check."""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

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


# --- File writing for research_claim ---


def _slugify(text: str) -> str:
    """Convert text to a kebab-case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")


def _write_source_files(
    source_files: list[tuple[str, SourceFile]],
    repo_root: Path,
) -> list[str]:
    """Write ingested source files to disk. Returns list of source IDs."""
    from common.frontmatter import serialize_frontmatter

    source_ids: list[str] = []

    for _url, sf in source_files:
        target_dir = repo_root / "research" / "sources" / str(sf.year)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{sf.slug}.md"

        fm_dict = sf.frontmatter.model_dump(mode="python")
        markdown = serialize_frontmatter(fm_dict, sf.body.rstrip() + "\n")

        if target_path.exists():
            logger.info("Source already exists, skipping: %s", target_path)
        else:
            target_path.write_text(markdown, encoding="utf-8")
            logger.info("Wrote source: %s", target_path)

        source_ids.append(f"{sf.year}/{sf.slug}")

    return source_ids


def _write_entity_file(
    draft: "ClaimDraft",
    repo_root: Path,
) -> str:
    """Write entity file if it doesn't exist. Returns entity path like 'companies/slug'."""
    from common.frontmatter import serialize_frontmatter

    entity_slug = _slugify(draft.entity_name)
    entity_type = draft.entity_type.rstrip("s")  # normalize "companies" -> "company"
    type_plural = {"company": "companies", "product": "products", "topic": "topics"}
    type_dir = type_plural.get(entity_type, f"{entity_type}s")

    entity_dir = repo_root / "research" / "entities" / type_dir
    entity_dir.mkdir(parents=True, exist_ok=True)
    entity_path = entity_dir / f"{entity_slug}.md"
    entity_ref = f"{type_dir}/{entity_slug}"

    if entity_path.exists():
        logger.info("Entity already exists: %s", entity_path)
        return entity_ref

    fm = {
        "name": draft.entity_name,
        "type": entity_type,
        "description": draft.entity_description,
    }
    body = f"{draft.entity_description}\n"
    entity_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")
    logger.info("Wrote entity: %s", entity_path)
    return entity_ref


def _write_claim_file(
    draft: "ClaimDraft",
    entity_ref: str,
    source_ids: list[str],
    repo_root: Path,
) -> Path:
    """Write the claim file to disk. Returns the file path."""
    from common.frontmatter import serialize_frontmatter

    entity_slug = _slugify(draft.entity_name)
    claim_slug = _slugify(draft.claim_slug)

    claim_dir = repo_root / "research" / "claims" / entity_slug
    claim_dir.mkdir(parents=True, exist_ok=True)
    claim_path = claim_dir / f"{claim_slug}.md"

    fm = {
        "title": draft.title,
        "entity": entity_ref,
        "category": draft.category.value,
        "verdict": draft.verdict.value,
        "confidence": draft.confidence.value,
        "as_of": datetime.date.today(),
        "sources": source_ids,
    }
    claim_path.write_text(
        serialize_frontmatter(fm, draft.narrative.rstrip() + "\n"),
        encoding="utf-8",
    )
    logger.info("Wrote claim: %s", claim_path)
    return claim_path


async def research_claim(
    claim_text: str,
    config: VerifyConfig | None = None,
) -> VerificationResult:
    """Research a claim, persist sources/entity/claim to disk, and run consistency check.

    Unlike verify_claim, this function:
    - Does not require an entity name (the drafter identifies it)
    - Writes source files to research/sources/
    - Creates entity file in research/entities/ if needed
    - Writes the claim file to research/claims/
    """
    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        from common.content_loader import resolve_repo_root
        cfg.repo_root = str(resolve_repo_root())

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
        urls = await _research(client, "", claim_text, cfg)
        result.urls_found = urls

        if not urls:
            result.errors.append("Research agent found no relevant URLs")
            return result

        # Step 2: Ingest
        logger.info("Step 2/5: Ingesting %d sources...", len(urls))
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

        # Step 3: Write sources to disk
        logger.info("Step 3/5: Writing %d source files...", len(source_files))
        source_ids = _write_source_files(source_files, repo_root)

        # Step 4: Draft claim (drafter identifies entity)
        logger.info("Step 4/5: Drafting claim...")
        draft = await _draft_claim(None, claim_text, result.sources, cfg)
        result.draft = draft

        if not draft:
            result.errors.append("Claim drafter failed to produce a draft")
            return result

        result.entity = draft.entity_name

        # Write entity and claim to disk
        entity_ref = _write_entity_file(draft, repo_root)
        claim_path = _write_claim_file(draft, entity_ref, source_ids, repo_root)

        # Step 5: Consistency check
        logger.info("Step 5/5: Running consistency check...")
        consistency = await _consistency_check(
            draft.entity_name, claim_text, draft, result.sources, cfg
        )
        result.consistency = consistency

    return result
