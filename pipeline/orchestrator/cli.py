"""Unified dr CLI with subcommands for the full pipeline."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Iterable
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

from common.logging_setup import configure_logging, new_run_id, progress, run_id_var
from common.models import AGENT_NAMES, DEFAULT_MODEL, resolve_model
from orchestrator.persistence import set_claim_status

logger = logging.getLogger(__name__)


def _safe_repo_root() -> Path | None:
    """Walk up from cwd looking for ``.git`` (file or dir); return None on miss.

    Pure-Python so every ``dr`` invocation skips the ``git rev-parse`` fork.
    ``dr --help`` outside a checkout falls back to console-only logging.
    """
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        if (parent / ".git").exists():
            return parent
    return None


def _required_env_for_model(model: str) -> tuple[str, ...]:
    """Env vars required to make a request against `model`'s provider.

    Specs containing "test" return an empty tuple (used by TestModel paths).
    """
    if "test" in model:
        return ()
    if model.startswith("infomaniak:"):
        return ("INFOMANIAK_API_KEY", "INFOMANIAK_PRODUCT_ID")
    return ("ANTHROPIC_API_KEY",)


def _check_provider_api_keys(models: str | Iterable[str]) -> None:
    """Exit with code 2 if the env vars required by the given models' providers are missing.

    Accepts a single model spec or an iterable so per-agent overrides can be
    validated as a union: a run that uses `anthropic:...` for the analyst and
    `infomaniak:...` for the auditor must have both providers' keys set.
    """
    if isinstance(models, str):
        models = [models]
    required: set[str] = set()
    for m in models:
        required.update(_required_env_for_model(m))
    missing = sorted(name for name in required if not os.environ.get(name))
    if missing:
        click.echo(f"Error: {', '.join(missing)} not set.", err=True)
        sys.exit(2)


def _agent_models_from_ctx(ctx: click.Context) -> list[str]:
    """All resolved model specs for the four agents in this CLI run."""
    base = ctx.obj["model"]
    seen: list[str] = []
    for agent in AGENT_NAMES:
        m = ctx.obj.get(f"{agent}_model") or base
        if m not in seen:
            seen.append(m)
    return seen


def _ctx_per_agent_kwargs(ctx: click.Context) -> dict[str, str | None]:
    """Per-agent model fields ready to splat into ``VerifyConfig(...)``."""
    return {f"{agent}_model": ctx.obj.get(f"{agent}_model") for agent in AGENT_NAMES}


# Subcommand groups for `dr --help`, ordered safest -> most destructive.
# New commands not listed here fall into the "Other" bucket so they stay visible.
_COMMAND_GROUPS: list[tuple[str, list[str]]] = [
    ("Read-only (dry run, no files written)",
     ["lint", "step-research", "step-ingest", "step-analyze", "step-audit", "claim-probe"]),
    ("Creates or overwrites claim files",
     ["onboard", "claim-draft", "claim-refresh", "claim-promote"]),
    ("Modifies existing files in place",
     ["publish", "review", "review-queue"]),
]


class _CategorizedGroup(click.Group):
    """`click.Group` that organizes `dr --help` by write semantics."""

    def format_commands(self, ctx: click.Context, formatter) -> None:
        seen: set[str] = set()
        for heading, names in _COMMAND_GROUPS:
            rows = []
            for name in names:
                cmd = self.get_command(ctx, name)
                if cmd is None or getattr(cmd, "hidden", False):
                    continue
                rows.append((name, cmd.get_short_help_str(limit=120)))
                seen.add(name)
            if rows:
                with formatter.section(heading):
                    formatter.write_dl(rows)

        # Catch-all so a newly-added command isn't silently hidden.
        leftovers = []
        for name in self.list_commands(ctx):
            if name in seen:
                continue
            cmd = self.get_command(ctx, name)
            if cmd is None or getattr(cmd, "hidden", False):
                continue
            leftovers.append((name, cmd.get_short_help_str(limit=70)))
        if leftovers:
            with formatter.section("Other"):
                formatter.write_dl(leftovers)


@click.group(cls=_CategorizedGroup)
@click.option("--verbose", is_flag=True, help="Enable verbose logging (INFO on console; DEBUG always written to logs/debug.log)")
@click.option("--model", default=DEFAULT_MODEL, help="Default LLM model for all agents", envvar="DR_MODEL")
@click.option("--researcher-model", default=None, help="Override model for the researcher agent (falls back to --model)", envvar="DR_RESEARCHER_MODEL")
@click.option("--analyst-model", default=None, help="Override model for the analyst agent (falls back to --model)", envvar="DR_ANALYST_MODEL")
@click.option("--auditor-model", default=None, help="Override model for the auditor agent (falls back to --model)", envvar="DR_AUDITOR_MODEL")
@click.option("--ingestor-model", default=None, help="Override model for the ingestor agent (falls back to --model)", envvar="DR_INGESTOR_MODEL")
@click.pass_context
def main(
    ctx: click.Context,
    verbose: bool,
    model: str,
    researcher_model: str | None,
    analyst_model: str | None,
    auditor_model: str | None,
    ingestor_model: str | None,
) -> None:
    """dr -- dangerousrobot.org research pipeline."""
    ctx.ensure_object(dict)
    ctx.obj["model"] = model
    ctx.obj["researcher_model"] = researcher_model
    ctx.obj["analyst_model"] = analyst_model
    ctx.obj["auditor_model"] = auditor_model
    ctx.obj["ingestor_model"] = ingestor_model
    ctx.obj["verbose"] = verbose
    # Skip logging setup for the bare `dr` / `dr --help` paths so we don't
    # open file handles when the user is just inspecting usage.
    if ctx.invoked_subcommand is not None:
        configure_logging(verbose=verbose, repo_root=_safe_repo_root())
        # Bare set() rather than bind_run_id(): the id must outlive this
        # callback frame to reach the subcommand body.
        run_id_var.set(new_run_id())


# --------------------------------------------------------------------------- #
# dr step-research                                                              #
# --------------------------------------------------------------------------- #

def _print_research_trace(
    entity: str, claim: str, urls: list[str], errors: list[str], trace: dict
) -> None:
    click.echo(f"Entity:  {entity}")
    click.echo(f"Claim:   {claim}")
    click.echo("")

    queries = trace.get("queries", [])
    planner_rationale = trace.get("planner_rationale", "")
    candidates_seen = trace.get("candidates_seen", 0)
    urls_kept = trace.get("urls_kept", 0)
    urls_dropped = trace.get("urls_dropped", 0)
    scorer_rationale = trace.get("scorer_rationale", "")

    click.echo("Step 1 — Query planning")
    click.echo(f"  Queries ({len(queries)}):")
    for q in queries:
        click.echo(f'    "{q}"')
    if planner_rationale:
        click.echo(f"  Rationale: {planner_rationale}")
    click.echo("")

    click.echo("Step 2 — Search")
    query_word = "query" if len(queries) == 1 else "queries"
    click.echo(f"  {candidates_seen} candidates from {len(queries)} {query_word}")
    click.echo("")

    click.echo("Step 3 — URL scoring")
    click.echo(f"  {urls_kept} kept  {urls_dropped} dropped")
    if scorer_rationale:
        click.echo(f"  Rationale: {scorer_rationale}")
    click.echo("")

    if urls:
        click.echo(f"URLs to ingest ({len(urls)}):")
        for i, url in enumerate(urls, 1):
            click.echo(f"  {i}. {url}")
        click.echo("")
        click.echo("  (blocklist not applied — use `dr claim-probe` for production results)")
    else:
        click.echo("No URLs returned.")

    if errors:
        click.echo("")
        click.echo("--- Errors ---")
        for err in errors:
            click.echo(f"  ! {err}")


@main.command("step-research")
@click.argument("entity")
@click.argument("claim")
@click.option("--llm-concurrency", default=8, type=int, help="Max concurrent LLM calls")
@click.pass_context
def step_research(ctx: click.Context, entity: str, claim: str, llm_concurrency: int) -> None:
    """Run only the researcher step and print what it found; nothing is written to disk.

    Runs the decomposed researcher (planner → search → scorer) and prints
    each step's output. Useful for inspecting source discovery without
    running the full pipeline.

    Example:
        dr step-research "Microsoft" "Microsoft's climate pledges rely on carbon credits"
    """
    logger.info("dr step-research: entity=%s claim=%s", entity, claim)
    _check_provider_api_keys(_agent_models_from_ctx(ctx))

    from orchestrator.pipeline import VerifyConfig
    from researcher.decomposed import decomposed_research

    config = VerifyConfig(
        model=ctx.obj["model"],
        llm_concurrency=llm_concurrency,
        **_ctx_per_agent_kwargs(ctx),
    )

    async def _run():
        import httpx
        sem = asyncio.Semaphore(llm_concurrency)
        async with httpx.AsyncClient() as client:
            return await decomposed_research(claim, entity, config, sem, client)

    urls, errors, trace = asyncio.run(_run())
    error_msgs = [f"{e.step}/{e.error_type}: {e.message}" for e in errors]
    _print_research_trace(entity, claim, urls, error_msgs, trace)


# --------------------------------------------------------------------------- #
# dr step-ingest                                                                #
# --------------------------------------------------------------------------- #

@main.command("step-ingest")
@click.argument("url")
@click.option("--write", "do_write", is_flag=True, help="Write source file to disk (default: read-only, prints markdown)")
@click.option("--force", is_flag=True, help="Overwrite existing source file; implies --write")
@click.option("--skip-wayback", is_flag=True, help="Skip Wayback Machine lookup")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def step_ingest(ctx: click.Context, url: str, do_write: bool, force: bool, skip_wayback: bool, repo_root: str | None) -> None:
    """Fetch a URL, structure via the ingestor agent, and print the result.

    Default: read-only (prints Markdown). Use --write (or --force) to persist
    to research/sources/<year>/<slug>.md.

    Example:
        dr step-ingest https://example.com/article
        dr step-ingest https://example.com/article --write
    """
    logger.info("dr step-ingest: url=%s do_write=%s", url, do_write)

    if not url.startswith(("http://", "https://")):
        click.echo(f"Error: invalid URL: {url}", err=True)
        sys.exit(1)

    ingestor_model = ctx.obj.get("ingestor_model") or ctx.obj["model"]
    _check_provider_api_keys(ingestor_model)

    import datetime
    import httpx
    from common.content_loader import resolve_repo_root
    from common.frontmatter import serialize_frontmatter
    from common.source_classification import classify_source_type, independence_for_source_type
    from ingestor.agent import IngestorDeps, ingestor_agent
    from ingestor.validation import validate_source_file

    root_str: str
    try:
        root_str = repo_root or str(resolve_repo_root())
    except Exception as exc:
        click.echo(f"Error: Cannot determine repo root: {exc}", err=True)
        sys.exit(2)

    async def _run():
        async with httpx.AsyncClient() as client:
            deps = IngestorDeps(http_client=client, repo_root=root_str, skip_wayback=skip_wayback)
            prompt = f"Ingest this URL and produce a SourceFile:\n\nURL: {url}\nToday's date: {deps.today.isoformat()}\n"
            try:
                with ingestor_agent.override(model=resolve_model(ingestor_model)):
                    res = await asyncio.wait_for(ingestor_agent.run(prompt, deps=deps), timeout=120)
            except asyncio.TimeoutError:
                click.echo("Error: agent timed out after 120 seconds.", err=True)
                return 1
            except Exception as exc:
                click.echo(f"Error: agent failed: {exc}", err=True)
                return 1

            sf = res.output
            validation = validate_source_file(sf, url, root_str)
            for w in validation.warnings:
                click.echo(f"Warning: {w}", err=True)
            if not validation.ok:
                for e in validation.errors:
                    click.echo(f"Validation error: {e}", err=True)
                return 1

            fm_dict = sf.frontmatter.model_dump(mode="python")
            source_type = classify_source_type(sf.frontmatter.publisher, sf.frontmatter.kind.value)
            fm_dict["source_type"] = source_type
            if not fm_dict.get("independence"):
                fm_dict["independence"] = independence_for_source_type(source_type)
            markdown = serialize_frontmatter(fm_dict, sf.body.rstrip() + "\n")

            if not (do_write or force):
                click.echo(markdown)
                return 0

            target_dir = Path(root_str) / "research" / "sources" / str(sf.year)
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{sf.slug}.md"
            mode = "w" if force else "x"
            try:
                with open(target_path, mode, encoding="utf-8") as f:
                    f.write(markdown)
            except FileExistsError:
                click.echo(f"Error: file already exists: {target_path} (use --force to overwrite)", err=True)
                return 1

            click.echo(f"Wrote {target_path}")
            return 0

    exit_code = asyncio.run(_run())
    if exit_code:
        sys.exit(exit_code)


# --------------------------------------------------------------------------- #
# dr step-analyze                                                               #
# --------------------------------------------------------------------------- #

@main.command("step-analyze")
@click.option("--claim", "claim_ref", required=True,
    help="Claim to re-analyze: entity/slug (e.g. microsoft/corporate-structure)")
@click.option("--write", "do_write", is_flag=True,
    help="Write analyst output to the claim file (default: read-only)")
@click.option("--force", is_flag=True,
    help="Overwrite existing claim file; implies --write")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def step_analyze(
    ctx: click.Context,
    claim_ref: str,
    do_write: bool,
    force: bool,
    repo_root: str | None,
) -> None:
    """Re-run the analyst on an existing claim using its already-ingested sources.

    Default: read-only (prints analyst output). Use --write (or --force) to
    overwrite the claim file on disk.

    Example:
        dr step-analyze --claim microsoft/corporate-structure
        dr step-analyze --claim microsoft/corporate-structure --write --force
    """
    logger.info("dr step-analyze: claim=%s do_write=%s force=%s", claim_ref, do_write, force)

    analyst_model = ctx.obj.get("analyst_model") or ctx.obj["model"]
    _check_provider_api_keys(analyst_model)

    from common.content_loader import load_entity, load_source, resolve_repo_root
    from common.frontmatter import parse_frontmatter
    from common.templates import get_template, load_templates, render_claim_text
    from orchestrator.pipeline import VerifyConfig, _analyse_claim
    from orchestrator.persistence import _write_claim_file

    root = Path(repo_root) if repo_root else resolve_repo_root()
    claims_dir = root / "research" / "claims"
    claim_path = _resolve_claim_path(claim_ref, claims_dir)

    if not claim_path.exists():
        click.echo(f"Error: claim file not found: {claim_path}", err=True)
        sys.exit(1)

    text = claim_path.read_text(encoding="utf-8")
    fm, _narrative = parse_frontmatter(text)

    # Resolve entity
    entity_fm, _ = load_entity(fm["entity"], root)
    entity_name = entity_fm["name"]

    # Reconstruct claim text: prefer re-rendering the template; fall back to title
    claim_text: str
    criteria_slug = fm.get("criteria_slug")
    if criteria_slug:
        try:
            templates = load_templates(root)
            template = get_template(templates, criteria_slug)
            claim_text = render_claim_text(template, entity_name)
        except (KeyError, ValueError):
            claim_text = fm["title"]
    else:
        claim_text = fm["title"]

    # Load sources
    source_dicts: list[dict] = []
    for sid in fm.get("sources") or []:
        try:
            src_fm, src_body = load_source(sid, root)
            source_dicts.append({
                "title": src_fm["title"],
                "publisher": src_fm["publisher"],
                "summary": src_fm["summary"],
                "key_quotes": src_fm.get("key_quotes") or [],
                "body": src_body,
                "slug": sid.split("/")[-1],
                "url": src_fm.get("url", ""),
            })
        except FileNotFoundError:
            click.echo(f"Warning: source '{sid}' not found, skipping", err=True)

    cfg = VerifyConfig(model=ctx.obj["model"], **_ctx_per_agent_kwargs(ctx))

    async def _run():
        return await _analyse_claim(entity_name, claim_text, source_dicts, cfg)

    analyst_out = asyncio.run(_run())

    if analyst_out is None:
        click.echo("Error: analyst agent failed to produce output.", err=True)
        sys.exit(1)

    # Always print the result
    a = analyst_out
    click.echo(f"Entity:     {a.entity.entity_name} ({a.entity.entity_type})")
    click.echo(f"Title:      {a.verdict.title}")
    click.echo(f"Topics:     {', '.join(t.value for t in a.verdict.topics)}")
    click.echo(f"Verdict:    {a.verdict.verdict.value}")
    click.echo(f"Confidence: {a.verdict.confidence.value}")
    click.echo(f"Narrative:")
    for line in a.verdict.narrative.strip().split("\n"):
        click.echo(f"  {line}")

    if not (do_write or force):
        return

    # Write claim file
    entity_ref = fm["entity"]
    claim_slug = claim_path.stem
    source_ids = fm.get("sources") or []

    try:
        written_path = _write_claim_file(
            title=a.verdict.title,
            entity_name=entity_fm["name"],
            entity_ref=entity_ref,
            topics=a.verdict.topics,
            verdict=a.verdict.verdict,
            confidence=a.verdict.confidence,
            narrative=a.verdict.narrative,
            claim_slug=claim_slug,
            source_ids=source_ids,
            repo_root=root,
            force=force,
            status=fm.get("status", "draft"),
            criteria_slug=criteria_slug,
            verification_level=(
                a.verdict.verification_level.value
                if a.verdict.verification_level is not None else None
            ),
            cap_rationale=a.verdict.cap_rationale,
            source_overrides=(
                [o.model_dump(mode="python", exclude_none=True) for o in a.verdict.source_overrides]
                if a.verdict.source_overrides else None
            ),
        )
        click.echo(f"Wrote {written_path}")
    except FileExistsError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# --------------------------------------------------------------------------- #
# dr claim-probe  (formerly verify)                                             #
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
        click.echo(f"  Topics:     {', '.join(t.value for t in a.verdict.topics)}")
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

    if result.blocked_reason is not None:
        click.echo("--- Blocked ---")
        click.echo(
            f"  Pipeline halted: blocked_reason={result.blocked_reason.value}"
        )
        click.echo("")

    if result.errors:
        click.echo("--- Errors ---")
        for err in result.errors:
            click.echo(f"  ! {err}")
        click.echo("")

    click.echo("=" * 60)


@main.command("claim-probe")
@click.argument("entity")
@click.argument("claim")
@click.option("--max-sources", default=None, type=int, help="Target number of successful sources to pass to the analyst (default: VerifyConfig.max_sources)")
@click.option("--candidate-pool-size", default=None, type=int, help="Max URLs to attempt before stopping (default: VerifyConfig.candidate_pool_size)")
@click.option("--skip-wayback/--wayback", default=False, help="Skip Wayback Machine")
@click.option("--interactive/--no-interactive", default=False, help="Enable human-in-the-loop checkpoints")
@click.option("--researcher-mode", default="decomposed", type=click.Choice(["classic", "decomposed"]), help="Researcher implementation (classic=tool-using agent, decomposed=3-step pipeline)")
@click.option("--max-initial-queries", default=None, type=int, help="Max search queries for decomposed researcher (default: VerifyConfig.max_initial_queries)")
@click.option("--llm-concurrency", default=None, type=int, help="Max concurrent LLM calls (default: VerifyConfig.llm_concurrency)")
@click.pass_context
def claim_probe(ctx: click.Context, entity: str, claim: str, max_sources: int | None, candidate_pool_size: int | None, skip_wayback: bool, interactive: bool, researcher_mode: str, max_initial_queries: int | None, llm_concurrency: int | None) -> None:
    """Run the full pipeline in memory and print the verdict; nothing is written to disk.

    Example:
        dr claim-probe "Ecosia" "Ecosia's AI chat runs on renewable energy"
    """
    logger.info("dr claim-probe: entity=%s claim=%s", entity, claim)
    _check_provider_api_keys(_agent_models_from_ctx(ctx))

    from orchestrator.checkpoints import AutoApproveCheckpointHandler, CLICheckpointHandler
    from orchestrator.pipeline import VerifyConfig, verify_claim

    model = ctx.obj["model"]
    overrides = {k: v for k, v in {"max_sources": max_sources, "candidate_pool_size": candidate_pool_size, "max_initial_queries": max_initial_queries, "llm_concurrency": llm_concurrency}.items() if v is not None}
    config = VerifyConfig(
        model=model,
        skip_wayback=skip_wayback,
        researcher_mode=researcher_mode,
        **overrides,
        **_ctx_per_agent_kwargs(ctx),
    )
    checkpoint = CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()

    resolved_entity = None
    if "/" in entity:
        from orchestrator.entity_resolution import parse_entity_ref
        from common.content_loader import resolve_repo_root
        try:
            resolved_entity = parse_entity_ref(entity, resolve_repo_root())
        except ValueError:
            pass  # fall back to bare name hint; not an error for claim-probe

    result = asyncio.run(verify_claim(entity, claim, config, checkpoint, resolved_entity=resolved_entity))
    _print_verify_result(result)


# --------------------------------------------------------------------------- #
# dr claim-draft  (formerly verify-claim)                                       #
# --------------------------------------------------------------------------- #

@main.command("claim-draft")
@click.argument("entity_ref")
@click.argument("claim_text")
@click.option("--max-sources", default=None, type=int, help="Target number of successful sources to pass to the analyst (default: VerifyConfig.max_sources)")
@click.option("--candidate-pool-size", default=None, type=int, help="Max URLs to attempt before stopping (default: VerifyConfig.candidate_pool_size)")
@click.option("--skip-wayback/--wayback", default=False, help="Skip Wayback Machine")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.option("--interactive/--no-interactive", default=False, help="Enable human-in-the-loop checkpoints")
@click.option("--force", is_flag=True, help="Overwrite existing claim file if present")
@click.option("--researcher-mode", default="decomposed", type=click.Choice(["classic", "decomposed"]), help="Researcher implementation (classic=tool-using agent, decomposed=3-step pipeline)")
@click.option("--max-initial-queries", default=None, type=int, help="Max search queries for decomposed researcher (default: VerifyConfig.max_initial_queries)")
@click.option("--llm-concurrency", default=None, type=int, help="Max concurrent LLM calls (default: VerifyConfig.llm_concurrency)")
@click.pass_context
def claim_draft(ctx: click.Context, entity_ref: str, claim_text: str, max_sources: int | None, candidate_pool_size: int | None, skip_wayback: bool, repo_root: str | None, interactive: bool, force: bool, researcher_mode: str, max_initial_queries: int | None, llm_concurrency: int | None) -> None:
    """Run the full pipeline for a claim and write it to disk with status=draft and no criteria_slug.

    ENTITY_REF is required. Use 'products/chatgpt' to pre-resolve entity from disk
    (deterministic claim path, skips LLM entity inference), or '-' to let the analyst
    infer and create the entity.

    Note: claims written by this command are not template-backed (no criteria_slug).
    Use dr claim-promote to generate a template, then dr onboard --only to create a
    template-backed claim.

    \b
    Examples:
        dr claim-draft products/chatgpt "ChatGPT excludes frontier models from user data training"
        dr claim-draft - "Some AI company makes a sustainability claim"
    """
    logger.info("dr claim-draft: entity_ref=%s claim=%s", entity_ref, claim_text)
    _check_provider_api_keys(_agent_models_from_ctx(ctx))

    if not os.environ.get("BRAVE_WEB_SEARCH_API_KEY"):
        click.echo("Error: BRAVE_WEB_SEARCH_API_KEY not set.", err=True)
        sys.exit(2)

    click.echo(
        "Warning: this claim will not be template-backed (no criteria_slug). "
        "Use dr claim-promote to promote it to a template, then dr onboard --only to re-create it.",
        err=True,
    )

    from orchestrator.checkpoints import AutoApproveCheckpointHandler, CLICheckpointHandler
    from orchestrator.pipeline import VerifyConfig, research_claim

    resolved_entity = None
    if entity_ref != "-":
        from orchestrator.entity_resolution import parse_entity_ref
        from common.content_loader import resolve_repo_root
        repo_root_path = Path(repo_root) if repo_root else resolve_repo_root()
        try:
            resolved_entity = parse_entity_ref(entity_ref, repo_root_path)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

    if resolved_entity is not None:
        click.echo(f"Entity: {resolved_entity.entity_name} ({resolved_entity.entity_type.value})")

    model = ctx.obj["model"]
    overrides = {k: v for k, v in {"max_sources": max_sources, "candidate_pool_size": candidate_pool_size, "max_initial_queries": max_initial_queries, "llm_concurrency": llm_concurrency}.items() if v is not None}
    config = VerifyConfig(
        model=model,
        skip_wayback=skip_wayback,
        repo_root=repo_root or "",
        force_overwrite=force,
        researcher_mode=researcher_mode,
        **overrides,
        **_ctx_per_agent_kwargs(ctx),
    )
    checkpoint = CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()

    result = asyncio.run(research_claim(claim_text, config, checkpoint, resolved_entity=resolved_entity))

    click.echo("=" * 60)
    click.echo("Claim-Draft Report")
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
    if result.claim_path:
        from common.sidecar import sidecar_path_for
        sidecar_rel = str(sidecar_path_for(Path(result.claim_path)))
        click.echo("")
        click.echo(f"Claim:   {result.claim_path}")
        click.echo(f"Audit:   {sidecar_rel}")
    if result.errors:
        click.echo("Errors:")
        for e in result.errors:
            click.echo(f"  ! {e}")
    click.echo("=" * 60)


# --------------------------------------------------------------------------- #
# dr claim-refresh                                                               #
# --------------------------------------------------------------------------- #

@main.command("claim-refresh")
@click.argument("claim_ref")
@click.option("--max-sources", default=None, type=int, help="Target number of successful sources to pass to the analyst (default: VerifyConfig.max_sources)")
@click.option("--candidate-pool-size", default=None, type=int, help="Max URLs to attempt before stopping (default: VerifyConfig.candidate_pool_size)")
@click.option("--skip-wayback/--wayback", default=False, help="Skip Wayback Machine")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.option("--interactive/--no-interactive", default=False, help="Enable human-in-the-loop checkpoints")
@click.option("--researcher-mode", default="decomposed", type=click.Choice(["classic", "decomposed"]), help="Researcher implementation (classic=tool-using agent, decomposed=3-step pipeline)")
@click.option("--max-initial-queries", default=None, type=int, help="Max search queries for decomposed researcher (default: VerifyConfig.max_initial_queries)")
@click.option("--llm-concurrency", default=None, type=int, help="Max concurrent LLM calls (default: VerifyConfig.llm_concurrency)")
@click.pass_context
def claim_refresh(
    ctx: click.Context,
    claim_ref: str,
    max_sources: int | None,
    candidate_pool_size: int | None,
    skip_wayback: bool,
    repo_root: str | None,
    interactive: bool,
    researcher_mode: str,
    max_initial_queries: int | None,
    llm_concurrency: int | None,
) -> None:
    """Re-run the full pipeline on an existing template-backed claim and overwrite it in place.

    CLAIM_REF is entity/claim-slug (e.g. microsoft/publishes-sustainability-report).
    The claim must already exist and must have a criteria_slug. The output is always
    written with status=draft regardless of the previous status; this signals that
    human review is needed after a pipeline re-run.

    \b
    Examples:
        dr claim-refresh microsoft/publishes-sustainability-report
        dr claim-refresh sectors/ai-llm-producers/signed-ai-safety-commitments
    """
    import datetime

    logger.info("dr claim-refresh: claim_ref=%s", claim_ref)
    _check_provider_api_keys(_agent_models_from_ctx(ctx))

    from common.content_loader import resolve_repo_root
    from common.frontmatter import parse_frontmatter
    from common.models import BlockedReason, Category, ClaimStatus, Confidence, Verdict
    from common.templates import (
        VOCABULARY_HINT_PREFIX,
        get_template,
        load_templates,
        render_blocked_title,
        render_claim_text,
    )
    from orchestrator.checkpoints import AutoApproveCheckpointHandler, CLICheckpointHandler
    from orchestrator.entity_resolution import parse_entity_ref
    from orchestrator.persistence import (
        _build_sources_consulted,
        _write_audit_sidecar,
        _write_claim_file,
        _write_source_files,
    )
    from orchestrator.pipeline import VerifyConfig, verify_claim

    root = Path(repo_root) if repo_root else resolve_repo_root()
    claims_dir = root / "research" / "claims"

    claim_path = _resolve_claim_path(claim_ref, claims_dir)
    if not claim_path.exists():
        click.echo(
            f"Error: claim file not found: {claim_path}. "
            "Use dr onboard --only to create it.",
            err=True,
        )
        sys.exit(1)

    raw_text = claim_path.read_text(encoding="utf-8")
    fm, _narrative = parse_frontmatter(raw_text)
    criteria_slug = fm.get("criteria_slug")
    if not criteria_slug:
        click.echo(
            "Error: cannot refresh an ad-hoc draft claim. "
            "Run dr claim-promote first to create a template, "
            "then dr onboard --only to create a template-backed claim.",
            err=True,
        )
        sys.exit(1)

    entity_ref = fm.get("entity", "")
    resolved_entity = None
    if entity_ref:
        try:
            resolved_entity = parse_entity_ref(entity_ref, root)
        except ValueError as exc:
            click.echo(f"Warning: could not load entity '{entity_ref}': {exc}", err=True)

    entity_name = (
        resolved_entity.entity_name
        if resolved_entity
        else claim_path.parent.name.replace("-", " ").title()
    )

    try:
        templates = load_templates(root)
        template = get_template(templates, criteria_slug)
    except Exception as exc:
        logger.warning("Could not load templates (falling back to title): %s", exc)
        templates = []
        template = None
    if template is not None:
        claim_text = render_claim_text(template, entity_name)
    else:
        claim_text = fm.get("title") or fm.get("claim") or claim_path.stem

    claim_slug_for_write = claim_path.stem

    model = ctx.obj["model"]
    overrides = {k: v for k, v in {"max_sources": max_sources, "candidate_pool_size": candidate_pool_size, "max_initial_queries": max_initial_queries, "llm_concurrency": llm_concurrency}.items() if v is not None}
    cfg = VerifyConfig(
        model=model,
        skip_wayback=skip_wayback,
        repo_root=str(root),
        force_overwrite=True,
        researcher_mode=researcher_mode,
        **overrides,
        **_ctx_per_agent_kwargs(ctx),
    )
    gate = CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()

    # Run full pipeline; writes are handled below per branch.
    vr = asyncio.run(verify_claim(entity_name, claim_text, cfg, gate, resolved_entity=resolved_entity))

    if vr.errors:
        for err in vr.errors:
            click.echo(f"Warning: {err}", err=True)

    ran_at = datetime.datetime.now(tz=datetime.timezone.utc)

    # Determine the entity_ref to pass to _write_claim_file; fall back to the
    # directory path relative to claims_dir if frontmatter entity is absent.
    write_entity_ref = entity_ref or str(claim_path.parent.relative_to(claims_dir))

    # Mirror onboard's write pattern (four branches).

    # Branch A: threshold-blocked.
    if vr.blocked_reason is not None:
        source_ids = vr.cached_source_ids + _write_source_files(vr.source_files, root)
        try:
            inherited_topics = [Category(t) for t in template.topics] if template else []
        except ValueError:
            inherited_topics = []
        blocked_body = (
            f"This claim is blocked: `{vr.blocked_reason.value}`. "
            f"The pipeline halted before the Analyst could produce a verdict. "
            f"Re-run once more usable sources are available, or archive this claim.\n"
        )
        blocked_title = render_blocked_title(template, entity_name) if template else fm.get("title", claim_slug_for_write)
        blocked_path = _write_claim_file(
            title=blocked_title,
            entity_name=entity_name,
            entity_ref=write_entity_ref,
            topics=inherited_topics,
            verdict=Verdict.UNVERIFIED,
            confidence=Confidence.LOW,
            narrative=blocked_body,
            claim_slug=claim_slug_for_write,
            source_ids=source_ids,
            repo_root=root,
            force=True,
            status=ClaimStatus.BLOCKED,
            blocked_reason=vr.blocked_reason,
            criteria_slug=criteria_slug,
        )
        agents_run = ["researcher", "ingestor"]
        _write_audit_sidecar(
            claim_path=blocked_path,
            comparison=None,
            model=model,
            ran_at=ran_at,
            sources_consulted=_build_sources_consulted(vr.source_files),
            agents_run=agents_run,
            models_used={a: cfg.model_for(a) for a in agents_run},
            research_trace=vr.research_trace,
            reset_review=True,
        )
        click.echo(f"Blocked ({vr.blocked_reason.value}): {blocked_path}")
        return

    # Branch B: analyst failed (no blocked_reason, no analyst_output).
    if vr.analyst_output is None:
        source_ids = vr.cached_source_ids + _write_source_files(vr.source_files, root)
        try:
            inherited_topics = [Category(t) for t in template.topics] if template else []
        except ValueError:
            inherited_topics = []
        blocked_body = (
            f"This claim is blocked: `{BlockedReason.ANALYST_ERROR.value}`. "
            f"The Analyst agent failed to produce a valid assessment after exhausting retries. "
            f"Re-run the pipeline to attempt again, or archive this claim if it consistently fails.\n"
        )
        blocked_title = render_blocked_title(template, entity_name) if template else fm.get("title", claim_slug_for_write)
        blocked_path = _write_claim_file(
            title=blocked_title,
            entity_name=entity_name,
            entity_ref=write_entity_ref,
            topics=inherited_topics,
            verdict=Verdict.UNVERIFIED,
            confidence=Confidence.LOW,
            narrative=blocked_body,
            claim_slug=claim_slug_for_write,
            source_ids=source_ids,
            repo_root=root,
            force=True,
            status=ClaimStatus.BLOCKED,
            blocked_reason=BlockedReason.ANALYST_ERROR,
            criteria_slug=criteria_slug,
        )
        agents_run = ["researcher", "ingestor", "analyst"]
        _write_audit_sidecar(
            claim_path=blocked_path,
            comparison=None,
            model=model,
            ran_at=ran_at,
            sources_consulted=_build_sources_consulted(vr.source_files),
            agents_run=agents_run,
            models_used={a: cfg.model_for(a) for a in agents_run},
            research_trace=vr.research_trace,
            reset_review=True,
        )
        click.echo(f"Blocked (analyst_error): {blocked_path}")
        return

    ao = vr.analyst_output

    # Branch C: vocabulary-unresolved (template has vocab slots, title still contains hint prefix).
    if template and template.vocabulary and VOCABULARY_HINT_PREFIX in ao.verdict.title:
        source_ids = vr.cached_source_ids + _write_source_files(vr.source_files, root)
        try:
            inherited_topics = [Category(t) for t in template.topics]
        except ValueError:
            inherited_topics = []
        blocked_body = (
            f"This claim is blocked: `{BlockedReason.ANALYST_ERROR.value}`. "
            f"The Analyst did not resolve the vocabulary placeholder in the title. "
            f"Re-run the pipeline with better sources, or resolve the vocabulary manually.\n"
        )
        blocked_path = _write_claim_file(
            title=render_blocked_title(template, entity_name),
            entity_name=entity_name,
            entity_ref=write_entity_ref,
            topics=inherited_topics,
            verdict=Verdict.UNVERIFIED,
            confidence=Confidence.LOW,
            narrative=blocked_body,
            claim_slug=claim_slug_for_write,
            source_ids=source_ids,
            repo_root=root,
            force=True,
            status=ClaimStatus.BLOCKED,
            blocked_reason=BlockedReason.ANALYST_ERROR,
            criteria_slug=criteria_slug,
        )
        agents_run = ["researcher", "ingestor", "analyst"]
        _write_audit_sidecar(
            claim_path=blocked_path,
            comparison=None,
            model=model,
            ran_at=ran_at,
            sources_consulted=_build_sources_consulted(vr.source_files),
            agents_run=agents_run,
            models_used={a: cfg.model_for(a) for a in agents_run},
            research_trace=vr.research_trace,
            reset_review=True,
        )
        click.echo(f"Blocked (unresolved vocabulary): {blocked_path}")
        return

    # Branch D: success.
    fresh_ids = _write_source_files(vr.source_files, root) if vr.source_files else []
    source_ids = list(dict.fromkeys(vr.cached_source_ids + fresh_ids))
    try:
        inherited_topics = [Category(t) for t in template.topics] if template else list(ao.verdict.topics)
    except ValueError as exc:
        logger.warning("Template %s has invalid topic; falling back to analyst topics: %s", criteria_slug, exc)
        inherited_topics = list(ao.verdict.topics)

    claim_path_written = _write_claim_file(
        title=ao.verdict.title,
        entity_name=entity_name,
        entity_ref=write_entity_ref,
        topics=inherited_topics,
        verdict=ao.verdict.verdict,
        confidence=ao.verdict.confidence,
        narrative=ao.verdict.narrative,
        claim_slug=claim_slug_for_write,
        source_ids=source_ids,
        repo_root=root,
        force=True,
        status=ClaimStatus.DRAFT,
        criteria_slug=criteria_slug,
        seo_title=ao.verdict.seo_title,
        takeaway=ao.verdict.takeaway,
        verification_level=(
            ao.verdict.verification_level.value
            if ao.verdict.verification_level is not None else None
        ),
        cap_rationale=ao.verdict.cap_rationale,
        source_overrides=(
            [o.model_dump(mode="python", exclude_none=True) for o in ao.verdict.source_overrides]
            if ao.verdict.source_overrides else None
        ),
    )

    agents_run = ["researcher", "ingestor", "analyst", "auditor"]
    _write_audit_sidecar(
        claim_path=claim_path_written,
        comparison=vr.consistency,
        model=model,
        ran_at=ran_at,
        sources_consulted=_build_sources_consulted(vr.source_files),
        agents_run=agents_run,
        models_used={a: cfg.model_for(a) for a in agents_run},
        research_trace=vr.research_trace,
        reset_review=True,
    )

    click.echo(f"Refreshed: {claim_path_written}")
    if vr.consistency and vr.consistency.needs_review:
        click.echo("Note: auditor flagged this claim for review (verdict disagreement).")


# --------------------------------------------------------------------------- #
# dr claim-promote                                                               #
# --------------------------------------------------------------------------- #

@main.command("claim-promote")
@click.argument("claim_ref")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def claim_promote(
    ctx: click.Context,
    claim_ref: str,
    repo_root: str | None,
) -> None:
    """Interactively generate a template from an ad-hoc draft claim and append it to research/templates.yaml.

    CLAIM_REF is entity/claim-slug (e.g. microsoft/some-ad-hoc-claim).

    Use this to promote a one-off claim to a repeatable template. After running,
    use dr onboard <entity> --only <template-slug> to create a proper template-backed claim.

    \b
    Example:
        dr claim-promote microsoft/some-ad-hoc-claim
    """
    logger.info("dr claim-promote: claim_ref=%s", claim_ref)

    from common.content_loader import resolve_repo_root
    from common.frontmatter import parse_frontmatter

    root = Path(repo_root) if repo_root else resolve_repo_root()
    claims_dir = root / "research" / "claims"

    claim_path = _resolve_claim_path(claim_ref, claims_dir)
    if not claim_path.exists():
        click.echo(f"Error: claim file not found: {claim_path}", err=True)
        sys.exit(1)

    raw_text = claim_path.read_text(encoding="utf-8")
    fm, _narrative = parse_frontmatter(raw_text)

    existing_criteria = fm.get("criteria_slug")
    if existing_criteria:
        click.echo(
            f"Error: claim is already template-backed (criteria_slug: {existing_criteria}). Nothing to promote.",
            err=True,
        )
        sys.exit(1)

    # Best-effort entity resolution; falls back to directory name.
    entity_ref = fm.get("entity", "")
    entity_name: str | None = None
    if entity_ref:
        try:
            from orchestrator.entity_resolution import parse_entity_ref
            resolved = parse_entity_ref(entity_ref, root)
            entity_name = resolved.entity_name
        except ValueError:
            pass

    if entity_name is None:
        # Fall back to title-casing the entity directory name.
        entity_name = claim_path.parent.name.replace("-", " ").title()

    claim_title = fm.get("title") or fm.get("claim") or ""  # 'claim' is the legacy key

    click.echo("")
    click.echo("Proposed template fields:")
    click.echo(f"  Entity name:  {entity_name}")
    click.echo(f"  Claim title:  {claim_title}")
    click.echo(f"  Topics:       {fm.get('topics', [])}")
    click.echo("")

    template_slug = click.prompt("Template slug (e.g. publishes-sustainability-report)")
    entity_type_input = click.prompt(
        "Entity type",
        type=click.Choice(["company", "product", "sector"]),
    )
    topics_input = click.prompt("Topics (comma-separated, e.g. environmental-impact,ai-safety)")
    core_input = click.prompt("Core template?", default="Y", show_default=True)
    notes_input = click.prompt("Notes (optional)", default="", show_default=False)

    # Derive template text by replacing entity name with type-appropriate placeholder.
    placeholder_map = {"company": "COMPANY", "product": "PRODUCT", "sector": "ENTITY"}
    placeholder = placeholder_map[entity_type_input]
    template_text = claim_title.replace(entity_name, placeholder) if entity_name and entity_name in claim_title else claim_title

    topics_list = [t.strip() for t in topics_input.split(",") if t.strip()]
    core_bool = core_input.strip().lower() not in ("n", "no", "false", "0")

    # Handle both dict-under-"templates:" format (production) and bare-list format
    # (test fixtures). Detect format here for the write step so appending stays valid.
    import yaml as _yaml

    templates_path = root / "research" / "templates.yaml"
    is_dict_format = False  # True for production {"templates": [...]} files
    if templates_path.exists():
        try:
            raw = _yaml.safe_load(templates_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "templates" in raw:
                existing_entries = raw["templates"] or []
                is_dict_format = True
            elif isinstance(raw, list):
                existing_entries = raw
            else:
                existing_entries = []
            existing_slugs = {e.get("slug") for e in existing_entries if isinstance(e, dict)}
            if template_slug in existing_slugs:
                click.echo(
                    f"Error: template slug '{template_slug}' already exists in templates.yaml.",
                    err=True,
                )
                sys.exit(1)
        except Exception as exc:
            click.echo(f"Warning: could not validate slug uniqueness: {exc}", err=True)
            existing_entries = []

    # For dict-format (production) files, append as a text fragment to preserve
    # comments and field ordering. For bare-list-format files (test fixtures),
    # do a read-modify-write so the YAML stays valid.
    topics_yaml = "[" + ", ".join(topics_list) + "]"
    entry_fragment = (
        f"- slug: {template_slug}\n"
        f'  text: "{template_text}"\n'
        f"  entity_type: {entity_type_input}\n"
        f"  topics: {topics_yaml}\n"
        f"  core: {'true' if core_bool else 'false'}\n"
        + (f'  notes: "{notes_input}"\n' if notes_input else "")
    )

    if is_dict_format:
        # Text-fragment append under "templates:": preserves comments and
        # field order of existing entries (2-space indent under the key).
        indented = "\n" + "".join(f"  {line}" for line in entry_fragment.splitlines(keepends=True))
        with open(templates_path, "a", encoding="utf-8") as f:
            f.write(indented)
    else:
        # Bare-list format (test fixtures): rebuild as a list YAML file.
        existing_text = templates_path.read_text(encoding="utf-8") if templates_path.exists() else ""
        # Normalise: strip any trailing empty-list marker `[]` and write entries.
        existing_stripped = existing_text.strip()
        if existing_stripped in ("", "[]"):
            new_content = entry_fragment
        else:
            # Existing entries already in list format; append after last entry.
            new_content = existing_stripped.rstrip("\n") + "\n" + entry_fragment
        templates_path.write_text(new_content, encoding="utf-8")

    click.echo(f"\nTemplate written to {templates_path}")
    entity_ref_for_cmd = entity_ref or claim_path.parent.name
    click.echo(f"Run: dr onboard {entity_ref_for_cmd} --only {template_slug} --force")


# --------------------------------------------------------------------------- #
# dr step-audit  (formerly reassess)                                            #
# --------------------------------------------------------------------------- #

@main.command("step-audit")
@click.option("--claim", default=None, help="Audit a single claim file (entity/slug)")
@click.option("--entity", default=None, help="Audit all claims for an entity")
@click.option("--topic", default=None, help="Audit all claims with a given topic")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
@click.option("--dry-run", is_flag=True, help="Show what would be audited without calling LLM")
@click.option("--write", "do_write", is_flag=True,
    help="Write auditor results to .audit.yaml sidecar (default: read-only)")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def step_audit(
    ctx: click.Context,
    claim: str | None,
    entity: str | None,
    topic: str | None,
    output_format: str,
    dry_run: bool,
    do_write: bool,
    repo_root: str | None,
) -> None:
    """Re-run the auditor on existing claim file(s) and report verdict/confidence disagreements.

    Default: read-only (prints report). Use --write to update .audit.yaml sidecars.

    Example:
        dr step-audit --entity ecosia
        dr step-audit --claim ecosia/renewable-energy-hosting
        dr step-audit --claim ecosia/renewable-energy-hosting --write
    """
    import datetime
    import yaml as _yaml

    logger.info(
        "dr step-audit: claim=%s entity=%s topic=%s dry_run=%s do_write=%s",
        claim, entity, topic, dry_run, do_write,
    )
    from common.content_loader import list_claims, load_entity, load_source, resolve_repo_root
    from common.frontmatter import parse_frontmatter
    from common.models import Category, Confidence, Verdict
    from auditor.agent import auditor_agent, build_auditor_prompt
    from auditor.compare import compare
    from auditor.models import ClaimBundle, EntityContext, SourceContext
    from auditor.report import format_json_report, format_text_report

    auditor_model = ctx.obj.get("auditor_model") or ctx.obj["model"]
    _check_provider_api_keys(auditor_model)
    verbose = ctx.obj.get("verbose", False)
    root = Path(repo_root) if repo_root else resolve_repo_root()
    claims_dir = root / "research" / "claims"

    if claim:
        claim_paths = [_resolve_claim_path(claim, claims_dir)]
    else:
        claim_paths = list_claims(root, entity=entity, topic=topic)

    if not claim_paths:
        click.echo("No claims found.", err=True)
        sys.exit(0)

    async def _run():
        from auditor.compare import compare as _compare
        from orchestrator.persistence import _write_audit_sidecar
        results = []
        for path in claim_paths:
            text = path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)

            claim_id = str(path.relative_to(claims_dir).with_suffix(""))
            actual_verdict = Verdict(fm["verdict"])
            actual_confidence = Confidence(fm["confidence"])

            entity_fm, _ = load_entity(fm["entity"], root)
            ent = EntityContext(
                name=entity_fm["name"],
                type=entity_fm["type"],
                description=entity_fm["description"],
            )

            source_contexts = []
            sources_consulted = []
            for sid in fm.get("sources", []):
                try:
                    src_fm, src_body = load_source(sid, root)
                    source_contexts.append(SourceContext(
                        id=sid,
                        title=src_fm["title"],
                        publisher=src_fm["publisher"],
                        summary=src_fm["summary"],
                        key_quotes=src_fm.get("key_quotes", []) or [],
                        body=src_body,
                    ))
                    sources_consulted.append({
                        "id": sid,
                        "url": src_fm.get("url", ""),
                        "title": src_fm["title"],
                        "ingested": True,
                    })
                except FileNotFoundError:
                    click.echo(f"Warning: source '{sid}' not found", err=True)

            bundle = ClaimBundle(
                claim_id=claim_id,
                entity=ent,
                topics=[Category(t) for t in fm["topics"]],
                narrative=body,
                sources=source_contexts,
            )

            if dry_run:
                click.echo(f"[dry-run] Would audit: {claim_id}")
                continue

            progress("Auditing: %s ...", claim_id)
            prompt = build_auditor_prompt(bundle)
            with auditor_agent.override(model=resolve_model(auditor_model)):
                res = await auditor_agent.run(prompt)
            result = _compare(actual_verdict, actual_confidence, res.output, claim_id, str(path.relative_to(root)))

            if verbose or result.needs_review:
                click.echo(
                    f"  {result.claim_id}: {result.primary_verdict.value} vs "
                    f"{result.assessed_verdict.value} ({result.verdict_severity.value})",
                    err=True,
                )
            results.append(result)

            if do_write:
                from common.sidecar import sidecar_path_for
                sidecar_path = sidecar_path_for(path)
                research_trace = None
                if sidecar_path.exists():
                    try:
                        existing = _yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or {}
                        research_trace = existing.get("research")
                    except _yaml.YAMLError:
                        pass
                _write_audit_sidecar(
                    claim_path=path,
                    comparison=result,
                    model=auditor_model,
                    ran_at=datetime.datetime.now(tz=datetime.timezone.utc),
                    sources_consulted=sources_consulted,
                    agents_run=["auditor"],
                    models_used={"auditor": auditor_model},
                    research_trace=research_trace,
                )
                click.echo(f"Wrote {sidecar_path}")

        if results:
            if output_format == "json":
                click.echo(format_json_report(results))
            else:
                click.echo(format_text_report(results))

    asyncio.run(_run())


@main.command("reassess", hidden=True)
@click.option("--claim", default=None)
@click.option("--entity", default=None)
@click.option("--topic", default=None)
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
@click.option("--dry-run", is_flag=True)
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def reassess(ctx, claim, entity, topic, output_format, dry_run, repo_root):
    """Deprecated: use `dr step-audit` instead."""
    click.echo("Note: `dr reassess` is deprecated; use `dr step-audit`.", err=True)
    ctx.invoke(step_audit, claim=claim, entity=entity, topic=topic,
               output_format=output_format, dry_run=dry_run, do_write=False,
               repo_root=repo_root)


# --------------------------------------------------------------------------- #
# dr ingest                                                                     #
# --------------------------------------------------------------------------- #

@main.command(hidden=True)
@click.argument("url")
@click.option("--repo-root", default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--skip-wayback", is_flag=True)
@click.option("--force", is_flag=True)
@click.pass_context
def ingest(ctx: click.Context, url: str, repo_root: str | None, dry_run: bool, skip_wayback: bool, force: bool) -> None:
    """Deprecated: use `dr step-ingest` instead."""
    click.echo("Note: `dr ingest` is deprecated; use `dr step-ingest`.", err=True)
    ctx.invoke(step_ingest, url=url, do_write=not dry_run, force=force,
               skip_wayback=skip_wayback, repo_root=repo_root)


# --------------------------------------------------------------------------- #
# dr onboard                                                                    #
# --------------------------------------------------------------------------- #

@main.command()
@click.argument("entity_name")
@click.argument("homepage_url", required=False, default=None)
@click.option("--type", "entity_type", required=False, default=None, type=click.Choice(["company", "product", "sector"]), help="Entity type (required for bare names; inferred from ref when entity_name is a type/slug ref)")
@click.option("--max-sources", default=None, type=int, help="Target number of successful sources to pass to the analyst per template (default: VerifyConfig.max_sources)")
@click.option("--candidate-pool-size", default=None, type=int, help="Max URLs to attempt before stopping (default: VerifyConfig.candidate_pool_size)")
@click.option("--skip-wayback/--wayback", default=False, help="Skip Wayback Machine")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.option("--interactive/--no-interactive", default=False, help="Enable human-in-the-loop checkpoints")
@click.option("--only", default=None, help="Comma-separated template slugs to run (subset of core templates for the entity type)")
@click.option("--force", is_flag=True, help="Overwrite existing claim files if present")
@click.option("--researcher-mode", default="decomposed", type=click.Choice(["classic", "decomposed"]), help="Researcher implementation (classic=tool-using agent, decomposed=3-step pipeline)")
@click.option("--max-initial-queries", default=None, type=int, help="Max search queries for decomposed researcher (default: VerifyConfig.max_initial_queries)")
@click.option("--llm-concurrency", default=None, type=int, help="Max concurrent LLM calls (default: VerifyConfig.llm_concurrency)")
@click.pass_context
def onboard(
    ctx: click.Context,
    entity_name: str,
    homepage_url: str | None,
    entity_type: str | None,
    max_sources: int | None,
    candidate_pool_size: int | None,
    skip_wayback: bool,
    repo_root: str | None,
    interactive: bool,
    only: str | None,
    force: bool,
    researcher_mode: str,
    max_initial_queries: int | None,
    llm_concurrency: int | None,
) -> None:
    """Generate stub claim files for a new entity, one per applicable template in research/templates.yaml.

    ENTITY_NAME can be a bare display name (requires --type) or a type/slug ref like
    sectors/ai-llm-producers (type inferred; skips entity-file creation).

    HOMEPAGE_URL is optional. If provided, it is used directly for entity
    light research instead of searching for the homepage.

    Example:
        dr onboard "Ecosia AI" --type product
        dr onboard "TreadLightlyAI" treadlightly.ai --type company --interactive
        dr onboard sectors/ai-llm-producers
    """
    resolved_entity_ref: str | None = None
    if "/" in entity_name:
        from common.content_loader import resolve_repo_root as _resolve_repo_root
        from orchestrator.entity_resolution import parse_entity_ref
        repo_root_path = Path(repo_root) if repo_root else _resolve_repo_root()
        try:
            resolved = parse_entity_ref(entity_name, repo_root_path)
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
        resolved_entity_ref = entity_name
        entity_name = resolved.entity_name
        entity_type = resolved.entity_type.value
    elif entity_type is None:
        raise click.UsageError("--type is required when ENTITY_NAME is not a type/slug ref")

    logger.info(
        "dr onboard: name=%s type=%s ref=%s seed_url=%s only=%s",
        entity_name,
        entity_type,
        resolved_entity_ref,
        homepage_url,
        only,
    )
    _check_provider_api_keys(_agent_models_from_ctx(ctx))

    from orchestrator.checkpoints import AutoApproveCheckpointHandler, CLICheckpointHandler
    from orchestrator.pipeline import OnboardResult, VerifyConfig, onboard_entity

    model = ctx.obj["model"]
    overrides = {k: v for k, v in {"max_sources": max_sources, "candidate_pool_size": candidate_pool_size, "max_initial_queries": max_initial_queries, "llm_concurrency": llm_concurrency}.items() if v is not None}
    config = VerifyConfig(
        model=model,
        skip_wayback=skip_wayback,
        repo_root=repo_root or "",
        force_overwrite=force,
        researcher_mode=researcher_mode,
        **overrides,
        **_ctx_per_agent_kwargs(ctx),
    )
    checkpoint = CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()

    only_slugs = [s.strip() for s in only.split(",") if s.strip()] if only else None
    result = asyncio.run(onboard_entity(entity_name, entity_type, config, checkpoint, seed_url=homepage_url, only=only_slugs, entity_ref=resolved_entity_ref))

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
        click.echo(f"Claims skipped:    {len(result.claims_skipped)}")
        click.echo(f"Claims failed:     {len(result.claims_failed)}")

        if result.claims_created:
            click.echo("")
            click.echo("Created:")
            for path in result.claims_created:
                click.echo(f"  + {path}")

        if result.claims_skipped:
            click.echo("")
            click.echo("Skipped (already exist):")
            for path in result.claims_skipped:
                click.echo(f"  = {path}")

    if result.templates_excluded:
        click.echo("")
        click.echo("Excluded templates:")
        for slug, reason in result.templates_excluded:
            click.echo(f"  - {slug}: {reason}")

    # Render failures and errors as a single "Failed:" block. Every entry in
    # result.errors is slug-prefixed (invariant enforced in pipeline.py); the
    # bare result.claims_failed list is redundant for rendering and only used
    # for the "Claims failed: N" count line above.
    if result.errors:
        click.echo("")
        click.echo("Failed:")
        for err in result.errors:
            click.echo(f"  ! {err}")

    click.echo("=" * 60)


# --------------------------------------------------------------------------- #
# dr review                                                                     #
# --------------------------------------------------------------------------- #

@main.command()
@click.option("--claim", required=True, help="Claim identifier: <entity-slug>/<claim-slug>, or a bare <claim-slug> if unique across entities.")
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
    """Record human sign-off in one claim's audit sidecar; --approve also flips status draft->published, --archive flips published->archived.

    With no flag, writes only the sidecar. With ``--approve`` flips
    ``status: draft`` to ``status: published``; with ``--archive`` flips
    ``status: published`` to ``status: archived`` (sidecar written first
    in either case).

    Example:
        dr review --claim ecosia/renewable-energy-hosting --approve
    """
    logger.info(
        "dr review: claim=%s approve=%s archive=%s",
        claim,
        approve,
        archive,
    )

    from common.content_loader import resolve_repo_root
    from common.sidecar import sidecar_path_for
    from orchestrator.review import approve_claim

    if approve and archive:
        raise click.ClickException("--approve and --archive are mutually exclusive")

    root = Path(repo_root) if repo_root else resolve_repo_root()
    claims_dir = root / "research" / "claims"

    bare = claim[:-3] if claim.endswith(".md") else claim
    if "/" in bare:
        claim_path = claims_dir / f"{bare}.md"
    else:
        # Bare slug is accepted if exactly one entity directory carries it.
        matches = sorted(claims_dir.glob(f"*/{bare}.md"))
        if not matches:
            click.echo(
                f"Claim file not found: no research/claims/*/{bare}.md.",
                err=True,
            )
            sys.exit(1)
        if len(matches) > 1:
            rels = ", ".join(str(m.relative_to(claims_dir).with_suffix("")) for m in matches)
            click.echo(
                f"Ambiguous claim slug {bare!r}; matches: {rels}. "
                f"Re-run with --claim <entity-slug>/{bare}.",
                err=True,
            )
            sys.exit(1)
        claim_path = matches[0]

    if not claim_path.exists():
        click.echo(
            f"Claim file not found: {claim_path.relative_to(root)}.",
            err=True,
        )
        sys.exit(1)
    if not sidecar_path_for(claim_path).exists():
        click.echo(
            f"No audit sidecar found at {sidecar_path_for(claim_path).relative_to(root)}. "
            f"Run the pipeline first.",
            err=True,
        )
        sys.exit(1)

    mode = "approve" if approve else "archive" if archive else "review"
    approve_claim(
        claim_path,
        reviewer=reviewer,
        notes=notes,
        pr_url=pr_url,
        mode=mode,
    )

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


# --------------------------------------------------------------------------- #
# dr review-queue                                                               #
# --------------------------------------------------------------------------- #


@main.command("review-queue")
@click.option(
    "--format", "output_format", default=None, type=click.Choice(["text", "json"]),
    help=(
        "Print the queue and exit instead of starting the interactive walkthrough. "
        "`text` is a tab-separated table; `json` is a JSON array. "
        "Matches the convention set by `dr lint --format`."
    ),
)
@click.option("--filter-entity", default=None, help="Restrict the queue to one entity directory (e.g. 'openai').")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def review_queue(
    ctx: click.Context,
    output_format: str | None,
    filter_entity: str | None,
    repo_root: str | None,
) -> None:
    """Walk through draft claims awaiting human review (a/s/p/o/q keys); --format text|json prints the queue for CI/scripting.

    Default (no --format): interactive loop over draft claims with completed
    research. Single-key actions: [a]pprove, [s]kip, [p]review, [o]pen in
    editor, [q]uit. Approve delegates to the same `approve_claim` callable as
    `dr review --approve`.

    With --format: prints the queue and exits. Always exits 0 regardless of
    queue size; this is informational.

    \b
    Examples:
      dr review-queue
      dr review-queue --format text
      dr review-queue --format json | jq '.[].claim_slug'
      dr review-queue --filter-entity openai
    """
    import json as _json

    from common.content_loader import resolve_repo_root as _resolve_root
    from orchestrator.review_queue import (
        find_publication_queue,
        format_table,
        run_interactive,
        to_json_records,
    )

    root = Path(repo_root) if repo_root else _resolve_root()
    items = find_publication_queue(root, filter_entity=filter_entity)

    if output_format == "json":
        click.echo(_json.dumps(to_json_records(items), indent=2))
        return
    if output_format == "text":
        click.echo(format_table(items))
        return

    run_interactive(items, root)


# --------------------------------------------------------------------------- #
# dr publish                                                                    #
# --------------------------------------------------------------------------- #


def _resolve_claim_path(claim: str, claims_dir: Path) -> Path:
    """Resolve a `--claim` argument to a concrete claim .md path.

    Accepts ``<entity>/<slug>``, ``<entity>/<slug>.md``, or a bare ``<slug>``
    that is unique across entity directories. Calls ``sys.exit(1)`` on
    missing or ambiguous slugs (matching dr review's behavior).
    """
    bare = claim[:-3] if claim.endswith(".md") else claim
    if "/" in bare:
        return claims_dir / f"{bare}.md"
    matches = sorted(claims_dir.glob(f"*/{bare}.md"))
    if not matches:
        click.echo(
            f"Claim file not found: no research/claims/*/{bare}.md.",
            err=True,
        )
        sys.exit(1)
    if len(matches) > 1:
        rels = ", ".join(str(m.relative_to(claims_dir).with_suffix("")) for m in matches)
        click.echo(
            f"Ambiguous claim slug {bare!r}; matches: {rels}. "
            f"Re-run with --claim <entity-slug>/{bare}.",
            err=True,
        )
        sys.exit(1)
    return matches[0]


@main.command()
@click.option("--entity", default=None, help="Publish all draft claims under this entity slug.")
@click.option("--claim", default=None, help="Publish a single claim: <entity-slug>/<claim-slug>, or a unique bare <claim-slug>.")
@click.option("--all", "all_", is_flag=True, default=False, help="Publish every draft claim in the repo.")
@click.option("--dry-run", is_flag=True, default=False, help="List planned transitions without writing anything.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip the interactive confirmation prompt.")
@click.option("--note", default=None, help="Suffix appended to the canonical '[auto-publish] ' note prefix.")
@click.option(
    "--continue-on-error/--strict",
    default=True,
    help=(
        "Default: continue past per-claim errors and exit 1 at end if any occurred. "
        "Use --strict to fail-fast on the first error."
    ),
)
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def publish(
    ctx: click.Context,
    entity: str | None,
    claim: str | None,
    all_: bool,
    dry_run: bool,
    yes: bool,
    note: str | None,
    continue_on_error: bool,
    repo_root: str | None,
) -> None:
    """Bulk-flip draft claims to published, filling sidecar with an auto-publish marker (no reviewer recorded); supports --dry-run.

    Claims processed by this command render as "Unreviewed" on the site.
    Use `dr review --approve` for human-reviewed publication.

    Each matched draft has its sidecar updated with reviewed_at=<today>,
    reviewer=null, notes="[auto-publish] <suffix>", and pr_url=null, then
    its `status:` flipped from draft to published. Claims with status
    published, archived, or blocked are skipped with a warning.

    Reversibility: a later `dr review --claim <slug> --reviewer alice` (no
    `--approve`) writes the reviewer in and flips the badge to "Reviewed".

    Discoverability: `grep -l '\\[auto-publish\\]' research/claims/*/*.audit.yaml`.

    \b
    Examples:
      dr publish --entity ecosia --dry-run
      dr publish --claim ecosia/renewable-energy-hosting --yes
      dr publish --all --yes --note "v1.0.0 backfill"
    """
    logger.info(
        "dr publish: claim=%s entity=%s all=%s dry_run=%s",
        claim,
        entity,
        all_,
        dry_run,
    )

    import datetime

    import yaml
    from common.content_loader import list_claims, resolve_repo_root
    from common.frontmatter import has_criterion, parse_frontmatter
    from common.sidecar import sidecar_path_for

    # Mode selection: exactly one of {--claim, --entity, --all}.
    selectors = sum(1 for s in (claim, entity, all_) if s)
    if selectors == 0:
        raise click.ClickException(
            "specify exactly one of --claim, --entity, or --all"
        )
    if selectors > 1:
        raise click.ClickException(
            "--claim, --entity, and --all are mutually exclusive"
        )

    root = Path(repo_root) if repo_root else resolve_repo_root()
    claims_dir = root / "research" / "claims"

    # Resolve the candidate claim set.
    if claim is not None:
        candidate_paths = [_resolve_claim_path(claim, claims_dir)]
    elif entity is not None:
        candidate_paths = list_claims(root, entity=entity)
    else:  # all_
        candidate_paths = list_claims(root)

    if not candidate_paths:
        click.echo("No claims matched the given filters.", err=True)
        sys.exit(1)

    # Build canonical note string. The "[auto-publish] " prefix is fixed
    # so a grep across audit sidecars finds every bot-published claim;
    # operator-supplied --note text appends as the suffix.
    suffix = note if note else "bulk publish, no human review"
    note_text = f"[auto-publish] {suffix}"

    # Classify each candidate. Only `to_publish` are written; other lists
    # surface in the summary so an operator can see what was skipped.
    to_publish: list[tuple[Path, str | None]] = []  # (claim_path, current_status)
    already_published: list[Path] = []
    skipped_archived: list[Path] = []
    skipped_blocked: list[tuple[Path, str]] = []  # (path, blocked_reason)
    skipped_missing_sidecar: list[Path] = []
    skipped_missing_criterion: list[Path] = []
    classify_errors: list[tuple[Path, str]] = []

    for claim_path in candidate_paths:
        try:
            fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError) as exc:
            classify_errors.append((claim_path, f"frontmatter parse failed: {exc}"))
            continue

        current_status = fm.get("status")
        # Missing status field is treated as draft (parity with `dr review`).
        effective_current = current_status if current_status is not None else "draft"

        if effective_current == "published":
            already_published.append(claim_path)
            continue
        if effective_current == "archived":
            skipped_archived.append(claim_path)
            continue
        if effective_current == "blocked":
            skipped_blocked.append((claim_path, str(fm.get("blocked_reason", "<unset>"))))
            continue
        if effective_current != "draft":
            classify_errors.append(
                (claim_path, f"unrecognized status {effective_current!r}")
            )
            continue

        # Draft: still need a sidecar to update.
        sidecar_path = sidecar_path_for(claim_path)
        if not sidecar_path.exists():
            skipped_missing_sidecar.append(claim_path)
            continue

        # Publish gate: criteria_slug is required for the public artifact.
        if not has_criterion(fm):
            skipped_missing_criterion.append(claim_path)
            continue

        to_publish.append((claim_path, current_status))

    # Print the classification summary.
    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(root))
        except ValueError:
            return str(p)

    click.echo(f"Matched {len(candidate_paths)} claim(s); {len(to_publish)} to publish.")
    if to_publish:
        sample = to_publish[:10]
        for path, _ in sample:
            click.echo(f"  draft -> published: {_rel(path)}")
        if len(to_publish) > 10:
            click.echo(f"  ... and {len(to_publish) - 10} more")
    if already_published:
        click.echo(f"Skipped (already published): {len(already_published)}")
    if skipped_archived:
        click.echo(f"Skipped (archived): {len(skipped_archived)}")
        for path in skipped_archived:
            click.echo(f"  ! archived, not republished: {_rel(path)}", err=True)
    if skipped_blocked:
        click.echo(f"Skipped (blocked): {len(skipped_blocked)}")
        for path, reason in skipped_blocked:
            click.echo(f"  ! blocked ({reason}): {_rel(path)}", err=True)
    if skipped_missing_sidecar:
        click.echo(f"Skipped (no audit sidecar): {len(skipped_missing_sidecar)}")
        for path in skipped_missing_sidecar:
            click.echo(f"  ! missing sidecar: {_rel(path)}", err=True)
    if skipped_missing_criterion:
        click.echo(f"Skipped (no criteria_slug): {len(skipped_missing_criterion)}")
        for path in skipped_missing_criterion:
            click.echo(f"  ! missing criteria_slug: {_rel(path)}", err=True)
    if classify_errors:
        click.echo(f"Skipped (errors during classification): {len(classify_errors)}")
        for path, msg in classify_errors:
            click.echo(f"  ! {_rel(path)}: {msg}", err=True)

    if dry_run:
        click.echo("Dry run: no files written.")
        sys.exit(0)

    if not to_publish:
        click.echo("Nothing to publish.")
        # Per-claim errors during classification (e.g. unparseable frontmatter)
        # and missing-criterion skips both count as failures: criterion is a
        # hard publish requirement, so a partial-completion run should signal.
        sys.exit(1 if (classify_errors or skipped_missing_criterion) else 0)

    # Confirmation prompt unless --yes.
    if not yes:
        click.confirm(
            f"Flip {len(to_publish)} draft(s) to published WITHOUT recording human review?",
            abort=True,
        )

    today_iso = datetime.date.today().isoformat()
    published_count = 0
    # Missing-criterion skips count as errors: the operator asked us to publish,
    # we couldn't, that's a partial-completion signal that should fail loud.
    publish_errors: list[tuple[Path, str]] = list(classify_errors) + [
        (p, "missing criteria_slug") for p in skipped_missing_criterion
    ]

    for claim_path, current_status in to_publish:
        sidecar_path = sidecar_path_for(claim_path)
        try:
            sidecar_data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
            sidecar_data["human_review"]["reviewed_at"] = today_iso
            sidecar_data["human_review"]["reviewer"] = None
            sidecar_data["human_review"]["notes"] = note_text
            sidecar_data["human_review"]["pr_url"] = None
            sidecar_path.write_text(
                yaml.safe_dump(sidecar_data, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            # current_status may be None (key absent); pass it through so
            # set_claim_status's mismatch check sees the actual on-disk value.
            set_claim_status(claim_path, "published", expected_current=current_status)
        except Exception as exc:
            publish_errors.append((claim_path, str(exc)))
            click.echo(f"  ! failed: {_rel(claim_path)}: {exc}", err=True)
            if not continue_on_error:
                click.echo(
                    f"\nAborted on first error (--strict). Published {published_count} "
                    f"of {len(to_publish)} before failing.",
                    err=True,
                )
                sys.exit(1)
            continue

        published_count += 1
        click.echo(f"  + published: {_rel(claim_path)}")

    click.echo(
        f"\nDone. Published {published_count} of {len(to_publish)} matched draft(s); "
        f"{len(publish_errors)} error(s)."
    )
    sys.exit(1 if publish_errors else 0)


@main.command()
@click.option("--entity", default=None, help="Lint only claims for this entity slug")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
@click.option("--severity", default="info", type=click.Choice(["error", "warning", "info"]), help="Minimum severity to report")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def lint(ctx: click.Context, entity: str | None, output_format: str, severity: str, repo_root: str | None) -> None:
    """Static content checks against research/ (frontmatter schema, source refs, criteria slugs, sign-off); no LLM, no network.

    Exits 1 if any errors are found.

    \b
    Examples:
      dr lint
      dr lint --entity ecosia
      dr lint --format json --severity error
    """
    logger.info(
        "dr lint: entity=%s severity=%s format=%s",
        entity or "<all>",
        severity,
        output_format,
    )

    from linter.runner import run_all_checks
    from linter.report import format_text_report, format_json_report
    from common.content_loader import resolve_repo_root as _resolve_root

    resolved_root = Path(repo_root) if repo_root else _resolve_root()
    issues, files_checked = run_all_checks(repo_root=resolved_root, entity_filter=entity)

    if output_format == "json":
        click.echo(format_json_report(issues, min_severity=severity))
    else:
        click.echo(format_text_report(issues, files_checked, min_severity=severity))

    errors = [i for i in issues if i.severity == "error"]
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
