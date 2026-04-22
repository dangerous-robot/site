# Work Item: Astro Site Development

**Phase**: 2 (Schemas, Content & Site -- MVP)
**Status**: not started
**Depends on**: Phase 1 (repo hygiene)
**Co-authored with**: research-schemas.md (Zod schemas and Content Collections are the same design decision)

## Goal

Build Astro pages that render research content (claims, sources, entities) using Content Collections. Follow the Dangerous Robot brand voice. Functional and navigable first, polished later.

## Artifacts Already in Place

- Astro 6.x installed, `astro.config.ts` with `site: "https://dangerousrobot.org"`
- `src/pages/index.astro` -- placeholder "Coming soon"
- `public/CNAME` -- custom domain file
- `.github/workflows/deploy.yml` -- working deploy
- `npm run build` produces `dist/`

## Brand Voice (from TreadLightly BRAND_VOICE.md)

- **Tone**: Direct, matter-of-fact. "State, don't explain." Shorter sentences, fewer qualifiers.
- **No marketing language** in content. No CTAs except one quiet one on landing page.
- **No inspirational framing**: "AI safety is information, not a journey."
- **Visual**: Dark background, minimal color, system fonts. Serif for headings.

## Tasks

- [ ] Define Content Collections in `src/content.config.ts` (co-authored with research-schemas.md):
  - `claims`, `sources`, `entities` collections pointing at `research/` subdirectories
  - Zod schemas as defined in research-schemas.md
- [ ] Create base layout (`src/layouts/Base.astro`):
  - HTML boilerplate, meta tags, minimal nav
  - Dark theme, system fonts, serif headings
  - Footer: "Dangerous Robot is a research project from TreadLightly AI"
- [ ] Create index page listing claims grouped by entity
- [ ] Create claim detail page (`src/pages/claims/[...slug].astro`):
  - Verdict badge, confidence, rationale, as_of date, source links
- [ ] Create source detail page (`src/pages/sources/[...slug].astro`):
  - Publisher, date, summary, key quotes, original + archive links
- [ ] Create entity page (`src/pages/entities/[...slug].astro`):
  - Entity description, list of all claims for that entity
- [ ] Verify `npm run build` succeeds with proof-of-concept content
- [ ] Verify deploy workflow produces correct pages

## Design Decisions

**Routing**: `[...slug]` pages. Claims at `/claims/{entity}/{claim-id}`, sources at `/sources/{year}/{slug}`, entities at `/entities/{slug}` (flat, not subtyped).

**Styling**: Dark mode default. System fonts, serif headings. Scoped `<style>` only -- no CSS framework. Inspired by existing `DR_COLORS` palette.

**No client-side JS**: Pure static HTML. Astro zero-JS output.

**Markdown pipeline**: If claim/source body content needs GFM tables or footnotes, add `@astrojs/mdx` or remark plugins to `astro.config.ts`. Evaluate when writing first content.

**Slug handling**: Claims use nested directories (`research/claims/openai/training-data-consent.md`). Astro Content Collections preserve directory structure in slugs. Verify that `getCollection('claims')` returns slugs like `openai/training-data-consent` and that `[...slug].astro` routes correctly.

## Open Questions

1. **Navigation**: Flat sections (claims, sources, entities) or entity-centric (entity pages as primary, claims nested)? Start flat, refine later.

## Estimated Scope

Medium. Template work + content collection configuration. Co-author schemas with research-schemas.md to avoid designing the same thing twice.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (cursory review) | completed-check | Added review history section; status is "not started" but file is in completed/; all tasks remain unchecked (8 items) |
