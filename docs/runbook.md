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

A refresh of a published, archived or blocked claim rewrites it as a draft and resets its sign-off; so does a forced rewrite of it (`dr draft --claim <entity>/<claim-slug> --force`, `dr step-analyze --write --force`, `dr draft --force`), and these steps apply to it too. A claim that is already a draft keeps its recorded sign-off through a refresh or forced rewrite, so after one, re-review it with `dr review` before you commit. `dr step-analyze --write --force` also clears the sidecar's Evaluator comparison, which graded the old analysis; run `uv run dr step-audit --claim <entity>/<claim-slug> --write` before approving to restore it. The pipeline keeps the published verdict and reviewer in the sidecar's `refresh` block until you approve again. A committed draft or blocked claim drops off the live site, so approve before you commit.

1. Run `uv run dr draft --claim <entity>/<claim-slug> --force`. It re-runs the claim's stored `statement` and writes back to the same path, keeping `criteria_slug`.
2. Run `uv run dr review-queue`. A refreshed claim shows "Was published: {verdict} (reviewed {date})".
3. If the verdict changed, the header says so, and pressing `a` asks for a correction: write one line for readers saying what changed and why. It becomes a dated entry under the verdict, with the previous verdict shown. Outside the queue, use `uv run dr review --claim <entity>/<claim-slug> --approve --correction "..."`. `dr publish` skips every refreshed claim, because it records no reviewer; approve each one with `dr review --approve` (adding `--correction` when the verdict changed). `dr review` and the queue's `a` action ask you to type the claim slug back before they write, and refuse when stdin is not a terminal, so a piped command cannot sign off.
4. Commit the claim, its sidecar and any new sources only after approval. Until then `dr lint` warns `refresh-pending-review`. A refresh that is blocked or fails writes nothing and leaves the claim as it was: re-run it. A `blocked` claim already on disk from an older run cannot be approved and drops off the live site if committed: re-run the refresh, or restore the claim and sidecar with `git restore` instead of committing them.

If you change the verdict with `e` before approving, approval records the change as `human_review.verdict_override`. A published verdict that matches neither the pipeline's nor a recorded override fails lint (`verdict-sidecar-mismatch`).

## Adding a product or subject

Entity files are hand-written; no command writes a product file. Claims are then drafted one criterion at a time, and each run costs model calls and archive.org captures.

1. Write the product file by hand at `research/entities/products/<slug>.md` (name, description, website, parent company, search hints; copy a neighbour).
2. Draft one claim per criterion: `uv run dr draft --criterion <slug> --entity products/<slug>`. The criterion's sentence is rendered once with the entity name and stored as the claim's `statement`; the claim is written to `research/claims/<entity-dir>/<criteria_slug>.md` with `criteria_slug` and the criterion's topics. The product criteria are `renewable-energy-hosting`, `no-training-on-user-data`, `discloses-models-used`, `discloses-energy-sourcing`, `realtime-energy-display`, `excludes-image-generation`, `excludes-frontier-models` and `open-source-models-only`. These replace the deleted `scripts/onboard-chatgpt.sh` and `scripts/onboard-openai.sh`. A criterion whose entity type does not match the entity is a usage error. Add `--dry-run` first to see the run without writing anything.
3. For a subject with no entity file, `uv run dr draft --subject <slug> "<sentence>"` writes a minimal subject record (`research/entities/subjects/<slug>.md`: name from the slug, description from the sentence) together with the claim, and never overwrites an existing record. A run that is abandoned (blocked, or a step that failed its retries) writes neither; its finding is the only record.
4. An ad hoc draft needs a criterion before `dr review --approve` can publish it. Before sign-off, run `uv run dr draft --claim <entity>/<claim-slug> --criterion <new-slug>`. It runs no model, moves no file, appends the entry to `research/templates.yaml` and sets `criteria_slug`. It is refused when the slug already exists, the claim already has `criteria_slug`, the claim is not a draft, or the entity is a company.
5. Review as usual (`uv run dr review-queue`), then commit the entity file, claims, sidecars and sources.

