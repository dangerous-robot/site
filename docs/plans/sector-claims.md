# Sector-wide claims

**Status**: Partially done — schema change complete (`sector` added to entity `type` enum, commit 33c8ad3). No sector entity files or sector claims exist on disk as of 2026-05-01. The `/sectors/` route and any sector claims are post-v1. A separate agent is handling this plan.
**Last updated**: 2026-05-01

The entity `type` enum needs to be extended to include `'sector'` to support sector-wide claims. The immediate use case is moving the `existential-safety-score` claim from `anthropic/` to a new `sectors/ai-llm-producers/` entity, as that criterion applies across the AI/LLM industry rather than to a single company.

The term `sector` was chosen over `industry` after evaluation -- `sector` is more precise in common usage and avoids conflation with `category: 'industry-analysis'` already in the claims schema.

---

## Scope

**Schema changes**: two files, one decision deferred.

**Display**: Sector entities don't belong under `/companies` or `/products`. For v0.1.0, surface them via `/claims` and cross-links from company entity pages. A dedicated `/sectors/` route is a post-v0.1.0 item.

**Ordering constraint**: the schema change and entity file must land before the claim migration. A single atomic commit satisfies this; if split into two commits, schema + entity must come first.

---

## Implementation

### Step 1 -- Schema change

**File**: `src/content.config.ts`, entities collection, line 65.

Change:
```ts
type: z.enum(['company', 'product', 'topic']),
```
To:
```ts
type: z.enum(['company', 'product', 'topic', 'sector']),
```

No other schema file needs updating for v0.1.0. The `entity_type` enum in `research/templates.yaml` (standards/criteria collection) currently only covers `['company', 'product']`. Sector-level criteria templates are possible in the future, but no sector-specific template exists for v0.1.0 -- the `existential-safety-score` claim uses the `entity:` field to reference the sector entity and does not require a sector template. Leave `entity_type` unchanged for now; add `'sector'` when a sector-scoped template is created.

### Step 2 -- New entity file

Create the directory and file:

```
research/entities/sectors/ai-llm-producers.md
```

File content:

```md
---
name: AI/LLM Producers
type: sector
aliases:
  - AI companies
  - large language model providers
  - foundation model companies
description: Companies that develop and operate large language model products offered to consumers or businesses. Includes both API providers and consumer-facing product operators.
---
```

The five entity schema fields: `name` (required), `type` (required), `website` (omitted -- no authoritative URL for a sector), `aliases` (optional, included), `description` (required).

### Step 3 -- Create initial sector claim

~~Claim migration~~ -- the `existential-safety-score` claim that was originally scoped for migration was deleted in the 2026-04-26 prep pass and does not exist in `research/claims/anthropic/` or anywhere else. There is nothing to migrate.

Instead, create an initial claim at the correct path from the start:

```
research/claims/sectors/ai-llm-producers/has-signed-safety-commitments.md
```

Set `entity: sectors/ai-llm-producers` in the frontmatter. A demo claim was created on 2026-05-01; see the Demo implementation section below.

### Step 4 -- Cross-links (v0.1.0 scope)

No new route is needed for v0.1.0. Verify that:

- The sector entity appears in the `/claims` list once the entity file exists and a claim references it.
- Company entity pages that share scope with this claim (e.g., `anthropic`) can link to it via the existing cross-link pattern. No code change needed if the claim's `entity:` field is correct.

---

## Future work (post-v0.1.0)

**Total estimate**: ~3-6 hours, mostly frontend scaffolding. The data model already supports sectors.

### Dedicated `/sectors/` route (~2-4 hours)

- Create `src/pages/sectors/index.astro` -- sector list page, mirrors `src/pages/companies/index.astro`
- Create `src/pages/sectors/[...slug].astro` -- sector entity page, mirrors `src/pages/entities/[...slug].astro`
- Register routes in any navigation/sitemap config
- The Astro content collection and entity schema already support sector entities; this is purely a page scaffolding task
- Verdict distribution and claim list components already work generically -- wire up the sector entity slug

### Sector-scoped criteria templates (~1-2 hours)

- Add `entity_type: sector` entries to `research/templates.yaml` under `active_templates`
- Update `src/content.config.ts` (criteria collection, `entity_type` enum at the `z.enum(['company', 'product'])` line) to add `'sector'`
- One starter template: sector-level safety commitments or sustainability transparency claim
- Requires deciding which criteria make sense at sector level vs. company level before writing templates

---

## Demo implementation (2026-05-01)

Created to verify the UI renders sector entities correctly before building the `/sectors/` route.

- Entity: `research/entities/sectors/ai-llm-producers.md`
- Claim: `research/claims/sectors/ai-llm-producers/has-signed-safety-commitments.md`

Verdict: true, confidence: medium. Sources the UK Frontier AI Safety Commitments (2023) and FLI open letter co-signed by major AI/LLM producers. Confidence is medium because the commitments are voluntary with no enforcement mechanism.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §4 |
| 2026-04-22 | agent | expansion | Expanded from industry-claims_stub.md; renamed to sector-claims.md |
| 2026-05-01 | agent | status update | Updated status; rewrote Step 3 (migration moot); expanded Future work with estimates; added Demo implementation section |
