# Source Pool Expansion — Tier 1

**Status**: In progress — § Schema prerequisites and § Shared infrastructure landed on `main` 2026-05-08 (commits `a40a09f`, `9a26ba8`, `0e5b1ff`, `98d094c`, `eb200f2`, `11aef7e`, `ee63cae`, `cfc8900`). Paths 1, 2, 3 + the companion search-backend plan are unblocked and may start in parallel.
**Companion plan**: [`source-pool-expansion-tier1-search-backend.md`](completed/source-pool-expansion-tier1-search-backend.md) — search-backend swap (Tavily) split out for independent shipping.
**Created**: 2026-05-08
**Last revised**: 2026-05-08

## Problem

The Researcher → Ingestor pathway currently uses a single search backend (Brave) and a single fetch path (`httpx` + Wayback fallback). Two pressures push the source pool toward `first-party` material:

1. **Paywalls and 403s on tech-news and trade outlets** make independent reporting hard to ingest. The in-pipeline Wayback fallback (`pipeline/ingestor/tools/wayback.py`, default `skip_wayback=False` per `VerifyConfig`) recovers some but not all.
2. **Brave's general-web ranking** mixes vendor-sponsored content, content farms, and stale aggregator pages into the candidate list. The host blocklist (`researcher-host-blocklist.md`) drops the worst offenders but doesn't add new surface area.

`verification_level` is derived from the `independence` distribution of the source pool (see `docs/architecture/source-quality.md`). When the pool skews `first-party`, the cap-and-rationale machinery routes verdicts toward `claimed` / `self-reported` even when independent reporting exists somewhere — it just isn't reachable via the current pathway.

## Goal

Add three never-paywalled, mostly-independent acquisition surfaces (Wayback gap-fill, academic APIs, SEC EDGAR) so the candidate pool routinely includes material the current pathway can't reach. Each path attaches to a specific stage: Wayback gap-fill is an Ingestor fetch fallback; the academic APIs (arXiv, S2, OpenAlex) are Researcher tools called from `execute_searches`; SEC EDGAR is a Researcher tool plus a publisher-classification override.

Tier 1 also fills two documented v1 imprecisions in `source-quality.md` (regulator filings, academic affiliation) and lays the shared infrastructure (throttle, dedup, audit-trail slots, lightweight `dr stats`) that Tier 2, Tier 3, and the companion search-backend plan all reuse.

The search-backend swap (originally Path 4) is now a separate companion plan; see [`source-pool-expansion-tier1-search-backend.md`](completed/source-pool-expansion-tier1-search-backend.md).

## Codebase touchpoints

The plan is anchored to current repo state:

- **Search execution** is `execute_searches()` inside `pipeline/researcher/decomposed.py:53`. Tier 1 adds new tool functions whose results merge into the same `SearchCandidate` list. Each tool is a separately-callable async function (`search_brave`, `search_arxiv`, `search_edgar`, …) with a uniform return shape, so a future state-machine workspace can record each as an independent step entry without restructuring. `execute_searches` becomes a thin gather-and-merge over the activated tool set; the activation decisions (topic-based, CIK-based) live in a small selector function called once before the gather. The backend-swap is in the companion plan.
- **Fetch + Wayback fallback** are `pipeline/ingestor/tools/wayback.py` (functions `check_wayback`, `save_to_wayback`), wired into the ingestor agent and gated by `VerifyConfig.skip_wayback` (default `False` interim; see `wayback-archive-job.md` for the steady-state plan).
- **Source classification** lives in `pipeline/common/source_classification.py` (sets `source_type` from publisher) and `pipeline/common/publisher_quality.py` (tags publisher quality for the scorer).
- **Source schema** is `src/content.config.ts`. `archived_url` already exists. `kind` enum is `report | article | documentation | dataset | blog | video | index` — `paper` is **not** present and is added by Tier 1.
- **`source_type` enum** is `primary | secondary | tertiary`; **`independence` enum** is `first-party | independent | unknown`. The original draft's hypothetical `regulatory` enum value does not exist; regulator-authority distinctions route through `independence`.
- **Entity files** live at `research/entities/companies/{slug}.md`. The entity schema currently has no `sec_cik` field; Tier 1 adds it.
- **Audit sidecar**: the `audit` object in `src/content.config.ts` does not yet carry an `acquisition` slot; Tier 1 adds it.
- **Pipeline config flags** live on `VerifyConfig` in `pipeline/orchestrator/pipeline.py` (existing examples: `skip_wayback`, `max_initial_queries`, per-agent model overrides). New flags follow the same dataclass-field pattern.

## Schema prerequisites

Three schema additions land **first**, in a single commit covering the TypeScript schema and the matching Python-side touches. Each path's code waits on its corresponding field.

| Field | Where | Used by |
|---|---|---|
| `kind: 'paper'` | `src/content.config.ts:16-24` (source schema) + `SourceKind` enum in `pipeline/common/models.py:122-129` | Path 2 |
| `acquisition: { stage, origin, recovered_via?, query?, paper_id?, filing_accession?, outcome? }` per kept URL | Extend `sources_consulted[]` items in `auditSchema` (`src/content.config.ts:42-47`). Per-URL placement keeps acquisition info with the URL it describes; no separate top-level array needed. The `origin` enum value is the per-URL source category (`brave|tavily|arxiv|s2|openalex|edgar`); section-level "Path 1/2/3" is a separate organizing concept. | All paths + companion plan |
| `sec_cik: string` (10-digit, optional) on company entity | `src/content.config.ts:209-224` | Path 3 |