## Triaging findings

An abandoned, recovered or tie-broken run leaves a record under `research/findings/<yyyy>/`. Nothing in the pipeline asks a person anything mid-run, so this is where a run's problems surface.

1. After runs, check `uv run dr findings`. It lists open findings newest first, then half-claims. `--summary` counts open findings by step, rule and outcome; `--all` includes closed ones.
2. A finding that points at a pipeline bug becomes a row in `docs/UNSCHEDULED.md`, with the finding's run id in the row. Close the finding: `uv run dr findings --close <id> --note "<where it went>"`. An id prefix works while it is unambiguous.
3. A finding that is model variance or a flaky source (a `recovered` run, a one-off timeout) is closed with a note saying so.
4. A half-claim is a crash between the writes. A claim without a sidecar is replaced with `uv run dr draft --claim <ref> --force`; a subject record with no claim is reused by the next `dr draft --subject <slug>`, or removed by hand. The tools never delete anything.
5. Commit the finding files you want kept; `dr lint` ignores the directory.

## Picking a restatement

A draft with a weak verdict (`unverified`, `mixed`, `not-applicable`) or a tie-broken one carries ranked restatement candidates in its sidecar. The original stays as drafted. Until `dr review` renders the candidates (RE-AV (Review packet)), read them in the file.

1. Read the `restatement:` block in `research/claims/<entity-dir>/<claim-slug>.audit.yaml`: `why_unverified`, then each candidate's `rank`, `text`, `expected_verdict`, `decisiveness` (0 to 4) and `supporting` quotes. `dr review-queue --format json` carries the same block per claim. A candidate with `needs_new_research: true` is a lead, not a finding; running it does the research.
2. Run the pick before you approve or archive the original, since both remove the block: `uv run dr draft --restates <entity-dir>/<claim-slug> --pick <n>`. There is no sentence to type; the text and the entity come from the sidecar. It runs the candidate as a new draft (a second run and a second sign-off), writes `restates:` in the new sidecar and records `restatement.picked: <n>` on the original. It is refused before any model call when the block or candidate `<n>` is missing. `--dry-run` shows the run without writing; `--force` replaces an existing draft at the same path.
3. Attach a criterion to the new draft: `uv run dr draft --claim <new-ref> --criterion <slug>`, as in "Adding a product or subject".
4. Sign off the new draft (`uv run dr review-queue`). Decide the original separately: approve it, archive it or leave it as a draft.

"Restatement unavailable (finding `<run-id>`)" in the `dr draft` output, or a non-empty `restatement_unavailable` field (the run id) in `dr review-queue --format json`, means the Restater failed after its retries; the claim was still written, without a `restatement` block, and the run left a `partial` finding. Read it with `uv run dr findings` and triage it as in "Triaging findings".

## Model slots

Every agent runs on `--model` unless its own override is set: `--researcher-model` (`DR_RESEARCHER_MODEL`), `--analyst-model` (`DR_ANALYST_MODEL`), `--auditor-model` (`DR_AUDITOR_MODEL`), `--ingestor-model` (`DR_INGESTOR_MODEL`), `--tiebreaker-model` (`DR_TIEBREAKER_MODEL`) and `--restater-model` (`DR_RESTATER_MODEL`, which falls back to `--auditor-model`, then `--model`). These are options of `dr` itself, so they go before the subcommand (`uv run dr --tiebreaker-model <model> draft ...`). The tie-breaker is the third judge when the analyst and the Evaluator disagree. Without `DR_TIEBREAKER_MODEL` it runs on the same model as the rest of the run, so set that variable to a stronger model if you want a disagreement settled by a different one.

## Archive links for sources

