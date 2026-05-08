# Source Pool Expansion — Tier 1

**Status**: Reviewed draft (ready for promotion). The original draft was written without full repo access; this revision corrects the assumptions that didn't match the codebase and reconciles overlap with adjacent plans.
**Created**: 2026-05-08
**Last revised**: 2026-05-08

## Problem

The Researcher → Ingestor pathway currently uses a single search backend (Brave) and a single fetch path (`httpx` + Wayback fallback). Two pressures push the source pool toward `first-party` material:

1. **Paywalls and 403s on tech-news and trade outlets** make independent reporting hard to ingest. The in-pipeline Wayback fallback (`pipeline/ingestor/tools/wayback.py`, default `skip_wayback=False` per `VerifyConfig`) recovers some of these but not all.
2. **Brave's general-web ranking** mixes vendor-sponsored content, content farms, and stale aggregator pages into the candidate list. The host blocklist (`researcher-host-blocklist.md`) drops the worst offenders but doesn't add new surface area.

`verification_level` is derived from the `independence` distribution of the source pool (see `docs/architecture/source-quality.md`). When the pool skews `first-party`, the cap-and-rationale machinery routes verdicts toward `claimed` / `self-reported` even when independent reporting exists somewhere — it just isn't reachable via the current pathway.

## Goal

Add three never-paywalled, mostly-independent acquisition surfaces and replace the search backend, so the candidate pool routinely includes material the current pathway can't reach. Tier 1 also fills two documented v1 imprecisions in `source-quality.md` (regulator filings, academic affiliation) and lays the shared infrastructure (rate-limit, dedup, audit-trail slots) that Tier 2 and Tier 3 will reuse.

## Codebase touchpoints (corrected)

The original draft cited several paths that don't match the repo. Corrected anchors:

- **Search execution** is `execute_searches()` inside `pipeline/researcher/decomposed.py:53`, not a standalone `execute_searches.py`. The Tavily/Exa swap lands here.
- **Fetch + Wayback fallback** are `pipeline/ingestor/tools/wayback.py` (functions `check_wayback`, `save_to_wayback`), wired into the ingestor agent and gated by `VerifyConfig.skip_wayback` (default `False` interim; see `wayback-archive-job.md` for the steady-state plan).
- **Source classification** lives in `pipeline/common/source_classification.py` (sets `source_type` from publisher) and `pipeline/common/publisher_quality.py` (tags publisher quality for the scorer). Both files exist as the draft assumed.
- **Source schema** is `src/content.config.ts`. `archived_url` already exists. `kind` enum is `report | article | documentation | dataset | blog | video | index` — `paper` is **not** present.
- **`source_type` enum** is `primary | secondary | tertiary`. The draft's hypothetical `regulatory` / `first-party` / `independent` enum names do not match; `independence` is a separate field (`first-party | independent | unknown`) proxied from `source_type`.
- **Entity files** live at `research/entities/companies/{slug}.md` (not `companies/{slug}.md`). The entity schema currently has no `sec_cik` field.
- **Pipeline config flags** live on `VerifyConfig` in `pipeline/orchestrator/pipeline.py` (existing examples: `skip_wayback`, `max_initial_queries`, per-agent model overrides). New flags follow the same dataclass-field pattern.

## Path 1 — Wayback fallback (already live; gap-filling only)

The original draft proposed building this. It already exists:

- `wayback_check` is a registered ingestor tool that calls `check_wayback` (Memento-style availability) and `save_to_wayback` on terminal fetch failure.
- `VerifyConfig.skip_wayback = False` is the interim default (commit 6409918, per `docs/plans/wayback-archive-job.md` § Interim status). The wayback-archive-job plan owns the steady-state design (out-of-band scheduled archival).

What Tier 1 *adds* is gap-filling, not rebuild:

1. **Memento Time Travel as a secondary fallback** when archive.org's availability API returns no snapshot. `http://timetravel.mementoweb.org/api/json/{datetime}/{url}` aggregates across non-archive.org archives. Same call site (`tools/wayback.py`), one extra leg before giving up.
2. **Telemetry**: emit `StepError(step="ingest", error_type="wayback_recovered" | "wayback_unavailable")` so `dr stats` (see Shared Infrastructure) can measure recovery rate.
3. **No change** to `archived_url` semantics: it remains the canonical archive pointer, written when archival succeeds, regardless of whether the live URL was reachable.

**Coordination**: this plan does **not** flip `skip_wayback` back to `True`. That happens when `wayback-archive-job.md` ships its background-job replacement.

**Effort**: ~1 day (Memento integration + telemetry + tests).

