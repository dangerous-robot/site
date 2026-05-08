# Source quality survey

**Type**: Survey (research report on what types of plans could be written)
**Created**: 2026-05-02
**Scope**: Whole pipeline, from query generation through analyst handoff

This survey maps the source quality problem across the full research pipeline. It identifies signals that are implemented, planned, or absent at each stage, and describes the types of plans that could be written to improve the likelihood that high-quality sources score higher than low-quality or unknown-quality sources. It is not an implementation plan. Prioritization and task breakdown belong in the plans that follow from this survey.

---

## Existing plans: scope notes

These plans already claim pieces of the source quality space. Any new plans should link to or explicitly update rather than duplicate them.

| Plan | Scope | What it does not own |
|------|-------|----------------------|
| [`researcher-host-blocklist.md`](../researcher-host-blocklist.md) | Post-search, pre-ingest domain filter; drops known paywall/403 hosts before the ingestor runs | Low-trust (non-paywall) domains; query quality; scoring |
| [`source-trust-metadata.md`](../source-trust-metadata.md) | Schema for per-source trust signals: site trust, document type, authority, COI/independence; phased backfill and agent classifier | Pre-ingest filtering; query generation; publisher group routing |
| [`research-quality-ideas.md`](../research-quality-ideas.md) | Ranked backlog: entity-context scoring, COI in analyst reasoning, freshness signal, source reuse, negative site signals, schema enrichment | Architecture; failed query detection; quality gates |
| [`wayback-archive-job.md`](../wayback-archive-job.md) | Background-job framework; `dr archive` as the first job; scheduled backfill of `archived_url` on existing sources | In-pipeline use of wayback data as a quality signal |
| [`pipeline-dedup-detection_stub.md`](pipeline-dedup-detection_stub.md) | URL canonicalization; match-and-reuse existing sources before ingest; claim identity dedup | Query-level deduplication (queries that surface overlapping URLs); query quality |
| [`pipeline-state-machine_stub.md`](pipeline-state-machine_stub.md) | Persisted claim workspace; resumable pipeline; feedback loops between agents | Specific quality signals or scoring logic |
| [`parent-company-inference.md`](../parent-company-inference.md) | Inferring `parent_company` slug during product onboarding | Using parent company in scorer or analyst reasoning (cross-referenced in `research-quality-ideas.md`) |
| [`multi-provider.md`](../multi-provider.md) | Per-agent model selection; Infomaniak/GreenPT integration; tool-free researcher variants | Source quality signals; scoring; quality gates |

---

## Scope breakdown

The improvements described in this survey fall into three tiers based on what the architecture needs to support them. Most improvements are in the first tier: the current linear pipeline is capable of them, and the primary work is prompt changes, data wiring, or adding detection logic inside existing stages. Only a narrow set of improvements require the state machine. A smaller set requires decisions or infrastructure changes that go beyond the state machine.

**State machine** here refers to the workspace-based persisted claim pipeline described in `pipeline-state-machine_stub.md`: a claim workspace that survives across agent steps, lets the orchestrator resume from a completed step, and enables feedback from a quality gate back to research. The threshold check (`below_threshold()`) already exists in the current pipeline; what the state machine adds is the path *back* from that gate with preserved knowledge of what was already tried.

### No architectural change required

