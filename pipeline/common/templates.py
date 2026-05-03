"""Load and query claim templates from research/templates.yaml.

Templates define repeatable research questions that can be evaluated across
multiple entities. Each template has a stable slug used for claim filenames
and a text pattern with a placeholder (PRODUCT or COMPANY) that gets replaced
with the entity name to produce a concrete claim statement.

A template may also carry a `vocabulary` mapping that defines controlled-value
slots (e.g. STRUCTURE, JURISDICTION). At render time each slot is replaced
with a "one of (...)" hint so the researcher/analyst picks a value from the
approved set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Prefix used when rendering vocabulary slots into claim text. The analyst is
# expected to replace this entire phrase with the specific option it supports.
# pipeline.py checks for this prefix to detect unresolved titles post-analysis.
VOCABULARY_HINT_PREFIX = "one of "


@dataclass(frozen=True)
class TemplateRecord:
    """A single claim template definition."""

    slug: str
    text: str  # e.g. "PRODUCT is hosted on renewable energy"
    entity_type: str  # "company" or "product"
    topics: list[str]  # 1-3 kebab-case topic slugs
    core: bool
    notes: str = ""
    vocabulary: dict[str, list[str]] = field(default_factory=dict)


def load_templates(repo_root: Path) -> list[TemplateRecord]:
    """Load all templates from research/templates.yaml."""
    path = repo_root / "research" / "templates.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [
        TemplateRecord(
            slug=entry["slug"],
            text=entry["text"],
            entity_type=entry["entity_type"],
            topics=list(entry["topics"]),
            core=entry["core"],
            notes=entry.get("notes") or "",
            vocabulary=entry.get("vocabulary") or {},
        )
        for entry in data["templates"]
    ]


def templates_for_entity_type(
    templates: list[TemplateRecord], entity_type: str
) -> list[TemplateRecord]:
    """Filter to templates matching entity_type, core only."""
    return [
        t for t in templates if t.entity_type == entity_type and t.core
    ]


def get_template(
    templates: list[TemplateRecord], slug: str
) -> TemplateRecord | None:
    """Look up a template by slug."""
    for t in templates:
        if t.slug == slug:
            return t
    return None


def _substitute_entity(template: TemplateRecord, entity_name: str) -> str:
    text = template.text
    if template.entity_type == "product":
        return text.replace("PRODUCT", entity_name)
    if template.entity_type == "company":
        return text.replace("COMPANY", entity_name)
    if template.entity_type == "sector":
        return text.replace("ENTITY", entity_name)
    return text


def render_claim_text(template: TemplateRecord, entity_name: str) -> str:
    """Replace PRODUCT/COMPANY placeholder with entity_name and expand any
    controlled-vocabulary slots to a "one of (...)" hint."""
    text = _substitute_entity(template, entity_name)
    for placeholder, values in template.vocabulary.items():
        hint = f"{VOCABULARY_HINT_PREFIX}({', '.join(values)})"
        text = text.replace(placeholder, hint)
    return text


def render_blocked_title(template: TemplateRecord, entity_name: str) -> str:
    """Render with entity name substituted but vocabulary slots left unexpanded.

    Used for blocked claim titles where the analyst never resolved the
    vocabulary. Produces e.g. "Microsoft has STRUCTURE corporate structure"
    instead of "Microsoft has one of (publicly-traded, ...) corporate structure".
    """
    return _substitute_entity(template, entity_name)
