# Research Workflow

How research content moves from idea to published claim on dangerousrobot.org.

## Content Model

Three entity types live under `research/`, each defined as a Zod schema in `src/content.config.ts` and enforced at build time by Astro Content Collections.

| Entity | Location | Purpose |
|--------|----------|---------|
| **Entity** | `research/entities/{type}/{slug}.md` | A stable thing we make claims about (company, product, topic) |
| **Source** | `research/sources/{yyyy}/{slug}.md` | A citable reference -- cite once, reference from many claims |
| **Claim** | `research/claims/{entity-slug}/{claim-id}.md` | An assertion with verdict, confidence, and linked sources |

Claims reference sources by slug (e.g., `2025/fli-safety-index`), never by raw URL. This indirection allows one source to back multiple claims and keeps URLs centralized.

## Content Lifecycle

Today, the workflow is manual. Agent automation is planned (Phase 4) but not yet implemented.

1. **Identify** -- A topic or URL is added to `research/QUEUE.md`.
2. **Ingest** -- A contributor reads the source material and creates a source file under `research/sources/{yyyy}/{slug}.md` with URL, archived URL, publisher, summary (max 200 chars), and key quotes.
3. **Claim** -- A claim file is created or updated under `research/claims/{entity-slug}/`. The claim links to one or more source slugs, sets a verdict, confidence level, and `as_of` date.
4. **Review** -- The change goes through a pull request. CI runs the quality gates (see below).
5. **Publish** -- On merge to main, the deploy workflow builds the Astro site and publishes to GitHub Pages.
6. **Maintain** -- Claims have a `recheck_cadence_days` field. When a claim is due for review, its sources and verdict should be re-evaluated and `as_of` updated.

## Agent Roles

Five roles are defined in `AGENTS.md`. Today these are performed by humans or AI coding agents during interactive sessions. PydanticAI-based automation is planned for Phase 4.

| Role | What it does | Current status |
|------|-------------|----------------|
| **Research Lead** | Orchestrates work from `QUEUE.md`. Creates sub-tasks and plans. Never edits claims directly. | Manual |
| **Ingestor** | Takes a URL, produces a source file. One URL in, one `sources/{yyyy}/{slug}.md` out. | Manual (planned for PydanticAI automation) |
| **Claim Updater** | Proposes verdict changes with rationale, given a claim and its source files. | Manual |
| **Citation Auditor** | Finds claims with zero sources, stale `as_of` dates, or broken URLs. Produces audit reports. | Partially automated via `scripts/check-citations.ts` (checks broken refs only). Full auditing planned for Phase 4. |
| **Page Builder** | Generates TS data files for downstream consumption by the TreadLightly site. | Not yet implemented (Phase 5). No LLM needed -- plain data transformation. |

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

There is no automated scheduling for reviews today. The Citation Auditor role is intended to flag stale claims, but this is manual. Automated review scheduling is planned for Phase 5.

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

These gaps are candidates for the Citation Auditor agent (Phase 4) or additional CI scripts.

## Claim Schema

Key fields enforced by Zod at build time:

| Field | Type | Notes |
|-------|------|-------|
| `title` | string | Human-readable claim statement |
| `entity` | string | Path like `companies/anthropic` |
| `category` | enum | One of 8 categories (see `AGENTS.md`) |
| `verdict` | enum | `true`, `mostly-true`, `mixed`, `mostly-false`, `false`, `unverified` |
| `confidence` | enum | `high`, `medium`, `low` |
| `as_of` | date | When the verdict was last evaluated |
| `sources` | string[] | Slugs referencing files under `research/sources/` |
| `recheck_cadence_days` | number | Default 60 |
| `next_recheck_due` | date | Optional. When this claim should next be reviewed |

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
- Phase tracking: `plans/BACKLOG.md`
