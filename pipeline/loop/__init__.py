"""The one claim run: research, ingest, analyse, evaluate, tie-break, restate.

``run`` takes a ``ClaimSpec`` and a ``VerifyConfig`` and returns a
``VerificationResult``; ``rerun`` runs the Analyst or the Evaluator alone over
stored sources. The package writes no file: a command that keeps a run calls
the writer in ``orchestrator.persistence`` with the result.

Everything not exported here is private to the package.
"""

from loop.errors import StepError
from loop.policy import ERROR_POLICY, STEP_ON_EXHAUSTION, Rule, classify_exception, rule_for
from loop.spec import ClaimSpec, VerificationResult, VerifyConfig
from loop.ingest import check_ingested_source, ingest_one, ingest_urls, merge_acquisition_writes
from loop.analyse import analyse_claim, apply_entity_match, audit_claim
from loop.fit import fit_verdict_to_written_pool
# Last: importing the ``loop.run`` submodule binds ``loop.run`` to the module;
# this line rebinds the name to the function.
from loop.run import blocked_reason_label, rerun, run

__all__ = [
    "ClaimSpec",
    "ERROR_POLICY",
    "Rule",
    "STEP_ON_EXHAUSTION",
    "StepError",
    "VerificationResult",
    "VerifyConfig",
    "analyse_claim",
    "apply_entity_match",
    "audit_claim",
    "blocked_reason_label",
    "check_ingested_source",
    "classify_exception",
    "fit_verdict_to_written_pool",
    "ingest_one",
    "ingest_urls",
    "merge_acquisition_writes",
    "rerun",
    "rule_for",
    "run",
]
