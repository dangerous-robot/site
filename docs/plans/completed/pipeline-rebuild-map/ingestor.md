# Pipeline map: the ingestor

Phase 1 (Challenge) reader output for the research pipeline rebuild (APP-1, the strangler approach: a new `pipeline/loop/` beside the old code). Facts carry `file:line`; paths are relative to the repo root. "Not found" means not on disk, not "does not exist".

Scope: `pipeline/ingestor/` (agent.py, validation.py, models.py, arxiv_affiliation.py, instructions.md, tools/wayback.py, tools/web_fetch.py), `pipeline/common/source_classification.py`, `pipeline/common/canonical_url.py`, `pipeline/common/blocklist.py`, `pipeline/common/publisher_quality.py`, `research/blocklist.yaml`, and the orchestrator code that drives them (`pipeline/orchestrator/pipeline.py:791-1381`, `persistence.py:97-270`, `cli.py:318-626`).

## 1. Entry points

| Entry | Location | What it does |
|---|---|---|
| `ingestor_agent` (PydanticAI agent, output `SourceFile`, 2 retries) | `pipeline/ingestor/agent.py:122-128` | The model reads a page through two tools and returns a `SourceFile`. Model name is `"test"` at definition; every caller overrides it (`pipeline.py:1190`, `cli.py:375`). |
| `web_fetch` tool | `agent.py:136-216` | Live GET or prefetched body; records text and errors on `IngestorDeps`. |
| `wayback_check` tool | `agent.py:219-263` | Archive lookup the model may call to recover a failed fetch. |
| `archive_after_ingest` | `agent.py:266-307` | Archive lookup run in code after the model finishes; sets `archived_url`. |
| `_ingest_one` | `pipeline/orchestrator/pipeline.py:1141-1238` | One URL: build deps, run the agent under the LLM semaphore and `ingest_timeout_s`, arXiv lab lookup, `_check_ingested_source`, archive lookup. |
| `_ingest_urls` | `pipeline.py:1241-1360` | Waterfall over the candidate pool, 2 concurrent, stops at `target` successes; same-page dedup within the batch; slug resolution. |
| `_ingest_claim_sources` | `pipeline.py:941-990` | Claim-level wrapper: `remaining = max_sources - cached`, coverage reorder, known pages, redirect reuse. |
| `_apply_url_dedup` | `pipeline.py:869-894` | Splits candidate URLs into cached-on-disk and to-ingest using the canonical URL index. |
| `_apply_blocklist_cap` | `pipeline.py:791-866` | Blocklist filter, entity-profile exemption, pool cap. Runs in the research step (`pipeline.py:1034-1041`), before ingest. |
| `_check_ingested_source` | `pipeline.py:1085-1138` | Accepts or rejects the model's output: fetch proof, URL rewrite, archived_url trust, quote check, arXiv relabel, `validate_source_file`. |
| `_build_source_dict` | `pipeline.py:1363-1381` | Source dict the analyst sees; derives `independence` from `classify_source_type`. |
| `dr step-ingest URL [--write\|--force] [--skip-wayback]` | `pipeline/orchestrator/cli.py:321-426` | Standalone one-URL ingest. Its own copy of the `_ingest_one` flow (see Duplication). |
| `dr ingest` (deprecated alias) | `cli.py:1743-1757` | Forwards to `step-ingest`. |
| `dr wayback-backfill [--recheck] <year>/<slug>...` | `cli.py:491-626` | Adds or re-checks `archived_url` on existing source files. |
| Light research (onboard) | `pipeline.py:2012-2032` | `_ingest_urls(..., archive=False)` on the seed or first search URL, only to get a summary; the SourceFile is discarded. |
| `build_source_url_index` / `load_source_dict` | `persistence.py:97-150` | The on-disk index and the cached-source reader. |
| `resolve_source_slugs` / `_write_source_files` / `source_markdown` | `persistence.py:198-270` | Source id collision handling and the file writer. |

