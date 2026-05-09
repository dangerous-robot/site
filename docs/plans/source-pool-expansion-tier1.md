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

**Path-owned schema extensions** (land in their respective Path commits, not in the prereq commit):
- Path 2 extends `acquisition` with optional `affiliation_decision: { label, rationale, source }` for OpenAlex affiliation overrides — see § Path 2 → Affiliation override.

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

**Where**: Researcher, parallel to `search_brave` / `search_tavily`. New tool functions invoked from `decomposed.py:execute_searches` via the selector function (see § Codebase touchpoints). Results merge into the same `SearchCandidate` list before the URL scorer runs.

**Trigger**: claim's criterion topics (`template.topics` per `src/content.config.ts:249-258`) intersect `{ai-safety, environmental-impact, industry-analysis}`. Other topics skip the academic dispatch.

**Topic plumbing prerequisite.** `decomposed_research` does not currently receive topics; the orchestrator has them at the call site (`pipeline.py:1530`, `cli.py:889`) but doesn't pass them. Path 2 adds an optional `topics: list[str] = []` parameter to `verify_claim`, `_research`, and `decomposed_research`, threaded through to a new `_select_research_origins(cfg, topics)` selector inside `execute_searches`. Empty `topics` means "no claim context" (e.g., `dr claim-probe` ad-hoc claims): Path 2 is **off** in that case (cheaper default; the operator can re-run `dr claim-refresh` once a `criteria_slug` exists). The orchestrator changes are small (one new kwarg threaded through three call sites) and ride in the Path 2 commit.

### Endpoints and auth

| API | Endpoint | Auth | Throttle | What it returns |
|-----|----------|------|----------|-----------------|
| arXiv | `https://export.arxiv.org/api/query?search_query={q}&start=0&max_results=10` (Atom XML) | none | `register('arxiv', rate_per_sec=1/3.0, burst=1)` per arXiv API guidelines | abstract, authors (free-text), primary category, arxiv_id |
| Semantic Scholar | `https://api.semanticscholar.org/graph/v1/paper/search?query={q}&fields=title,abstract,authors.name,authors.affiliations,externalIds,url&limit=10` | optional `x-api-key: ${SEMANTIC_SCHOLAR_API_KEY}` | `register('s2', rate_per_sec=1.0, burst=1)` anon; bump to 10/s when key present | abstract, authors with best-effort affiliations, externalIds (DOI, arXiv) |
| OpenAlex | `https://api.openalex.org/works?search={q}&per-page=10&mailto=${OPENALEX_MAILTO}` (polite pool) | none; UA carries `mailto=` | `register('openalex', rate_per_sec=10.0, burst=10)` | structured authorships with `institutions[]` (display_name, ror, country_code), abstract_inverted_index, doi |

OpenAlex is the affiliation source of truth; arXiv/S2 are corroborators. The polite-pool UA needs an `OPENALEX_MAILTO` env var (no default; if unset, fall through to anonymous pool with throttle dropped to 1/s — symmetric with the S2-no-key path). Document in `AGENTS.md` § Tooling.

### Selector and tool shape

```python
# pipeline/researcher/decomposed.py
_ACADEMIC_TOPICS: frozenset[str] = frozenset({
    "ai-safety", "environmental-impact", "industry-analysis",
})

def _select_research_origins(cfg: VerifyConfig, topics: list[str]) -> list[str]:
    """Decide which Researcher tools fire for this claim.

    Returns a subset of cfg.research_origins. `search_backend` (brave/tavily)
    always runs as the general-web spine; academic tools fire only when the
    claim carries one of _ACADEMIC_TOPICS AND the corresponding origin is
    enabled in cfg.research_origins. Empty topics keeps academics off
    (no criterion context, e.g. claim-probe).
    """
```

Each new tool is a separately-callable async function (mirrors `search_brave`/`search_tavily`):

```python
# pipeline/researcher/tools/arxiv.py (siblings: semantic_scholar.py, openalex.py)
async def search_arxiv(client: httpx.AsyncClient, query: str, max_results: int = 10) -> list[dict]:
    """Returns dicts shaped {url, title, snippet, paper_id, authors, raw_content=None}.
    `paper_id` carries the arXiv id (or DOI for S2/OpenAlex) for downstream
    affiliation resolution and the audit-trail entry. Same dispatch shape
    as search_brave/search_tavily."""
```

