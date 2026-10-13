"""Invoke tasks for dangerousrobot.org.

Usage: inv <task>
Setup: uv tool install invoke  (once, globally)
"""

import json
import shlex
import sys

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
    """Type-check, build, lint, and test -- the pre-push gate."""
    ctx.run("npm run check:types", pty=True)
    build(ctx)
    lint(ctx)
    _test_unit(ctx)


@task
def worker_deploy(ctx):
    """Type-check, test, migrate and deploy the dr-api petition Worker.

    Wrangler lists pending D1 migrations and asks before applying them; they
    change the live signature database and cannot be undone.
    """
    with ctx.cd("workers/api"):
        ctx.run("npm ci", pty=True)
        ctx.run("npm run check:types", pty=True)
        ctx.run("npm test", pty=True)
        ctx.run("npx wrangler d1 migrations apply dr-api --remote", pty=True)
        ctx.run("npx wrangler deploy", pty=True)


# --- Petition email lists (read from D1 with your wrangler login; no public endpoint) ---

_PETITION_LISTS = {
    # Pending confirmation; the daily cleanup deletes these after 7 days.
    "unconfirmed": "signatures WHERE confirmed_at IS NULL",
    # Double opt-in, defined once in migration 0004 and shared with the Worker's cleanup.
    "updates": "update_recipients WHERE 1",
}


def _sql_str(value):
    """A SQL string literal; `wrangler d1 execute` takes no bind values."""
    return "'" + value.replace("'", "''") + "'"


def _d1(ctx, sql, local):
    target = "--local" if local else "--remote"
    with ctx.cd("workers/api"):
        result = ctx.run(f"npx wrangler d1 execute dr-api {target} --json --command {shlex.quote(sql)}", hide=True)
    return json.loads(result.stdout)[0]["results"]


@task(
    help={
        "kind": "unconfirmed (not yet confirmed) or updates (confirmed and asked for updates)",
        "petition": "The petition's slug; required for updates, since each signer opted in to one campaign",
        "local": "Read the local dev database instead of the live one",
    }
)
def petition_emails(ctx, kind, petition="", local=False):
    """Print petition signers' email addresses, one per line, from the live database."""
    if kind not in _PETITION_LISTS:
        raise SystemExit(f"--kind must be one of: {', '.join(_PETITION_LISTS)}")
    if kind == "updates" and not petition:
        raise SystemExit("--petition is required for updates: each signer asked for one campaign's updates")
    sql = f"SELECT DISTINCT email FROM {_PETITION_LISTS[kind]} AND email IS NOT NULL"
    if petition:
        sql += f" AND petition_slug = {_sql_str(petition)}"
    rows = _d1(ctx, sql + " ORDER BY email", local)
    for row in rows:
        print(row["email"])
    print(f"{len(rows)} {kind} address(es)", file=sys.stderr)


@task(help={"email": "The address that asked to stop updates", "local": "Use the local dev database"})
def petition_stop_updates(ctx, email, local=False):
    """Stop campaign updates for an address. The signature stays; a closed petition's cleanup then deletes the address."""
    rows = _d1(
        ctx,
        f"UPDATE signatures SET updates_consent = 0 WHERE email = {_sql_str(email.strip().lower())} AND updates_consent = 1 RETURNING petition_slug",
        local,
    )
    print(f"Updates stopped on {len(rows)} signature(s): {', '.join(r['petition_slug'] for r in rows) or 'none matched'}")


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


# --- Audit namespace: inv audit, inv audit.prune ---


@task(positional=[])
def _audit(ctx, detail=False, output="", json=False, min_severity="info"):
    """Run content integrity checks and print a summary.

    Options:
      --detail              show full per-file output on stdout
      --output FILE         write full per-file detail to FILE
      --json                emit JSON (full detail, implies --detail)
      --min-severity LEVEL  error | warning | info  (default: info)

    Subtasks:
      inv audit.prune            list orphaned source files (dry-run)
      inv audit.prune --apply    delete orphaned sources + empty year dirs
    """
    parts = ["uv run python -m linter"]
    if detail:
        parts.append("--detail")
    if output:
        parts.extend(["--output", output])
    if json:
        parts.append("--json")
    if min_severity != "info":
        parts.extend(["--min-severity", min_severity])
    with ctx.cd("pipeline"):
        ctx.run(" ".join(parts), pty=True, in_stream=False, warn=True)


@task(positional=[])
def _audit_prune(ctx, apply=False):
    """Show orphaned source count by year (dry-run). Pass --apply to delete.

    Dry-run prints a year-bucket summary of source files not cited by any claim.

    Options:
      --apply    delete the files and remove any empty year directories

    Related:
      inv audit                  show full integrity summary
      inv audit --detail         see per-file unreferenced-source warnings
    """
    flags = " --apply" if apply else ""
    with ctx.cd("pipeline"):
        ctx.run(f"uv run python -m linter.prune{flags}", pty=True, in_stream=False, warn=True)


audit_ns = Collection("audit")
audit_ns.add_task(_audit, name="run", default=True)
audit_ns.add_task(_audit_prune, name="prune")


# --- Namespace assembly ---

ns = Collection()
ns.add_task(setup)
ns.add_task(dev)
ns.add_task(build)
ns.add_task(lint)
ns.add_task(check)
ns.add_task(clean)
ns.add_task(worker_deploy)
ns.add_task(petition_emails)
ns.add_task(petition_stop_updates)
ns.add_collection(test_ns)
ns.add_collection(audit_ns)
