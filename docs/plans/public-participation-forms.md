# Plan: Public Participation Forms

Three participation forms that extend the Phase 6 Cloudflare backend: a per-claim challenge form, a "request a claim" form, and a "propose a standard" form. All share the same Worker, D1 database, and spam-prevention stack already designed in Phase 6.

## Goal

Give public visitors three structured ways to participate in research without a GitHub account:

1. Challenge a specific claim (dispute a verdict or counter-source)
2. Request that a company or claim be researched
3. Propose a new standardized claim template

Phase 6 builds the submission infrastructure. This plan extends it with these three form types.

## Scope decisions

| # | Decision | Choice | Notes |
|---|----------|--------|-------|
| 1 | D1 schema | Extend the Phase 6 `submissions` table | Add new `type` values and a `payload` JSON column for type-specific fields. Three separate tables would require three admin list paths and duplicate status logic. Phase 6 hasn't shipped yet, so this is an amendment to the schema, not a migration. |
| 2 | Admin CLI naming | Rename Phase 6's `feedback-admin` → generalized `dr-admin submissions` | Phase 6's `scripts/feedback-admin.ts` and `feedback:list`/`feedback:review` npm scripts should be renamed as part of this work, since these three types land before or with Phase 6. The prompt-specified `dr-admin submissions list [type]` becomes the canonical interface. |
| 3 | Progressive enhancement vs. Turnstile | True progressive enhancement: `<form method="post">` works without JS; Turnstile and fetch are layered on with JS | Each form is a real HTML form posting `application/x-www-form-urlencoded` to the Worker. Without JS: the four non-Turnstile spam layers (honeypot, time-check, rate-limit, content heuristic) still fire. With JS: Turnstile token is injected and the submit handler upgrades to `fetch` with inline success/error state. This satisfies both the progressive-enhancement requirement and keeps Turnstile as an enhancement for the ~99% with JS rather than a hard gate. |
| 4 | Category list source of truth | `research/templates.yaml` category enum | A `topics` content collection is not populated. The existing `templates.yaml` defines 5 categories: `environmental-impact`, `data-privacy`, `ai-literacy`, `ai-safety`, `industry-analysis`. Dropdowns for both claim requests and standard proposals use this list. The task-stated "8 categories" figure does not match the current taxonomy; if the taxonomy grows, dropdown options follow. |
| 5 | Claim foreign key | Store `claim_slug` as a string in D1, not a numeric FK | Content is static. Validate slug format (`^[a-z0-9-/]+$`) server-side. Do not attempt to verify slug existence against the static site. |
| 6 | Rate-limit buckets | Per-(IP, type) | Prevents cross-blocking between form types. A burst of claim requests shouldn't consume a user's challenge budget. |
| 7 | Backlog placement | Extend Phase 6 as items 6.4–6.6 | No BACKLOG.md edit needed; tracked in this plan. |

## Non-goals

- Admin dashboard (Phase 6.3 covers all submission types when built)
- Email follow-up per submission (Phase 6.2 covers this for all types)
- GitHub issue promotion for these types (follows same Phase 6.2 path)
- Verdict display or research scheduling (operator decides what to do with claim requests and standard proposals)
- Any operator-facing UI beyond the CLI
- Operator-visible triage queue UI (CLI is sufficient in v1)

---

## Backend extension

### D1 schema amendment

The Phase 6 `submissions` table gains:

- Two new `type` values in the CHECK constraint: `'challenge'`, `'claim-request'`, `'standard-proposal'`
- One new column: `payload TEXT` — JSON object containing type-specific fields

Full updated CHECK constraint:

```sql
type TEXT NOT NULL CHECK(type IN (
  'flag', 'feedback', 'claim',
  'challenge', 'claim-request', 'standard-proposal'
))
```

New column (added to the Phase 6 schema before initial deployment):

```sql
ALTER TABLE submissions ADD COLUMN payload TEXT;
-- or add to CREATE TABLE if Phase 6 hasn't shipped yet
```

`payload` holds the type-specific JSON blob. Type-common fields (`status`, `created_at`, `ip_hash`, etc.) remain top-level columns. An additional `claim_slug` column is added as a convenience index field for challenge submissions:

```sql
ALTER TABLE submissions ADD COLUMN claim_slug TEXT;
CREATE INDEX idx_submissions_claim_slug ON submissions(claim_slug);
```

**Payload shapes by type:**

