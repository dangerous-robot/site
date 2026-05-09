# Source quality follow-ups

> Companion to [`source-pool-expansion-tier1.md`](source-pool-expansion-tier1.md). Collects ideas, drafted follow-ups, and full plans deferred until Tier 1 ships. Anything here that crystallizes into active work gets promoted to its own plan file.

**Status**: Backlog (active collector — entries are added, promoted, or dropped over time)
**Created**: 2026-05-08

## How this file works

This is the single landing page for "what's pending in source quality after Tier 1?" Three categories live here:

1. **Idea backlog** (Section 1): ranked future improvements that aren't yet plan-shaped.
2. **Drafted follow-ups** (Section 2): outlined plans that are post-Tier-1 by design — Tier 2/3 expansion, PDF publish surface, scheduled audits.
3. **v1.x trust schema** (Section 3): the full-trust-block schema deferred from the v1 source-quality work; digest only, full text retained in `completed/source-trust-metadata_superseded.md`.

Section 4 is a reference index to historical / superseded material now in `completed/`.

## Promotion criteria

Move an entry out of this file when **all** of these are true:

1. The scope is named, not "fix source quality more."
2. There is a designated implementation surface (file paths, agent prompt, schema field).
3. The dependencies (Tier 1, schema work, decisions) are resolved or scheduled.
4. Effort is estimated to within an order of magnitude.
5. The entry has at least one operator-facing test or acceptance criterion.

Promotion = create `docs/plans/<name>.md` with the entry's content fleshed out, add a Review history row, and delete the corresponding section from this file (leaving a one-line stub: `Promoted to [name].md`).

---

## Section 1 — Idea backlog (raw)

Ideas for improving the pipeline's research output quality. Organized by concern: content quality (what evidence the pipeline finds and how it weights it) and schema quality (what structured data the pipeline can represent and reason over). Ranked within each section by expected research impact, with pragmatic notes on cost and dependency.

### Content quality

#### Source independence signals in analyst reasoning

Sources from the subject entity (the company or product being evaluated) carry an inherent conflict of interest. Today the analyst receives all sources equally. The analyst instructions could be updated to treat first-party sources as lower-weight evidence, especially for verdict-sensitive claims.

**Research impact**: High. Credibility of verdicts depends heavily on whether the analyst can distinguish independent evidence from self-reported claims.
**Cost**: Low for instruction update; medium if COI classification is added to source schema.
**Cross-reference**: Section 3 (v1.x trust schema) tracks schema-side COI metadata; this idea is the analyst-instruction counterpart.

#### Scoring with entity context

The URL scorer today receives only the claim text and candidate URL metadata. It has no knowledge of the entity being evaluated — its parent company, industry, or common aliases. A source that mentions "Google" but not "Gemini" may still be highly relevant if the claim is about Google's subsidiary products.

**Ideas**:
- Pass entity name + parent company to the scorer prompt.
- Pass known entity aliases or industry terms from the entity's schema fields.

**Research impact**: High. Improves precision of early-stage source retrieval, especially for subsidiary products and holding-company claims.
**Cost**: Low (prompt-level change in `pipeline/researcher/scorer.py`); requires entity metadata (see Schema quality below).

#### Source freshness as a quality signal

The analyst has no structured signal about how recent a source is. For fast-changing claims (regulatory filings, energy metrics, corporate structure), a 2022 source may be actively misleading even if it was accurate at the time.

**Ideas**:
- Add optional `published_date` to `SourceFrontmatter`; ingest agent attempts to extract it from page metadata.
- The analyst instruction could reference source dates when building the verdict narrative.
- Claims with `recheck_cadence_days` set low could deprioritize sources older than the cadence.

**Research impact**: Medium. Matters most for claims about current practices or live data; less important for historical facts.
**Cost**: Medium (schema change + ingest agent change + instruction update).

#### Source reuse before fetching

The researcher generates candidate URLs from web search. If a URL already exists in `research/sources/`, the pipeline re-ingests it anyway. Reusing the existing source file would improve coherence (same summary text across claims) and cut ingest cost.

**Ideas**:
- Before ingesting a candidate URL, check if it matches an existing source by URL (after canonicalization).
- If matched, skip ingest and pass the existing source file to the analyst.

**Research impact**: Medium. Primarily coherence and cost; also prevents divergent summaries of the same source across claims.
**Cost**: Low for URL match; depends on dedup canonicalization work already tracked in `docs/UNSCHEDULED.md` (Dedup detection) and partly delivered by `source-pool-expansion-tier1.md` § Shared infrastructure (prerequisite for Paths 1–3) (URL canonicalizer).

#### Negative site signals in search results

Some publishers are structurally weak for research: content farms, vendor-sponsored analysis, PR wire services, and community discussion forums. Today these pass the scorer unless the title/snippet is obviously irrelevant.

**Ideas**:
- Extend the researcher host blocklist (see [`researcher-host-blocklist.md`](researcher-host-blocklist.md)) to cover not just paywalled sites but low-trust source categories.
- The scorer prompt could note known-problematic source patterns (press release wires, vendor white papers presented as independent research, community forum posts).
- Community forums (Reddit, Quora, HN) are a specific failure case: a topically on-point thread title scores ≥4 for relevance even when the post is from a deleted user with 21 upvotes. The social-quality signals (author standing, vote count, thread age) are invisible to the scorer.
- `pipeline/common/source_classification.py` already classifies sources as primary/secondary/tertiary from domain/publisher patterns, but this runs post-hoc (after ingestion). Its domain patterns could be used earlier: either as a pre-scorer filter (drop `tertiary` candidates before scoring) or as a signal injected into the scorer prompt so it can discount low-credibility domains before spending an ingest slot on them.

