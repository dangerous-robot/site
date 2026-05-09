# Ingestor — Tavily prefetch passthrough

**Status**: Done. Implemented 2026-05-08 in commit `a151998`; simplified follow-up in `3ce0fa2` (memory-leak fix) and `7567466` (raw_content shape unification + comment trims). Operator-validated on `contributes-to-environmental-causes`: 4 prefetch hits, terminal 403s dropped from 5 to 3 (the 3 remaining are Tavily-can't-reach publishers, owned by `multi-provider.md` § Part 3).
**Family**: follow-on to [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md).
**Created**: 2026-05-08
**Last revised**: 2026-05-08

## Context

The Tavily backend landed (commit `ac2dfac`) and was made the default (commit `653f5b6`). A first operator-validated `dr onboard` cycle on 2026-05-08 confirmed Tavily fires cleanly (7/7 queries, 51 candidates, no rate-limit errors), but the run still produced six terminal `403`s on Cloudflare-shielded news domains (`sustainabilitymag.com`, `aimagazine.com`, `ien.com`, `fastcompany.com`, `ditchcarbon.com`, `ien.com`). The 403s come from `pipeline/ingestor/agent.py:web_fetch`'s `httpx.get`, after Tavily already returned the URL with body content alongside it. Tavily's `/search` response carries a per-result `raw_content` field (full extracted body) when requested, but the current wrapper at `pipeline/researcher/tools/tavily.py:142-145` deliberately discards it — only `content` (snippet) is mapped onto the scorer's `SearchCandidate.snippet`.

The companion plan called the discarded `raw_content` out as scope-limited:

> The pre-extracted body content is intentionally not used for fetch-skipping yet -- that's a follow-on once the backend is established.

This plan is that follow-on.

## Goal

Wire Tavily's `raw_content` through the researcher → orchestrator → ingestor so that when Tavily already supplied a body, the ingestor's `web_fetch` tool returns the prefetched body instead of issuing an `httpx.get`. Eliminates 403s for any Tavily-found URL whose publisher serves Tavily but blocks anonymous httpx. Falls back to live fetch when `raw_content` is absent.

Not scope: the `multi-provider.md` § Part 3 fetch-backend swap (GreenPT Scraper API) — that's the broader fix for non-Tavily URLs.

## Codebase touchpoints

- **Tavily wrapper**: `pipeline/researcher/tools/tavily.py:71-148`. POST body adds `include_raw_content: true`; the per-result mapping carries `raw_content` alongside the existing `{url, title, snippet}` shape.
- **SearchCandidate**: `pipeline/researcher/scorer.py:10-15`. New optional field `raw_content: str | None = None`. Carries cleanly through the scorer (which only reads title/snippet) and onto the kept-URL list.
- **Researcher dispatch**: `pipeline/researcher/decomposed.py:_dispatch_one_query` and `execute_searches`. Populates `raw_content` on `SearchCandidate` when the dispatched backend returned it; Brave returns `None`.
- **Acquisition trace**: no schema change. The Tier 1 schema's `acquisition.origin: 'tavily'` plus `stage: 'research'` already records that the URL (and its body) came from Tavily search; the ingestor short-circuit is operational, not audit-relevant. `outcome` stays unset for prefetched URLs — `outcome` is meaningful for ingest-stage rescues (`'recovered'`) and for ingest-stage fresh fetches (`'matched'`); a research-stage entry with `outcome: 'matched'` would conflate "search found something" with "ingest succeeded" and isn't what the enum is for. If a prefetch-hit-rate metric is wanted later, it can be derived from logs or added to `dr stats` (e.g., a per-origin "fetch skipped" counter computed from a structured log line) without touching the schema.
- **Orchestrator → ingestor handoff**: `pipeline/orchestrator/pipeline.py:_ingest_urls` (line 618) currently takes `urls: list[str]`. It gains a `prefetched_bodies: dict[str, str] | None = None` kwarg; callers at `pipeline.py:330`, `:870`, `:1284`, `:1291` build the map from the researcher's kept candidates and pass it through. The waterfall semantics are unchanged.
- **`_ingest_one`**: `pipeline.py:569`. Threads the relevant `prefetched_bodies.get(url)` value into `IngestorDeps`.
- **`IngestorDeps`**: `pipeline/ingestor/agent.py:31-38`. New optional field `prefetched_bodies: dict[str, str] = field(default_factory=dict)`.
- **`web_fetch` tool**: `pipeline/ingestor/agent.py:54-91`. Before issuing the `httpx.get`, check `ctx.deps.prefetched_bodies.get(url)`. If present (and non-empty), return a synthesized dict matching `extract_page_data`'s output shape — `{title: "", description: "", author: None, published_time: None, text: <raw_content>, url: <url>}` — and skip the network call. Tavily's `raw_content` is documented as cleaned/extracted body content; the plan assumes Markdown-or-plain-text, which lets `extract_page_data` (HTML parser) be bypassed. **Verify at implementation time** — if Tavily returns HTML fragments instead, route through `extract_page_data` rather than passing through raw. Title and description are best-effort blank; the LLM derives them from the body, same as it would for a thin HTML page. Empty/missing `raw_content` falls through to the live fetch path unchanged.

The agent's behavior is unchanged: it still calls `web_fetch`, still gets a dict, still optionally calls `wayback_check` if `web_fetch` errors. It just doesn't know the body came from Tavily.

## Implementation

1. **Tavily wrapper** — add `include_raw_content: true` to the POST body; map `raw_content` into the per-result dict alongside `snippet`. Keep the snippet mapping; the scorer still uses it.
2. **`SearchCandidate.raw_content: str | None`** — optional, defaults `None`.
3. **Researcher dispatch** — populate `raw_content` from the per-result dict when present. The existing `acquisition[url] = {stage: 'research', origin: 'tavily', query: …}` stamp from the search-backend plan is unchanged; no `prefetched` key is added.
4. **`decomposed_research` output** — `ResearchOutput` already exposes URLs; add a `prefetched_bodies: dict[str, str]` field built from kept candidates whose `raw_content` is non-empty.
5. **`_ingest_urls` / `_ingest_one`** — accept the optional `prefetched_bodies` map; pass each URL's body into `IngestorDeps`.
6. **`web_fetch` tool** — short-circuit when `prefetched_bodies.get(url)` is set. Log at INFO so audit-trail readers can see the path was taken: `"Prefetch hit (Tavily raw_content): %s"`.

## Testing

- Unit test on `tavily.py`: mock response with `raw_content` set on some results, absent on others; assert the wrapper returns it on the right entries.
- Unit test on `web_fetch`: build `IngestorDeps(prefetched_bodies={"https://x": "BODY"})`, call `web_fetch`, assert the returned dict's `text == "BODY"` and that `httpx.get` was not invoked.
- Integration test on `_ingest_urls` with a mocked agent and `prefetched_bodies`: assert the agent runs and that `web_fetch` returns the prefetched body without network I/O.
- Existing 403-handling tests in `pipeline/tests/test_terminal_fetch.py` keep passing; prefetch skipping doesn't bypass the terminal-status path for un-prefetched URLs.

## Rollout

One commit, on by default (no flag). Prefetch only fires when the researcher already produced `raw_content`, so Brave-only runs are unaffected. Operator-validated cycle: re-run the same `contributes-to-environmental-causes` claim and confirm the previously-403'd URLs now ingest. The `dr stats` per-origin counts remain valid; add an aggregate later if prefetch-hit-rate becomes a tracked metric.

## Effort

| Item | Hours |
|---|---|
| Tavily wrapper + `raw_content` plumbing | 1 |
| SearchCandidate / decomposed dispatch / `ResearchOutput.prefetched_bodies` | 1 |
| Orchestrator handoff + `IngestorDeps` field | 1 |
| `web_fetch` short-circuit + tests | 2 |
| Operator validation cycle | 0.5 |
| **Total** | **~5–6 hours** |

Caveat: estimate assumes Tavily's `raw_content` is Markdown-or-plain-text. If verification finds it's HTML, add ~1 hour to wire it through `extract_page_data` (same call shape, different argument source) and to refresh the unit test fixture.

## File touches

| File | Change |
|---|---|
| `pipeline/researcher/tools/tavily.py` | Request `include_raw_content`; map `raw_content` into result dicts. |
| `pipeline/researcher/scorer.py` | `SearchCandidate.raw_content: str \| None = None`. |
| `pipeline/researcher/decomposed.py` | Populate `raw_content` on candidates; collect `prefetched_bodies` into `ResearchOutput`. No new `acquisition` keys; the existing `{stage, origin, query}` stamp is unchanged. |
| `pipeline/orchestrator/pipeline.py` | Plumb `prefetched_bodies` through `_ingest_urls` / `_ingest_one`; build the map at the four call sites. |
| `pipeline/ingestor/agent.py` | `IngestorDeps.prefetched_bodies`; `web_fetch` short-circuit. |
| `pipeline/tests/test_tavily_search.py` | New `raw_content` mapping test. |
| `pipeline/tests/test_ingest_urls.py` (and/or new `test_prefetch.py`) | `web_fetch` short-circuit test; end-to-end ingest with prefetched body. |

## Out of scope

- **Brave prefetch.** Brave doesn't return body content. No-op for Brave runs.
- **Fetch backend swap (GreenPT Scraper API).** Owned by `multi-provider.md` § Part 3.
- **Using Tavily's `content` snippet** for fetch-skipping — too short to be a faithful body. Only `raw_content` qualifies.
- **Title / metadata extraction from `raw_content`.** The Ingestor LLM derives these from body text already; no need to teach the wrapper to extract HTML metadata.
- **Caching prefetched bodies across runs.** In-process only; if the orchestrator re-ingests later, it re-searches.

## Open questions

- **`raw_content` quotas / latency.** `include_raw_content: true` may push the request into a higher Tavily tier or slow the response. Confirm at implementation time; if it does, gate behind a `VerifyConfig.tavily_include_raw_content: bool = True` for easy rollback.
- **403 attribution in `dr stats`.** Today every `http_403` ingest error counts toward the same bucket. After this lands, `http_403`s on Tavily-prefetched URLs become impossible (the fetch never happens), so the 403 count should drop; if it doesn't, the prefetch path isn't firing as intended. Track this as a sanity check for the operator-validation cycle, not a new metric.
- **`raw_content` content format.** Tavily's docs describe `raw_content` as cleaned/parsed body, but the exact format (Markdown, plain text, or HTML fragments) is not pinned in this plan. The short-circuit assumes plain-text-or-Markdown so `extract_page_data` can be bypassed. If `raw_content` is HTML, the short-circuit must route through `extract_page_data(raw_content, url)` instead — same shape, slightly different code path. Verify on the first real `include_raw_content: true` call and pick the branch.
- **Empty / truncated `raw_content`.** Tavily may return an empty string for some results (e.g., publishers that block its crawler) or a truncated representation for very long pages. Handling: empty string falls through to live fetch (already specified in the `web_fetch` short-circuit); truncation is opaque from our side and is accepted as-is — the analyst sees the same body the LLM would have read on a normal fetch, just shorter. Flag if a future operator-validation cycle shows truncated bodies tipping verdicts toward `needs_review`.
- **`dr re-audit` interaction.** The Tier 1 parent plan flags that the auditor-only refresh path (`cli.py:1390`, `dr re-audit`) drops the `acquisition` block on rewrite unless re-grafted. The Tavily backend plan already exposes this hazard; the prefetch plan inherits it but doesn't worsen it (no new keys). One-line note here for traceability; the fix lives in the Tier 1 plan's "Known limitation" section.

## Cross-references

- Companion search-backend plan: [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md)
- Fetch-backend swap (the broader 403 fix): [`multi-provider.md`](../multi-provider.md) § Part 3
- Ingestor terminal-fetch handling: `pipeline/ingestor/tools/web_fetch.py` (`TerminalFetchError`, `TERMINAL_STATUS_CODES`)
- Audit-trail acquisition plumbing: [`source-pool-expansion-tier1.md`](../source-pool-expansion-tier1.md) § Audit-trail acquisition plumbing

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-08 | agent (opus-4-7) | initial draft | Drafted after the first Tavily-default `dr onboard` run on 2026-05-08 produced 6 terminal-403s on URLs that Tavily had already returned with `raw_content`. |
| 2026-05-08 | agent (opus-4-7) | cross-review against plan family | Cross-checked against `source-pool-expansion-tier1.md`, `source-pool-expansion-tier1-search-backend.md`, and `multi-provider.md` § Part 3. Findings applied: (1) Resolved an internal contradiction — § Codebase touchpoints said "no schema change" but § Implementation step 3 stamped `acquisition[url]["prefetched"] = True`, which would have been a closed-Zod-object schema extension. Dropped the `prefetched` key entirely; `acquisition.origin: 'tavily'` plus `stage: 'research'` already records what's needed and the short-circuit is logged at INFO. Future prefetch-hit-rate metrics can derive from logs or land as a `dr stats` extension without schema work. (2) Clarified `outcome` semantics — leave `outcome` unset on prefetched URLs. The Tier 1 enum is `'matched' | 'recovered'`, both meaningful for ingest-stage entries; setting `outcome: 'matched'` on a research-stage entry would conflate "search found something" with "ingest succeeded." No new enum value; no value set. (3) Flagged `raw_content` format as a verification-time question (Markdown/plain vs HTML fragments) and added a +1h caveat to the effort estimate for the HTML branch. (4) Added open questions covering empty/truncated `raw_content` handling and the `dr re-audit` acquisition-drop hazard inherited from the Tier 1 parent. (5) Confirmed the boundary with `multi-provider.md` § Part 3: GreenPT Scraper API is an alternate `web_fetch` impl for any URL; Tavily prefetch only short-circuits Tavily-returned URLs. Surfaces are disjoint, no edit to multi-provider.md needed. (6) Noted file-touches overlap on `decomposed.py` and `pipeline.py` with Tier 1 Paths 1–3; sequential, not parallel — no body change. **No change to the Goal or to which work gets done**, only to how it's recorded in the audit trail and where the assumptions sit. |
| 2026-05-08 | agent (opus-4-7) | implementation + validation | Implemented end-to-end (commit `a151998`): Tavily wrapper requests `include_raw_content`, body threads through `SearchCandidate` → `ResearchOutput.prefetched_bodies` → `_ingest_urls` / `_ingest_one` → `IngestorDeps.prefetched_bodies`, `web_fetch` short-circuits with INFO log. Pre-implementation verification of Tavily's `raw_content` format on three real domains (wikipedia, sustainabilitymag, fastcompany) confirmed Markdown/plain text — pass-through branch taken; `extract_page_data` not invoked. Operator-validated `dr onboard` cycle on `contributes-to-environmental-causes` produced 4 prefetch hits and dropped terminal-403s from 5 (prior run) to 3 (`ditchcarbon.com`, `thehill.com`, `fastcompany.com` — Tavily can't reach these either; remediation owned by `multi-provider.md` § Part 3). 667 tests pass; no warnings/errors in run. Acquisition trace verified intact end-to-end (`origin: tavily, stage: research` on all 8 sources_consulted; no schema change). Follow-up `/simplify` pass landed two refactor commits: `3ce0fa2` (drop orphaned prefetched bodies after blocklist cap — memory-leak fix; previously kept Tavily bodies for blocklist-dropped URLs alive for the rest of the verify run) and `7567466` (unify `raw_content` empty representation as `None` end-to-end; trim plan-pointer comments). |
