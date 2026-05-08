# Source Pool Expansion — Tier 1

**Status**: Active (ready to start coding).
**Companion plan**: [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md) — search-backend swap (Tavily) split out for independent shipping.
**Created**: 2026-05-08
**Last revised**: 2026-05-08

## Problem

The Researcher → Ingestor pathway currently uses a single search backend (Brave) and a single fetch path (`httpx` + Wayback fallback). Two pressures push the source pool toward `first-party` material:

1. **Paywalls and 403s on tech-news and trade outlets** make independent reporting hard to ingest. The in-pipeline Wayback fallback (`pipeline/ingestor/tools/wayback.py`, default `skip_wayback=False` per `VerifyConfig`) recovers some but not all.
2. **Brave's general-web ranking** mixes vendor-sponsored content, content farms, and stale aggregator pages into the candidate list. The host blocklist (`researcher-host-blocklist.md`) drops the worst offenders but doesn't add new surface area.

`verification_level` is derived from the `independence` distribution of the source pool (see `docs/architecture/source-quality.md`). When the pool skews `first-party`, the cap-and-rationale machinery routes verdicts toward `claimed` / `self-reported` even when independent reporting exists somewhere — it just isn't reachable via the current pathway.

## Goal

Add three never-paywalled, mostly-independent acquisition surfaces (Wayback gap-fill, academic APIs, SEC EDGAR) so the candidate pool routinely includes material the current pathway can't reach. Tier 1 also fills two documented v1 imprecisions in `source-quality.md` (regulator filings, academic affiliation) and lays the shared infrastructure (throttle, dedup, audit-trail slots) that Tier 2, Tier 3, and the companion search-backend plan all reuse.

The search-backend swap (originally Path 4) is now a separate companion plan; see [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md).

## Codebase touchpoints

The plan is anchored to current repo state:

- **Search execution** is `execute_searches()` inside `pipeline/researcher/decomposed.py:53`. Tier 1's paths add new tool functions called from this site; the backend-swap is in the companion plan.
- **Fetch + Wayback fallback** are `pipeline/ingestor/tools/wayback.py` (functions `check_wayback`, `save_to_wayback`), wired into the ingestor agent and gated by `VerifyConfig.skip_wayback` (default `False` interim; see `wayback-archive-job.md` for the steady-state plan).
- **Source classification** lives in `pipeline/common/source_classification.py` (sets `source_type` from publisher) and `pipeline/common/publisher_quality.py` (tags publisher quality for the scorer).
- **Source schema** is `src/content.config.ts`. `archived_url` already exists. `kind` enum is `report | article | documentation | dataset | blog | video | index` — `paper` is **not** present and is added by Tier 1.
- **`source_type` enum** is `primary | secondary | tertiary`; **`independence` enum** is `first-party | independent | unknown`. The original draft's hypothetical `regulatory` enum value does not exist; regulator-authority distinctions route through `independence`.
- **Entity files** live at `research/entities/companies/{slug}.md`. The entity schema currently has no `sec_cik` field; Tier 1 adds it.
- **Audit sidecar**: the `audit` object in `src/content.config.ts` does not yet carry an `acquisition` slot; Tier 1 adds it.
- **Pipeline config flags** live on `VerifyConfig` in `pipeline/orchestrator/pipeline.py` (existing examples: `skip_wayback`, `max_initial_queries`, per-agent model overrides). New flags follow the same dataclass-field pattern.

## Schema prerequisites

Three schema additions land **first**, in a single commit covering both the TypeScript schema and the Pydantic mirror. Each path's code waits on its corresponding field.

| Field | Where | Used by |
|---|---|---|
| `kind: 'paper'` | `src/content.config.ts:16–24` (source schema) + `pipeline/common/models.py` mirror | Path 2 |
| `audit.acquisition: array<{path, query?, paper_id?, filing_accession?}>` | `src/content.config.ts:32–63` (`auditSchema`) + `pipeline/common/models.py` mirror | All paths + companion plan |
| `sec_cik: string` (10-digit, optional) on company entity | `src/content.config.ts:209–224` + Pydantic mirror | Path 3 |

