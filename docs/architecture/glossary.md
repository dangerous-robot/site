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
| **Topics** | Claim, Criterion | Taxonomy array (1 to 3 slugs): ai-safety, environmental-impact, product-comparison, etc. (8 total) |
| **Kind** | Source | Classification: report, article, documentation, dataset, blog, video, index |
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
| **unverified** | Sources were sought but none are sufficient to judge the claim in either direction. Distinct from "no sources cited," which is a lint error rather than a verdict. |
| **not-applicable** | The claim does not apply to this entity, either because the template targets a different entity type or because the question is semantically inapplicable to this specific entity. |

## Roles

Roles describe *what* should happen. They can be filled by humans or automation. Defined in [AGENTS.md](../../AGENTS.md).

| Role | Responsibility |
|---|---|
| **Research Lead** | Assigns tasks, never edits claims directly |
| **Orchestrator** | Owns the claim lifecycle: advances `phase`, routes to `blocked` on threshold breach, manages queue (`pipeline/orchestrator/`) |
| **Router** | Dispatches small classifications; matches new sources to criteria/claims; triggers blocked routing on `< 2` sources; stale flagging (implementation deferred via `docs/plans/triage-agent.md`) |
| **Researcher** | Finds relevant URLs for a given claim topic |
| **Ingestor** | Converts a URL into a source file |
| **Analyst** | Proposes verdict and narrative given a claim and its sources |
| **Evaluator** | Produces an independent evaluation of the analyst's output |

## Workflow

The workflow implements roles as runnable code. Lives in `pipeline/`.

| Term | Meaning |
|---|---|
| **Orchestrator** | Owns the claim lifecycle: advances `phase`, routes to `blocked` on threshold breach, manages queue. Implicit in `pipeline/orchestrator/`; named role documented (`pipeline/orchestrator/`) |
| **Router** | Matches new sources to criteria/claims; small classification calls; threshold-trigger to blocked; stale flagging. Documented; implementation deferred (`pipeline/router/` planned) |
| **Researcher agent** | Takes claim text, returns relevant URLs (`pipeline/researcher/`) |
| **Ingestor agent** | Takes a URL, produces a source file (`pipeline/ingestor/`) |
| **Analyst agent** | Takes sources + claim, produces verdict + narrative (`pipeline/analyst/`) |
| **Evaluator agent** | Independent evaluation of the analyst's output (`pipeline/auditor/` in v1; directory rename to `pipeline/evaluator/` deferred to post-v1) |
| **Pipeline** | The collective automation: agents + CLI + shared utilities |

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

Claim states.

| State | Meaning | Where | Schema status |
|---|---|---|---|
| **queued** | Intake recorded, pipeline not yet run | `QUEUE.md` | (no schema field; `QUEUE.md` only) |
| **in-progress** | Pipeline is working it; `phase` ∈ {researching, ingesting, analyzing, evaluating} | (transient) | (v1: schema only has draft / published / archived) |
| **blocked** | Pipeline halted: insufficient sources (< 2) or terminal fetch error | `status: draft` + reason field | (v1: schema only has draft / published / archived) |
| **drafted** | Pipeline produced a draft verdict; awaiting review | `status: draft` | (in schema) |
| **published** | Operator approved | `status: published` | (in schema) |
| **archived** | Retired | `status: archived` | (in schema) |

## Lifecycle vocabulary

Operator-facing pipeline-step terms. These describe pipeline mechanics, not claim states.

| Term | Meaning |
|---|---|
| **Queue** | Intake list of URLs/topics to process (`QUEUE.md`) |
| **Ingest** | Fetching a URL, archiving it, producing a source file |
| **Onboard** | Adding a new entity to the archive via `dr onboard`; see [onboarding.md](onboarding.md) |
| **Recheck** | Scheduled re-evaluation of a claim per `recheck_cadence_days` |
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
