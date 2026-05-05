# Source quality

Reference for how the pipeline classifies sources, derives a per-claim verification level, and caps confidence on weakly-sourced claims.

This is the single source of truth for source-quality methodology. Plans, instructions, and lint rules cross-reference this file rather than restating its rules.

## What the verification scale measures

The `verification_level` field on each claim is derived from the diversity and kind of its source pool. **It measures source-type diversity, not claim corroboration.** "Independently verified" means independent-origin sources exist in the pool, not that independent analysis confirmed the underlying claim.

This is a bounded representation of what the system can determine without access to internal company systems. The cap-and-rationale machinery below is how we keep that boundedness honest in the verdict.

## Verification scale

Single claim-level field, set by the analyst. Five levels, ordered weakest to strongest:

| Level | Plain-language meaning (display copy) | Derivation |
|-------|----------------------------------------|------------|
| `claimed` | The entity asserts this; no formal documentation or independent source was found. | All `first-party` sources have `kind` in {blog, index, video, article}; no `independent` sources. |
| `self-reported` | The entity has published formal documentation; no independent source was found to corroborate. | At least one `first-party` source with `kind` in {report, documentation, dataset}; no `independent` sources. |
| `partially-verified` | A mix of entity documentation and independent sources. | Both `first-party` and `independent` sources present. |
| `independently-verified` | At least one independent source corroborates this claim. | At least one `independent` source; may include first-party. |
| `multiply-verified` | Multiple independent sources corroborate this claim. | Two or more `independent` sources. |

The plain-language column is what the claim page shows readers under each level. Editing those strings here means editing them on the site too.

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

- Plan that introduced this v1 scope: [`docs/plans/source-quality-robust-roadmap.md`](../plans/source-quality-robust-roadmap.md).
- Strategic critique that drove the rewrite: [`docs/plans/source-quality-agent-review.md`](../plans/source-quality-agent-review.md).
- Survey of all source-quality signals considered: [`docs/plans/source-quality_survey.md`](../plans/source-quality_survey.md).
- Canonical schema: `src/content.config.ts` (sources, claims).
- Analyst behavior: `pipeline/analyst/instructions.md`.
- Lint rules: `pipeline/linter/checks.py`.
