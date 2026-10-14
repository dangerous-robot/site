# Pipeline map: the Analyst and the Auditor (Evaluator)

Phase 1 (Challenge) reader output for the research pipeline rebuild. Facts carry `file:line`; paths are relative to the repo root `/Users/brandon/dev/ai/dangerous-robot/site`. "Not found" means the fact is not on disk. Line numbers are as of 2026-10-14 (HEAD `40ba781`).

Scope: `pipeline/analyst/` (agent.py 359 lines, citations.py 180, instructions.md 260), `pipeline/auditor/` (agent.py 78, bundle.py 51, compare.py 97, models.py 78, report.py 75, instructions.md 58), `pipeline/common/verdict-scale.md` (19 lines), and `fit_verdict_to_written_pool` (lives in `pipeline/orchestrator/persistence.py:354-445`, not in analyst/ or auditor/).

---

## 1. Entry points (who calls the two agents)

| Entry | Where | Analyst call | Evaluator call | Graded statement | Criterion notes reach both? |
|---|---|---|---|---|---|
| `verify_claim` (used by `dr onboard`, `dr claim-refresh`, `dr claim-probe`) | `pipeline/orchestrator/pipeline.py:345-553` | `_analyse_claim` at `:504-510` | `_audit_claim` at `:535-538`, only when `_graded_statement` (`:522-524`) returns a statement | Analyst's title when it passes the template; the operator's text when there is no template (`:1513-1532`) | Yes, one value computed at `:503` |
| `research_claim` (`dr claim-draft`) | `pipeline.py:1619-1868` | not shown in this read; the level fit and write are at `:1795-1820` | `_audit_claim` at `:1832-1836` with `analyst_out.verdict.title` and the cited sources, **no `criterion_notes`** | The analyst's title it writes (`:1833`), not the operator's sentence | No: ad hoc claims have no template, so neither agent gets notes |
| `onboard_entity` per-template loop (`dr onboard`) | `pipeline.py:2293-2975` | inside `verify_claim` | inside `verify_claim`; result reused as `vr.consistency` at `:2952` | as `verify_claim` | as `verify_claim` |
| `dr step-analyze` | `pipeline/orchestrator/cli.py:632-808` | `_analyse_claim` at `:732-739` with `criterion_notes=template.notes` | none; `--write --force` clears the sidecar's Evaluator block (`clear_audit`, `:779`; `docs/runbook.md:75`) | n/a | analyst only |
| `dr step-audit` (`dr reassess` is a hidden alias, `cli.py:1726-1743`) | `cli.py:1518-1723` | none | builds `ClaimBundle` by hand (`:1627-1636`) and calls `auditor_agent.run(prompt)` directly (`:1644-1645`) | `fm["title"]` from the claim file (`:1630`); blocked claims skipped (`:1593-1595`) | Evaluator gets `template.notes` via `_claim_template` (`:1626`, `:1635`) |
| `dr claim-probe` | `cli.py:878-930`, prints with `_print_verify_result` (`:810-877`) | via `verify_claim` with no template | via `verify_claim`; grades the operator's text | operator's text | none (no template) |

Live command list: `.venv/bin/dr --help` groups `step-analyze`, `step-audit`, `claim-probe` under "Read-only" and `onboard`, `claim-draft`, `claim-refresh`, `claim-promote` under "Creates or overwrites claim files". Note `step-analyze --write` and `step-audit --write` do write, despite the heading.

---

## 2. The Analyst

### 2.1 Agents and prompt assembly

| Fact | Location |
|---|---|
| Two PydanticAI agents share one system prompt: `analyst_agent` (output `AnalystOutput` = entity + verdict) and `verdict_only_agent` (output `VerdictAssessment`); both `retries=2`, placeholder model `"test"` overridden per call | `pipeline/analyst/agent.py:252-266` |
| System prompt = `instructions.md` + `common/verdict-scale.md` appended with a blank line | `agent.py:252`; loader `pipeline/common/instructions.py:10-33` |
| `verdict_only_agent` is used when the entity is pre-resolved from disk; `analyst_agent` (which also infers the entity) otherwise | `pipeline/orchestrator/pipeline.py:1476-1499` |
| Model per agent: `VerifyConfig.model_for("analyst")`, falling back to `--model`; default `greenpt:gpt-oss-120b` | `pipeline.py:336-338`; `pipeline/common/models.py:201` |
| Timeout 120 s each for analyst and auditor; null-body and rate-limit retries wrap the call | `pipeline.py:308-309`, `_run_with_null_retry` `:1384-1434` |
| Before the prompt, `_apply_entity_match` relabels each source's `independence` in place for this claim (entity's own page → `first-party`; another organization's first-party page or an independent source that never names the entity → `unknown`), returning overrides marked `_code_relabel=True` | `pipeline.py:556-623`; `SourceOverride._code_relabel` `agent.py:139` |
| Prompt sections, in order: `## Entity (pre-resolved — do not infer)` block (name, type, description, aliases, legal name, founded, parent, verification status) or `## Entity: name`; `## Claim to evaluate`; `## Criterion notes`; `## Sub-questions` (each with rationale; an uncovered one gets the marker "no source addresses this sub-question; describe this gap in plain words and never write the sub-question id"); `## Source materials` with `### {title}`, `Source id`, `Publisher`, `Kind`, `Independence`, `Addresses`, `Summary`, `Key quotes`, `Full text`; closing line "Based on the sources above, draft a structured claim assessment." | `agent.py:269-359` |
| "Full text" is the ingest model's short body, not page text | `agent.py:347-348`; backlog RF20 `docs/UNSCHEDULED.md:361` |
| The analyst prompt deliberately has no numbered source headings (so the model is not nudged into "Source N") | test `pipeline/tests/test_analyst.py:66`; backlog RF4 history `docs/UNSCHEDULED.md:346` |

