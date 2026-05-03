# Project Glossary

Canonical vocabulary for the dangerousrobot.org project. See also [AGENTS.md](../../AGENTS.md) for role definitions and content rules.

## How the system works

The system tracks four object types: **criteria** (reusable claim templates), **entities** (companies, products, sectors), **sources** (citable references, which can enter from outside or be produced inside the pipeline), and **claims** (verdicts about entities, generated from the other three; claims are the only output type). Anything to investigate enters a queue. Agents match incoming work to relevant items, gather and archive sources, propose a draft verdict, and evaluate it independently (the evaluation is open-loop: disagreements surface to the operator rather than being auto-resolved). The operator reviews and publishes the combined verdict, archives it, or sends it back for rework. Every step is recorded and reproducible. Small decisions are made by small models; large models are used only when the task demands it.

For the operator-facing v1 rules, see `AGENTS.md` § How the system works.

## Research Objects

| Term | What it is | Lives at |
|---|---|---|
| **Entity** | A stable subject (company, product, sector, or topic) that claims are about | `research/entities/{type}/{slug}.md` |
| **Claim** | A single factual assertion with a verdict, confidence, evidence links, and recheck schedule | `research/claims/{entity-slug}/{claim-id}.md` |
| **Source** | A citable reference -- "cite once, reference many" | `research/sources/{yyyy}/{slug}.md` |
| **Criterion** | A reusable claim template applied uniformly across entities | `research/templates.yaml` |

## Research Object Fields

| Term | On | Meaning |
|---|---|---|
| **Verdict** | Claim | Assessment: true, mostly-true, mixed, mostly-false, false, unverified, not-applicable |
| **Confidence** | Claim | Certainty level: high, medium, low |
| **Topics** | Claim, Criterion | Taxonomy array (1 to 3 slugs): ai-safety, environmental-impact, product-comparison, etc. (8 total). Field name is `topics` (renamed from singular `category` per `docs/plans/multi-topic.md`). |
| **Takeaway** | Claim | Optional reader-facing one-liner (≤200 chars) rendered under the verdict badge. Operators add this by hand during review in v1. |
| **Phase** | Claim | Optional pipeline-progress field, set by the Orchestrator while a claim is in flight; absent on terminal states. Enum: `researching`, `ingesting`, `analyzing`, `evaluating`. |
| **blocked_reason** | Claim | Optional reason field paired with `status: blocked`. Enum: `insufficient_sources`, `terminal_fetch_error`. |
| **Kind** | Source | Classification: report, article, documentation, dataset, blog, video, index |
| **source_type** | Source | Optional authority classification: `primary`, `secondary`, `tertiary`. Set by `pipeline/common/source_classification.py` during ingest. |
| **as_of** | Claim | Date when verdict was last evaluated |
| **recheck_cadence_days** | Claim | Days between scheduled re-evaluations (default 60) |
| **criteria_slug** | Claim | Optional back-reference linking a claim to the criterion template it was generated from |

## Verdict definitions

Operational rules for picking a verdict. Values match the enum in `src/content.config.ts`.

| Verdict | When to pick it |
|---|---|
| **true** | Cited sources support the claim in full; no material caveats or contradicting evidence. |
| **mostly-true** | The claim's main thrust is supported by sources. Deviations are scoped to caveats, minor factual drift, or outdated specifics that do not change the reader's takeaway. |
| **mixed** | A reader acting on the claim would be misled about at least one material element. Different parts of the claim are supported and contradicted by evidence. |
| **mostly-false** | The claim is misleading or wrong in its main thrust, though some narrow element is accurate. |
| **false** | Cited sources directly contradict the claim; no supporting evidence found. |
| **unverified** | Sources were sought but none directly **engage with** the claim's central assertion — they may circle the topic and surround it without dispositively answering it either way. Distinct from `mixed`, where sources *do* engage and contradict each other. Also distinct from "no sources cited," which is a lint error rather than a verdict. |
| **not-applicable** | The claim does not apply to this entity, either because the template targets a different entity type or because the question is semantically inapplicable to this specific entity. |

## Role / agent / CLI cross-walk

