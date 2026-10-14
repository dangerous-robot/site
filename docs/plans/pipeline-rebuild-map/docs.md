# Pipeline map: docs that describe the pipeline

Phase 1 (Challenge) reader output for the research pipeline rebuild. Facts carry `file:line` as of the working tree on 2026-10-14 (HEAD `40ba781`). Paths are relative to the repo root. "Not found" means the thing is not on disk.

Scope: AGENTS.md, `docs/architecture/*.md`, `pipeline/README.md`, `docs/runbook.md`, `docs/plans/claim-restate.md`, `docs/plans/drafts/*_stub.md`, `.claude/skills/release-triage/SKILL.md`, `scripts/release-gate/*.py`. Purpose: when a spike removes a command, pathway or file, this map says which sentences must change.

## 1. The live command list (control for every doc)

`.venv/bin/dr --help` (run 2026-10-14) groups commands as `_COMMAND_GROUPS` does (`pipeline/orchestrator/cli.py:119-126`):

| Group | Commands (as `--help` prints them) |
|---|---|
| Read-only (dry run, no files written) | `lint`, `stats`, `step-research`, `step-ingest`, `step-analyze`, `step-audit`, `claim-probe` |
| Creates or overwrites claim files | `onboard`, `claim-draft`, `claim-refresh`, `claim-promote` |
| Modifies existing files in place | `entity-enrich`, `publish`, `review`, `review-queue` |
| Other | `wayback-backfill` |

Hidden commands (not in `--help`): `reassess` (`cli.py:1726`, hidden alias of `step-audit`) and `ingest` (`cli.py:1746`, hidden alias of `step-ingest`).

Group options on `dr`: `--verbose`, `--model`, `--researcher-model`, `--analyst-model`, `--auditor-model`, `--ingestor-model` (from `--help`). Per-command `--interactive/--no-interactive` exists on `claim-probe` (`cli.py:884`), `claim-draft` (`cli.py:939`), `claim-refresh` (`cli.py:1039`) and `onboard` (`cli.py:1772`).

Not a command today: `dr claim-restate` (planned, RE-AC Claim restatement), `dr recheck` (interview Q7), `dr findings` (interview Q8 D), `dr verify` (named in `docs/architecture/source-quality.md:62`; no match in `cli.py`).

Entry-point functions the docs name, confirmed in `pipeline/orchestrator/pipeline.py`: `verify_claim` (:345), `_apply_entity_match` (:556), `_run_with_null_retry` (:1384), `research_claim` (:1619), `_screen_templates` (:1953), `gather_light_research` (:1991), `onboard_entity` (:2293). Checkpoint methods confirmed in `pipeline/orchestrator/checkpoints.py`: `review_sources` (:101), `review_disagreement` (:117), `review_onboard` (:124), `review_entity_enrichment` (:135), `review_entity_disambiguation` (:148), `review_verification_status` (:167).

## 2. Per-doc map

### 2.1 AGENTS.md

| Lines | What it states | Will change when |
|---|---|---|
| 11 | "How the system works": four object types, Orchestrator, Router, Researcher, Ingestor, Analyst, Evaluator (open-loop, no auto-resolution), `dr review --approve` / `--archive`, Citation check as static CI | SP2 (rules and findings file plus tie-breaker) changes "open-loop: disagreements surface to the operator and are not auto-resolved"; SP8 (companies out) changes "entities (companies and products in v1...)" |
| 13 | Points at `docs/architecture/glossary.md` § How the system works | |
| 17 | Design principle "Small decisions, small models"; "only Analyst and Evaluator may invoke frontier models" | SP2 adds a tie-breaker tier above Analyst/Evaluator; this sentence must name it |
| 33-39 | Research content structure: `entities/companies/`, `entities/products/`, `entities/subjects/`; claims `claims/{entity-slug}/{claim-id}.md`; sources `sources/{yyyy}/{slug}.md` | SP8 (companies out) |
| 45-48 | Topic taxonomy: `topics:` array on claims and criteria; points at `docs/plans/completed/multi-topic.md` | SP6 (one claim path) if criteria go away |
| 72 | Boundary rule: pipeline agents (`dr` commands, `pipeline/` packages) write only under `research/` | Keep; a new `pipeline/loop/` must obey it |
| 92-100 | Claim tags `highlight`, `home-familiar`, `home-second` (operator-set, not pipeline) | Q11 home-page cards may touch these |
| 104-107 | Content rules (cite a source, `as_of` today, 30-word summaries, `archived_url`) | Keep |
| 111 | "Pipeline routing and persistence live in `orchestrator/`" | SP1 (one loop) adds `pipeline/loop/` |
| 113-121 | Agent roles table: Research Lead (manual, `QUEUE.md`), Orchestrator (`pipeline/orchestrator/`), Router (`pipeline/router/` planned; `docs/plans/completed/triage-agent.md`, `claim-lifecycle-states.md`), Researcher (`researcher/`, `web_search`), Ingestor (`ingestor/`, `web_fetch`, `wayback_check`), Analyst (`analyst/`, `AnalystOutput`), Evaluator (`auditor/`, `IndependentAssessment`) | SP2 adds a tie-breaker row; SP7 (fold side tools) may retire the Router row |
| 125-134 | Directory layout: `common/`, `ingestor/`, `researcher/`, `analyst/`, `auditor/` ("rename to evaluator/ deferred to post-v1"), `orchestrator/` ("Routing logic, checkpoints, persistence, dr CLI"), `tests/` | SP1 adds `loop/`; `linter/` is on disk but missing here (`ls pipeline/`) |
| 138 | Each agent package has `instructions.md` loaded via `common/instructions.py` | Keep |
| 142-151 | Checkpoint behavior: `CheckpointHandler` protocol; `review_sources`, `review_disagreement`, `review_onboard`, `review_entity_disambiguation`, `review_verification_status`, `review_entity_enrichment`; `--interactive` on `dr claim-probe`, `dr claim-draft`, `dr onboard`; tests use `AutoApproveCheckpointHandler` | SP2 (rules replace the disagreement checkpoint); SP6/SP7 (onboard folds in); the `--interactive` list omits `dr claim-refresh`, which has it (`cli.py:1039`) |
| 157-160 | `dr` vs `inv` table: `dr` for "claim-probe, claim-draft, claim-refresh, claim-promote, evaluate, ingest" | `evaluate` is not a command (not in `--help`, no match in `cli.py`); `ingest` is hidden. SP7 rewrites |
| 162-173 | `dr` lives in `orchestrator/cli.py`; examples `uv run dr claim-probe`, `claim-draft products/chatgpt`, `claim-draft -`, `step-audit --entity ecosia`, `step-ingest <url>`, `onboard "Ecosia AI" --type product`, `lint --entity ecosia`, `review --claim ecosia/renewable-energy-hosting` | SP7 (five commands: draft, recheck, review, findings, lint) rewrites the whole block |
| 177-188 | Command descriptions: `claim-probe`, `claim-draft` (ENTITY_REF `products/chatgpt` or `-`), `claim-refresh` (needs `criteria_slug`; "use `dr claim-promote` first"), `claim-promote` (`research/templates.yaml`), `step-research`/`step-ingest`/`step-analyze`/`step-audit` ("`dr reassess` and `dr ingest` remain as hidden deprecated aliases"), `onboard`, `wayback-backfill` (`--recheck`), archive.org capture rules per command (`--skip-wayback`, `--write`, `--force`, `dr entity-enrich`, `dr ingest --dry-run`), `lint`, `review` (tty rule, `dr review-queue` `a` action, agents never run it) | SP6 (templates become sentences: `claim-promote`, `criteria_slug`, `onboard` wording), SP7 (every name), SP5 (`recheck --due` added). Missing from this list although live: `dr stats`, `dr publish`, `dr review-queue`, `dr entity-enrich` (mentioned only inside the capture paragraph) |
| 189 | `source .venv/bin/activate` makes `uv run` optional | Keep |
| 193-202 | `inv setup/test/test.all/build/check/clean`; `uv tool install invoke` | `inv dev`, `inv lint`, `inv audit`, `inv audit.prune`, `inv test.acceptance`, `inv worker-deploy` exist in `tasks.py` (:25, :37, :198, :225, :167, :55) and are not listed |
| 208-216 | Env vars: `BRAVE_WEB_SEARCH_API_KEY`, `RESEARCH_SEARCH_BACKEND`, `TAVILY_API_KEY`; arXiv Path 2 via `VerifyConfig.research_origins` default `["tavily", "arxiv"]` in `pipeline/orchestrator/pipeline.py` (confirmed :293); Tier 2 Semantic Scholar and OpenAlex "will add"; Tavily data-handling note, `docs/plans/completed/source-pool-expansion-tier1-search-backend.md` | SP1 if the loop changes how the researcher is configured |
| 220-221 | File naming: kebab-case; `sources/2026/polytechnique-energy.md` | Keep |
| 231 | Priorities flow: `python3 scripts/release-gate/work_item.py start` | Keep |
| 246-272 | Plan lifecycle (`docs/plans/drafts/` gitignored, `docs/plans/`, `completed/`, `deferred/`), rules 1-8 | Keep; governs this spike series |
| 301-345 | Release planning: only Scheduled work may be coded; gate; roadmap layout; work item IDs `RE-*`; "roadmaps state the current truth" | Keep |
| 349-364 | Agent workflow tooling: `scripts/release-gate/release_gate.py` (PreToolUse on Edit/Write/MultiEdit; gated prefixes `src/`, `pipeline/`, `workers/`, `scripts/`, `public/`, `.github/`), `release_context.py` (UserPromptSubmit), `work_item.py status/start/hotfix/finish`, `RELEASE_GATE=off`, `release_common.py` lists, `HOTFIX_TTL_HOURS` | Keep; a `pipeline/loop/` directory is gated like the rest |
| 366-379 | Architecture docs rules: update before plans, update after work, link in `docs/architecture/README.md` | Governs every spike's doc step |

