# Project Glossary

Canonical vocabulary for the dangerousrobot.org project. See also [AGENTS.md](../../AGENTS.md) for role definitions and content rules.

## How the system works

The system tracks four object types: **criteria** (a registry of claim sentences, each with a `grading_rule`), **entities** (products and subjects are what claims are about; companies are read-only parent records), **sources** (citable references, which can enter from outside or be produced inside the pipeline), and **claims** (verdicts about entities, generated from the other three; claims are the only output type). Anything to investigate enters through a `dr draft` command. Agents match incoming work to relevant items, gather and archive sources, propose a draft verdict, and evaluate it independently (the evaluation does not feed back into the Analyst; a verdict disagreement is settled by a blind tie-breaker, and every split, abandoned, recovered or partial run leaves a finding). The operator reviews and publishes the combined verdict, archives it, or sends it back for rework. Every step is recorded and reproducible. Small decisions are made by small models; large models are used only when the task demands it.

For the operator-facing v1 rules, see `AGENTS.md` § How the system works.

## Research Objects

| Term | What it is | Lives at |
|---|---|---|
| **Entity** | A stable thing that claims are about (a product or a subject). A company is a read-only parent record that feeds first-party source matching, not a claim target | `research/entities/{type}/{slug}.md` |
| **Claim** | A single factual assertion with a verdict, confidence, evidence links, and recheck schedule | `research/claims/{entity-slug}/{claim-id}.md` |
| **Source** | A citable reference -- "cite once, reference many" | `research/sources/{yyyy}/{slug}.md` |
| **Criterion** | A registry entry in `research/templates.yaml`: a claim sentence applied uniformly across entities, with a `grading_rule` that the Analyst and the Evaluator both receive | `research/templates.yaml` |

## Research Object Fields

