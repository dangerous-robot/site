# Standards -> Criteria rename

**Status**: Ready
**Last updated**: 2026-04-22

The decision has been made to do a full rename from "Standards" to "Criteria" across the site -- display labels, URL route (`/criteria/`), schema collection name (`criteria`), and field name (`criteria_slug`). The research agent had recommended display-only to reduce risk, but the full rename was chosen. No external links need protection because DNS is currently unresolved.

---

## Scope

| File | Change |
|---|---|
| `src/layouts/Base.astro` | Nav href `/standards` -> `/criteria`, label "Standards" -> "Criteria" |
| `src/pages/index.astro` | Collection call, count strip label, section card label and href |
| `src/pages/standards/` | Rename directory -> `src/pages/criteria/` |
| `src/pages/criteria/index.astro` | Title, h1, disclaimer, placeholder text, CSS class names, hrefs |
| `src/pages/criteria/[slug].astro` | Imports, collection call, variable names, hrefs, prose label |
| `src/content.config.ts` | Collection `standards` -> `criteria`, field `standard_slug` -> `criteria_slug` |
| `src/lib/standards.ts` | Rename file -> `src/lib/criteria.ts`; update interface, variable names, log prefix, JSDoc |
| `src/lib/citations.ts` | Import path from `./standards` -> `./criteria`; field `standard_slug` -> `criteria_slug` |
| `src/components/StandardsMatrix.astro` | Rename file -> `CriteriaMatrix.astro`; update root div class attribute only |
| `src/pages/entities/[...slug].astro` | Import path, collection call, variable names, section heading, prose, hrefs, CSS class names |
| `src/pages/claims/[...slug].astro` | Collection call, variable names, label text, href, CSS class names (10 occurrences) |
| `src/components/AccessibilityIcon.astro` | No change needed (line 9 references "Web Accessibility Initiative standard symbol" -- W3C icon meaning, unrelated to this collection) |
| `src/pages/faq/index.astro` | No change needed (no Standards collection references in this file) |
| `research/claims/**/*.md` | No backfill needed today (see field rename step) |
| `research/templates.yaml` | No change needed (see templates step) |

**`std` variable names and `std-*` CSS class names**: These appear throughout as loop variables (`std`, `std.id`, `std.data.*`) and CSS class names (`.std-text`, `.std-meta`, `.std-header`, `.std-category`, `.std-notes`, `.std-row`, `.std-rows`, `.std-verdict`, `.std-category-group`, `.std-category-heading`). They are neutral abbreviations not tied to the word "standard" and do not appear in any URL or user-visible label. Leave all of them unchanged.

Index page one-liner: *"Criteria are the questions we ask of every company and product. Each criterion links to the claims filed against it across all entities."*

---

## Implementation

All steps in this plan should land in a single atomic commit. The nav link, page route, and schema collection name are tightly coupled: a build between any two of them will fail. If you must split the work across commits, do not push intermediary states to a deployed branch.

### Schema: rename collection and field

**File**: `src/content.config.ts`

Change the `claims` collection field (line 53):

```ts
// Before
standard_slug: z.string().optional(),

// After
criteria_slug: z.string().optional(),
```

Change the collection declaration (line 72):

```ts
// Before
const standards = defineCollection({

// After
const criteria = defineCollection({
```

Change the export (line 99):

```ts
// Before
export const collections = { sources, claims, entities, standards };

// After
export const collections = { sources, claims, entities, criteria };
```

No other fields in this file change. The `entity_type` field inside the collection schema refers to entity kinds (`company`, `product`) -- it is not related to this rename.

### Rename the utility library

Rename the file:

```
src/lib/standards.ts -> src/lib/criteria.ts
```

Inside `src/lib/criteria.ts`, apply these 7 changes:

```ts
// Line 10: interface field
// Before
standard_slug?: string;
// After
criteria_slug?: string;
```

```ts
// Line 13: interface name
// Before
export interface StandardsMiss {
// After
export interface CriteriaMiss {
```

```ts
// Line 18: JSDoc comment
// Before
/** Build a map: standardSlug -> entityId -> ClaimEntry[] */
// After
/** Build a map: criteriaSlug -> entityId -> ClaimEntry[] */
```

```ts
// Line 19: function name
// Before
export function buildStandardsIndex(
// After
export function buildCriteriaIndex(
```

```ts
// Lines 25-31: internal variable names (4 occurrences of standardSlug)
// Before
const standardSlug =
  claim.data.standard_slug ?? stemFromId(claim.id);
if (!standardSlug) continue;
if (!index.has(standardSlug)) index.set(standardSlug, new Map());
const byEntity = index.get(standardSlug)!;
// After
const criteriaSlug =
  claim.data.criteria_slug ?? stemFromId(claim.id);
if (!criteriaSlug) continue;
if (!index.has(criteriaSlug)) index.set(criteriaSlug, new Map());
const byEntity = index.get(criteriaSlug)!;
```

