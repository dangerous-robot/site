# Site Architecture

Static Astro site that renders structured research content (claims, sources, entities) into GitHub Pages.

## Stack

| Component     | Detail                        |
|---------------|-------------------------------|
| Framework     | Astro 6.x (`^6.1.8`)         |
| Node          | >= 22                         |
| Output        | Static HTML (default adapter) |
| Hosting       | GitHub Pages                  |
| Custom domain | `dangerousrobot.org`          |

There are no runtime dependencies beyond Astro itself. Dev dependencies are limited to `markdownlint-cli2`, `gray-matter`, and `tsx` (used by lint and validation scripts).

## Content Collections

The site mixes pipeline-managed research content (under `research/`, outside `src/`) with hand-authored editorial content (under `src/content/resources/`). Astro's content layer loads both via loaders defined in `src/content.config.ts`.

Five collections are defined:

| Collection  | Loader / source                        | Schema highlights                                        |
|-------------|----------------------------------------|----------------------------------------------------------|
| `claims`    | custom `claims-with-audit` loader      | title, entity, topics, verdict, confidence, as_of, sources, audit (sidecar) |
| `sources`   | `glob()` from `research/sources`       | url, title, publisher, kind, summary, key_quotes         |
| `entities`  | `glob()` from `research/entities`      | name, type (company/product/subject), website, description |
| `criteria`  | `file()` from `research/templates.yaml` (single file) | slug, text, entity_type, topics, core, notes |
| `resources` | `glob()` from `src/content/resources`  | title, description, pubDate, layout, wallpaper, topics (resources-scoped enum), data, further_reading |

The `sources` and `entities` collections use a `glob()` loader -- each entry is a Markdown file with YAML frontmatter. The Markdown body is rendered as HTML on detail pages via Astro's `render()` function.

The `claims` collection uses a custom loader (`claims-with-audit`) that reads each claim's `.md` file and, if a paired `.audit.yaml` sidecar exists, merges it into the claim's `audit` field. See [content-model.md](content-model.md) for the audit sidecar schema.

The `criteria` collection uses a `file()` loader, loading all entries from a single YAML file rather than individual Markdown files.

The `resources` collection holds editorial articles for the `/resources/` section (decision tools, comparison articles, reference guides). Its schema is independent of the research collections: it carries a layout discriminator (`article | matrix | guide | tool`), a wallpaper variant, a small resources-scoped `topics` enum (`ai-literacy`, `ai-safety`, `consumer-guide`, `responsible-ai`), and an optional `data` payload that is validated per layout at render time. See AGENTS.md "Editorial content" section for the boundary between `research/` and `src/content/resources/`.

### Content directory structure

```
research/
  claims/
    anthropic/existential-safety-score.md
    ecosia/renewable-energy-hosting.md
    greenpt/renewable-energy-hosting.md
  entities/
    companies/anthropic.md
    companies/ecosia.md
    companies/greenpt.md
    products/...
    subjects/...
  sources/
    2025/earthday-chatgpt-prompt-cost.md
    2025/fli-safety-index.md
    ...
  templates.yaml

src/content/resources/
  ai-safety.md
  responsible-ai.md
  should-i.md
  turn-off-ai.md
```

Subdirectory structure within each `glob`-loaded collection is flexible -- the loader picks up all `**/*.md` files under the base path. The full relative path (minus extension) becomes the entry's `id`, which drives URL slugs.

## Page Routing

All routes are statically generated at build time via `getStaticPaths()`.

The site has three top-level URL spaces:

- `/` -- the research-tool landing (claim scatter).
- `/research/*` -- the research tool: claims, entities, sources, criteria, taxonomy indexes, plus a `/research/` hub that explains how the tool works (FAQ + explainer).
- `/resources/*` -- the editorial section: hand-authored articles, comparison matrices, decision tools, and how-to guides.