Callers of `_ingest_urls`: `_ingest_claim_sources` (`pipeline.py:975`, used by both `verify_claim` at `:430` and `research_claim` at `:1693`) and light research (`:2016`, `:2027`). `onboard_entity` goes through `verify_claim` per template with a shared `onboard_url_index` (`pipeline.py:2689`).

## 2. Step list: one URL through the ingestor

1. **Blocklist and pool cap** (research step, before ingest): `_apply_blocklist_cap` loads `research/blocklist.yaml` (`common/blocklist.py:42-65`, cached per repo root), drops matching hosts as `StepError(step="research", error_type="blocked_host", retryable=False)` (`pipeline.py:847-856`), prepends `all_blocked` when nothing is left (`:857-865`), spares a blocklisted URL that is the entity's own profile post with a prefetched body (`:816-838`, recorded under `trace["blocklist_spared"]` `:842-846`), then cuts to `candidate_pool_size` keeping each sub-question's first two URLs (`_coverage_pool`, `:761-788`).
2. **Dedup against disk**: `build_source_url_index` scans `research/sources/*/*.md` and keys `canonical_key(url) -> "year/slug"` (`persistence.py:97-119`); `_apply_url_dedup` looks each URL up and loads the file as a source dict (`pipeline.py:869-894`). Cached sources skip the ingest entirely (no quote re-check, no archive lookup; see Hazards).
3. **Slot count**: `remaining = max(0, cfg.max_sources - len(cached_sources))` (`pipeline.py:958`); `max_sources` defaults to 8, `candidate_pool_size` to 32, and the config refuses a pool smaller than the target (`pipeline.py:278-279`, `:331-334`).
4. **Reorder by coverage**: `_order_by_coverage` fills the sub-question with the fewest sources first, counting dedup hits (`pipeline.py:727-758`, called at `:965-968`).
5. **Known pages**: every indexed URL of a cached source is passed as `known_pages` so a fetch that redirects to one does not count (`pipeline.py:969-982`).
6. **Waterfall**: `_ingest_urls` takes `urls[:candidate_pool_size]`, runs workers under a dispatch semaphore of 2 (`pipeline.py:1286-1287`), each calling `_ingest_one`; a success past `target` sets a stop flag but in-flight work finishes (`:1332-1336`, `:1350-1352`).
7. **Deps and prompt**: `IngestorDeps` carries the client, `requested_url`, `skip_wayback`, `allow_save`, `today`, and the one prefetched body if the researcher had Tavily `raw_content` (`pipeline.py:1175-1183`). The prompt is three lines: URL and today's date (`:1184-1188`).
8. **Agent run**: `ingestor_agent.run` under `asyncio.wait_for(timeout=cfg.ingest_timeout_s)` and the shared LLM semaphore (`pipeline.py:1190-1194`). `ingest_timeout_s` defaults to `ingest_budget_with_wayback_s()` (= 5+15+2+5+15+(15+20+30+30+6)+25 = 168 s) or 60 s with `--skip-wayback` (`pipeline.py:326-330`, `common/timeouts.py:46-75`).
9. **`web_fetch`** (`agent.py:136-216`): prefetched body returns immediately with empty title/description (`:166-177`); otherwise GET with redirects, terminal statuses 401/402/403/404/451 raise `TerminalFetchError` (`:131-133`, `web_fetch.py:22-41`); 429 sleeps 2 s and retries once, then raises (`:184-194`); binary content types (`application/pdf`, `octet-stream`, `msword`) are an error dict (`:32`, `:197-200`); HTML goes through `extract_page_data` (`web_fetch.py:44-75`: strips nav/footer/script/style/header/aside, 50,000-char cap, title from og:title or `<title>`, description, author, published_time from `article:published_time` or `datePublished`). Recorded text is title + description + text (`agent.py:205-207`); `final_url` is set only for a live fetch of the requested page (`:208-209`). Other `httpx.HTTPError`s become error dicts so the model can call `wayback_check` (`:213-216`).
10. **`wayback_check`** (`agent.py:219-263`): runs `find_or_save_archive` (no freshness limit); records archive.org failures to `wayback_failures` and an `acquisition_writes[url]` record when an existing capture was found (`:255-260`); remembers the link as `wayback_link` when it is for the requested page (`:261-262`). Instructions tell the model to call it only to recover a failed fetch (`instructions.md:32-33`) and not after a terminal status (`:44-47`).
11. **Model output**: `SourceFile{frontmatter, body, slug, year}` (`ingestor/models.py:42-48`); frontmatter validators: URL scheme, summary max 200 chars and 30 words (`models.py:26-39`). `kind` is `common.models.SourceKind` with 8 values including `paper` (`common/models.py:137-145`); the instructions list 7 (`instructions.md:16`, no `paper`).
12. **Slug override**: `slug_from_url(url)` replaces the model's slug whenever the URL has a path tail (`pipeline.py:1196-1198`, `common/utils.py:17-27`); `dr step-ingest` does not do this (`cli.py:384-409`).
13. **arXiv affiliation**: `arxiv_corporate_lab` fetches `arxiv.org/html/<id>` (throttled with the arXiv search bucket), reads `.ltx_authors`, and names the first corporate lab unless an academic affiliation comes first (`ingestor/arxiv_affiliation.py:33-76`, `source_classification.py:334-398`). Never fails the ingest.
14. **`_check_ingested_source`** (`pipeline.py:1085-1138`), in order: reject as `fetch_failed` when `fetch_failure_reason` says the requested page (or its archive copy) never yielded text (`agent.py:105-119`); overwrite `frontmatter.url` with the requested URL (`:1108-1113`); drop a model-written `archived_url` unless it equals `deps.wayback_link` (`:1117-1121`); `drop_unfound_quotes` against `requested_page_text` (`:1122-1123`; dropped quotes go only to a log warning); arXiv lab relabel sets publisher and `independence=first-party` (`:1124-1128`); `validate_source_file` errors reject as `invalid_source` (`:1129-1135`).
15. **Quote verification** (`ingestor/validation.py:106-271`): folds Unicode (NFKC, html unescape, dash and quote-mark map `:94-98`, `:252-254`), strips Markdown markup from prefetched bodies (`:257-264`), unwraps wrapping quotation marks and an attribution tail (`:128-163`), matches fragments split on ellipses with at most 300 elided chars and at least 3 words per interior fragment (`:102-103`, `:192-223`), word-boundary aware and tolerant of a newline inside a word (`:226-238`). Kept quotes are stored bare (`:121`).
16. **`validate_source_file`** (`validation.py:26-75`): URL equals input, slug regex, year in 2000..current year, `archived_url` starts with `https://web.archive.org`. No warnings are produced today (`warnings` list exists, nothing appends to it).
17. **Error mapping in `_ingest_one`**: timeout -> `timeout`; `TerminalFetchError` -> `http_<status>` non-retryable; other exceptions -> `http_error` if the class name contains "HTTP" else `model_error` (`pipeline.py:1204-1221`).
18. **Archive lookup in code** (`archive_after_ingest`, `agent.py:266-307`), outside the semaphore and time limit (`pipeline.py:1224-1229`): skipped with `{"status":"not-attempted"}` under `skip_wayback`; after a live fetch, `archive_with_time_limit` with `max_age=90 days`, `not_before=published_date`, `also_same_as=final_url` (`:284-289`); otherwise reuses `wayback_link` if the model found one (`:290-292`); any exception clears the link and records `failed` (`:293-303`). Result goes to `notes.archive[url]` and from there to the sidecar `sources_consulted[].archive` (`persistence.py:751-752`).
19. **Archive lookup internals** (`tools/wayback.py`): TimeGate `web/<now>/<url>` without following redirects (`:128-173`); `check_capture` HEADs the `id_` replay, accepts only a `Memento-Datetime` replay with 200 of the same page, follows at most 3 captured-redirect hops that stay on the page or `also_same_as` (`:258-321`); on rejection, CDX `latest_ok_capture` with `filter=statuscode:200`, `limit=-25`, `fastLatest` (`:324-373`); Save Page Now by GET `/save/<url>` needing a dated snapshot link in `Location` or `Content-Location` (`:186-220`); no save after any 429 (`:467`); a stale capture is replaced only when the refresh save succeeds and checks (`:469-481`). Whole lookup under `archive_lookup_budget_s()` = 101 s (`:493-520`, `timeouts.py:63-79`).
20. **Side channels drained**: `acquisition_writes` merged into `research_trace["acquisition"]` (`pipeline.py:1233-1234`, `:1056-1069`); `wayback_failures` promoted to `StepError(error_type="wayback_unavailable")` only when the URL's ingest itself failed (`:1339-1348`).
21. **Batch dedup**: `_same_page_as_kept` compares the requested and final URL keys with `kept_pages` (seeded from `known_pages`); a hit is an alias, not a result (`pipeline.py:1297-1301`, `:1322-1327`). `kept = results[:target]`; aliases of unkept results are deleted (`:1352-1356`).
22. **Slug resolution**: `resolve_source_slugs` picks slug, `<host>-<slug>`, `<host>-<slug>-2`... against disk and the batch; a file with the same canonical URL reuses its slug (`persistence.py:162-215`), called before the analyst sees ids (`pipeline.py:1357-1359`).
23. **Redirect reuse**: `_reuse_stored_redirect_targets` moves a fresh source whose `final_url` is indexed into `cached_sources` (`pipeline.py:909-938`).
24. **Source dict**: `_build_source_dict` computes `source_type` from publisher and kind, and `independence` from the model's value else the proxy (`pipeline.py:1363-1381`). `load_source_dict` does the same for cached files (`persistence.py:122-150`).
25. **Entity match** (not ingestor code, but the second half of the independence label): `_apply_entity_match` relabels per claim (`pipeline.py:556-623`) using `entity_first_party_reason`, `publisher_named_in_claim`, `source_engages_entity`, `entity_affiliated` (`source_classification.py:212-310`).
26. **Write**: `source_markdown` adds `source_type` and fills a missing `independence` (`persistence.py:218-229`), wraps bare links (`common/markdown_links.py:59`), `_write_source_files` opens with `"x"` and re-resolves on collision (`persistence.py:232-270`). Uncited fresh sources are never written (`pipeline.py:196`, `:1572-1615`).

