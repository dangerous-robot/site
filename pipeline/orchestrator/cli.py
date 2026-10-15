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

from common.logging_setup import configure_logging, hr, new_run_id, progress, run_id_var
from common.models import AGENT_NAMES, DEFAULT_MODEL, resolve_model

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


_PROVIDER_ENV: dict[str, tuple[str, ...]] = {
    "infomaniak": ("INFOMANIAK_API_KEY", "INFOMANIAK_PRODUCT_ID"),
    "greenpt": ("GREENPT_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "google-gla": ("GEMINI_API_KEY",),
    "google-vertex": ("GOOGLE_APPLICATION_CREDENTIALS",),
}


def _required_env_for_model(model: str) -> tuple[str, ...]:
    """Env vars required to make a request against `model`'s provider.

    Specs containing "test" return an empty tuple (used by TestModel paths).
    Specs without a recognized provider prefix raise a click.UsageError so
    the failure surfaces upfront with a clear message rather than as a deep
    SDK error like "OPENAI_API_KEY not set" mid-run.

    The ``||`` split must precede the ``"test" in model`` short-circuit,
    otherwise ``"anthropic:claude||test"`` skips the API-key check for
    the anthropic leg.
    """
    if "||" in model:
        return tuple(dict.fromkeys(
            var for leg in model.split("||") for var in _required_env_for_model(leg.strip())
        ))
    if "test" in model:
        return ()
    prefix, sep, _ = model.partition(":")
    if sep and prefix in _PROVIDER_ENV:
        return _PROVIDER_ENV[prefix]
    known = ", ".join(sorted(_PROVIDER_ENV))
    raise click.UsageError(
        f"Model spec {model!r} has no recognized provider prefix. "
        f"Use one of: {known} (e.g. 'greenpt:gpt-oss-120b')."
    )


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


def _check_search_key(config) -> None:
    """Fail before any model call when the Brave backend has no key.

    The researcher only discovers a missing key at search time, after the
    planner's paid model call has already run.
    """
    if config.search_backend == "brave" and not os.environ.get("BRAVE_WEB_SEARCH_API_KEY"):
        raise click.UsageError(
            "BRAVE_WEB_SEARCH_API_KEY is not set and RESEARCH_SEARCH_BACKEND is brave"
        )


def _agent_models_from_ctx(ctx: click.Context) -> list[str]:
    """All resolved model specs for the agents in this CLI run."""
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
     ["lint", "stats", "step-research", "step-ingest", "step-analyze", "step-audit"]),
    ("Creates or overwrites claim files (dr draft --dry-run writes nothing)",
     ["draft"]),
    ("Modifies existing files in place (dr findings writes only with --close)",
     ["review", "findings"]),
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
@click.option("--verbose", is_flag=True, help="Surface INFO-level events on stderr in addition to progress lines. File logs (logs/info.log, logs/debug.log) are written at full detail regardless of this flag.")
@click.option("--model", default=DEFAULT_MODEL, help="Default LLM model for all agents", envvar="DR_MODEL")
@click.option("--researcher-model", default=None, help="Override model for the researcher agent (falls back to --model)", envvar="DR_RESEARCHER_MODEL")
@click.option("--analyst-model", default=None, help="Override model for the analyst agent (falls back to --model)", envvar="DR_ANALYST_MODEL")
@click.option("--auditor-model", default=None, help="Override model for the auditor agent (falls back to --model)", envvar="DR_AUDITOR_MODEL")
@click.option("--ingestor-model", default=None, help="Override model for the ingestor agent (falls back to --model)", envvar="DR_INGESTOR_MODEL")
@click.option("--tiebreaker-model", default=None, help="Override model for the tie-breaker agent (falls back to --model)", envvar="DR_TIEBREAKER_MODEL")
@click.option("--restater-model", default=None, help="Override model for the restater (falls back to --auditor-model, then --model)", envvar="DR_RESTATER_MODEL")
@click.pass_context
def main(
    ctx: click.Context,
    verbose: bool,
    model: str,
    researcher_model: str | None,
    analyst_model: str | None,
    auditor_model: str | None,
    ingestor_model: str | None,
    tiebreaker_model: str | None,
    restater_model: str | None,
) -> None:
    """dr -- dangerousrobot.org research pipeline."""
    ctx.ensure_object(dict)
    ctx.obj["model"] = model
    ctx.obj["researcher_model"] = researcher_model
    ctx.obj["analyst_model"] = analyst_model
    ctx.obj["auditor_model"] = auditor_model
    ctx.obj["ingestor_model"] = ingestor_model
    ctx.obj["tiebreaker_model"] = tiebreaker_model
    ctx.obj["restater_model"] = restater_model
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
        click.echo("  (blocklist not applied — use `dr draft --dry-run` for production results)")
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

    from loop import VerifyConfig
    from researcher.decomposed import decomposed_research

    config = VerifyConfig(
        model=ctx.obj["model"],
        llm_concurrency=llm_concurrency,
        **_ctx_per_agent_kwargs(ctx),
    )
    _check_search_key(config)

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
    from ingestor.agent import IngestorDeps, archive_after_ingest, ingestor_agent
    from ingestor.arxiv_affiliation import arxiv_corporate_lab
    from loop import StepError, check_ingested_source
    from orchestrator.persistence import resolve_source_slugs, source_markdown

    root_str: str
    try:
        root_str = repo_root or str(resolve_repo_root())
    except Exception as exc:
        click.echo(f"Error: Cannot determine repo root: {exc}", err=True)
        sys.exit(2)

    # A dry run must not make archive.org capture the page, through the
    # model's wayback_check tool or the lookup in code.
    capture = do_write or force

    async def _run():
        async with httpx.AsyncClient() as client:
            deps = IngestorDeps(
                http_client=client, repo_root=root_str, requested_url=url,
                skip_wayback=skip_wayback, allow_save=capture,
            )
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

            corporate_lab = await arxiv_corporate_lab(client, url)
            checked = check_ingested_source(
                url, res.output, deps, Path(root_str), corporate_lab
            )
            if isinstance(checked, StepError):
                if checked.error_type == "fetch_failed":
                    click.echo(f"Error: fetch failed, no page text for {url}: {checked.message}", err=True)
                else:
                    click.echo(f"Validation error: {checked.message}", err=True)
                return 1
            _url, sf = checked

            archive = await archive_after_ingest(sf, deps)
            if archive["status"] == "failed":
                hint = "" if capture else " (Save Page Now runs only with --write)"
                click.echo(f"Archive lookup failed for {url}: {archive['error']}{hint}", err=True)

            markdown = source_markdown(sf)

            if not (do_write or force):
                click.echo(markdown)
                return 0

            # After resolving, an existing file at the slug always has this
            # URL, so --force can only overwrite the same page.
            resolve_source_slugs([sf], Path(root_str))
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
# dr wayback-backfill                                                           #
# --------------------------------------------------------------------------- #

def _set_archived_url(text: str, archived_url: str | None) -> str:
    """Return ``text`` with its ``archived_url:`` line set to ``archived_url``.

    The line is added after ``url:`` when absent, replaced (with any indented
    continuation lines) when present, and removed when ``archived_url`` is
    None. Editing the line, not re-serializing the frontmatter, keeps the rest
    of the file byte-for-byte (quoting, wrapping and key order).
    """
    import yaml

    from common.frontmatter import parse_frontmatter

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("no frontmatter")
    close_at = next(
        (i for i, ln in enumerate(lines[1:], 1) if ln.rstrip("\r\n") == "---"), None
    )
    if close_at is None:
        raise ValueError("frontmatter is not closed")

    def _key_line(key: str) -> int | None:
        return next(
            (i for i in range(1, close_at) if lines[i].startswith(f"{key}:")), None
        )

    def _after_continuation(i: int) -> int:
        i += 1
        while i < close_at and lines[i].startswith(" "):
            i += 1
        return i

    new_lines = (
        [yaml.safe_dump({"archived_url": archived_url}, width=1_000_000)]
        if archived_url
        else []
    )
    existing = _key_line("archived_url")
    if existing is not None:
        updated_lines = lines[:existing] + new_lines + lines[_after_continuation(existing):]
    else:
        url_at = _key_line("url")
        if url_at is None:
            raise ValueError("no url line in frontmatter")
        insert_at = _after_continuation(url_at)
        updated_lines = lines[:insert_at] + new_lines + lines[insert_at:]
    updated = "".join(updated_lines)

    before, body = parse_frontmatter(text)
    after, new_body = parse_frontmatter(updated)
    expected = {k: v for k, v in before.items() if k != "archived_url"}
    if archived_url:
        expected["archived_url"] = archived_url
    if after != expected or new_body != body:
        raise ValueError("setting archived_url changed other frontmatter")
    return updated


