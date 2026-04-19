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

Research content lives outside `src/` in the `research/` directory. Astro's content layer loads it via `glob()` loaders defined in `src/content.config.ts`.

Three collections are defined:

| Collection | Loader base          | Schema highlights                                        |
|------------|----------------------|----------------------------------------------------------|
| `claims`   | `research/claims`    | title, entity, category, verdict, confidence, as_of, sources |
| `sources`  | `research/sources`   | url, title, publisher, kind, summary, key_quotes         |
| `entities` | `research/entities`  | name, type (company/product/topic), website, description |

Each collection entry is a Markdown file with YAML frontmatter. The Markdown body is rendered as HTML on detail pages via Astro's `render()` function.

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
  sources/
    2025/earthday-chatgpt-prompt-cost.md
    2025/fli-safety-index.md
    ...
```

Subdirectory structure within each collection is flexible -- the `glob` loader picks up all `**/*.md` files under the base path. The full relative path (minus extension) becomes the entry's `id`, which drives URL slugs.

## Page Routing

All routes are statically generated at build time via `getStaticPaths()`.

| Route pattern                | File                                | Data source           |
|------------------------------|-------------------------------------|-----------------------|
| `/`                          | `src/pages/index.astro`             | `claims` collection   |
| `/claims/[...slug]`          | `src/pages/claims/[...slug].astro`  | `claims` collection   |
| `/sources/[...slug]`         | `src/pages/sources/[...slug].astro` | `sources` collection  |
| `/entities/[...slug]`        | `src/pages/entities/[...slug].astro`| `entities` collection |

The `[...slug]` rest parameter supports nested IDs (e.g., `anthropic/existential-safety-score` maps to `/claims/anthropic/existential-safety-score`).

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
    <nav>      -- site name + Home link (list pages to be added later)
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

`astro.config.ts` is minimal:

```ts
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://dangerousrobot.org",
});
```

The `site` value is used by Astro for canonical URLs and sitemap generation. No adapter is configured -- output defaults to `static`.
