# Plan: SITE-J claims readiness (dedup, archive links, ClaimReview removal)

**Status**: `in progress` (approved for implementation 2026-10-07, see Decisions)
**Last updated**: 2026-10-07
**Serves**: SITE-J (Responsible AI chatbots, backed by claims), `docs/v1.0.0-roadmap.md` § SITE-J
**Line numbers**: code references are as of HEAD `4fa679b`, before the refresh-trail commits (`e6c96a5..e709800`) changed `pipeline/` and `src/`; re-read each file before editing it.
**Related plans (referenced, not absorbed)**: [`completed/published-claim-refresh-trail.md`](completed/published-claim-refresh-trail.md) (done), [`deferred/wayback-archive-job.md`](deferred/wayback-archive-job.md) (scheduled archival, deferred), `drafts/responsible-ai-chatbots-claims.md` (the page plan, local draft)

## Goal

Before the Responsible AI chatbots page cites published claims:

- one paper or page is stored, and counted, as one source;
- each cited source has an archive link, made in code rather than left to the model, and a failed archive lookup is recorded, not silent;
- claim pages emit no ClaimReview markup.

Not in this plan: the indexing flip (ending the pre-release noindex policy). Brandon decides it, and it is not considered until after 1.0.0 (`docs/decisions.md` 2026-10-07).

## Status checklist

- [x] CR1: arXiv abs/html/pdf URLs are one source
- [x] CR2: a fetch that redirects to an existing source reuses it
- [x] CR3: archive lookups run in code, retry HTTP 429 and are recorded
- [ ] CR4: archive links for the sources the page cites, and the other committed sources without one
- [ ] CR5: remove ClaimReview markup
- [x] CR6: backlog cleanup (run at promotion, before CR1)

## Steps

### CR1: arXiv abs/html/pdf URLs are one source

Merges the UNSCHEDULED rows "arXiv abs/html/pdf as one source" (Dedup detection) and "Canonicalize arXiv URLs at ingest" (arXiv ingest hardening).

Current state:
- `canonicalize` has no arXiv rule (`pipeline/common/canonical_url.py:40-100`) and keeps `http` and `https` distinct (`:7`).
- The arXiv search tool stores the Atom id as the URL, `http://arxiv.org/abs/{id}v{n}` (`pipeline/researcher/tools/arxiv.py:64-65`; fixture `pipeline/tests/test_arxiv_search.py:36`). Web search returns `https://arxiv.org/html/{id}v{n}` or `/abs/{id}`. Today these never match.
- PDF fetches are rejected (`pipeline/ingestor/agent.py:28`, `:175`), so `/pdf/` URLs matter only as a dedup lookup.
- `canonicalize` feeds two kinds of callers. Lookup keys go through `canonical_key` (`canonical_url.py:157`): the dedup index (`pipeline/orchestrator/persistence.py:81-103`), the run's `url_index` (`pipeline/orchestrator/pipeline.py:168-169`, `:652`) and the kept-URL merge (`pipeline/researcher/decomposed.py:502-506`). Page comparisons go through `same_resource` (`:165`): the check that the requested page was fetched (`agent.py:79`) and slug resolution (`persistence.py:171`, `:177`, `:234`). Search candidates merge on `canonicalize` directly (`decomposed.py:285`).
- No duplicate arXiv files are on disk: the two pairs the backlog row names were removed in `7780ace`, and `research/claims/chatgpt/` no longer exists. The one committed arXiv source is `research/sources/2025/250212447v1.md` (`https://arxiv.org/html/2502.12447v1`).