- Pass `parent_company` into the planner and scorer prompts — §1 (query generation), §6 (scoring)
- Add `query_angles` hints to entities — §1 (query generation)
- Add entity-context vs. independent-coverage angle guidance to the planner — §1 (query generation)
- Extend the research trace with per-query quality signals (overlap rate, source type distribution, query quality flag) — §2 (failed query detection)
- Define and log a "failing query" threshold criterion in the trace — §2 (failed query detection)
- Add 403 recovery via Wayback as a fallback on `TerminalFetchError` — §3 (source fetching and Wayback)
- Extend the blocklist to cover low-trust source categories beyond paywall/403 hosts — §4 (publisher and site quality)
- Apply `source_classification.py` domain patterns as a pre-ingest filter or scorer hint — §4 (publisher and site quality)
- Inject community-forum domain patterns into the scorer prompt or blocklist — §4 (publisher and site quality)
- Add thin-content detection to the ingestor — §5 (page-level evaluation)
- Add soft-paywall detection to the ingestor — §5 (page-level evaluation)
- Instruct the ingestor to extract and record author/byline information — §5 (page-level evaluation)
- Draft `document_type` and `independence` at ingest time rather than post-hoc backfill — §5 (page-level evaluation)
- Revise the scorer prompt to accept per-candidate publisher quality hints — §6 (scoring)
- Add entity context (parent company slug, aliases) to the scorer prompt — §6 (scoring)
- Revise the scorer fallback: when the scorer drops all candidates, fail the query rather than silently keeping all candidates — §6 (scoring)
- Add analyst source weighting via `source_type` in the analyst prompt — §6 (scoring)
- Extend the blocked-reason taxonomy to include `low_quality_sources` — §7 (architectural direction)
- Add non-blocking quality warnings to the threshold check — §7 (architectural direction)
- A publisher groups registry — §4 (publisher and site quality)

### Requires state machine

- A failing query triggers a re-plan: the planner receives the original query, its quality signal, and instruction to try a different angle — §2 (failed query detection). This is cross-stage re-research: the gate fires post-scoring, and the pipeline must loop back to the researcher with memory of which queries were already tried and why they were replaced.
- Quality gate extensions to `threshold_check` that block on source quality (not just source count) and route back to research — §7 (architectural direction). The gate exists today; the routing-back-with-context does not.
- Persisted iteration state for any re-research cycle: which queries were tried, what the gate found, how many attempts have been made — §7 (architectural direction). Without this, a re-research loop has no budget cap and no way to avoid repeating failed queries.

### Requires larger refactor

- **Wayback-as-a-pre-flight-quality-signal** — §3 (source fetching and Wayback). Using `archived_url` availability as a scoring signal before analyst handoff requires synchronous wayback access, which conflicts with the background-job design in `wayback-archive-job.md` and adds latency regardless of the state machine. This requires resolving the timing decision as an explicit architectural choice first. The 403 recovery use case (fallback only on fetch failure) does not have this constraint and is in "no change required" above.
- **Within-stage iterative query refinement for tool-free researcher variants** — §1 (query generation), cross-referenced in `tool-free-researcher-ingestor_stub.md`. The tool-free researcher is intentionally single-shot; adding iterative refinement there requires a different agent decomposition.

### Notes on scope judgment calls

The **scorer fallback fix** was split across two tiers. Changing the fallback from "keep all candidates" to "fail the query and let the threshold check handle it" is a small code change in `decomposed.py` — no state machine needed. But "trigger a re-plan when the scorer drops everything" requires the state machine, because acting on that failure means routing back to the researcher with context. The survey's "types of plans" section in §6 describes both options; this breakdown separates them.

The **publisher groups registry** is in "no change required" because the registry itself is a YAML data file and the plan that owns it (`source-trust-metadata.md` Phase 7) does not depend on the state machine. Using the registry to detect same-group sources in the analyst prompt is also a prompt change. If a future plan wanted to use publisher group membership to gate which sources are allowed past the threshold check, that gate would require the state machine, but that plan doesn't exist yet.

The **failing query re-plan** was placed in "requires state machine" rather than "can be done with a recursive call in the current architecture." A bounded inner loop inside `_research()` that regenerates a single failing query is technically possible in the current architecture — the classic researcher already retries when results come back thin. But that variant is query-local and stateless with respect to other queries. The re-plan described in §2 needs to know the quality signals from the full multi-query set, communicate a reason back to the planner, and avoid repeating the same failed angle. That context-passing requirement is what the state machine stub is designed to carry.

The **wayback timing decision** remains outside both the "no change required" and "state machine" tiers because it is an architectural prerequisite, not an implementation task. The state machine does not resolve the timing conflict; it tracks state across pipeline steps, but `archived_url` availability depends on when archive.org has data, which the pipeline cannot control.