Concrete TypeScript edits (illustrative; coder should match the existing Zod style):

```typescript
// 1. Source kind enum
kind: z.enum(['report', 'article', 'documentation', 'dataset', 'blog', 'video', 'index', 'paper']),

// 2. Acquisition trace, per kept URL (inside auditSchema.sources_consulted[])
sources_consulted: z.array(z.object({
  id: z.string(),
  url: z.string().url(),
  title: z.string(),
  ingested: z.boolean(),
  acquisition: z.object({
    stage: z.enum(['research', 'ingest']),                          // which pipeline stage produced this entry
    origin: z.enum(['brave', 'tavily', 'arxiv', 's2', 'openalex', 'edgar']),  // search backend OR origin API
    recovered_via: z.enum(['archive_org', 'memento']).optional(),   // set only when an Ingestor fallback rescued a fetch
    outcome: z.enum(['matched', 'recovered']).optional(),           // per-URL result; per-tool 'no_results' lives in research_trace
    query: z.string().optional(),
    paper_id: z.string().optional(),
    filing_accession: z.string().optional(),
  }).optional(),
})),

// 3. Company entity sec_cik
sec_cik: z.string().regex(/^\d{10}$/, { message: 'sec_cik must be a 10-digit CIK' }).optional(),
```

**Python-side note.** The audit sidecar has no Pydantic class today: `_write_audit_sidecar` (`pipeline/orchestrator/persistence.py:356-441`) writes a hand-built dict from a `research_trace` parameter. The `acquisition` field is appended to each kept URL's entry in that dict; no Pydantic mirror is added. The only Python-side schema touch is `SourceKind.PAPER = "paper"` in `pipeline/common/models.py:122-129`. `sec_cik` doesn't need a Pydantic class until entity-resolution code grows a typed model — track separately.

These ship as one commit titled along the lines of `feat(schema): add kind:paper, per-URL acquisition trace, sec_cik for tier1 source-pool expansion`.

## Shared infrastructure (prerequisite for all paths + companion plan)

Lands as the **second** commit (or small set of commits, one per module). Once this is in place, Paths 1–3 *and* the companion search-backend plan can all start in parallel — none of them depend on each other, only on this section and § Schema prerequisites.

### Rate-limit / throttle layer

A small per-host-or-API throttle in `pipeline/common/throttle.py`. Each path declares its limits (arXiv 1/3s, S2 1/s anon, OpenAlex 10/s polite, EDGAR 10/s, Tavily per its tier). The closest existing precedent is the Brave 429 sleep-and-retry at `pipeline/researcher/agent.py:50-55` and the orchestrator's analyst-rate-limit retry at `pipeline/orchestrator/pipeline.py:701-703`; both are point-of-use, not generalised. The new module factors out an `async` semaphore-or-token-bucket per host. (`wayback.py` today has only timeouts — `WAYBACK_CHECK_S` / `WAYBACK_SAVE_S` — no throttle; the planned `WAYBACK_RATE_LIMIT_S` described in `wayback-archive-job.md` is not implemented and stays job-scoped if/when it ships.)

### URL deduplication across paths

A single canonical URL form (lowercase host, strip default ports, drop tracking params) before insertion into the `seen` set in `execute_searches`. Today the dedup is exact-string match (`decomposed.py:62`, confirmed). Tracked as part of "Dedup detection on URL ingest" in `docs/UNSCHEDULED.md`; Tier 1 lands the canonicalizer in `pipeline/common/canonical_url.py` for use by the new paths and the existing flow.

### Audit-trail `acquisition` plumbing

The audit sidecar's `research:` block (written by `_write_audit_sidecar` at `pipeline/orchestrator/persistence.py:356-441` from the `research_trace` dict it receives — see `decomposed.py` `out.trace`) currently records planner queries + scorer rationale. The per-URL `acquisition` field added in § Schema prerequisites is appended for every kept URL by every path. Write site is `decomposed.py` extending entries in `out.trace` for Researcher paths; Path 1 extends `vr.research_trace` from the Ingestor side when Wayback or Memento rescues a fetch. The analyst doesn't read this; the operator reads it during review (and `dr stats` reads it for aggregates).

**Resolved — auditor-only refresh path.** The original concern was that `dr re-audit` (`pipeline/orchestrator/cli.py:1390-1418`) re-runs the auditor against an existing sidecar with a fresh `research_trace` and would drop the prior per-URL `acquisition` map on rewrite. Verified during Path 1 review: the refresh flow already preserves prior `acquisition` entries generically by reading them off the existing sidecar before rewrite, so no per-path code is required. Path commits that produce real `acquisition` data inherit the preservation behavior automatically.

### Two event channels (failures vs. per-path outcomes)

Today `StepError.error_type` (`pipeline/orchestrator/checkpoints.py:12-31`) is a free-form `str`, not a closed enum; existing values in production code are `"timeout"`, `"blocked_host"`, `"all_blocked"`, `f"http_{status}"`, `"http_error"`, `"model_error"`, `"api_key_missing"`, `"no_queries"`, `"no_results"`, `"scorer_dropped_all"`. (`http_error` is emitted at `pipeline.py:535` when the ingest exception class name contains `"HTTP"`; `api_key_missing` is emitted at `pipeline.py:485` when `"API key"` appears in a research-stage exception. Both are documented in the `StepError` docstring after the vocab smoke test landed.) Tier 1 keeps the channel free-form and splits new signals along their natural boundary:

