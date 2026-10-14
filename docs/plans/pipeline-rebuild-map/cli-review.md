# Pipeline map: CLI and review

Phase 1 (Challenge) reader output for the research pipeline rebuild. Subsystem: `pipeline/orchestrator/cli.py`, `review.py`, `review_queue.py`, `stats.py`, `entity_resolution.py`, `pipeline/common/templates.py`, `pipeline/linter/`. Facts carry `file:line` as of the working tree on 2026-10-14 (HEAD `40ba781`). "Not found" means I looked and found nothing on disk.

Paths are relative to the repo root; `pipeline/` is written out everywhere.

## 1. Entry points

| Entry point | Location | Purpose |
|---|---|---|
| `dr` console script | `pipeline/pyproject.toml:24-25` (`dr = "orchestrator.cli:main"`) | The only installed pipeline CLI |
| `main` click group | `pipeline/orchestrator/cli.py:192-219` | Global options, logging setup, run id |
| `python -m linter` | `pipeline/linter/__main__.py:12-46` | Second lint entry (argparse), used by `inv audit` (`tasks.py:195-220`) |
| `python -m linter.prune` | `pipeline/linter/prune.py:16-54` | Deletes `unreferenced-source` files; `inv audit.prune` (`tasks.py:224-240`) |
| CI lint job | `.github/workflows/ci.yml:80-108` | `uv run dr lint --format json --severity error` from `pipeline/`, annotates errors, fails on exit 1 |
| Local pre-commit hook | `.git/hooks/pre-commit:2-14` (not committed; `core.hooksPath` unset) | Runs `dr lint --repo-root <root>` before every commit |

Global options (`cli.py:193-198`): `--verbose`, `--model` (env `DR_MODEL`, default `greenpt:gpt-oss-120b`, `pipeline/common/models.py:201`), `--researcher-model`, `--analyst-model`, `--auditor-model`, `--ingestor-model` (env `DR_<AGENT>_MODEL`). Agent names: `AGENT_NAMES = ("researcher", "analyst", "auditor", "ingestor")` (`models.py:73`). Logging and a run id are set only when a subcommand is invoked (`cli.py:216-219`).

Provider key check: `_required_env_for_model` (`cli.py:55-80`) maps a model prefix to env vars (`_PROVIDER_ENV`, `cli.py:44-51`: infomaniak, greenpt, anthropic, openai, google-gla, google-vertex); an unknown prefix is a `UsageError`; `_check_provider_api_keys` exits 2 when any var is missing (`cli.py:83-98`). Every LLM command calls it (13 call sites).

Help grouping: `_COMMAND_GROUPS` (`cli.py:119-126`) files commands as "Read-only", "Creates or overwrites claim files", "Modifies existing files in place"; unlisted commands land in "Other" (`cli.py:162-189`). `step-ingest`, `step-analyze` and `step-audit` sit in the read-only group although each has `--write`/`--force` (`cli.py:121`; also noted in `docs/UNSCHEDULED.md` "Docs versus code" row).

## 2. Command inventory (live `dr --help`, 2026-10-14)

Eighteen commands: 16 visible, 2 hidden deprecated aliases.

