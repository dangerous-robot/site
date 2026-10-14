"""Load and query criteria (claim templates) from research/templates.yaml.

A criterion is a sentence asked of many entities. Each has a stable slug
(the claim file stem) and a text with the entity type's placeholder
(``PRODUCT``, ``COMPANY`` or ``ENTITY``) that ``render_statement`` replaces
with the entity name. ``grading_rule`` is the per-criterion text both the
Analyst and the Evaluator get; ``notes`` is reader-facing and the pipeline
does not send it. A ``vocabulary`` map in the YAML is read by the site only
(home page bolding, the matrix check); the pipeline ignores it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from orchestrator.entity_resolution import ResolvedEntity

# The placeholder a criterion's text uses for each entity type.
ENTITY_TYPE_PLACEHOLDERS: dict[str, str] = {
    "company": "COMPANY",
    "product": "PRODUCT",
    "subject": "ENTITY",
}


_SUBJECT_REF_RE = re.compile(r"^subjects/[a-z0-9-]+$")


@dataclass(frozen=True)
class TemplateRecord:
    """A single claim template definition."""

    slug: str
    text: str  # e.g. "PRODUCT is hosted on renewable energy"
    entity_type: str  # "company", "product", or "subject"
    topics: list[str]  # 1-3 kebab-case topic slugs
    core: bool
    notes: str = ""
    grading_rule: str = ""
    # For entity_type == "subject", the list of subject refs (e.g. "subjects/ai-model-producers")
    # this template applies to. Required and non-empty for subject templates; forbidden for
    # company/product templates. Each entry must match ^subjects/[a-z0-9-]+$.
    subjects: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.entity_type == "subject":
            if not self.subjects:
                raise ValueError(
                    f"Template {self.slug!r}: subjects required and non-empty when entity_type == 'subject'"
                )
            for ref in self.subjects:
                if not _SUBJECT_REF_RE.match(ref):
                    raise ValueError(
                        f"Template {self.slug!r}: invalid subject ref {ref!r}; "
                        f"must match ^subjects/[a-z0-9-]+$"
                    )
        else:
            if self.subjects:
                raise ValueError(
                    f"Template {self.slug!r}: subjects forbidden when entity_type == {self.entity_type!r}"
                )


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
            grading_rule=entry.get("grading_rule") or "",
            subjects=list(entry.get("subjects") or []),
        )
        for entry in data["templates"]
    ]


def templates_for_entity_type(
    templates: list[TemplateRecord],
    entity_type: str,
    entity_slug: str | None = None,
) -> list[TemplateRecord]:
    """Filter templates by entity_type (core only).

    For ``company`` and ``product``, ``entity_slug`` is ignored and behavior matches
    the historical "all core templates of that type" rule.

    For ``subject``, the filter additionally requires that the template's
    ``subjects:`` list contain ``f"subjects/{entity_slug}"``. With
    ``entity_slug=None`` no fan-out is possible, so the function returns ``[]``;
    returning all subject templates would silently break the N:M pairing.
    """
    typed_core = [t for t in templates if t.entity_type == entity_type and t.core]
    if entity_type != "subject":
        return typed_core
    if entity_slug is None:
        return []
    target_ref = f"subjects/{entity_slug}"
    return [t for t in typed_core if target_ref in t.subjects]


def get_template(
    templates: list[TemplateRecord], slug: str
) -> TemplateRecord | None:
    """Look up a template by slug."""
    for t in templates:
        if t.slug == slug:
            return t
    return None


def render_statement(template: TemplateRecord, entity_name: str) -> str:
    """The criterion's sentence for one entity: its placeholder replaced, nothing else."""
    placeholder = ENTITY_TYPE_PLACEHOLDERS.get(template.entity_type)
    return template.text.replace(placeholder, entity_name) if placeholder else template.text


def criterion_entry_for(
    statement: str, entity: "ResolvedEntity", slug: str, topics: list[str]
) -> dict:
    """The ``research/templates.yaml`` entry that attaches a new criterion to a drafted claim.

    ``text`` is ``statement`` with its first mention of the entity (its name
    or an alias, longest first, any case, as a whole word) replaced by the
    entity type's placeholder; a statement that names neither is kept
    verbatim. A subject criterion names the one subject it was drafted for.
    """
    entity_type = entity.entity_type.value
    placeholder = ENTITY_TYPE_PLACEHOLDERS[entity_type]
    text = statement
    names = sorted({n for n in (entity.entity_name, *entity.aliases) if n}, key=len, reverse=True)
    for name in names:
        match = re.search(rf"(?<!\w){re.escape(name)}(?!\w)", statement, flags=re.IGNORECASE)
        if match:
            text = statement[:match.start()] + placeholder + statement[match.end():]
            break
    entry: dict = {"slug": slug, "text": text, "entity_type": entity_type}
    if entity_type == "subject":
        entry["subjects"] = [entity.entity_ref]
    entry["topics"] = list(topics)
    entry["core"] = False
    return entry


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip()).lower()
