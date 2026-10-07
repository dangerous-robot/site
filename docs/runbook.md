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
ai_assisted: false          # optional; true when AI drafted the text
draft: false                # optional
tags: [ai-literacy]         # optional
---
```

**Byline:** the post page prints "Written by {author}". With `ai_assisted: true` it prints "Written by {author}, with AI assistance" (the CMS field is "AI assisted"). Set it on when AI drafted the text. Guest authors keep their own names.

**Drafts:** `draft: true` posts show in dev (marked Draft) and are left out of production builds and the RSS feed.

**Resources:** the CMS **Resources** collection edits plain articles (`layout: article`) in `src/content/resources/`, published at `/resources/<slug>`. The matrix, guide and tool pages (`responsible-ai`, `turn-off-ai`, `should-i`) carry structured `data`, so the CMS hides them; edit those by hand. Images go in `public/images/resources/`.

**Production login (TODO):** the CMS can only sign in to GitHub on the live site once these are done:
1. Register a GitHub OAuth app.
2. Deploy https://github.com/sveltia/sveltia-cms-auth on Cloudflare Workers with that app's credentials.
3. Set `backend.base_url` in `public/admin/config.yml` to the Worker URL.

## Corrections

Readers report errors through the GitHub issue form `.github/ISSUE_TEMPLATE/correction.yml`, linked from `/corrections`. Reports arrive as issues with the `correction` label. A published correction is recorded in the claim's optional `corrections` frontmatter (`date`, `summary`, `previous_verdict`), which the claim page shows under the meta row. A forced pipeline rewrite of the claim file keeps existing `corrections` entries.

**Issue labels (operator step, once).** GitHub skips a template label that does not exist in the repo, so create the labels the issue templates apply:

```bash
gh label create correction -R dangerous-robot/site --description "Reader-reported error on a page or claim"
gh label create source-submission -R dangerous-robot/site --description "Reader-submitted source"
```

Legal and safety matters go to `contact@dangerousrobot.org`, a domain alias the operator creates and points at an inbox. It is the only non-public contact path and is shown on `/about#contact`.

**Interaction limits (operator setting, not code).** To keep the correction form and the issue tracker usable, limit who can open issues and comment on the repo. This is a GitHub setting, not part of the site build:

```bash
gh api -X PUT repos/dangerous-robot/site/interaction-limits -f limit=existing_users -f expiry=six_months
```

The same setting is in the repo's Moderation settings. A limit expires (anywhere from one day to six months) and then lapses on its own, so renew it before the expiry date. Nothing in the repo records that date; put it in your own calendar.

## Refreshing a published claim

A refresh rewrites the claim as a draft and resets its sign-off. The pipeline keeps the published verdict and reviewer in the sidecar's `refresh` block until you approve again. A committed draft or blocked claim drops off the live site, so approve before you commit.

1. Run `uv run dr claim-refresh <entity>/<claim-slug>`.
2. Run `uv run dr review-queue`. A refreshed claim shows "Was published: {verdict} (reviewed {date})".
3. If the verdict changed, the header says so, and pressing `a` asks for a correction: write one line for readers saying what changed and why. It becomes a dated entry under the verdict, with the previous verdict shown. Outside the queue, use `uv run dr review --claim <entity>/<claim-slug> --approve --correction "..."`. `dr publish` skips every refreshed claim, because it records no reviewer; approve each one with `dr review --approve` (adding `--correction` when the verdict changed).
4. Commit the claim, its sidecar and any new sources only after approval. Until then `dr lint` warns `refresh-pending-review`. A refresh that ends `blocked` cannot be approved, and a committed blocked claim drops off the live site: re-run the refresh, or restore the claim and sidecar with `git restore` instead of committing them.

If you change the verdict with `e` before approving, approval records the change as `human_review.verdict_override`. A published verdict that matches neither the pipeline's nor a recorded override fails lint (`verdict-sidecar-mismatch`).

## Archive links for sources

The pipeline gives each new source an `archived_url` after ingesting it: an existing archive.org snapshot if there is one, otherwise it asks archive.org to capture the page. Commands that write nothing (`dr claim-probe`, `dr step-ingest` without `--write`) only look for an existing snapshot. The `dr` command list in AGENTS.md says which commands can capture.

