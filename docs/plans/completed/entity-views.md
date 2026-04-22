# Plan: Entity list & detail views (draft)

## Goal

Give the site a navigable information structure that exposes the research repo as a browse experience, with cross-links that serve the mission: **transparently connect verifiable facts to verdicts for claims across AI + environmental topics**.

## Terminology

- **Standard** — an entry in `research/templates.yaml`. Used in UI labels. Internal to this site; not an ISO/NIST-style external standard. A one-line disclaimer ("Standards are claim templates defined in this project") appears on `/standards` to head off confusion.
- **Topic** — a `category` value (8 enum members). Not an entity. Despite the entity schema allowing `type: topic` and a `research/entities/topics/` directory existing, topic *entities* are out of scope for v1 — the `/topics` route is a category view only.

## Scope decisions

1. Standards are a first-class browse axis sourced from `research/templates.yaml`.
2. `/topics` in v1 is a view over the 8 `category` enum values. No topic entity pages.
3. Each list page has filter + sort + search. Client-side only (no URL state, no server).
4. Layout width is per-page (`wide` vs `reading`), not global. See Layout.

## Non-goals

- No changes to `sources`, `entities` Zod schemas. One additive claim-schema change is committed: an optional `standard_slug` field. See "Schema change" below.
- No topic entity pages, no `topics[]` tag on claims.
- No pagination. No full-text body search (title/name search only).
- No verdict rollup dashboards, no recheck queue, no auth, no write UI.

## Data-quality notes (known issues to handle gracefully)

The plan's derivations meet live data that doesn't always cleanly match templates. Handle, don't mask:

- `research/claims/anthropic/existential-safety-score.md` — no matching standard slug. Expected behavior: not linked to any `/standards/[slug]` page; still listed on `/claims` and on the entity.
- `research/claims/ecosia/renewable-energy-hosting.md` — filed under a company entity, but the standard is typed `entity_type: product`. Resolved by the `standard_slug` field (see Schema change): the claim self-identifies its standard regardless of filing location.
- `research/claims/anthropic/publishes-sustainability-report.md` — `category: industry-analysis`, not `environmental-impact` as in the template. The category grouping on entity detail will place it under `industry-analysis`. This is a content fix, not a code fix.
- `research/claims/greenpt/` — entity file deleted but claims remain. Build should warn on orphaned claims; the `/claims` page still renders them, the entity cross-link renders a muted "entity not found" placeholder rather than a broken link.

Build-time logging surface: a single `logDerivationMisses(warnings)` call in one of the build hooks, output to stdout. No exceptions.

## Information architecture

| Route                          | Contents                                                               |
| ------------------------------ | ---------------------------------------------------------------------- |
| `/`                            | Count strip (N companies · M products · K claims · J standards) + entry cards per section |
| `/companies`                   | Entity list where `type=company` (card grid)                           |
| `/products`                    | Entity list where `type=product` (card grid)                           |
| `/claims`                      | All claims, filterable (single-column row list)                        |
| `/standards`                   | All entries from `templates.yaml` with coverage + gap counts           |
| `/standards/[slug]`            | Entity × verdict matrix for one standard                               |
| `/topics`                      | 8 category values with counts + sample verdicts                        |
| `/topics/[category]`           | Per-category cross-entity `VerdictDistribution` comparison + claim list grouped by entity |
| `/entities/[...slug]`          | (exists) enriched: claims grouped by category + standards-applied/gap  |
| `/claims/[...slug]`            | (exists) enriched: standard prefix above `<h1>` + inline source quotes |
| `/sources/[...slug]`           | (exists) enriched: reverse citations (claims using this source)        |

Nav (global, 5 items): **Companies · Products · Claims · Standards · Topics**. Sources moves to the footer alongside TreadLightly attribution and license (discovery target from within pages, not a primary entry point).

## Components (new, reusable)

Create under `src/components/`. Each component has a **scan-order contract** defining the visual anchor (leftmost / primary) and secondary fields. The CSS agent owns breakpoint values, typography, and color tokens.

