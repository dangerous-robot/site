# Industry entity type

**Status**: Stub
**Last updated**: 2026-04-22

The entity `type` enum needs to be extended to include `'industry'` to support industry-wide claims. The immediate use case is moving the `existential-safety-score` claim from `anthropic/` to a new `industries/ai-llm-producers/` entity, as that criterion applies across the industry rather than to a single company.

---

## Scope

**Schema change**: `type: z.enum(['company', 'product', 'topic', 'industry'])` in `src/content.config.ts`.

**New entity file**: Create `research/entities/industries/ai-llm-producers.md` (5 required fields).

**Claim migration**: Move `research/claims/anthropic/existential-safety-score.md` → `research/claims/industries/ai-llm-producers/existential-safety-score.md`.

**Display**: Industry entities don't belong under `/companies` or `/products`. For v0.1.0, surface them via `/claims` and cross-links from company pages. A dedicated `/industry` route is a future item.

---

## Implementation

TBD

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §4 |