### 2.2 Output schema (`VerdictAssessment`)

| Field | Rule | Location |
|---|---|---|
| `title` | free string; instructions require the claim text verbatim with three mechanical transforms; orchestrator validates with `validate_analyst_title` | `agent.py:145`; `instructions.md:55-84`; `pipeline.py:1527` |
| `verdict` | `Verdict` enum: true, mostly-true, mixed, mostly-false, false, unverified, not-applicable | `agent.py:146`; `pipeline/common/models.py:76-83` |
| `confidence` | `Confidence` enum: high, medium, low | `agent.py:147`; `models.py:86-90` |
| `narrative` | 2-5 sentences, Markdown; validator inserts blank lines around lists (MD032) | `agent.py:148`, `:25-58`, `:214-217` |
| `topics` | 1-3 `Category` values | `agent.py:149-153` |
| `verification_level` | required; 5-level enum claimed … multiply-verified | `agent.py:154-160`; `models.py:160-171` |
| `cap_rationale` | optional, max 400; required by prose when level is claimed/self-reported; must not cite a source | `agent.py:161-170`, `:233-242` |
| `source_overrides` | optional list of `{source, independence, reason(max 300)}` | `agent.py:117-139`, `:171-178` |
| `cited_sources` | list of source ids the verdict relies on; default empty | `agent.py:179-186` |
| `seo_title` | required, 1-42 chars, rejected if it looks truncated | `agent.py:187-197`, `:219-223`, heuristics `:61-102` |
| `takeaway` | optional, max 200, must end in `.!?`, no citations | `agent.py:198-207`, `:225-242` |
| `_cap_rationale_fitted` | private attr, set by the level fit when it wrote the rationale | `agent.py:209-212`; set at `persistence.py:439`; read at `:346` |

Validation failures (truncation, citation in a short field) raise `ValueError`, which PydanticAI turns into a retry (`retries=2`). Nothing records how many retries a run spent; not found.

### 2.3 Verdict scale and confidence (`pipeline/common/verdict-scale.md`)

| Fact | Location |
|---|---|
| Seven verdicts with one-line definitions; `unverified` = sources sought but none engage the central assertion; `not-applicable` = template targets another entity type or the question is inapplicable | `verdict-scale.md:3-9` |
| Confidence is "the strength of the evidence base, independent of which verdict"; high = multiple independent sources with direct evidence, with a vocabulary-claim exception (one named exchange or regulator suffices); medium = single source, self-reported or ambiguous; low = thin, contradictory, anecdotal | `verdict-scale.md:13-17` |
| For `unverified`, confidence means how thoroughly the search circled the claim | `verdict-scale.md:19` |
| Same file is appended to both the analyst and the Evaluator prompts | `analyst/agent.py:252`; `auditor/agent.py:13` |
| The verdict list also lives as the Python enum, the TS enum, and the glossary table | `models.py:76-83`; `src/lib/verdict.ts:2`; `docs/architecture/glossary.md:40-49` |

### 2.4 Analyst rules in prose (`pipeline/analyst/instructions.md`)

| Rule | Lines |
|---|---|
| Entity identification; legal name; founded year; verification status (sparse coverage is a reason to lower confidence and reach for `unverified`) | 11-47 |
| TITLE: verbatim claim text; three allowed transforms; "flag it as unresolvable so the orchestrator can mark it blocked" when no vocabulary option is supported | 55-84 |
| SEO_TITLE and TAKEAWAY | 86-105 |
| Cite by italic title; never ids, bracket tokens or "Source N" | 110-112 |
| `cited_sources` lists every source named or relied on | 113-115 |
| `unverified` only when sources circle without engaging; vocabulary claims must reason through each option; `mixed` when a reader would be misled; medium is the default confidence | 116-133 |
| SUB-QUESTION COVERAGE: an uncovered sub-question forbids `true`/`false` at `high`; choose `unverified` or render at `medium`; "editorial, not mechanical" | 139-157 |
| SOURCE QUALITY: level derivation from `independence` + `kind` (first matching level wins, strongest first); `unknown` counts as neither; FIRST-PARTY ARTICLE BOUNDARY | 159-192 |
| `cap_rationale` templates (three sentences, written with `--`) | 194-207 |
| CONFIDENCE CAP: claimed/self-reported ⇒ `confidence: low`; "a lint check enforces this" | 209-212 |
| RESTATEMENT TEST: independent source that only restates → `source_overrides` entry `first-party` | 214-223 |
| ABSENCE OF EVIDENCE: "no contradicting evidence found" claims should be `unverified`; an index source supports no "does not list X" statement unless its text enumerates comparable items | 225-238 |
| CRITERION NOTES: scope, verdict mapping, narrative coverage; notes are not evidence | 240-251 |
| PRECEDENCE: a note's verdict mapping beats the scale, the absence default, and coverage step 3's `unverified`; step 3's confidence cap still applies | 253-260 |

