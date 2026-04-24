# Plan: Claim detail page review status and site-wide breadcrumbs

**Status**: ready
**Created**: 2026-04-24

## Context

The claim detail page currently hides human review status in a collapsed `<details>` at the bottom and surfaces the confidence explanation only on click. Readers cannot answer at a glance whether a verdict was reviewed by a person. The entity is rendered as raw text rather than navigation.

This plan promotes review status into the header meta row, simplifies confidence display, adds a site-wide `Breadcrumb` component, enriches the audit trail with source collection metadata, and moves the criterion reference to the bottom of the page.

## Non-goals

Tracked in `docs/UNSCHEDULED.md`, out of scope here:

| Deferred | Notes |
|----------|-------|
| Verdict change history | Append-only `history` array in `.audit.yaml`; site renders a timeline. Requires pipeline changes. |
| Multi-reviewer tracking | `human_review` becomes an array. Site shows `✓ N reviewers`. Schema version bump and backfill. |
| Sign-off count in list views | Once multi-reviewer array exists, surface count in `ClaimRow` and entity claim lists. |

---

## Changes

### 1. New: `src/lib/entityTypes.ts`

Single source of truth for entity-type to parent-page mapping. Used by both claim and entity pages so the map is not duplicated.

```typescript
export const ENTITY_TYPE_PARENTS = {
  company: { label: "Companies", href: "/companies" },
  product: { label: "Products",  href: "/products"  },
  topic:   { label: "Topics",    href: "/topics"    },
  sector:  { label: "Sectors",   href: "/sectors"   },
} as const;

export type EntityType = keyof typeof ENTITY_TYPE_PARENTS;
```

The schema (`src/content.config.ts`) defines `entity.type` as `z.enum(['company', 'product', 'topic', 'sector'])`, so all four are covered. Verify each parent index page exists before merging; if any is missing, omit that crumb rather than ship a 404.

### 2. New: `src/components/Breadcrumb.astro`

Props: `crumbs: { label: string; href?: string }[]`. Callers pass `Home` explicitly as the first crumb (no auto-injection). The last crumb has no `href` and gets `aria-current="page"`. Separator via CSS `::after`. CSS-generated content is implicitly `aria-hidden`, but verify with VoiceOver during the verification pass.

```astro
---
interface Props { crumbs: { label: string; href?: string }[] }
const { crumbs } = Astro.props;
---
<nav aria-label="Breadcrumb" class="breadcrumb">
  <ol>
    {crumbs.map((c, i) => {
      const isLast = i === crumbs.length - 1;
      return (
        <li>
          {(isLast || !c.href)
            ? <span aria-current={isLast ? "page" : undefined}>{c.label}</span>
            : <a href={c.href}>{c.label}</a>}
        </li>
      );
    })}
  </ol>
</nav>
<style>
  .breadcrumb ol { list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap;
    align-items:center; font-size:var(--font-size-xs); color:var(--color-text-faint); }
  .breadcrumb li { display:flex; align-items:center; }
  .breadcrumb li:not(:last-child)::after { content:"/"; margin:0 0.4em; opacity:0.5; }
  .breadcrumb a { color:var(--color-accent); text-decoration:none; }
  .breadcrumb a:hover { text-decoration:underline; }
  .breadcrumb [aria-current="page"] { color:var(--color-text-muted); }
</style>
```

### 3. Modify: `src/pages/claims/[...slug].astro`

**Imports**: add `Breadcrumb`, `VerdictBadge`, and `ENTITY_TYPE_PARENTS`.

**Frontmatter additions** (entity lookup for breadcrumb, source map for audit trail, review state):

```typescript
const entities = await getCollection("entities");
const entityEntry = entities.find(e => e.id === claim.data.entity) ?? null;
const typeParent = entityEntry ? (ENTITY_TYPE_PARENTS[entityEntry.data.type] ?? null) : null;
const entityLabel = entityEntry?.data.name ?? claim.data.entity;

const claimCrumbs = [
  { label: "Home", href: "/" },
  ...(typeParent ? [typeParent] : []),
  { label: entityLabel, href: `/entities/${claim.data.entity}` },
  { label: claim.data.title },
];

const allSources = await getCollection("sources");
const sourceMap = new Map(allSources.map(s => [s.id, s]));

const isReviewed = !!(audit?.human_review.reviewer);
```

**Frontmatter removals**: the `verdictCssVar` map (replaced by `VerdictBadge`) and `confidenceExplanations` (no longer needed; see meta row decision below). Keep `confidenceLabels`.

**Header markup** (replace current header block):

```astro
<Breadcrumb crumbs={claimCrumbs} />

<header>
  {showNotice && <p class="status-notice">...</p>}
  <h1>{claim.data.title}</h1>

  <div class="meta">
    <VerdictBadge verdict={claim.data.verdict} />
    <span class="confidence">{confidenceLabels[claim.data.confidence] || claim.data.confidence} confidence</span>
    <span class="as-of">{asOfDate}</span>
    <span class={isReviewed ? "review-state reviewed" : "review-state unreviewed"}>
      {isReviewed ? "✓ Reviewed" : "Unreviewed"}
    </span>
  </div>
</header>
```

Decisions:

- **Confidence** is a plain label. The previous dotted-underline + `title=` tooltip pattern was invisible on touch and the H/M/L label already carries the signal. The longer explanation, if needed, can live on a dedicated `/about/confidence` page (out of scope here).
- **Review state** shows status only, not count. With the single-reviewer schema today the count is always 0 or 1 and `✓ 1 reviewer` reads oddly. Reintroduce `✓ N reviewers` when multi-reviewer lands.
- The phrase **"Unreviewed"** (factual) replaces "Pending review" (sounds like the verdict itself is provisional).
- Reviewer name, date, notes, and PR link remain in the research details section (kept, unchanged structurally).

