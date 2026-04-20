"""Analyst agent: assesses evidence and renders verdicts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from common.instructions import load_instructions
from common.models import Category, Confidence, Verdict


class EntityResolution(BaseModel):
    """Entity identified from the claim context."""

    entity_name: str = Field(description="Primary entity name (e.g. 'Apple', 'OpenAI')")
    entity_type: str = Field(description="One of: company, product, topic")
    entity_description: str = Field(description="One-sentence description of the entity")


class VerdictAssessment(BaseModel):
    """Verdict and narrative produced from source analysis."""

    title: str = Field(description="Concise claim title (e.g. 'Ecosia runs AI chat on non-renewable infrastructure')")
    verdict: Verdict
    confidence: Confidence
    narrative: str = Field(description="2-5 sentence assessment. Cite sources by title. Factual, not evaluative.")
    category: Category


class AnalystOutput(BaseModel):
    """Full output of the analyst agent."""

    entity: EntityResolution
    verdict: VerdictAssessment


@dataclass
class AnalystDeps:
    pass


_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent)

analyst_agent = Agent(
    "test",
    output_type=AnalystOutput,
    deps_type=AnalystDeps,
    system_prompt=_INSTRUCTIONS,
    retries=2,
)


def slugify(text: str) -> str:
    """Convert text to a kebab-case slug (deterministic, no LLM)."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")


def build_analyst_prompt(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
) -> str:
    """Build the user prompt for the analyst agent."""
    parts: list[str] = []

    if entity_name:
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