| Command | Lines in `cli.py` | Arguments and flags | What it calls | What it writes |
|---|---|---|---|---|
| `step-research ENTITY CLAIM` | 279-315 | `--llm-concurrency` (default 8) | `researcher.decomposed.decomposed_research` | Nothing. Blocklist not applied (`:267`) |
| `step-ingest URL` | 321-427 | `--write`, `--force` (implies write), `--skip-wayback`, `--repo-root` | `ingestor_agent.run` (120 s timeout, `:365`), `arxiv_corporate_lab`, `_check_ingested_source` (`pipeline.py`), `archive_after_ingest`, `resolve_source_slugs`, `source_markdown` | `research/sources/<year>/<slug>.md`; mode `x` without `--force`, `w` with (`:417-423`). Save Page Now only when writing (`capture = do_write or force`, `:357`) |
| `wayback-backfill SOURCE_IDS...` | 491-626 | `--recheck`, `--repo-root` | `check_capture`, `archive_with_time_limit` (`ingestor/tools/wayback.py`); one live GET per source (`_live_end`, `:531-545`) | Edits only the `archived_url:` line of a source file (`_set_archived_url`, `:433-488`, byte-preserving with a parse round-trip check `:481-488`). Exit 1 if any source failed |
| `step-analyze --claim REF` | 632-803 | `--write`, `--force` (implies write), `--repo-root` | `load_entity`, `parse_entity_ref`, `_claim_template`/`render_claim_text`, `load_source_dict`, `_analyse_claim` (`pipeline.py`), `fit_verdict_to_written_pool` | With `--write`: claim file via `_write_claim_file` (`:776-795`). With `--force`: `mark_forced_rewrite` returns a non-draft to draft and `clear_audit` nulls the sidecar `audit` block (`:767-773`) |
| `claim-probe ENTITY CLAIM` | 878-926 | `--max-sources`, `--candidate-pool-size`, `--skip-wayback/--wayback`, `--interactive/--no-interactive`, `--max-initial-queries`, `--llm-concurrency` | `verify_claim` (`pipeline.py:345`) with `allow_save=False` (`:902`); `parse_entity_ref` when ENTITY contains `/`, errors swallowed (`:912-918`) | Nothing |
| `claim-draft ENTITY_REF CLAIM_TEXT` | 932-1026 | same six as probe plus `--repo-root`, `--force` | Requires `BRAVE_WEB_SEARCH_API_KEY` (`:951-953`); `parse_entity_ref` or `-` for analyst inference (`:964-972`); `research_claim` (`pipeline.py:1619`) | Sources, entity file when `-` (`pipeline.py:1785-1791`), claim at `slugify(analyst title)` with `status: draft` and no `criteria_slug` (`pipeline.py:1805-1820`), sidecar (`pipeline.py:1838-1853`). Prints a warning that the claim is not template-backed (`:955-959`) |
| `claim-refresh CLAIM_REF` | 1033-1348 | same six as probe plus `--repo-root` | Refuses without `criteria_slug` (`:1095-1102`); `_read_published_snapshot` before the run (`:1149`); `verify_claim` with the template (`:1155-1161`); `vr.persist_sources` (`:1172`) | Sidecar first, then claim, in four branches: A threshold-blocked (`:1198-1227`), B analyst failed (`:1229-1259`), C title fails template (`:1263-1291`), D success as `status: draft` (`:1294-1340`). `reset_review=True` (`:1189`) |
| `claim-promote CLAIM_REF` | 1355-1510 | `--repo-root` | Interactive prompts for slug, type, topics, core, notes (`:1420-1430`) | Appends a YAML text fragment under `templates:` in `research/templates.yaml` (`:1485-1489`); subject templates get `subjects: [subjects/<slug>]` (`:1467-1474`). Prints `dr onboard <ref> --only <slug> --force` (`:1510`). Does not write `tags` or `vocabulary` |
| `step-audit` | 1518-1723 | `--claim`, `--entity`, `--topic`, `--format text\|json`, `--dry-run`, `--write`, `--repo-root` | `list_claims`, `build_auditor_prompt`, `auditor_agent.run` called directly (`:1632-1633`, no semaphore, no `_run_with_null_retry`), `compare` | With `--write`: `_write_audit_sidecar(agents_run=["auditor"], keep_other_models=True)` (`:1700-1713`), re-grafting `acquisition`/`archive` from the old sidecar (`:1662-1697`). Skips blocked claims (`:1565-1567`) |
| `reassess` (hidden) | 1726-1743 | as step-audit minus `--write` | `ctx.invoke(step_audit, do_write=False)` | Nothing |
| `ingest URL` (hidden) | 1746-1761 | `--dry-run`, `--skip-wayback`, `--force`, `--repo-root` | `ctx.invoke(step_ingest, do_write=not dry_run)` | As step-ingest |
| `onboard ENTITY_NAME [HOMEPAGE_URL]` | 1764-1941 | `--type company\|product\|subject`, the six probe flags, `--repo-root`, `--only`, `--force`, `--search-hint-include`/`--search-hint-exclude` (repeatable) | `parse_entity_ref` when the name has `/` (`:1824-1835`); `onboard_entity` (`pipeline.py:2293`) | Entity file (or `research/entities/drafts/` on reject, `persistence.py:1135`), one claim plus sidecar per core template in four branches (`pipeline.py:2747-2940`), source files. `--force` also splices enricher output into an existing entity (`pipeline.py:2650`) |
| `entity-enrich ENTITY_REF` | 1974-2040 | `--repo-root`, `--interactive`, `--force` | Refuses without `--force` when the entity body is non-empty (`:2010-2020`); `enrich_entity` (`pipeline.py:2164`) | Entity frontmatter `founded`, `description` and body (`update_entity_enrichment`, `persistence.py`). Exit 1 on `failed` |
| `review --claim REF` | 2047-2157 | `--reviewer`, `--notes`, `--pr-url`, `--approve`, `--archive`, `--correction`, `--repo-root` | Inline bare-slug resolution (`:2093-2115`), sidecar must exist (`:2123`), `approve_claim` (`review.py:209`) | Sidecar `human_review`; claim `status` on `--approve`/`--archive`; `corrections` entry when a refresh changed the verdict |
| `review-queue` | 2164-2222 | `--format text\|json`, `--filter-entity`, `--repo-root` | `find_publication_queue`, `format_table`, `to_json_records`, `run_interactive` (`review_queue.py`) | Interactive: approve (via `approve_claim`), delete (Trash on macOS), edit five header fields. Always exit 0 |
| `publish` | 2275-2571 | exactly one of `--entity`, `--claim`, `--all`; `--dry-run`, `-y/--yes`, `--note`, `--continue-on-error/--strict`, `--repo-root` | Classifies drafts (`:2370-2420`), `refresh_verdict_change`, `unreviewed_verdict_change` (`review.py`) | Sidecar `human_review` with `reviewer: null`, `notes: "[auto-publish] <suffix>"` (`:2498-2504`), then `set_claim_status(..., "published")` (`:2508`). Exit 1 if any skip counted as an error (`:2470-2473`, `:2571`) |
| `lint` | 2574-2613 | `--entity`, `--format text\|json`, `--severity error\|warning\|info`, `--repo-root` | `linter.runner.run_all_checks` | Nothing. Exit 1 when any `error` issue exists (`:2611-2613`), whatever `--severity` hides |
| `stats` | 2620-2662 | `--format text\|json`, `--repo-root` | `orchestrator.stats.compute_stats` | Nothing |

Shared flag block: `--max-sources`, `--candidate-pool-size`, `--skip-wayback/--wayback`, `--interactive/--no-interactive`, `--max-initial-queries`, `--llm-concurrency` are declared four times (`cli.py:881-886`, `935-942`, `1035-1041`, `1768-1776`) and folded into `VerifyConfig` by an identical `overrides` dict four times (`:899`, `:977`, `:1136`, `:1850`). `VerifyConfig` defaults: `max_sources 8`, `candidate_pool_size 32`, `max_initial_queries 7`, `llm_concurrency 8`, `research_origins ["tavily", "arxiv"]` (`pipeline/orchestrator/pipeline.py:278-315`).

Checkpoints: `--interactive` swaps `AutoApproveCheckpointHandler` for `CLICheckpointHandler` (`pipeline/orchestrator/checkpoints.py:186-280`): `review_sources` (confirm, `:188-205`), `review_disagreement` (confirm, default no, `:207-218`), `review_onboard` (accept/reject/edit slugs, `:220-244`), `review_entity_enrichment` (`:246-262`), `review_entity_disambiguation` (`:264`).

