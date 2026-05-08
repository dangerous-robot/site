"""Checkpoint protocol and implementations for human-in-the-loop gates."""

from __future__ import annotations

from typing import Literal, runtime_checkable, Protocol

import click

from auditor.models import ComparisonResult


class StepError:
    """Typed error from a pipeline step.

    The ``error_type`` attribute is intentionally a free-form ``str``, not a
    closed enum or ``Literal``. This is a deliberate design choice: the field
    is a coarse classifier for log filtering and checkpoint UI grouping, and
    new categories should be cheap to add. The trade-off is drift -- so the
    smoke test in ``pipeline/tests/test_step_error_vocab.py`` scans
    production code and fails if a new literal lands without an entry below.

    Currently in-use values
    -----------------------

    Fetch / network (``step="ingest"``):
        - ``timeout``                  -- ingest deadline exceeded
        - ``blocked_host``             -- URL host on the blocklist
        - ``all_blocked``              -- every candidate URL was blocked
        - ``http_{status}``            -- terminal HTTP status (format pattern,
          not a literal; e.g. ``http_404``, ``http_410``)
        - ``http_error``               -- non-terminal HTTP failure
          (exception class name contains ``"HTTP"``)

    Model (``step="research"`` or ``step="ingest"``):
        - ``model_error``              -- agent run raised an unexpected exception
        - ``api_key_missing``          -- model invocation failed because an
          API key wasn't configured

    Researcher (``step="research"``):
        - ``no_queries``               -- query planner returned an empty plan
        - ``no_results``               -- search returned zero candidates
        - ``scorer_dropped_all``       -- URL scorer rejected every candidate

    Reserved (tier1 source-pool expansion, not yet wired)
    -----------------------------------------------------
    See ``docs/plans/source-pool-expansion-tier1.md`` and the companion
    search-backend plan. These literals are documented up-front so paths
    can be implemented in any order without doc churn:

        - ``wayback_unavailable``      -- Path 1: Wayback Machine API down
        - ``memento_unavailable``      -- Path 1: Memento aggregator API down
        - ``edgar_ua_missing``         -- Path 3: SEC EDGAR User-Agent header
          not configured
        - ``edgar_rate_limited``       -- Path 3: SEC EDGAR rate limit hit
        - ``tavily_rate_limited``      -- search backend: Tavily rate limit hit

    What does NOT belong on this channel
    ------------------------------------
    Two adjacent concepts ride on different channels and must not leak here:

        - **Tool fired but found nothing** (e.g. an arXiv query returning zero
          hits) is a normal outcome, not an error. It rides on
          ``research_trace["tool_outcomes"]`` -- do not add literals like
          ``arxiv_no_results`` to ``StepError``.
        - **Per-URL acquisition outcomes** (``recovered``, ``matched``, etc.)
          live on ``sources_consulted[].acquisition.outcome`` in the audit
          trail, not on the error stream.

    Keeping the error channel narrow makes log dashboards and the
    ``review_sources`` checkpoint readable; the trace and audit channels
    carry the per-tool / per-URL detail.
    """

    def __init__(
        self,
        step: str,
        error_type: str,
        message: str,
        url: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.step = step
        self.url = url
        self.error_type = error_type
        self.message = message
        self.retryable = retryable

    def __repr__(self) -> str:
        loc = f" url={self.url}" if self.url else ""
        return f"StepError(step={self.step!r}{loc}, type={self.error_type!r})"


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

    async def review_onboard(
        self,
        entity_name: str,
        entity_type: str,
        applicable_templates: list[str],
        excluded_templates: list[tuple[str, str]],
        entity_description: str = "",
    ) -> Literal["accept", "reject"] | list[str]:
        """Return 'accept', 'reject', or an edited list of template slugs."""
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

    async def review_onboard(
        self,
        entity_name: str,
        entity_type: str,
        applicable_templates: list[str],
        excluded_templates: list[tuple[str, str]],
        entity_description: str = "",
    ) -> Literal["accept", "reject"] | list[str]:
        click.echo(f"\nOnboard: {entity_name} ({entity_type})")
        if entity_description:
            click.echo(f"Description: {entity_description}")
        click.echo(f"Applicable templates ({len(applicable_templates)}):")
        for slug in applicable_templates:
            click.echo(f"  + {slug}")
        if excluded_templates:
            click.echo(f"Excluded templates ({len(excluded_templates)}):")
            for slug, reason in excluded_templates:
                click.echo(f"  - {slug}: {reason}")
        choice = click.prompt(
            "Action", type=click.Choice(["accept", "reject", "edit"]), default="accept"
        )
        if choice == "edit":
            raw = click.prompt("Comma-separated slugs to keep")
            return [s.strip() for s in raw.split(",") if s.strip()]
        return choice


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

    async def review_onboard(
        self,
        entity_name: str,
        entity_type: str,
        applicable_templates: list[str],
        excluded_templates: list[tuple[str, str]],
        entity_description: str = "",
    ) -> Literal["accept", "reject"] | list[str]:
        self.calls.append("review_onboard")
        return "accept"