Change: the arXiv rule goes in `canonical_key` only. When the host is `arxiv.org` or `export.arxiv.org` and the path is `/abs/`, `/html/` or `/pdf/` followed by an arXiv id (new style `NNNN.NNNNN`, or old style `archive/NNNNNNN` with an optional `.SUBCLASS`, as in `math.AG/0601001`), with an optional `v{n}` and optional `.pdf` or trailing path, the key is `https://arxiv.org/abs/{id}` (no version, no query, no fragment). `canonicalize` and `same_resource` stay page-exact, so:
- the dedup index and `url_index` treat all versions and forms of one paper as one source; the stored file keeps the URL it was ingested from and needs no edit;
- `decomposed.py:285` keeps an abs and an html candidate apart, and `:502-506` merges them once kept;
- the fetched-page check is unchanged: fetching the abstract-only abs page does not satisfy a requested html or pdf URL;
- slug resolution is unchanged.

Update the `canonical_key` docstring and the module docstring to name the rule and its exception to the http/https rule.

Side effect: once kept, an abs and an html URL for one paper become one candidate, and the first variant stored is reused by later claims. The abs page carries only the abstract, and the backlog row "Detect corporate authorship on arXiv abstracts" (not in this plan) records an abs ingest that mislabeled independence. Accepted here; that row stays open.

Files: `pipeline/common/canonical_url.py`, `pipeline/tests/test_canonical_url.py`, `pipeline/tests/test_source_url_dedup.py`, `pipeline/tests/test_researcher_decomposed.py`, `pipeline/tests/test_ingest_fetch_failure.py`.

Verify:
- New unit tests, run first against current code and seen to fail: `canonical_key` of `abs/2502.12447`, `abs/2502.12447v2`, `http://arxiv.org/abs/2502.12447v1`, `html/2502.12447v1`, `pdf/2502.12447v1`, `pdf/2502.12447.pdf`, `export.arxiv.org/abs/2502.12447` is `https://arxiv.org/abs/2502.12447`; old-style `hep-th/9901001` and `http://arxiv.org/abs/math.AG/0601001v1` map to their abs keys; the key is idempotent.
- `canonicalize` of the same inputs is unchanged, `same_resource` of an abs and an html URL is false, and the existing `test_canonical_url.py` cases pass unchanged; a non-paper arXiv path (`https://arxiv.org/list/cs.AI/recent`) keys as today.
- `decomposed.py` test: abs and html candidates for one paper stay two candidates at `:285` and yield one kept URL at `:502-506`; the test asserts which one survives.
- Fetched-page test: requested `https://arxiv.org/html/2502.12447v1`, the stubbed model fetches only `https://arxiv.org/abs/2502.12447`; `fetch_failure_reason` returns a reason (passes before and after; it guards the choice above).
- Dedup test: temp repo holding a copy of `250212447v1.md`; `_apply_url_dedup(["http://arxiv.org/abs/2502.12447v1"], index, root)` returns it as cached and nothing to ingest (`pipeline.py:635-659`).

### CR2: a fetch that redirects to an existing source reuses it

Merges the UNSCHEDULED row "Stored redirect target (RF23 remainder)" (Dedup detection) and RF23 (claim-refresh review findings follow-ups).

First, rerun the legacy check: for every commit touching `research/claims/*.audit.yaml`, compare each `sources_consulted[].url` (the requested URL) with `url` in `research/sources/{id}.md` at that commit, and for each mismatch run `curl -s -o /dev/null -L -w '%{url_effective}' <requested>` to see whether the stored URL is its redirect target. At `4fa679b` (41 commits; all 29 committed ids have a requested URL on record) it found none on current ids: their two mismatches, `2025/ai-safety-index-summer-2025` and `2026/about`, are different pages that once shared a slug. Control: it does catch a since-deleted file, `2026/voluntary-commitments`, stored as `anthropic.com/transparency/voluntary-commitments`, where the requested `anthropic.com/voluntary-commitments` redirects. If the rerun finds one, fix that file's `url` by hand; no migration code is planned.

