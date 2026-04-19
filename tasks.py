"""Invoke tasks for dangerousrobot.org.

Usage: inv <task>
Setup: uv tool install invoke  (once, globally)
"""

import shlex

from invoke import Collection, task

PIPELINE = "pipeline"


def _uv_pipeline(cmd):
    """Build a uv command targeting the pipeline project."""
    return f"uv run --directory {PIPELINE} {cmd}"


# --- Root tasks ---


@task
def setup(ctx):
    """Install Node and Python dependencies."""
    ctx.run("npm ci")
    ctx.run(f"uv sync --directory {PIPELINE} --dev")


@task
def dev(ctx):
    """Start the Astro dev server."""
    ctx.run("npm run dev", pty=True)


@task
def build(ctx):
    """Build the Astro site to dist/."""
    ctx.run("npm run build", pty=True)


@task
def lint(ctx):
    """Lint research Markdown and check citations."""
    ctx.run("npm run lint:md", pty=True)
    ctx.run("npm run check:citations", pty=True)


@task
def check(ctx):
    """Build, lint, and test -- the pre-push gate."""
    build(ctx)
    lint(ctx)
    _test_unit(ctx)


@task
def clean(ctx):
    """Remove build artifacts and caches."""
    ctx.run("rm -rf dist .astro", warn=True)
    ctx.run(
        "find pipeline -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null",
        warn=True,
    )


# --- Test namespace: inv test, inv test.all ---


@task
def _test_unit(ctx):
    """Run pipeline unit tests (excludes acceptance)."""
    ctx.run(_uv_pipeline("pytest -m 'not acceptance'"), pty=True)


@task
def _test_all(ctx):
    """Run all pipeline tests including acceptance (needs ANTHROPIC_API_KEY)."""
    ctx.run(_uv_pipeline("pytest"), pty=True)


test_ns = Collection("test")
test_ns.add_task(_test_unit, name="unit", default=True)
test_ns.add_task(_test_all, name="all")


# --- Pipeline CLI wrappers ---


@task(
    positional=["url"],
    help={
        "url": "URL to ingest",
        "dry_run": "Print output without writing file",
        "skip_wayback": "Skip Wayback Machine lookup",
    },
)
def ingest(ctx, url, dry_run=False, skip_wayback=False):
    """Ingest a URL into a research source file."""
    cmd = f"ingest {shlex.quote(url)}"
    if dry_run:
        cmd += " --dry-run"
    if skip_wayback:
        cmd += " --skip-wayback"
    ctx.run(_uv_pipeline(cmd), pty=True)


@task(
    help={
        "claim": "Check one claim (path relative to research/claims/)",
        "entity": "Check all claims for an entity slug",
        "fmt": "Output format: text (default) or json",
        "dry_run": "List claims without calling the LLM",
    },
)
def consistency(ctx, claim=None, entity=None, fmt="text", dry_run=False):
    """Run narrative-verdict consistency check on claims."""
    cmd = "consistency-check"
    if claim:
        cmd += f" --claim {shlex.quote(claim)}"
    if entity:
        cmd += f" --entity {shlex.quote(entity)}"
    if fmt != "text":
        cmd += f" --format {shlex.quote(fmt)}"
    if dry_run:
        cmd += " --dry-run"
    ctx.run(_uv_pipeline(cmd), pty=True)


@task(
    positional=["entity", "claim_text"],
    help={
        "entity": "Entity name, e.g. 'Ecosia'",
        "claim_text": "Claim statement to verify",
        "max_sources": "Max sources to ingest (default 4)",
    },
)
def verify(ctx, entity, claim_text, max_sources=4):
    """Verify a claim about an entity via web research."""
    cmd = f"verify-claim {shlex.quote(entity)} {shlex.quote(claim_text)}"
    if int(max_sources) != 4:
        cmd += f" --max-sources {int(max_sources)}"
    ctx.run(_uv_pipeline(cmd), pty=True)


# --- Namespace assembly ---

ns = Collection()
ns.add_task(setup)
ns.add_task(dev)
ns.add_task(build)
ns.add_task(lint)
ns.add_task(check)
ns.add_task(clean)
ns.add_task(ingest)
ns.add_task(consistency)
ns.add_task(verify)
ns.add_collection(test_ns)
