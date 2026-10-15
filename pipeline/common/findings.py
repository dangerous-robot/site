"""The findings record: one per retried, abandoned, split or half-written claim run.

A finding lands at ``research/findings/<yyyy>/<run-id>.yaml`` (the writer is
``orchestrator.persistence.write_finding``); ``dr findings`` lists, counts and
closes them. The loop builds the record, the writer writes it and the CLI
reads it, so this module imports nothing from either.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

# The steps of a claim run, in run order. ``restate`` belongs to the restater
# (not built yet); ``write`` is the writer after the loop.
STEPS: tuple[str, ...] = ("research", "ingest", "analyse", "evaluate", "tiebreak", "restate", "write")
RULES: tuple[str, ...] = ("flaw-retry", "transport-retry", "config-fatal", "half-claim", "tiebreaker", "replay")
OUTCOMES: tuple[str, ...] = ("recovered", "abandoned", "split", "half-claim", "partial")

# The keys of ``config`` a finding records: what a replay needs to run the
# claim again the same way.
CONFIG_KEYS: tuple[str, ...] = (
    "max_sources", "candidate_pool_size", "max_initial_queries", "search_backend",
    "research_origins", "model", "skip_wayback",
)


@dataclass(kw_only=True)
class Finding:
    """One record in ``research/findings/``; fields in the file's key order."""

    run_id: str
    date: datetime.date
    command: str | None = None
    claim_spec: dict[str, Any]
    claim_ref: str | None = None
    config: dict[str, Any]
    models_used: dict[str, str] = field(default_factory=dict)
    step: str
    rule: str
    error: dict[str, Any]
    attempts: int
    outcome: str
    # Every step that was retried on the way, earlier ones included:
    # ``{step, error_type, rule, attempts}``, plus ``message`` on a split
    # entry (a half-claim after a tie-broken run).
    retries: list[dict[str, Any]] = field(default_factory=list)
    closed: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "date": self.date,
            "command": self.command,
            "claim_spec": dict(self.claim_spec),
            "claim_ref": self.claim_ref,
            "config": dict(self.config),
            "models_used": dict(self.models_used),
            "step": self.step,
            "rule": self.rule,
            "error": dict(self.error),
            "attempts": self.attempts,
            "outcome": self.outcome,
            "retries": [dict(r) for r in self.retries],
            "closed": dict(self.closed) if self.closed is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        when = data.get("date")
        if isinstance(when, str):
            when = datetime.date.fromisoformat(when)
        return cls(
            run_id=str(data["run_id"]),
            date=when,
            command=data.get("command"),
            claim_spec=dict(data.get("claim_spec") or {}),
            claim_ref=data.get("claim_ref"),
            config=dict(data.get("config") or {}),
            models_used=dict(data.get("models_used") or {}),
            step=data["step"],
            rule=data["rule"],
            error=dict(data.get("error") or {}),
            attempts=int(data.get("attempts") or 0),
            outcome=data["outcome"],
            retries=[dict(r) for r in data.get("retries") or []],
            closed=dict(data["closed"]) if isinstance(data.get("closed"), dict) else None,
        )

    def summary_line(self) -> str:
        """``finding <run_id>: <outcome> at <step> (<rule>, <n> attempts): <error_type>: <message>``."""
        noun = "attempt" if self.attempts == 1 else "attempts"
        return (
            f"finding {self.run_id}: {self.outcome} at {self.step} "
            f"({self.rule}, {self.attempts} {noun}): "
            f"{self.error.get('error_type')}: {self.error.get('message')}"
        )


def claim_spec_record(spec: Any) -> dict[str, Any]:
    """The ``claim_spec`` block for a ``loop.ClaimSpec``."""
    return {
        "statement": spec.statement,
        "entity": spec.entity.entity_ref,
        "criteria_slug": spec.criteria_slug,
        "topics": list(spec.topics or []),
        "grading_rule": spec.grading_rule,
    }


def config_record(config: Any) -> dict[str, Any]:
    """The ``config`` block for a ``loop.VerifyConfig``."""
    out = {key: getattr(config, key) for key in CONFIG_KEYS}
    out["research_origins"] = list(out["research_origins"] or [])
    return out
