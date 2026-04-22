# Claim status field

**Status**: Stub
**Last updated**: 2026-04-22

A `status` field needs to be added to the claims schema to support a draft/published/archived workflow. The backfill script must run before the schema change lands in CI, since 84 existing claims currently lack the field.

---

## Scope

**Schema change**: Add `status: z.enum(['draft', 'published', 'archived']).default('draft')` to the claims schema in `src/content.config.ts`. Also extend the verdict enum with `'not-applicable'` for claims where a criterion doesn't apply to an entity.

**Build behavior**: Public list pages and entity pages show only `status: published`. Direct URLs show all statuses with an appropriate notice.

**Pipeline integration**:
- `dr onboard` writes `status: draft`
- `dr review` promotes to `published` and writes the audit sidecar (Phase 4.8)

**Backfill**: 84 existing claim files need `status: published` inserted. A script is recommended over manual edit.

**Open decision**: Zod default `draft` (pipeline writes it explicitly, backfill script needed) vs. default `published` (simpler backfill, pipeline must write `draft` explicitly). Current recommendation is `draft` — safer production posture.

---

## Implementation

TBD

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §2 |