@main.command("wayback-backfill")
@click.argument("source_ids", nargs=-1, required=True)
@click.option(
    "--recheck",
    is_flag=True,
    help="Also check sources that already have archived_url, and replace or remove a bad link.",
)
@click.option("--repo-root", default=None, type=click.Path(exists=True))
def wayback_backfill(source_ids: tuple[str, ...], recheck: bool, repo_root: str | None) -> None:
    """Add an archive.org link to existing source files that lack one.

    SOURCE_IDS are year/slug ids, e.g. 2025/brave-website-challenge. Each
    source's URL is looked up on archive.org and a link is written as
    `archived_url` only when archive.org replays that capture with HTTP 200
    for the same page (TimeGate's nearest capture, else the newest such one
    in the CDX index, else a checked Save Page Now capture). Sources that
    already have one are skipped, unless --recheck: then the existing link
    is checked the same way and kept, replaced with an existing good capture
    (no save is made), or removed when none exists. A plain backfill of a
    removed source afterwards may save a fresh capture. The live page is
    fetched first so that, as in the ingest, a captured redirect to where it
    ends up still counts as the page. Exits 1 if any source could not be
    archived, could not be checked, or lost its link.
    """
    import httpx

    from common.content_loader import resolve_repo_root
    from common.frontmatter import parse_frontmatter
    from common.timeouts import default_httpx_timeout
    from ingestor.tools.wayback import archive_with_time_limit, check_capture

    root = Path(repo_root) if repo_root else resolve_repo_root()

    def _write(sid: str, path: Path, text: str, archived_url: str | None) -> bool:
        try:
            path.write_text(_set_archived_url(text, archived_url), encoding="utf-8")
        except ValueError as exc:
            click.echo(f"{sid}: not written: {exc}", err=True)
            return False
        return True

    async def _live_end(client, url: str) -> str | None:
        """Where the live page ends up now, or None when it does not load.

        Source files do not record where the ingest's fetch ended, so this
        stands in for it: without it a capture that redirects there, which the
        ingest accepted, would be rejected here.
        """
        try:
            async with client.stream(
                "GET", url, follow_redirects=True, timeout=default_httpx_timeout()
            ) as resp:
                return str(resp.url) if resp.is_success else None
        except (httpx.HTTPError, httpx.InvalidURL):
            return None

    async def _recheck(
        client, sid: str, path: Path, text: str, url: str, old: str, live: str | None
    ) -> bool:
        """Check ``old`` and keep, replace or remove it; False when the source counts as failed."""
        check = await check_capture(client, old, url, also_same_as=live)
        if check.ok:
            click.echo(f"{sid}: unchanged")
            return True
        if check.unverified:
            click.echo(f"{sid}: could not check {old}: {check.reason}", err=True)
            return False
        # No save here: a replacement must already exist on archive.org.
        lookup = await archive_with_time_limit(
            client, url, allow_save=False, also_same_as=live
        )
        if lookup.archived_url:
            if lookup.archived_url == old:
                click.echo(f"{sid}: unchanged")
                return True
            if not _write(sid, path, text, lookup.archived_url):
                return False
            click.echo(f"{sid}: {old} -> {lookup.archived_url}")
            return True
        if not _write(sid, path, text, None):
            return False
        reasons = [check.reason or "capture failed its check"]
        reasons += [e for e in lookup.errors if e not in reasons]
        reason = "; ".join(reasons)
        if lookup.incomplete:
            outcome = (
                "the search for another capture did not finish; "
                f"rerun `dr wayback-backfill {sid}` later"
            )
        else:
            outcome = "no other 200 capture found"
        click.echo(f"{sid}: removed {old}: {reason}; {outcome}", err=True)
        return False

    async def _run() -> int:
        failed = 0
        async with httpx.AsyncClient() as client:
            for sid in source_ids:
                path = root / "research" / "sources" / f"{sid}.md"
                if not path.is_file():
                    click.echo(f"{sid}: not found ({path})", err=True)
                    failed += 1
                    continue
                text = path.read_text(encoding="utf-8")
                fm, _body = parse_frontmatter(text)
                if fm.get("archived_url") and not recheck:
                    click.echo(f"{sid}: already has archived_url, skipped")
                    continue
                if not fm.get("url"):
                    click.echo(f"{sid}: no url in frontmatter", err=True)
                    failed += 1
                    continue
                url = str(fm["url"])
                live = await _live_end(client, url)
                if fm.get("archived_url"):
                    old = str(fm["archived_url"])
                    if not await _recheck(client, sid, path, text, url, old, live):
                        failed += 1
                    continue
                # No freshness limit: only the ingest refreshes a stale capture.
                lookup = await archive_with_time_limit(client, url, also_same_as=live)
                if not lookup.archived_url:
                    reason = "; ".join(lookup.errors) or "no archive.org snapshot"
                    click.echo(f"{sid}: archive lookup failed: {reason}", err=True)
                    failed += 1
                    continue
                if not _write(sid, path, text, lookup.archived_url):
                    failed += 1
                    continue
                click.echo(f"{sid}: {lookup.archived_url}")
        return 1 if failed else 0

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
    overwrite the claim file on disk. A claim that is not a draft (published,
    archived or blocked) returns to draft and awaits re-approval, as with
    ``dr draft --claim --force``. The analyst assesses the claim's stored
    ``statement`` (``title`` for a claim written before it existed), and
    --write writes that sentence as both. The sidecar's Evaluator comparison (``audit``) is cleared,
    since it graded the old analysis; run ``dr step-audit --write`` after.

    Example:
        dr step-analyze --claim microsoft/corporate-structure
        dr step-analyze --claim microsoft/corporate-structure --write --force
    """
    logger.info("dr step-analyze: claim=%s do_write=%s force=%s", claim_ref, do_write, force)

    analyst_model = ctx.obj.get("analyst_model") or ctx.obj["model"]
    _check_provider_api_keys(analyst_model)

    import datetime

    from common.content_loader import load_entity, resolve_repo_root
    from common.frontmatter import claim_statement, parse_frontmatter
    from common.models import ClaimStatus
    from loop import ClaimSpec, VerifyConfig, rerun
    from orchestrator.entity_resolution import parse_entity_ref
    from orchestrator.persistence import (
        _write_claim_file,
        clear_audit,
        load_source_dict,
        mark_forced_rewrite,
        verdict_write_kwargs,
    )

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
    # With the resolved entity the analyst sees the entity-match labels, and
    # --write keeps their overrides, as dr draft does. The loop runs on a
    # resolved entity, so a missing entity file is a usage error.
    try:
        resolved_entity = parse_entity_ref(fm["entity"], root)
    except ValueError as exc:
        raise click.UsageError(f"could not load entity '{fm['entity']}': {exc}") from exc

    claim_text = claim_statement(fm)
    template = _claim_template(fm, root)

    # Load sources
    # Same shape the main pipeline gives the analyst: ``source_id`` lets
    # year/slug citation tokens resolve, ``independence`` feeds the prompt.
    source_dicts: list[dict] = []
    for sid in fm.get("sources") or []:
        sd = load_source_dict(sid, root)
        if sd is None:
            click.echo(f"Warning: source '{sid}' not found, skipping", err=True)
            continue
        source_dicts.append(sd)

    cfg = VerifyConfig(model=ctx.obj["model"], repo_root=str(root), **_ctx_per_agent_kwargs(ctx))

    spec = ClaimSpec(
        statement=claim_text,
        entity=resolved_entity,
        criteria_slug=fm.get("criteria_slug"),
        grading_rule=template.grading_rule or None if template else None,
    )
    rerun_result = asyncio.run(rerun(spec, cfg, source_dicts, agent="analyst"))
    analyst_out, analyst_failure = rerun_result.analyst_output, rerun_result.failure
    _record_finding(
        rerun_result.finding, root, command="dr step-analyze",
        dry_run=not (do_write or force), claim_ref=_claim_ref(claim_path, root),
    )

    if analyst_out is None:
        if analyst_failure is not None:
            click.echo(
                f"Error: analyst agent failed: {analyst_failure.error_class}: "
                f"{analyst_failure.error_message} "
                f"(model={analyst_failure.model}, timeout_s={analyst_failure.timeout_s})",
                err=True,
            )
        else:
            click.echo("Error: analyst agent failed to produce output.", err=True)
        sys.exit(1)

    # The loop fitted the level to the stored sources, so the printed level
    # is the one --write writes.
    source_ids = fm.get("sources") or []
    level_clamp = rerun_result.level_clamp

    # Always print the result
    a = analyst_out
    click.echo(f"Entity:     {a.entity.entity_name} ({a.entity.entity_type})")
    click.echo(f"Title:      {a.verdict.title}")
    click.echo(f"Topics:     {', '.join(t.value for t in a.verdict.topics)}")
    click.echo(f"Verdict:    {a.verdict.verdict.value}")
    click.echo(f"Confidence: {a.verdict.confidence.value}")
    click.echo(f"Level:      {a.verdict.verification_level.value}")
    if level_clamp:
        click.echo(f"Level fit:  {level_clamp}")
    click.echo(f"Narrative:")
    for line in a.verdict.narrative.strip().split("\n"):
        click.echo(f"  {line}")

    if not (do_write or force):
        return

    # Write claim file
    entity_ref = fm["entity"]
    claim_slug = claim_path.stem

    # Without --force the write below refuses, so nothing is reset.
    status = fm.get("status", "draft")
    if force:
        if mark_forced_rewrite(
            claim_path, source_ids, datetime.datetime.now(tz=datetime.timezone.utc),
        ):
            status = ClaimStatus.DRAFT
        clear_audit(claim_path)

    try:
        written_path = _write_claim_file(
            title=claim_text,
            statement=claim_text,
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
            status=status,
            criteria_slug=fm.get("criteria_slug"),
            seo_title=a.verdict.seo_title,
            takeaway=a.verdict.takeaway,
            uncited_by_title=rerun_result.uncited_by_title,
            **verdict_write_kwargs(a.verdict),
        )
        click.echo(f"Wrote {written_path}")
    except FileExistsError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# --------------------------------------------------------------------------- #
# Run report, shared by dr draft --dry-run                                      #
# --------------------------------------------------------------------------- #

def _print_verify_result(result) -> None:
    hr()
    click.echo("Claim Verification Report")
    hr()
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
        if result.level_clamp:
            click.echo(f"  Level fit:  {result.level_clamp}")
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
        if c.tiebreaker_verdict is not None:
            click.echo(f"  Tie-breaker:      {c.tiebreaker_verdict.value} ({c.tiebreaker_confidence.value})")
        if c.pipeline_verdict is not None:
            click.echo(f"  Pipeline verdict: {c.pipeline_verdict.value} ({c.rule_applied})")
        click.echo(f"  Reasoning:")
        for line in c.reasoning.strip().split("\n"):
            click.echo(f"    {line}")
        if c.evidence_gaps:
            click.echo(f"  Evidence gaps:")
            for gap in c.evidence_gaps:
                click.echo(f"    - {gap}")
        click.echo("")

    if result.restatement is not None or (result.finding is not None and result.finding.step == "restate"):
        _print_restatement(result)
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

    hr()


# --------------------------------------------------------------------------- #
# dr draft                                                                      #
# --------------------------------------------------------------------------- #

@main.command("draft")
@click.argument("sentence", required=False)
@click.option("--entity", "entity_ref", default=None, metavar="REF", help="Entity the sentence is about, as a type/slug ref naming an entity file (e.g. products/chatgpt)")
@click.option("--subject", "subject_slug", default=None, metavar="SLUG", help="Subject the sentence is about; the subject record is written with the claim when none exists")
@click.option("--criterion", "criterion_slug", default=None, metavar="SLUG", help="Draft the criterion's sentence for --entity, or attach it to --claim")
@click.option("--claim", "claim_ref", default=None, metavar="REF", help="Re-run the claim's stored statement in place (needs --force or --dry-run), or attach a criterion with --criterion")
@click.option("--dry-run", is_flag=True, help="Run the loop and print the result; write nothing and never ask archive.org to capture a page")
@click.option("--force", is_flag=True, help="Overwrite the claim file if present; a claim that is not a draft returns to draft and awaits re-approval")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.option("--max-sources", default=None, type=int, help="Target number of successful sources to pass to the analyst (default: VerifyConfig.max_sources)")
@click.option("--candidate-pool-size", default=None, type=int, help="Max URLs to attempt before stopping (default: VerifyConfig.candidate_pool_size)")
@click.option("--skip-wayback/--wayback", default=False, help="Skip Wayback Machine")
@click.option("--max-initial-queries", default=None, type=click.IntRange(min=1), help="Max search queries for decomposed researcher, at least 1 (default: VerifyConfig.max_initial_queries)")
@click.option("--llm-concurrency", default=None, type=int, help="Max concurrent LLM calls (default: VerifyConfig.llm_concurrency)")
@click.option("--restates", "restates_ref", default=None, metavar="REF", help="Run candidate --pick N from the claim's restatement block as a new claim linked back with restates:")
@click.option("--pick", "pick", default=None, type=click.IntRange(min=1), metavar="N", help="The rank of the restatement candidate to run (with --restates)")
@click.pass_context
def draft(
    ctx: click.Context,
    sentence: str | None,
    entity_ref: str | None,
    subject_slug: str | None,
    criterion_slug: str | None,
    claim_ref: str | None,
    dry_run: bool,
    force: bool,
    repo_root: str | None,
    max_sources: int | None,
    candidate_pool_size: int | None,
    skip_wayback: bool,
    max_initial_queries: int | None,
    llm_concurrency: int | None,
    restates_ref: str | None,
    pick: int | None,
) -> None:
    """Run the loop on one claim and write it as a draft (--dry-run writes nothing).

    Exactly one of --entity, --subject, --claim or --restates names what the
    claim is about. The claim stores the sentence it checks as its statement (and as
    its title). A run abandoned by the error policy writes only its finding
    under research/findings/ and exits 1; a retried or tie-broken run writes
    the claim and its finding. A writer failure leaves a half-claim finding.

    \b
    --entity REF SENTENCE        an ad hoc claim at <entity-dir>/<slugified sentence>.md
    --criterion SLUG --entity REF
                                 the criterion's sentence for the entity, at
                                 <entity-dir>/<SLUG>.md, with criteria_slug and the
                                 criterion's topics
    --subject SLUG SENTENCE      an ad hoc subject claim; writes
                                 research/entities/subjects/SLUG.md with the claim
                                 when it is missing
    --claim REF --force          re-runs the claim's stored statement and writes back
                                 to the same path (--dry-run prints the run instead)
    --claim REF --criterion SLUG attaches a new criterion to a draft: appends it to
                                 research/templates.yaml and sets criteria_slug; no
                                 model call
    --restates REF --pick N      runs candidate N of the claim's restatement block as a
                                 new ad hoc claim about the same entity, writes
                                 restates: REF in its sidecar and records the pick on
                                 the original

    \b
    Examples:
        dr draft --dry-run --entity subjects/generative-ai "Generative AI assistants answer most questions without browsing"
        dr draft --criterion renewable-energy-hosting --entity products/chatgpt
        dr draft --subject us-data-centers "US data centers used more than 4% of US electricity in 2024"
        dr draft --claim chatgpt/renewable-energy-hosting --force
        dr draft --claim subjects/us-data-centers/<stem> --criterion data-centers-electricity-share
        dr draft --restates subjects/us-data-centers/<stem> --pick 2
    """
    import re

    from common.content_loader import resolve_repo_root
    from common.frontmatter import claim_statement, parse_frontmatter
    from common.models import EntityType
    from common.sidecar import sidecar_path_for
    from common.templates import get_template, load_templates, render_statement
    from common.utils import slugify
    from loop import ClaimSpec, VerifyConfig, run
    from orchestrator.entity_resolution import ResolvedEntity, parse_entity_ref
    from orchestrator.persistence import planned_claim_path, record_restatement_pick, write_claim_run

    logger.info(
        "dr draft: entity=%s subject=%s criterion=%s claim=%s restates=%s pick=%s sentence=%s dry_run=%s force=%s",
        entity_ref, subject_slug, criterion_slug, claim_ref, restates_ref, pick, sentence, dry_run, force,
    )

    # Click cannot express this grammar, so it is checked here, before any
    # model call: every failure is a usage error (exit 2) naming the flag.
    modes = [flag for flag, value in (
        ("--entity", entity_ref), ("--subject", subject_slug), ("--claim", claim_ref),
        ("--restates", restates_ref),
    ) if value is not None]
    if pick is not None and restates_ref is None:
        raise click.UsageError("--pick goes with --restates <claim-ref>")
    if not modes:
        raise click.UsageError("one of --entity <ref>, --subject <slug>, --claim <ref> or --restates <ref> is required")
    if len(modes) > 1:
        raise click.UsageError(f"{' and '.join(modes)} cannot be combined; pass exactly one")
    if restates_ref is not None:
        if pick is None:
            raise click.UsageError("--restates needs --pick <n>: the rank of the candidate to run")
        if sentence is not None:
            raise click.UsageError("SENTENCE is not taken with --restates: the candidate's text is the sentence")
        if criterion_slug is not None:
            raise click.UsageError(
                "--criterion is not taken with --restates; attach one to the new claim with "
                "dr draft --claim <new-ref> --criterion <slug>"
            )
    has_sentence = bool(sentence and sentence.strip())
    attach = claim_ref is not None and criterion_slug is not None
    if criterion_slug is not None:
        if subject_slug is not None:
            raise click.UsageError(
                "--criterion goes with --entity (draft the criterion) or --claim (attach it), not --subject"
            )
        if sentence is not None:
            raise click.UsageError("SENTENCE is not taken with --criterion: the criterion's text is the sentence")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", criterion_slug):
            raise click.UsageError(f"--criterion {criterion_slug}: a slug is lowercase words joined by hyphens")
        if attach and (force or dry_run):
            raise click.UsageError("--claim with --criterion runs no loop and writes no claim run; drop --force and --dry-run")
    elif claim_ref is not None:
        if sentence is not None:
            raise click.UsageError("SENTENCE is not taken with --claim: the claim's stored statement is re-run")
        if not (force or dry_run):
            raise click.UsageError(
                f"--claim {claim_ref} writes over the existing claim: pass --force to write it, "
                "--dry-run to print the run, or --criterion <slug> to attach a criterion"
            )
    elif restates_ref is None and not has_sentence:
        raise click.UsageError(f"SENTENCE is required with {modes[0]}")
    if subject_slug is not None and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", subject_slug):
        raise click.UsageError(f"--subject {subject_slug}: a slug is lowercase words joined by hyphens")

    root = Path(repo_root) if repo_root else resolve_repo_root()

    if attach:
        _attach_criterion(claim_ref, criterion_slug, root)
        return

    claim_path: Path | None = None
    create_entity = False
    original_path: Path | None = None
    if restates_ref is not None:
        original_path, candidate_text, original_entity = _restatement_candidate(restates_ref, pick, root)
        ref_label = original_entity
        try:
            resolved_entity = parse_entity_ref(original_entity, root)
        except ValueError as exc:
            click.echo(f"Error: --restates {restates_ref}: could not load entity {original_entity!r}: {exc}", err=True)
            sys.exit(1)
        spec = ClaimSpec(statement=candidate_text, entity=resolved_entity)
        claim_slug = slugify(candidate_text)
        planned = planned_claim_path(resolved_entity.entity_ref, resolved_entity.entity_name, claim_slug, root)
        if planned.resolve() == original_path.resolve():
            raise click.UsageError(
                f"--restates: candidate {pick} would be written over the original claim {restates_ref}; "
                "its text slugifies to the original's file name. Pick another candidate, or rerun the "
                f"original with dr draft --claim {restates_ref} --force"
            )
    elif claim_ref is not None:
        claim_path = _resolve_claim_path(claim_ref, root / "research" / "claims")
        if not claim_path.exists():
            click.echo(f"Error: claim file not found: {claim_ref} ({claim_path})", err=True)
            sys.exit(1)
        fm, _body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
        claim_entity = fm.get("entity", "")
        try:
            resolved_entity = parse_entity_ref(claim_entity, root)
        except ValueError as exc:
            raise click.UsageError(f"--claim {claim_ref}: could not load entity {claim_entity!r}: {exc}") from exc
        template = _claim_template(fm, root)
        spec = ClaimSpec(
            statement=claim_statement(fm),
            entity=resolved_entity,
            criteria_slug=fm.get("criteria_slug"),
            topics=list(template.topics) if template else [],
            grading_rule=template.grading_rule or None if template else None,
        )
        claim_slug = claim_path.stem
        force = True
        ref_label = claim_ref
    elif subject_slug is not None:
        ref_label = f"subjects/{subject_slug}"
        if (root / "research" / "entities" / f"{ref_label}.md").exists():
            try:
                resolved_entity = parse_entity_ref(ref_label, root)
            except ValueError as exc:
                raise click.UsageError(f"--subject {subject_slug}: {exc}") from exc
        else:
            # A minimal record, written with the claim; the operator edits it afterwards.
            resolved_entity = ResolvedEntity(
                entity_ref=ref_label,
                entity_name=subject_slug.replace("-", " ").title(),
                entity_type=EntityType.SUBJECT,
                entity_description=sentence.strip(),
            )
            create_entity = True
        spec = ClaimSpec(statement=sentence, entity=resolved_entity)
        claim_slug = slugify(sentence)
    else:
        ref_label = entity_ref
        try:
            resolved_entity = parse_entity_ref(entity_ref, root)
        except ValueError as exc:
            raise click.UsageError(f"--entity {entity_ref}: {exc}") from exc
        if criterion_slug is not None:
            try:
                template = get_template(load_templates(root), criterion_slug)
            except Exception as exc:
                raise click.UsageError(f"--criterion {criterion_slug}: could not read research/templates.yaml: {exc}") from exc
            if template is None:
                raise click.UsageError(
                    f"--criterion {criterion_slug}: no active criterion with that slug in research/templates.yaml"
                )
            entity_type = resolved_entity.entity_type.value
            if template.entity_type != entity_type:
                raise click.UsageError(
                    f"--criterion {criterion_slug} is a {template.entity_type} criterion; "
                    f"{entity_ref} is a {entity_type}"
                )
            if template.entity_type == "subject" and resolved_entity.entity_ref not in template.subjects:
                raise click.UsageError(
                    f"--criterion {criterion_slug} does not list {entity_ref} in its subjects"
                )
            spec = ClaimSpec(
                statement=render_statement(template, resolved_entity.entity_name),
                entity=resolved_entity,
                criteria_slug=criterion_slug,
                topics=list(template.topics),
                grading_rule=template.grading_rule or None,
            )
            claim_slug = criterion_slug
        else:
            spec = ClaimSpec(statement=sentence, entity=resolved_entity)
            claim_slug = slugify(sentence)

    if not dry_run:
        # Refused before the paid loop; the writer checks the same two things again.
        planned = planned_claim_path(resolved_entity.entity_ref, resolved_entity.entity_name, claim_slug, root)
        if claim_path is not None and planned.resolve() != claim_path.resolve():
            click.echo(
                f"Error: {claim_ref} is at {claim_path}, but its entity {resolved_entity.entity_ref} "
                f"writes to {planned}. Nothing was run.",
                err=True,
            )
            sys.exit(1)
        if not force and planned.exists():
            click.echo(f"Error: claim file already exists: {planned}. Use --force to overwrite it.", err=True)
            sys.exit(1)

    _check_provider_api_keys(_agent_models_from_ctx(ctx))

    overrides = {k: v for k, v in {"max_sources": max_sources, "candidate_pool_size": candidate_pool_size, "max_initial_queries": max_initial_queries, "llm_concurrency": llm_concurrency}.items() if v is not None}
    config = VerifyConfig(
        model=ctx.obj["model"],
        skip_wayback=skip_wayback,
        repo_root=str(root),
        # A dry run writes nothing, so archive lookups check TimeGate only.
        allow_save=not dry_run,
        show_progress=True,
        **overrides,
        **_ctx_per_agent_kwargs(ctx),
    )
    _check_search_key(config)

    click.echo(f"Entity: {resolved_entity.entity_name} ({resolved_entity.entity_type.value})")
    progress("Drafting claim: %s (%s)%s", spec.statement, ref_label, " [dry run]" if dry_run else "")
    result = asyncio.run(run(spec, config))
    existing_ref = _claim_ref(claim_path, root) if claim_path is not None else None

    if dry_run:
        _record_finding(result.finding, root, command="dr draft", dry_run=True)
        _print_verify_result(result)
        return

    if result.finding is not None and result.finding.outcome == "abandoned":
        _record_finding(result.finding, root, command="dr draft", claim_ref=existing_ref)
    if not _report_unwritable_run(result):
        sys.exit(1)

    planned = claim_path or planned_claim_path(
        resolved_entity.entity_ref, resolved_entity.entity_name, claim_slug, root,
    )
    try:
        written_path = write_claim_run(
            result, spec, config,
            repo_root=root,
            claim_slug=claim_slug,
            force=force,
            # --claim writes back to the file it read, whatever its stem.
            target=claim_path,
            create_entity=create_entity,
            restates=_claim_ref(original_path, root) if original_path is not None else None,
        )
    except FileExistsError as exc:
        click.echo(f"Error: {exc}. Use --force to overwrite it.", err=True)
        sys.exit(1)
    except Exception as exc:
        # Nothing is deleted: a claim without its sidecar, or a subject record
        # without its claim, is listed by dr findings.
        click.echo(f"Error: the claim was not written: {exc}", err=True)
        _record_half_claim(result, spec, config, root, _claim_ref(planned, root), exc)
        sys.exit(1)

    try:
        claim_rel = written_path.relative_to(root)
    except ValueError:
        claim_rel = written_path
    if result.finding is not None:
        _record_finding(result.finding, root, command="dr draft", claim_ref=_claim_ref(written_path, root))

    hr()
    click.echo("Draft Report")
    hr()
    click.echo(f"Entity:  {result.entity}")
    click.echo(f"Claim:   {result.claim_text}")
    click.echo(f"URLs found: {len(result.urls_found)} | ingested: {len(result.urls_ingested)} | failed: {len(result.urls_failed)}")
    click.echo("")

    a = result.analyst_output
    click.echo(f"Verdict:    {a.verdict.verdict.value} ({a.verdict.confidence.value})")
    c = result.consistency
    if c is not None and c.tiebreaker_verdict is not None and c.pipeline_verdict is not None:
        click.echo(
            f"Settled:    {c.pipeline_verdict.value} ({c.rule_applied}; analyst {c.primary_verdict.value}, "
            f"Evaluator {c.assessed_verdict.value}, tie-breaker {c.tiebreaker_verdict.value})"
        )
    _print_restatement(result)
    click.echo(f"Analyst title: {a.verdict.title}")
    click.echo(f"Entity:     {a.entity.entity_name} ({a.entity.entity_type})")
    click.echo("")
    click.echo(f"Claim:   {claim_rel}")
    click.echo(f"Audit:   {sidecar_path_for(Path(claim_rel))}")
    if result.errors:
        click.echo("Errors:")
        for e in result.errors:
            click.echo(f"  ! {e}")
    hr()
    if claim_path is not None:
        click.echo(f"Refreshed: {written_path}")
        if result.consistency and result.consistency.needs_review:
            from auditor.compare import needs_review_reasons

            reasons = ", ".join(needs_review_reasons(result.consistency))
            click.echo(f"Note: flagged for human review ({reasons}).")
    if original_path is not None:
        # Recorded only once the new claim is written: a dry run, an abandoned
        # run or a refused write leaves the original's sidecar untouched.
        try:
            record_restatement_pick(original_path, pick)
        except ValueError as exc:
            click.echo(f"Warning: the pick was not recorded on {restates_ref}: {exc}", err=True)
        # Printed as the sidecar key it wrote.
        click.echo(f"restates: {_claim_ref(original_path, root)} (candidate {pick})")


def _restatement_candidate(restates_ref: str, pick: int, root: Path) -> tuple[Path, str, str]:
    """The original claim's path, candidate ``pick``'s text and the original's entity ref.

    Exits 1 when the claim, its ``restatement`` block or the candidate is missing.
    """
    from common.frontmatter import parse_frontmatter
    from common.sidecar import read_sidecar

    def refuse(message: str):
        click.echo(f"Error: {message}", err=True)
        sys.exit(1)

    claims_root = root / "research" / "claims"
    original = _resolve_claim_path(restates_ref, claims_root)
    if not original.exists():
        refuse(f"claim file not found: {restates_ref} ({original})")
    fm, _body = parse_frontmatter(original.read_text(encoding="utf-8"))
    sidecar = read_sidecar(original) or {}
    block = sidecar.get("restatement")
    if not isinstance(block, dict):
        refuse(
            f"no restatement block in {original.with_suffix('.audit.yaml')}; nothing to pick "
            "(approving or archiving a claim with no recorded pick removes the block)"
        )
    candidates = [c for c in block.get("candidates") or [] if isinstance(c, dict)]
    chosen = next((c for c in candidates if c.get("rank") == pick), None)
    if chosen is None or not str(chosen.get("text") or "").strip():
        refuse(f"no candidate {pick} in the restatement block of {restates_ref}; it has {len(candidates)}")
    return original, str(chosen["text"]).strip(), str(fm.get("entity") or "")


def _print_restatement(result) -> None:
    """The run's restatement candidates, or why there are none when the restater failed."""
    block = result.restatement
    finding = result.finding
    if block is not None:
        candidates = block.get("candidates") or []
        click.echo(f"Restatement: {len(candidates)} candidates ({block.get('trigger')})")
        for c in candidates:
            click.echo(
                f"  #{c['rank']} decisiveness {c['decisiveness']}/4 expected: "
                f"{c['expected_verdict']} ({c['expected_confidence']})  \"{c['text']}\""
            )
    elif finding is not None and finding.step == "restate" and finding.outcome == "partial":
        click.echo(f"Restatement: unavailable (finding {finding.run_id})")