## 3. Source classification and independence labels

| Rule | Location |
|---|---|
| `classify_source_type(publisher, kind)`: substring lists for primary (12 names + `sec.gov`), secondary (13), tertiary (6); `documentation` -> primary; `blog` -> tertiary; default secondary | `source_classification.py:18-100` |
| `independence_for_source_type`: primary -> first-party, secondary -> independent, tertiary -> unknown | `:103-115` |
| Where the proxy runs: analyst dict (`pipeline.py:1364-1368`), cached dict (`persistence.py:137-138`), file write (`persistence.py:221-226`) | three call sites |
| `classify_url_publisher_quality`: same name lists matched against the hostname, plus forum hosts; a scorer hint only | `common/publisher_quality.py:21-40`, used at `researcher/decomposed.py:311` |
| Entity identity: names (normalized, inc/llc/ltd stripped) and website hosts | `source_classification.py:120-146`, built by `entity_identity_for` (`orchestrator/entity_resolution.py:63`) |
| Profile platforms and handle rules (LinkedIn, X, Facebook, Instagram, YouTube) | `:150-209` |
| `entity_first_party_reason`: host match, profile handle, publisher equality | `:212-231` |
| Off-entity: `publisher_named_in_claim`, `source_engages_entity` (title+summary+quotes+body, whole word or host), `entity_affiliated` (brand label without a public-suffix list, `_brand_label` `:284-291`) | `:237-310` |
| `effective_independence`: override else file label, one entry per ref | `:313-327`; mirrors `src/lib/sourceQuality.ts:58-73` |
| Corporate lab patterns and academic-first rule | `:334-398` |
| Label distribution on disk (121 files found by `research/sources/*/*.md`; 112 tracked): `first-party` 51, `independent` 58, `unknown` 9, 3 files without `independence`; `source_type` primary 55 / secondary 56 / tertiary 10; `kind` article 50, documentation 28, report 18, blog 15, index 5, paper 4, video 1; 11 files without `archived_url`; 3 without `key_quotes` | counted 2026-10-14 (the task text says 136 sources; 136 not found on disk) |

