# Plan: Restructure dangerousrobot.org and add /resources/ section

**Status**: Ready to start
**Created**: 2026-05-09

## Summary

This plan covers two coupled changes:

1. **Site restructure.** Move the existing research-tool's subpages from top-level URLs (`/claims`, `/entities`, `/companies`, `/products`, `/subjects`, `/topics`, `/sources`, `/criteria`) under a `/research/` prefix. Move `/faq` to `/research/` itself, prepended with a short explainer that introduces the research tool. The site root `/` keeps its current claim-scatter landing.
2. **New `/resources/` section.** Migrate five pages from the parallax-ai Next.js project (`/robot`, `/robot/should-i`, `/robot/ai-safety`, `/robot/turn-off-ai`, `/robot/responsible-ai`) into a new section at `/resources/`. Visual flavor (background wallpapers, paper-grain texture) comes from the source; chrome (nav, footer, tokens, focus styles, theme switching, typography) comes from this site.

The resources section is conceptually "Dangerous Robot for humans" (decision tools, comparison articles, reference guides). The research tool is "Dangerous Robot for assessors" (the structured claim/source database). The site root `/` is the research-tool's landing today; whether it should change later is out of scope here.

## Final URL layout

| Path | Content | Source |
|---|---|---|
| `/` | Research-tool landing (claim scatter) | unchanged |
| `/research/` | Tool explainer + FAQ | new explainer text + relocated `/faq` content |
| `/research/claims/` and `/claims/<slug>` | Claims index and detail | moved from `/claims` |
| `/research/entities/<slug>` | Entity detail | moved from `/entities` |
| `/research/companies/`, `/products/`, `/subjects/` | Entity-type indexes | moved from top-level |
| `/research/topics/` and `/topics/<slug>` | Topic index and detail | moved from top-level |
| `/research/sources/` and `/sources/<slug>` | Source index and detail | moved from top-level |
| `/research/criteria/` and `/criteria/<slug>` | Criteria index and detail | moved from top-level |
| `/resources/` | Section hub | new |
| `/resources/should-i` | Decision tree | new (port of source `/robot/should-i`) |
| `/resources/ai-safety` | FLI AI Safety Index article | new (port of source `/robot/ai-safety`) |
| `/resources/turn-off-ai` | Step-by-step guide | new (port of source `/robot/turn-off-ai`) |
| `/resources/responsible-ai` | Comparison matrix | new (port of source `/robot/responsible-ai`) |
| `/values`, `/credits` | unchanged | |
| `/faq` | redirect → `/research/` | new redirect |
| `/claims/*`, `/entities/*`, etc. | redirect → `/research/*` | new redirects |

Redirects implemented via Astro's `redirects` config (`astro.config.ts`). Astro emits these as static HTML pages with `<meta http-equiv="refresh">`, not HTTP 301s (GitHub Pages cannot serve real 301s). For alpha this is acceptable; full SEO consolidation would require fronting the site with Cloudflare. All preserved permanently.

## Decisions resolved

| Decision | Resolution |
|---|---|
| Section URL | `/resources/` (collection name `resources`, content dir `src/content/resources/`) |
| Site root `/` | Unchanged for now; remains research-tool landing |
| `/research/` | Hosts FAQ content with a new explainer block prepended (large hero section: "What this tool is, what the verdicts mean, how to read a claim page") |
| Old URLs (`/faq`, `/claims`, `/entities`, etc.) | Redirect to new `/research/*` paths |
| Icon library | Add `lucide-astro` dependency. Used in the responsible-ai matrix and possibly elsewhere. |
| `should-i` decision tree | Vanilla JS Astro client script. No UI framework added. Time-box to one work session; defer to UNSCHEDULED if it overruns. |
| Page bodies | Mixed: markdown for prose, Astro components for structured data. `data` payload in frontmatter for matrix and guide layouts. |
| Hub page (`/resources/`) | Astro page (not a collection entry). Lists collection entries plus external "Further reading" resources from the source `/robot` page. |
| Font | Reuse existing site tokens (`--font-heading` Georgia). Don't load Rokkitt. |
| Theme | Reuse existing site tokens. Don't import `DR_COLORS` or Tailwind v4 token overrides. |
| Topics taxonomy | Separate, smaller enum scoped to `resources` collection: `ai-literacy`, `ai-safety`, `consumer-guide`, `responsible-ai` |
| Article freshness model | Articles treated as static reference (`pubDate` only). Embedded "living" data carries its own dates: per-platform `last_verified` in `turn-off-ai`, optional `last_checked` on `further_reading` entries. Expose a `dateModified` JSON-LD field as the max of those if SEO benefits; otherwise omit. Low priority to optimize. |
| Indexing | Visible to search engines from day one. Not alpha-flagged. |
| Commits | Small-to-medium commits direct to main. No PR workflow. |

