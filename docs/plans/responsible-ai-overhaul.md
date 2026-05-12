# Plan: responsible-ai page overhaul

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Schema + content migration (existing rows port over) | `[ ] planned` |
| 2 | Matrix component on new schema (no filters, no Ideal) | `[ ] planned` |
| 3 | Content authoring (summary cells, ideal values, new footnote) | `[ ] planned` |
| 4 | Summary table component | `[ ] planned` |
| 5 | Matrix filters (chips, header toggles, reset) | `[ ] planned` |
| 6 | Editorial "Ideal" column | `[ ] planned` |
| 7 | Excluded products + footnotes sections | `[ ] planned` |
| 8 | Frontend design pass | `[ ] planned` |

Theme/contrast styling and a11y are gates folded into each milestone's acceptance criteria, not standalone steps.

### Sequencing rationale

Direct commits to main (no PRs before beta) let this ship in slices. Each numbered step is a landable commit:

1. Migrate frontmatter and schema. Existing rows port over. Page renders equivalently to today.
2. Port the matrix component to the new schema with no behavior change. De-risks the data shape before adding new UI.
3. Author the new editorial content (28 summary strings across 7 products, 48 feature cells for the 3 newly-included products, ~10 ideal values, the Ideal-column footnote). Pure content task, parallelizable with code from step 4 onward.
4. Summary table goes live once its content exists.
5. Filters add the marquee reader value (compare three, hide one group).
6. Ideal column lands last among feature work because it depends on editorial content from step 3 and is the most contestable piece.
7. Excluded products and footnotes are small, grouped together.
8. Design pass after function is locked.

Riskiest piece: step 3 (content authoring) is hidden effort that gates steps 4 and 6. Worth front-loading.

---

## Background

Current state: `src/content/resources/responsible-ai.md` stores a flat list of dimensions in frontmatter; `src/components/ResponsibleAIMatrix.astro` renders a single non-interactive table.

Goal: replace with two tables (a static summary, and a dynamic filterable matrix grouped into 5 categories) backed by structured Markdown frontmatter. Primary use case: compare three products while hiding one feature group. No persistence in v1.

Scope is intentionally limited to one page. The pattern may generalize later but should not be over-abstracted now.

---

## Architecture

### Files touched / added

- `src/content/resources/responsible-ai.md`: frontmatter rewritten
- `src/content.config.ts`: extend `resources` schema for new fields (currently `data: z.unknown().optional()`)
- `src/components/ResponsibleAIMatrix.astro`: full rewrite, becomes the matrix-only component
- `src/components/ResponsibleAISummary.astro`: new
- `src/components/ResponsibleAIFilters.astro`: new (chips + reset, "only" links)
- `src/pages/resources/[...slug].astro`: render summary + body + matrix for `layout: matrix`
- Component-scoped styles inside each `.astro` file; no token changes expected
- `src/styles/tokens.css`: additive only if a new semantic token is needed (e.g., `--color-table-sticky-shadow`)

### Data shape (frontmatter)

```yaml
data:
  lede: "..."
  caption: "..."
  groups:
    - key: environmental
      label: "Environmental"
    - key: models-safety
      label: "Models & AI safety"
    - key: privacy-data
      label: "Privacy & data"
    - key: business
      label: "Business & ownership"
    - key: product-access
      label: "Product & access"
  products:
    - key: greenpt
      name: GreenPT
      url: https://greenpt.ai/
      status: active           # active | excluded
      # excluded_reason omitted when status=active (required iff status=excluded)
      summary:                 # required iff status=active (omit on excluded)
        ai_ethics: "..."             # InlineMd
        financial_transparency: "..."# InlineMd
        environmental: "..."         # InlineMd
        notes: "..."                 # InlineMd (links allowed)
    - key: viro
      name: Viro AI
      url: https://...
      status: excluded
      excluded_reason: "Wraps OpenAI and Anthropic APIs..."
  features:
    - key: renewable-hosting
      label: "Hosted on renewable energy"
      group: environmental
      ideal: { value: "yes", note: "" }   # optional
      cells:
        greenpt: { type: "yes" }
        ecosia:  { type: "no", detail: "..." }   # detail optional on every cell
  footnotes:
    - subject: "..."
      text: "..."
```

