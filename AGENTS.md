# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, Copilot, etc.) working in this repository.

## Purpose

This repo is the research hub behind [dangerousrobot.org](https://dangerousrobot.org), backing claims made on the TreadLightly AI site with structured, citable evidence. Research content is Markdown with YAML frontmatter, organized for agent parsing and downstream consumption.

## Research Content Structure

Three entity types under `research/`:

- **Entities** (`entities/companies/`, `entities/products/`, `entities/topics/`) -- stable things we make claims about
- **Claims** (`claims/{entity-slug}/{claim-id}.md`) -- each assertion displayed on a page, with frontmatter carrying `verdict`, `as_of`, `sources`, `confidence`, `recheck_cadence_days`
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
| Research Lead | Orchestrator, never edits claims directly | `research/QUEUE.md` | Sub-tasks, plans |
| Ingestor | One URL in, one source file out | URL from queue | `sources/{yyyy}/{slug}.md` |
| Claim Updater | Proposes verdict changes with rationale | Claim + source files | Updated claim file |
| Citation Auditor | Finds claims with 0 sources, stale `as_of`, broken URLs | All claims | Audit report |
| Page Builder | Generates TS data files for TreadLightly | All claims | TS data files |

## Pipeline Agents (pipeline/)

The `pipeline/` directory contains PydanticAI agents that automate claim research and verification.

| Agent | Package | Input | Output |
|-------|---------|-------|--------|
| **Researcher** | `researcher/` | Claim text | URLs + reasoning (`web_search` tool) |
| **Ingestor** | `ingestor/` | URL | `SourceFile` (frontmatter + body) (`web_fetch`, `wayback_check` tools) |
| **Analyst** | `analyst/` | Sources + claim | `AnalystOutput` (entity + verdict + narrative) |
| **Auditor** | `auditor/` | Sources + claim (no verdict) | Independent `IndependentAssessment` |

Pipeline routing and persistence live in `orchestrator/`.

### Directory layout

```
pipeline/
  common/          # Shared models, frontmatter, content_loader, instructions loader
  ingestor/        # Agent: URL -> SourceFile
  researcher/      # Agent: claim -> relevant URLs
  analyst/         # Agent: sources + claim -> verdict + narrative
  auditor/         # Agent: independent second opinion
  orchestrator/    # Routing logic, checkpoints, persistence, dr CLI
  tests/
```

### Instruction files

Each agent package contains an `instructions.md` file that is loaded at import time via `common/instructions.py`. Edit `instructions.md` to change agent behavior without touching Python code.

### Checkpoint behavior

The pipeline supports human-in-the-loop checkpoints via a `CheckpointHandler` protocol:

- `review_sources` -- fires after ingest; allows halting before analysis when sources are poor
- `review_disagreement` -- fires when analyst and auditor verdicts conflict

Pass `--interactive` to `dr verify` or `dr research` to enable CLI prompts. Tests use `AutoApproveCheckpointHandler`.

### Tooling: dr vs inv

Two CLIs exist with different scopes:

| Tool | What it is | Use for |
|------|-----------|---------|
| `dr` | Python CLI defined in `pipeline/` | Pipeline operations: verify, research, audit, ingest |
| `inv` | Invoke task runner defined in `tasks.py` | Repo-level operations: setup, build, test, lint |

**`dr`** is the pipeline entry point. It lives in `orchestrator/cli.py` and is installed into the repo's venv:

```
uv run dr verify "Entity" "claim text"
uv run dr research "claim text"
uv run dr audit --entity ecosia
uv run dr ingest https://example.com/article
```

With the venv activated (`source .venv/bin/activate`), the `uv run` prefix is optional.

**`inv`** wraps repo-wide tasks:

```
inv setup      # install all dependencies (npm + uv)
inv test       # run pipeline unit tests
inv test.all   # run all tests including acceptance
inv build      # build Astro site
inv check      # build + lint + test (pre-push gate)
inv clean      # remove build artifacts
```

`inv` requires a one-time global install: `uv tool install invoke`. For pipeline operations, use `dr` directly.

## File Naming

- Use lowercase kebab-case slugs: `openai.md`, `training-data-consent.md`
- Sources go in year directories: `sources/2026/polytechnique-energy.md`

## Plans & Backlog

All plans live under `docs/plans/`. Lifecycle determines subdirectory:

| Location | Purpose | Git status |
|----------|---------|------------|
| `docs/plans/drafts/` | Work-in-progress plans | Gitignored -- never commit |
| `docs/plans/` | Active, final plans | Committed |
| `docs/plans/completed/` | Fully done plans | Committed |

Rules:

1. **Drafts stay local.** Write WIP plans to `docs/plans/drafts/`. Never commit a plan until its design is reviewed and final.
2. **Final plans are committed** to `docs/plans/` when approved.
3. **Completed plans move.** When all work items in a plan are done, `git mv` the plan to `docs/plans/completed/`.
4. **Keep the backlog current.** Update `docs/BACKLOG.md` whenever you start, complete, or plan work. This is not optional -- stale backlogs mislead future agents.
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
