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

Readers report errors through the GitHub issue form `.github/ISSUE_TEMPLATE/correction.yml`, linked from `/corrections`. Reports arrive as issues with the `correction` label. A published correction is recorded in the claim's optional `corrections` frontmatter (`date`, `summary`, `previous_verdict`), which the claim page shows under the meta row. A recheck's pending draft keeps existing `corrections` entries, and so does a forced rewrite of a draft.

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

A published or archived claim is never rewritten in place. `dr recheck` re-runs it and writes the result as a pending draft beside the live claim, so the live page stays up while you decide. `dr draft --claim <entity>/<claim-slug> --force` (and `dr draft --force`, `dr step-analyze --write --force`, `dr step-audit --claim <ref> --write`) on a published or archived claim is a usage error that names `dr recheck --claim`; `dr step-audit --entity|--topic --write` grades such a claim but writes only the drafts' sidecars; only a draft is overwritten in place, and a blocked claim still resets to draft. Rechecks cost model calls and archive.org captures.

1. See what is due: `uv run dr recheck --due --dry-run`. It lists each due published claim with its due date and calls no model. A claim is due when its `next_recheck_due` has passed or, without one, when `as_of` plus `recheck_cadence_days` (default 60) has passed. A claim that already has a pending draft is not listed.
2. Run one claim, `uv run dr recheck --claim <entity>/<claim-slug>`, or every due claim, `uv run dr recheck --due`. A batch runs the claims one after another under one LLM limit and prints one summary line per claim (ran, recovered or abandoned, and whether the verdict changed). An abandoned claim leaves only a finding (`uv run dr findings`), including a claim the batch could not start (its entity file does not load) and a run that raised; the batch carries on and exits 0.
3. The pending draft is `research/pending/<entity-dir>/<claim-slug>.md` plus its `.audit.yaml`. The live claim and its sidecar are untouched, and the site does not read `research/pending/`. `dr lint` checks the pending draft as a draft and counts the sources only it cites as referenced.
4. Run `uv run dr review`. The pending draft is listed under the live claim's ref with a Recheck row in its header facts: "verdict unchanged, N of M quotes still found, K sources re-fetched" (with a second row "N quotes not rechecked" when a cited source inside its cadence kept its stored quotes unchecked) or "verdict changed: X to Y". Sources older than the claim's cadence were fetched again and their quotes and archive link re-checked; each outcome is in the pending sidecar's `sources_consulted[].recheck`, and the shared source files are not rewritten. `uv run dr review --format json` prints the same record without writing anything.
5. Promote it with `a` in the walkthrough or `uv run dr review --claim <entity>/<claim-slug> --approve`. Both ask you to type the live claim slug back and refuse when stdin is not a terminal, so a piped command cannot sign off. Promotion moves the pending files over the live ones and the same approval completes the sign-off. If the verdict changed, approval needs a correction: press `a` and write one line for readers saying what changed and why, or pass `--correction "..."`. It becomes a dated entry under the verdict, with the previous verdict shown. A plain `dr review --claim <ref>` sign-off of a pending draft is refused, pointing at `--approve`. To discard a pending draft, press `d` in the walkthrough; it deletes only the pending pair.
6. Commit the claim, its sidecar and any new sources only after approval. If the process stopped between the moves and the approval, the live claim is a draft with a `refresh` block, `dr lint` warns `refresh-pending-review`, and a second `--approve` finishes it. If it stopped after moving the sidecar and before moving the claim, the live claim is still published with the pending sidecar (carrying the `refresh` block) beside it, and the pending claim file has no sidecar: a second `--approve` finishes the move and the approval. For an archived live claim that state cannot be told apart, so move the pending claim file over the live one by hand, then approve. A recheck that is blocked or abandoned writes nothing but its finding and leaves the claim as it was: run it again. A recheck whose writer fails (`<ref>: failed (half-claim)`) also leaves the live pair and any earlier pending pair as they were, because the pending pair is written in a `.dr-recheck-*` directory at the repo root and moved into `research/pending/` only after every write succeeded; the only files it can leave are the new source files it wrote under `research/sources/`, which the next run reuses. The claim stays due, and the finding is in `dr findings`.

