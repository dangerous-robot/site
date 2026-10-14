"""Checkpoint protocol and implementations for human-in-the-loop gates."""

from __future__ import annotations

from typing import TYPE_CHECKING, runtime_checkable, Protocol

import click

from auditor.models import ComparisonResult

if TYPE_CHECKING:
    from loop.errors import StepError


@runtime_checkable
class CheckpointHandler(Protocol):
    async def review_sources(
        self,
        urls_found: int,
        urls_ingested: int,
        errors: list[StepError],
        sub_question_coverage: dict[str, list[str]] | None = None,
    ) -> bool:
        """Return True to proceed to analysis, False to halt.

        ``sub_question_coverage`` is a map of SubQuestion.id -> list of
        source_ids that addressed it; an empty list signals an uncovered
        axis. May be omitted (or empty) when the planner emitted no
        sub-questions.
        """
        ...

    async def review_disagreement(
        self,
        comparison: ComparisonResult,
    ) -> bool:
        """Return True to accept result, False to flag for human review."""
        ...


class CLICheckpointHandler:
    """Interactive CLI checkpoints via click.confirm()."""

    async def review_sources(
        self,
        urls_found: int,
        urls_ingested: int,
        errors: list[StepError],
        sub_question_coverage: dict[str, list[str]] | None = None,
    ) -> bool:
        click.echo(f"\nFound {urls_found} URLs, ingested {urls_ingested}.")
        if sub_question_coverage:
            click.echo("Sub-question coverage:")
            for sq_id, source_ids in sub_question_coverage.items():
                click.echo(f"  {sq_id}: {len(source_ids)} sources")
        if errors:
            click.echo("Ingestion errors:")
            for e in errors:
                loc = f" ({e.url})" if e.url else ""
                click.echo(f"  [{e.error_type}]{loc}: {e.message}")
        return click.confirm("Proceed to analysis?", default=True)

    async def review_disagreement(
        self,
        comparison: ComparisonResult,
    ) -> bool:
        click.echo(
            f"\nAnalyst: {comparison.primary_verdict.value} ({comparison.primary_confidence.value})"
        )
        click.echo(
            f"Auditor: {comparison.assessed_verdict.value} ({comparison.assessed_confidence.value})"
        )
        click.echo(f"Severity: {comparison.verdict_severity.value}")
        return click.confirm("Accept this result?", default=False)


class AutoApproveCheckpointHandler:
    """Auto-approves all checkpoints. For tests and CI.

    The `calls` attribute records which checkpoints were reached.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def review_sources(
        self,
        urls_found: int,
        urls_ingested: int,
        errors: list[StepError],
        sub_question_coverage: dict[str, list[str]] | None = None,
    ) -> bool:
        self.calls.append("review_sources")
        return True

    async def review_disagreement(
        self,
        comparison: ComparisonResult,
    ) -> bool:
        self.calls.append("review_disagreement")
        return True
