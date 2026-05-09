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

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Prefix used when rendering vocabulary slots into claim text. The analyst is
# expected to replace this entire phrase with the specific option it supports.
# pipeline.py checks for this prefix to detect unresolved titles post-analysis.
VOCABULARY_HINT_PREFIX = "one of "


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
    vocabulary: dict[str, list[str]] = field(default_factory=dict)
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
            vocabulary=entry.get("vocabulary") or {},
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


def _substitute_entity(template: TemplateRecord, entity_name: str) -> str:
    text = template.text
    if template.entity_type == "product":
        return text.replace("PRODUCT", entity_name)
    if template.entity_type == "company":
        return text.replace("COMPANY", entity_name)
    if template.entity_type == "subject":
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


_WHITESPACE_RE = re.compile(r"\s+")

SEO_TITLE_FALLBACK_THRESHOLD = 60
_SEO_SAFE_SHORT_WORDS = frozenset({"a", "i", "ai", "us", "uk", "eu", "ok", "ny", "la", "dc", "tv"})


def _normalize_title(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip()).lower()


def _build_title_pattern(template: TemplateRecord, entity_name: str) -> "re.Pattern[str]":
    """Compile a regex matching any legal analyst title for this template.

    Each vocabulary placeholder becomes `(?:a |an )?(value1|value2|...)`; everything
    else is literal. Operates on the normalized (lowercased, whitespace-collapsed)
    text so the matcher tolerates casing and spacing variation only.
    """
    template_text = _normalize_title(_substitute_entity(template, entity_name))
    pattern_parts: list[str] = []
    cursor = 0
    placeholder_spans = sorted(
        (template_text.find(p.lower()), p.lower(), values)
        for p, values in template.vocabulary.items()
        if template_text.find(p.lower()) != -1
    )
    for start, placeholder, values in placeholder_spans:
        if start < cursor:
            continue
        pattern_parts.append(re.escape(template_text[cursor:start]))
        alternation = "|".join(re.escape(v.lower()) for v in values)
        pattern_parts.append(f"(?:a |an )?(?:{alternation})")
        cursor = start + len(placeholder)
    pattern_parts.append(re.escape(template_text[cursor:]))
    return re.compile("".join(pattern_parts))


def validate_analyst_title(
    template: TemplateRecord, entity_name: str, analyst_title: str
) -> tuple[bool, str | None]:
    """Returns (True, None) if `analyst_title` is reachable from the template by
    entity substitution + per-vocab-slot value choice + optional 'a'/'an' before
    each resolved value. Otherwise (False, reason). Case- and whitespace-insensitive.
    """
    actual = _normalize_title(analyst_title)
    template_text = _substitute_entity(template, entity_name)

    if not template.vocabulary:
        if actual == _normalize_title(template_text):
            return True, None
        return False, f"title diverges from template; expected {template_text!r}"

    if _build_title_pattern(template, entity_name).fullmatch(actual):
        return True, None
    return False, (
        f"title diverges from template; expected {template_text!r} "
        f"with vocabulary slots resolved to one allowed value (optional 'a'/'an')"
    )


def blocked_title_message(
    template: TemplateRecord,
    analyst_title: str,
    title_reason: str | None,
    blocked_reason_value: str,
) -> tuple[str, str]:
    """Returns (narrative_body, short_label) for the two title-validation
    failure modes. Used by both the onboard pipeline and the single-claim CLI
    refresh path so the operator-facing wording stays consistent.
    """
    if template.vocabulary and VOCABULARY_HINT_PREFIX in analyst_title:
        body = (
            f"This claim is blocked: `{blocked_reason_value}`. "
            f"The Analyst did not resolve the vocabulary placeholder in the title. "
            f"Re-run the pipeline with better sources, or resolve the vocabulary manually.\n"
        )
        return body, "unresolved vocabulary"
    body = (
        f"This claim is blocked: `{blocked_reason_value}`. "
        f"The Analyst rewrote the claim title outside the allowed transforms "
        f"(entity substitution, vocabulary resolution, optional article). "
        f"Analyst title: {analyst_title!r}. Reason: {title_reason}\n"
    )
    return body, "title rewritten"


def looks_seo_truncated(seo_title: str) -> bool:
    """Heuristic: last word is a 1-2 char fragment that isn't a common abbreviation.
    Catches LLM outputs that hit the max_length boundary mid-word.
    """
    stripped = seo_title.rstrip(" .,;:!?")
    if not stripped:
        return False
    last = stripped.rsplit(None, 1)[-1].rstrip("-")
    return len(last) <= 2 and last.lower() not in _SEO_SAFE_SHORT_WORDS