If you change the verdict with `e` before approving, approval records the change as `human_review.verdict_override`. A published verdict that matches neither the pipeline's nor a recorded override fails lint (`verdict-sidecar-mismatch`).

## Scheduled rechecks

No job runs `dr recheck` yet; the job is a backlog row in `docs/UNSCHEDULED.md`. A job that does must do the following.

1. Run `uv run dr recheck --due` in `pipeline/`, then `uv run dr findings`. The command exits 0 unless it failed to start, so read the summary lines and the findings, not the exit code, to see which claims were abandoned.
2. Provide the provider keys for the models in use as GitHub Actions repository secrets, named as the environment variables the pipeline reads (the model-to-variable mapping is `_required_env_for_model` in `pipeline/orchestrator/cli.py`; `_check_provider_api_keys` fails the run before any model call when one is missing). When `search_backend` is `brave`, also provide the Brave key (`_check_search_key`); the default `tavily` backend needs `TAVILY_API_KEY`, and Brave is its fallback. Today only `YOUTUBE_API_KEY` exists as a repository secret (`docs/architecture/ci-deploy.md`).
3. Commit the pending drafts (`research/pending/`), the new sources and the findings to an Actions branch, never to main. Fetch that branch locally and review it with `dr review`; nothing is promoted without a person at a terminal.
4. Do not run `dr review` or any sign-off in the job.

## Adding a product or subject

Entity files are hand-written; no command writes a product file. Claims are then drafted one criterion at a time, and each run costs model calls and archive.org captures.

1. Write the product file by hand at `research/entities/products/<slug>.md` (name, description, website, parent company, search hints; copy a neighbour).
2. Draft one claim per criterion: `uv run dr draft --criterion <slug> --entity products/<slug>`. The criterion's sentence is rendered once with the entity name and stored as the claim's `statement`; the claim is written to `research/claims/<entity-dir>/<criteria_slug>.md` with `criteria_slug` and the criterion's topics. The product criteria are `renewable-energy-hosting`, `no-training-on-user-data`, `discloses-models-used`, `discloses-energy-sourcing`, `realtime-energy-display`, `excludes-image-generation`, `excludes-frontier-models` and `open-source-models-only`. These replace the deleted `scripts/onboard-chatgpt.sh` and `scripts/onboard-openai.sh`. A criterion whose entity type does not match the entity is a usage error. Add `--dry-run` first to see the run without writing anything.
3. For a subject with no entity file, `uv run dr draft --subject <slug> "<sentence>"` writes a minimal subject record (`research/entities/subjects/<slug>.md`: name from the slug, description from the sentence) together with the claim, and never overwrites an existing record. A run that is abandoned (blocked, or a step other than the restater that failed its retries) writes neither; its finding is the only record. A run whose restater failed still writes the claim and records a `partial` finding.
4. An ad hoc draft needs a criterion before `dr review --approve` can publish it. Before sign-off, run `uv run dr draft --claim <entity>/<claim-slug> --criterion <new-slug>`. It runs no model, moves no file, appends the entry to `research/templates.yaml` and sets `criteria_slug`. It is refused when the slug already exists, the claim already has `criteria_slug`, the claim is not a draft, or the entity is a company (`dr draft` refuses a company entity in every mode with one usage error, exit 2: companies are read-only parent records, not a claim target).
5. Review as usual (`uv run dr review`), then commit the entity file, claims, sidecars and sources.

## Triaging findings

An abandoned, recovered, tie-broken or partial run leaves a record under `research/findings/<yyyy>/`. Nothing in the pipeline asks a person anything mid-run, so this is where a run's problems surface. A `partial` finding means the claim was written but the restater failed, so it carries no `restatement` block.