## Path 2 — Academic APIs (arXiv, Semantic Scholar, OpenAlex)

**Where**: Researcher, parallel to `search_brave`. New tool functions invoked from `decomposed.py:execute_searches`. Results merge into the same `SearchCandidate` list before the URL scorer runs.

**Trigger**: claims whose criterion topic (per `src/content.config.ts:238`) is `ai-safety`, `environmental-impact`, or `industry-analysis`. Other topics skip the academic dispatch (negative-cache to keep cost down).

**APIs**:

| API | Auth | Rate limit | What it gives |
|-----|------|-----------|---------------|
| arXiv | none | ~1 req / 3s | abstract, authors, primary category. No structured affiliation. |
| Semantic Scholar | optional API key (`SEMANTIC_SCHOLAR_API_KEY`) | 1 req/sec anon, higher with key | citation graph, author-org mapping (best-effort). |
| OpenAlex | none, polite pool with `mailto=` UA | ~10 req/sec | most reliable structured affiliation; cross-references arXiv/DOI. |

OpenAlex is the affiliation source of truth; arXiv/S2 are corroborators.

**Schema impact**: add `paper` to the `kind` enum in `src/content.config.ts` and the matching Python model in `pipeline/common/models.py`. PDF text extraction is **not** wired in this plan — Path 2 ingests the abstract + metadata + landing-page HTML; full-text PDF parsing is deferred (see `source-pdf-attachment.md` for the manual path; an automated PDF reader is Tier 2).

### Architecture amendment (academic affiliation)

`source-quality.md` documents this failure mode: *"Academic articles authored by entity employees are `secondary` by publisher (arxiv, IEEE) and proxied to `independent`. They may functionally be entity-authored content disclosed through a third-party venue."*

Tier 1 resolves it by overriding `independence` at ingest time using OpenAlex affiliation:

- All authors employed by the subject entity (or a same-parent subsidiary, resolved via `parent_company`): `independence: first-party`.
- Mixed authorship (≥1 external author): `independence: independent`.
- Affiliation unavailable: `independence: unknown`. The analyst's restatement test (per `source-quality.md` § Known failure mode) still applies.

This is an explicit amendment to `source-quality.md` and is recorded as a v1.x item there once the implementation lands.

**Effort**: 4–6 days (three API integrations, affiliation extraction, classification override, fixtures, instructions update).

## Path 3 — SEC EDGAR

**Where**: Researcher, conditional on the entity (or its `parent_company`) carrying a `sec_cik` field.

**Schema**: add optional `sec_cik` to the company entity in `src/content.config.ts:209-225`. This is the first concrete field on the broader Company-metadata-enrichment idea collected in `source-quality-followups.md` § Company metadata enrichment; the other candidate fields there stay deferred.

**Endpoints**:
- Filing index: `https://data.sec.gov/submissions/CIK{cik}.json`
- Full-text search: `https://efts.sec.gov/LATEST/search-index?q={keywords}&ciks={cik}`
- Filings: `https://www.sec.gov/Archives/edgar/data/...`

**Compliance**: SEC requires a specific `User-Agent` header (`<Org> <contact-email>`) and rate-limits hard at 10 req/sec. Both are wired through the shared throttle layer (see Shared Infrastructure) and a `SEC_EDGAR_USER_AGENT` env var (no default — pipeline aborts the EDGAR path if unset).

**False-positive handling**: full-text search returns filings *containing* the keywords, not *about* them. The Researcher's URL scorer evaluates these alongside web-search candidates, so the existing scorer rationale carries the disambiguation. Where the analyst is consuming the source, the surrounding sentence (extracted at ingest time) gives context.

**Investor-corroboration use case**: Anthropic and OpenAI are private companies and don't file with the SEC themselves. Their commercial-partnership and investment claims **are** corroborated through public-investor filings:

- Anthropic via **Amazon** (CIK 0001018724) and **Alphabet/Google** (CIK 0001652044). The original draft incorrectly attributed Anthropic's investments to Microsoft — corrected here.
- OpenAI via **Microsoft** (CIK 0000789019).

Path 3's value for these claims is the regulator-authority distinction: a 10-K that quantifies a partnership commitment is a stronger source than a press release announcing it.

### Architecture amendment (regulator-authority)

`source-quality.md` documents this failure mode: *"Regulator filings about (not by) the entity are `primary` by publisher rule (sec.gov, ftc.gov) and proxied to `first-party`. The document originates outside the entity but speaks with regulator authority — neither label fits cleanly."*

Tier 1's resolution: keep the existing two-field model (`source_type` + `independence`) and route the distinction through `independence`:

