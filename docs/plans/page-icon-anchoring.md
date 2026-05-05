# Page icon anchoring — outdented icon + rail rollout

Roll out the prototype Design 4 (icon outdented into the page gutter, tied to the metadata block by a hairline vertical rail) to every page that has a page-identity icon. Extend the same pattern, with appropriate adjustments, to index pages and to selected in-page lists.

Reference prototype: `src/pages/proto/header-designs.astro` (`#d4`).

## Why

The icon is being promoted from "metadata satellite" to "page-level identity landmark in the gutter." The current `.item-meta` icon column also has a separate alignment bug (it floats because it's vertically centered against a variable-height metadata column), but a one-line fix exists for that and is not why we're rebuilding the layout. We are rebuilding because we want the icon outside the body column entirely, anchored to its own gutter location.

The H1 remains the strongest *informational* element on the page. The icon is the page-identity *landmark*: a stable visual that says "this page is a Source / Claim / Criterion" before any text is read.

This rollout is a placement change, not a prominence change. It depends on the kind / source-type badges being demoted in parallel (see "Badge demotion" below). Without that, a 64px outlined icon in the gutter still ranks third visually behind two saturated solid-fill badges in the body.

## Scope

In scope:

1. **Badge demotion (prerequisite).** Quiet `.kind-badge` and `.source-type-badge` so the page-identity icon can rank ahead of them in the visual hierarchy.
2. Update the shared `PageHeader.astro` to the outdent + rail layout. This rolls the change out to all 5 detail page types in one edit.
3. Introduce a page-type header treatment for index pages so the same icon system anchors list pages, via a `variant` prop on `PageHeader` (not a sibling component).
4. Add small per-row type icons on selected in-page lists where a type icon adds scannability and does not duplicate an existing colored badge.
5. Responsive fallback: stack icon above title when the gutter cannot fit the outdent. Driven by container queries on `<main>`, not viewport breakpoints. See acceptance below for the resolved breakpoints.

Out of scope:

- Promoting the icon further (size increase beyond 64px, colorization beyond current tokens). Decided against in prototype review.
- Restyling verdict badges. Verdict remains the dominant in-body landmark on Claim detail; the page-identity icon is a distinct concern.

## What changes

### Badge demotion (prerequisite)

Today `.kind-badge` and `.source-type-badge` use saturated solid-fill backgrounds with white bold uppercase text. They are the strongest visual elements on the source / claim detail pages. Until they step down, no amount of icon repositioning will produce the intended hierarchy.

Demote both badge classes from "solid pill" to "tinted chip":

- Replace solid backgrounds with a faint tinted background derived from the same semantic color (e.g., the kind color at low alpha) plus a 1px border in the saturated semantic color. Text becomes the saturated semantic color rather than `--color-on-badge` white.
- Drop `font-weight: bold`. Keep small size, uppercase, letter-spacing.
- Keep semantic meaning carried by hue.

Files:

- `src/pages/sources/[...slug].astro` — `.kind-badge`, `.source-type-badge` definitions (lines around 155–186).
- Any other call sites that re-style these classes.

Acceptance:

- The chip is recognizable at a glance and color-coded as today.
- Side-by-side, the page H1 reads as the strongest element, the page-identity icon as the next-strongest, and the chips as metadata.
- No regressions in dark / light / high-contrast themes (verify the chip's background tint and border are legible in all three).

This block lands before any header changes; otherwise the icon promotion has nothing to win against.

### Detail page header (one component, five page types)

Edit `src/components/PageHeader.astro` to replace the current grid (icon-col + meta-col) with the outdent + rail pattern. Existing `type` and `crumbs` props remain. Existing `<slot />` for metadata stays — call sites do not need changes.

Detail pages affected (no edits required at call sites):

- `src/pages/sources/[...slug].astro`
- `src/pages/criteria/[slug].astro`
- `src/pages/entities/[...slug].astro`
- `src/pages/topics/[topic].astro`
- `src/pages/claims/[...slug].astro`

Layout in the new component:

- Crumbs stay above the title.
- Title block becomes `position: relative` host for the absolutely-positioned icon outdent.
- Icon outdent: 64px box, type label below, hairline rail extending alongside the title + metadata block. Sits at `right: calc(100% + var(--space-md))` of the title block, so it consumes page gutter, not body width.
- The type label span gets `aria-hidden="true"` (sighted-only redundancy with the H1; screen readers should not announce "Source / [title]").
- Metadata `<slot />` content flows normally inside the body column; no left gutter inside the body.
- Empty-slot detection uses `Astro.slots.has('default')` in component frontmatter — the rail is conditionally rendered only when there is metadata to flank. (`:has(:empty)` is unreliable due to whitespace text nodes in Astro slot output.)
- Container-query driven: add `container-type: inline-size` to `<main>` in `Base.astro` so `PageHeader` adapts to its actual layout context (`reading` vs `wide` vs `bare`) rather than peeking at the viewport.

Resolved breakpoint math (replaces the prototype's 900px figure):

- *Reading* (`max-width: 48rem` = 768px): outdent needs 88px gutter. Container width ≥ ~1000px clears it. Below that, collapse to inline-stack above the H1.
- *Wide* (`max-width: 72rem` = 1152px): outdent needs viewport ~1328px to clear. Common laptop sizes (1280, 1366) do not. **Wide layout uses inline-stack at all sizes.** No container-query branch needed; the `wide` variant is always stacked.
- *Bare*: stacked.

Acceptance:

- Detail pages render with icon in gutter when the container clears ~1000px, and stacked above the H1 otherwise.
- Long titles wrap inside the body column without colliding with the icon.
- Rail spans the full title + metadata block height (matching the prototype's `.d4-rail` behavior). The rail is hidden when no metadata slot is present.
- Type label fits in the 72px outdent column for all `ENTITY_TYPE_LABELS` values; long labels (e.g., "Documentation") use `width: max-content; min-width: 64px` so the label can spill slightly without truncating.
- No shift of the H1 left edge versus current production layout.
- `@media print`: outdent falls back to inline-stack so the icon does not vanish in print.

### Index page header (new variant)

Index pages currently use a bare `<h1>` with no icon anchoring (`src/pages/{claims,sources,criteria,sectors,companies,products,topics}/index.astro`).

Apply the same outdent + rail treatment, with the icon representing the *type of thing listed*:

| Index page | Icon type |
|---|---|
| `/claims` | `claim` |
| `/sources` | `source` |
| `/criteria` | `criterion` |
| `/sectors` | `sector` |
| `/companies` | `company` |
| `/products` | `product` |
| `/topics` | `topic` |

Implementation: extend `PageHeader.astro` with a `variant?: 'detail' | 'index'` prop. Index variant skips the rail (no metadata to flank), allows omitted or empty crumbs, and may keep the type label visible (since the icon's referent — "this page IS a Source" vs "this page LISTS Sources" — is ambiguous on index pages and the label is what disambiguates). One source of truth, no sibling component.

Wide-layout indexes (criteria, etc.) use the inline-stack treatment at all viewport sizes per the resolved breakpoint math above.

`src/pages/faq/index.astro` is excluded — FAQ has no entity type and the icon adds no signal there.

Home (`src/pages/index.astro`) is excluded — bespoke layout, separate concern.

### Per-row icons in lists (selective, not blanket)

Honest assessment: most existing list rows already carry strong visual landmarks (verdict badges in `ClaimRow`, source-type badges, etc.). Adding a type icon on rows that already have a badge introduces duplicate landmarks and clutters scan flow. Apply only where the row has no badge today and where the page contains a *mix* of contexts that benefits from a per-row type cue.

Candidates (verify during implementation, do not blanket-apply):

| Location | Add icon? | Reason |
|---|---|---|
| `ClaimRow` (used on `/claims`, criterion detail "Also referenced", source detail "Claims using this source") | No | Verdict badge already anchors the row |
| `CriteriaMatrix` rows on criterion detail (Brandon's example: `/criteria/publishes-sustainability-report`) | Investigate | If rows lack a badge, a small claim icon (16px) at row left adds scannability; if the matrix already shows verdict cells, skip |
| `SourceRow` on `/sources` | Investigate | Currently shows kind badge; if kind badge is the only visual anchor, leave it alone |
| Entity detail "Claims" lists | No | Uses `ClaimRow` |

Rule of thumb to apply: **if a row already has a colored badge, do not add a type icon**. The icon's job (landmarking the row's type) is already done by the badge.

`ObjectTypeIcon` already supports a `size` prop — use 16px for row-scale icons.

## Implementation order

1. **Badge demotion.** Restyle `.kind-badge` and `.source-type-badge` to tinted chips. Verify dark, light, and high-contrast themes. Land first; the icon promotion that follows depends on this.
2. Refactor `PageHeader.astro`: add `variant` prop, switch to outdent + rail layout for `detail`, inline-stack for `index` and for `wide` containers. Add `container-type: inline-size` to `<main>` in `Base.astro`. Use `Astro.slots.has('default')` to gate the rail. (No call-site changes for detail pages.)
3. Visual QA pass on the 5 detail pages using the verification matrix below.
4. Adopt `PageHeader` (with `variant="index"`) on the 7 index pages listed above.
5. Per-row icons: audit each list component, apply only where the rule above says so. One row component at a time; visual diff before/after.
6. Remove `src/pages/proto/header-designs.astro` once the rollout is committed. Confirm no docs link to `/proto/header-designs` before deletion.

### Verification matrix (manual)

The prop API is unchanged for detail pages, so a feature flag is unnecessary. Sweep this matrix on dev before committing the PageHeader refactor:

| Page type | Short title | Long title | Sparse meta | Rich meta | ~768px | ~1024px | ~1440px |
|-----------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| sources/[slug] | | | | | | | |
| criteria/[slug] (layout=wide) | | | | | | | |
| entities/[slug] | | | | | | | |
| topics/[topic] | | | | | | | |
| claims/[slug] | | | | | | | |

## Risks

- **Light-theme icon-box visibility.** `--color-surface` (light) is `#ffffff` on `#f8f7f4` background with a `#e0dfd8` border — the icon box becomes a near-invisible white square on cream. Pre-existing issue but the outdent makes the box more load-bearing. Verify in light mode; consider a slightly tinted surface for the icon box specifically, or an inverted treatment (transparent box + glyph + label only).
- **Token gap for icon dimensions.** 64px (icon box), 72px (outdent column), 44px (icon glyph) are not in the spacing scale. Add `--icon-box-size: 64px` and `--icon-box-size-row: 32px` (or similar) to `tokens.css` so the values are reusable and themable. Low cost, do it as part of step 2.
- **Per-row icon overuse.** Adding type icons to every list "because consistency" defeats their purpose. Mitigation: the rule above is conservative; require an explicit reason per list before adding. Underlying principle: page-icon answers "where am I"; row-icon answers "what is this thing in this list". Most rows on this site are mono-typed, so row icons add no signal regardless of badges.
- **Section H2 anchoring.** Out of scope and should stay that way. Section headings ("Summary", "Sources", etc.) must not adopt the icon-anchored treatment; the page-level icon is the only landmark of its kind.

## Reviewer notes — design lens

Captured 2026-05-05 by a design-lens reviewer. Items below either change how the plan should be evaluated or call out questions the plan does not answer.

**Open the simpler-fix question first.** The stated diagnosis ("icon floats because metadata column varies in height") is a vertical-alignment problem. `PageHeader.astro` line 57 uses `justify-content: center` on `.icon-col`. Changing that to `flex-start` (or `align-items: start` on `.item-meta`) anchors the icon to the top of the metadata row without rebuilding the layout. Outdent + rail should be justified against that alternative, not against the current centered layout. If outdent+rail is kept, the justification is: "we want the icon as a page-level landmark (in the gutter, not co-mingled with metadata)", not "we want it to stop floating." The current "Why" conflates these.

**Rail-height contradiction.** Acceptance criterion in this plan says the rail extends "to the bottom of the metadata content." The d4 prototype implements the outdent with `top: 0; bottom: 0` on an absolutely-positioned container, and `flex: 1 1 auto` on the rail — which stretches to the whole `.d4-body` column (title + meta + dates + links + takeaway), not just metadata. Pick one. If "metadata only", the implementation needs the rail to stop at the meta block boundary (e.g., the rail lives inside the meta block, not the title block). If "whole body column", reword the criterion.

**Badge restyle out-of-scope is defensible-but-fragile.** The icon's claim to be a "page-identity landmark" depends on the badges stepping down in loudness. Today, `.kind-badge` uses fully-saturated `--color-kind-*` values as backgrounds (sources/[...slug].astro line 84). Until those quiet down, a 64px outlined icon in the gutter will still come third in the visual order behind the kind badge and the source-type badge. The plan should at least state the dependency: "the icon-as-landmark claim assumes badge hierarchy is later adjusted; if it isn't, this rollout buys placement, not prominence."

**Three labels for one fact.** On a Source detail page the user sees: breadcrumb tail "Sources", a `Source`-style type label below the icon, and the icon glyph itself. Three signals for the same thing. The type label is the weakest of the three and could be dropped on detail pages once the icon is established. Keep it on index pages where the icon's referent is ambiguous (see next point).

**Index page conflation is a real semantic mismatch.** On `/sources/foo` the icon means "this page is a Source." On `/sources` the icon means "this page lists Sources." Same glyph, different semantic. The type label below the icon is what disambiguates, but the plan removes nothing to compensate. Minimal fix: keep the type label on index variants and consider a treatment difference (e.g., outlined vs filled, or a "All" prefix on the label) so users learn the difference. Do not solve in this plan; just flag.

**Per-row icons: state the principle.** The rule ("don't add a row icon if the row has a colored badge") is fine in practice, but the underlying principle is worth naming: page-icon answers "where am I", row-icon answers "what is this thing in the list". Pages always need the first; rows only need the second when the row's *type* is non-obvious from context. Most rows on this site are mono-typed lists (`/claims` is all claims), so the row-icon adds no signal regardless of badges. State the principle so future lists inherit it.

**Token gap for icon dimensions.** 64px (icon box), 72px (outdent width), 44px (icon glyph) are not in the spacing scale. They're justified one-offs but they will show up in three components (PageHeader, index variant, possibly per-row at 16px). Add `--icon-box-size: 64px`, `--icon-box-size-row: 32px` (or similar) to `tokens.css` so the values are reused, themable, and easy to revisit. Low priority but cheap.

**Light-theme icon box.** `--color-surface` (light) is `#ffffff` on `--color-bg` `#f8f7f4` with a `#e0dfd8` border. The icon box becomes a near-invisible white square on cream. This is a pre-existing issue, not introduced by the plan — but the outdent makes the box more visually load-bearing, so the issue gets worse, not better. Verify in light mode during QA; consider a slightly tinted surface for the icon box specifically, or an inverted treatment (transparent box + just the glyph + label).

**Section H2 anchoring — out of scope, leave it that way.** Worth saying explicitly so it doesn't bleed into a later iteration. Section headings ("Summary", "Sources", "Audit trail") should not adopt the icon-anchored treatment; the page-level icon is the only landmark of its kind.

**One thing missing.** "Verdict" is the closest thing to a page-identity treatment Claim detail pages already have (the verdict badge is the visual anchor of a Claim). The icon-anchoring change moves the icon into the gutter and leaves the verdict badge inside the body column. On Claim detail specifically, the icon and the verdict badge will compete more once the icon is gutter-anchored. Worth a sentence in the plan: on Claim detail, the verdict badge remains the dominant in-body landmark; the icon is the page-identity marker only.

## Reviewer notes — implementation lens

Senior-engineer pass (2026-05-05) focused on layout math, edge cases, a11y, and migration. Design lens is in the section above; no overlap.

**Breakpoint math — the 900px figure is wrong.** The outdent needs `72px (icon box) + --space-md (16px) = 88px` of gutter on the title-block side.

- *Reading layout* (`max-width: 48rem` = 768px): at viewport 900px, gutter per side = (900 - 768) / 2 = 66px. The outdent overflows by ~22px and clips against the viewport edge between roughly 816px and ~960-1000px. Fix: raise the collapse breakpoint to ~1000px, **or** (preferred) switch to a container query (next bullet).
- *Wide layout* (`max-width: 72rem` = 1152px): the outdent does not fit until viewport ~1328px. Common laptops (1280, 1366) do not clear it. The plan's "Open question" on line 74 has a definitive answer: **wide layout should use the inline-stack treatment at all viewport sizes** (or the breakpoint must be raised to ~1340px specifically for wide). Recommendation: ship stack-above for wide; revisit only if a wide page lands on a >1340px reference design.

**Container queries are the right axis.** The constraint is "does the gutter have room," not "is the viewport narrow." Adding `container-type: inline-size` to `<main>` in `Base.astro` (one line) lets `PageHeader` use `@container` queries that adapt to the actual layout (reading vs wide vs bare) without per-page knowledge. Component then doesn't need to read the `layout` prop. Recommended.

**`:has(:empty)` will not work for empty-slot detection.** Two reasons: `:empty` does not match elements containing whitespace text nodes (Astro slot output frequently includes whitespace), and call sites passing nothing still produce a rendered wrapper in some cases. Reliable approach: in `PageHeader.astro` frontmatter, branch on `Astro.slots.has('default')` and conditionally render the rail. No CSS-selector magic.

```astro
const hasMeta = Astro.slots.has('default');
...
{hasMeta && <div class="rail" aria-hidden="true" />}
```

**Index page adoption: prop, not sibling component.** Reusing `PageHeader` with an empty slot leaves the rail dangling and forces every index page to think about crumbs. Cleaner: add `variant?: 'detail' | 'index'` to `PageHeader`. Index variant skips the rail, allows omitted/empty crumbs, and keeps one source of truth. (Pairs with the design-lens reviewer's note about index-page semantic mismatch.)

**Per-row icon rule holds up.** Verified against `ClaimRow.astro` (has `VerdictBadge` in `.badge-col`) and `sources/index.astro` `.source-row` (has `.kind-badge`). The "if a row already has a colored badge, no type icon" rule produces a clean implementation. No new exceptions surfaced.

**A11y / semantics.**
- `ObjectTypeIcon.astro` already sets `aria-hidden="true"` and `focusable="false"`. Good.
- The type label ("Source", etc.) is sighted-only redundancy with the H1 page context. Add `aria-hidden="true"` on the type-label span so screen readers don't announce "Source / [title]" with double framing.
- Rail keeps `aria-hidden="true"` per the prototype. Correct (decorative tether).
- Breadcrumbs already render as `<nav aria-label="Breadcrumb">` via `Breadcrumb.astro`. No change.
- The `<header>` element in `PageHeader.astro` is correct semantics; keep it.

**Migration is low risk; use a verification matrix instead of staged rollout.** Prop API is unchanged (`type`, `crumbs`, `title`, `<slot />`). All 5 detail call sites stay as-is. A feature flag adds complexity with no payoff. Add a manual verification checklist:

| Page type | Short title | Long title | Sparse meta | Rich meta | ~768px | ~1024px | ~1440px |
|-----------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| sources/[slug] | | | | | | | |
| criteria/[slug] (layout=wide) | | | | | | | |
| entities/[slug] | | | | | | | |
| topics/[topic] | | | | | | | |
| claims/[slug] | | | | | | | |

**Other implementation pitfalls.**
- *Rail height vs acceptance criterion.* In the prototype, `.d4-rail` is `flex: 1 1 auto` inside an absolutely-positioned `.d4-icon-outdent` with `top: 0; bottom: 0`. The rail equals `.d4-body` height, which is title + all metadata sections. The plan's acceptance criterion (line 53) says "rail equals height of metadata block." These disagree (the design-lens reviewer flagged this too). Resolve by either tightening the criterion or moving the rail anchor inside the meta block.
- *Long type labels.* The 72px outdent width truncates labels longer than ~10 characters ("Documentation", future labels). Use `width: max-content; min-width: 64px` or constrain `ENTITY_TYPE_LABELS` to short forms.
- *Print stylesheet.* Absolute-positioned outdent often disappears in print. One `@media print` override to fall back to inline-stack. Low priority.
- *Prototype removal.* Step 5 deletes `src/pages/proto/header-designs.astro`. Confirm no docs link to `/proto/header-designs` before deletion.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-05 | claude-opus-4-7 (drafted) | basic | Initial draft based on prototype review session |
| 2026-05-05 | agent (claude-opus-4-7, design lens) | iterated | Added Reviewer notes — design lens. Flagged simpler-fix alternative (`align-items: start`), rail-height contradiction between plan and prototype, badge-loudness dependency the icon's landmark claim rests on, and several smaller items (index-page conflation, three-labels redundancy, token gap, light-theme icon-box visibility, claim-detail verdict-badge competition). No body edits; recommendations parked in notes for the author to triage. |
| 2026-05-05 | agent (claude-opus-4-7, implementation lens) | iterated | Added Reviewer notes — implementation lens. Corrected the 900px breakpoint (reading should be ~1000px; wide should stack-above at all sizes), recommended container queries on `<main>`, replaced `:has(:empty)` with `Astro.slots.has('default')`, recommended a `variant` prop over a sibling index component, added a 5x7 verification matrix, and noted the rail-height/long-label/print-style pitfalls. |
| 2026-05-05 | Brandon + claude-opus-4-7 | iterated | Resolved both reviewer questions: (1) intent is "icon-as-gutter-landmark", "Why" rewritten to say so explicitly; (2) badge demotion folded in as a prerequisite step (`.kind-badge` and `.source-type-badge` to tinted chips). Mechanical corrections from the implementation lens applied to the plan body: container queries on `<main>`, `Astro.slots.has('default')` for empty-meta, `variant: 'detail'\|'index'` prop, resolved breakpoints (reading collapse ~1000px, wide always inline-stack), aria-hidden on type-label, verification matrix in implementation order, rail-height criterion tightened to match prototype, light-theme and token-gap risks promoted from notes into the Risks section. Reviewer notes left intact as audit trail. |