```ts
// Line 40: field in ClaimEntry push
// Before
standard_slug: claim.data.standard_slug,
// After
criteria_slug: claim.data.criteria_slug,
```

```ts
// Line 54: log prefix in logDerivationMisses
// Before
console.warn(`[standards] ${miss.claimId}: ${miss.reason}`);
// After
console.warn(`[criteria] ${miss.claimId}: ${miss.reason}`);
```

### Update citations.ts

**File**: `src/lib/citations.ts`

Two changes:

```ts
// Line 2: import path
// Before
import type { ClaimEntry } from './standards';
// After
import type { ClaimEntry } from './criteria';
```

```ts
// Line 21: field in ClaimEntry push
// Before
standard_slug: claim.data.standard_slug,
// After
criteria_slug: claim.data.criteria_slug,
```

### Rename the component

Rename the file:

```
src/components/StandardsMatrix.astro -> src/components/CriteriaMatrix.astro
```

Inside `src/components/CriteriaMatrix.astro`, change only the class attribute on the root div (line 18). The style block uses `.matrix-table`, `.matrix-item`, `.matrix-summary`, and similar names -- no CSS rule references `.standards-matrix` and no style changes are needed.

```html
<!-- Before -->
<div class="standards-matrix">

<!-- After -->
<div class="criteria-matrix">
```

### Rename the page directory and update index page

Rename the directory:

```
src/pages/standards/ -> src/pages/criteria/
```

**File**: `src/pages/criteria/index.astro` (was `standards/index.astro`)

Update the import (line 4):

```ts
// Before
import { buildStandardsIndex } from '../../lib/standards';
// After
import { buildCriteriaIndex } from '../../lib/criteria';
```

Update the collection call and index variable (lines 9-12). The loop variable `std` and field accessors `std.id`, `std.data.*` are left unchanged per the `std` naming decision.

```ts
// Before
const standards = await getCollection('standards');
const standardsIndex = buildStandardsIndex(claims);
const rows = standards.map(std => {
  const byEntity = standardsIndex.get(std.id) ?? new Map();
// After
const criteria = await getCollection('criteria');
const criteriaIndex = buildCriteriaIndex(claims);
const rows = criteria.map(std => {
  const byEntity = criteriaIndex.get(std.id) ?? new Map();
```

Update the `<Base>` title (line 40), remove the old disclaimer (line 41), update `<h1>` (line 42). The old disclaimer warns about ISO/NIST confusion -- "criteria" does not carry that baggage, so replace it with the approved one-liner:

```astro
<!-- Before -->
<Base title="Standards" layout="wide">
  <p class="disclaimer">Standards are claim templates defined in this project — not ISO/NIST-style external standards.</p>
  <h1>Standards</h1>

<!-- After -->
<Base title="Criteria" layout="wide">
  <h1>Criteria</h1>
  <p class="disclaimer">Criteria are the questions we ask of every company and product. Each criterion links to the claims filed against it across all entities.</p>
```

Update search placeholder (line 45) and empty state message (line 68):

```astro
<!-- Before -->
searchPlaceholder="Search standards…"
...
<EmptyState message="No standards match this filter." />
<!-- After -->
searchPlaceholder="Search criteria…"
...
<EmptyState message="No criteria match this filter." />
```

Update the href in each row link (line 52):

```astro
<!-- Before -->
href={`/standards/${row.slug}`}
<!-- After -->
href={`/criteria/${row.slug}`}
```

Update CSS class names in the `<style>` block (lines 73-80) and the corresponding JSX class attributes (lines 49 and 53). The `.std-text` and `.std-meta` classes are left unchanged per the `std` naming decision.

```css
/* Before */
.standards-list { ... }
.standard-row { ... }
.standard-row:hover { ... }
/* After */
.criteria-list { ... }
.criteria-row { ... }
.criteria-row:hover { ... }
```

Corresponding JSX class attributes:

```astro
<!-- Before -->
<div class="standards-list">
  <a ... class="standard-row" ...>
<!-- After -->
<div class="criteria-list">
  <a ... class="criteria-row" ...>
```

### Update the detail page

**File**: `src/pages/criteria/[slug].astro` (was `standards/[slug].astro`)

Update 3 import lines (lines 4-6):

