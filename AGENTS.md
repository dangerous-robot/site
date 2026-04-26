# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, Copilot, etc.) working in this repository.

## Purpose

This repo is the research hub behind [dangerousrobot.org](https://dangerousrobot.org), backing claims made on the TreadLightly AI site with structured, citable evidence. Research content is Markdown with YAML frontmatter, organized for agent parsing and downstream consumption.

## How the system works

The system tracks four object types: **criteria** (reusable claim templates, intake-only), **entities** (companies and products in v1; sectors exist but aren't yet an intake; intake-only), **sources** (citable references; dual-role: they can enter from outside as operator-supplied intake **or** be produced inside the pipeline by the Ingestor), and **claims** (the system's only output type, never an intake). The **Orchestrator** owns each claim's lifecycle (queue → phases → drafted / blocked); the **Router** dispatches small classifications and matches incoming sources to criteria or claims. Work enters when one of the three non-claim objects is added to the queue: a **criterion** generates a claim for each entity it applies to; a **company** or **product** generates a claim for each active criterion; a **source** is matched by the **Router** to existing criteria (queuing new claim work) or to existing claims (queuing reassessment). The **Researcher** gathers candidate sources; the **Ingestor** archives each as a source file; the **Analyst** proposes a **draft verdict** and narrative once enough usable sources are available; the **Evaluator** produces an **independent evaluation** (open-loop: disagreements surface to the operator and are not auto-resolved, so the Evaluator does not feed back into the Analyst in v1). The combined post-review artifact is the **verdict**. The operator runs `dr review --approve` to publish, `--archive` to retire, or leaves a claim as draft for rework. **Citation check** is a static CI verification, not an agent.

For the generalized vision, see `docs/architecture/glossary.md` § How the system works.

## Design principle

**Small decisions, small models.** Each agent is scoped to make the smallest defensible decision in its lane. Larger models are reserved for tasks that genuinely require them. The Router runs on the smallest model class; only Analyst and Evaluator may invoke frontier models. This minimizes wasteful use of large models, the central cost the project exists to make visible, and keeps behavior auditable and legible. (This is testable design intent: a future check can verify model classes per agent.)

## Writing conventions

- Rarely use em dash characters. Prefer commas, colons, or parentheses instead.

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

Roles are listed below; several are automated via PydanticAI agents in `pipeline/`. Pipeline routing and persistence live in `orchestrator/`.

| Role | What it does | Status | Package |
|------|-------------|--------|---------|
| **Research Lead** | Orchestrates work from `QUEUE.md`; creates sub-tasks and plans; never edits claims directly | Manual | (none) |
| **Orchestrator** | Owns claim lifecycle: phase transitions, blocked routing, queue management | Implicit in `pipeline/orchestrator/` today; named role documented; full implementation tracked via `docs/plans/triage-agent.md` and `docs/plans/claim-lifecycle-states.md` | `pipeline/orchestrator/` |
| **Router** | Dispatches small classifications; matches new sources to criteria/claims; triggers blocked routing on `< 2` sources | Documented; implementation deferred via `docs/plans/triage-agent.md` | (`pipeline/router/` planned) |
| **Researcher** | Takes claim text, returns relevant URLs for ingestion (`web_search` tool) | Automated | `researcher/` |
| **Ingestor** | Takes a URL, produces a source file (one URL in, one `sources/{yyyy}/{slug}.md` out); uses `web_fetch`, `wayback_check` | Automated | `ingestor/` |
| **Analyst** | Given a claim and its sources, produces `AnalystOutput` (entity + verdict + narrative) | Automated | `analyst/` |
| **Evaluator** | Produces an independent evaluation of analyst output, returning `IndependentAssessment` | Automated | `auditor/` |

### Directory layout

```
pipeline/
  common/          # Shared models, frontmatter, content_loader, instructions loader
  ingestor/        # Agent: URL -> SourceFile
  researcher/      # Agent: claim -> relevant URLs
  analyst/         # Agent: sources + claim -> verdict + narrative
  auditor/         # Evaluator role; directory rename to evaluator/ deferred to post-v1
  orchestrator/    # Routing logic, checkpoints, persistence, dr CLI
  tests/
```

### Instruction files

Each agent package contains an `instructions.md` file that is loaded at import time via `common/instructions.py`. Edit `instructions.md` to change agent behavior without touching Python code.

### Checkpoint behavior

The pipeline supports human-in-the-loop checkpoints via a `CheckpointHandler` protocol:

- `review_sources` -- fires after ingest; allows halting before analysis when sources are poor
- `review_disagreement` -- fires when analyst and evaluator verdicts conflict
- `review_onboard` -- fires during `dr onboard` after applicable claim templates are selected; responses are `accept`, `reject`, or an edited list of template slugs to keep

Pass `--interactive` to `dr verify`, `dr research`, or `dr onboard` to enable CLI prompts. Tests use `AutoApproveCheckpointHandler`.

### Tooling: dr vs inv

Two CLIs exist with different scopes:

| Tool | What it is | Use for |
|------|-----------|---------|
| `dr` | Python CLI defined in `pipeline/` | Pipeline operations: verify, research, evaluate, ingest |
| `inv` | Invoke task runner defined in `tasks.py` | Repo-level operations: setup, build, test, lint |

**`dr`** is the pipeline entry point. It lives in `orchestrator/cli.py` and is installed into the repo's venv:

```
uv run dr verify "Entity" "claim text"
uv run dr research "claim text"
uv run dr reassess --entity ecosia
uv run dr ingest https://example.com/article
uv run dr onboard "Ecosia AI" --type product
uv run dr lint --entity ecosia
uv run dr review --claim ecosia/renewable-energy-hosting
```

Commands:

- `dr verify` -- Verify a claim about an entity using web research
- `dr research` -- Research a claim: find sources, evaluate verdict, write everything to disk
- `dr reassess` -- Run evaluator checks on research claims
- `dr ingest` -- Ingest a URL and produce a source file
- `dr onboard` -- Onboard an entity using claim templates
- `dr lint` -- Run static content checks (no LLM, no network); exits 1 on errors
- `dr review` -- Mark a claim as human-reviewed in its audit sidecar

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

### Plan review records

Every plan in `docs/plans/` (not drafts) must have a `## Review history` section at the bottom of the file.

Each review appends a row to the table -- never overwrites previous rows.

```markdown
## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| YYYY-MM-DD | agent (model-id) or human (name) | basic / deep / security / implementation / iterated | brief summary or "no changes" |
```

Scope definitions:

- `basic` -- skimmed for obvious issues; no deep verification
- `implementation` -- verified against actual code; checked file paths, function names, patterns
- `deep` -- full review: implementation accuracy, edge cases, design tradeoffs
- `security` -- focused on security implications
- Scopes can be combined: `deep, implementation`
- `iterated` -- plan was revised during this review; use alongside a scope level

**Promotion rule:** A draft without a review record must not be promoted from `docs/plans/drafts/` to `docs/plans/`. Add the first review row before or during promotion.

The review record lives in the plan file itself, not in a separate file.

## Release planning

Three mutually exclusive work states:

| State | Location | Meaning |
|---|---|---|
| Unscheduled | `docs/UNSCHEDULED.md` | Known work not yet assigned to a release. May or may not have a plan file. Default holding area. |
| Scheduled | A release doc (`docs/plans/v*.*.*.md`) | Committed to a specific release. When an item enters a release doc, remove it from UNSCHEDULED.md. |
| Plan-only | `docs/plans/drafts/` (draft) or `docs/plans/` (reviewed) | A plan exists for exploratory/future work not yet prioritized into a release or unscheduled. |

**Plan lifecycle** (within plan-only state):
1. New/speculative plan → `docs/plans/drafts/` (gitignored, WIP)
2. Design reviewed → `docs/plans/` (committed)
3. Fully implemented → `docs/plans/completed/`

**Transition rules:**
- When a plan-only item gets prioritized but not release-assigned: add to UNSCHEDULED.md
- When assigned to a release: add to release doc, remove from UNSCHEDULED.md
- When a release ships: move its release doc to `docs/plans/completed/`

**Plan filename suffix convention** — append to base name when it adds signal:

| Suffix | Meaning |
|---|---|
| `_stub` | Scaffolded from a description; not yet fully implementable |
| `_completed` | Fully implemented; use in `completed/` to distinguish from abandoned/superseded |

No suffix = plan is complete and reviewable. Keep the set small.

**Release doc naming:** `docs/plans/v{semver}.md`. `VERSION.md` declares the current working version.

**Note on `future/` directory:** `docs/plans/future/` is undocumented. Dissolve it: move contents to `docs/plans/drafts/` and delete the directory.

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