- Filing **by** the subject entity (the entity is the filer, CIK matches): `source_type: primary`, `independence: first-party` — unchanged.
- Filing **about** the subject entity by another filer (subject mentioned but not the filer): `source_type: primary`, `independence: independent`. The override is recorded as a per-source classification at ingest time.

No new `source_type` enum value. The override is a publisher-rule extension in `pipeline/common/source_classification.py`, gated on the EDGAR-ingest path knowing the subject CIK vs the filer CIK.

This amendment is recorded in `source-quality.md` once the implementation lands.

**Effort**: 5–7 days (schema change + Pydantic mirror + entity-loader plumbing + UA/throttle + filing parser + classification override + tests).

## Path 4 — Tavily or Exa as search backend

**Where**: `pipeline/researcher/decomposed.py:53` (`execute_searches`). The function currently fans `search_brave(client, q)` calls in parallel; the swap replaces or augments the per-query call.

**Coordination**: this is the *search* backend. It is **independent** of `multi-provider.md` Part 3's note about GreenPT's Scraper API as an alternate `web_fetch` (which is the *fetch* backend). The two can stack: agent-optimized search + agent-optimized fetch.

**Candidates**:

| Backend | Pricing | Posture |
|---|---|---|
| Tavily | Free research tier | Returns extracted content + URLs; cached/extracted delivery sidesteps some paywalls. |
| Exa | ~$10–50/mo at expected volume | Semantic/neural retrieval; returns full content of indexed pages. |

**Rollout**: implement both behind a `RESEARCH_SEARCH_BACKEND` env var (`brave` | `tavily` | `exa`), with `brave` as the default. Run a frozen-claim replay (see Shared Infrastructure) over both new backends and decide which to keep based on the rubric below. Keep Brave as a fallback unless a clear loser emerges.

**Decision rubric** (defined now so the evaluation isn't post-hoc):
1. **Independence ratio** of the kept pool: Tavily/Exa must produce ≥ Brave's `independent`-classified-source share without raising the host-blocklist drop rate.
2. **Fetch success on returned URLs**: ≥ Brave's success rate (Tavily's pre-extracted content counts as success).
3. **Verdict stability** on the frozen-replay set: no swing in `verification_level` distribution beyond the noise floor measured against Brave-on-Brave.
4. **Cost**: under $50/mo at current claim throughput; revisit at v1.x if claim volume changes.

**Data-handling note**: claim text and entity names go to the third-party retrieval API. The published research is already public, but operators should verify Tavily/Exa's retention and reuse posture before enabling. Note in pipeline docs.

**Effort**: 1 day swap + 3–5 days frozen-replay evaluation + 1 day decision write-up = ~6 days.

## Shared infrastructure (used by all paths)

The four paths share enough plumbing that it has to land somewhere. This is the smallest version that doesn't pre-build a framework.

### Rate-limit / throttle layer

A small per-host-or-API throttle in `pipeline/common/throttle.py`. Each path declares its limits (arXiv 1/3s, S2 1/s anon, OpenAlex 10/s polite, EDGAR 10/s, Tavily/Exa per-tier monthly cap). Wayback already has its own throttle (`WAYBACK_RATE_LIMIT_S` per `wayback-archive-job.md` § Throttle); we don't merge — the wayback throttle stays job-scoped, and the new layer covers in-pipeline fetches/searches.

### URL deduplication across paths

A single canonical URL form (lowercase host, strip default ports, drop tracking params) before insertion into the `seen` set in `execute_searches`. Today the dedup is exact-string match (`decomposed.py:62`). Tracked as part of "Dedup detection on URL ingest" in `docs/UNSCHEDULED.md`; Tier 1 lands the canonicalizer used by the new paths and the existing flow.

### Audit-trail slots

The audit sidecar's `research:` block currently records planner queries + scorer rationale. Add an optional `acquisition:` field per kept URL: `{path: brave|tavily|exa|arxiv|s2|openalex|edgar|wayback, query?, paper_id?, filing_accession?}`. The analyst doesn't read this; the operator reads it during review.

### Error-type vocabulary additions

Add to the `StepError(error_type=...)` vocabulary:
- `wayback_recovered`, `wayback_unavailable` (Path 1 telemetry)
- `arxiv_no_results`, `s2_no_results`, `openalex_no_results` (Path 2)
- `edgar_no_match`, `edgar_ua_missing`, `edgar_rate_limited` (Path 3)
- `tavily_rate_limited`, `exa_rate_limited` (Path 4)

These are emitted but don't fail the run unless terminal.

### Frozen-claim replay harness

