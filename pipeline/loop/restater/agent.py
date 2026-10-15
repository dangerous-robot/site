"""Restater agent: ranked restatements of a claim whose sources do not settle it.

It sees the claim, the pipeline verdict, the analyst's narrative as context,
the Evaluator's evidence gaps and a pool of sources; never either reviewer's
reasoning or a verdict any candidate should get (the polarity guard in its
instructions). The loop's code-side checks (``loop/restate.py``) rank what it
returns; its own order is discarded.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext

from common.instructions import common, load_instructions
from loop.restater.models import RestateBundle, RestatementProposal, RestaterDeps

_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent, common("verdict-scale.md"))

restater_agent = Agent(
    "test",
    system_prompt=_INSTRUCTIONS,
    output_type=RestatementProposal,
    deps_type=RestaterDeps,
    retries=2,
)


@restater_agent.output_validator
def _some_candidate_names_the_entity(
    ctx: RunContext[RestaterDeps], output: RestatementProposal
) -> RestatementProposal:
    """Ask again when no candidate names the entity: the loop would drop them all."""
    from loop.restate import names_entity

    names = ctx.deps.allowed_names if ctx.deps is not None else ()
    if names and not any(names_entity(c.text, names) for c in output.candidates):
        raise ModelRetry(
            "Every candidate must have the claim's entity as its subject, named as one of: "
            + ", ".join(names)
            + ". None of your candidates names any of these; write new candidates."
        )
    return output


def build_restater_prompt(bundle: RestateBundle) -> str:
    """The restater's user prompt for ``bundle``."""
    lines = [f"Claim statement: {bundle.statement}"]
    verdict = f"Pipeline verdict: {bundle.pipeline_verdict} ({bundle.pipeline_confidence})"
    if bundle.tiebreak_rule:
        verdict += f"; settled by the tie-breaker ({bundle.tiebreak_rule})"
    lines.append(verdict)
    lines += ["", "Analyst narrative (context only, not evidence):", bundle.narrative.strip() or "(none)"]
    if bundle.evidence_gaps:
        lines += ["", "Evidence gaps the pipeline's review listed:"]
        lines += [f"- {gap}" for gap in bundle.evidence_gaps]
    lines += ["", f"Entity: {bundle.entity_name}"]
    if bundle.entity_aliases:
        lines.append(f"Aliases: {', '.join(bundle.entity_aliases)}")
    if bundle.entity_type:
        lines.append(f"Type: {bundle.entity_type}")
    if bundle.entity_description:
        lines.append(f"Description: {bundle.entity_description}")
    lines += ["", f"Return between 2 and {bundle.max_candidates} candidates.", "", "Sources:"]
    for src in bundle.sources:
        lines += [
            "",
            f"[{src.marker}] {src.id}",
            f"Title: {src.title}",
            f"Publisher: {src.publisher}",
            f"Kind: {src.kind}",
            f"independence: {src.independence}",
            f"Summary: {src.summary}",
        ]
        if src.key_quotes:
            lines.append("Key quotes:")
            lines += [f"- {q}" for q in src.key_quotes]
        lines += ["Text:", src.body.strip()]
    return "\n".join(lines)