---

## Pipeline stages and quality touchpoints

The pipeline runs: **query generation → search execution → URL scoring → blocklist filter → ingest → [threshold check] → analyst → evaluator**. Source quality problems can enter at any stage and compound downstream.

---

## 1. Query generation

### Current state

Two paths exist for query generation:

- **Decomposed researcher** (current default): a query planner agent (Haiku-class) generates 2 to N queries from claim text and entity context. The planner prompt instructs it to vary the angle and prefer primary sources.
- **Classic researcher** (legacy): the researcher agent runs web_search tools directly, generates 2-3 queries, and retries with improved queries if fewer than 6 URLs come back.

The planner receives entity name, entity description, aliases, and `search_hints.include` / `search_hints.exclude` from the resolved entity. Parent company is present on the `ResolvedEntity` dataclass but is not currently passed into the planner prompt or scorer prompt.

### Signals available today

- Entity name, description, aliases, search hints (from entity frontmatter)
- Claim text
- `parent_company` field on `ResolvedEntity` (populated but not used in prompts)

### Gaps

**Parent company not in prompts.** If a claim is about Claude, "Anthropic" never appears in the queries unless the entity description mentions it. For subsidiary products and holding-company claims, queries without the parent name miss a large body of relevant coverage. This is the gap noted in `research-quality-ideas.md` "Scoring with entity context" — the fix applies equally to the planner.

**Query diversity is instruction-driven only.** The planner is told to vary the angle, but there is no structural check that queries actually target meaningfully different result sets. Two queries that differ in wording but return mostly the same URLs consume search budget without adding coverage.

**No explicit instruction to avoid known-low-quality source types at query time.** The classic researcher instruction says "avoid social media posts or forums" and "avoid pure marketing pages." The decomposed planner prompt has no equivalent guidance. Queries that would primarily surface PR wire services, corporate blogs, or community forum discussions are indistinguishable from higher-quality queries until after the search executes.

**Sector/abstract entity edge case.** The planner prompt includes a note that sector-level entities should skip the entity name and query by subject matter. This is good advice but is a prose instruction with no enforcement mechanism. It could be handled more reliably upstream (routing logic or entity-type-aware planner prompt variants).

### Types of plans that could be written

- Pass `parent_company` (and optionally, known aliases of the parent) into the planner prompt and scorer prompt. Low implementation cost; pairs with the "Scoring with entity context" item in `research-quality-ideas.md`.
- Add per-entity or per-template `query_angles` hints — structured guidance about which source types or organizations are authoritative for this specific claim topic. Different from `search_hints.include` (which targets result filtering) in that these would guide the *shape* of queries rather than the *content* of results.
- Instruct the planner to distinguish "entity-facing" from "independent coverage" angles explicitly, so queries that might surface only self-reported data are balanced against queries that surface third-party coverage.

---

## 2. Failed query detection

### Current state

There is no mechanism today to detect a query that is producing low-value results. The pipeline executes all queries the planner generates, fans out via Brave search, and passes every candidate to the URL scorer. A query that returns 10 URLs from PR wire services, the entity's own blog, and community forums looks identical in the pipeline to a query that returns 10 URLs from independent journalism and regulatory filings.

The decomposed researcher logs `candidates_seen`, `urls_kept`, and `urls_dropped` in the research trace, which provides raw counts. This data reaches the audit sidecar. It does not feed back into the research step.

### Signals that could indicate a failing query

Three signals are available post-search but pre-ingest:

1. **URL overlap rate.** If query B returns 80% of the same URLs as query A, it is not meaningfully widening coverage. High overlap is detectable at the candidate-deduplication step in `decomposed.py`, which already deduplicates by URL. The overlap rate per-query-pair could be computed from the `from_query` field on each `SearchCandidate`.

