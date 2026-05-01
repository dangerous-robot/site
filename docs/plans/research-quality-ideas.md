# Research quality improvement ideas

**Type**: Idea backlog (not an implementation plan)
**Created**: 2026-05-01
**Source**: Consolidation of `arch-docs-pipeline-improvements.md` + operator review

Ideas for improving the pipeline's research output quality. Organized by concern: content quality (what evidence the pipeline finds and how it weights it) and schema quality (what structured data the pipeline can represent and reason over).

Ranked within each section by expected research impact, with pragmatic notes on cost and dependency.

---

## Content quality

### Source independence signals in analyst reasoning

Sources from the subject entity (the company or product being evaluated) carry an inherent conflict of interest. Today the analyst receives all sources equally. The analyst instructions could be updated to treat first-party sources as lower-weight evidence, especially for verdict-sensitive claims.

**Research impact**: High. Credibility of verdicts depends heavily on whether the analyst can distinguish independent evidence from self-reported claims.  
**Cost**: Low for instruction update; medium if COI classification is added to source schema.  
**Cross-reference**: `source-trust-metadata_stub.md` tracks schema-side COI metadata; this idea is the analyst-instruction counterpart.

---

### Scoring with entity context

The URL scorer today receives only the claim text and candidate URL metadata. It has no knowledge of the entity being evaluated -- its parent company, industry, or common aliases. A source that mentions "Google" but not "Gemini" may still be highly relevant if the claim is about Google's subsidiary products.

**Ideas**:
- Pass entity name + parent company to the scorer prompt.
- Pass known entity aliases or industry terms from the entity's schema fields.

**Research impact**: High. Improves precision of early-stage source retrieval, especially for subsidiary products and holding-company claims.  
**Cost**: Low (prompt-level change in `pipeline/researcher/scorer.py`); requires entity metadata (see schema section).

---

### Source freshness as a quality signal

The analyst has no structured signal about how recent a source is. For fast-changing claims (regulatory filings, energy metrics, corporate structure), a 2022 source may be actively misleading even if it was accurate at the time.

**Ideas**:
- Add optional `published_date` to `SourceFrontmatter`; ingest agent attempts to extract it from page metadata.
- The analyst instruction could reference source dates when building the verdict narrative.
- Claims with `recheck_cadence_days` set low could deprioritize sources older than the cadence.

**Research impact**: Medium. Matters most for claims about current practices or live data; less important for historical facts.  
**Cost**: Medium (schema change + ingest agent change + instruction update).

---

### Source reuse before fetching

The researcher generates candidate URLs from web search. If a URL already exists in `research/sources/`, the pipeline re-ingests it anyway. Reusing the existing source file would improve coherence (same summary text across claims) and cut ingest cost.

**Ideas**:
- Before ingesting a candidate URL, check if it matches an existing source by URL (after canonicalization).
- If matched, skip ingest and pass the existing source file to the analyst.

**Research impact**: Medium. Primarily coherence and cost; also prevents divergent summaries of the same source across claims.  
**Cost**: Low for URL match; depends on dedup canonicalization work already tracked in `docs/UNSCHEDULED.md` (Dedup detection).

---

### Negative site signals in search results

Some publishers are structurally weak for research: content farms, vendor-sponsored analysis, PR wire services. Today these pass the scorer unless the title/snippet is obviously irrelevant.

**Ideas**:
- Extend the researcher host blocklist (`researcher-host-blocklist.md`) to cover not just paywalled sites but low-trust source categories.
- The scorer prompt could note known-problematic source patterns (press release wires, vendor white papers presented as independent research).

**Research impact**: Medium. Reduces noise in the source pool; most valuable for claims that attract a lot of PR coverage.  
**Cost**: Low for blocklist extension; medium for scorer-prompt adjustments.

---

## Schema quality / capability

### Product → company relationship

Products (`research/entities/products/`) have a `parent_company` field but it is schema-only and not used in pipeline reasoning or site rendering. Formalizing this relationship would enable:
- Passing parent company context to the scorer and analyst.
- Cross-referencing company-level sources when evaluating a product claim.
- Site rendering: "Made by Anthropic" on a Claude claim page.

**Research impact**: High (enables entity-context scoring above).  
**Cost**: Medium (schema change + pipeline reads + site rendering).  
**Cross-reference**: `docs/UNSCHEDULED.md` → "parent_company not rendered" (site gap).

---

### Company metadata enrichment

Company entities today carry minimal structured data. Adding structured fields would support richer conflict-of-interest detection and entity-context scoring.

**Candidate fields**:
- `legal_name` (distinguish "OpenAI" from "OpenAI, LLC" vs "OpenAI Global, LLC")
- `official_website` (used as a signal for primary-source classification)
- `parent_company` (holding companies, acquisition history)
- `subsidiaries` (cross-link to related entities)

**Research impact**: Medium. Most valuable when combined with COI detection and entity-context scoring.  
**Cost**: Low for schema addition; medium for backfill and any agent-side use.

---

### White label domain classification by sector

Several sectors (financial analysis, technology press, energy reporting) have dominant white-label or syndication networks that appear independent but share ownership. Classifying domains by sector affiliation would let the analyst and scorer recognize when three "different" sources are actually the same publisher.

**Ideas**:
- Maintain a `research/publisher-groups.yaml` mapping domains to publisher groups.
- The ingest agent checks the source URL against this map and populates a `publisher_group` field on the source.
- The analyst instruction could warn against treating same-group sources as independent corroboration.

**Research impact**: Medium. Especially relevant for energy claims, where a few publishers dominate syndicated content.  
**Cost**: High (manual curation of publisher map; ongoing maintenance).

---

### Sector entity type support

**Status: implemented.** `SECTOR = "sector"` is in `EntityType` (`pipeline/common/models.py`) and `dr onboard --type sector` is supported. Included here as a capability marker: the schema can represent sector-level entities, but sector-scoped claim templates and sector-specific research strategies (e.g., identifying industry-level sources vs. company sources) are not yet developed.

**Schema extension opportunity**: Sectors could carry additional metadata that improves claim context -- dominant publishers in the sector, regulatory bodies, common conflict-of-interest patterns.

---

### Source trust metadata (already planned)

See `docs/plans/source-trust-metadata_stub.md`. Covers: site trustworthiness, document type classification, authority signals, and conflict-of-interest annotation on source files. That stub covers the schema and display decisions; the content-quality complement is the analyst-instruction update noted above.

---

## Notes from prior doc

**3.2 (Apply `source_type` in standalone `dr ingest`)** was a code gap: `dr ingest` wrote source files without a `source_type` field because `classify_source_type()` was only wired into the full pipeline flow. Resolved -- `dr ingest` was deprecated in favor of `dr step-ingest`, which calls `classify_source_type` before writing. No action needed.

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-01 | human (Brandon) | iterated | Refactored from `arch-docs-pipeline-improvements.md`; restructured as ranked idea backlog; cross-referenced existing plans |