**Research impact**: Medium. Reduces noise in the source pool; most valuable for claims that attract a lot of PR coverage.
**Cost**: Low for blocklist extension; medium for scorer-prompt adjustments or pre-scorer tertiary filter.

### Schema quality / capability

#### Product → company relationship

Products (`research/entities/products/`) have a `parent_company` field but it is schema-only and not used in pipeline reasoning or site rendering. Formalizing this relationship would enable:
- Passing parent company context to the scorer and analyst.
- Cross-referencing company-level sources when evaluating a product claim.
- Site rendering: "Made by Anthropic" on a Claude claim page.

**Research impact**: High (enables entity-context scoring above).
**Cost**: Medium (schema change + pipeline reads + site rendering).
**Cross-reference**: `docs/UNSCHEDULED.md` → "parent_company not rendered" (site gap).

#### Company metadata enrichment

Company entities today carry minimal structured data. Adding structured fields would support richer conflict-of-interest detection and entity-context scoring.

**Candidate fields**:
- `legal_name` (distinguish "OpenAI" from "OpenAI, LLC" vs "OpenAI Global, LLC")
- `official_website` (used as a signal for primary-source classification)
- `parent_company` (holding companies, acquisition history)
- `subsidiaries` (cross-link to related entities)
- `sec_cik` — landing first, via [`source-pool-expansion-tier1.md`](source-pool-expansion-tier1.md) § Schema prerequisites (used by § Path 3)

**Research impact**: Medium. Most valuable when combined with COI detection and entity-context scoring.
**Cost**: Low for schema addition; medium for backfill and any agent-side use.

#### White label domain classification by sector

Several sectors (financial analysis, technology press, energy reporting) have dominant white-label or syndication networks that appear independent but share ownership. Classifying domains by sector affiliation would let the analyst and scorer recognize when three "different" sources are actually the same publisher.

**Ideas**:
- Maintain a `research/publisher-groups.yaml` mapping domains to publisher groups.
- The ingest agent checks the source URL against this map and populates a `publisher_group` field on the source.
- The analyst instruction could warn against treating same-group sources as independent corroboration.

**Research impact**: Medium. Especially relevant for energy claims, where a few publishers dominate syndicated content.
**Cost**: High (manual curation of publisher map; ongoing maintenance).
**Cross-reference**: Section 3 below — Phase 7 of the v1.x trust schema is the implementation vehicle.

#### Entity onboarding research (verification gate + enrichment)

Promoted to drafted-plan stub: [`drafts/entity-onboarding-research_stub.md`](drafts/entity-onboarding-research_stub.md) (2026-05-09). Single onboarding-research agent across `company` / `product` / `subject` entities — same workflow, per-type prompt section. Verifier halts on typo / collision / sparse-evidence cases (`goooogle`, `greenpt`, `treadlightlyai` examples). Enricher populates structured + narrative fields on verified entities. Schema seat (`verification_status`) lands separately in [`entity-metadata-surface.md`](entity-metadata-surface.md). See stub for the full design space.

#### Subject entity type support

**Status: implemented.** `SUBJECT = "subject"` is in `EntityType` (`pipeline/common/models.py`) and `dr onboard --type subject` is supported. Included here as a capability marker: the schema can represent subject-level entities, but subject-specific research strategies (e.g., identifying industry-level sources vs. company sources) are still maturing.

**Schema extension opportunity**: Subjects could carry additional metadata that improves claim context — dominant publishers in the area, regulatory bodies, common conflict-of-interest patterns.

### Notes from prior doc

**3.2 (Apply `source_type` in standalone `dr ingest`)** was a code gap: `dr ingest` wrote source files without a `source_type` field because `classify_source_type()` was only wired into the full pipeline flow. Resolved — `dr ingest` was deprecated in favor of `dr step-ingest`, which calls `classify_source_type` before writing. No action needed.

---

## Section 2 — Drafted follow-ups

Outlined plans that are post-Tier-1 by design. Each subsection has enough scope to crystallize into its own plan file once dependencies are met.

### Source pool — Tier 2 (drafted)

**Depends on**: [`source-pool-expansion-tier1.md`](source-pool-expansion-tier1.md) and its companion [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md).

Tier 2 builds on the foundations laid by Tier 1: once new acquisition paths exist, these items improve their hit rate, surface area, or fallback options. None are blockers for v1.

#### Semantic Scholar + OpenAlex + affiliation override (deferred from Tier 1 Path 2)

Tier 1 ships arXiv-only as the academic API (see [`source-pool-expansion-tier1.md`](source-pool-expansion-tier1.md) § Path 2 → Why arXiv-only). Tier 2 reintroduces the broader scope that the original Path 2 design carried:

- **Semantic Scholar tool** — `pipeline/researcher/tools/semantic_scholar.py`. Graph v1 endpoint with optional `SEMANTIC_SCHOLAR_API_KEY` (1/s anon, 10/s with key). Activates the `s2` value of the `acquisition.origin` enum (already shipped as a reserved value in Tier 1's schema commit; no schema change needed).
- **OpenAlex tool** — `pipeline/researcher/tools/openalex.py`. Polite-pool endpoint with optional `OPENALEX_MAILTO` (1/s anon, 10/s polite). Returns structured `institutions[]` per author, which feeds the affiliation override below. Activates the `openalex` enum value (already shipped, reserved).
- **Affiliation override (cross-stage)** — new optional Zod sub-field `acquisition.affiliation_decision: { label, rationale, source }` on `auditSchema.sources_consulted[]`; new `IngestorDeps.acquisition_in: dict[str, dict]` side-channel (sibling to `prefetched_bodies` and `acquisition_writes`) so the OpenAlex-time decision reaches the Ingestor; new `apply_affiliation_override(base_independence, override_label) -> str` helper in `pipeline/common/source_classification.py`.
- **`IndependenceCall` classifier** — `pipeline/researcher/independence_classifier.py` (Haiku-class agent, same shape as `planner.py` / `scorer.py`). Two-pass logic: deterministic substring match against `entity_name` / `parent_company` / sibling-entity aliases first; small-model classifier only on mixed-authorship OpenAlex results. arXiv / S2 don't carry structured affiliation so the deterministic pass returns `unknown` and the classifier never fires for them.
- **`source-quality.md` § Independence override rules academic-affiliation amendment** — resolves the documented "entity employees publishing on arXiv tagged as `independent`" failure mode that Tier 1 left as architectural debt. Lands in the same subsection Path 3 introduces (regulator-authority).
- **Publisher-quality tags** — add `semanticscholar` and `openalex` to `_SECONDARY_PUBLISHERS` in `pipeline/common/source_classification.py`. `pipeline/common/publisher_quality.py` re-imports the same set.
- **`dr stats` `academic_topic_coverage`** — extend the set-shaped origin filter from `{arxiv}` to `{arxiv, s2, openalex}` (the Tier 1 aggregate is shaped for this extension; no aggregate-shape change). Revise the success metric upward — Tier 1 ships ≥40% single-source target; Tier 2 restores the original ≥60% three-source target.
- **Test surface** — port the per-API success/failure cases, the deterministic-vs-classifier branches, and the cross-stage end-to-end affiliation-override test from the original Path 2 plan.
- **`AGENTS.md` § Tooling** — document `SEMANTIC_SCHOLAR_API_KEY` and `OPENALEX_MAILTO`.

**Effort estimate**: ~3–4 days (down from the 5–7-day original three-source design, because Tier 1 already shipped: topic plumbing through `verify_claim` / `_research` / `decomposed_research`, the `_select_research_origins` selector, the per-URL `acquisition` write site in `execute_searches`, and the `academic_topic_coverage` aggregate scaffold). Re-baseline at planning time.

**Affiliation threshold open question** (re-opened from the Tier 1 plan's "Resolved" list when Path 2 was simplified): the substring-match algorithm + same-parent subsidiary alias resolution + classifier-on-mixed-authorship design from the original Path 2 stays the proposed answer; verify it against real OpenAlex payloads during Tier 2 implementation.

#### Curated allowlist of independent AI research orgs

A small, hand-maintained list of high-trust, freely-accessible AI watchdog and research domains. Bias the URL scorer and `publisher_quality` classifier toward these.

**Candidate domains to evaluate**: Stanford HAI AI Index, Epoch AI, Future of Life Institute, AI Incident Database, METR, Apollo Research, MLCommons, AI Now Institute, ACM Digital Library (open-access content only), Mozilla Foundation AI research, Center for AI Safety, Algorithmic Justice League.

**Open questions**:
- Where does the list live? Static YAML, a new content collection, or extension of the publisher-quality registry?
- How is independence handled? Some of these (FLI, Epoch) are funded by AI labs — is that a COI flag or background context?
- Refresh cadence — who reviews the list and how often?

#### MCP servers for Tier 1/2 APIs

Rather than building bespoke pipeline integrations for the academic and regulator APIs (Tier 1 ships native code for arXiv and SEC EDGAR; Tier 2 will add Semantic Scholar and OpenAlex), evaluate existing community MCP servers and wire them into the Researcher's tool surface.

**To evaluate**:
- Existing community MCP servers for arXiv, Semantic Scholar, OpenAlex, SEC EDGAR — survey what's available, what's maintained, what's reliable.
- Trade-off: less code to maintain vs. less control over query shape, error handling, and rate limits.
- Authentication and key management for hosted MCP servers vs. local servers.

**Open questions**:
- Does the pipeline architecture support MCP-server-as-tool natively, or does this need an adapter layer?
- How do MCP-sourced results get classified for `publisher_quality` and `independence`?
- Do we want a hybrid (MCP for discovery, native code for ingest) or full MCP?

#### Seattle Public Library digital catalog

SPL has one of the strongest urban library digital subscriptions in the US — free remote access to ProQuest, EBSCOhost, Statista, Gale Business, sometimes Bloomberg. With a library card, this opens a large block of paywalled trade and academic content.

**Possible approaches**:
- **Manual workflow** — operator logs in, exports a PDF or HTML, ingests via `dr ingest` against a local file path. Low engineering cost, high human cost.
- **Session-cookie automation** — pipeline holds an authenticated session and fetches through it. Higher engineering cost, requires cookie refresh handling.
- **Bookmarklet / browser extension companion** — operator browses, the companion captures and ships URLs to the pipeline. Middle ground.

**Open questions**:
- Are SPL ToS compatible with automated fetching through an authenticated session? Likely not for bulk.
- Can `dr ingest` accept a local file path today? If not, that's a prerequisite.
- Independence and trust: ProQuest and EBSCOhost re-host published articles; the underlying source (publisher) is what determines `independence`, not the database.

#### Tier 2 sequencing & not-in-scope

These are mostly independent of each other. Curated allowlist is the cheapest and ships first; SPL is the most valuable but most operationally fiddly.

Not in scope (yet): building a new MCP server (only evaluating existing ones); negotiating institutional access with non-public databases beyond SPL; multi-library support.

### Source pool — Tier 3 (drafted)

**Depends on**: [`source-pool-expansion-tier1.md`](source-pool-expansion-tier1.md) and its companion [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md), Tier 2 above.

Tier 3 covers ideas that are real but lower priority. They either have narrower applicability, depend on relationships that take time to build, or address gaps Tier 1 and Tier 2 already mostly cover.

#### News APIs

Replace ad-hoc news searches with a structured news API. Better systematic coverage, fewer 403s, cleaner metadata.

**Candidates**: GDELT (free, massive scale, sentiment + entity tags); NewsAPI.org (free tier, simple REST, limited historical depth); NewsCatcher (free tier, sometimes better for niche tech outlets).

**Open questions**:
- Where does this slot in vs. Tavily/Exa? Is it a third search backend or a different abstraction (e.g. "monitor entity X for news mentions")?
- For claim *verification* (the system's main job), do we need news-as-event-stream, or is news-as-search sufficient?
- Independence handling: news outlets are mostly `secondary` / `independent`, but the restatement failure mode applies heavily here.

#### RSS feed aggregation

Many publishers expose full-content RSS even when their HTML pages return 403 to bots. Curate feeds from the 30–50 publications that matter for AI coverage and ingest them on a poll cadence.

**Possible shape**: a curated feed list (YAML); a periodic poll that ingests new entries as draft sources, available for Researcher queries; deduplication against the existing source corpus.

**Open questions**:
- Does this push us toward an event-driven mode the pipeline doesn't currently have?
- Storage cost — every poll yields entries even when no claim needs them. Unbounded growth without a retention policy.
- Overlap with news APIs — pick one or both?

#### Direct partnerships

Some nonprofit and journalist publications grant API or research access on request. The dangerousrobot.org research mission is plausibly aligned with their own.

**Possible partners to approach**: ProPublica, MIT Technology Review research desk, Future of Life Institute (already cited heavily), AI Incident Database (already free; partnership could help with data quality / cross-linking), Mozilla Foundation researchers.

**Open questions**:
- This is a relationship-building track, not an engineering track. Who owns it?
- What does dangerousrobot.org offer in return — citation, cross-linking, joint research?
- Legal: do partnership terms create obligations the project isn't ready for?

#### Tier 3 sequencing & not-in-scope

These are mostly low-coupling. The most valuable is probably the partnership track because it can produce permission to access content the engineering tracks can't reach. But it's also the slowest.

Not in scope (yet): paid premium news APIs (Bloomberg Terminal, Refinitiv); scraping behind authentication on sites that don't permit it; pub/sub event bus for incoming sources.

### PDF publish surface (drafted, post-attachment)

**Depends on**: [`source-pdf-attachment.md`](source-pdf-attachment.md) landed.

PDF attachment gives a source a locally-stored PDF and wires the ingestor to read from it, but does nothing with the PDF on the public site. For redistributable PDFs (public domain, permissively licensed, granted permission) we want dangerousrobot.org to additionally serve the file with a download link, so readers can audit the grounding document without navigating to a dead origin URL. Non-redistributable PDFs stay off the site.

**Design summary**:

- **Gating flag**: `pdfs[].republish: true` is required to expose a PDF on the site. Default `false`. `license_note` is required alongside `republish: true` (already validated by the core plan).
- **Astro rendering**: `src/pages/sources/[...slug].astro` gains a conditional section between summary and key_quotes. Consider factoring `<PdfAttachment>` into `src/components/PdfAttachment.astro`.
- **Build-time asset copy**: walk `research/sources/**/*.md`; for sources with `pdfs[0].republish === true`, copy the on-disk PDF to `dist/sources/<year>/<slug>.pdf`. The sha256 verification in the core plan's loader has already run, so bytes copied are known-good. Build fails if `republish: true` but the PDF is missing. `republish: false` PDFs are **never** copied.
- **Headers and indexing**: `_headers` sets `X-Robots-Tag: noindex` for `/sources/*.pdf` (keeps the source `.md` page canonical) and a conservative 1-hour cache.
- **Accessibility**: `aria-label` carries the full announcement (page count, "opens in new tab"); arrow glyph is `aria-hidden`; page count in text so screen readers can pre-announce download weight.

**Test plan**:
- Fixture `republish: false` + matching PDF: build succeeds, `dist/sources/<year>/<slug>.pdf` absent, no PDF section rendered.
- Fixture `republish: true` + `license_note` + matching PDF: build succeeds, file present, download link with correct `aria-label`.
- Fixture `republish: true` without `license_note`: build fails at schema validation (already enforced by core plan's `superRefine`).
- Manual: Lighthouse a11y check; `curl -I` confirms `X-Robots-Tag: noindex`.

**Done when**:
1. Source pages with `pdfs[0].republish === true` render the attachment section with download link and accessible label.
2. Source pages with `pdfs[0].republish === false` (or no `pdfs`) render no attachment section.
3. `dist/` contains only republishable PDFs; non-republishable PDFs are never copied.
4. `_headers` attaches `X-Robots-Tag: noindex` and a conservative `Cache-Control` to all `.pdf` responses under `/sources/`.
5. Build fails loudly if a `republish: true` source lacks a `license_note`.

**Out of scope**: pdf.js inline viewer; full-text search across attached PDFs; cache-busting hash in PDF URLs (`<slug>.<sha8>.pdf`); social card / OG-image preview of PDFs.

**Critical files**: `src/pages/sources/[...slug].astro`; `src/components/PdfAttachment.astro` (new, optional); `astro.config.mjs` (or `scripts/copy-republishable-pdfs.ts`); `public/_headers`; `AGENTS.md`.

### Scheduled citation audits (drafted)

**Trigger**: content volume makes manual auditing burdensome; agents from Phase 4 exist.
**Depends on**: Phase 4 (agents must exist to automate).

Set up recurring automated tasks: citation audits, stale claim detection, and source ingestion queue.

**Tasks**:
- Create `.github/workflows/audit.yml`: scheduled weekly (Monday); runs citation integrity check + stale claim detection; creates PR with results using `peter-evans/create-pull-request`.
- Implement stale claim checker: check claims where `next_review_due <= today`; output the list of claims due for review.
- Implement `QUEUE.md` intake workflow: define `QUEUE.md` format (append-only with processed/unprocessed flag); on PR merge with `QUEUE.md` changes, run the ingestor for new URLs; ingestor output committed to a branch, PR opened for review.
- Pin GitHub Actions by SHA (supply-chain security).
- Set up Dependabot for dependency updates.

**Design decisions**:
- **GitHub Actions for scheduling**: agents are PydanticAI (not Claude Code native), so scheduling uses GitHub Actions.
- **PR-based output**: all automated changes go through PRs. Human reviews verdicts.
- **`QUEUE.md` format**: append-only Markdown list. Each entry has a URL and a status (`[ ]` pending, `[x]` processed). Workflow diffs against previous commit to find new entries.

**Open questions**:
1. **API key for LLM in CI**: PydanticAI agents need an API key. GitHub Actions secrets — but which provider/key?
2. **Notification**: stale claim alerts via GitHub Issues, or just a PR?

**Estimated scope**: medium. Mostly GitHub Actions YAML + connecting existing agent scripts.

---

## Section 3 — Full trust schema (v1.x reference)

The v1 source-quality scope shipped in `completed/source-quality-robust-roadmap_completed.md` reduced to a single new `independence` field plus claim-level `verification_level` / `cap_rationale` / `source_overrides`. The full trust block originally proposed (`document_type`, `authority`, `coi_with_subject`, `coi_notes`, detailed `publisher_group` spec, agent classifier for full backfill) is retained as v1.x scope. This section is a digest; full design text is in `completed/source-trust-metadata_superseded.md`.

### Four-axis schema

The full trust block organizes per-source signals along four axes:

1. **Site trustworthiness** — is the publisher itself a trustworthy venue? Distinct from topical authority.
2. **Document type** — marketing post, sustainability report, technical documentation, regulatory filing, blog post, independent research, or news article. Applicable to any source.
3. **Authority** — institutional (journalism, academic research, science publishing, industry analysis) and topical (authority on this specific claim's subject matter).
4. **Conflicts of interest / independence** — who funded it, who published it, what financial relationships exist.

### Schema shape (proposed)

Composite `trust:` block in source frontmatter, plus a flat `publisher_group` join key. Both `SourceFrontmatter` (`pipeline/ingestor/models.py`) and the Zod schema (`src/content.config.ts`) update in lockstep.

```yaml
trust:
  site_trust: low | medium | high
  document_type: marketing | sustainability-report | technical | regulatory | blog | research | news
  authority: low | medium | high
  independence: independent | first-party | trade-funded | regulatory | unknown
  coi_with_subject: true | false
  coi_notes: string

publisher_group: string
```

**Range rationale**: `site_trust` and `authority` use a 3-band categorical scale (numeric precision is false precision for editorial judgment). `document_type` and `independence` are enums (factual classifications, not ratings). `coi_with_subject` is a boolean with required `coi_notes` when true.

**Cross-field rule**: when `coi_with_subject: true`, `coi_notes` must be present and non-empty. Pydantic implementation uses `model_validator(mode="after")` on a nested `TrustMetadata` model. Zod implementation uses `.superRefine()` on the nested object.

### Phase 6 — Agent classifier and full backfill (v1.x)

Ingestor agent drafts `site_trust`, `document_type`, `authority`, and `independence` classifications. Operator reviews before committing. Manual `coi_with_subject` remains operator-only. Full backfill of all 146+ source files.

**Exit criterion**: all source files have `trust:` block populated; agent classifier validated on a held-out set before full run.

### Phase 7 — Publisher groups registry (v1.x)

Populate `research/publisher-groups.yaml` for sectors relevant to launch claims (energy, tech press, financial analysis). Ingest agent populates `publisher_group` on new sources. Analyst instructions updated to note same-group corroboration.

**Exit criterion**: registry covers major publishers in at least energy and tech press sectors; new source ingest populates `publisher_group` where match found.

### Phase 8 — Scoring with entity context (v1.x)

Pass parent company metadata to scorer to improve COI detection and source relevance for subsidiary products. Depends on entity enrichment work (see Section 1: "Scoring with entity context" and "Product → company relationship"). Scorer at this point is `pipeline/researcher/scorer.py` (introduced by `completed/researcher-decomposition.md`).

### Cross-references for v1.x trust schema

- v1 shipped scope: [`completed/source-quality-robust-roadmap_completed.md`](completed/source-quality-robust-roadmap_completed.md).
- Full original design (with all 8 phases): [`completed/source-trust-metadata_superseded.md`](completed/source-trust-metadata_superseded.md).
- Architecture contract for source classification: [`docs/architecture/source-quality.md`](../architecture/source-quality.md).
- Schema mirror locations: `pipeline/ingestor/models.py` (Pydantic) and `src/content.config.ts` (Zod).
- Analyst-decomposition interaction: if [`drafts/analyst-decomposition_stub.md`](drafts/analyst-decomposition_stub.md) lands before Phase 6, COI/independence weighting moves into the per-source stance classifier rather than the monolithic analyst instructions.

---

## Section 4 — Reference materials

Historical and superseded source-quality documents, retained for context.

- **Signal landscape survey** → [`completed/source-quality_survey_completed.md`](completed/source-quality_survey_completed.md). Maps the source-quality problem across the full pipeline; identifies signals that are implemented, planned, or absent at each stage. The taxonomy and "scope breakdown" (no architectural change vs. requires state machine vs. requires larger refactor) inform any future plan in this area.
- **2026-04 strategic critique** → [`completed/source-quality-agent-review_completed.md`](completed/source-quality-agent-review_completed.md). Three-agent independent critique that drove the rewrite of the original v1 roadmap. Surfaced the verification-scale-measures-diversity-not-corroboration limitation, the cap-as-blunt-rule limitation, and the display-layer-underdeveloped problem.
- **v1 roadmap (superseded)** → [`completed/source-quality-roadmap_superseded.md`](completed/source-quality-roadmap_superseded.md). Original 13-item roadmap. Superseded by the robust roadmap after the agent critique.
- **v1 trust metadata (superseded)** → [`completed/source-trust-metadata_superseded.md`](completed/source-trust-metadata_superseded.md). Full 8-phase trust-block design. Phases 1–5 absorbed into v1; phases 6–8 are digested in Section 3 above.

### Related independent peer plans

These are not source-quality plans per se, but they affect source pool quality enough to cross-reference:

- [`source-pool-expansion-tier1.md`](source-pool-expansion-tier1.md) — Tier 1 do-now: shared infrastructure, arXiv (academic API), SEC EDGAR, Wayback gap-filling. Semantic Scholar / OpenAlex / affiliation override deferred to § Source pool — Tier 2 above.
- [`source-pool-expansion-tier1-search-backend.md`](source-pool-expansion-tier1-search-backend.md) — Tier 1 companion: search backend swap (Tavily-only; Exa deferred).
- [`source-pdf-attachment.md`](source-pdf-attachment.md) — PDF attachment as an alternate ingestion surface for paywalled / 403-locked documents.
- [`researcher-host-blocklist.md`](researcher-host-blocklist.md) — pre-ingest URL filter for known-paywall and known-noise hosts.
- [`wayback-archive-job.md`](wayback-archive-job.md) — background-job framework, with wayback archival as the first concrete job.

---

## Section 5 — Cost/benefit triage (2026-05-09)

Triage of the open backlog after a `completed/` re-review. Items already shipped were dropped (see § Already shipped below). Items partially shipped were restored to the open list with a narrowed scope.

Scale: cost and benefit each 1–10 (1 = trivial / marginal, 10 = months / transformative). Ratio = cost ÷ benefit; smaller is better. Rough estimates — re-baseline at planning time.

### Already shipped (dropped from triage)

- **Source reuse before fetching** → `completed/onboard-reuse-verify-sources.md`.
- **Pass entity name + parent_company into scorer / planner prompts** (Section 1 "Scoring with entity context"; Section 3 Phase 8) → `completed/scorer-quality-signals.md` Item C.
- **First-party source weighting in analyst reasoning** (Section 1 "Source independence signals") → analyst instructions already weight `first-party` heavily per `completed/source-quality-robust-roadmap_completed.md`. Auditor mirror could still be added as a small follow-up.

### Partial landings restored to the open list

- **Path 2 completion** — Tier 1 Path 2 only shipped arXiv (`commit 6fcb0ed`). Semantic Scholar + OpenAlex tools + cross-stage affiliation override + `source-quality.md` independence-amendment were carved out as "Tier 2" in § Section 2 above; restored here as Tier 1 leftover work.
- **Source freshness** — `published_date` schema field already exists on both `SourceFrontmatter` (`pipeline/ingestor/models.py:19`) and Zod (`src/content.config.ts:14`), but ingestor extraction + analyst reference are unwired. Counted as a partial.

### Triage table — sorted smallest ratio first

| Technical change | Benefit | Cost / Benefit (ratio) |
|---|---|---|
| Path 2 completion: Semantic Scholar + OpenAlex tools + cross-stage affiliation override classifier + `source-quality.md` § Independence override amendment | Restores ≥60% 3-source academic coverage; fills documented "entity employees on arXiv tagged independent" architectural debt | C:4 / B:7 = **0.57** — Tier 1 scaffolding already shipped; enum slots reserved |
| Negative site signals: extend `researcher-host-blocklist` to low-trust categories + pre-scorer drop of `tertiary` candidates | Cleaner candidate pool; kills Reddit/Quora forum-result false-positives observed during recent content sprint | C:3 / B:5 = **0.60** — `source_classification.py` patterns ready to reuse |
| Curated allowlist of independent AI research orgs (HAI, Epoch, METR, FLI…) biasing scorer + publisher_quality | High-trust watchdog content rises in candidate ranking | C:2 / B:3 = **0.67** — small static list; FLI/Epoch COI flag is the open question |
| Source freshness: wire ingestor `published_date` extraction + analyst instruction to weight age (schema field already exists) | Catches stale sources on fast-changing claims (regulatory, energy metrics) | C:3 / B:4 = **0.75** — half-shipped (schema only); ingestor parser + instruction remain |
| Path 3: SEC EDGAR tool + subject-relevance classifier + filer-vs-subject independence override + `source-quality.md` amendment | Regulator-authority sources for OpenAI (via Microsoft) and Anthropic (via Amazon/Alphabet); resolves "regulator filings about not by entity" gap | C:6 / B:6 = **1.00** — 5–7 days; gated on `'edgar'` in `research_origins` and `SEC_EDGAR_USER_AGENT` |
| ~~Render `parent_company` on product entity pages~~ | Promoted to [`entity-metadata-surface.md`](entity-metadata-surface.md) (2026-05-09). Bundled with company entity fields into one plan. | — |
| ~~Company entity fields + `legal_name` + render surfaces~~ | Promoted to [`entity-metadata-surface.md`](entity-metadata-surface.md) (2026-05-09). `subsidiaries` punted from the bucket; remains in § Section 1 (Schema quality) as a candidate field. `official_website` not added — existing `website` field already plays that role. | — |
| News API integration (GDELT or NewsAPI) as additional Researcher backend | Systematic news coverage with cleaner metadata vs. ad-hoc Tavily/Brave | C:5 / B:4 = **1.25** — open: third backend vs. event-stream abstraction |
| PDF publish surface: build-time copy of `republish: true` PDFs to `dist/sources/<year>/<slug>.pdf` + `_headers` `noindex` | Readers can audit grounding documents when origin URL dies | C:4 / B:3 = **1.33** — depends on `source-pdf-attachment.md` landing first |
| Phase 7 / §1 white-label: `research/publisher-groups.yaml` + `publisher_group` field on sources + analyst warning on same-group corroboration | Defeats syndication-as-independence false-positive (3 "independent" Hearst sites = 1) | C:7 / B:5 = **1.40** — manual curation + ongoing maintenance |
| Phase 6: ingestor agent classifier for `site_trust` / `document_type` / `authority` / `independence` + full backfill of all source files | Trust signals on every source, not just `independence`; foundation for Phase 7 | C:7 / B:5 = **1.40** — agent prompt + held-out validation + backfill of 146+ files |
| Seattle Public Library digital catalog (ProQuest, EBSCOhost, Statista) ingest path | Unlocks paywalled trade/academic content via library access | C:7 / B:5 = **1.40** — ToS risk; manual workflow likely; `dr ingest` local-file path may be prereq |
| Eval community MCP servers for arXiv / S2 / OpenAlex / EDGAR | Less bespoke integration code | C:3 / B:2 = **1.50** — late: Tier 1 already shipped native code; ROI weakens after Path 3 |
| Scheduled citation audits via `.github/workflows/audit.yml` + `QUEUE.md` intake | Weekly stale-claim scan + agent-driven re-audit at content scale | C:6 / B:4 = **1.50** — gated on Phase 4 agents existing; CI LLM key is open |
| Direct partnerships (ProPublica, MIT TR, AIID, Mozilla) for research-grade access | Permission-based access to sources engineering can't reach | C:8 / B:5 = **1.60** — relationship track, slowest payoff |
| RSS feed aggregation from 30–50 AI publications | Full-content access where HTML returns 403 to bots | C:6 / B:3 = **2.00** — pushes toward event-driven mode the pipeline lacks |

### Recommended bucketing for the six top items

The six lowest-ratio items cluster naturally by shared file surface and shared review pass. Three buckets reduce friction (one prompt-eval pass, one schema review, one analyst-instruction review per bucket) while letting buckets ship in parallel.

**Bucket 1 — Scoring quality (ship first; ~1–2 days total)**
- Negative site signals (blocklist categories + pre-scorer tertiary drop)
- Curated allowlist of independent AI research orgs

*Why together*: both touch `pipeline/researcher/scorer.py` (prompt) and `pipeline/common/source_classification.py` / `publisher_quality.py`. Single eval pass tests both. (3) is subtractive (drop noise) and (1) is additive (boost trusted) — opposing levers on the same rank list, so co-tuning catches over-correction. Ship as one PR; revert is one revert.

**Bucket 2 — Entity metadata surface** — Promoted to [`entity-metadata-surface.md`](entity-metadata-surface.md) (2026-05-09); shipped 2026-05-09 in a single commit covering schema, ResolvedEntity passthrough, writer + linter mirrors, render across product / company / claim pages (incl. verification badge), pipeline reads (scorer + analyst prompts and instructions), one-time `parent_company` backfill on all five product files (`claude`, `chatgpt`, `gemini`, `greenpt`, `treadlightlyai`), `verification_status: unverified-startup` on `products/treadlightlyai.md`, drive-by linter fixes for `sec_cik` and `status`, and the `## Entity metadata` amendment in [`docs/architecture/source-quality.md`](../architecture/source-quality.md).

**Bucket 3 — Source provenance (3–5 days total, mostly Path 2)**
- Source freshness wiring (ingestor `published_date` extraction + analyst instruction)
- Path 2 completion (Semantic Scholar + OpenAlex + affiliation override)

*Why together*: both add per-source provenance metadata that the analyst should weigh. Both require an analyst-instruction pass and a `source-quality.md` amendment. Same review surface; same regression set. Ship freshness first as a small commit (~half day) so the analyst-instruction pattern is in place, then Path 2 lands the larger researcher-tool work against that pattern.

**Friction-reduction summary**
- Each bucket touches a coherent slice of the codebase: scorer prompt + classification (1), entity schema + Astro (2), ingestor + analyst instructions + researcher tools (3).
- Buckets are independent — any two can ship in parallel without merge collisions.
- Within each bucket, item ordering is dictated by the smaller item warming up the analyst/eval surface for the larger one.
- An alternative four-bucket split would carve Path 2 off on its own track (it's the largest single item); use that if Path 2 needs different reviewers or longer cadence than freshness wiring.

---

## Open questions

These are open questions for the *collector*, not items inside specific entries.

- **When does an idea promote out of Section 1 into Section 2?** Heuristic: when a designated implementation surface and an effort estimate both exist. Trigger: operator review.
- **Should completed peer plans (researcher-decomposition, scorer-quality-signals, source-quality-do-now) get an explicit "where their gaps land now" pointer in this file?** Today no; the architecture doc carries that context. Revisit if pointers are repeatedly searched for.
- **Backlog volume threshold for splitting this collector.** If Section 1 grows past ~15 ideas or Section 2 past ~6 drafted plans, consider splitting along the seam from Option B of the consolidation review (ideas + reference vs. drafts).

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-08 | agent (opus-4-7) | iterated | Initial creation. Subsumes `research-quality-ideas.md` (Section 1), `drafts/source-pool-expansion-tier{2,3}.md` (Section 2), `drafts/source-pdf-publish.md` (Section 2), `drafts/scheduled-citation-audits.md` (Section 2). Phases 6–8 of `source-trust-metadata.md` digested into Section 3 (full text retained in `completed/source-trust-metadata_superseded.md`). `source-quality_survey.md`, `source-quality-agent-review.md`, `source-quality-roadmap.md`, and `source-trust-metadata.md` moved to `completed/` with `_completed` / `_superseded` suffixes per AGENTS.md naming table. Tightened only obvious internal redundancy in the absorbed material; substance preserved. |
| 2026-05-09 | agent (opus-4-7) | added | Section 5 — Cost/benefit triage. Triaged backlog after a `completed/` re-review: dropped three already-shipped ideas (source reuse, parent_company-in-scorer / Phase 8, first-party analyst weighting); restored Path 2 leftover (S2 + OpenAlex + affiliation override) and source-freshness wiring as partials. Sorted-by-ratio table + 3-bucket sequencing recommendation (Scoring quality → Entity metadata → Source provenance) for the six lowest-ratio items. |
| 2026-05-09 | agent (opus-4-7) | promoted | Promoted Bucket 2 (Entity metadata surface) to [`entity-metadata-surface.md`](entity-metadata-surface.md). Triage table rows for the company-entity-fields and parent_company-render items collapsed into the single new plan stub. `subsidiaries` field explicitly dropped from the bucket; remains in § Section 1 as a candidate field for future COI work. `official_website` decision resolved: not adding it — existing `website` field already plays that role. Bucket 1 (Scoring quality) and Bucket 3 (Source provenance) untouched. |
| 2026-05-09 | operator | added | Two new ideas surfaced during entity-metadata-surface planning ("Pipeline-driven company entity enrichment" + "Onboarding verification gate / entity verification status"). Operator chose a single shared onboarding-research agent across all three entity types (same workflow, per-type prompt section). Both ideas collapsed into a Section 1 pointer at [`drafts/entity-onboarding-research_stub.md`](drafts/entity-onboarding-research_stub.md), which holds the full design space. The lightweight `verification_status` schema seat + render badge folded into [`entity-metadata-surface.md`](entity-metadata-surface.md) so the agent has a place to plug in. |
