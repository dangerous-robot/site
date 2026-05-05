# Source quality: do-now implementation plan

> **Completed (2026-05-05)**: items folded into other plans. Groups 1+3a shipped in [`scorer-quality-signals.md`](../completed/scorer-quality-signals.md); Groups 2a, 2b, 3b, 4a, 4b, 6a, 6b, 7a, 8 incorporated into [`source-quality-robust-roadmap.md`](../source-quality-robust-roadmap.md); Groups 5a, 5b deferred to v1.x. Tracking lives in those plans; this file is retained as historical context.

**Type**: Draft implementation plan (retired into other plans)
**Created**: 2026-05-02
**Derived from**: [`source-quality_survey.md`](../source-quality_survey.md) — "No architectural change required" tier
**Scope**: All items implementable in the current linear pipeline; no state machine needed

This plan takes the "no architectural change required" items from the source quality survey and orders them by impact. Each item is a candidate for a focused implementation plan. Items that share a code surface or dependency are grouped.

Items requiring the state machine or a larger refactor are out of scope here. See the survey's "Scope breakdown" section.

---

## Group 1: Scorer fixes (highest leverage)

> **Promoted**: Items 1a, 1b, and 3a have been extracted into [`plans/scorer-quality-signals.md`](../scorer-quality-signals.md) and added to the v1.0.0 roadmap. They remain here for context but implementation tracking moves to that plan.

These two items directly address the biggest quality bypass in the current pipeline. The scorer is the main pre-ingest quality filter; both items tighten it.

### 1a. Fix scorer fallback behavior

**Survey ref**: §6 (scoring and ranking)

When the scorer drops all candidates (every URL scores <4), `decomposed.py` falls back to keeping all candidates. This silently bypasses quality filtering for the weakest queries — the ones that most need it. The fix: when the scorer drops everything, fail the query and log it in the trace rather than passing all candidates through. The threshold check handles the downstream consequence (blocked if insufficient usable sources result).

This is a code change in `decomposed.py`, not a prompt change. The behavior should be covered by a new unit test: scorer-drops-all → query marked failed → trace logged → no candidates passed to ingest.

### 1b. Inject publisher quality hints into the scorer prompt

**Survey ref**: §4, §6

The scorer prompt currently sees only URL, title, snippet, and source query. It has no awareness of domain type. A relevant-sounding snippet from a PR wire service scores identically to one from a regulatory filing.

Two complementary approaches — combine them or pick one:
- **Domain classification hint**: for each candidate URL, classify the domain against the `source_classification.py` patterns (already implemented post-ingest; the domain lookup can be extracted and run pre-ingest) and inject a quality label (`primary`, `secondary`, `tertiary`) into the scorer prompt per candidate.
- **Community forum soft-block**: add a list of known forum domains (reddit.com, quora.com, news.ycombinator.com, stackexchange.com, etc.) and inject a per-candidate flag or a global instruction. Allow forum sources through only when no better alternatives exist. Alternatively, add them to the blocklist with a `soft: true` treatment.

Dependency: whichever approach is chosen, it should be consistent with the expanded blocklist in Group 2.

---

## Group 2: Pre-ingest publisher filtering

These items expand publisher quality filtering that already exists (the blocklist and `source_classification.py`) to cover more cases.

### 2a. Extend the blocklist to cover low-trust source categories

**Survey ref**: §4

The current blocklist covers 7 domains with known 403/paywall behavior. It does not cover:
- PR wire services (prnewswire.com, businesswire.com, globenewswire.com, accesswire.com)
- Content farms and aggregators that republish without original reporting
- Vendor-sponsored "research" hubs

The existing blocklist YAML structure supports this. A plan would define the categories, enumerate known domains per category, and document the rationale for each addition so future operators can evaluate edge cases.

Pairing with 1b: the scorer hint approach (1b) handles domains that are low-quality but not worth hard-blocking. The blocklist handles domains that should never appear regardless of relevance score.

### 2b. Apply `source_classification.py` domain patterns as a pre-ingest filter

**Survey ref**: §4

`classify_source_type()` in `pipeline/common/source_classification.py` already maps domain substrings to primary/secondary/tertiary. This logic runs post-ingest. The domain patterns can be extracted and applied at the candidate stage — before scoring and before any ingest tokens are spent.

A plan for this would define the operational behavior: drop all tertiary-classified candidates before scoring (hard filter), or pass a quality label to the scorer prompt (soft signal). The soft signal approach (see 1b) is lower risk; the hard filter is faster and cheaper. Either could be implemented without changing the source_classification.py interface.

---

## Group 3: Query generation improvements

These items improve what the planner sends to search. They affect every research run.

### 3a. Pass `parent_company` into the planner and scorer prompts *(promoted to [`scorer-quality-signals.md`](../scorer-quality-signals.md))*

**Survey ref**: §1, §6

`parent_company` is present on the `ResolvedEntity` dataclass but not injected into any prompt. For subsidiary products and holding-company claims, queries without the parent name miss a large body of relevant coverage. For the scorer, a source about Anthropic is relevant to a claim about Claude — but the scorer doesn't know the relationship.

Low implementation cost: two prompt changes (planner and scorer), no schema changes. This pairs with the "Scoring with entity context" item in `research-quality-ideas.md`, which notes the same gap.

### 3b. Add entity-context vs. independent-coverage angle guidance to the planner

**Survey ref**: §1