### 2.2 docs/architecture/research-flow.md (282 lines)

| Lines | What it states | Will change when |
|---|---|---|
| 17-31 | Claim lifecycle diagram: `dr claim-draft` / `dr claim-refresh` / `dr onboard` / manual edit → draft; `blocked` on `< 4 sources or terminal fetch error`; `dr review --archive`; PR opened → `under_review`; `dr review --approve` + PR merged → published; `recheck_cadence_days` → stale; `stale → under_review: dr claim-refresh, PR opened` | SP5 (recheck), SP7 (names). `under_review` and `stale` are not schema states (`content-model.md:74` lists draft, published, archived, blocked) |
| 36 | `blocked_reason` values `insufficient_sources`, `terminal_fetch_error`, `analyst_error` | SP2 if blocked becomes "deleted half-claim plus finding" |
| 37 | Stale claims flagged by `dr lint` (`next_recheck_due` as `info`) and by `dr reassess` ("re-runs the Evaluator"); "No scheduler exists" | SP5; `dr reassess` is a hidden alias, the visible name is `dr step-audit` |
| 39 | `dr review` (per-claim) or `dr publish` (bulk); `docs/plans/completed/audit-trail.md` | SP7 if `publish` is folded |
| 47-61 | Queue diagram: `research/QUEUE.md` → `dr step-ingest URL` / `dr claim-draft claim-text` / `dr onboard entity type` | `research/QUEUE.md` exists and is empty (its body is the heading plus one comment). SP6/SP7 |
| 67 | Pipeline execution prose: concurrent ingest per URL; quote rules (300 chars elided, three words between ellipses, two words per fragment); Evaluator in `pipeline/auditor/`; Evaluator grades the claim title; title failing the template skips the Evaluator and blocks; `dr claim-probe` grades the operator's text; criterion `notes` from `research/templates.yaml` go to analyst and Evaluator; `pipeline/common/verdict-scale.md` | SP1 (loop), SP3 (restate in loop), SP6 (templates). RE-AL (Source pool and coverage quality) line "Template notes serve readers and the analyst" (roadmap `docs/v1.0.0-roadmap.md:338`) decided a separate grading-rule field; this sentence still says `notes` goes to the agents |
| 71-76 | Ingest order: entity-host first; sub-question fill order; `candidate_pool_size` (confirmed `pipeline.py:279`); uncovered sub-question warning; cited-source list rules (`cited_sources`, `source_overrides`, `sources_consulted`); every source listed when nothing cited or level would drop; analyst failure writes sources and no claim | SP1 rewrites; RE-AL lines 3 and 5 (scorer tags as coverage; dedup hits shrink ingest) touch these sentences |
| 78-120 | Sequence diagram: Operator → Researcher → Ingestor (par) → `review_sources` checkpoint → threshold (`< 4 usable sources`) → Analyst `AnalystOutput` → Evaluator `ComparisonResult` → `review_disagreement` → `VerificationResult` | SP1, SP2 (tie-breaker participant; rule instead of checkpoint) |
| 126-170 | Onboard diagram: light research, template screening, `review_onboard`, write `research/entities/{type}/{slug}.md`, per-template `verify_claim`, `OnboardResult` | SP6 (one claim path; onboard loop goes), SP8 |
| 176-234 | Sign-off diagram: `review_sources`, `review_disagreement`, `review_onboard`, local `inv check` + `dr lint`, PR, CI (`scripts/check-citations.ts`, `dr lint --severity error` in `lint-content`), GitHub Pages deploy | SP2, SP4 (review packet), SP7. Repo convention today is direct commits to main, no PR for research (CLAUDE.md says PRs for `research/claims/`; memory says no PRs before beta) |
| 238-240 | `dr review` writes `human_review`; `--approve`, `--archive`, bare; `dr publish` bulk, skips verdict-differs-without-override; `dr claim-refresh` and forced rewrites (`dr step-analyze --write --force`, `dr claim-draft --force`, `dr onboard --force`) return a published claim to draft, `refresh` block, `corrections` entry; `docs/runbook.md` § Refreshing a published claim | SP5 (recheck lands as a new draft while the old stays live; today a refresh overwrites in place and drops the claim off the site until re-approved), SP7 |
| 246-282 | Researcher internals: planner → search executor → scorer; `research_origins` default `["tavily", "arxiv"]`; `search_backend`; `ACADEMIC_TOPICS` (`ai-safety`, `environmental-impact`, `industry-analysis`); `llm_concurrency` semaphore "guards all LLM calls"; `publisher_quality`; `max_initial_queries`; `max_sources`, blocklist | SP1. `docs/plans/claim-restate.md:561` records that `dr step-audit` calls `auditor_agent.run` without the semaphore, so line 246 overstates |

### 2.3 docs/architecture/research-workflow.md (120 lines)