Current state:
- Partly fixed by `3c6d0e5`: new ingests store the requested URL, not a redirect target the model echoes (`pipeline.py:745-752`). The dedup index matches by canonical URL (`904c376`).
- What remains: (a) a request that redirects to a page already stored under its final URL misses the index and writes a duplicate; (b) two requested URLs that redirect to one page each get a file, within one claim's batch or across claims of one run.
- `web_fetch` follows redirects (`agent.py:156`, `:166`) but never records the final URL (`resp.url`). Prefetched bodies from Tavily skip the fetch (`:143-154`), so they carry no redirect information.
- `research_claim` (`dr claim-draft`) writes through `_write_source_files` (`pipeline.py:1234`, `:1241`), not `persist_sources`, and builds its source ids only from the cached and fresh maps (`:1241-1250`), so a URL in neither is silently skipped.
- Slug resolution compares only the stored `url` (`persistence.py:158-179`).

Change:
- `IngestorDeps` gains `final_url: str | None`, set from `str(resp.url)` only when `web_fetch` loads the requested URL live; not for an archive.org copy and not for a prefetched body (`agent.py:34-61`, `:114-187`).
- `_ingest_urls` (`pipeline.py:845-930`) returns the requested-to-final URL map and merges by final URL: a result whose canonical final URL matches an earlier result's requested or final URL is dropped, logged `dedup-hit (redirect)`, does not count toward `target`, and is returned in an alias map (dropped URL to kept URL).
- One helper, called by `verify_claim` (after `:387-394`) and `research_claim` (after `:1187-1194`): a fresh source whose final URL hits `url_index` (and whose file loads) moves to `cached_sources` and is not written. Both callers fold an alias's `ro.url_addresses` into the kept source and resolve aliases when building source ids.
- `persist_sources` also indexes the final URL (`pipeline.py:155-170`), so later claims in an onboard run reuse it.

Not covered: case (b) across runs (it needs the final URL stored in source frontmatter, a schema change), and prefetched bodies. The fetch still happens before the match; this step prevents the duplicate file and double count, not the fetch.

Files: `pipeline/ingestor/agent.py`, `pipeline/orchestrator/pipeline.py`, `pipeline/tests/test_source_url_dedup.py`.

Verify:
- Unit test, seen to fail on current code, through both `verify_claim` and `research_claim`: temp repo with a source file whose `url` is `https://example.org/new`; an `httpx.MockTransport` answers `https://example.org/old` with a 301 to `/new` and a page; with the ingest model stubbed, the claim's source ids contain the existing id, and no new file appears under `research/sources/`.
- Same-batch test: two requested URLs redirecting to one page in one `_ingest_urls` call give one result and an alias for the other; with `target=2` and a third URL, the third is ingested too.
- Control: a request that does not redirect still writes a new file.

### CR3: archive lookups run in code, retry HTTP 429 and are recorded

RF11, first half (claim-refresh review findings table).

Current state:
- `check_archive_org_timegate` treats any status other than a redirect or 5xx as "no snapshot" with no error (`pipeline/ingestor/tools/wayback.py:76-93`), so HTTP 429 is a silent miss.
- `save_to_wayback` has no retry and returns `None` with only a log line (`wayback.py:96-126`).
- The lookup runs only if the ingest model calls `wayback_check` (`agent.py:191`); `pipeline/ingestor/instructions.md:10` and `:31` ask the model to fill `archived_url` whenever possible. `wayback_check` records every TimeGate hit as a recovery in `acquisition_writes` (`agent.py:225`).
- Ingest runs in two places: `_ingest_one` (`pipeline.py:765`; model call under the LLM semaphore at `:807-810`, limit `cfg.ingest_timeout_s`) and `dr step-ingest` (`pipeline/orchestrator/cli.py:321-418`), which runs the agent directly with a fixed 120 s limit (`:372`). The page plan's S7 creates cited sources with `dr step-ingest`.
- Archive failures on a successful ingest are dropped by design (`_ingest_urls` docstring, `pipeline.py:871-874`).
- 6 of 29 committed source files have no `archived_url`: `2016/announcement-100`, `2025/1441254323968196`, `2025/brave-website-challenge`, `2025/fli-index-2025-winter-anthropicpdf`, `2026/clean-energy-resources-meet-data-center-electricity-demand`, `2026/soc2`.
- The ingest budget with archive lookups is 112 s (`pipeline/common/timeouts.py`, `ingest_budget_with_wayback_s`).