Documentation of the rules: `docs/architecture/source-quality.md:50-98` (the proxy, entity match, arXiv rule), `docs/architecture/content-model.md:86-100` (source fields).

## 4. Config, flags and command contract today

| Knob | Default | Where |
|---|---|---|
| `max_sources` | 8 | `pipeline.py:278`; CLI `--max-sources` on claim-probe, claim-draft, claim-refresh, onboard (`cli.py:881`, `:935`, `:1035`, `:1768`) |
| `candidate_pool_size` | 32, must be >= `max_sources` | `pipeline.py:279`, `:331-334` |
| `skip_wayback` | False | `pipeline.py:284`; `--skip-wayback/--wayback` on the claim commands, `--skip-wayback` on step-ingest |
| `allow_save` | True; False for `dr claim-probe` and `dr step-ingest` without `--write` | `pipeline.py:285-287`, `cli.py:904-906`, `:363-372` |
| `ingest_timeout_s` | 168 s with wayback, 60 s without; `dr step-ingest` hardcodes 120 s | `pipeline.py:326-330`, `cli.py:376` |
| `ingestor_model` | falls back to `--model`; `DR_INGESTOR_MODEL` env | `cli.py:198`, `pipeline.py:336-338` |
| Dispatch concurrency | 2 ingests at once, inside the shared `llm_concurrency` (8) semaphore | `pipeline.py:1287`, `:315` |
| HTTP timeouts | connect 5, read 15, write 5, pool 5; wayback check 15, save 30, verify 10, CDX 30; 429 retry 2 s | `common/timeouts.py:22-32` |
| `SNAPSHOT_MAX_AGE` | 90 days | `wayback.py:71` |
| Blocklist | 13 hosts (paywalls, LinkedIn, 6 PR wires) | `research/blocklist.yaml:8-36` |

