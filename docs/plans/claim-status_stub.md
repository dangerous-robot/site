# Claim status field

**Status**: Stub
**Last updated**: 2026-04-22

A `status` field needs to be added to the claims schema to support a draft/published/archived workflow. 

---

## Scope

**Schema change**: Add `status: z.enum(['draft', 'published', 'archived']).default('draft')` to the claims schema in `src/content.config.ts`. Also extend the verdict enum with `'not-applicable'` for claims where a criterion doesn't apply to an entity.

**Build behavior**: Public list pages and entity pages show only `status: published`. Direct URLs show all statuses with an appropriate notice.

**Pipeline integration**:
- `dr onboard` writes `status: draft`
- `dr review` promotes to `published` and writes the audit sidecar (Phase 4.8)

**Decision (2026-04-22)**: Zod default is `draft`. Pipeline writes `status: draft` explicitly on new claims. A backfill script must set `status: published` on all 84 existing claims **before** the schema lands in CI — if schema lands first, all 84 claims vanish from public pages. No CI enforcement of this ordering; treat as an atomic manual step.

---

## Implementation

TBD

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §2 |
