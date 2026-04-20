"""Load and query claim templates from research/templates.yaml.

Templates define repeatable research questions that can be evaluated across
multiple entities. Each template has a stable slug used for claim filenames
and a text pattern with a placeholder (PRODUCT or COMPANY) that gets replaced
with the entity name to produce a concrete claim statement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TemplateRecord:
    """A single claim template definition."""

    slug: str
    text: str  # e.g. "PRODUCT is hosted on renewable energy"
    entity_type: str  # "company" or "product"
    category: str  # kebab-case category slug
    core: bool
    notes: str


def load_templates(repo_root: Path) -> list[TemplateRecord]:
    """Load all templates from research/templates.yaml."""
    path = repo_root / "research" / "templates.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [TemplateRecord(**entry) for entry in data["templates"]]


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


def render_claim_text(template: TemplateRecord, entity_name: str) -> str:
    """Replace PRODUCT/COMPANY placeholder with entity_name."""
    text = template.text
    if template.entity_type == "product":
        text = text.replace("PRODUCT", entity_name)
    elif template.entity_type == "company":
        text = text.replace("COMPANY", entity_name)
    return text
