"""Unified dr CLI with subcommands for the full pipeline."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from common.models import DEFAULT_MODEL
from orchestrator.persistence import set_claim_status


@click.group()
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.option("--model", default=DEFAULT_MODEL, help="LLM model to use", envvar="DR_MODEL")
@click.pass_context
def main(ctx: click.Context, verbose: bool, model: str) -> None:
    """dr -- dangerousrobot.org research pipeline."""
    ctx.ensure_object(dict)
    ctx.obj["model"] = model
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )


# --------------------------------------------------------------------------- #
# dr verify                                                                     #
# --------------------------------------------------------------------------- #

def _print_verify_result(result) -> None:
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

    if result.analyst_output:
        a = result.analyst_output
        click.echo("--- Analyst Assessment ---")
        click.echo(f"  Entity:     {a.entity.entity_name} ({a.entity.entity_type})")
        click.echo(f"  Title:      {a.verdict.title}")
        click.echo(f"  Category:   {a.verdict.category.value}")
        click.echo(f"  Verdict:    {a.verdict.verdict.value}")
        click.echo(f"  Confidence: {a.verdict.confidence.value}")
        click.echo(f"  Narrative:")
        for line in a.verdict.narrative.strip().split("\n"):
            click.echo(f"    {line}")
        click.echo("")

    if result.consistency:
        c = result.consistency
        click.echo("--- Auditor Check ---")
        click.echo(f"  Analyst verdict:  {c.primary_verdict.value} ({c.primary_confidence.value})")
        click.echo(f"  Auditor verdict:  {c.assessed_verdict.value} ({c.assessed_confidence.value})")
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


@main.command()
@click.argument("entity")
@click.argument("claim")
@click.option("--max-sources", default=4, type=int, help="Max sources to ingest")
@click.option("--skip-wayback/--wayback", default=True, help="Skip Wayback Machine")
@click.option("--interactive/--no-interactive", default=False, help="Enable human-in-the-loop checkpoints")
@click.pass_context
def verify(ctx: click.Context, entity: str, claim: str, max_sources: int, skip_wayback: bool, interactive: bool) -> None:
    """Verify a claim about an entity using web research.

    Example:
        dr verify "Ecosia" "Ecosia's AI chat runs on renewable energy"
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(2)

    from orchestrator.checkpoints import AutoApproveCheckpointHandler, CLICheckpointHandler
    from orchestrator.pipeline import VerifyConfig, verify_claim

    model = ctx.obj["model"]
    config = VerifyConfig(model=model, max_sources=max_sources, skip_wayback=skip_wayback)
    checkpoint = CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()

    result = asyncio.run(verify_claim(entity, claim, config, checkpoint))
    _print_verify_result(result)


# --------------------------------------------------------------------------- #
# dr research                                                                   #
# --------------------------------------------------------------------------- #