Activation lives in `_select_research_origins`, called once before the gather; `execute_searches` becomes a thin gather-and-merge over the activated tool set. Per-API failure isolation: each tool is wrapped in a per-tool dispatch helper that returns `(results, origin_used)` on success and an empty list + `tool_outcomes` entry on a clean miss. Transport failures (timeouts, 5xx) surface to the orchestrator via `errors_out: list[StepError]` (see § Failures emitted, below). Academic tools do **not** fall back to a different backend the way Tavily falls back to Brave at `decomposed.py:84-108` (they are complementary sources, not interchangeable ones); copying Tavily's fallback semantics here is a bug, not a feature.

### Throttle registration

Each tool registers its bucket at module-import time, mirroring `pipeline/researcher/tools/tavily.py:50-66`'s `_ensure_throttle_registered()` pattern. Idempotent re-registration; tests reset between runs. No new constants in `pipeline/common/timeouts.py`; reuse the per-call `httpx` 15s timeout that Tavily uses (`tavily.py:115`).

### Negative cache (per-claim)

Path 2's "skip when topic doesn't match" gate is the cache: there is no separate run-cache layer in the codebase today. The selector is a deterministic function of `(cfg.research_origins, topics)`, called once per claim — no memoisation needed. The "negative-cache" item under § Open questions → Resolved referred to that selector being cheap and pure; reframed there for accuracy.

### Affiliation override (cross-stage)

OpenAlex affiliations are captured at Researcher time, but `independence` is set at Ingest time by `pipeline/common/source_classification.py:103`. The override needs a vehicle:

- The OpenAlex tool stamps `acquisition[url]` with a new optional sub-field `affiliation_decision: {label: 'first-party' | 'independent' | 'unknown', rationale: str, source: 'deterministic' | 'classifier'}` (added to the per-URL `acquisition` block from § Schema prerequisites — extends the existing dict, no new top-level field).
- `_ingest_one` reads it via `IngestorDeps.acquisition_in: dict[str, dict]` (new side-channel, sibling to `prefetched_bodies` and `acquisition_writes`) and passes the label to `classify_source_type` / `independence_for_source_type`.
- `pipeline/common/source_classification.py` grows a new helper `apply_affiliation_override(base_independence, override_label) -> str` so the rule is one decision point, not scattered.

The schema impact is one optional sub-field on `acquisition` (not a new origin enum value, not a new top-level key). Add to the Zod object in § Schema prerequisites in the same commit; the smoke test for the audit sidecar (auditor-refresh preservation) stays correct because the field rides inside `acquisition` and the existing graft preserves the whole dict.

### `IndependenceCall` classifier

Two-pass affiliation logic. The deterministic pass runs always; the classifier fires only when the deterministic pass returns `unknown` AND at least one author has a known affiliation (mixed authorship). No author has affiliation -> deterministic `unknown`, no model call. All authors at the entity -> deterministic `first-party`, no model call.

```python
# pipeline/researcher/independence_classifier.py (or pipeline/researcher/agents/independence.py
# if the agents/ subdir is created — see "Decisions" below)
class IndependenceCall(BaseModel):
    label: Literal['first-party', 'independent']
    rationale: str = Field(max_length=240)

independence_classifier_agent = Agent(
    "test",  # resolved per-call via .override(model=resolve_model(cfg.model_for("researcher")))
    output_type=IndependenceCall,
    system_prompt=_INDEPENDENCE_INSTRUCTIONS,
    retries=2,
)
```

Same shape as `research_planner_agent` and `url_scorer_agent` (both at `pipeline/researcher/planner.py:43` and `scorer.py:64`). Prompt sketch: receives `(entity_name, parent_company, author_affiliations[], abstract)`; returns `first-party` only when authorships are substantively from the subject entity (entity employees as senior or majority authors), else `independent`. The rationale lands in `acquisition.affiliation_decision.rationale` for operator review.

Error/timeout behaviour mirrors the planner (`decomposed.py:244-249`): `asyncio.wait_for(..., timeout=cfg.research_timeout_s)`; on timeout or model error the affiliation override defaults to `unknown` (analyst restatement test still applies) and a `tool_outcomes` entry records the miss. No `StepError` for classifier failures (the academic tool itself succeeded; only the override is degraded).

### Failures emitted to `StepError`