The "unresolvable" flag at `instructions.md:76-77` has no field in `VerdictAssessment` (`agent.py:142-242`); the orchestrator instead blocks on `validate_analyst_title` (`pipeline.py:1527`). Not found: any output field or tool for the analyst to flag a claim unresolvable.

### 2.5 Citation rules (`pipeline/analyst/citations.py`)

| Fact | Location |
|---|---|
| One regex matches bracket runs `【id】` and numbered references ("Source N", "Sources 2, 4", lowercase "sources 2 and 4") | `citations.py:39-46` |
| `NO_CITATION_FIELDS = ("takeaway", "cap_rationale")`: the schema rejects citations there; `dr lint` checks the same fields | `citations.py:57`; `agent.py:233-242`; `pipeline/linter/checks.py:11`, `:691-723` |
| `clean_citations(narrative, sources)`: bracket ids resolve on `source_id` or `slug` to italic titles; unknown bracket ids are deleted; "Source N" maps to `sources[N-1]` in prompt order; out-of-range numbers are left for lint | `citations.py:92-132`; called from `_clean_verdict_citations` `pipeline.py:1501-1510` |
| `cited_source_ids(verdict, sources, overrides)`: union of `cited_sources`, sources named in overrides, and sources whose title appears in the narrative as whole words after folding dashes and curly quotes; ids outside `sources` ignored; empty means "unknown", not "none" | `citations.py:137-180` |
| `_apply_cited_filter` narrows the claim's listed sources to the cited ones, but keeps the full list when nothing is cited or when the cited subset would fit a lower `verification_level` (trial run of the level fit on a deep copy, `:1598-1603`) | `pipeline.py:1572-1616` |
| The Evaluator grades against the cited (listed) sources, not the full consulted pool | `pipeline.py:532-538`, `:1832-1836`; `docs/architecture/research-flow.md:76` |
| On disk: 62 of 90 listed sources across 12 claims were never named by title in the narrative (RE-AL row) | `docs/v1.0.0-roadmap.md:335` |

---

## 3. The level fit and confidence clamp (`fit_verdict_to_written_pool`)

Lives at `pipeline/orchestrator/persistence.py:354-445`; documented at `docs/architecture/source-quality.md:31-40`.

| Step | Location |
|---|---|
| Drops `source_overrides` for sources not in the written `source_ids` | `persistence.py:386-390` |
| Returns `None` (no change) when the level needs no independent source and is not `self-reported` (`claimed`, or a level outside the table) | `:392-395`; table `INDEPENDENT_SOURCES_REQUIRED` `models.py:175-179` (partially 1, independently 1, multiply 2) |
| Counts effective independence per written ref: override wins over the (already relabelled) source label; a ref listed twice counts twice | `effective_independence` `pipeline/common/source_classification.py:313-327`; called at `:402-406` |
| `self-reported` with no independent source and no first-party report/documentation/dataset/article falls to `claimed` | `:414-419`; kinds `models.py:182-185` |
| A level short of its independent count falls to `independently-verified` (if ≥1), else `self-reported` (if a first-party report/doc/dataset is written), else `claimed` | `:420-431` |
| When the new level is `self-reported` or `claimed`: `confidence = low`, and a template rationale "Confidence is capped at low: no source on this claim independently addresses <entity>." is written when the analyst gave none or when `self-reported` fell to `claimed`; `_cap_rationale_fitted` marks the former | `:432-443` |
| Returns a one-line note; callers store it as `pipeline_run.level_clamp` | `:444-447`; sidecar write `persistence.py:1044-1045` |
| Called just before the claim write in all four write paths | `pipeline.py:1795` (claim-draft), `:2925` (onboard), `cli.py:1320` (claim-refresh), `cli.py:745` (step-analyze) |
| Called on a deep copy, `log=False`, by the cited filter | `pipeline.py:1598-1600` |
| The fit runs **after** the Evaluator comparison in `verify_claim` paths (comparison at `pipeline.py:535`, fit at `:2925` / `cli.py:1320`), so the sidecar `audit.analyst_confidence` is the pre-fit value | RE-AL row `docs/v1.0.0-roadmap.md:333` |
| No sidecar on disk has a `level_clamp` entry (grep over all 11 sidecars, 2026-10-14) | `research/claims/**/*.audit.yaml` |

Lint checks that mirror the fit: `check_confidence_cap_violation` (warning) `linter/checks.py:527-556`; `check_missing_cap_rationale` (warning) `:559-589`; `check_verification_level_pool` (warning; same counting rule) `:726-794`. Site-side count: `countSourcesByIndependence` `src/lib/sourceQuality.ts:58`. Backlog RF25: lint reads file labels only while the analyst gets a `source_type`-derived fallback label (`docs/UNSCHEDULED.md:376`).

---

## 4. The Evaluator (package `pipeline/auditor/`)

### 4.1 Prompt and schema

