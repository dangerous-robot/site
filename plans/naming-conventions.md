# Naming Conventions & Project Vocabulary

**Status**: active
**Depends on**: None (applies across all phases)

## Goal

Establish consistent vocabulary across the project to reduce ambiguity as the codebase grows, especially with the addition of Python automation (Phase 4) and public feedback (Phase 6).

---

## 1. Architecture Diagram

```
                        +-----------------------------+
                        |       QUEUE.md (intake)      |
                        +-------------+---------------+
                                      | URL
                                      v
                        +-----------------------------+
                        |     Ingestor (role/runner)   |
                        |  fetch + archive + summarize |
                        +-------------+---------------+
                                      | creates
                                      v
+---------------+      +-----------------------------+
|   Entity      |<-----|          Source              |
|               |      |  research/sources/YYYY/slug  |
|  companies/   |      +-------------+---------------+
|  products/    |                    | cited by
|  topics/      |                    v
|               |      +-----------------------------+
|  research/    |<-----|          Claim               |
|  entities/    | ref  |  research/claims/entity/slug |
|  {type}/slug  |      |                              |
+---------------+      |  verdict + confidence +      |
                       |  sources[] + as_of +         |
                       |  recheck_cadence_days        |
                       +-------------+---------------+
                                     |
                   +-----------------+-----------------+
                   v                 v                  v
            +------------+   +--------------+   +-------------+
            | Zod Schema |   | Citation     |   | Markdown    |
            | Validation |   | Check        |   | Lint        |
            | (build)    |   | (CI)         |   | (CI)        |
            +------+-----+   +------+-------+   +------+------+
                   +------------------+------------------+
                                      v
                       +-----------------------------+
                       |   Astro Build -> dist/      |
                       |   GitHub Pages deploy       |
                       |   dangerousrobot.org        |
                       +-----------------------------+

RELATIONSHIPS:
  Claim --references--> Entity   (claim.entity = "{type}/{slug}")
  Claim --cites-------> Source[] (claim.sources = ["{yyyy}/{slug}"])
  Source -- stands alone, shared across claims
  Entity -- stands alone, referenced by claims
```

---

## 2. Glossary

### Research Objects

The three core content types that make up the research archive.

| Term | What it is | Lives at |
|---|---|---|
| **Entity** | A stable subject (company, product, or topic) that claims are about | `research/entities/{type}/{slug}.md` |
| **Claim** | A single factual assertion with a verdict, confidence, evidence links, and recheck schedule | `research/claims/{entity-slug}/{claim-id}.md` |
| **Source** | A citable reference -- "cite once, reference many" | `research/sources/{yyyy}/{slug}.md` |

### Research Object Fields

| Term | On | Meaning |
|---|---|---|
| **Verdict** | Claim | Assessment: true, mostly-true, mixed, mostly-false, false, unverified |
| **Confidence** | Claim | Certainty level: high, medium, low |
| **Category** | Claim | Taxonomy: ai-safety, environmental-impact, product-comparison, etc. (8 total) |
| **Kind** | Source | Classification: report, article, documentation, dataset, blog, video, index |
| **as_of** | Claim | Date when verdict was last evaluated |
| **recheck_cadence_days** | Claim | Days between scheduled re-evaluations (default 60) |

### Roles (defined in AGENTS.md)

Roles describe *what* should happen. They can be filled by humans or automation.

| Role | Responsibility |
|---|---|
| **Research Lead** | Orchestrator; assigns tasks, never edits claims directly |
| **Ingestor** | Converts a URL into a source file |
| **Claim Updater** | Proposes verdict changes with rationale |
| **Citation Auditor** | Finds claims with zero sources, stale dates, broken references |
| **Page Builder** | Generates TypeScript data files for downstream consumption |

### Pipeline (automation code)

The pipeline implements roles as runnable code. Lives in `pipeline/` (not `agents/`, to avoid collision with AGENTS.md).

| Term | Meaning |
|---|---|
| **Runner/Worker** | A Python script or PydanticAI agent that implements a role |
| **Ingestor runner** | PydanticAI implementation of the Ingestor role |
| **Pipeline** | The collective automation: runners + CLI + shared utilities |

### Lifecycle

| Term | Meaning |
|---|---|
| **Queue** | Intake list of URLs/topics to process (`QUEUE.md`) |
| **Ingest** | Fetching a URL, archiving it, producing a source file |
| **Recheck** | Scheduled re-evaluation of a claim per `recheck_cadence_days` |
| **Submitted claim** | A claim proposed through public feedback (Phase 6), pending review |