2. **Source type rate.** `classify_source_type()` in `pipeline/common/source_classification.py` maps publisher substring to primary/secondary/tertiary. This runs today only after ingest (post-hoc). If it ran at the candidate stage (using snippet or URL domain as a publisher proxy), a query where 80% of candidates classify as tertiary would be a candidate for replacement or augmentation.

3. **Low-quality domain signals.** The blocklist (`research/blocklist.yaml`) identifies domains to drop entirely. A softer version — domains that are low-trust but not blocked — could be used to flag queries that predominantly surface those domains.

### Structural challenge

Feeding failed query detection back into the pipeline requires either (a) a re-plan step after search execution (generate new/different queries when quality signals are poor), or (b) downgrading the signal from "gate the query" to "flag the query in the trace for operator review." Option (a) requires the state machine or a recursive research step. Option (b) is achievable within the current architecture by extending the research trace.

A quality gate that triggers re-planning is the intended long-run direction (see Architectural Direction section). Before that lands, logging the query quality signals in the trace gives operators visibility without changing pipeline behavior.

### Types of plans that could be written

- Extend the research trace with per-query quality signals: URL overlap rate (vs. other queries in the plan), estimated source type distribution based on URL domain heuristics, and an overall "query quality" flag. No behavioral change; operators can see this in the audit sidecar.
- Define a threshold (e.g., a query where 70%+ of candidates are already seen from other queries, or 60%+ are classified as tertiary by domain) as a "failing query" criterion, and log a warning in the trace when a query crosses it.
- A future plan (requires state machine or feedback-loop infrastructure) where a failing query triggers a re-plan: the planner receives the original query, its quality signal, and instruction to try a different angle.

---

## 3. Source fetching and Wayback integration

### Current state

**In-pipeline**: `skip_wayback` is currently defaulted to `False` (the interim flip per `wayback-archive-job.md`). This means the ingestor calls `check_wayback` and optionally `save_to_wayback` during source ingestion. The plan notes this adds ~45s of HTTP budget per source.

**Background job**: `wayback-archive-job.md` defines `dr archive` — a scheduled job that would backfill `archived_url` out-of-band and allow the in-pipeline default to return to `skip_wayback=True`.

### The timing conflict

The two approaches conflict for any plan that wants to use archived URL availability as an early-pipeline quality signal:

- If wayback runs in-pipeline, the archived URL is available at ingest time but slows the pipeline.
- If wayback runs as a background job, the archived URL arrives later — possibly days after initial ingestion — and is not available when the claim is first verified.
- Using `archived_url` as a quality signal (e.g., "prefer sources that have been archived, because unarchivable URLs are fragile") requires the URL to be archived before scoring. The background job model makes this impossible for new sources.

A 403-recovery use case (when a live fetch fails, try the Wayback archive) is a different problem: it requires synchronous wayback access only when the live fetch fails, not for all sources. This is more tractable in-pipeline because it only triggers on failures.

### Signals available from Wayback

- **Presence of an archived snapshot**: indicates the page has been indexed and is considered archival-worthy by archive.org.
- **Snapshot recency**: a recent snapshot suggests the page was live and publicly accessible recently.
- **Snapshot age gap**: if the most recent snapshot is significantly older than the `published_date`, the live page may have changed.

These signals are secondary quality indicators. A page that was never archived is not necessarily low quality; it may simply be new or on a domain that archive.org doesn't crawl frequently.

### Types of plans that could be written

- A plan specifically for **403 recovery via Wayback** as a fallback: when `TerminalFetchError` is raised, attempt a Wayback lookup before marking the source as failed. This is narrower than the general wayback integration and does not require resolving the background-job timing conflict.
- If the background job ships and the in-pipeline default returns to `skip_wayback=True`, a plan for **Wayback-as-a-pre-flight-signal**: before the background job runs its backfill, new sources could have a lightweight check (does this URL have any archived snapshot?) rather than a full `save_to_wayback` call.
- Documenting the resolution of the timing conflict as an explicit decision: does the pipeline ever use `archived_url` as a quality signal before the background job has run, or is `archived_url` exclusively a reader-facing and resilience signal?