Academic-API failures stay narrow and use the existing `model_error` / `timeout` / `http_error` vocabulary; no new literals. Concretely:

- arXiv / S2 / OpenAlex transport failures (timeout, connection error, 5xx) -> `StepError(step="research", error_type="http_error" | "timeout")`. These piggyback on the existing channel; no docstring update needed.
- Per-tool clean misses ("found nothing") ride on `research_trace["tool_outcomes"]` per § Two event channels, not on the error stream. Entries shaped `{tool: 'arxiv'|'s2'|'openalex', query, outcome: 'no_results'}`.
- Classifier failures: silent degrade to `unknown` (see above).

This means the smoke test in `pipeline/tests/test_step_error_vocab.py` does **not** need a Path 2 update. (Contrast with Path 1's `memento_unavailable` and Path 3's `edgar_*` literals.)

### Audit-trail writes (per-URL)

Each kept URL from an academic tool gets one `acquisition` entry, written by `execute_searches` (extending the existing pattern at `decomposed.py:187-192` that already writes `{stage, origin, query}` for Brave/Tavily):

| Field | Value |
|-------|-------|
| `stage` | `'research'` |
| `origin` | `'arxiv' \| 's2' \| 'openalex'` |
| `query` | the planner query that produced this hit |
| `paper_id` | arXiv id, DOI, or OpenAlex work id (whichever the tool natively returns) |
| `affiliation_decision` (OpenAlex only) | `{label, rationale, source}` (see § Affiliation override above) |

Per-tool "no results" lands in `research_trace["tool_outcomes"]` (init'd at `decomposed.py:216`), not on per-URL acquisition.

### Decisions

- **Topics plumbing**: parameter threading, not inference. Adds `topics: list[str]` to three function signatures (`verify_claim`, `_research`, `decomposed_research`) wired from the orchestrator's existing `template.topics`. `claim-probe` passes `[]` (Path 2 off). One commit, one test confirming the kwarg flows end-to-end (mock `_select_research_origins` and assert it sees the topic list).
- **`agents/` subdirectory**: today's pattern is one file per agent at `pipeline/researcher/` top level (`planner.py`, `scorer.py`). Path 2 follows the same pattern: new module `pipeline/researcher/independence_classifier.py`. (The plan's File touches table line 298 implies a new `agents/` subdir; flag and update the table at implementation time, OR create the subdir and migrate planner.py/scorer.py in a separate refactor commit. Keep Path 2 narrow.)
- **Classifier trigger**: deterministic-shortcut fallback only. Fires per-OpenAlex-paper, only when at least one author has affiliation AND not all authors map to the subject entity. Never fires for arXiv/S2 results (they don't have structured affiliation; deterministic pass always returns `unknown` for them).
- **Affiliation matching algorithm**: case-insensitive substring match of `entity_name` (and `parent_company` if present) against each `institutions[].display_name` returned by OpenAlex. Same-parent subsidiary resolution: load the subject entity's `parent_company` slug, look up sibling entities under the same parent, build the alias set from each sibling's `name` + `aliases[]`. Substring match is intentionally lenient; false-positives surface in operator review via the `rationale` field.
- **`OPENALEX_MAILTO`**: recommended, not required. When set, the tool joins OpenAlex's polite pool (10/s) and the bucket registers at that rate. When unset, the tool logs once at startup (mirroring Tavily's `TAVILY_API_KEY` warning at `decomposed.py:149-154`) and registers the bucket at 1/s anon. The selection happens at first-call time, not module-import, so the throttle rate matches the actually-used pool. Document in `AGENTS.md` § Tooling alongside `SEMANTIC_SCHOLAR_API_KEY`.
- **Host blocklist interaction**: arxiv.org, semanticscholar.org, openalex.org are not on `research/blocklist.yaml` (verified). Academic tool URLs flow through `_apply_blocklist_cap` (`pipeline/orchestrator/pipeline.py:486`) like every other origin; no special-casing. Preprint mirrors (e.g. `arxiv-vanity.com`) are out of scope; only the canonical hosts are queried.
- **Publisher-quality tags**: `arxiv` already lives in `_SECONDARY_PUBLISHERS` (`pipeline/common/source_classification.py:30-45`); `semanticscholar`, `openalex` are added in the same commit so the URL scorer's `publisher_quality` hint is correct from day one. `pipeline/common/publisher_quality.py` re-imports the same set, so the hostname classifier picks the new tags up automatically.