## 3. Review and publish flow

### 3.1 Objects and states

- Claim `status`: `draft | published | archived | blocked` (`pipeline/common/models.py:92-96`; site enum with default `draft`, `src/content.config.ts:208`). `BlockedReason`: `insufficient_sources | terminal_fetch_error | analyst_error` (`models.py:106-109`).
- Sidecar `<claim>.audit.yaml` (`pipeline/common/sidecar.py:10-20`). Blocks written by `_write_audit_sidecar` (`pipeline/orchestrator/persistence.py:899-1074`): `schema_version`, `pipeline_run` (`ran_at`, `model`, `agents`, optional `level_clamp`, `failure`), `models_used`, `research`, `sub_questions`, `sources_consulted`, `refresh` (optional), `audit` (nullable), `human_review`, `analyst_record` (optional). `human_review` keys: `reviewed_at`, `reviewer`, `notes`, `pr_url`, plus `verdict_override` only once approval writes it (`persistence.py:973-990`; site schema `src/content.config.ts:85-93`).
- Site visibility: index pages list only `status === 'published'` claims (`src/pages/research/claims/index.astro:11`, `src/pages/index.astro:13`, and 7 more pages). The reviewer shown is mapped from the sidecar email in `src/lib/reviewers.ts`; an unmapped non-null reviewer throws at build (`src/lib/reviewers.ts:55`).

### 3.2 `dr review` (one claim, a person at a terminal)

1. `--approve` and `--archive` are mutually exclusive (`cli.py:2088`).
2. Claim resolution: `<entity>/<slug>` joins directly; a bare slug is globbed as `claims/*/<slug>.md` and must be unique (`cli.py:2093-2115`). The glob is one directory deep, so a bare slug never finds a subject claim under `claims/subjects/<subject>/`.
3. Sidecar must exist ("run the pipeline first", `cli.py:2123-2129`).
4. `approve_claim(claim_path, mode=review|approve|archive, ...)` (`pipeline/orchestrator/review.py:209-291`):
   - Preflight (`_preflight_status`, `review.py:97-147`): approve needs status `draft` (a missing status counts as draft, `:109`), refuses archived (`:111`), blocked (`:112-117`), and any claim without `criteria_slug` (`has_criterion`, `:128-134`; `pipeline/common/frontmatter.py:80-88`). Archive needs `published` or `blocked` (`:138-146`).
   - Reviewer defaults to `git config user.email` (`_resolve_reviewer`, `:66-80`).
   - A refresh that changed the published verdict requires `--correction TEXT` (`refresh_verdict_change`, `:150-160`; raised at `:234-241`).
   - Person gate: stdin must be a tty and the operator must type the claim slug back (`require_terminal`, `:43-48`; `confirm_person_present`, `:51-63`; `claim_slug_for`, `:35-40` handles the nested subject path). Runs after preflight so a failing claim never prompts (`:243-245`).
   - Re-read after the prompt, repeat preflight (`:247-256`).
   - Write order: correction entry prepended to claim `corrections` (`_add_correction`, `:190-206`, deduped on `previous_verdict`), then sidecar (`reviewed_at` today, `reviewer`, `notes`, `pr_url`, `verdict_override` from `_verdict_override` `:162-171`; `refresh` block popped on approve/archive, `:276-278`), then `set_claim_status` with the expected current status (`:286-291`; `persistence.py:1077-1124` raises on mismatch). The sidecar is the commit point (`:283-285`).
5. The success message prints `research/claims/{claim}.md` from the raw `--claim` text, not the resolved path (`cli.py:2141-2149`).

Rule for agents: never run `dr review`, never wrap it in a pty, never edit `human_review` by hand (`AGENTS.md:187`).

### 3.3 `dr review-queue` (walk the drafts)

- Queue membership (`_build_item`, `pipeline/orchestrator/review_queue.py:55-113`): status `draft` or absent (`:62-65`), sidecar present (`:67-70`), `human_review.reviewed_at` empty (`:72-75`). Carries analyst/auditor verdicts, `needs_review`, source counts, `tags`, `takeaway`, `seo_title`, and the pending refresh's previous verdict and date (`:97-113`).
- Keys (`_ACTIONS`, `:135`): `a` approve via `approve_claim(mode="approve")` with a correction prompt when the verdict changed since publication (`:473-500`; `require_terminal` first, `:476`); `d` delete claim and sidecar, to `~/.Trash` on macOS, hard delete elsewhere (`_delete_files`, `:158-173`); `e` edit `title`, `takeaway`, `seo_title`, `tags`, `verdict` in `$VISUAL`/`$EDITOR`/`code --wait` through a temp YAML buffer with validation, preview, and an mtime conflict check (`_EDITABLE_FIELDS` `:142`, `_ALLOWED_VERDICTS` `:143-146`, `_edit_fields` `:343-425`, mtime at `:408`); `s` skip; `p` preview through `$PAGER`/`less` (`:222-233`); `o` open in editor non-blocking (`:236-247`); `q` quit.
- `--format text` is a 5-column TSV (`format_table`, `:520-528`); `--format json` dumps every `QueueItem` field (`to_json_records`, `:531-533`).
- `_apply_edits` rewrites the claim frontmatter with `serialize_frontmatter`, keeping `tags` flow style (`:319-329`).

### 3.4 `dr publish` (bulk, no reviewer)

- Selector: exactly one of `--claim`, `--entity`, `--all` (`cli.py:2335-2342`).
- Classification per draft (`cli.py:2370-2420`): skip published, archived, blocked (with reason), missing sidecar, missing `criteria_slug`, a sidecar `refresh` block (needs `dr review --approve`, `:2400-2404`), and a verdict that differs from `audit.analyst_verdict` with no matching `verdict_override` (`unreviewed_verdict_change`, `review.py:174-187`; skip at `:2408-2411`; roadmap RE-U (Publish refuses unreviewed overrides)).
- Writes `human_review` with `reviewer: null` and the `[auto-publish]` note prefix (`:2359-2360`, `:2498-2504`), then flips status (`:2508`). Missing-criterion, refresh and override skips count as errors (exit 1, `:2470-2473`, `:2484-2490`).
- Reversal path: a later `dr review --claim X` without `--approve` writes the reviewer in (docstring `:2313-2314`).

