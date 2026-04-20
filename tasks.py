"""Invoke tasks for dangerousrobot.org.

Usage: inv <task>
Setup: uv tool install invoke  (once, globally)
"""

from invoke import Collection, task


# --- Root tasks ---


@task
def setup(ctx):
    """Install Node and Python dependencies."""
    ctx.run("npm ci")
    ctx.run("uv sync --dev")


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
    with ctx.cd("pipeline"):
        ctx.run("uv run python -m pytest -m 'not acceptance'", pty=True)


@task
def _test_all(ctx):
    """Run all pipeline tests including acceptance (needs ANTHROPIC_API_KEY)."""
    with ctx.cd("pipeline"):
        ctx.run("uv run python -m pytest", pty=True)


test_ns = Collection("test")
test_ns.add_task(_test_unit, name="unit", default=True)
test_ns.add_task(_test_all, name="all")


# --- Namespace assembly ---

ns = Collection()
ns.add_task(setup)
ns.add_task(dev)
ns.add_task(build)
ns.add_task(lint)
ns.add_task(check)
ns.add_task(clean)
ns.add_collection(test_ns)