| Component               | Scan order (left → right or primary → secondary)                                     | Used on |
| ----------------------- | ------------------------------------------------------------------------------------ | ------- |
| `EntityCard.astro`      | Entity name → `VerdictDistribution` strip → claim count                              | `/companies`, `/products`, home entry cards |
| `ClaimRow.astro`        | `VerdictBadge` (fixed-width leftmost) → title → entity → category → `as_of`          | `/claims`, `/topics/[category]` |
| `SourceRow.astro`       | Kind badge → publisher → title → year → citation count                               | Sources list in footer, source cross-reference blocks |
| `VerdictBadge.astro`    | Single badge; extracted from inline use                                              | Everywhere a verdict appears |
| `VerdictDistribution.astro` | Horizontal pill strip: counts per verdict for a claim set                        | Entity cards, `/topics/[category]` header, `/standards/[slug]` summary |
| `FilterBar.astro`       | Composes `SearchInput` + `FacetBar`; live count in header ("Showing N of M")         | All list pages |
| `SearchInput.astro`     | Text input; always visible on mobile                                                 | Composed by FilterBar |
| `FacetBar.astro`        | Facet controls; on narrow viewports collapses behind a "Filter (N)" disclosure       | Composed by FilterBar |
| `StandardsMatrix.astro` | Entity × verdict grid on wide; stacked accordion on narrow (one standard per row, expanded = entity verdicts as vertical list) | `/standards/[slug]` |
| `EmptyState.astro`      | Message slot; shared zero-results / no-content placeholder                           | All list pages, empty cross-link sections |
| `NotAssessedCell.astro` | Compact "Not assessed" indicator (inline context)                                    | Standards matrix cells, entity detail standards gap list |

Layout rule: card grid for entity list pages; single wide column for claim/source row lists. Never mix in the same page.

## Shared lib

- `src/lib/verdict.ts` — canonical sort order (`true > mostly-true > mixed > mostly-false > false > unverified`), human-readable label map (`"mostly-true" → "Mostly true"`), tooltip copy, color/kind maps.
- `src/lib/standards.ts` — `buildStandardsIndex(claims, standards) → Map<standardSlug, Map<entityId, ClaimEntry>>`. One pass over claims; drives standard detail, entity standards-applied section, and matrix.
- `src/lib/citations.ts` — `buildCitationIndex(claims) → Map<sourceId, ClaimEntry[]>`. Drives source detail reverse-citation list.
- `src/lib/research.ts` — `CATEGORY_LABELS: Record<Category, string>` (single source-of-truth for category human-readable names; used by Topics index, filter bar, entity detail grouping).

## Standards loading

Add a fourth Astro content collection backed by `research/templates.yaml`:

```ts
// src/content.config.ts (addition)
import { file } from 'astro/loaders';
import yaml from 'js-yaml';  // Astro bundles js-yaml but it is not in site deps — add explicitly

const standards = defineCollection({
  loader: file('research/templates.yaml', {
    parser: (text) => (yaml.load(text) as { templates: unknown[] }).templates,
  }),
  schema: z.object({
    slug: z.string(),
    text: z.string(),
    entity_type: z.enum(['company', 'product']),
    category: z.enum([/* same 8 values as claims */]),
    core: z.boolean().default(false),
    notes: z.string().optional(),
    vocabulary: z.record(z.array(z.string())).optional(),
  }),
});
```

Notes:
- The Astro `file` loader uses `rawItem.id ?? rawItem.slug` for entry IDs, so `entry.id === entry.data.slug`. The dynamic route `/standards/[slug].astro` matches on `entry.id`.
- Alternative simplification: restructure `templates.yaml` to a bare array at the root (drop the `templates:` wrapper). This lets the `file` loader parse natively without a custom parser and removes the `js-yaml` dependency add. Do this if touching the YAML file is acceptable to the data-content owner.
- Standards are not MDX; no `render()` needed.
- Add `js-yaml` to `package.json` if the custom parser is kept.