### 3.5 Refresh trail (what approval must preserve)

- `_read_published_snapshot` (`persistence.py:765-790`) captures status, verdict, confidence, title, as_of, sources, reviewed_at, reviewer, ran_at before an overwrite; `_refresh_block` (`:793-823`) stores it as `refresh.previous` with `refreshed_at` and `dropped_sources`, and carries an existing block forward unchanged so a second refresh never replaces the published state with an unapproved one.
- `mark_forced_rewrite` (`:858-896`) is the one helper that returns a published, archived or blocked claim to draft and resets `human_review` for `dr claim-draft --force`, `dr onboard --force` and `dr step-analyze --write --force` (roadmap RE-AK (Published fields survive the pipeline)).
- `clear_audit` (`:838-855`) nulls `audit` after `dr step-analyze --write --force` so approval does not record a `verdict_override` the reviewer never made.
- `_write_claim_file` (`:464-640`) refuses to overwrite without `force` (`:521-524`) and, on a forced write, keeps operator-owned fields: `tags` and `corrections` always (`:546-547`, `:607-608`), `seo_title`, `takeaway` and `cap_rationale` by the `analyst_record` keep rules (`:526-600`; roadmap RE-AH and RE-AK). `analyst_record` lives in the sidecar (`_store_analyst_record` `:623`, `:686`; `updated_analyst_record` `:627-655`).
- Lint enforces the trail: `published-without-criterion` (`checks.py:95-123`), `published-without-review` (`:126-155`), `verdict-sidecar-mismatch` (`:158-194`), `refresh-pending-review` warning (`:197-229`).

Operator steps for a refresh are in `docs/runbook.md:73-80`; the sign-off diagram is `docs/architecture/research-flow.md:174-242`.

## 4. templates.yaml and onboard

### 4.1 The file

`research/templates.yaml`: 16 active entries under `templates:` (5 company, 8 product, 3 subject) and 7 under `inactive_templates:`, which nothing reads (file comment). Entry fields: `slug`, `text`, `entity_type`, `topics`, `core`, optional `notes`, `vocabulary` (`corporate-structure` only), `subjects` (subject templates), and `tags: [highlight]` on `ai-producers-existential-score` and `using-generative-ai-harms-cognitive-ability`.

### 4.2 Readers

| Reader | Location | What it reads |
|---|---|---|
| `load_templates` | `pipeline/common/templates.py:66-83` | `templates:` into `TemplateRecord` (`:31-63`): slug, text, entity_type, topics, core, notes, vocabulary, subjects. No `tags` field; the key is dropped |
| `linter.runner.load_templates` | `pipeline/linter/runner.py:54-64` | Slug set only, for `broken-criteria-slug` |
| `claim-promote` | `cli.py:1443-1460` | Raw YAML for slug uniqueness; appends a text fragment to keep comments |
| Site `criteria` collection | `src/content.config.ts:257-285` | Zod schema: slug, text, entity_type, topics (1 to 3), core, notes, subjects, vocabulary. No `tags` |

Consumer of template `tags`: not found (grep over `pipeline/orchestrator/pipeline.py`, `templates.py`, `content.config.ts`). Claim tags are operator-set per `AGENTS.md:90-100`; `_write_claim_file` keeps whatever `tags` the claim file already has (`persistence.py:608`).

### 4.3 Rendering and validation

- `templates_for_entity_type` (`templates.py:86-107`): core templates of the type; for `subject` only those whose `subjects:` names `subjects/<slug>`, and `[]` when no slug is given.
- `render_claim_text` (`:131-138`): replaces `PRODUCT`/`COMPANY`/`ENTITY` (`_substitute_entity`, `:120-128`; placeholder table also in `cli.py:33-38`) and expands each vocabulary slot to `one of (a, b, ...)` (`VOCABULARY_HINT_PREFIX`, `:25`). That hint string is what onboard and refresh pass as `claim_text` (`docs/UNSCHEDULED.md` "Vocabulary claim text" row).
- `validate_analyst_title` (`:184-204`): the analyst title must equal the rendered template (case and whitespace insensitive) with each vocabulary slot resolved to one allowed value and an optional `a`/`an`; otherwise the claim is written blocked (`blocked_title_message`, `:207-230`; refresh Branch C `cli.py:1263-1291`; onboard `pipeline.py:2860-2895`).
- `render_blocked_title` (`:141-148`) keeps the raw slot name for blocked titles.

### 4.4 Onboard flow (`onboard_entity`, `pipeline/orchestrator/pipeline.py:2293-2975`)

1. A `type/slug` ref loads the entity file first (`parse_entity_ref`, `:2345-2352`) and seeds light research with its website.
2. Phase A light research (`gather_light_research`, `:2367-2371`); Phase B entity verifier with the disambiguation and verification-status checkpoints (`:2383-2455`); Phase C enricher with its checkpoint, skipped when no page summary or when an entity file exists without `--force` (`:2457-2525`).
3. Step 2 template screening: `templates_for_entity_type` with the subject slug from the ref or the slugified name (`:2540-2550`); `_screen_templates` passes every core template (`:1953-1960`, "MVP"); a subject with no matching template warns and still writes the entity (`:2552-2583`).
4. Step 3 `review_onboard` checkpoint (`:2590-2593`); reject writes a draft entity under `research/entities/drafts/` (`:2603-2617`; `persistence.py:1135-1165`).
5. Entity file written if absent (`:2625-2635`); `--force` splices enricher output (`update_entity_enrichment`, `:2650`).
6. Per template: skip when the claim file exists without `--force` (`:2718-2721`); `verify_claim` with `template` and `topics` (`:2724-2730`); `mark_forced_rewrite` on `--force` (`:2738`); then the same four write branches as `claim-refresh` (threshold-blocked from `:2747`, analyst failed from `:2804`, title fails template from `:2860`, success from `:2925`).

