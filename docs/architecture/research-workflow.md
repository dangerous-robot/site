# Research Workflow

How research content moves from idea to published claim on dangerousrobot.org.

## What this is

dangerousrobot.org is a research hub that publishes structured, citable fact-checks about AI companies, products, and sectors. Each claim carries a verdict, a confidence level, source references, and a recheck date, all captured as Markdown with YAML frontmatter. Two audiences consume the published content: humans reading the site directly, and the upstream TreadLightly AI site, which ingests the same files as structured data. The workflow below exists to keep claims auditable (every assertion traces to cited sources), agent-processable (the schema is stable enough for pipeline automation), and decoupled from the rendered site (content lives in `research/` and can move to its own repo later without breaking consumers).

## Content Model

Research content lives under `research/` as Markdown with YAML frontmatter, defined as Zod schemas in `src/content.config.ts` and enforced at build time. Three on-disk types -- **Entity**, **Source**, **Claim** -- plus reusable claim templates (criteria) in `research/templates.yaml`. Claims reference sources by slug (e.g., `2025/fli-safety-index`), never by raw URL, so one source can back many claims. Full schema and directory conventions: [content-model.md](content-model.md).

## Content Lifecycle

Steps 1-3 are automated by PydanticAI agents in `pipeline/`. Steps 4-6 remain manual or partially automated.

1. **Identify** -- A topic or URL is added to `research/QUEUE.md`.
2. **Ingest** -- The Ingestor agent takes a URL and produces a source file under `research/sources/{yyyy}/{slug}.md`.
3. **Claim** -- The Analyst proposes a draft verdict; the Evaluator independently assesses it. Both write to a claim file under `research/claims/{entity-slug}/`. The orchestrator halts the claim with `status: blocked` and a `blocked_reason` if fewer than two usable sources were obtained.
4. **Review** -- The change goes through a pull request. CI runs the quality gates (see below).
5. **Publish** -- On merge to main, the deploy workflow builds the Astro site and publishes to GitHub Pages.
6. **Maintain** -- Claims have a `recheck_cadence_days` field. When a claim is due for review, its sources and verdict should be re-evaluated and `as_of` updated. This step is currently manual. Lifecycle transitions are driven by `dr review`: `--approve` flips a reviewed `draft` to `published` (and records the sign-off in the audit sidecar); `--archive` retires a `published` claim to `archived`; bare `dr review` records a sign-off without changing status.

A separate operator command, `dr publish`, performs a bulk `draft → published` flip without recording an individual reviewer. Affected claims render as "Unreviewed" on the site until a later `dr review` writes a reviewer in. Use it for backfills (e.g., a release-cut auto-publish); use `dr review --approve` for human-reviewed publication.

## Agent Roles

