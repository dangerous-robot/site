# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, Copilot, etc.) working in this repository.

## Purpose

This repo is the research hub behind [dangerousrobot.org](https://dangerousrobot.org), backing claims made on the TreadLightly AI site with structured, citable evidence. Research content is Markdown with YAML frontmatter, organized for agent parsing and downstream consumption.

## Research Content Structure

Three entity types under `research/`:

- **Entities** (`entities/companies/`, `entities/products/`, `entities/topics/`) -- stable things we make claims about
- **Claims** (`claims/{entity-slug}/{claim-id}.md`) -- each assertion displayed on a page, with frontmatter carrying `verdict`, `as_of`, `sources`, `confidence`, `review_cadence_days`
- **Sources** (`sources/{yyyy}/{slug}.md`) -- cite-once, reference-many pool with `url`, `archived_url`, `publisher`, `kind`, `summary`, `key_quotes`

Claims reference source files by ID, never raw URLs.

Schemas are defined in `src/content.config.ts` and enforced at build time by Astro.

## Claim Category Taxonomy

| Slug | Description |
|------|-------------|
| `ai-safety` | Independent evaluations of AI company/provider safety |
| `environmental-impact` | Energy, emissions, water, renewable energy claims |
| `product-comparison` | Feature/practice comparisons across AI products |
| `consumer-guide` | How to opt out, disable, limit AI features |
| `ai-literacy` | Decision frameworks, when/how to use AI thoughtfully |
| `data-privacy` | What happens to your data across AI services |
| `industry-analysis` | Corporate structure, business models, ownership |
| `regulation-policy` | Government oversight, AI policy landscape |

## Content Rules

- Never edit a claim without citing at least one source
- Always set `as_of` to today's date when updating a claim verdict
- Source summaries must not paraphrase beyond 30 words
- Every source should have an `archived_url` (Wayback Machine) when possible

## Agent Roles

| Role | Scope | Input | Output |
|------|-------|-------|--------|
| Research Lead | Orchestrator, never edits claims directly | `QUEUE.md` | Sub-tasks, plans |
| Ingestor | One URL in, one source file out | URL from queue | `sources/{yyyy}/{slug}.md` |
| Claim Updater | Proposes verdict changes with rationale | Claim + source files | Updated claim file |
| Citation Auditor | Finds claims with 0 sources, stale `as_of`, broken URLs | All claims | Audit report |
| Page Builder | Generates TS data files for TreadLightly | All claims | TS data files |

## File Naming

- Use lowercase kebab-case slugs: `openai.md`, `training-data-consent.md`
- Sources go in year directories: `sources/2026/polytechnique-energy.md`

## Plans & Backlog

All plans live under `plans/`. Lifecycle determines subdirectory:

| Location | Purpose | Git status |
|----------|---------|------------|
| `plans/drafts/` | Work-in-progress plans | Gitignored -- never commit |
| `plans/` | Active, final plans | Committed |
| `plans/completed/` | Fully done plans | Committed |

Rules:

1. **Drafts stay local.** Write WIP plans to `plans/drafts/`. Never commit a plan until its design is reviewed and final.
2. **Final plans are committed** to `plans/` when approved.
3. **Completed plans move.** When all work items in a plan are done, `git mv` the plan to `plans/completed/`.
4. **Keep the backlog current.** Update `plans/BACKLOG.md` whenever you start, complete, or plan work. This is not optional -- stale backlogs mislead future agents.
5. **Check approved issues.** When determining what to work on next, also check: `gh issue list --label approved --state open`. Reference relevant issue numbers in BACKLOG.md but do not duplicate issue content.

## Architecture Docs

Architectural summaries live in `docs/architecture/`. These are reference documents for humans and agents -- they describe how the system works today, not how it should work (that's what plans are for).

| File | Describes |
|------|-----------|
| `docs/architecture/README.md` | Document map -- index of all architecture docs with one-line descriptions |
| Other files | One doc per major subsystem or concern |

Rules:

1. **Update before writing plans.** Before starting a new plan, read the relevant architecture docs to ensure your baseline understanding is correct.
2. **Update after completing work.** When finishing implementation work that changes how the system works, update the affected architecture doc(s). If no doc exists for the area you changed, create one.
3. **Link new docs in the map.** When creating a new architecture doc, add it to `docs/architecture/README.md`.