```json
// challenge
{
  "counter_url": "https://...",
  "counter_quote": "...",
  "reason": "source is inaccurate|source is outdated|source is misrepresented|verdict is wrong|other",
  "notes": "..."
}

// claim-request
{
  "company_or_product": "...",
  "topic_category": "...",
  "why": "..."
}

// standard-proposal
{
  "question_text": "...",
  "entity_type": "company|product",
  "category": "...",
  "why_it_matters": "...",
  "example_companies": "..."
}
```

### Worker endpoints

Three new routes added to `workers/feedback/`:

**`POST /submissions/challenge`**

Accepts a challenge against a specific claim.

Required fields: `claim_slug`, `reason`
Optional fields: `counter_url`, `counter_quote`, `notes`

Stores `claim_slug` as a top-level column, full payload as JSON in `payload`.

**`POST /submissions/claim-request`**

Accepts a request to research a company or claim.

Required fields: `company_or_product`, `topic_category`
Optional fields: `why`

**`POST /submissions/standard-proposal`**

Accepts a proposal for a new standardized claim template.

Required fields: `question_text`, `entity_type`, `category`
Optional fields: `why_it_matters`, `example_companies`

All three endpoints share the same spam-prevention stack from Phase 6, applied per-(IP, type) bucket:

1. Honeypot field (`website` must be empty)
2. Time-based check (reject if `_loaded_at` indicates < 3s from load to submit)
3. Rate limiting (max 5 per IP per type per hour via KV, key: `rl:{type}:{ip_hash}`)
4. Content heuristics (reject if required text fields are < 5 chars or contain > 3 URLs)
5. Turnstile server-side verification (same `TURNSTILE_SECRET`, same siteverify call)

Input length limits enforced server-side:

| Field | Max length |
|-------|-----------|
| `claim_slug` | 200 chars, format `^[a-z0-9-/]+$` |
| `counter_url` | 2,048 chars, valid URL |
| `counter_quote` | 1,000 chars |
| `reason` | enum validation |
| `notes` | 500 chars |
| `company_or_product` | 300 chars |
| `topic_category` | enum: `environmental-impact`, `data-privacy`, `ai-literacy`, `ai-safety`, `industry-analysis` |
| `why` | 300 chars |
| `question_text` | 200 chars |
| `entity_type` | enum: `company`, `product` |
| `category` | enum: `environmental-impact`, `data-privacy`, `ai-literacy`, `ai-safety`, `industry-analysis` |
| `why_it_matters` | 300 chars |
| `example_companies` | 300 chars |

All three endpoints return `200 OK` unconditionally (same pattern as Phase 6) to avoid leaking validation state to bots. Rejection reasons are logged to Workers Logs with a request ID.

### Admin CLI

Phase 6's `scripts/feedback-admin.ts` is renamed and extended to `scripts/dr-admin.ts`, with corresponding npm script renames:

| Old npm script | New npm script |
|---------------|----------------|
| `feedback:list` | `submissions:list` |
| `feedback:review` | `submissions:review` |
| `feedback:stats` | `submissions:stats` |

The CLI accepts an optional `[type]` filter:

```
$ npm run submissions:list
$ npm run submissions:list -- --type challenge
$ npm run submissions:list -- --type claim-request
$ npm run submissions:list -- --type standard-proposal
$ npm run submissions:review -- 42
```

Review output for challenge submissions includes `claim_slug`. Review output for claim-request and standard-proposal includes the full `payload` JSON, pretty-printed.

---

## Feature 2: Claim Challenge Form

### Placement

Bottom of `/claims/[slug]` pages, below the sources section. A heading `Challenge this verdict` introduces the form.

### Fields

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `reason` | dropdown | yes | "Source is inaccurate", "Source is outdated", "Source is misrepresented", "Verdict is wrong", "Other" |
| `counter_url` | URL input | no | Valid URL, 2,048 chars max |
| `counter_quote` | textarea | no | 1,000 chars max |
| `notes` | textarea | no | 500 chars max; shown always |
| `cf-turnstile-response` | hidden | yes | Turnstile widget |
| `website` | hidden honeypot | -- | Must be empty |
| `_loaded_at` | hidden | -- | Timestamp set on page load |

`claim_slug` is set from the page URL, not a form field.

### UX

- Collapsed by default behind a "Challenge this verdict" button to keep claim pages uncluttered
- Expand/collapse via progressive JS; falls back to always-visible if JS is absent
- Without JS: form submits directly to the Worker as a standard POST; Turnstile is absent but the other 4 spam layers still fire
- With JS: `ParticipationForm.ts` upgrades to `fetch` + inline success/error state + Turnstile token injection
- `<noscript>` within the Turnstile widget area: "Spam protection requires JavaScript. Your submission will be reviewed but may be filtered." (No email redirect — the form still works.)
- Success state replaces the form: "Submitted — your input will be reviewed."
- Error state: inline message below the offending field