Help text and `docs/architecture/onboarding.md:5-17` describe the same flags.

## 5. Entity resolution: companies, products, subjects

- Directory to type: `_DIR_ENTITY_TYPE` (`pipeline/orchestrator/entity_resolution.py:16-20`); the reverse map `_ENTITY_TYPE_DIR` (`persistence.py:51-55`); the linter's `ENTITY_DIR_TO_TYPE` (`pipeline/linter/checks.py:46-50`); CLI choices `_ENTITY_TYPE_CHOICES` (`cli.py:33`); site enum (`src/content.config.ts:235`). Five copies of one three-row table.
- `parse_entity_ref(ref, repo_root)` (`entity_resolution.py:104-154`): requires `type_dir/slug`, a known dir, an existing file with `name`; returns `ResolvedEntity` (`:29-41`: ref, name, type, description, aliases, parent_company, website, legal_name, verification_status, founded, search_hints). `verification_status: verified` normalizes to None (`:44-49`).
- `entity_identity_for` (`:63-75`) folds the parent company's names and website into source matching; a product's `parent_company` therefore makes company files load-bearing for independence labels even with no company claims on disk.
- `build_entity_context` (`:78-101`) is the researcher prompt block (description, aliases, parent, website, search hints).
- Claim directory layout (`_claim_dir_for`, `persistence.py:313-327`): companies and products are flat (`research/claims/<slug>/`); every other type nests the type dir (`research/claims/subjects/<slug>/`). A claim with no ref falls back to `slugify(entity_name)`.
- Who creates entity files: `dr onboard` (`_write_entity_file`, `persistence.py:279-311`, never overwrites), `dr claim-draft -` (analyst-inferred entity, `pipeline.py:1785-1791`), and `dr onboard` reject (`_write_draft_entity_file`). `dr entity-enrich` edits in place.
- Subjects today are entity files with the same schema (`research/entities/subjects/{ai-model-producers,generative-ai,us-data-centers}.md`); `docs/UNSCHEDULED.md` "Decouple subject from entity model" holds the open design (lighter record vs `kind: subject`).
- Entity-scoped filters match on the claim's parent directory name only: `list_claims(entity=)` (`pipeline/common/content_loader.py:50-70`), lint `collect_all_paths` (`runner.py:75-78`), `review-queue --filter-entity`, `publish --entity`, `step-audit --entity`. For a subject claim the matching value is the subject slug (`generative-ai`), not `subjects/generative-ai`.

Data on disk (2026-10-14): entities 10 companies, 9 products, 3 subjects; claims 11 files with 11 sidecars (`git ls-files research/claims`: 23 files): 6 product `renewable-energy-hosting` (all `published`, `criteria_slug` set), `subjects/ai-model-producers/ai-producers-existential-score` (published), `subjects/generative-ai/using-generative-ai-harms-cognitive-ability` (published), and three ad hoc drafts with no `criteria_slug`: two under `subjects/generative-ai/` and one under `subjects/us-data-centers/`. The interview note's "10 claims (6 product, 4 subject)" undercounts by one. Company entities carry zero claims.

## 6. Lint checks

Runner (`pipeline/linter/runner.py:85-164`) reads every claim, entity and source file plus every claim sidecar once, builds entity and source id indexes, and runs the checks below in this order (`:133-162`). `LintIssue` is `path, check_id, severity, message, hint` (`pipeline/linter/models.py:4-10`). Reports: text grouped by severity then path (`report.py:18-52`), summary by check id (`:55-88`, `python -m linter` only), JSON array (`:91-93`).

| check_id | Severity | Scope | Rule | Lines in `checks.py` |
|---|---|---|---|---|
| `orphaned-claim` | error | claim | `entity:` ref has no file under `research/entities/` | 53-73 |
| `missing-required-field` | error | claim | `REQUIRED_CLAIM_FIELDS` = title, entity, topics, verdict, confidence, as_of, sources (`:17`) | 76-92 |
| `empty-required-string` | error | claim, entity | empty title / entity description | 232-263 |
| `broken-criteria-slug` | error | claim | `criteria_slug` not in `templates.yaml` | 266-283 |
| `broken-source-ref` | error | claim | `sources:` id has no file | 286-306 |
| `duplicate-entity-slug` | error | entity | same slug twice within one type dir | 309-330 |
| `placeholder-website` | warning | entity | example.com or `/login`-style website | 333-357 |
| `legacy-field-name` | warning | claim | `standard_slug` (pre-rename) | 360-376 |
| `unknown-frontmatter-key` | warning | claim, entity | key not in `CANONICAL_CLAIM_KEYS` (`:30-36`) or `CANONICAL_ENTITY_KEYS` (`:18-29`) | 379-406 |
| `missing-criteria-slug` | info | claim | no `criteria_slug` (any status) | 409-424 |
| `missing-seo-title` | info | claim | published without `seo_title` | 427-444 |
| `stale-recheck` | info | claim | `next_recheck_due` in the past | 447-468 |
| `future-as-of` | info | claim | `as_of` after today | 471-491 |
| `entity-type-dir-mismatch` | warning | entity | `type:` disagrees with the directory | 593-610 |
| `published-without-criterion` | error | claim | published and no `criteria_slug` | 95-123 |
| `published-without-review` | error | claim | published with no sidecar or no `human_review.reviewed_at` | 126-155 |
| `verdict-sidecar-mismatch` | error | claim | published verdict differs from `audit.analyst_verdict` with no matching `verdict_override` | 158-194 |
| `refresh-pending-review` | warning | claim | unpublished claim whose sidecar `refresh.previous.status` is `published` | 197-229 |
| `missing-independence` | warning | source | no `independence` label after `INDEPENDENCE_GRACE_DATE` 2026-05-01 (`:37`) | 494-524 |
| `confidence-cap-violation` | warning | claim | `claimed`/`self-reported` level with medium or high confidence | 527-556 |
| `missing-cap-rationale` | warning | claim | capped level without `cap_rationale` | 559-590 |
| `raw-citation-token`, `numbered-source-reference` | error | claim | `【id】` tokens or "Source N" in body or `NO_CITATION_FIELDS` (`analyst/citations.py`) | 691-723, kinds at `:40-43` |
| `unsafe-markup` | error | claim, entity, source, sidecar URLs | raw HTML tag, non-http(s) link target, non-http(s) URL field | 851-909 |
| `verification-level-pool-mismatch` | warning | claim | level needs more independent sources than the pool has (`INDEPENDENT_SOURCES_REQUIRED`), or `self-reported` with no first-party basis kind | 726-790 |
| `unreferenced-source` | warning | source | cited by no claim and no `src/content/resources/*.md` frontmatter (`page_cited_source_ids`, `:613-635`) | 638-664 |
| `unreferenced-entity` | info | entity | no claim's `entity:` names it | 667-688 |