Concrete TypeScript edits (illustrative; coder should match the existing Zod style):

```typescript
// 1. Source kind enum
kind: z.enum(['report', 'article', 'documentation', 'dataset', 'blog', 'video', 'index', 'paper']),

// 2. Audit acquisition slot (inside auditSchema)
acquisition: z.array(z.object({
  path: z.enum(['brave', 'tavily', 'arxiv', 's2', 'openalex', 'edgar', 'wayback']),
  query: z.string().optional(),
  paper_id: z.string().optional(),
  filing_accession: z.string().optional(),
})).optional(),

// 3. Company entity sec_cik
sec_cik: z.string().regex(/^\d{10}$/, { message: 'sec_cik must be a 10-digit CIK' }).optional(),
```

These ship as one commit titled along the lines of `feat(schema): add kind:paper, audit.acquisition, sec_cik for tier1 source-pool expansion`.

## Shared infrastructure (prerequisite for all paths + companion plan)

Lands as the **second** commit (or small set of commits, one per module). Once this is in place, Paths 1–3 *and* the companion search-backend plan can all start in parallel — none of them depend on each other, only on this section and § Schema prerequisites.

### Rate-limit / throttle layer

A small per-host-or-API throttle in `pipeline/common/throttle.py`. Each path declares its limits (arXiv 1/3s, S2 1/s anon, OpenAlex 10/s polite, EDGAR 10/s, Tavily per its tier). Wayback already has its own throttle (`WAYBACK_RATE_LIMIT_S` per `wayback-archive-job.md` § Throttle); we don't merge — the wayback throttle stays job-scoped, and the new layer covers in-pipeline fetches/searches.

### URL deduplication across paths

A single canonical URL form (lowercase host, strip default ports, drop tracking params) before insertion into the `seen` set in `execute_searches`. Today the dedup is exact-string match (`decomposed.py:62`). Tracked as part of "Dedup detection on URL ingest" in `docs/UNSCHEDULED.md`; Tier 1 lands the canonicalizer in `pipeline/common/canonical_url.py` for use by the new paths and the existing flow.

### Audit-trail `acquisition` slot

The audit sidecar's `research:` block currently records planner queries + scorer rationale. The `acquisition` field added in § Schema prerequisites is filled per kept URL by every path: `{path: brave|tavily|arxiv|s2|openalex|edgar|wayback, query?, paper_id?, filing_accession?}`. The analyst doesn't read this; the operator reads it during review.

### Error-type vocabulary additions

Add to the `StepError(error_type=...)` vocabulary:
- `wayback_recovered`, `wayback_unavailable`, `memento_unavailable` (Path 1)
- `arxiv_no_results`, `s2_no_results`, `openalex_no_results` (Path 2)
- `edgar_no_match`, `edgar_ua_missing`, `edgar_rate_limited` (Path 3)
- `tavily_rate_limited` (companion plan)

Emitted but don't fail the run unless terminal.

### Observability

`dr stats` (originally part of this section) is now scoped as a **follow-up plan**, not a Tier 1 deliverable. The original deferral was to avoid merge friction with the (since-completed) [`dr-cli-output-cleanup_phase2_completed.md`](completed/dr-cli-output-cleanup_phase2_completed.md); re-included if observability becomes the bottleneck. Until then, per-path observability is via the audit-trail `acquisition` field plus ad-hoc parsing of run logs.

## Path 1 — Wayback fallback (already live; gap-filling only)

The original draft proposed building this. It already exists:

- `wayback_check` is a registered ingestor tool that calls `check_wayback` (Memento-style availability) and `save_to_wayback` on terminal fetch failure.
- `VerifyConfig.skip_wayback = False` is the interim default (commit 6409918, per `docs/plans/wayback-archive-job.md` § Interim status). The wayback-archive-job plan owns the steady-state design (out-of-band scheduled archival).

What Tier 1 adds is gap-filling, not rebuild:

1. **Memento Time Travel as a secondary fallback** when archive.org's availability API returns no snapshot. `http://timetravel.mementoweb.org/api/json/{datetime}/{url}` aggregates across non-archive.org archives. Same call site (`tools/wayback.py`), one extra leg before giving up.
2. **Telemetry**: emit `StepError(step="ingest", error_type="wayback_recovered" | "wayback_unavailable" | "memento_unavailable")`. These feed audit-trail review until `dr stats` lands.
3. **No change** to `archived_url` semantics: it remains the canonical archive pointer, written when archival succeeds, regardless of whether the live URL was reachable.

**Coordination**: this plan does **not** flip `skip_wayback` back to `True`. That happens when `wayback-archive-job.md` ships its background-job replacement.

**Effort**: ~1 day (Memento integration + telemetry + tests). Gates on § Schema prerequisites (`acquisition`) + § Shared infrastructure (error-type vocab).

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

**Schema dependency**: `kind: 'paper'` (per § Schema prerequisites). PDF text extraction is **not** wired in this plan — Path 2 ingests the abstract + metadata + landing-page HTML; full-text PDF parsing is deferred (see `source-pdf-attachment.md` for the manual path; an automated PDF reader is Tier 2).

### Architecture amendment (academic affiliation)

`source-quality.md` documents this failure mode: *"Academic articles authored by entity employees are `secondary` by publisher (arxiv, IEEE) and proxied to `independent`. They may functionally be entity-authored content disclosed through a third-party venue."*

Tier 1 resolves it by overriding `independence` at ingest time using OpenAlex affiliation:

- All authors employed by the subject entity (or a same-parent subsidiary, resolved via `parent_company`): `independence: first-party`.
- Mixed authorship (≥1 external author): `independence: independent`.
- Affiliation unavailable: `independence: unknown`. The analyst's restatement test (per `source-quality.md` § Known failure mode) still applies.

This is an explicit amendment to `source-quality.md`. Record the amendment in the same commit as the Path 2 implementation, in a new `docs/architecture/source-quality.md` § v1.x amendments subsection.

**Effort**: 4–6 days (three API integrations, affiliation extraction, classification override, fixtures, instructions update). Gates on § Schema prerequisites + § Shared infrastructure (throttle).

## Path 3 — SEC EDGAR

**Where**: Researcher, conditional on the entity (or its `parent_company`) carrying a `sec_cik` field.

**Schema dependency**: `sec_cik` on the company entity (per § Schema prerequisites). This is the first concrete field on the broader Company-metadata-enrichment idea collected in `source-quality-followups.md` § Company metadata enrichment; the other candidate fields there stay deferred.

**Endpoints**:
- Filing index: `https://data.sec.gov/submissions/CIK{cik}.json`
- Full-text search: `https://efts.sec.gov/LATEST/search-index?q={keywords}&ciks={cik}`
- Filings: `https://www.sec.gov/Archives/edgar/data/...`

**Compliance**: SEC requires a specific `User-Agent` header (`<Org> <contact-email>`) and rate-limits hard at 10 req/sec. Both wire through § Shared infrastructure's throttle and a `SEC_EDGAR_USER_AGENT` env var (no default — the EDGAR path is skipped if unset, with `edgar_ua_missing` emitted).

**False-positive handling**: full-text search returns filings *containing* the keywords, not *about* them. The Researcher's URL scorer evaluates these alongside web-search candidates, so the existing scorer rationale carries the disambiguation. Where the analyst is consuming the source, the surrounding sentence (extracted at ingest time) gives context.

**Investor-corroboration use case**: Anthropic and OpenAI are private companies and don't file with the SEC themselves. Their commercial-partnership and investment claims **are** corroborated through public-investor filings:

- Anthropic via **Amazon** (CIK 0001018724) and **Alphabet/Google** (CIK 0001652044).
- OpenAI via **Microsoft** (CIK 0000789019).

Path 3's value for these claims is the regulator-authority distinction: a 10-K that quantifies a partnership commitment is a stronger source than a press release announcing it.

### Architecture amendment (regulator-authority)

