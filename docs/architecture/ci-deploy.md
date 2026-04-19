# CI & Deploy Architecture

How continuous integration, deployment, and quality checks work for the Dangerous Robot site.

## CI Workflow (`.github/workflows/ci.yml`)

**Trigger:** Pull requests targeting `main`.

Runs a single `check` job on `ubuntu-latest` with Node 22. Steps run sequentially so a failure in an earlier step short-circuits the rest:

1. `npm run build` -- Astro site build (catches template/config errors)
2. `npm run lint:md` -- Markdown linting on research content
3. `npm run check:citations` -- Citation integrity check

If any step fails, the PR check fails.

## Deploy Workflow (`.github/workflows/deploy.yml`)

**Trigger:** Push to `main`, or manual dispatch (`workflow_dispatch`).

Two-job pipeline:

1. **build** -- Checks out the repo, installs deps, runs `astro build`, and uploads `dist/` as a Pages artifact.
2. **deploy** -- Depends on `build`. Deploys the artifact to GitHub Pages using `actions/deploy-pages@v4`.

Key settings:

- **Concurrency group:** `pages` with `cancel-in-progress: false` -- queues deploys rather than canceling in-flight ones.
- **Permissions:** `contents: read`, `pages: write`, `id-token: write` (OIDC for Pages).
- **Custom domain:** A `CNAME` file in `public/` maps to `dangerousrobot.org`.

## Quality Checks (`npm run check`)

The `check` script chains three stages in order:

```
npm run build && npm run lint:md && npm run check:citations
```

This is the same sequence CI runs. You can run it locally before pushing.

### Stage 1: Build

`astro build` -- compiles the site to `dist/`. Catches broken imports, invalid frontmatter, and template errors.

### Stage 2: Markdown Lint

`markdownlint-cli2 'research/**/*.md'`

Lints all Markdown files under `research/`. See [Markdown Linting](#markdown-linting) below.

### Stage 3: Citation Integrity

`tsx scripts/check-citations.ts` -- see [Citation Integrity](#citation-integrity) below.

## Citation Integrity

`scripts/check-citations.ts` validates that claim files reference real sources.

**What it does:**

1. Recursively collects all `.md` files under `research/claims/`.
2. For each claim, reads its YAML frontmatter and extracts the `sources` array.
3. For each slug in `sources`, checks that `research/sources/<slug>.md` exists as a file.
4. If any slug has no matching source file, it logs the broken reference and increments an error counter.

**Exit behavior:**

- No claim files found -- exits 0 (skip).
- All citations resolve -- exits 0.
- Any broken citation -- exits 1 with a count of broken references.

**Example error output:**

```
BROKEN: research/claims/water-usage.md references "missing-source" but research/sources/missing-source.md does not exist

1 broken citation(s) found.
```

## Markdown Linting

Config file: `.markdownlint.jsonc`

The linter runs on `research/**/*.md`. Three rules are disabled:

| Rule  | Name                 | Why disabled                                          |
|-------|----------------------|-------------------------------------------------------|
| MD013 | Line length          | Research content can be verbose                       |
| MD033 | No inline HTML       | Astro templates may use HTML in Markdown              |
| MD041 | First line heading   | Content files start with body text after frontmatter  |

All other `markdownlint` defaults are enforced.

## Scripts Reference

| Script             | Command                                              | Purpose                                          |
|--------------------|------------------------------------------------------|--------------------------------------------------|
| `dev`              | `astro dev`                                          | Start local dev server                           |
| `build`            | `astro build`                                        | Build site to `dist/`                            |
| `preview`          | `astro preview`                                      | Preview production build locally                 |
| `astro`            | `astro`                                              | Run Astro CLI directly                           |
| `lint:md`          | `markdownlint-cli2 'research/**/*.md'`                       | Lint research Markdown files             |
| `check:citations`  | `tsx scripts/check-citations.ts`                     | Validate claim-to-source references              |
| `check`            | `npm run build && npm run lint:md && npm run check:citations` | Run full quality gate (same as CI)      |