### Architecture amendment (academic affiliation)

`source-quality.md` documents this failure mode: *"Academic articles authored by entity employees are `secondary` by publisher (arxiv, IEEE) and proxied to `independent`. They may functionally be entity-authored content disclosed through a third-party venue."*

Tier 1's resolution is the deterministic + classifier pass described above. This is an explicit amendment to `source-quality.md`. Record the amendment in the same commit as the Path 2 implementation, in the `docs/architecture/source-quality.md` § Independence override rules subsection introduced by Path 3.

### Test surface

Inline `respx` mocks following the `pipeline/tests/test_tavily_search.py` pattern (per-API test class with `_reset_throttle` autouse fixture and a `_<api>_key`/`_<api>_mailto` env fixture where applicable):

| Case | Mock setup | Expected |
|------|------------|----------|
| arXiv success | Atom XML body with two entries | Two `SearchCandidate`s with `acquisition.origin='arxiv'`, `paper_id` set; throttle bucket consumes one token. |
| arXiv timeout | `httpx.ReadTimeout` | `StepError(error_type='timeout')`; `tool_outcomes` empty (transport failure, not a clean miss). |
| S2 no key, anon throttle | env unset; mock 200 with one result | One candidate; warning logged once; throttle at 1/s. |
| S2 with key, faster throttle | env set; mock 200 | Same shape; throttle at 10/s; `x-api-key` header sent. |
| S2 5xx | 503 response | `StepError(error_type='http_error')`. |
| OpenAlex success + deterministic first-party | OpenAlex result, all authors at "Anthropic" | `acquisition.affiliation_decision = {label: 'first-party', source: 'deterministic'}`; classifier not invoked. |
| OpenAlex success + deterministic unknown | OpenAlex result, all authors with `institutions: []` | `affiliation_decision.label = 'unknown'`; classifier not invoked. |
| OpenAlex mixed authorship -> classifier | one entity author, one external author | Classifier invoked; `affiliation_decision.source = 'classifier'`; deterministic label and rationale recorded. |
| OpenAlex classifier timeout | `wait_for` raises | `affiliation_decision.label = 'unknown'`; `tool_outcomes` records the miss; no `StepError`. |
| OpenAlex no `mailto` env | env unset | Anon-pool throttle at 1/s; one warning logged. |
| Selector: tagged topic | `topics=['ai-safety']`, all three origins enabled | All three academic tools dispatched in `gather`. |
| Selector: untagged topic | `topics=['data-privacy']` | Academic tools skipped; only general-web backend runs. |
| Selector: empty topics | `topics=[]` (claim-probe) | Academic tools skipped. |
| Cross-stage affiliation override | OpenAlex stamps `affiliation_decision.label='first-party'`; ingest classifies | Source file's `independence` lands as `first-party` despite arxiv-publisher rule. End-to-end test in `test_research_integration.py` style. |

Also extend `pipeline/tests/test_cli_stats.py` to confirm the academic-origin counts increment in `acquisition_origins` (the aggregator already lists arxiv/s2/openalex per `pipeline/orchestrator/stats.py:34-41`).

### Coordination and metric

- **Success metric** (per § Per-path success criteria): ≥60% of tagged-topic claim runs ingest at least one academic source. The current `dr stats` aggregate at `pipeline/orchestrator/stats.py:118-136` counts per-origin URLs across all sidecars but does **not** segment by claim topic. Path 2 adds a fourth aggregate `academic_topic_coverage` to `compute_stats`: walk claims, filter to those whose `topics` intersect `_ACADEMIC_TOPICS`, count claims with ≥1 source whose `acquisition.origin` is in `{arxiv, s2, openalex}`. Measurement command: `dr stats --format json | jq '.academic_topic_coverage.rate'`. Field origins: claim topics from `parse_frontmatter` on each claim file (already loaded for the verification-level aggregate at `stats.py:65-73`); academic origin set defined alongside `ACQUISITION_ORIGINS` at `stats.py:34-41`.
- **Coordination with Path 1**: independent. Both write to `acquisition` per kept URL; Path 1 at ingest stage with `recovered_via`, Path 2 at research stage with `paper_id` and (for OpenAlex) `affiliation_decision`. No shared touchpoint other than the schema slot, which is already shipped.
- **Coordination with Path 3**: independent. Both add per-tool `tool_outcomes` entries; both extend `_SECONDARY_PUBLISHERS` (Path 2 adds `semanticscholar`, `openalex`); the affiliation-override and filer-vs-subject-CIK logic both extend `pipeline/common/source_classification.py` but at different decision points. Land Path 2's amendment first if both ship in the same week so Path 3's amendment can reference the existing § Independence override rules subsection.

