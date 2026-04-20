"""File I/O for persisting research artifacts to disk."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from ingestor.models import SourceFile

logger = logging.getLogger(__name__)


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
    entity_name: str,
    entity_type: str,
    entity_description: str,
    repo_root: Path,
) -> str:
    """Write entity file if it doesn't exist. Returns entity path like 'companies/slug'."""
    from analyst.agent import slugify
    from common.frontmatter import serialize_frontmatter

    entity_slug = slugify(entity_name)
    entity_type_norm = entity_type.rstrip("s")  # normalize "companies" -> "company"
    type_plural = {"company": "companies", "product": "products", "topic": "topics"}
    type_dir = type_plural.get(entity_type_norm, f"{entity_type_norm}s")

    entity_dir = repo_root / "research" / "entities" / type_dir
    entity_dir.mkdir(parents=True, exist_ok=True)
    entity_path = entity_dir / f"{entity_slug}.md"
    entity_ref = f"{type_dir}/{entity_slug}"

    if entity_path.exists():
        logger.info("Entity already exists: %s", entity_path)
        return entity_ref

    fm = {
        "name": entity_name,
        "type": entity_type_norm,
        "description": entity_description,
    }
    body = f"{entity_description}\n"
    entity_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")
    logger.info("Wrote entity: %s", entity_path)
    return entity_ref


def _write_claim_file(
    title: str,
    entity_name: str,
    entity_ref: str,
    category,
    verdict,
    confidence: str,
    narrative: str,
    claim_slug: str,
    source_ids: list[str],
    repo_root: Path,
) -> Path:
    """Write the claim file to disk. Returns the file path."""
    from analyst.agent import slugify
    from common.frontmatter import serialize_frontmatter

    entity_slug = slugify(entity_name)
    claim_slug_clean = slugify(claim_slug)

    claim_dir = repo_root / "research" / "claims" / entity_slug
    claim_dir.mkdir(parents=True, exist_ok=True)
    claim_path = claim_dir / f"{claim_slug_clean}.md"

    fm = {
        "title": title,
        "entity": entity_ref,
        "category": category.value if hasattr(category, "value") else category,
        "verdict": verdict.value if hasattr(verdict, "value") else verdict,
        "confidence": confidence.value if hasattr(confidence, "value") else confidence,
        "as_of": datetime.date.today(),
        "sources": source_ids,
    }
    claim_path.write_text(
        serialize_frontmatter(fm, narrative.rstrip() + "\n"),
        encoding="utf-8",
    )
    logger.info("Wrote claim: %s", claim_path)
    return claim_path
