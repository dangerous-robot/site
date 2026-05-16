# Research Outputs Improvement Plan

## Goals

Three goals, restated tightly:

1. **Consistency with research standards**, so that claims, sources, and audits resemble outputs from established fact-checking and provenance traditions enough that an outside reader recognizes them.
2. **Usability as evidence**, so that a claim plus its sidecar is a citeable starting point for someone else's research, not just a node in our pipeline.
3. **Improveability with audit trail**, so that new inputs and rechecks update claims while leaving the prior state legible.

These goals depend on the structural direction in `docs/architecture/vision-state-machine.md`. That document defines the **substrate**: named states, named transitions with pre/post-conditions, an append-only transition log per claim, and build-time validation as the enforcement layer. This document defines the **surface** that readers and citers see: which transitions are named, what verdicts and confidence levels mean, what gets exported, and what an outside researcher reads when they land on a published claim. Where this plan needs a substrate piece, it points to the vision rather than re-specifying it.

## Consistency with research standards

A survey of external standards worth considering, with recommendations.

**Schema.org `ClaimReview`** is the de facto standard for machine-readable fact-checks. It defines a verdict (`reviewRating`), the claim being reviewed (`itemReviewed.Claim`), the reviewer, and the date. Google and Bing surface ClaimReview in search; IFCN signatories publish it. **Recommendation: align.** Our claim frontmatter already maps to ClaimReview with light renaming; a JSON-LD export per claim is achievable without changing the markdown source of truth. This is the single highest-leverage standards move.

**W3C PROV-O** is the W3C provenance vocabulary: entities, activities, agents, and the relations among them (`wasGeneratedBy`, `wasDerivedFrom`, `wasAttributedTo`). **Recommendation: note as influence, do not adopt the vocabulary.** PROV-O is more general than we need and adopting its terms in YAML would obscure rather than clarify. We borrow the discipline (every artifact has a generating activity and an attributable agent) without the namespace.

**IFCN verification methodology**, from the International Fact-Checking Network's code of principles, requires nonpartisanship, source transparency, methodology transparency, open corrections, and funding transparency. **Recommendation: note as discipline, not as code-level alignment.** Our source-independence labels and confidence-capping on self-reported claims already reflect IFCN-style transparency. A public methodology page is the appropriate vehicle, not schema changes.

**FAIR data principles** (Findable, Accessible, Interoperable, Reusable) come from the research-data movement. **Recommendation: align in spirit.** Stable IDs serve Findable; markdown plus JSON-LD serves Accessible and Interoperable; clear licensing serves Reusable. Tracking FAIR explicitly as a checklist is overkill; treating it as a quality lens for the rubric is right-sized.

Net: actually align with **ClaimReview** (export) and **FAIR** (lens). Note PROV-O and IFCN; do not adopt their vocabularies into the YAML.

## Usability as evidence

For a claim plus sidecar to be a citeable starting point for outside readers, the following must hold:

- **Stable IDs.** Claim IDs do not change when verdicts change. Supersession is a new state, not a new ID, except where a claim is genuinely redefined (a different proposition).
- **Clear verdict semantics.** The verdict vocabulary is small, defined, and documented in one place. The verification-level taxonomy (multiply-verified through claimed) names the evidentiary basis distinct from the verdict.
- **Machine-readable export.** Each published claim has a ClaimReview JSON-LD representation accessible by URL. This is what makes "consistent with research standards" concrete rather than aspirational.
- **Source independence labels.** Already in place (`first-party | independent | unknown`); surface them in the export so citers see them.
- **Confidence rubric.** A single document defining what `confidence` levels mean, what evidence supports each, and how self-reported claims are capped. Today this is partly implicit in agent prompts and partly in source independence; it deserves a unified statement.

## Improveability with audit trail

New inputs (a fresh source, a counter-claim, a corrected fact) should improve claims without erasing the prior state. Each of these is a named transition over the substrate the vision describes; the mechanics here are how those transitions surface to readers:

- **Recheck as a transition.** A recheck is a named transition (`recheck`) that appends to the per-claim transition log with cause, inputs read, outputs written, and resulting state. "Append-only recheck history" is the reader-facing view of that log, filtered to recheck transitions. The log itself is Phase 2/3 of `docs/plans/audit-trail-extensions.md` and is the load-bearing piece.
- **Supersession as a named transition.** A verdict change is the `supersede` transition, reserved for operator approval (one of the vision's open-loop decision points). Pre-condition: a prior published verdict exists. Post-condition: the new verdict is recorded with prior verdict, new verdict, trigger, and approving operator; the claim ID is unchanged. The published page shows the current verdict; the transition log shows the chain.
- **Schema migration log.** Schema changes are themselves transitions, recorded in a migration log with date, rationale, and affected fields. Claims persisted under earlier schemas continue to validate or are explicitly migrated; readers can see which schema version produced which fields.
- **Agent and inputs recorded per transition.** Every transition records the agent (model or human) and the inputs it consumed. This is the vision's transition record; this plan does not re-specify it. PROV-O is the discipline behind the field set, not a vocabulary we adopt.

## Near-term moves

Ordered by dependency. The vision recommends building the transition substrate before surface work that reads against it; substrate items lead.

1. **Audit Trail Phase 2 and 3** (`docs/plans/audit-trail-extensions.md`): extended sidecar fields and the append-only transition log. This is the substrate everything below reads.
2. **Confidence and verdict rubric document**, consolidating today's implicit rules into one citeable page. Locks the verdict vocabulary and rating scale that the ClaimReview export needs.
3. **ClaimReview JSON-LD export**, per-claim files generated from frontmatter at build time, plus a sitemap listing them. Build fails if any published claim does not produce a valid `ClaimReview` document; this is the export's build-time invariant in the vision's principle 4 sense. Aggregated feed deferred until a consumer asks.
4. **Schema migration log** as a root `CHANGELOG.md`, started with the v1 audit schema as its first entry. Each entry records a schema-level transition.
5. **Staleness build-time gate**, the first CI invariant on the transition log: claims past `recheck_cadence_days` fail or warn at build. Listed in the vision's near-term direction; landing it here closes the loop with item 1.

Explicitly deferred:

- **Verification-level field** (`multiply-verified | independently-verified | partially-verified | self-reported | claimed`). The vision lists verification-level taxonomy in its near-term direction; this plan defers the field until the ClaimReview export has forced decisions about verdict vocabulary and rating scale. Adding it now is not a standards-alignment move: Schema.org `ClaimReview` standardizes the verdict (`reviewRating`), not evidence strength, and no external standard prescribes a verification-level taxonomy. Premature commitment risks shipping a field name that collides with the verdict scale and requires migration. The taxonomy can be named and used in the rubric document before becoming a frontmatter field.
- **Aggregated ClaimReview feed.** Per-claim JSON-LD plus a sitemap is enough until a downstream consumer asks for a single feed.
- **JSON-LD for entities and sources.** ClaimReview is the highest-leverage export; entity and source exports wait for a consumer.

## Trade-offs and what this is not

This plan is the reader-facing surface of the state machine, not a parallel substrate. It does not introduce a new audit format, a new lifecycle, or a workflow engine. The ClaimReview export is a build-time emitter that reads state; it is not an orchestrated step in the pipeline. The rubric document is editorial, not executable. Costs: one more build-time invariant, one more document to keep current as the verdict vocabulary evolves. Benefits: an outside researcher landing on a published claim sees a machine-readable verdict, a defined confidence level, and a transition log they can follow.

## Review history

| Date       | Reviewer                | Notes         |
|------------|-------------------------|---------------|
| 2026-05-16 | Claude (planning agent) | Initial draft |
| 2026-05-16 | Claude (planning agent) | Aligned to vision-state-machine.md: substrate/surface split, recheck and supersession framed as named transitions, ClaimReview export gains build-time invariant, near-term moves reordered by dependency, verification-level deferral reconciled with vision's near-term list |
