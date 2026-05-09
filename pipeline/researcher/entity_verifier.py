"""Entity verifier: classifies a candidate entity as verified, ambiguous, or unverified (tool-free, Haiku).

Mirrors the planner / scorer / enricher convention: inline system
prompt, typed Pydantic output, ``retries=2``. Consumes a
``LightResearchBundle`` assembled by the orchestrator's light-research
pass and emits a ``VerificationOutcome`` that the orchestrator routes
on. The verifier never writes; the orchestrator handles halts and
``verification_status`` persistence.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from common.models import EntityType

if TYPE_CHECKING:
    from orchestrator.pipeline import LightResearchBundle


class VerificationOutcome(BaseModel):
    """Verifier's per-entity classification.

    ``status`` drives the orchestrator: ``verified`` proceeds to the
    enricher; ``needs-disambiguation`` halts and surfaces the candidate
    list; ``unverified`` halts and asks the operator to pick a
    ``verification_status`` enum value.

    ``candidates`` is populated only on ``needs-disambiguation`` —
    alphabetical, distinct names the verifier cannot collapse to a
    single entity.
    """

    status: Literal["verified", "needs-disambiguation", "unverified"] = Field(
        description=(
            "Classification of the candidate entity against external "
            "signals. ``verified`` means the inputs identify a single "
            "entity with strong public signals; ``needs-disambiguation`` "
            "means the name resolves to two or more distinct entities "
            "with comparable signal strength; ``unverified`` means no "
            "strong public signal was found in the inputs."
        ),
    )
    candidates: list[str] = Field(
        default_factory=list,
        description=(
            "Alphabetical list of candidate entity names. Populated only "
            "when ``status == 'needs-disambiguation'``; empty otherwise."
        ),
    )
    reasoning: str = Field(
        description=(
            "One- or two-sentence justification for the chosen status. "
            "On ``verified``, name the strongest signal; on "
            "``needs-disambiguation``, name the colliding entities; on "
            "``unverified``, name what was missing."
        ),
    )


_VERIFIER_SCAFFOLD = """\
You verify whether a candidate entity name resolves to a single, recognizable entity given a light-research bundle. You do not write to any file; the orchestrator routes on your output.

Inputs (provided in the user prompt):
- Entity name and type (company / product / subject).
- A raw webpage summary the orchestrator collected during light research.
- The entity's website (when known) and probe-suggested name-collision exclusions.

Output rules (apply to every entity type):
- Return ``verified`` when the inputs describe a single entity with strong public signals (per the per-type guidance below).
- Return ``needs-disambiguation`` when the name resolves to two or more distinct entities with comparable signal strength. Populate ``candidates`` with the colliding names, alphabetical, distinct, no duplicates. Do not include the original ``entity_name`` unless it is itself one of the colliding entities.
- Return ``unverified`` when no strong public signal was found in the inputs. Leave ``candidates`` empty.
- ``reasoning`` is one or two sentences. On ``verified`` name the strongest signal; on ``needs-disambiguation`` name the colliding entities; on ``unverified`` name what was missing.
- Never invent candidates or signals not supported by the inputs. Be conservative: if the inputs are thin, prefer ``unverified`` over a forced ``verified``.
"""


_PER_TYPE_SECTIONS: dict[EntityType, str] = {
    EntityType.COMPANY: """\
Per-type guidance (company):
- Verifier signals (any one is sufficient for ``verified``): the official site resolves and matches the inputs; an SEC EDGAR or Companies House registry hit names this entity; a substantive Wikipedia article exists; news coverage from independent outlets in the last 5 years; identifiable leadership.
- Disambiguation triggers: the name collides with a known product, or with another company in the same or adjacent industry. When two distinct companies are plausible, return ``needs-disambiguation`` and list both in ``candidates``.
""",
    EntityType.PRODUCT: """\
Per-type guidance (product):
- Verifier signals (any one is sufficient for ``verified``): a product page on a recognized parent company's official site; independent reviews from product-review outlets; an app-store or GitHub presence where relevant; consistent versioning or release history.
- Disambiguation triggers: same name as a competing product (different maker), or ambiguous version naming that conflates two distinct products.
- Important exception: the same name as the parent company (e.g., ``greenpt`` / ``treadlightlyai``) is NOT a disambiguation halt — that pattern is the documented self-publication signal and should resolve to ``verified`` when other signals support it.
""",
    EntityType.SUBJECT: """\
Per-type guidance (subject):
- Verifier signals (any one is sufficient for ``verified``): encyclopedic / academic / dictionary consensus on the term's meaning; the term is distinct from a brand using the same word as a product name.
- Disambiguation triggers: the term has multiple unrelated definitions across different fields (e.g., a technical sense and a colloquial sense). Return ``needs-disambiguation`` and list the distinct senses.
""",
}


entity_verifier_agent = Agent(
    "test",
    output_type=VerificationOutcome,
    system_prompt=_VERIFIER_SCAFFOLD,
    retries=2,
)


def build_entity_verifier_prompt(bundle: "LightResearchBundle") -> str:
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
            f"Name-collision probe suggested excludes: {', '.join(bundle.probe_excludes)}"
        )
    lines.append("")
    lines.append("Webpage summary:")
    lines.append(raw_summary)
    lines.append("")
    lines.append(section.rstrip())
    return "\n".join(lines)
