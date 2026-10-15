# Pipeline map: the tests (`pipeline/tests/`)

Phase 1 (Challenge) reader output for the research pipeline rebuild. Facts carry `file:line`; paths are relative to the repo root unless absolute. "Not found" means the fact is not on disk.

Scope: 55 test files, `conftest.py`, `fixtures/`. Totals from `wc -l`: 23,916 lines across `pipeline/tests/*.py` (the interview note's "tests ~27k" likely counted fixtures or an earlier state; not checked).

## 1. How the tests run

| Fact | Where |
|---|---|
| Runner config: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, one marker `acceptance` ("live end-to-end tests that hit real APIs (requires API keys in .env)") | `pipeline/pyproject.toml:33-38` |
| Dev deps: `pytest>=8.0`, `pytest-asyncio>=0.24`, `respx>=0.22` | `pipeline/pyproject.toml:18-22` |
| Root `pyproject.toml` repeats the `acceptance` marker (uv workspace root) | `pyproject.toml:26-29` |
| `inv test` = `uv run python -m pytest -m 'not acceptance'` in `pipeline/`; `inv test.all` runs everything; `inv test.acceptance` runs `-m acceptance` with optional `-k` and `--log-cli-level=INFO` | `tasks.py:140-191` |
| `inv check` (type-check, site tests, build, lint, then `_test_unit`) is the pre-push gate and is what the git pre-commit hook runs after `dr lint` | `tasks.py:43-51`; `.git/hooks/pre-commit:14-17`; `docs/architecture/ci-deploy.md:78` |
| CI (`.github/workflows/ci.yml`) runs `uv run dr lint --format json --severity error` in `pipeline/`; it does not run pytest. The `check` job runs `npm run check:types`, `check:watch`, `check:citations` | `.github/workflows/ci.yml:27-32, 82-87` |
| README says `uv run pytest tests/ -v` | `pipeline/README.md:20-23` |
| AGENTS.md lists `inv test` and `inv test.all` | `AGENTS.md:195-196` |
| Unit run on 2026-10-14 (this reader, `-m 'not acceptance'`): `1440 passed, 5 skipped, 4 deselected in 14.19s`, exit 0 | scratchpad `pytest-unit.txt` (not in repo) |
| Slowest tests are the `uv run dr ... --help` subprocess cases (`test_cli_smoke.py`, ~0.3 s each) and the production-source scan in `test_step_error_vocab.py` (0.64 s) | same run, `--durations=15` |

### conftest.py (161 lines)

| Fixture | What it does | Where |
|---|---|---|
| `_reset_run_id_var` (autouse) | clears `common.logging_setup.run_id_var` after every test, because `dr` via `CliRunner` binds it | `conftest.py:15-24` |
| `repo_root` (session) | `resolve_repo_root()` of the real checkout; used by tests that read real `research/` data | `conftest.py:26-29` |
| `_isolate_cli_logging` (autouse, session) | monkeypatches `orchestrator.cli._safe_repo_root` to return `None` so `CliRunner` tests never write `logs/` | `conftest.py:32-48` |
| `sample_frontmatter_text` | a 3-field claim frontmatter string | `conftest.py:51-61` |
| `stub_ingest_model` / `stub_ingest_model_calling_wayback` | a `FunctionModel` that parses the URL out of the prompt text (`prompt.split("URL: ", 1)`), calls `web_fetch` (and optionally `wayback_check`) and returns a fixed `SourceFile`; also patches `ingestor_agent.override` to a no-op so the CLI's own override does not replace it | `conftest.py:64-121` |
| `human_at_terminal` | patches `orchestrator.review._stdin_is_tty` and `_prompt_slug` so sign-off tests pass the "person at a terminal" gate | `conftest.py:124-137` |
| `mock_capture_replay` | a respx HEAD route for archive.org `id_` replay checks (every recorded capture is HEAD-checked) | `conftest.py:140-161` |

### Mocking styles in use

| Style | Count of files | Notes |
|---|---|---|
| PydanticAI `TestModel` / `FunctionModel` with `agent.override(model=...)` | 26 files | scripted structured outputs; `test_onboard.py` has 82 `override(` calls |
| `respx` HTTP mocks | 15 files | `test_tools.py` 134 uses; `test_ingest_fetch_failure.py` 49; `test_cli.py` 38 |
| `monkeypatch.setattr` on private orchestrator seams | most orchestration tests | `"orchestrator.pipeline._research"` 37 times, `"common.content_loader.resolve_repo_root"` 23, `"orchestrator.pipeline._probe_collision_suggestions"` 17, `"orchestrator.pipeline._ingest_urls"` 13, `"orchestrator.pipeline._audit_claim"` 9, `"orchestrator.pipeline.verify_claim"` 8, `"orchestrator.pipeline._analyse_claim"` 8 (grep over `pipeline/tests/*.py`) |
| `patch("orchestrator.pipeline._ingest_one")` / `patch("researcher.decomposed.execute_searches")` | 12 each | |
| `click.testing.CliRunner().invoke(main, [...])` | 7 files (`test_cli.py` 93 invocations, `test_publish.py` 46, `test_audit_trail.py` 38, `test_review_queue.py` 23, `test_cli_stats.py` 12, `test_review_gate.py` 6, `test_logging_setup.py` 2) | `--model test` selects PydanticAI's TestModel through `resolve_model` |
| `subprocess` of `uv run dr` | `test_cli_smoke.py` only | cwd hardcoded to `/Users/brandon/dev/ai/dangerous-robot/site` (`test_cli_smoke.py:20`) |
| Live model calls | `test_acceptance.py` only (4 tests, marker `acceptance`) | skip unless `ANTHROPIC_API_KEY` (3 stage tests) or that plus `BRAVE_WEB_SEARCH_API_KEY` (smoke) (`test_acceptance.py:32-39`) |

### Fixtures directory

| File | Used by | Notes |
|---|---|---|
| `fixtures/sample_page.html` | `test_tools.py:93` (`TestExtractPageData`) | |
| `fixtures/arxiv_html_corporate.html`, `arxiv_html_academic.html` | `test_ingest_fetch_failure.py:505-507` (RE-AE arXiv affiliation) | added in `3d48707` |
| `fixtures/sample_source.md` | no test references it (grep over `pipeline/`) | orphan |
| `fixtures/known_good/{clearly-unverified,well-supported-true}.md`, `fixtures/known_bad/{narrative-says-true-verdict-says-false,weak-evidence-high-confidence}.md` | no test references them (grep over `pipeline/`) | orphans from 2026-04-19; claim frontmatter uses an old shape (`entity: companies/betaco`, `topics:`, no `status`/`criteria_slug`) |

### Tests that read the real checkout, not `tmp_path`

| Test | Reads | Where |
|---|---|---|
| `TestLoadTemplates.test_loads_active_templates_from_yaml` asserts `len(templates) == 16`; `test_first_template_matches_yaml_order` pins slug `publishes-sustainability-report`; `test_load_templates_excludes_inactive` pins `data-jurisdiction` inactive | real `research/templates.yaml` | `test_templates.py:23-43` |
| `TestResponsibleAIPageCriteria` pins `financial-transparency`, `open-source-models-only` active and the text "PRODUCT uses only open-weight models" | real `research/templates.yaml` | `test_templates.py:46-60` |
| `TestListClaims` lists real `research/claims/`, filters entity `anthropic` and topics | real `research/claims/` | `test_content_loader.py:86-117` |
| 5 tests skipped with reason "multi-topic rename ... see docs/plans/multi-topic.md"; that file now lives at `docs/plans/completed/multi-topic.md` | | `test_content_loader.py:58,87,93,103,108` |
| `_setup_tmp_repo` copies the real `research/templates.yaml` into `tmp_path` (so onboard tests track whatever templates exist) | real `research/templates.yaml` | `test_onboard.py:140-147`; same again in `test_cli.py:1126-1132` (`TestOnboardCLIPhaseB._setup_repo`) and `test_cli.py:1128-1129` |
| `test_founded_present_in_zod_schema`, `test_verification_status_enum_lockstep` read `src/content.config.ts` | site Zod schema | `test_entity_resolution.py:199-226` |
| `test_no_undocumented_error_type_literals_in_production` scans every production `.py` under `pipeline/` for `error_type=` literals and checks them against the `StepError` docstring | pipeline source tree | `test_step_error_vocab.py:91-190` |
| `TestAgentInstructionsWiring` checks each agent's system prompt equals `load_instructions(agent_dir, common("verdict-scale.md"))` | the agents' `instructions.md` | `test_instructions.py:38-59` |
| `test_dr_cli_help` runs `uv run dr <cmd> --help` with cwd hardcoded to Brandon's path, for `""`, `claim-probe`, `claim-draft`, `claim-refresh`, `claim-promote`, `reassess`, `ingest` | the installed `dr` | `test_cli_smoke.py:10-23`. `reassess` and `ingest` are `hidden=True` commands (`pipeline/orchestrator/cli.py:1726,1746`) that `dr --help` does not list |

## 2. File-by-file map

Columns: lines (`wc -l`), tests (count of `def test_`), module under test, what it pins, contract kind. "Public" = file formats, CLI output, keep rules, lint rules, a documented decision rule. "Internal" = private helpers, prompt wording, orchestration seams reached by patching. "Mixed" = both.

| File | Lines | Tests | Module / behavior | Kind |
|---|---|---|---|---|
| `test_acceptance.py` | 276 | 4 | live: scorer split (`url_scorer_agent`), planner shape, analyst false verdict, `verify_claim` end to end on a false Anthropic claim | Public (behavior), live only |
| `test_agent.py` | 138 | 11 | `IngestorDeps` / `ingestor_agent` round trip with `TestModel`; `build_analyst_prompt` sections (`TestBuildAnalystPrompt`, :79) | Internal (prompt) |
| `test_analyst.py` | 431 | 35 | `analyst.agent`: prompt sections, `seo_title`/`takeaway` field validation (:172, :236), narrative list normalisation (:274), criterion notes in prompt (:321, RE-AG), instruction wording anchors (:347, RE-AG), uncovered sub-question marker (:383, RE-AF), `cited_sources` rule (:416, RE-AF) | Internal (prompt text) + Public (field validators) |
| `test_archive_after_ingest.py` | 311 | 10 | `research_claim` / `gather_light_research` archive lookup after ingest: `archived_url` set, `acquisition` outcomes, `--skip-wayback`, stale-capture refresh (:294, RE-AI) | Mixed (sidecar `acquisition` record is public; reached by stubbing `_research`) |
| `test_arxiv_search.py` | 153 | 5 | `researcher.tools.arxiv.search_arxiv` Atom parsing, empty feed, timeout propagation | Internal |
| `test_audit_trail.py` | 2300 | 116 | `orchestrator.persistence`: `_build_sources_consulted` (:106), `_write_audit_sidecar` (:192), refresh snapshot (:534), acquisition/tool outcomes (:650), `_write_claim_file` keep rules (:936, 38 tests; RE-AH, RE-AK), `dr review` CLI (:1435), promotion (:1566), `approve_claim` (:1851), approving refreshed claims and corrections (:1988), verdict override record (:2164), `set_claim_status` blocked (:2226) | Public (claim file + sidecar formats, operator keep rules, review trail) |
| `test_auditor_agent.py` | 319 | 21 | `auditor.agent`: prompt round trip, bundle never leaks the analyst verdict (:91), Evaluator grades the claim statement (:158, RE-AD), `_audit_claim` sends the claim (:219, RE-AD), criterion notes reach the Evaluator (:259, RE-AG) | Internal (prompt text and order) |
| `test_auditor_models.py` | 109 | 7 | `ClaimBundle`, `IndependentAssessment`, `ComparisonResult` field validation | Public (sidecar `audit` shape) |
| `test_backfill_analyst_record.py` | 212 | 10 | `scripts/backfill_analyst_record.py`: picks the last pipeline-written version from git, dry run writes nothing (RE-AK one-shot backfill, done `c0fe380`) | Public (script), one-shot |
| `test_blocklist.py` | 137 | 13 | `common.blocklist.filter_urls`, `load_blocklist` (`research/blocklist.yaml` shape) | Public |
| `test_brave_search.py` | 131 | 7 | `researcher.agent.search_brave` 429 retry, quoted-query fallback | Internal |
| `test_canonical_url.py` | 310 | 40 | `common.canonical_url`: `canonicalize`, arXiv key, `same_page_any_scheme` (:276, RE-AI) | Public (dedup key rule) |
| `test_checkpoints.py` | 125 | 10 | `orchestrator.checkpoints`: auto-approve handler answers, CLI prompt wording for verification status | Internal (interactive prompts; the interview says normal runs ask no questions) |
| `test_citations.py` | 256 | 23 | `analyst.citations.clean_citations` (bracket tokens, "Source N"), short-field citation rejection, `_analyse_claim` returns a clean narrative (:163), `cited_source_ids` title matching (:227-253, RE-AF) | Mixed |
| `test_classify_source_type.py` | 170 | 40 | `common.source_classification.classify_source_type` (primary/secondary/tertiary by publisher and kind), corporate-lab publisher (:110, RE-AE), `profile_url_names_entity` (:150, RE-AE) | Public (source labels) |
| `test_cli_smoke.py` | 23 | 1×7 | `uv run dr <cmd> --help` exits 0 | Public (command names), hardcoded path |
| `test_cli_stats.py` | 419 | 15 | `orchestrator.stats.compute_stats` and `dr stats --format text/json` over a tmp repo | Public (CLI output) |
| `test_cli.py` | 2678 | 91 | `orchestrator.cli`: `dr ingest` (:21), required env per model (:44), provider key check (:96), per-agent model options (:121), `claim-probe` options (:130), `claim-draft` (:138), `claim-refresh` (:256, with `verify_claim` stubbed at :559), refresh keeps published state (:612), removed `verify`/`verify-claim` (:724), `claim-promote` (:746), `entity-enrich` (:903; RE-AJ at :1098, :1112), onboard Phase B CLI (:1123), `step-analyze` criterion notes (:1681, RE-AG), refresh flag reason (:1753), `step-ingest` archive flags (:1813), `wayback-backfill` (:2097) and `--recheck` (:2192, RE-AI), refresh lists cited sources (:2618, RE-AF); top-level `step-analyze --write` tests (:1397-1649, RE-AE/RE-AK), `step-audit --write` keep tests (:1949-2065, RE-AK), `claim-probe` never captures (:2076), `step-audit` sends title/notes and skips blocked (:2435-2571, RE-AD/RE-AG) | Mixed: command names, flags and exit codes are public; most tests stub `verify_claim` or `_research` and read what the command wrote |
| `test_compare.py` | 217 | 22 | `auditor.compare.compare`: exact/adjacent/major/opposite disagreement, unverified, evidence gaps, `needs_review_reasons` | Public (the Analyst/Evaluator disagreement rule the interview's Q3 tie-breaker replaces) |
| `test_content_loader.py` | 117 | 14 (5 skipped) | `common.content_loader` load/list over the real `research/` | Public (file layout) |
| `test_entity_enricher.py` | 144 | 7 | `researcher.entity_enricher` prompt per entity type, round trip | Internal |
| `test_entity_independence.py` | 915 | 52 | `_apply_entity_match` (entity host/publisher matching :53-154, off-entity rule :406-583, RE-AE), `fit_verdict_to_written_pool` (:619-694, :842-912; RE-AE, RE-AH, RE-AK), `research_claim` writes overrides and fitted level (:376, :703), forced rewrite keeps the refresh trail (:726, RE-AK) | Mixed: level-fit rule is public (matches `src/lib/sourceQuality.ts`, :873); `_apply_entity_match` is private |
| `test_entity_resolution.py` | 226 | 23 | `parse_entity_ref` forms; lockstep guards against `linter.checks.CANONICAL_ENTITY_KEYS` and `src/content.config.ts` | Public (entity ref grammar, entity frontmatter keys) |
| `test_entity_verifier.py` | 123 | 6 | `researcher.entity_verifier` prompt per type, round trip | Internal |
| `test_frontmatter.py` | 124 | 15 | `common.frontmatter` parse/strip/serialize (enum, date, quoting) | Public (file format) |
| `test_ingest_fetch_failure.py` | 592 | 24 | `IngestorDeps` fetch record, `_ingest_one` rejects invented sources (`fetch_failed`, `invalid_source`), model-written `archived_url` dropped, key-quote checks end to end (:322-414, RE-AH/RE-AK), `dr step-ingest` writes nothing on failure (:457-482), arXiv affiliation agreement (:544-576, RE-AE) | Mixed |
| `test_ingest_urls.py` | 245 | 12 | `_ingest_urls` stop-at-target and failure handling (:44-113); `_order_by_coverage` and `_ingest_claim_sources` thin-sub-question-first (:148-229, RE-AF) | Internal |
| `test_ingest_validation.py` | 271 | 26 | `ingestor.validation.drop_unfound_quotes`: paraphrase dropped, wrapping marks and attribution tail, ellipsis rules, stored bare (RE-AH, RE-AK); `test_instructions_ask_for_bare_quotes` (:264) pins instruction text | Public (quote keep rule) + 1 Internal |
| `test_ingestor_models.py` | 132 | 15 | `SourceFrontmatter` / `SourceFile` validation | Public (source file schema) |
| `test_instructions.py` | 59 | 8 | `common.instructions.load_instructions`; agents' system prompts equal their `instructions.md` | Internal (loader convention) |
| `test_linter.py` | 802 | 95 | `linter.checks` (25 classes: orphaned claims, required fields, published criterion, sign-off, criteria slug, source refs, duplicate slugs, placeholder website, legacy field names, seo_title, stale recheck, future as_of, type/dir mismatch, unknown keys, unreferenced sources/entities, raw citation tokens, verification-level pool (:539, RE-AE), verdict/sidecar mismatch (:659), refresh pending review (:693), unsafe markup (:736)); `format_summary_report`; two runner tests (:425, :718) | Public (content rules `dr lint` enforces; CI runs these on every push) |
| `test_logging_setup.py` | 284 | 15 | `common.logging_setup`: handlers, JSON formatter with `run_id`, per-task isolation, verbose console, UTC timestamps, `dr` emits a run id | Public (log file format `logs/info.log`, `logs/debug.log`) |
| `test_models.py` | 232 | 28 | `common.models` enums; `resolve_model` builds `OpenAIModel` for `infomaniak:` specs, fallback spec, reasoning strip | Public (enum values, `DR_MODEL` spec grammar) |
| `test_onboard.py` | 1838 | 44 | `onboard_entity`: happy path, no double ingest, keeps sources on disk, seed URL, error attribution, rejection, vocabulary resolution (:149-557); `_probe_collision_suggestions` (:563); Phase B verifier (:686); search hints merge/persist (:1094-1214); entity file on disk (:1215); subject fan-out (:1458); `gather_light_research` errors (:1540, RE-AJ); forced rewrites keep the refresh trail (:1691, RE-AK); criterion notes reach analyst and auditor (RE-AG) | Internal (patches `_research`, `_probe_collision_suggestions`, agent overrides); the written entity/claim files it asserts on are public |
| `test_orchestrator.py` | 1434 | 64 | `VerificationResult` shape (:30-119), `_apply_blocklist_cap` (:120) and the spared entity post (:248, RE-AE), `VerifyConfig` models/origins/timeouts (:293-395), `below_threshold` and blocked writes (:396, 17 tests), `verify_claim`/`research_claim` with a resolved entity (:643, :724), rejected review reason (:894), `_graded_statement` (:955, RE-AD), uncovered sub-question warning (:1199, RE-AF), cited-source filter (:1243, RE-AF), title-blocked claim keeps every source (:1384, RE-AF), uncited sources not persisted (:1414, RE-AF) | Internal (private seams patched: `_research`, `_ingest_urls`, `_analyse_claim`, `_audit_claim`) |
| `test_prefetch.py` | 146 | 4 | `IngestorDeps.prefetched_bodies` short-circuits `web_fetch`; `_ingest_urls` threads bodies | Internal |
| `test_publish.py` | 668 | 25 | `dr publish`: single/bulk/selectors/idempotency/confirmation; refreshed claims need review (:555); edited verdicts refused without `dr review --approve` (:624, RE-U) | Public (CLI behavior and sidecar `human_review` marker) |
| `test_rerun_v1_claims.py` | 79 | 1 | `scripts/rerun_v1_claims.py` never carries a sign-off onto refreshed content | Public (script), likely one-shot |
| `test_research_integration.py` | 205 | 2 | `research_claim` end to end with all four agents on `TestModel`: writes claim, sources, sidecar; names the real flag reason | Mixed (the only mocked whole-loop test that stubs no private seam except `execute_searches`) |
| `test_research_planner.py` | 165 | 1 | `research_planner_agent` output shape over a curated corpus | Internal |
| `test_researcher_decomposed.py` | 1339 | 52 | `researcher.decomposed`: planner/scorer shapes, dedup, step sequencing, semaphore, scorer drops all, parent/legal name/founded in prompts, entity exclude and spared profile URL (:1185-1224, RE-AE), kept-URL ordering (:1258-1335, RE-AF), backend dispatch (:520), research origins (:724), arXiv dispatch (:770), acquisition trace (:680) | Internal (prompt content and private ordering); the sidecar `research` trace shape is public |
| `test_review_gate.py` | 209 | 11 | `dr review` and `review-queue a` refuse without a tty and a typed slug | Public (sign-off rule; AGENTS.md names it) |
| `test_review_queue.py` | 820 | 39 | `find_publication_queue` membership; `dr review-queue --format`; interactive keys a/s/p/q/e/d; edit round trip; `_delete_files`; refreshed header | Public (CLI behavior) |
| `test_scorer.py` | 109 | 4 | `url_scorer_agent` keeps per-sub-question `addresses`; `build_scorer_prompt` blocks | Internal |
| `test_source_bare_links.py` | 137 | 4 | source bodies wrap bare emails/URLs (MD034) in both writers | Public (source file content rule) |
| `test_source_id_collision.py` | 241 | 11 | `resolve_source_slugs`: host-prefixed ids, same canonical URL reuses id, `_write_source_files` never returns another URL's id, `step-ingest --force` scope | Public (source id rule) |
| `test_source_url_dedup.py` | 705 | 29 | `build_source_url_index`, `load_source_dict`, `_apply_url_dedup`, target cap, cached sources surfaced, `_persist_sources`, `slug_from_url`, redirect to a stored source, same-batch redirects, `_invert_addresses` | Mixed |
| `test_step_error_vocab.py` | 234 | 4 | `StepError.error_type` literals in production match the docstring list | Public (error vocabulary; scans any new package under `pipeline/`) |
| `test_tavily_search.py` | 221 | 10 | `researcher.tools.tavily.search_tavily` mapping, auth, 429 | Internal |
| `test_templates.py` | 457 | 44 | `common.templates`: load, `render_claim_text`, `render_blocked_title`, `validate_analyst_title` (:229, 12 tests), frozen record, subject template schema and fan-out | Public (`research/templates.yaml` schema and the title rule) |
| `test_terminal_fetch.py` | 293 | 13 | `web_fetch` terminal codes 401/402/403/451 fail fast, 429 retry once, no wayback on terminal, agent retry budget, no archive lookup after a failed ingest | Internal (fetch policy) |
| `test_throttle.py` | 300 | 21 | `common.throttle.Throttle` per-host token bucket | Internal |
| `test_tools.py` | 1174 | 73 | `extract_page_data` (:31), TimeGate lookup and rate limit (:109, :225), `find_or_save_archive` (:269), archive budgets (:311), Save Page Now (:336), fetch timeouts (:448), `wayback_check` tool (:481), acquisition merge and drain (:571, :606), capture lookup / `check_capture` / freshness / latest-OK capture / replay without memento (:770-1174, RE-AI) | Mixed: the "a capture counts only when it replays 200 for the same page" rule is public (AGENTS.md:185); the rest is wayback internals |

## 3. Tests that pin the beta.7 fixes RE-AD to RE-AK

Derived from `git show --stat` and the added `def test_`/`class Test` lines of the commits the roadmap names (`docs/v1.0.0-roadmap.md:233-325`). A rebuild that absorbs the loop must re-home each row or lose the fix silently.

| Fix | Commits | Tests (file:line) |
|---|---|---|
| RE-AD Evaluator grades the claim | `98fc21b`, `3c212e4`, `1e628f5` | `test_auditor_agent.py:158` `TestEvaluatorGradesTheClaim` (instruction text + prompt order), `:219` `TestAuditClaimSendsTheClaim`; `test_orchestrator.py:955` `TestAuditorGradedStatement` (6 tests: vocabulary claim grades the resolved title, failing title skips the audit, free text with "one of (" keeps the operator's text, `verify_claim` skips auditor and review on a failing title, `research_claim` grades the title it writes); `test_cli.py:2435` `test_step_audit_sends_claim_title`, `:2571` `test_step_audit_skips_blocked_claims` |
| RE-AE Source pool independence | `3d48707`, `e1074d8`, `c5f2183`, `df6d6f1`, `bf72bcb`, `1b2c517` | `test_entity_independence.py:406-583` (engages-entity, off-entity unknown, override beats analyst), `:619-694, :786-912` (`fit_verdict_to_written_pool` level rules, self-reported needs a first-party basis, stale rationale replaced); `test_classify_source_type.py:110` `TestCorporateLabPublisher`, `:150` `TestProfileUrlNamesEntity`; `test_ingest_fetch_failure.py:544,576` arXiv abs/html agreement (fixtures `arxiv_html_*.html`); `test_researcher_decomposed.py:1185-1224` entity exclude spares the profile URL and the parent's; `test_orchestrator.py:248` `TestBlocklistSparesEntityProfilePost`; `test_linter.py:539` `TestVerificationLevelPool` (`test_claimed_not_checked`, `test_self_reported_needs_a_first_party_report`, `test_repeated_ref_counts_each_time_like_the_site`); `test_cli.py:1397` `test_step_analyze_write_keeps_the_entity_match_override` |
| RE-AF Sub-question coverage and the cited source list | `e8341c4`, `b8fda79`, `487b758`, `26ab88b` | `test_ingest_urls.py:148-229` (`_order_by_coverage`, thin sub-question first, second thin URL on failure); `test_orchestrator.py:1199` `TestUncoveredSubQuestionWarning`, `:1243` `TestCitedSourceFilter` (8), `:1384` `TestTitleBlockedClaimKeepsEverySource`, `:1414` `TestPersistSourcesSkipsUncited`; `test_researcher_decomposed.py:1258-1335` (kept-URL order entity host then score, score coercion, pool cut keeps each sub-question's first two); `test_citations.py:227-253` (`cited_source_ids` title matching, whole-word); `test_analyst.py:383` `TestUncoveredSubQuestionMarker`, `:416` `TestCoverageAndCitedSourcesInstructions`; `test_cli.py:2618` `TestClaimRefreshListsCitedSources` |
| RE-AG Analyst prompt: criterion notes and absence claims | `7774fff`, `abd44fb`, `6eacf37`, `3af5bae`, `5a4ed1a` | `test_analyst.py:321` `TestCriterionNotesInPrompt`, `:347` `TestAnalystInstructionAnchors` (pins the PRECEDENCE paragraph and the `Kind: index` absence sentence verbatim modulo whitespace, `:364-381`); `test_cli.py:1681` `TestStepAnalyzeCriterion` (notes reach analyst; unknown slug and missing templates fall back to title), `:2549` `test_step_audit_sends_criterion_notes`, `:2566` `test_step_audit_without_notes_sends_none`; `test_onboard.py:1380` `test_criterion_notes_reach_analyst_and_auditor`; `test_auditor_agent.py:259` `TestEvaluatorGetsCriterionNotes` (5) |
| RE-AH Claim refresh keeps operator fields and verifies quotes | `589a8fc`, `58086e2`, `5675471` | `test_audit_trail.py` `TestWriteClaimFile` (:936): `test_force_overwrite_keeps_seo_title_when_title_unchanged`, `..._takes_new_seo_title_when_title_changed`, `..._keeps_cap_rationale_when_level_and_confidence_unchanged`, `..._takes_new_cap_rationale_when_level_changes` / `..._when_confidence_changes`, `test_blocked_force_overwrite_drops_cap_rationale`, `test_blocked_write_between_runs_keeps_operator_seo_title`, `test_blocked_write_seeds_record_for_claim_written_before_it`, `test_analyst_seo_title_replaced_when_title_unchanged`, `test_operator_seo_title_replaced_when_analyst_title_changes`, `test_sidecar_rewrite_keeps_analyst_titles`, `test_claim_written_before_first_sidecar_records_passed_titles`, `test_force_overwrite_drops_cap_rationale_on_an_uncapped_level`, `test_force_overwrite_takes_the_level_fit_rationale`; `test_cli.py:673` `test_refresh_keeps_operator_seo_title_and_cap_rationale` (fixture `_write_operator_fields_refresh_fixture` :523); `test_ingest_validation.py:40-257` (all of `drop_unfound_quotes`); `test_ingest_fetch_failure.py:322-414, :482` (end to end and `step-ingest`); `test_entity_independence.py:912` `test_fit_keeping_the_analyst_rationale_is_not_marked_fitted` |
| RE-AI Archive snapshot correctness | `7b5dd4f`, `8bd4c95`, `329fb39` | `test_tools.py:770` `TestCaptureLookup` (9), `:892` `TestCheckCapture` (10), `:1003` `TestFreshness` (6), `:1084` `TestLatestOkCapture` (6), `:1160` `TestReplayWithoutMemento`, plus `test_no_save_after_a_replay_429`; `test_cli.py:2097` `TestWaybackBackfill` (4), `:2192` `TestWaybackBackfillRecheck` (9); `test_archive_after_ingest.py:116, :294`; `test_ingest_fetch_failure.py:230` `test_wayback_recovery_does_not_refresh_stale_capture`; `test_canonical_url.py:276` `TestSamePageAnyScheme`; `conftest.py:140` `mock_capture_replay` |
| RE-AJ Entity enrich refuses to guess | `c0efbd0`, `7ee9b5a` | `test_onboard.py:1540` `TestGatherLightResearchErrors` (6: fetch errors kept, search errors, no website, exception, empty summary, silent ingest failure), `:932` `test_onboard_skips_enricher_when_no_page_fetched`, `test_onboard_new_entity_skips_enricher_when_no_page_fetched`, `:989` `test_name_based_force_keeps_on_disk_description`; `test_cli.py:1098` `test_refuses_when_no_page_fetched`, `:1112` `test_not_enriched_report_names_fetch_reason` |
| RE-AK Published fields survive the pipeline | `9fb70be`, `887fb09`, `c158457`, `a77bb58`, `0b993d5`, `1eee1bb`, `dcb2a5e`, `9e8e210`, `98ffb47`, `54d2192`, `df20c58`, `f0910a6`, `24ee5a2` | `test_audit_trail.py` `TestWriteClaimFile`: takeaway rules (`test_operator_takeaway_kept_when_the_analyst_writes_a_new_one`, `..._replaced_by_the_analysts_new_one`, `..._replaced_when_the_verdict_changes`, `test_analyst_without_a_takeaway_keeps_the_record`, `test_takeaway_without_a_record_counts_as_the_operators`, `test_blocked_write_between_runs_keeps_operator_takeaway`, `test_sidecar_written_after_the_claim_keeps_the_stored_takeaway`), cap-reason rules (`test_operator_cap_rationale_kept_over_the_level_fit`, `..._kept_over_a_new_analyst_one`, `test_analyst_cap_rationale_replaced_by_the_new_one`, `test_record_holds_the_proposed_cap_rationale_not_the_kept_one`, `..._kept_when_the_level_changes`, `..._kept_when_the_confidence_changes`, `..._kept_across_level_changes_until_the_operator_edits_it`, `..._kept_when_no_cap_applies`, `..._survives_a_blocked_run`, `test_blocked_write_keeps_the_cap_rationale_record`), `test_models_used_drops_agents_this_run_did_not_invoke_by_default`; `test_cli.py:1523-1649` (`step-analyze --write --force` resets published/archived to draft, leaves a draft's sidecar, clears the Evaluator comparison, approval after step-analyze records no override, takes the analyst's seo_title/takeaway), `:2046` `test_step_audit_write_keeps_the_models_of_agents_it_did_not_run`, `:2065` `test_step_audit_write_keeps_the_level_fit_note`; `test_entity_independence.py:905` `test_fit_writing_the_only_rationale_is_marked_fitted`, `:726` `test_forced_research_claim_over_a_published_claim_keeps_the_refresh_trail`; `test_onboard.py:1691` `TestOnboardForceRewritesKeepTheRefreshTrail` (4, incl. unparseable claim refused); `test_ingest_validation.py:85-264` bare-quote storage and `test_instructions_ask_for_bare_quotes`; `test_ingest_fetch_failure.py:414`; `test_backfill_analyst_record.py` (10, the one-shot backfill script) |

Not pinned by any test (the roadmap says so): RE-AG's absence rule is "a prompt rule, checked only by paid acceptance runs" (`docs/v1.0.0-roadmap.md:280`, the RE-AG second checklist line); the live checks for RE-AD and RE-AE are shelved backlog rows (`docs/UNSCHEDULED.md:442-443`).

## 4. Keep as acceptance vs mine and delete

Rule used: keep a test when it asserts on something the interview freezes (Q10: claim, source and entity file formats; site URLs) or on a decision rule Brandon recorded (keep rules, lint rules, sign-off gate, archive rule), and when it reaches that behavior through a public function or the CLI. Mine (copy the cases into new tests, then delete) when the test reaches behavior by patching a private name in `orchestrator/pipeline.py` or pins prompt wording.

### A. Keep as acceptance (behavior; re-point imports, keep assertions)

| File / class | Why |
|---|---|
| `test_audit_trail.py` `TestWriteClaimFile` (:936), `TestWriteAuditSidecar` (:192), `TestRefreshSnapshot` (:534), `TestAcquisitionAndToolOutcomes` (:650), `TestApproveRefreshedClaim` (:1988), `TestApproveRecordsVerdictOverride` (:2164), `TestDrReviewPromotion` (:1566) | claim file and sidecar formats; RE-AH/RE-AK keep rules; refresh trail. The function name `_write_claim_file` is private, so these need the new writer to expose one write entry point with the same keyword contract (`force`, `narrative`, `title`, `confidence`, `verdict`, status, record) |
| `test_frontmatter.py`, `test_ingestor_models.py`, `test_auditor_models.py`, `test_templates.py`, `test_entity_resolution.py` (ref grammar + lockstep), `test_models.py` (enums, `resolve_model`) | frozen formats and schemas |
| `test_linter.py` | the content rules `dr lint` enforces in CI; SP7 (fold side tools) keeps `lint` |
| `test_publish.py`, `test_review_queue.py`, `test_review_gate.py`, `test_audit_trail.py` `TestDrReviewCli`/`TestApproveClaimCallable` | sign-off is a person's (interview Q6 premise); `review` stays in the five-command set |
| `test_cli_stats.py` | `dr stats` JSON/text contract (SP7 decides whether `stats` survives; if folded, delete with it) |
| `test_ingest_validation.py` (except `:264`), `test_source_bare_links.py`, `test_source_id_collision.py`, `test_canonical_url.py`, `test_classify_source_type.py`, `test_blocklist.py`, `test_source_url_dedup.py` `TestBuildSourceUrlIndex`/`TestLoadSourceDict`/`TestSlugFromUrl`/`TestRedirectToStoredSource` | source file rules: quotes, ids, dedup keys, labels |
| `test_entity_independence.py:619-694, :786-912` (`fit_verdict_to_written_pool`) and `:53-154` (host/publisher match) | the level rule the site mirrors (`src/lib/sourceQuality.ts`, per `:873`) |
| `test_compare.py` | the current disagreement rule; SP2 (rules, findings file, tie-breaker) changes it, so keep until SP2 lands, then rewrite the expectations for the tie-breaker |
| `test_tools.py:770-1174` (`TestCaptureLookup`, `TestCheckCapture`, `TestFreshness`, `TestLatestOkCapture`, `TestReplayWithoutMemento`), `test_cli.py:2097-2434` (`wayback-backfill`) | RE-AI archive rule, HTTP-mocked, no private seam |
| `test_step_error_vocab.py` | self-updating guard over any new package under `pipeline/` |
| `test_logging_setup.py` | `logs/` file format operators read (`docs/runbook.md`) |
| `test_acceptance.py` `test_full_pipeline_false_claim_smoke` | the one live end-to-end check; re-point from `verify_claim` to the new loop and re-key the skip on the configured model's key, not `ANTHROPIC_API_KEY` |

### B. Mine for cases, then delete with the code they patch

| File / class | Reaches behavior by | What to mine |
|---|---|---|
| `test_orchestrator.py` (all but `TestVerificationResult*`) | `monkeypatch.setattr("orchestrator.pipeline._research" ...)`, `_ingest_urls`, `_analyse_claim`, `_audit_claim`, `_run_with_null_retry`, `below_threshold` | threshold and blocked-write cases (:396), blocklist cap and spared post (:120, :248), `_graded_statement` cases (:955, RE-AD), cited-source filter cases (:1243, RE-AF), uncovered sub-question warning |
| `test_onboard.py` | 82 `override(`, 102 patches, `_research`, `_probe_collision_suggestions`, `gather_light_research` | RE-AJ error cases (:1540), forced-rewrite trail (:1691), subject fan-out (:1458), entity-file-on-disk (:1215), search hints (:1094-1214); the collision probe cases (:563) go with SP6/SP8 if the probe is dropped or narrowed (`docs/UNSCHEDULED.md` RE-AL row "Collision probe treats coverage of the entity as a name collision", `docs/v1.0.0-roadmap.md:337`) |
| `test_cli.py` `TestClaimDraftCLI`, `TestClaimRefreshCLI` (+ `_run_refresh` :559), `TestClaimRefreshKeepsPublishedState`, `TestOnboardCLIPhaseB`, `TestEntityEnrichCLI`, `TestStepAnalyzeCriterion`, `step-analyze`/`step-audit` top-level tests, `TestClaimPromoteCLI`, `TestRemovedCommands` | stubs `verify_claim` / `_research`; targets commands SP6/SP7 fold (`claim-refresh`, `claim-promote`, `step-*`, `entity-enrich`) | the written-file expectations (status reset to draft, `refresh` block, `models_used` kept, Evaluator comparison cleared, cited list) become acceptance cases on the new `draft`/`recheck` commands |
| `test_researcher_decomposed.py` | patches `execute_searches`, `search_brave`, agent `run` | kept-URL ordering, exclude/spare rules, dedup, acquisition trace shape; search-backend dispatch (:520) survives if the search tools survive |
| `test_ingest_urls.py`, `test_prefetch.py`, `test_terminal_fetch.py`, `test_archive_after_ingest.py`, `test_source_url_dedup.py` `TestApplyUrlDedup`/`TestTargetCap`/`TestVerifyClaimSurfacesCachedSources`/`TestPersistSources`/`TestSameBatchRedirects`/`TestRedirectToACachedSourceDoesNotCount`, `test_tools.py:571-769` | `_ingest_one`, `_ingest_urls` internals | fetch policy (terminal codes, 429, no wayback after a failed ingest), thin-sub-question-first (RE-AF), dedup-shrinks-target (RE-AL row at `docs/v1.0.0-roadmap.md:336`) |
| `test_ingest_fetch_failure.py` | `_ingest_one` plus `step-ingest` | "a failed fetch never becomes a source" (:192-303), quote checks end to end, arXiv fixtures |
| `test_entity_independence.py:305-376, :556-583, :703-726` | `verify_claim`/`research_claim` with `_patch_pipeline` (:268) | off-entity overrides written, fitted level written, refresh trail kept |
| `test_citations.py:163` (`_analyse_claim`) | private | clean narrative on write |
| `test_analyst.py` `TestAnalystInstructionAnchors`, `TestCoverageAndCitedSourcesInstructions`, `TestCriterionNotesInPrompt`, `TestAnalystPrompt`; `test_auditor_agent.py` (all); `test_agent.py` `TestBuildAnalystPrompt`; `test_entity_enricher.py`, `test_entity_verifier.py`, `test_scorer.py`, `test_research_planner.py`, `test_instructions.py` `TestAgentInstructionsWiring`; `test_ingest_validation.py:264` | prompt wording and section order | the rules they encode (criterion notes precede sources; Evaluator sees the claim statement before the narrative and never the analyst verdict; absence rule; bare quotes) become behavior checks on the new loop's prompt builders, not string anchors |
| `test_checkpoints.py` `TestCLIReviewVerificationStatus` and the auto-approve classes | interactive prompts | the interview says normal runs ask no nuanced questions; delete with the checkpoint handlers, keep the entity-rejection outcome as a findings-file case (SP2) |
| `test_research_integration.py` | all agents on `TestModel`, patches `_write_*` | the one whole-loop mocked test; rewrite as the SP1 acceptance test for `pipeline/loop/` |
| `test_cli_smoke.py` | subprocess with Brandon's absolute path; lists hidden `reassess`/`ingest` | replace with a `CliRunner` test over the SP7 command list |
| `test_backfill_analyst_record.py`, `test_rerun_v1_claims.py` | one-shot scripts (`c0fe380` ran the backfill; `rerun_v1_claims` is a 2026-10-10 script) | delete with the scripts, or keep if the scripts stay |
| `test_content_loader.py` | real `research/claims/` with 5 stale skips | fold into a `tmp_path` loader test |
| `test_brave_search.py`, `test_tavily_search.py`, `test_arxiv_search.py`, `test_throttle.py` | tool wrappers | keep as is if the tools move unchanged under `pipeline/loop/`; they patch nothing in the orchestrator |

## 5. Duplication

| What | Locations |
|---|---|
| `_make_source_file` helper (build a `SourceFile` with defaults) | `test_source_url_dedup.py:45`, `test_onboard.py:75`, `test_ingest_urls.py:16`, `test_audit_trail.py:59` |
| `_write_claim` helper (write a claim `.md` into a tmp repo) | `test_review_queue.py:30`, `test_review_gate.py:25`, `test_cli_stats.py:32`, `test_cli.py:259` (`TestClaimRefreshCLI._write_claim`) |
| `_write_minimal_sidecar` | `test_publish.py:28`, `test_audit_trail.py:71` |
| Copy the real `research/templates.yaml` into `tmp_path` | `test_onboard.py:140` (`_setup_tmp_repo`), `test_cli.py:1126` (`TestOnboardCLIPhaseB._setup_repo`) |
| `_make_ctx` (a `RunContext` with `IngestorDeps`) | `test_terminal_fetch.py:29`, `test_prefetch.py:24`, `test_ingest_fetch_failure.py:36` |
| `_make_cfg` (a `VerifyConfig`) | `test_source_url_dedup.py:61`, `test_researcher_decomposed.py:46`, `test_ingest_urls.py:32` |
| `_analyst_output` (a scripted `AnalystOutput`) | `test_archive_after_ingest.py:49`, `test_auditor_agent.py:172`, `test_source_url_dedup.py:503` |
| `_analyst_model` / `_auditor_model` / `_ingestor_model` (FunctionModels for the three agents) | `test_onboard.py:91,110,129`, `test_research_integration.py:27,46,67` |
| `_noop` / `_ro` (no-op async and a `ResearchOutput` stub) | `test_onboard.py:32,37`, `test_orchestrator.py:93,98`, `test_research_integration.py:22` |
| `_sf` (short `SourceFile` builder) | `test_orchestrator.py:1111`, `test_source_bare_links.py:30`, `test_source_id_collision.py:36` |
| `_noop_ctx`, `_fetch_then_return` (ingest FunctionModel that fetches then returns), `_invoke_step_ingest` | `test_source_bare_links.py:78,82`, `test_source_id_collision.py:181,185,200`, `test_ingest_fetch_failure.py:431` |
| `_patch_git_email` | `test_review_queue.py:128`, `test_review_gate.py:203` |
| `_load_script` (import a `scripts/*.py` by path) | `test_backfill_analyst_record.py:25`, `test_rerun_v1_claims.py:41` |
| `_reset_throttle` | `test_tavily_search.py:43`, `test_arxiv_search.py:64` |
| `_bundle` (`LightResearchBundle`) | `test_entity_enricher.py:17`, `test_entity_verifier.py:17` |
| `_ts`, `_sidecar`, `_verdict` | `test_archive_after_ingest.py:26` / `test_tools.py:737`; `test_backfill_analyst_record.py:65` / `test_linter.py:649`; `test_citations.py:142` / `test_entity_independence.py:229` |
| Auditor prompt capture (`_capturing_auditor`) copied into `test_step_audit_sends_claim_title` | `test_auditor_agent.py:192`, `test_cli.py:2435`; recorded at `docs/UNSCHEDULED.md:434` |
| `patch.object(Agent, "override", ...)` no-op pattern so the CLI's own model override does not replace the test's | 16 occurrences across `test_cli.py`, `test_onboard.py`, `test_source_bare_links.py`, `test_source_id_collision.py`, `conftest.py:117` |
| `fixtures/known_good/`, `fixtures/known_bad/`, `fixtures/sample_source.md` | unused by any test; `fixtures/sample_page.html` used once (`test_tools.py:93`) |

## 6. Hazards for a rebuild

| Hazard | Where |
|---|---|
| Private seam names are the test suite's main entry points: `orchestrator.pipeline._research` is patched 37 times, `common.content_loader.resolve_repo_root` 23, `_probe_collision_suggestions` 17, `_ingest_urls` 13, `_audit_claim` 9, `verify_claim` 8, `_analyse_claim` 8, `_ingest_one` 12 (`patch(`). A new `pipeline/loop/` with different names breaks these in bulk, so the beta.7 pins inside them (section 3) vanish at the same time as the scaffolding | grep over `pipeline/tests/*.py`; `test_orchestrator.py`, `test_onboard.py`, `test_cli.py`, `test_entity_independence.py:268` |
| The RE-AH/RE-AK keep rules (operator `seo_title`, `takeaway`, `cap_rationale`; `analyst_record`; refresh trail; `models_used` carry-over) are 38 tests on `_write_claim_file` and `_write_audit_sidecar`, private functions in `orchestrator/persistence.py`. If SP1 writes claims through a new writer, nothing else guards those rules | `test_audit_trail.py:936-1434`, `:192-533` |
| The Evaluator contract (grades the claim statement; never sees the analyst verdict; gets criterion notes) is pinned as prompt string order and instruction wording, not as model behavior. A rewritten prompt passes no test and fails none unless the anchors are re-pinned | `test_auditor_agent.py:91,158,219,259`; `test_analyst.py:347-381,416-431`; `test_ingest_validation.py:264` |
| Pytest runs only locally: pre-commit hook via `inv check`, or `inv test`. CI runs `dr lint` only. A spike that breaks tests is caught at commit time on this machine and nowhere else | `.git/hooks/pre-commit:14-17`; `.github/workflows/ci.yml:82-87`; `tasks.py:43-51` |
| The live tests skip on `ANTHROPIC_API_KEY`, while the configured default model is GreenPT/Infomaniak (`docs/plans/deferred/acceptance-test-fixture_stub.md:5`), so they likely never run; the interview's "one live dr probe per spike" is the only live check planned | `test_acceptance.py:32-39` |
| `test_cli_smoke.py` hardcodes `/Users/brandon/dev/ai/dangerous-robot/site` as cwd and passes for hidden commands `reassess` and `ingest` (both exit 0 on `--help` today); SP7's five-command fold must edit the parametrize list or it fails | `test_cli_smoke.py:10-20`; `pipeline/orchestrator/cli.py:1726,1746` |
| Tests coupled to real data: template count 16, first template slug, inactive `data-jurisdiction`, the two Responsible AI criteria and their text, `research/claims/` listing by entity `anthropic` and topic. SP6 (templates become stored sentences) and any `templates.yaml` edit changes these | `test_templates.py:23-60`; `test_content_loader.py:86-117`; `test_onboard.py:140`; `test_cli.py:1126` |
| `conftest.stub_ingest_model` parses the URL from the ingest prompt (`prompt.split("URL: ", 1)`); a new ingest prompt layout silently breaks every test using it (`test_archive_after_ingest.py`, `test_cli.py` step-ingest classes) | `conftest.py:72-76` |
| `conftest._isolate_cli_logging` patches `orchestrator.cli._safe_repo_root`; a new CLI module must expose the same name or `CliRunner` tests write to the real `logs/` | `conftest.py:32-48` |
| `human_at_terminal` patches `orchestrator.review._stdin_is_tty` and `_prompt_slug`; moving the sign-off gate renames break 5 classes in `test_audit_trail.py`, `test_publish.py:499`, `test_review_queue.py:322` | `conftest.py:124-137` |
| `test_step_error_vocab.py` scans every production `.py` under `pipeline/` (new `pipeline/loop/` included) and fails on any `error_type="..."` literal missing from the `StepError` docstring; SP2's findings rules will add literals | `test_step_error_vocab.py:91-190`; `orchestrator/checkpoints.py` `StepError.__doc__` |
| `test_instructions.TestAgentInstructionsWiring` requires each agent's system prompt to equal `instructions.md` (+ `verdict-scale.md` for analyst and auditor); a tie-breaker agent (SP2) needs the same layout or an updated test | `test_instructions.py:38-59` |
| Five skipped tests reference a moved plan path (`docs/plans/multi-topic.md` is now `docs/plans/completed/multi-topic.md`) and a claim `anthropic/publishes-sustainability-report` | `test_content_loader.py:58-108` |
| `test_entity_resolution.py` lockstep tests read `src/content.config.ts`; dropping company entities (SP8) changes `CANONICAL_ENTITY_KEYS` expectations and the Zod literals they check | `test_entity_resolution.py:184-226` |
| `test_compare.py` pins the disagreement rule SP2 replaces (tie-breaker); the `needs_review_reasons` strings it asserts are rendered on the claim page | `test_compare.py:157-217` |
| Fixture claims in `fixtures/known_good`/`known_bad` use an old claim shape; anyone reviving them as acceptance data would pin the wrong format | `pipeline/tests/fixtures/known_good/*.md` |
| Known test gaps already recorded: `validate_source_file` slug/year/URL checks have no direct tests; the onboard verifier runs on an empty light-research bundle in most `test_onboard.py` tests | `docs/UNSCHEDULED.md:419, 432` |

## 7. Open questions

1. Does the rebuild keep `orchestrator/persistence.py`'s `_write_claim_file` / `_write_audit_sidecar` as the one write path (so `test_audit_trail.py`'s 116 tests survive by import change), or does SP1 write files its own way (then the 38 keep-rule tests need a new home before the old path is deleted)?
2. Should the prompt-wording anchors (RE-AD, RE-AG, RE-AF, bare quotes) be re-pinned as prompt-builder output checks in `pipeline/loop/`, or dropped in favor of the one live probe per spike? The roadmap already calls RE-AG's absence rule "checked only by paid acceptance runs" (`docs/v1.0.0-roadmap.md:280`).
3. Which key gates `test_acceptance.py` after the rebuild: `ANTHROPIC_API_KEY` (today), or the configured provider's key via `resolve_model`? Today's gate likely means the smoke test has not run since the model switch (not verified; no run log on disk).
4. Does SP7 keep `stats` and `wayback-backfill`? Their tests (`test_cli_stats.py`, `test_cli.py:2097-2434`) are public-contract tests that go or stay with the commands.
5. Should pytest run in CI for the rebuild (it does not today), given the spikes delete code paths that only local pre-commit runs would catch?
6. Are `scripts/backfill_analyst_record.py` and `scripts/rerun_v1_claims.py` kept (their tests stay) or removed as one-shots?
7. `test_cli_smoke.py`'s hardcoded cwd and hidden-command list: fix in SP7 or delete now?
