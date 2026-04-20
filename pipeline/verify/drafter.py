"""Claim drafter agent: synthesizes sources into a structured claim."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from common.models import Category, Confidence, Verdict


class ClaimDraft(BaseModel):
    """A draft claim produced by the drafter agent."""

    title: str = Field(description="Concise claim title (e.g. 'Ecosia runs AI chat on non-renewable infrastructure')")
    category: Category
    verdict: Verdict
    confidence: Confidence
    narrative: str = Field(description="2-5 sentence assessment. Cite sources by title. Factual, not evaluative.")
    entity_name: str = Field(description="Primary entity name (e.g. 'Apple', 'OpenAI')")
    entity_type: str = Field(description="One of: company, product, topic")
    entity_description: str = Field(description="One-sentence description of the entity")
    claim_slug: str = Field(description="Kebab-case filename slug for the claim (e.g. 'neural-link-support')")


SYSTEM_PROMPT = """\
You are a claim drafter for dangerousrobot.org, a research site that evaluates
claims about AI companies and products with structured, citable evidence.

Given a claim to evaluate and source materials, your job is to:

1. Identify the primary entity the claim is about
2. Assess whether the evidence supports, refutes, or is mixed on the claim
3. Choose the appropriate verdict and confidence level
4. Write a factual narrative citing the sources

ENTITY IDENTIFICATION:
- entity_name: The primary company, product, or topic (e.g. "Apple", "ChatGPT")
- entity_type: One of "company", "product", or "topic"
- entity_description: One sentence describing the entity
- If the claim mentions a product, the entity is usually the product.
  If it mentions a company without a specific product, the entity is the company.
  If it is about a general topic (e.g. "AI regulation"), the entity is a topic.

CLAIM SLUG:
- Generate a short kebab-case slug for the claim filename
- Derived from the core assertion, not the entity (e.g. "neural-link-support",
  "renewable-energy-hosting", "training-data-consent")

VERDICT SCALE:
- true: Well-supported by the cited evidence
- mostly-true: Largely supported but has minor qualifications
- mixed: Evidence partially supports and partially contradicts
- mostly-false: Largely unsupported by the cited evidence
- false: The cited evidence contradicts the claim
- unverified: Insufficient evidence to render a verdict

CONFIDENCE SCALE:
- high: Multiple independent sources with direct evidence
- medium: Evidence exists but has limitations (single source, self-reported, indirect)
- low: Thin, contradictory, or primarily anecdotal evidence

CATEGORIES:
- ai-safety, environmental-impact, product-comparison, consumer-guide,
  ai-literacy, data-privacy, industry-analysis, regulation-policy

RULES:
- Base your verdict ONLY on the provided source materials
- The narrative should be factual and balanced, not advocacy
- Cite sources by title when making specific claims in the narrative
- If the sources don't address the claim, use verdict "unverified"
- Do not inflate confidence -- "medium" is the right default for most claims
  with limited sourcing\
"""


@dataclass
class DrafterDeps:
    pass


drafter_agent = Agent(
    "test",
    output_type=ClaimDraft,
    deps_type=DrafterDeps,
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)


def build_drafter_prompt(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
) -> str:
    """Build the user prompt for the drafter agent."""
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