1. **Failures** stay on `StepError` (something we wanted to do but couldn't):
   - `wayback_unavailable`, `memento_unavailable` (Path 1)
   - `edgar_ua_missing`, `edgar_rate_limited` (Path 3)
   - `tavily_rate_limited` (companion plan)

2. **Per-path outcomes ride on the audit trail, not the error stream**:
   - Per-kept-URL outcomes (`outcome: 'recovered' | 'matched'`) live on each `sources_consulted[].acquisition` entry — see § Schema prerequisites.
   - Per-tool "fired but found nothing" outcomes (`arxiv_no_results`, `s2_no_results`, `openalex_no_results`, `edgar_no_match`) live in the runtime `research_trace["tool_outcomes"]` array, alongside the existing planner-query and scorer-rationale entries. Not on `StepError`.

This split keeps "X found nothing" out of the error stream and gives the future state-machine workspace a natural per-step outcome home. To keep the `StepError` vocabulary discoverable, document the full set in the `StepError` docstring and grep it in a smoke test (no enum migration needed).

### Observability — `dr stats` (lightweight)

A read-only `dr stats` subcommand lands as a small commit between Path 1 and Path 2. The CLI cleanup that prompted the original deferral has shipped (commit `2839537`); the `--format text|json` precedent is already established by `dr lint --format` and `dr review-queue --format`. Scope is intentionally narrow:

- Walk `list_claims(repo_root)` (`pipeline/common/content_loader.py:50`).
- Read each `.audit.yaml` via `read_sidecar()` (`pipeline/common/sidecar.py:14`).
- Aggregate three counters from the `research:` block + per-URL acquisition: `wayback_recovered` rate, per-path acquisition counts (using `acquisition.origin`), `verification_level` distribution.
- Emit `--format text|json`.
- Sit in the "Read-only" `_COMMAND_GROUPS` bucket (`pipeline/orchestrator/cli.py:102-109`).

Effort: ~0.5–1 day.

## Path 1 — Wayback gap-fill (Ingestor fallback; already live)

The original draft proposed building this. It already exists:

- `wayback_check` is a registered ingestor tool (`pipeline/ingestor/agent.py:115-127`) that calls `check_wayback` (archive.org availability API) and `save_to_wayback` (`pipeline/ingestor/tools/wayback.py:18-77`) when the LLM is reasoning over a terminal fetch failure.
- `VerifyConfig.skip_wayback = False` is the interim default (commit `6409918`, per `docs/plans/wayback-archive-job.md` § Interim status). The wayback-archive-job plan owns the steady-state design (out-of-band scheduled archival).

What Tier 1 adds is gap-filling, not rebuild:

### What lands

1. **Memento Time Travel as a secondary fallback** when archive.org's availability API returns no snapshot. `http://timetravel.mementoweb.org/api/json/{datetime}/{url}` aggregates across non-archive.org archives (a `datetime` of "now" — formatted `YYYYMMDDHHMMSS` — gets the most recent snapshot). The aggregator returns a JSON `mementos.closest.uri` we use as the archived URL. Same call site: a new `check_memento(client, url)` helper alongside `check_wayback` in `pipeline/ingestor/tools/wayback.py`, invoked by `wayback_check` (in `agent.py`) only when the archive.org leg returns `available: False`. One extra leg before giving up.
2. **Telemetry, split per § Two event channels**:
   - **Failures** emit `StepError(step="ingest", error_type="wayback_unavailable" | "memento_unavailable")`. The `wayback_check` tool itself can't raise — it returns dicts the LLM consumes. Bridge via `IngestorDeps`: add a `wayback_failures: list[dict]` field (same shape pattern as the existing `prefetched_bodies` side-channel at `pipeline/ingestor/agent.py:43`); the tool appends `{stage, error_type, message}` entries; `_ingest_one_url` (`pipeline/orchestrator/pipeline.py:580-621`) drains the list post-run and converts entries to `StepError`s **only when the ingest itself failed terminally** (a successful ingest with a transient Memento blip isn't worth noise).
   - **Successes** ride on the audit trail: a per-URL `acquisition` entry with `stage: 'ingest'`, `recovered_via: 'archive_org' | 'memento'`, `outcome: 'recovered'`. Threaded through `IngestorDeps.acquisition_writes: dict[str, dict]` populated by the tool, drained by `_ingest_one_url` into the `research_trace["acquisition"]` map that `_write_audit_sidecar` already grafts onto matching `sources_consulted[]` entries (`pipeline/orchestrator/persistence.py:418-442`).
3. **No change** to `archived_url` semantics: it remains the canonical archive pointer, written when archival succeeds, regardless of whether the live URL was reachable.

### Decisions

- **Memento error vocabulary** (resolves the lone item in § Open questions). `memento_unavailable` is reserved for Memento-aggregator transport failures (timeout, connection error, 5xx). "Memento returned no snapshot" is **not** an error — emit no `StepError`, no `acquisition` entry, the URL stays terminal-failed and shows up in `dr stats`'s `wayback_recovery` denominator unrecovered. Symmetric to the existing archive.org leg, where "no snapshot" returns `{available: False}` without raising.
- **Throttle**. Register `'memento'` on `pipeline/common/throttle.py` at module-import time inside `wayback.py`. Conservative `rate_per_sec=1.0` (the timetravel aggregator fans out across upstream archives — courteous default; revise after live-traffic observation). Archive.org availability stays unthrottled (preserves current behavior; the wayback-archive-job plan owns any future archive.org throttle).
- **Timeout**. Reuse `WAYBACK_CHECK_S` (15s) from `pipeline/common/timeouts.py:24` for the Memento call — same shape as the availability check. No new timeout constant.
- **Auditor-refresh handling**. Already resolved generically: `pipeline/orchestrator/cli.py:1390-1418` reads prior `acquisition` off the existing sidecar's `sources_consulted[]` and re-grafts it onto `research_trace` before rewrite. Path 1 inherits this; no per-path code is required. (The § Audit-trail acquisition plumbing → "Known limitation" note pre-dates that fix and should be flipped to "Resolved" in a later edit.)