Change:
- TimeGate: 429 returns an `error` (`archive.org TimeGate check failed (HTTP 429)`) after one retry, waiting `Retry-After` capped at `RATE_LIMIT_RETRY_S`, or `RATE_LIMIT_RETRY_S` when absent.
- Save: the same single retry on 429; return the failure reason with the result so `wayback_check` can append it to `wayback_failures`.
- One helper in `wayback.py` does the lookup in code: TimeGate, then save on a miss, and no save after a TimeGate 429. It sets `archived_url` on the source and does not write `acquisition_writes` (it is not a recovery). It honors `skip_wayback`, and it skips a source only when `wayback_check` returned a link during this ingest (tracked on `IngestorDeps`), so an `archived_url` the model wrote on its own is replaced, or cleared when the lookup fails. It runs under its own limit, `archive_lookup_budget_s()` in `timeouts.py` (check, save and the retry wait), so the ingest budget does not grow for it. Cost: when archive.org is slow, each fresh ingest (including one later dropped past `target` or as a redirect duplicate) holds one of the two waterfall slots up to that limit longer, about 50 s.
- Callers: `_ingest_one` after `wait_for` and a successful `_check_ingested_source`, outside `async with sem`; `dr step-ingest` after its check, printing a failure as an error line. In read-only mode (no `--write`) it runs the TimeGate check only and never calls Save Page Now, so a dry run makes no archive.org capture.
- `instructions.md:10` and `:31`: the model calls `wayback_check` only to recover a failed fetch and leaves `archived_url` empty unless `wayback_check` returned one (otherwise two lookups run, up to about 90 s).
- `ingest_budget_with_wayback_s` gains the retry time, for the model's recovery call only.
- Record the outcome on the sidecar's `sources_consulted` entry: an optional `archive` object with `status` and, when failed, `error`. `found`: the helper or a recovery `wayback_check` returned a link. `failed`: 429 after the retry, another error, or the helper's time limit. `not-attempted`: `skip_wayback` only. Cached (dedup-hit) entries carry no `archive` object; CR4's listing covers files without a link. The refresh-trail plan adds `audit.*`, `refresh` and `human_review.verdict_override` to the same files: re-read the Python writer (`persistence.py:415-458`), the site schema (`src/content.config.ts:45-58`) and the sidecar table in `docs/architecture/content-model.md` at implementation time, and add `archive` to whatever `sources_consulted` entry shape exists then.
- `dr wayback-backfill SOURCE_ID...` runs the helper on existing source files and writes `archived_url` into each (used by CR4). Add it to the `dr` command list in `AGENTS.md`. The name avoids the deferred job's `dr archive` and `dr review --archive` (`cli.py:1880`, which archives a claim).

Files: `pipeline/ingestor/tools/wayback.py`, `pipeline/ingestor/agent.py`, `pipeline/ingestor/instructions.md`, `pipeline/orchestrator/pipeline.py`, `pipeline/orchestrator/persistence.py`, `pipeline/orchestrator/cli.py`, `pipeline/common/timeouts.py`, `src/content.config.ts`, `AGENTS.md`, `docs/architecture/content-model.md`, `pipeline/tests/test_tools.py`, `pipeline/tests/test_terminal_fetch.py`, `pipeline/tests/test_cli.py`.

