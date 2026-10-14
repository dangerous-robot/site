# Pipeline map: persistence and the sidecar

Phase 1 (Challenge) reader output for the research pipeline rebuild. Facts carry `file:line`; paths are relative to the repo root. Line numbers are from the working tree on 2026-10-14 (persistence.py last changed 2026-10-11, 70 commits since 2026-04-19).

Scope: `pipeline/orchestrator/persistence.py` (1209 lines), `pipeline/orchestrator/checkpoints.py` (389), `pipeline/common/frontmatter.py` (113), `pipeline/common/models.py` (325), `pipeline/common/sidecar.py` (21), plus every caller that writes a claim, sidecar, source or entity file, and every reader in `src/`.

## 1. Files on disk and who writes them

| File | Path rule | Writer(s) | Overwrite rule |
|---|---|---|---|
| Claim | `research/claims/<entity-slug>/<claim-slug>.md` for companies and products (flat); `research/claims/<type>/<slug>/<claim-slug>.md` for everything else (`_claim_dir_for`, persistence.py:314-326) | `_write_claim_file` (persistence.py:464-624); `set_claim_status` (:1077-1124); `set_claim_corrections` (:1127-1131); `review_queue._apply_edits` (review_queue.py:319-329); hand edits | `_write_claim_file` refuses to overwrite unless `force=True` (:520-523) |
| Sidecar | `<claim-stem>.audit.yaml` beside the claim (sidecar.py:10-11; duplicated at persistence.py:939 and scripts/rerun_v1_claims.py:53) | `_write_audit_sidecar` (persistence.py:899-1071); `_store_analyst_record` (:686-704); `_edit_sidecar` (:821-835) via `clear_audit` (:838-855) and `mark_forced_rewrite` (:858-896); `review.approve_claim` (review.py:269-282); `dr publish` (cli.py:2540-2548) | Always overwritten whole by `_write_audit_sidecar`; the other four writers load, edit one block, dump |
| Source | `research/sources/<year>/<slug>.md` (persistence.py:240-242) | `_write_source_files` (:232-270) via `VerificationResult.persist_sources` (pipeline.py:185-207) and the two direct calls in `research_claim` (pipeline.py:1735, 1755, 1770); `dr step-ingest --write` through `source_markdown` (:218-229); `dr wayback-backfill` edits `archived_url` (cli.py:499) | Never overwritten: `open("x")` (:251); a slug taken by a different URL gets `<host>-<slug>`, `-2`, `-3` (:162-195) |
| Entity | `research/entities/<companies\|products\|subjects>/<slug>.md` (:51-55, :273-276) | `_write_entity_file` (:279-311); `_write_draft_entity_file` to `research/entities/drafts/<type>/` (:1134-1166; no `drafts/` dir exists on disk today); `update_entity_enrichment` (:1181-1209) | `_write_entity_file` returns early if the file exists (:297-299); enrichment splices `description`, `founded`, body only (:1203-1208) |

Current disk state (2026-10-14): 11 claim files (8 `status: published`, 3 `draft`), all 11 sidecars carry `analyst_record`, none has a pending `refresh` block, no claim carries `phase`, `recheck_cadence_days` or `next_recheck_due`.

## 2. Claim file schema as written

`_write_claim_file` builds this dict in this key order (persistence.py:591-609) and dumps it through `serialize_frontmatter` (frontmatter.py:103-113), which drops every key whose value is `None` (frontmatter.py:90-100). So an optional field is absent from the file, never `null`.