### Test surface

Inline `respx` mocks following the `pipeline/tests/test_tools.py:99-177` pattern (no on-disk JSON fixtures — the existing Wayback tests mock the availability and save endpoints directly). Add to `TestCheckWayback`'s sibling class `TestCheckMemento`, plus integration cases that exercise the bridge in `_ingest_one_url`:

| Case | Mock setup | Expected |
|------|------------|----------|
| Archive-only success | archive.org returns `available: True` | No Memento call; `acquisition.recovered_via = 'archive_org'`. |
| Memento rescue | archive.org returns `archived_snapshots: {}`; Memento returns `mementos.closest.uri` | `acquisition.recovered_via = 'memento'`; archived URL set from Memento response. |
| Both no-snapshot | archive.org `{}`; Memento `mementos: {}` | No `acquisition` entry, no `StepError` (silent miss). |
| Memento aggregator down | archive.org `{}`; Memento returns 503 | `StepError(error_type="memento_unavailable")` reaches the orchestrator. |
| Both unavailable | archive.org 500; Memento timeout | `StepError(error_type="wayback_unavailable")` *and* `StepError(error_type="memento_unavailable")` (both legs failed independently). |

Also extend `pipeline/tests/test_step_error_vocab.py` to confirm `memento_unavailable` and `wayback_unavailable` actually appear in production code (the smoke test at `:53-54` only checks they're documented, not emitted).

### Coordination and metric

- **`skip_wayback` stays `False`**: this plan does **not** flip it back to `True`. That belongs to `wayback-archive-job.md`'s background-job ship.
- **Success metric** (per § Per-path success criteria): ≥50% recovered rate. Measured by `dr stats --format json | jq '.wayback_recovery.rate'`; numerator is entries with `acquisition.recovered_via in {archive_org, memento}`, denominator is `stage: 'ingest'` entries (`pipeline/orchestrator/stats.py:48,84-112`).

**Effort**: 1.5–2 days (Memento helper + `IngestorDeps` side-channel plumbing + orchestrator drain + 5 respx test cases + smoke-test extension). Gates on § Schema prerequisites (`acquisition`) + § Shared infrastructure (`throttle.register('memento', ...)`, `StepError` vocabulary already documented).

## Path 2 — Academic APIs (arXiv, Semantic Scholar, OpenAlex)

**Where**: Researcher, parallel to `search_brave`. New tool functions invoked from `decomposed.py:execute_searches` via the selector function (see § Codebase touchpoints). Results merge into the same `SearchCandidate` list before the URL scorer runs.

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

Tier 1 resolves it by overriding `independence` at ingest time using OpenAlex affiliation, in two passes:

1. **Deterministic shortcut** — no model call:
   - All authors employed by the subject entity (or a same-parent subsidiary, resolved via `parent_company`): `independence: first-party`.
   - Affiliation unavailable for every author: `independence: unknown`. The analyst's restatement test (per `source-quality.md` § Known failure mode) still applies.
2. **Mixed authorship** — small classifier:
   - A Haiku-class model with structured output (`IndependenceCall(label: 'first-party' | 'independent', rationale: str)`) sees `(entity_name, parent_company, author_affiliations[], abstract)` and returns the call with a one-sentence rationale recorded on the source. This handles both the obvious "≥1 external author = independent" case and the harder "external authors of record but substantively entity-authored" case (e.g., entity employees as senior authors with external students as first authors). Resolves the threshold question that previously sat in § Open questions.

This is an explicit amendment to `source-quality.md`. Record the amendment in the same commit as the Path 2 implementation, in a new `docs/architecture/source-quality.md` § Independence override rules subsection.

**Effort**: 4–6 days (three API integrations, affiliation extraction, deterministic + classifier passes, fixtures, instructions update). Gates on § Schema prerequisites + § Shared infrastructure (throttle).

## Path 3 — SEC EDGAR

**Where**: Researcher, conditional on the entity (or its `parent_company`) carrying a `sec_cik` field. Activation is decided by the selector function described in § Codebase touchpoints, not by branching inside `execute_searches`.

**Schema dependency**: `sec_cik` on the company entity (per § Schema prerequisites). This is the first concrete field on the broader Company-metadata-enrichment idea collected in `source-quality-followups.md` § Company metadata enrichment; the other candidate fields there stay deferred.

**Endpoints**:
- Filing index: `https://data.sec.gov/submissions/CIK{cik}.json`
- Full-text search: `https://efts.sec.gov/LATEST/search-index?q={keywords}&ciks={cik}`
- Filings: `https://www.sec.gov/Archives/edgar/data/...`

**Compliance**: SEC requires a specific `User-Agent` header (`<Org> <contact-email>`) and rate-limits hard at 10 req/sec. Both wire through § Shared infrastructure's throttle and a `SEC_EDGAR_USER_AGENT` env var (no default — Path 3 is skipped if unset, with `edgar_ua_missing` emitted).

**False-positive handling (small-model disambiguation)**: full-text search returns filings *containing* the keywords, not *about* them. Inside `tools/edgar.py`, before merging into the candidate list, run a small classifier per match: `(entity_name, surrounding_paragraph) → SubjectRelevance(label: 'about' | 'mentioned' | 'unclear', rationale)`. Drop `mentioned` (or downweight before the URL scorer sees it); keep `about` and `unclear`. The classifier is a Haiku-class call, deterministic prompt, no tools — same shape as the existing planner/scorer agents. The label and rationale ride on the per-URL `acquisition` audit entry. This keeps subject-vs-keyword disambiguation out of the URL scorer (which works from title + snippet) and out of the analyst's hands.

**Investor-corroboration use case**: Anthropic and OpenAI are private companies and don't file with the SEC themselves. Their commercial-partnership and investment claims **are** corroborated through public-investor filings:

- Anthropic via **Amazon** (CIK 0001018724) and **Alphabet/Google** (CIK 0001652044).
- OpenAI via **Microsoft** (CIK 0000789019).

Path 3's value for these claims is the regulator-authority distinction: a 10-K that quantifies a partnership commitment is a stronger source than a press release announcing it.

### Architecture amendment (regulator-authority)

`source-quality.md` documents this failure mode: *"Regulator filings about (not by) the entity are `primary` by publisher rule (sec.gov, ftc.gov) and proxied to `first-party`. The document originates outside the entity but speaks with regulator authority — neither label fits cleanly."*

Tier 1's resolution: keep the existing two-field model (`source_type` + `independence`) and route the distinction through `independence`:

- Filing **by** the subject entity (the entity is the filer, CIK matches): `source_type: primary`, `independence: first-party` — unchanged.
- Filing **about** the subject entity by another filer (subject mentioned but not the filer): `source_type: primary`, `independence: independent`. The override is recorded as a per-source classification at ingest time.

No new `source_type` enum value. The override is a publisher-rule extension in `pipeline/common/source_classification.py`, gated on the EDGAR-ingest path knowing the subject CIK vs the filer CIK. The CIK comparison is a string equality check on structured data — correctly deterministic, not a model call.

Record the amendment in the same commit as the Path 3 implementation, in `docs/architecture/source-quality.md` § Independence override rules.

**Effort**: 5–7 days (entity-loader plumbing for `sec_cik`, UA/throttle, filing parser, subject-relevance classifier, classification override, tests). Gates on § Schema prerequisites + § Shared infrastructure.

## Commit sequence

Each row is one focused commit (or a small linked group). All commits land on `main` directly (Brandon's pre-beta convention); per-path activation is gated by the `research_origins` field on `VerifyConfig` (see § Rollout order).

1. **Schema commit** — § Schema prerequisites. `kind: 'paper'`, per-URL `acquisition` on `sources_consulted[]`, `sec_cik`. TypeScript schema + `SourceKind` enum in one change.
2. **Shared infra commits** (1–4 small commits) — `pipeline/common/throttle.py`, `pipeline/common/canonical_url.py`, audit-trail `acquisition` plumbing in `_write_audit_sidecar`, `StepError`-vs-`research_trace` event-channel split. Land each module in its own commit if it's >50 LOC.
3. **Path 1 commit** — Memento secondary fallback + per-URL `acquisition` writes + failure telemetry. Always on (cheap, additive). ~1.5–2 days.
4. **`dr stats` commit** — read-only subcommand + aggregations + tests. ~0.5–1 day. Lands here so Paths 2 and 3 can validate their target metrics via the same command.
5. **Path 2 commit(s)** — arXiv + S2 + OpenAlex tools + selector wiring + deterministic affiliation pass + small-model affiliation classifier + `source-quality.md` amendment. Activated by including `'arxiv'`, `'s2'`, and `'openalex'` in `VerifyConfig.research_origins`. 4–6 days. Optionally split into "API integrations" + "affiliation override + amendment".
6. **Path 3 commit(s)** — EDGAR tool + selector gating on `sec_cik` + small-model subject-relevance classifier + filer-vs-subject classification override + `source-quality.md` amendment. Activated by including `'edgar'` in `VerifyConfig.research_origins`. 5–7 days. Optionally split into "EDGAR fetch + subject classifier" + "classification override + amendment".

Paths 1–3 are parallel-able after step 2. Path 1 is small enough to ride alongside step 2 if convenient; `dr stats` (step 4) is independent of which paths ship.

## Rollout order

1. **Schema commit + Shared infrastructure** (steps 1–2 above) — ~3 days. Lands the prerequisites that everything else depends on.
2. After step 1, the following can all start independently — pick whichever order fits available time:
   - **Path 1 (Memento + telemetry, Wayback gap-fill)** — ~1.5–2 days. Cheapest add; on by default since Wayback is already live.
   - **`dr stats` (lightweight)** — ~0.5–1 day. Read-only; no flag.
   - **Path 2 (arXiv + S2 + OpenAlex + affiliation rules)** — 4–6 days. Activated via `VerifyConfig.research_origins`.
   - **Path 3 (SEC EDGAR + subject-relevance classifier + classification override)** — 5–7 days. Activated via `VerifyConfig.research_origins`.
   - **Companion plan**: [`source-pool-expansion-tier1-search-backend.md`](completed/source-pool-expansion-tier1-search-backend.md) — ~4 days. Behind `RESEARCH_SEARCH_BACKEND` (the companion plan owns its own gating).

None of these blocks depend on each other; only on step 1. Default activations happen after one operator-validated cycle on the audit-trail data (now readable via `dr stats`).

**Why one `research_origins` list instead of per-path booleans.** Three booleans (`ENABLE_ACADEMIC_RESEARCH`, `ENABLE_EDGAR_RESEARCH`, …) encode "is this path enabled" as global config; the long-term direction is a state-machine workspace where each claim's record lists which sources to attempt. A single `research_origins: list[str]` field (default `['tavily']` after the companion search-backend swap landed; grows as paths activate) ports cleanly to that future per-claim listing without an enum-to-list migration. The field name uses "origins" because the values are per-URL source categories (`'brave'`, `'tavily'`, `'arxiv'`, `'edgar'`, …) — the same vocabulary as the schema's `acquisition.origin` enum. Section-level "Path 1/2/3" remains the organizing concept for this plan.

**Total effort estimate**: 12.5–18 days for Tier 1 (Paths 1–3 + shared infra + `dr stats`), plus ~4 days for the companion search-backend plan.

## Per-path success criteria

| Path | Metric | Target |
|---|---|---|
| 1 (Wayback gap-fill) | `outcome: 'recovered'` rate on terminal fetch failures (combined archive.org + Memento) | ≥ 50% |
| 2 (Academic APIs) | Tagged-topic claim runs ingesting ≥1 academic source | ≥ 60% on `ai-safety` / `environmental-impact` topics |
| 3 (SEC EDGAR) | Public-investor company claims surfacing ≥1 EDGAR document | ≥ 50% of claims where `sec_cik` resolves |
| All | `verification_level` distribution shift toward weakly-sourced verdicts | None (lint already enforces the cap; sidecar carries the level) |

Measured via `dr stats --format json` (lands between Path 1 and Path 2, per § Observability).

## Out of scope

- **Search-backend swap (Tavily).** Owned by [`source-pool-expansion-tier1-search-backend.md`](completed/source-pool-expansion-tier1-search-backend.md).
- **Flipping `skip_wayback` back to `True`.** Owned by `wayback-archive-job.md` (background-job ship).
- **Automated PDF text extraction.** Path 2 ingests metadata + abstract; full PDF reading is Tier 2 (or a follow-on plan to `source-pdf-attachment.md`).
- **Energy telemetry.** Tracked in `multi-provider.md` Part 3.
- **A registry-driven publisher trust system.** Deferred to v1.x per `source-quality.md` § Publisher registry.

## File touches

| File | Change |
|------|--------|
| `src/content.config.ts` | § Schema prerequisites: `kind: 'paper'`; per-URL `acquisition` on `sources_consulted[]`; optional `sec_cik` on company entity. |
| `pipeline/common/models.py` | Add `PAPER = "paper"` to the `SourceKind` enum (lines 122-129). The audit sidecar has no Pydantic class today (`_write_audit_sidecar` writes a hand-built dict at `persistence.py:418`); the `acquisition` field threads through that dict directly. |
| `pipeline/common/throttle.py` (new) | Per-host-or-API throttle. |
| `pipeline/common/canonical_url.py` (new) | Cross-path URL canonicalization for dedup. |
| `pipeline/researcher/decomposed.py` | Selector function deciding active paths per claim; thin gather-and-merge over the activated tools; per-URL acquisition tag on `SearchCandidate`; canonicalizer at the dedup site (`:62`). |
| `pipeline/researcher/tools/` (new) | `arxiv.py`, `semantic_scholar.py`, `openalex.py`, `edgar.py` — one tool function per API, called from `execute_searches`. |
| `pipeline/researcher/agents/` (extended) | Small classifiers: `IndependenceCall` (mixed-authorship affiliation) and `SubjectRelevance` (EDGAR full-text disambiguation). Same Haiku-class shape as planner/scorer agents. |
| `pipeline/ingestor/tools/wayback.py` | Memento secondary fallback; per-URL acquisition writes; failure `StepError` emissions. |
| `pipeline/orchestrator/persistence.py` | `_write_audit_sidecar` threads `acquisition` entries through the existing `research_trace` dict; new `tool_outcomes` array for "tool fired, found nothing" runtime trace. |
| `pipeline/common/source_classification.py` | EDGAR filer-vs-subject CIK rule; preprint/journal publisher tags; affiliation-derived `independence` override (deterministic + classifier-driven). |
| `pipeline/common/publisher_quality.py` | Tag arXiv / OpenAlex / SEC publishers. |
| `pipeline/orchestrator/pipeline.py` | New `VerifyConfig.research_origins: list[str]` (default `['tavily']` since the companion search-backend swap; was originally `['brave']`); throttle plumbing. |
| `pipeline/orchestrator/cli.py` | New `dr stats` subcommand (read-only; `--format text\|json`) reading `research:` + per-URL `acquisition` aggregates from sidecars. Sits in the "Read-only" `_COMMAND_GROUPS` bucket. |
| `pipeline/orchestrator/checkpoints.py` | Document the full `StepError.error_type` vocabulary in the docstring; no enum migration. |
| `docs/architecture/source-quality.md` | New § Independence override rules subsection; record the academic-affiliation rule (with Path 2) and EDGAR filer-vs-subject rule (with Path 3). |
| `docs/architecture/research-flow.md` | Update Researcher-internals diagram (§6) for parallel tool dispatch and the new selector function. |
| `docs/architecture/research-workflow.md` | Document `VerifyConfig.research_origins` under § Pipeline configuration knobs. |
| `AGENTS.md` § Tooling | New env vars (`SEMANTIC_SCHOLAR_API_KEY`, `SEC_EDGAR_USER_AGENT`). Search-backend env vars are in the companion plan. |

## Open questions

(none currently open)

Resolved:
- ~~Memento error vocabulary~~ — `memento_unavailable` is reserved for aggregator transport failures (timeout / connection error / 5xx); "Memento returned no snapshot" is a silent miss (no `StepError`, no `acquisition` entry). `wayback_unavailable` covers the archive.org leg under the same rule. See Path 1 § Decisions.
- ~~Affiliation threshold for "majority external" papers~~ — handled by the `IndependenceCall` small-model classifier (see § Architecture amendment, Path 2); no static threshold needed.
- ~~`sec_cik` lookup for entities not yet seeded~~ — manual operator add, matching existing entity-onboard flow. Auto-resolution deferred to follow-up if backlog grows.
- ~~Negative-cache for academic / EDGAR misses~~ — Path 3 skips when `sec_cik` is unset (the gate is the cache); Path 2 negative-cache is per-(entity, topic) and lives in the existing run-cache layer.

## Cross-references

- Companion search-backend plan (Tavily): [`source-pool-expansion-tier1-search-backend.md`](completed/source-pool-expansion-tier1-search-backend.md)
- Follow-on to the Tavily search-backend plan (`raw_content` passthrough to skip httpx fetch on Cloudflare-shielded URLs): [`ingestor-tavily-prefetch.md`](completed/ingestor-tavily-prefetch.md). Inherits Tier 1's `acquisition` schema unchanged — no new enum values or keys.
- Independence accounting and amendments: [`docs/architecture/source-quality.md`](../architecture/source-quality.md)
- Researcher internals (parallel tool dispatch): [`docs/architecture/research-flow.md`](../architecture/research-flow.md) § 6
- `VerifyConfig` knobs: [`docs/architecture/research-workflow.md`](../architecture/research-workflow.md) § Pipeline configuration knobs
- Wayback steady-state design: [`docs/plans/wayback-archive-job.md`](wayback-archive-job.md)
- Search vs fetch backend distinction: [`docs/plans/multi-provider.md`](multi-provider.md) § Part 3
- Company metadata enrichment (Tier 1 lands `sec_cik` first): [`docs/plans/source-quality-followups.md`](source-quality-followups.md) § Company metadata enrichment
- Host blocklist interaction: [`docs/plans/researcher-host-blocklist.md`](researcher-host-blocklist.md)
- Recently-completed CLI cleanup that unblocked the in-Tier-1 `dr stats` subcommand: [`docs/plans/completed/dr-cli-output-cleanup_phase2_completed.md`](completed/dr-cli-output-cleanup_phase2_completed.md)
- Tier 2 / Tier 3 follow-up scope: [`docs/plans/source-quality-followups.md`](source-quality-followups.md) § Source pool — Tier 2 and § Source pool — Tier 3

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-08 | agent (opus-4-7) | implementation, iterated | Initial draft asserted file paths and architectural states the codebase did not match. Verified every claim against the repo: corrected `pipeline/researcher/execute_searches.py` → function in `decomposed.py:53`; noted Wayback fallback is already live (`skip_wayback=False` default; `wayback_check` tool registered) and reframed Path 1 from "build" to "gap-fill"; corrected entity path to `research/entities/companies/{slug}.md`; noted `sec_cik` is not in the schema today and routed it through the broader Company-metadata-enrichment idea; corrected `source_type` enum to `primary | secondary | tertiary` (the draft's `regulatory` / `first-party` / `independent` enum names did not exist) and routed the regulator-authority distinction through `independence` instead of a new enum value; flagged `kind: paper` as a missing enum addition; corrected the SEC corroboration example — Anthropic is funded by Amazon (CIK 0001018724) and Alphabet (CIK 0001652044), not Microsoft (CIK 0000789019, which is OpenAI's). Surfaced two source-quality.md amendments out of "open questions" into an explicit "Architecture amendment" subsection per path. Replaced global success metrics with per-path metrics. Added a Shared Infrastructure section. Realistic effort revised from ~6 days to 16–20 days. Coordinated explicitly with `wayback-archive-job.md`, `multi-provider.md` Part 3, `research-quality-ideas.md` company metadata, `researcher-host-blocklist.md`, and `source-quality.md`'s documented v1 imprecisions. Added Tavily/Exa decision rubric and data-handling note. |
| 2026-05-08 | agent (opus-4-7) | iterated | Cross-references rewritten as part of the source-quality plan-family consolidation: `research-quality-ideas.md` and `drafts/source-pool-expansion-tier{2,3}.md` were absorbed into the new `source-quality-followups.md` collector, so this plan now points at the collector's sections instead. Plan body is unchanged. |
| 2026-05-08 | agent (opus-4-7) | implementation, iterated | Three-lens review (correctness, structure, executability/simplification) found 2 schema gaps and recommended structural changes. Changes applied: (1) split Path 4 (search-backend swap) into companion plan `source-pool-expansion-tier1-search-backend.md`, reduced to Tavily-only (Exa deferred), with simplified 2-metric+gate decision rubric and frozen-replay harness interface spec'd; (2) added explicit § Schema prerequisites section with concrete Zod edits (`kind: 'paper'`, `audit.acquisition`, `sec_cik`) sequenced as the first commit; (3) reordered so § Shared infrastructure precedes the Path subsections and renamed it as a prerequisite for Paths 1–3; (4) added § Commit sequence with five focused commits; (5) reframed `dr stats` from "deferred behind CLI cleanup" to "future follow-up plan" after the CLI cleanup landed mid-review; (6) marked two open questions as resolved (sec_cik lookup, negative-cache); (7) added `memento_unavailable` to error vocab; (8) re-baselined effort to 12–17 days for Tier 1 (search-backend's ~4 days lives in the companion plan). |
| 2026-05-08 | agent (opus-4-7) | post-implementation findings | Schema commit + 6 shared-infra commits landed. Two corrections folded back into the plan: (1) the `StepError.error_type` "currently in-use" enumeration in § Two event channels missed `api_key_missing` (`pipeline.py:485`) and `http_error` (`pipeline.py:535`); both now listed and the smoke test guards against further drift. (2) Added a § Audit-trail acquisition plumbing → "Known limitation — auditor-only refresh path" note flagging that `cli.py:1390`'s `dr re-audit` flow drops the `acquisition` map on rewrite; the first path commit producing real `acquisition` data must preserve it (read-from-existing-sidecar) or re-derive it. Acceptable until then since no producers exist. |
| 2026-05-08 | agent (opus-4-7) | family cross-review (prefetch follow-on) | Added `ingestor-tavily-prefetch.md` to § Cross-references as a follow-on to the Tavily companion plan. No schema-prerequisite edits: cross-review confirmed that the prefetch plan's audit-trail design rides on the existing `acquisition` shape (`origin: 'tavily'`, `stage: 'research'`) without adding keys or enum values. Verification: the prefetch plan's own draft initially proposed an `acquisition[url]["prefetched"] = True` stamp; that contradicted its "no schema change" claim and was dropped during cross-review (recorded in the prefetch plan's review history). |
| 2026-05-08 | agent (opus-4-7) | Path 1 concretization | Path 1 rewritten before implementation. Added concrete decisions the section had punted on: (1) **StepError emission mechanism** — the `wayback_check` ingestor tool can't raise (it returns dicts the LLM consumes), so failures bridge via a new `IngestorDeps.wayback_failures` side-channel (same shape pattern as `prefetched_bodies` at `agent.py:43`), drained by `_ingest_one_url` (`pipeline.py:580-621`) only when the ingest itself failed terminally. Successes ride through `IngestorDeps.acquisition_writes` into `research_trace["acquisition"]`, picked up by the existing graft at `persistence.py:418-442`. (2) **Memento throttle** — register `'memento'` at module-import in `wayback.py` with conservative `rate_per_sec=1.0`; archive.org stays unthrottled. (3) **Memento timeout** — reuse `WAYBACK_CHECK_S` (15s) from `common/timeouts.py:24`; no new constant. (4) **Memento error vocabulary** — closed the lone open question: `memento_unavailable` covers aggregator transport failures only; "no snapshot" is a silent miss. Symmetric to archive.org leg. (5) **Auditor-refresh choice** — none needed; `cli.py:1390-1418` already preserves prior `acquisition` on rewrite generically (the §95 "known limitation" note pre-dates that fix). (6) **Test surface** — five named `respx` mock cases (archive-only, memento-rescue, both-no-snapshot, memento-down, both-down) following `tests/test_tools.py:99-177`; no on-disk fixtures. Smoke-test `memento_unavailable`/`wayback_unavailable` actually emit. (7) **Success metric** — pointed at `dr stats --format json | jq '.wayback_recovery.rate'` with field origin in `orchestrator/stats.py:48,84-112`. (8) **Effort** re-baselined from ~1 day to 1.5–2 days (telemetry plumbing + 5 cases + smoke-test extension). |
| 2026-05-08 | parallel agents (opus-4-7) | concrete-readiness + architectural-lens review | Two-agent parallel review against five seed questions (dr-stats inclusion, schema/infra readiness, language clarity, state-machine direction, small-models-for-small-tasks). Findings applied: **(1)** `dr stats` folded into Tier 1 as a small ~0.5–1 day commit between Path 1 and Path 2; CLI-cleanup blocker shipped in `2839537`. **(2)** Schema corrections — `acquisition` now lives per-URL inside `sources_consulted[]` items (not a top-level array); reshaped to `{stage, origin, recovered_via?, query?, paper_id?, filing_accession?, outcome?}` to stop conflating search backends, fetch fallbacks, and origin APIs under one `path` enum; "Pydantic mirror" framing dropped (no audit Pydantic class exists; `_write_audit_sidecar` is dict-based at `persistence.py:418`); only Python-side schema touch is `SourceKind.PAPER`. **(3)** Wayback throttle precedent claim corrected — `wayback.py` has timeouts only; closest existing precedent is `pipeline/researcher/agent.py:50-55` and `pipeline/orchestrator/pipeline.py:701-703`. **(4)** `StepError.error_type` reframed as the free-form `str` it already is (not a closed enum); event channels split — failures stay on `StepError`, per-URL outcomes ride on `acquisition.outcome`, per-tool "no results" goes to `research_trace["tool_outcomes"]`. **(5)** `execute_searches` reframed as thin gather-and-merge over a selector-chosen tool set, isolating activation decisions for future state-machine extraction. **(6)** Three per-path booleans collapsed into one `VerifyConfig.research_origins: list[str]` field, ports cleanly to a per-claim workspace listing later. **(7)** Two small-model classifiers added: `IndependenceCall` for mixed-authorship affiliation (resolves the threshold open question), `SubjectRelevance` for EDGAR full-text disambiguation (keeps subject-vs-keyword work out of the URL scorer). Filer-vs-subject CIK rule flagged as correctly deterministic. **(8)** `v1.x amendments` subsection renamed to `Independence override rules`. Effort re-baselined to 12.5–18 days. **(Reverted in same session)**: An interim Path → Origin section-heading rename was reverted because it broke "Paths 1–3" / "Path 4" cross-references in `source-pool-expansion-tier1-search-backend.md` and `source-quality-followups.md`. Section organization stays "Path 1/2/3"; `origin` lives only as the per-URL schema enum value and as the `research_origins` config field name (its values are per-URL source categories — `'brave'`, `'arxiv'`, `'edgar'`, …). |