---

## Feature 3: Request a Claim Form

### Placement

On the `/claims` index page, below the claims list. Also accessible at `/request` (redirect or dedicated page — redirect preferred to avoid duplication).

### Fields

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `company_or_product` | text input | yes | 300 chars max |
| `topic_category` | dropdown | yes | Values from `research/templates.yaml` categories: `environmental-impact`, `data-privacy`, `ai-literacy`, `ai-safety`, `industry-analysis` |
| `why` | textarea | no | 300 chars max |
| `cf-turnstile-response` | hidden | yes | Turnstile widget |
| `website` | hidden honeypot | -- | Must be empty |
| `_loaded_at` | hidden | -- | Timestamp set on page load |

### UX

- Appears as a section titled "Request a claim" after the claims list
- Without JS: form submits directly to the Worker; Turnstile absent but other 4 spam layers fire
- With JS: `ParticipationForm.ts` upgrades to `fetch` + inline success/error state + Turnstile token
- Success state: "Submitted — your input will be reviewed."
- Submissions go into the triage queue. The operator decides whether to schedule research. No automated scheduling.

---

## Feature 4: Propose a Standard Form

### Placement

On the `/standards` index page, below the standards matrix.

### Fields

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `question_text` | text input | yes | 200 chars max; label: "Proposed claim template" |
| `entity_type` | radio or small dropdown | yes | "Company", "Product" |
| `category` | dropdown | yes | Values from `research/templates.yaml` categories: `environmental-impact`, `data-privacy`, `ai-literacy`, `ai-safety`, `industry-analysis` |
| `why_it_matters` | textarea | no | 300 chars max |
| `example_companies` | text input | no | 300 chars max; label: "Example companies" |
| `cf-turnstile-response` | hidden | yes | Turnstile widget |
| `website` | hidden honeypot | -- | Must be empty |
| `_loaded_at` | hidden | -- | Timestamp set on page load |

### UX

- Appears as a section titled "Propose a standard" after the standards matrix
- Without JS: form submits directly to the Worker; Turnstile absent but other 4 spam layers fire
- With JS: `ParticipationForm.ts` upgrades to `fetch` + inline success/error state + Turnstile token
- Success state: "Submitted — your input will be reviewed."
- Submissions go into a review queue. The operator decides whether to add to `research/templates.yaml`. No automated template creation.

---

## Shared form behavior

Applies to all three forms:

- No account required
- Base layer: standard `<form method="post" action="https://api.dangerousrobot.org/submissions/{type}">` with `application/x-www-form-urlencoded` encoding — works without JS
- Enhancement layer (JS present): `ParticipationForm.ts` intercepts submit, switches to `fetch` + JSON, injects Turnstile token, shows inline success/error state
- Turnstile widget loaded via the Cloudflare JS snippet; rendered invisible where possible. Without JS, Turnstile is absent — the four other spam layers compensate.
- Success state: replace form with "Submitted — your input will be reviewed." No ticket number in v1.
- Error state (JS path): inline message near the field or at the top of the form. Non-JS path: Worker returns a redirect to a static success/error page.
- CORS: Worker returns `Access-Control-Allow-Origin: https://dangerousrobot.org`
- A shared vanilla JS module (`src/components/ParticipationForm.ts`) handles the fetch enhancement, Turnstile token injection, and success/error state — avoiding duplicated logic across three pages. The three Astro pages each render their own form HTML; `ParticipationForm.ts` attaches to the form element on page load.

---

## File plan

### New files

| File | Purpose |
|------|---------|
| `src/components/ParticipationForm.ts` | Shared vanilla JS: attaches to a form element; upgrades submit to `fetch`, injects Turnstile token, handles success/error state. Honeypot and `_loaded_at` fields are rendered in Astro; this module sets `_loaded_at` on attach. |
| `docs/plans/public-participation-forms.md` | This plan |

### Edited files

