"""PydanticAI agent for independent claim assessment."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from common.models import DEFAULT_MODEL
from .models import ClaimBundle, IndependentAssessment

SYSTEM_PROMPT = """\
You are an independent fact-check reviewer for a research site that evaluates
claims about AI companies and products. You will be given:

1. A claim narrative (the text of the claim as written)
2. Source materials that the claim cites
3. Basic information about the entity the claim is about

Your job is to determine what verdict and confidence level the evidence supports.
You must form your own independent judgment.

VERDICT SCALE (ordered from positive to negative):
- true: The claim is well-supported by the cited evidence
- mostly-true: Largely supported but has minor qualifications
- mixed: Evidence partially supports and partially contradicts
- mostly-false: Largely unsupported by the cited evidence
- false: The cited evidence contradicts the claim
- unverified: Insufficient evidence to render a verdict

CONFIDENCE SCALE:
- high: Multiple independent sources strongly support the verdict; evidence is direct
- medium: Evidence supports the verdict but has limitations (single source,
  self-reported data, indirect evidence)
- low: Evidence is thin, contradictory, or primarily anecdotal

RULES:
- Base your verdict ONLY on the narrative text and the provided source materials.
- Do not rely on your own knowledge about the entities or topics.
- If the narrative makes claims that the sources do not support, that should
  lower your verdict and/or confidence.
- If the narrative is cautious but sources strongly support the conclusion,
  your verdict may be stronger than the narrative implies.
- Pay attention to whether the narrative accurately represents what the sources say.
- Note any evidence gaps -- things the narrative claims that no source backs up.
- Be genuinely critical. Do not default to agreement. Disagreement is valuable.\
"""


@dataclass
class ConsistencyDeps:
    """Dependencies injected into the agent at runtime."""

    repo_root: str


consistency_agent = Agent(
    "test",
    system_prompt=SYSTEM_PROMPT,
    output_type=IndependentAssessment,
    deps_type=ConsistencyDeps,
    retries=2,
)


def build_user_prompt(bundle: ClaimBundle) -> str:
    """Build the user prompt from a ClaimBundle.

    Deliberately excludes verdict, confidence, and title to preserve
    information asymmetry.
    """
    parts: list[str] = []

    parts.append("## Entity")
    parts.append(f"Name: {bundle.entity.name}")
    parts.append(f"Type: {bundle.entity.type}")
    parts.append(f"Description: {bundle.entity.description}")
    parts.append("")

    parts.append(f"## Category: {bundle.category.value}")
    parts.append("")

    parts.append("## Claim Narrative")
    parts.append(bundle.narrative.strip())
    parts.append("")

    if bundle.sources:
        parts.append("## Source Materials")
        for i, src in enumerate(bundle.sources, 1):
            parts.append(f"### Source {i}: {src.title}")
            parts.append(f"Publisher: {src.publisher}")
            parts.append(f"Summary: {src.summary}")
            if src.key_quotes:
                parts.append("Key quotes:")
                for quote in src.key_quotes:
                    parts.append(f"  - \"{quote}\"")
            if src.body.strip():
                parts.append(f"Full text:\n{src.body.strip()}")
            parts.append("")
    else:
        parts.append("## Source Materials")
        parts.append("No sources provided.")
        parts.append("")

    parts.append(
        "Based on the narrative and sources above, provide your independent "
        "assessment of what verdict and confidence level the evidence supports."
    )

    return "\n".join(parts)