- Add links to existing sources: `uv run dr wayback-backfill <year>/<slug> ...`. It skips a source that already has a link and exits 1 if any source got none.
- A failed lookup is recorded in the claim sidecar as `sources_consulted[].archive` with `status: failed` and the reason (for example `archive.org TimeGate check failed (HTTP 429)`). The source is still written, without a link; rerun `dr wayback-backfill` later.
- A link without a 14-digit timestamp (`https://web.archive.org/web/<url>`) does not name a capture. The pipeline no longer writes one.

## Petitions: open, close, export, remove

Signatures live in the `dr-api` D1 database behind the `dr-api` Worker (`workers/api/`, served at `api.dangerousrobot.org`). Design and privacy rules: `docs/architecture/petitions.md`. Run every command below from `workers/api/` (`cd workers/api` first, as its own command). Drop `--remote` to run against the local database that `wrangler dev` uses.

**Deploy (after a Worker change).** The Worker is not deployed by GitHub Actions. From the repo root:

```bash
inv worker-deploy
```

It runs `npm ci`, the type check and tests in `workers/api/`, then `wrangler d1 migrations apply dr-api --remote` (which lists pending migrations and asks before applying them) and `wrangler deploy`. It stops at the first failure. First deploy only, before it: `npx wrangler secret put RESEND_API_KEY` from `workers/api/` (paste the Resend sending key).

**Open a petition.** Add the row, then add `src/content/actions/<slug>.md` with `petition: <slug>` (CMS collection "Petitions"). The page is `/petitions/<slug>`, with the sign block under the body. Switch on "Feature on homepage" (`featured: true`) to put it in the homepage spotlight; any writing post or resource can be featured the same way, and the newest featured entry wins.

```bash
npx wrangler d1 execute dr-api --remote --command "INSERT INTO petitions (slug, title, post_url, status, opened_at) VALUES ('<slug>', '<title>', 'https://dangerousrobot.org/petitions/<slug>', 'open', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
```

**Move a petition's page.** The Worker's message pages link back to `post_url`; update it after the new page is deployed.

```bash
npx wrangler d1 execute dr-api --remote --command "UPDATE petitions SET post_url = 'https://dangerousrobot.org/petitions/<slug>' WHERE slug = '<slug>'"
```

**Close a petition.** Export first if you need the emails: the daily cleanup deletes the email column for closed petitions (names, consent and dates stay).

```bash
npx wrangler d1 execute dr-api --remote --command "UPDATE petitions SET status = 'closed', closed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE slug = '<slug>'"
```

**Export confirmed signatures to CSV.** The file holds emails: write it outside the repo (never into the checkout), keep it on your machine, and delete it when done.

```bash
mkdir -p ~/dr-exports
npx wrangler d1 execute dr-api --remote --json --command "SELECT name, email, display_consent, created_at, confirmed_at, petition_slug FROM signatures WHERE petition_slug = '<slug>' AND confirmed_at IS NOT NULL ORDER BY confirmed_at" \
  | jq -r '["name","email","display_consent","created_at","confirmed_at","petition_slug"] as $k | ($k | @csv), (.[0].results[] | [.[$k[]]] | @csv)' > ~/dr-exports/signatures-<slug>.csv
```

**Remove a signer on request** (a message to `contact@dangerousrobot.org`). Emails are stored lowercased. This is a hard delete; check the row count in the output.

```bash
npx wrangler d1 execute dr-api --remote --command "DELETE FROM signatures WHERE email = lower('<address>')"
```

After a petition closes the email is gone, so match on `name` and `petition_slug` instead.

**Local testing.** `cp .dev.vars.example .dev.vars` (emails print to the terminal instead of sending), `npx wrangler d1 migrations apply dr-api --local`, insert a petition row without `--remote`, then `npx wrangler dev`. Start the site with `PUBLIC_PETITION_API=http://localhost:8787` so the sign block talks to the local Worker. Unit tests: `npm test`.

<!-- TODO: plan additional runbook sections
Sections still needed:
- Deploy process (GitHub Actions)
- Content pipeline (how research files are generated)
- Adding a new entity / claim / source
- Linting and pre-commit hooks
- Environment variables reference
-->