| Lines | What it states | Will change when |
|---|---|---|
| 11 | Content model: Entity, Source, Claim, criteria in `research/templates.yaml`; sources cited by slug | SP6 |
| 15-22 | Lifecycle steps 1-6: `research/QUEUE.md`; Ingestor writes `research/sources/{yyyy}/{slug}.md`; Analyst and Evaluator "both write to a claim file" (inaccurate: the orchestrator writes; `persistence.py`); blocked under four sources; PR review; deploy; Maintain is manual; `dr review --approve/--archive`, bare | SP1, SP5, SP7 |
| 24 | `dr publish` bulk flip, "Unreviewed" badge | SP7 |
| 30-40 | Roles status table: Orchestrator files (`pipeline.py`, `cli.py`, `persistence.py`, `checkpoints.py`), Router (`triage-agent.md`, UNSCHEDULED § Router), Researcher/Ingestor/Analyst (`pipeline/<pkg>/`), Evaluator `pipeline/auditor/`, Citation Auditor (three tools), Page Builder (not implemented) | SP1 adds `loop/`; SP2 adds tie-breaker; SP7 |
| 44-50 | Citation Auditor tools: `scripts/check-citations.ts`, `dr lint`, `dr step-audit` ("formerly `dr reassess`, hidden alias") | SP7 |
| 56-59 | Four content rules | Keep |
| 63-71 | Review cadence table (60 / 14-30 / 90-180 days); "no automated scheduling" | SP5 |
| 75-80 | `VerifyConfig` knobs: `max_initial_queries` (7), `research_origins`, `search_backend` (`RESEARCH_SEARCH_BACKEND`), `llm_concurrency` (8) | SP1 |
| 84-91 | CI gates: `npm run build`, `npm run lint:md`, `npm run check:citations`, `dr lint --severity error` (`lint-content`, `pipeline/linter/`); local `npm run check` and `uv run dr lint` | Keep unless SP7 renames `lint` |
| 95-100 | What the gates do not check (`as_of` currency, `archived_url`, 30-word rule, link validity) | SP5 may add staleness |
| 104 | Claim schema fields incl. `phase`, `blocked_reason`, `audit` | SP2 |
| 115-120 | File references: `src/content.config.ts`, `AGENTS.md`, `.github/workflows/ci.yml`, `scripts/check-citations.ts`, `research/QUEUE.md`, `docs/UNSCHEDULED.md` | SP7 if QUEUE.md goes |

### 2.4 docs/architecture/glossary.md (221 lines)

Terms that name pipeline concepts (every one is a candidate to rename, retire or redefine):

| Lines | Term | Names or paths it cites |
|---|---|---|
| 7-9 | How the system works: criteria, entities, sources, claims; queue; open-loop evaluation | AGENTS.md § How the system works |
| 15-18 | Entity, Claim, Source, Criterion | `research/entities/{type}/{slug}.md`, `research/claims/{entity-slug}/{claim-id}.md`, `research/sources/{yyyy}/{slug}.md`, `research/templates.yaml` |
| 24-36 | Verdict, Confidence, Topics, Takeaway, seo_title (forced-rewrite keep rules, `analyst_record`), Phase (`researching`, `ingesting`, `analyzing`, `evaluating`), blocked_reason, Kind, source_type (`pipeline/common/source_classification.py`), as_of, recheck_cadence_days, criteria_slug, founded (`dr onboard` / `dr entity-enrich`, `entity_enricher`) | |
| 42-50 | Verdict definitions: true, mostly-true, mixed, mostly-false, false, unverified, not-applicable | `src/content.config.ts` |
| 56-66 | Role / agent / CLI cross-walk: Orchestrator = "the `dr` CLI itself"; Router planned `pipeline/router/`; Researcher invoked by `dr claim-draft`, `dr claim-probe`, `dr claim-refresh`, `dr onboard`, standalone `dr step-research`, enricher `dr entity-enrich`; Ingestor standalone `dr step-ingest` (`dr ingest` hidden alias); Analyst standalone `dr step-analyze`; Evaluator `pipeline/auditor/`, standalone `dr step-audit` (`dr reassess` hidden alias); Linter `pipeline/linter/`, `dr lint`, `lint-content` CI job; sidecar/status: `dr review`, `dr review-queue`, `dr publish`, `dr stats` | SP1, SP2, SP6, SP7: every row |
| 70 | Model-tier discipline: `models_used` in `.audit.yaml`; enforcement stub `docs/plans/deferred/model-tier-enforcement_stub.md` | SP2 (tie-breaker tier must be recorded in `models_used`) |
| 76-84 | Roles: Research Lead, Orchestrator, Router, Researcher (3-step, `max_initial_queries`, `parent_company`, `publisher_quality`, `entity_verifier`, `entity_enricher`, `LightResearchBundle`), Ingestor, Analyst, Evaluator | SP2, SP8 (parent_company is a company concept) |
| 92 | Pipeline (`pipeline/`) | |
| 98-112 | Pipeline mechanisms: Audit sidecar / `.audit.yaml` (`claims-with-audit` loader), `human_review` (`dr review`, `dr publish`, `verdict_override`), Threshold gate (`pipeline/orchestrator/pipeline.py`), Blocklist (`research/blocklist.yaml`), Checkpoint (six names, `--interactive`, `AutoApproveCheckpointHandler`), Linter package, `max_initial_queries`, `llm_concurrency` (semaphore at `verify_claim`, `research_claim`, `onboard_entity`), `publisher_quality` (`pipeline/common/publisher_quality.py`), `research_origins`, `search_backend`, `ACADEMIC_TOPICS` (`pipeline/common/models.py`, confirmed :126), Archive recovery chain (`pipeline/ingestor/tools/wayback.py`) | SP1 (three entry points become one), SP2 (checkpoint list) |
| 118-123 | Agent tasks | SP2 |
| 129-134 | Object lifecycle (general): proposed, active, flagged, retired | Not in any schema; aspirational |
| 140-147 | Claim lifecycle: queued (`QUEUE.md`), in-progress (`phase`), blocked, draft, published, archived | SP2, SP7 |
| 153-166 | Lifecycle vocabulary: Queue, Ingest (`dr step-ingest`, `dr ingest`), Onboard (`dr onboard`, loops `verify_claim`), Claim-probe, Claim-draft, Claim-refresh (`criteria_slug`), Claim-promote (`research/templates.yaml`), Reassess (`dr step-audit`, `dr reassess`), Lint, Review (`dr review`, `--approve`, `--archive`, tty rule), Publish (`dr publish`, `[auto-publish]`), Recheck ("manual today; no scheduler") | SP5 (Recheck becomes a command), SP6, SP7: every row |
| 170-172 | Planned terms: Submitted claim | Longer-term platform goal |
| 176-185 | Criterion vocabularies (`vocabulary:` in `research/templates.yaml`), Frontier-scale | SP6 (templates become stored sentences) |
| 189-194 | Governance rules: content rules, schema authority, plan lifecycle | Keep |
| 198-204 | Vocabulary layers: research objects, roles, pipeline (orchestrator "Implicit in `pipeline/orchestrator/`"; router "implementation deferred") | SP7 |
| 208-213 | Tests and checks | Keep |
| 217-221 | Infrastructure: Content Collection, Zod schema, Pydantic model | Keep |

### 2.5 docs/architecture/content-model.md (285 lines)