Exit code: `dr lint` and `python -m linter` exit 1 only on `error` issues, regardless of the severity filter (`cli.py:2611-2613`, `__main__.py:31,46`). `prune.py` deletes every `unreferenced-source` path with `--apply` (`:44-54`).

## 7. Stats

`compute_stats` (`pipeline/orchestrator/stats.py:191-203`) scans claims and sidecars once (`_scan_claims`, `:53-106`) for four aggregates: `wayback_recovery` (entries with `acquisition.stage == ingest` or no `acquisition`, recovered when `recovered_via == archive_org`, `:109-140`), `acquisition_origins` histogram over `ACQUISITION_ORIGINS` brave, tavily, arxiv, s2, openalex, edgar (`:36-43`, "keep in sync with the Zod enum", `src/content.config.ts:60`), `academic_topic_coverage` (`:164-188`), `verification_levels` (`:47`, `:202`). Docstring ties them to `docs/plans/completed/source-pool-expansion-tier1.md` (`cli.py:2630-2637`). Backlog row: recovery counts captures written before RE-AI (Archive snapshot correctness) that were never checked (`docs/UNSCHEDULED.md` "Wayback recovery stats" row).

## 8. Tests covering this subsystem

| File | Tests | Covers |
|---|---|---|
| `pipeline/tests/test_cli.py` | 91 (2678 lines) | provider key checks, claim-draft entity refs, claim-refresh branches and snapshot, claim-promote, entity-enrich, onboard CLI, step-analyze write rules, step-ingest capture rules, step-audit sidecar keep rules, claim-probe no capture, wayback-backfill |
| `pipeline/tests/test_cli_smoke.py` | 1, parametrized over `""`, claim-probe, claim-draft, claim-refresh, claim-promote, reassess, ingest | `--help` exits 0; `cwd` is hard-coded to `/Users/brandon/dev/ai/dangerous-robot/site` (`:19`) |
| `pipeline/tests/test_review_gate.py` | 11 | tty gate, typed slug, nested subject slug, queue `a` with piped stdin |
| `pipeline/tests/test_review_queue.py` | 39 | queue membership, formats, every key, edit buffer, delete to Trash, refresh header |
| `pipeline/tests/test_publish.py` | 25 | flips, notes, selectors, dry run, refresh and override skips, reversal via `dr review` |
| `pipeline/tests/test_onboard.py` | 44 | onboard phases, checkpoints, search hints, subject template gating, forced rewrites |
| `pipeline/tests/test_entity_resolution.py` | 23 | `parse_entity_ref`, lockstep with `CANONICAL_ENTITY_KEYS` and the Zod schema (`:187-216`) |
| `pipeline/tests/test_templates.py` | 44 | loading, filters, rendering, title validation, subject rules |
| `pipeline/tests/test_linter.py` | 95 | every check above, report summary, runner page citations and draft sidecars |
| `pipeline/tests/test_cli_stats.py` | 15 | aggregates and formats |

## 9. Duplication

| What | Locations |
|---|---|
| Bare claim-slug resolution (glob `claims/*/<slug>.md`, uniqueness, exit 1) | `cli.py:2093-2115` (inside `review`); `cli.py:2247-2273` (`_resolve_claim_path`, used by step-analyze, claim-refresh, claim-promote, step-audit, publish) |
| Four claim write branches (threshold-blocked, analyst failed, title fails template, success) | `cli.py:1198-1340` (claim-refresh); `pipeline/orchestrator/pipeline.py:2747-2940` (onboard per template: branches start at `:2747`, `:2804`, `:2860`, `:2925`); single-branch variant `pipeline.py:1785-1853` (claim-draft) |
| Claim-text reconstruction with different fallbacks | `cli.py:674-678` (step-analyze: template else title); `cli.py:1119-1129` (refresh: template, else title, `claim`, file stem); `cli.py:1409` (promote: title or `claim`) |
| templates.yaml readers | `pipeline/common/templates.py:66-83`; `pipeline/linter/runner.py:54-64`; `cli.py:1443-1460`; `src/content.config.ts:257-262` |
| Lint entry points with different flag sets and reports | `cli.py:2574-2613` (`--entity`, `--format`, `--severity`); `pipeline/linter/__main__.py:12-46` (`--detail`, `--output`, `--json`, `--min-severity`, `--root` defaulting to the parent of cwd) |
| Sidecar `human_review` read-modify-write | `pipeline/orchestrator/review.py:270-282` (approve); `cli.py:2498-2504` (publish, bypasses `approve_claim`) |
| Verdict-override comparison | `review.py:162-187`; `pipeline/linter/checks.py:158-194` |
| Entity dir-to-type tables | `entity_resolution.py:16-20`; `persistence.py:51-55`; `checks.py:46-50`; `cli.py:33-38`; `src/content.config.ts:235` |
| Verdict value lists | `review_queue.py:143-146` (`_ALLOWED_VERDICTS`); `pipeline/common/models.py:76-83` (`Verdict`); `VERDICT_ORDER` in `src/content.config.ts` |
| Shared six research flags and the `overrides` dict | `cli.py:881-886`, `935-942`, `1035-1041`, `1768-1776`; `cli.py:899`, `977`, `1136`, `1850` |
| Self-reported basis rule | `checks.py:726-790`; `persistence.py` `fit_verdict_to_written_pool` (`docs/UNSCHEDULED.md` "Self-reported basis rule written twice") |
| Report header assembly | `pipeline/linter/report.py:18-33` and `:55-69` |
| Published-only filter on the site | `data.status === 'published'` in 9 `src/pages/**` files (outside this subsystem, listed for the URL contract) |

