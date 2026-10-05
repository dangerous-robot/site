# Petition signatures

**Status**: `in progress` (launched 2026-10-05: Worker deployed, pledge post live with the sign block; two production tests deferred to `docs/UNSCHEDULED.md`)
**Last updated**: 2026-10-05
**Decision** (`docs/decisions.md`, 2026-10-04, quoted): "Pledge signatures are collected on the site. A Cloudflare Worker and D1 database (the stack `docs/plans/public-feedback.md` chose) take name and email, confirm by email, and show a signer's name publicly only if they opt in. Only Brandon receives the signer list. No hosted form in the meantime: the pledge post and its homepage menu entry wait for the Worker, and beta.4 waits with them. ..."

Very basic petition management for dangerousrobot.org: open a petition, collect signatures on the post itself, show a count and (with consent) a public signatory list, export, close, and remove a signer on request. The first petition is the pledge post; more pledges may follow.

## Status checklist

Ticked as items land (AGENTS.md rule 4). Item ids are the Scope table ids below.

- [x] Design questions answered by Brandon, 2026-10-04 (see Decisions)
- [x] Needs from Brandon: account steps 1 to 4 (Worker deployed 2026-10-05, version 547e1171)
- [x] Needs from Brandon: copy, policy and naming items 5 to 9
- [x] W1 to W6: Worker, D1 schema, routes, email, cron, spam layers (`workers/api/`, 25 tests in `workers/api/test/`)
- [x] S1 to S3: `petition` field, Sveltia mirror, sign block on the post (`src/components/PetitionSign.astro`, shared text in `src/lib/petition.ts`)
- [x] S4: pledge post wired up (`petition: prohibit-ai-self-improvement`, published 2026-10-05; the editor's note links the sign form at `#sign`, added under `refocus-foundation.md` G1)
- [x] O1: runbook section "Petitions: open, close, export, remove"; architecture doc `docs/architecture/petitions.md`
- [x] Testing table run against a deployed Worker, 2026-10-05, except Export and No-JS path (deferred to `docs/UNSCHEDULED.md`, Petition Worker follow-ups). Fixes found on the way: hourly email cap, review fixes W1 to W4, self-hosted fonts, Cloudflare analytics and email obfuscation turned off
- [x] `refocus-foundation.md` G1 unblocked (pledge post live with the sign block, `draft: false`)

## Goal

`src/content/writing/pledge-prohibit-ai-self-improvement-pledge.md` ends its editor's note "You can add yourself as a signatory to the pledge at ..." with no destination. `docs/plans/refocus-foundation.md` G1 (finish the pledge post) and "Needs from Brandon, beta.4" item 1 wait on this plan. When it lands, a reader can sign on the post, confirm by email, see the count and the names of signers who opted in, and remove their own signature; Brandon can export, close and delete from his machine; and the next pledge needs a database row and a frontmatter field, not new code.

## Decisions

| # | Question | Answer (Brandon, 2026-10-04) |
|---|---|---|
| 1 | Where signatures live | Cloudflare Worker and D1 (the `public-feedback.md` stack, which sets the `api.dangerousrobot.org` subdomain in its Decisions table, row 3) |
| 2 | What a signer gives | Name and email, confirmed by an email link |
| 3 | Public list | Opt-in: a separate, unchecked box; email never shown |
| 4 | Who receives the list | Brandon only |
| 5 | Where signing happens | On the post itself, not a link-out |
| 6 | Interim hosted form (Tally link-out) | Not chosen. The pledge post, its homepage menu entry and beta.4 wait for the Worker |

## Facts the plan relies on

Checked in the repo on 2026-10-04.

- `workers/` does not exist. `docs/plans/public-feedback.md` chose, in its Decisions table, Cloudflare Workers + D1 (Skip Formspree prototype), `api.dangerousrobot.org` (API subdomain), Turnstile, and `workers/feedback/` in this repo (Worker location); its Resolved Decisions list adds Resend for email (item 2, Email provider), but none of it is built. This plan builds the Worker and the D1 database first; the feedback forms add their tables and routes later.
- `src/pages/writing/[...slug].astro` renders the post body with `<Content />` (line 32). Posts are plain Markdown through a glob loader (`src/content.config.ts`, `writing` collection at line 426), so a frontmatter field is the only way to add a block under one post without MDX.
- `public/admin/config.yml` defines the Sveltia `writing` collection (line 26), which mirrors the schema.
- The Cloudflare account already holds the site's DNS and 301 redirects (`scripts/seo/apply-cloudflare-redirects.sh`).
- The pledge post is untracked and `draft: true`. `refocus-foundation.md` G2 will add a homepage menu entry that links to the post.

## Design

### Choices

| Choice | Detail |
|---|---|
| Where signatures live | Cloudflare D1 (SQLite) behind a Worker at `api.dangerousrobot.org` |
| Fields collected | Name, email, "show my name publicly" checkbox (default off), timestamp. No IP stored, no address, no phone |
| Verification | Email confirmation link (double opt-in). Unconfirmed rows are purged after 7 days and never counted |
| Spam protection | Honeypot field, minimum fill time, per-IP rate limit (Cloudflare's rate-limiting binding; no IP is written to the database), and the confirmation email itself. No CAPTCHA at launch; add self-hosted ALTCHA first if spam appears, Turnstile second |
| Confirmation and removal email | Resend free plan ($0, 100 emails/day, 3,000/month) sending from `dangerousrobot.org`. Each email carries a "remove my signature" link |
| Display on the site | A `petition:` frontmatter field renders a sign block and count under the post body. Count and public names come from a client-side fetch to the Worker (the site's own subdomain, no third party), with a build-time number as the no-JS fallback |
| Export | `wrangler d1 export` or a `wrangler d1 execute ... --json` query from Brandon's machine; no admin web UI |
| Close a petition | `status` column (`open`, `closed`); the Worker refuses new signatures and the page says "Closed on [date], N signatories." |
| Remove a signer | Self-service link in every email, or Brandon runs one `wrangler d1 execute` delete on a request to `contact@dangerousrobot.org` |
| Cost | $0 at this site's scale (Workers Free 100k requests/day, D1 free 100k writes/day, Resend free). First paid step is Workers Paid at $5/month |
| Effort | 1 to 2 days of build; about an hour of account work |

### Worker and data

- D1 tables: `petitions` (`slug`, `title`, `post_url`, `status`, `opened_at`, `closed_at`) and `signatures` (`id`, `petition_slug`, `name`, `email`, `display_consent`, `created_at`, `confirmed_at`, `token_hash`).
- Routes:
  - `POST /petitions/{slug}/sign`: honeypot, time check, rate limit, insert unconfirmed, send email. A `fetch` from the component gets JSON and the component shows "check your email" in place; a plain form POST (no JS) gets a Worker-served "check your email" page that links back to `post_url`.
  - `GET /petitions/{slug}/confirm?t=` and `GET /petitions/{slug}/remove?t=`: each shows a landing page with one button; nothing changes on GET.
  - `POST` to the same two paths: sets `confirmed_at`, or hard-deletes, then returns a Worker-served result page ("Thank you, you are signatory N", N being the confirmed count after this row; or "Your signature is removed") that links back to `post_url#sign`. Worker pages are plain HTML with inline styles and load nothing from outside `api.dangerousrobot.org`.
  - `GET /petitions/{slug}`: public JSON with `status`, `count`, and `names[]` for consenting confirmed signers; not cached (`no-store`), so a signer returning from the confirm page sees the new count; one D1 read per page view.
- Why the extra click on confirm and remove: email link scanners (Outlook Safe Links, Gmail prefetch, corporate proxies) fetch every URL in a message. A one-click GET would let a scanner confirm a signature or silently delete one.
- Rate limit: the Workers rate-limiting binding (`[[ratelimits]]` in `wrangler.toml`, 5 per 60 seconds per IP). Counts are approximate and per Cloudflare location. No rate-limit table, so no IP or IP hash ever reaches D1.
- One signature per address per petition (unique index on `petition_slug`, lowercased `email`). Re-signing while unconfirmed rotates the token and resends; re-signing a confirmed address sends nothing and gets the same "check your email" reply, so the form never reveals who has signed.
- Minimum fill time is weak by design: the page script sends the elapsed milliseconds (`performance.now()`, not the system clock, so clock skew cannot drop a signer), and a missing value (the no-JS form) is accepted.
- An unconfirmed address gets at most one confirmation email per 10 minutes, so the form cannot flood someone else's inbox.
- A scheduled Worker trigger (cron) deletes unconfirmed rows older than 7 days and, for closed petitions past the retention window, nulls the email column.
- D1 queries use bound parameters only, as `public-feedback.md` requires for its Worker.

### Display on the static site

Client-side fetch of `GET /petitions/{slug}` (recommended): live, one small module script in the same pattern as the site's other vanilla scripts. No-JS readers see the build-time number and a form that still posts as a plain HTML form. Considered and not chosen: a build-time fetch plus a daily GitHub Actions rebuild (up to 24 hours stale), and a link-out to a page served by the Worker (leaves the site's design and its no-tracker promise behind).

Build step (decided 2026-10-04): `astro build` fetches the Worker with a 3-second timeout and renders no number on any error or missing petition, so a Worker outage never fails the site deploy.

### Privacy blurb (approved by Brandon 2026-10-04)

"We keep your name, your email, and whether you want your name shown. Your email is used only to confirm your signature. We never show it, share it, or send you anything else. Only Dangerous Robot can read the list; Cloudflare stores it and Resend delivers the confirmation email. To remove your signature, use the link in your confirmation email or write to contact@dangerousrobot.org."

Consent checkbox label: "Show my name on the public list of signers" (unchecked by default).

The blurb makes no retention promise on purpose; the cleanup in P5 still runs.

## Requirements

Functional:

- R1: Create a petition by adding a row (slug, title, status, opened date) and a frontmatter field on the post; no admin UI.
- R2: A visitor signs with name and email, confirms by email, and lands on a "thank you, you are signatory N" page.
- R3: The post shows the current count. Signatories who opted in appear in a public list (name only, newest first, exactly as the signer typed it).
- R4: Export to CSV with exactly the columns the privacy blurb promises.
- R5: Close a petition; the page and the Worker both reflect it.
- R6: Remove a signer on request within days, not weeks, and have the count drop.
- R7: Reusable for the next pledge without new code.

Privacy and fit with the site's stance (`src/pages/values.astro`, TreadLightlyAI ethos):

- P1 Data minimization: name and email only. No IP, user agent, address, phone, or "tell us why" free text at launch (free text is where abuse and sensitive data arrive).
- P2 Consent for display: separate, unchecked box; email never displayed; consent recorded with its timestamp so it can be shown on request.
- P3 Verification vs friction: email confirmation costs one extra click and loses some signers, but it makes the count mean something, stops most bots without a CAPTCHA, and gives each signer a removal link. The UK Parliament petition site uses the same step for the same reasons ([petition.parliament.uk FAQ via Full Fact](https://fullfact.org/europe/possible-repeatedly-sign-parliamentary-petition/)).
- P4 Spam without an invasive CAPTCHA: layers that touch no third party first; a CAPTCHA only when evidence demands it. This differs from the `public-feedback.md` Decisions table's Turnstile row (Turnstile in the stack) on purpose: email confirmation already gates petitions, and the feedback forms have no such gate. Revisit if the feedback forms ship with Turnstile and one consistent stack matters more.
- P5 Retention: unconfirmed rows purged after 7 days; emails deleted when a petition closes (name, consent flag and date kept for the record). Not promised in the blurb.
- P6 Deletion: self-service link plus a manual path via `contact@dangerousrobot.org`; deletion is a hard delete, not a flag.
- P7 Law: GDPR likely does not apply by letter (a site merely reachable from the EU is not "targeting" per EDPB guidance summaries: [Hunton](https://hunton.com/privacy-and-information-security-law/edpb-publishes-final-version-of-guidelines-on-the-gdprs-territorial-scope)), but the pledge invites "international agreement," so behave as if it does: consent as the basis, a short notice, access and erasure on request. CCPA thresholds ($25M revenue, 100k California residents' data, or 50% revenue from selling data) are not met ([California AG](https://oag.ca.gov/privacy/ccpa), checked 2026-10-04). Washington has no comprehensive consumer privacy statute in force as of mid-2026 (secondary sources: [privacylawmap](https://privacylawmap.com/blog/washington-state-privacy-law-guide), [BakerHostetler](https://www.bakerlaw.com/insights/washington-states-2026-tech-legislative-agenda-what-in-house-counsel-should-watch/); unverified against the legislature's site).
- P8 No third-party trackers: the post loads nothing from outside `dangerousrobot.org` and `api.dangerousrobot.org`.
- P9 Who can see the data: Brandon (Cloudflare account, wrangler) and the processors Cloudflare (storage, US/global edge) and Resend (email delivery, US). The notice names both. The list goes to no one else (decision 4).
- P10 Honest copy: the notice says what is kept, who can see it, and how to be removed.

## Scope

### W. Worker and database

| ID | Item | Files |
|---|---|---|
| W1 | Worker project with `wrangler.toml`, bound to the D1 database and the `api.dangerousrobot.org` route | `workers/api/` (new) |
| W2 | D1 schema and migration for `petitions` and `signatures` as in "Worker and data" | `workers/api/migrations/` (new) |
| W3 | Routes: sign (JSON for the component, "check your email" page for a no-JS POST), confirm (GET landing, POST action returning the "signatory N" page), remove (GET landing, POST action returning the removed page), public JSON (not cached); CORS limited to `https://dangerousrobot.org`. Result pages link back to `post_url#sign` | `workers/api/src/` |
| W4 | Confirmation email through Resend with confirm and remove links; tokens stored as hashes | `workers/api/src/` |
| W5 | Cron trigger: purge unconfirmed rows older than 7 days; null emails on closed petitions past retention | `workers/api/src/`, `wrangler.toml` |
| W6 | Spam layers: honeypot, minimum fill time (3 seconds), per-IP rate limit through the rate-limiting binding (5 sign POSTs per IP per minute); closed petitions refuse signatures | `workers/api/src/` |

### S. Site

| ID | Item | Files |
|---|---|---|
| S1 | Add optional `petition: z.string()` (the petition slug) to the `writing` schema | `src/content.config.ts` |
| S2 | Mirror `petition` in the Sveltia `writing` collection | `public/admin/config.yml` |
| S3 | `<PetitionSign>` component rendered after `<Content />` when `post.data.petition` is set, with `id="sign"`: count line, form (name, email, consent checkbox, honeypot, hidden timestamp), privacy blurb, public list, closed state. Check it against site patterns (typography, spacing, form styles) before building | `src/components/PetitionSign.astro` (new), `src/pages/writing/[...slug].astro` |
| S4 | Pledge post: set `petition:`, link the editor's note to `#sign` on the same page. This is `refocus-foundation.md` G1; `draft: false` lands there | `src/content/writing/pledge-prohibit-ai-self-improvement-pledge.md` |

### O. Operations

| ID | Item | Files |
|---|---|---|
| O1 | Runbook section "Petitions: open, close, export, remove", with the exact `wrangler d1 execute` commands for each | `docs/runbook.md` |

## Needs from Brandon

Account steps (about an hour):

1. Done 2026-10-04: D1 database `dr-api` created in region WNAM (`database_id` `8594b5ae-cfeb-470c-b0cd-8509df1fe108`, for W1's `wrangler.toml`). No manual `api` DNS record: declare `api.dangerousrobot.org` as a Worker custom domain in `wrangler.toml` and the deploy creates the record and certificate.
2. Done 2026-10-05: Cloudflare: set the Worker secret `RESEND_API_KEY`, apply the migration, then deploy with `wrangler` (or hand the deploy to an agent once secrets exist). Waits on W1, since secrets attach to an existing Worker.
3. Done 2026-10-04: Resend account created and `dangerousrobot.org` verified.
4. Decided 2026-10-04: sender `no-reply@dangerousrobot.org` (`MAIL_FROM` in `workers/api/wrangler.toml`).

Copy and policy:

5. Decided 2026-10-04: privacy blurb approved as written above, naming Cloudflare and Resend.
6. Decided 2026-10-04: unconfirmed rows purged after 7 days; emails deleted when a petition closes; 5 sign POSTs per IP per minute.
7. Decided 2026-10-04: public name shown exactly as typed, only with the box checked.
8. Decided 2026-10-04: the sixth POST in a minute gets 429 with a plain "try again in a minute" message.
10. Decided 2026-10-04 (after the deployed test): a site-wide cap of 30 confirmation emails per hour; over it, `/sign` returns 429 "try again in an hour". The per-IP limiter counts per Cloudflare machine, so fresh connections slipped past it in production (15 spaced POSTs, all 200; over one connection, 429 from the 7th). The cap counts recently emailed addresses (rows by `created_at`), not individual sends; migration 0002 indexes `created_at`. Changed 2026-10-05 after code review: re-sends reuse their row, so row counting let one script send unlimited re-sends; the cap now counts sends in the timestamp-only `email_sends` table (migration 0003), and the shared ceiling still lets 30 bogus sign-ups lock out real signers for an hour (accepted; ALTCHA is the response).
9. Decided 2026-10-04: Worker directory `workers/api/`, D1 database `dr-api` (one Worker serves petitions and, later, feedback). Recorded in `public-feedback.md` Decisions table, Worker location.

## Testing

Oracles are a `wrangler d1 execute dr-api --command "..."` query or a `curl` against the Worker, not a dashboard look.

| Area | Action | Expected | Artifact |
|---|---|---|---|
| Consent | Sign twice from two addresses, one with the box checked, confirm both | `GET /petitions/{slug}` returns `count: 2` and one name | curl output |
| Consent record | Query the consenting row | `display_consent = 1` with the same `created_at`; the other row `0` | query output |
| Email never shown | Grep the JSON and the rendered page for `@` | No matches | grep output |
| Deletion (self-service) | Follow the remove link from the confirmation email and press the button | 200 page, row gone, count drops by one, name gone from JSON | query plus curl before and after |
| Deletion (manual) | Run the documented delete for an email | Same as above; runbook step works as written | shell transcript |
| Export | Run the runbook's export query (O1) to CSV | Columns are exactly `name, email, display_consent, created_at, confirmed_at, petition_slug` | CSV header |
| Schema holds no tracking data | `PRAGMA table_info(signatures)` | No IP or user agent column | query output |
| Spam: honeypot | POST with the hidden field filled | 200 (no signal to bots) and no row inserted | query count unchanged |
| Spam: too fast | POST with timestamp under 3 seconds old | 200, no row | same |
| Spam: rate limit | POSTs from one IP over a single connection (`curl --next`) | 429 within a few posts past five (Needs item 8); counts are per machine, so separate connections may all get 200 | curl output |
| Spam: hourly email cap | Seed 30 `email_sends` rows in the last hour, then sign | 429, no email sent (Needs item 10); a unit test covers it, so no production run needed | test output |
| Spam: unconfirmed never counts | Sign, do not confirm | Count unchanged; row has null `confirmed_at`; gone after the 7-day purge (run the cron handler with `wrangler dev --test-scheduled`) | query before and after |
| Close | Set `status = closed`, POST a signature | Worker refuses with a clear message; page shows "Closed on [date], N signatories" | curl plus screenshot |
| No-JS path | Submit the form with scripts disabled | Plain POST works and redirects to a "check your email" page | screenshot |
| No third-party requests | Load the post with DevTools network open | Only `dangerousrobot.org` and `api.dangerousrobot.org` | network list |
| Token safety | Reuse a confirm token, use a malformed one | Idempotent 200 or 400; no row change | curl output |
| Link scanners | `curl` the confirm and remove URLs with GET | Landing page only, no row change; the POST from the landing-page button is what changes the row | query before and after each |

## Options considered

Prices and features checked 2026-10-04 unless marked.

### Hosted tools

| Option | Cost | Privacy posture | Export | Embed or link | Verdict |
|---|---|---|---|---|---|
| Tally ([pricing](https://tally.so/pricing), [privacy](https://tally.so/privacy)) | Free, unlimited forms and submissions under fair use; Pro $24/mo removes branding | Belgium company, data in the EU; Tally says it uses no third-party trackers or ads on forms ([Tally help](https://tally.so/help/how-to-create-a-gdpr-compliant-form), vendor claim; its privacy notice does not address respondent data explicitly) | CSV | Either; embed loads Tally's script, link-out loads nothing on the site | **Not chosen** (decision 6). Email verification is a Business-plan ($74/mo) feature ([Tally help](https://tally.so/help/form-settings)); no public count or list; Tally branding on free; data in a third party |
| Formspark ([pricing](https://formspark.io/pricing/)) | 250 submissions free for life; $25 one-time for 50,000 (promo price) | GDPR/CCPA/DPA pages exist; data location not checked | CSV, JSON | Form posts to Formspark | Plain form backend only; no verification, count, or list. 250 free submissions is tight for a petition |
| Formspree ([plans](https://formspree.io/plans), [privacy](https://formspree.io/legal/privacy-policy/)) | 50/mo free, 30-day history; export only from Professional ($20/mo) | US infrastructure; policy says data may be used for "customized content and advertising" and third-party marketing cookies | Paid only | Form post | **Rejected**: advertising use conflicts with the site's stance; export is paywalled |
| Action Network ([plans](https://www.actionnetwork.org/partnerships), [privacy](https://actionnetwork.org/privacy)) | Free plan includes petitions; paid from $15/mo for email sends | US data; cookies, web beacons and analytics on their pages; you own and can export your data; "exclusively partners with progressive causes" | Yes | Link-out or embed | **Rejected**: an advocacy CRM; signers land in a mailing system, pages carry trackers, eligibility rests on their judgment of the cause. Free-plan limits unverified |
| Change.org ([privacy](https://change.org/policies/privacy), updated 2026-05-20) | Free | Signers join Change.org's own list and get promoted other petitions; AdRoll marketing cookies; creator does not get emails | Limited | Link-out | **Rejected**: signers' data is the product |
| Google Forms | Free | Data at Google; a Google account and Google scripts are involved | Sheets | Either | Not considered further; weaker privacy story than Tally for no gain |

### Self-hosted or serverless, compatible with GitHub Pages

| Option | Cost | Privacy posture | Verdict |
|---|---|---|---|
| Cloudflare Worker + D1 ([Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)) | $0: 100k requests/day, D1 5M row reads and 100k row writes/day, 5 GB. D1 free limits are hard-enforced since 2026-09-01 ([changelog](https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/)). Paid $5/mo ([pricing](https://developers.cloudflare.com/workers/platform/pricing/)) | Brandon controls schema, retention, and every byte; Cloudflare is the only storage processor | **Chosen** (decision 1) |
| Resend for email ([pricing](https://resend.com/pricing)) | Free: 3,000/mo, 100/day, 3 domains; Pro $20/mo | US company; already the choice in `public-feedback.md` | **Chosen.** 100/day caps confirmations at 100 signatures a day; a spike queues to the next day or triggers the paid plan |
| Cloudflare Email Service ([docs](https://developers.cloudflare.com/email-service/), [pricing](https://developers.cloudflare.com/email-service/platform/pricing/)) | 3,000/mo included on Workers Paid ($5/mo), then $0.35 per 1,000 | Keeps everything in one account | Sending is marked beta on the docs index page (as of 2026-10-04). Switch later if the $5 plan is taken anyway |
| Pytition ([GitHub](https://github.com/pytition/Pytition), [releases](https://github.com/pytition/Pytition/releases)) | Free software (BSD-3); needs a Django host with MySQL and SMTP | Purpose-built, privacy-first: email confirmation, no CDN, no tracking, CSV export, public signature display | Needs a server; the Infomaniak VM is only a local draft plan. Last release v2.9 on 2025-03-01. Revisit if the VM lands and more petitions follow |
| ALTCHA ([site](https://altcha.org/)) for bot checks | Free, open source, self-hosted proof-of-work; no cookies, no fingerprinting | Nothing leaves the site | First CAPTCHA to add if the no-CAPTCHA launch attracts spam |
| Cloudflare Turnstile ([plans](https://developers.cloudflare.com/turnstile/plans/), [privacy addendum](https://www.cloudflare.com/turnstile-privacy-policy/)) | Free, 20 widgets | Processes IP, TLS fingerprint, user agent; used only for bot detection per the addendum; loads a Cloudflare script on the page | Second choice; already planned for the feedback forms |
| GitHub issue or Discussion as the signature list | $0 | Every signature is a public comment under a GitHub account | **Rejected**: needs a GitHub account, no consent choice, removal means editing public history that mirrors and caches keep |
| Staticman-style commit-to-repo ([docs](https://best.staticman.net/docs)) | $0 plus a Staticman host | Names and emails land in git history, which cannot be truly deleted | **Rejected** on deletion alone |
| Netlify or Cloudflare Pages Forms | Needs moving hosting off GitHub Pages | n/a | Out of scope; the site stays on Pages |

### Shortlist comparison

| | Worker + D1 (chosen) | Tally link-out (not chosen) | Action Network | Pytition on a VM |
|---|---|---|---|---|
| Time to a working URL | 1 to 2 days of build | 1 hour | 2 hours | Days, plus a server to run |
| Email verification | Yes | Only on the $74/mo plan | Yes (unverified detail) | Yes |
| Public count on the post | Live | Hand-updated | Link-out only | Link-out only |
| Public list with consent | Yes | No (manual) | Yes | Yes |
| Trackers on the signer's page | None | None on link-out (vendor claim) | Cookies and beacons | None |
| Who holds the data | Brandon (Cloudflare) | Tally (EU) | Action Network (US) | Brandon (Infomaniak) |
| Delete a signer | One command or self-service | Dashboard click | Dashboard | Admin UI |
| Monthly cost | $0 | $0 | $0 | VM cost |
| Reuse for the next pledge | Add a row | New form | New petition | New petition |

## Out of scope

- An admin web UI; export and edits run through `wrangler` from Brandon's machine.
- Free-text comments from signers (P1).
- Sharing the list with anyone other than Brandon (decision 4).
- The feedback and participation forms; they reuse this Worker later under their own plans.

## Sources

- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/ (checked 2026-10-04)
- Cloudflare Workers pricing: https://developers.cloudflare.com/workers/platform/pricing/ (checked 2026-10-04)
- Cloudflare D1 pricing: https://developers.cloudflare.com/d1/platform/pricing/ (checked 2026-10-04)
- D1 free-tier enforcement: https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/
- Cloudflare Email Service: https://developers.cloudflare.com/email-service/ and https://developers.cloudflare.com/email-service/platform/pricing/ (checked 2026-10-04)
- Turnstile plans and privacy: https://developers.cloudflare.com/turnstile/plans/ and https://www.cloudflare.com/turnstile-privacy-policy/
- Resend pricing: https://resend.com/pricing (checked 2026-10-04)
- Tally pricing, privacy, settings: https://tally.so/pricing, https://tally.so/privacy, https://tally.so/help/how-to-create-a-gdpr-compliant-form, https://tally.so/help/form-settings
- Formspark pricing: https://formspark.io/pricing/ (checked 2026-10-04)
- Formspree plans and privacy: https://formspree.io/plans, https://formspree.io/legal/privacy-policy/
- Action Network plans and privacy: https://www.actionnetwork.org/partnerships, https://actionnetwork.org/privacy
- Change.org privacy: https://change.org/policies/privacy; help on signer data: https://help.change.org/en_US/privacy-data-protection
- Pytition: https://github.com/pytition/Pytition, https://github.com/pytition/Pytition/releases
- ALTCHA: https://altcha.org/
- Staticman: https://best.staticman.net/docs
- UK Parliament petitions email confirmation: https://fullfact.org/europe/possible-repeatedly-sign-parliamentary-petition/
- EDPB territorial scope summary: https://hunton.com/privacy-and-information-security-law/edpb-publishes-final-version-of-guidelines-on-the-gdprs-territorial-scope
- CCPA thresholds: https://oag.ca.gov/privacy/ccpa
- Washington privacy law status (secondary): https://privacylawmap.com/blog/washington-state-privacy-law-guide, https://www.bakerlaw.com/insights/washington-states-2026-tech-legislative-agenda-what-in-house-counsel-should-watch/

## Cross-references

- `docs/decisions.md`, 2026-10-04: "Pledge signatures are collected on the site."
- `docs/plans/refocus-foundation.md`: G1 (finish the pledge post) waits on this plan; G2 (homepage menu entry links to the post); "Needs from Brandon, beta.4" item 1.
- `docs/plans/public-feedback.md`: the Worker + D1 stack (Decisions table: Worker location, API subdomain, Skip Formspree prototype) and Resend (Resolved Decisions list, item 2, Email provider) this plan builds first; its Turnstile decision (Decisions table) is deliberately not followed here (P4). Overlap is intentional: one Worker and one D1 database, separate tables and routes.
- `docs/plans/public-participation-forms.md`: spam layers and later forms on the same backend.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-04 | agent (claude-fable-5-1, research subagent) | basic | Self-review by the drafting agent. Draft written locally (gitignored drafts folder). Checked every price and feature line against the fetched page; marked vendor claims and secondary sources; cut the Google Forms and Netlify rows to one line each. |
| 2026-10-04 | agent (claude-opus-5-5, workflow subagent) | implementation, iterated | Promoted from the draft after Brandon's 2026-10-04 answers: Tally interim recorded as not chosen and its migration path dropped; open questions turned into Decisions; added Scope tables (W, S, O) and "Needs from Brandon". Verified in the repo: `workers/` absent, `<Content />` at `src/pages/writing/[...slug].astro` line 32, `writing` collection at `src/content.config.ts` line 426 and `public/admin/config.yml` line 26, the pledge note's "at ..." ending. Not yet reviewed by Brandon. |
| 2026-10-04 | agent (claude-opus-5-5, workflow subagent) | review fixes | Named the no-JS sign result and the confirm/remove result pages (Worker-served, linking back via a new `post_url` column) so R2's "signatory N" has a source; cited `public-feedback.md` decisions by name and list; attributed the subdomain to that plan; stated the 5-per-minute rate limit as a placeholder; made the D1 database name a `<db>` placeholder in Needs item 9. |
| 2026-10-05 | agent (claude-opus-5-5, Claude Code with Brandon) | code review fixes | The hourly cap now counts sends in `email_sends` (migration 0003, applied and deployed 2026-10-05), so re-sends count; `show_name` must be "on" to count as consent. Decision 10, the cap testing row and S4 (the `#sign` link exists) updated. |