```ts
// Before
import { buildStandardsIndex, logDerivationMisses } from '../../lib/standards';
import type { StandardsMiss } from '../../lib/standards';
import StandardsMatrix from '../../components/StandardsMatrix.astro';
// After
import { buildCriteriaIndex, logDerivationMisses } from '../../lib/criteria';
import type { CriteriaMiss } from '../../lib/criteria';
import CriteriaMatrix from '../../components/CriteriaMatrix.astro';
```

Update the `getStaticPaths` collection call (line 9). The loop variable `std` and prop name `std` are left unchanged.

```ts
// Before
const standards = await getCollection('standards');
return standards.map(std => ({ params: { slug: std.id }, props: { std } }));
// After
const criteria = await getCollection('criteria');
return criteria.map(std => ({ params: { slug: std.id }, props: { std } }));
```

Update the body collection call and index (lines 17-18):

```ts
// Before
const standardsIndex = buildStandardsIndex(claims);
const byEntity = standardsIndex.get(std.id) ?? new Map();
// After
const criteriaIndex = buildCriteriaIndex(claims);
const byEntity = criteriaIndex.get(std.id) ?? new Map();
```

Update the misses array type (line 20):

```ts
// Before
const misses: StandardsMiss[] = [];
// After
const misses: CriteriaMiss[] = [];
```

Update the comment on line 22:

```ts
// Before
// All entities matching this standard's entity_type
// After
// All entities matching this criterion's entity_type
```

Update component references -- 2 occurrences (lines 66 and 72):

```astro
<!-- Before -->
<StandardsMatrix rows={rows} />
...
<StandardsMatrix rows={alsoReferenced} />
<!-- After -->
<CriteriaMatrix rows={rows} />
...
<CriteriaMatrix rows={alsoReferenced} />
```

Update the "also referenced" prose (line 71):

```astro
<!-- Before -->
<p class="muted">These entities have claims referencing this standard but don't match its entity type.</p>
<!-- After -->
<p class="muted">These entities have claims referencing this criterion but don't match its entity type.</p>
```

The CSS classes `.std-header`, `.std-category`, `.std-notes` are left unchanged per the `std` naming decision.

### Update nav and home page

**File**: `src/layouts/Base.astro`, one change (line 63):

```html
<!-- Before -->
<li><a href="/standards">Standards</a></li>
<!-- After -->
<li><a href="/criteria">Criteria</a></li>
```

**File**: `src/pages/index.astro`

Update the collection call, count strip text, and section card (3 changes):

```ts
// Before
const standards = await getCollection('standards');
// After
const criteria = await getCollection('criteria');
```

```astro
<!-- Before -->
<span><strong>{standards.length}</strong> standards</span>
<a href="/standards" class="section-card">
  <strong>Standards</strong>
  <span>{standards.length} templates</span>
</a>
<!-- After -->
<span><strong>{criteria.length}</strong> criteria</span>
<a href="/criteria" class="section-card">
  <strong>Criteria</strong>
  <span>{criteria.length} templates</span>
</a>
```

### Update entities detail page

**File**: `src/pages/entities/[...slug].astro`

Update the import (line 4):

```ts
// Before
import { buildStandardsIndex } from "../../lib/standards";
// After
import { buildCriteriaIndex } from "../../lib/criteria";
```

Update comment (line 34), collection call, index variable, filter comment and variable, group comment and map variable, derived sort variable (lines 34-50). The loop variable `std` in `for (const std of ...)` and inner `.map(std =>` are left unchanged per the `std` naming decision.

```ts
// Before
// Standards-applied section
const standards = await getCollection("standards");
const standardsIndex = buildStandardsIndex(allClaims);
// Filter standards matching this entity's type
const applicableStandards = standards.filter(...)
// Group applicable standards by category
const stdsByCategory = new Map<string, typeof applicableStandards>();
for (const std of applicableStandards) {
  ...
  stdsByCategory.get(cat)!.push(std);
}
const stdCategoriesSorted = [...stdsByCategory.keys()].sort();

// After
// Criteria-applied section
const criteria = await getCollection("criteria");
const criteriaIndex = buildCriteriaIndex(allClaims);
// Filter criteria matching this entity's type
const applicableCriteria = criteria.filter(...)
// Group applicable criteria by category
const critByCategory = new Map<string, typeof applicableCriteria>();
for (const std of applicableCriteria) {
  ...
  critByCategory.get(cat)!.push(std);
}
const critCategoriesSorted = [...critByCategory.keys()].sort();
```

Also update `byEntity` in the inner map:

```ts
// Before
const byEntity = standardsIndex.get(std.id) ?? new Map();
// After
const byEntity = criteriaIndex.get(std.id) ?? new Map();
```

Update the section guard and template (rename 3 items; leave 7 `std-*` CSS classes unchanged):