The pipeline gives each new source an `archived_url` after ingesting it: an existing archive.org capture that replays with HTTP 200 for the same page if there is one, otherwise it asks archive.org to capture the page and checks that capture the same way. When the live fetch succeeded and the capture found is older than 90 days or than the page's `published_date`, it asks for a fresh capture and keeps the old one if that fails. Commands that write nothing (`dr draft --dry-run`, `dr step-ingest` without `--write`) only look for an existing snapshot. The `dr` command list in AGENTS.md says which commands can capture.

- Add links to existing sources: `uv run dr wayback-backfill <year>/<slug> ...`. It skips a source that already has a link and exits 1 if any source got none.
- Check existing links: `uv run dr wayback-backfill --recheck <year>/<slug> ...`. A link that replays with HTTP 200 for the same page prints `unchanged`. A bad link (an error page, a redirect to another page, a capture of another URL) is replaced by an existing good capture, or removed with the reason when none exists; no capture is made. A link archive.org could not check is left as is. It exits 1 on a removal or a failed check. A removal ends `no other 200 capture found` when archive.org answered every step, or with a rerun hint when a step failed (for example a 429), since a good capture may still exist. After a removal, a plain `uv run dr wayback-backfill <year>/<slug>` looks again and may save a fresh capture, which is checked before it is written.
- Both forms fetch the live page first: a capture that replays as a redirect to where the live page now ends counts as the page, as in the ingest. When the live page does not load, only captures of the URL itself count.
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

**Close a petition.** Export first if you need the emails: the daily cleanup deletes the email column for closed petitions (names, consent and dates stay), except for confirmed signers who asked for updates, whose emails stay until they opt out.

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

After a petition closes the email is gone (unless the signer asked for updates), so match on `name` and `petition_slug` instead.

**List emails.** `inv petition-emails --kind unconfirmed` prints addresses still waiting to confirm (add `--petition <slug>` for one petition); `inv petition-emails --kind updates --petition <slug>` prints the update list for one petition: signers who ticked "Send me occasional email updates about this campaign" and confirmed. Both read the live database through your wrangler login and print one address per line, so redirect to a file outside the repo (`~/dr-exports/`) and delete it when done.

**Send an update.** From a petition author's Gmail, with every address in BCC (the privacy page promises addresses are hidden from other recipients). Say in each update that replying or writing to `contact@dangerousrobot.org` stops them.

**Stop updates on request.** `inv petition-stop-updates <address>` turns updates off on every petition that address signed; the signature stays. On a closed petition, the next daily cleanup then deletes the address.

**Confirmation reminders.** The daily cron (11:17 UTC) emails unconfirmed signers once, 4 days after signing, at most 20 a run, with fresh links that replace the first email's. Nothing to run; reminders count against Resend's daily quota but not the form's hourly cap.

**Then rebuild the site.** The petition page carries the signer list as it stood at the last build (`src/components/PetitionSign.astro` reads it from the Worker at build time). Readers with JavaScript load the live list, so the name leaves their view at once; readers without JavaScript and search crawlers keep seeing it until the next deploy. Check the row count above first, because the build reads the live database. A deploy runs on a push to `main` or a manual run of the "Deploy to GitHub Pages" workflow (`docs/architecture/ci-deploy.md`); with nothing to push, start one from the repository's Actions tab or with `gh workflow run deploy.yml --ref main`.

**Local testing.** `cp .dev.vars.example .dev.vars` (emails print to the terminal instead of sending), `npx wrangler d1 migrations apply dr-api --local`, insert a petition row without `--remote`, then `npx wrangler dev`. Start the site with `PUBLIC_PETITION_API=http://localhost:8787` so the sign block talks to the local Worker. Unit tests: `npm test`.

<!-- TODO: plan additional runbook sections
Sections still needed:
- Deploy process (GitHub Actions)
- Content pipeline (how research files are generated)
- Adding a new entity / claim / source
- Linting and pre-commit hooks
- Environment variables reference
-->