## Non-goals (explicitly deferred)

| Deferred | Notes |
|---|---|
| Rethinking the `/` landing | Out of scope. Stays as research-tool landing. |
| Search/filter on resources hub | Five entries, static list is fine |
| Comments | Out of scope |
| Author profiles | Single-author |
| RSS feed | Section is small and not chronological |
| Tailwind utility classes | All styles rewritten in vanilla CSS using site tokens |
| `DR_COLORS` palette | Site tokens only |
| Lightbox library | Native `<dialog>` element |
| Sub-nav inside `/research/` | Keep flat top-level nav for now (with URLs updated to `/research/*`). Sub-nav refactor is a follow-up. |

---

## Architecture

### 1. Astro redirects config

**File: `astro.config.ts`** (edit). Add a `redirects` map for the eight moved sections plus FAQ.

```ts
export default defineConfig({
  site: "https://dangerousrobot.org",
  trailingSlash: "never",
  redirects: {
    "/faq": "/research",
    "/claims": "/research/claims",
    "/claims/[...slug]": "/research/claims/[...slug]",
    "/entities/[...slug]": "/research/entities/[...slug]",
    "/companies": "/research/companies",
    "/products": "/research/products",
    "/subjects": "/research/subjects",
    "/topics": "/research/topics",
    "/topics/[topic]": "/research/topics/[topic]",
    "/sources": "/research/sources",
    "/sources/[...slug]": "/research/sources/[...slug]",
    "/criteria": "/research/criteria",
    "/criteria/[slug]": "/research/criteria/[slug]",
  },
  // existing sitemap config below
});
```

### 2. Page file moves (research subpages)

Move these files; update internal links wherever they reference the old URLs.

| From | To |
|---|---|
| `src/pages/claims/index.astro` | `src/pages/research/claims/index.astro` |
| `src/pages/claims/[...slug].astro` | `src/pages/research/claims/[...slug].astro` |
| `src/pages/entities/[...slug].astro` | `src/pages/research/entities/[...slug].astro` |
| `src/pages/companies/index.astro` | `src/pages/research/companies/index.astro` |
| `src/pages/products/index.astro` | `src/pages/research/products/index.astro` |
| `src/pages/subjects/index.astro` | `src/pages/research/subjects/index.astro` |
| `src/pages/topics/index.astro` | `src/pages/research/topics/index.astro` |
| `src/pages/topics/[topic].astro` | `src/pages/research/topics/[topic].astro` |
| `src/pages/sources/index.astro` | `src/pages/research/sources/index.astro` |
| `src/pages/sources/[...slug].astro` | `src/pages/research/sources/[...slug].astro` |
| `src/pages/criteria/index.astro` | `src/pages/research/criteria/index.astro` |
| `src/pages/criteria/[slug].astro` | `src/pages/research/criteria/[slug].astro` |
| `src/pages/faq/index.astro` | content folded into new `src/pages/research/index.astro`; old file deleted |

Internal link updates: there is no shared URL-builder today; URLs are hardcoded inline at each callsite. Either introduce `src/lib/urls.ts` with helpers (`claimUrl(slug)`, `entityUrl(type, slug)`, etc.) and route all callsites through it, or grep-and-replace at the literal callsites. Known callsites that hardcode old prefixes:

- `src/components/EntityCard.astro` (template literal `/entities/${typeSegment}/${slug}`)
- `src/components/ClaimRow.astro` (`/claims/${id}`)
- `src/components/SourceRow.astro`, `src/components/CriteriaMatrix.astro` (verify during the pass)
- `src/lib/entityTypes.ts` (top-level `/companies`, `/products`, `/entities/...`)
- `src/layouts/Base.astro` nav `<ul>` and footer link `/faq#methodology`
- `src/pages/404.astro` fallback nav (eight stale links: companies/products/topics/claims/sources/criteria/faq)
- `Breadcrumb.astro` itself takes caller-supplied `crumbs[].href`, so callers, not the component, are the surface to update