**Remove from page markup**:

- `<details class="confidence-details">` block.
- `<div class="entity-link">` (replaced by breadcrumb).
- `<p class="criterion-ref">` from the header (moved to bottom).

**Audit trail summary** (currently shows `model`):

```astro
<summary>Research process · {ranAt} · {audit.pipeline_run.agents.join(', ')}</summary>
```

**Sources display** in audit trail. The schema includes `{ id, url, title, ingested }`. The new UI uses presence in the sources collection (internal vs external link) as the trust signal and drops the separate "ingested" badge.

```astro
{audit.sources_consulted.map((src) => {
  const meta = sourceMap.get(src.id);
  return (
    <li>
      {meta
        ? <a href={`/sources/${src.id}`}>{src.title}</a>
        : <a href={src.url} target="_blank" rel="noopener noreferrer">{src.title} ↗</a>}
      {meta && (
        <span class="source-meta">
          {meta.data.kind}{meta.data.source_type ? ` · ${meta.data.source_type}` : ''} · {meta.data.publisher}
        </span>
      )}
    </li>
  );
})}
```

**Criterion ref at bottom** (insert before `<section class="review-info">`):

```astro
{matchedCriteria && (
  <p class="criterion-ref">
    Criterion: <a href={`/criteria/${matchedCriteria.id}`}>{matchedCriteria.data.text}</a>
  </p>
)}
```

**CSS removals**: `.verdict-badge`, `.confidence-details` (and children), `.entity-link`, `.ingested-yes`, `.ingested-no`. Split the combined `.confidence, .as-of, .category` rule (the dotted-underline styling on `.confidence` goes away with the tooltip).

**CSS additions**:

```css
.confidence, .as-of { color: var(--color-text-muted); font-size: var(--font-size-sm); }
.review-state { font-size: var(--font-size-sm); }
.review-state.reviewed { color: var(--color-text-muted); }
.review-state.unreviewed {
  color: var(--color-text);
  border: 1px solid var(--color-text-faint);
  border-radius: 999px;
  padding: 0.1em 0.6em;
}
.source-meta { color: var(--color-text-faint); font-size: var(--font-size-xs); margin-left: 0.4em; }
```

The unreviewed state gets an outlined chip so it reads as a distinct status rather than muted footnote text. No fill color: that would compete with the verdict badge.

### 4. Modify: `src/pages/entities/[...slug].astro`

Import `Breadcrumb` and `ENTITY_TYPE_PARENTS`. Build `entityCrumbs` from the shared map. Insert `<Breadcrumb crumbs={entityCrumbs} />` before the `<header>` at line 61 (inside the existing `<article class="entity-detail">`).

### 5. Modify: `src/pages/sources/[...slug].astro`

Import `Breadcrumb`. Build `sourceCrumbs = [{ label: "Home", href: "/" }, { label: "Sources", href: "/sources" }, { label: source.data.title }]`. Insert before `<header>` at line 58.

### 6. Modify: `src/pages/criteria/[slug].astro`

Import `Breadcrumb`. Build `criteriaCrumbs = [{ label: "Home", href: "/" }, { label: "Criteria", href: "/criteria" }, { label: std.data.text }]`. Insert before `<header class="std-header">` at line 60.

### 7. Update `docs/UNSCHEDULED.md`

Append a "Claim detail page, deferred improvements" section with the table from Non-goals above.

---

## Rollout

Two commits, in order, each independently reviewable and revertible:

1. **Breadcrumb landing**: `src/lib/entityTypes.ts`, `src/components/Breadcrumb.astro`, applied to claim, entity, source, and criterion pages. Verify all four parent index pages exist; omit any that do not.
2. **Claim header restructure**: meta-row review state, confidence simplification, audit summary agent names, source metadata enrichment, criterion to bottom, CSS deltas.

`docs/UNSCHEDULED.md` edits land with whichever commit goes first.

## Edge cases

- **Entity lookup miss**: claim's `entity` value not found in collection. Breadcrumb falls back to raw entity ID as a non-linked label. No crash.
- **Source not in collection**: audit-trail item renders an external link with no metadata badge.
- **Missing parent index**: if `/companies`, `/products`, `/topics`, or `/sectors` does not exist, omit that crumb rather than 404.

## Acceptance

- [ ] `inv dev` serves with no console errors.
- [ ] `npm run build` passes type-check and content-collection validation.
- [ ] `/claims/anthropic/publishes-sustainability-report` shows breadcrumb `Home / Companies / Anthropic / [title]`; meta row shows verdict badge, confidence label, date, and either "✓ Reviewed" or an outlined "Unreviewed" chip; criterion appears at bottom; audit summary shows agent names; sources show internal links with `kind · source_type · publisher`.
- [ ] A claim with `audit.human_review.reviewer === null` renders the outlined "Unreviewed" chip.
- [ ] A claim whose `entity` frontmatter does not match any entity falls back to a non-linked crumb without crashing.
- [ ] An audit `sources_consulted` entry whose `id` is not in the sources collection renders an external link with no metadata.
- [ ] A sector-typed entity page renders `Home / Sectors / [name]`.
- [ ] Source detail page renders `Home / Sources / [title]`.
- [ ] Criterion detail page renders `Home / Criteria / [text]`.
- [ ] Keyboard tab order through breadcrumb links matches DOM order; focus ring visible.
- [ ] Mobile viewport (<380px): meta row wraps cleanly, outlined chip does not overflow.
- [ ] VoiceOver pass on the claim page: breadcrumb `/` separators are not announced as "slash"; the unreviewed chip is read as its label only.
