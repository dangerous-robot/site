"""File I/O for persisting research artifacts to disk."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from common.frontmatter import serialize_frontmatter
from common.models import Category, Confidence, EntityType, Verdict
from common.utils import slugify
from ingestor.models import SourceFile

logger = logging.getLogger(__name__)

_ENTITY_TYPE_DIR = {
    EntityType.COMPANY: "companies",
    EntityType.PRODUCT: "products",
    EntityType.TOPIC: "topics",
}


def _write_source_files(
    source_files: list[tuple[str, SourceFile]],
    repo_root: Path,
) -> list[str]:
    """Write ingested source files to disk. Returns list of source IDs."""
    source_ids: list[str] = []

    for _url, sf in source_files:
        target_dir = repo_root / "research" / "sources" / str(sf.year)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{sf.slug}.md"

        fm_dict = sf.frontmatter.model_dump(mode="python")
        markdown = serialize_frontmatter(fm_dict, sf.body.rstrip() + "\n")

        try:
            with target_path.open("x", encoding="utf-8") as f:
                f.write(markdown)
            logger.info("Wrote source: %s", target_path)
        except FileExistsError:
            logger.info("Source already exists, skipping: %s", target_path)

        source_ids.append(f"{sf.year}/{sf.slug}")

    return source_ids


def _write_entity_file(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    repo_root: Path,
) -> str:
    """Write entity file if it doesn't exist. Returns entity path like 'companies/slug'."""
    entity_slug = slugify(entity_name)
    type_dir = _ENTITY_TYPE_DIR.get(entity_type, f"{entity_type.value}s")

    entity_dir = repo_root / "research" / "entities" / type_dir
    entity_dir.mkdir(parents=True, exist_ok=True)
    entity_path = entity_dir / f"{entity_slug}.md"
    entity_ref = f"{type_dir}/{entity_slug}"

    if entity_path.exists():
        logger.info("Entity already exists: %s", entity_path)
        return entity_ref

    fm = {
        "name": entity_name,
        "type": entity_type,
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
    category: Category,
    verdict: Verdict,
    confidence: Confidence,
    narrative: str,
    claim_slug: str,
    source_ids: list[str],
    repo_root: Path,
) -> Path:
    """Write the claim file to disk. Returns the file path."""
    entity_slug = slugify(entity_name)
    claim_slug_clean = slugify(claim_slug)

    claim_dir = repo_root / "research" / "claims" / entity_slug
    claim_dir.mkdir(parents=True, exist_ok=True)
    claim_path = claim_dir / f"{claim_slug_clean}.md"

    fm = {
        "title": title,
        "entity": entity_ref,
        "category": category,
        "verdict": verdict,
        "confidence": confidence,
        "as_of": datetime.date.today(),
        "sources": source_ids,
    }
    claim_path.write_text(
        serialize_frontmatter(fm, narrative.rstrip() + "\n"),
        encoding="utf-8",
    )
    logger.info("Wrote claim: %s", claim_path)
    return claim_path