Documented behaviour the rebuild must keep saying the same thing: AGENTS.md:185 (which commands capture), `docs/runbook.md:84-92` (archive links), `docs/architecture/research-flow.md:67-76` (quote rules, ingest order), `pipeline/README.md:33-35` (blocklist).

## 5. Tests that pin this subsystem

| File | Tests | Covers |
|---|---|---|
| `tests/test_ingest_fetch_failure.py` | 24 | fetch proof, archive-copy text, quote checks end to end, step-ingest behaviours, arXiv relabel |
| `tests/test_ingest_urls.py` | 12 | target stop, coverage ordering, thin sub-question first |
| `tests/test_ingest_validation.py` | 26 | `drop_unfound_quotes`, unwrapping, ellipses; `validate_source_file` has no direct tests (UNSCHEDULED.md:422) |
| `tests/test_archive_after_ingest.py` | 10 | archive record statuses, stale refresh, no save when off |
| `tests/test_tools.py` | 73 | `extract_page_data`, TimeGate, 429, `find_or_save_archive`, budgets, Save Page Now, `wayback_check` tool, acquisition drain, capture checks, CDX, freshness |
| `tests/test_terminal_fetch.py` | 13 | terminal status handling |
| `tests/test_prefetch.py` | 4 | prefetched bodies |
| `tests/test_source_url_dedup.py` | 29 | index, cached dicts, dedup, target cap, redirects (batch and stored) |
| `tests/test_source_id_collision.py` | 11 | slug resolution, write guard, step-ingest `--force` |
| `tests/test_blocklist.py` | 13 | host matching and YAML loading |
| `tests/test_canonical_url.py` | 40 | canonical forms |
| `tests/test_classify_source_type.py` | 40 | the proxy lists |
| `tests/test_entity_independence.py` | 52 | entity match, off-entity, level fit |
| `tests/test_source_bare_links.py`, `test_step_error_vocab.py`, `test_ingestor_models.py` | 4, 4, 15 | link wrapping, error vocabulary, model validators |
| `tests/conftest.py:63-159` | | Fixtures: stubbed ingest model with/without `wayback_check`, capture replay mock |

## 6. Duplication