Verify:
- Unit tests with `httpx.MockTransport`, seen to fail on current code: TimeGate 429 then 302 gives `available: True` and two requests; 429 twice gives an `error` containing `429`, and the helper then sends no save request; save 429 twice returns a reason.
- Sidecar tests (Python), seen to fail first, reading the YAML back (a passing build proves nothing: the site schema is not `.strict()` and drops unknown keys). With a stubbed model that never calls `wayback_check`: a mock archive returning a snapshot gives the source an `archived_url`, the entry `archive.status: found` and no `acquisition`; a mock archive answering 429 gives `archive.status: failed` and an `error` containing `429`. With `skip_wayback=True`: `archive.status: not-attempted` and no archive request. A dedup-hit entry has no `archive`.
- `dr step-ingest` test (`CliRunner`, stubbed model, mock archive): the printed source has `archived_url`; with `--skip-wayback`, no archive request is made.
- The zod schema gains the `archive` object. A temporary fixture (one committed sidecar entry edited to `archive: {status: bogus}`) fails `npm run build`; the edit is reverted after.
- A new timeout test: `ingest_budget_with_wayback_s()` includes the retry time and `archive_lookup_budget_s()` covers check, save and the retry wait (no timeout test exists today).
- Live, best effort: `dr step-ingest <url>` while `curl -I https://web.archive.org/` returns 429 prints the error line instead of a silent miss.

### CR4: archive links for the sources the page cites

RF11, second half (one-time backfill).

Current state: no command fills `archived_url` on existing files (`dr` has no archive subcommand; `cli.py`). The deferred `dr archive` job is not built. The page cites no sources yet; its cited set comes from the page plan's S7 and S10 (`drafts/responsible-ai-chatbots-claims.md`).

Change: once the cited set exists, run `dr wayback-backfill` on each cited source without an `archived_url` (`https://web.archive.org/...`; the domain is checked by `pipeline/ingestor/validation.py:73-77`). A source that cannot be archived gets its reason recorded in this plan's checklist line, not left blank. Also run it now on the 6 committed sources without a link (orchestrating session's default, 2026-10-07: cheap, and every source page gains an archived copy); this part does not wait on the page plan.

Files: the 6 committed sources without a link, and source files under `research/sources/` cited by `src/content/resources/responsible-ai.md`.

Verify:
- Control, run first: `git ls-files 'research/sources/*.md' | xargs grep -L '^archived_url:'` lists the 6 known gaps. It covers committed files only; the untracked US data center research in the tree belongs to another session and is out of scope.
- After: the listing is empty, except sources whose reason is recorded.
- `curl -sI` on a sample of 3 new archive links returns 200 or a 30x into `web.archive.org`.
- `dr lint` and `npm run build` pass.

### CR5: remove ClaimReview markup

Brandon's decision (2026-10-07): Google removed ClaimReview rich results from Search in 2025, and Fact Check Explorer listing is limited to approved fact-check publishers, so the markup costs upkeep and returns nothing today. Verdicts and ratings stay in the claim files, so it can be added back.

Current state:
- The claim page builds ClaimReview JSON-LD at `src/pages/research/claims/[...slug].astro:101-120` and emits it at `:278` for every claim that is not draft or archived, so a blocked claim emits it too.
- `VERDICT_RATINGS` (`src/lib/verdict.ts:38-46`) and the `type Verdict` import (`[...slug].astro:8`) are used only by that block; `VERDICT_LABELS` is also used at `:150`.
- Docs that mention it: `docs/plans/seo-external.md` (gates, Rich Results tests, GSC monitoring, Fact Check program row, GDELT note), `docs/plans/completed/published-claim-refresh-trail.md` (Out of scope), `docs/UNSCHEDULED.md` "SEO basics" (Site gaps) and the deferred `research-outputs-improvement-plan.md` row.

Change:
- Re-read the page first (the refresh-trail work touches `src/`). Delete the `claimReview` object and its `<script type="application/ld+json">`, and drop `VERDICT_RATINGS` and `type Verdict` from the import; keep `VERDICT_LABELS`.
- Delete `VERDICT_RATINGS` from `verdict.ts` if nothing else uses it.
- Update the docs above to state that claim pages emit no ClaimReview markup; drop ClaimReview from `seo-external.md`'s gates and test lists (the rest of that plan is post-1.0 with the indexing flip).

