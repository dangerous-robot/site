"""Auditor agent: independent adversarial assessment of claims."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

from common.instructions import load_instructions
from .models import ClaimBundle, IndependentAssessment


_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent)

auditor_agent = Agent(
    "test",
    system_prompt=_INSTRUCTIONS,
    output_type=IndependentAssessment,
    retries=2,
)


def build_auditor_prompt(bundle: ClaimBundle) -> str:
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

    topics_label = ", ".join(t.value for t in bundle.topics)
    parts.append(f"## Topics: {topics_label}")
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
                    parts.append(f'  - "{quote}"')
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
