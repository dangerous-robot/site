# Plan: `dr lint` — static content auditor

| Phase | Status |
|-------|--------|
| Phase 1: static lint command | `[ ] ready to implement` |
| Phase 2: CI integration | `[ ] planned` |
| Phase 3: QUEUE.md re-onboard loop | `[ ] future` |
| Phase 4: scheduled agent triage | `[ ] future / long-term` |

---

## Background: known data quality problems

These are the concrete issues that prompted this plan. Phase 1 is designed to detect all of them.

1. **Missing required fields** — `description` empty on entities, required claim fields absent (e.g., `as_of`, `title`)
2. **Orphaned claims** — claim files exist under `research/claims/{entity-slug}/` but no matching entity file exists at `research/entities/{type}/{entity-slug}.md`
3. **Entity misresolution** — pipeline matched the wrong entity (e.g., Earthly Insight resolved to an NGO, not the AI company). Indicator: `website` is a `/login` URL, or `description` reads like a landing-page placeholder
4. **Field name drift** — `standard_slug` vs `criteria_slug` after a rename; old name should be flagged as unrecognized
5. **Invalid / placeholder values** — `website` set to a `/login` path, `description` contains boilerplate text
6. **Broken cross-references** — `standard_slug` value not found in `research/templates.yaml`; source IDs in `sources:` not found in `research/sources/`
7. **Duplicate slugs** — two entity files resolving to the same slug across different type directories

---

## Phase 1: static `dr lint` command

**Status:** `[ ] ready to implement`

### What it does

Runs fast, file-level checks on research content — no LLM, no network. Reads YAML frontmatter from entities, claims, and sources; parses `research/templates.yaml` for known standard slugs. Emits a structured report with severity levels. Exits 1 if any errors are found.

### Checks

| ID | Severity | Description |
|----|----------|-------------|
| `orphaned-claim` | error | Claim's `entity:` path (e.g., `companies/ecosia`) has no matching file in `research/entities/` |
| `missing-required-field` | error | Any required frontmatter field (`title`, `entity`, `category`, `verdict`, `confidence`, `as_of`, `sources`) is absent from a claim file. Source files are out of scope for Phase 1 — the six known data problems are all entity- or claim-side. Add source-field checks in a later iteration if source data quality becomes a concern. |
| `empty-required-string` | error | Required string field present but empty or whitespace-only (e.g., entity `description: ""`) |
| `broken-standard-slug` | error | `standard_slug` value is set but does not match any `slug:` in `research/templates.yaml` |
| `broken-source-ref` | error | A source ID in a claim's `sources:` list has no corresponding file in `research/sources/`. Source IDs are year-prefixed slugs (e.g., `2025/fli-safety-index`), resolving to `research/sources/{id}.md` |
| `duplicate-entity-slug` | error | Two entity files across any type directories produce the same slug |
| `placeholder-website` | warning | Entity `website` field contains a path-only URL (e.g., `/login`) or a known placeholder domain (`example.com`) |
| `legacy-field-name` | warning | Frontmatter contains `standard_slug` (pre-rename name); rename to `criteria_slug` once the Standards→Criteria rename lands |
| `unknown-frontmatter-key` | warning | Frontmatter contains a key not in the canonical schema for that collection type. Canonical entity fields: `name`, `type`, `website`, `aliases`, `description`. Canonical claim fields: `title`, `entity`, `category`, `verdict`, `confidence`, `standard_slug`, `as_of`, `sources`, `recheck_cadence_days`, `next_recheck_due` |
| `missing-standard-slug` | info | Claim has no `standard_slug` — not required, but reduces traceability |
| `stale-recheck` | info | `next_recheck_due` is in the past |
| `future-as-of` | info | Claim `as_of` date is in the future — likely a paste error |
| `entity-type-dir-mismatch` | warning | Entity file `type:` field does not match its directory (e.g., `type: company` in `research/entities/products/`) |

`standard_slug` is the canonical name today (per `content.config.ts`). The roadmap plans to rename it to `criteria_slug` as part of the Standards→Criteria rename before v0.1.0. Until that rename ships, `standard_slug` is valid and `criteria_slug` is unknown; after the rename, the polarity of `legacy-field-name` flips. The linter treats absence of `standard_slug` as `info`, not `error`. A present-but-broken value (not matched in `templates.yaml`) is `error`.

### New module: `pipeline/linter/`

Does not touch the existing `pipeline/auditor/` package (which is LLM-side).

```
pipeline/linter/
    __init__.py
    checks.py      # individual check functions, each returns list[LintIssue]
    models.py      # LintIssue dataclass (path, check_id, severity, message, hint)
    report.py      # format_text_report, format_json_report
    runner.py      # load_templates(), collect_all_paths(), run_all_checks()
```

#### `LintIssue` model