### Effort breakdown

5–7 days, broken down:

- Topic plumbing through `verify_claim` → `_research` → `decomposed_research` (1 commit, ~0.5 day).
- arXiv tool + Atom-XML parser + 2 respx tests (~0.5 day).
- S2 tool + key-vs-anon throttle + 3 respx tests (~0.5 day).
- OpenAlex tool + affiliation extraction + same-parent subsidiary resolution + 4 respx tests (~1 day).
- `_select_research_origins` selector + `execute_searches` gather-and-merge refactor + 3 selector tests (~0.5 day).
- Schema extension: `acquisition.affiliation_decision` Zod sub-field (~0.25 day).
- `apply_affiliation_override` helper in `source_classification.py` + Ingestor `IngestorDeps.acquisition_in` plumbing + 2 cross-stage tests (~1 day).
- `IndependenceCall` classifier module + prompt + structured output + override path + 3 tests (~1 day).
- `dr stats` `academic_topic_coverage` aggregate + 2 tests (~0.5 day).
- `source-quality.md` § Independence override rules amendment + `AGENTS.md` env var docs (~0.25 day).

Range covers prompt iteration on the `IndependenceCall` classifier (the harder-to-budget item) and possible affiliation-matching edge cases on real OpenAlex payloads. Gates on § Schema prerequisites + § Shared infrastructure (throttle).

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
5. **Path 2 commit(s)** — arXiv + S2 + OpenAlex tools + selector wiring + deterministic affiliation pass + small-model affiliation classifier + `source-quality.md` amendment. Activated by including `'arxiv'`, `'s2'`, and `'openalex'` in `VerifyConfig.research_origins`. 5–7 days. Optionally split into "API integrations + selector" + "affiliation override + classifier + amendment".
6. **Path 3 commit(s)** — EDGAR tool + selector gating on `sec_cik` + small-model subject-relevance classifier + filer-vs-subject classification override + `source-quality.md` amendment. Activated by including `'edgar'` in `VerifyConfig.research_origins`. 5–7 days. Optionally split into "EDGAR fetch + subject classifier" + "classification override + amendment".

Paths 1–3 are parallel-able after step 2. Path 1 is small enough to ride alongside step 2 if convenient; `dr stats` (step 4) is independent of which paths ship.

## Rollout order

1. **Schema commit + Shared infrastructure** (steps 1–2 above) — ~3 days. Lands the prerequisites that everything else depends on.
2. After step 1, the following can all start independently — pick whichever order fits available time:
   - **Path 1 (Memento + telemetry, Wayback gap-fill)** — ~1.5–2 days. Cheapest add; on by default since Wayback is already live.
   - **`dr stats` (lightweight)** — ~0.5–1 day. Read-only; no flag.
   - **Path 2 (arXiv + S2 + OpenAlex + affiliation rules)** — 5–7 days. Activated via `VerifyConfig.research_origins`.
   - **Path 3 (SEC EDGAR + subject-relevance classifier + classification override)** — 5–7 days. Activated via `VerifyConfig.research_origins`.
   - **Companion plan**: [`source-pool-expansion-tier1-search-backend.md`](completed/source-pool-expansion-tier1-search-backend.md) — ~4 days. Behind `RESEARCH_SEARCH_BACKEND` (the companion plan owns its own gating).

None of these blocks depend on each other; only on step 1. Default activations happen after one operator-validated cycle on the audit-trail data (now readable via `dr stats`).

**Why one `research_origins` list instead of per-path booleans.** Three booleans (`ENABLE_ACADEMIC_RESEARCH`, `ENABLE_EDGAR_RESEARCH`, …) encode "is this path enabled" as global config; the long-term direction is a state-machine workspace where each claim's record lists which sources to attempt. A single `research_origins: list[str]` field (default `['tavily']` after the companion search-backend swap landed; grows as paths activate) ports cleanly to that future per-claim listing without an enum-to-list migration. The field name uses "origins" because the values are per-URL source categories (`'brave'`, `'tavily'`, `'arxiv'`, `'edgar'`, …) — the same vocabulary as the schema's `acquisition.origin` enum. Section-level "Path 1/2/3" remains the organizing concept for this plan.