Path 4's evaluation needs a way to re-run the Researcher over a fixed claim list with deterministic seeds and capture the candidate pool / scorer output for diff. If a harness already exists in `pipeline/tests/`, reuse it; if not, build a thin one (~1 day) that records inputs/outputs to a JSONL file. Counted in Path 4's effort.

### `dr stats` (lightweight)

A `dr stats` Click subcommand that scans recent run logs for: independence-ratio, fetch-failure rate, per-path firing rate. Read-only; no aggregation server. Counted as ~1 day in Path 4's effort because it's the first place the Path-4 evaluation needs the numbers, but it serves all four paths after.

## Rollout order

1. **Path 4 (Tavily/Exa swap + `dr stats` + frozen replay)** — ~6 days. Biggest impact on the existing pathway and forces the shared-infra build.
2. **Path 1 gap-filling (Memento + telemetry)** — ~1 day. Lands cheaply once Path 4's telemetry plumbing exists.
3. **Path 2 (arXiv + S2 + OpenAlex + affiliation rule)** — 4–6 days. Depends on `paper` enum addition and the Path-4 throttle layer.
4. **Path 3 (SEC EDGAR + `sec_cik` + classification override)** — 5–7 days. Schema migration last; depends on the throttle layer and benefits from Paths 2/4 having shaken out the multi-source dedup.

Each ships behind a flag (`RESEARCH_SEARCH_BACKEND`, `ENABLE_ACADEMIC_RESEARCH`, `ENABLE_EDGAR_RESEARCH`). Disabled by default for one operator-validated cycle; default flips after verdict-stability check on the frozen-replay set.

**Total effort estimate**: 16–20 days end-to-end (was "~6 days" in the original draft; the original under-counted integration, schema migration, and evaluation).

## Per-path success criteria

| Path | Metric | Target |
|---|---|---|
| 1 | `wayback_recovered` rate on terminal fetch failures | ≥ 50% (combined archive.org + Memento) |
| 2 | Tagged-topic claim runs ingesting ≥1 academic source | ≥ 60% on `ai-safety` / `environmental-impact` topics |
| 3 | Public-investor company claims surfacing ≥1 EDGAR document | ≥ 50% of claims where `sec_cik` resolves |
| 4 | Frozen-replay verdict stability vs Brave baseline | No verdict swing outside the noise floor (defined during evaluation) |
| All | `verification_level` distribution shift toward weakly-sourced verdicts | None (lint already enforces the cap; sidecar carries the level) |

A baseline snapshot of `verification_level` distribution on the current corpus is taken **before** Path 4 ships; it's the reference for the "no regression" check.

`dr stats` surfaces these numbers; nothing else is built for instrumentation.

## Out of scope

- **Flipping `skip_wayback` back to `True`.** Owned by `wayback-archive-job.md` (background-job ship).
- **Automated PDF text extraction.** Path 2 ingests metadata + abstract; full PDF reading is Tier 2 (or a follow-on plan to `source-pdf-attachment.md`).
- **Energy telemetry.** Out of scope for Tier 1; tracked in `multi-provider.md` Part 3.
- **A registry-driven publisher trust system.** Deferred to v1.x per `source-quality.md` § Publisher registry.
- **Replacing Brave entirely on day one.** Path 4 keeps Brave as a backend option; deprecation is a follow-on decision.

## File touches (corrected)

| File | Change |
|------|--------|
| `pipeline/researcher/decomposed.py` | Search backend dispatch in `execute_searches`; per-path acquisition tag on `SearchCandidate`. |
| `pipeline/researcher/tools/` (new) | `arxiv.py`, `semantic_scholar.py`, `openalex.py`, `edgar.py` — one tool function per API, called from `execute_searches`. |
| `pipeline/ingestor/tools/wayback.py` | Memento secondary fallback; new error-type emissions. |
| `pipeline/common/source_classification.py` | EDGAR filer-vs-subject CIK rule; preprint/journal publisher tags. |
| `pipeline/common/publisher_quality.py` | Tag arXiv / OpenAlex / SEC publishers. |
| `pipeline/common/throttle.py` (new) | Per-host-or-API throttle. |
| `pipeline/common/canonical_url.py` (new) | Cross-path URL canonicalization for dedup. |
| `pipeline/common/models.py` | `kind: paper` addition; `acquisition` audit-trail field. |
| `pipeline/orchestrator/pipeline.py` | New `VerifyConfig` flags; throttle plumbing. |
| `pipeline/orchestrator/cli.py` | `dr stats` subcommand. |
| `src/content.config.ts` | `kind: paper`; optional `sec_cik` on company entity. |
| `docs/architecture/source-quality.md` | Record amendments (academic affiliation rule, EDGAR filer-vs-subject rule). |
| `docs/architecture/research-flow.md` | Update Researcher-internals diagram (§6) for parallel tool dispatch. |
| `docs/architecture/research-workflow.md` | Document new `VerifyConfig` flags under § Pipeline configuration knobs. |
| `AGENTS.md` § Tooling | New env vars (`RESEARCH_SEARCH_BACKEND`, `SEMANTIC_SCHOLAR_API_KEY`, `SEC_EDGAR_USER_AGENT`, etc.). |

