# Claim status field

**Status**: Ready
**Last updated**: 2026-04-22

A `status` field needs to be added to the claims schema to support a draft/published/archived workflow.

---

## Scope

**Schema change**: Add `status: z.enum(['draft', 'published', 'archived']).default('draft')` to the claims schema in `src/content.config.ts`. Also extend the verdict enum with `'not-applicable'` for claims where a criterion does not apply to an entity (distinct from `NotAssessedCell`, which means no claim has been filed).

**Build behavior**: All public list pages, index pages, entity pages, topic pages, criteria pages, and source citation lists show only `status: published`. Direct URLs (`/claims/[...slug]`) show all statuses with an appropriate notice banner.

**Pipeline integration**:
- `dr onboard` writes `status: draft` on new claim files
- `dr review` promotes to `published` and writes the audit sidecar -- not yet implemented; addressed in the audit-trail plan

**Decision (2026-04-22)**: Zod default is `draft`. Pipeline writes `status: draft` explicitly on new claims. A backfill script must set `status: published` on all existing claims before the schema lands in CI -- if the schema lands first, all existing claims vanish from public pages. No CI enforcement of this ordering; treat as an atomic manual step.

**Decision (2026-04-22)**: `not-applicable` is added to `VERDICT_ORDER`. It is a genuine verdict value (the criterion exists but does not apply to this entity), distinct from `NotAssessedCell` (no claim has been assessed yet). It will appear in the claims list filter bar and in `VerdictDistribution` counts.

---

## Implementation

Steps must be executed in the order listed. Steps 1 and 2 are a single atomic manual operation. Steps 3 onward are independent code changes that can be merged after the backfill is complete.

### Step 1 -- Backfill existing claims (run before any code change)

Run from the repo root. Prepends `status: published` as the first line after the opening `---` delimiter in every claim file.

```bash
python3 -c "
import pathlib, re
claims_dir = pathlib.Path('research/claims')
pat = re.compile(r'^(---\n)', re.MULTILINE)
count = 0
for p in sorted(claims_dir.rglob('*.md')):
    text = p.read_text()
    parts = text.split('---')
    if len(parts) < 3:
        print('SKIP (no frontmatter):', p)
        continue
    if 'status:' not in parts[1]:
        text = pat.sub(r'\1status: published\n', text, count=1)
        p.write_text(text)
        count += 1
        print('patched', p)
print(f'Done. {count} files patched.')
"
```

The script is idempotent: it skips any file that already contains `status:` in its frontmatter block. Files without frontmatter delimiters are skipped with a warning rather than erroring.

Verify before committing:

```bash
# Total claim file count
find research/claims -name '*.md' | wc -l
# Files containing status: in frontmatter (should match above)
grep -rl "^status:" research/claims/ | wc -l
```

Do not use `grep -r "^status:" ... | wc -l` (without `-l`) -- it counts body lines, not files.

Commit this change alone, before any schema change lands.

### Step 2 -- Schema change: `src/content.config.ts`

**Depends on**: Step 1 committed.

**File**: `src/content.config.ts`, claims collection. The current block from `verdict` through `next_recheck_due`:

```ts
verdict: z.enum([
  'true',
  'mostly-true',
  'mixed',
  'mostly-false',
  'false',
  'unverified',
]),
confidence: z.enum(['high', 'medium', 'low']),
standard_slug: z.string().optional(),
as_of: z.coerce.date(),
sources: z.array(z.string()),
recheck_cadence_days: z.number().default(60),
next_recheck_due: z.coerce.date().optional(),
```

Replace with:

```ts
verdict: z.enum([
  'true',
  'mostly-true',
  'mixed',
  'mostly-false',
  'false',
  'unverified',
  'not-applicable',
]),
confidence: z.enum(['high', 'medium', 'low']),
standard_slug: z.string().optional(),
status: z.enum(['draft', 'published', 'archived']).default('draft'),
as_of: z.coerce.date(),
sources: z.array(z.string()),
recheck_cadence_days: z.number().default(60),
next_recheck_due: z.coerce.date().optional(),
```

