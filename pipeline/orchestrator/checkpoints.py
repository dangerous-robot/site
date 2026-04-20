"""Checkpoint protocol and implementations for human-in-the-loop gates."""

from __future__ import annotations

from typing import Literal, runtime_checkable, Protocol

import click

from auditor.models import ComparisonResult


class StepError:
    """Typed error from a pipeline step."""

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
    ) -> bool:
        """Return True to proceed to analysis, False to halt."""
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
    ) -> bool:
        click.echo(f"\nFound {urls_found} URLs, ingested {urls_ingested}.")
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