---

## 4. Publisher and site quality evaluation

### Current state

Three mechanisms exist today:

1. **Blocklist** (`research/blocklist.yaml`, `pipeline/common/blocklist.py`): drops domains with known 403/paywall behavior. Runs post-search, pre-ingest, before `max_sources` slicing. Currently covers 7 hosts.

2. **`source_classification.py`**: classifies sources as primary, secondary, or tertiary based on publisher substring matching and `kind`. Runs post-ingest (at write time). The domain patterns it contains are the closest thing to publisher quality intelligence in the pipeline today, but they run too late to influence which URLs get ingested.

3. **URL scorer** (`researcher/scorer.py`): scores candidates on relevance (1-5 scale) using title and snippet. The scorer instructions do not reference publisher quality; a relevant-looking snippet from a content farm scores identically to one from an academic institution.

### Gap: publisher quality is invisible before ingest

The blocklist stops the worst offenders (paywalls, 403 walls). The source classifier provides post-hoc quality labeling. But there is no mechanism to prefer high-quality publishers over low-quality publishers during URL scoring — before any ingest tokens are spent.

From `research-quality-ideas.md`:

> `common/source_classification.py` already classifies sources as primary/secondary/tertiary from domain/publisher patterns, but this runs post-hoc (after ingestion). Its domain patterns could be used earlier: either as a pre-scorer filter (drop `tertiary` candidates before scoring) or as a signal injected into the scorer prompt so it can discount low-credibility domains before spending an ingest slot on them.

### Community forums as a specific blind spot

The scorer prompt has no awareness of domain type. A Reddit thread or Quora answer with an on-topic title scores ≥4 for relevance. Community forum signals (upvotes, author standing, thread age, response quality) are invisible in the title/snippet. The source classifier does not have forum-domain patterns, so forum posts typically classify as secondary (the fallback default).

### Signals available for publisher evaluation

- **URL domain**: extractable before ingest; can be matched against the blocklist, a classification table, or an expanded low-trust list.
- **Publisher substring from snippet/metadata**: the Brave search API returns some publisher/source metadata; this may be partially useful before a full page fetch.
- **`source_type` from post-hoc classification**: available only after ingest, but the classification rules could be applied earlier against domain strings.
- **`trust.site_trust`** (from `source-trust-metadata.md`): a planned schema field on source files. Not yet populated; would require backfill or agent-classifier work.

### Types of plans that could be written

- Extend the blocklist to cover low-trust source categories (PR wire services, content farms, vendor-sponsored analysis hubs) in addition to paywall/403 hosts. The existing blocklist structure supports this; it would need new entries and a revised matching rationale.
- Apply `source_classification.py` domain patterns as a pre-ingest filter or scorer hint. A plan would define what "pre-scorer tertiary filter" means operationally: drop all tertiary-classified candidates before scoring, or inject a quality label into the scorer prompt for each candidate URL.
- Inject community-forum domain patterns into the scorer prompt or blocklist. Forum domains (reddit.com, quora.com, news.ycombinator.com, etc.) could receive a scorer penalty or a soft blocklist treatment that allows them through only when no better alternatives exist.
- A publisher groups registry (`research/publisher-groups.yaml`) per `source-trust-metadata.md` Phase 7 — domains mapped to publisher group names so the scorer and analyst can detect same-group sources presented as independent corroboration.

---

## 5. Page-level quality evaluation

### Current state

The ingestor is the only pipeline stage that reads actual page content. Its instructions ask it to extract: title, publisher, published date (optional), `kind`, summary (≤30 words), and key quotes (0-5 direct quotes). The ingestor does not produce quality signals.

After ingest, `source_classification.py` classifies sources using only publisher name and kind — not page content, author, or page metadata.

### Signals the ingestor could extract but currently does not

