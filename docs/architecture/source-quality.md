# Source quality

Reference for how the pipeline classifies sources, derives a per-claim verification level, and caps confidence on weakly-sourced claims.

This is the single source of truth for source-quality methodology. Plans, instructions, and lint rules cross-reference this file rather than restating its rules.

## What the verification scale measures

The `verification_level` field on each claim is derived from the diversity and kind of its source pool. **It measures source-type diversity, not claim corroboration.** "Independently verified" means independent-origin sources exist in the pool, not that independent analysis confirmed the underlying claim.

This is a bounded representation of what the system can determine without access to internal company systems. The cap-and-rationale machinery below is how we keep that boundedness honest in the verdict.

## Verification scale

Single claim-level field, set by the analyst. Each row's "Derivation" describes the *pool composition* required: each source in the pool has its own `independence` value (`first-party | independent | unknown`), and the level reflects how those values are distributed across the pool — never a property of any single source.

**Selection rule**: evaluate strongest to weakest; the first row whose derivation matches the pool wins. The rules overlap by design (a pool with two independent sources matches both `independently-verified` and `multiply-verified`); the cascade picks the strongest accurate label.

| Schema value (strongest first) | Display copy: **label** — gloss | Derivation |
|-------|----------------------------------------|------------|
| `multiply-verified` | **Cross-verified** — Multiple independent sources corroborate this claim. | The pool contains two or more `independent` sources. |
| `independently-verified` | **Independently verified** — At least one independent source corroborates this claim. | The pool contains at least one `independent` source. The pool may also contain `first-party` sources. |
| `partially-verified` | **Partially verified** — A mix of entity documentation and independent sources. | The pool contains at least one `first-party` source and at least one `independent` source. (Mechanically a subset of `independently-verified`; the cascade routes mixed pools to the stronger label, so this row is selected only when the analyst judges the independent source provides supplementary context rather than corroboration.) |
| `self-reported` | **Self-reported** — The entity has published formal documentation; no independent source was found to corroborate. | The pool has zero `independent` sources and at least one `first-party` source whose `kind` is in {report, documentation, dataset}. |
| `claimed` | **Claimed** — The entity asserts this; no formal documentation or independent source was found. | The pool has zero `independent` sources and every `first-party` source has `kind` in {blog, index, video, article}. |

The display-copy column is what the claim page shows readers under each level. Both the label and the gloss are mirrored from `src/lib/sourceQuality.ts`; editing those strings here means editing them on the site too.

### `claimed` vs `self-reported` boundary

The boundary turns on whether a `first-party` source contains formal documentation:

- `kind: report`, `documentation`, `dataset` → `self-reported` qualifies.
- `kind: blog`, `index`, `video` → `claimed` only.
- `kind: article` (first-party) → defaults to `claimed`. The analyst may upgrade to `self-reported` only when the article contains methodology, data, or signed commitments. Marketing framing and announcements are not enough.

## The `independence` field

Each source carries `independence: first-party | independent | unknown`. The ingestor proxies it from `source_type`:

- `source_type: primary` → `independence: first-party`
- `source_type: secondary` → `independence: independent`
- `source_type: tertiary` → `independence: unknown`

The proxy is a starting classification. It has a known failure mode (next section).

### `source_type` and `independence`: why both?

Two fields, two different questions:

- **`source_type`** (`primary | secondary | tertiary`, set by `pipeline/common/source_classification.py`): how close is this source to the originating authority? Older field; used by the scorer and surfaced in the audit trail.
- **`independence`** (`first-party | independent | unknown`): is this source authored by the entity (or by someone with structural COI to the entity) or not? v1 field; feeds the verification scale and confidence cap.

For most of the corpus the two coincide:

| `source_type` | `independence` | Typical case |
|---|---|---|
| `primary` | `first-party` | Company press release, the entity's own SEC 10-K |
| `secondary` | `independent` | Newspaper article, peer-reviewed journal |
| `tertiary` | `unknown` | Personal blog, foundation site, content aggregator |

That coincidence is why the ingestor mechanically derives `independence` from `source_type`. The mapping is a v1 proxy, not a definition — the two fields answer related but distinct questions and could disagree.

Edges where the proxy is imprecise:

- **Regulator filings about (not by) the entity** are `primary` by publisher rule (sec.gov, ftc.gov) and proxied to `first-party`. The document originates outside the entity but speaks with regulator authority — neither label fits cleanly. Today the proxy treats them as first-party; the analyst can correct per-claim if it matters.
- **Academic articles authored by entity employees** are `secondary` by publisher (arxiv, IEEE) and proxied to `independent`. They may functionally be entity-authored content disclosed through a third-party venue. Independent venue, not independent author.
- **Secondary sources that restate primary numbers without original analysis** — by far the most common edge — are addressed per-claim via `source_overrides` (see § Source overrides on claims). Other edges currently rely on the analyst flagging them in the narrative.

