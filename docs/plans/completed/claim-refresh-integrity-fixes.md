# Plan: claim-refresh integrity fixes (RF1 to RF4)

**Status**: `done` (2026-10-04)
**Last updated**: 2026-10-04
**Reviewed by:** self-review, 2026-10-04 (see Review history)
**Findings**: RF1 to RF4 in [`docs/UNSCHEDULED.md` § claim-refresh review findings (2026-10-04)](../../UNSCHEDULED.md#claim-refresh-review-findings-2026-10-04)

Fix the four bugs that let one `dr claim-refresh` cite the wrong file (RF1), keep a failed fetch as evidence (RF2), label the entity's own pages `independent` (RF3), and publish raw citation tokens (RF4). Every fix is test-first: write the failing test, confirm it fails for the stated reason, change the code, confirm it passes.

Paths are under `pipeline/` unless they start with `docs/`, `research/`, `src/` or `scripts/`. Line numbers are as of 2026-10-04 (HEAD `d57ae1d`).

## Status checklist

Ticked as items land (AGENTS.md rule 4). Ids match the step headings below.

- [x] S0: link this plan from the four RF rows in `docs/UNSCHEDULED.md`
- [x] F1: fetch-success record on `IngestorDeps` (RF2, shared)
- [x] F2: `_ingest_one` rejects sources with no successful fetch or failed validation (RF2)
- [x] F3: `dr step-ingest` rejects sources with no successful fetch (RF2)
- [x] C1: source id resolver with collision handling (RF1, shared)
- [x] C2: resolve ids in `_ingest_urls` before analysis (RF1)
- [x] C3: `_write_source_files` never returns the id of a different URL (RF1)
- [x] C4: `dr step-ingest` write path uses the resolver; `--force` only overwrites the same URL (RF1)
- [x] E1: entity match helper (RF3, shared)
- [x] E2: apply entity match to the analyst's source pool and record `source_overrides` (RF3)
- [x] E3: `parent_company` and the "Brave" alias on the Brave entities (RF3; Q1 answered: both)
- [x] E4: `docs/architecture/source-quality.md` describes the entity match
- [x] T1: citation cleaner module (RF4)
- [x] T2: analyst prompt and instructions stop inviting "Source N" (RF4)
- [x] T3: hand-fix the `ai-producers-existential-score` body (RF4; Q2 answered: delete the sub-question block)
- [x] T4: lint rules: citation tokens (error) and level-vs-pool mismatch (warning) (RF4, RF3); lands after the Brave refresh in V1 is approved (Q3)
- [x] T5: wire the citation cleaner into `_analyse_claim` (RF4)
- [x] V1: Verification section passes; Brandon's end-to-end refresh inspected

## Facts the plan relies on

Checked against code on 2026-10-04.

| Id | Fact | Where |
|----|------|-------|
| K1 | The source id the analyst, coverage map and sidecar use is computed from `sf.slug` before any file is written. Disambiguating only at write time is too late. | `orchestrator/pipeline.py:374-379` (`_build_source_dict` at `:805`, `source_id` at `:820`) |
| K2 | `_ingest_urls` is the one place every pipeline ingest passes through (`verify_claim`, `research_claim`, the add-source path). | `orchestrator/pipeline.py:359`, `:1033`, `:1321` |
| K3 | `research_claim` zips `source_files` with the ids `_write_source_files` returns, by position. The write function must keep returning one id per input. | `orchestrator/pipeline.py:1087-1088` |
| K4 | `common/canonical_url.py:40` `canonicalize()` already defines "same resource" (scheme and host lowercased, `www.` and default ports stripped, fragment and tracking params dropped). It raises `ValueError` on malformed input. | |
| K5 | `web_fetch` turns every non-terminal `httpx.HTTPError` (including DNS failure) into an error dict so the model can try `wayback_check`. Raising there would remove the archive recovery path. | `ingestor/agent.py:113-115`, docstring `:73-76` |
| K6 | New `StepError.error_type` literals must be added to the `StepError` docstring and `tests/test_step_error_vocab.py` `DOCUMENTED_LITERALS`, or that test fails. | `orchestrator/checkpoints.py:15`, `tests/test_step_error_vocab.py:38` |
| K7 | `verification_level` is chosen by the analyst model from the labels it is shown; no code derives it. | `analyst/agent.py:149`, `analyst/instructions.md:159-171` |
| K8 | The claim page counts sources from the file-level `independence` plus the claim's `source_overrides`. Changing only the analyst's in-memory labels would leave the page saying "1 independent" next to a `claimed` level. | `src/lib/sourceQuality.ts:58-75` |
| K9 | The file-level `independence` is entity-agnostic by design; per-claim corrections go in `source_overrides`. A brave.com page is first-party on a Brave claim and could be independent on an AWS claim. | `docs/architecture/source-quality.md` § Source overrides on claims |
| K10 | `ResolvedEntity` carries `entity_name`, `aliases`, `legal_name`, `website`, `parent_company` (a `companies/<slug>` ref). `verify_claim` receives it from claim-refresh, onboard and `dr verify`. `research_claim` gets it only when the operator pre-resolves the entity. | `orchestrator/entity_resolution.py:29-40`, `orchestrator/cli.py:869-875`, `:916` |
| K11 | `research/entities/products/brave-browser.md` has `website: https://brave.com` and no `parent_company`; `companies/brave-software.md` exists (`website: https://brave.com/about/#company-info`). The forum thread in the run was on `community.brave.app` with publisher "Brave Software", so only a parent-company name match catches it. | |
| K12 | `dr lint` reads frontmatter only (`linter/runner.py:36-41`, `:89`); checks are pure functions over pre-built maps (`linter/checks.py:1`). CI fails on `dr lint --severity error`. | `.github/workflows/ci.yml:37-41` |
| K13 | Python `re` `\s` matches U+00A0 and U+202F. The investigation's check used a literal-space substring and missed "Source 1" written with U+00A0. | |
| K14 | Two published claims carry the RF4 defect today: `subjects/ai-model-producers/ai-producers-existential-score` (6 `【id】` tokens) and `brave-browser/renewable-energy-hosting` ("(Source 2, 4)", "(Sources 4, 8)", "Sources 6 and 7", "(Source 2)", with 6 sources listed, so 7 and 8 point at nothing). | scan of `research/claims/**` bodies |

## Order and lanes

Shared pieces first: F1 (fetch record) before F2 and F3; C1 (resolver) before C2 to C4; E1 (matcher) before E2. T4's level check reads only frontmatter, so it needs nothing from lane core.

## Lanes

- **Lane core** (serial, in this order): S0, F1, F2, F3, C1, C2, C3, C4, E1, E2, E3, E4, then T5. Scope: `ingestor/agent.py`, `orchestrator/pipeline.py`, `orchestrator/persistence.py`, `orchestrator/cli.py`, `orchestrator/checkpoints.py`, `orchestrator/entity_resolution.py`, `common/source_classification.py`, `research/entities/products/brave-browser.md`, `research/entities/companies/brave-software.md`, `docs/architecture/source-quality.md`, `docs/UNSCHEDULED.md`, and their tests.
- **Lane text** (serial within the lane, T1 to T4 in order; independent of lane core, so the two lanes can run in parallel): T1, T2, T3; T4 waits for V1. T4 must land after T3 and after the Brave claim is replaced by Brandon's refresh (Q3), or CI fails on the published Brave body. Scope: `analyst/citations.py` (new), `analyst/agent.py`, `analyst/instructions.md`, `linter/checks.py`, `linter/runner.py`, the two claim files in K14, `tests/test_citations.py` (new), `tests/test_linter.py`, `tests/test_analyst.py`.
- T5 runs after both lanes finish (it touches `orchestrator/pipeline.py` and imports T1).

RF2 lands before RF1 because a failed fetch is the worse defect (invented content) and both touch `_ingest_one`/step-ingest; doing RF2 first keeps C4's diff on a step-ingest that already has its fetch check.

---

## RF2: a failed fetch never becomes a source

**Decision**: post-check, not tool error propagation. `web_fetch` keeps returning an error dict (K5) so wayback recovery still works; the orchestrator rejects any run in which no fetch returned page text. This also catches a model that never calls `web_fetch` and answers from the URL alone, which raising would not.

**Decision**: run `validate_source_file` in `_ingest_one`. Before validating, set `sf.frontmatter.url` to the URL the orchestrator asked for (log at INFO when the model's value differed); the orchestrator knows the requested URL, the dedup index keys on it, and a model echoing a redirect target would otherwise fail `_check_url_match` (`ingestor/validation.py:51-58`) and drop good sources. Remaining errors (slug format, year range, non-archive.org `archived_url`) reject the source.

**Decision**: new literals `fetch_failed` and `invalid_source` (clearer in the progress line and sidecar than reusing `http_error`); document both per K6.

**RF10**: pulled in only as far as running `validate_source_file` in the refresh path. Key-quote checking (`page_text`) is not passed in this plan; what to do with a non-verbatim quote (warn, drop, reject) stays RF10. F1's record keeps the fetched text so RF10 can use it.

### F1: fetch-success record on `IngestorDeps`

- Failing test first: `tests/test_ingest_fetch_failure.py::test_web_fetch_records_success_and_failure`. Calls `web_fetch` directly (pattern: `tests/test_terminal_fetch.py:34-43` `_make_ctx`) with respx: a 200 HTML page records `deps.fetched_text[url]` non-empty; `httpx.ConnectError("[Errno 8] nodename nor servname provided")` records nothing in `fetched_text` and one entry in `deps.fetch_errors`; a prefetched body counts as fetched. Fails today: the fields do not exist.
- Change: `ingestor/agent.py:32-47` add `fetched_text: dict[str, str]` and `fetch_errors: list[str]` (default empty), siblings of `acquisition_writes`. In `web_fetch` (`:63`) record on the prefetched return (`:79-89`), after `extract_page_data` when `text` is non-empty (`:112`), and in the `except httpx.HTTPError` branch (`:113-115`). Add `def fetch_succeeded(deps) -> bool` in the same module so F2 and F3 share one rule.
- Commit: `fix(ingestor): record which fetches returned page text`

### F2: `_ingest_one` rejects unfetched or invalid sources

- Failing tests first, same file, using the harness in `tests/test_terminal_fetch.py:189-197`, `:248-271` (`_noop_ctx`, patched `ingestor_agent.override`), with a `FunctionModel` that calls `web_fetch` and then returns a `SourceFile` through the output tool:
  - `test_dns_failure_returns_fetch_failed`: respx raises `ConnectError`; assert `_ingest_one` returns a `StepError` with `error_type == "fetch_failed"` and not a `(url, SourceFile)` tuple. Fails today (returns the tuple, the RF2 bug).
  - `test_model_skips_fetch_returns_fetch_failed`: the model returns a `SourceFile` without calling any tool; same assertion.
  - `test_wayback_recovery_still_ingests` (control against over-blocking): original URL raises `ConnectError`, the model calls `web_fetch` on a `https://web.archive.org/...` URL that returns 200; assert a tuple is returned.
  - `test_invalid_archived_url_returns_invalid_source`: fetch succeeds, model sets `archived_url` to a non-archive.org URL; assert `error_type == "invalid_source"`.
  - `test_model_url_replaced_with_requested_url`: model echoes a different URL; assert the returned `SourceFile.frontmatter.url` equals the requested URL.
- Change: `orchestrator/pipeline.py:689-695`, after `sf = res.output`: if `not fetch_succeeded(deps)` return `StepError(step="ingest", url=url, error_type="fetch_failed", message=<last fetch error or "model returned a source without fetching the page">)`; set the URL; run `validate_source_file(sf, url, cfg.repo_root or "")`; on errors return `StepError(..., error_type="invalid_source", message="; ".join(errors))`; log warnings. Add both literals to the `StepError` docstring (`orchestrator/checkpoints.py:15`) and `DOCUMENTED_LITERALS` (`tests/test_step_error_vocab.py:38`).
- Expected side effect: more URLs fail, so the waterfall (`orchestrator/pipeline.py:723-802`) tries further candidates and a thin claim may hit the 4-source block (`:149-157`) more often. That is the correct outcome.
- Commit: `fix(pipeline): drop ingests with no fetched page text or failed validation`

### F3: `dr step-ingest` rejects unfetched sources

- Failing test first: `tests/test_ingest_fetch_failure.py::test_step_ingest_fetch_failure_writes_nothing`. `CliRunner` against a tmp repo root, `--write`, agent patched as in F2 with a DNS failure; assert exit code 1, an error line naming the fetch failure, and no file under `research/sources/`.
- Change: `orchestrator/cli.py:365-376`, after the agent run, if `not fetch_succeeded(deps)` echo the error and return 1, before `validate_source_file` at `:377`. Unlike F2, step-ingest keeps `_check_url_match` on the model's URL: it is the operator-facing path and a mismatch there is worth a visible error.
- Commit: `fix(cli): step-ingest refuses a source whose page was never fetched`

---

## RF1: a source id always names the file for that URL

**Decision**: disambiguate, do not fail. Failing drops a valid source (the run lost AWS's "net-zero by 2040" quote this way) and would break the one-id-per-input contract (K3). Rule, evaluated per new source against disk and against ids already assigned in the same batch:

1. Slug free: use it.
2. Taken by a file (or batch entry) whose URL canonicalizes equal (K4): reuse that id; it is the same page.
3. Taken by a different URL: try `<host>-<slug>`, where `<host>` is the hostname without `www.` and without its last label, dots to hyphens (`aws.amazon.com` gives `aws-amazon-sustainability`). If that is also taken by a different URL, append `-2`, `-3`, and so on.

Host prefix first because it is readable and the same URL gets the same id on every run; the numeric suffix is only a last resort. Existing files are never renamed or rewritten; only the new file gets the longer name. A `canonicalize` `ValueError` counts as "different URL".

**Scope against existing backlog sections**:

- [Improve source slug generation](../../UNSCHEDULED.md#improve-source-slug-generation): in scope here is only the collision rule above. Title-based slugs, `%20` decoding and numeric or generic path tails (RF14), PDF re-segmentation and the backfill rename stay there.
- [Dedup detection](../../UNSCHEDULED.md#dedup-detection-on-url-ingest-and-claim-creation): canonical-URL lookup before ingest (`_apply_url_dedup`, `orchestrator/pipeline.py:554-575`, still exact-match) and claim-level match-and-return stay there. This plan uses `canonicalize` only to decide rule 2 at slug time, so a near-duplicate URL that lands on the same slug reuses the existing id; one that lands on a different slug is still a duplicate file (Dedup's job).

### C1: source id resolver

- Failing tests first: `tests/test_source_id_collision.py` (new), all against a tmp repo root.
  - `test_cross_run_collision_gets_host_prefixed_id`: existing `research/sources/2026/sustainability.md` with url `https://datacenters.microsoft.com/sustainability/`; resolving `https://aws.amazon.com/sustainability` returns `aws-amazon-sustainability`; the Microsoft file's bytes are unchanged.
  - `test_same_canonical_url_reuses_id`: existing url `https://aws.amazon.com/sustainability`, new `https://www.aws.amazon.com/sustainability#top`; returns `sustainability`.
  - `test_same_run_duplicates_get_distinct_ids`: `https://aws.amazon.com/sustainability` and `https://aws.amazon.com/energy-utilities/sustainability` in one batch with no file on disk; ids are `sustainability` and `aws-amazon-sustainability`.
  - `test_numeric_suffix_when_host_prefix_taken`: both `sustainability` and `aws-amazon-sustainability` taken by other URLs; returns `aws-amazon-sustainability-2`.
  - `test_existing_files_never_renamed`: directory listing before and after only gains files.
- Change: `orchestrator/persistence.py`, new `resolve_source_slugs(items: list[tuple[str, SourceFile]], repo_root: Path) -> None` that sets `sf.slug` in place per the rule (reads only the `url` frontmatter of the colliding file via `parse_frontmatter`). Helper `_host_token(url)` next to `slug_from_url` in `common/utils.py:17-27`.
- Commit: `feat(pipeline): resolve source slug collisions by URL`

### C2: resolve ids in `_ingest_urls`

- Failing test first: `tests/test_source_id_collision.py::test_ingest_urls_assigns_unique_ids`, `_ingest_one` patched to return the two AWS URLs with slug `sustainability` and the Microsoft file on disk; assert the returned `SourceFile`s have distinct slugs, neither equal to `sustainability`. Fails today.
- Change: `orchestrator/pipeline.py:801-802`, call `resolve_source_slugs(results[:target], Path(cfg.repo_root or resolve_repo_root()))` before returning (K2 covers all callers; K1 is why it is here and not at write time). `tests/test_ingest_urls.py:30-36` builds `VerifyConfig(repo_root="/tmp")`; switch it to `tmp_path` so the resolver never reads a shared directory.
- Commit: `fix(pipeline): assign collision-free source ids before analysis`

### C3: write guard

- Failing test first: `tests/test_source_id_collision.py::test_write_source_files_never_returns_other_urls_id`, calling `_write_source_files` directly (skipping C2, as a parallel process or a later onboard template could) with the Microsoft file on disk and the two AWS `SourceFile`s both slugged `sustainability`. Assert: two distinct ids returned; each id's file has the url of the matching input; the Microsoft file is unchanged. Fails today: returns `['2026/sustainability', '2026/sustainability']`.
- Change: `orchestrator/persistence.py:157-163`, on `FileExistsError` read the existing url; same canonical URL keeps today's behavior; different URL logs a WARNING naming both URLs, re-runs the resolver for that item, writes, updates `sf.slug`, and appends the new id. Return stays one id per input (K3).
- Note: `orchestrator/cli.py:1087` `dict.fromkeys` then only merges true duplicates (cached and fresh copies of the same page). No change there.
- Commit: `fix(persistence): never cite an existing source file for a different URL`

### C4: `dr step-ingest` write path

- Failing test first: `tests/test_source_id_collision.py::test_step_ingest_force_does_not_overwrite_other_url`. `CliRunner`, tmp repo with the Microsoft file, agent patched to return the AWS URL slugged `sustainability`, `--force`; assert exit 0, Microsoft file unchanged, new file `2026/aws-amazon-sustainability.md`. Fails today (overwrites at `orchestrator/cli.py:399`).
- Change: `orchestrator/cli.py:396-407`, call `resolve_source_slugs` first; `--force` overwrites only when the resolved slug is the same-URL file.
- Commit: `fix(cli): step-ingest --force only overwrites the same URL`

---

## RF3: the entity's own pages are first-party for its claims

**Decision**: a deterministic match, applied per claim and recorded as `source_overrides` (K8, K9). The source file's `independence` is not changed. This is the deterministic pass of the planned entity-match classifier (`docs/plans/source-quality-followups.md:166`), without the model fallback.

A source is first-party for the claim when either:

- **Host**: its URL host (without `www.`) equals or is a subdomain of the host of the entity's `website` or the parent company's `website`. `search.brave.com` matches `brave.com`; `notbrave.com` and `brave.com.example.net` do not.
- **Publisher**: its `publisher`, lowercased with punctuation and trailing `inc`/`llc`/`ltd` removed, equals the entity's `name`, `legal_name`, an alias, or the parent's `name`, `legal_name` or an alias. Equality, not substring (`"meta"` would otherwise match many publishers).

The match beats any label, including the ingest model's (the forum thread's `independent` came from the model). It only ever moves a source toward `first-party`.

**Level**: chosen by the analyst model (K7), so the unit tests check labels and overrides, not the level. Evidence that corrected labels change the level: the investigation's analyst replay with the two Brave pages relabelled and the failed source removed returned `claimed` with a `cap_rationale` (one run; unlabelled pool returned `independently-verified`). T4 adds a deterministic lint check that a level claiming independent sources has at least one in the effective pool. The end-to-end run (V1) checks the level.

### E1: entity match helper

- Failing tests first: `tests/test_entity_independence.py` (new), pure function, no I/O:
  - `test_entity_host_match`: brave-browser identity (website `https://brave.com`, parent "Brave Software" with website `https://brave.com/about/#company-info`), source `https://brave.com/transparency/` publisher "Brave Software" kind `report`: returns a reason mentioning `brave.com`.
  - `test_parent_publisher_match`: `https://community.brave.app/t/.../631793` publisher "Brave Software": matches via parent name.
  - `test_no_parent_no_forum_match`: same forum source, identity without a parent: no match (documents why E3 is needed).
  - `test_unrelated_publisher_no_match`: `https://aws.amazon.com/sustainability` publisher "AWS": no match.
  - `test_lookalike_hosts_no_match`: `notbrave.com`, `brave.com.example.net`: no match; `search.brave.com`: match.
  - `test_substring_publisher_no_match`: entity "Meta", publisher "Metacritic": no match.
  - `test_short_publisher_needs_alias`: forum source with publisher "Brave": no match without an alias, match once the identity has alias "Brave" (documents that `aliases:` on the entity file is the lever; see Q1).
- Change: `common/source_classification.py`, add `EntityIdentity` (frozen dataclass: `names: frozenset[str]`, `hosts: frozenset[str]`) and `entity_first_party_reason(publisher: str, url: str, identity: EntityIdentity) -> str | None`. Add `entity_identity_for(resolved: ResolvedEntity, repo_root: Path) -> EntityIdentity` in `orchestrator/entity_resolution.py`, loading the parent with `parse_entity_ref(resolved.parent_company, repo_root)` (`:89`) and falling back to `resolve_parent_name` (`:51`) for the name if the parent file is missing.
- Commit: `feat(sources): match a source to the claim's entity or its parent company`

### E2: apply to the analyst's pool and record overrides

- Failing test first: `tests/test_entity_independence.py::test_verify_claim_marks_entity_sources_first_party`. Monkeypatch `_research`, `_ingest_urls`, `_audit_claim` and `_analyse_claim` in `orchestrator.pipeline` (pattern: `tests/test_orchestrator.py`) with a pool of five sources: the brave.com transparency report labelled `independent`, the forum thread labelled `independent` by the model, three AWS/Google pages; a cached hit for one Brave page (exercises `load_source_dict`, `orchestrator/persistence.py:104-132`). The fake analyst captures the `sources` it receives and returns a verdict with `source_overrides=None`. Assert: both Brave sources reach the analyst as `first-party`; the result's `analyst_output.verdict.source_overrides` has one entry per Brave source with `independence: first-party` and a reason naming the matched host or publisher; AWS/Google labels unchanged. Second case: the analyst already overrode one Brave source; assert no duplicate entry. Fails today (labels pass through unchanged).
- Change: `orchestrator/pipeline.py`, in `verify_claim` after the source-assembly loops (`:368-379`) and before `_invert_addresses` (`:389`), when `resolved_entity` is set: build the identity, relabel matching dicts to `first-party`, keep the list of overrides. After the analyst returns (`:433-437`), append those overrides to `analyst_out.verdict.source_overrides` (create the list if `None`, skip sources the analyst already overrode). Same two insertions in `research_claim` (`:1044-1055`, `:1100`) when its `resolved_entity` is set. Writes then flow through `verdict_write_kwargs` (`orchestrator/persistence.py:221-236`) unchanged. Rejected: wiring into `_write_source_files` or step-ingest, because those write the entity-agnostic file label (K9).
- Commit: `fix(pipeline): treat the claim entity's own sources as first-party`

### E3: `parent_company` on Brave Browser

- Add `parent_company: companies/brave-software` to `research/entities/products/brave-browser.md` and `aliases: [Brave]` to `research/entities/companies/brave-software.md` (Q1). Test: `tests/test_entity_independence.py::test_brave_entity_has_parent` loads the real entity with `parse_entity_ref("products/brave-browser", repo_root)` and asserts the identity includes "brave software". Fails until the edit lands.
- Commit: `fix(entities): link Brave Browser to Brave Software`

### E4: architecture doc

- `docs/architecture/source-quality.md` § The `independence` field: add the entity-match rule and that it is recorded in `source_overrides`; add "the claim entity's own pages" to the Edges list as handled. No test.
- Commit: `docs(architecture): describe the entity-match independence override`

---

## RF4: no raw citation tokens or "Source N" on the site

### Options

| Id | Option | For | Against |
|----|--------|-----|---------|
| O1 | Analyst prompt: drop the `### Source N:` numbering (`analyst/agent.py:285`), restate "cite by title" with a "never write ids, 【】 or Source N" line (`analyst/instructions.md:110`) | Removes the likely trigger; cheap | Not a guarantee; gpt-oss writes `【id】` natively |
| O2 | Post-processing in the pipeline: replace `【id】` with ` (*Title*)` when the id is in the pool, drop unknown tokens; replace "Source N"/"Sources N, M"/"Source N: *Title*" with titles by prompt order | Deterministic for known patterns; fixes every write path at once | Pattern list can lag new model habits; awkward prose possible |
| O3 | `dr lint` error rule on claim bodies and `takeaway` (`【...】`, `\bSources?\s+\d+\b`, `\s` covers U+00A0 per K13) | Catches existing and future cases; CI blocks them (K12) | Detects only; needs the content fixed first or CI fails |
| O4 | Site-side remark plugin that rewrites or hides tokens at render | Protects readers even if the files are wrong | Hides the defect in the data; couples the site to a pipeline quirk while research content is slated to move repos |

**Recommendation**: O1 + O2 + O3; not O4. O2 is the fix, O1 lowers how often O2 has to act, O3 is the gate for anything O2 misses.

**Published bodies**: hand edit, not a pipeline re-run. A `claim-refresh` today resets status to draft, wipes `human_review`, can change the verdict with no corrections entry and overwrites `seo_title` (RF7, RF8), which is worse than the defect. The edit is formatting only, no finding changes, so no `corrections` entry (the corrections page promises one "when a claim changes").

### T1: citation cleaner

- Failing tests first: `tests/test_citations.py` (new), pure function:
  - `test_bracket_token_replaced_with_title`: `"...or lower【2025/ai-safety-index-summer-2025】."` with that id titled "2025 AI Safety Index" gives `"...or lower (*2025 AI Safety Index*)."`; no `【` remains.
  - `test_adjacent_bracket_tokens`: two tokens back to back give two titles joined with "and".
  - `test_unknown_bracket_id_removed_and_reported`.
  - `test_source_n_with_nbsp`: `"Source 1"` replaced with source 1's title.
  - `test_source_n_colon_title_keeps_one_title`: `"(Source 1: *Where are Brave's sync servers located?*)"` gives `"(*Where are Brave's sync servers located?*)"`.
  - `test_sources_list`: `"Sources 2, 4"` and `"Sources 6 and 7"` give titles joined with "and".
  - `test_out_of_range_left_and_reported`: `"Source 9"` with 6 sources is left as is and returned as unresolved (O3 catches it).
  - `test_open_source_3d_untouched`: `"open Source 3D printer"` unchanged.
- Change: `analyst/citations.py` (new), `clean_citations(text: str, sources: list[dict]) -> tuple[str, list[str]]` (cleaned text, unresolved tokens). Source N maps to `sources[N-1]`, the order `build_analyst_prompt` lists them (`analyst/agent.py:283-285`). After T2 the prompt has no numbers, so listing order is what a model counting headings would mean.
- Commit: `feat(analyst): convert citation tokens and Source N references to titles`

### T2: prompt and instructions

- Failing test first: `tests/test_analyst.py::test_prompt_has_no_numbered_source_headings`: `build_analyst_prompt` output contains each title as a `### ` heading and the `Source id:` line, and no `### Source 1`. Fails today.
- Change: `analyst/agent.py:285` heading to `### {title}`; `analyst/instructions.md:110` becomes: "Cite sources by title in italics, for example *AWS Cloud Sustainability*. Never write source ids, bracketed tokens such as 【2026/example】, or numbered references such as \"Source 3\"." The auditor prompt (`auditor/agent.py:48`) keeps its numbering; its text is not published.
- Commit: `fix(analyst): stop numbering sources in the prompt`

### T3: hand-fix the `ai-producers-existential-score` body

- `research/claims/subjects/ai-model-producers/ai-producers-existential-score.md:30-39`: replace the six tokens with titles from the source files (`2025/ai-safety-index-summer-2025` is "2025 AI Safety Index"; `2025/ai-safety-future-of-life-institute-risk-mitigation` is "AI Safety Report: Top 3 Companies Outpace Rivals In Risk"). Also delete the "Sub-question coverage" block (`:36-39`, internal ids `sq1` to `sq3`) (Q2).
- The Brave body is not hand-edited (Q3): Brandon's refresh in V1 replaces it after lane core and T5 land.
- No frontmatter change. Test: T4's citation rule (unit-tested first) passes on this file.
- Commit: `fix(claims): replace raw citation tokens in the existential-score claim`

### T4: lint rules (after T3 and the approved Brave refresh)

- Failing tests first, `tests/test_linter.py`:
  - `test_raw_citation_token_is_error`: body with `【2026/631793】` gives one `raw-citation-token` issue, severity `error`.
  - `test_numbered_source_reference_is_error`: bodies with `"Source 1"`, `"Source 2"`, `"Sources 4, 8"` each give a `numbered-source-reference` error; same for a `takeaway` containing `"Source 1"`.
  - `test_clean_body_no_issue` and `test_open_source_3d_no_issue`.
  - `test_level_claims_independent_with_none_in_pool`: claim with `verification_level: independently-verified`, two sources whose files say `first-party` and no overrides gives a `verification-level-pool-mismatch` warning; with one source `independent`, none; with an override turning the only independent source `first-party`, a warning; `multiply-verified` with one independent source, a warning.
- Change: `linter/runner.py:36-41`, `:89`, read claim bodies into a `claim_bodies` map; `linter/checks.py`, add `check_raw_citation_tokens(claim_files, claim_frontmatters, claim_bodies)` and `check_verification_level_pool(claim_files, claim_frontmatters, source_frontmatters)` (effective independence = override or file label, as `src/lib/sourceQuality.ts:58-75`); register both after `:136` in `linter/runner.py`.
- Commit: `feat(lint): flag raw citation references and levels the source pool cannot support`

### T5: wire the cleaner into `_analyse_claim`

- Failing test first: `tests/test_citations.py::test_analyse_claim_returns_clean_narrative`. `verdict_only_agent` overridden with a `TestModel`/`FunctionModel` whose verdict narrative contains `【id】` and `"Source 1"`; assert the `AnalystOutput` narrative and takeaway from `_analyse_claim` contain neither. Fails until wired.
- Change: `orchestrator/pipeline.py:905-924`, before both returns (`:918`, `:924`), run `clean_citations` on `verdict.narrative` and `verdict.takeaway` with the same `sources` list; log unresolved tokens at WARNING. Covers claim-refresh, onboard, `research_claim` and `dr step-analyze` (`orchestrator/cli.py:503`).
- Commit: `fix(pipeline): clean citation references in analyst output`

---

## Verification

Run from the repo root (`cd` as its own call first).

| Id | Command | Expect |
|----|---------|--------|
| V1a | `inv test` | All unit tests pass, including the new files `test_ingest_fetch_failure.py`, `test_source_id_collision.py`, `test_entity_independence.py`, `test_citations.py` |
| V1b | `pipeline/.venv/bin/dr lint --severity error` | No errors. Positive control: T4's unit tests prove the rule fires on U+00A0 input |
| V1c | `pipeline/.venv/bin/dr lint --severity warning` | No `verification-level-pool-mismatch` on published claims, or each one listed for Brandon |
| V1d | `inv check` | Types, build, markdown lint, citations, unit tests pass |
| V1e | `grep -rl '【' dist/research/claims` | No output. Control: `grep -l 'Evidence Summary' dist/research/claims/subjects/ai-model-producers/ai-producers-existential-score/index.html` prints the file, so the grep reads the built pages |

**End-to-end (Brandon runs)**: `pipeline/.venv/bin/dr claim-refresh brave-browser/renewable-energy-hosting`. Inspect:

1. Run log (`logs/`): every URL with an ERROR `Failed to fetch` either has a later successful archive fetch or shows `! ingest: ... fetch_failed`; no `Ingested:` line for a URL whose page never loaded.
2. `git status research/sources/`: no tracked or pre-existing source file modified; for each new id in the claim's `sources:`, the file's `url` matches the sidecar `sources_consulted[].url` for that id, and no two ids point to the same file.
3. Claim frontmatter: every brave.com or Brave Software source appears in `source_overrides` as `first-party` with a reason; `verification_level` is `claimed` or `self-reported` unless a source not published by Brave or its parent supports the claim; `cap_rationale` is present when capped.
4. Claim body and `takeaway`: no `【`, no "Source N"; `dr lint --severity error` still clean.
5. Claim page on the dev server (`inv dev`, port 4321): the source count line ("N sources (X company-published, Y independent)") agrees with the level.
6. The refresh replaces the published Brave claim (Q3). It lands as draft with a new `seo_title` and no review record (RF7, RF8): check the new `seo_title` reads correctly for the verdict, then `dr review --claim brave-browser/renewable-energy-hosting --approve` once satisfied. Then land T4.

## Needs from Brandon

| Id | Decision | Recommendation |
|----|----------|----------------|
| Q1 (answered 2026-10-04: both) | Add `parent_company: companies/brave-software` to `research/entities/products/brave-browser.md` (E3). Without it the forum thread (publisher "Brave Software" on `community.brave.app`) stays `independent`. Optionally also `aliases: [Brave]` on `companies/brave-software.md`, so a page labelled publisher "Brave" matches. | Yes to both |
| Q2 (answered 2026-10-04: delete) | In `ai-producers-existential-score`, also delete the "Sub-question coverage" block (pipeline ids `sq1` to `sq3` mean nothing to readers), or only fix the tokens. | Delete it; the Evidence Summary already says the same thing |
| Q3 (answered 2026-10-04: let the refresh replace it) | Brave published body: hand-edit now and keep it published (T3), with your end-to-end refresh as a throwaway check; or let the refresh replace it (draft status, new verdict, RF7/RF8 losses). | Hand-edit; discard the refresh output unless its verdict is clearly better |

## Out of scope (follow-ups)

RF5 (research drifts off the entity; scorer order), RF6 (verdict instability), RF7 (`seo_title`/`cap_rationale` overwritten on refresh), RF8 (no trail when a refresh changes a published verdict), RF9 (wrong "verdict disagreement" message), RF10 (key quotes not verbatim; only `validate_source_file` wiring is done here), RF11 (Wayback 429 treated as no snapshot), RF12 (stalled LLM call holds an ingest slot), RF13 (`dr step-analyze` not a faithful replay), RF14 (poor slugs), RF15 (`failed=` count), RF16 (sidecar model fields), RF17 (scorer omits candidates), RF18 (arXiv on single-product claims), RF19 (`---` in a source body), RF20 (analyst sees only the ingest summary). All tracked in `docs/UNSCHEDULED.md` § claim-refresh review findings. Code-review follow-ups RF21 to RF24 are tracked in the same section. Not yet tracked: the analyst writes a "Sub-question coverage" block with internal ids (`sq1` to `sq3`) into published bodies; add it to `docs/UNSCHEDULED.md` when this plan closes.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-04 | agent (claude-opus-5-5), self-review | implementation, iterated | Checked every path:line against HEAD `d57ae1d` and fixed seven stale line references. Moved RF1 disambiguation from write time to `_ingest_urls` (ids are used before writing, K1) and kept a write-time guard that preserves one id per input (K3). Chose per-claim `source_overrides` over editing file labels for RF3 so the site count agrees (K8, K9). Confirmed `brave-browser.md` lacks `parent_company` (added Q1). Confirmed level is model-chosen, so RF3 tests labels and adds a lint check. Ordered T4 after T3 so CI stays green. Dropped `[parallel]` checklist tags so only the Lanes section declares parallel work. Counted the Brave body's Source N references (four). |
| 2026-10-04 | agent (claude-opus-5-5, Claude Code session with Brandon) | implementation, second pass | Read RF1 to RF4 sections against the findings and spot-checked `orchestrator/cli.py:1087`, `src/content.config.ts:235` (`parent_company` exists in the schema; other product entities already set it). No changes to the steps. Added the untracked sub-question-coverage habit to Out of scope. Watch in F2: running `validate_source_file` in the refresh path may reject more sources than expected; the plan accepts that. |
| 2026-10-04 | agent (claude-opus-5-5, Claude Code session with Brandon) | implementation | Implemented S0, F1 to F3, C1 to C4, E1 to E4, T1 to T3 (two parallel lanes in worktrees, merged to main) and T5, all test-first; 846 unit tests pass. A /simplify pass (20512f3) moved the entity match and overrides from `verify_claim`/`research_claim` into `_analyse_claim` (one site, next to the T5 cleaner), replaced `fetch_succeeded` with `fetch_failure_reason`, and merged three URL-host helpers into `common/utils.url_host`/`host_matches`. Deviations: the entity match also rewrites an analyst override that was not first-party; step-ingest writes a host-prefixed file instead of failing on a slug taken by another URL; `test_research_integration.py` patches the fetch check because its fake ingestor never fetches. |
| 2026-10-04 | agent (claude-opus-5-5, Claude Code session with Brandon) | code review | `/code-review` (high) over 669dd71..1cca488: 10 findings. Fixed test-first: citation lists, single-pass cleaning, case handling and strip mode for `takeaway`/`cap_rationale` (f6dddc5, then 9ad59f0 keeps lowercase prose such as "the source 2 weeks ago" untouched); fetch check now requires the requested page or its archive.org copy (57d3679). Tracked as RF21 to RF24 in `docs/UNSCHEDULED.md`. Deferred to RF10: fetched page text is kept but key quotes are not yet checked. |
| 2026-10-04 | agent (claude-opus-5-5, Claude Code session with Brandon) | implementation | V1: Brandon ran `dr claim-refresh brave-browser/renewable-energy-hosting` and approved it (8940eba; unverified, low, self-reported; brave.com sources first-party via entity match). T4 lint rules landed test-first (2e97a0b, tidied in ebb4d6b); real repo lints with 0 errors and no new warnings. Open: the refreshed `seo_title` reads as an affirmation for an unverified verdict (RF7). |