## 10. Hazards (what a rewrite could silently lose or break)

| Hazard | Location |
|---|---|
| The person gate: tty check plus typed slug before any write, and the agent rule never to run or fake it | `review.py:43-63`; `AGENTS.md:187`; tests `test_review_gate.py` |
| Approval refuses claims without `criteria_slug`; lint errors on published claims without one; publish skips them. Every ad hoc claim on disk (3 drafts) is therefore unpublishable until a template exists | `review.py:128-134`; `checks.py:95-123`; `cli.py:2388-2391` |
| Write order correction, sidecar, status; the sidecar is the commit point and a rerun completes a half-done flip | `review.py:268-291` |
| Changed verdict after a refresh needs a reader-facing correction; dedupe on `previous_verdict` | `review.py:150-160`, `:190-206`, `:234-256` |
| `refresh` block carries forward across repeated refreshes and is removed only by approve, archive, or publish | `persistence.py:793-823`; `review.py:276-278` |
| `verdict_override` is written only at approval, kept by non-reset sidecar writes, and read by lint and publish | `review.py:162-171`, `:275`; `persistence.py:973-990`; `checks.py:158-194`; `cli.py:2408-2411` |
| Forced rewrites return a non-draft to draft and reset sign-off (`mark_forced_rewrite`); `step-analyze --write --force` also nulls `audit` | `persistence.py:838-896`; `cli.py:767-773` |
| Operator-owned claim fields survive a pipeline rewrite: `tags`, `corrections` always; `seo_title`, `takeaway`, `cap_rationale` by `analyst_record` rules | `persistence.py:526-608`, `:623-686` |
| `dr publish` records no reviewer; the site renders such claims as unreviewed; an unmapped non-null reviewer breaks the build | `cli.py:2498-2504`; `src/lib/reviewers.ts:35-55` |
| Bare slug resolution and `--entity` filters are one directory deep, so subject claims need the full `subjects/<subject>/<slug>` ref and the bare subject slug as entity filter | `cli.py:2093-2115`, `:2247-2273`; `content_loader.py:50-70`; `runner.py:75-78` |
| Claim path layout: flat for companies and products, nested for subjects; site URLs follow it | `persistence.py:313-327` |
| `templates.yaml` `tags` and `inactive_templates` are read by nothing; `claim-promote` appends a text fragment and never writes `tags` or `vocabulary` | `templates.py:66-83`; `cli.py:1461-1489`; `src/content.config.ts:264-281` |
| Vocabulary templates: claim text sent to the researcher and analyst is the `one of (...)` hint; the Evaluator grades the title; a title outside the allowed transforms blocks the claim | `templates.py:131-138`, `:184-204`; `cli.py:1263-1291` |
| Subject templates are gated by `subjects:`; a subject with none onboards with zero claims | `templates.py:86-107`; `pipeline.py:2548-2583` |
| `verification_status` must be a schema enum value or the onboard rejects | `pipeline.py:2436-2455`; `src/content.config.ts:240-244` |
| Lint is a commit and CI gate on `error` severity only; three places (local hook, CI, `inv audit`) call two different entry points | `.git/hooks/pre-commit:14`; `.github/workflows/ci.yml:80-108`; `tasks.py:195-220` |
| Adding a frontmatter key needs `CANONICAL_CLAIM_KEYS`/`CANONICAL_ENTITY_KEYS`, the Zod schema, and the lockstep tests | `checks.py:18-36`; `src/content.config.ts`; `test_entity_resolution.py:187-216` |
| `unreferenced-source` drives deletion by `prune.py`; editorial page citations count only from `src/content/resources/*.md` frontmatter | `checks.py:613-664`; `prune.py:44-54` |
| `stale-recheck` is the only recheck signal and nothing in `pipeline/` writes `next_recheck_due` or `recheck_cadence_days` (grep: only `checks.py:34`, `:455`); the site defaults the cadence to 60 days | `checks.py:447-468`; `src/content.config.ts:216-217`; `docs/architecture/open-issues.md:36-50` |
| `step-audit` calls the auditor outside the concurrency semaphore and null retry | `cli.py:1632-1633`; `docs/UNSCHEDULED.md` "Docs versus code" row |
| `step-audit --write` must keep `models_used` of agents it did not run, `level_clamp`, `acquisition` and `archive` entries | `cli.py:1662-1713`; `persistence.py:1003-1009` (roadmap RE-AK) |
| `claim-draft --force` writes no `criteria_slug`, so it strips one from a template-backed claim at the same path | `pipeline.py:1805-1820`; `docs/UNSCHEDULED.md` "`dr claim-draft --force` drops `criteria_slug`" |
| `claim-draft` demands `BRAVE_WEB_SEARCH_API_KEY` while `VerifyConfig.research_origins` defaults to tavily and arxiv | `cli.py:951-953`; `pipeline.py:293` |
| Hidden deprecated aliases `reassess` and `ingest` are documented and smoke-tested | `cli.py:1726-1761`; `AGENTS.md:181`; `test_cli_smoke.py:11` |
| `stats` origin list must match the site enum | `stats.py:35-43`; `src/content.config.ts:60` |
| `entity-enrich` refuses to overwrite a non-empty entity body without `--force` and refuses with no fetched page (RE-AJ) | `cli.py:2010-2020`; `pipeline.py:2164` |
| Docs that name commands and will drift: `AGENTS.md:153-157` table ("evaluate, ingest" are not commands), `AGENTS.md:177-187` list (no `review-queue`, `publish`, `stats`, `entity-enrich`), `pipeline/README.md:26-30` (`consistency/` does not exist), `docs/architecture/glossary.md:52-66` cross-walk, `docs/runbook.md:73-91`, `docs/architecture/research-flow.md:174-242`, `docs/architecture/onboarding.md:5-17` | as listed |
| `test_cli_smoke.py` hard-codes Brandon's checkout path | `pipeline/tests/test_cli_smoke.py:19` |