When the v1.x publisher-groups registry lands and the deferred `coi_with_subject` field is added, the proxy can be tightened. For v1, the analyst's restatement test is the only persistent correction mechanism.

### Known failure mode: independent restatement of primary disclosures

The proxy's biggest gap is on the most common real case: a secondary source (a journalist, an analyst) restating a number from a company's own press release or report. The source originates outside the entity, so the proxy classifies it `independent`, but it adds no independent corroboration: the only place the number actually exists is the entity's own document.

**The analyst applies a restatement test on each `independent` source**: does this source conduct original analysis of the claim, or does it restate a number the entity itself published? If it only restates, the analyst overrides `independence` to `first-party` for that source's contribution to this claim's `verification_level`, and records the override on the claim.

The override is per-claim, not on the source file itself. A source may add genuine independent analysis on one claim and restate primary disclosures on another. See [Source overrides on claims](#source-overrides-on-claims).

## Confidence cap

When `verification_level` is `claimed` or `self-reported`, `confidence` is capped at `low`. The cap fires regardless of how comprehensive or auditable the entity's self-report appears. Cap quality is communicated through the rationale, not through cap level.

### Rationale templates

When the cap fires, the analyst writes a one-sentence rationale matching one of these templates and puts it in the `cap_rationale` field on the claim. The exact words are not required; the structure and honesty are.

- "Confidence is capped at low — all sources originate from entity documentation; no independent source was found that conducts original analysis of this claim."
- "Confidence is capped at low — the independent sources found restate entity-published numbers without conducting original analysis; no source independently confirms this claim."
- "Confidence is capped at low — sources are informal entity communications (blog posts, announcements); no formal documentation or independent source was found."

The display layer surfaces the rationale beneath the verdict, in plain text.

### Editorial policy on absence of evidence

When the evidentiary basis is "no contradicting evidence found" rather than corroborating evidence (no breach disclosures, no regulatory findings, no public lawsuits), the analyst notes this explicitly: "No contradicting evidence was found; this does not constitute independent confirmation."

Claims where absence of evidence is the primary basis should use `verdict: unverified` rather than forcing a positive or negative verdict.

### Lint enforcement

`dr lint` issues a warning when `confidence` is `medium` or `high` and `verification_level` is `claimed` or `self-reported`. The warning surfaces drift; the analyst is responsible for the cap at write time.

## Source overrides on claims

A claim may carry an optional `source_overrides:` list to record per-claim overrides of source-level fields. Today this exists only for the restatement failure mode above:

```yaml
source_overrides:
  - source: 2025/some-secondary-restatement
    independence: first-party
    reason: restates Anthropic RSP without original analysis
```

The analyst sets these. They have two purposes:

1. They make the analyst's per-claim judgment legible — a reader can see why a source the file says is `independent` was treated as `first-party` for this claim.
2. They are honest in the data: `verification_level` derivation uses the overridden values, not the raw source-file values.

The source file's `independence` is unchanged; the override is scoped to the one claim that detected the restatement.

## Publisher registry

Bigger registry-driven trust signals (`site_trust`, `publisher_group`) are deferred to v1.x. The reasoning:

- `site_trust` would map domains to a trust band (high / medium / low). Without a registry it would be inconsistent or wholly absent on most sources.
- `publisher_group` would identify ownership clusters (so two outlets owned by the same conglomerate don't appear as two independent corroborations).

When the registry lands, `site_trust: unknown` will be the default for any domain not in it. **`unknown` is not a negative signal** — it means "this publisher is not yet tracked," not "this publisher is untrusted." The display layer must not penalize unknown publishers.

Until then, low-trust sources are handled by the blocklist (PR wire services, content farms) for hard drops.

## What the system cannot do

Some claim categories are inherently unverifiable without insider access — energy contracts, training data practices, internal safety protocols. Independent sources covering these claims often restate the entity's own numbers. The verification scale will sometimes show `independently-verified` or `multiply-verified` for such claims even though every source ultimately traces to the entity's own document. The analyst's restatement test (above) is the only mitigation.

When the analyst recognizes that the entire pool is restatement, the right move is the cap rationale plus a narrative caveat, or `verdict: unverified` if the claim cannot be supported even at low confidence.

## Cross-references

- Plan that introduced this v1 scope: [`docs/plans/completed/source-quality-robust-roadmap_completed.md`](../plans/completed/source-quality-robust-roadmap_completed.md).
- Strategic critique that drove the rewrite: [`docs/plans/source-quality-agent-review.md`](../plans/source-quality-agent-review.md).
- Survey of all source-quality signals considered: [`docs/plans/source-quality_survey.md`](../plans/source-quality_survey.md).
- Canonical schema: `src/content.config.ts` (sources, claims).
- Analyst behavior: `pipeline/analyst/instructions.md`.
- Lint rules: `pipeline/linter/checks.py`.
