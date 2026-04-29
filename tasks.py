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


# in_stream=False disables invoke's stdin capture; works around a Python 3.14
# fcntl.ioctl buffer overflow that fires after pytest exits.

@task
def _test_unit(ctx):
    """Run pipeline unit tests (excludes acceptance).

    Subtasks:
      inv test           (= inv test.unit)  unit tests only
      inv test.all                          unit + acceptance
      inv test.acceptance                   acceptance only (live APIs)
        -k <substring>   filter by test name (pytest substring match)
        --log            stream pipeline log output live
    """
    with ctx.cd("pipeline"):
        ctx.run(
            "uv run python -m pytest -m 'not acceptance'",
            pty=True,
            in_stream=False,
        )


@task
def _test_all(ctx):
    """Run all pipeline tests including acceptance (needs ANTHROPIC_API_KEY)."""
    with ctx.cd("pipeline"):
        ctx.run("uv run python -m pytest", pty=True, in_stream=False)


@task(positional=[])
def _test_acceptance(ctx, k="", log=False):
    """Run only acceptance tests (live APIs; needs ANTHROPIC_API_KEY + BRAVE_WEB_SEARCH_API_KEY).

    -k does pytest substring matching on test names, e.g.:
      inv test.acceptance -k smoke        # matches test_full_pipeline_false_claim_smoke
      inv test.acceptance -k scorer       # matches test_scorer_obvious_split
    --log streams pipeline log output live (uses --log-cli-level=INFO).
    """
    extra = ""
    if k:
        extra += f" -k {k!r}"
    if log:
        extra += " --log-cli-level=INFO"
    with ctx.cd("pipeline"):
        ctx.run(
            f"uv run python -m pytest -m acceptance{extra}",
            pty=True,
            in_stream=False,
        )


test_ns = Collection("test")
test_ns.add_task(_test_unit, name="unit", default=True)
test_ns.add_task(_test_all, name="all")
test_ns.add_task(_test_acceptance, name="acceptance")


# --- Namespace assembly ---

ns = Collection()
ns.add_task(setup)
ns.add_task(dev)
ns.add_task(build)
ns.add_task(lint)
ns.add_task(check)
ns.add_task(clean)
ns.add_collection(test_ns)