| Fact | Location |
|---|---|
| One agent `auditor_agent`, output `IndependentAssessment`, `retries=2`, same `verdict-scale.md` fragment | `pipeline/auditor/agent.py:13-20` |
| `IndependentAssessment`: `verdict`, `confidence`, `reasoning` (2-4 sentences), `evidence_gaps: list[str]` | `pipeline/auditor/models.py:46-61` |
| `ClaimBundle` carries `claim_id`, `claim_text` (the statement graded), entity, topics, narrative, sources, `criterion_notes`; by design no analyst verdict, confidence, level or cap | `models.py:29-43`; tests `pipeline/tests/test_auditor_agent.py:91-122` (`TestBundleNeverLeaksVerdict`, incl. `test_prompt_excludes_level_and_cap` `:109`) |
| `SourceContext` = id, title, publisher, summary, key_quotes, body: **no `kind`, no `independence`, no `source_id`** reach the Evaluator | `models.py:10-18`; `bundle.py:31-41` (id is `src["slug"]`) |
| Prompt order: `## Entity`, `## Topics`, `## Claim`, `## Criterion notes`, `## Analyst narrative (context; not the thing you grade)`, `## Source Materials` with `### Source {i}: {title}` (numbered), closing "Judge the claim above … give your independent verdict and confidence on that claim." | `agent.py:23-78` |
| `claim_id` in a run is `verify/{entity-slug}` and `claim_file` is `"(draft -- not yet saved)"`; neither is persisted | `bundle.py:44`; `pipeline.py:1563-1569` |

### 4.2 Evaluator rules in prose (`pipeline/auditor/instructions.md`)

| Rule | Lines |
|---|---|
| Inputs: claim statement (graded), narrative (argument), sources, entity, criterion notes | 1-8 |
| Grade the claim, not the narrative; if no source engages the claim, `unverified` even when the narrative correctly says so; no own knowledge; verdict may be stronger or weaker than the narrative; "Do not default to agreement" | 15-27 |
| CRITERION NOTES: a note's mapping beats the scale and the `unverified` rule; "a verdict that follows a note's mapping is not a scale mismatch" | 29-42 |
| EVIDENCE GAPS: what no source addresses, and narrative assertions no source backs | 44-47 |
| CONFIDENCE CAP mirrors the analyst's: select `low` when the pool is entirely entity documentation or restatements. The Evaluator is never told the level or any independence label (4.1), so it must infer the pool's independence from publisher names and text | 49-58 |

### 4.3 Comparison and the agreement record (`pipeline/auditor/compare.py`)

| Fact | Location |
|---|---|
| `VERDICT_ORDER`: true 0, mostly-true 1, mixed 2, mostly-false 3, false 4; `unverified` and `not-applicable` are off-scale | `compare.py:9-16` |
| `CONFIDENCE_ORDER`: high 0, medium 1, low 2 | `:18-22` |
| Severity: equal → `match`; either side off-scale → `major`; distance 1 → `adjacent`; 2 → `major`; 3-4 → `opposite` | `_verdict_severity` `:25-41`; enum `models.py:194-199` |
| `needs_review` reasons: "verdict disagreement" (major or opposite); "confidence gap" (adjacent and confidence ≥2 steps apart); "2+ evidence gaps" (more than one gap listed, even on a match) | `_review_reasons` `:49-57`; `needs_review_reasons` `:60-66` |
| `verdict_agrees` is plain equality; `confidence_agrees` likewise; `needs_review = bool(reasons)` | `compare` `:69-97` |
| `ComparisonResult` fields: claim_id, claim_file, primary/assessed verdict and confidence, reasoning, evidence_gaps, verdict_agrees, confidence_agrees, verdict_severity, needs_review | `models.py:64-78` |
| In a run, "primary" = the analyst's verdict and confidence (pre-fit); in `dr step-audit`, "primary" = the claim file's frontmatter `verdict` and `confidence` (post-fit, possibly operator-edited) | `pipeline.py:1563-1565`; `cli.py:1596-1597`, `:1646` |
| Text and JSON reports for `step-audit` | `pipeline/auditor/report.py:10-75` |

### 4.4 Where the record is stored and read

| Consumer and what it reads | Location |
|---|---|
| Sidecar writer: `audit` block with 10 keys (`analyst_verdict`, `auditor_verdict`, `analyst_confidence`, `auditor_confidence`, `verdict_agrees`, `confidence_agrees`, `needs_review`, `auditor_reasoning`, `evidence_gaps`, `needs_review_reasons`); `null` when no comparison | `persistence.py:953-966` |
| Site schema: `audit` object nullable with the same keys; `human_review.verdict_override {from,to}` | `src/content.config.ts:73-92` |
| Claim page "Verdict check" panel: Analyst (conf), Evaluator (conf), "Verdicts agree/differ", "Flagged for human review: reasons", then reasoning and gaps | `src/pages/research/claims/[...slug].astro:86`, `:207-233` |
| Field doc | `docs/architecture/content-model.md:131-140` |
| `dr review-queue`: header shows analyst/auditor verdicts and a "needs review" flag; TSV column | `pipeline/orchestrator/review_queue.py:39-40`, `:104-105`, `:180-184`, `:521-526` |
| `dr review --approve`: writes `human_review.verdict_override` when the file's verdict differs from `audit.analyst_verdict` | `pipeline/orchestrator/review.py:154`, `:199`, `:274` |
| `dr publish`: skips a draft whose verdict differs from `audit.analyst_verdict` with no recorded override | `cli.py:2314-2316`, `:2435-2439`; `review.py:166-174` |
| Lint `verdict-sidecar-mismatch` (error): a published verdict must equal `audit.analyst_verdict` or match the override | `linter/checks.py:158-195` |
| Checkpoint `review_disagreement`: CLI prints Analyst/Auditor/Severity and asks "Accept this result?" (default No); auto handler returns True and only records the call. A "No" appends "Flagged for human review: …" to `result.errors`; the claim file is already written by then in `research_claim` | `pipeline/orchestrator/checkpoints.py:117-122`, `:207-218`, `:344-349`; gates `pipeline.py:543-549`, `:1860-1864`; `cli.py:1344-1347` |
| `needs_review` is not read by `dr stats` or any other orchestrator module (grep) | not found outside cli.py, pipeline.py, persistence.py, review_queue.py |
| Design intent: "open-loop: disagreements surface to the operator and are not auto-resolved" | `AGENTS.md:11`; `docs/architecture/glossary.md:7`; `research-flow.md:108-116` |

