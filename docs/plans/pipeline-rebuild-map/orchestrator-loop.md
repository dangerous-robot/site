# Orchestrator loop map

Phase 1 (Challenge) reader output for the pipeline rebuild (interview note: `handoff/2026-10-13-pipeline-improvement-interview.md`; approach APP-1, the strangler: a new `pipeline/loop/` beside the old code, each spike deleting the path it replaces). Facts only, with `file:line`. Line numbers are as of HEAD `40ba781` (2026-10-14). Paths are repo-relative; `pipeline/` is written out where it matters.

Scope: `pipeline/orchestrator/pipeline.py` (2975 lines) and the run paths `pipeline/orchestrator/cli.py` exposes over it. Persistence, checkpoints and the agent packages are named only where the loop calls them.

---

## 1. Entry points

The live command list (`.venv/bin/dr --help`, 2026-10-14) groups 18 commands. The ones below drive, or replay a step of, the research loop.

| Command | CLI (`orchestrator/cli.py`) | Loop function (`orchestrator/pipeline.py`) | Writes | archive.org capture | Checkpoint handler |
|---|---|---|---|---|---|
| `dr claim-probe ENTITY CLAIM` | `claim_probe` 878-925 | `verify_claim` 345-553 | nothing | off: `allow_save=False` at cli 906 | CLI if `--interactive`, else auto (cli 911) |
| `dr claim-draft ENTITY_REF CLAIM` | `claim_draft` 932-1030 | `research_claim` 1619-1866 | sources, entity (when ref is `-`), claim, sidecar | on (cfg default `allow_save=True`, 292) | cli 999 |
| `dr claim-refresh ENTITY/SLUG` | `claim_refresh` 1033-1340 | `verify_claim` (cli 1167-1173), then four write branches in the CLI (cli 1213-1333) | sources, claim, sidecar (always `force_overwrite=True`, cli 1152) | on | cli 1157 |
| `dr onboard NAME [URL] --type T` or `dr onboard TYPE/SLUG` | `onboard` 1764-1941 | `onboard_entity` 2293-2975, which calls `verify_claim` once per template (2723-2729) | entity (or draft entity), sources, one claim + sidecar per template | on | cli 1860 |
| `dr entity-enrich REF` | `entity_enrich` 1974-2040 | `enrich_entity` 2164-2290 | entity file fields | only if the ingest model recovers a fetch (AGENTS.md:185) | cli 2035 |
| `dr step-research ENTITY CLAIM` | `step_research` 279-317 | none: calls `researcher.decomposed.decomposed_research` directly (cli 311) | nothing | n/a | none |
| `dr step-ingest URL [--write]` | `step_ingest` 321-426 | none: `ingestor_agent.run` directly (cli 376), then `_check_ingested_source` (pipeline 1085-1138) | one source file with `--write`/`--force` | only with `--write` (cli 365-367) | none |
| `dr step-analyze --claim REF [--write]` | `step_analyze` 632-806 | `_analyse_claim` 1435-1498 on the claim's stored sources | claim file with `--write`; `--force` also resets status and clears the sidecar `audit` block (cli 775-779) | n/a | none |
| `dr step-audit --claim/--entity/--topic [--write]` | `step_audit` 1518-1723 | none: `auditor_agent.run` directly (cli 1649-1651) | sidecar with `--write` (cli 1654-1721) | n/a | none |
| `dr reassess`, `dr ingest` | hidden aliases 1726-1761 | delegate to step-audit / step-ingest | | | |

Not loop paths, listed for the stop-and-ask inventory in § 5: `dr review` (cli 2047-2161), `dr review-queue` (2164-2226), `dr publish` (2275-2571), `dr claim-promote` (1355-1515), `dr wayback-backfill` (491-629), `dr lint`, `dr stats`.

Every subcommand goes through `main` (cli 192-224): logging configured and a run id set per process (cli 221-224). Every LLM command first runs `_check_provider_api_keys` (cli 83-98; `sys.exit(2)` when a key is missing).

---

## 2. The loop copies, step by step

