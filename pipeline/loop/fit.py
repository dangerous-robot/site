"""The level fit: lower ``verification_level`` to what the claim's listed sources support.

The loop runs it once per run, after the cited filter has fixed the listed
source ids and before the Evaluator, so the Evaluator grades the fitted
verdict; the cited filter also runs it on copies to compare two source lists.
The writer only records its note (``pipeline_run.level_clamp``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from common.models import (
    INDEPENDENT_SOURCES_REQUIRED,
    SELF_REPORT_KINDS,
    SELF_REPORTED_BASIS_KINDS,
    Confidence,
    Independence,
    VerificationLevel,
)
from common.source_classification import effective_independence
from orchestrator.persistence import shorten

if TYPE_CHECKING:
    from analyst.agent import VerdictAssessment

logger = logging.getLogger(__name__)


def _enum_value(value: object) -> object:
    # Callers pass enums; a parsed file holds their string values.
    return getattr(value, "value", value)


def fit_verdict_to_written_pool(
    verdict: "VerdictAssessment",
    sources: list[dict],
    source_ids: list[str],
    entity_name: str,
    log: bool = True,
) -> str | None:
    """Lower ``verification_level`` to what the written source list supports.

    The analyst picks the level from every source it was shown, but the claim
    cites only ``source_ids``, and the site counts that list. Overrides for
    sources not in the list are dropped. Independence per source is its
    override, else the label in ``sources`` (already relabelled for the
    entity). A level short of independent sources falls to
    ``independently-verified`` with one, else to ``self-reported`` (a
    first-party report, documentation or dataset is written) or ``claimed``.
    ``self-reported`` falls to ``claimed`` when no independent source and no
    first-party report, documentation, dataset or article is written; an
    article is kept because the analyst may judge one with methodology or
    data self-reported.
    A level lowered to ``self-reported`` or ``claimed`` gets ``confidence: low``
    and, when the verdict has none, a template ``cap_rationale``. A ``self-reported`` verdict lowered to
    ``claimed`` always gets the template: its own rationale describes the
    first-party report that is no longer written. Either way, a rationale the
    operator wrote on the claim is kept at write time (``_write_claim_file``).

    Returns a one-line note when the level changed, else None. Call it once
    the final ``source_ids`` exist; the loop does so before the Evaluator.
    ``log=False`` is for trial runs on a copy.
    """
    written = set(source_ids)
    if verdict.source_overrides:
        verdict.source_overrides = [
            o for o in verdict.source_overrides if o.source in written
        ] or None

    level = _enum_value(verdict.verification_level)
    required = INDEPENDENT_SOURCES_REQUIRED.get(level)
    if required is None and level != VerificationLevel.SELF_REPORTED.value:
        return None
    by_id = {sd.get("source_id"): sd for sd in sources}
    overrides = {
        o.source: o.independence.value
        for o in verdict.source_overrides or []
        if o.independence is not None
    }
    labels = effective_independence(
        source_ids,
        {sid: by_id.get(sid, {}).get("independence") for sid in source_ids},
        overrides,
    )

    def first_party_of(kinds: frozenset[str]) -> bool:
        return any(
            label == Independence.FIRST_PARTY.value and by_id.get(sid, {}).get("kind") in kinds
            for sid, label in labels
        )

    independent = sum(1 for _, v in labels if v == Independence.INDEPENDENT.value)
    if required is None:
        # self-reported. With an independent source the pool supports more,
        # and the fit only lowers.
        if independent or first_party_of(SELF_REPORTED_BASIS_KINDS):
            return None
        new_level = VerificationLevel.CLAIMED
        reason = "include no first-party report, documentation, dataset or article"
    elif independent >= required:
        return None
    else:
        reason = (
            f"include {independent} independent source(s), and {level} needs {required}"
        )
        if independent >= 1:
            new_level = VerificationLevel.INDEPENDENTLY_VERIFIED
        elif first_party_of(SELF_REPORT_KINDS):
            new_level = VerificationLevel.SELF_REPORTED
        else:
            new_level = VerificationLevel.CLAIMED
    verdict.verification_level = new_level
    if new_level in (VerificationLevel.SELF_REPORTED, VerificationLevel.CLAIMED):
        verdict.confidence = Confidence.LOW
        if not verdict.cap_rationale or required is None:
            # Marked fitted only when the analyst gave no rationale: then the
            # template is all this run proposes. Otherwise a rationale the
            # operator wrote on the claim still wins at write time.
            verdict.cap_rationale_fitted = not verdict.cap_rationale
            verdict.cap_rationale = (
                "Confidence is capped at low: no source on this claim independently "
                f"addresses {shorten(entity_name, 200)}."
            )
    note = f"verification_level {level} lowered to {new_level.value}: the written sources {reason}"
    if log:
        logger.info("Level fit: %s", note)
    return note