| File | Change |
|------|--------|
| `workers/feedback/index.ts` (or equivalent) | Add routes: `POST /submissions/challenge`, `POST /submissions/claim-request`, `POST /submissions/standard-proposal`; add per-(IP, type) KV rate-limit logic |
| `workers/feedback/schema.sql` | Add `payload TEXT` column, `claim_slug TEXT` column, updated `type` CHECK constraint |
| `scripts/feedback-admin.ts` → `scripts/dr-admin.ts` | Rename; add `--type` filter to `list` command; extend `review` output to render `payload` fields |
| `package.json` | Rename npm scripts: `feedback:list` → `submissions:list`, `feedback:review` → `submissions:review`, `feedback:stats` → `submissions:stats` |
| `src/pages/claims/[slug].astro` | Add challenge form section below sources; import `ParticipationForm.ts` |
| `src/pages/claims/index.astro` | Add claim request form section; import `ParticipationForm.ts` |
| `src/pages/standards/index.astro` (or `standards.astro`) | Add standard proposal form section; import `ParticipationForm.ts` |

Note: `workers/feedback/` does not exist yet (Phase 6 not started). The Worker files will be created in Phase 6.1. This plan amends the schema and routes before they are finalized.

---

## Acceptance

- [ ] `POST /submissions/challenge` stores a row with `type='challenge'`, `claim_slug`, and `payload` JSON
- [ ] `POST /submissions/claim-request` stores a row with `type='claim-request'` and `payload` JSON
- [ ] `POST /submissions/standard-proposal` stores a row with `type='standard-proposal'` and `payload` JSON
- [ ] All three endpoints reject submissions with an invalid Turnstile token (logged, silent 200 returned)
- [ ] All three endpoints enforce per-(IP, type) rate limiting (5/hour)
- [ ] Honeypot and time-check fire on all three endpoints
- [ ] Challenge form appears on `/claims/[slug]` below the sources section; submits and shows success state
- [ ] Claim request form appears on `/claims`; submits and shows success state
- [ ] Standard proposal form appears on `/standards`; submits and shows success state
- [ ] `<noscript>` fallback displays on all three forms when JS is disabled
- [ ] `npm run submissions:list -- --type challenge` returns challenge submissions
- [ ] `npm run submissions:list -- --type claim-request` returns claim-request submissions
- [ ] `npm run submissions:list -- --type standard-proposal` returns standard-proposal submissions
- [ ] `npm run submissions:review -- [id]` renders payload fields for each type

---

## Execution

This plan depends on Phase 6.1 (Worker + D1 setup) being complete or in progress simultaneously. Steps that touch the Worker are effectively co-developed with Phase 6.

**Step 1 — Schema amendment**
Update `workers/feedback/schema.sql` to add `payload TEXT`, `claim_slug TEXT`, updated `type` CHECK constraint, and `idx_submissions_claim_slug` index. This happens before the database is initialized.

**Step 2 — Worker routes**
Add the three new route handlers to `workers/feedback/index.ts`. Each handler shares the existing spam-check middleware. Add per-(IP, type) KV rate-limit buckets.

**Step 3 — Shared form JS module**
Create `src/components/ParticipationForm.ts` with the fetch wrapper, Turnstile loader, honeypot injection, `_loaded_at` timestamping, and success/error state management.

**Step 4 — Challenge form**
Add challenge form section to `src/pages/claims/[slug].astro`. Wire to `POST /submissions/challenge`.

**Step 5 — Claim request form**
Add claim request form section to `src/pages/claims/index.astro`. Wire to `POST /submissions/claim-request`. Add `/request` redirect or alias.

**Step 6 — Standard proposal form**
Add standard proposal form section to the standards index page. Wire to `POST /submissions/standard-proposal`.

**Step 7 — Admin CLI rename and extension**
Rename `scripts/feedback-admin.ts` to `scripts/dr-admin.ts`. Add `--type` filter. Update npm scripts in `package.json`. Extend `review` output to render `payload` fields.

**Step 8 — Turnstile site key**
Register one Turnstile widget for `dangerousrobot.org` (covers all pages under that origin). The same site key and `TURNSTILE_SECRET` Worker secret from Phase 6 are reused.

**Step 9 — Smoke test**
Submit one of each type in a staging environment. Verify D1 rows, KV rate-limit keys, and `submissions:list --type` output.

---

## Backlog placement

These features extend Phase 6 as items 6.4, 6.5, and 6.6. No new phase number is needed. The Phase 6 BACKLOG.md entry should be updated when work begins to add these three items.

| # | Work Item | Plan | Status |
|---|-----------|------|--------|
| 6.4 | Claim challenge form + Worker endpoint | This plan | not started |
| 6.5 | Claim request form + Worker endpoint | This plan | not started |
| 6.6 | Standard proposal form + Worker endpoint | This plan | not started |

Dependency: 6.1 (Cloudflare Worker + D1 initial setup) must land before or alongside these.
