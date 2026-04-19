"""CLI entry point for the ingestor agent."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()
from pathlib import Path

import click
import httpx

from common.content_loader import resolve_repo_root
from common.frontmatter import serialize_frontmatter
from common.models import DEFAULT_MODEL
from ingestor.agent import IngestorDeps, ingestor_agent
from ingestor.validation import validate_source_file

logger = logging.getLogger(__name__)


def _resolve_root(repo_root: str | None) -> str:
    """Resolve the repo root, preferring the explicit flag."""
    if repo_root:
        return repo_root
    try:
        return str(resolve_repo_root())
    except Exception as exc:
        raise click.ClickException(f"Cannot determine repo root: {exc}") from exc


def _build_prompt(url: str, today: str) -> str:
    """Build the user prompt for the agent."""
    return (
        f"Ingest this URL and produce a SourceFile:\n\n"
        f"URL: {url}\n"
        f"Today's date: {today}\n"
    )


async def _run_agent(
    url: str,
    repo_root: str,
    dry_run: bool,
    model: str,
    skip_wayback: bool,
) -> int:
    """Run the ingestor agent and handle output."""
    async with httpx.AsyncClient() as client:
        deps = IngestorDeps(http_client=client, repo_root=repo_root, skip_wayback=skip_wayback)
        prompt = _build_prompt(url, deps.today.isoformat())

        agent = ingestor_agent.override(model=model)

        try:
            result = await asyncio.wait_for(
                agent.run(prompt, deps=deps),
                timeout=120,
            )
        except asyncio.TimeoutError:
            click.echo("Error: agent timed out after 120 seconds.", err=True)
            return 1
        except Exception as exc:
            click.echo(f"Error: agent failed: {exc}", err=True)
            return 1

        source_file = result.output
        validation = validate_source_file(source_file, url, repo_root)

        if validation.warnings:
            for w in validation.warnings:
                click.echo(f"Warning: {w}", err=True)

        if not validation.ok:
            for e in validation.errors:
                click.echo(f"Validation error: {e}", err=True)
            return 1

        fm_dict = source_file.frontmatter.model_dump(mode="python")
        markdown = serialize_frontmatter(fm_dict, source_file.body.rstrip() + "\n")

        if dry_run:
            click.echo(markdown)
            return 0

        target_dir = (
            Path(repo_root)
            / "research"
            / "sources"
            / str(source_file.year)
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{source_file.slug}.md"

        try:
            with open(target_path, "x", encoding="utf-8") as f:
                f.write(markdown)
        except FileExistsError:
            click.echo(f"Error: file already exists: {target_path}", err=True)
            return 1

        click.echo(f"Wrote {target_path}")
        return 0


@click.command()
@click.argument("url")
@click.option("--repo-root", default=None, help="Repository root path.")
@click.option("--dry-run", is_flag=True, help="Print output without writing.")
@click.option(
    "--model",
    default=DEFAULT_MODEL,
    help="Model to use.",
)
@click.option("--skip-wayback", is_flag=True, help="Skip Wayback Machine lookup.")
def main(url: str, repo_root: str | None, dry_run: bool, model: str, skip_wayback: bool) -> None:
    """Ingest a URL and produce a source file."""
    if not url.startswith(("http://", "https://")):
        click.echo(f"Error: invalid URL: {url}", err=True)
        sys.exit(1)

    # Check for API key (only needed for non-test models)
    if not os.environ.get("ANTHROPIC_API_KEY") and "test" not in model:
        click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(2)

    try:
        root = _resolve_root(repo_root)
    except click.ClickException as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    exit_code = asyncio.run(_run_agent(url, root, dry_run, model, skip_wayback))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
