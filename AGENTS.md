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
- Plans are local only (`research/plans/` is gitignored)
