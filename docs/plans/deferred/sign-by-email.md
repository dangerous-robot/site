# Sign by email for readers without JavaScript

**Deferred**: 2026-10-30, Brandon set it aside for a few releases, before the header test (T3). Shipped to `main`, not deployed: the Worker merge a47d612 (email handler, parser, migration 0005, tests) and its test commit; the site copy merge 41a0411 was reverted in 325bbf0 (partial back-out, decision S5).
**Status**: `deferred` (roadmap item SITE-BG (Sign by email); design approved by Brandon 2026-10-16, code built 2026-10-16, deferred 2026-10-16, revived 2026-10-23 for beta.9, deferred again 2026-10-30)
**Last updated**: 2026-10-30

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reader without JavaScript, or one the bot check turns away, signs a petition by sending one prefilled email from their own address; the Worker records the signature only when Cloudflare's own DMARC result says the message really came from that address.

**Architecture:** The code already exists on two local branches that merge onto `main` without conflicts: the Worker branch (`feat/site-aq-sign-by-email`: an `email()` handler on the petition Worker `dr-api`, a pure header and subject parser, migration 0005, 48 tests) and the site branch stacked on it (`feat/site-aq-sign-by-email-site`: no-JS form copy, a "Sign by email instead" fallback button, a privacy paragraph). A third throwaway branch (`feat/site-aq-email-probe`) is a Worker that only logs which authentication headers Cloudflare adds; it is deployed once to answer the one open question the design rests on and is never merged. This plan merges the two real branches into `main` now (inert in production: the Worker deploys only by hand, the site only on the beta.9 push), then gates the Worker deploy on the header test, and ships the site copy last so the site never promises a path that is not live.

**Tech Stack:** Cloudflare Workers (Email Workers `email()` handler, Email Routing custom address, D1, Resend for the receipt), `@cloudflare/vitest-pool-workers` tests in `workers/api/`, Astro 7 component and page copy, Invoke tasks.

**Spec:** this file, § Design. Origin: Brandon's local note `~/handoff/2026-10-15-site-aq-no-js-design.md` (gitignored, not on any clone); everything a fresh agent needs is copied below.

## Status checklist

Ticked as tasks land (AGENTS.md Plans & Backlog rule 4). Task ids are the headings below. Items marked **Brandon** need the Cloudflare dashboard, wrangler or a live mailbox, which agents cannot use.

