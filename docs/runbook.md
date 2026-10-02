# Dangerous Robot Runbook

## Dev server

Start: `inv dev` (Invoke task runner)

Default port: **4321**. Use this port when inspecting changes. Avoid starting duplicate servers -- they bump to 4322/4323.

**Hot reload:** Astro/Vite HMR picks up changes to `.astro`, `.ts`, `.js`, `.css`, and content files (`.md`, `.yaml`) automatically. A running server on 4321 does not need to be restarted for these.

**Restart required for:**
- `astro.config.mjs`
- `src/content.config.ts` (schema changes)
- `.env` / environment variables
- New npm packages

## Writing posts

Posts live in `src/content/writing/<slug>.md` and publish at `/writing/<slug>`. The schema is the `writing` collection in `src/content.config.ts`. RSS: `/writing/rss.xml`.

**With the CMS (local):** Sveltia CMS, config in `public/admin/config.yml`.
1. With the dev server running, open http://localhost:4321/admin/index.html in a Chromium browser such as Chrome, Edge, or Brave (the bare `/admin/` path 404s under Astro dev). Firefox and Safari cannot use the local-repository mode.
2. Click **Work with Local Repository** and pick the repo root folder.
3. Create or edit a post. Files are written straight to disk; nothing is committed.
4. Review the diff and commit as usual.

**By hand:** create `src/content/writing/<slug>.md` with frontmatter:

```yaml
---
title: "Post title"
description: "One sentence, 200 characters max."
pubDate: 2026-10-02
author: "Brandon Faloona"   # optional, this is the default
draft: false                # optional
tags: [ai-literacy]         # optional
---
```

**Drafts:** `draft: true` posts show in dev (marked Draft) and are left out of production builds and the RSS feed.

**Production login (TODO):** the CMS can only sign in to GitHub on the live site once these are done:
1. Register a GitHub OAuth app.
2. Deploy https://github.com/sveltia/sveltia-cms-auth on Cloudflare Workers with that app's credentials.
3. Set `backend.base_url` in `public/admin/config.yml` to the Worker URL.

<!-- TODO: plan additional runbook sections
Sections still needed:
- Deploy process (GitHub Actions)
- Content pipeline (how research files are generated)
- Adding a new entity / claim / source
- Linting and pre-commit hooks
- Environment variables reference
-->