- **Author/byline**: institutional journalism and academic papers typically have named authors. Absence of a byline is a weak negative signal; a recognizable institutional author is a positive signal.
- **Page type indicators**: is this a product landing page, a press release, a news article, an op-ed, a technical report? Distinct from `kind` (which is a content type taxonomy) — this is closer to the editorial independence dimension.
- **Publication date recency**: the ingestor can extract `published_date` when present. Whether a source is within the claim's `recheck_cadence_days` window is an unused signal.
- **Content density**: a page with 200 words of prose around a 10-word factual claim is lower-quality evidence than a full report. Currently not extracted.
- **Paywall / thin content / login wall signals**: pages that fetch but return near-empty bodies (e.g., "subscribe to read more" content) currently pass through the ingestor. The ingestor instructions say to abort on 401/402/403/451 HTTP codes, but soft paywalls (200 status, minimal content) are not detected.

### Relationship to `source-trust-metadata.md`

The `trust:` block planned in `source-trust-metadata.md` covers `site_trust`, `document_type`, `authority`, and `independence`. Phase 6 of that plan adds an agent classifier that drafts these fields during ingest. That plan is the primary home for page-level trust classification. This survey notes it as the vehicle for page-level quality signals, with the following gaps:

- **`document_type`** will distinguish marketing from news from regulatory filing, but the enum is declaration-level (`sustainability-report`, `blog`, `research`, `news`) — it does not capture content density or author credibility within a document type.
- **Thin content / soft paywalls** are not covered by the trust schema. They are a separate detection problem.

### Types of plans that could be written

- Add thin-content detection to the ingestor: if the extracted body is below a word-count threshold after stripping boilerplate, flag the source with a `thin_content: true` field and log a warning. This is distinct from the terminal-fetch-error handling and does not require a trust schema change.
- Add soft-paywall detection: pages that include common "subscribe to continue" patterns (detectable in the extracted body text) could be flagged similarly.
- Instruct the ingestor to extract and record author/byline information as an optional field on `SourceFrontmatter`. This would pair with the `authority` axis in `source-trust-metadata.md`.
- As part of `source-trust-metadata.md` Phase 6, the ingestor agent could draft `document_type` and `independence` classifications at ingest time rather than as a post-hoc backfill, making those signals available to the analyst on the first run.

---

## 6. Scoring and ranking

### Current state

The URL scorer (`researcher/scorer.py`) scores candidates on a 1-5 relevance scale using title and snippet. URLs scoring ≥4 are kept; those <4 are dropped. If the scorer drops all candidates, the pipeline falls back to keeping all candidates (a safety net in `decomposed.py`).

The scorer prompt currently passes: entity name, claim text, and the candidate list (URL, title, snippet, source query). It does not pass: entity type, parent company, known aliases, publisher quality signals, or domain type classifications.

After ingest, `source_classification.py` classifies sources into primary/secondary/tertiary. This classification is stored on the source file and is the only quality-adjacent field that survives to the analyst.

The analyst receives all ingested sources equally. There is no mechanism to weight sources by quality; the analyst instructions do not reference `source_type`, `kind`, or any trust signal. (Note: `source-trust-metadata.md` Phase 2 will add COI/independence weighting to analyst instructions once those fields are populated.)

### How the scoring stack fits together

The current architecture has three separate scoring/filtering steps with no coordination between them:

1. **URL scorer** (pre-ingest, relevance only): keeps URLs with score ≥4
2. **Blocklist** (pre-ingest, domain reputation only): drops blocked hosts
3. **Source classifier** (post-ingest, source type only): labels primary/secondary/tertiary

These three steps run independently. A URL can pass the scorer (high relevance title/snippet), survive the blocklist (domain not blocked), be ingested, and then be classified as tertiary — meaning the ingest cost was spent on a source that any pre-ingest classification would have flagged as low quality.

### What "quality sources scoring higher" requires

For high-quality sources to consistently score higher than low/unknown-quality sources, the scoring stack needs to incorporate quality signals alongside relevance signals. The minimum changes:

- Publisher quality signal injected into the scorer prompt (so a tertiary-domain candidate can be scored down even if topically relevant)
- Entity context (parent company, aliases) injected into the scorer prompt (so a source about the parent company is correctly recognized as relevant)
- Scorer fallback behavior revised: falling back to all candidates when the scorer drops everything means the quality filter is silently bypassed for the weakest queries

### Types of plans that could be written

- Revise the scorer prompt to accept per-candidate publisher quality hints. The classification logic from `source_classification.py` (or a simpler domain lookup) generates the hint; the scorer uses it to break ties and penalize known-low-quality domains.
- Add entity context (parent company slug, aliases) to the scorer prompt. This is the "Scoring with entity context" item from `research-quality-ideas.md`, which currently notes Phase 8 of `source-trust-metadata.md` as the dependency. The dependency is on entity enrichment (entity having a usable `parent_company` field), not on the trust schema itself.
- Revise the scorer fallback: instead of keeping all candidates when the scorer drops everything, flag the query as failing and either (a) log it in the trace or (b) trigger a re-plan if the state machine supports it.
- A plan for analyst source weighting: pass `source_type` (primary/secondary/tertiary) into the analyst prompt so the analyst can explicitly note when its verdict relies primarily on secondary or tertiary sources. This is a bridge between the existing classification and the full trust metadata planned in `source-trust-metadata.md`.

---

## 7. Architectural direction

### Quality gates as blocking steps

The current pipeline is a linear chain: research → ingest → threshold check → analyst → evaluator. The threshold check (currently: <4 usable sources → blocked[^1]) is the only quality gate, and it acts on ingest count, not source quality.

The intended direction — stated in the task context and reinforced by the state machine stub — is quality gates as blocking steps: before passing sources to the analyst, the pipeline verifies that the source pool meets a minimum quality bar. If it does not, the pipeline recursively improves (re-queries, adds more queries, discards and replaces low-quality sources) rather than passing inferior evidence to the analyst and letting the analyst work around it.

This is a meaningful architectural shift. Today, quality problems are absorbed downstream (analyst note: "limited sources available") or are simply not surfaced. A quality-gate model surfaces them early and prevents the analyst from writing verdicts against structurally weak evidence.

### What quality gates require that does not exist yet

For quality gates to work as blocking steps, the pipeline needs:

1. **Measurable quality signals before the analyst runs.** Today's post-ingest signals (source_type, kind) are available but not evaluated as a gate. Pre-ingest signals (publisher domain classification) exist in code but run too late.

2. **A feedback loop from the gate back to research.** When the quality gate fires (not enough high-quality sources), the pipeline needs to re-research with different or additional queries. Today there is no re-research path once the ingestor has run.

3. **A way to persist state across the re-research cycle.** The state machine stub addresses this: the workspace document would hold the quality gate result and the re-research instructions so the pipeline can resume without rerunning completed steps.

### State machine implications

The state machine stub (`pipeline-state-machine_stub.md`) adds a `[threshold_check]` state to the pipeline state graph:

```
queued → researching → ingesting → [threshold_check] → analysing → auditing → done
                                        ↓
                                     blocked
```

Quality gates fit naturally as conditions on the `threshold_check → analysing` transition. The check currently evaluates source count. It could be extended to evaluate source quality: a run that has 4 sources but 3 of them are tertiary could be treated as below threshold just as a run with 2 sources is today.

Before the state machine lands, smaller moves are available:

- Log quality signals in the research trace so operators can see them (no behavioral change)
- Add an optional warning to the threshold check when the source pool is predominantly low-quality (display only, does not block)
- Extend the blocked-reason taxonomy to include `low_quality_sources` alongside `insufficient_sources` and `terminal_fetch_error`

### The real-time vs. blocking tradeoff

Real-time pass-through (always run the analyst, let it work with what it has) is the current behavior. It is fast and never blocks. It also means the analyst absorbs every research quality failure silently, and the operator cannot distinguish a strong verdict backed by independent reporting from a weak verdict backed by the entity's own press releases.

The blocking direction trades speed for defensibility. A claim that blocks due to `low_quality_sources` is more informative than a claim that slips through with a `medium` confidence verdict backed by three tertiary sources. It also forces research improvement to happen before publication rather than after operator review.

