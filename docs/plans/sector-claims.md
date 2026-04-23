# Sector-wide claims

**Status**: Ready
**Last updated**: 2026-04-22

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

### Step 3 -- Claim migration

Create the directory:

```
research/claims/sectors/ai-llm-producers/
```

Move the file:

```
research/claims/anthropic/existential-safety-score.md
  → research/claims/sectors/ai-llm-producers/existential-safety-score.md
```

Update the `entity:` field in the frontmatter:

```yaml
# Before
entity: anthropic

# After
entity: sectors/ai-llm-producers
```

No other frontmatter fields change. The claim content, verdict, sources, and confidence remain as-is.

**Note**: As of 2026-04-22, the claim file does not exist in the repo yet -- it is listed in `v0.1.0-roadmap.md §3` as item 8 in the flagship claims, marked "needs entity move." Steps 1 and 2 unblock its creation at the correct path from the start. If the file is created before this plan lands, apply the migration above.

### Step 4 -- Cross-links (v0.1.0 scope)

No new route is needed for v0.1.0. Verify that:

- The sector entity appears in the `/claims` list once the entity file exists and a claim references it.
- Company entity pages that share scope with this claim (e.g., `anthropic`) can link to it via the existing cross-link pattern. No code change needed if the claim's `entity:` field is correct.

---

## Future work (post-v0.1.0)

- Dedicated `/sectors/` route and index page, mirroring `/companies/` and `/products/`.
- `entity_type: 'sector'` added to `research/templates.yaml` when sector-scoped criteria templates are defined.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §4 |
| 2026-04-22 | agent | expansion | Expanded from industry-claims_stub.md; renamed to sector-claims.md |