```astro
<!-- Before -->
{applicableStandards.length > 0 && (
  <section class="standards-applied">
    <h2>Standards</h2>
    <p class="standards-note">...</p>
    {stdCategoriesSorted.map(cat => (
      ...
      {stdsByCategory.get(cat)!.map(std => {
        ...
        <a href={`/standards/${std.id}`} ...>
<!-- After -->
{applicableCriteria.length > 0 && (
  <section class="criteria-applied">
    <h2>Criteria</h2>
    <p class="criteria-note">...</p>
    {critCategoriesSorted.map(cat => (
      ...
      {critByCategory.get(cat)!.map(std => {
        ...
        <a href={`/criteria/${std.id}`} ...>
```

Update 3 CSS rules in the `<style>` block. The 7 `std-*` CSS rules are unchanged.

```css
/* Before */
/* Standards applied section */
.standards-applied { ... }
.standards-applied h2 { ... }
.standards-note { ... }
/* After */
/* Criteria applied section */
.criteria-applied { ... }
.criteria-applied h2 { ... }
.criteria-note { ... }
```

### Update claims detail page

**File**: `src/pages/claims/[...slug].astro`

10 occurrences to update:

```ts
// Line 16: comment
// Before: // Resolve matching standard
// After:  // Resolve matching criterion

// Line 17: collection call
// Before: const standards = await getCollection("standards");
// After:  const criteria = await getCollection("criteria");

// Line 19: variable and field
// Before: const standardSlug = claim.data.standard_slug ?? stem;
// After:  const criteriaSlug = claim.data.criteria_slug ?? stem;

// Line 20: variable
// Before: const matchedStandard = standards.find(s => s.id === standardSlug);
// After:  const matchedCriteria = criteria.find(s => s.id === criteriaSlug);
```

```astro
<!-- Lines 51-53: JSX -->
<!-- Before -->
{matchedStandard && (
  <p class="standard-ref">
    Standard: <a href={`/standards/${matchedStandard.id}`}>{matchedStandard.data.text}</a>
<!-- After -->
{matchedCriteria && (
  <p class="criterion-ref">
    Criterion: <a href={`/criteria/${matchedCriteria.id}`}>{matchedCriteria.data.text}</a>
```

```css
/* Lines 118, 126, 131: 3 CSS rules */
/* Before */
.standard-ref { ... }
.standard-ref a { ... }
.standard-ref a:hover { ... }
/* After */
.criterion-ref { ... }
.criterion-ref a { ... }
.criterion-ref a:hover { ... }
```

### Claim frontmatter: field rename

The `criteria_slug` field (formerly `standard_slug`) is optional and currently absent from all claim files -- the code derives the slug from the filename stem when the field is missing. No backfill is required.

Before closing this rename, verify:

```bash
grep -r "standard_slug:" research/claims/
```

If this returns any hits, rename the field in those files from `standard_slug:` to `criteria_slug:`. If no hits (expected), no edits are needed. Document in the commit message that the field was verified absent.

### research/templates.yaml

No change needed. The `entity_type` field enumerates entity kinds (`company`, `product`) -- it is not named after the collection and does not reference "standards" or "criteria."

---

## Verification checklist

After all edits:

1. `npx astro build` -- zero type errors, zero missing collection references.
2. `/criteria` route loads with the new heading and one-liner.
3. `/criteria/publishes-sustainability-report` loads with `CriteriaMatrix`.
4. `/companies/anthropic` (or any entity): "Criteria" section heading, links point to `/criteria/...`.
5. `/claims/anthropic/publishes-sustainability-report`: "Criterion:" label and link point to `/criteria/...`.
6. Nav "Criteria" link highlights correctly on criteria pages.
7. Home page count strip shows "N criteria."
8. `grep -r "standard_slug:" research/claims/` -- zero results.
9. `grep -rn "/standards" src/` -- zero results (all route hrefs updated).
10. `grep -rni "getCollection.*standards\|from.*['\"].*standards['\"]" src/` -- zero results (all collection and import references updated).

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md section 1 |
| 2026-04-22 | agent | expansion | Full implementation steps; resolved all open decisions; added citations.ts and index.astro to scope; corrected claim backfill count (0, not 84); added verification checklist |
| 2026-04-22 | agent | review | Corrected Step 4 (no CSS rule for standards-matrix exists, only a div class attribute); added explicit std/std-* naming decision; enumerated all 10 occurrences in claims/[...slug].astro; enumerated all 3 CSS rules in entities/[...slug].astro scope; added missing comment updates; added AccessibilityIcon.astro to scope as no-change; strengthened verification checklist with second grep |