**Total effort estimate**: 13.5–19 days for Tier 1 (Paths 1–3 + shared infra + `dr stats`), plus ~4 days for the companion search-backend plan. (Path 2 re-baselined from 4–6 to 5–7 days during concretization; see § Path 2 → Effort breakdown.)

## Per-path success criteria

| Path | Metric | Target |
|---|---|---|
| 1 (Wayback gap-fill) | `outcome: 'recovered'` rate on terminal fetch failures (combined archive.org + Memento) | ≥ 50% |
| 2 (Academic APIs) | Tagged-topic claim runs ingesting ≥1 academic source (origin in `{arxiv, s2, openalex}`) | ≥ 60% on `ai-safety` / `environmental-impact` / `industry-analysis` topics (matches Path 2 trigger set) |
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
| `pipeline/researcher/independence_classifier.py` (new, Path 2) and `pipeline/researcher/subject_relevance_classifier.py` (new, Path 3) | Small classifiers: `IndependenceCall` (mixed-authorship affiliation) and `SubjectRelevance` (EDGAR full-text disambiguation). Same Haiku-class agent shape as `planner.py`/`scorer.py`; lives at the `pipeline/researcher/` top level since `pipeline/researcher/agents/` does not exist today (creating that subdir is out of Tier 1 scope). |
| `pipeline/ingestor/tools/wayback.py` | Memento secondary fallback; per-URL acquisition writes; failure `StepError` emissions. |
| `pipeline/orchestrator/persistence.py` | `_write_audit_sidecar` threads `acquisition` entries through the existing `research_trace` dict; new `tool_outcomes` array for "tool fired, found nothing" runtime trace. |
| `pipeline/common/source_classification.py` | EDGAR filer-vs-subject CIK rule; preprint/journal publisher tags; affiliation-derived `independence` override (deterministic + classifier-driven). |
| `pipeline/common/publisher_quality.py` | Tag arXiv / OpenAlex / SEC publishers. |
| `pipeline/orchestrator/pipeline.py` | New `VerifyConfig.research_origins: list[str]` (default `['tavily']` since the companion search-backend swap; was originally `['brave']`); throttle plumbing. Path 2 adds `topics: list[str] = []` parameter to `verify_claim` / `_research`, threaded from existing `template.topics` at orchestrator call sites (`pipeline.py:1530`, `cli.py:889`). |
| `pipeline/orchestrator/cli.py` | New `dr stats` subcommand (read-only; `--format text\|json`) reading `research:` + per-URL `acquisition` aggregates from sidecars. Sits in the "Read-only" `_COMMAND_GROUPS` bucket. |
| `pipeline/orchestrator/stats.py` | Path 2 adds `academic_topic_coverage` aggregate (per-claim filter on tagged topics, count of claims with ≥1 academic-origin source) for the §Per-path success criteria measurement. Existing `acquisition_origins` already lists arxiv/s2/openalex (`stats.py:34-41`). |
| `pipeline/orchestrator/checkpoints.py` | Document the full `StepError.error_type` vocabulary in the docstring; no enum migration. |
| `docs/architecture/source-quality.md` | New § Independence override rules subsection; record the academic-affiliation rule (with Path 2) and EDGAR filer-vs-subject rule (with Path 3). |
| `docs/architecture/research-flow.md` | Update Researcher-internals diagram (§6) for parallel tool dispatch and the new selector function. |
| `docs/architecture/research-workflow.md` | Document `VerifyConfig.research_origins` under § Pipeline configuration knobs. |
| `AGENTS.md` § Tooling | New env vars (`SEMANTIC_SCHOLAR_API_KEY`, `OPENALEX_MAILTO`, `SEC_EDGAR_USER_AGENT`). Search-backend env vars are in the companion plan. |

## Open questions

(none currently open)

