"""CLI entry point for the consistency check agent."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from common.content_loader import list_claims, load_claim, load_entity, load_source, resolve_repo_root
from common.frontmatter import parse_frontmatter
from common.models import Category, Confidence, DEFAULT_MODEL, Verdict

from .agent import ConsistencyDeps, build_user_prompt, consistency_agent
from .compare import compare
from .models import ClaimBundle, ComparisonResult, EntityContext, SourceContext
from .report import format_json_report, format_text_report


def _build_bundle(claim_path: Path, repo_root: Path) -> tuple[ClaimBundle, Verdict, Confidence, str]:
    """Load a claim and its dependencies, returning the bundle plus actual metadata.

    Returns (bundle, actual_verdict, actual_confidence, claim_id).
    """
    text = claim_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    claims_dir = repo_root / "research" / "claims"
    claim_id = str(claim_path.relative_to(claims_dir).with_suffix(""))

    actual_verdict = Verdict(fm["verdict"])
    actual_confidence = Confidence(fm["confidence"])

    entity_path = fm["entity"]
    entity_fm, entity_body = load_entity(entity_path, repo_root)
    entity = EntityContext(
        name=entity_fm["name"],
        type=entity_fm["type"],
        description=entity_fm["description"],
    )

    sources: list[SourceContext] = []
    for source_id in fm.get("sources", []):
        try:
            src_fm, src_body = load_source(source_id, repo_root)
            sources.append(
                SourceContext(
                    id=source_id,
                    title=src_fm["title"],
                    publisher=src_fm["publisher"],
                    summary=src_fm["summary"],
                    key_quotes=src_fm.get("key_quotes", []) or [],
                    body=src_body,
                )
            )
        except FileNotFoundError:
            click.echo(f"Warning: source '{source_id}' not found, skipping", err=True)

    bundle = ClaimBundle(
        claim_id=claim_id,
        entity=entity,
        category=Category(fm["category"]),
        narrative=body,
        sources=sources,
    )

    return bundle, actual_verdict, actual_confidence, claim_id


def _resolve_claim_paths(
    repo_root: Path,
    claim: str | None,
    entity: str | None,
    category: str | None,
) -> list[Path]:
    """Resolve which claim files to check based on CLI options."""
    if claim:
        path = Path(claim)
        if not path.is_absolute():
            path = repo_root / "research" / "claims" / claim
        if not path.exists():
            click.echo(f"Error: claim file not found: {path}", err=True)
            sys.exit(1)
        return [path]

    return list_claims(repo_root, entity=entity, category=category)


async def _check_one(
    bundle: ClaimBundle,
    actual_verdict: Verdict,
    actual_confidence: Confidence,
    claim_id: str,
    claim_file: str,
    model: str,
) -> ComparisonResult:
    """Run consistency check on a single claim."""
    prompt = build_user_prompt(bundle)
    agent = consistency_agent.override(model=model)
    deps = ConsistencyDeps(repo_root="")
    result = await agent.run(prompt, deps=deps)
    return compare(actual_verdict, actual_confidence, result.output, claim_id, claim_file)


async def _run(
    claim_paths: list[Path],
    repo_root: Path,
    output_format: str,
    model: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run consistency checks on the given claim paths."""
    resolved_model = model or DEFAULT_MODEL

    prepared = []
    for path in claim_paths:
        bundle, actual_verdict, actual_confidence, claim_id = _build_bundle(path, repo_root)
        claim_file = str(path.relative_to(repo_root))

        if dry_run:
            click.echo(f"[dry-run] Would check: {claim_id}")
            continue

        click.echo(f"Checking: {claim_id} ...", err=True)
        prepared.append((bundle, actual_verdict, actual_confidence, claim_id, claim_file))

    if dry_run or not prepared:
        return

    results = await asyncio.gather(*(
        _check_one(bundle, av, ac, cid, cf, resolved_model)
        for bundle, av, ac, cid, cf in prepared
    ))

    for r in results:
        if verbose or r.needs_review:
            click.echo(f"  {r.claim_id}: {r.actual_verdict.value} vs {r.assessed_verdict.value} ({r.verdict_severity.value})", err=True)

    if output_format == "json":
        click.echo(format_json_report(list(results)))
    else:
        click.echo(format_text_report(list(results)))


@click.command()
@click.option("--claim", default=None, help="Check a single claim file")
@click.option("--entity", default=None, help="Check all claims for an entity")
@click.option("--category", default=None, help="Check all claims in a category")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]), help="Output format")
@click.option("--model", default=None, help="Override LLM model")
@click.option("--dry-run", is_flag=True, help="Show what would be checked without calling LLM")
@click.option("--verbose", is_flag=True, help="Show full reasoning for all claims")
@click.option("--repo-root", default=None, type=click.Path(exists=True), help="Path to repo root")
def main(
    claim: str | None,
    entity: str | None,
    category: str | None,
    output_format: str,
    model: str | None,
    dry_run: bool,
    verbose: bool,
    repo_root: str | None,
) -> None:
    """Check narrative-verdict consistency for research claims."""
    root = Path(repo_root) if repo_root else resolve_repo_root()
    claim_paths = _resolve_claim_paths(root, claim, entity, category)

    if not claim_paths:
        click.echo("No claims found matching the given filters.", err=True)
        sys.exit(0)

    asyncio.run(_run(claim_paths, root, output_format, model, dry_run, verbose))


if __name__ == "__main__":
    main()