Files: `src/pages/research/claims/[...slug].astro`, `src/lib/verdict.ts`, `docs/plans/seo-external.md`, `docs/plans/completed/published-claim-refresh-trail.md`, `docs/UNSCHEDULED.md`.

Verify:
- Before the change: `npm run build`, then `grep -rl '"ClaimReview"' dist/research/claims/ | wc -l` prints the number of non-draft, non-archived claim pages (control: the check finds the markup).
- After: the same command prints 0; `npm run check` passes; one claim page still shows its verdict and reviewer.
- `grep -rn "ClaimReview" src/` prints nothing.

### CR6: backlog cleanup (run at promotion, before CR1)

When Brandon approves this plan and it moves to `docs/plans/site-j-claims-readiness.md`. Re-read `docs/UNSCHEDULED.md` and the roadmap right before editing; other sessions edit both.
- `docs/UNSCHEDULED.md`: remove the rows "arXiv abs/html/pdf as one source", "Stored redirect target (RF23 remainder)", "Canonicalize arXiv URLs at ingest" and the "ClaimReview markup" bullet (Site gaps). In the claim-refresh findings table, RF11's Related cell names this plan (CR3, CR4) and RF23's names it (CR2), and both lose their `Triage:` marker, as RF8 and RF9 carry none for the refresh-trail plan. Keep "Detect corporate authorship on arXiv abstracts" (not SITE-J) and "Claim-level match on onboard".
- `docs/v1.0.0-roadmap.md` SITE-J: replace the RF11, dedup and ClaimReview lines with lines naming this plan's steps, and add `**Plan**:` for this file. Update RE-E's pointer to RF11 (`:161`) to point here.
- Inbound pointers to update: `docs/UNSCHEDULED.md` Deferred plans row for `wayback-archive-job.md` (RF11); the Deferred line in `docs/plans/deferred/wayback-archive-job.md:3`; `drafts/responsible-ai-chatbots-claims.md:247`, `:281`, and its S14, S17 and Q8 (the indexing flip is after 1.0.0 and Brandon's call); `drafts/chatbot-guide-proposal.md:55-56` (local draft, optional).

Verify: `grep -n "in SITE-J" docs/UNSCHEDULED.md` matches no row this plan covers; `grep -rn "RF11\|RF23" docs/` shows only the findings tables, this plan and pointers to it.

## Order and dependencies

- CR6 first, at promotion.
- CR1 then CR2 (CR2's tests rely on `canonical_key`; both touch dedup tests).
- CR3 then CR4. CR4 also waits on the page plan's S7 and S10 (the cited set).
- CR5 is independent.
- `published-claim-refresh-trail.md` (done) and CR1 to CR4 must land before the page's first claims are published (the page plan's S15).

## Out of scope

- The scheduled archival job and `dr archive` framework (`deferred/wayback-archive-job.md`).
- Corporate authorship on arXiv abstracts; claim-level match on onboard.
- Storing the final URL in source frontmatter (CR2 case b across runs).
- The indexing flip and the external SEO validation that follows it (after 1.0.0, Brandon's call).
- The Google Fact Check program.

## Decisions (Brandon, 2026-10-07)

Recorded in `docs/decisions.md` 2026-10-07.

- The indexing flip is not considered until after 1.0.0, and Brandon owns it; it is out of this plan.
- Archive links are made in code after each ingest, plus a `dr` command for backfill (CR3, CR4).
- ClaimReview markup is removed, not validated (CR5).
- Implementation approved: Brandon asked for SITE-J to be implemented autonomously (2026-10-07, after the cross-review was launched); read as approval of this plan as cross-reviewed. Two orchestrator defaults, easy to reverse: read-only `dr step-ingest` never calls Save Page Now; CR4 also fills the committed sources without a link.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-07 | agent (claude-opus-5-5) | implementation | First draft at HEAD `a64672c`. Checked against `canonical_url.py`, `arxiv.py`, `ingestor/agent.py`, `wayback.py`, `timeouts.py`, `orchestrator/pipeline.py`, `persistence.py`, `validation.py`, `seo.ts`, `astro.config.ts`, the claim page, `verdict.ts`, `content.config.ts`, `package.json`, CI, git history of `research/sources/2025/`, and Google's fact-check documentation. Found the arXiv duplicates already removed (`7780ace`), the redirect case partly fixed (`3c6d0e5`), the archive lookup model-driven, and ClaimReview emitted for blocked claims. |
| 2026-10-07 | agent (claude-opus-5-5), self-review | implementation, iterated | Fresh-eyes pass: corrected the `agent.py` line refs; noted no timeout test exists, so CR3 adds one; CR5 now wires the check into `inv check` (`tasks.py:40-45`), not `inv lint`, which runs without a build; DEC3 cost stated from `timeouts.py`. Checked: step ids match the checklist; prefixes CR and DEC do not collide with the page plan (S, Q, T, D) or the refresh-trail plan (P, A, L, U, D, V); no em dashes. Advisor follow-up: confirmed all 3 published claims name a reviewer; CR1 names its effect on researcher candidate merging; CR3 records `not-attempted` separately from `failed` and verifies by reading the sidecar back (the site schema drops unknown keys); the `datePublished` rule is labeled a site rule. |
| 2026-10-07 | agent (claude-opus-5-5), orchestrating session | iterated | Applied Brandon's decisions: CR5 now removes ClaimReview; the indexing-flip step is dropped (after 1.0.0, Brandon's call); CR3 runs the archive lookup in code with a `dr` backfill command; backlog cleanup renumbered CR6. |
| 2026-10-07 | agent (claude-opus-5-5), cross-review | deep, implementation | Checked every code and doc reference against HEAD `a64672c` and the working tree. Fixed refs: `arxiv.py:64-65`; CR2's lines are in `verify_claim` (not `research_claim`, which repeats the block at `:1182-1194`); `validation.py:73-77` checks the archive domain, it does not require the field; RE-E pointer `:161`; the UNSCHEDULED bullet is now "ClaimReview markup"; CR1 Files gains the decomposed test. Findings X1 to X9 returned to the orchestrating session, not applied: CR3 does not cover `dr step-ingest` (`cli.py:321-418`, used by the page plan's S7) or say where the in-code lookup runs; CR3 Verify contradicts itself on `not-attempted`; CR2 misses `research_claim` and same-claim redirects; CR1 changes `_is_page_or_archive_copy`; CR4 and CR6 Verify controls cannot pass as written. |
| 2026-10-07 | agent (claude-opus-5-5), findings pass | iterated | Applied X1 to X9 after checking each against HEAD `4fa679b`; none rejected. CR1: arXiv rule moved to `canonical_key` only, so the fetched-page check and slug resolution stay page-exact; names `decomposed.py:285`; adds `math.AG/0601001` and a fetched-page test. CR2: legacy check runs first (rerun at `4fa679b` found no committed redirect target, so no migration); same-batch merge in `_ingest_urls` with aliases; `research_claim` covered. CR3: one helper after `wait_for`, outside the semaphore, own time limit, no save after a TimeGate 429; used by `_ingest_one` and `dr step-ingest`; instructions limit `wayback_check` to recovery; `not-attempted` means `skip_wayback` only; cached entries carry no `archive`; `dr wayback-backfill` named; Files and fixture note completed; re-read the files the refresh-trail plan changes. CR4 control over committed sources. CR5 drops `type Verdict`. CR6 RF11 and RF23 lose their triage markers. Archive-in-code decision added to `docs/decisions.md`. |
