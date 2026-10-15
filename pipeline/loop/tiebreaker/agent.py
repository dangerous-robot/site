"""Tie-breaker agent: grades the claim statement blind when the analyst and the Evaluator disagree.

It sees the bundle the Evaluator saw and nothing of either opinion; its own
instructions say it is the deciding grade. ``auditor.compare.settle_verdict``
turns its assessment into the pipeline verdict.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

from auditor.agent import build_auditor_prompt
from auditor.models import ClaimBundle, IndependentAssessment
from common.instructions import common, load_instructions

_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent, common("verdict-scale.md"))

tiebreaker_agent = Agent(
    "test",
    system_prompt=_INSTRUCTIONS,
    output_type=IndependentAssessment,
    retries=2,
)


def build_tiebreaker_prompt(bundle: ClaimBundle) -> str:
    """The Evaluator's prompt for ``bundle``: no verdict, no confidence, no reasoning from either side."""
    return build_auditor_prompt(bundle)

