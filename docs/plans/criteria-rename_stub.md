# Standards → Criteria rename

**Status**: Stub
**Last updated**: 2026-04-22

The decision has been made to do a full rename from "Standards" to "Criteria" across the site — display labels, URL route (`/criteria/`), schema collection name (`criteria`), and field name (`criteria_slug`). The research agent had recommended display-only to reduce risk, but the full rename was chosen. No external links need protection because DNS is currently unresolved.

---

## Scope

| File | Change |
|---|---|
| `src/layouts/Base.astro` | Nav href `/standards` → `/criteria`, label "Standards" → "Criteria" |
| `src/pages/standards/` | Rename directory → `src/pages/criteria/` |
| `src/pages/criteria/index.astro` | Title + h1 + one-liner |
| `src/pages/criteria/[slug].astro` | Title prefix update |
| `src/content.config.ts` | Collection `standards` → `criteria`, field `standard_slug` → `criteria_slug` |
| `research/claims/**/*.md` | `standard_slug:` → `criteria_slug:` backfill (84 files) |
| `src/lib/standards.ts` | Rename file, update imports |
| `src/pages/entities/[...slug].astro` | Update any `standard_slug` references |
| `src/pages/claims/[...slug].astro` | Update standard/criteria prefix display |
| FAQ | Update any "Standards" references |

Index page one-liner: *"Criteria are the questions we ask of every company and product. Each criterion links to the claims filed against it across all entities."*

---

## Implementation

TBD

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §1 |