| Lines | What it states | Will change when |
|---|---|---|
| 9-14, 18-30 | Content types and directory tree: `entities/companies/`, `products/`, `subjects/`; `claims/{entity-slug}/{claim-id}.md`; `sources/{yyyy}/{slug}.md`; `research/templates.yaml` | SP8 (companies), SP6 (templates). Note the tree omits `claims/subjects/<slug>/` (subject claims live one level deeper: `research/claims/subjects/`) and `.audit.yaml` sidecars |
| 43-57 | Entity schema: `parent_company` (`companies/{slug}`), `search_hints`, `sec_cik`, `verification_status`, `legal_name`, `founded` | SP8 |
| 61-84 | Claim schema: `seo_title` keep rule (`dr claim-refresh`, `--force`, `analyst_record`), `verification_level`, `cap_rationale` keep rules, `source_overrides`, `takeaway`, `criteria_slug`, `status` (draft, published, archived, blocked; production builds only published and archived), `phase`, `blocked_reason`, `recheck_cadence_days`, `next_recheck_due`, `tags`, `audit` | SP2 (blocked), SP5 (recheck fields), SP6 (`criteria_slug`), SP1 (keep rules live in `persistence.py` and must survive) |
| 88-101 | Source schema: `archived_url` rules (TimeGate, CDX, Save Page Now; 90-day refresh; `dr wayback-backfill`, `--recheck`; `dr claim-probe` and `dr step-ingest` without `--write` never capture), `kind`, `source_type`, `independence`, `summary`, `key_quotes` | SP7 if wayback-backfill folds |
| 104-157 | Audit sidecar: `claims-with-audit` loader; `pipeline_run.*` incl. `level_clamp`; `models_used` (`dr step-audit --write` replaces only `auditor`); `sources_consulted[]` with `acquisition` (`stage`, `origin` enum `brave`, `tavily`, `arxiv`, `s2`, `openalex`, `edgar`; `recovered_via`, `outcome`, `query`, `paper_id`, `filing_accession`) and `archive` (`status` found/failed/not-attempted, `error`); `audit` block (`analyst_verdict`, `auditor_verdict`, `*_confidence`, `verdict_agrees`, `confidence_agrees`, `needs_review`, `auditor_reasoning`, `evidence_gaps`, `needs_review_reasons`; `null` after `dr step-analyze --write --force` until `dr step-audit --write`); `human_review.*` incl. `verdict_override`; `refresh` block (`refreshed_at`, `previous`, `dropped_sources`); `analyst_record`; `scripts/backfill_analyst_record.py` | SP2 (tie-breaker verdict needs a field; `audit.auditor_*` names), SP4 (review packet reads these), SP5 (`refresh` semantics change if a recheck becomes a new draft). `research`, `sub_questions`, `restatement`, `restates` are not listed (`docs/plans/claim-restate.md:421, 561`) |
| 159 | Evaluator in `pipeline/auditor/`; `auditor_` sidecar prefix kept "until the package directory is renamed (post-v1)" | SP1/SP2 decide whether to rename now |
| 163-176 | Criterion schema: `slug`, `text`, `entity_type`, `subjects` (required for subject criteria), `topics`, `core`, `notes` ("sent to the analyst as grading guidance"), `vocabulary` | SP6; RE-AL line 7 (separate grading-rule field) |
| 180-192 | Relationships; claims never contain raw URLs | Keep |
| 283-285 | Build-time validation | Keep |

### 2.6 docs/architecture/onboarding.md (161 lines)

Whole file describes `dr onboard` and `dr entity-enrich`; SP6 (one claim path) and SP8 (companies out) rewrite or retire it.

| Lines | What it states |
|---|---|
| 8-17 | Command: `dr onboard "Entity Name" [seed-url] --type {company\|product\|subject} [--force] [--only <slugs>] [--interactive]`; entity-ref form `dr onboard products/<slug>`; `--search-hint-*` flags; `dr entity-enrich <type>/<slug>` refuses with `not enriched`, exit 1 |
| 22-74 | Phases A-F: light research (Brave probe for collisions), `entity_verifier`, `entity_enricher`, template screening (core by `entity_type`; subjects by `subjects:`), checkpoint `review_onboard`, per-template Researcher → Ingestor → Analyst → Evaluator |
| 79-88 | Subject example `dr onboard subjects/ai-model-producers` |
| 92-103 | Agent responsibilities; verifier and enricher in `pipeline/researcher/`; `LightResearchBundle`; "Template screening (Phase D) is a passthrough today" |
| 107-134 | Checkpoint protocol signatures for `review_entity_disambiguation`, `review_verification_status`, `review_entity_enrichment`, `review_onboard`; reject "saved as a draft under `research/entities/drafts/`" (`persistence.py:1147-1151` writes there; the directory does not exist on disk today) |
| 138-143 | `core: true/false` in `research/templates.yaml`; `--type subject`; templates file is the source of truth |
| 147 | Company-product relationships: `parent_company` injected into planner and scorer prompts |
| 151 | Topics locked to template in onboard and claim-refresh; analyst topics only for ad hoc claims; `docs/plans/completed/multi-topic.md` |
| 155-161 | File references: `pipeline/orchestrator/cli.py` (`dr onboard`, `dr entity-enrich`), `pipeline.py:onboard_entity`, `pipeline/researcher/entity_verifier.py`, `entity_enricher.py`, `pipeline.py:gather_light_research`, `checkpoints.py`, `research/templates.yaml` (all exist) |

### 2.7 docs/architecture/open-issues.md (62 lines)

| Lines | What it states | Relevance |
|---|---|---|
| 9-11 | Resolved: `dr review`, `dr audit` → `dr reassess` rename (`docs/plans/completed/claim-promotion-audit-rename-verdicts.md`) | Name history: `audit` → `reassess` → `step-audit` |
| 15-32 | Issue 1: `_screen_templates()` is a pass-through stub; `dr onboard --only` is the workaround | SP6 removes the question |
| 36-48 | Issue 2: recheck has no operational owner; `dr lint` flags `next_recheck_due`; options cron / CI gate / manual | SP5 answers it (`dr recheck --due`, then schedule) |
| 52-62 | Issue 3: `verify_claim()`, `research_claim()`, onboard per-template loop are three copies; a `persist: bool` flag risks `dr claim-probe` writing files; "a clear test harness verifying `dr claim-probe` produces zero file writes is a prerequisite" | SP1 is exactly this; the probe-vs-draft test the interview names (Q8 B) is the prerequisite this doc asked for |

### 2.8 docs/architecture/README.md (18 lines)

Index rows for `content-model.md`, `research-workflow.md`, `onboarding.md`, `glossary.md`, `research-flow.md`, `source-quality.md`, `open-issues.md`, `vision-state-machine.md` (lines 8-16). Any doc retired or added (for example a loop doc or a findings-file doc) changes this table (AGENTS.md:379 rule 3).

### 2.9 docs/architecture/source-quality.md (183 lines)

| Lines | What it states | Will change when |
|---|---|---|
| 19-29 | Verification scale (`multiply-verified` ... `claimed`), display copy mirrored from `src/lib/sourceQuality.ts` | Keep |
| 33-40 | Level fit at write time: `fit_verdict_to_written_pool` in `pipeline/orchestrator/persistence.py`, called by `dr claim-refresh`, `dr onboard`, `dr step-analyze`, `research_claim`; `effective_independence` in `pipeline/common/source_classification.py`; lint `verification-level-pool-mismatch` (confirmed `checks.py:770,784`); `pipeline_run.level_clamp` | SP1 (one loop must call it once); RE-AL line 2 (sidecar confidence from before the fit) |
| 52-57 | `independence` proxied from `source_type` by the ingestor | Keep |
| 62-74 | Entity match: applies under `dr claim-refresh`, `dr onboard`, `dr verify` (not a command), `dr step-analyze`, `research_claim` with pre-resolved entity; `entity_first_party_reason`; host / profile / publisher rules; `entity_affiliated`; "Off-entity:" and "Entity match:" override reasons; `parent_company`, `aliases:` | SP1, SP8 (parent company rules are company-specific) |
| 95-96 | arXiv affiliation: `arxiv_corporate_lab` in `pipeline/ingestor/arxiv_affiliation.py` (exists) | Keep |
| 102-108 | Restatement test (analyst) | Keep |
| 112-132 | Confidence cap, rationale templates, `dr lint` warnings | Keep |
| 136-150 | `source_overrides` on claims | Keep |
| 154-156 | Entity metadata: `website`, `legal_name`, `verification_status`; `pipeline/researcher/scorer.py` "ENTITY DISAMBIGUATION"; `entity_enricher` during `dr onboard` and `dr entity-enrich` | SP6/SP7/SP8 |
| 160-167 | Publisher registry deferred; blocklist handles low-trust | RE-AL line 1 (newswire) |
| 177-183 | Cross-references: four completed/deferred plans, `pipeline/analyst/instructions.md`, `pipeline/linter/checks.py` | Keep |

