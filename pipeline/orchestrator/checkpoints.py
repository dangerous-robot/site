"""Checkpoint protocol and implementations for human-in-the-loop gates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, runtime_checkable, Protocol

import click

from auditor.models import ComparisonResult

if TYPE_CHECKING:
    from loop.errors import StepError
    from researcher.entity_enricher import EnrichmentDraft


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

    async def review_entity_enrichment(
        self,
        entity_name: str,
        draft: "EnrichmentDraft",
    ) -> Literal["accept", "reject"]:
        """Surface an enricher draft to the operator and return their decision.

        ``"accept"`` writes the draft to the entity file. ``"reject"`` aborts
        the enrichment without writing. The auto-approve handler returns
        ``"accept"``; CI / tests therefore pick up enricher output verbatim.
        """
        ...

    async def review_entity_disambiguation(
        self,
        entity_name: str,
        candidates: list[str],
    ) -> Literal["accept", "reject"] | str:
        """Surface a candidate list to the operator and return their decision.

        Mirrors ``review_onboard``'s sentinel-or-payload signature:

        - ``"accept"`` — proceed using the first candidate as-is
        - ``"reject"`` — abort the run
        - ``str`` — use this name verbatim (one of the candidates, or a
          free-text override)

        The auto-approve handler returns ``"reject"`` — auto-approve in
        the disambiguation case is conservative; it aborts.
        """
        ...

    async def review_verification_status(
        self,
        entity_name: str,
        website: str | None,
        reasoning: str,
        statuses: list[str],
    ) -> Literal["reject"] | str:
        """Ask the operator which ``verification_status`` to record when the
        verifier found no strong public signal for the entity.

        The entity itself is not in question (its name and file are
        settled); only the status label is. Returns one of ``statuses``
        or ``"reject"`` to abort the run. The auto-approve handler
        returns ``"reject"``.
        """
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

    async def review_entity_enrichment(
        self,
        entity_name: str,
        draft: "EnrichmentDraft",
    ) -> Literal["accept", "reject"]:
        click.echo(f"\nEnrichment draft: {entity_name}")
        if draft.founded is not None:
            click.echo(f"Founded: {draft.founded}")
        click.echo(f"Description: {draft.description}")
        click.echo("History:")
        click.echo(draft.history_markdown.rstrip() or "  (empty)")
        choice = click.prompt(
            "Action",
            type=click.Choice(["accept", "reject"]),
            default="accept",
        )
        return choice

    async def review_entity_disambiguation(
        self,
        entity_name: str,
        candidates: list[str],
    ) -> Literal["accept", "reject"] | str:
        click.echo(f"\nDisambiguation: {entity_name}")
        click.echo("Candidates:")
        for idx, name in enumerate(candidates, 1):
            click.echo(f"  {idx}. {name}")
        click.echo(
            "Reply 'accept' (use #1), 'reject' (abort), a number (1.."
            f"{len(candidates)}), or a name to use verbatim."
        )
        raw = click.prompt("Choice", default="reject").strip()
        if raw in ("accept", "reject"):
            return raw
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(candidates):
                return candidates[n - 1]
            click.echo(f"Out of range; treating {raw!r} as a literal name.")
        return raw

    async def review_verification_status(
        self,
        entity_name: str,
        website: str | None,
        reasoning: str,
        statuses: list[str],
    ) -> Literal["reject"] | str:
        where = f" ({website})" if website else ""
        click.echo(f"\nVerification: {entity_name}{where} could not be verified.")
        if reasoning:
            click.echo(f"Verifier: {reasoning}")
        click.echo(
            "The entity is not in question; its name and file stay as they are. "
            "This sets the entity's `verification_status`, which tells the analyst "
            "to weigh self-published evidence conservatively."
        )
        for idx, status in enumerate(statuses, 1):
            click.echo(f"  {idx}. {status}: {_STATUS_MEANING.get(status, '')}")
        while True:
            raw = click.prompt(
                f"Choice (a number 1..{len(statuses)}, a status, or 'reject' to abort)",
                default="reject",
            ).strip()
            if raw == "reject":
                return raw
            if raw.isdigit() and 1 <= int(raw) <= len(statuses):
                return statuses[int(raw) - 1]
            if raw in statuses:
                return raw
            click.echo(f"{raw!r} is not a verification status; pick a number or 'reject'.")


_STATUS_MEANING = {
    "unverified-startup": "a young company with little public coverage yet",
    "unverified-other": "any other reason, such as a site that blocks fetches",
}


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

    async def review_entity_enrichment(
        self,
        entity_name: str,
        draft: "EnrichmentDraft",
    ) -> Literal["accept", "reject"]:
        self.calls.append("review_entity_enrichment")
        return "accept"

    async def review_entity_disambiguation(
        self,
        entity_name: str,
        candidates: list[str],
    ) -> Literal["accept", "reject"] | str:
        self.calls.append("review_entity_disambiguation")
        # Conservative default: auto-approve in the disambiguation case
        # aborts rather than picking the first candidate.
        return "reject"

    async def review_verification_status(
        self,
        entity_name: str,
        website: str | None,
        reasoning: str,
        statuses: list[str],
    ) -> Literal["reject"] | str:
        self.calls.append("review_verification_status")
        # Conservative default: never label an entity unverified unattended.
        return "reject"