`status` is placed after `standard_slug` and before `as_of`.

### Step 3 -- Filter all public-facing `getCollection('claims')` calls

There are 11 call sites total. One (`getStaticPaths` in `src/pages/claims/[...slug].astro`) must not be filtered so that direct URLs resolve for all statuses. The remaining 10 must filter to `published`.

Apply this change in each file listed below:

```ts
// Before
await getCollection('claims')   // or getCollection("claims")

// After
await getCollection('claims', ({ data }) => data.status === 'published')
```

Files requiring the filter:

| File | Variable name | Notes |
|---|---|---|
| `src/pages/claims/index.astro` | `claims` | Claims list page |
| `src/pages/entities/[...slug].astro` | `allClaims` | `buildStandardsIndex` and `relatedClaims` filter automatically |
| `src/pages/companies/index.astro` | `claims` | Verdict distributions only count published |
| `src/pages/products/index.astro` | `claims` | Verdict distributions only count published |
| `src/pages/topics/index.astro` | `claims` | Category stats and sample titles only show published |
| `src/pages/topics/[category].astro` | `allClaims` | Filters to category after collection fetch |
| `src/pages/standards/index.astro` | `claims` | Coverage counts only count published |
| `src/pages/standards/[slug].astro` | `claims` | Standards matrix only shows published |
| `src/pages/sources/[...slug].astro` | `allClaims` | Citation index only shows published |
| `src/pages/index.astro` | `claims` | Home page claim count only reflects published |

File that must not be filtered:

| File | Reason |
|---|---|
| `src/pages/claims/[...slug].astro` `getStaticPaths` | Must emit paths for draft and archived claims so direct URLs resolve |

### Step 4 -- Update `src/pages/claims/[...slug].astro` (status notice)

`getStaticPaths` at line 5: do not filter. Leave unchanged.

In the frontmatter script block, insert after the `asOfDate` constant (line 43):

```ts
const isDraft = claim.data.status === 'draft';
const isArchived = claim.data.status === 'archived';
const showNotice = isDraft || isArchived;
```

Add `'not-applicable'` to the `verdictCssVar` map (lines 22-29):

```ts
"not-applicable": "var(--color-verdict-not-applicable)",
```

In the template, the `<header>` block begins with an optional standard reference paragraph, then `<h1>`. Insert the notice banner before `<h1>` and after the `{matchedStandard && (...)}` block:

```astro
{showNotice && (
  <p class="status-notice">
    {isDraft ? 'This claim is a draft and has not been published.' : 'This claim is archived and may be outdated.'}
  </p>
)}
```

Add the style to the `<style>` block:

```css
.status-notice {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-text-muted);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  padding: var(--space-xs) var(--space-sm);
  margin-bottom: var(--space-md);
}
```

### Step 5 -- Update `src/lib/verdict.ts`

Add `'not-applicable'` to all four exports. Place it last in each.

```ts
// Type
// Before
export type Verdict = 'true' | 'mostly-true' | 'mixed' | 'mostly-false' | 'false' | 'unverified';
// After
export type Verdict = 'true' | 'mostly-true' | 'mixed' | 'mostly-false' | 'false' | 'unverified' | 'not-applicable';

// VERDICT_ORDER -- add last
'not-applicable',

// VERDICT_LABELS -- add
'not-applicable': 'N/A',

// VERDICT_TOOLTIP -- add
'not-applicable': 'This criterion does not apply to this entity',

// VERDICT_KIND -- add
'not-applicable': 'not-applicable',
```

`verdictCounts` iterates `VERDICT_ORDER` to seed its counts object -- adding `'not-applicable'` to `VERDICT_ORDER` is sufficient for it to appear in counts. No changes needed to `sortByVerdict` or `verdictCounts` function bodies.

### Step 6 -- Update `src/components/VerdictBadge.astro`

Add the CSS rule for `not-applicable` after `.verdict-unverified`:

```css
.verdict-not-applicable { background: var(--color-verdict-not-applicable); font-style: italic; }
```

### Step 7 -- Update `src/components/VerdictDistribution.astro`

This component has its own inline `.verdict-*` CSS block separate from `VerdictBadge.astro`. `not-applicable` pills will appear automatically via `VERDICT_ORDER` once Step 5 is done, but the CSS class will be unstyled without this addition. Add after `.verdict-unverified`:

```css
.verdict-not-applicable { background: var(--color-verdict-not-applicable); }
```

No `font-style: italic` here -- the pill shows a count number, not a label.

### Step 8 -- Update `src/styles/tokens.css`

Add `--color-verdict-not-applicable` after `--color-verdict-unverified` in all four theme blocks:

| Block selector | Suggested value |
|---|---|
| `:root, [data-theme="dark"]` | `#888899` |
| `[data-theme="light"]` | `#777788` |
| `[data-contrast="high"]` | `#bbbbcc` |
| `[data-theme="light"][data-contrast="high"]` | `#333344` |

### Step 9 -- Update `src/pages/faq/index.astro`

The FAQ documents verdict values. Add a description of `not-applicable` after the Unverified entry:

```html
<li><strong>N/A (not applicable)</strong> -- this criterion does not apply to this entity.</li>
```

### Step 10 -- Update `pipeline/common/models.py`

Add `NOT_APPLICABLE` to the `Verdict` enum after `UNVERIFIED`:

```python
NOT_APPLICABLE = "not-applicable"
```

### Step 11 -- Update `pipeline/orchestrator/persistence.py`

Add `status: "draft"` to the frontmatter dict in `_write_claim_file`. The current dict (lines 211-219):

```python
fm = {
    "title": title,
    "entity": entity_ref,
    "category": category,
    "verdict": verdict,
    "confidence": confidence,
    "as_of": datetime.date.today(),
    "sources": source_ids,
}
```

Change to:

```python
fm = {
    "title": title,
    "entity": entity_ref,
    "category": category,
    "verdict": verdict,
    "confidence": confidence,
    "status": "draft",
    "as_of": datetime.date.today(),
    "sources": source_ids,
}
```

`status` is placed after `confidence` and before `as_of`. The pipeline dict does not include `standard_slug` (set manually in claim files), so no ordering gap exists.

### Step 12 -- `dr review` (deferred)

`dr review` is not implemented. The CLI defines: `verify`, `research`, `audit`, `ingest`, `onboard`. Promotion from `draft` to `published` and audit sidecar writing are addressed in the audit-trail plan. Do not implement here.

---

## Dependency order

| Step | Depends on |
|---|---|
| 1 (backfill) | nothing -- run first |
| 2 (schema) | Step 1 committed |
| 3 (filter all pages) | Step 2 |
| 4 (claims/[...slug] status notice) | Step 2 |
| 5 (verdict.ts) | Step 2 |
| 6 (VerdictBadge.astro) | Step 5 |
| 7 (VerdictDistribution.astro) | Step 5 |
| 8 (tokens.css) | Step 5 |
| 9 (faq) | Step 2 |
| 10 (pipeline/models.py) | Step 2 |
| 11 (pipeline/persistence.py) | Step 2 |
| 12 (dr review) | audit-trail plan |

Steps 3-4 and 5-9 and 10-11 are independent of each other and can be developed in parallel after Step 2 merges.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md section 2 |
| 2026-04-22 | agent | expansion | Full implementation plan; located write site in persistence.py; noted dr review as unimplemented; enumerated not-applicable touch points; added dependency order table |
| 2026-04-22 | agent | review | Corrected published-filter scope from 2 pages to 10; added VerdictDistribution.astro (Step 7); added FAQ update (Step 9); fixed content.config.ts Before/After to show full surrounding fields; added defensive guard to backfill script; corrected verification command to use grep -rl; added not-applicable to verdictCssVar in claims/[...slug].astro; clarified header insertion point for status notice; resolved not-applicable/VERDICT_ORDER decision explicitly |
