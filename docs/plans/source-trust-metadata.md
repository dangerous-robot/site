# Source trust metadata

> **Superseded (v1 scope)**: the v1 source-quality scope is defined in [`completed/source-quality-robust-roadmap_completed.md`](completed/source-quality-robust-roadmap_completed.md) (2026-05-05). The v1 schema reduces to a single new `independence` field plus claim-level `verification_level` / `cap_rationale` / `source_overrides`. The full trust block proposed here (`document_type`, `authority`, `coi_with_subject`, `coi_notes`, detailed `publisher_group` spec, agent classifier for full backfill) is retained as v1.x scope. Phases 6–8 of this plan remain valid v1.x cross-references.

**Status**: Superseded (v1 scope) — v1.x reference for full trust block
**Priority**: v1.x (full backfill + agent classifier + extended schema)
**Last updated**: 2026-05-05

Add structured trust metadata to source files so a skeptical reader can judge source quality without leaving the page, and so the analyst agent can weight sources appropriately when building verdicts.

## Why now

- The skeptical-reader test requires per-source signals beyond the current `kind` enum and `source_type` (primary/secondary/tertiary).
- The current schema doesn't capture conflicts of interest, source independence, authority, or marketing-vs-research disambiguation.
- The analyst currently receives all sources equally. COI and independence signals are verdict-sensitive and should be used in analyst reasoning from v1.
- v1 launch surface is ~20 claims, ~20-50 sources; backfilling that subset is feasible. Full backfill of all 146+ sources is v1.x.
- This plan is the schema-side answer to the structured source-quality signals called out in the v1.0.0-roadmap §13 "Result-quality validation" (status: `decision needed`). See cross-references.

## The four axes