1. After runs, check `uv run dr findings`. It lists open findings newest first, then half-claims. `--summary` counts open findings by step, rule and outcome; `--all` includes closed ones.
2. A finding that points at a pipeline bug becomes a row in `docs/UNSCHEDULED.md`, with the finding's run id in the row. Close the finding: `uv run dr findings --close <id> --note "<where it went>"`. An id prefix works while it is unambiguous.
3. A finding that is model variance or a flaky source (a `recovered` run, a one-off timeout) is closed with a note saying so.
4. A half-claim is a crash between the writes. A claim without a sidecar is replaced with `uv run dr draft --claim <ref> --force`. A pending recheck under `research/pending/` with no sidecar is listed under its live ref: a recheck stopped between moving its claim and its sidecar is replaced with `uv run dr recheck --claim <ref>`, and a promotion stopped between its moves is finished with `uv run dr review --claim <ref> --approve`. A `.dr-recheck-*` directory at the repo root is a recheck killed while writing; nothing reads it, so remove it by hand. A subject record with no claim is reused by the next `dr draft --subject <slug>`, or removed by hand. The tools never delete anything.
5. Commit the finding files you want kept; `dr lint` ignores the directory.

## Replaying findings after a pipeline change

After a pipeline change that might fix what an abandoned run hit, re-run the finding instead of retyping the command.

1. `uv run dr findings --replay --finding <id>` replays one finding (an id prefix works while it is unambiguous). `uv run dr findings --replay` replays every open finding, oldest first, one after another under one LLM limit. Each replayed finding is one full paid run, so replay one finding first.
2. The run uses the finding's recorded claim spec and config, with today's per-agent model settings. A `dr draft` finding writes a draft; a `dr recheck` finding writes a pending draft. Review either as usual.
3. A success prints `<id>: closed (replay <new id> wrote <path>)` (for a `dr recheck` finding, `wrote pending draft <path>`) and closes the finding with `by: replay`. A failure prints `<id>: failed (finding <new id>)`, records a new finding with `replays: <id>` and leaves the old one open, so `dr findings` shows both. A chain of such findings is replayed once, through its newest finding (also when `--finding` names an older one), and a success closes the whole chain.
4. Skipped with a `skipped:` line and left open: `recovered`, `split` and `partial` findings (their claim was written; close them by hand) and `dr step-analyze` and `dr step-audit` findings (one-agent reruns). A replay that cannot start prints `not replayed: <reason>`, writes nothing and leaves the finding open: a `dr draft` finding whose claim is now published or archived (the line points at `uv run dr recheck --claim <ref>`), a missing claim file, an entity that does not load, or a criterion that `research/templates.yaml` no longer has for that entity.
5. Exit codes: a batch exits 0 unless it could not start (a missing API key, bad options). With `--finding`, 0 means the finding was closed and 1 means it was not.

## Picking a restatement

A draft with a weak verdict (`unverified`, `mixed`, `not-applicable`) or a tie-broken one carries ranked restatement candidates in its sidecar. The original stays as drafted. `dr review` prints the candidates in the draft's packet.

