# Claim Detail Page: Review Status Promotion + Site-wide Breadcrumbs

## Context

The claim detail page buries critical provenance information: human review status is hidden inside a collapsed `<details>` at the bottom, and the confidence explanation requires a click to reveal (non-obvious UX). Readers cannot answer at a glance: *when was this verdict reached, was it reviewed by a person, what process was followed?* The entity link is raw text rather than navigational context.

This plan promotes review status into the header meta row, fixes confidence UX, adds a site-wide Breadcrumb component, enriches audit trail source display with collection metadata, and moves the criterion reference to the bottom of the page.

Future improvements (verdict history, multi-reviewer) are appended to `docs/UNSCHEDULED.md`.

---

## Changes

### 1. New: `src/components/Breadcrumb.astro`

Props: `crumbs: { label: string; href?: string }[]`

- Callers pass `{ label: "Home", href: "/" }` as first crumb explicitly — no auto-injection
- Last crumb has no `href`; gets `aria-current="page"`
- `<nav aria-label="Breadcrumb"><ol>` structure; CSS `::after` separator `/` — no JS

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

---

### 2. Modify: `src/pages/claims/[...slug].astro`

**New imports:**
```typescript
import Breadcrumb from "../../components/Breadcrumb.astro";
import VerdictBadge from "../../components/VerdictBadge.astro";
```

**New data fetching (after existing frontmatter, before closing `---`):**
```typescript
// Entity lookup for breadcrumb
const entities = await getCollection("entities");
const entityEntry = entities.find(e => e.id === claim.data.entity) ?? null;

const typeParentMap: Record<string, { label: string; href: string }> = {
  company: { label: "Companies", href: "/companies" },
  product: { label: "Products",  href: "/products" },
  topic:   { label: "Topics",    href: "/topics" },
};
const typeParent = entityEntry ? (typeParentMap[entityEntry.data.type] ?? null) : null;
const entityLabel = entityEntry?.data.name ?? claim.data.entity;

const claimCrumbs = [
  { label: "Home", href: "/" },
  ...(typeParent ? [typeParent] : []),
  { label: entityLabel, href: `/entities/${claim.data.entity}` },
  { label: claim.data.title },  // current page — no href
];

// Source metadata lookup for audit trail
const allSources = await getCollection("sources");
const sourceMap = new Map(allSources.map(s => [s.id, s]));

// Reviewer status
const hasReviewer = !!(audit?.human_review.reviewer);
const reviewerCount = hasReviewer ? 1 : 0;  // single-reviewer schema today
```

**Remove from frontmatter:**
- `verdictCssVar` map — replaced by `VerdictBadge`
- Keep `confidenceLabels` and `confidenceExplanations` — used for `title` tooltip

**Restructured header** (replace current header block):
```astro
<Breadcrumb crumbs={claimCrumbs} />

<header>
  {showNotice && <p class="status-notice">...</p>}
  <h1>{claim.data.title}</h1>

  <div class="meta">
    <VerdictBadge verdict={claim.data.verdict} />

    <span class="confidence" title={confidenceExplanations[claim.data.confidence]}>
      {confidenceLabels[claim.data.confidence] || claim.data.confidence} confidence
    </span>

    <span class="as-of">{asOfDate}</span>

    <span class="reviewer-status"
      aria-label={hasReviewer ? `${reviewerCount} reviewer` : 'Pending review'}>
      {hasReviewer ? `✓ ${reviewerCount} reviewer` : 'Pending review'}
    </span>
  </div>
</header>
```

Remove `<details class="confidence-details">` (replaced by `<span title>`).  
Remove `<div class="entity-link">` (replaced by `<Breadcrumb>`).  
Remove `<p class="criterion-ref">` from header (moves to bottom — see below).

**Audit trail `<details>` summary** — update to show agents, not model:
```astro
<summary>Research process · {ranAt} · {audit.pipeline_run.agents.join(', ')}</summary>
```

**Sources display in audit trail** — replace `ingested` span:
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
- Source in collection → internal link to `/sources/{id}` + `kind · source_type · publisher`
- Source not in collection → external link, no metadata, no "ingested" label

**Human review subsection in research details** — keep and update to expose reviewer name (meta row shows count only; name lives here):
```astro
<section class="audit-section">
  <h3>Human review</h3>
  {reviewedAt ? (
    <div>
      <p>Reviewed {reviewedAt}{audit.human_review.reviewer ? ` by ${audit.human_review.reviewer}` : ''}</p>
      {audit.human_review.notes && <p class="audit-muted">{audit.human_review.notes}</p>}
      {audit.human_review.pr_url && <p><a href={audit.human_review.pr_url}>Review PR</a></p>}
    </div>
  ) : (
    <p class="audit-muted">Pending human review</p>
  )}
</section>
```
The `.reviewer-status` span in the meta row shows count (`✓ 1 reviewer`). The reviewer name, date, notes, and PR link are only visible when the research details section is expanded.

