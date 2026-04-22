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

# Publisher substrings (lowercase) that identify primary sources.
# Matched against publisher.lower() — order doesn't matter here.
_PRIMARY_PUBLISHERS: frozenset[str] = frozenset(
    {
        "anthropic",
        "openai",
        "google",
        "microsoft",
        "meta",
        "ecosia",
        "greenpt",
        "chattree",
        "infomaniak",
        "tracklight",
        "transparently",
        "edgar",
    }
)

# Publisher substrings (lowercase) that strongly imply secondary sources.
_SECONDARY_PUBLISHERS: frozenset[str] = frozenset(
    {
        "arxiv",
        "ieee",
        "university",
        "journal",
        "b lab",
        "b corp",
        "ditchcarbon",
        "sacra",
        "crunchbase",
        "unesco",
        "ntia",
        "unfccc",
        "oecd",
    }
)

# Publisher substrings (lowercase) that imply tertiary sources.
_TERTIARY_PUBLISHERS: frozenset[str] = frozenset(
    {
        "future of life",
        "earth day",
        "center for ai safety",
        "nerdwallet",
        "zenbusiness",
        "substack",
    }
)

# SourceKind values that are intrinsically tertiary when publisher is unknown.
_TERTIARY_KINDS: frozenset[str] = frozenset({"blog"})


def _classify_source_type(publisher: str, kind: str) -> str:
    """Return 'primary', 'secondary', or 'tertiary' for a source.

    Rules (evaluated in order — first match wins):
    1. publisher matches a known AI-company or regulatory-filing term → primary
    2. kind is 'documentation' → primary (company docs are first-party)
    3. publisher matches a known secondary-source term → secondary
    4. publisher matches a known tertiary-source term → tertiary
    5. kind is 'blog' → tertiary
    6. everything else → secondary (safer default)
    """
    pub_lower = publisher.lower()
    kind_lower = kind.lower()

    # 1. Primary: known company / government-filing publisher
    # Use sec.gov substring to avoid matching "section", "secretary", etc.
    if "sec.gov" in pub_lower or any(term in pub_lower for term in _PRIMARY_PUBLISHERS):
        return "primary"

    # 2. Primary: company's own documentation (kind == "documentation")
    if kind_lower == "documentation":
        return "primary"

    # 3. Secondary: known research / journalism / certification publisher
    if any(term in pub_lower for term in _SECONDARY_PUBLISHERS):
        return "secondary"

    # 4. Tertiary: known advocacy / opinion publisher
    if any(term in pub_lower for term in _TERTIARY_PUBLISHERS):
        return "tertiary"

    # 5. Tertiary: blog kind (unless already caught as primary above)
    if kind_lower in _TERTIARY_KINDS:
        return "tertiary"

    # 6. Default
    return "secondary"


_ENTITY_TYPE_DIR = {
    EntityType.COMPANY: "companies",
    EntityType.PRODUCT: "products",
    EntityType.TOPIC: "topics",
}


def _entity_frontmatter(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    website: str | None = None,
    aliases: list[str] | None = None,
    status: str | None = None,
) -> dict:
    return {
        "name": entity_name,
        "type": entity_type,
        "website": website,
        "aliases": aliases or None,
        "description": entity_description,
        "status": status,
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
        fm_dict["source_type"] = _classify_source_type(
            sf.frontmatter.publisher, sf.frontmatter.kind.value
        )
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
    website: str | None = None,
    aliases: list[str] | None = None,
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

    fm = _entity_frontmatter(entity_name, entity_type, entity_description, website, aliases)
    entity_path.write_text(serialize_frontmatter(fm, ""), encoding="utf-8")
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


def _write_draft_entity_file(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    repo_root: Path,
    website: str | None = None,
    aliases: list[str] | None = None,
) -> str:
    """Write entity file to research/entities/drafts/{type-dir}/{slug}.md."""
    entity_slug = slugify(entity_name)
    type_dir = _ENTITY_TYPE_DIR.get(entity_type, f"{entity_type.value}s")

    draft_dir = repo_root / "research" / "entities" / "drafts" / type_dir
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"{entity_slug}.md"
    entity_ref = f"drafts/{type_dir}/{entity_slug}"

    fm = _entity_frontmatter(
        entity_name, entity_type, entity_description, website, aliases, status="draft"
    )
    draft_path.write_text(serialize_frontmatter(fm, ""), encoding="utf-8")
    logger.info("Wrote draft entity: %s", draft_path)
    return entity_ref