def _attach_criterion(claim_ref: str, slug: str, root: Path) -> None:
    """``dr draft --claim <ref> --criterion <slug>``: attach a new criterion to a draft claim.

    Appends the criterion built from the claim's stored statement to
    ``research/templates.yaml`` and writes ``criteria_slug`` into the claim.
    Runs no loop and calls no model. Each refusal exits 1 and changes nothing.
    """
    from common.frontmatter import claim_statement, parse_frontmatter
    from common.templates import criterion_entry_for
    from orchestrator.entity_resolution import parse_entity_ref
    from orchestrator.persistence import append_template_entry, set_claim_criterion

    def refuse(message: str) -> None:
        click.echo(f"Error: {message}", err=True)
        sys.exit(1)

    claim_path = _resolve_claim_path(claim_ref, root / "research" / "claims")
    if not claim_path.exists():
        refuse(f"claim file not found: {claim_ref} ({claim_path})")
    fm, _body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    if fm.get("criteria_slug"):
        refuse(f"{claim_ref} already has criteria_slug {fm['criteria_slug']!r}; nothing to attach")
    status = fm.get("status", "draft")
    if status != "draft":
        refuse(f"{claim_ref} is {status}, not a draft; a criterion is attached before sign-off")
    claim_entity = fm.get("entity", "")
    if claim_entity.startswith("companies/"):
        refuse(f"{claim_ref} is about a company ({claim_entity}); claims are drafted for products and subjects")
    try:
        resolved = parse_entity_ref(claim_entity, root)
    except ValueError as exc:
        refuse(f"{claim_ref}: could not load entity {claim_entity!r}: {exc}")
    entry = criterion_entry_for(claim_statement(fm), resolved, slug, list(fm.get("topics") or []))
    # The claim is written first and restored if the registry write fails, so no
    # failure leaves a registry entry that no claim carries.
    claim_before = claim_path.read_bytes()
    try:
        set_claim_criterion(claim_path, slug)
        append_template_entry(root, entry)
    except (ValueError, OSError) as exc:
        claim_path.write_bytes(claim_before)
        refuse(str(exc))
    click.echo(f"Criterion {slug}: {entry['text']}")
    click.echo(f"Attached to {claim_path}")