## Cross-links (the mission payoff)

This is where the plan earns the mission framing. Data wiring **and** UI affordance both matter.

### Data wiring (build time)

- `buildStandardsIndex` walks claims once, keyed by standard slug then entity id. Match rule: `claim.data.standard_slug` if present, otherwise fall back to filename stem (for claims written before the field was added; the pipeline should populate the field going forward).
- `buildCitationIndex` walks claims once, keyed by source id, with each entry storing the referring claim.
- Both log non-matches via `logDerivationMisses` at build time.

### UI affordances

- **Claim detail (`/claims/[...slug]`)**: when a matching standard exists, render a labeled prefix above the `<h1>`:
  ```
  <p class="standard-ref">Standard: <a href="/standards/[slug]">[standard text]</a></p>
  <h1>[claim title]</h1>
  ```
  Provenance is visible before the verdict. Do not bury it in the meta row.
- **Standard detail (`/standards/[slug]`)**: for each applicable entity (matching `entity_type`), show verdict if a claim exists, else `<NotAssessedCell />`. Entities that have a matching claim but mismatched entity_type (see data-quality note #2) appear in a separate "also referenced" section below the main matrix with a muted note.
- **Entity detail**: a two-column standards-applied section grouped by category. Left column: standard text. Right column: `<VerdictBadge />` if claim exists, `<NotAssessedCell />` otherwise.
- **Source detail (`/sources/[...slug]`)**: reverse-citation list appears **after key quotes, before the body content** — scannable at the top, not buried after prose.
- **Topic detail (`/topics/[category]`)**: `<VerdictDistribution />` at top compares all entities side-by-side (the differentiator vs. `/claims?category=X`), then claim list grouped by entity.
- **Home (`/`)**: count strip (N companies · M products · K claims · J standards) + entry cards per section (not a claim list).

## Layout

`src/layouts/Base.astro` accepts a `layout` prop:

- `"reading"` (default) — `.content` at narrow column, centered. Used by all `[slug]` detail pages.
- `"wide"` — `.content` expands to the wider list/matrix width. Used by all list and matrix pages.

Exact widths, breakpoints, and column-count rules live in the CSS token system (authored by the parallel CSS agent). This plan specifies structural pattern only:

- Entity list pages (`/companies`, `/products`): two-column card grid at wide viewports, single column on narrow.
- Claim/source list pages (`/claims`, etc.): single column at all widths.
- Standards matrix: grid on wide, stacked accordion on narrow (one standard per row, expanded = entity verdicts as a vertical list).
- `FilterBar`: `SearchInput` always visible; `FacetBar` collapses behind a "Filter (N)" disclosure on narrow.
- Nav: 5 items. If wrap produces two rows at narrowest widths, drop Topics from the nav bar and link it from home entry cards only.

Detail-page articles wrap their main body in `<article class="reading">` regardless of page layout, so prose stays readable even when the outer layout is wide.

## Filtering UX

Per list page, `<FilterBar>` composes:

- `<SearchInput>` — title/name substring.
- `<FacetBar>` — facets relevant to the list:
  - `/claims`: verdict, category, confidence
  - `/sources`: kind, year, publisher
  - `/companies`, `/products`: has-claims
  - `/standards`: category, core, coverage-gap
- Sort control: sort values sourced from `verdict.ts` (canonical order) or obvious per-page keys (updated, name, count).

Implementation: vanilla JS. Rows carry `data-verdict`, `data-category`, etc. On input change, toggle a `hidden` class. Live count in header. When filters yield zero rows, render `<EmptyState message="No claims match this filter" />` (or context-appropriate copy).

**Known UX gap (accepted for v1)**: filter state is not preserved across navigation. Going to a claim and returning resets filters. Deep-link URL sync is in follow-ups.

## File plan

**New:**

- `src/pages/companies/index.astro`
- `src/pages/products/index.astro`
- `src/pages/claims/index.astro`
- `src/pages/standards/index.astro`
- `src/pages/standards/[slug].astro`
- `src/pages/topics/index.astro`
- `src/pages/topics/[category].astro`
- `src/components/` — 11 files listed above
- `src/lib/verdict.ts`
- `src/lib/standards.ts`
- `src/lib/citations.ts`
- `src/lib/research.ts`

**Edited:**

- `src/content.config.ts` — add `standards` collection
- `src/layouts/Base.astro` — accept `layout` prop, update nav to 5 items, move Sources to footer
- `src/pages/index.astro` — reduce to count strip + entry cards
- `src/pages/entities/[...slug].astro` — group claims by category, add standards-applied two-column section
- `src/pages/claims/[...slug].astro` — add standard prefix above `<h1>`, inline source quotes
- `src/pages/sources/[...slug].astro` — add reverse-citation list after quotes, before body

**Dependencies:** add `js-yaml` to `package.json` (Astro bundles it but it is not a direct dep). Skip if the flat-YAML simplification (above) is adopted.

## Coordination with the parallel CSS work

A parallel agent owns the token system, theme (light/dark/high-contrast), font-size scaling, and a11y FAB. This plan does not specify colors, breakpoint pixel values, typography, or a11y-control behavior. Assume tokens for:

- `--content-max-width-reading` and `--content-max-width-wide` (exact values set by CSS agent)
- semantic color tokens for verdict badge backgrounds and foregrounds
- spacing / radius / border / shadow tokens

If CSS token names differ, rename on integration; do not block on the CSS work landing first. Structural HTML and component boundaries are stable independently of the token layer.

## Acceptance

- `inv build` succeeds; no Zod validation regressions.
- Every route in the IA table renders.
- From `/standards/publishes-sustainability-report`, a reader can see all companies + verdicts on that standard side by side (on wide) or as a stacked accordion (on narrow).
- From `/entities/companies/anthropic`, a reader can see which standards have been applied vs. not.
- Filter bar on `/claims` narrows results without a page reload.
- When no claims match active filters, `<EmptyState>` renders a context-appropriate message (list is not blank).
- Standard prefix appears above the `<h1>` on claim detail pages that match a standard.
- Build logs derivation misses for the known data-quality issues without throwing.

## Schema change

**Add `standard_slug: z.string().optional()` to the claim schema.**

A claim's link to its standard is declared in frontmatter rather than inferred from the filename. The stem heuristic stays as a fallback for older files, but the content pipeline should populate the field when it generates or regenerates a claim — that makes this a template change, not a migration, especially given the plan for ongoing claim-set iteration.

The field also decouples where a claim is filed (e.g., under a company entity) from which standard it instantiates (e.g., a product-typed standard), resolving the `ecosia/renewable-energy-hosting.md` class of mismatch.

Non-standard claims (e.g., `existential-safety-score.md`) omit the field.

## Out-of-scope follow-ups

- Topic entity pages and tag-based cross-linking.
- Verdict rollup dashboards, recheck-due queue.
- Client-side URL-synced filters (deep-linkable filter state).
- Full-text body search.
- Curated copy per category on `/topics/[category]`.

## Execution

Single senior web-dev agent. Order:

1. Add `standard_slug` to the claim schema in `src/content.config.ts`; backfill the field in existing claim files that correspond to a standard (auto-generatable from filename stem, human-reviewable diff).
2. Land `src/lib/*` (verdict, standards, citations, research) and the `standards` collection in `src/content.config.ts`.
3. Add shared components (`VerdictBadge`, `EmptyState`, `NotAssessedCell`, `VerdictDistribution` before the row/card components that use them).
4. Update `Base.astro` (layout prop, nav trim, Sources-to-footer).
5. Build list pages, then enrich detail pages.
6. Run `inv build` and fix any type / schema errors.
7. Report data-quality warnings surfaced and any subtask that hit unexpected complexity.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (cursory review) | completed-check | Added review history section; no unfinished work found |