## 11. Roadmap and backlog items that touch this subsystem

- Beta.7 fixes that must not be lost (`docs/v1.0.0-roadmap.md:233-324`): RE-AD (Evaluator grades the claim: `step-audit` grades the file title, skips blocked claims, live `step-audit` runs shelved), RE-AG (criterion notes reach analyst and Evaluator; `_claim_template` shared by step-analyze and step-audit, `cli.py:2229-2244`), RE-AH (refresh keeps `seo_title` and `cap_rationale`), RE-AI (`wayback-backfill` capture checks), RE-AJ (`entity-enrich` refuses to guess), RE-AK (step-analyze returns to draft and clears audit; step-audit keeps models; forced rewrites write the refresh trail), RE-U (publish refuses unreviewed overrides, `:468-476`).
- Beta.8 to absorb: RE-AC (Claim restatement) plan `docs/plans/claim-restate.md` proposes `dr claim-restate CLAIM_REF [--write] [--accept N] [--format] [--max-candidates]` (`:142-173`), a sidecar `restatement` block (`:367-420`), `--accept` reusing the `claim-promote` writer (D13, `:45`), and a `restates` sidecar key (D17, `:49`). RE-AL (Source pool and coverage quality, roadmap `:326-338`) is pipeline-side; its "Template notes serve readers and the analyst" line decides a separate grading-rule field in `templates.yaml` (`:106`).
- Backlog rows naming this subsystem (`docs/UNSCHEDULED.md`): "Docs versus code" (step-audit semaphore, `_COMMAND_GROUPS`), "Claim-text reconstruction duplicated", "`dr claim-draft --force` drops `criteria_slug`", "`dr step-analyze` leaves the old analyst model in the sidecar", "Verdict hand-edited after `dr step-analyze` goes unrecorded until re-audit", "`dr wayback-backfill` fetches every live page", "`--recheck` removes a bad link before another capture is found", "Onboard report omits the enricher skip", "Wayback recovery stats count captures never checked", "Self-reported basis rule written twice", "Prompt-capture test helper duplicated", RF13/RF16/RF24 in "claim-refresh review findings", "Operator workflow and data lifecycle" (queue + batch + error-file flow, not v1), "Decouple subject from entity model".
- Interview intent that lands here (`handoff/2026-10-13-pipeline-improvement-interview.md`): Q2 publish decision stays Brandon's; Q6 review packet (verdict chain, quotes beside archived passages, independence at a glance, what was searched and rejected) replaces today's queue header (`review_queue.py:176-208`); Q7 `dr recheck --due`; Q8 (D) about five commands: draft, recheck, review, findings, lint; Q8 (A) templates become stored sentences run through claim-draft; Q8 (C) companies out.

## 12. Open questions for the plan

1. SP6 (one claim path, templates as sentences): `criteria_slug` is the publish gate in three places (`review.py:128-134`, `checks.py:95-123`, `cli.py:2388-2391`) and the site's criteria pages key on it. What identifies a sentence-based claim's criterion, and does every ad hoc claim get one automatically?
2. SP5 (`recheck --due`): no code writes `next_recheck_due`; the site defaults `recheck_cadence_days` to 60. Is "due" computed from `as_of` plus cadence, or does the new loop write the date?
3. SP7 (fold to about five commands): `dr publish` writes no reviewer, which contradicts the Q6 premise that a person signs off on every claim. Delete it, or keep it as an explicit "unreviewed" path? Same question for `step-research`, `step-ingest`, `step-analyze`, `step-audit`, `wayback-backfill`, `entity-enrich`, `claim-promote`, `stats`, `review-queue`.
4. SP8 (companies out): the 10 company files carry zero claims, but product `parent_company` refs feed `entity_identity_for` (`entity_resolution.py:63-75`) for first-party matching. Do company files stay as parent records, or does the product file absorb the parent's names and website?
5. Subject claim ids: should the new CLI accept one id form (`subjects/<subject>/<slug>`) everywhere and drop the one-directory-deep bare-slug glob and `--entity` matching?
6. `claim-draft`'s `BRAVE_WEB_SEARCH_API_KEY` check versus the tavily/arxiv default: stale requirement or still needed?
7. Lint wiring: the pre-commit hook is a local uncommitted file in `.git/hooks`; CI calls `dr lint` from `pipeline/`; `inv audit` calls `python -m linter`. Which one survives SP7, and should the hook be committed?
8. `templates.yaml` `tags` on two templates: a leftover, or intended to seed claim `tags` at onboard?
9. Q6 review packet item 2 (quotes beside archived passages with a pass/fail) has no data today: dropped quotes are only logged (`docs/UNSCHEDULED.md` "Dropped key quotes are recorded only in the log"). Which spike adds that record to the sidecar?
10. Claim count: 11 claims on disk, not the interview's 10. Which of the three ad hoc drafts are candidates for deletion under the Q4 flaw rule?
