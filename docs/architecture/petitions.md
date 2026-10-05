# Petitions

How readers sign a petition on a writing post, and where the signatures live. Plan and decisions: `docs/plans/petition-signatures.md`. Operations (open, close, export, remove, deploy): `docs/runbook.md`, "Petitions".

## Pieces

| Piece | Where | Role |
|---|---|---|
| `dr-api` Worker | `workers/api/` (own `package.json`, deployed by hand with `wrangler deploy`) | Routes under `api.dangerousrobot.org/petitions/{slug}` |
| `dr-api` D1 database | Cloudflare, region WNAM; schema in `workers/api/migrations/` | `petitions` and `signatures` tables |
| Sign block | `src/components/PetitionSign.astro`, rendered by `src/pages/writing/[...slug].astro` | Form, count, public names, privacy notice |
| `petition` frontmatter field | `writing` collection in `src/content.config.ts`, mirrored in `public/admin/config.yml` | Links a post to a petition row by slug |
| `petition_statement` frontmatter field | Same two files, optional | The sentence signers put their name to; the sign block sets it above the count |
| Homepage tally | `src/pages/index.astro`, menu entry for a post with `petition` set | Count beside the menu label, from the same build-time fetch, refreshed in the browser |
| Resend | External, called over HTTPS from the Worker | Delivers the one confirmation email |

The site stays static. The sign block and the homepage fetch the Worker at build time through `fetchPetitionState` in `src/lib/petition.ts` (3-second timeout; any error renders no count, so a Worker outage never fails the site build); both fetch again in the browser on load for a live count, and keep the snapshot if that fails.

## Routes

| Route | Does |
|---|---|
| `GET /petitions/{slug}` | Public JSON: `status`, `closed_at`, `count`, `names[]` (confirmed signers who opted in). `no-store`, so a returning signer sees the new count |
| `POST /petitions/{slug}/sign` | Form-encoded `name`, `email`, `show_name`, `website` (honeypot), `elapsed` (milliseconds the page was open). JSON reply when `Accept: application/json`, otherwise a Worker-served page |
| `GET /petitions/{slug}/confirm?t=`, `/remove?t=` | Landing page with one button. Changes nothing, because email link scanners fetch every URL |
| `POST /petitions/{slug}/confirm`, `/remove` | Confirms (page shows "signatory N") or hard-deletes the signature |
| Cron, daily | Deletes unconfirmed signatures older than 7 days; nulls emails on closed petitions |

The browser fetch sends a URL-encoded body with only an `Accept` header, so it is a CORS "simple" request with no preflight. `ALLOWED_ORIGINS` (a `wrangler.toml` var) controls which origins get CORS headers and may POST to `/sign`. A missing Origin (non-browser clients) is accepted; `Origin: null` is refused, because sandboxed iframes on any site send it. The site's `strict-origin-when-cross-origin` referrer policy means real browsers send the true origin.

Known limit: the per-IP rate limit counts per Cloudflare machine, so a script opening fresh connections gets past it (seen in production on 2026-10-04). The real ceiling is the site-wide cap of 30 confirmation emails per hour, re-sends included (counted in the timestamp-only `email_sends` table). It also means 30 bogus sign-ups in an hour lock out real signers until the hour passes. The cap still allows a script to use up Resend's free 100 emails a day in a few hours and draw bounces from fake addresses. The plan's response if it happens is ALTCHA.

## Privacy rules the code enforces

- `signatures` has no IP, user agent or free-text column; a test asserts the exact column list.
- Rate limiting uses the Workers rate-limiting binding (`SIGN_LIMITER`, 5 per 60 seconds per IP, approximate and per Cloudflare machine), so no IP or IP hash reaches D1. The hourly email cap counts rows in `email_sends`, which holds only a send time: no address, no signature id.
- Tokens are 32 random bytes; only their SHA-256 hash is stored.
- One signature per lowercased email per petition. A repeat from a confirmed address sends nothing, and an unconfirmed address gets at most one email per 10 minutes. Every case gets the same reply, so the form does not reveal who has signed and cannot flood someone's inbox.
- The email is plain text only, so no tracking pixel. Links stay unrewritten only while open and click tracking are off for the domain in Resend's settings.
- Worker pages send `Referrer-Policy: no-referrer`, so tokens in email links never reach the post's server logs.

## Spam layers

Honeypot field, a 3-second minimum fill time (the page script sends how long the page was open, measured with `performance.now()` so a wrong system clock cannot drop a signer; a missing value is accepted for the no-JS form, so this check is weak), the per-IP rate limit, the site-wide cap of 30 confirmation emails an hour, and the email confirmation itself (unconfirmed signatures never count). No CAPTCHA. If spam appears, the plan's order is self-hosted ALTCHA first, Turnstile second.

## Email modes

`EMAIL_MODE` in `wrangler.toml` is `resend` in production. `.dev.vars` (from `.dev.vars.example`) sets `log`, which prints emails in the `wrangler dev` terminal. Tests keep `resend` and intercept `fetch`, so they check the real Resend request.

## Tests

`workers/api/test/petitions.test.ts` runs inside the Workers runtime through `@cloudflare/vitest-pool-workers`, against a fresh local D1 per test. Run with `npm test` in `workers/api/`. These tests are not in CI yet.
