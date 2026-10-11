"""Auditor agent: independent adversarial assessment of claims."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

from common.instructions import common, load_instructions
from .models import ClaimBundle, IndependentAssessment


_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent, common("verdict-scale.md"))

auditor_agent = Agent(
    "test",
    system_prompt=_INSTRUCTIONS,
    output_type=IndependentAssessment,
    retries=2,
)


def build_auditor_prompt(bundle: ClaimBundle) -> str:
    """Build the user prompt from a ClaimBundle.

    Leaves out the analyst's verdict and confidence so the Evaluator forms
    its own. The claim statement comes before the narrative and is what the
    Evaluator grades.
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

    parts.append("## Claim")
    parts.append(bundle.claim_text.strip())
    parts.append("")

    parts.append("## Analyst narrative (context; not the thing you grade)")
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
        "Judge the claim above against the source materials and give your "
        "independent verdict and confidence on that claim."
    )

    return "\n".join(parts)
