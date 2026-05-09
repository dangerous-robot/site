"""Entity enricher: tightens description and drafts a history body (tool-free, Haiku).

Mirrors the planner / scorer convention: inline system prompt, typed
Pydantic output, ``retries=2``. Consumes a ``LightResearchBundle``
assembled by the orchestrator's light-research pass and emits an
``EnrichmentDraft`` that the operator reviews before the writer commits
the fields to the entity file.

This module subsumes the standalone ``_tighten_entity_description`` agent
in ``orchestrator/pipeline.py``. The ``description`` field on the draft
replaces what that helper produced.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from common.models import EntityType

if TYPE_CHECKING:
    from orchestrator.pipeline import LightResearchBundle


class EnrichmentDraft(BaseModel):
    """Operator-reviewed draft of enrichable entity fields.

    ``founded`` is left ``None`` for subjects (no calendar founding date)
    and may also be ``None`` for companies / products when the bundle
    carries no reliable signal. The schema itself does not branch on
    entity type — the prompt's per-type section is what differs.
    """

    founded: int | None = Field(
        default=None,
        description=(
            "Year the entity was founded (companies / products). Leave "
            "null when no reliable signal is available, or when the "
            "entity is a subject."
        ),
    )
    description: str = Field(
        description=(
            "One-sentence description of the organization or subject. "
            "Subsumes the standalone description-tightening agent."
        ),
    )
    history_markdown: str = Field(
        description=(
            "Two to four paragraphs of narrative history, in Markdown. "
            "No headings — the renderer wraps the body under a 'History' "
            "subsection. Plain prose, no marketing language."
        ),
    )


_ENRICHER_SCAFFOLD = """\
You enrich an entity record with a tightened one-sentence description and a 2–4 paragraph history body.

Inputs (provided in the user prompt):
- Entity name and type (company / product / subject).
- A raw webpage summary the orchestrator collected during light research.
- The entity's website (when known) and probe-suggested name-collision exclusions.

Output rules (apply to every entity type):
- ``description``: one sentence. Subject is the entity itself, not the webpage. Do not start with "Landing page", "Homepage", "Website". Preserve concrete facts from the inputs; do not invent. If the inputs do not actually describe the entity, return the empty string.
- ``history_markdown``: 2–4 paragraphs of plain Markdown prose. No headings, no bullet lists, no marketing language ("revolutionary", "cutting-edge", etc.). When the inputs are thin, write a shorter, factual paragraph rather than padding.
- Tone: direct, factual, content-first. The reader is a researcher, not a marketer.
- Never fabricate names, dates, or events that are not supported by the inputs.
"""


_PER_TYPE_SECTIONS: dict[EntityType, str] = {
    EntityType.COMPANY: """\
Per-type guidance (company):
- Solicit ``founded`` (year only, e.g. 2021). If the inputs don't give a year, leave it null rather than guessing.
- ``description`` covers what the company does and its primary focus area.
- ``history_markdown`` covers founding context, notable products or pivots, leadership transitions, and major funding or acquisitions when supported by the inputs.
- Do NOT populate a legal name; that's an operator-set field on a separate path.
""",
    EntityType.PRODUCT: """\
Per-type guidance (product):
- Solicit ``founded`` as the year the product first launched (year only). Leave null if the inputs don't pin it down.
- ``description`` covers what the product does and who makes it.
- ``history_markdown`` covers launch context, version milestones, and platform shifts when supported by the inputs.
""",
    EntityType.SUBJECT: """\
Per-type guidance (subject):
- Subjects are concepts or categories (e.g. "generative AI", "AI model producers"). They do not have a founded year — leave ``founded`` null.
- ``description`` is an encyclopedic one-sentence definition of the term.
- ``history_markdown`` traces the concept's origin, key inflection points, and current usage when the inputs support it.
""",
}


entity_enricher_agent = Agent(
    "test",
    output_type=EnrichmentDraft,
    system_prompt=_ENRICHER_SCAFFOLD,
    retries=2,
)


def build_entity_enricher_prompt(bundle: "LightResearchBundle") -> str:
    """Assemble the per-call user prompt from a light-research bundle."""
    section = _PER_TYPE_SECTIONS.get(bundle.entity_type, "")
    raw_summary = (bundle.raw_description or "").strip() or "(no webpage summary collected)"
    lines = [
        f"Entity name: {bundle.entity_name}",
        f"Entity type: {bundle.entity_type.value}",
    ]
    if bundle.entity_website:
        lines.append(f"Website: {bundle.entity_website}")
    if bundle.probe_excludes:
        lines.append(
            f"Avoid confusion with: {', '.join(bundle.probe_excludes)}"
        )
    lines.append("")
    lines.append("Webpage summary:")
    lines.append(raw_summary)
    lines.append("")
    lines.append(section.rstrip())
    return "\n".join(lines)