def _claim_ref(claim_path: Path, root: Path) -> str:
    """The ``dr`` claim ref for a claim path: its path under research/claims/ without ``.md``."""
    try:
        return claim_path.relative_to(root / "research" / "claims").with_suffix("").as_posix()
    except ValueError:
        return claim_path.with_suffix("").as_posix()


def _record_finding(finding, root: Path, *, command: str, dry_run: bool = False, claim_ref: str | None = None) -> None:
    """Print the run's finding in one line and write it under research/findings/ (never on a dry run)."""
    from orchestrator.persistence import write_finding

    if finding is None:
        return
    if claim_ref is not None:
        finding.claim_ref = claim_ref
    if finding.command is None:
        finding.command = command
    click.echo(finding.summary_line(), err=True)
    if dry_run:
        return
    try:
        path = write_finding(finding, root, command=command)
    except OSError as exc:
        click.echo(f"Error: the finding was not written: {exc}", err=True)
        return
    click.echo(f"Finding: {path}", err=True)


def _record_half_claim(result, spec, config, root: Path, claim_ref: str, exc: BaseException) -> None:
    """Write the finding for a writer that failed part-way (rule half-claim)."""
    import datetime

    from common.findings import Finding, claim_spec_record, config_record

    earlier = result.finding
    agents = ["researcher", "ingestor", "analyst", "auditor"]
    if result.consistency is not None and result.consistency.tiebreaker_verdict is not None:
        agents.append("tiebreaker")
    if result.restatement is not None or (earlier is not None and earlier.step == "restate"):
        agents.append("restater")
    retries = list(earlier.retries) if earlier is not None else []
    if earlier is not None and earlier.outcome in ("recovered", "split", "partial"):
        entry = {"step": earlier.step, "error_type": earlier.error.get("error_type"),
                 "rule": earlier.rule, "attempts": earlier.attempts}
        if earlier.outcome == "split":
            # The sidecar that would hold the three verdicts was not written.
            entry["message"] = earlier.error.get("message")
        retries.append(entry)
    finding = Finding(
        run_id=config.run_id,
        date=datetime.date.today(),
        claim_spec=claim_spec_record(spec),
        claim_ref=claim_ref,
        config=config_record(config),
        models_used={a: config.model_for(a) for a in agents},
        step="write",
        rule="half-claim",
        error={"error_type": "write_failed", "message": str(exc) or type(exc).__name__,
               "error_class": type(exc).__name__},
        attempts=1,
        outcome="half-claim",
        retries=retries,
    )
    _record_finding(finding, root, command="dr draft")