### 2.10 docs/architecture/vision-state-machine.md (67 lines)

Direction, not state (line 3). Names: claim status and phase enums (15-16), object lifecycle (17), queue lifecycle (18), audit sidecar v1 (19); principle 3 "open-loop at decision points: Analyst/Evaluator disagreement ... never auto-resolves" (29); scheduled agents Observe / Nudge / Execute (41-43); near-term `docs/plans/deferred/audit-trail-extensions.md`, `docs/plans/completed/published-claim-refresh-trail.md` (57). SP2 (tie-breaker rule) contradicts line 29 and AGENTS.md:11; SP5 (scheduled recheck) is the "Nudge" posture line 47 said not to settle yet. Both docs need one sentence each saying the stance changed and why (Brandon, interview Q2/Q3).

### 2.11 pipeline/README.md (35 lines)

| Lines | What it states | Status |
|---|---|---|
| 14-18 | `uv sync --locked` from repo root; workspace member; `uv lock` after `pyproject.toml` change | Current |
| 23 | `uv run pytest tests/ -v` | Current (`tasks.py:151` uses `uv run python -m pytest -m 'not acceptance'`) |
| 28-31 | Structure: `common/`, `ingestor/` "(Phase 4.1)", `consistency/` "(Phase 4.2)", `tests/` | Stale: `consistency/` does not exist; `researcher/`, `analyst/`, `auditor/`, `orchestrator/`, `linter/` are missing (`ls pipeline/`). Already recorded at `docs/plans/claim-restate.md:540, 561` |
| 35 | Blocklist at `research/blocklist.yaml` (exists); `StepError(error_type="blocked_host")`, `"all_blocked"`, `review_sources`, `OnboardResult.errors`; filter runs before the `max_sources` slice | SP1, SP2 (findings file replaces `StepError` surfacing?), SP6 (`OnboardResult`) |

### 2.12 docs/runbook.md (159 lines)

| Lines | What it states | Will change when |
|---|---|---|
| 5-15 | `inv dev`, port 4321, restart rules | Keep |
| 52-54 | Corrections: `.github/ISSUE_TEMPLATE/correction.yml`, `corrections` frontmatter, forced rewrite keeps entries | SP5 |
| 73-82 | Refreshing a published claim: `dr step-analyze --write --force`, `dr claim-draft --force`, `dr onboard --force` reset sign-off; `uv run dr step-audit --claim <ref> --write`; steps `uv run dr claim-refresh <entity>/<claim-slug>`, `uv run dr review-queue` ("Was published"), `a` asks for a correction, `uv run dr review --claim <ref> --approve --correction "..."`, `dr publish` skips refreshed claims, tty rule, lint `refresh-pending-review` (confirmed `checks.py:221`), `git restore` for a blocked refresh, `e` then `verdict_override`, lint `verdict-sidecar-mismatch` (`checks.py:186`) | SP5 rewrites (recheck lands as a new draft; old stays live), SP7 (names) |
| 86-92 | Archive links: capture rules; `uv run dr wayback-backfill <year>/<slug>`, `--recheck`; exit codes; `sources_consulted[].archive`; 14-digit timestamp rule; "The `dr` command list in AGENTS.md says which commands can capture" | SP7 |
| 96-150 | Petitions (Worker, D1, `inv worker-deploy`, `inv petition-emails`, `inv petition-stop-updates`) | Out of pipeline scope |
| 152-159 | TODO comment: sections still needed: deploy, content pipeline, adding entity/claim/source, linting and pre-commit hooks, env vars | SP7 (command contract) and SP4 (review packet) are where these sections get written; `docs/UNSCHEDULED.md:134` "Expand runbook.md" is the backlog row |

Not in the runbook but operative: `.git/hooks/pre-commit` (untracked) runs `$REPO_ROOT/pipeline/.venv/bin/dr lint --repo-root` then `inv check` (hook lines 6-17); both `pipeline/.venv/bin/dr` and `.venv/bin/dr` exist.

### 2.13 docs/plans/claim-restate.md (602 lines; the plan RE-AC Claim restatement absorbs)

Status line 3: "design reviewed by the operator 2026-10-10; Not started." Register line 7: `work_item.py start --title "RE-AC (Claim restatement)" ... --plan docs/plans/claim-restate.md`.

What SP3 (restate inside the loop) must carry over or consciously drop:

