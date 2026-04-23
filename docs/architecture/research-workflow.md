# Research Workflow

How research content moves from idea to published claim on dangerousrobot.org.

## What this is

dangerousrobot.org is a research hub that publishes structured, citable fact-checks about AI companies, products, and sectors. Each claim carries a verdict, a confidence level, source references, and a recheck date, all captured as Markdown with YAML frontmatter. Two audiences consume the published content: humans reading the site directly, and the upstream TreadLightly AI site, which ingests the same files as structured data. The workflow below exists to keep claims auditable (every assertion traces to cited sources), agent-processable (the schema is stable enough for pipeline automation), and decoupled from the rendered site (content lives in `research/` and can move to its own repo later without breaking consumers).

## Content Model

Three entity types live under `research/`, each defined as a Zod schema in `src/content.config.ts` and enforced at build time by Astro Content Collections.

| Entity | Location | Purpose |
|--------|----------|---------|
| **Entity** | `research/entities/{type}/{slug}.md` | A stable thing we make claims about (company, product, sector, topic) |
| **Source** | `research/sources/{yyyy}/{slug}.md` | A citable reference -- cite once, reference from many claims |
| **Claim** | `research/claims/{entity-slug}/{claim-id}.md` | An assertion with verdict, confidence, and linked sources |

Claims reference sources by slug (e.g., `2025/fli-safety-index`), never by raw URL. This indirection allows one source to back multiple claims and keeps URLs centralized.

## Content Lifecycle

Steps 1-3 are automated by PydanticAI agents in `pipeline/`. Steps 4-6 remain manual or partially automated.

1. **Identify** -- A topic or URL is added to `research/QUEUE.md`.
2. **Ingest** -- The Ingestor agent takes a URL and produces a source file under `research/sources/{yyyy}/{slug}.md`.
3. **Claim** -- The Analyst and Auditor agents propose or update a claim file under `research/claims/{entity-slug}/`.
4. **Review** -- The change goes through a pull request. CI runs the quality gates (see below).
5. **Publish** -- On merge to main, the deploy workflow builds the Astro site and publishes to GitHub Pages.
6. **Maintain** -- Claims have a `recheck_cadence_days` field. When a claim is due for review, its sources and verdict should be re-evaluated and `as_of` updated. This step is currently manual. Lifecycle transitions are driven by `dr review`: `--approve` flips a reviewed `draft` to `published` (and records the sign-off in the audit sidecar); `--archive` retires a `published` claim to `archived`; bare `dr review` records a sign-off without changing status.

## Agent Roles

Seven roles are defined in `AGENTS.md`. Several are now automated via PydanticAI agents in `pipeline/`.

| Role | What it does | Current status |
|------|-------------|----------------|
| **Research Lead** | Orchestrates work from `QUEUE.md`. Creates sub-tasks and plans. Never edits claims directly. | Manual |
| **Researcher** | Takes a claim text, returns relevant URLs for ingestion. | Automated -- PydanticAI agent in `pipeline/researcher/` |
| **Ingestor** | Takes a URL, produces a source file. One URL in, one `sources/{yyyy}/{slug}.md` out. | Automated -- PydanticAI agent in `pipeline/ingestor/` |
| **Analyst** | Proposes verdict changes with rationale, given a claim and its source files. | Automated -- PydanticAI agent in `pipeline/analyst/` |
| **Auditor** | Reviews and refines analyst output before the claim file is written. | Automated -- PydanticAI agent in `pipeline/auditor/` |
| **Citation Auditor** | Finds claims with zero sources, stale `as_of` dates, or broken URLs. Produces audit reports. | Partially automated, split across three tools (see below). Full auditing is a backlog item (see `docs/UNSCHEDULED.md`). |
| **Page Builder** | Generates TS data files for downstream consumption by the TreadLightly site. | Not yet implemented. No LLM needed -- plain data transformation. Backlog item (see `docs/UNSCHEDULED.md`). |

### Citation Auditor tools

The Citation Auditor responsibility is covered by three separate tools:

| Tool | Scope |
|------|-------|
| `scripts/check-citations.ts` | Broken source refs (claim `sources` slugs that do not resolve to a file). Runs in CI. |
| `dr lint` | Missing required fields, orphaned claims, stale `next_recheck_due` dates. No LLM, no network. |
| `dr reassess` | Verdict re-evaluation: re-runs the Auditor agent against current sources to flag claims whose published verdict may no longer hold. |

Note: `dr reassess` was previously named `dr audit`; it was renamed because its scope (verdict re-evaluation) differs from the broader Citation Auditor role.

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

## Quality Gates

PRs to `main` run a CI workflow (`.github/workflows/ci.yml`) with three checks:

1. **Astro build** (`npm run build`) -- Validates all content against Zod schemas. A claim with a missing required field, invalid verdict value, or malformed date will fail the build.
2. **Markdown lint** (`npm run lint:md`) -- Runs `markdownlint-cli2` against `research/**/*.md` (excluding `research/plans/`).
3. **Citation integrity** (`npm run check:citations`) -- Verifies every source slug in a claim's `sources` array resolves to an existing file under `research/sources/`. Catches broken references before merge.

All three must pass. The combined check is also available locally via `npm run check`.

### What the gates do NOT currently check

- Whether `as_of` is current (no staleness detection in CI)
- Whether `archived_url` is present on sources
- Whether source summaries exceed the 30-word content rule (only the 200-char schema limit is enforced)
- Link validity (URLs are not fetched)

These gaps are candidates for additional CI scripts or the Citation Auditor agent (see `docs/UNSCHEDULED.md`).

## Claim Schema

Key fields enforced by Zod at build time:

| Field | Type | Notes |
|-------|------|-------|
| `title` | string | Human-readable claim statement |
| `entity` | string | Path like `companies/anthropic` |
| `category` | enum | One of 8 categories (see `AGENTS.md`) |
| `verdict` | enum | `true`, `mostly-true`, `mixed`, `mostly-false`, `false`, `unverified`, `not-applicable` |
| `confidence` | enum | `high`, `medium`, `low` |
| `criteria_slug` | string | Optional. Links to the criterion template this claim was generated from |
| `status` | enum | `draft`, `published`, `archived` (default: `draft`) |
| `as_of` | date | When the verdict was last evaluated |
| `sources` | string[] | Slugs referencing files under `research/sources/` |
| `recheck_cadence_days` | number | Default 60 |
| `next_recheck_due` | date | Optional. When this claim should next be reviewed |
| `audit` | object | Optional. Pipeline audit sidecar data (see content-model.md) |

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