**Criterion ref at bottom** — insert before `<section class="review-info">`:
```astro
{matchedCriteria && (
  <p class="criterion-ref">
    Criterion: <a href={`/criteria/${matchedCriteria.id}`}>{matchedCriteria.data.text}</a>
  </p>
)}
```

**CSS — remove:**
- `.verdict-badge` (local, replaced by component)
- `.confidence-details`, `.confidence-details summary`, `.confidence-explanation`
- `.entity-link`
- `.ingested-yes`, `.ingested-no`
- Split combined `.confidence, .as-of, .category` rule

**CSS — add:**
```css
.confidence {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-decoration: underline dotted;
  text-decoration-color: var(--color-text-faint);
  text-underline-offset: 2px;
  cursor: default;
  /* title tooltip not visible on touch — acceptable; label is self-explanatory */
}
.reviewer-status { color: var(--color-text-muted); font-size: var(--font-size-sm); }
.source-meta { color: var(--color-text-faint); font-size: var(--font-size-xs); margin-left: 0.4em; }
```

---

### 3. Modify: `src/pages/entities/[...slug].astro`

**Import:** `import Breadcrumb from "../../components/Breadcrumb.astro";`

**Add breadcrumb data (before closing `---`):**
```typescript
const typeParentMap = {
  company: { label:"Companies", href:"/companies" },
  product: { label:"Products",  href:"/products" },
  topic:   { label:"Topics",    href:"/topics" },
};
const entityTypeParent = typeParentMap[entity.data.type as keyof typeof typeParentMap] ?? null;
const entityCrumbs = [
  { label:"Home", href:"/" },
  ...(entityTypeParent ? [entityTypeParent] : []),
  { label: entity.data.name },
];
```

**In markup** — insert before `<header>` (line 61):
```astro
<article class="entity-detail">
  <Breadcrumb crumbs={entityCrumbs} />
  <header>
```

---

### 4. Modify: `src/pages/sources/[...slug].astro`

**Import:** `import Breadcrumb from "../../components/Breadcrumb.astro";`

**Add:** `const sourceCrumbs = [{ label:"Home", href:"/" }, { label:"Sources", href:"/sources" }, { label: source.data.title }];`

**In markup** — insert before `<header>` (line 58):
```astro
<article class="source-detail">
  <Breadcrumb crumbs={sourceCrumbs} />
  <header>
```

---

### 5. Modify: `src/pages/criteria/[slug].astro`

**Import:** `import Breadcrumb from "../../components/Breadcrumb.astro";`

**Add:** `const criteriaCrumbs = [{ label:"Home", href:"/" }, { label:"Criteria", href:"/criteria" }, { label: std.data.text }];`

**In markup** — insert before `<header class="std-header">` (line 60, no `<article>` wrapper):
```astro
<Base title={std.data.text} layout="wide">
  <Breadcrumb crumbs={criteriaCrumbs} />
  <header class="std-header">
```

---

### 6. Update `docs/UNSCHEDULED.md`

Append section **"Claim detail page — deferred improvements"**:

| Work Item | Notes |
|-----------|-------|
| Verdict change history | Append-only `history` array in `.audit.yaml`; site renders a timeline. Requires pipeline changes. |
| Multi-reviewer tracking | `human_review` becomes array. Site shows `✓ N reviewers`. Schema version bump + backfill script. |
| Sign-off count in list views | Once multi-reviewer array exists, surface count in `ClaimRow` and entity claim lists as trust signal. |

---

## Implementation notes

**`getCollection` cache:** Astro caches collection data per build pass, so adding `getCollection("entities")` and `getCollection("sources")` to the claim page adds no meaningful I/O cost.

**Entity lookup failure:** If `entityEntry` is null (typo in `entity` frontmatter), breadcrumb falls back to raw entity ID as a non-linked crumb. No crash.

**Source map miss:** If a sidecar source ID has no matching collection entry, the audit trail shows an external link with no metadata badges — clean degradation, no "ingested" label.

**Touch devices:** `title` tooltip is not visible on touch. The confidence label (`High confidence`, `Medium confidence`, `Low confidence`) is self-explanatory without the tooltip. `VerdictBadge` uses the same `title` pattern.

---

## Verification

1. `inv dev`
2. Open `/claims/anthropic/publishes-sustainability-report`
   - Breadcrumb: `Home / Companies / Anthropic / [claim title]`
   - Meta row: `[UNVERIFIED]  High confidence  2026-04-24  ✓ 1 reviewer`
   - Hovering "High confidence" shows tooltip (dotted underline visible)
   - No criterion in header; criterion appears at bottom before review cadence
   - Audit summary shows agent names
   - Sources show `kind · source_type · publisher` with internal links
3. Open `/entities/companies/anthropic` — breadcrumb: `Home / Companies / Anthropic`
4. Open a source detail page — breadcrumb: `Home / Sources / [title]`
5. Open a criterion detail page — breadcrumb: `Home / Criteria / [text]`
6. `npm run build` — no type errors