### 3. New research index

**File: `src/pages/research/index.astro`** (new). Composed of:

- A hero block with `--font-display` heading, subhead. Content like "How this site works", "What the verdicts mean", "How to read a claim page", "What's in alpha". This is the "explainer" the user asked for.
- Below, the existing FAQ content (`<details>/<summary>` disclosure blocks, FAQPage JSON-LD).

Wraps in `Base.astro` with `layout="reading"`. Title "How this works | Dangerous Robot Research" or similar.

Anchor preservation: the existing footer link points to `/faq#methodology`. Audit the current `<h2 id="...">` IDs in `src/pages/faq/index.astro` and either preserve them on the new page or update the footer link target in the same commit so the deep link survives.

### 4. Resources content collection

**File: `src/content.config.ts`** (edit). Add a `resources` collection alongside the existing four.

```ts
const resources = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'src/content/resources' }),
  schema: z.object({
    title: z.string(),
    description: z.string().max(200),
    pubDate: z.coerce.date(),
    layout: z.enum(['article', 'matrix', 'guide', 'tool']).default('article'),
    wallpaper: z.enum(['default', 'ai-safety', 'responsible-ai', 'none']).default('default'),
    topics: z.array(z.enum([
      'ai-literacy', 'ai-safety', 'consumer-guide', 'responsible-ai',
    ])).min(1).max(3),
    /** Layout-specific structured payload. Validated per-layout at render time. */
    data: z.unknown().optional(),
    noindex: z.boolean().default(false),
    /** External resources to surface with the entry on the hub page. */
    further_reading: z.array(z.object({
      title: z.string(),
      url: z.string().url(),
      publisher: z.string().optional(),
      last_checked: z.coerce.date().optional(),
    })).optional(),
  }),
});

export const collections = { sources, claims, entities, criteria, resources };
```

Content lives in `src/content/resources/`. Boundary: research content stays in `research/`; resources are editorial and live in `src/content/`.

### 5. Routing for /resources/

| Path | File | Purpose |
|---|---|---|
| `/resources` | `src/pages/resources/index.astro` | Section hub |
| `/resources/<slug>` | `src/pages/resources/[...slug].astro` | Detail route, dispatches by `data.layout` |

Detail route dispatch:

- `article` → `<ResourcePage>` with rendered Markdown body
- `matrix` → `<ResourcePage>` containing `<ResponsibleAIMatrix data={entry.data.data} />`
- `guide` → `<ResourcePage>` containing `<TurnOffGuide data={entry.data.data} />`
- `tool` → `<ResourcePage>` containing `<ShouldIDecisionTree data={entry.data.data} />` (or 404 if deferred)

Each layout still accepts a Markdown body slot for prose intro/outro.

### 6. Visual blending: layouts and styles

**File: `src/layouts/ResourcePage.astro`** (new). Wraps `Base.astro`, adds:

- Fixed-position wallpaper layer (`<Wallpaper variant={frontmatter.wallpaper}>`), bottom-right, opacity 0.06, CSS `mask-image: linear-gradient(...)` gradient mask, behind content.
- Paper-grain texture overlay (`<PaperGrain>`), SVG data-URI noise, very low opacity, mix-blend-mode.
- Hero block: large display heading, optional subhead.
- Breadcrumb (Home / Resources / <Title>) using existing `Breadcrumb.astro`.

Both decorative layers honor `prefers-reduced-motion` and `[data-motion="reduce"]`.

Wallpapers (copy from parallax-ai source `public/images/`):

| Variant | Source file | Destination |
|---|---|---|
| `default` | `dr-wallpaper.svg` | `public/resources/wallpapers/default.svg` |
| `ai-safety` | `dr-wallpaper-ai-safety.svg` | `public/resources/wallpapers/ai-safety.svg` |
| `responsible-ai` | `dr-wallpaper-responsible-ai.png` | `public/resources/wallpapers/responsible-ai.png` |
| `none` | — | (no wallpaper layer) |