| Term | On | Meaning |
|---|---|---|
| **Verdict** | Claim | Assessment: true, mostly-true, mixed, mostly-false, false, unverified, not-applicable |
| **Confidence** | Claim | Certainty level: high, medium, low |
| **Topics** | Claim, Criterion | Taxonomy array (1 to 3 slugs): ai-safety, environmental-impact, product-comparison, etc. (8 total). Field name is `topics` (renamed from singular `category` per `docs/plans/completed/multi-topic.md`). |
| **Takeaway** | Claim | Optional reader-facing one-liner (≤200 chars) rendered under the verdict badge. Operators add this by hand during review in v1. |
| **seo_title** | Claim | Short title for the rendered page's `<title>` tag (≤42 chars, leaving room for ` - Dangerous Robot`). The Analyst writes one on every generated claim; a forced rewrite (`dr draft --claim --force`) keeps an operator's `seo_title` (one that differs from the analyst's last, recorded in the audit sidecar's `analyst_record`, whose `title` records the claim's statement) while the claim's statement is unchanged, and keeps an operator's `cap_rationale` (likewise told apart through `analyst_record`) until the operator edits it, even when `verification_level` or `confidence` changes. The schema marks it optional so hand-written legacy claims still validate. Falls back to `title` when absent. |
| **Phase** | Claim | Optional pipeline-progress field, set by the Orchestrator while a claim is in flight; absent on terminal states. Enum: `researching`, `ingesting`, `analyzing`, `evaluating`. |
| **Kind** | Source | Classification: report, article, documentation, dataset, blog, video, index, paper |
| **source_type** | Source | Optional authority classification: `primary`, `secondary`, `tertiary`. Set by `pipeline/common/source_classification.py` during ingest. |
| **as_of** | Claim | Date when verdict was last evaluated |
| **recheck_cadence_days** | Claim | Days between scheduled re-evaluations (default 60). Carried forward from the existing claim by the writer; the default is not written. |
| **next_recheck_due** | Claim | Date the claim is next due for `dr recheck`: `as_of` plus `recheck_cadence_days`. The writer sets it on every claim write. A claim with none is due when `as_of` plus the cadence has passed. |
| **criteria_slug** | Claim | Optional back-reference linking a claim to the criterion it was drafted from (`dr draft --criterion`) or had attached (`dr draft --claim --criterion`); the publish gate |
| **statement** | Claim | The sentence the loop re-runs and the Evaluator grades; `title` equals it. For a criterion-backed claim, the criterion's text rendered once with the entity name; for an ad hoc claim, the operator's sentence. |
| **founded** | Entity (company, product) | Year the entity was founded (companies) or first launched (products). Optional integer (1800–current year). Subjects ignore this field. Hand-written in the entity file; surfaced on the entity page's Facts subsection and threaded into analyst and scorer prompts. |

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
| **Orchestrator** | `pipeline/orchestrator/` (commands and the one writer); the research run itself is `pipeline/loop/` | the `dr` CLI itself; entry point for every pipeline command |
| **Router** | planned (`pipeline/router/`); v1 surface shipped via [`triage-agent.md`](../plans/completed/triage-agent.md), full implementation tracked in `docs/UNSCHEDULED.md` § Router | — |
| **Researcher** | `pipeline/researcher/` | invoked by `dr draft` |
| **Ingestor** | `pipeline/ingestor/` | invoked by `dr draft`; one URL alone via `dr draft --source <url>` |
| **Analyst** | `pipeline/analyst/` | invoked by `dr draft`; alone over a claim's stored sources via `dr draft --claim <ref> --rerun analyst` |
| **Evaluator** | `pipeline/auditor/` (directory rename to `pipeline/evaluator/` deferred to post-v1) | invoked by `dr draft`; alone over a claim's stored sources via `dr draft --claim <ref> --rerun evaluator` |
| **Tie-breaker** | `pipeline/loop/tiebreaker/` | invoked by `dr draft` (including `--rerun evaluator`) on a disagreement; model slot `--tiebreaker-model` |
| **Restater** | `pipeline/loop/restater/` | invoked by `dr draft` on a weak or tie-broken verdict; model slot `--restater-model`; a pick is run with `dr draft --restates <claim-ref> --pick <n>` |
| **Linter** | `pipeline/linter/` (no LLM, no network) | `dr lint`; same code path runs in the `lint-content` CI job |
| (sidecar/status only) | (no agent) | `dr review` (the walkthrough of drafts awaiting sign-off, each with its review packet; per-claim sign-off + optional status flip), `dr findings` (lists, counts and closes the findings file; `dr findings --replay` is not agent-free: it runs the full loop, see **Replay** below) |

## Model-tier discipline

Agents default to the smallest model class that can defensibly handle the task; larger models are reserved for tasks that genuinely require them. Canonical statement: [`AGENTS.md` § How the system works](../../AGENTS.md). Each `.audit.yaml` sidecar records the per-agent model used in `models_used`, so the lineage of a published verdict is auditable; it names the tie-breaker when that agent ran. The concrete enforcement mechanism is open: option (b), per-agent tier caps in config, is the chosen direction — stubbed at [`plans/deferred/model-tier-enforcement_stub.md`](../plans/deferred/model-tier-enforcement_stub.md).

## Roles

Roles describe *what* should happen. They can be filled by humans or automation. Defined in [AGENTS.md](../../AGENTS.md).

| Role | Responsibility |
|---|---|
| **Research Lead** | Assigns tasks, never edits claims directly |
| **Orchestrator** | Owns the claim lifecycle: advances `phase`, stops a run on threshold breach (nothing is written) (`pipeline/orchestrator/`) |
| **Router** | Dispatches small classifications; matches new sources to criteria/claims; stale flagging (v1 surface shipped via `docs/plans/completed/triage-agent.md`; full implementation tracked in `docs/UNSCHEDULED.md` § Router) |
| **Researcher** | Finds relevant URLs for a given claim topic. Internally orchestrates a 3-step pipeline (query planner → search executor → URL scorer), all tool-free by design, with effort controlled by `max_initial_queries`. The planner always adds a counter-evidence sub-question (what would falsify the claim) with its own query. Entity context (including `parent_company` when set, used for matching only) is injected into both the planner and scorer prompts. Each search candidate is classified with a `publisher_quality` label before scoring. |
| **Ingestor** | Converts a URL into a source file |
| **Analyst** | Proposes verdict and narrative given a claim and its sources |
| **Evaluator** | Grades the claim statement against the sources, independent of the analyst's verdict |
| **Tie-breaker** | Grades the claim statement blind when the Analyst and Evaluator verdicts differ; the one agent above them that may use the frontier tier |
| **Restater** | Proposes ranked restatements of a weak or tie-broken claim from the run's consulted sources and the source archive; never rewrites the claim |

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
| **`human_review`** | Sub-object in the audit sidecar written by `dr review`. Records `reviewed_at`, `reviewer`, `notes`, and `pr_url`, plus `verdict_override` when `dr review` approves a verdict that differs from the pipeline verdict (`audit.pipeline_verdict`, which the tie-breaker can set against the Analyst). Drives the "Reviewed" / "Unreviewed" badge on the rendered claim. |
| **Threshold gate** | Post-ingest check in the loop: if fewer than four usable sources are available, the run stops with no verdict (the loop's `blocked_reason`, never written to a claim), the Analyst is not invoked, and nothing is written (no claim, no source file, no sidecar). (`pipeline/loop/run.py`) |
| **Blocklist** | Domain-level filter applied to candidate URLs before ingest. Lives at `research/blocklist.yaml`; consumed by the orchestrator. |
| **Tie-breaker** | Agent in `pipeline/loop/tiebreaker/` that runs only when the Analyst and Evaluator verdicts differ. It gets the Evaluator's blind bundle (no verdicts) with a higher thinking budget, on the `--tiebreaker-model` slot (the run's `--model` unless `DR_TIEBREAKER_MODEL` is set). A verdict matching either side wins; a three-way split takes the weakest by strength. The sidecar records `tiebreaker_*`, `pipeline_verdict` and `rule_applied`. |
| **Restater** | Agent in `pipeline/loop/restater/` that runs after the verdict is settled, only when the pipeline verdict is `unverified`, `mixed` or `not-applicable` or the tie-breaker ran. It reads the run's consulted sources plus the best-matching sources in `research/sources/`, never a thesis to prove, and returns up to five candidate statements ranked by how decisively the evidence settles each in either direction. Its model slot is `--restater-model` (falls back to `--auditor-model`). A failure writes the claim without a `restatement` block and records a `partial` finding. Schema in [content-model.md § Claim Audit Sidecar](content-model.md#claim-audit-sidecar). |
| **Finding** | One YAML record per abandoned, recovered, split or partial run (a partial run wrote the claim but its restater failed), or per half-claim at `research/findings/<yyyy>/<run-id>.yaml`: the claim spec, config, step, rule, error, attempts and outcome; a replay's own finding also carries `replays`, the run id of the finding it replayed. Listed by `dr findings`; `dr lint` ignores the directory. |
| **Replay** | `dr findings --replay [--finding <id>]`: re-runs an open abandoned or half-claim finding's recorded claim spec and config through the loop, after a pipeline change. A success closes the finding (`closed.by: replay`); a failure records a new finding whose `replays` key names the old one, which stays open. A replay writes what the original command would have: a draft for `dr draft`, a pending draft for `dr recheck`. A `dr draft --rerun analyst\|evaluator` finding is skipped: a replay is a full run. |
| **Half-claim** | What a writer crash leaves: a claim without a sidecar, or a subject record without a claim. `dr findings` lists them; nothing deletes them automatically. |
| **Linter** (the package) | `pipeline/linter/` -- Python package that implements the static checks invoked by `dr lint` and the `lint-content` CI job. Distinct from the `dr lint` operator command. |
| **`max_initial_queries`** | Effort lever on `VerifyConfig` controlling how many search queries the Researcher's query planner generates per claim. The orchestrator hard-truncates the planner's output to this count before executing searches. Default: 7. |
| **`llm_concurrency`** | Pipeline-level cap on concurrent LLM calls, set on `VerifyConfig` and enforced via `asyncio.Semaphore` created at each top-level entry point (`run` in `pipeline/loop/`; `rerun` creates none). Bounds peak LLM parallelism within one claim run. |
| **`publisher_quality`** | Pre-ingest domain quality label on `SearchCandidate`: `primary`, `secondary`, `tertiary`, or `forum`. Classified from the URL hostname by `pipeline/common/publisher_quality.py` during `execute_searches`; injected into the scorer prompt as a tiebreaker signal. Not persisted. Contrast with `source_type` (post-ingest, written to source frontmatter). |
| **`research_origins`** | List of dispatch types the Researcher attempts for a claim. Default: `["tavily", "arxiv"]`. Web origins (`tavily`) always fire; academic origins (`arxiv`, and later `s2`/`openalex`) fire only when the claim's topics intersect `ACADEMIC_TOPICS` (see row below). Mirrors the schema enum on `audit.sources_consulted[].acquisition.origin`. Distinct from `search_backend`, which selects the API powering the web origin. |
| **`search_backend`** | Which API powers the web (non-academic) leg of `research_origins`. Today `tavily` (default) or `brave`. Read once at `VerifyConfig` construction from `RESEARCH_SEARCH_BACKEND`; unknown values fall back to `brave` with a warning. Distinct from `research_origins`, which lists dispatch types. |
| **`ACADEMIC_TOPICS`** | Frozen set of topic slugs that activate academic-API dispatch (currently `ai-safety`, `environmental-impact`, `industry-analysis`). Defined in `pipeline/common/models.py` as the single source of truth used by `_select_research_origins`. |
| **Archive recovery chain** | Ingestor lookup waterfall when a URL's live fetch fails or no `archived_url` is yet known: archive.org TimeGate (nearest capture) → a HEAD on that capture's replay, which must answer HTTP 200 for the same page (path case counts; a captured redirect counts only while it stays on the page) → the CDX index's newest 200 capture when the TimeGate capture fails that check → archive.org Save Page Now (capture on miss, checked the same way). A capture that fails every step is never recorded. Per-URL outcomes are recorded as `acquisition.recovered_via ∈ {archive_org}` on the audit sidecar's `sources_consulted[]`. Implemented in `pipeline/ingestor/tools/wayback.py`. |

## Agent tasks

| Agent | Tasks |
|---|---|
| **Orchestrator** | Advance claim through `phase`; stop a run on threshold breach (nothing is written) |
| **Router** | (Documented; implementation deferred) Match new sources back to criteria/claims; small classification calls; stale flagging |
| **Researcher** | Find sources for a claim |
| **Ingestor** | Fetch URL; extract content; classify source kind; produce source file |
| **Analyst** | Propose draft verdict; write narrative; cite sources |
| **Evaluator** | Grade the claim statement against the sources (the narrative is context, not the thing graded); flag disagreements |
| **Tie-breaker** | Grade the claim statement blind, only on a disagreement; return a third verdict that settles it by rule |
| **Restater** | Propose ranked restatement candidates for a weak or tie-broken verdict, each with the verdict the pool would give it, the quoted passages it relies on and why the original is weak (`why_unverified`) |

## Object lifecycle (general)

Applies to criteria, entities, and sources.

| State | Meaning |
|---|---|
| **proposed** | Object exists, not yet vetted/active |
| **active** | Object is in use |
| **flagged** | Needs review (stale, COI, broken, contested) |
| **retired** | No longer in use |

## Lifecycle

Claim states. Schema source of truth: `src/content.config.ts` § claims (`status`, `phase`). Any other `status` value is a `dr lint` error (`invalid-claim-status`).

| State | Meaning | Where | Schema field |
|---|---|---|---|
| **in-progress** | Pipeline is working it | (transient frontmatter) | `phase` ∈ {researching, ingesting, analyzing, evaluating} |
| **draft** | Pipeline produced a draft verdict; awaiting review | `status: draft` | `status: draft` |
| **published** | Operator approved | `status: published` | `status: published` |
| **archived** | Retired | `status: archived` | `status: archived` |

## Lifecycle vocabulary

Operator-facing pipeline-step terms. These describe pipeline mechanics, not claim states.

| Term | Meaning |
|---|---|
| **Ingest** | Fetching a URL, archiving it, producing a source file. CLI: `dr draft --source <url>` for one page alone; the loop ingests the pages a claim run finds. |
| **Draft dry run** | Run the full pipeline (Researcher → Ingestor → Analyst → Evaluator) for a single claim; no disk writes and no archive.org capture. CLI: `dr draft --dry-run --entity <ref> "<sentence>"`. |
| **Draft** | Run the full pipeline and write outputs to disk (sources, claim file with `status: draft`, audit sidecar); no `criteria_slug`. A run with no verdict (too few usable sources, or an analyst failure) writes nothing. CLI: `dr draft --entity <ref> "<sentence>"` or `dr draft --subject <slug> "<sentence>"` (which also writes the subject record when missing). |
| **Draft from a criterion** | Render a criterion's sentence once with the entity name, store it as `statement`, and run the loop; the claim takes `criteria_slug` and the criterion's topics and is written to `<entity-dir>/<criteria_slug>.md`. CLI: `dr draft --criterion <slug> --entity <ref>`. |
| **Forced rerun** | Re-run an existing draft claim's stored `statement` and write back to the same path, keeping `criteria_slug`. A draft only: a published or archived claim reruns with `dr recheck --claim <ref>`. CLI: `dr draft --claim <ref> --force`. |
| **Attach a criterion** | Add a new criterion to `research/templates.yaml` from an ad hoc draft and set the draft's `criteria_slug`. Runs no pipeline agent and moves no file. CLI: `dr draft --claim <ref> --criterion <new-slug>`. |
| **Restatement** | The ranked candidate statements the Restater writes into a weak or tie-broken draft's sidecar (the `restatement` block): each carries the verdict the pool would give it. The original stays as drafted. A pick is recorded as `restatement.picked`; approving or archiving the original removes the block, except while a pick is recorded and no claim restates the original yet. |
| **Restated claim** | A new ad hoc claim run from a picked candidate with `dr draft --restates <claim-ref> --pick <n>`, linked to the original by the sidecar key `restates:`. It is a second run and needs its own sign-off. |
| **Agent rerun** | Re-run one agent over a claim's stored sources, with no search and no ingest. CLI: `dr draft --claim <ref> --rerun analyst` (the sidecar's `audit` becomes null until the Evaluator grades the new analysis) or `--rerun evaluator` (grades the stored statement; the tie-breaker sets the claim's verdict when it settles on another one). A draft is rewritten in place; a published or archived claim gets a pending draft. |
| **Lint** | Static content checks (no LLM, no network): missing required fields, orphaned claims, stale `next_recheck_due`. CLI: `dr lint`. Backed by `pipeline/linter/`. |
| **Review** | Record human sign-off in the audit sidecar; optionally flip status. `dr review` with no arguments walks the drafts awaiting sign-off, printing each one's review packet before the key prompt. `dr review --claim <ref>` (record only); `--approve` (draft → published); `--archive` (published → archived). `--format text\|json` prints packets and writes nothing. Every sign-off needs a person at a terminal: stdin must be a tty and the claim slug is typed back before the write. |
| **Review packet** | What `dr review` shows for a draft, in four parts: the verdict chain (the claim, the Analyst, the Evaluator, the tie-breaker when one ran, the pipeline's verdict and the rule that set it); every consulted source with each key quote beside its page passage and the automated check's result; source independence, including `shared_with` (other consulted sources from the same publisher host or newswire origin); the searches and the rejected candidates with the scorer's reason. In the walkthrough the verdict chain and header facts print last, directly above the key prompt. |
| **Recheck** | Re-evaluation of a published claim once `next_recheck_due` has passed. CLI: `dr recheck` (`--due`, `--claim <ref>`, `--sources <id>...`). The rerun is written as a pending draft under `research/pending/` while the live claim stays up; `dr review --approve` promotes it. A person starts it today; no scheduler runs it. |
| **Pending draft** | A recheck's (or a `--rerun` of a published or archived claim's) result: claim plus audit sidecar at `research/pending/<entity-dir>/<claim-slug>.md`, outside the site's claims loader. `dr review` lists it under the live claim's ref. |

### Planned terms

| Term | Meaning |
|---|---|
| **Submitted claim** | A claim proposed through public feedback (planned feature, pending public-participation work), pending review |

## Criterion vocabularies

Some criteria carry controlled vocabularies (e.g. `STRUCTURE`, `JURISDICTION`) in `research/templates.yaml` under `vocabulary:`. They are site-only: the home page bolds their terms and the matrix check reads them, and the pipeline ignores them (no slot is rendered into a claim's `statement`). Definitions below are for terms whose meaning is not self-evident from the value list.

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