def _report_unwritable_run(result) -> bool:
    """Print why a run cannot be written and return False, or return True.

    A run the error policy abandoned, a blocked run and a run whose analyst
    failed write nothing: no placeholder claim and no source file.
    """
    from common.models import BlockedReason
    from loop import blocked_reason_label

    for err in result.errors:
        click.echo(f"Warning: {err}", err=True)
    if result.blocked_reason is not None:
        label = blocked_reason_label(result.blocked_reason.value, result.errors, failure=result.failure)
        click.echo(f"Blocked ({result.blocked_reason.value}): {label}. Nothing was written.", err=True)
        return False
    finding = result.finding
    if finding is not None and finding.outcome == "abandoned":
        click.echo(
            f"Abandoned at the {finding.step} step ({finding.error.get('error_type')}). Nothing was written.",
            err=True,
        )
        return False
    if result.analyst_output is None:
        failure = result.failure
        if failure is not None:
            click.echo(
                f"Error: analyst agent failed: {failure.error_class}: {failure.error_message} "
                f"(model={failure.model}, timeout_s={failure.timeout_s}). Nothing was written.",
                err=True,
            )
        else:
            label = blocked_reason_label(BlockedReason.ANALYST_ERROR.value, result.errors)
            click.echo(f"Error: analyst agent failed ({label}). Nothing was written.", err=True)
        return False
    return True


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

    A verdict disagreement goes to the tie-breaker, as in dr draft. Default:
    read-only (prints report and any finding). Use --write to update
    .audit.yaml sidecars and write findings under research/findings/; an
    abandoned rerun writes only its finding.

    Example:
        dr step-audit --entity ecosia
        dr step-audit --claim ecosia/renewable-energy-hosting
        dr step-audit --claim ecosia/renewable-energy-hosting --write
    """
    logger.info(
        "dr step-audit: claim=%s entity=%s topic=%s dry_run=%s do_write=%s",
        claim, entity, topic, dry_run, do_write,
    )
    import dataclasses

    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment
    from auditor.report import format_json_report, format_text_report
    from common.content_loader import list_claims, load_entity, resolve_repo_root
    from common.frontmatter import claim_statement, parse_frontmatter
    from common.models import Category, Confidence, Verdict, VerificationLevel
    from common.sidecar import sidecar_path_for
    from loop import ClaimSpec, VerifyConfig, rerun
    from orchestrator.entity_resolution import parse_entity_ref
    from orchestrator.persistence import load_source_dict, write_evaluator_rerun

    # The tie-breaker runs when the Evaluator disagrees with the claim.
    _check_provider_api_keys([
        ctx.obj.get("auditor_model") or ctx.obj["model"],
        ctx.obj.get("tiebreaker_model") or ctx.obj["model"],
    ])
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

    cfg = VerifyConfig(model=ctx.obj["model"], repo_root=str(root), **_ctx_per_agent_kwargs(ctx))

    async def _run():
        results = []
        for path in claim_paths:
            text = path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)

            claim_id = str(path.relative_to(claims_dir).with_suffix(""))
            # A blocked claim's title keeps the raw vocabulary placeholder and
            # its body is the block notice: there is no claim to grade.
            if fm.get("status") == "blocked":
                click.echo(f"Skipped (blocked): {claim_id}", err=True)
                continue

            entity_fm, _ = load_entity(fm["entity"], root)
            sources = []
            for sid in fm.get("sources", []):
                sd = load_source_dict(sid, root)
                if sd is None:
                    click.echo(f"Warning: source '{sid}' not found", err=True)
                    continue
                sources.append(sd)

            if dry_run:
                click.echo(f"[dry-run] Would audit: {claim_id}")
                continue

            # The claim file is the analysis the Evaluator grades. Built
            # without validation: a claim written before seo_title existed
            # does not validate as a VerdictAssessment.
            level = fm.get("verification_level")
            analysis = AnalystOutput.model_construct(
                entity=EntityResolution(
                    entity_name=entity_fm["name"],
                    entity_type=entity_fm["type"],
                    entity_description=entity_fm["description"],
                ),
                verdict=VerdictAssessment.model_construct(
                    title=fm["title"],
                    verdict=Verdict(fm["verdict"]),
                    confidence=Confidence(fm["confidence"]),
                    narrative=body,
                    topics=[Category(t) for t in fm["topics"]],
                    verification_level=VerificationLevel(level) if level else None,
                    seo_title=fm.get("seo_title") or "",
                    takeaway=fm.get("takeaway"),
                    cap_rationale=fm.get("cap_rationale"),
                    source_overrides=None,
                    cited_sources=[],
                ),
            )
            template = _claim_template(fm, root)
            spec = ClaimSpec(
                statement=claim_statement(fm),
                entity=parse_entity_ref(fm["entity"], root),
                criteria_slug=fm.get("criteria_slug"),
                grading_rule=template.grading_rule or None if template else None,
            )

            progress("Auditing: %s ...", claim_id)
            # One run id per claim, so each claim's finding is its own record.
            claim_cfg = cfg if len(claim_paths) == 1 else dataclasses.replace(cfg, run_id=new_run_id())
            graded = await rerun(spec, claim_cfg, sources, agent="evaluator", analyst_output=analysis)
            _record_finding(
                graded.finding, root, command="dr step-audit",
                dry_run=not do_write, claim_ref=_claim_ref(path, root),
            )
            abandoned = graded.finding is not None and graded.finding.outcome == "abandoned"
            if graded.consistency is None or abandoned:
                reason = "; ".join(graded.errors) or "the Evaluator produced no assessment"
                click.echo(f"Skipped (not graded): {claim_id}: {reason}", err=True)
                continue
            result = graded.consistency.model_copy(
                update={"claim_id": claim_id, "claim_file": str(path.relative_to(root))}
            )

            if verbose or result.needs_review:
                click.echo(
                    f"  {result.claim_id}: {result.primary_verdict.value} vs "
                    f"{result.assessed_verdict.value} ({result.verdict_severity.value})",
                    err=True,
                )
            results.append(result)

            settled = graded.consistency.pipeline_verdict
            moved = settled is not None and settled.value != fm.get("verdict")
            if do_write and fm.get("status") == "published" and moved:
                # The sidecar's pipeline verdict would then differ from the
                # published one with no review behind it, which lint rejects.
                # The finding above keeps the split; RE-AW (Recheck) gives
                # this case a pending-draft location.
                click.echo(
                    f"Not written: {claim_id} is published as {fm.get('verdict')} and the "
                    f"pipeline verdict is now {settled.value}; see the finding.",
                    err=True,
                )
            elif do_write:
                write_evaluator_rerun(path, graded, claim_cfg)
                click.echo(f"Wrote {sidecar_path_for(path)}")

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
# dr review                                                                     #
# --------------------------------------------------------------------------- #

_SIGN_OFF_FLAGS = ("--approve", "--archive", "--correction", "--reviewer", "--notes", "--pr-url")


@main.command()
@click.option("--claim", default=None, help="Claim ref: <entity-dir>/<claim-slug> (subjects/<s>/<stem> for a subject), or a bare <claim-slug> if unique. Without --format, records the sign-off.")
@click.option("--reviewer", default=None, help="Reviewer name or email (defaults to git config user.email)")
@click.option("--notes", default=None, help="Optional review notes")
@click.option("--pr-url", default=None, help="Optional GitHub PR URL")
@click.option("--approve", is_flag=True, default=False, help="Flip status from draft to published after sidecar write")
@click.option("--archive", is_flag=True, default=False, help="Flip status from published to archived after sidecar write")
@click.option(
    "--correction", default=None,
    help="One-line public correction, required with --approve when a refresh changed the published verdict.",
)
@click.option(
    "--format", "output_format", default=None, type=click.Choice(["text", "json"]),
    help="Print review packets and exit, writing nothing: the queue's, or the --claim's. `text` is the whole packet; `json` a JSON array.",
)
@click.option("--filter-entity", default=None, help="Restrict the queue to one entity directory (e.g. 'openai').")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def review(
    ctx: click.Context,
    claim: str | None,
    reviewer: str | None,
    notes: str | None,
    pr_url: str | None,
    approve: bool,
    archive: bool,
    correction: str | None,
    output_format: str | None,
    filter_entity: str | None,
    repo_root: str | None,
) -> None:
    """Walk the drafts awaiting sign-off through their review packets; --format prints packets; --claim signs one off.

    \b
    dr review                          the walkthrough: each draft's review packet,
                                       then a key: [a]pprove [d]elete [e]dit fields
                                       [s]kip [p]review [o]pen in editor [r]estate
                                       [v]iew packet [q]uit
    dr review --format text|json       every queued draft's packet; writes nothing
    dr review --claim REF --format text|json
                                       one claim's packet (published too); writes nothing
    dr review --claim REF [--approve|--archive] [--correction TEXT]
                                       records the sign-off in the sidecar; --approve
                                       also flips draft to published, --archive
                                       published to archived

    The packet shows, in this order: the verdict chain (statement, restated
    candidates, analyst, Evaluator, tie-breaker, the pipeline's verdict and
    rule) with the header facts; every key quote beside its page passage and
    the check's result; source independence; the run's queries and the
    scorer's rejected candidates. The walkthrough prints the verdict chain
    last, directly above the key prompt. `r` records a restatement pick and
    prints the `dr draft --restates REF --pick N` command to run afterwards;
    `v` opens the whole packet in $PAGER.

    The walkthrough's `a` and every --claim sign-off need a person at a
    terminal: stdin must be a tty, and the claim slug is typed back before
    anything is written. Agents never run the walkthrough or a sign-off.

    \b
    Examples:
      dr review
      dr review --format json | jq '.[].claim_slug'
      dr review --claim subjects/us-data-centers/<stem> --format text | less
      dr review --claim ecosia/renewable-energy-hosting --approve
    """
    logger.info(
        "dr review: claim=%s approve=%s archive=%s format=%s",
        claim,
        approve,
        archive,
        output_format,
    )

    import json as _json

    from common.content_loader import resolve_repo_root
    from common.sidecar import sidecar_path_for
    from orchestrator.review import approve_claim

    # Click cannot express this grammar: each refusal is a usage error (exit 2)
    # raised before anything is read or written.
    sign_off = [flag for flag, value in zip(
        _SIGN_OFF_FLAGS, (approve, archive, correction, reviewer, notes, pr_url),
    ) if value]
    if claim is None and sign_off:
        raise click.UsageError(f"{sign_off[0]} signs off one claim: pass --claim <ref>")
    if output_format is not None and sign_off:
        raise click.UsageError(f"--format prints packets and writes nothing; it does not take {sign_off[0]}")
    if claim is not None and filter_entity is not None:
        raise click.UsageError("--filter-entity narrows the queue; it does not take --claim")
    if approve and archive:
        raise click.UsageError("--approve and --archive are mutually exclusive")

    root = Path(repo_root) if repo_root else resolve_repo_root()
    claims_dir = root / "research" / "claims"

    if claim is None:
        from orchestrator.packet import build_packet, item_line, render_full
        from orchestrator.review_queue import _partial_restate_runs, find_publication_queue, run_interactive

        items = find_publication_queue(root, filter_entity=filter_entity)
        if output_format is None:
            run_interactive(items, root)
            return
        partial_runs = _partial_restate_runs(root)
        packets = [build_packet(root / item.path, root, partial_restate_runs=partial_runs) for item in items]
        if output_format == "json":
            click.echo(_json.dumps(packets, indent=2, default=str))
            return
        for n, packet in enumerate(packets, 1):
            click.echo(item_line(packet["claim_slug"], n, len(packets)))
            click.echo(render_full(packet))
            click.echo()
        return

    claim_path = _resolve_claim_path(claim, claims_dir)
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

    if output_format is not None:
        from orchestrator.packet import build_packet, render_full

        try:
            packet = build_packet(claim_path, root)
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)
        if output_format == "json":
            click.echo(_json.dumps([packet], indent=2, default=str))
        else:
            click.echo(render_full(packet))
        return

    mode = "approve" if approve else "archive" if archive else "review"
    approve_claim(
        claim_path,
        reviewer=reviewer,
        notes=notes,
        pr_url=pr_url,
        mode=mode,
        correction_summary=correction,
    )

    rel = claim_path.relative_to(claims_dir).with_suffix("").as_posix()
    if approve:
        click.echo(
            f"Marked reviewed and published: research/claims/{rel}.md (+ .audit.yaml)"
        )
    elif archive:
        click.echo(
            f"Marked reviewed and archived: research/claims/{rel}.md (+ .audit.yaml)"
        )
    else:
        click.echo(f"Marked reviewed: research/claims/{rel}.audit.yaml")


# --------------------------------------------------------------------------- #
# Claim refs                                                                    #
# --------------------------------------------------------------------------- #


def _claim_template(fm: dict, root: Path):
    """The template named by the claim's ``criteria_slug``, or None.

    None also covers an unknown slug and an unreadable ``templates.yaml``, so a
    claim-file command degrades to no criterion topics and no grading rule
    instead of failing.
    """
    from common.templates import get_template, load_templates

    criteria_slug = fm.get("criteria_slug")
    if not criteria_slug:
        return None
    try:
        return get_template(load_templates(root), criteria_slug)
    except Exception as exc:
        logger.warning("Could not load templates (no criterion topics and no grading rule for this run): %s", exc)
        return None


def _resolve_claim_path(claim: str, claims_dir: Path) -> Path:
    """Resolve a `--claim` argument to a concrete claim .md path.

    Accepts ``<entity>/<slug>`` (``subjects/<subject>/<slug>`` for a subject
    claim), either with ``.md``, or a bare ``<slug>`` that is unique under
    ``research/claims/`` at any depth. Calls ``sys.exit(1)`` on missing or
    ambiguous slugs.
    """
    bare = claim[:-3] if claim.endswith(".md") else claim
    if "/" in bare:
        return claims_dir / f"{bare}.md"
    matches = sorted(claims_dir.glob(f"**/{bare}.md"))
    if not matches:
        click.echo(
            f"Claim file not found: no research/claims/**/{bare}.md.",
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


# --------------------------------------------------------------------------- #
# dr findings                                                                   #
# --------------------------------------------------------------------------- #


@main.command()
@click.option("--all", "show_all", is_flag=True, default=False, help="Include closed findings and their notes.")
@click.option("--summary", is_flag=True, default=False, help="Count open findings by step, rule and outcome.")
@click.option("--close", "close_id", default=None, metavar="ID", help="Close the finding with this run id (or a unique prefix); needs --note.")
@click.option("--note", default=None, help="Why the finding is closed (with --close).")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
def findings(show_all: bool, summary: bool, close_id: str | None, note: str | None, repo_root: str | None) -> None:
    """List the run findings under research/findings/ and the half-claims a writer crash left.

    A finding records a run the error policy retried, abandoned or settled
    with the tie-breaker. Nothing is deleted: a half-claim is replaced with
    dr draft, or removed by hand.

    \b
    Examples:
        dr findings
        dr findings --summary
        dr findings --close a06d7a7e --note "model variance; replay later"
    """
    from collections import Counter

    from common.content_loader import resolve_repo_root
    from orchestrator.persistence import close_finding, half_claims, load_findings

    if close_id is not None:
        if show_all or summary:
            raise click.UsageError("--close cannot be combined with --all or --summary")
        if not note or not note.strip():
            raise click.UsageError("--close needs --note <why it is closed>")
    elif note is not None:
        raise click.UsageError("--note goes with --close <id>")

    root = Path(repo_root) if repo_root else resolve_repo_root()

    if close_id is not None:
        try:
            path = close_finding(root, close_id, note.strip())
        except KeyError:
            click.echo(f"Error: no finding with id {close_id}", err=True)
            sys.exit(1)
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)
        click.echo(f"Closed {path.stem}: {note.strip()}")
        return

    everything = load_findings(root, include_closed=True)
    open_findings = [f for f in everything if f.closed is None]

    if summary:
        click.echo(f"open: {len(open_findings)}, closed: {len(everything) - len(open_findings)}")
        for label, attr in (("step", "step"), ("rule", "rule"), ("outcome", "outcome")):
            counts = Counter(getattr(f, attr) for f in open_findings)
            pairs = ", ".join(f"{name}: {n}" for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
            click.echo(f"by {label}: {pairs}" if pairs else f"by {label}: none")
        return

    shown = everything if show_all else open_findings
    for f in sorted(shown, key=lambda f: (f.date, f.run_id), reverse=True):
        click.echo(f"{f.date} {f.command or '-'} {f.summary_line()}")
        if f.claim_ref:
            click.echo(f"    claim: {f.claim_ref}")
        if f.closed is not None:
            click.echo(f"    closed {f.closed.get('date')} by {f.closed.get('by')}: {f.closed.get('note')}")

    left = half_claims(root)
    rows = [
        f"{ref}: no sidecar; replace it with dr draft --claim {ref} --force"
        for ref in left["claims_without_sidecar"]
    ] + [
        f"{ref}: subject record with no claim; the next dr draft --subject {ref.split('/', 1)[1]} reuses it"
        for ref in left["subjects_without_claim"]
    ]
    if rows:
        if shown:
            click.echo("")
        click.echo("Half-claims:")
        for row in rows:
            click.echo(f"  {row}")
    if not shown and not rows:
        click.echo("No open findings." if not show_all else "No findings.")


# --------------------------------------------------------------------------- #
# dr stats                                                                      #
# --------------------------------------------------------------------------- #


@main.command()
@click.option(
    "--format", "output_format", default="text", type=click.Choice(["text", "json"]),
    help="Output format. Mirrors `dr lint --format` and `dr review --format`.",
)
@click.option("--repo-root", default=None, type=click.Path(exists=True))
@click.pass_context
def stats(ctx: click.Context, output_format: str, repo_root: str | None) -> None:
    """Aggregate read-only counters from claims and audit sidecars; no LLM, no network.

    Reports four aggregates that back the success-criteria table in
    docs/plans/completed/source-pool-expansion-tier1.md:

    \b
      - wayback_recovery: Path 1 archive_org recovery rate
      - acquisition_origins: per-origin distribution (brave/tavily/arxiv/...)
      - academic_topic_coverage: Path 2 hit-rate on academic-tagged claims
      - verification_levels: analyst-derived source-pool level distribution

    Empty-state safe: a corpus with no `acquisition` blocks (the current
    state) reports zero counts and a null rate rather than crashing.

    \b
    Examples:
      dr stats
      dr stats --format json | jq '.wayback_recovery.rate'
      dr stats --format json | jq '.academic_topic_coverage.rate'
    """
    logger.info("dr stats: format=%s", output_format)

    from common.content_loader import resolve_repo_root as _resolve_root
    from orchestrator.stats import (
        compute_stats,
        format_json_report,
        format_text_report,
    )

    resolved_root = Path(repo_root) if repo_root else _resolve_root()
    aggregates = compute_stats(resolved_root)

    if output_format == "json":
        click.echo(format_json_report(aggregates))
    else:
        click.echo(format_text_report(aggregates))


if __name__ == "__main__":
    main()