| Lines | Content | SP3 relevance |
|---|---|---|
| 13 | Goal: read one unverified claim plus the whole local pool, propose ranked restatements with the verdict the evidence would give; no web research; `--write` to sidecar; `--write --accept N` writes a criterion to `research/templates.yaml`; operator onboards with `dr onboard --only` | Interview Q5 changes the shape: restate runs inside the loop automatically, keeps the original, returns verdict on Brandon's sentence plus a restated supportable claim linked via sidecar, picked at `dr review`. The `--accept` → criterion → `dr onboard --only` chain depends on templates (SP6 removes them) |
| 33-49 | D1-D17: new command and agent (D1); whole pool, no web research (D3); polarity guard (D4); only `verdict: unverified` input (D5); read-only by default (D6); Evaluator model slot `--restater-model` (D7); one `restatement` block per sidecar (D9); `why_unverified` enum (D10); `--accept` writes criterion `core: false` (D13); never another entity (D14); no lint rule (D16); `restates:` sidecar key on the new claim (D17) | D4 polarity guard and D14 same-entity rule should survive. D5 (unverified only) conflicts with Q5 (restate every ad hoc run). D13 goes with templates |
| 53-140 | Evidence sweep of 4 claims; reasons R1-R7 (R6: auditor grades the narrative, fixed by RE-AD; R7: narrative asserts absences) | R1-R4 become `why_unverified`; R5-R7 are pipeline findings already in UNSCHEDULED § Unverified-claim sweep findings |
| 144-221 | Command contract `dr claim-restate CLAIM_REF [--write] [--accept N] [--format] [--max-candidates] [--max-sources] [--pool all\|cited] [--dry-run] [--repo-root]`; exit codes 0/1/2/3; help group Read-only; report sketch; `_check_provider_api_keys` (`cli.py:83-98`), `_resolve_claim_path` (`cli.py:2058`), `_run_with_null_retry` | SP7 wants about five commands; a separate `claim-restate` command is unlikely to survive |
| 225-246 | Retrieval module `pipeline/restater/retrieval.py`: keyword ranking over `research/sources/`, weights table, `load_source_dict` (`persistence.py:109`), `host_matches` (`common/utils.py:44`), `_apply_entity_match` (`pipeline.py:511` then; now :556) | Line numbers were "as of HEAD `0b3d0a9`" (line 6); several have drifted (`_apply_entity_match` :511 → :556, `_run_with_null_retry` :1124 → :1384, `research_claim` :1312 → :1619, `onboard_entity` :1808 → :2293, `claim-draft` :798 → :932, `claim-refresh` :897 → :1033, `claim-promote` :1207 → :1355) |
| 250-365 | Package `pipeline/restater/` mirroring `pipeline/auditor/`; models `RestateSource`, `RestateBundle`, `EvidenceRef`, `Frame`, `WhyUnverified`, `RestatementCandidate`, `RestatementProposal`; decisiveness rubric 0-4; code-side checks (quote verification, caps, sort); instructions outline items 1-10 (polarity guard verbatim at item 3); model tier = Evaluator slot, `AGENT_NAMES` (`common/models.py:73`, confirmed) not extended; `RESTATE_TIMEOUT_S = 180` | Models and rubric are reusable inside a loop step |
| 369-421 | Sidecar `restatement` block schema; read-modify-write (not `_write_audit_sidecar`, `persistence.py:542`); carry-over beside `refresh`; `approve_claim` removes on approve/archive (`review.py:276-277`); `auditSchema` strips unknown keys (`src/content.config.ts:38-90`) | SP3 sidecar design; SP4 review packet needs the chain on one screen |
| 427-447 | `--accept`: `append_template_entry` factored out of `dr claim-promote` (`cli.py:1207-1356` then), `_ENTITY_TYPE_PLACEHOLDERS` (company `COMPANY`, product `PRODUCT`, subject `ENTITY`), `dr onboard --only` widened to non-core (`pipeline.py:2139-2147` then) | Dropped with templates (SP6) |
| 451-478 | Operator loop outcomes A (new claim), B (template text change plus `dr claim-refresh`, siblings must each refresh), C (record only); `restates:` key | Outcome B's sibling problem disappears with SP6 |
| 482-497 | Tests table: `test_restater_*`, `TestClaimRestateCli`, `test_templates.py` (`len == 16` assertion at `test_templates.py:23-25`), `test_onboard.py` counts (:194, :250, :309), `test_cli_smoke.py:10` parametrize list, `test_audit_trail.py`, acceptance fixture `pipeline/tests/fixtures/restate/us-data-centers/` | Fixture and acceptance idea carry to SP3's acceptance claims (Q11 card sentences) |
| 503-549 | Steps S1-S9 | Replaced by SP3 |
| 540 | S8 doc targets: `AGENTS.md:181`, `glossary.md:64` and `:86-92`, `docs/runbook.md` new section, `pipeline/README.md` structure list | The same doc targets apply to SP3 |
| 553-561 | Pipeline defects found (template notes never reach analyst; off-entity contamination; absence assertions; entity exclude dropped the LinkedIn post; Viro level wrong; docs-vs-code list) | Some fixed in beta.7 (RE-AE, RE-AG); confirm each against the roadmap before carrying |
| 565-568 | RISK-1 quote fidelity (RF20, RF10), RISK-2 model variance (RF6), RISK-3 low ceiling, RISK-4 untracked worked example | RISK-4 still true: `research/claims/subjects/us-data-centers/` and `research/sources/2026/*data-center*` are untracked (`git status`) |
| 576-592 | Release-triage inputs; UNSCHEDULED section text (now at `docs/UNSCHEDULED.md:380-388`, follow-ups only) | |

### 2.14 docs/plans/drafts/analyst-decomposition_stub.md (62 lines)

Proposes splitting the Analyst into entity resolver (Haiku), per-source stance classifier (Haiku, fan-out), verdict synthesizer (frontier), narrative writer (Haiku) (lines 27-34). Names `build_analyst_prompt` (`agent.py:83`), onboard discarding analyst topics (`pipeline.py:829-836, 842` then), `research_claim` consuming them (:542-547 then), `retries=2`, `ClaimBundle`, `IndependentAssessment`, `token-usage-log.md` (lines 9-10, 36, 42, 44, 46). Critical files (52-56): `pipeline/analyst/agent.py`, `instructions.md`, `pipeline/orchestrator/pipeline.py`, `pipeline/common/models.py`, `pipeline/auditor/bundle.py`. Backlog home: `docs/UNSCHEDULED.md:52` "Analyst decomposition (cost lever)". Relevance: SP1's loop decides the Analyst call shape; this stub's "frontier sees structured stances, not raw bodies" is a cost lever the interview did not rank. Line numbers are from 2026-04-27 and have drifted.

### 2.15 docs/plans/drafts/ingestor-decomposition_stub.md (68 lines)

Proposes the orchestrator fetch and wayback deterministically and the LLM only structure the body (lines 5, 21-30). Status note line 9: not started; ingestor still registers `web_fetch` and `wayback_check` (`pipeline/ingestor/agent.py`); prefetched Tavily bodies reach the model through `web_fetch`; RF2 fixed elsewhere; RF10 and RF20 in UNSCHEDULED. References (58-61): `pipeline/ingestor/agent.py`, `pipeline/ingestor/tools/web_fetch.py`, `docs/plans/drafts/archive/tool-free-researcher-ingestor_stub.md`, `docs/plans/deferred/wayback-archive-job.md`. Out of scope line 53: keep the tool-using ingestor until a full run matches. Relevance: SP1 could adopt this shape when it writes the loop's ingest step; the interview did not mention it.

### 2.16 .claude/skills/release-triage/SKILL.md (178 lines)

Command and path names the spike series will use, not pipeline paths:

| Lines | Names |
|---|---|
| 8 | Gate prefixes `src/`, `pipeline/`, `workers/`, `scripts/`, `public/`, `.github/`; `.claude/active-work.json` |
| 17-24 | Step 1 commands: `python3 scripts/release-gate/work_item.py status`, `cat VERSION.md`, `cat docs/priorities.md`, `sed -n '1,30p' docs/v*-roadmap.md`, `grep ... docs/UNSCHEDULED.md`, `ls docs/plans/ docs/plans/drafts/` |
| 33-37 | `major` / `minor` / `patch` per VERSION.md; "new `dr` command" is `minor` (line 36) |
| 105-107 | `work_item.py start --title ... --kind ... --release v{semver} --plan docs/plans/drafts/{name}.md` or `--section "{ID} ({name})"` |
| 118 | Next-beta line format: "SITE-J (Responsible AI chatbots): published-claim refresh trail"; size guideline 5 |
| 156 | `work_item.py hotfix --title --reason`; 4-hour expiry |
| 166 | `work_item.py finish` |
| 173-178 | `RELEASE_GATE=off claude`; `scripts/release-gate/release_common.py`; `HOTFIX_TTL_HOURS`; `.claude/settings.json` hook entries; shell writes bypass the gate (do not use) |

Implication for the run decisions (interview "Ultracode run decisions"): one RE item per spike means nine `--section "RE-xx (name)"` registrations or one plan file `docs/plans/drafts/pipeline-rebuild.md` passed as `--plan`; `start` refuses a missing plan file (`work_item.py:74-77`, `release_common.py:211-215`).

### 2.17 scripts/release-gate/*.py