The same work is described by three vocabularies: **role** (what should happen, agnostic of who does it), **pipeline agent** (the runnable code that fills the role), and **CLI command** (the operator surface that triggers it). This single table maps all three for quick reference; the detailed responsibility/task tables follow below.

| Role | Pipeline agent | CLI surface |
|---|---|---|
| **Research Lead** | (human; no agent) | — |
| **Orchestrator** | `pipeline/orchestrator/` | the `dr` CLI itself; entry point for every pipeline command |
| **Router** | planned (`pipeline/router/`); deferred via [`triage-agent.md`](../plans/triage-agent.md) | — |
| **Researcher** | `pipeline/researcher/` | invoked by `dr claim-draft`, `dr claim-probe`, `dr claim-refresh`, `dr onboard` |
| **Ingestor** | `pipeline/ingestor/` | invoked by `dr claim-draft`, `dr claim-probe`, `dr claim-refresh`, `dr onboard`; standalone via `dr ingest` |
| **Analyst** | `pipeline/analyst/` | invoked by `dr claim-draft`, `dr claim-probe`, `dr claim-refresh`, `dr onboard` |
| **Evaluator** | `pipeline/auditor/` (directory rename to `pipeline/evaluator/` deferred to post-v1) | invoked by `dr claim-draft`, `dr claim-probe`, `dr claim-refresh`, `dr onboard`, `dr reassess` |
| **Linter** | `pipeline/linter/` (no LLM, no network) | `dr lint`; same code path runs in the `lint-content` CI job |
| (sidecar/status only) | (no agent) | `dr review` (per-claim sign-off + optional status flip), `dr publish` (bulk draft→published flip; bypasses individual reviewer recording) |

## Model-tier discipline

Agents default to the smallest model class that can defensibly handle the task; larger models are reserved for tasks that genuinely require them. Canonical statement: [`AGENTS.md` § How the system works](../../AGENTS.md). Each `.audit.yaml` sidecar records the per-agent model used in `models_used`, so the lineage of a published verdict is auditable. The concrete enforcement mechanism (instructions-only vs. config-level caps) is open — see Q4 in [`pre-launch-questions.md`](../pre-launch-questions.md).

## Roles

Roles describe *what* should happen. They can be filled by humans or automation. Defined in [AGENTS.md](../../AGENTS.md).

| Role | Responsibility |
|---|---|
| **Research Lead** | Assigns tasks, never edits claims directly |
| **Orchestrator** | Owns the claim lifecycle: advances `phase`, routes to `blocked` on threshold breach, manages queue (`pipeline/orchestrator/`) |
| **Router** | Dispatches small classifications; matches new sources to criteria/claims; triggers blocked routing on `< 4` sources; stale flagging (implementation deferred via `docs/plans/triage-agent.md`) |
| **Researcher** | Finds relevant URLs for a given claim topic. Internally orchestrates a 3-step pipeline (query planner → search executor → URL scorer), all tool-free by design, with effort controlled by `max_initial_queries`. Entity context (including `parent_company` when set) is injected into both the planner and scorer prompts. Each search candidate is classified with a `publisher_quality` label before scoring. |
| **Ingestor** | Converts a URL into a source file |
| **Analyst** | Proposes verdict and narrative given a claim and its sources |
| **Evaluator** | Produces an independent evaluation of the analyst's output |

## Workflow