Resolved:
- ~~Memento error vocabulary~~ — `memento_unavailable` is reserved for aggregator transport failures (timeout / connection error / 5xx); "Memento returned no snapshot" is a silent miss (no `StepError`, no `acquisition` entry). `wayback_unavailable` covers the archive.org leg under the same rule. See Path 1 § Decisions.
- ~~Affiliation threshold for "majority external" papers~~ — handled by the `IndependenceCall` small-model classifier (see § Architecture amendment, Path 2); no static threshold needed.
- ~~`sec_cik` lookup for entities not yet seeded~~ — manual operator add, matching existing entity-onboard flow. Auto-resolution deferred to follow-up if backlog grows.
- ~~Negative-cache for academic / EDGAR misses~~ — Path 3 skips when `sec_cik` is unset (the gate is the cache); Path 2 skips when the claim's `topics` don't intersect `_ACADEMIC_TOPICS` (the selector is the gate). No separate cache layer is needed; both gates are deterministic and per-claim. (The earlier "lives in the existing run-cache layer" framing was inaccurate — the only cache in the pipeline today is the URL dedup index, which is unrelated.)

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
| 2026-05-08 | agent (opus-4-7) | Path 2 concretization | Path 2 rewritten to match Path 1's level of implementation-readiness. Decisions concretized: **(1)** **Topics plumbing** — surfaced the hard gap that `decomposed_research` does not currently receive criterion topics (`template.topics` exists at the orchestrator caller in `pipeline.py:1530` and `cli.py:889` but isn't threaded through `verify_claim`). Path 2 adds a `topics: list[str] = []` parameter through three signatures; `claim-probe` (no criterion) passes `[]` and Path 2 stays off. Selector function shape sketched as `_select_research_origins(cfg, topics)` in `decomposed.py`. **(2)** **Concrete endpoints** — arXiv Atom XML, S2 graph v1 with `x-api-key`, OpenAlex polite pool with `mailto=`. Throttle constants per API guidelines (1/3s, 1/s anon vs 10/s with key, 10/s polite). **(3)** **Throttle registration** — module-import `_ensure_throttle_registered()` per tool, mirroring `tavily.py:50-66`. **(4)** **Timeout** — reuse Tavily's per-call 15s `httpx` default; no new constant in `common/timeouts.py`. **(5)** **`IndependenceCall` classifier** — concrete Pydantic shape, lives at `pipeline/researcher/independence_classifier.py` (top-level, mirroring `planner.py`/`scorer.py` since `pipeline/researcher/agents/` does not exist today; flagged as a discrepancy with the File touches table line 298). Triggers only on deterministic-fallback OpenAlex with mixed authorship. Timeout/error behaviour mirrors planner. **(6)** **Affiliation override mechanics** — extends `acquisition` with an optional `affiliation_decision` sub-field at Researcher write time; new `IngestorDeps.acquisition_in` side-channel surfaces it at Ingest time; new `apply_affiliation_override` helper in `source_classification.py` lands the decision. Substring matching with same-parent subsidiary alias resolution. **(7)** **Audit-trail writes** — per-URL `acquisition` shape table (`stage`, `origin`, `query`, `paper_id`, `affiliation_decision`); per-tool no-results goes to `research_trace["tool_outcomes"]`. **(8)** **Test surface** — 14-row table covering per-API success/failure, selector logic, classifier branches, cross-stage override. **(9)** **`StepError`** — Path 2 emits no new vocabulary (uses existing `http_error`/`timeout`); smoke test does not need updating. **(10)** **Success metric** — flagged that current `dr stats` does **not** segment per-origin counts by claim topic; spec'd a new `academic_topic_coverage` aggregate in `stats.py` with `dr stats --format json | jq '.academic_topic_coverage.rate'` as the measurement command. **(11)** **Coordination** — host blocklist verified clean for arxiv.org/openalex.org/semanticscholar.org; publisher-quality tags land in same commit (arxiv already in `_SECONDARY_PUBLISHERS`; semanticscholar/openalex added). Land Path 2 amendment first if Path 3 ships same week (Path 3's amendment references the existing § Independence override rules subsection). **(12)** **Effort breakdown** — 5–7 days, broken down into 10 components each ~0.25–1 day. Re-baselined upward from 4–6 days because of the topic-plumbing prerequisite and cross-stage `IngestorDeps.acquisition_in` plumbing that the prior estimate didn't account for. Also reframed the resolved "negative-cache" open-question item: there is no run-cache layer in the pipeline today (the only cache is the URL dedup index); Path 2's selector is itself the gate. |
