# Petitions

How readers sign a petition on a writing post, and where the signatures live. Plan and decisions: `docs/plans/petition-signatures.md`. Operations (open, close, export, remove, deploy): `docs/runbook.md`, "Petitions".

## Pieces

| Piece | Where | Role |
|---|---|---|
| `dr-api` Worker | `workers/api/` (own `package.json`, deployed by hand with `wrangler deploy`) | Routes under `api.dangerousrobot.org/petitions/{slug}` |
| `dr-api` D1 database | Cloudflare, region WNAM; schema in `workers/api/migrations/` | `petitions` and `signatures` tables |
| Sign block | `src/components/PetitionSign.astro`, rendered by `src/pages/writing/[...slug].astro` | Form, count, public names, privacy notice |
| `petition` frontmatter field | `writing` collection in `src/content.config.ts`, mirrored in `public/admin/config.yml` | Links a post to a petition row by slug |
| Resend | External, called over HTTPS from the Worker | Delivers the one confirmation email |

The site stays static. The sign block fetches the Worker at build time (3-second timeout; any error renders no count, so a Worker outage never fails the site build) and again in the browser on load for a live count.

## Routes

| Route | Does |
|---|---|
| `GET /petitions/{slug}` | Public JSON: `status`, `closed_at`, `count`, `names[]` (confirmed signers who opted in). `no-store`, so a returning signer sees the new count |
| `POST /petitions/{slug}/sign` | Form-encoded `name`, `email`, `show_name`, `website` (honeypot), `started` (page-load time). JSON reply when `Accept: application/json`, otherwise a Worker-served page |
| `GET /petitions/{slug}/confirm?t=`, `/remove?t=` | Landing page with one button. Changes nothing, because email link scanners fetch every URL |
| `POST /petitions/{slug}/confirm`, `/remove` | Confirms (page shows "signatory N") or hard-deletes the signature |
| Cron, daily | Deletes unconfirmed signatures older than 7 days; nulls emails on closed petitions |

The browser fetch sends a URL-encoded body with only an `Accept` header, so it is a CORS "simple" request with no preflight. `ALLOWED_ORIGINS` (a `wrangler.toml` var) controls which origins get CORS headers and may POST to `/sign`.

## Privacy rules the code enforces

- `signatures` has no IP, user agent or free-text column; a test asserts the exact column list.
- Rate limiting uses the Workers rate-limiting binding (`SIGN_LIMITER`, 5 per 60 seconds per IP, approximate and per Cloudflare location), so no IP or IP hash reaches D1.
- Tokens are 32 random bytes; only their SHA-256 hash is stored.
- One signature per lowercased email per petition. A repeat from a confirmed address sends nothing and gets the same reply as a new one, so the form does not reveal who has signed.
- The email is plain text only: no tracking pixels and no rewritten links.
- Worker pages send `Referrer-Policy: no-referrer`, so tokens in email links never reach the post's server logs.

## Spam layers

Honeypot field, a 3-second minimum fill time (set by page JS; a missing value is accepted for the no-JS form, so this check is weak), the rate limit, and the email confirmation itself (unconfirmed signatures never count). No CAPTCHA. If spam appears, the plan's order is self-hosted ALTCHA first, Turnstile second.

## Email modes

`EMAIL_MODE` in `wrangler.toml` is `resend` in production. `.dev.vars` (from `.dev.vars.example`) sets `log`, which prints emails in the `wrangler dev` terminal. Tests keep `resend` and intercept `fetch`, so they check the real Resend request.

## Tests

`workers/api/test/petitions.test.ts` runs inside the Workers runtime through `@cloudflare/vitest-pool-workers`, against a fresh local D1 per test. Run with `npm test` in `workers/api/`. These tests are not in CI yet.
