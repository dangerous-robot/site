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
class SearchHints:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class ResolvedEntity:
    entity_ref: str
    entity_name: str
    entity_type: EntityType
    entity_description: str
    aliases: list[str] = field(default_factory=list)
    parent_company: str | None = None
    website: str | None = None
    search_hints: SearchHints | None = None


def build_entity_context(resolved_entity: ResolvedEntity | None, fallback_name: str = "") -> str:
    """Build a plain-text entity context block for researcher prompts."""
    if resolved_entity is None:
        return f"Entity: {fallback_name or '(unknown)'}\n"
    lines = [f"Entity: {resolved_entity.entity_name}"]
    if resolved_entity.entity_description:
        lines.append(f"Description: {resolved_entity.entity_description}")
    if resolved_entity.aliases:
        lines.append(f"Also known as: {', '.join(resolved_entity.aliases)}")
    if resolved_entity.search_hints:
        if resolved_entity.search_hints.include:
            lines.append(f"Prefer queries including: {', '.join(resolved_entity.search_hints.include)}")
        if resolved_entity.search_hints.exclude:
            lines.append(f"Avoid results about: {', '.join(resolved_entity.search_hints.exclude)}")
    return "\n".join(lines) + "\n"


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

    raw_hints = fm.get("search_hints")
    search_hints = SearchHints(
        include=raw_hints.get("include") or [],
        exclude=raw_hints.get("exclude") or [],
    ) if raw_hints else None

    return ResolvedEntity(
        entity_ref=entity_ref,
        entity_name=fm["name"],
        entity_type=entity_type,
        entity_description=fm.get("description", ""),
        aliases=fm.get("aliases") or [],
        parent_company=fm.get("parent_company") or None,
        website=fm.get("website") or None,
        search_hints=search_hints,
    )