### Governance Rules

Constraints and policies that govern content and process.

| Term | Meaning |
|---|---|
| **Content rules** | Constraints on research objects (e.g., summary word limits, citation requirements) |
| **Schema authority** | Zod in `content.config.ts` is the single source of truth for field shapes |
| **Plan lifecycle** | `drafts/` -> `plans/` -> `completed/` |
| **AGENTS.md** | Defines roles, content rules, and schema authority |

### Tests & Checks

"Tests" for unit/integration testing of code. "Checks" for CI quality verification of content.

| Term | Meaning |
|---|---|
| **Build validation** | Zod schemas enforced during `astro build` |
| **Citation check** | CI verification that source slugs in claims resolve to real files |
| **Markdown lint** | CI verification of Markdown formatting |
| **Unit/integration tests** | pytest tests for pipeline code (runners, models, tools) |

### Infrastructure

| Term | Meaning |
|---|---|
| **Content Collection** | Astro's system for loading research Markdown as typed data |
| **Zod schema** | TypeScript schema in `content.config.ts` defining valid frontmatter |
| **Pydantic model** | Python mirror of Zod schema, used by pipeline runners |

---

## 3. Naming Changes

### Confirmed changes

| Current | New | Scope | Rationale |
|---|---|---|---|
| `review_cadence_days` | `recheck_cadence_days` | Claim schema field | Distinguishes scheduled content re-evaluation from PR review |
| `agents/` (planned directory) | `pipeline/` | Directory for Python automation | Avoids collision with AGENTS.md; aligns with plan naming (`agent-pipeline.md`) |

### Vocabulary conventions

| Layer | Collective noun | Examples |
|---|---|---|
| Content | "research objects" | entity, claim, source |
| People/AI doing work | "roles" (defined in AGENTS.md) | Research Lead, Ingestor |
| Python automation | "pipeline" (code in `pipeline/`) | ingestor runner, consistency checker |
| Constraints/policies | "governance rules" | content rules, schema authority, plan lifecycle |
| Verification | "tests" (code) / "checks" (CI/content) | unit tests, citation check, build validation |

### No change needed

| Term | Why |
|---|---|
| `AGENTS.md` | Established convention for AI-readable project docs. Internally understood as roles + rules. |
| Claim (content type) vs. submitted claim (Phase 6) | Same concept at different lifecycle stages, not a naming conflict. |

---

## 4. Implementation Steps

### Step 1: Rename `review_cadence_days` to `recheck_cadence_days`

Build-critical (must update together):
- `src/content.config.ts:53` -- Zod schema definition
- `src/pages/claims/[...slug].astro:87` -- template rendering

No existing claim files set this field explicitly (all use the default), so no frontmatter edits needed.

Documentation:
- `AGENTS.md:14`
- `docs/architecture/research-workflow.md:26,51,93` (3 occurrences)
- `docs/architecture/content-model.md:63`
- `plans/TODO.md:22,31` (2 occurrences)

Auto-generated (no manual edit): `.astro/collections/claims.schema.json` rebuilds on `astro build`.

### Step 2: Use `pipeline/` instead of `agents/` in Phase 4 plans

The directory does not exist yet. Updates are plan-level only:
- `plans/agent-pipeline.md:35` (1 reference)
- `plans/BACKLOG.md:102` (1 reference)
- `plans/drafts/agent-pipeline-ingestor.md` (11 references)
- `plans/drafts/narrative-verdict-consistency.md` (6 references)

Also consider: rename Python package from `dangerous-robot-agents` to `dangerous-robot-pipeline` in draft pyproject.toml examples.

No CI workflows, .gitignore entries, or configs reference `agents/`.

### Step 3: Add glossary to `docs/architecture/glossary.md`

Extract the glossary (Section 2 of this plan) once promoted.

### Step 4: Apply "tests" vs "checks" language consistently

The repo is mostly consistent already. Two spots need clarification:
- `plans/TODO.md:34` -- "A test framework (Vitest) for scripted validators" should say "check framework" (content verification, not code testing)
- `plans/TODO.md:36` -- "inter-rater consistency testing" should say "validation" (verifying reasoning quality, not testing code)

CI workflows, npm scripts, and architecture docs already use "checks" correctly.

---

## Resolved Decisions

1. **Glossary location**: `docs/architecture/glossary.md`
2. **Research repo separation**: No impact on naming decisions now. Future concern only.
3. **`agent-pipeline.md` name**: Keep as-is. It describes the pipeline for executing agent roles -- the name is accurate.