1. **Site trustworthiness** — is the publisher itself a trustworthy venue? Distinct from topical authority.
2. **Document type** — what kind of document this is: marketing post, sustainability report, technical documentation, regulatory filing, blog post, independent research, or news article. Applicable to any source, not only first-party sources.
3. **Authority** — institutional (journalism, academic research, science publishing, industry analysis) and topical (authority on this specific claim's subject matter).
4. **Conflicts of interest / independence** — who funded it, who published it, what financial relationships exist between author and subject.

## Design decisions

### Schema shape

Use a composite `trust:` block in source frontmatter, not flat fields. Composite is more legible for manual backfill and groups related signals clearly. All subfields are optional to avoid breaking any of the existing 146+ source files.

Separately, add a flat `publisher_group: str` field (outside the `trust:` block) as a join key for the publisher registry. It is not a trust signal itself -- it enables the analyst and scorer to detect when "different" sources share ownership.

Both `SourceFrontmatter` in `pipeline/ingestor/models.py` and the Zod schema in `src/content.config.ts` must update in lockstep.

### Trust block field spec

```yaml
trust:
  site_trust: low | medium | high        # agent-classifiable from publisher signal
  document_type: marketing | sustainability-report | technical | regulatory | blog | research | news
  authority: low | medium | high          # hybrid: agent drafts, operator reviews
  independence: independent | first-party | trade-funded | regulatory | unknown
  coi_with_subject: true | false          # operator judgment
  coi_notes: string                       # free-text, required when coi_with_subject is true

publisher_group: string                   # e.g. "Gannett", "S&P Global", optional
```

**Range rationale:**
- `site_trust` and `authority`: categorical (low/medium/high) -- numeric precision is false precision for editorial judgment.
- `document_type` and `independence`: enums -- these are factual classifications, not ratings.
- `coi_with_subject`: boolean -- is or isn't -- with required notes for the non-trivial case.

**Enum-value style:** All enum values use hyphens to match the existing verdict enum convention (`mostly-true`, `not-applicable`). This applies to `document_type` (`sustainability-report`) and `independence` (`first-party`, `trade-funded`).

**Cross-field rule for `coi_notes`:** When `coi_with_subject: true`, `coi_notes` must be present and non-empty. This is a cross-field constraint. On the Pydantic side, implement as `model_validator(mode="after")` on the `TrustMetadata` nested model. On the Zod side, implement as `.superRefine()` on the trust object. Implementations that leave `coi_notes: Optional[str]` without the validator do not satisfy this requirement.

### Scoring ownership (per Q3 in `docs/pre-launch-questions.md`)

- `site_trust` → agent-classifiable from publisher URL and known signals.
- `document_type` → agent-classifiable from document metadata and content.
- `authority` → hybrid: agent drafts, operator reviews and adjusts.
- `independence` → agent-classifiable for first-party and regulatory; operator confirms trade-funded.
- `coi_with_subject` + `coi_notes` → operator judgment; agent cannot reliably detect financial relationships.

### Effect on analyst reasoning

COI and independence are verdict-sensitive and are used in analyst reasoning in v1. Site trust and authority are informational for v1 (display only; not fed to analyst).

Specifically: the analyst instructions will be updated to treat `first-party` independence sources as lower-weight for verdict-sensitive claims, and to flag when `coi_with_subject: true` sources are the primary evidence. This is the instruction-level counterpart to the schema-side COI field (see `research-quality-ideas.md` → "Source independence signals in analyst reasoning").

**Analyst decomposition interaction:** If `analyst-decomposition_stub.md` lands before Phase 2, COI and independence weighting moves into the per-source stance classifier (Step 2 of the decomposed pipeline), not the monolithic analyst instructions. The schema contract and behavioral intent are unchanged -- the wiring target shifts from `pipeline/analyst/instructions.md` to `pipeline/analyst/stance_classifier.py` (or equivalent). Phase 2 implementation must account for whichever path is active at that time.

Source freshness (`published_date`, already in schema) is also referenced in analyst instructions for claims with short `recheck_cadence_days`. No schema change required.

### Publisher entity question

**Decision: no new entity type for v1.** Publisher metadata is denormalized on the source record via the `trust:` block. To handle the white-label/syndication problem without requiring a new entity type, add an optional `research/publisher-groups.yaml` registry that maps domains to publisher group names. The ingest agent checks source URLs against this map and populates `publisher_group` on the source. This is exactly the approach described in `research-quality-ideas.md` → "White label domain classification by sector." The registry is optional infrastructure: sources without a match simply have no `publisher_group`.

v1.x can formalize this into a publisher entity type if operator needs arise. For v1, the YAML registry is sufficient.

### Site values vs. source trust signals

The site takes positions (climate change is real; unregulated AI is dangerous). Trust metadata must represent source relationships without the schema encoding which side is correct.

**Decision: option (a).** COI and independence are factual labels -- who funded it, who published it, what financial relationships exist. The schema records facts; the analyst uses them to contextualize. A fossil fuel industry report is labeled `trade-funded` because of who funded it, not because its energy consumption numbers are wrong. An AI company's own safety report is labeled `first-party` because the company published it, not because its claims are false.

The analyst is responsible for contextualizing these labels in the verdict narrative. The schema is not opinionated about which labels are disqualifying.

### Display

Render trust metadata on source detail pages (full panel) and inline on claim pages (compact badge cluster). COI is the highest-signal axis for skeptical readers; `coi_with_subject: true` surfaces most prominently. Expand-on-click for the full panel from the compact view.

Freshness (from `published_date`) is displayed alongside trust signals without requiring a new field.

## Phases

### Phase 1 — Schema (v1)

Add the `trust:` block and `publisher_group` field to `SourceFrontmatter` (Pydantic) and the Zod source schema. All fields optional for now -- Phase 5 lint will tighten this for newly-added sources once backfill is complete. No source files touched yet.

The Pydantic implementation requires a nested `TrustMetadata` model with the cross-field `model_validator` for `coi_notes`. The Zod implementation uses a nested `z.object({...}).optional()` with `.superRefine()` for the same rule.

**Exit criterion**: `pipeline/ingestor/models.py` and `src/content.config.ts` updated in lockstep; existing source files pass validation unchanged; schema diff reviewed by operator.

### Phase 2 — Analyst instructions (v1)

Update analyst instructions to reference `independence` and `coi_with_subject` when available. First-party sources are lower-weight for verdict-sensitive claims. COI-flagged sources trigger a note in the verdict narrative.

Also update analyst instructions to reference `published_date` relative to claim `recheck_cadence_days`.

**Risk note**: this phase changes verdict computation. Treating first-party sources as lower-weight will shift verdicts on existing claims. The exit criterion requires operator review of any verdict changes, not just a spot-check.

**Cost note**: "operator reviews any verdict changes" means re-running ~20 claims through the pipeline and triaging every verdict delta before Phase 3 backfill begins. Budget a full session for this step.

**Analyst decomposition interaction**: see "Effect on analyst reasoning" above. If decomposition is in flight, confirm which path is active before updating instructions.

**Exit criterion**: analyst instructions updated; all v1 claims re-run with COI-annotated sources; operator reviews any verdict changes before Phase 3 backfill begins.

### Phase 3 — Backfill launch sources (v1)

Manual scoring of the ~20-50 sources backing v1 launch claims. Document scoring rationale as you go -- this becomes reference material for the v1.x agent classifier.

**Exit criterion**: all sources cited in v1 claims have at minimum `independence` and `coi_with_subject` populated. `site_trust`, `document_type`, and `authority` are best-effort for this phase.

### Phase 4 — Display (v1)

Render trust metadata on source detail pages and inline on claim pages. COI badge is the most prominent. Freshness indicator where `published_date` is present.

**Exit criterion**: source detail page shows full trust panel; claim page shows compact badge cluster with COI flag visible.

### Phase 5 — Lint (v1)

`dr lint` warns on missing `independence` and `coi_with_subject` for newly-added sources. These two fields are the minimum viable trust signal.

**Grace period**: sources with `accessed_date` before 2026-05-01 are exempt from the lint warning (date-cutoff exemption). Sources added after that date must have both fields, or lint emits a warning. This is simpler than a per-source grace flag.

**Exit criterion**: `dr lint` command emits warnings for sources missing the two required-for-new fields; sources accessed before 2026-05-01 are exempt.

### Phase 6 — Agent classifier and full backfill (v1.x)

Ingestor agent drafts `site_trust`, `document_type`, `authority`, and `independence` classifications. Operator reviews before committing. Manual `coi_with_subject` remains operator-only.

Full backfill of all 146+ source files.

**Exit criterion**: all source files have `trust:` block populated; agent classifier validated on a held-out set before full run.

### Phase 7 — Publisher groups registry (v1.x)

Populate `research/publisher-groups.yaml` for sectors relevant to launch claims (energy, tech press, financial analysis). Ingest agent populates `publisher_group` on new sources. Analyst instructions updated to note same-group corroboration.

**Exit criterion**: registry covers major publishers in at least energy and tech press sectors; new source ingest populates `publisher_group` where match found.

### Phase 8 — Scoring with entity context (v1.x, dependency)

Pass parent company metadata to scorer to improve COI detection and source relevance for subsidiary products. This depends on entity enrichment work (see `research-quality-ideas.md` → "Scoring with entity context" and "Product → company relationship"). Do not take on here until entity enrichment is in place.

The scorer at that point will be `pipeline/researcher/scorer.py` (introduced by `researcher-decomposition.md`). Coordinate with that plan's state before implementing.

## Out of scope

- Trust metadata on entities (could come later, not a v1 concern).
- Aggregate trust scores at the claim level (derive on the fly if needed; do not store).
- Numeric (1-5) ratings for any axis -- categorical is sufficient and avoids false precision.

## Cross-references

- `docs/pre-launch-questions.md` Q3 (scoring ownership) -- answered above per-axis.
- `docs/pre-launch-questions.md` Q1 (reader test scope) -- resolved: trust metadata is part of the v1 reader experience via Phase 4.
- `docs/v1.0.0-roadmap.md` §13 "Result-quality validation" -- this plan is the structured source-quality signal answer to the gap identified there. Cross-reference both directions.
- `research-quality-ideas.md` → "Source independence signals in analyst reasoning" -- this plan is the schema side; Phase 2 is the instruction side.
- `research-quality-ideas.md` → "Source freshness as a quality signal" -- `published_date` already exists; Phase 2 adds the instruction reference.
- `research-quality-ideas.md` → "White label domain classification by sector" -- incorporated as Phase 7.
- `research-quality-ideas.md` → "Scoring with entity context" -- deferred to Phase 8 with entity enrichment dependency noted.
- `docs/plans/source-pdf-attachment.md` -- also extends `SourceFrontmatter` with a `pdfs:` block. Both plans are additive (different fields) and order-independent; either can land first without conflicting.
- `docs/plans/drafts/analyst-decomposition_stub.md` -- if analyst decomposition lands before Phase 2, COI/independence weighting in analyst instructions shifts to the per-source stance classifier. Schema and behavioral contract are unchanged; wiring target changes.
- `docs/plans/researcher-decomposition.md` -- introduces `pipeline/researcher/scorer.py`, which Phase 8 extends with entity context. Coordinate Phase 8 implementation with that plan's state.
- `docs/plans/audit-trail-extensions.md` -- also touches `src/content.config.ts` (the `auditSchema`, not the `sources` collection). Both changes are additive to different schemas and order-independent.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-24 | agent (claude-opus-4-7) | initial stub from triage | Four-axis structure scaffolded |
| 2026-05-01 | agent (claude-sonnet-4-6) | full rewrite | Resolved all open questions; added publisher-entity and site-values decisions; split into 8 phases with exit criteria; incorporated independence/freshness/white-label/entity-context ideas; defined mixed-range field spec and per-axis scoring ownership |
| 2026-05-01 | agent (claude-sonnet-4-6) | promotion review | Added cross-refs to source-pdf-attachment, analyst-decomposition stub, researcher-decomposition, audit-trail-extensions, and roadmap §13. Unified enum-value style to hyphens (sustainability-report, first-party, trade-funded). Flagged Pydantic model_validator / Zod superRefine requirement for coi_notes cross-field rule. Picked date-cutoff (2026-05-01) over grace-flag in Phase 5. Noted Phase 2 operational cost. Added analyst-decomposition forward-pointer in Phase 2. |