### 4.5 Research data today (11 claims on disk, not 10: 6 product + 5 subject)

| Claim | Analyst / Evaluator | verdict_agrees | needs_review | Sidecar lines |
|---|---|---|---|---|
| chatgptree/renewable-energy-hosting (published) | unverified / true | false | true | `research/claims/chatgptree/renewable-energy-hosting.audit.yaml:153-170` |
| earthly-insight/… (published) | unverified / unverified | true | false | `earthly-insight/….audit.yaml:177-195` |
| ecosia-ai/… (published) | mixed / true | false | true (verdict disagreement, 2+ evidence gaps) | `ecosia-ai/….audit.yaml:199-219` |
| euria/… (published) | true / true | true | false | `euria/….audit.yaml:173-194` |
| greenpt/… (published) | true / true | true | false | `greenpt/….audit.yaml:184-202` |
| viro-ai/… (published) | unverified / true | false | true | `viro-ai/….audit.yaml:158-175` |
| subjects/ai-model-producers/ai-producers-existential-score (published) | true / true | true | false | `….audit.yaml:198-206` |
| subjects/generative-ai/answering-…-web-search (draft) | unverified / true | false | true | `….audit.yaml:187-207` |
| subjects/generative-ai/serving-…-inference (draft) | true / true | true | false | `….audit.yaml:225-241` |
| subjects/generative-ai/using-generative-ai-harms-cognitive-ability (published) | true / mostly-true | false | true | `….audit.yaml:184-192` |
| subjects/us-data-centers/there-are-fewer-than-10-… (draft) | unverified / true | false | true | `….audit.yaml:172-188` |

Totals: 6 of 11 disagree; 6 of 11 flagged. All 11 record `analyst: greenpt:gpt-oss-120b` and `auditor: greenpt:gpt-oss-120b` (same model for both, backlog RF16 `docs/UNSCHEDULED.md:357`). Four claim files carry `source_overrides` (chatgptree, earthly-insight, greenpt, viro-ai). Five of the six disagreements are the pre-RE-AD "Evaluator graded the narrative" pattern (`docs/v1.0.0-roadmap.md:235`), still on disk because the live re-audit was shelved (`docs/UNSCHEDULED.md:442`).

---

## 5. Where RE-AD and RE-AG landed

### RE-AD (Evaluator grades the claim), status done in beta.7 (`docs/v1.0.0-roadmap.md:233-249`)

| Piece | Location |
|---|---|
| `ClaimBundle.claim_text` is the statement graded; comment says the narrative is never the object | `auditor/models.py:33-36` |
| Prompt puts `## Claim` before the narrative, labels the narrative "(context; not the thing you grade)", closing line asks for a verdict "on that claim" | `auditor/agent.py:42-53`, `:73-76` |
| Instructions: grade the claim; an accurate narrative is not evidence; `unverified` when no source engages | `auditor/instructions.md:15-27` |
| `_graded_statement`: template-backed claim → analyst's title if it passes the template, else skip the audit (claim will be blocked); no template → operator's text | `pipeline.py:1513-1532`, used `:522-530` |
| `research_claim` grades the analyst's title it writes | `pipeline.py:1832-1833` |
| `dr step-audit` grades `fm["title"]`, skips blocked claims | `cli.py:1593-1595`, `:1630` |
| Tests | `tests/test_auditor_agent.py:158-166` (`TestEvaluatorGradesTheClaim`), `:219` (`TestAuditClaimSendsTheClaim`); `tests/test_orchestrator.py:955-1030` (`TestAuditorGradedStatement`) |
| Live check shelved; sidecars on disk still show the old pattern | `docs/v1.0.0-roadmap.md:240-249`; `docs/UNSCHEDULED.md:442` |
| Side effects logged as backlog: claim-draft no longer compares the analyst's title with the operator's text (`UNSCHEDULED.md:421`); claim-refresh without templates grades the old title and writes a new one (`:420`); "Size the narrative-grading effect on published sidecars" (`:399`) | as cited |

### RE-AG (Analyst prompt: criterion notes and absence claims), status done in beta.7 (`docs/v1.0.0-roadmap.md:273-282`)

