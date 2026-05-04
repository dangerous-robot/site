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

<!-- TODO: plan additional runbook sections
Sections still needed:
- Deploy process (GitHub Actions)
- Content pipeline (how research files are generated)
- Adding a new entity / claim / source
- Linting and pre-commit hooks
- Environment variables reference
-->
