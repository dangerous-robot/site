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
    ctx.run("npm run test:site", pty=True)
    build(ctx)
    ctx.run("npm run check:watch", pty=True)
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


_SIGNATURE_COLUMNS = "id, name, email, display_consent, updates_consent, created_at, confirmed_at"


def _column_widths(columns, cells):
    return [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(columns)]


def _print_table(columns, cells, widths=None):
    widths = widths or _column_widths(columns, cells)
    for line in [columns, *cells]:
        print("  ".join(v.ljust(w) for v, w in zip(line, widths)).rstrip())


def _print_signatures(rows, none_message):
    if not rows:
        print(none_message)
        return
    _print_table(list(rows[0]), [["" if v is None else str(v) for v in row.values()] for row in rows])
    print(f"{len(rows)} signature(s); display_consent 1 = name may be shown publicly", file=sys.stderr)


@task(
    help={
        "petition": "The petition's slug",
        "names": "Comma-separated names or surnames to look up; case-insensitive, partial match",
        "ids": "Comma-separated signature ids to confirm, taken from a --names lookup",
        "local": "Use the local dev database",
    }
)
def petition_confirm(ctx, petition, names="", ids="", local=False):
    """Confirm signatures by hand when the confirmation email was not acted on: look up by name, then confirm by id."""
    if bool(names) == bool(ids):
        raise SystemExit("Give exactly one of --names (look signatures up) or --ids (confirm them)")
    scope = f"petition_slug = {_sql_str(petition)}"
    if names:
        terms = [n.strip() for n in names.split(",") if n.strip()]
        if not terms:
            raise SystemExit("--names has no names in it")
        # SQLite LIKE ignores case on its own.
        match = " OR ".join(f"name LIKE {_sql_str('%' + t + '%')}" for t in terms)
        rows = _d1(ctx, f"SELECT {_SIGNATURE_COLUMNS} FROM signatures WHERE {scope} AND ({match}) ORDER BY name", local)
        _print_signatures(rows, "No signatures matched.")
        return
    try:
        id_list = ", ".join(str(int(i)) for i in ids.split(","))
    except ValueError:
        raise SystemExit("--ids must be integers, comma-separated") from None
    # Same timestamp shape as the Worker's confirm handler (toISOString), since the
    # thank-you page ranks signers by comparing confirmed_at as text.
    rows = _d1(
        ctx,
        f"UPDATE signatures SET confirmed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        f" WHERE {scope} AND id IN ({id_list}) AND confirmed_at IS NULL"
        f" AND (SELECT status FROM petitions WHERE slug = petition_slug) = 'open'"
        f" RETURNING {_SIGNATURE_COLUMNS}",
        local,
    )
    _print_signatures(rows, "Nothing confirmed: ids not on this petition, already confirmed, or the petition is closed.")


_REPORT_COLUMNS = ["email", "date", "show?", "updates?", "reminder?"]


def _report_cells(row):
    yes_no = ("no", "yes")
    return [
        # The daily cleanup nulls emails once a petition closes; the row stays.
        row["email"] or "(deleted)",
        row["created_at"][:10],
        yes_no[bool(row["display_consent"])],
        yes_no[bool(row["updates_consent"])],
        yes_no[bool(row["reminded_at"])],
    ]


@task(help={"petition": "The petition's slug", "local": "Use the local dev database"})
def petition_report(ctx, petition, local=False):
    """List every signature on a petition, confirmed first, then unconfirmed, with counts."""
    # on_update_list comes from the update_recipients view so the double opt-in
    # rule stays defined once (migration 0004), as petition-emails reads it.
    rows = _d1(
        ctx,
        "SELECT email, created_at, display_consent, updates_consent, reminded_at, confirmed_at,"
        " id IN (SELECT id FROM update_recipients) AS on_update_list"
        f" FROM signatures WHERE petition_slug = {_sql_str(petition)} ORDER BY created_at",
        local,
    )
    if not rows:
        print("No signatures on this petition.")
        return
    confirmed = [_report_cells(r) for r in rows if r["confirmed_at"] is not None]
    unconfirmed = [_report_cells(r) for r in rows if r["confirmed_at"] is None]
    # One set of widths so the two tables line up.
    widths = _column_widths(_REPORT_COLUMNS, confirmed + unconfirmed)
    for label, cells in (("Confirmed", confirmed), ("Unconfirmed", unconfirmed)):
        print(f"{label} ({len(cells)})")
        if cells:
            _print_table(_REPORT_COLUMNS, cells, widths)
        print()
    on_update_list = sum(r["on_update_list"] for r in rows)
    reminded = sum(1 for r in rows if r["reminded_at"] is not None)
    print(
        f"{len(rows)} signature(s): {len(confirmed)} confirmed, {len(unconfirmed)} unconfirmed,"
        f" {on_update_list} on the update list, {reminded} reminded"
    )


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
    """Run content integrity checks (dr lint) and print a summary.

    Options:
      --detail              show full per-file output on stdout (dr lint --format text)
      --output FILE         write full per-file detail to FILE
      --json                emit JSON (dr lint --format json)
      --min-severity LEVEL  error | warning | info  (default: info)

    Subtasks:
      inv audit.prune            list orphaned source files by year
      inv audit.prune --apply    delete orphaned sources + empty year dirs (dr lint --prune)
    """
    fmt = "json" if json else "text" if detail else "summary"
    parts = ["uv run dr lint", "--format", fmt]
    if min_severity != "info":
        parts.extend(["--severity", min_severity])
    with ctx.cd("pipeline"):
        ctx.run(" ".join(parts), pty=True, in_stream=False, warn=True)
        if output:
            detail_parts = ["uv run dr lint", "--format", "text"]
            if min_severity != "info":
                detail_parts.extend(["--severity", min_severity])
            result = ctx.run(" ".join(detail_parts), hide=True, in_stream=False, warn=True)
            with open(output, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            print(f"  detail written to {output}")


@task(positional=[])
def _audit_prune(ctx, apply=False):
    """Show orphaned source count by year. Pass --apply to delete them.

    Without --apply, prints a year-bucket summary of source files not cited
    by any claim, pending draft or editorial page (dr lint's
    unreferenced-source issues) and deletes nothing.

    Options:
      --apply    delete the files and remove any empty year directories
                 (dr lint --prune)

    Related:
      inv audit                  show full integrity summary
      inv audit --detail         see per-file unreferenced-source warnings
    """
    with ctx.cd("pipeline"):
        if apply:
            ctx.run("uv run dr lint --prune --format summary", pty=True, in_stream=False, warn=True)
            return
        result = ctx.run("uv run dr lint --format json", hide=True, in_stream=False, warn=True)
    issues = [i for i in json.loads(result.stdout) if i["check_id"] == "unreferenced-source"]
    if not issues:
        print("No orphaned sources found.")
        return
    by_year: dict[str, int] = {}
    for issue in issues:
        year = issue["path"].replace("\\", "/").split("/")[-2]
        by_year[year] = by_year.get(year, 0) + 1
    print(f"{len(issues)} orphaned source(s) by year:")
    for year in sorted(by_year):
        print(f"  {year}  {by_year[year]:>4}")
    print("\nPass --apply to delete them (dr lint --prune).")


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
ns.add_task(petition_confirm)
ns.add_task(petition_report)
ns.add_collection(test_ns)
ns.add_collection(audit_ns)