| Route pattern                  | File                                              | Data source                                 |
|--------------------------------|---------------------------------------------------|---------------------------------------------|
| `/`                            | `src/pages/index.astro`                           | `claims` collection                         |
| `/research`                    | `src/pages/research/index.astro`                  | Static explainer + FAQ content              |
| `/research/claims`             | `src/pages/research/claims/index.astro`           | `claims` collection                         |
| `/research/claims/[...slug]`   | `src/pages/research/claims/[...slug].astro`       | `claims` collection                         |
| `/research/sources`            | `src/pages/research/sources/index.astro`          | `sources` collection                        |
| `/research/sources/[...slug]`  | `src/pages/research/sources/[...slug].astro`      | `sources` collection                        |
| `/research/entities/[...slug]` | `src/pages/research/entities/[...slug].astro`     | `entities` collection                       |
| `/research/companies`          | `src/pages/research/companies/index.astro`        | `entities` (company type)                   |
| `/research/products`           | `src/pages/research/products/index.astro`         | `entities` (product type)                   |
| `/research/subjects`           | `src/pages/research/subjects/index.astro`         | `entities` (subject type)                   |
| `/research/topics`             | `src/pages/research/topics/index.astro`           | `claims` (cross-cutting taxonomy)           |
| `/research/topics/[topic]`     | `src/pages/research/topics/[topic].astro`         | `claims` (filtered by topic)                |
| `/research/criteria`           | `src/pages/research/criteria/index.astro`         | `criteria` collection                       |
| `/research/criteria/[slug]`    | `src/pages/research/criteria/[slug].astro`        | `criteria` collection                       |
| `/resources`                   | `src/pages/resources/index.astro`                 | `resources` collection (hub list)           |
| `/resources/[...slug]`         | `src/pages/resources/[...slug].astro`             | `resources` collection (layout dispatch)    |
| `/values`                      | `src/pages/values.astro`                          | Static content                              |
| `/credits`                     | `src/pages/credits.astro`                         | Static content                              |

The `[...slug]` rest parameter supports nested IDs (e.g., `anthropic/existential-safety-score` maps to `/research/claims/anthropic/existential-safety-score`).

Entities of type `subject` are listed at `/research/subjects/` and have detail pages at `/research/entities/subjects/[slug]`.

### URL restructure (2026-05) and redirects

The research subpages were originally at top-level URLs (`/claims`, `/entities`, `/companies`, `/products`, `/subjects`, `/topics`, `/sources`, `/criteria`) and `/faq`. They moved under a `/research/` prefix in May 2026 to make room for the `/resources/` editorial section and to express the "research tool" vs "resources" split in the URL.

Redirects are configured in `astro.config.ts` via Astro's `redirects` map, including dynamic-segment passthroughs for the detail routes:

```ts
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
}
```

**Implementation note: meta-refresh, not 301.** Astro emits these as static HTML pages with `<meta http-equiv="refresh" content="0;url=...">`, not as HTTP 301s, because GitHub Pages cannot serve real 301 redirects from a user-controlled config. For alpha and beta this is acceptable; full SEO link-equity consolidation would require fronting the site with a CDN that supports edge redirects (e.g., Cloudflare). All redirects are preserved permanently regardless.

Sitemap `serialize()` rules and `src/lib/seo.ts` `ALPHA_DETAIL_PATTERNS` are anchored to the new `/research/*` prefixes; they were updated in lockstep with the page move so the sitemap priorities and alpha-noindex behavior stayed correct.

### `/resources/` section: layout dispatch

The detail route at `/resources/[...slug]` reads the entry's `layout` discriminator and dispatches to one of four renderings inside the shared `ResourcePage.astro` shell:

| `layout`  | Renders                                                                          | Used by             |
|-----------|----------------------------------------------------------------------------------|---------------------|
| `article` | Plain Markdown body (with optional embedded components like `Lightbox`)          | `ai-safety.md`      |
| `matrix`  | `<ResponsibleAIMatrix>` reading `data` (products, dimensions, cells, footnotes)  | `responsible-ai.md` |
| `guide`   | `<TurnOffGuide>` reading `data.platforms` + sticky pill nav, FAQ JSON-LD         | `turn-off-ai.md`    |
| `tool`    | `<ShouldIDecisionTree>` (vanilla JS, module-scoped script)                       | `should-i.md`       |

Each layout still accepts a Markdown body slot for prose intro/outro. The layout-specific `data` payload lives in frontmatter as a typed-but-unvalidated `unknown`; per-layout components do their own runtime shape checks.

### `ResourcePage.astro` and the wallpaper / grain layer pattern

`src/layouts/ResourcePage.astro` wraps `Base.astro` and adds three decorative layers behind the content:

1. **Wallpaper** (`<Wallpaper variant={frontmatter.wallpaper}>`) -- a fixed-position, low-opacity SVG or PNG anchored bottom-right, with a CSS `mask-image` linear-gradient mask so it fades into the page background. Variants: `default`, `ai-safety`, `responsible-ai`, `none`.
2. **Paper grain** (`<PaperGrain>`) -- an inline SVG data-URI noise overlay using `mix-blend-mode` for subtle paper texture.
3. **Hero block** -- large display heading + optional subhead, sized via `--font-heading` and existing site tokens.