| Field | Value written | Source of the value | Site reads it (`src/`) |
|---|---|---|---|
| `title` | analyst title, or placeholder title on a blocked write | caller (`ao.verdict.title`, `render_blocked_title`) | `[...slug].astro:109` fallback for page title; `index.astro:189` |
| `entity` | `<type-dir>/<slug>` ref | caller (`entity_ref_for`, :273-276, or the file's own `entity`) | every index page filters on it (`matrixLookups.ts:29`, `entities/[...slug].astro:35`) |
| `topics` | `FlowList` (flow style `[a, b]`) | analyst topics for claim-draft (pipeline.py:1808); template topics for onboard and refresh (pipeline.py:2916, cli.py:1315) | `topics/[topic].astro:21`, `criteria.ts:39` |
| `verdict` | enum | analyst, or `unverified` on a blocked write (pipeline.py:2764) | everywhere |
| `confidence` | enum | analyst, after the level fit may lower it to `low` (:433-434) | `ResponsibleAIEvidence.astro:115` |
| `verification_level` | enum value or absent | analyst, after `fit_verdict_to_written_pool` (:354-447) | `[...slug].astro:91` |
| `cap_rationale` | string or absent | analyst, level-fit template (:440-443), or kept operator text (see § 4) | `[...slug].astro:95` (only on a capped level) |
| `takeaway` | string or absent | analyst or kept (see § 4) | `[...slug].astro:106,145`; `review_queue.py:109` |
| `seo_title` | string or absent | analyst or kept (see § 4) | `[...slug].astro:109` |
| `criteria_slug` | template slug or absent | onboard and refresh pass it; claim-draft passes none (cli.py:944 docstring, pipeline.py:1804-1819) | `criteria.ts:26`, `matrixCheck.ts:82`; lint `published-without-criterion` (checks.py:95) and `review.py:121-126` require it to publish |
| `status` | `draft`, `blocked`, or the caller's value | `draft` by default (:476); `blocked` on the three blocked branches; `dr step-analyze --write` without `--force` passes the file's current status (cli.py:773) | production builds only `published` and `archived` pages (`[...slug].astro:26`); every index filters `=== 'published'` |
| `blocked_reason` | enum or absent | `_classify_blocked_reason` (pipeline.py:221-236) or `ANALYST_ERROR` | not read by `src/` beyond schema (content.config.ts:213) |
| `as_of` | `datetime.date.today()` (:604), local date, quoted string on disk (frontmatter.py:28-29) | the write itself | `claims/index.astro:13` sort; `[...slug].astro:60` |
| `sources` | list of `year/slug` ids | `source_ids` from the write of the cited sources (pipeline.py:1770-1780, `persist_sources`) | `[...slug].astro:97,266`, `citations.ts:11` |
| `source_overrides` | list of `{source, independence?, reason}` or absent | `verdict_write_kwargs` (:336-351), filtered to written ids by the level fit (:384-388) | `[...slug].astro:99`, `sourceQuality.ts:60-80` |
| `corrections` | existing list, or absent | always carried over from the file (:546, :607); written only by `review._add_correction` (review.py:180-196) | `[...slug].astro:135-143` |
| `tags` | existing list, `[]` when none | always carried over (:547, :608); set by `review_queue._apply_edits` as `FlowList` (review_queue.py:326) or by hand | `index.astro:158-161` (`home-familiar`, `home-second`, `highlight`) |

Fields the site schema and the linter know but no pipeline code writes:

| Field | Declared at | Written by | Note |
|---|---|---|---|
| `phase` | content.config.ts:211; `Phase` enum models.py:99-104; `CANONICAL_CLAIM_KEYS` checks.py:33 | nothing. `set_claim_status` accepts a `phase` kwarg (:1082, :1120-1121) but no caller passes it (grep `phase=` over `pipeline/` outside tests: none) | dead on the write side. content.config.ts:210 cites `docs/plans/claim-lifecycle-states.md`, which now lives at `docs/plans/completed/claim-lifecycle-states.md` |
| `recheck_cadence_days` | content.config.ts:216 (default 60) | nothing | `[...slug].astro:287` prints "reviewed every N days" from the default |
| `next_recheck_due` | content.config.ts:217 | nothing | lint `check_stale_recheck` (checks.py:447-465) warns when it is past; no claim has one, so the check never fires |

Body: the analyst narrative, `rstrip() + "\n"` (:610). No markdown normalisation beyond that (the emitter bugs in `docs/UNSCHEDULED.md` "Pipeline markdown emitter bugs" are upstream of this write).

Style facts that churn diffs: `topics` is always flow style; `tags` is flow style only when `review_queue` wrote it (disk today: nine `tags: []`, one `tags: [highlight]`, one block-style `tags:` with `- highlight` on the next line); dates are quoted strings; `yaml.dump(sort_keys=False, allow_unicode=True)` (frontmatter.py:106-112).

## 3. Who calls `_write_claim_file`, and in what order relative to the sidecar

| Command | Call site | Status written | Order |
|---|---|---|---|
| `dr claim-draft` (`research_claim`) | pipeline.py:1804-1819 | `draft` | claim first (:1804), sidecar after the auditor (:1841-1857) |
| `dr onboard` success | pipeline.py:2928-2944 | `draft` | claim first, sidecar at :2950-2966 |
| `dr onboard` blocked, three branches (threshold, analyst failure, title fails template) | pipeline.py:2759-2774, :2815-2830, :2868-2883 | `blocked` | claim first, sidecar at :2777, :2833, :2886 with `comparison=None` and no `analyst_record` |
| `dr claim-refresh` four branches | cli.py:1226-1241, :1258-1273, :1294-1309, :1324-1341 | `blocked` ×3, `draft` | sidecar first (`_write_sidecar` :1192-1211), then claim; the comment at :1185-1188 explains the inversion (snapshot survives a failed claim write) |
| `dr step-analyze --write [--force]` | cli.py:782-799 | file's status, or `draft` when `mark_forced_rewrite` says the claim was not a draft (:773-779) | no sidecar write at all except `clear_audit` (:779) and `_store_analyst_record` inside the claim write (:618-623) |
| `dr review --approve/--archive` | review.py:289 via `set_claim_status` | `published` / `archived` | sidecar first (:279-282, "commit point"), then status flip |
| `dr publish` | cli.py:2551 | `published` | sidecar first (:2540-2548), then status |

Before a forced write that is not `dr claim-refresh`, callers run `mark_forced_rewrite` (persistence.py:858-896) so a published, archived or blocked claim gets `human_review` reset and a published one gets the `refresh` block before the claim is replaced: pipeline.py:1800-1803, :2738-2741, cli.py:775-777. `dr claim-refresh` gets the same effect by passing `reset_review=True`, `previous_publication` and `current_source_ids` to `_write_audit_sidecar` (cli.py:1207-1209).

## 4. Keep rules that protect operator fields

All in `_write_claim_file` (persistence.py:525-589). They run only on a forced overwrite with a parseable existing claim; an unparseable one raises (:533-540).

The reference point is the sidecar's `analyst_record` (`_read_analyst_record`, :665-683): what the analyst last proposed. Missing record: synthesised as `{title, seo_title: None, verdict}` from the file when it is not blocked (:677-683), so any `seo_title` or `takeaway` on disk then counts as the operator's.

| Field | Keep the existing value when | Lines |
|---|---|---|
| `seo_title` | it differs from `record.seo_title` AND `normalize_title(record.title) == normalize_title(new title)`; else when the analyst passes `None` | :553-561 |
| `takeaway` | the analyst passes `None` (whatever the verdict); or it differs from `record.takeaway` AND `record.verdict ==` new verdict | :564-569 |
| `cap_rationale` | with a `cap_rationale` key in the record: it differs from `record["cap_rationale"]` (any level, any confidence, blocked writes too). Without one: `not cap_rationale_fitted` AND new level is `claimed`/`self-reported` AND level and confidence both unchanged | :571-589 |
| `corrections` | always | :546, :607 |
| `tags` | always | :547, :608 |

Everything else is replaced: title, verdict, confidence, verification_level, topics, sources, source_overrides, criteria_slug, status, blocked_reason, as_of, body.

After the write, `updated_analyst_record` (:627-654) merges this run's analyst values into the record (a field the analyst omitted keeps its previous value; `cap_rationale` is always set, `None` included) and `_store_analyst_record` writes it into an existing sidecar only (:686-704). A blocked write leaves the record alone (:617-618). `research_claim` and `onboard` also pass `analyst_record_for(verdict)` to `_write_audit_sidecar` for a claim's first sidecar (pipeline.py:1855, :2964); an existing record wins there (:949-952).

`cap_rationale_fitted` travels as a private attribute `_cap_rationale_fitted` set on the pydantic `VerdictAssessment` (:439) and read back with `getattr` (:346).

Roadmap items that encode these rules: RE-AH (Claim refresh keeps operator fields and verifies quotes, roadmap:284-290) and RE-AK (Published fields survive the pipeline, roadmap:309-324); `docs/architecture/content-model.md` claim table (rows `seo_title`, `cap_rationale`, `takeaway`) and the `analyst_record` paragraph state the same rules in prose. One-time backfill: `scripts/backfill_analyst_record.py` (ran 2026-10-11, `c0fe380`).

Known gap still open: a takeaway written for the old verdict survives a verdict change when the analyst passes none (`docs/UNSCHEDULED.md` "Beta.7 fix-run findings", row "An old takeaway survives a verdict change when the analyst writes none").

## 5. Sidecar schema as written

`_write_audit_sidecar` (persistence.py:899-1071) assembles the dict in this order (:1050-1064) and dumps it with `yaml.safe_dump(sort_keys=False, allow_unicode=True)` (:1066-1069).

| Key | Shape | Source | Site reads (`src/`) |
|---|---|---|---|
| `schema_version` | `1` literal (:1051) | constant | `auditSchema` requires a number (content.config.ts:44); nothing reads the value |
| `pipeline_run.ran_at` | ISO timestamp, UTC from callers | caller | `[...slug].astro:84` |
| `pipeline_run.model` | `cfg.model` (the `--model` default) | caller | not shown; may name a model no agent ran (RF16, UNSCHEDULED "claim-refresh review findings") |
| `pipeline_run.agents` | list of agent names this run invoked | caller (`["researcher","ingestor"]`, `[..., "analyst"]`, full four, or `["auditor"]`) | `[...slug].astro:172` |
| `pipeline_run.level_clamp` | one-line note, present only when the level fit lowered the level (:1044-1045) | `fit_verdict_to_written_pool` return (:445) | no |
| `pipeline_run.failure` | `FailureInfo` dataclass minus `None` fields (:1046-1049; models.py:207-222: step, agent, model, error_class, error_message, timeout_s, traceback_head) | `VerificationResult.failure` | no; not in `auditSchema`, passes because the zod object is not strict |
| `models_used` | `{agent: model}` for `agents_run` only (:990-996); other agents' entries kept only with `keep_other_models=True`, which only `dr step-audit --write` passes (cli.py:1713) | `cfg.model_for(a)` | `[...slug].astro:197-205` |
| `research` | the researcher trace minus `acquisition` (:1012-1017): `mode`, `tool_outcomes`, `queries`, `planner_rationale`, `candidates_seen`, `urls_kept`, `urls_dropped`, `scorer_rationale`, `scorer_dropped_all`, `entity_exclude_*`, `blocklist_spared`, `urls_after_blocklist` (researcher/decomposed.py:376-607, pipeline.py:846, :1049) | `result.research_trace` | no |
| `sub_questions` | list of `{id, question, rationale, queries, citations}` (pipeline.py:650-674); key omitted when the planner emitted none (:1056-1057) | `_build_sub_questions_block` | no |
| `sources_consulted` | list of `{id, url, title, ingested, archive?, acquisition?}` (:707-754); `ingested` is always `True` (:737, :750); `acquisition` grafted by URL from `research_trace["acquisition"]` (:1019-1037); `archive` from `IngestNotes.archive` (:752-753) | `VerificationResult.sources_consulted()` (pipeline.py:177-183) | `[...slug].astro:179`; `review_queue.py:81-87` counts `ingested`; `stats.py:89-98` reads `acquisition.origin`; lint `check_unsafe_markup` (checks.py:904-905) |
| `refresh` | `{refreshed_at, previous{status, verdict, confidence, title, as_of, sources, reviewed_at, reviewer, ran_at}, dropped_sources}` (:794-818, snapshot :765-791) | started by `previous_publication` or carried forward from the existing sidecar; `dropped_sources` recomputed from `current_source_ids` | no. Read by `review_queue.py:78-79,111-112`, `review.py:142-151`, lint `check_refresh_pending_review` (checks.py:197-227), `dr publish` (cli.py:2430) |
| `audit` | `null`, or `{analyst_verdict, auditor_verdict, analyst_confidence, auditor_confidence, verdict_agrees, confidence_agrees, needs_review, auditor_reasoning, evidence_gaps, needs_review_reasons}` (:954-968) | `ComparisonResult` | `[...slug].astro:86,210-240`; `review.py:154-163` (override detection); lint `verdict-sidecar-mismatch` (checks.py:158-192) |
| `human_review` | `{reviewed_at, reviewer, notes, pr_url}` all `null` on a fresh or reset write; carried from the existing sidecar otherwise, plus `verdict_override` only when present (:973-986) | this function, `mark_forced_rewrite` (:889), `review.py:269-274`, `dr publish` (cli.py:2541-2544, reviewer `None`) | `[...slug].astro:85,87,103`; `matrixLookups.ts:35`; `people/brandon-f.astro:15`; lint `published-review-signoff` (checks.py:126-155) |
| `analyst_record` | `{title, seo_title, verdict, takeaway, cap_rationale}` (:627-654) | existing sidecar wins; else the passed record (:949-952, :1063-1064) | no |

Site-side validation that can fail a build from sidecar content: `sources_consulted[].url` must pass `httpUrl` (content.config.ts:56); `human_review` is required with its four keys present (nullable, not optional, :84-94); `pipeline_run` must have `ran_at`, `model`, `agents` (:45-49); a `human_review.reviewer` value with no entry in `src/lib/reviewers.ts:22-24` throws at render (`resolveReviewer`, reviewers.ts:52-58). A malformed sidecar is logged and treated as absent by the loader (content.config.ts:140-148), so a published claim with a corrupt sidecar builds without an audit trail and then fails lint (`published-review-signoff`).

`audit` is set to `null` by `clear_audit` (:838-855) for `dr step-analyze --write --force` (cli.py:779); the page then shows "Evaluator check unavailable" (`[...slug].astro:210-211`).

## 6. Sidecar readers and how each treats a corrupt file

| Reader | On missing | On unparseable | Lines |
|---|---|---|---|
| `read_sidecar` (used by lint, stats, review_queue, `_read_analyst_record`, `_read_published_snapshot`, `dr publish`) | `None` | `{}` (swallows every exception) | sidecar.py:14-21 |
| `_write_audit_sidecar` | fresh | warning, then proceeds with `existing = {}`: `human_review`, `refresh`, `analyst_record` and other agents' `models_used` are lost on that write | persistence.py:941-947 |
| `_store_analyst_record` | no-op | warning, return | :690-698 |
| `_edit_sidecar` (`clear_audit`, `mark_forced_rewrite`) | no-op | raises `ValueError` | :825-830 |
| `review.approve_claim` | `ClickException` | raw `yaml.safe_load` raises | review.py:229-237 |
| `dr step-audit --write` carry-over | fresh | `except YAMLError: pass`, so research trace, sub-questions, `level_clamp`, `acquisition` and `archive` are dropped silently | cli.py:1660-1701 |
| `dr publish` | skipped | raw `yaml.safe_load` inside `try/except Exception`, reported per claim | cli.py:2539-2554 |

## 7. The "checkpoint" format

`pipeline/orchestrator/checkpoints.py` holds no on-disk format. It defines:

- `StepError` (:15-96): a typed error with a free-form `error_type` vocabulary documented in the docstring (:25-62) and policed by `pipeline/tests/test_step_error_vocab.py`; errors reach the operator through `review_sources` and `VerificationResult.errors`, never the sidecar (the sidecar gets only `pipeline_run.failure` for the first fatal agent failure, models.py:209-214).
- `CheckpointHandler` protocol (:99-182): six interactive gates (`review_sources`, `review_disagreement`, `review_onboard`, `review_entity_enrichment`, `review_entity_disambiguation`, `review_verification_status`), with a `CLICheckpointHandler` (:185-316) and an `AutoApproveCheckpointHandler` (:325-389; disambiguation and verification-status auto-reject, :378, :389).

No resumable run state exists on disk. A run that dies mid-way leaves whatever it had written in order: sources before any claim (pipeline.py:1733-1737, 1754-1756, 2736; cli.py:1189), the claim before its sidecar on the draft and onboard paths, the sidecar before the claim on refresh and approve. A rerun starts from the sources already on disk through the URL dedup index (`build_source_url_index`, persistence.py:97-119; `_apply_url_dedup`, pipeline.py:869-894).

## 8. Source and entity writes

- `source_markdown` (:218-229) adds `source_type` from publisher and kind, `independence` from `source_type` when the ingest model gave none, and wraps bare links (RF31). The same derivation sits in `load_source_dict` (:137-138) and `_build_source_dict` (pipeline.py:1363-1369); the docstring at :125 says the dict shapes "must stay in sync" by hand.
- Slug collisions: `resolve_source_slugs` (:198-215) settles ids before the analyst sees them; `_write_source_files` repeats the check at write time (:246-266) and can rename a slug after the analyst and sidecar already used it (RF21, UNSCHEDULED "claim-refresh review findings").
- A source file is never updated once written, so a changed page keeps its first ingest forever and `dr claim-refresh` reuses it from disk (:122-150, pipeline.py:885-892).
- Entity refs: `entity_ref_for` (:273-276) and `_write_draft_entity_file` (:1148-1154) compute `<type-dir>/<slug>` separately.

## 9. Duplication (complete list)

| What | Locations |
|---|---|
| Sidecar YAML dump (same `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)` call) | persistence.py:702-705, :832-835, :1066-1069; review.py:279-282; cli.py:2545-2548 |
| Sidecar path rule | sidecar.py:10-11; persistence.py:939; scripts/rerun_v1_claims.py:53; content.config.ts:134 |
| Sidecar load with a different corrupt-file policy each time | sidecar.py:14-21; persistence.py:941-947, :690-698, :825-830; review.py:237; cli.py:1660-1701, :2539-2554 |
| Starting the `refresh` block and resetting `human_review` | `_write_audit_sidecar(reset_review, previous_publication, current_source_ids)` for `dr claim-refresh` (cli.py:1207-1209) vs `mark_forced_rewrite` for claim-draft, onboard and step-analyze (pipeline.py:1800, :2738; cli.py:775); both call `_refresh_block` (:794-818); the reset dict literal is at :889 and :973-978 |
| Blocked-claim write (placeholder title and body, `_write_claim_file(status="blocked")`, `_write_audit_sidecar(comparison=None)`) | three branches in `onboard_entity` (pipeline.py:2747-2800, :2804-2856, :2859-2908) and three in `claim_refresh` (cli.py:1214-1243, :1246-1275, :1285-1311) |
| Full-claim write + sidecar write sequence | pipeline.py:1795-1857 (`research_claim`), :2925-2966 (`onboard_entity`), cli.py:1320-1341 (`claim_refresh`), cli.py:747-799 (`step_analyze`) |
| Verification-level counting rules | `fit_verdict_to_written_pool` (persistence.py:354-447), lint `check_verification_level_pool` (checks.py:726-800), site `countSourcesByIndependence` (sourceQuality.ts:60-80); the `self-reported` basis rule is named as written twice in UNSCHEDULED "Beta.7 fix-run findings" |
| `source_type` / `independence` derivation | persistence.py:137-138, :221-226; pipeline.py:1363-1369 |
| Schema declared four times by hand | Python enums (models.py:76-192); Zod (content.config.ts:17-228); linter `CANONICAL_CLAIM_KEYS` and `CANONICAL_ENTITY_KEYS` (checks.py:20-36); prose tables in `docs/architecture/content-model.md` |
| Entity ref computation | persistence.py:273-276 and :1148-1154 |
| `human_review` approval write | review.py:269-274 (with reviewer and override) vs cli.py:2541-2544 (`dr publish`, reviewer `None`, no override) |
| Status transition rules | `review._preflight_status` (review.py:98-139) vs `dr publish` classification (cli.py:2398-2441) |

## 10. Hazards: what a rewrite could silently lose or break

| Hazard | Location |
|---|---|
| The three keep rules (`seo_title`, `takeaway`, `cap_rationale`) depend on `analyst_record`; a new loop that writes claims without reading and updating the record overwrites operator text on every rerun (RE-AH and RE-AK regress) | persistence.py:525-589, :617-623 |
| `corrections` and `tags` must be carried over on every claim rewrite; `tags` drive the homepage cards (`home-familiar`, `home-second`, `highlight`) and `corrections` are the public record of a changed verdict | persistence.py:546-547, :607-608; index.astro:158-161; review.py:180-196 |
| `human_review` (including `verdict_override`) carries over on a non-refresh sidecar rewrite and resets on a refresh; losing the carry-over erases Brandon's sign-off, losing the reset lets a changed verdict go live without review | persistence.py:973-986, :889 |
| The `refresh` block must carry forward unchanged through a second refresh, be removed only by approval or archiving, and block `dr publish` while present | persistence.py:808-809; review.py:276-277; cli.py:2430-2432 |
| `models_used` keeps other agents' entries only on `dr step-audit --write`; `level_clamp`, `acquisition` and `archive` are re-grafted there by hand | persistence.py:1000-1005; cli.py:1657-1699 |
| `dr step-analyze --write` rewrites the claim with no sidecar rewrite, so `pipeline_run` and `models_used` go stale (open UNSCHEDULED row) | cli.py:768-799 |
| Site build fails on: a sidecar `sources_consulted[].url` that is not http(s); a sidecar missing `human_review` or `pipeline_run`; a `human_review.reviewer` not in `reviewers.ts` | content.config.ts:45-94; reviewers.ts:22-58 |
| A sidecar holding only `analyst_record` fails the site schema, which is why `_store_analyst_record` refuses to create one | persistence.py:686-693 |
| Production builds only `published` and `archived`; a committed `draft` or `blocked` rewrite of a published claim removes its page | `[...slug].astro:26`; runbook.md:75,80 |
| Publishing needs `criteria_slug`; ad hoc claims from `dr claim-draft` have none and `dr claim-refresh` refuses them. SP6 (one claim path, templates as sentences) changes who supplies this field | review.py:121-126; checks.py:95; cli.py:944, :1108-1116 |
| Claim ids and URLs come from the file path (`research/claims/<...>` minus `.md`); companies and products are flat, subjects nested. Interview Q10 assumes site URLs stay stable | persistence.py:314-326; content.config.ts:128 |
| `as_of` is the local date, `ran_at` is UTC; claims list and matrix sort on `as_of` | persistence.py:604; `claims/index.astro:13` |
| Sources are never rewritten; a recheck (SP5) that relies on fresh page text will reuse the first ingest from disk | persistence.py:251; pipeline.py:885-892 |
| `sources_consulted[].ingested` is always `True`, and the list names ids of uncited sources that were never written (open UNSCHEDULED row) | persistence.py:737, :750; UNSCHEDULED "Beta.7 fix-run findings" |
| `_write_audit_sidecar` on an unparseable existing sidecar drops `human_review`, `refresh`, `analyst_record` with only a warning | persistence.py:941-947 |
| The level fit mutates the analyst's `VerdictAssessment` in place (level, confidence, overrides, rationale) after the auditor compared against the original, so `audit.analyst_confidence` can disagree with the claim (RE-AL row 2) | persistence.py:384-388, :432-443; pipeline.py:1795 before :1832 |
| Blocked writes pass `Verdict.UNVERIFIED` / `Confidence.LOW` placeholders; a later keep rule must not treat them as the analyst's (the record skips blocked writes for this reason) | persistence.py:617-618, :677-678 |
| Entity file is written once and never refreshed by the pipeline; `search_hints.exclude` written at onboard shapes every later search (RE-AL row 6) | persistence.py:297-299 |
| Phase enum, `recheck_cadence_days`, `next_recheck_due` are schema-only; a rewrite that deletes them must also edit content.config.ts, checks.py:31-36 and content-model.md, or keep writing nothing | models.py:99-104; checks.py:33-34; content.config.ts:211-217 |
| Test coverage of these rules is spread over seven files (9,680 lines): `test_audit_trail.py` (2,300 lines, 116 tests, 63 named for keep, record, refresh, clamp, override or status), `test_cli.py`, `test_orchestrator.py`, `test_backfill_analyst_record.py`, `test_linter.py`, `test_entity_independence.py`, `test_researcher_decomposed.py`; a strangler loop must either reuse or port them | pipeline/tests/ |

## 11. Open questions for the plan

- Carrier: does the new loop keep `.audit.yaml` as the sidecar, or does it take the "Canonical verdict artifact" decision (UNSCHEDULED, operator decision pending) and reshape or merge it? The site reads nine sidecar keys today (§ 5); everything else is operator-only.
- Write order and atomicity: claim-first (draft, onboard) or sidecar-first (refresh, approve)? One order, or a single write function that does both.
- `dr recheck --due` (SP5): what date drives "due"? No claim carries `next_recheck_due`; the only dates on disk are `as_of` (local) and `pipeline_run.ran_at` (UTC).
- Recheck and stale sources: should a recheck re-ingest a source already on disk, and if so what happens to the file and to the other claims that cite it?
- Restatement link (SP3): the claim-restate plan's D17 puts `restates: <claim>` in the sidecar, not the frontmatter; does the review packet (SP4) need it in the claim file instead?
- `phase`: delete from the schemas, or have the new loop write it?
- `sources_consulted[].ingested`: keep the field and start writing `false` for failed URLs, or drop it?
- Which of the five sidecar writers survive SP7 (fold side tools)? `dr publish`, `dr review`, `dr review-queue` each edit the sidecar by hand today.
- Does a blocked claim stay a claim file with placeholders (today), or become a findings-file entry with no claim (interview Q4: retry N times, then delete the half-claim)? The second removes three of the four write branches and the `blocked` status from the site schema.