```python
@dataclass
class LintIssue:
    path: str           # relative to repo root
    check_id: str       # e.g. "orphaned-claim"
    severity: str       # "error" | "warning" | "info"
    message: str        # human-readable description
    hint: str = ""      # optional suggested fix
```

Line numbers are not included. GitHub annotations support a `line:` field, but YAML frontmatter is parsed as a dict (no position tracking). If a later iteration adds line numbers, switch from `python-frontmatter` or add a pass with `ruamel.yaml` or manual scanning. Deferring is reasonable for Phase 1.

#### `checks.py` structure

Each check function signature:

```python
def check_orphaned_claims(
    claim_files: list[Path],
    entity_index: set[str],  # known entity refs like "companies/ecosia"
) -> list[LintIssue]: ...
```

This makes checks independently testable without disk I/O (caller builds the indexes; checks receive them).

#### Report format (text)

```
dr lint — dangerousrobot.org content linter
============================================================
  18 files checked  |  3 errors  |  2 warnings  |  1 info

ERRORS
  research/claims/earthly-insight/corporate-structure.md
    [orphaned-claim] entity "companies/earthly-insight" has no matching file
    hint: if the entity is missing, run `dr onboard "Earthly Insight" --type company`; if the entity exists under a different path, correct the `entity:` field in the claim

  research/entities/companies/earthly-insight.md
    [placeholder-website] website "https://www.earthlyinsight.ai/login" looks like a login page
    hint: update to the product homepage

WARNINGS
  research/entities/companies/earthly-insight.md
    [entity-type-dir-mismatch] entity type "product" is in directory "companies/"
    hint: move file to research/entities/products/ or correct the type field

INFO
  research/claims/openai/carbon-commitments.md
    [missing-standard-slug] no standard_slug set
============================================================
Exit code: 1
```

JSON output (`--format json`) emits a list of `LintIssue` objects for downstream tooling.

### CLI command

```python
@main.command()
@click.option("--entity", default=None, help="Lint only claims for this entity slug")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
@click.option("--severity", default="info", type=click.Choice(["error", "warning", "info"]), help="Minimum severity to report")
@click.option("--repo-root", default=None, type=click.Path(exists=True))
def lint(entity, output_format, severity, repo_root):
    """Run static content checks — no LLM, no network.

    Exits 1 if any errors are found.

    Example:
        dr lint
        dr lint --entity ecosia
        dr lint --format json --severity error
    """
```

Follows the same `ctx.pass_context` + `resolve_repo_root()` pattern as existing commands. The `--model` option inherited from the group is unused but harmless.

### Files changed

| File | Change |
|------|--------|
| `pipeline/linter/__init__.py` | new, empty |
| `pipeline/linter/models.py` | new — `LintIssue` dataclass |
| `pipeline/linter/checks.py` | new — all check functions |
| `pipeline/linter/runner.py` | new — path collection, template loading, check orchestration |
| `pipeline/linter/report.py` | new — text + JSON formatters |
| `pipeline/orchestrator/cli.py` | add `lint` command (import from `linter.*`) |
| `pipeline/tests/test_linter.py` | new — unit tests per check function using fixture dicts |

### Design decisions

- **Pure functions / no I/O in checks.** `runner.py` does all the disk reading and builds index structures (entity slug set, template slug set, source ID set). Check functions receive those indexes. This makes each check unit-testable without temp files.
- **`standard_slug` / `criteria_slug` naming posture.** The current canonical name in `content.config.ts` is `standard_slug`. The roadmap plans to rename it to `criteria_slug` before v0.1.0. Until that rename ships: `standard_slug` is valid, `criteria_slug` is unknown (would fire `unknown-frontmatter-key`), and `legacy-field-name` has nothing to flag. After the rename, the check polarity flips — `criteria_slug` becomes canonical and `standard_slug` triggers `legacy-field-name`. The plan documents the post-rename direction so the check is written once and only the warning message changes at flip time.
- **Orphan detection logic.** A claim is orphaned if its `entity:` frontmatter value (e.g., `companies/earthly-insight`) does not correspond to an existing file at `research/entities/companies/earthly-insight.md`. The claim directory name is not used — the frontmatter value is authoritative.
- **Templates loaded from `research/templates.yaml` directly.** Not through Astro collections or any API. The linter parses YAML with PyYAML (already in the project) and builds a `set[str]` of known slugs.
- **`legacy-field-name` is implemented now, not deferred.** It is currently a no-op (nothing to flag before the Standards→Criteria rename). Implementing it now means it activates automatically when the rename ships — no second PR needed.
- **No LLM calls anywhere in Phase 1.**

---

## Phase 2: CI integration

**Status:** `[ ] planned`

### What changes

The existing `.github/workflows/ci.yml` is Node-only (Node 22, `npm ci`, `npm run build`, `npm run lint:md`, `npm run check:citations`). Adding Python-based linting requires either:

- **Option A (preferred): new job** — add a second `lint-content` job in parallel with `check`. This avoids inflating the existing build matrix and keeps Node/Python concerns separate.
- **Option B: extend existing job** — add Python setup steps to the existing `check` job after `npm run build`. Simpler but couples Python install time to every build.

The snippet below uses Option A:

```yaml
# .github/workflows/ci.yml

jobs:
  check:
    # ... existing Node job unchanged ...

  lint-content:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install pipeline deps
        run: pip install uv && uv sync
        working-directory: pipeline

      - name: Run content linter
        run: uv run dr lint --format json --severity error > lint-report.json
        working-directory: pipeline

      - name: Annotate PR with lint errors
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const issues = JSON.parse(fs.readFileSync('pipeline/lint-report.json'));
            for (const issue of issues) {
              core.error(issue.message, { file: issue.path, title: issue.check_id });
            }
```

GitHub's `core.error()` renders inline annotations on the PR diff when `file:` matches a changed file. Issues in unchanged files appear in the job summary.

### Design decisions

- Run linter on every PR, not just on `research/` changes. False-negative risk from partial runs outweighs the minor CI overhead (linter is fast).
- JSON output to a file allows the annotation step to run separately without re-scanning.
- `--severity error` in CI means warnings and info items don't fail the build. Operators can escalate to `--severity warning` once the backlog of existing warnings is cleared.

---

## Phase 3: QUEUE.md re-onboard loop

**Status:** `[ ] future`

### What it does

`dr lint --queue` appends orphaned-claim entity names to `research/ONBOARD_QUEUE.md` so `dr onboard` can process them in bulk. This creates a closed loop: lint surfaces orphans, `ONBOARD_QUEUE.md` holds the backlog, onboard clears it.

**Note on file choice:** `research/QUEUE.md` holds URLs/topics for source ingestion (input to `dr ingest`). `research/ONBOARD_QUEUE.md` is the correct target for entity re-onboarding. The previous file was deleted 2026-04-24 as stale; `dr lint --queue` should re-create it on first append in the pipe-delimited format below.

`ONBOARD_QUEUE.md` uses a pipe-delimited format (`name|type`, one per line) that a bash one-liner or `dr onboard --queue ONBOARD_QUEUE.md` can iterate without shell parsing complexity. `dr lint --queue` appends in this same format with an inline comment noting the reason:

```
Earthly Insight|company  # orphaned-claim
```

The bash runner skips `#`-prefixed lines, so commented-out entries (manual review holds) are ignored automatically.

### Design decisions

- `--queue` flag is additive. It appends; it does not clear existing entries.
- `dr lint` does not modify `ONBOARD_QUEUE.md` by default. The flag is opt-in so CI runs are always read-only.
- Deduplication: before appending, check whether the entity slug is already present in the queue or already has an entity file.
- Entity type may be unknown when lint detects an orphan (the claim directory name is not type-categorized). Either infer type from the entity `type:` frontmatter in the claim, or append with `--type unknown` and require human resolution.

---

## Phase 4: scheduled agent triage

**Status:** `[ ] future / long-term`

### Vision

A multi-agent loop running on a GitHub Actions cron schedule:

1. **Surface agent** — runs `dr lint` + `dr reassess` (LLM verdicts), collects issues, produces a structured triage report
2. **Triage agent** — classifies issues by severity, assigns to appropriate action (re-onboard, human review, auto-fix)
3. **Fix agent** — for high-confidence fixable issues (orphaned entity with a known homepage, stale entity with a `website` to re-scrape), opens a draft PR with the proposed fix
4. **Human approval** — PR review gates any write action to `research/`

### Design decisions

- Agents collaborate asynchronously via PR comments and issue labels, not direct function calls.
- Fix agent never auto-merges. Human approval is required.
- `dr lint` remains the fast, synchronous foundation that all agents call first.
- Phase 4 depends on Phases 1-3 being stable; do not implement until the static linter has been in CI for at least one sprint.

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-04-22 | agent (claude-sonnet-4-6) | deep — CLI patterns, schema accuracy, CI workflow, check completeness | Fixed inverted `standard_slug`/`criteria_slug` direction throughout; corrected Phase 3 queue file from `QUEUE.md` to `ONBOARD_QUEUE.md`; rewrote Phase 2 CI snippet to match Node-only existing workflow and proposed parallel job; documented year-prefix source ID format for `broken-source-ref`; added `entity-type-dir-mismatch` and `future-as-of` checks; expanded `unknown-frontmatter-key` with canonical field lists (including `aliases`); added `LintIssue` line-number deferral note |
| 2026-04-22 | agent (active review) | status + stub + duplicate check | Status accurate (per-phase table present). Not a stub. No duplicates with other active plans. Suggested rename: `dr-lint.md` is clear. |