The workflow implements roles as runnable code under `pipeline/`. Per-agent package paths are in the [Role / agent / CLI cross-walk](#role--agent--cli-cross-walk) above; tasks are listed in [Agent tasks](#agent-tasks) below.

| Term | Meaning |
|---|---|
| **Pipeline** | The collective automation: agents + CLI + shared utilities (`pipeline/`) |

## Pipeline mechanisms

Implementation-level concepts that surface in operator workflows and audit artifacts.

| Term | Meaning |
|---|---|
| **Audit sidecar** / `.audit.yaml` | Paired YAML file at the same path as a claim `.md`. Records the pipeline run (model, agents), sources consulted, analyst/evaluator verdicts, and human review state. Merged into the claim's `audit` field by the `claims-with-audit` content loader. Schema in [content-model.md § Claim Audit Sidecar](content-model.md#claim-audit-sidecar). |
| **`human_review`** | Sub-object in the audit sidecar written by `dr review` and `dr publish`. Records `reviewed_at`, `reviewer`, `notes`, and `pr_url`. Drives the "Reviewed" / "Unreviewed" badge on the rendered claim. |
| **Threshold gate** | Post-ingest check in the orchestrator: if fewer than four usable sources are available, the claim is halted with `status: blocked` and a `blocked_reason`, and the Analyst is not invoked. (`pipeline/orchestrator/pipeline.py`) |
| **Blocklist** | Domain-level filter applied to candidate URLs before ingest. Lives at `research/blocklist.yaml`; consumed by the orchestrator. |
| **Checkpoint** | Human-in-the-loop hook implementing the `CheckpointHandler` protocol. v1 checkpoints: `review_sources`, `review_disagreement`, `review_onboard`. Enabled with `--interactive`; tests use `AutoApproveCheckpointHandler`. |
| **Linter** (the package) | `pipeline/linter/` -- Python package that implements the static checks invoked by `dr lint` and the `lint-content` CI job. Distinct from the `dr lint` operator command. |
| **`max_initial_queries`** | Effort lever on `VerifyConfig` controlling how many search queries the Researcher's query planner generates per claim. The orchestrator hard-truncates the planner's output to this count before executing searches. |
| **`llm_concurrency`** | Pipeline-level cap on concurrent LLM calls, set on `VerifyConfig` and enforced via `asyncio.Semaphore` created at each top-level entry point (`verify_claim`, `research_claim`, `onboard_entity`). Bounds peak LLM parallelism during `dr onboard`, which runs multiple claim templates concurrently. |
| **`publisher_quality`** | Pre-ingest domain quality label on `SearchCandidate`: `primary`, `secondary`, `tertiary`, or `forum`. Classified from the URL hostname by `pipeline/common/publisher_quality.py` during `execute_searches`; injected into the scorer prompt as a tiebreaker signal. Not persisted. Contrast with `source_type` (post-ingest, written to source frontmatter). |

## Agent tasks

| Agent | Tasks |
|---|---|
| **Orchestrator** | Advance claim through `phase`; route to `blocked` on threshold breach; manage queue |
| **Router** | (Documented; implementation deferred) Match new sources back to criteria/claims; small classification calls; threshold-trigger to blocked; stale flagging |
| **Researcher** | Find sources for a claim |
| **Ingestor** | Fetch URL; extract content; classify source kind; produce source file |
| **Analyst** | Propose draft verdict; write narrative; cite sources |
| **Evaluator** | Produce an independent evaluation; flag disagreements |

## Object lifecycle (general)

Applies to criteria, entities, and sources.

| State | Meaning |
|---|---|
| **proposed** | Object exists, not yet vetted/active |
| **active** | Object is in use |
| **flagged** | Needs review (stale, COI, broken, contested) |
| **retired** | No longer in use |

## Lifecycle

Claim states. Schema source of truth: `src/content.config.ts` § claims (`status`, `phase`, `blocked_reason`).

| State | Meaning | Where | Schema field |
|---|---|---|---|
| **queued** | Intake recorded, pipeline not yet run | `QUEUE.md` | (no schema field; `QUEUE.md` only) |
| **in-progress** | Pipeline is working it | (transient frontmatter) | `phase` ∈ {researching, ingesting, analyzing, evaluating} |
| **blocked** | Pipeline halted before Analyst: < 4 usable sources or terminal fetch error | `status: blocked` + `blocked_reason` | `status: blocked`, `blocked_reason` ∈ {insufficient_sources, terminal_fetch_error} |
| **draft** | Pipeline produced a draft verdict; awaiting review | `status: draft` | `status: draft` |
| **published** | Operator approved | `status: published` | `status: published` |
| **archived** | Retired | `status: archived` | `status: archived` |

## Lifecycle vocabulary

Operator-facing pipeline-step terms. These describe pipeline mechanics, not claim states.

| Term | Meaning |
|---|---|
| **Queue** | Intake list of URLs/topics to process (`QUEUE.md`) |
| **Ingest** | Fetching a URL, archiving it, producing a source file. CLI: `dr ingest`. |
| **Onboard** | Adding a new entity to the archive via `dr onboard`; runs light research, screens templates, then loops `verify_claim` per applicable template. See [onboarding.md](onboarding.md) |
| **Claim-probe** | Dry-run the full pipeline (Researcher → Ingestor → Analyst → Evaluator) for a single claim; no disk writes. CLI: `dr claim-probe`. |
| **Claim-draft** | Run the full pipeline and write outputs to disk (sources, claim file with `status: draft`, audit sidecar); no `criteria_slug`. CLI: `dr claim-draft`. |
| **Claim-refresh** | Re-run the full pipeline on an existing template-backed claim file (requires `criteria_slug`). CLI: `dr claim-refresh`. |
| **Claim-promote** | Promote an ad-hoc claim draft to a reusable template entry in `research/templates.yaml`. Edits only the templates file; does not invoke any pipeline agent. CLI: `dr claim-promote`. |
| **Reassess** | Re-run the Evaluator against a published claim's current sources to flag verdicts that may no longer hold. CLI: `dr reassess`. |
| **Lint** | Static content checks (no LLM, no network): missing required fields, orphaned claims, stale `next_recheck_due`. CLI: `dr lint`. Backed by `pipeline/linter/`. |
| **Review** | Record human sign-off in the audit sidecar; optionally flip status. `dr review` (record only); `dr review --approve` (draft → published); `dr review --archive` (published → archived; also accepts blocked → archived). |
| **Publish** | Bulk draft → published flip without recording an individual reviewer. CLI: `dr publish`. Sidecar gets `[auto-publish]` notes; resulting claims render as "Unreviewed" until a later `dr review` writes a reviewer in. |
| **Recheck** | Scheduled re-evaluation of a claim per `recheck_cadence_days` (manual today; no scheduler) |

### Planned terms

| Term | Meaning |
|---|---|
| **Submitted claim** | A claim proposed through public feedback (planned feature, pending public-participation work), pending review |

## Criterion vocabularies

Some criterion templates use controlled vocabularies for substitutions in their `text` (e.g. `STRUCTURE`, `JURISDICTION`). The authoritative lists live alongside each template in `research/templates.yaml` under `vocabulary:`. Definitions below are for terms whose meaning is not self-evident from the value list.

### Frontier-scale

Used by the `excludes-frontier-models` criterion. A model is **frontier-scale** if it meets either criterion at time of release:

- Top-5 performance on major benchmarks (MMLU, HumanEval, etc.)
- Greater than 100B parameters

This definition is a moving target. When evaluating a claim, the narrative should state which criterion was applied and the date of assessment.

## Governance Rules

| Term | Meaning |
|---|---|
| **Content rules** | Constraints on research objects (e.g., summary word limits, citation requirements) |
| **Schema authority** | Zod in `content.config.ts` is the single source of truth for field shapes |
| **Plan lifecycle** | `docs/plans/drafts/` -> `docs/plans/` -> `docs/plans/completed/` |
| **AGENTS.md** | Defines roles, content rules, and schema authority |

## Vocabulary Layers

| Layer | Collective noun | Examples |
|---|---|---|
| Content | "research objects" | entity, claim, source |
| People/AI doing work | "roles" (defined in AGENTS.md) | Research Lead, Ingestor |
| Python automation | "pipeline" (code in `pipeline/`) | researcher agent, ingestor agent, analyst agent, evaluator agent, orchestrator (Implicit in `pipeline/orchestrator/`; named) and router agent (Documented; implementation deferred) |
| Constraints/policies | "governance rules" | content rules, schema authority, plan lifecycle |
| Verification | "tests" (code) / "checks" (CI/content) | unit tests, citation check, build validation |

## Tests and Checks

| Term | Meaning |
|---|---|
| **Build validation** | Zod schemas enforced during `astro build` |
| **Citation check** | CI verification that source slugs in claims resolve to real files |
| **Markdown lint** | CI verification of Markdown formatting |
| **Unit/integration tests** | pytest tests for pipeline code (runners, models, tools) |

## Infrastructure

| Term | Meaning |
|---|---|
| **Content Collection** | Astro's system for loading research Markdown as typed data |
| **Zod schema** | TypeScript schema in `content.config.ts` defining valid frontmatter |
| **Pydantic model** | Python mirror of Zod schema, used by pipeline runners |
