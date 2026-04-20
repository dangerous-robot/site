"""CLI for researching a claim and persisting results to disk."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import click
from dotenv import load_dotenv

load_dotenv()

from common.models import DEFAULT_MODEL

from .orchestrator import VerifyConfig, research_claim


def _print_result(result) -> None:
    """Print the research result."""
    click.echo("=" * 60)
    click.echo("Research Report")
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
        click.echo("--- Sources (written to disk) ---")
        for i, src in enumerate(result.sources, 1):
            click.echo(f"  {i}. {src['title']} ({src['publisher']})")
        click.echo("")

    if result.draft:
        d = result.draft
        click.echo("--- Claim (written to disk) ---")
        click.echo(f"  Title:      {d.title}")
        click.echo(f"  Entity:     {d.entity_name} ({d.entity_type})")
        click.echo(f"  Category:   {d.category.value}")
        click.echo(f"  Verdict:    {d.verdict.value}")
        click.echo(f"  Confidence: {d.confidence.value}")
        click.echo("")

    if result.consistency:
        c = result.consistency
        click.echo("--- Consistency Check ---")
        click.echo(f"  Draft verdict:    {c.actual_verdict.value} ({c.actual_confidence.value})")
        click.echo(f"  Independent:      {c.assessed_verdict.value} ({c.assessed_confidence.value})")
        click.echo(f"  Agreement:        {'yes' if c.verdict_agrees else 'NO'}")
        click.echo(f"  Severity:         {c.verdict_severity.value}")
        click.echo(f"  Needs review:     {'YES' if c.needs_review else 'no'}")
        click.echo("")

    if result.errors:
        click.echo("--- Errors ---")
        for err in result.errors:
            click.echo(f"  ! {err}")
        click.echo("")

    click.echo("=" * 60)


@click.command()
@click.argument("claim_text")
@click.option("--model", default=DEFAULT_MODEL, help="LLM model to use")
@click.option("--max-sources", default=4, type=int, help="Max sources to ingest")
@click.option("--skip-wayback/--wayback", default=True, help="Skip Wayback Machine")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
def main(claim_text: str, model: str, max_sources: int, skip_wayback: bool, repo_root: str | None) -> None:
    """Research a claim: find sources, evaluate verdict, write everything to disk.

    Example:
        uv run research "iPhone 20 will support Neuralink"
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(2)

    if not os.environ.get("BRAVE_WEB_SEARCH_API_KEY"):
        click.echo("Error: BRAVE_WEB_SEARCH_API_KEY not set.", err=True)
        sys.exit(2)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    config = VerifyConfig(
        model=model,
        max_sources=max_sources,
        skip_wayback=skip_wayback,
        repo_root=repo_root or "",
    )

    result = asyncio.run(research_claim(claim_text, config))
    _print_result(result)


if __name__ == "__main__":
    main()