| What | Locations |
|---|---|
| The one-URL ingest flow (deps, prompt, agent run, arXiv lookup, `_check_ingested_source`, archive lookup) written twice; the CLI copy skips `slug_from_url`, hardcodes 120 s, and maps every exception to "agent failed" | `pipeline/orchestrator/pipeline.py:1141-1238` and `pipeline/orchestrator/cli.py:367-422` |
| The ingest prompt string | `pipeline.py:1184-1188`, `cli.py:373` |
| Source dict shape (title, publisher, summary, key_quotes, body, slug, url, source_id, kind, independence) built twice and kept in sync by comment | `pipeline.py:1363-1381` (`_build_source_dict`), `persistence.py:122-150` (`load_source_dict`) |
| `source_type` + `independence` proxy applied at three points | `pipeline.py:1364-1368`, `persistence.py:137-138`, `persistence.py:221-226` |
| Publisher name lists used for two different classifiers (post-ingest publisher string vs pre-ingest hostname) | `source_classification.py:18-64` imported by `publisher_quality.py:5-9` |
| Host blocklist filtering run twice with the same `filter_urls`: entity `search_hints.exclude` in the researcher, then `research/blocklist.yaml` in the orchestrator; each has its own "spare the entity's profile post" branch | `researcher/decomposed.py:593-612`, `pipeline.py:813-838` |
| Independence counting rule in Python and TypeScript | `source_classification.py:313-327`, `src/lib/sourceQuality.ts:58-73` |
| Archive lookup launched from two places on one ingest (model's `wayback_check`, then `archive_after_ingest` after a live fetch) | `agent.py:247`, `agent.py:294` (UNSCHEDULED.md:433 "Archive lookup runs twice on one ingest") |
| "Where the live page ends" fetched separately by `dr wayback-backfill` because the ingest's `final_url` is never stored | `cli.py:532-545`; `IngestorDeps.final_url` (`agent.py:73`) reaches only the in-memory index (`pipeline.py:202-203`) |
| Research step + ingest step sequence (dedup, cached loop, source dict, addresses) in `verify_claim` and `research_claim` | `pipeline.py:422-450`, `pipeline.py:1687-1713` (also UNSCHEDULED.md:316) |
| `sources_consulted` entries built in `_build_sources_consulted` and again by hand in `dr step-audit` | `persistence.py:707-754`, `cli.py:1614-1619` |

## 7. Hazards: what a rewrite could silently lose

| Hazard | Location |
|---|---|
| Fetch proof: a model may return a SourceFile with no fetch or after every fetch failed; only text from the requested page or its archive copy counts (`same_page_any_scheme`). Dropping this re-opens RF2 (invented summary cited as a source). | `agent.py:85-119`, `pipeline.py:1101-1104` |
| Model-written `archived_url` is dropped before validation (RF22); only a link `wayback_check` returned is trusted. | `pipeline.py:1114-1121` |
| Quote verification rules (fold, unwrap, ellipsis caps, word boundaries, inline-tag newlines, Markdown stripping for prefetched bodies). Documented at `research-flow.md:67`. | `validation.py:78-271` |
| Prefetched (Tavily `raw_content`) bodies bypass the live fetch; they carry no title/description and no `final_url`, so the archive lookup reuses the model's link or runs without freshness. The blocklist exemption for the entity's own profile post depends on this body existing. | `agent.py:166-177`, `:290-292`; `pipeline.py:816-838` |
| Terminal statuses (401/402/403/404/451, and 429 twice) must escape the agent as `TerminalFetchError`, not `httpx.HTTPError`, so the model never recovers them through `wayback_check` and the retry budget is not spent. | `web_fetch.py:22-41`, `agent.py:182-194`, `pipeline.py:1209-1217` |
| Archive capture acceptance: only a dated 14-digit snapshot that replays 200 with `Memento-Datetime` for the same page (path case counts); CDX fallback; no save after a 429; stale (90 days / before `published_date`) refreshed only after a live fetch and only when the refresh checks; `http://web.archive.org` normalised to https. RE-AI (Archive snapshot correctness) lives entirely here. | `wayback.py:118-125`, `:258-321`, `:393-404`, `:419-490` |
| `allow_save=False` for read-only commands (`dr claim-probe`, `dr step-ingest` without `--write`) so a dry run never makes archive.org capture a page; AGENTS.md:185 promises this. | `pipeline.py:285-287`, `cli.py:363-372`, `wayback.py:467`, `:484` |
| Archive lookup runs outside the LLM semaphore and ingest time limit, with its own 101 s budget, so a slow archive.org never turns a good ingest into a timeout. | `pipeline.py:1224-1229`, `wayback.py:493-520` |
| Archive failures reach the sidecar as `sources_consulted[].archive {status, error}` and `wayback_unavailable` errors only when the ingest itself failed; `acquisition` records are merged, not replaced, so research-stage `origin` survives (the Astro schema requires it). | `pipeline.py:1053-1082`, `:1339-1348`; `persistence.py:1013-1037`; `cli.py:1668-1699` (step-audit re-graft) |
| Requested URL is the dedup key: the model's `url` is overwritten with the requested one, and `final_url` is indexed after a write so a redirect target matches in the same run. | `pipeline.py:1106-1113`, `:198-203` |
| Canonical URL rules: `http`/`https` distinct except arXiv; `www.` and default ports stripped; path case kept; fragment dropped; 12 tracking params removed; arXiv abs/html/pdf/version/export all key as `https://arxiv.org/abs/<id>`. | `canonical_url.py:36-49`, `:54-114`, `:171-197` |
| `same_page_any_scheme` (scheme, default port, trailing-dot host ignored) is the archive matching rule; `canonical_key` is the dedup rule; `same_resource` is the slug-collision rule. Three different equality tests on purpose (docstring `canonical_url.py:16-27`). | `canonical_url.py:181-237` |
| Source id collisions: slug, then `<host>-<slug>`, then numeric suffix; a file holding another URL is never overwritten (RF1). `dr step-ingest --force` can only overwrite the same page. | `persistence.py:162-215`, `:246-266`; `cli.py:407-413` |
| arXiv corporate-lab relabel sets `publisher` to the exact lab name (the entity match compares by equality) and `independence=first-party`; academic-first affiliation wins; footnotes ignored. | `pipeline.py:1124-1128`, `arxiv_affiliation.py:43-51`, `source_classification.py:381-398` |
| Independence is two-stage: file-level proxy at ingest (entity-agnostic) plus per-claim entity match recorded as `source_overrides`. The file label must not change per claim. | `source_classification.py:103-115`, `pipeline.py:556-623`, `source-quality.md:60-74` |
| `effective_independence` counting (one entry per ref, repeated refs count twice) must match the site's `countSourcesByIndependence`. | `source_classification.py:313-327`, `src/lib/sourceQuality.ts:58-73` |
| Blocklist entries carry an operator-facing `reason` that lands in `blocked_host` errors; PR wires are blocked by design (source-quality "known failure mode"). | `research/blocklist.yaml:22-36`, `pipeline.py:847-856` |
| Coverage ordering and the "first two URLs per sub-question stay in the pool" rule shape which sources are tried. | `pipeline.py:727-788` |
| Dedup hits count toward `max_sources` (`remaining = max_sources - cached`), which RE-AL (Source pool and coverage quality) names as a defect (`v1.0.0-roadmap.md:336`): a rewrite should decide, not inherit. | `pipeline.py:958` |
| Successes finishing after the target are discarded with their paid archive save (`kept = results[:target]`). | `pipeline.py:1332-1336`, `:1352`; UNSCHEDULED.md:410 |
| Cached sources are never re-checked for quotes or archive links (RF10 remainder, `UNSCHEDULED.md:17` in the claim-refresh table). | `pipeline.py:869-894` |
| `summary` limits (30 words, 200 chars) and `key_quotes` 0-5 are enforced by the model schema and the Zod schema; `kind: paper` is accepted by both schemas but absent from the instructions. | `ingestor/models.py:23-39`, `src/content.config.ts:26-39`, `instructions.md:16-19` |
| Bodies get bare links wrapped (`MD034`); a stray `---` in a body still renders as a heading (RF19). | `persistence.py:227-229`, `markdown_links.py` |
| `IngestorDeps` buffers (`fetched_text`, `acquisition_writes`, `wayback_failures`) are per-run state; a retry wrapper must reset them (UNSCHEDULED.md:33 "retry Infomaniak null-body responses"). | `agent.py:37-77` |
| Year check rejects real pre-2000 reports (`invalid_source`, RF22 remainder). | `validation.py:62-67` |
| Light research must not archive the page it discards (`archive=False`) and ingests with no entity, so it spares nothing from the blocklist. | `pipeline.py:2016-2018`, `:2027-2031`; test `test_light_research_does_not_archive_the_page_it_discards` |
| Dropped key quotes are logged only; the review packet (Q6, interview) wants them beside the archived passage. | `pipeline.py:1122-1123`; UNSCHEDULED.md:413 |

## 8. Known defects on record that touch this subsystem

From `docs/UNSCHEDULED.md` (line numbers in that file): Infomaniak null-body retry for ingest (33); PDF attachment as an alternate content path, proposed drop (75-83); source-type edge cases (267-277); RF10 cached quotes (351), RF12 stalled slot (354), RF14 poor slugs (356), RF15 `failed` count (357), RF19 `---` body (361), RF20 analyst sees only the short body (362), RF21 slug rename window (373), RF22 pre-2000 year (374), RF25 lint vs fallback label (377), RF28 stale capture kept silently (364); beta.7 findings: profile namesake (408), ingest discards post-target successes (410), uncited sources refetched and archived every onboard run (412), dropped quotes only logged (413), model edits quotes so matcher drops them (414), `validate_source_file` untested (415), entity affiliation alias words (418), brand label without public-suffix list (419), host mention matches longer host (420), wayback stats count unchecked captures (422), archive lookup twice (423), `--recheck` removes before replacement (424), backfill fetches every live page (425), CDX slow (426), unwrapped quotes may lower a label (434); slug generation plan (458-471); newswire counted independent (roadmap RE-AL, `v1.0.0-roadmap.md:332`).

Interview facts that bear on the ingestor (`handoff/2026-10-13-pipeline-improvement-interview.md`): Q6 review packet wants every quote beside its archived passage with the check's pass/fail, and source independence at a glance (line 26); Q8 (D) folds side tools into about five commands, which would absorb `dr step-ingest` and `dr wayback-backfill` (line 28); Q10 says source file format and site URLs stay stable (line 30). The ad hoc path note records that "comparative claims never ingest the baseline half" (`handoff/2026-10-10-ai-energy-subject-claims.md:16`), a researcher gap rather than an ingest one.

## 9. Open questions

1. Does the new loop keep `dr step-ingest` and `dr wayback-backfill` as separate commands, or fold them (Q8 (D) in the interview says about five commands: draft, recheck, review, findings, lint)? Both have operator docs (`docs/runbook.md:84-92`, AGENTS.md:181-185) and tests (`test_source_id_collision.py:220-240`, `test_cli.py`).
2. Should cached (dedup-hit) sources be re-checked for quotes and archive links on reuse, or does `dr recheck --due` (Q7) own that? Today neither happens (`pipeline.py:869-894`).
3. Should the ingest's `final_url` be stored in the source file (or sidecar) so `dr wayback-backfill` and cross-run redirect dedup stop guessing (`cli.py:532-545`, RF23 remainder)? Q10 says the source format stays stable; one optional field may or may not count.
4. The slot rule `remaining = max_sources - cached` (RE-AL defect): count cached sources toward the target or not?
5. `kind: paper` exists in both schemas and on 4 files but not in `instructions.md:16`; which list is authoritative?
6. Is the file-level `independence` proxy (publisher substring lists, `source_classification.py:18-64`) to be kept, or does the new loop label independence only per claim through the entity match? The lint check and the site read the file label (`linter/checks.py:755-757`, `sourceQuality.ts:71`).
7. The task's "136 sources" is not what the disk shows (121 files, 112 tracked); which count is the plan's baseline?
