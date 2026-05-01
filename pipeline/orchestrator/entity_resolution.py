"""Entity pre-resolution for the verification pipeline.

Parses a short 'type_dir/slug' reference into a ResolvedEntity by reading
the entity file from disk before any LLM runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from common.content_loader import load_entity
from common.models import EntityType

_DIR_ENTITY_TYPE: dict[str, EntityType] = {
    "companies": EntityType.COMPANY,
    "products": EntityType.PRODUCT,
    "topics": EntityType.TOPIC,
    "sectors": EntityType.SECTOR,
}


@dataclass
class ResolvedEntity:
    entity_ref: str
    entity_name: str
    entity_type: EntityType
    entity_description: str
    aliases: list[str] = field(default_factory=list)
    parent_company: str | None = None
    website: str | None = None


def parse_entity_ref(entity_ref: str, repo_root: Path) -> ResolvedEntity:
    """Parse 'products/chatgpt' into a ResolvedEntity. Raises ValueError on error."""
    if "/" not in entity_ref:
        raise ValueError(
            f"Invalid entity ref '{entity_ref}': expected '{{type_dir}}/{{slug}}'"
        )

    type_dir, _ = entity_ref.split("/", 1)

    if type_dir not in _DIR_ENTITY_TYPE:
        known = ", ".join(sorted(_DIR_ENTITY_TYPE))
        raise ValueError(
            f"Unknown entity type dir '{type_dir}': must be one of {known}"
        )

    entity_type = _DIR_ENTITY_TYPE[type_dir]

    try:
        fm, _ = load_entity(entity_ref, repo_root)
    except FileNotFoundError:
        raise ValueError(
            f"Entity file not found: {repo_root / 'research' / 'entities' / entity_ref}.md"
        ) from None
    except Exception as exc:
        raise ValueError(f"Failed to parse entity frontmatter for '{entity_ref}': {exc}") from exc

    if "name" not in fm:
        raise ValueError(
            f"Entity file research/entities/{entity_ref}.md missing required field 'name'"
        )

    return ResolvedEntity(
        entity_ref=entity_ref,
        entity_name=fm["name"],
        entity_type=entity_type,
        entity_description=fm.get("description", ""),
        aliases=fm.get("aliases") or [],
        parent_company=fm.get("parent_company") or None,
        website=fm.get("website") or None,
    )