@main.command()
@click.argument("claim_text")
@click.option("--max-sources", default=4, type=int, help="Max sources to ingest")
@click.option("--skip-wayback/--wayback", default=True, help="Skip Wayback Machine")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.option("--interactive/--no-interactive", default=False, help="Enable human-in-the-loop checkpoints")
@click.pass_context
def research(ctx: click.Context, claim_text: str, max_sources: int, skip_wayback: bool, repo_root: str | None, interactive: bool) -> None:
    """Research a claim: find sources, evaluate verdict, write everything to disk.

    Example:
        dr research "iPhone 20 will support Neuralink"
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(2)

    if not os.environ.get("BRAVE_WEB_SEARCH_API_KEY"):
        click.echo("Error: BRAVE_WEB_SEARCH_API_KEY not set.", err=True)
        sys.exit(2)

    from orchestrator.checkpoints import AutoApproveCheckpointHandler, CLICheckpointHandler
    from orchestrator.pipeline import VerifyConfig, research_claim

    model = ctx.obj["model"]
    config = VerifyConfig(
        model=model,
        max_sources=max_sources,
        skip_wayback=skip_wayback,
        repo_root=repo_root or "",
    )
    checkpoint = CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()

    result = asyncio.run(research_claim(claim_text, config, checkpoint))

    click.echo("=" * 60)
    click.echo("Research Report")
    click.echo("=" * 60)
    click.echo(f"Entity:  {result.entity}")
    click.echo(f"Claim:   {result.claim_text}")
    click.echo(f"URLs found: {len(result.urls_found)} | ingested: {len(result.urls_ingested)} | failed: {len(result.urls_failed)}")
    click.echo("")

    if result.analyst_output:
        a = result.analyst_output
        click.echo(f"Verdict:    {a.verdict.verdict.value} ({a.verdict.confidence.value})")
        click.echo(f"Title:      {a.verdict.title}")
        click.echo(f"Entity:     {a.entity.entity_name} ({a.entity.entity_type})")
    if result.errors:
        click.echo("Errors:")
        for e in result.errors:
            click.echo(f"  ! {e}")
    click.echo("=" * 60)


# --------------------------------------------------------------------------- #
# dr reassess                                                                   #
# --------------------------------------------------------------------------- #

@main.command()
@click.option("--claim", default=None, help="Check a single claim file")
@click.option("--entity", default=None, help="Check all claims for an entity")
@click.option("--category", default=None, help="Check all claims in a category")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
@click.option("--dry-run", is_flag=True, help="Show what would be checked without calling LLM")
@click.option("--verbose-output", is_flag=True, help="Show full reasoning for all claims")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def reassess(
    ctx: click.Context,
    claim: str | None,
    entity: str | None,
    category: str | None,
    output_format: str,
    dry_run: bool,
    verbose_output: bool,
    repo_root: str | None,
) -> None:
    """Run auditor checks on research claims.

    Example:
        dr reassess --entity ecosia
        dr reassess --claim ecosia/renewable-energy-hosting
    """
    from common.content_loader import list_claims, load_entity, load_source, resolve_repo_root
    from common.frontmatter import parse_frontmatter
    from common.models import Category, Confidence, Verdict
    from auditor.agent import auditor_agent, build_auditor_prompt
    from auditor.compare import compare
    from auditor.models import ClaimBundle, EntityContext, SourceContext
    from auditor.report import format_json_report, format_text_report

    model = ctx.obj["model"]
    root = Path(repo_root) if repo_root else resolve_repo_root()

    if claim:
        path = Path(claim)
        if not path.is_absolute():
            path = root / "research" / "claims" / claim
        if not path.exists():
            click.echo(f"Error: claim file not found: {path}", err=True)
            sys.exit(1)
        claim_paths = [path]
    else:
        claim_paths = list_claims(root, entity=entity, category=category)

    if not claim_paths:
        click.echo("No claims found.", err=True)
        sys.exit(0)

    async def _run():
        from auditor.compare import compare as _compare
        results = []
        for path in claim_paths:
            text = path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)

            claims_dir = root / "research" / "claims"
            claim_id = str(path.relative_to(claims_dir).with_suffix(""))

            actual_verdict = Verdict(fm["verdict"])
            actual_confidence = Confidence(fm["confidence"])

            entity_fm, _ = load_entity(fm["entity"], root)
            ent = EntityContext(
                name=entity_fm["name"],
                type=entity_fm["type"],
                description=entity_fm["description"],
            )

            sources = []
            for sid in fm.get("sources", []):
                try:
                    src_fm, src_body = load_source(sid, root)
                    sources.append(SourceContext(
                        id=sid,
                        title=src_fm["title"],
                        publisher=src_fm["publisher"],
                        summary=src_fm["summary"],
                        key_quotes=src_fm.get("key_quotes", []) or [],
                        body=src_body,
                    ))
                except FileNotFoundError:
                    click.echo(f"Warning: source '{sid}' not found", err=True)

            bundle = ClaimBundle(
                claim_id=claim_id,
                entity=ent,
                category=Category(fm["category"]),
                narrative=body,
                sources=sources,
            )

            if dry_run:
                click.echo(f"[dry-run] Would check: {claim_id}")
                continue

            click.echo(f"Checking: {claim_id} ...", err=True)
            prompt = build_auditor_prompt(bundle)
            with auditor_agent.override(model=model):
                res = await auditor_agent.run(prompt)
            result = _compare(actual_verdict, actual_confidence, res.output, claim_id, str(path.relative_to(root)))

            if verbose_output or result.needs_review:
                click.echo(
                    f"  {result.claim_id}: {result.primary_verdict.value} vs "
                    f"{result.assessed_verdict.value} ({result.verdict_severity.value})",
                    err=True,
                )
            results.append(result)

        if results:
            if output_format == "json":
                click.echo(format_json_report(results))
            else:
                click.echo(format_text_report(results))

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# dr ingest                                                                     #
# --------------------------------------------------------------------------- #

@main.command()
@click.argument("url")
@click.option("--repo-root", default=None, help="Repository root path.")
@click.option("--dry-run", is_flag=True, help="Print output without writing.")
@click.option("--skip-wayback", is_flag=True, help="Skip Wayback Machine lookup.")
@click.pass_context
def ingest(ctx: click.Context, url: str, repo_root: str | None, dry_run: bool, skip_wayback: bool) -> None:
    """Ingest a URL and produce a source file.

    Example:
        dr ingest https://example.com/article
    """
    if not url.startswith(("http://", "https://")):
        click.echo(f"Error: invalid URL: {url}", err=True)
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY") and "test" not in ctx.obj["model"]:
        click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(2)

    import datetime
    import httpx
    from common.content_loader import resolve_repo_root
    from common.frontmatter import serialize_frontmatter
    from common.source_classification import classify_source_type
    from ingestor.agent import IngestorDeps, ingestor_agent
    from ingestor.validation import validate_source_file

    model = ctx.obj["model"]

    try:
        root = repo_root or str(resolve_repo_root())
    except Exception as exc:
        click.echo(f"Error: Cannot determine repo root: {exc}", err=True)
        sys.exit(2)

    async def _run():
        async with httpx.AsyncClient() as client:
            deps = IngestorDeps(
                http_client=client,
                repo_root=root,
                skip_wayback=skip_wayback,
            )
            today = deps.today.isoformat()
            prompt = (
                f"Ingest this URL and produce a SourceFile:\n\n"
                f"URL: {url}\n"
                f"Today's date: {today}\n"
            )

            try:
                with ingestor_agent.override(model=model):
                    res = await asyncio.wait_for(
                        ingestor_agent.run(prompt, deps=deps), timeout=120
                    )
            except asyncio.TimeoutError:
                click.echo("Error: agent timed out after 120 seconds.", err=True)
                return 1
            except Exception as exc:
                click.echo(f"Error: agent failed: {exc}", err=True)
                return 1

            sf = res.output
            validation = validate_source_file(sf, url, root)

            for w in validation.warnings:
                click.echo(f"Warning: {w}", err=True)

            if not validation.ok:
                for e in validation.errors:
                    click.echo(f"Validation error: {e}", err=True)
                return 1

            fm_dict = sf.frontmatter.model_dump(mode="python")
            fm_dict["source_type"] = classify_source_type(
                sf.frontmatter.publisher, sf.frontmatter.kind.value
            )
            markdown = serialize_frontmatter(fm_dict, sf.body.rstrip() + "\n")

            if dry_run:
                click.echo(markdown)
                return 0

            target_dir = Path(root) / "research" / "sources" / str(sf.year)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{sf.slug}.md"

            try:
                with open(target_path, "x", encoding="utf-8") as f:
                    f.write(markdown)
            except FileExistsError:
                click.echo(f"Error: file already exists: {target_path}", err=True)
                return 1

            click.echo(f"Wrote {target_path}")
            return 0

    exit_code = asyncio.run(_run())
    if exit_code:
        sys.exit(exit_code)


# --------------------------------------------------------------------------- #
# dr onboard                                                                    #
# --------------------------------------------------------------------------- #

@main.command()
@click.argument("entity_name")
@click.argument("homepage_url", required=False, default=None)
@click.option("--type", "entity_type", required=True, type=click.Choice(["company", "product", "sector"]), help="Entity type")
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.option("--max-sources", default=4, type=int, help="Max sources to ingest per template")
@click.option("--skip-wayback/--wayback", default=True, help="Skip Wayback Machine")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.option("--interactive/--no-interactive", default=False, help="Enable human-in-the-loop checkpoints")
@click.option("--only", default=None, help="Comma-separated template slugs to run (subset of core templates for the entity type)")
@click.pass_context
def onboard(
    ctx: click.Context,
    entity_name: str,
    homepage_url: str | None,
    entity_type: str,
    verbose: bool,
    max_sources: int,
    skip_wayback: bool,
    repo_root: str | None,
    interactive: bool,
    only: str | None,
) -> None:
    """Onboard an entity using claim templates.

    HOMEPAGE_URL is optional. If provided, it is used directly for entity
    light research instead of searching for the homepage.

    Example:
        dr onboard "Ecosia AI" --type product
        dr onboard "TreadLightlyAI" treadlightly.ai --type company --interactive
    """
    if verbose:
        logging.getLogger().setLevel(logging.INFO)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("Error: ANTHROPIC_API_KEY not set.", err=True)
        sys.exit(2)

    from orchestrator.checkpoints import AutoApproveCheckpointHandler, CLICheckpointHandler
    from orchestrator.pipeline import OnboardResult, VerifyConfig, onboard_entity

    model = ctx.obj["model"]
    config = VerifyConfig(
        model=model,
        max_sources=max_sources,
        skip_wayback=skip_wayback,
        repo_root=repo_root or "",
    )
    checkpoint = CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()

    only_slugs = [s.strip() for s in only.split(",") if s.strip()] if only else None
    result = asyncio.run(onboard_entity(entity_name, entity_type, config, checkpoint, seed_url=homepage_url, only=only_slugs))

    click.echo("=" * 60)
    click.echo("Onboard Report")
    click.echo("=" * 60)
    click.echo(f"Entity:  {result.entity_name} ({result.entity_type})")
    click.echo(f"Status:  {result.status}")

    if result.entity_ref:
        click.echo(f"Ref:     {result.entity_ref}")

    if result.status == "rejected":
        click.echo("")
        click.echo("Onboarding rejected.")
        if result.entity_ref and "drafts/" in result.entity_ref:
            click.echo(f"Draft entity file: research/entities/{result.entity_ref}.md")
    else:
        click.echo("")
        click.echo(f"Templates applied: {len(result.templates_applied)}")
        click.echo(f"Claims created:    {len(result.claims_created)}")
        click.echo(f"Claims failed:     {len(result.claims_failed)}")

        if result.claims_created:
            click.echo("")
            click.echo("Created:")
            for path in result.claims_created:
                click.echo(f"  + {path}")

        if result.claims_failed:
            click.echo("")
            click.echo("Failed:")
            for slug in result.claims_failed:
                click.echo(f"  ! {slug}")

    if result.templates_excluded:
        click.echo("")
        click.echo("Excluded templates:")
        for slug, reason in result.templates_excluded:
            click.echo(f"  - {slug}: {reason}")

    if result.errors:
        click.echo("")
        click.echo("Errors:")
        for err in result.errors:
            click.echo(f"  ! {err}")

    click.echo("=" * 60)


# --------------------------------------------------------------------------- #
# dr review                                                                     #
# --------------------------------------------------------------------------- #

@main.command()
@click.option("--claim", required=True, help="Claim identifier: <entity-slug>/<claim-slug>")
@click.option("--reviewer", default=None, help="Reviewer name or email (defaults to git config user.email)")
@click.option("--notes", default=None, help="Optional review notes")
@click.option("--pr-url", default=None, help="Optional GitHub PR URL")
@click.option("--approve", is_flag=True, default=False, help="Flip status from draft to published after sidecar write")
@click.option("--archive", is_flag=True, default=False, help="Flip status from published to archived after sidecar write")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def review(
    ctx: click.Context,
    claim: str,
    reviewer: str | None,
    notes: str | None,
    pr_url: str | None,
    approve: bool,
    archive: bool,
    repo_root: str | None,
) -> None:
    """Mark a claim as human-reviewed in its audit sidecar.

    With no flag, writes only the sidecar. With ``--approve`` flips
    ``status: draft`` to ``status: published``; with ``--archive`` flips
    ``status: published`` to ``status: archived`` (sidecar written first
    in either case).

    Example:
        dr review --claim ecosia/renewable-energy-hosting --approve
    """
    import datetime
    import subprocess

    import yaml
    from common.content_loader import resolve_repo_root
    from common.frontmatter import parse_frontmatter

    if approve and archive:
        raise click.ClickException("--approve and --archive are mutually exclusive")

    root = Path(repo_root) if repo_root else resolve_repo_root()

    claim_path = root / "research" / "claims" / f"{claim}.md"
    sidecar_path = claim_path.with_name(claim_path.stem + ".audit.yaml")

    if not sidecar_path.exists():
        click.echo("No audit sidecar found. Run the pipeline first.", err=True)
        sys.exit(1)

    # Pre-flight runs before any write so a bad state aborts cleanly,
    # leaving both files untouched.
    expected_current: str | None = None
    new_status: str | None = None
    if approve or archive:
        try:
            fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise click.ClickException(f"claim file not found: {claim_path}") from exc
        except ValueError as exc:
            raise click.ClickException(
                f"malformed frontmatter in {claim_path}: {exc}"
            ) from exc

        current_status = fm.get("status")
        if approve:
            # Missing status field is treated as draft (older pre-stub claims).
            effective_current = current_status if current_status is not None else "draft"
            if effective_current == "archived":
                raise click.ClickException("cannot approve an archived claim")
            if effective_current != "draft":
                raise click.ClickException(
                    f"claim already {effective_current}; use --archive to retire"
                )
            expected_current = current_status  # may be None (key absent)
            new_status = "published"
        else:  # archive
            if current_status is None:
                raise click.ClickException(
                    "cannot archive: claim has no status field; publish first or edit the file manually"
                )
            if current_status != "published":
                raise click.ClickException(
                    f"cannot archive a claim with status {current_status!r}; only published claims can be archived"
                )
            expected_current = "published"
            new_status = "archived"

    # Resolve reviewer
    effective_reviewer = reviewer
    if not effective_reviewer:
        proc = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            check=False,
        )
        git_email = proc.stdout.strip()
        if git_email:
            effective_reviewer = git_email
        else:
            click.echo(
                "Error: --reviewer not provided and git config user.email is empty.",
                err=True,
            )
            sys.exit(1)

    sidecar_data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    sidecar_data["human_review"]["reviewed_at"] = datetime.date.today().isoformat()
    sidecar_data["human_review"]["reviewer"] = effective_reviewer
    effective_notes = notes
    if archive and not effective_notes:
        effective_notes = "archived"
    sidecar_data["human_review"]["notes"] = effective_notes
    sidecar_data["human_review"]["pr_url"] = pr_url

    sidecar_path.write_text(
        yaml.safe_dump(sidecar_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Sidecar is the commit point: if the .md flip raises, the sidecar is
    # already updated and rerunning the same flag re-detects the pre-flip
    # status to complete the transition.
    if new_status is not None:
        try:
            set_claim_status(claim_path, new_status, expected_current)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

    if approve:
        click.echo(
            f"Marked reviewed and published: research/claims/{claim}.md (+ .audit.yaml)"
        )
    elif archive:
        click.echo(
            f"Marked reviewed and archived: research/claims/{claim}.md (+ .audit.yaml)"
        )
    else:
        click.echo(f"Marked reviewed: research/claims/{claim}.audit.yaml")


@main.command()
@click.option("--entity", default=None, help="Lint only claims for this entity slug")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
@click.option("--severity", default="info", type=click.Choice(["error", "warning", "info"]), help="Minimum severity to report")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def lint(ctx: click.Context, entity: str | None, output_format: str, severity: str, repo_root: str | None) -> None:
    """Run static content checks — no LLM, no network.

    Exits 1 if any errors are found.

    \b
    Examples:
      dr lint
      dr lint --entity ecosia
      dr lint --format json --severity error
    """
    from linter.runner import run_all_checks
    from linter.report import format_text_report, format_json_report
    from common.content_loader import resolve_repo_root as _resolve_root

    resolved_root = Path(repo_root) if repo_root else _resolve_root()
    issues = run_all_checks(repo_root=resolved_root, entity_filter=entity)

    if output_format == "json":
        click.echo(format_json_report(issues, min_severity=severity))
    else:
        click.echo(format_text_report(issues, min_severity=severity))

    errors = [i for i in issues if i.severity == "error"]
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
