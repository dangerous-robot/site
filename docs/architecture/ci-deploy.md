# CI & Deploy Architecture

How continuous integration, deployment, and quality checks work for the Dangerous Robot site.

## CI Workflow (`.github/workflows/ci.yml`)

**Trigger:** Pull requests targeting `main`. The workflow also declares `workflow_call`, so the deploy pipeline can reuse it as a verification gate.

Four jobs run in parallel on `ubuntu-latest`:

**`check`** (Node 22). The job sets `WATCH_DATA: fixture`, so `/watch` is built from the invented fixture data with no network and no API key. Steps run sequentially so a failure in an earlier step short-circuits the rest:

1. `npm run check:types` -- `astro check`
2. `npm run test:site` -- unit tests (`node:test`)
3. `npm run build` -- Astro site build (catches template/config errors)
4. `npm run check:watch` -- `/watch` dist check (see [Watch page checks](#watch-page-checks))
5. `npm run check:flyers` -- petition flyer check (see [Petition flyer check](#petition-flyer-check))
6. `npm run lint:md` -- Markdown linting on research content
7. `npm run check:citations` -- Citation integrity check

**`e2e`** (Node 22). Runs the browser tests (`/watch` and the petition QR decode test):

1. `npm ci`, then `npx playwright install --with-deps chromium`.
2. `npm run test:e2e` -- Playwright builds the site with fixture data and serves it on port 4329 (see [Watch page checks](#watch-page-checks)).
3. On failure only, uploads `node_modules/.cache/watch-e2e/*/test-results/` (traces and screenshots) as the `playwright-results` artifact, kept 7 days. The path is inside a dot directory, so the upload step sets `include-hidden-files: true`.

The checkout, setup-node and upload-artifact steps in `e2e` are pinned by commit SHA.

**`lint-content`** (Python 3.12). Runs the pipeline's research content linter:

1. Installs `uv` (`astral-sh/setup-uv`, SHA-pinned, version matched to the laptop) and runs `uv sync --locked` from the repo root, so the job fails rather than resolving fresh when the committed `uv.lock` is stale.
2. Runs `uv run dr lint --format json --severity error`, writing `lint-report.json` and capturing the exit code without failing yet.
3. Annotates each reported error on the PR (file path plus check id) via `actions/github-script`.
4. Fails the job if `dr lint` exited nonzero.

**`pipeline-tests`** (Python 3.12, 15-minute limit). Runs the pipeline's unit tests:

1. Installs `uv` the same way as `lint-content` and runs `uv sync --locked`.
2. Runs `uv run python -m pytest -m 'not acceptance'` from `pipeline/`, so pytest reads that directory's `pyproject.toml`. Acceptance tests call live APIs and need keys, so CI leaves them out.

If any job fails, the PR check fails.

## Deploy Workflow (`.github/workflows/deploy.yml`)

**Trigger:** Push to `main`, manual dispatch (`workflow_dispatch`), or the weekly schedule (`cron: '17 6 * * 1'`, Mondays 06:17 UTC).

Three-job pipeline:

1. **verify** -- Reuses the CI workflow (`ci.yml`) via `workflow_call`, so the same `check`, `e2e`, `lint-content` and `pipeline-tests` jobs gate every deploy.
2. **build** -- Depends on `verify`. Checks out the repo, installs deps, runs `npm run build` with the YouTube key, runs `npm run check:watch` in deploy context, runs `npm run check:flyers`, removes `dist/admin`, and uploads `dist/` as a Pages artifact.
3. **deploy** -- Depends on `build`. Deploys the artifact to GitHub Pages using `actions/deploy-pages@v5`.

### Weekly scheduled deploy

`/watch` shows playlist and video data fetched from the YouTube Data API at build time. The YouTube API Services Developer Policies allow that data to be stored for at most 30 days, and nothing from the API is committed, so the page is rebuilt every week.

A scheduled run uses the same jobs as a push deploy, with no job conditions and no checkout options: it checks out the latest commit on `main`, which the push deploy for that commit has already shipped, so the only change it publishes is fresher YouTube data. Because it goes through `verify`, a red `main` (`check`, `e2e`, `lint-content` or `pipeline-tests`) also blocks the weekly refresh, and the last good deploy stays live. Playwright retries a failed test once in CI, so one flaky test does not block it.

GitHub turns off scheduled workflows in a public repository after 60 days with no repository activity. The weekly refresh then stops and the `/watch` data grows older than the 30 days allowed; if that happens, re-enable the "Deploy to GitHub Pages" workflow in the repository's Actions tab.

### YouTube API key

`YOUTUBE_API_KEY` is a GitHub Actions repository secret. It is passed to two steps of the `build` job and to nothing else:

- `npm run build`, with `WATCH_EXPECT_KEY: '1'`. The `/watch` content loader fetches live data with the key. If the key is missing it logs a warning (shown as a `Watch page` annotation) and the page renders its empty state; if the API fails, the build still succeeds and publishes the empty state.
- `npm run check:watch`, with `WATCH_CHECK_CONTEXT: deploy`. The key lets the check scan `dist/` for its exact value, which fails the step in any file. The `AIza` prefix every Google key starts with fails it in any file but `/watch`, where it is only a warning, since YouTube titles and descriptions may contain one. Deploy context fails the step if `/watch` was built from fixture data.

The loader never sets a `Referer` or `Origin` header. The key carries an API restriction (YouTube Data API v3) and no HTTP referrer restriction.

Key settings:

- **Concurrency group:** `pages` with `cancel-in-progress: false` -- queues deploys rather than canceling in-flight ones.
- **Permissions:** `contents: read`, `pages: write`, `id-token: write` (OIDC for Pages).
- **Custom domain:** A `CNAME` file in `public/` maps to `dangerousrobot.org`.

## Quality Checks (`npm run check`)

The `check` script chains eight stages in order:

```bash
npm run check:types && npm run test:site && npm run build && npm run lint:md && npm run check:citations && npm run check:reviewers && npm run check:watch && npm run check:flyers
```

Run it locally before pushing. The CI `check` job runs all of these except check:reviewers. `inv check` runs check:types, test:site, build, check:watch, lint:md and check:citations, then the pipeline's pytest suite; it does not run check:reviewers or check:flyers. check:flyers is left out so a pledge edit does not block every commit until a new flyer PDF is rendered; it runs in `npm run check`, CI's `check` job and the deploy `build` job, so a stale flyer can be committed but not deployed. The pre-commit hook (`scripts/git-hooks/pre-commit`, installed by symlink into `.git/hooks/`; see `docs/runbook.md` § Linting and the pre-commit hook) runs `dr lint` first, then `inv check`, and fails the commit when `.venv/bin/dr` is missing. Browser tests (`npm run test:e2e`) are in none of these; CI runs them in the `e2e` job. (CI's `lint-content` job is separate; it runs the same `dr lint` entry point as the hook and `inv audit`.)

### Stage 1: Types

`astro check` -- type-checks the site.

### Stage 2: Unit Tests

`tsx --test 'src/lib/**/*.test.ts'` -- `node:test` unit tests for the site's library code, including the `/watch` loader and client logic, which run against fixtures with no network.

### Stage 3: Build

`astro build` -- compiles the site to `dist/`. Catches broken imports, invalid frontmatter, and template errors.

### Stage 4: Markdown Lint

`markdownlint-cli2 'research/**/*.md'`

Lints all Markdown files under `research/`. See [Markdown Linting](#markdown-linting) below.

### Stage 5: Citation Integrity

`tsx scripts/check-citations.ts` -- see [Citation Integrity](#citation-integrity) below.

### Stage 6: Reviewer Display

`tsx scripts/check-reviewer-display.ts` -- checks reviewed claim pages in `dist/` for the reviewer's handle and profile link, and that each profile lists exactly the reviewed published claims. See [`site.md`](site.md#cross-linking).

### Stage 7: Watch Page

`tsx scripts/check-watch-page.ts` -- checks the built `/watch` page and scans `dist/` for API key leaks. See [Watch page checks](#watch-page-checks).

### Stage 8: Petition Flyers

`tsx scripts/check-flyers.ts` -- see [Petition flyer check](#petition-flyer-check).

## Watch Page Checks

**Dist check** (`npm run check:watch`, `scripts/check-watch-page.ts`). Run after a build. It reads `dist/`, or the directory in `WATCH_CHECK_DIST`. It fails when:

- any file in `dist/` contains `AIza` (the prefix of every Google API key), or the exact value of `YOUTUBE_API_KEY` when that variable is set in the step's environment;
- `/watch` has no single page root with `data-watch-mode` of `live`, `fixture` or `none`, or contains an `<iframe>` before Play;
- in `none` mode, the page-level empty state is missing or any thumbnail renders;
- `/privacy` does not link the YouTube Terms of Service and the Google Privacy Policy;
- in `live` or `fixture` mode, a thumbnail is not a link to youtube.com, the switcher's playlists and the panels do not match, or a panel has neither a video list nor an empty state;
- in `fixture` mode, the switcher's playlists, statuses and video counts differ from `src/lib/watch/fixtures/expected.ts`;
- with `WATCH_CHECK_CONTEXT=deploy`, the page was built from fixture data.

An empty or failed playlist, and live mode with no thumbnails, print GitHub `::warning::` lines and do not fail the check. A keyless build (`none` mode) passes, in deploy context too, so a missing key never fails a deploy.

**Browser tests** (`npm run test:e2e`, config in `playwright.config.ts`, specs in `tests/e2e/`). Playwright runs Chromium against a fixture build:

- The port is `WATCH_E2E_PORT`, default 4329. Do not set it to 4321, which `inv dev` uses. `reuseExistingServer` is off, so a run never attaches to another run's server.
- Each run builds into its own directory, `node_modules/.cache/watch-e2e/<port>/dist`, with test results beside it in `test-results/` (both are created by the run), then serves it with `astro preview`.
- `WATCH_E2E_REUSE_BUILD=1` skips the build when that directory already holds one, for runs where only spec files changed. CI ignores it.
- `tests/e2e/helpers.ts` routes every request to another origin: `i.ytimg.com` gets generated images, `youtube-nocookie.com` a blank page, and anything else is blocked and fails the test. No test touches the network.

## Petition Flyer Check

`npm run check:flyers` (`scripts/check-flyers.ts`) runs after a build and reads `dist/`, or the directory in `FLYER_CHECK_DIST`. It fails when an open petition's flyer PDF in `public/flyers/` is missing, out of date (its fingerprint covers the pledge text, the petition URL and the flyer template files), or not linked from the petition page; when an open petition's flyer page has no QR code or contains a form or live data; when a closed petition still has a flyer page or a link to its PDF (the PDF file itself may stay, and `public/robots.txt` keeps `/flyers/` out of crawlers); or when `public/flyers/` holds a file no petition owns. The fix for a stale flyer is `inv flyers`, then committing `public/flyers/`. See [`petitions.md`](petitions.md) and `docs/runbook.md` § Petitions: open, close, export, remove.

The browser test `tests/e2e/petition-qr.spec.ts` decodes the QR code on the petition page and on the flyer page and expects the page URL; it skips when the built page says the petition is closed. It runs with the `/watch` specs in `npm run test:e2e`.

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
| `check:reviewers`  | `tsx scripts/check-reviewer-display.ts`              | Check reviewer mentions in `dist/`               |
| `check:types`      | `astro check`                                        | Type-check the site                              |
| `check:watch`      | `tsx scripts/check-watch-page.ts`                    | Check `/watch` in `dist/` and scan for key leaks |
| `check:flyers`     | `tsx scripts/check-flyers.ts`                        | Check petition flyer PDFs and links against `dist/` |
| `test:site`        | `tsx --test 'src/lib/**/*.test.ts'`                  | Unit tests                                       |
| `test:e2e`         | `playwright test`                                    | `/watch` browser tests and the petition QR decode test (Chromium, fixture build) |
| `check`            | `npm run check:types && npm run test:site && npm run build && npm run lint:md && npm run check:citations && npm run check:reviewers && npm run check:watch && npm run check:flyers` | Run the full local quality gate (CI's `check` job runs all but check:reviewers) |
