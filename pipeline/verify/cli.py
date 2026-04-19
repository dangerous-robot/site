"""CLI for end-to-end claim verification."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import click
from dotenv import load_dotenv

load_dotenv()

from common.models import DEFAULT_MODEL

from .orchestrator import VerificationResult, VerifyConfig, verify_claim


def _print_result(result: VerificationResult) -> None:
    """Print the verification result in a human-readable format."""
    click.echo("=" * 60)
    click.echo("Claim Verification Report")
    click.echo("=" * 60)
    click.echo(f"Entity:  {result.entity}")
    click.echo(f"Claim:   {result.claim_text}")
    click.echo("")

    click.echo(f"URLs found:    {len(result.urls_found)}")
    click.echo(f"URLs ingested: {len(result.urls_ingested)}")
    click.echo(f"URLs failed:   {len(result.urls_failed)}")
    if result.urls_failed:
        for url in result.urls_failed:
            click.echo(f"  - {url}")
    click.echo("")

    if result.sources:
        click.echo("--- Sources ---")
        for i, src in enumerate(result.sources, 1):
            click.echo(f"  {i}. {src['title']} ({src['publisher']})")
            click.echo(f"     {src['url']}")
        click.echo("")

    if result.draft:
        d = result.draft
        click.echo("--- Draft Claim ---")
        click.echo(f"  Title:      {d.title}")
        click.echo(f"  Category:   {d.category.value}")
        click.echo(f"  Verdict:    {d.verdict.value}")
        click.echo(f"  Confidence: {d.confidence.value}")
        click.echo(f"  Narrative:")
        for line in d.narrative.strip().split("\n"):
            click.echo(f"    {line}")
        click.echo("")

    if result.consistency:
        c = result.consistency
        click.echo("--- Consistency Check ---")
        click.echo(f"  Draft verdict:    {c.actual_verdict.value} ({c.actual_confidence.value})")
        click.echo(f"  Independent:      {c.assessed_verdict.value} ({c.assessed_confidence.value})")
        click.echo(f"  Agreement:        {'yes' if c.verdict_agrees else 'NO'}")
        click.echo(f"  Severity:         {c.verdict_severity.value}")
        click.echo(f"  Needs review:     {'YES' if c.needs_review else 'no'}")
        click.echo(f"  Reasoning:")
        for line in c.reasoning.strip().split("\n"):
            click.echo(f"    {line}")
        if c.evidence_gaps:
            click.echo(f"  Evidence gaps:")
            for gap in c.evidence_gaps:
                click.echo(f"    - {gap}")
        click.echo("")

    if result.errors:
        click.echo("--- Errors ---")
        for err in result.errors:
            click.echo(f"  ! {err}")
        click.echo("")

    click.echo("=" * 60)


@click.command()
@click.argument("entity")
@click.argument("claim")
@click.option("--model", default=DEFAULT_MODEL, help="LLM model to use")
@click.option("--max-sources", default=4, type=int, help="Max sources to ingest")
@click.option("--skip-wayback/--wayback", default=True, help="Skip Wayback Machine")
def main(entity: str, claim: str, model: str, max_sources: int, skip_wayback: bool) -> None:
    """Verify a claim about an entity using web research.

    Example:
        uv run verify-claim "Ecosia" "Ecosia's AI chat runs on renewable energy"
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(2)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    config = VerifyConfig(
        model=model,
        max_sources=max_sources,
        skip_wayback=skip_wayback,
    )

    result = asyncio.run(verify_claim(entity, claim, config))
    _print_result(result)


if __name__ == "__main__":
    main()