The pragmatic path: start with logging (no blocking), then add non-blocking warnings in the threshold check, then use the state machine to enable blocking with re-research. Each step improves operator visibility without requiring the full architecture.

This three-step sequence is architecturally sound. The state machine stub correctly characterizes what the first two steps need: nothing beyond the current linear pipeline. It also correctly characterizes what the third step needs: persisted workspace state and a routing path from `threshold_check` back to `researching`. Where the stub remains a stub is on the operational specifics of the re-research cycle itself — how many attempts are allowed before the claim is considered permanently blocked, how the gate's fired reason is converted into a re-plan instruction for the planner, and how the workspace tracks which queries were already tried so the planner doesn't repeat them. These are not architectural unknowns, but they must be resolved before a blocking re-research gate can be implemented. The "recursion" concept (re-research when quality gate fires) does not require anything beyond what the stub describes in principle; it requires the stub's open questions to be answered in practice.

### The wayback timing decision as an architectural constraint

The wayback timing conflict (in-pipeline vs. background job) is an unresolved constraint on plans that want to use `archived_url` as a quality signal. It should be resolved as an explicit decision before any plan takes a dependency on it. The two options:

- **Archive availability as a quality signal** requires synchronous wayback access at ingest time, which conflicts with the background-job design and adds latency.
- **Archive availability as a resilience and reader-trust signal only** requires no pipeline timing change — the background job handles backfill, and the signal never enters pipeline scoring.

The 403-recovery use case (synchronous wayback lookup on terminal fetch error) is independent of this decision and can be planned without resolving it.

The state machine does not resolve the timing conflict. The workspace tracks pipeline state; it does not change when archive.org has a snapshot of a given URL. This decision needs to be made independently of the state machine plan, and it blocks any plan that wants to use `archived_url` as a quality gate input.

---

## Summary of signal inventory

| Signal | Where available | Currently used for | Pre-ingest availability |
|--------|----------------|---------------------|-------------------------|
| Entity name, description, aliases | Query planner prompt | Query generation | Yes — already in planner (parent company gap) |
| Parent company | `ResolvedEntity` (not passed to prompts) | Not used | Yes — on dataclass, not injected |
| Search hints (include/exclude) | Query planner prompt | Query steering | Yes — in use |
| URL overlap rate across queries | Candidate dedup (computed but not stored) | Not used | Yes — computable from `from_query` field |
| Domain-based tertiary classification | `source_classification.py` (post-ingest) | Source file label | No — runs post-ingest; patterns could move earlier |
| Blocklist domain match | Pre-ingest filter | Hard drop | Yes — in use |
| Scorer relevance (1-5) | Pre-ingest scoring | URL keep/drop | Yes — in use, relevance only |
| `source_type` (primary/secondary/tertiary) | Post-ingest source file | Display only | No — post-ingest label only |
| `trust:` block (site_trust, document_type, authority, independence, COI) | Planned (source-trust-metadata.md) | Not yet in use | No — agent classifier planned for ingest time |
| `published_date` recency | Post-ingest source file | Not yet in analyst prompt | No — post-ingest extraction |
| Thin content / soft paywall | Not extracted | Not applicable | Partial — soft paywalls may be detectable at ingest |
| `archived_url` presence | Post-ingest (background job backfill) | Reader-facing link | No — timing conflict unresolved |

[^1]: The correct threshold is `< 4` — confirmed by the live code (`below_threshold()` in `pipeline/pipeline.py`). Earlier planning docs referenced `≥ 2`; those have been updated.

---

## Review history

| Date | Reviewer | Scope |
|------|----------|-------|
| 2026-05-02 | agent (claude-sonnet-4-6) | Initial draft |
| 2026-05-02 | agent (claude-sonnet-4-6) | Architectural critique: added Scope breakdown section; annotated §7 Architectural Direction with state machine recursion budget caveat and explicit wayback/state-machine independence note |