Canonical role definitions live in [AGENTS.md § Agent Roles](../../AGENTS.md#agent-roles). The table below tracks current automation status; refer to AGENTS.md for what each role does.

| Role | Current status |
|------|----------------|
| **Research Lead** | Manual |
| **Orchestrator** | `pipeline/orchestrator/` (`pipeline.py`, `cli.py`, `persistence.py`, `checkpoints.py`) |
| **Router** | Documented; implementation deferred via `docs/plans/triage-agent.md` |
| **Researcher** | Automated -- `pipeline/researcher/` |
| **Ingestor** | Automated -- `pipeline/ingestor/` |
| **Analyst** | Automated -- `pipeline/analyst/` |
| **Evaluator** | Automated -- `pipeline/auditor/` (directory rename to `pipeline/evaluator/` deferred to post-v1) |
| **Citation Auditor** | Partially automated, split across three tools (see below). Full auditing is a backlog item (`docs/UNSCHEDULED.md`). |
| **Page Builder** | Not yet implemented. No LLM needed -- plain data transformation. Backlog item (`docs/UNSCHEDULED.md`). |

### Citation Auditor tools

The Citation Auditor responsibility is covered by three separate tools:

| Tool | Scope |
|------|-------|
| `scripts/check-citations.ts` | Broken source refs (claim `sources` slugs that do not resolve to a file). Runs in CI. |
| `dr lint` | Missing required fields, orphaned claims, stale `next_recheck_due` dates. No LLM, no network. |
| `dr reassess` | Verdict re-evaluation: re-runs the Evaluator agent against current sources to flag claims whose published verdict may no longer hold. |

## Content Rules

Four rules govern all research content changes. These are documented in `AGENTS.md` and apply to both human and agent contributors.

1. **Source citation required** -- Never edit a claim without citing at least one source in its `sources` array.
2. **`as_of` dating** -- Always set `as_of` to today's date when updating a claim's verdict.
3. **Summary length** -- Source summaries must not paraphrase beyond 30 words. (The Zod schema enforces a 200-character max.)
4. **Archived URLs** -- Every source should have an `archived_url` (Wayback Machine or equivalent) when possible. The schema makes this optional but it is strongly encouraged.

## Review Cadence

Claims carry a `recheck_cadence_days` field (default: 60 days) that signals when the claim should be re-evaluated.

| Content type | Cadence | Rationale |
|-------------|---------|-----------|
| Default | 60 days | General claims |
| Pricing claims | 14-30 days | Prices change frequently |
| Policy/regulation claims | 90-180 days | Policy moves slowly |

There is no automated scheduling for reviews today. The Citation Auditor role is intended to flag stale claims, but this is manual. Automated scheduling is a backlog item (see `docs/UNSCHEDULED.md`).

## Pipeline configuration knobs

Two operator-visible fields on `VerifyConfig` control researcher effort and LLM call concurrency:

- **`max_initial_queries`** -- how many search queries the Researcher's query planner generates per claim (default: 3). Lower values reduce API cost and latency; higher values improve recall.
- **`llm_concurrency`** -- cap on concurrent LLM calls across the pipeline (default: 8), enforced via `asyncio.Semaphore`. Relevant during `dr onboard`, which runs multiple claim templates concurrently.

## Quality Gates

PRs to `main` run a CI workflow (`.github/workflows/ci.yml`) with four checks across two jobs:

1. **Astro build** (`npm run build`) -- Validates all content against Zod schemas. A claim with a missing required field, invalid verdict value, or malformed date will fail the build.
2. **Markdown lint** (`npm run lint:md`) -- Runs `markdownlint-cli2` against `research/**/*.md`.
3. **Citation integrity** (`npm run check:citations`) -- Verifies every source slug in a claim's `sources` array resolves to an existing file under `research/sources/`. Catches broken references before merge.
4. **Content lint** (`dr lint --severity error`) -- Separate `lint-content` CI job that runs static content checks (no LLM, no network) and annotates errors on the PR. Backed by `pipeline/linter/`.

All four must pass. The first three are also available locally via `npm run check`; the fourth runs locally via `uv run dr lint`.

### What the gates do NOT currently check

- Whether `as_of` is current (no staleness detection in CI)
- Whether `archived_url` is present on sources
- Whether source summaries exceed the 30-word content rule (only the 200-char schema limit is enforced)
- Link validity (URLs are not fetched)

These gaps are candidates for additional CI scripts or the Citation Auditor agent (see `docs/UNSCHEDULED.md`).

## Claim Schema

Canonical schema lives in `src/content.config.ts` and is documented in [content-model.md § Claim](content-model.md#claim). Notable fields: `topics` (1-3 slugs), `verdict`, `confidence`, `status` (`draft` | `published` | `archived` | `blocked`), `phase`, `blocked_reason`, `as_of`, `sources`, `recheck_cadence_days`, `audit` (sidecar).

## Licensing

- **Code** (site source, scripts, configs): MIT License (`LICENSE`)
- **Research content** (`research/`): CC-BY-4.0 (`LICENSE-CONTENT`)

Contributors agree to these terms. See `CONTRIBUTING.md`.

## File References

- Schema definitions: `src/content.config.ts`
- Agent roles and content rules: `AGENTS.md`
- CI workflow: `.github/workflows/ci.yml`
- Citation checker: `scripts/check-citations.ts`
- Research queue: `research/QUEUE.md`
- Unscheduled work: `docs/UNSCHEDULED.md`