The planner is told to vary the angle but has no instruction to balance entity-facing queries (which surface self-reported data) against independent-coverage queries (which surface third-party reporting). Adding explicit framing — "at least one query should target coverage by parties other than the entity itself" — is a prompt change with no structural dependency.

This is lower priority than 3a because it addresses query diversity, not entity coverage gaps. It can be combined with 3a in a single prompt revision.

---

## Group 4: Ingestor quality signals

These items add quality signals at ingest time — the only stage that reads actual page content.

### 4a. Add thin-content detection

**Survey ref**: §5

Pages that fetch successfully (HTTP 200) but return minimal content currently pass through the ingestor without any signal. A page with 200 words of prose around a 10-word factual claim is structurally different from a full report. Detect thin content by checking extracted body word count after stripping boilerplate; flag with `thin_content: true` on the source file and log a warning.

This does not require a trust schema change and is distinct from the `TerminalFetchError` path.

### 4b. Add soft-paywall detection

**Survey ref**: §5

Soft paywalls (HTTP 200 status, "subscribe to continue" body) are not caught by the existing HTTP error code check. Common patterns are detectable in extracted body text. Flag with `soft_paywall: true` and treat similarly to thin content: log a warning, allow the operator to decide whether to keep or discard.

Both 4a and 4b are ingestor instruction changes. They can be implemented together.

### 4c. Extract author/byline

**Survey ref**: §5

The ingestor does not extract author information. Institutional journalism and academic papers have named authors; absence of a byline is a weak negative signal. Adding an optional `author` field to `SourceFrontmatter` gives the analyst a signal it currently lacks. This pairs with the `authority` axis in `source-trust-metadata.md` Phase 6, which will use author information in trust classification.

Lower priority than 4a/4b because it adds data without immediately changing filtering behavior.

---

## Group 5: Operator visibility (no behavioral change)

These items add quality signal logging without changing pipeline behavior. They are prerequisites for the non-blocking warnings in Group 6, and for the eventual state machine quality gate.

### 5a. Extend research trace with per-query quality signals

**Survey ref**: §2

The decomposed researcher already logs `candidates_seen`, `urls_kept`, and `urls_dropped`. Extend with:
- **URL overlap rate**: what fraction of this query's candidates were already seen from other queries (computable from `from_query` field on `SearchCandidate`)
- **Estimated source type distribution**: domain-based classification of candidates (tertiary%, secondary%, primary%) using the patterns from 2b
- **Query quality flag**: a derived boolean or enum (good / low-overlap / low-quality-sources / both)

No behavioral change; operators see this in the audit sidecar.

### 5b. Define and log a failing query threshold

**Survey ref**: §2

Using the signals from 5a, define what constitutes a "failing query" (e.g., overlap rate >70% with other queries, or >60% of candidates classify as tertiary) and emit a warning-level log entry when a query crosses the threshold. No behavioral change.

These two items (5a, 5b) belong in a single focused plan.

---

## Group 6: Threshold check improvements

These items extend the existing `below_threshold()` gate — the only behavioral quality gate currently in the pipeline — to cover quality, not just count.

### 6a. Extend blocked-reason taxonomy to include `low_quality_sources`

**Survey ref**: §7

Add `low_quality_sources` as a valid `blocked_reason` alongside `insufficient_sources` and `terminal_fetch_error`. This is a schema change (frontmatter enum) and a code change in the threshold check. It does not change when blocking occurs — it enables future items (6b and the state machine gate) to use a meaningful reason when they do block.

### 6b. Add non-blocking quality warnings to the threshold check

**Survey ref**: §7

After the threshold check passes on source count, evaluate source quality: if the source pool is predominantly tertiary (e.g., 3 of 4 sources are tertiary), log a non-blocking warning in the claim sidecar. The analyst still runs; the operator sees a quality flag. No behavioral change, but gives the operator information that is currently invisible.

Dependency: 6a (for the reason enum), and Group 2 (for post-ingest source_type to be meaningful at threshold check time — it already is today via source_classification.py).

---

## Group 7: Analyst source weighting

### 7a. Pass `source_type` into analyst prompt

**Survey ref**: §6

The analyst currently receives all ingested sources equally, with no weighting by quality. Passing `source_type` (primary/secondary/tertiary) into the analyst prompt instructions allows the analyst to explicitly note when its verdict relies primarily on secondary or tertiary sources.

This is a bridge between the existing classification (which already runs) and the full trust metadata in `source-trust-metadata.md`. Lower priority than Groups 1-3 because it improves analyst reasoning, not source selection.

---

## Group 8: Publisher groups registry

**Survey ref**: §4

A `research/publisher-groups.yaml` registry maps domains to publisher group names, enabling the scorer and analyst to detect when multiple sources that appear independent are actually from the same corporate group. This is a data infrastructure item, not a code change. It pairs with `source-trust-metadata.md` Phase 7.

Lowest priority here because it requires ongoing data maintenance and has no immediate pipeline hook to consume it.

---

## Suggested implementation order

For a first focused plan, Groups 1 and 3a are the highest-leverage items: they fix the main quality bypass (scorer fallback), tighten scorer inputs (publisher hints), and improve query coverage (parent company). These can likely be grouped into a single implementation plan.

Groups 2 and 4a/4b are the next tier: expand publisher filtering, catch thin content at ingest.

Groups 5, 6, and 7 are visibility improvements that pay off once Groups 1-4 are in place and operators have something to observe.

Group 8 is data infrastructure; plan it alongside `source-trust-metadata.md` Phase 7.

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-02 | agent (claude-sonnet-4-6) | Initial draft | — |