| Piece | Location |
|---|---|
| `build_analyst_prompt(criterion_notes=…)` emits `## Criterion notes` after the claim | `analyst/agent.py:276`, `:305-308` |
| Analyst CRITERION NOTES and PRECEDENCE sections | `analyst/instructions.md:240-260` |
| Absence rule (index pages) | `analyst/instructions.md:232-238` |
| `ClaimBundle.criterion_notes`; `build_bundle(criterion_notes=)`; auditor prompt `## Criterion notes`; Evaluator CRITERION NOTES section | `auditor/models.py:40-43`; `bundle.py:19`, `:50`; `agent.py:46-49`; `instructions.md:29-42` |
| `verify_claim` computes notes once for both agents; `dr step-analyze` and `dr step-audit` share `_claim_template` | `pipeline.py:501-503`; `cli.py:2229`, `:702`, `:1626` |
| Decision record: notes bind both agents; "grading rules move to their own per-criterion field in beta.8 (RE-AL)" | `docs/decisions.md:10` |
| Tests | `tests/test_analyst.py:321-381`; `tests/test_auditor_agent.py:259-280` |
| Not covered: `research_claim` (ad hoc / subject claims) never passes notes to either agent | `pipeline.py:1832-1836` |

Other beta.7 items touching this subsystem, for the "must not be lost" list: RE-AE entity match and level fit (`pipeline.py:556-623`, `persistence.py:354-445`); RE-AF cited filter and uncovered sub-question marker (`pipeline.py:1572-1616`, `analyst/agent.py:310-326`); RE-AH/RE-AK operator-field keep rules via `analyst_record` (`persistence.py:465-586`, `:657-683`; `step-audit --write` keeps `models_used` and `level_clamp`, `cli.py:1667`, `:1714-1718`).

---

## 6. Where a tie-breaker third pass would plug in

The interview (handoff `2026-10-13-pipeline-improvement-interview.md:22`, Q3) wants: a larger model with more thinking budget runs when Analyst and Evaluator disagree; agreement settles it; a remaining split falls to the weaker verdict.

