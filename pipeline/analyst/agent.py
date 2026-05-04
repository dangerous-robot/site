"""Analyst agent: assesses evidence and renders verdicts."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from common.instructions import common, load_instructions
from common.models import Category, Confidence, EntityType, Verdict
from common.utils import slugify

if TYPE_CHECKING:
    from orchestrator.entity_resolution import ResolvedEntity


class EntityResolution(BaseModel):
    """Entity identified from the claim context."""

    entity_name: str = Field(description="Primary entity name (e.g. 'Apple', 'OpenAI')")
    entity_type: EntityType = Field(description="One of: company, product, topic")
    entity_description: str = Field(description="One-sentence description of the entity")
    aliases: list[str] = Field(
        default_factory=list,
        description="Common alternate names, abbreviations, or product lines (e.g. ['Claude'] for Anthropic). Omit if none apply.",
    )


class VerdictAssessment(BaseModel):
    """Verdict and narrative produced from source analysis."""

    title: str = Field(description="Concise claim title (e.g. 'Ecosia runs AI chat on non-renewable infrastructure')")
    verdict: Verdict
    confidence: Confidence
    narrative: str = Field(description="2-5 sentence assessment. Cite sources by title. Factual, not evaluative.")
    topics: list[Category] = Field(
        min_length=1,
        max_length=3,
        description="One to three topic slugs that classify the claim. Mirror the source criterion's topics by default.",
    )
    seo_title: str | None = Field(
        default=None,
        description=(
            "Short page title for search results (max 42 chars). Only provide when "
            "`title` exceeds ~60 characters and a shorter version conveys the same "
            "finding. Omit if the full title already fits or if shortening would "
            "lose the core finding."
        ),
        max_length=42,
    )
    takeaway: str | None = Field(
        default=None,
        description=(
            "One sentence a reader would want to repeat (max 200 chars). Only "
            "include when the finding is striking, counterintuitive, or unusually "
            "significant — e.g., an industry-wide failure or direct contradiction "
            "of public claims. Do not paraphrase the title. Default: omit."
        ),
        max_length=200,
    )


class AnalystOutput(BaseModel):
    """Full output of the analyst agent."""

    entity: EntityResolution
    verdict: VerdictAssessment


_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent, common("verdict-scale.md"))

analyst_agent = Agent(
    "test",
    output_type=AnalystOutput,
    system_prompt=_INSTRUCTIONS,
    retries=2,
)

verdict_only_agent = Agent(
    "test",
    output_type=VerdictAssessment,
    system_prompt=_INSTRUCTIONS,
    retries=2,
)


def build_analyst_prompt(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
    resolved_entity: "ResolvedEntity | None" = None,
) -> str:
    """Build the user prompt for the analyst agent."""
    parts: list[str] = []

    if resolved_entity is not None:
        aliases_str = ", ".join(resolved_entity.aliases) if resolved_entity.aliases else "none"
        parent_str = resolved_entity.parent_company or "none"
        parts.append("## Entity (pre-resolved — do not infer)")
        parts.append("")
        parts.append(f"Name: {resolved_entity.entity_name}")
        parts.append(f"Type: {resolved_entity.entity_type.value}")
        parts.append(f"Description: {resolved_entity.entity_description}")
        parts.append(f"Aliases: {aliases_str}")
        parts.append(f"Parent company: {parent_str}")
        parts.append("")
        parts.append("The entity above is authoritative. Produce only a VerdictAssessment.")
    elif entity_name:
        parts.append(f"## Entity: {entity_name}")

    parts.append("")
    parts.append(f"## Claim to evaluate: {claim_text}")
    parts.append("")

    if sources:
        parts.append("## Source materials")
        for i, src in enumerate(sources, 1):
            parts.append(f"### Source {i}: {src['title']}")
            parts.append(f"Publisher: {src['publisher']}")
            parts.append(f"Summary: {src['summary']}")
            if src.get("key_quotes"):
                parts.append("Key quotes:")
                for q in src["key_quotes"]:
                    parts.append(f'  - "{q}"')
            if src.get("body"):
                parts.append(f"Full text:\n{src['body'].strip()}")
            parts.append("")
    else:
        parts.append("## Source materials")
        parts.append("No sources were found.")
        parts.append("")

    parts.append(
        "Based on the sources above, draft a structured claim assessment."
    )

    return "\n".join(parts)