Theme-aware: SVG wallpapers get `filter: invert(1)` under `[data-theme="dark"]`. The PNG ships as-is; if it inverts poorly, ship `responsible-ai-dark.png` and switch via CSS.

**File: `src/styles/resources.css`** (new), scoped to `.resources-page`. Holds:

- `.resources-wallpaper`: positioning, mask, theme-aware filter, motion-reduce override
- `.resources-grain`: paper-texture overlay
- `.resources-hero`: display heading sizing
- `.resources-pill-nav`: in-page section navigation (used by `guide` and `matrix`)
- `.resources-callout`: left-accent callout boxes
- `.resources-matrix-cell-*`: state styling using existing tokens (`--color-verdict-*`, `--color-text-muted`, `--color-text-faint`)
- `.resources-details`: nicer styling for `<details>` footnote groups

Imported only by `ResourcePage.astro` and the hub.

### 7. New components

| File | Used by | Notes |
|---|---|---|
| `src/layouts/ResourcePage.astro` | All `/resources/*` detail pages and the hub | Wraps `Base.astro` (`layout="reading"` or `"wide"`) |
| `src/components/Wallpaper.astro` | `ResourcePage.astro` | Renders wallpaper layer based on prop |
| `src/components/PaperGrain.astro` | `ResourcePage.astro` | Inline SVG data-URI noise overlay |
| `src/components/Lightbox.astro` | `ai-safety` entry | Native `<dialog>`, focus trap, ESC-to-close |
| `src/components/ResponsibleAIMatrix.astro` | `responsible-ai` entry | Reads `data.data` (products, dimensions, cells, footnotes, excluded products) |
| `src/components/TurnOffGuide.astro` | `turn-off-ai` entry | Reads `data.data` (PLATFORMS, FURTHER_READING). Renders pill nav, per-platform sections with `last_verified`, callouts, FAQ JSON-LD |
| `src/components/ShouldIDecisionTree.astro` | `should-i` entry | Vanilla `<script>` (module scope). Questions, lens picker, scoring, history, focus management |

### 8. Icons

Add `lucide-astro` to dependencies. Used by:

- `ResponsibleAIMatrix.astro`: Check, X, Minus, HelpCircle, ArrowUp, ExternalLink
- `TurnOffGuide.astro`: ArrowUp, ExternalLink
- Possibly elsewhere if useful

### 9. JSON-LD

Article schema on each detail page; FAQ schema on `turn-off-ai` and on the new `/research/` index. Implement as small inline templates per layout component (matches existing `Base.astro` Organization schema pattern). No util library needed.

```astro
<script type="application/ld+json" set:html={JSON.stringify({
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": entry.data.title,
  "description": entry.data.description,
  "datePublished": entry.data.pubDate.toISOString(),
  "author": { "@type": "Organization", "name": "Dangerous Robot" },
})} />
```

If exposing the freshest `last_verified` as `dateModified` is easy (it is for `turn-off-ai`), do so. Skip if it complicates the template.

### 10. Navigation

**File: `src/layouts/Base.astro`** (edit). Replace the current nav `<ul>` with the updated link set. New top-level entries:

```astro
<ul class="nav-links" id="nav-links">
  <li><a href="/research">Research</a></li>
  <li><a href="/research/subjects">Subjects</a></li>
  <li><a href="/research/companies">Companies</a></li>
  <li><a href="/research/products">Products</a></li>
  <li><a href="/research/topics">Topics</a></li>
  <li><a href="/research/claims">Claims</a></li>
  <li><a href="/research/sources">Sources</a></li>
  <li><a href="/research/criteria">Criteria</a></li>
  <li><a href="/resources">Resources</a></li>
</ul>
```

Nine links. Mobile breakpoint already collapses to hamburger ≤768px, no change needed. The `/faq` link is gone (now folded into `/research/`).

If the nine-link main nav feels crowded, a follow-up plan can collapse the seven research subpages under a "Research" group with a sub-nav at `/research/`. Out of scope here.

### 11. Sitemap

**File: `astro.config.ts`** (edit sitemap `serialize`). The current rules match the *old* prefixes (`/claims/`, `/entities/|/companies/|/products/`, `/sources` exact, `/sources/`). Don't simply prepend a generic `/research/` clause: that swallows everything and silently drops the per-section priorities. Rewrite the existing matchers to use the new prefixes, then add `/resources/`:

```ts
serialize(item) {
  if (item.url.includes("/research/claims/")) {
    return { ...item, changefreq: "monthly", priority: 0.9 };
  }
  if (
    item.url.includes("/research/entities/") ||
    item.url.includes("/research/companies/") ||
    item.url.includes("/research/products/") ||
    item.url.includes("/research/subjects/")
  ) {
    return { ...item, changefreq: "weekly", priority: 0.8 };
  }
  if (item.url === "https://dangerousrobot.org/research/sources") {
    return { ...item, changefreq: "weekly", priority: 0.5 };
  }
  if (item.url.includes("/research/sources/")) {
    return { ...item, changefreq: "monthly", priority: 0.4 };
  }
  if (item.url.includes("/resources/") || item.url.endsWith("/resources")) {
    return { ...item, changefreq: "monthly", priority: 0.7 };
  }
  return { ...item, changefreq: "weekly", priority: 0.7 };
}
```

Also update the `filter` block: `INDEX_ALPHA_DETAIL_PAGES` uses `isAlphaDetailPath` from `src/lib/seo.ts`, whose patterns are anchored to the *old* prefixes (see §13).

### 12. Alpha-noindex path matching

**File: `src/lib/seo.ts`** (edit). `ALPHA_DETAIL_PATTERNS` is anchored to the old prefixes (e.g. `^/claims/...`, `^/sources/\d{4}/...`, `^/entities/...`). After the restructure, `shouldNoindex(Astro.url.pathname)` returns false for every alpha detail page, and they will start getting indexed mid-alpha. Update the regexes to the new `/research/...` prefixes in the *same* commit as the page move (Stage A step 1 in the revised sequence below). The sitemap `filter` block (§11) reuses this helper and depends on it being correct.

### 13. Architecture documentation

- **`docs/architecture/site.md`** (edit): document the URL restructure, the `resources` collection, and the wallpaper/grain layer pattern.
- **`AGENTS.md`** (edit, required): add a section explaining the boundary between `research/` (pipeline-managed structured content) and `src/content/resources/` (hand-authored editorial). The new `topics` enum scoped to resources also belongs here.
- **`VERSION.md`** and **`docs/v1.0.0-roadmap.md`**: this restructure is user-visible (URL changes, new section), so bump the minor version. Add a roadmap note.

---

## File-by-file: resources content

### `src/pages/resources/index.astro` (hub, replaces source `/robot`)

- Loads `getCollection('resources')`, sorts by `pubDate` desc.
- Renders the source's tagline ("AI literacy resources for people who didn't ask to live in the future but ended up here anyway.") as hero subhead.
- Lists each collection entry: title, description, pubDate.
- "Further reading" section at the bottom: external links transcribed verbatim from the source `/robot/page.tsx` (FLI, Stanford AI Index, Center for Humane Tech, etc.).
- Wraps in `ResourcePage.astro` with `wallpaper="default"`, `layout="reading"`.

### `src/content/resources/should-i.md` + `ShouldIDecisionTree.astro`

Frontmatter `layout: tool`, `wallpaper: default`, `topics: [ai-literacy]`. Frontmatter `data` holds questions, lenses, scoring map (transcribed from source `DecisionTree.tsx` and related files).

Vanilla JS port strategy:

1. Render initial state in HTML (lens picker visible, first question hidden).
2. `<script>` (module scope) holds questions array, scoring map, lens-modifier function, history stack.
3. Event delegation on form clicks; updates DOM directly.
4. Focus management: after answering, focus moves to the next question heading (`tabindex="-1"` + `.focus()`).
5. History: a back button pops the stack and re-renders.
6. Animated underlined blank in the title: pure CSS animation gated on `prefers-reduced-motion: no-preference` and `:root:not([data-motion="reduce"])`.

Effort estimate: 4 to 8 hours including focus/keyboard testing. Time-box; defer to UNSCHEDULED if it overruns.

### `src/content/resources/ai-safety.md` + `Lightbox.astro`

Frontmatter `layout: article`, `wallpaper: ai-safety`, `topics: [ai-safety]`. Markdown body: hero blurb ("The best overall grade is a C+."), scorecard image with click-to-zoom, six category definitions as a `<dl>`, closing thoughts.