## Open questions

- **Affiliation threshold for "majority external" papers.** A 10-author paper with one entity employee is functionally independent; what about 5/5? Default: any external author flips to `independent`, but flag for analyst review when the entity author count is ≥ half. Decision needed before Path 2 ships.
- **`sec_cik` lookup for entities not yet seeded.** Manual operator add (preferred — matches existing entity-onboard flow) or auto-resolution from name during onboard? Default: manual; revisit if backlog is large.
- **Tavily vs Exa**: pick one or run both? Default: run both during evaluation, pick one based on the rubric, keep the loser disabled but available behind the flag.
- **Negative-cache for academic / EDGAR misses.** Re-running a claim shouldn't keep hitting EDGAR for an entity with no `sec_cik`. Resolved within Path 3: skip when `sec_cik` is unset; that's the cache. Path 2 negative-cache is per-(entity, topic) and lives in the existing run-cache layer.

## Cross-references

- Independence accounting and amendments: [`docs/architecture/source-quality.md`](../architecture/source-quality.md)
- Researcher internals (parallel tool dispatch): [`docs/architecture/research-flow.md`](../architecture/research-flow.md) § 6
- `VerifyConfig` knobs: [`docs/architecture/research-workflow.md`](../architecture/research-workflow.md) § Pipeline configuration knobs
- Wayback steady-state design: [`docs/plans/wayback-archive-job.md`](wayback-archive-job.md)
- Search vs fetch backend distinction: [`docs/plans/multi-provider.md`](multi-provider.md) § Part 3
- Company metadata enrichment (Tier 1 lands `sec_cik` first): [`docs/plans/source-quality-followups.md`](source-quality-followups.md) § Company metadata enrichment
- Host blocklist interaction: [`docs/plans/researcher-host-blocklist.md`](researcher-host-blocklist.md)
- Tier 2 / Tier 3 follow-up scope: [`docs/plans/source-quality-followups.md`](source-quality-followups.md) § Source pool — Tier 2 and § Source pool — Tier 3

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-08 | agent (opus-4-7) | implementation, iterated | Initial draft asserted file paths and architectural states the codebase did not match. Verified every claim against the repo: corrected `pipeline/researcher/execute_searches.py` → function in `decomposed.py:53`; noted Wayback fallback is already live (`skip_wayback=False` default; `wayback_check` tool registered) and reframed Path 1 from "build" to "gap-fill"; corrected entity path to `research/entities/companies/{slug}.md`; noted `sec_cik` is not in the schema today and routed it through the broader Company-metadata-enrichment idea; corrected `source_type` enum to `primary | secondary | tertiary` (the draft's `regulatory` / `first-party` / `independent` enum names did not exist) and routed the regulator-authority distinction through `independence` instead of a new enum value; flagged `kind: paper` as a missing enum addition; corrected the SEC corroboration example — Anthropic is funded by Amazon (CIK 0001018724) and Alphabet (CIK 0001652044), not Microsoft (CIK 0000789019, which is OpenAI's). Surfaced two source-quality.md amendments out of "open questions" into an explicit "Architecture amendment" subsection per path. Replaced global success metrics with per-path metrics measurable from `dr stats`. Added a Shared Infrastructure section (throttle, URL canonicalizer, audit-trail `acquisition` slot, error-type vocab additions, frozen-claim replay harness, `dr stats`). Realistic effort revised from ~6 days to 16–20 days. Coordinated explicitly with `wayback-archive-job.md`, `multi-provider.md` Part 3, `research-quality-ideas.md` company metadata, `researcher-host-blocklist.md`, and `source-quality.md`'s documented v1 imprecisions. Added Tavily/Exa decision rubric and data-handling note. |
| 2026-05-08 | agent (opus-4-7) | iterated | Cross-references rewritten as part of the source-quality plan-family consolidation: `research-quality-ideas.md` and `drafts/source-pool-expansion-tier{2,3}.md` were absorbed into the new `source-quality-followups.md` collector, so this plan now points at the collector's sections instead. Plan body is unchanged. |