Three functions walk research > ingest > analyse > evaluate. Two of them (`verify_claim`, `research_claim`) are copies of each other with persistence inlined in the second. The third (`onboard_entity`'s per-template body) wraps `verify_claim` in a write block, and `claim_refresh` in `cli.py` carries a second copy of that write block.

### 2.1 `verify_claim` (pipeline.py 345-553): the in-memory loop

Signature 345-355: `entity_name, claim_text, config, checkpoint, sem, resolved_entity, url_index, topics, template`. Returns `VerificationResult` (118-204).

| Step | Lines | What happens | Stop condition |
|---|---|---|---|
| Setup | 371-374 | `cfg` defaults to `VerifyConfig()`, `gate` to `AutoApproveCheckpointHandler()`, semaphore created here if none passed | |
| Progress plumbing | 386-393 | `say` prints to stderr only when `cfg.show_progress` (probe and refresh set it; onboard does not, 323-327) | |
| Run id and HTTP client | 395-397 | `bind_run_id(cfg.run_id)`, one `httpx.AsyncClient` | |
| 1 Research | 399-420 | `_research` (1004-1053): decomposed researcher, then blocklist and pool cap (`_apply_blocklist_cap` 791-866) | no URLs: append `_NO_URLS_ERR`, set `blocked_reason=insufficient_sources` only when the scorer dropped everything (418-419), return 420 |
| 2 Ingest | 422-446 | build `url_index` if the caller passed none (426-427); `_apply_url_dedup` (869-895) splits cached vs to-fetch; `_ingest_claim_sources` (941-990) reorders by sub-question coverage and runs the waterfall `_ingest_urls` (1241-1360); cached then fresh appended to `result.sources` | |
| Coverage | 448-458 | `urls_failed`, `sub_question_coverage` via `_invert_addresses` (676-698), `_warn_uncovered` (701-714) logs only | |
| Checkpoint | 476-484 | `gate.review_sources(...)` | `False`: append "Halted at source review checkpoint", return 484 |
| Threshold | 489-496 | `below_threshold` (210-218: fewer than 4 usable sources) | `_record_threshold_block` (248-261) sets `blocked_reason`, return 496 |
| 3 Analyst | 498-519 | `_analyse_claim` with `criterion_notes = template.notes` (503) | no output: error + `result.failure`, return 519 |
| 4 Evaluator | 522-539 | `_graded_statement` (1513-1532): with a template, the analyst title is graded only when it passes `validate_analyst_title`; a failing title skips the Evaluator (526-530); without a template the operator's text is graded. `_apply_cited_filter` (1572-1616) narrows sources and sets `result.uncited_urls`; `_audit_claim` (1535-1569) | |
| Checkpoint | 542-548 | `gate.review_disagreement` when `comparison.needs_review` | `False` appends "Flagged for human review: ..." to `errors`; the function still returns the full result |
| Return | 553 | | |

What `verify_claim` never does: write a file, build a sidecar, read the published snapshot, or apply `force_overwrite`. The callers do all of it from `VerificationResult` (`persist_sources` 185-204, `sources_consulted` 177-183).

### 2.2 `research_claim` (pipeline.py 1619-1866): the loop with persistence inlined (`dr claim-draft`)

| Step | Lines | Difference from `verify_claim` |
|---|---|---|
| Setup | 1643-1661 | `cfg.repo_root` forced to a real path (1644-1645); `result.entity = "(pending)"` (1652); research entity hint is `""` unless a resolved entity was passed (1661) |
| 1 Research | 1669-1685 | `progress()` lines always, no `say` switch; `topics` are never passed to `_research` (1674), so the arXiv origin never fires here |
| 2 Ingest | 1687-1716 | `url_index` always built fresh (1690); otherwise the same 25 lines (1691-1716 vs 428-458) |
| Checkpoint | 1721-1729 | same |
| Threshold | 1733-1737 | **writes every fresh source file** (`_write_source_files`, 1735) before returning blocked; no claim file is written (compare onboard, which writes a placeholder claim) |
| 3 Analyst | 1739-1756 | `entity_name=None` (1743): with no resolved entity, `_analyse_claim` runs `analyst_agent`, which infers the entity (1493-1498); with one, it runs `verdict_only_agent` (1476-1491). On analyst failure every fresh source is written and no claim (1754-1756; the "orphan source files" backlog row, `docs/UNSCHEDULED.md` § Beta.7 fix-run findings) |
| Cited filter | 1759-1761 | same helper |
| 4 Write sources | 1763-1778 | only cited fresh files (1766-1770); `source_ids` ordered by the researcher's URL order through the alias map (1775-1778), not cached-then-fresh as `persist_sources` returns |
| Entity | 1781-1788 | `_write_entity_file` only when no resolved entity: the only path that creates an entity from analyst output |
| Claim | 1789-1820 | `claim_slug = slugify(title)` (1789); `fit_verdict_to_written_pool` (1790-1793); `mark_forced_rewrite` when `--force` (1794-1798); `_write_claim_file` with default `status="draft"` and **no `criteria_slug`** (1799-1813) |
| 5 Evaluator | 1822-1831 | runs **after** the claim write; grades `analyst_out.verdict.title` (1831), the title just written, not the operator's text |
| Sidecar | 1834-1854 | `agents_run` is always all four even when `_audit_claim` returned `None` (1836); no `reset_review`, no `previous_publication` (the snapshot is handled by `mark_forced_rewrite` on the `--force` path) |
| Checkpoint | 1856-1865 | same; result only |

### 2.3 `onboard_entity` (pipeline.py 2293-2975): entity phases, then `verify_claim` per template

| Phase | Lines | Notes |
|---|---|---|
| Ref parse | 2345-2356 | `entity_ref` names a file on disk; `seed_url` defaults to its website |
| A Light research | 2366-2374 | `gather_light_research` (1991-2073): seed URL ingest or "official website" search + one ingest (`archive=False`), then the collision probe (2086-2132) |
| B Verifier | 2376-2454 | `entity_verifier_agent` with `research_timeout_s` (2397-2400); failure proceeds without the gate (2402-2407). `needs-disambiguation` asks `review_entity_disambiguation` (2410); reject returns `status="rejected"` with nothing written (2413-2419); accept or a name re-runs light research (2429-2434). `unverified` asks `review_verification_status` (2438); anything but a listed status returns rejected (2442-2454) |
| C Enricher | 2456-2522 | runs only when `file_entity is None or cfg.force_overwrite` and a page summary exists (2474-2476); `review_entity_enrichment` (2499); reject keeps the raw summary |
| Description fallback | 2524-2531 | name-based run over an existing file with no page: the file's description |
| 2 Templates | 2539-2583 | `templates_for_entity_type` with a subject slug (2543-2552); subject with zero templates warns and continues (2555-2563); company/product with zero rejects (2564-2571); `--only` unknown slug rejects (2576-2582); `_screen_templates` is a pass-through (1953-1960) |
| 3 Checkpoint | 2588-2592 | `review_onboard`: reject writes a **draft entity file** and returns (2605-2617); a list replaces the slugs (2619-2620) |
| Entity write | 2624-2636 | `_write_entity_file` only when no ref was given; `--force` with a draft splices enrichment into the existing file (2643-2655) |
| Resolved entity | 2657-2685 | re-read from disk when a ref was given (merges file hints + CLI hints + probe excludes) |
| 4 Per-template loop | 2687-2973 | shared `onboard_url_index` (2688); **each template gets its own `run_id`** (2694-2695); template missing > `claims_failed` (2698-2706); existing claim file skipped unless `--force` (2714-2720); `verify_claim` (2723-2729); `vr.persist_sources(repo_root, onboard_url_index)` first, every branch (2735); `mark_forced_rewrite` on `--force` (2736-2740); then four branches; any exception > `claims_failed`, loop continues (2969-2973) |

The four write branches in the onboard loop:

| Branch | Lines | Claim write | Sidecar `agents_run` |
|---|---|---|---|
| Threshold-blocked (`vr.blocked_reason`) | 2746-2802 | placeholder: `render_blocked_title`, `Verdict.UNVERIFIED`, `Confidence.LOW`, `status="blocked"`, `criteria_slug=slug` (2759-2775) | `["researcher","ingestor"]` + `failure` (2777-2795) |
| Analyst failed (`not vr.analyst_output`) | 2804-2857 | placeholder with `BlockedReason.ANALYST_ERROR` (2815-2831) | `["researcher","ingestor","analyst"]` + `failure` |
| Title fails template (`validate_analyst_title`) | 2859-2918 | placeholder with `blocked_title_message` body (2865-2884); lists **every** ingested source (the cited filter never ran, see 526-530) | `["researcher","ingestor","analyst"]` |
| Success | 2920-2967 | topics inherited from the template (2920-2927); `fit_verdict_to_written_pool` (2925-2927); `_write_claim_file` with `criteria_slug=slug`, `force=iter_cfg.force_overwrite` (2928-2944); claim before sidecar | all four, `analyst_record`, `level_clamp` (2950-2965) |

### 2.4 `claim_refresh` (cli.py 1033-1340): `verify_claim` plus a second copy of the four branches

| Step | Lines | Notes |
|---|---|---|
| Preconditions | 1101-1116 | claim file must exist (`sys.exit(1)` 1104); must carry `criteria_slug` (`sys.exit(1)` 1116): ad hoc drafts are refused |
| Entity, template, claim text | 1118-1142 | entity parse failure is a warning only (1123-1124); when templates fail to load, `template=None` and `claim_text` falls back to title, then `claim`, then the file stem (1132-1142) |
| Config | 1146-1157 | `force_overwrite=True`, `show_progress=True` always |
| Snapshot | 1161 | `_read_published_snapshot` before the run (persistence 765-790) |
| Loop | 1167-1173 | `verify_claim` with `resolved_entity`, `topics`, `template` |
| Sources | 1189 | `vr.persist_sources(root)` with **no url index** |
| Sidecar helper | 1192-1211 | `_write_sidecar` passes `reset_review=True`, `previous_publication`, `current_source_ids` |
| Branch A threshold-blocked | 1213-1243 | **sidecar written before the claim** (1225, comment 1183-1187: a failed claim write leaves the published claim intact with the snapshot pending) |
| Branch B analyst failed | 1245-1275 | same shape |
| Branch C title fails | 1279-1311 | only when a template loaded (1285-1288) |
| Branch D success | 1313-1333 | `status=ClaimStatus.DRAFT` explicit (1339); prints "flagged for human review" note when `needs_review` (1335-1339) |

### 2.5 Where the copies diverge (one table)

| Concern | `verify_claim` (probe, and inside onboard/refresh) | `research_claim` (claim-draft) | onboard per-template body | `claim_refresh` write block |
|---|---|---|---|---|
| Progress output | `say` only with `show_progress` (386-393) | always `progress()` (1670, 1688, 1740, 1768, 1823) | `progress("[i/n] ...")` per template (2696, 2719, 2796, 2851, 2912, 2967, 2970) | `progress("Refreshing ...")` (1163) |
| Step numbering in logs | "Step N/4" (400, 424, 500, 529/534) | "Step N/5" (1671, 1689, 1741, 1769, 1829) | inherits 1/4 | inherits 1/4 |
| `url_index` | caller's or fresh (426-427) | fresh (1690) | one per onboard run, updated by `persist_sources` (2688, 2735) | none passed to `persist_sources` (1189) |
| `topics` to research | passed by onboard/refresh | never (1674) | `template.topics` (2727) | `template.topics` (1166, 1170) |
| Entity to analyst | `entity_name` + optional resolved | `None` + optional resolved (1743) | resolved from file or built (2657-2685) | resolved or a title-cased dir name (1126-1130) |
| Entity file write | never | when no resolved entity (1785) | `_write_entity_file`/`_write_draft_entity_file` (2625, 2607) | never |
| Threshold-blocked outcome | `blocked_reason` on the result | sources written, no claim (1735) | placeholder blocked claim + sidecar | placeholder blocked claim + sidecar, sidecar first |
| Analyst-failed outcome | `failure` on the result | sources written, no claim (1755) | placeholder blocked claim, `ANALYST_ERROR` | same, sidecar first |
| Title fails template | Evaluator skipped, `consistency=None` (526-530) | n/a (no template) | blocked claim, every source listed | blocked claim |
| Statement the Evaluator grades | operator text (no template) or passing analyst title | the written title (1831) | passing analyst title | passing analyst title |
| Evaluator runs before or after the claim write | n/a | after (1822) | before (inside `verify_claim`) | before |
| Which sources are written | none | cited fresh only (1766-1770), all fresh on blocked/analyst-failed | `persist_sources` skips `uncited_urls` (185-204) | same |
| `sources:` order on the claim | n/a | researcher URL order (1775-1778) | cached ids then fresh ids (200-204) | same |
| `criteria_slug` | n/a | never (1799-1813) | template slug | the file's |
| `status` on success | n/a | default `"draft"` | default `"draft"` | explicit `DRAFT` (1339) |
| `force_overwrite` | ignored | `mark_forced_rewrite` then `force=cfg.force_overwrite` (1794-1811) | `mark_forced_rewrite` before all branches (2736-2740) | `force=True` always; `reset_review` + snapshot through the sidecar (1192-1211) |
| Sidecar order vs claim | n/a | claim then sidecar (1804, 1841) | claim then sidecar (2928, 2950) | **sidecar then claim** (1225/1228, 1257/1260, 1293/1296, 1323/1324) |
| `agents_run` on success | n/a | all four always (1836) | all four (2949) | all four (1323) |
| `run_id` | `cfg.run_id` (325-326) | `cfg.run_id` | new id per template (2694) | `cfg.run_id` |
| Exceptions | propagate | propagate | caught per template, loop continues (2969-2973) | propagate (no handler) |

---

## 3. Every place a run can stop and ask, or wait for, a person

### 3.1 Checkpoints inside the loop (`orchestrator/checkpoints.py`)

`CheckpointHandler` protocol 99-182. Two implementations: `CLICheckpointHandler` 185-317 (prompts) and `AutoApproveCheckpointHandler` 325-389 (default everywhere; `--interactive` selects the CLI one at cli 911, 999, 1157, 1860, 2035).

| Checkpoint | Called from | Interactive prompt | Auto-approve answer | Effect of the "no" answer |
|---|---|---|---|---|
| `review_sources` | `verify_claim` 476, `research_claim` 1721 | `click.confirm("Proceed to analysis?", default=True)` 197 | `True` 342 | append "Halted at source review checkpoint", return before the threshold check (484, 1729) |
| `review_disagreement` | `verify_claim` 543, `research_claim` 1861 | `click.confirm("Accept this result?", default=False)` 208 | `True` 349 | append "Flagged for human review: reasons" to `errors`; nothing else changes (claim and sidecar are already written in `research_claim`; onboard/refresh ignore `errors` except for printing) |
| `review_onboard` | `onboard_entity` 2590 | `click.prompt` accept/reject/edit 228-234 | `"accept"` 360 | reject writes a draft entity file, no claims (2605-2617) |
| `review_entity_enrichment` | `onboard_entity` 2499, `enrich_entity` 2257 | accept/reject 247-251 | `"accept"` 368 (so unattended runs take the enricher draft verbatim; RE-AJ (Entity enrich refuses to guess) made the no-page case refuse instead, 2474-2476 and 2226-2235) | onboard keeps the raw summary (2520-2521); enrich returns `rejected` (2260-2265) |
| `review_entity_disambiguation` | `onboard_entity` 2410 | number, name, accept or reject 258-278 | `"reject"` 378: **an unattended onboard of an ambiguous name aborts** | return `status="rejected"`, nothing written (2413-2419) |
| `review_verification_status` | `onboard_entity` 2438 | pick a status or reject 286-314 | `"reject"` 389: **unattended onboard of an unverifiable entity aborts** | return rejected (2442-2454) |

### 3.2 Hard stops before the loop (`sys.exit`, `click.UsageError`) on the loop commands

| Command | Line | Condition |
|---|---|---|
| all LLM commands | cli 98 | missing provider API key for any configured model (`exit 2`) |
| `claim-draft` | cli 963-965 | `BRAVE_WEB_SEARCH_API_KEY` unset (`exit 2`), although the default search backend is Tavily (`search_backend` default at pipeline 311-313); no other loop command checks it |
| `claim-draft` | cli 984 | entity ref does not parse (`UsageError`) |
| `claim-refresh` | cli 1104, 1116 | claim file missing; no `criteria_slug` |
| `onboard` | cli 1830, 1835 | ref does not parse; bare name without `--type` |
| `entity-enrich` | cli 2011-2023 | file missing; non-empty history body without `--force` |
| `step-analyze` | cli 688, 743, 803 | file missing; analyst failed; `FileExistsError` on write without `--force` |

### 3.3 Prompts outside the loop (for the "five commands" fold, SP7)

| Where | Lines | Prompt |
|---|---|---|
| `dr review` | `orchestrator/review.py` 26-31, 47, 64 | stdin must be a tty; the claim slug is typed back; `--approve` after a verdict-changing refresh needs `--correction` (review.py 105-122 raise) |
| `dr review-queue` | `orchestrator/review_queue.py` 385-502 | per-claim action key, edit loop, correction prompt, confirm |
| `dr publish` | cli 2521 | `click.confirm` unless `--yes` |
| `dr claim-promote` | cli 1423-1430 | five `click.prompt` calls for the template fields |

### 3.4 Waits that are not prompts

- Ingest waterfall: `asyncio.gather` waits for every in-flight worker after the target is reached (`stop.set()` 1336 does not cancel; `gather` 1350). The backlog row RF12 (`docs/UNSCHEDULED.md` § claim-refresh review findings) records a 39 s stall.
- Throttle sleeps: `common/throttle.py` 128-160 `acquire` sleeps under the bucket lock. Registered by `researcher/tools/tavily.py:57`, `researcher/tools/arxiv.py:43`, `ingestor/arxiv_affiliation.py:64`. The orchestrator never touches the throttle.
- Retry sleeps: § 4.

---

## 4. Every retry and timeout the loop depends on

### 4.1 Retries

| Where | Lines | What is retried | How many, how long |
|---|---|---|---|
| `_run_with_null_retry` | pipeline 1384-1432 | an agent run that raised `UnexpectedModelBehavior` containing "Invalid response from" (null body), or `openai.RateLimitError` | `_NULL_BODY_RETRIES = 2` (91) extra attempts; 45 s between null-body attempts (92); rate limit waits `Retry-After` or 90 s (93, 1414-1419). Each attempt has its own `wait_for` timeout (1403) |
| callers of it | `_analyse_claim` 1477-1479 and 1494; `_audit_claim` 1557 | analyst and Evaluator only | |
| Ingestor | `_ingest_one` 1190-1194 | **no** null-body retry: `ingestor_agent.run` called directly (backlog row "Ingest: retry Infomaniak null-body responses", `docs/UNSCHEDULED.md` § Pipeline performance & hardening) | PydanticAI `retries=2` on the agent definition (`ingestor/agent.py:127`) covers output validation retries, not transport nulls |
| `web_fetch` tool | `ingestor/agent.py:186-188` | HTTP 429 | one retry after `RATE_LIMIT_RETRY_S = 2.0` (`common/timeouts.py:37`) |
| archive.org requests | `ingestor/tools/wayback.py:106-113` | HTTP 429 | one retry, `Retry-After` capped |
| Brave search | `researcher/agent.py:47-56, 72-82` | 429; then a quoted query with zero results | one 429 retry; one unquoted retry |
| Tavily | `researcher/decomposed.py:159-178` | rate limit, missing key, any exception | per-query fallback to Brave; `tavily_rate_limited` StepError recorded |
| Planner, scorer | `researcher/decomposed.py:388-391, 492-495` | none | planner timeout or error ends research (404-409); scorer timeout or error falls back to the unscored candidates (510-520) |
| Onboard per template | pipeline 2969-2973 | none; the exception is recorded and the next template runs | |
| Loop level | nowhere | a blocked or failed claim is never re-run automatically; the operator re-runs `claim-refresh` or `onboard --force` | |

### 4.2 Timeouts (`VerifyConfig`, pipeline 269-340)

| Field | Default | Applied at |
|---|---|---|
| `research_timeout_s` | 120 (316) | planner and scorer runs; also the verifier (2397-2400) and enricher (2243-2246, 2488-2491) |
| `analyst_timeout_s` | 120 (317) | `_run_with_null_retry` per attempt (1479, 1494) |
| `auditor_timeout_s` | 120 (318) | 1557 |
| `ingest_timeout_s` | `None` > `ingest_budget_with_wayback_s()` when wayback is on, else 60 (335-338) | `_ingest_one` 1192-1194. The budget sums the constants in `common/timeouts.py:44-58`: 5+15 (fetch) + 2+5+15 (one 429 retry) + 101 (`archive_lookup_cost_s`, 61-75) + 25 (LLM) = 168 s |
| archive lookup after ingest | `archive_lookup_budget_s()` = 101 s (`common/timeouts.py:78-80`) | `archive_after_ingest` 1226, outside the ingest timeout and the LLM semaphore |
| `dr step-ingest` | fixed 120 s (cli 376) | not `VerifyConfig` |
| `dr step-audit` | none (cli 1650-1651: no `wait_for`, no semaphore, no null retry) | backlog row "Docs versus code" |

### 4.3 Concurrency

- `llm_concurrency` 8 (322): one `asyncio.Semaphore` per top-level call (374, 1651, 2210, 2334; cli 308 for step-research). Onboard shares one across light research and every template (2334).
- Ingest dispatch: `asyncio.Semaphore(2)` inside `_ingest_urls` (1287), target-stop at 1333-1336, `kept = results[:target]` 1352 (late successes discarded; backlog row "Ingest discards successes that finish after the target").
- The LLM semaphore wraps only the agent call (1191); the arXiv author lookup and the archive lookup run outside it (1198, 1223-1228).

---

## 5. Cross-cutting hooks

| Hook | Where set up | Where the loop uses it |
|---|---|---|
| Run id | `cli.main` 224 sets one per process; `VerifyConfig.run_id` inherits it (325-326); `bind_run_id` 395, 1666, 2211, 2358; onboard replaces it per template (2694-2695) | every log record (`common/logging_setup.py` 89-95 filter); the sidecar does not record it (persistence 899-1071 has no `run_id` field) |
| Logging | `configure_logging` (cli 221): `logs/info.log`, `logs/debug.log`, console | `logger.info("Step N/M ...")` pairs with `progress()`/`say` (`common/logging_setup.py` 164-188: stderr line plus an info.log record unless `log=False`); `hr()` 190-198 is stderr chrome only |
| Checkpoints | § 3.1 | `gate` object threaded through every function |
| URL dedup index | `build_source_url_index` (persistence 97-120) | 426-428, 1690-1691, 2688; `persist_sources` extends it (193-199) |
| Blocklist | `common/blocklist.py` via `_apply_blocklist_cap` 791-866 | inside `_research` (1030-1038); `trace["blocklist_spared"]` for the entity's own profile post (834-846) |
| Archive capture switch | `cfg.allow_save` (292) | `IngestorDeps` 1172; `archive_after_ingest` 1226; probe sets `False` (cli 906); `step-ingest` only with `--write` (cli 365) |
| Force overwrite | `cfg.force_overwrite` (319) | `mark_forced_rewrite` (persistence 858-897) at 1794-1798, 2736-2740, cli 775-779; `_write_claim_file(force=...)` |
| Operator-field keep rules | `_write_claim_file` (persistence 520-600), `analyst_record` (627-705) | every claim write; RE-AH (Claim refresh keeps operator fields and verifies quotes) and RE-AK (Published fields survive the pipeline) live here |
| Published snapshot and refresh trail | `_read_published_snapshot` 765-790, `_refresh_block` 793-818 | refresh via sidecar args (cli 1206-1208); draft/onboard/step-analyze via `mark_forced_rewrite` |
| Level fit | `fit_verdict_to_written_pool` (persistence 354-447) | before every success claim write (1790, 2925, cli 1320, cli 747) and as a trial inside `_apply_cited_filter` (1600) |
| Structured failure | `_failure_from_exc` 96-115, `FailureInfo` | `result.failure` 514-516; sidecar `pipeline_run.failure` (persistence 1046-1049); `_blocked_reason_label` 1872-1904 |
| StepError vocabulary | `checkpoints.py` 15-97 docstring; `tests/test_step_error_vocab.py` scans production code for new literals | every error the loop records |
| Model routing | `cfg.model_for(agent)` (330-332); `resolve_model` | each `agent.override(model=...)` (1191, 1477, 1493, 1556, 2241, 2397, 2486) |
| Throttle | `common/throttle.py` | search and arXiv tools only |

---

## 6. Persistence call matrix

Which writer each path calls, in order. Functions are in `orchestrator/persistence.py` unless noted.

| Path | Order of writes |
|---|---|
| `claim-probe` | none |
| `claim-draft` success | `_write_source_files` (cited fresh) 1770 > `_write_entity_file` 1785 (no ref only) > `mark_forced_rewrite` 1800 (`--force`) > `_write_claim_file` 1804 > `_write_audit_sidecar` 1841 |
| `claim-draft` blocked / analyst failed | `_write_source_files` (all fresh) 1735 / 1755; nothing else |
| `onboard` per template | `persist_sources` 2735 > `mark_forced_rewrite` 2738 (`--force`) > `_write_claim_file` (2759 / 2815 / 2868 / 2928) > `_write_audit_sidecar` (2777 / 2833 / 2886 / 2950) |
| `onboard` entity | `_write_draft_entity_file` 2607 (reject) or `_write_entity_file` 2625; `update_entity_enrichment` 2650 (`--force` splice) |
| `claim-refresh` | `persist_sources` 1189 > `_write_audit_sidecar` (1225 / 1257 / 1293 / 1323) > `_write_claim_file` (1228 / 1260 / 1296 / 1324) |
| `step-analyze --write` | `mark_forced_rewrite` 775, `clear_audit` 779 (`--force`) > `_write_claim_file` 782 |
| `step-audit --write` | `_write_audit_sidecar` with `keep_other_models=True` 1706-1714 |
| `step-ingest --write` | `resolve_source_slugs` 409 > direct file write 415-419 |

Read-before-write guards a new loop must keep: `_write_claim_file` refuses an existing file without `force` (persistence 520-523) and raises on an unparseable existing claim (529-535); `_write_source_files` resolves slug collisions by URL (persistence 247-268); `resolve_source_slugs` runs before ids reach the analyst (1357-1359).

---

## 7. What one loop with a persist flag would need to carry

Derived from the divergence table (§ 2.5) and the call matrix (§ 6). Each row is something the three copies do differently today and the new loop has to decide once.

| Need | Today's sources of truth |
|---|---|
| A `persist` switch that also controls archive capture (`allow_save`) and whether `url_index` writes back | cli 906; 185-204 |
| One place for the four outcomes (success, threshold-blocked, analyst-failed, title-failed) and what each writes | onboard 2746-2967; cli 1213-1333; `research_claim` 1733-1756 (which writes sources only). The interview's Q4 answer ("retry N times, then delete the half-claim; only the finding survives") replaces the placeholder-claim convention, so the blocked branches become a findings record plus cleanup |
| Sidecar-before-claim ordering for a published claim (refresh), or `mark_forced_rewrite` before the claim (draft, onboard, step-analyze) | cli 1183-1187; persistence 858-897 |
| Published snapshot read before the run | cli 1161 |
| Operator-field keep rules and `analyst_record` | persistence 520-600, 627-705 |
| Level fit after final `source_ids`, before claim and sidecar | 1790-1793, 2925-2927, cli 1320 |
| Cited-source filter and the "list every source when blocked" rule | 1572-1616, 526-530 |
| The statement the Evaluator grades, and whether it runs before or after the claim write | 1513-1532, 1831 |
| `criteria_slug` and `status` policy per outcome | 1799-1813 (none), 2928-2944 (template slug), cli 1324-1339 (the file's; `DRAFT`) |
| `sources:` ordering on the claim | 1775-1778 vs 200-204 |
| Entity resolution: file ref, built entity, or analyst inference, and whether an entity file is written | 1476-1498, 1781-1788, 2657-2685 |
| Topics to research (arXiv origin) and criterion notes to analyst and Evaluator | 2727, 503, 1170 |
| Progress and log lines with step numbering | 386-393, 1670 |
| Run id per claim (onboard) vs per command, and the findings file key (SP2, rules and findings file) | 2694-2695, 325-326 |
| Checkpoint protocol: which prompts survive in a rules-only run (`review_sources`, `review_disagreement` are the two inside the loop) | § 3.1 |
| Per-claim exception containment (onboard) vs propagate (the rest) | 2969-2973 |
| `failure` and `blocked_reason` labels for the report | 1872-1904 |
| StepError literals registered in the vocabulary docstring | `checkpoints.py` 15-97 |

---

## 8. Hazards: what a rewrite could silently lose or break

| ID | Hazard | Location |
|---|---|---|
| HZ-1 | Probe safety is a caller convention, not a loop property: `verify_claim` has no notion of persistence; only `allow_save=False` at the CLI and the absence of write calls keep `dr claim-probe` write-free. A loop with a `persist` flag must bind `allow_save`, `url_index` write-back and every writer to that one flag; the current test is `test_claim_probe_never_captures_on_archive_org` (`tests/test_cli.py:2076`) | cli 906; pipeline 185-204 |
| HZ-2 | Refresh writes the sidecar before the claim so a failed claim write leaves the published claim live with the snapshot pending; onboard and draft write the claim first. Folding to one order changes crash behaviour on a published claim | cli 1183-1187, 1225-1228; pipeline 1804/1841, 2928/2950 |
| HZ-3 | Operator-field keep rules (`seo_title`, `takeaway`, `cap_rationale`, `corrections`, `tags`) and the `analyst_record` live inside `_write_claim_file`; a new loop that writes through any other writer drops RE-AH (Claim refresh keeps operator fields and verifies quotes) and RE-AK (Published fields survive the pipeline) without a test failing unless `tests/test_cli.py` 612-720 and `tests/test_onboard.py` 1691-1831 are kept running against it | persistence 520-600, 627-705, 858-897 |
| HZ-4 | `research_claim` writes every fresh source and no claim on a threshold block or analyst failure; onboard and refresh write a blocked placeholder claim. The site, `dr lint` (`unreferenced-source`), `prune.py` and `dr review-queue` each see a different artifact today | pipeline 1735, 1755; 2759, cli 1228 |
| HZ-5 | Entity inference (`analyst_agent` with `entity_name=None`) and entity-file creation exist only in `research_claim` with ref `-`; dropping `research_claim` without a decision drops the only path that creates an entity from a claim | pipeline 1476-1498, 1781-1788 |
| HZ-6 | Three rules pick the statement the Evaluator grades: operator text (probe), passing analyst title (template paths, Evaluator skipped when the title fails), the just-written title (draft). RE-AD (Evaluator grades the claim) depends on which rule the new loop keeps; the backlog row "`dr claim-draft` no longer compares the analyst's title with the operator's text" is the gap today | pipeline 1513-1532, 526-530, 1831 |
| HZ-7 | `sources:` order differs (researcher order vs cached-then-fresh); claim pages and lint read the list, so a rewrite can reorder every refreshed claim's source list | pipeline 1775-1778 vs 200-204 |
| HZ-8 | The shared `onboard_url_index` lets later templates reuse sources written seconds earlier; refresh passes no index and draft builds a fresh one. RE-AL (Source pool and coverage quality) row "Dedup hits from a sibling claim shrink the ingest target" is the known downside, so the behaviour is both relied on and disputed | pipeline 2688, 2735; cli 1189 |
| HZ-9 | Per-template `run_id` (onboard) is what makes `logs/info.log` searchable per claim; the sidecar never stores it. A findings file keyed by run id (SP2, rules and findings file) needs the id written somewhere durable | pipeline 2694-2695; persistence 899-1071 |
| HZ-10 | `review_disagreement` has no on-disk effect: the only durable trace of an Evaluator split is `audit.needs_review` in the sidecar. A tie-breaker (SP2) replaces the checkpoint, but `dr publish` (cli 2275-2571) and the review queue read `needs_review` and `verdict_override`, so the sidecar shape must keep those keys or those commands change too | pipeline 542-548, 1856-1865; persistence 955-966 |
| HZ-11 | Level fit runs twice: as a trial inside the cited filter (`log=False`) and for real before the write; the Evaluator comparison runs before the real fit, so `audit.analyst_confidence` can disagree with the claim (RE-AL (Source pool and coverage quality) row). Reordering steps in the new loop changes which value lands in the sidecar | pipeline 1600, 1790; persistence 354-447 |
| HZ-12 | A title that fails the template lists every ingested source and skips the Evaluator; templates becoming stored sentences (SP6, one claim path) removes `validate_analyst_title`, and with it this branch and `render_blocked_title`, `blocked_title_message` (`common/templates.py`) | pipeline 526-530, 2859-2918 |
| HZ-13 | `tests/test_step_error_vocab.py` fails on any new `StepError(error_type=...)` literal not listed in the `checkpoints.py` docstring; a new `pipeline/loop/` module is scanned too (confirm the scan root before adding literals) | checkpoints.py 16-99 |
| HZ-14 | Ingest waterfall details that tests and the sidecar rely on: 2-wide dispatch, target stop without cancel, `kept = results[:target]`, redirect aliases and `known_pages`, `resolve_source_slugs` before any downstream use (RF21 window), `IngestNotes.final_urls/archive` feeding `sources_consulted` | pipeline 1241-1360, 898-938, 177-183 |
| HZ-15 | Blocklist exemption for the entity's own profile post and the `research.blocklist_spared` sidecar block (RE-AE (Source pool independence) decision 2026-10-11) | pipeline 791-866 |
| HZ-16 | `claim-refresh` refuses ad hoc drafts and `claim-draft --force` drops `criteria_slug`; the one-claim-path spike (SP6) has to define how a claim remembers its sentence and entity filter so recheck (SP5) can re-run it | cli 1108-1116; pipeline 1799-1813; backlog row "`dr claim-draft --force` drops `criteria_slug`" |
| HZ-17 | When `research/templates.yaml` fails to load, refresh still runs with `template=None`, grading the old title and writing a new one | cli 1132-1142; backlog row "`dr claim-refresh` without templates ..." |
| HZ-18 | `claim-draft` exits unless `BRAVE_WEB_SEARCH_API_KEY` is set, while the default backend is Tavily; a folded `dr draft` that drops the check changes which runs fail at startup | cli 963-965; pipeline 311-313 |
| HZ-19 | Unattended onboard aborts on `needs-disambiguation` and `unverified` (auto-approve answers reject). Under the "normal runs follow clear rules" goal those become rules or findings, and `tests/test_onboard.py` 686-770 pin today's abort | checkpoints.py 378-389; pipeline 2410-2454 |
| HZ-20 | `topics` never reach `_research` from `research_claim`, so arXiv never fires on `claim-draft`; onboard and refresh pass template topics. A single loop makes the academic origin fire on ad hoc claims for the first time (cost and pool change) | pipeline 1674 vs 2727 |
| HZ-21 | Exceptions inside the onboard loop are caught per template and the run continues; in every other path they propagate with nothing written. A unified "retry N then delete" rule (interview Q4) has to cover both the exception and the recorded-failure cases | pipeline 2969-2973 |
| HZ-22 | `VerificationResult` fields marked `exclude=True` (`source_files`, `cached_sources`, `queries_by_sub_question`, `failure`, `final_urls`, `archive`, `uncited_urls`) are exactly the ones the sidecar and `persist_sources` need; serialising the result (for a findings file or replay, SP9) loses them unless the model changes | pipeline 140-168 |
| HZ-23 | Subject special cases: template fan-out by subject slug, zero-template subjects onboard with a warning, `_claim_dir_for` puts subjects under `research/claims/subjects/<slug>/` while companies and products are flat | pipeline 2543-2571; persistence 314-333 |
| HZ-24 | `step-audit --write` carries `research`, `sub_questions`, per-URL `acquisition` and `archive` forward by re-reading the sidecar (cli 1654-1704); any sidecar schema change in the new loop must keep that replay working or `step-audit` drops provenance again (the RE-AK (Published fields survive the pipeline) "erases the model record" fix) | cli 1654-1721 |

---

## 9. Duplication

| ID | What | Locations |
|---|---|---|
| DUP-1 | Research + ingest + dedup + coverage block (about 60 lines) | pipeline 399-458; 1669-1716 (also backlog row "`verify_claim` ↔ `research_claim` deduplication", `docs/UNSCHEDULED.md` § Pipeline code-quality refactors) |
| DUP-2 | Source checkpoint + threshold block | pipeline 476-496; 1721-1737 |
| DUP-3 | Analyst-failure handling | pipeline 511-519; 1748-1756 |
| DUP-4 | Disagreement checkpoint handling | pipeline 542-548; 1856-1865 |
| DUP-5 | Four-branch write block (blocked, analyst failed, title failed, success) | pipeline 2746-2967; cli 1213-1333 |
| DUP-6 | Blocked placeholder body strings | pipeline 2755-2758, 2811-2814; cli 1218-1222, 1250-1254 |
| DUP-7 | `inherited_topics = [Category(t) ...]` try/except | pipeline 2748-2751, 2805-2808, 2860-2863, 2920-2927; cli 1214-1217, 1246-1249, 1280-1283, 1314-1317 |
| DUP-8 | `_write_audit_sidecar(...)` call with the `sub_questions_block` build | pipeline 1841-1854, 2777-2795, 2833-2851, 2886-2903, 2950-2965; cli 1192-1211, 1706-1719 |
| DUP-9 | `VerifyConfig` built from CLI overrides (`overrides = {k: v ...}` comprehension) | cli 903-910, 988-997, 1145-1156, 1849-1858 |
| DUP-10 | Checkpoint handler selection (`CLICheckpointHandler() if interactive else AutoApproveCheckpointHandler()`) | cli 911, 999, 1157, 1860, 2035 |
| DUP-11 | Entity ref parsing with a different failure policy each time | cli 913-920 (probe: ignore), 975-984 (draft: `UsageError`), 1118-1124 (refresh: warning), 1820-1830 (onboard: `UsageError`), 700-702 (step-analyze: warning) |
| DUP-12 | Claim-text reconstruction from a template with different fallbacks | cli 705-708; 1132-1142 (backlog row "Claim-text reconstruction duplicated") |
| DUP-13 | Enricher phase | pipeline 2237-2255 (`enrich_entity`); 2456-2522 (onboard Phase C) |
| DUP-14 | Writing fresh sources: inline `_write_source_files` calls vs `VerificationResult.persist_sources` | pipeline 1735, 1755, 1770; 185-204 (used at 2735, cli 1189) |
| DUP-15 | `agents_run` / `models_used` lists written by hand per branch | pipeline 1836-1848, 2783-2784, 2839-2840, 2892-2893, 2949-2957; cli 1225, 1257, 1293, 1323 |
| DUP-16 | Direct agent invocation bypassing the loop helpers (no semaphore, no null retry, own timeout) | cli 376 (step-ingest), 1649-1651 (step-audit); pipeline 2243-2246 and 2488-2491 (enricher twice), 2397-2400 (verifier) |

---

## 10. Tests that pin the loop today

| File | Covers |
|---|---|
| `pipeline/tests/test_orchestrator.py` (classes at 30-1414) | `VerificationResult`, blocklist and pool cut, `VerifyConfig` models and timeouts, threshold enforcement with `verify_claim` (502-640), resolved entity in both loops (643-890), rejected review reason (894), graded statement (955-1197), uncovered sub-question warning (1199-1240), cited filter (1243-1412), `persist_sources` (1414) |
| `pipeline/tests/test_onboard.py` (149-1831) | happy path, single research per template (217), source reuse across templates (273-330), seed URL, error attribution, rejection draft, vocabulary blocking (469), Phase B verifier outcomes (686-1090), search hints, entity file on disk (1215-1456), subject fan-out (1458-1538), light research errors, forced rewrites keep the refresh trail (1691-1831) |
| `pipeline/tests/test_cli.py` (91 tests) | claim-refresh branches and published state (256-720), promote, entity-enrich, onboard CLI Phase B (1123), step-analyze criterion and status resets (1523-1600, 1681), refresh flag reason (1753), step-ingest archive (1813), probe never captures (2076), wayback backfill, refresh lists cited sources (2618) |
| `pipeline/tests/test_acceptance.py` | live `verify_claim` run (26, 260) |
| `pipeline/tests/test_research_integration.py`, `test_source_url_dedup.py`, `test_ingest_urls.py`, `test_terminal_fetch.py`, `test_archive_after_ingest.py`, `test_entity_independence.py` | research/ingest internals the loop calls |
| `pipeline/tests/test_checkpoints.py`, `test_step_error_vocab.py`, `test_throttle.py`, `test_logging_setup.py` | the cross-cutting hooks |

No test drives `research_claim` and `verify_claim` against the same inputs to assert they agree; the "probe-vs-draft safety by test" line in the interview (Q8 item B) has no existing fixture to build on.

---

## 11. Open questions for the plan

| ID | Question |
|---|---|
| OQ-1 | Blocked and failed outcomes: does the new loop write a placeholder claim (onboard, refresh), sources only (draft), or nothing plus a findings record (interview Q4: delete the half-claim)? Lint, prune, the review queue and `dr publish` each react to the placeholder today (§ 8 HZ-4). |
| OQ-2 | Is `review_sources` retired in a rules-only run, or kept behind `--interactive`? The interview's Q2 answer makes "pipeline flaw mid-run" a rule, which is what the checkpoint asks a person about. |
| OQ-3 | Which `sources:` order the site and lint expect (researcher order vs cached-then-fresh), or whether order is free. |
| OQ-4 | When templates become stored sentences (SP6, one claim path), what replaces `render_claim_text`'s "one of (...)" hint, `validate_analyst_title` and the title-failed branch; and what the Evaluator grades then (HZ-6, HZ-12). |
| OQ-5 | Does entity inference (`claim-draft -`) survive? It is the only path that writes an entity from analyst output (HZ-5), and the longer-term submissions platform in the interview framing would want something like it. |
| OQ-6 | Run id granularity for the findings file: per claim (onboard today) or per command. |
| OQ-7 | Is the `claim-draft` Brave key check intentional (HZ-18)? Not found: any note explaining it. |
| OQ-8 | Should the academic origin (arXiv) fire on ad hoc claims once one loop passes `topics` everywhere (HZ-20)? Today it never does on `claim-draft`. |
| OQ-9 | Where the `claim-refresh` sidecar-first ordering belongs in a single writer: always sidecar first (then draft/onboard change), or a per-outcome rule. |