Asset: `public/resources/fli-ai-safety-scorecard-winter-2025.png` (copy from source).

Lightbox is a native `<dialog>` element with backdrop styling, focus trap (the dialog handles this in modern browsers), ESC closes. Markdown image opens the dialog via inline `<a>` wrapper or via Astro component. Recommendation: ship a static `<img>` first, layer in the lightbox after.

### `src/content/resources/turn-off-ai.md` + `TurnOffGuide.astro`

Frontmatter `layout: guide`, `wallpaper: none`, `topics: [consumer-guide, ai-literacy]`. Frontmatter `data.platforms` is a transcription of `src/data/turn-off-ai-data.ts` from the source (PLATFORMS array, FURTHER_READING).

Component renders:

- Sticky pill-shaped section nav with scroll-spy via `IntersectionObserver`
- Per-platform sections with `last_verified` date prominently shown
- Step-by-step lists with inline code segments and callout boxes
- "What doesn't work" subsections styled with a distinct accent
- Bottom: FAQ JSON-LD inline `<script type="application/ld+json">` built from PLATFORMS questions

### `src/content/resources/responsible-ai.md` + `ResponsibleAIMatrix.astro`

Frontmatter `layout: matrix`, `wallpaper: responsible-ai`, `topics: [responsible-ai, consumer-guide]`. Frontmatter `data` holds products, dimensions, cells, footnotes, excluded products.

Cell type → token mapping:

| Cell type | Visual | Token |
|---|---|---|
| `yes` | check icon, accent green | `--color-verdict-true` |
| `no` | X icon, muted | `--color-text-muted` |
| `no-good` | X icon, red | `--color-verdict-false` |
| `partial` | minus icon, amber | `--color-verdict-mixed` |
| `planned` | up-arrow icon, blue | `--color-kind-report` (or new local) |
| `text` | plain string | `--color-text` |
| `unknown` | ? icon, faint | `--color-text-faint` |
| `na` | en-dash, faint | `--color-text-faint` |

Icons via `lucide-astro`. Footnotes group at the bottom in `<details>`.

---

## Sequencing (small-to-medium commits, direct to main)

### Stage A: Site restructure

Order matters: redirect entries cannot be added before the source paths are vacated (Astro will see two routes for the same URL pattern, and dynamic-segment redirects need the destination route to exist at build time). Sitemap rules and `seo.ts` patterns must move in lockstep with the pages so the build never emits a degraded sitemap or stops noindexing alpha detail pages.

1. **Page move + companion edits** (one medium commit). Move every file in §2's table under `src/pages/research/`. In the same commit:
   - Update internal links per §2 (components, `entityTypes.ts`, `Base.astro` nav and footer, `404.astro`).
   - Update `src/lib/seo.ts` `ALPHA_DETAIL_PATTERNS` to new prefixes (§12).
   - Update `astro.config.ts` `serialize()` rules (§11).
2. **Build + verify**. Run `npm run build`, inspect `dist/sitemap-0.xml` (old URLs gone, new URLs present with correct priorities), confirm a sample `dist/research/claims/<slug>/index.html` still emits `noindex` while alpha is on, run `npm run check:citations` (CI gate).
3. **Add redirects** to `astro.config.ts` (§1). Source paths are now free, so dynamic redirects resolve cleanly.
4. **Create `src/pages/research/index.astro`** with explainer hero + folded FAQ content. Preserve or update the `#methodology` anchor used by the footer (§3). Delete `src/pages/faq/index.astro` only after this page builds.
5. **Final verification**. Build, eyeball every section. Smoke-test redirects with `curl -sI` on a sample old URL and confirm the meta-refresh target.

### Stage B: Resources foundation + first article (turn-off-ai)