1. Run `uv run dr review` and read the candidates in the draft's packet: each candidate's rank, expected verdict and confidence, `decisiveness` (0 to 4) and text. `uv run dr review --claim <entity-dir>/<claim-slug> --format text | less` prints the same for one claim. The rest of the block is in `uv run dr review --claim <entity-dir>/<claim-slug> --format json`, under `restatement`: `why_unverified`, and each candidate's `supporting` quotes and `needs_new_research`. A candidate with `needs_new_research: true` is a lead, not a finding; running it does the research.
2. Press `r` at the key prompt and enter the candidate number. It records `restatement.picked: <n>` on the original (on a pending recheck, on the pending sidecar, which the printed command then reads) and prints the exact `dr draft --restates <entity-dir>/<claim-slug> --pick <n>` command. Nothing runs inside `dr review`. You can approve or archive the original in the same walkthrough: while a pick is recorded and no claim restates the original yet, approving or archiving keeps the block. Without a pick, both remove it.
3. After the walkthrough, run the printed command, whether or not you approved or archived the original. There is no sentence to type; the text and the entity come from the sidecar. It runs the candidate as a new draft (a second run and a second sign-off) and writes `restates:` in the new sidecar. It is refused before any model call when the block or candidate `<n>` is missing, or when the candidate's file would be the original's. `--dry-run` shows the run without writing; `--force` replaces an existing draft at the same path.
4. Attach a criterion to the new draft: `uv run dr draft --claim <new-ref> --criterion <slug>`, as in "Adding a product or subject".
5. Sign off the new draft (`uv run dr review`). Decide the original separately: approve it, archive it or leave it as a draft.

"Restatement unavailable (finding `<run-id>`)" in the packet or the `dr draft` output, or a non-empty `restatement_unavailable` field (the run id) in `dr review --format json`, means the Restater failed after its retries; the claim was still written, without a `restatement` block, and the run left a `partial` finding. The `r` key is refused for it. Read the finding with `uv run dr findings` and triage it as in "Triaging findings".

## Model slots

Every agent runs on `--model` unless its own override is set: `--researcher-model` (`DR_RESEARCHER_MODEL`), `--analyst-model` (`DR_ANALYST_MODEL`), `--auditor-model` (`DR_AUDITOR_MODEL`), `--ingestor-model` (`DR_INGESTOR_MODEL`), `--tiebreaker-model` (`DR_TIEBREAKER_MODEL`) and `--restater-model` (`DR_RESTATER_MODEL`, which falls back to `--auditor-model`, then `--model`). These are options of `dr` itself, so they go before the subcommand (`uv run dr --tiebreaker-model <model> draft ...`). The tie-breaker is the third judge when the analyst and the Evaluator disagree. Without `DR_TIEBREAKER_MODEL` it runs on the same model as the rest of the run, so set that variable to a stronger model if you want a disagreement settled by a different one.

## Archive links for sources

The pipeline gives each new source an `archived_url` after ingesting it: an existing archive.org capture that replays with HTTP 200 for the same page if there is one, otherwise it asks archive.org to capture the page and checks that capture the same way. When the live fetch succeeded and the capture found is older than 90 days or than the page's `published_date`, it asks for a fresh capture and keeps the old one if that fails. Commands that write nothing (`dr draft --dry-run`, `dr step-ingest` without `--write`) only look for an existing snapshot. The `dr` command list in AGENTS.md says which commands can capture.

- Add links to existing sources: `uv run dr recheck --sources <year>/<slug> ...`. A source with no link gets one only when archive.org returns a checked capture; the command exits 1 if any source got none.
- Check existing links with the same command. A link that replays with HTTP 200 for the same page prints `unchanged`. A bad link (an error page, a redirect to another page, a capture of another URL) is replaced by an existing good capture; when none exists the old link is kept, the reason is printed and the exit code is 1. No capture is saved to replace a bad link. The message ends `no other 200 capture found` when archive.org answered every step, or with a rerun hint when a step failed (for example a 429), since a good capture may still exist. A link archive.org could not check is left as is and exits 1.
- The command also checks the live page's text against each source's `key_quotes` and prints how many were found and each missing quote; quotes never change the exit code. It writes only `archived_url`.
- `--sources` fetches the live page first: a capture that replays as a redirect to where the live page now ends counts as the page, as in the ingest. When the live page does not load, only captures of the URL itself count.
- A failed lookup is recorded in the claim sidecar as `sources_consulted[].archive` with `status: failed` and the reason (for example `archive.org TimeGate check failed (HTTP 429)`). The source is still written, without a link; run `dr recheck --sources <year>/<slug>` later.
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