| File | Lines | Names |
|---|---|---|
| `release_common.py` | 24-31 | `GATED_PREFIXES`: `src/`, `pipeline/`, `workers/`, `scripts/`, `public/`, `.github/` |
| | 34-42 | `GATED_ROOT_FILES`: `astro.config.ts`, `package.json`, `package-lock.json`, `pyproject.toml`, `tasks.py`, `tsconfig.json`, `wrangler.toml` |
| | 46-54 | `EXEMPT_PREFIXES`: `src/content/`, `docs/`, `research/`, `.claude/`; `EXEMPT_SUFFIXES`: `.md`, `.mdx`, `.txt` (so `pipeline/*/instructions.md` and `pipeline/common/verdict-scale.md` are never gated) |
| | 57, 60, 66-69 | `WORK_ITEM_FILE = ".claude/active-work.json"`, `HOTFIX_TTL_HOURS = 4`, `RELEASE_GATE=off`, `VALID_KINDS` |
| | 112-128 | `read_version`: first non-empty line of `VERSION.md` is the version; `Active release:` names the roadmap |
| | 131-151 | Roadmap file patterns `docs/v{semver}-roadmap.md` or `docs/v{semver}.md` |
| | 180-218 | `validate_work_item`: kind, title, hotfix expiry, release roadmap must exist, plan file must exist or section non-empty |
| `release_gate.py` | 2, 54-82 | PreToolUse on Edit/Write/MultiEdit; deny text names `release-triage`, `work_item.py start ... --plan docs/plans/drafts/<name>.md` or `--section "§N"`, `hotfix`, `status` |
| `release_context.py` | 45-61 | Per-turn lines: working version, active release, roadmaps, active work item, gate state; "brainstorming -> writing-plans into docs/plans/drafts/" |
| `work_item.py` | 4-9, 57-81, 84-107, 110-119 | `status`, `start` (`--title`, `--kind patch\|minor\|major`, `--release`, `--plan`, `--section`, `--force`), `hotfix`, `finish` |
| `.claude/settings.json` | 8, 20 | Hook wiring for `release_context.py` and `release_gate.py` |

Nothing in these scripts names a `dr` command or a pipeline path beyond the `pipeline/` prefix; a spike that adds `pipeline/loop/` needs no gate change.

### 2.18 Other docs that name pipeline commands (outside the assigned set, for completeness)

- `docs/architecture/ci-deploy.md:31-33, 78`: `uv run dr lint --format json --severity error` in the `lint-content` job; `inv check` (pre-commit) runs type check, `test:site`, build, `check:watch`, `lint:md`, `check:citations`, pytest.
- `README.md:19-20`: "`pipeline/` — Python agents (Researcher, Ingestor, Analyst, Evaluator) plus the Orchestrator and the `dr` CLI"; `inv setup/dev/test`.
- `docs/v1.0.0-roadmap.md`: 30 lines mention `dr` commands (grep count); the RE-AD to RE-AK sections (`:233-325`) and RE-AL (`:326-338`), RE-AC (`:340-350`).
- `docs/priorities.md:18`: theme 1 names RE-AC and RE-AD to RE-AJ.
- `docs/decisions.md:17`: "Evaluator reruns held" (`dr step-audit` runs for RE-AD not run yet).
- `docs/UNSCHEDULED.md`: 38 lines with `dr` commands; pipeline sections at `:29, :42, :52, :242, :253, :311, :322, :335, :380, :390, :404, :447, :474`; "Expand runbook.md" row `:134` asks for a `dr` CLI reference and documents `inv audit`, `inv audit.prune`.
- `CLAUDE.md` (project): "Research content changes to `research/claims/` should go through PRs" (Git Conventions), which `research-flow.md` § 5 also assumes; the project memory says no PRs before beta.

## 3. Glossary terms that name pipeline concepts

From `docs/architecture/glossary.md` (line in parentheses): Criterion (18), Verdict (24), Confidence (25), Takeaway (27), seo_title (28), Phase (29), blocked_reason (30), source_type (32), recheck_cadence_days (34), criteria_slug (35), founded (36); the seven verdict values (44-50); Orchestrator, Router, Researcher, Ingestor, Analyst, Evaluator, Linter (59-66); Model-tier discipline (70); Pipeline (92); Audit sidecar (100), `human_review` (101), Threshold gate (102), Blocklist (103), Checkpoint (104), Linter package (105), `max_initial_queries` (106), `llm_concurrency` (107), `publisher_quality` (108), `research_origins` (109), `search_backend` (110), `ACADEMIC_TOPICS` (111), Archive recovery chain (112); lifecycle states queued, in-progress, blocked, draft, published, archived (142-147); Queue, Ingest, Onboard, Claim-probe, Claim-draft, Claim-refresh, Claim-promote, Reassess, Lint, Review, Publish, Recheck (155-166); Submitted claim (172); Frontier-scale (178-185).

Terms the interview introduces that have no glossary entry: tie-breaker (Q3), findings file (Q4), half-claim (Q4), review packet (Q6), recheck `--due` (Q7), one loop (Q8 B), stored sentence + entity filter (Q8 A), command contract (run decisions).

## 4. Duplication across docs (the same fact stated in more than one place)

| Fact | Locations |
|---|---|
| Full `dr` command list with descriptions | `AGENTS.md:177-188`; `glossary.md:56-66` (cross-walk); `glossary.md:155-166` (lifecycle vocabulary); `cli.py:119-126` (`_COMMAND_GROUPS`, the only one `--help` reads) |
| Which commands invoke which agents | `AGENTS.md:159`; `glossary.md:61-64`; `research-flow.md:17, 21` |
| Checkpoint names and `--interactive` | `AGENTS.md:142-151`; `glossary.md:104`; `onboarding.md:107-134`; `research-flow.md:101, 113-116, 183-194`; `checkpoints.py:101-167` |
| `dr review` / `dr publish` semantics (approve, archive, bare, tty rule, auto-publish marker) | `AGENTS.md:187`; `research-flow.md:39, 238-239`; `research-workflow.md:22-24`; `glossary.md:101, 164-165`; `runbook.md:79` |
| Refresh of a published claim (`refresh` block, `corrections`, forced rewrites, `dr publish` skips) | `research-flow.md:240`; `content-model.md:147-153`; `runbook.md:73-82`; `glossary.md:28` (seo_title keep rule); `content-model.md:64, 70, 72` (per-field keep rules) |
| Archive.org capture rules per command | `AGENTS.md:185`; `content-model.md:91`; `glossary.md:112`; `runbook.md:86-92` |
| Threshold gate (`< 4` sources, `blocked_reason` enum) | `AGENTS.md:117`; `research-flow.md:22, 36, 104-105`; `research-workflow.md:19`; `glossary.md:30, 80, 102, 144`; `content-model.md:76` |
| Evaluator is in `pipeline/auditor/`, rename deferred | `AGENTS.md:121, 131`; `research-workflow.md:38`; `glossary.md:64`; `research-flow.md:67`; `content-model.md:159`; `onboarding.md:99` |
| Evaluator is open-loop, disagreements go to the operator | `AGENTS.md:11`; `glossary.md:7`; `vision-state-machine.md:29`; `research-flow.md:111`; `onboarding.md:70, 99` |
| Research directory layout | `AGENTS.md:33-37`; `content-model.md:18-30`; `glossary.md:15-18`; `research-workflow.md:11`; `README.md:17-18` |
| Researcher internals (`max_initial_queries`, `research_origins`, `search_backend`, `ACADEMIC_TOPICS`, `llm_concurrency`) | `AGENTS.md:210-214`; `research-flow.md:246`; `research-workflow.md:75-80`; `glossary.md:81, 106-111` |
| Content rules (four) | `AGENTS.md:104-107`; `research-workflow.md:56-59` |
| Topic taxonomy table | `AGENTS.md:50-59`; `content-model.md:196-205` |
| Template `notes` go to the analyst (and Evaluator) | `research-flow.md:67`; `content-model.md:173`; contradicted by the RE-AL decision at `docs/v1.0.0-roadmap.md:338` |
| Recheck is manual, no scheduler | `research-flow.md:37`; `research-workflow.md:22, 71`; `glossary.md:166`; `open-issues.md:40-48` |
| Verification level fit at write time | `source-quality.md:33-40`; `content-model.md:116`; `glossary.md:28` (partial) |
| Plan lifecycle and gate rules | `AGENTS.md:246-364`; `SKILL.md:8-24, 95-110, 171-178`; `release_gate.py:71-82`; `release_context.py:51-61` |
| `pipeline/README.md` structure list vs AGENTS.md directory layout | `pipeline/README.md:28-31` (stale); `AGENTS.md:125-134` |