Both decorative layers honor `prefers-reduced-motion` and the site's `[data-motion="reduce"]` attribute (driven by `A11yControl.astro`). Styles are scoped under `.resources-page` in `src/styles/resources.css`, imported only by `ResourcePage.astro` and the hub.

**Theme-aware SVG inversion.** The SVG wallpapers are authored on a light background. Under `[data-theme="dark"]` they have `filter: invert(1)` applied via CSS so the linework reads correctly. The PNG wallpaper (`responsible-ai`) ships as-is; if dark-theme contrast is poor, the pattern is to add a `responsible-ai-dark.png` companion and switch via the same theme attribute.

Wallpaper assets and provenance live in `public/resources/wallpapers/` (see `CREDITS.md` in that directory).

### How dynamic routes work

Each dynamic route file exports `getStaticPaths()`, which:

1. Fetches the full collection with `getCollection("claims")` (or equivalent).
2. Maps each entry to `{ params: { slug: entry.id }, props: { entry } }`.
3. Astro generates one HTML file per entry at build time.

The page component receives the entry via `Astro.props`, calls `render()` to get the Markdown body as a `<Content />` component, and renders the detail template.

### Cross-linking

- The homepage groups claims by `entity` and links to `/claims/{id}` and `/entities/{entity}`.
- Claim detail pages link back to their entity (`/entities/{entity}`) and to each source (`/sources/{sourceRef}`).
- Entity detail pages query all claims and display those whose `entity` field matches.

## Layout

A single layout -- `src/layouts/Base.astro` -- wraps every page.

### Props

| Prop          | Type     | Default                                                        |
|---------------|----------|----------------------------------------------------------------|
| `title`       | `string` | Required. Rendered as `{title} - Dangerous Robot` in `<title>` |
| `description` | `string` | Falls back to a default site description                       |

### Structure

```
<html>
  <head>       -- charset, viewport, title, description, global styles
  <body>
    <nav>      -- site name + nav links to list pages
    <main>     -- <slot /> receives page content
    <footer>   -- TreadLightly AI attribution
```

### Styling approach

- Global styles are defined in `<style is:global>` within `Base.astro` (resets, body, headings, links).
- Component-scoped styles live in `<style>` blocks in each `.astro` file -- Astro scopes them automatically.
- No CSS framework or preprocessor. Design is dark-theme with serif headings (`Georgia`) and system-ui body text.
- Content is constrained to `max-width: 48rem` with horizontal padding.

## Build Output

```bash
npm run build     # runs `astro build`
```

Produces a `dist/` directory containing static HTML, CSS, and any assets. No JavaScript is shipped to the client (no client-side components or islands exist).

The `public/CNAME` file is copied as-is to `dist/CNAME` during the build, which GitHub Pages needs for custom domain routing.

### Other scripts

| Script              | Command                                                   | Purpose                                  |
|---------------------|-----------------------------------------------------------|------------------------------------------|
| `npm run dev`       | `astro dev`                                               | Local dev server                         |
| `npm run preview`   | `astro preview`                                           | Preview the built site                   |
| `npm run lint:md`   | `markdownlint-cli2 'research/**/*.md'`                   | Lint research Markdown files             |
| `npm run check:citations` | `tsx scripts/check-citations.ts`                   | Validate source references in claims     |
| `npm run check`     | `build + lint:md + check:citations`                       | Full CI check                            |

## Deployment

The deploy pipeline is in `.github/workflows/deploy.yml`. It runs on every push to `main` (and on manual dispatch).

Steps:

1. Checkout, setup Node 22, `npm ci`.
2. `npm run build` -- produces `dist/`.
3. Upload `dist/` as a Pages artifact.
4. Deploy to the `github-pages` environment via `actions/deploy-pages@v4`.

A separate CI workflow (`.github/workflows/ci.yml`) runs checks on PRs.

### Custom domain

`public/CNAME` contains `dangerousrobot.org`. This file lands in `dist/` at build time, telling GitHub Pages to serve the site at that domain.

## Configuration

`astro.config.ts` declares:

- `site: "https://dangerousrobot.org"` -- used by Astro for canonical URLs and sitemap generation.
- `trailingSlash: "never"` -- canonical URL form.
- `redirects: { ... }` -- the old-URL-to-`/research/*` map described under "URL restructure" above.
- `integrations: [sitemap({ ... })]` -- per-section `serialize()` priorities and a `filter` that defers to `src/lib/seo.ts` for alpha-noindex paths.

No adapter is configured -- output defaults to `static`.