| Plug point | Today | Location |
|---|---|---|
| Trigger | `comparison.needs_review` (which also fires on "2+ evidence gaps" with agreeing verdicts) or `not comparison.verdict_agrees` | `pipeline.py:543`, `:1860`; `compare.py:49-57` |
| Earliest place that has both opinions | right after `_audit_claim` returns, before the sidecar write: `verify_claim` `:535-540` (onboard/refresh/probe), `research_claim` `:1832-1838` (claim-draft) | as cited |
| Ordering problem | In `research_claim` the claim file is written (`:1805-1820`) **before** the audit (`:1832`); in `onboard` the claim is written from `ao.verdict` (`:2928-2944`) after `verify_claim` returned. A third verdict that should land in `verdict:` must run before `_write_claim_file` in both, and the level fit (`:1795`, `:2925`) must run on whichever verdict is written | `pipeline.py` as cited |
| Record | `audit` block has exactly two sides (`persistence.py:953-966`); site schema and page likewise (`content.config.ts:73-85`, `[...slug].astro:207-233`); `content-model.md:131-140` | a third side needs new keys in all three |
| Publish and lint anchors | `dr publish` and lint compare the published verdict with `audit.analyst_verdict` only (`cli.py:2435-2439`; `linter/checks.py:178`); `dr review --approve` writes `verdict_override` from `analyst_verdict` (`review.py:154`, `:274`) | a tie-breaker verdict written into the claim would be a "mismatch" unless these learn a new anchor (e.g. a `pipeline_verdict`) |
| Model slot | `AGENT_NAMES = ("researcher","analyst","auditor","ingestor")` with a comment that adding an agent means editing the tuple and `VerifyConfig` fields; CLI has `--<agent>-model` options | `models.py:68-73`; `pipeline.py:269`; `cli.py:200-230`. The claim-restate plan chose not to extend the tuple (restater falls back to `--auditor-model`, `docs/plans/claim-restate.md:39`, `:160`) |
| Model-tier rule | "only Analyst and Evaluator may invoke frontier models" | `AGENTS.md:17` |
| `step-audit --write` carry-over | keeps `models_used` of other agents and `level_clamp`; `human_review` kept unless `reset_review`; any new sidecar key must be carried the same way | `cli.py:1667`, `:1714-1718`; `persistence.py:975-986`, `:1000-1006` |
| "Weaker verdict" | not defined anywhere. `VERDICT_ORDER` is a polarity axis (true…false), not a strength axis; `unverified` and `not-applicable` are off it (`compare.py:9-16`). The analyst's SUB-QUESTION COVERAGE text uses "weaker" to mean lower confidence or `unverified` (`analyst/instructions.md:148-154`) | open question |
| Review packet Q6 (verdict chain on one screen) | the page already prints Analyst, Evaluator, reasoning and gaps (`[...slug].astro:207-233`); the original operator sentence is not stored for claim-draft claims (the title is the analyst's, `pipeline.py:1833`); `UNSCHEDULED.md:421` | gap for SP3/SP4 |

---

## 7. Duplication

| What | Locations |
|---|---|
| Verification-level counting rule, four copies: analyst prose, write-time fit, lint, site | `analyst/instructions.md:165-192`; `persistence.py:354-445`; `linter/checks.py:726-794`; `src/lib/sourceQuality.ts:58` (`effective_independence` is shared by only the middle two, `source_classification.py:313-327`) |
| Confidence cap, four copies: analyst prose, Evaluator prose, level fit code, lint | `analyst/instructions.md:209-212`; `auditor/instructions.md:49-58`; `persistence.py:432-433`; `linter/checks.py:527-556` |
| `cap_rationale` template sentences in three spellings (em dash, `--`, colon) | `docs/architecture/source-quality.md:118-120`; `analyst/instructions.md:198-204`; `persistence.py:440-443`; backlog `docs/UNSCHEDULED.md:411` |
| Evaluator call path: `_audit_claim` vs `dr step-audit` hand-built bundle (the latter has no timeout, no null-body retry, `SourceContext.id = sid` not slug, sources from `load_source`) | `pipeline.py:1535-1569`; `cli.py:1598-1646` |
| Level fit + claim write + sidecar write sequence, four copies | `pipeline.py:1795-1857` (claim-draft); `:2925-2965` (onboard); `cli.py:1320-1340` (claim-refresh); `cli.py:745-808` (step-analyze, no sidecar) |
| `needs_review` gate, three copies | `pipeline.py:543-549`; `:1860-1864`; `cli.py:1344-1347` |
| Criterion-notes rules (not evidence; definition-pointer notes add nothing; commentary ignored; mapping beats the scale) restated in both prompts | `analyst/instructions.md:240-260`; `auditor/instructions.md:29-42` |
| Verdict list: Python enum, TS enum, prose scale, glossary, compare ordering | `models.py:76-83`; `src/lib/verdict.ts:2`; `verdict-scale.md:3-9`; `docs/architecture/glossary.md:40-49`; `compare.py:9-16` |
| Two analyst agents differing only in output type | `analyst/agent.py:254-266` |
| Agreement-record readers that each re-derive "verdict differs from analyst": publish, review, lint | `review.py:154-174`; `linter/checks.py:158-195` |
| The three near-copies of the pipeline (`verify_claim`, `research_claim`, onboard loop) each wire the analyst and Evaluator slightly differently (notes, graded statement, cited filter, write order) | `docs/architecture/open-issues.md:56`; §1 above |

---

## 8. Hazards (what a rewrite could silently lose or break)

| Hazard | Location |
|---|---|
| The Evaluator is blind to the analyst's verdict, confidence, level, cap, and to every independence label and source id; tests pin this. Re-adding labels "to help the cap rule" changes the independence of the second opinion | `auditor/models.py:10-18`, `:29-43`; `tests/test_auditor_agent.py:91-122` |
| Comparison uses the analyst's pre-fit confidence; the written claim may show `low` after the fit while the sidecar says `medium`/`high` | `pipeline.py:535` vs `:2925`; `cli.py:1320`; RE-AL row `docs/v1.0.0-roadmap.md:333` |
| The claim is written before the audit in `research_claim`; a tie-breaker inserted "after compare" cannot change `verdict:` without reordering | `pipeline.py:1805-1836` |
| Publish, review and lint anchor on `audit.analyst_verdict`; any verdict in the claim file that is not the analyst's and not an override is a lint **error** and a publish skip | `linter/checks.py:158-195`; `cli.py:2435-2439`; `review.py:154-174` |
| The Evaluator grades only the cited (listed) sources; agreement rates change if a rewrite audits the full consulted pool | `pipeline.py:532-538`; `research-flow.md:76` |
| Private pydantic attrs carry pipeline state outside the schema: `SourceOverride._code_relabel` (decides what the cited filter counts) and `VerdictAssessment._cap_rationale_fitted` (decides whether the operator's rationale is kept); `model_copy(deep=True)` and `getattr` depend on them | `analyst/agent.py:139`, `:212`; `pipeline.py:1589`, `:1598`; `persistence.py:346`, `:439`, `:583` |
| Operator-field keep rules (`seo_title`, `takeaway`, `cap_rationale`, `corrections`, `tags`) depend on `analyst_record` in the sidecar; a sidecar rewrite that drops the record turns every operator edit into "the analyst's" | `persistence.py:519-586`, `:657-683`, `:949-952` |
| `dr step-audit` calls `auditor_agent.run` with no timeout and no null-body retry | `cli.py:1644-1645` vs `pipeline.py:1384-1434` |
| `step-audit --write` carries `level_clamp`, other agents' `models_used`, `research`, `sub_questions`, `acquisition` and `archive` by explicit code; a new sidecar key is dropped unless added there | `cli.py:1655-1721` |
| "Source N" resolves by prompt order (`sources[N-1]`); the analyst prompt is unnumbered on purpose and the Evaluator prompt is numbered; numbering the analyst prompt or reordering sources between prompt and cleaner mis-maps citations | `citations.py:123-124`; `tests/test_analyst.py:66`; `auditor/agent.py:58` |
| The cited filter keeps every ingested source when the cited subset would lower the level, so a claim can list uncited sources to hold `verification_level` | `pipeline.py:1603-1608` |
| `unverified` and `not-applicable` are off the severity scale: any mismatch with them is `major`; `unverified`/`unverified` is `match`; "weaker verdict" has no ordering for them | `compare.py:9-16`, `:33-34` |
| `needs_review` fires on "2+ evidence gaps" with agreeing verdicts; a rule keyed on `needs_review` as "disagreement" over-triggers | `compare.py:55-56`; RF9 history `docs/UNSCHEDULED.md:350` |
| The auto-approve checkpoint never blocks on disagreement; the only durable trace is `needs_review` in the sidecar and `result.errors` in the console | `checkpoints.py:344-349`; `pipeline.py:543-549` |
| Ad hoc and subject claims (`dr claim-draft`) get no criterion notes in either prompt, and the Evaluator grades the analyst's title, not the operator's sentence | `pipeline.py:1832-1836`; `docs/UNSCHEDULED.md:421` |
| Truncation and citation validators reject model output and spend retries (`retries=2`) with no record | `analyst/agent.py:61-102`, `:219-242`, `:258`, `:265` |
| The analyst instructions promise an "unresolvable" path (`instructions.md:76-77`) that has no output field; the orchestrator blocks via title validation instead | `analyst/agent.py:142-242`; `pipeline.py:1527` |
| The Evaluator prompt bundle `claim_id` is `verify/{entity}` and `claim_file` is a placeholder; a rewrite that stores `ComparisonResult` whole would persist junk ids | `bundle.py:44`; `pipeline.py:1567-1568` |
| The analyst sees the ingest model's 1-3 sentence body labelled "Full text"; ingest errors flow into verdicts (RF20); verdicts are unstable across reruns on the same sources (RF6) | `analyst/agent.py:347-348`; `docs/UNSCHEDULED.md:348`, `:361` |
| Subject entities: both prompts and the entity match reason about "the entity's own pages", COI and restatement; a subject (topic) has none, and `_apply_entity_match` applies only its first rule to subjects | `pipeline.py:588`; `docs/UNSCHEDULED.md:449-454` |
| `confidence-cap-violation` and `verification-level-pool-mismatch` are lint **warnings**; `verdict-sidecar-mismatch` is an **error** | `linter/checks.py:545`, `:759`, `:188` |
| Both agents ran the same model on every claim on disk; the second opinion's independence rests on prompt difference alone | sidecars `models_used`; `docs/UNSCHEDULED.md:357` |

---

## 9. Tests that pin this subsystem (`pipeline/tests/`)

| File | Covers |
|---|---|
| `test_analyst.py` (431 lines) | prompt sections, no numbered headings, sub-question marker, seo_title and takeaway validators, MD032, criterion notes in prompt, instruction anchors (absence rule, cited_sources rule) |
| `test_citations.py` (256) | bracket and "Source N" rewriting, short-field rejection, `cited_source_ids` matching |
| `test_auditor_agent.py` (319) | prompt contents, verdict/level/cap never leak, claim before narrative, `_audit_claim` sends the claim, notes reach the Evaluator |
| `test_auditor_models.py` (109) | bundle and assessment shapes |
| `test_compare.py` (217) | match, adjacent, major, opposite, unverified off-scale, evidence-gap trigger, reasons |
| `test_orchestrator.py` | `TestAuditorGradedStatement` (`:955-1030`), `TestCitedSourceFilter` (`:1243`), `_audit_claim` monkeypatched in several pipeline tests (`:630`, `:797`, `:876`, `:943`, `:1173`) |
| `test_audit_trail.py` | `cap_rationale` keep rules including the level-fit rationale (`:1042-1114`, `:1315-1411`) |
| `test_cli.py` | refresh keeps operator seo_title and cap_rationale and records `level_clamp` (`:673-721`); `step-audit --write` keeps the level-fit note (`:2065-2073`) |

No test exercises `fit_verdict_to_written_pool` by name outside the audit-trail and CLI tests above (grep for the function name in tests returned only those); not found: a unit test file dedicated to the fit.

---

## 10. Open questions for the plan

1. Tie-breaker rule: what does "falls to the weaker verdict" mean when one side is `unverified` or `not-applicable` (off the polarity scale)? Candidate readings: lower confidence, `unverified`, or the verdict further from `true`.
2. Does the third pass see the two prior opinions (judge of judges) or run blind like the Evaluator? Today the Evaluator is blind by design and tests enforce it.
3. Does the third verdict replace `verdict:` on the claim file? If so, `dr publish`, `dr review --approve`, lint `verdict-sidecar-mismatch` and the claim page all anchor on `audit.analyst_verdict` and need a new "pipeline verdict" anchor.
4. Should the comparison use post-fit confidence (RE-AL row at `docs/v1.0.0-roadmap.md:333`), and should the fit run before the Evaluator so both grade the same claim?
5. Should the Evaluator receive independence labels and the verification level? Its confidence-cap rule assumes knowledge it is not given.
6. Should the Evaluator grade against the full consulted pool or the cited list (today)?
7. Should the confidence cap live in code only (the fit) and leave both prompts, removing two of the four copies?
8. Trigger for the third pass: `needs_review` (includes "2+ evidence gaps" on agreement) or `not verdict_agrees` only?
9. Model slot for the third pass: extend `AGENT_NAMES` and `VerifyConfig` (the comment at `models.py:70-73` says so) or follow the restater pattern of falling back to `--auditor-model`?
10. The analyst's "unresolvable" instruction has no field; keep title validation as the only block, or give the analyst an explicit refusal output?
11. For SP3 (restate inside the loop): on `dr claim-draft` the original operator sentence is not stored and the Evaluator grades the analyst's title; where does the original sentence live for the Q6 verdict chain?
12. Subject claims: which analyst and Evaluator rules (entity match, COI, restatement, "first-party") apply when the entity is a topic?