## 5. Hazards (things a rewrite could silently lose or break)

| Hazard | Location |
|---|---|
| The per-field keep rules on forced rewrites (`seo_title`, `takeaway`, `cap_rationale`, `corrections`, operator `source_overrides`) are described only in prose and live in `persistence.py`; a new loop that writes claims through a new writer drops them without any doc saying so | `content-model.md:64, 70, 72, 147-155`; `glossary.md:28`; `runbook.md:54`; roadmap RE-AH and RE-AK (`docs/v1.0.0-roadmap.md:284, 309-325`) |
| `models_used` carry-over (`dr step-audit --write` keeps entries of agents it did not run) and `pipeline_run.level_clamp` are RE-AK fixes; a loop with one sidecar writer must keep them | `content-model.md:116-117`; roadmap `:319` |
| The `refresh` block (snapshot of the last published state, `dropped_sources`) and the `corrections` entry on approval are the only public trail of a changed verdict; SP5's "recheck lands as a new draft, old stays live" is a different model and the two must not coexist half-done | `content-model.md:147-153`; `research-flow.md:240`; `runbook.md:73-82` |
| `dr claim-probe` must write nothing and never ask archive.org to capture; `dr step-ingest` without `--write` likewise. SP1's one loop with a persist switch is the exact risk `open-issues.md` §3 named; the probe-vs-draft test is the guard | `open-issues.md:52-62`; `AGENTS.md:177, 185`; `content-model.md:91`; `runbook.md:86` |
| `dr review` tty rule (stdin must be a tty, slug typed back; agents never run it or wrap it in a pty) is a sign-off integrity rule, not a convenience; a folded `review` command must keep it | `AGENTS.md:187`; `glossary.md:164`; `runbook.md:79` |
| `dr publish` refuses a draft whose verdict differs from the sidecar analyst verdict without `verdict_override` (RE-U) and skips refreshed claims; folding `publish` into `review` must keep both refusals | `research-flow.md:239-240`; roadmap RE-U `:468` |
| Lint checks `published-without-criterion` (error), `verdict-sidecar-mismatch`, `refresh-pending-review`, `verification-level-pool-mismatch` encode lifecycle rules; SP6 (templates become sentences) makes `published-without-criterion` block every claim unless rewritten | `checks.py:115, 186, 221, 770`; `claim-restate.md:79, 425`; `runbook.md:80-82` |
| Topic locking: template-backed claims take topics from the template; ad hoc claims take the analyst's; SP6 removes the template side and must say where topics come from | `onboarding.md:151`; `analyst-decomposition_stub.md:10` |
| Entity match (`_apply_entity_match`) and the level fit (`fit_verdict_to_written_pool`) run on some paths and not others; a loop must call both once, in the documented order (match before the analyst, fit before the write) | `source-quality.md:33-40, 62-74` |
| Instruction files (`pipeline/*/instructions.md`, `pipeline/common/verdict-scale.md`) are exempt from the release gate (`.md` suffix); edits to them are behavior changes with no gate check | `release_common.py:54`; `AGENTS.md:138` |
| The pre-commit hook is untracked and runs `pipeline/.venv/bin/dr lint`; a command rename or venv move breaks every commit silently (hook exits 0 when `dr` is missing) | `.git/hooks/pre-commit:6-10` |
| The `lint-content` CI job runs `uv run dr lint --format json --severity error`; renaming `lint` or its flags breaks CI | `ci-deploy.md:31-33`; `research-workflow.md:89` |
| `research/entities/drafts/` is the documented reject path for `review_onboard`; the directory does not exist on disk; removing onboard removes the only writer | `onboarding.md:133`; `persistence.py:1147-1151` |
| `research/QUEUE.md` is the documented intake and is empty; three docs and the glossary "queued" state depend on it | `research-flow.md:49-57`; `research-workflow.md:17, 119`; `glossary.md:142, 155`; `AGENTS.md:115` |
| `vision-state-machine.md:29` and `AGENTS.md:11, 17` state the open-loop principle and "only Analyst and Evaluator may invoke frontier models"; SP2's tie-breaker contradicts both unless the sentences are rewritten with the Q3 decision | `AGENTS.md:11, 17`; `vision-state-machine.md:29`; `glossary.md:7, 70` |
| `docs/plans/claim-restate.md` is a committed, reviewed plan; marking RE-AC "absorbed" needs the plan moved (`completed/` with a superseded banner or `deferred/`) per AGENTS.md rules 3 and 8, and the `docs/UNSCHEDULED.md:380` follow-ups row re-pointed | `AGENTS.md:267, 272, 335`; `claim-restate.md:3-7` |
| The hidden aliases `dr reassess` and `dr ingest` are named in four docs; deleting them without a doc pass leaves dangling references | `AGENTS.md:181`; `research-flow.md:37`; `research-workflow.md:50`; `glossary.md:62, 64, 156, 162` |
| The `audit.auditor_*` sidecar field names and the `auditor/` package name are public (the site reads `audit.*`); a rename during SP1/SP2 touches `src/content.config.ts` and every sidecar on disk | `content-model.md:131-140, 159` |
| Subject claims live at `research/claims/subjects/<slug>/`, one level deeper than `content-model.md:24-26` shows; `_resolve_claim_path` globs one level (`claim-restate.md:151`) | `content-model.md:24-26`; `claim-restate.md:151` |
| Line numbers in `claim-restate.md` and both stubs are stale (HEAD `0b3d0a9` and April 2026); a spike that copies them copies wrong anchors | `claim-restate.md:6`; `analyst-decomposition_stub.md:9-10`; `ingestor-decomposition_stub.md:9` |

## 6. Open questions

1. Does SP7 (fold side tools to about five commands) keep `lint` as a `dr` subcommand? CI (`ci-deploy.md:31`), the pre-commit hook and `inv check` call it by that name.
2. Where do `wayback-backfill`, `stats`, `entity-enrich`, `step-*` and `claim-promote` go under five commands: deleted, folded as flags, or kept hidden? The interview names only draft, recheck, review, findings, lint.
3. SP3 (restate in loop) vs `claim-restate.md` D5: does restatement run on every ad hoc draft, or only when the verdict is `unverified`?
4. SP5: when a recheck "lands as a new draft" while the old published claim stays live, what is the file layout (two files for one claim? a sidecar-only draft?) and what replaces the `refresh` block and `corrections` entry? `content-model.md:147-153` and `runbook.md:73-82` need a decided answer before they can be rewritten.
5. SP6: with templates gone, what satisfies `published-without-criterion` (lint error) and the criteria page (`src/pages/research/criteria/[slug].astro`, roadmap `:338`)? Is the comparison-matrix row keyed on `criteria_slug` (`claim-restate.md:470`) kept?
6. SP8 (companies out): are existing `research/entities/companies/` files and `parent_company` references deleted, or left on disk and ignored? `source-quality.md:62-74` entity-match rules read `parent_company`.
7. Is `research/QUEUE.md` retired? It is empty and three docs describe it as the intake.
8. Which doc becomes the home of the "command contract" the run decisions call for: `AGENTS.md` § Tooling (today's list), `docs/runbook.md` (TODO says "Content pipeline"), or a new `docs/architecture/pipeline-commands.md` linked from `docs/architecture/README.md`?
9. Does the findings file (Q4) get a schema row in `content-model.md`, or is it operator data outside `research/` (and therefore outside the Astro schema)?
10. Does the project CLAUDE.md "Research content changes to `research/claims/` should go through PRs" line stay? `research-flow.md` § 5 is built on it; the memory and interview assume direct commits.