Notes:
- Group keys (decided): `environmental | models-safety | privacy-data | business | product-access`.
- `groups` order in frontmatter = render order. Five groups are hard-coded as the *default*, but the renderer reads order from the data, so a sixth can be added by editing the markdown.
- `status: excluded` products are **not rendered** in the matrix columns. They appear in the "Excluded products" section below the matrix.
- `ideal` is optional. Rows without it omit the Ideal cell content (renderer outputs an empty cell with `aria-label="no editorial pick"`).
- `summary.*` fields are short markdown strings, rendered via the existing `InlineMd.astro` component. `InlineMd` renders inline-only (no `<p>` wrap, no block-level markdown): summary strings must be a single inline string, no paragraph breaks. Supports `**bold**`, `[text](url)`, `` `code` ``.
- All cell types from today carry over: `yes | no | no-good | partial | planned | text | unknown | na`. Every cell may carry an optional `detail: string` (free text; today's data uses it on `yes`, `partial`, `no`, `text`, `unknown` cells). Schema must preserve `detail` across the migration or content is silently dropped.

### Collection schema changes

Replace the existing `data` shape for `layout: matrix` in `src/content.config.ts` (currently typed as `z.unknown()`) with a validated schema for `groups`, `products[].status`, `products[].summary`, `features`, `footnotes`. Migration is a single commit: rip-and-replace, no dual-schema transition period.

Schema specifics:
- `data` becomes a layout-specific union. Simplest: extend the `resources` schema with `data: z.unknown().optional()` unchanged at the collection level, and validate the matrix shape inside `[...slug].astro` (or a helper) before passing to the component. Alternative: discriminated union on `layout`. Pick the simpler one; only matrix has structured data today.
- `cells[product]` is `z.object({ type: z.enum([...8 types]), detail: z.string().optional(), footnote: z.string().optional() })`. The `footnote` field is reserved for milestone 7 anchoring (default empty); add it now so the schema doesn't churn.
- `products[]` validation: use `superRefine` to require non-empty `excluded_reason` iff `status === "excluded"`, and require non-empty `summary.{ai_ethics,financial_transparency,environmental,notes}` iff `status === "active"`. (During milestone 1 the `summary` constraint must be relaxed or summary fields stubbed with `""`; tighten it in milestone 3.)
- `summary` is a fixed-keys object, not an array. The four keys (`ai_ethics`, `financial_transparency`, `environmental`, `notes`) are part of the summary-table column contract; making them an array would lose the column-to-field mapping.
- `groups[]` keys constrained to the five decided values via `z.enum`. Adding a sixth requires a code change (schema edit), not just frontmatter.
- `features[].group` must reference an existing `groups[].key`; validate via `superRefine` over the whole `data` payload.

---

## Milestone 1: Schema + content migration

**Status:** `[ ] planned`

The schema flip and the data move ship together as one commit, so the page never sees an invalid frontmatter state.

Steps:
1. Update the `resources` collection schema in `src/content.config.ts` to validate the new `data` shape (`groups`, `products[].status`, `products[].summary` optional and empty at this stage, `features`, `footnotes`).
2. Migrate existing `dimensions[]` to `features[]`; assign each existing row to one of the 5 groups (see Appendix A).
3. Move existing `excluded_products` entries (Viro AI, ChatGPTree, Earthly Insight) into `products[]` as new **active** rows with `status: "active"`. Assign each a slug `key` (e.g., `viro`, `chatgptree`, `earthly-insight`) and a `url` (vendor homepage). The existing `reason` text is preserved by being folded into each product's `summary.notes` cell during milestone 3 (not into `excluded_reason`). The `excluded_products` field is removed from frontmatter; the schema retains the `excluded` status as a capability for future use, but no products carry it at launch.
4. Carry footnotes forward unchanged. Leave `products[].summary` fields empty for now (filled in milestone 3, 7 products total).
5. Leave `ideal` off all rows (filled in milestone 3).

Acceptance:
- `inv build` passes schema validation.
- Page renders with no lost data versus current production (only restructuring).
- No dual-schema compatibility code remains.

---

## Milestone 2: Matrix component on new schema

**Status:** `[ ] planned`

Port `ResponsibleAIMatrix.astro` to read `features[]` (with `group`) instead of `dimensions[]`. No filters, no Ideal column, no sticky behavior yet. Goal: prove the data shape end-to-end without piling new UI on top.

Acceptance:
- Page renders feature-equivalent to today, including `detail` strings on icon cells (e.g., "All but Anthropic" next to a `partial` icon) and `text`-cell content.
- All eight cell types (`yes | no | no-good | partial | planned | text | unknown | na`) render with the same icons and colors as today (see Theme gate for the verdict-token mapping).
- Row grouping (visual section headers per group key) is present using `groups[]` order from frontmatter.
- No JS added; this is a static refactor.

---

## Milestone 3: Content authoring

**Status:** `[ ] planned`

Pure editorial work, gates milestones 4 and 6. Can run in parallel with milestone 2.

Inputs to author (anew, not derived):
- **7 active products** × 4 summary fields (`ai_ethics`, `financial_transparency`, `environmental`, `notes`) = 28 short markdown strings. The 4 existing products (GreenPT, Ecosia AI, Euria, TreadLightly AI) plus the 3 newly-included products (Viro AI, ChatGPTree, Earthly Insight). Tone matches existing claim-page copy; keep each cell ≤ ~25 words.
  - For the 3 newly-included products: each product's `summary.notes` carries forward the existing `excluded_products[].reason` prose as a starting point, edited for the active-row context.
- **16 feature cells × 3 new products = 48 new matrix cells** for Viro AI, ChatGPTree, and Earthly Insight. Primary source: `docs/reports/Sustainable AI Chatbot Claims_ Verifica...ro AI, ChatGPTree, and Earthly Insight.pdf`; cross-reference with vendor sites where the PDF is silent. Where information isn't readily available, use cell type `unknown` (blanks are fine; don't fabricate).
- `ideal` values for the rows marked "yes" in Appendix A (approximately 8 rows). Each is a `{ value, note? }` pair. `ideal` carries no source citation; citations stay on product cells (Ideal is editorial).
- One new footnote: the editorial-pick explainer ("Ideal is Dangerous Robot's editorial judgment, not a vendor claim...").