1. Add `resources` collection to `src/content.config.ts` (small).
2. Add `lucide-astro` dependency.
3. Copy wallpapers to `public/resources/wallpapers/`. Confirm parallax-ai's license permits redistribution (no `LICENSE` file in that repo as of this writing); if unclear, get explicit author sign-off and record the provenance/attribution in `docs/architecture/site.md` or a `public/resources/wallpapers/CREDITS.md`.
4. Create `src/layouts/ResourcePage.astro`, `Wallpaper.astro`, `PaperGrain.astro`, `src/styles/resources.css` (medium). Confirm `Wallpaper.astro`/`PaperGrain.astro` defer motion gating to the existing `A11yControl.astro` (`[data-motion="reduce"]`) rather than scripting their own.
5. Create `src/content/resources/turn-off-ai.md` (stub frontmatter is fine at this point) so the route file in step 6 has at least one entry to type-check against.
6. Create `src/pages/resources/index.astro` (hub) and `src/pages/resources/[...slug].astro` (route).
7. Flesh out `turn-off-ai.md` and `TurnOffGuide.astro` (medium, includes data transcription).
8. Build + sitemap re-verify (resources entries appear with monthly/0.7 priority).

`turn-off-ai` first because it has no wallpaper and no lightbox, isolating the layout/data-payload/JSON-LD path.

### Stage C: Remaining static articles

1. `src/content/resources/ai-safety.md` + scorecard PNG + `Lightbox.astro` (small-medium)
2. `src/content/resources/responsible-ai.md` + `ResponsibleAIMatrix.astro` (medium, lots of data transcription)

### Stage D: Decision tree (or defer)

1. `src/content/resources/should-i.md` + `ShouldIDecisionTree.astro` (medium-large)

If Stage D balloons past one work session, drop it for now: add an entry to `docs/UNSCHEDULED.md` and omit `should-i` from the hub entirely. The hub enumerates `getCollection('resources')`, so an absent entry produces no listing; a "(coming soon)" affordance would require special-casing in the hub template, which isn't worth the code for one item.

### Stage E: Architecture doc updates

1. Update `docs/architecture/site.md` and any related architecture pages (small).
2. Add the `research/` vs `src/content/resources/` boundary section to `AGENTS.md` (§13).
3. Bump the minor version in `VERSION.md` and add a roadmap note in `docs/v1.0.0-roadmap.md`.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Internal link breakage during restructure | Redirects catch external/cached links. Internal links handled by grepping for `href="/<section>` and updating helper functions. Run `npm run build` after each move and check the dev server. |
| Sitemap regressions | After restructure, build and inspect `dist/sitemap-0.xml`. Verify old URLs are gone and new ones present. |
| FAQ content placement awkward under explainer | Hero + `<details>` groups should compose naturally. If not, add a visual divider or rename the `<h2>` "Frequently asked questions" to make the transition obvious. |
| Decision-tree vanilla port harder than expected | Time-box Stage D to one session. Defer per UNSCHEDULED.md. Don't introduce a UI framework as a workaround. |
| `responsible-ai` PNG wallpaper looks wrong in dark theme | Ship a `-dark.png` companion if invert filter looks bad. |
| Paper-grain overlay flickers on theme switch | Use CSS `transition: none` on the overlay. |
| Mobile nav crowding with 9 links | Hamburger handles overflow. If desktop feels crowded, follow-up plan can group seven research links under a "Research" parent. |
| JSON-LD typos | Validate with Google's Rich Results Test on a representative entry. |
| Source uses Tailwind v4 token overrides | None translates directly; all styles rewritten in vanilla CSS using site tokens. |
| Markdown lint catching em-dashes | AGENTS.md forbids them; sanitize during the markdown port. |
| Old URLs hard-coded in research-content frontmatter (e.g. `sources: ['claims/...']`) | Astro content collection refs are slug-based, not URL-based. Should be unaffected. Verify with `grep -rn "https://dangerousrobot.org" research/` and a build. |
| Redirects emit meta-refresh, not 301 | Acceptable for alpha; SEO link equity won't fully consolidate. Document in `docs/architecture/site.md`. Revisit if the site moves behind Cloudflare. |
| `seo.ts` `ALPHA_DETAIL_PATTERNS` left stale after move | Alpha pages start getting indexed silently. Mitigation: §12 bundles the regex update into the same commit as the page move; verify with a sample built HTML file. |
| Sitemap `serialize` rules stale after move | Every URL falls through to default priorities. Mitigation: §11 rewrites the matchers in lockstep with the move. |

---

## Open questions

None blocking. The plan can proceed.

If anything drifts during execution, capture it in `docs/UNSCHEDULED.md` rather than amending this plan.