`source-quality.md` documents this failure mode: *"Regulator filings about (not by) the entity are `primary` by publisher rule (sec.gov, ftc.gov) and proxied to `first-party`. The document originates outside the entity but speaks with regulator authority — neither label fits cleanly."*

Tier 1's resolution: keep the existing two-field model (`source_type` + `independence`) and route the distinction through `independence`:

- Filing **by** the subject entity (the entity is the filer, CIK matches): `source_type: primary`, `independence: first-party` — unchanged.
- Filing **about** the subject entity by another filer (subject mentioned but not the filer): `source_type: primary`, `independence: independent`. The override is recorded as a per-source classification at ingest time.

No new `source_type` enum value. The override is a publisher-rule extension in `pipeline/common/source_classification.py`, gated on the EDGAR-ingest path knowing the subject CIK vs the filer CIK.

Record the amendment in the same commit as the Path 3 implementation, in `docs/architecture/source-quality.md` § v1.x amendments.

**Effort**: 5–7 days (entity-loader plumbing for `sec_cik`, UA/throttle, filing parser, classification override, tests). Gates on § Schema prerequisites + § Shared infrastructure.

## Commit sequence

Each row is one focused commit (or a small linked group). All commits land on `main` directly (Brandon's pre-beta convention); the feature flags are how partial work is gated.

1. **Schema commit** — § Schema prerequisites. `kind: 'paper'`, `audit.acquisition`, `sec_cik`. Both TypeScript and Pydantic mirror in one change.
2. **Shared infra commits** (1–4 small commits) — `pipeline/common/throttle.py`, `pipeline/common/canonical_url.py`, audit-trail `acquisition` plumbing in the audit-writer, error-type vocab additions. Land each module in its own commit if it's >50 LOC.
3. **Path 1 commit** — Memento secondary fallback + telemetry. Behind no flag (cheap, additive). ~1 day.
4. **Path 2 commit(s)** — academic-API tools + affiliation rule + `source-quality.md` amendment. Behind `ENABLE_ACADEMIC_RESEARCH` flag. 4–6 days. Optionally split into "API integrations" + "affiliation override + amendment".
5. **Path 3 commit(s)** — EDGAR tool + filer-vs-subject classification override + `source-quality.md` amendment. Behind `ENABLE_EDGAR_RESEARCH` flag. 5–7 days. Optionally split into "EDGAR fetch" + "classification override + amendment".

Paths 1–3 are parallel-able after step 2. Path 1 is so small it can ride alongside step 2 if convenient.

## Rollout order

1. **Schema commit + Shared infrastructure** (steps 1–2 above) — ~3 days. Lands the prerequisites that everything else depends on.
2. After step 1, the following can all start independently — pick whichever order fits available time:
   - **Path 1 (Memento + telemetry)** — ~1 day. Cheapest add; flips on by default since Wayback is already live.
   - **Path 2 (arXiv + S2 + OpenAlex + affiliation rule)** — 4–6 days. Behind `ENABLE_ACADEMIC_RESEARCH`.
   - **Path 3 (SEC EDGAR + classification override)** — 5–7 days. Behind `ENABLE_EDGAR_RESEARCH`.
   - **Companion plan**: [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md) — ~4 days. Behind `RESEARCH_SEARCH_BACKEND`.

None of these four blocks depend on each other; only on step 1. Default-flag flips happen after one operator-validated cycle on the audit-trail data.

**Total effort estimate**: 12–17 days for Tier 1 (Paths 1–3 + shared infra), plus ~4 days for the companion search-backend plan. Down from the previous 16–20 days that bundled all four.

## Per-path success criteria

| Path | Metric | Target |
|---|---|---|
| 1 | `wayback_recovered` rate on terminal fetch failures (combined archive.org + Memento) | ≥ 50% |
| 2 | Tagged-topic claim runs ingesting ≥1 academic source | ≥ 60% on `ai-safety` / `environmental-impact` topics |
| 3 | Public-investor company claims surfacing ≥1 EDGAR document | ≥ 50% of claims where `sec_cik` resolves |
| All | `verification_level` distribution shift toward weakly-sourced verdicts | None (lint already enforces the cap; sidecar carries the level) |

Until `dr stats` lands, these are measured by parsing audit-trail `acquisition` entries and `StepError` events directly from run logs.

## Out of scope

- **Search-backend swap (Tavily).** Owned by [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md).
- **Flipping `skip_wayback` back to `True`.** Owned by `wayback-archive-job.md` (background-job ship).
- **Automated PDF text extraction.** Path 2 ingests metadata + abstract; full PDF reading is Tier 2 (or a follow-on plan to `source-pdf-attachment.md`).
- **`dr stats` subcommand.** Tracked as a follow-up plan; not a Tier 1 deliverable.
- **Energy telemetry.** Tracked in `multi-provider.md` Part 3.
- **A registry-driven publisher trust system.** Deferred to v1.x per `source-quality.md` § Publisher registry.

## File touches

| File | Change |
|------|--------|
| `src/content.config.ts` | § Schema prerequisites: `kind: 'paper'`; `audit.acquisition`; optional `sec_cik` on company entity. |
| `pipeline/common/models.py` | Pydantic mirror of all three schema additions. |
| `pipeline/common/throttle.py` (new) | Per-host-or-API throttle. |
| `pipeline/common/canonical_url.py` (new) | Cross-path URL canonicalization for dedup. |
| `pipeline/researcher/decomposed.py` | Per-path acquisition tag on `SearchCandidate`; canonicalizer at the dedup site (`:62`). |
| `pipeline/researcher/tools/` (new) | `arxiv.py`, `semantic_scholar.py`, `openalex.py`, `edgar.py` — one tool function per API, called from `execute_searches`. |
| `pipeline/ingestor/tools/wayback.py` | Memento secondary fallback; new error-type emissions. |
| `pipeline/common/source_classification.py` | EDGAR filer-vs-subject CIK rule; preprint/journal publisher tags; affiliation-derived `independence` override. |
| `pipeline/common/publisher_quality.py` | Tag arXiv / OpenAlex / SEC publishers. |
| `pipeline/orchestrator/pipeline.py` | New `VerifyConfig` flags (`enable_academic_research`, `enable_edgar_research`); throttle plumbing. |
| `docs/architecture/source-quality.md` | New § v1.x amendments subsection; record the academic-affiliation rule (with Path 2) and EDGAR filer-vs-subject rule (with Path 3). |
| `docs/architecture/research-flow.md` | Update Researcher-internals diagram (§6) for parallel tool dispatch. |
| `docs/architecture/research-workflow.md` | Document new `VerifyConfig` flags under § Pipeline configuration knobs. |
| `AGENTS.md` § Tooling | New env vars (`SEMANTIC_SCHOLAR_API_KEY`, `SEC_EDGAR_USER_AGENT`). Search-backend env vars are in the companion plan. |

Does **not** touch `pipeline/orchestrator/cli.py` — `dr stats` is a separate follow-up plan.

## Open questions

- **Affiliation threshold for "majority external" papers.** A 10-author paper with one entity employee is functionally independent; what about 5/5? Default: any external author flips to `independent`, but flag for analyst review when the entity author count is ≥ half. Decision needed before Path 2 ships.
- **Memento error vocabulary.** When Memento itself is unreachable or rate-limited, emit `memento_unavailable` (added to error vocab) — not `wayback_unavailable`, which is reserved for "no snapshot anywhere." Confirm at implementation time.

Resolved:
- ~~`sec_cik` lookup for entities not yet seeded~~ — manual operator add, matching existing entity-onboard flow. Auto-resolution deferred to follow-up if backlog grows.
- ~~Negative-cache for academic / EDGAR misses~~ — Path 3 skips when `sec_cik` is unset (the gate is the cache); Path 2 negative-cache is per-(entity, topic) and lives in the existing run-cache layer.

## Cross-references

- Companion search-backend plan (Tavily): [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md)
- Independence accounting and amendments: [`docs/architecture/source-quality.md`](../architecture/source-quality.md)
- Researcher internals (parallel tool dispatch): [`docs/architecture/research-flow.md`](../architecture/research-flow.md) § 6
- `VerifyConfig` knobs: [`docs/architecture/research-workflow.md`](../architecture/research-workflow.md) § Pipeline configuration knobs
- Wayback steady-state design: [`docs/plans/wayback-archive-job.md`](wayback-archive-job.md)
- Search vs fetch backend distinction: [`docs/plans/multi-provider.md`](multi-provider.md) § Part 3
- Company metadata enrichment (Tier 1 lands `sec_cik` first): [`docs/plans/source-quality-followups.md`](source-quality-followups.md) § Company metadata enrichment
- Host blocklist interaction: [`docs/plans/researcher-host-blocklist.md`](researcher-host-blocklist.md)
- Recently-completed CLI cleanup (cleared the way for a future `dr stats`): [`docs/plans/completed/dr-cli-output-cleanup_phase2_completed.md`](completed/dr-cli-output-cleanup_phase2_completed.md)
- Tier 2 / Tier 3 follow-up scope: [`docs/plans/source-quality-followups.md`](source-quality-followups.md) § Source pool — Tier 2 and § Source pool — Tier 3

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-08 | agent (opus-4-7) | implementation, iterated | Initial draft asserted file paths and architectural states the codebase did not match. Verified every claim against the repo: corrected `pipeline/researcher/execute_searches.py` → function in `decomposed.py:53`; noted Wayback fallback is already live (`skip_wayback=False` default; `wayback_check` tool registered) and reframed Path 1 from "build" to "gap-fill"; corrected entity path to `research/entities/companies/{slug}.md`; noted `sec_cik` is not in the schema today and routed it through the broader Company-metadata-enrichment idea; corrected `source_type` enum to `primary | secondary | tertiary` (the draft's `regulatory` / `first-party` / `independent` enum names did not exist) and routed the regulator-authority distinction through `independence` instead of a new enum value; flagged `kind: paper` as a missing enum addition; corrected the SEC corroboration example — Anthropic is funded by Amazon (CIK 0001018724) and Alphabet (CIK 0001652044), not Microsoft (CIK 0000789019, which is OpenAI's). Surfaced two source-quality.md amendments out of "open questions" into an explicit "Architecture amendment" subsection per path. Replaced global success metrics with per-path metrics. Added a Shared Infrastructure section. Realistic effort revised from ~6 days to 16–20 days. Coordinated explicitly with `wayback-archive-job.md`, `multi-provider.md` Part 3, `research-quality-ideas.md` company metadata, `researcher-host-blocklist.md`, and `source-quality.md`'s documented v1 imprecisions. Added Tavily/Exa decision rubric and data-handling note. |
| 2026-05-08 | agent (opus-4-7) | iterated | Cross-references rewritten as part of the source-quality plan-family consolidation: `research-quality-ideas.md` and `drafts/source-pool-expansion-tier{2,3}.md` were absorbed into the new `source-quality-followups.md` collector, so this plan now points at the collector's sections instead. Plan body is unchanged. |
| 2026-05-08 | agent (opus-4-7) | implementation, iterated | Three-lens review (correctness, structure, executability/simplification) found 2 schema gaps and recommended structural changes. Changes applied: (1) split Path 4 (search-backend swap) into companion plan `source-pool-expansion-tier1-search-backend.md`, reduced to Tavily-only (Exa deferred), with simplified 2-metric+gate decision rubric and frozen-replay harness interface spec'd; (2) added explicit § Schema prerequisites section with concrete Zod edits (`kind: 'paper'`, `audit.acquisition`, `sec_cik`) sequenced as the first commit; (3) reordered so § Shared infrastructure precedes the Path subsections and renamed it as a prerequisite for Paths 1–3; (4) added § Commit sequence with five focused commits; (5) reframed `dr stats` from "deferred behind CLI cleanup" to "future follow-up plan" after the CLI cleanup landed mid-review; (6) marked two open questions as resolved (sec_cik lookup, negative-cache); (7) added `memento_unavailable` to error vocab; (8) re-baselined effort to 12–17 days for Tier 1 (search-backend's ~4 days lives in the companion plan). |
