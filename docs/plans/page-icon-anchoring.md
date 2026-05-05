# Page icon anchoring — outdented icon + rail rollout

Roll out the prototype Design 4 (icon outdented into the page gutter, tied to the metadata block by a hairline vertical rail) to every page that has a page-identity icon. Extend the same pattern, with appropriate adjustments, to index pages and to selected in-page lists.

Reference prototype: `src/pages/proto/header-designs.astro` (`#d4`).

## Why

Diagnosis from prototype review (2026-05-05): the current `.item-meta` icon column floats — the icon is vertically centered against a metadata column whose height varies by page, so it looks anchored to nothing. The outdent + rail pattern places the icon in the page gutter (not competing with the H1) and uses a hairline rule to tether it to the metadata, giving it a stable visual home regardless of how much metadata sits in the right column.

Reference: prior decision on visual hierarchy preserves the H1 as the strongest *informational* element; the icon is the page-identity *landmark*. See conversation 2026-05-05.

## Scope

In scope:

1. Update the shared `PageHeader.astro` to the outdent + rail layout. This rolls the change out to all 5 detail page types in one edit.
2. Introduce a page-type header treatment for index pages so the same icon system anchors list pages.
3. Add small per-row type icons on selected in-page lists where a type icon adds scannability (and does not duplicate an existing verdict badge).
4. Responsive fallback: stack icon above title below ~900px viewport (already specced in prototype).

Out of scope:

- Promoting the icon further (sized increase, colorization beyond current tokens). Decided against in prototype review.
- Removing or restyling source-type / kind badges. Separate concern; track in a follow-up if needed.

## What changes

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
- Icon outdent: 64px box, `Source`-style type label below, hairline rail extending from below the label down to the bottom of the metadata content. Sits at `right: calc(100% + space-md)` of the title block, so it consumes page gutter, not body width.
- Metadata `<slot />` content flows normally inside the body column; no left gutter inside the body.
- Below 900px viewport: outdent collapses to inline (icon + label horizontal, above title); rail is hidden.

Acceptance:

- All 5 detail pages render with icon in gutter on viewports ≥ 900px and stacked above title on narrower viewports.
- Long titles wrap inside the body column without colliding with the icon.
- Rail height equals the height of the metadata block (top of icon to bottom of last metadata row, not extending past it).
- Visual regression: no shift of H1 left edge versus current production layout.

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

Implementation: have each index page's `<h1>` and surrounding header markup adopt `PageHeader` (or a thin index-flavored variant) with `type` set to the listed entity. Index pages currently have no breadcrumb — pass `crumbs={[{label: 'Home', href: '/'}]}` or extend `PageHeader` to accept an empty crumbs array.

Open question: index pages typically use `layout="wide"` (e.g., the criteria index is wide). The outdent gutter is narrower at wider body widths. Confirm during implementation that the icon still fits in the gutter at the `wide` layout's viewport sizes; if not, fall back to the inline-stack treatment above the H1.

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

1. Refactor `PageHeader.astro` to the outdent + rail pattern. Verify all 5 detail page types render correctly on dev. (No call-site changes.)
2. Visual QA pass on detail pages with realistic content: long titles, sparse metadata (e.g., topic detail), rich metadata (source detail).
3. Adopt `PageHeader` (or index variant) on the 7 index pages listed above. Resolve `wide` layout fit; fall back to stack-above if outdent doesn't clear.
4. Per-row icons: audit each list component, apply only where the rule above says so. One row component at a time; visual diff before/after.
5. Remove `src/pages/proto/header-designs.astro` once the rollout is committed.

## Risks

- **Wide-layout indexes:** The outdent assumes a centered narrow body. On `wide` layouts the gutter is smaller and the icon may not fit. Mitigation: the responsive stack-above fallback already exists; trigger it for `wide` layouts at all viewport sizes, or raise the breakpoint for those pages.
- **Rail length on title-only pages:** If a page has no metadata `<slot />` content, the rail has nothing to extend toward. Mitigation: hide the rail when the metadata slot is empty (CSS `:has(:empty)` or a Boolean prop on `PageHeader`).
- **Per-row icon overuse:** Adding type icons to every list "because consistency" defeats their purpose. Mitigation: the rule above is conservative; require an explicit reason per list before adding.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-05 | claude-opus-4-7 (drafted) | basic | Initial draft based on prototype review session |