Acceptance:
- All 28 summary cells written and committed to `responsible-ai.md`.
- 48 new feature cells written for the 3 newly-included products; cells with no available data use `unknown`.
- Ideal values present on every row Appendix A flags `yes`.
- Footnote drafted and committed (rendered in milestone 7).

---

## Milestone 4: Summary table component

**Status:** `[ ] planned`

`ResponsibleAISummary.astro`:
- Renders a table: rows = active products, columns = `Product`, `AI ethics`, `Financial transparency`, `Environmental`, `Notes`.
- Each cell after `Product` is `<InlineMd>` of the corresponding `products[].summary.*` field.
- Product cell links to `products[].url` with `rel="noopener noreferrer"` and `target="_blank"`.
- No interactivity. Static HTML.
- Caption: `<caption>` element with summary text for screen readers.

Mobile: collapses to a stack of definition lists below ~640px (`dl` per product). One table, two presentations via CSS only: no JS, no duplicate markup.

Acceptance:
- Renders 7 product rows with all 28 summary cells populated.
- Validates a11y gate (see below).
- Stacks cleanly at 375px viewport.

---

## Milestone 5: Matrix filters (and sticky columns)

**Status:** `[ ] planned`

Adds filter chips, header-click toggles, sticky Feature column, and the horizontal-scroll region to the matrix from milestone 2. Ideal column still absent.

`ResponsibleAIMatrix.astro`:

Markup:
```html
<section class="ra-matrix">
  <ResponsibleAIFilters ... />
  <div class="ra-matrix__scroll" role="region" aria-label="Feature comparison matrix" tabindex="0">
    <table>
      <thead>
        <tr>
          <th scope="col">Feature</th>
          <th scope="col">Ideal</th>
          <th scope="col"><button>...product name...</button></th>
          ...
        </tr>
      </thead>
      <tbody data-group="environmental">
        <tr class="ra-group-header"><th colspan="N"><button aria-expanded="true">Environmental</button></th></tr>
        <tr><th scope="row">Feature label</th> <td>Ideal cell</td> <td>...product cells...</td></tr>
        ...
      </tbody>
      ...
    </table>
  </div>
</section>
```

Sticky behavior:
- `thead th { position: sticky; top: 0; z-index: 2; }`
- `tbody th[scope="row"] { position: sticky; left: 0; z-index: 2; }` — Feature column is sticky-left in this milestone. Ideal column becomes sticky in milestone 6 with `left: var(--ra-feature-col-width)`.
- `--ra-feature-col-width` is declared on the matrix root (e.g., `14rem`, matching today's `.dim-col`). Fixed value, not measured at runtime, to avoid layout-after-paint flicker.
- Top-left intersection (sticky row header inside sticky thead) needs `z-index: 3` and an opaque `background: var(--color-bg)`. All sticky cells require opaque backgrounds (sticky doesn't lift cells out of the table; the row scrolls under them, so any transparent sticky cell will show the row through it).
- Group-header rows (`<tr class="ra-group-header">`) also use `position: sticky; top: 0` if we want them to pin at scroll; for v1 they do **not** pin (scroll past them). Keep group headers non-sticky to avoid double-sticky z-index complexity.
- The matrix lives inside a horizontal-scroll container; vertical scroll is page-level. `.ra-matrix__scroll { overflow-x: auto; }`. Astro's scoped CSS does not interfere with `position: sticky`; sticky positions against the nearest scroll container.

Filter behavior (vanilla JS inside the component, no framework):
- Product chip click → toggle `[data-hidden-product="<key>"]` on the root; CSS hides matching cells.
- Product chip "(only)" link → set all other products to hidden.
- Group chip click → toggle `[data-hidden-group="<key>"]`; CSS hides the group's `<tbody>`.
- Group "(only)" link → hide all other groups.
- Reset button → clear all hidden state.
- Column header click → same as product chip toggle (with `aria-pressed`).
- Group header click → same as group chip toggle (with `aria-expanded`).

State model: a single Set of hidden product keys + a single Set of hidden group keys, reflected as multiple attributes on the matrix root. All visibility is driven by CSS attribute selectors — no DOM rewriting. Easier to test, less likely to glitch.

Group-collapse DOM shape: **one `<tbody>` per group**. The group-header `<tr>` is the first row of its tbody; the toggle button writes `[data-collapsed]` on the tbody, and CSS hides every non-first row within. This keeps `scope="rowgroup"` semantically correct (one tbody = one rowgroup).

Text-cell column width: column width is capped regardless of filter state. When a single product is "only"-filtered, text cells do **not** expand to fill the wider table. Keeps reflow consistent across filter changes. Cap via `max-width` on the product `<td>` plus `word-break: break-word`.

Acceptance:
- All filter controls and header-click toggles agree on state.
- "Show all" resets to default.
- Hidden products: both the column `<th data-product-key="<k>"]` AND every `<td data-product-key="<k>"]` are hidden. CSS selector: `.ra-matrix[data-hidden-product~="<k>"] [data-product-key="<k>"] { display: none; }` (use `~=` on a space-separated attribute list of hidden keys, written by JS).
- Hidden groups: `tbody[data-group="<k>"]` collapses fully (`display: none`).
- Group-header `<th colspan>` does not need recalculation when columns hide; `colspan` larger than visible columns extends to the table edge in all browsers. Set `colspan` to the total column count rendered (Feature + Ideal + N products) and leave it.
- Keyboard-operable end to end (a11y gate below).
- Sticky Feature column survives horizontal scroll without focus-ring occlusion. Focus ring uses `outline-offset: 3px` (matches site default); verify it's not clipped by `overflow: hidden` on any ancestor.

---

## Milestone 6: Editorial "Ideal" column

**Status:** `[ ] planned`

- Second column from left, after Feature label. Sticky-left.
- Each cell renders the same icon set used in product cells (`yes/no/partial/...`), or empty for rows without `ideal`.
- Optional `ideal.note` shown as a tooltip / `<details>` toggle on the cell.
- Header text: `Ideal` with a `<sup>` footnote marker linking to a dedicated footnote.
- The footnote (added to the `footnotes[]` block via the migration step) reads, approximately:
  > "Ideal" is an editorial judgment by Dangerous Robot, not a vendor claim. It marks the value that, in our view, is best for this row. For some rows (e.g. lists of models) there's no single best answer.
- Color treatment: the Ideal column gets a faint background tint using `--color-surface` (or `--color-code-bg`) to signal "different kind of column" without being loud. (`--color-surface-alt` is not a token in this codebase.)

Acceptance:
- Every Appendix-A row marked `yes` shows an Ideal icon.
- Rows without `ideal` render a visually-empty cell containing `<span class="sr-only">no editorial pick</span>` (preferred over `aria-label` on an empty `<td>`, which some screen readers ignore).
- Ideal column is sticky-left alongside Feature column.
- Ideal-explainer footnote is referenced from the column header.

---

## Milestone 7: Excluded products + footnotes sections

**Status:** `[ ] planned`

Excluded products block below the matrix:
- Heading: "Why these aren't included".
- For each `products[]` with `status: excluded`: name (linked) + `excluded_reason`.
- No icons, no table. Plain prose list.
- Hidden when no excluded products exist. **At launch this section will not render**, since all currently-tracked products are active. The block is built as a capability for future use.

Footnotes block below excluded products:
- Heading: "Footnotes".
- `<ol>` of footnotes, each with an `id` so cells with markers can `<a href="#fn-...">` deep-link. Ship anchor IDs in this milestone even though no cells currently reference them; this enables per-cell markers later without re-migration.
- Footnote backreference links (`↩`) jump back to the cell.
- The Ideal-column explainer footnote (authored in milestone 3) is rendered here.

Acceptance:
- Excluded-products block renders only when at least one `products[]` entry has `status: "excluded"`; at launch (no excluded products) the block emits no output.
- All existing footnotes plus the new editorial-pick footnote render in order.
- Anchor links from any cell footnote marker round-trip to the list item and back.

---

## Gate: Theme + contrast styling

Applies to every component above. Not a standalone milestone; verify alongside each component's acceptance.

The site has four theme axes set on `<html>` by `A11yControl.astro`:
- `data-theme="dark" | "light"` (default dark; "system" follows `prefers-color-scheme`)
- `data-contrast="normal" | "high"`
- `data-font-size="small" | "medium" | "large"` (handled globally)
- `data-motion="on" | "reduce"` (any transition/animation must respect this — wrap in `:where(html:not([data-motion="reduce"])) ...` or honor `prefers-reduced-motion`)

All component CSS uses tokens from `src/styles/tokens.css`. No raw hex. Tokens `--color-surface-alt` and `--color-focus` do **not** exist — don't reference them. Focus rings reuse `--color-accent` (see `src/styles/global.css:105-106`).

Required behavior (token names verified against `tokens.css`):

| Aspect | Dark / normal | Light / normal | High contrast (both themes) |
|---|---|---|---|
| Cell icons (matches existing matrix) | `yes` → `--color-verdict-true`; `no` → `--color-text-muted`; `no-good` → `--color-verdict-false`; `partial` → `--color-verdict-mixed`; `planned` → `--color-kind-report`; `unknown` → `--color-text-faint` | same tokens (light variants auto-applied by tokens.css) | high-contrast overrides on the same verdict tokens (already in tokens.css) |
| Sticky cell background | `--color-bg` (opaque, never semi-transparent) | `--color-bg` | `--color-bg` |
| Sticky cell border-shadow | subtle 1px right/bottom border via `--color-border` (prefer `border-right` over `box-shadow` — sticky `box-shadow` can be clipped by overflow ancestors) | same | thicker `--color-border` value already applied via high-contrast token |
| Ideal column tint | `--color-surface` (exists) or `--color-code-bg` (exists). Pick one, not both. | same | tint dropped in high-contrast: use `border-left`/`border-right` of `--color-border` instead |
| Active filter chip | filled `--color-accent` | filled `--color-accent` | adds an inset outline for redundancy with color |
| Focus rings | `outline: 2px solid var(--color-accent); outline-offset: 3px` (matches global.css default) | same | `outline-width: 3px` in high-contrast |
| Excluded-product link | normal link color | same | underline always (not only on hover) |

CSS strategy:
- Component-scoped CSS in each `.astro` file.
- High-contrast deltas via `[data-contrast="high"] .ra-matrix ...` selectors near each rule, not in a separate block — keeps related styles co-located.
- No `prefers-contrast` media query: the global `A11yControl` already maps user preference to `data-contrast`.

Verification: visually exercise all four combinations (dark/normal, dark/high, light/normal, light/high) in the running dev server.

---

## Gate: A11y

Applies to every component above. Not a standalone milestone; each component's acceptance includes the relevant items from this checklist.

Conformance target: WCAG 2.2 AA, plus the project's existing high-contrast and font-size controls.

Checklist:

**Semantics**
- Each `<table>` has a `<caption>` (sr-only). Caption text also names the icon vocabulary so icons are not the sole carrier of meaning.
- Row headers use `<th scope="row">`, column headers `<th scope="col">`.
- Group rows use a single `<th colspan>` with `scope="rowgroup"`. (`scope="rowgroup"` is the correct HTML5 value here; AT support is uneven, so the visible button text inside the `<th>` carries the group label as well.)
- The collapse button lives inside the group-header `<th>`: `<th colspan="N" scope="rowgroup"><button type="button" aria-expanded="true" aria-controls="ra-group-<key>-body">Group label</button></th>`. The button toggles `display: none` on a sibling `<tbody>` (or a wrapper around the group's data rows) — note: a `<th colspan>` group header that *lives in the same `<tbody>`* as its data rows means `aria-controls` targets the tbody by id, and "collapsing" means hiding sibling rows, not the header row. Simplest pattern: one `<tbody>` per group, group-header `<tr>` is the first row inside that tbody, button toggles `[data-collapsed]` on the tbody, CSS hides all non-header rows when `[data-collapsed]`.
- Filter chips are `<button type="button" aria-pressed="...">`.
- Column header toggles are `<button aria-pressed>`; group header toggles are `<button aria-expanded>`.
- The horizontal scroll region has `role="region"`, an `aria-label`, and `tabindex="0"` so keyboard users can scroll it.

**Keyboard**
- Tab order follows DOM order: filter chips → matrix scroll region (single tab stop on the region itself) → column header buttons (visible only) → group header buttons → cell links (no tab stops on plain cells). Verify the DOM is authored in this order; sticky positioning does not reorder tab focus.
- Hidden buttons (column header for a hidden product) must be removed from tab order. Since visibility is driven by `display: none` via CSS attribute selectors, `display: none` already removes from tab order — no extra `tabindex=-1` handling needed.
- Enter / Space activates buttons; Esc on a focused chip does nothing special (no modals).
- Arrow keys do **not** navigate cells in v1. (Documented as future work.)

**Screen reader announcements**
- Icon cells have `aria-label` (e.g., "Yes", "No", "Partial — detail text").
- Toggling a column or group updates `aria-pressed` / `aria-expanded`. No `aria-live` region needed; state is self-evident from the controls.
- Reset button is `<button>` with accessible name "Show all products and groups".

**Color and contrast**
- All text ≥ 4.5:1 in every theme/contrast combo. Verify with axe-devtools in dev.
- Icons never the only carrier of meaning — every icon cell pairs with `aria-label` and the table caption explains what icons mean.

**Reduced motion**
- Honor `[data-motion="reduce"]` on `<html>` (set by `A11yControl.astro`) in addition to `prefers-reduced-motion`. Pattern: `:where(html[data-motion="on"]) .ra-chip { transition: ... }`. No animations on filter toggles, collapse expand, or chip presses by default; if any are added, gate both on `data-motion="on"` and `prefers-reduced-motion: no-preference`.

**Focus**
- Visible focus on every interactive element.
- Sticky cells must not occlude focus rings — verify the focus ring on a row's first cell is visible when that cell is sticky-left.

Tooling:
- Manual: NVDA + Firefox, VoiceOver + Safari.
- Automated: axe-core run on the rendered page; aim for zero violations.

---

## Milestone 8: Frontend design pass

**Status:** `[ ] planned`

Decision: design pass runs **after** functional implementation lands (milestones 1-7 complete), not interleaved. Invoke the `frontend-design` skill to:
- Refine the filter-chip styling and grouping
- Sharpen the visual treatment of the Ideal column so its editorial nature is obvious
- Tighten the summary table's information hierarchy
- Validate the excluded-products section feels like an annex, not a fifth-tier feature

Constraints for the design pass:
- Stay inside the existing token palette; no new color literals.
- Don't introduce framework islands (Astro stays SSG).
- Keep table-heavy layouts; the page is comparison-first.
- Print stylesheet not in scope.

Acceptance:
- No new tokens added unless reused elsewhere.
- All four theme/contrast combos still pass the gate.
- No new JS dependencies introduced.

---

## Out of scope (deferred)

- URL or localStorage persistence of filter state
- Search across feature labels
- Sort, export, or share-link of the matrix
- Multi-page split (one product per file)
- Schema.org structured data for the matrix itself (keep existing `buildResourceSchema`)
- Print stylesheet
- Per-cell footnote inline rendering (cells reference footnotes by anchor today; can revisit)

---

## Resolved decisions

All open questions resolved 2026-05-12. Recorded here so future implementers can see why specific shapes were chosen.

1. **Group keys**: `environmental | models-safety | privacy-data | business | product-access`. Locked as-is.
2. **Appendix A row mapping**: approved as-is.
3. **Frontend design timing**: after functional implementation lands (milestone 8).
4. **Footnote anchor scheme**: ship anchor `id`s in milestone 7 even before cells reference them. Enables per-cell markers later without re-migration.
5. **Ideal-row source attribution**: keep citations on product cells; Ideal stays editorial (no source field on `ideal`).
6. **Excluded products section**: the 3 previously-excluded products (Viro AI, ChatGPTree, Earthly Insight) become **active** products in the matrix. The excluded-products section/schema remains as a capability but launches with no entries.
7. **Newly-included product sourcing**: PDF in `docs/reports/` plus vendor sites; allow `unknown` cells for any feature where info isn't readily available.
8. **`reason` text disposition**: existing `excluded_products[].reason` text folds into the new active products' `summary.notes` (edited for context).
9. **Text-cell column width under "only" filter**: cap regardless of filter state for consistent reflow.
10. **Group-collapse anatomy**: one `<tbody>` per group; group-header `<tr>` is first row; toggle `[data-collapsed]` on the tbody; CSS hides non-first rows. Keeps `scope="rowgroup"` correct.
11. **Ideal-cell empty state**: visually-hidden `<span class="sr-only">no editorial pick</span>` (not `aria-label` on an empty `<td>`).

---

## Appendix A: Group assignment for existing rows (approved)

| Existing label | Proposed group | Has `ideal`? |
|---|---|---|
| Hosted on renewable energy | environmental | yes (yes) |
| Real-time energy display | environmental | yes (yes) |
| No image generation | environmental | yes (yes) |
| Image and document analysis | product-access | no (text-y) |
| Models | models-safety | no (text) |
| Open-source models only | models-safety | yes (yes) |
| Data used for training | privacy-data | yes (no-good) |
| Published AI limitations | models-safety | yes (yes) |
| Data jurisdiction | privacy-data | no (text) |
| Web search | product-access | no (yes? optional) |
| Free tier | product-access | yes (yes) |
| Pricing (paid tier) | business | no (text) |
| Accessibility | product-access | yes (yes) |
| Maturity | product-access | no (text) |
| Corporate structure | business | no (text) |
| Financial transparency | business | yes (yes) |