- [x] T0: Register the work item; promote this plan
- [x] T1: Merge the Worker branch into `main`
- [x] T2: Merge the site branch into `main`; confirm the QR code survived
- [x] T2b: Extend the probe so the header test can be read against production's parser
- [ ] T3: **Brandon:** header test with the probe Worker (go or no-go)
- [ ] T4: Settle the two findings the header test answers (fail-open rule; Workers Logs and sender addresses)
- [ ] T5: **Brandon:** migration 0005, routing rule `sign@`, Worker deploy, live check
- [ ] T6: Docs, backlog, worktree cleanup, finish
- [ ] T7 (only on a no-go): back the merged code out before the beta.9 push
- [x] Deferred before T3: partial back-out (T7's partial alternative) applied in 325bbf0. To revive: `git revert 325bbf0` restores the site copy, the sign-by-email page on a tokenless POST and its tests, then resume at T3

## Decisions

Made by Brandon unless noted. The IDs are the design note's; each is glossed where it is used below.

| ID | Question | Answer |
|---|---|---|
| Q-N1 | Per-domain daily cap on messages to `sign@` | 20 per registered domain per UTC day. Exempt (large providers): gmail.com, googlemail.com, outlook.com, hotmail.com, live.com, msn.com, icloud.com, me.com, mac.com, yahoo.com, proton.me, protonmail.com, pm.me (2026-10-16) |
| Q-N2 | Does an emailed signature count publicly at once? | Yes, a DMARC-passing message confirms the signature immediately (2026-10-16) |
| Q-N3 | Offer sign-by-email to JavaScript readers too? | Yes, from launch: a "Sign by email instead" button under the form's bot-check error (2026-10-16) |
| Q-N4 | Keep `contact@dangerousrobot.org` as the last resort in the copy? | Yes (2026-10-16) |
| Q-N5 | Address form | One `sign@dangerousrobot.org`, petition slug in the subject; no plus addressing (2026-10-16) |
| K1 | Per-address daily cap | 5 messages per sender address per UTC day, large providers included (2026-10-16) |
| K2 | Domain cap key | The registered domain (`example.co.uk`, not `mail.example.co.uk`), with a hand-written two-label suffix list (2026-10-16) |
| K3 | Counter table | `email_in_counts` (day, hashed key, count), pruned by the daily cron (2026-10-16) |
| K4 | Privacy sentence for the counter | "We also note that you signed by email, and keep a scrambled copy of your address for a day to limit repeat messages." (2026-10-16) |
| K5 | Do Workers Logs record the sender address of an email event? | **Open.** Answered by T3; acted on in T4 |
| F8 | What the Worker does when Cloudflare adds no authentication result header | **Open.** Today the code fails closed (rejects, logs `no-auth-header`). Confirmed or changed in T4 once T3 shows the live header order |
| S1 | Release | Minor, rides the beta line as SITE-BG (Sign by email) on beta.9 (Brandon, 2026-10-23) |
| S2 | Merge order (agent call, override freely) | Merge both branches into `main` before the header test. Merging is inert here: the Worker deploys only through `inv worker-deploy`, and the site only on the beta.9 push, which Brandon is holding. T7 names the back-out if the test fails. The alternative, holding the merge until the test passes, costs nothing today (the merge is clean) but leaves the branches drifting from `main` |
| S3 | Probe Worker replaces the live Worker during the test (agent call) | Accepted. `git diff ccd982b main -- workers/api/src/index.ts` shows the probe's base differs from `main` by two comment lines only, so production behaviour is unchanged while the probe is deployed, except that mail to `sign-test@` is logged and rejected |
| S4 | What runs in production between the header test and the real deploy (agent call, from review finding 2) | The probe Worker stays deployed from T3 until T5. After T1 and T2, `main`'s Worker already answers a tokenless POST with the last-step page, so redeploying `main` before migration 0005 and the `sign@` rule exist would send readers to an unrouted address. The probe without its `sign-test@` rule behaves exactly like the beta.8 Worker (S3) |
| S5 | Back-out when deferred before the header test | Partial (T7's partial alternative): site copy merge reverted and the tokenless form POST back to the 403 page naming contact@, in 325bbf0. The email handler, parser, migration 0005 and their tests stay on `main`; with no routing rule for `sign@` the handler is never called, so the Worker can deploy from `main` (answer yes to migration 0005) and ship SITE-BI (Petition unconfirmed limit back to 7 days) on its own (Brandon, 2026-10-30) |

## Design

### Reference table

| Name used below | What it is |
|---|---|
| Worker branch | `feat/site-aq-sign-by-email`, worktree `site-worktrees/site-aq-sign-by-email`, commits `c5d2433` (feature) and `518fdcf` (review fixes), base `ccd982b` |
| Site branch | `feat/site-aq-sign-by-email-site`, worktree `site-worktrees/site-aq-sign-by-email-site`, commits `e866fe7` (copy, privacy, fallback button) and `6ff3c4b` (privacy sentence K4), stacked on the Worker branch |
| Probe branch | `feat/site-aq-email-probe`, worktree `site-worktrees/site-aq-email-probe`, head `304191e`; a Worker whose `email()` logs header names and authentication results (no local parts, names, subjects or bodies) and rejects every message. Never merged |
| Header test | Deploying the probe Worker and mailing `sign-test@dangerousrobot.org` to see whether Cloudflare's own `Authentication-Results` header (server id `mx.cloudflare.net`) is present and topmost when the Worker runs. The whole design rests on it; no Cloudflare doc says so |
| Last-step page | The Worker page a tokenless, non-JSON sign POST now gets instead of a 403: a `mailto:` link and the same address and subject as plain text |
| Receipt | The one reply the Worker sends after a signature is recorded: "Your signature is counted" plus a removal link |

### Flow (as built on the Worker branch)

1. The reader fills in the normal form and presses Sign. Without JavaScript the browser POSTs with no Turnstile token; with JavaScript, the "Sign by email instead" button (Q-N3) removes any token and submits the form natively.
2. `sign()` in `workers/api/src/index.ts` keeps every existing check (origin, limiter, honeypot, fields, closed petition). A missing token on a non-JSON request returns the last-step page (`lastStepPage` in `workers/api/src/pages.ts`) with the subject from `buildSubject` in `workers/api/src/inbound.ts`; `|` in a name becomes `/`. Nothing is stored or sent. The JSON branch stays a 403.
3. Subject format: `Sign <slug> | Name: <name> | Show my name: yes|no | Updates: yes|no`. Subject only; the Worker never parses a body.
4. Email Routing passes mail for `sign@dangerousrobot.org` to `email()` on `dr-api`, which calls `signByEmail(message, env)` and logs one outcome code (`email-sign: ok | no-auth-header | dmarc-fail | bad-from | capped | closed | unknown-petition | no-name | auto | error`, with a ` reply=sent|capped|failed|none` suffix), never an address, domain or name.
5. `readHeaderBlock` reads the raw header block (`Headers.get()` would merge duplicates and hide order). `cloudflareDmarc` trusts only the topmost result header, which must be Cloudflare's; pass needs `dmarc=pass` with `header.from` equal to the From domain. A result header naming `dmarc` or `header.from` twice is refused (a sender can forge one through fields Cloudflare copies).
6. Auto-replies and bulk mail (`Auto-Submitted`, `Precedence`) are dropped with no reply.
7. Caps, before any reply: per address 5 a day (K1), per registered domain 20 a day (Q-N1, K2) unless exempt, counted in `email_in_counts` (K3) under SHA-256 keys. Over a cap: `setReject`. Receipts also count against the existing `HOURLY_EMAIL_CAP` of 30.
8. Subject parsed (`parseSubject`, RFC 2047 words decoded). An unknown slug or an unreadable subject gets one shared reply saying so; a closed petition gets its own ("Petition closed: <title>"). Name from the subject, else the From display name; neither gets a reply asking for it.
9. Store: insert or update `(petition_slug, email)` with `confirmed_at = now`, `source = 'email'`. An unconfirmed web row becomes confirmed with the emailed name and choices (so no reminder goes out); a confirmed row keeps its data.
10. One receipt through the existing Resend `sendEmail`, header `Auto-Submitted: auto-replied`. The new `token_hash` is written only after the send succeeds, so an existing removal link stays valid when the receipt is capped or fails.
11. Failed check: `setReject("We could not confirm this message came from your address. Write to contact@dangerousrobot.org.")`. A processing error also rejects.

### Schema (migration 0005, on the Worker branch)

`workers/api/migrations/0005_signatures_source.sql`: `signatures.source TEXT NOT NULL DEFAULT 'web' CHECK (source IN ('web','email'))`, and table `email_in_counts (day, key_hash, n)`.

### Site copy (on the site branch)

- `<noscript>` text in `src/components/PetitionSign.astro`: "Without JavaScript, signing takes one more step. Press Sign and we will show you a short email to send from your address. Sending it is what confirms your signature."
- Button `Sign by email instead` (`data-email-sign`), shown only after a 403 or a bot check that did not finish; styled as the roll toggle (accent text, no box).
- `/privacy#petitions`: a paragraph after the Turnstile one ("If you sign by email, Cloudflare receives your message and checks that it really came from your address. We read the sender address, the name on it and the subject line, and keep with your signature the same four things listed above. We do not keep the message.") plus the K4 sentence.

### Tests already on the Worker branch

`workers/api/test/inbound.test.ts` (23, pure parser), `workers/api/test/email-in.test.ts` (24, the handler against a fresh D1), `workers/api/test/premigration.test.ts` (1: web inserts work before migration 0005 runs), and changed cases in `workers/api/test/petitions.test.ts` (60 lines). The design's numbered tests appear in the titles: T1 hostile name encoded in the page and the `mailto:` link, and a pipe becomes a slash (`petitions.test.ts`); T2 stores and sends one receipt; T3 forged lower header; T4 pass for another domain; T5 fails closed with no header; T6 auto and bulk; T7 confirms a web row; T8 domain cap, exempt provider still signs; T9 hourly cap keeps the old link; T10 encoded words, display name, pipe, no name; T11 closed or unknown; T12 logs no address; T13 domain cap on unknown petitions. Worker branch total 114 passing (2026-10-16), type check clean. Site branch: `npm run check` passed (2026-10-16).

### Header test reading rules (for T3)

From the probe branch's record. Pass: the first `authResults` entry has `serverId: mx.cloudflare.net`, `dmarc: pass`, and `headerFromDomain` equal to `fromDomain`. No-go as written: `dmarc: null`, or the entry is absent or not first, or `fromDomainHasNoDmarcEntry: true` for a sender whose domain has a DMARC record. Inconclusive: no log line, `read-failed`, or `truncated`. A `dmarcCount` or `headerFromCount` above 1 in genuine mail is a finding for T4 (the refuse-duplicates rule may need changing), not a no-go; read it together with the `topResultHeader` value that T2b adds, because the probe's counter also counts `policy.dmarc=` while production's does not, so the count alone can be a false alarm. Also note whether `toHasPlusDetail` is kept (future use only) and, for K5, whether the dashboard's invocation view for an email event shows the sender address.

## Global Constraints

- Never push to `origin`; the beta.9 push is Brandon's, after T5.
- Agents cannot run `wrangler` (any form) or `inv worker-deploy`; those steps are Brandon's at a terminal.
- Commits name explicit paths (peers share the checkout); conventional commit messages. A merge commit runs no pre-commit hook here (only `.git/hooks/pre-commit` exists), so each merge task runs its own checks.
- Logs hold outcome codes only, never a sender address, display name, subject or body.
- The Worker is deployed only after the routing rule for `sign@` exists, or in the same sitting: a deployed Worker shows the last-step page, and mail to an unrouted `sign@` would bounce.
- The site copy (T2's merge) reaches readers only in the beta.9 push, after T5.

## Review Focus

Inputs the design implies that no test on the branch pins. Each gets a test in the task named.

1. The hostile-name test on the branch ("encodes a hostile name in both the page and the mailto: link (T1)", `petitions.test.ts`) checks the page but not that nothing was stored or sent for that request. T1 adds the two assertions.
2. A merged `PetitionSign.astro` must still render the QR tile and flyer link for an open petition (the site branch predates SITE-BC (Pledge QR code and print flyer)). T2 runs the QR decode e2e spec.
3. Genuine mail whose topmost Cloudflare header carries a nested result such as `arc=pass (... dmarc=pass ...)`: production's `cloudflareDmarc` reads only that header and returns `ambiguous`, so the message is rejected. The probe's Gmail-style fixture has exactly that shape. Only the live header test can say whether Cloudflare writes it; T2b makes the probe log the header's value, T3 reads it, T4 Step 2 changes the parser if needed. This is the finding most likely to turn a pass into silent rejections.
4. A sender whose domain publishes no DMARC record (Cloudflare records `dmarc=none` or no entry): the design fails closed. T3 sends one such mail if Brandon has an address on such a domain; T4 records the outcome in the runbook so contact@ replies are expected.
5. The probe Worker rejecting mail to `sign-test@` must not affect the live cron or `fetch` routes: T3 step 2 checks the petition page still loads the live count during the test window.

---

### T0: Register the work item; promote this plan

**Files:**
- Modify: `docs/v1.0.0-roadmap.md` (SITE-BG (Sign by email) section already added 2026-10-23; link this plan once promoted)
- Move: `docs/plans/drafts/sign-by-email.md` → `docs/plans/sign-by-email.md`

- [x] **Step 1: Confirm the roadmap entry** names SITE-BG (Sign by email) on the beta.9 line and under `## Scheduled`, and that `docs/UNSCHEDULED.md` no longer has the row "Sign by email for readers without JavaScript" (removed 2026-10-23).
- [x] **Step 2: Promote the plan**: `mv docs/plans/drafts/sign-by-email.md docs/plans/sign-by-email.md` then `git add -N docs/plans/sign-by-email.md` (the drafts folder is gitignored, so `git mv` refuses it), set Status to `ready`, and point the roadmap's `**Plan**:` line at it. The Review history already has two rows.
- [x] **Step 3: Register**

```bash
python3 scripts/release-gate/work_item.py start --title "Sign by email" --kind minor --release v1.0.0 --plan docs/plans/sign-by-email.md
```

- [x] **Step 4: Commit** `docs/plans/sign-by-email.md docs/v1.0.0-roadmap.md docs/UNSCHEDULED.md` (the backlog row removal is still uncommitted) as `docs(plans): promote the sign-by-email plan (SITE-BG)`.

### T1: Merge the Worker branch into `main`

**Files:**
- Merge: `feat/site-aq-sign-by-email` (adds `workers/api/src/inbound.ts`, `workers/api/migrations/0005_signatures_source.sql`, `workers/api/test/email-in.test.ts`, `workers/api/test/inbound.test.ts`, `workers/api/test/premigration.test.ts`; modifies `workers/api/src/index.ts`, `workers/api/src/email.ts`, `workers/api/src/pages.ts`, `workers/api/test/petitions.test.ts`)
- Test: `workers/api/test/petitions.test.ts` (new case, Review Focus 1), `workers/api/test/email-in.test.ts` (Review Focus 3, if missing)

**Interfaces:**
- Produces: `signByEmail(message: ForwardableEmailMessage, env: Env, now?: Date): Promise<string>` (outcome code), `lastStepPage(subject: string, postUrl: string)`, `buildSubject({ slug, name, showName, wantsUpdates }): string`, `parseSubject(subject: string): SignSubject | null`, `cloudflareDmarc(headers: RawHeader[]): DmarcResult | null`, constants `SIGN_ADDRESS` (`inbound.ts`), `DOMAIN_DAILY_CAP = 20` and `ADDRESS_DAILY_CAP = 5` (`index.ts`); `HOURLY_EMAIL_CAP = 30` already exists on `main`.

- [x] **Step 1: Check the checkout** with `ListAgents` and `git status --short`; the only expected untracked paths are Brandon's (`docs/pixabay-terms-202418Nov.md`, `public/images/writing/`). A peer or a dirty tracked file: stop and ask.
- [x] **Step 2: Merge** on `main`: `git merge --no-ff feat/site-aq-sign-by-email -m "feat(api): sign by email for readers without JavaScript (SITE-BG)"`. Expected: no conflicts (dry run 2026-10-23 with `git merge-tree --write-tree main feat/site-aq-sign-by-email` was clean). No hook runs on a merge commit; Step 3 is the check.
- [x] **Step 3: Run the Worker tests** from `workers/api/`: `npm test`. Expected: 114 passed, as recorded on the branch 2026-10-16 (`main` alone has 61 in `petitions.test.ts`), 0 failed. Then `npm run check:types` (`tsc --noEmit`, in `workers/api/package.json`): clean.
- [x] **Step 4: Extend the hostile-name test** ("encodes a hostile name in both the page and the mailto: link (T1)", `workers/api/test/petitions.test.ts`, near line 612) with two assertions from the neighbouring tokenless case (near line 595): `SELECT count(*) FROM signatures` is 0 and no `fetch` to Resend happened.
- [x] **Step 5: Run it**: `npm test -- -t "hostile name"`. Expected: PASS (the branch stores and sends nothing on that path; the assertions pin it).
- [x] **Step 6: Commit** the test file only: `git commit -m "test(api): the hostile-name last-step case stores and sends nothing (SITE-BG)" -- workers/api/test/petitions.test.ts`.
- [x] **Step 7: Tick the roadmap line** "Worker branch merged" in SITE-BG (Sign by email) with the merge commit id; commit `docs/v1.0.0-roadmap.md`.

### T2: Merge the site branch into `main`; confirm the QR code survived

**Files:**
- Merge: `feat/site-aq-sign-by-email-site` (modifies `src/components/PetitionSign.astro`, `src/pages/privacy.astro`)
- Test: `tests/e2e/petition-qr.spec.ts` (existing), `npm run check`

- [x] **Step 1: Merge** on `main`: `git merge --no-ff feat/site-aq-sign-by-email-site -m "feat(site): sign-by-email copy, privacy note and bot-check fallback (SITE-BG)"`. Expected: no conflicts (dry run 2026-10-23 clean).
- [x] **Step 2: Confirm the three-way merge kept the QR work**: `grep -c 'PetitionQr\|flyerHref\|data-email-sign' src/components/PetitionSign.astro`. Expected: 6 (the dry-run merge result had 6; the branch alone has none of the first two).
- [x] **Step 3: Run the site checks**: `npm run check` (exit 0) and `npm run test:e2e -- petition-qr` (the QR decode spec; expected: pass, or self-skip only if the live petition is closed).
- [x] **Step 4: Look at the form** on `inv dev` (port 4321, do not start a second server if one runs): with scripts off, the `<noscript>` text reads as in § Design; with scripts on, the "Sign by email instead" button is hidden until a bot-check failure. Take one screenshot of each state for the handoff note.
- [x] **Step 5: Tick the roadmap line** "Site branch merged; QR tile and flyer link still render" with the merge commit id; commit `docs/v1.0.0-roadmap.md`.

### T2b: Extend the probe so the header test can be read against production's parser

**Files:**
- Modify: `workers/api/src/email-probe.ts` (probe branch, in its worktree `site-worktrees/site-aq-email-probe`; the branch is never merged, so this is the one task that edits a worktree instead of `main`)
- Test: `workers/api/test/email-probe.test.ts`

Why: the probe logs parsed fields and counts, never a header's text, and its `dmarc` counter differs from production's (it counts `policy.dmarc=`, production does not). Review Focus 3 needs the topmost Cloudflare result header's actual shape.

- [ ] **Step 1: Write the failing test** in `email-probe.test.ts`: with the existing Gmail-style fixture, the logged record has `topResultHeader: string` equal to the unfolded value of the first `Authentication-Results` or `ARC-Authentication-Results` header whose server id is `mx.cloudflare.net`, with every `<something>@` run replaced by `[redacted]@` (so `smtp.mailfrom=bob@example.com` logs as `smtp.mailfrom=[redacted]@example.com`), and `null` when there is none. Assert the field contains `dmarc=pass` and no `@` preceded by anything but `[redacted]`.
- [ ] **Step 2: Run it**: from the probe worktree's `workers/api/`, `npm test -- -t "topResultHeader"`. Expected: FAIL, field undefined.
- [ ] **Step 3: Implement** `topResultHeader` on `ProbeRecord` in `email-probe.ts`, filled from the already-parsed `AuthResult` list and the raw header text (cap the logged value at 2 KiB).
- [ ] **Step 4: Run the probe tests**: `npm test`. Expected: 78 before plus the new case, all passing; `npm run check:types` clean.
- [ ] **Step 5: Commit on the probe branch** from its worktree: `git commit -m "feat(api): email probe logs the top Cloudflare result header, redacted (SITE-BG)" -- workers/api/src/email-probe.ts workers/api/test/email-probe.test.ts`.

### T3: Brandon: header test with the probe Worker (go or no-go)

**Files:** none in the repo. Record the result in `docs/plans/sign-by-email.md` § Decisions (K5, F8) and in the roadmap line.

Brandon, at a terminal, in this order:

- [ ] **Step 1: Deploy the probe**: `cd /Users/brandon/dev/ai/dangerous-robot/site-worktrees/site-aq-email-probe`, then `/Users/brandon/.local/bin/inv worker-deploy`. Wrangler lists pending D1 migrations first: expect none (the probe carries 0001 to 0004, the same as the live database). If it lists one, the worktree is on the wrong branch: Ctrl-C and check `git -C <worktree> log --oneline -1` shows the T2b commit.
- [ ] **Step 2: Check production still works**: open an open petition page; the live count and names load. Mail to `contact@` is untouched (no rule changes yet).
- [ ] **Step 3: Routing rule**: Cloudflare dashboard, Email Routing, Routing rules, create `sign-test@dangerousrobot.org`, action Send to Worker, `dr-api`.
- [ ] **Step 4: Send test mail** to `sign-test@` from a Gmail account, an Outlook account, once to `sign-test+x@`, and, if you have one, from an address on a domain with no DMARC record. Subject anything.
- [ ] **Step 5: Read the logs**: dr-api Workers Logs filtered on `email-probe`. Apply the reading rules in § Design. While one invocation is open, note whether the dashboard shows the sender address anywhere (K5).
- [ ] **Step 6: Clean up**: delete the `sign-test@` rule. Leave the probe Worker deployed (decision S4): without the rule it behaves like the beta.8 Worker, and `main`'s Worker must not go live before migration 0005 and the `sign@` rule exist (T5).
- [ ] **Step 7: Record** PASS, NO-GO or INCONCLUSIVE with the observed `authResults` shape, the `dmarcCount` values, and the K5 answer, and the redacted `topResultHeader` text, in § Decisions here and on the roadmap line "Header test". On NO-GO go to T7; on INCONCLUSIVE fix the probe and repeat; on PASS continue.

### T4: Settle the two findings the header test answers

**Files:**
- Modify: `workers/api/src/inbound.ts` (`cloudflareDmarc`, only if T3 showed a duplicate-field pattern in genuine mail), `workers/api/src/index.ts` (only if F8 changes), `src/pages/privacy.astro` (only if K5 is yes), `workers/api/wrangler.toml` (`[observability]`, only if K5 is yes and Brandon prefers less logging)
- Test: `workers/api/test/inbound.test.ts`, `workers/api/test/email-in.test.ts`

- [ ] **Step 1: F8 (no result header).** If T3 showed Cloudflare always adds a result header, keep fail-closed and write the sentence "Cloudflare adds `Authentication-Results` on every delivery (observed 2026-MM-DD); a message without one is rejected" into § Decisions F8. If it sometimes does not, Brandon decides between fail-closed (readers on such mail get the reject text and write to contact@) and an alternative; this plan does not pre-decide. No code change in the keep case.
- [ ] **Step 2: Nested or repeated fields.** Take the recorded `topResultHeader` text (domains replaced by `example.com`). Write a test in `inbound.test.ts` that feeds it to `cloudflareDmarc` and asserts a pass. Run it. If it passes, keep it as the pin and stop. If it returns `ambiguous` (the Gmail-style `arc=pass (... dmarc=pass ...)` shape), change `cloudflareDmarc` so a `dmarc=` inside a parenthesised comment does not count as a second field, while a bare second `dmarc=` outside comments is still refused; run to PASS and keep the existing forged-header tests passing.
- [ ] **Step 3: K5 (Workers Logs show the sender address).** If yes, Brandon chooses one: (a) add to the privacy paragraph "Cloudflare's own logs for our Worker record the sending address for a short time", or (b) set `[observability] invocation_logs = false` in `wrangler.toml` (this silences every invocation log for the Worker, including the petition form's). Apply the choice; for (a) rerun `npm run check`; for (b) rerun `npm test`.
- [ ] **Step 4: Commit** touched files by path: `fix(api): settle header-test findings for sign by email (SITE-BG)`. Tick the roadmap lines "F8 decided" and "K5 decided".

### T5: Brandon: migration 0005, routing rule `sign@`, Worker deploy, live check

**Files:** none in the repo beyond the roadmap tick.

Brandon, at a terminal, in one sitting so the rule and the Worker go live together:

- [ ] **Step 1**: dashboard, Email Routing, Routing rules, create `sign@dangerousrobot.org`, Send to Worker, `dr-api`. Confirm `sign-test@` is gone. (The probe is still deployed, so mail to `sign@` is rejected until Step 2; that is the safe side.)
- [ ] **Step 2**: from the repo root, `/Users/brandon/.local/bin/inv worker-deploy`; when wrangler lists `0005_signatures_source.sql` as pending, answer yes. Expected: migration applied, Worker deployed, no errors.
- [ ] **Step 3: Live check**: send one real sign-by-email message from your own address for the open petition using the subject format in § Design. Expected within a minute: a receipt arrives, the public tally rises by one, and the receipt's removal link removes the signature (tally back down).
- [ ] **Step 4: Tokenless POST**: with scripts off in a browser, submit the live form. Expected: the last-step page with your name in the `mailto:` link (the site copy itself is not live yet; the `<noscript>` text still reads as beta.8 until the push).
- [ ] **Step 5: Record** in the roadmap line "Worker live" with the date; note the receipt arrival time in the handoff note.

### T6: Docs, backlog, worktree cleanup, finish

**Files:**
- Modify: `docs/architecture/petitions.md` (§ Pieces, § Routes, § Privacy rules the code enforces, § Spam layers, § Tests), `docs/runbook.md` (§ Petitions: open, close, export, remove), `docs/v1.0.0-roadmap.md`, `docs/UNSCHEDULED.md`, `docs/plans/sign-by-email.md`

- [ ] **Step 1: Architecture doc.** § Pieces: add `inbound.ts` (header, From, subject parsing; pure) and the `email()` handler. § Routes: a row for mail to `sign@` (not an HTTP route; say so). § Privacy rules: `source` column, `email_in_counts` holds hashes only and is pruned daily, logs hold outcome codes. § Spam layers: replace "No CAPTCHA. If spam appears, the plan's order is self-hosted ALTCHA first, Turnstile second." with the current state (Turnstile since SITE-AQ (Petition sign bot check); sign by email for readers without it, with the address and domain caps). § Tests: name the three new test files and the count.
- [ ] **Step 2: Runbook.** Under Petitions add **Sign by email**: the routing rule and where it lives; how to list email signatures by domain (`SELECT ... WHERE source = 'email'` through `inv`, or a note that it needs a one-off `wrangler d1 execute`); that a signer whose provider fails DMARC gets a reject and writes to contact@ (confirm by hand with `inv petition-confirm`); that the receipt carries the removal link.
- [ ] **Step 3: Roadmap and backlog.** Set SITE-BG (Sign by email) to `done` with the commit ids; confirm the backlog row is gone; add any T3 or T4 leftovers as new rows with a triage marker (theme `none` or `Security`).
- [ ] **Step 4: Worktrees and branches** (after T2 merged both, and after T3 is done with the probe): `git worktree remove ../site-worktrees/site-aq-sign-by-email`, `git worktree remove ../site-worktrees/site-aq-sign-by-email-site`, `git worktree remove ../site-worktrees/site-aq-email-probe`, then `git branch -d feat/site-aq-sign-by-email feat/site-aq-sign-by-email-site` (merged, so `-d` works) and `git branch -D feat/site-aq-email-probe` (never merged; `-D` on purpose, note it in the commit message of Step 5). Ask Brandon before the `-D`.
- [ ] **Step 5: Commit** docs by path: `docs(petitions): sign by email in architecture and runbook (SITE-BG)`. Move the plan: `git mv docs/plans/sign-by-email.md docs/plans/completed/sign-by-email.md` in the same commit after asking Brandon whether it is complete (AGENTS.md rule 5).
- [ ] **Step 6: Finish**: `python3 scripts/release-gate/work_item.py finish`. Update `handoff/2026-10-21-beta9-triage.md`.

### T7 (only on a no-go): back the merged code out before the beta.9 push

**Files:**
- Revert, newest first: any T4 commit, the T1 Step 6 test commit (it modifies a file the Worker merge created, so reverting the merge first would hit a modify/delete conflict), then `git revert -m 1 <site-merge>`, then `git revert -m 1 <worker-merge>`.
- Partial alternative, if Brandon prefers to keep the parser for later: revert only the site merge, and change the tokenless non-JSON branch of `sign()` back to the 403 with the contact@ text, restoring `main`'s test "refuses a form POST without a bot check token with a page that explains why" in `petitions.test.ts`. Migration 0005 then stays in `main`; it is additive with a default, so the next `inv worker-deploy` prompt is answered yes.

- [ ] **Step 1**: Brandon decides full revert or partial (one line in § Decisions as S5).
- [ ] **Step 2**: apply it; `npm test` in `workers/api/` and `npm run check` at the root pass.
- [ ] **Step 2b**: **Brandon** redeploys the Worker from `main` (`inv worker-deploy`), so the probe does not stay in production.
- [ ] **Step 3**: roadmap SITE-BG (Sign by email) set to `retired` with the reason and the probe's observed header shape; restore the backlog row as "keep (operator)" with the finding, so the idea is not re-proposed without new information. Delete the three worktrees and branches as in T6 Step 4.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-23 | agent (claude-fable-5-1) | basic, implementation (self-review against the three branches: exported names, test titles, migration text, merge dry runs) | plan written |
| 2026-10-23 | agent (claude-opus-5-5, read-only) | implementation, iterated | 15 findings. Fixed: `git mv` on a gitignored draft; the probe now stays deployed until the real deploy (decision S4) and the `sign@` rule is created before it; `docs/UNSCHEDULED.md` added to T0's commit; Review Focus 1 was already covered on the branch (replaced by its two missing assertions); Review Focus 3 rewritten around the nested `arc=pass (dmarc=pass)` shape, with new task T2b so the probe logs the header; T4 Step 2 works from that text; T7 revert order, redeploy step and the partial option's migration and test; `check:types`; log codes, closed-petition reply, T1 and T8 in the test list, where each constant lives; dropped the claim that a merge commit runs the pre-commit hook |
