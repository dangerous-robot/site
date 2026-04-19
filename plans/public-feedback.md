# Public Feedback System

Plan for accepting public feedback on dangerousrobot.org research content without requiring a GitHub account.

## Problem

The site publishes structured research (claims, sources, entities). Members of the public should be able to:

1. **Flag problems** -- something is wrong or outdated in existing content
2. **Submit feedback** -- general commentary on research efforts or conclusions
3. **Submit claims** -- propose new claims or evidence

The standard GitHub issue/PR path should be gated by this process. GitHub contributors still use issues/PRs, but only after a submission exists in the feedback system.

## Decisions

| # | Decision | Choice | Notes |
|---|----------|--------|-------|
| 1 | Worker location | Same repo (`workers/feedback/`) | Simpler for solo maintainer |
| 2 | Turnstile | Include | Free, invisible, no user friction. Added to spam prevention stack |
| 3 | API subdomain | `api.dangerousrobot.org` | Clean separation from static site |
| 4 | Gating strategy | Strongly guided (templates + contact links) | Can switch to hard gated (Actions-based) later if needed |
| 5 | Skip Formspree prototype | Yes | Go straight to Cloudflare Workers + D1 (Option B) |

## 1. Survey of Existing Approaches

### How static/research sites handle public input without accounts

| Approach | Examples | Pros | Cons |
|----------|----------|------|------|
| **Form-to-email services** (Formspree, Formspark, Basin) | Small open-source projects, documentation sites | Zero infrastructure, free tiers, instant setup | No structured review workflow; inbox becomes the queue |
| **Serverless function + database** (Cloudflare Workers + D1/KV, Vercel Functions + Turso) | IndieWeb sites, small SaaS landing pages | Full control over schema, review UI, spam filtering | More to build and maintain |
| **GitHub Discussions** | Many open-source repos | Native to GitHub, threaded, searchable | Requires a GitHub account -- fails the core requirement |
| **Embedded comment systems** (Giscus, Utterances) | Dev blogs, documentation | Easy to add | Require GitHub accounts (backed by GitHub Discussions/Issues) |
| **Self-hosted feedback tools** (Fider, Canny self-hosted) | Product teams | Full-featured | Overkill for 1-2 maintainer repo; hosting costs |
| **Email link only** | Academic research, small nonprofits | Zero maintenance | No structure, no queue, hard to track |
| **Static forms with admin dashboard** (Tally, Typeform free tier) | Nonprofits, research surveys | Polished UX, conditional logic | Third-party dependency, free tier limits, data lives elsewhere |

**Key insight**: For a static site needing no-account submissions with structured admin review, the realistic options are (a) a form-to-email SaaS or (b) a lightweight serverless function + storage. Everything else either requires accounts or is over-engineered.

## 2. Spam Prevention Options

Evaluated for a static site form where the submitter has no account.

| Method | How it works | Effectiveness | Simplicity | Recommendation |
|--------|-------------|---------------|------------|----------------|
| **Honeypot fields** | Hidden form field; bots fill it, humans don't | Good against basic bots, poor against targeted attacks | Trivial to implement | **Use** -- first line of defense |
| **Time-based check** | Reject submissions completed in < N seconds (e.g., 3s) | Good against scripted bots | Trivial -- record timestamp on load, check on submit | **Use** -- complements honeypot |
| **Content-based heuristics** | Reject if body contains > N URLs, known spam patterns, or is empty | Good for link spam | Moderate -- needs tuning | **Use** -- simple rules only |
| **Rate limiting by IP** | Limit submissions per IP per hour | Good against volume attacks | Easy in serverless (KV counter) | **Use** -- essential baseline |
| **Simple challenge question** | "What does AI stand for?" or site-specific: "What color is the robot?" | Good against generic bots, poor against targeted | Easy UX if question is obvious | **Consider** -- optional, add if spam becomes a problem |
| **Proof-of-work (Hashcash-style)** | Client computes a hash before submission is accepted | Effective, no UX friction for humans | Moderate to implement, JS required | **Defer** -- interesting but over-engineered for current scale |
| **CAPTCHA (reCAPTCHA, hCaptcha, Turnstile)** | Visual/behavioral challenge | Very effective | Frustrates users, accessibility issues, third-party dependency | **Avoid** -- except Cloudflare Turnstile, which is invisible and free |
| **Cloudflare Turnstile** | Invisible challenge, no user interaction needed | Very effective, privacy-friendly | Requires Turnstile API key (free), JS snippet | **Use if Cloudflare stack** -- best CAPTCHA alternative |

### Spam stack (layered)

1. Honeypot field (hidden `website` field)
2. Time-based check (reject if < 3 seconds from page load)
3. Rate limiting (max 5 submissions per IP per hour via KV)
4. Content heuristic (reject if body has > 3 URLs or < 10 characters)
5. Cloudflare Turnstile (invisible, free)

This layered approach stops the vast majority of spam without any user-facing friction. Turnstile requires a JS snippet on the form page but is invisible to the user.

## 3. Submission Backend

### Option A: Form-to-email service (Formspree)

**How it works**: HTML form posts to `https://formspree.io/f/{form-id}`. Submissions arrive in email and in the Formspree dashboard.

- **Free tier**: 50 submissions/month, 1 form, email notifications
- **Pros**: Zero code to deploy, instant setup, built-in spam filtering, submissions dashboard
- **Cons**: No API for programmatic review; admin workflow is "check email/dashboard, then manually create GitHub issue"; 50/month limit is tight if spam leaks through; no structured follow-up with submitter (reply-to-email only)
- **Verdict**: Good for Phase 1 prototype but will likely need replacing

### Option B: Cloudflare Workers + D1

**How it works**: Astro form submits to a Cloudflare Worker endpoint. Worker validates, applies spam checks, stores submission in D1 (SQLite at the edge). Admin reviews via a simple dashboard (either a separate Worker route or a local CLI script).

- **Free tier**: Workers: 100K requests/day; D1: 5M reads/day, 100K writes/day, 5 GB storage
- **Pros**: Full control; structured data; can build admin dashboard; can programmatically create GitHub issues via API; rate limiting is native (KV or D1); Turnstile integration is trivial; free tier is absurdly generous for this use case
- **Cons**: More to build upfront (~200-300 lines of Worker code + admin UI); another service to manage
- **Verdict**: Best long-term fit. The free tier will never be exhausted at this scale.

### Option C: GitHub API via serverless function

**How it works**: Serverless function receives form submission, creates a GitHub issue labeled `feedback/pending` using a GitHub token.

- **Pros**: Everything stays in GitHub; admin reviews in the Issues tab
- **Cons**: Requires a PAT or GitHub App with write access stored as a secret; conflates public feedback with developer issues; no way to follow up with anonymous submitter; submission becomes immediately visible in the public issue tracker (may not want that)
- **Verdict**: Appealing but the "everything is a GitHub issue" model creates noise and loses the gating benefit

### Option D: Formspark / Basin / similar

Similar to Formspree. Formspark free tier: 250 submissions (lifetime, not monthly). Basin: 100/month free. Same pros/cons as Formspree with minor variations.

### Decision: Option B (Cloudflare Workers + D1)

Rationale:
- The site already uses a custom domain, so Cloudflare DNS is likely already in play (or trivially added)
- Free tier is more than sufficient for years of operation
- Full control over spam prevention, data schema, and admin workflow
- Turnstile for invisible CAPTCHA at zero cost
- Can programmatically create GitHub issues when submissions are approved
- D1 is SQLite -- familiar, debuggable, exportable
- The Worker is ~200 lines of code; the admin dashboard is ~100 more
- Worker lives in `workers/feedback/` in this repo
- `api.dangerousrobot.org` routes to the Worker

## 4. Admin Review Workflow

### Submission lifecycle

```
[Public submitter]
       |
       v
  POST /api/feedback
       |
       v
  [Spam checks] --fail--> 422 rejected (silent)
       |
      pass
       |
       v
  [D1: status=pending]
       |
       v
  [Admin notification] (email via Worker, or daily digest)
       |
       v
  [Admin reviews] ---> reject (with optional reason)
       |                  |
       |                  v
       |             [D1: status=rejected]
       |
       +---> accept
       |       |
       |       v
       |   [D1: status=accepted]
       |       |
       |       v
       |   [Optional: create GitHub issue via API]
       |       |
       |       v
       |   [Issue labeled: feedback/{type}, has submission ID]
       |
       +---> inquire (ask follow-up question)
               |
               v
          [D1: status=needs-info]
               |
               v
          [If submitter provided email: send follow-up]
          [If no email: mark as stale after 30 days]
```

### Where the admin sees pending submissions

**Option 1 (recommended for simplicity): CLI-based admin tool**

A local script (`scripts/feedback-admin.ts`) that queries the D1 database via the Cloudflare API or `wrangler d1 execute`:

```
$ npm run feedback:list
3 pending submissions

#12  [flag]     2026-04-18  "Anthropic safety score is outdated"
#11  [feedback] 2026-04-17  "Your renewable energy claims should cite..."
#10  [claim]    2026-04-15  "Google Gemini training data consent"

$ npm run feedback:review 12
Type:     flag
Content:  "The Anthropic existential safety score claim cites a 2025..."
Email:    alice@example.com
Submitted: 2026-04-18 14:32 UTC

Actions: [a]ccept  [r]eject  [i]nquire  [s]kip
> a

Created GitHub issue #45: "Flag: Anthropic safety score is outdated"
Submission #12 marked accepted.
```

**Option 2 (future): Admin dashboard Worker route**

A password-protected route at `/admin/feedback` served by the same Worker. Shows pending submissions in a simple HTML table with accept/reject/inquire buttons. This is more convenient but more code to build.

**Recommendation**: Start with the CLI tool. Build the dashboard only if the volume of submissions justifies it.

### Communicating with the submitter

- Submitters can optionally provide an email address
- If an email is provided, a confirmation link is sent immediately (token-based, expires 24 hours). The email is only stored and used for follow-up after the submitter clicks the link. This prevents phishing via spoofed email addresses.
- On accept/reject/inquire, the Worker sends a transactional email via Resend (free tier: 100 emails/day) -- but only to confirmed addresses
- If no email was provided (or unconfirmed), no follow-up is possible -- the submission is accepted or rejected silently
- Email content is templated and minimal: "Your feedback on dangerousrobot.org was received / accepted / we have a question"

### Approval flow into GitHub Issues/PRs

When admin accepts a submission:
1. The CLI tool (or admin dashboard) calls the GitHub API to create an issue
2. Issue is labeled `type:{flag|feedback|claim}` and `from:public`
3. Issue body includes: a header noting this is user-submitted content, the submission content wrapped in a blockquote (to prevent markdown injection), a link back to the submission ID. Strip `@` mentions from user content before insertion. Do not include submitter email in the issue body (it's in D1).
4. The admin (or a contributor) then handles the issue normally -- editing content, opening a PR, etc.

This is the "promotion path" -- approved feedback becomes a real GitHub issue that enters the standard workflow.

## 5. Gating Standard GitHub Contributions

### The gating requirement

"Issues and PRs cannot be opened without first satisfying the feedback mechanism."

This is the trickiest requirement. GitHub does not natively support "you cannot open an issue unless X." Options:

### Option A: Issue templates + blank issue restriction (Recommended)

GitHub supports disabling blank issues and providing only structured templates. Configure:

```yaml
# .github/ISSUE_TEMPLATE/config.yml
blank_issues_enabled: false
contact_links:
  - name: "Flag a problem with existing content"
    url: "https://dangerousrobot.org/feedback?type=flag"
    about: "Something is wrong or outdated -- submit through our feedback form"
  - name: "Submit feedback or a new claim"
    url: "https://dangerousrobot.org/feedback?type=claim"
    about: "Propose new evidence or claims through our feedback form"
  # Note: site bugs use the site-bug.yml issue template (below), NOT a contact link.
  # Do not add a contact_link with an empty URL -- it won't render.
```

Plus one issue template for non-content issues (actual site bugs):

```yaml
# .github/ISSUE_TEMPLATE/site-bug.yml
name: "Site bug report"
description: "Report a bug in the website (not research content)"
labels: ["bug"]
body:
  - type: textarea
    id: description
    attributes:
      label: "Bug description"
    validations:
      required: true
```

**Effect**: When someone clicks "New Issue," they see three options. Two of them redirect to the dangerousrobot.org feedback form. The third is for site bugs only. There is no blank issue option. Content feedback is funneled to the feedback system.

**Pros**: Uses native GitHub features. Clear UX. No enforcement gap for honest actors.
**Cons**: Does not *technically* prevent API-based issue creation. A determined GitHub user could still POST an issue via the API. This is acceptable -- the goal is to guide, not to build a wall.

### Option B: GitHub Actions issue validator

A workflow triggered by `issues: [opened]` that checks whether the issue references a feedback submission ID:

```yaml
on:
  issues:
    types: [opened]
jobs:
  validate:
    if: contains(github.event.issue.labels.*.name, 'needs-feedback-link') == false
    steps:
      - name: Check for feedback reference
        run: |
          # Check if issue body contains "Feedback-ID: NNN" or was created by the admin bot
          # If not, add a comment asking submitter to use the feedback form
          # Optionally close the issue
```

**Pros**: Actual enforcement.
**Cons**: Annoying for legitimate contributors; complex to maintain; creates friction for the repo owner opening issues for their own work.

### Option C: PR template with checklist

```markdown
<!-- .github/PULL_REQUEST_TEMPLATE.md -->
## PR Checklist

- [ ] Research content changes have a linked feedback submission or were initiated by a maintainer
- [ ] Sources are cited per AGENTS.md content rules
```

**Pros**: Lightweight reminder. **Cons**: Checklist, not enforcement.

### Recommendation: Option A (templates + contact links) plus Option C (PR template)

Full gating (Option B) is impractical for a 1-2 person repo. The owner needs to open issues freely. The goal is to make the feedback form the obvious, easy path for the public while keeping the repo usable for maintainers.

The template approach achieves this: public visitors to the GitHub repo are guided to the feedback form for content issues. The PR template reminds contributors about the feedback link. This is "strongly guided" rather than "hard gated" -- and that is the right tradeoff.

### Upgrade path to hard gating

If spam or unauthorized issues become a problem, add a GitHub Actions workflow that auto-closes issues not matching approved patterns:

```yaml
# .github/workflows/issue-gate.yml
name: Issue Gate
on:
  issues:
    types: [opened]
jobs:
  validate:
    runs-on: ubuntu-latest
    if: github.event.issue.author_association != 'OWNER' && github.event.issue.author_association != 'MEMBER'
    steps:
      - name: Check for feedback reference
        uses: actions/github-script@v7
        with:
          script: |
            const body = context.payload.issue.body || '';
            const hasFeedbackId = /Feedback-ID:\s*\d+/.test(body);
            const isSiteBug = context.payload.issue.labels.some(l => l.name === 'bug');
            if (!hasFeedbackId && !isSiteBug) {
              await github.rest.issues.createComment({
                ...context.repo,
                issue_number: context.issue.number,
                body: 'Content feedback should be submitted via [our feedback form](https://dangerousrobot.org/feedback). This issue will be closed. If this is a site bug, please reopen with the bug template.'
              });
              await github.rest.issues.update({
                ...context.repo,
                issue_number: context.issue.number,
                state: 'closed'
              });
            }
```

This workflow is not active by default. Add it when/if the strongly-guided approach proves insufficient.

## 6. Architecture Recommendation

### Component diagram

```
                     dangerousrobot.org
                     (Astro / GitHub Pages)
                            |
                     /feedback page
                     (static Astro page with <form>)
                            |
                            | POST
                            v
               api.dangerousrobot.org/submit
               (Cloudflare Worker)
                   |              |
                   |         [Spam checks]
                   |         - Honeypot
                   |         - Time check
                   |         - Rate limit (KV)
                   |         - Content heuristic
                   |         - Turnstile verify
                   |              |
                   |         pass/fail
                   |              |
                   v              v
              [Cloudflare D1]   422 reject
              submissions table
                   |
                   |
        +----------+-----------+
        |                      |
   [CLI admin tool]     [Email notification]
   scripts/feedback-    (Resend or CF Email)
   admin.ts
        |
        | accept
        v
   [GitHub API]
   create issue with
   labels + metadata
        |
        v
   [GitHub Issues]
   standard workflow
```

### Technology choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Form page** | Astro page (`src/pages/feedback.astro`) | Part of the existing site; no new infrastructure |
| **Submission endpoint** | Cloudflare Worker | Free tier (100K req/day), edge latency, native rate limiting |
| **Data store** | Cloudflare D1 | Free tier (5M reads/day, 100K writes/day), SQLite, pairs with Workers |
| **Rate limit store** | Cloudflare KV | Free tier (100K reads/day), low-latency counters |
| **Invisible CAPTCHA** | Cloudflare Turnstile | Free, invisible, privacy-friendly, included in form |
| **Admin review** | CLI script (`scripts/feedback-admin.ts`) | No additional infrastructure; uses `wrangler d1 execute` |
| **Email notifications** | Resend (free tier: 100/day) | Simple API, generous free tier, no domain verification needed for low volume |
| **GitHub integration** | GitHub REST API via CLI tool | Creates issues labeled `from:public` + `feedback/{type}` |
| **Issue gating** | GitHub issue templates + contact links | Native feature, redirects public to feedback form |

### D1 schema

```sql
CREATE TABLE submissions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  type       TEXT NOT NULL CHECK(type IN ('flag', 'feedback', 'claim')),
  status     TEXT NOT NULL DEFAULT 'pending'
               CHECK(status IN ('pending', 'accepted', 'rejected', 'needs-info', 'stale')),
  name       TEXT,
  email      TEXT,
  page_url   TEXT,          -- which page the feedback is about (for flags)
  subject    TEXT NOT NULL,
  body       TEXT NOT NULL,
  source_url TEXT,          -- evidence URL (for claim submissions)
  ip_hash    TEXT,          -- HMAC-SHA-256 of IP with secret key (not bare SHA-256; IPv4 keyspace is trivially reversible)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  github_issue_number INTEGER,  -- set when promoted to an issue
  admin_notes TEXT
);

CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_type ON submissions(type);
```

### API endpoint spec

**`POST /submit`**

Request body (JSON or form-encoded):
```json
{
  "type": "flag|feedback|claim",
  "name": "Alice (optional)",
  "email": "alice@example.com (optional)",
  "page_url": "https://dangerousrobot.org/claims/anthropic/existential-safety-score",
  "subject": "Safety score seems outdated",
  "body": "The claim references a 2025 report but Anthropic published...",
  "source_url": "https://example.com/new-report (optional, for claims)",
  "cf-turnstile-response": "<token>",
  "website": "",
  "_loaded_at": 1713456000
}
```

- `website` is the honeypot (hidden field, must be empty)
- `_loaded_at` is the timestamp when the form loaded (for time check)
- `cf-turnstile-response` is the Turnstile token (validated server-side, see Security section)

**Input length limits** (enforced server-side, reject silently if exceeded):

| Field | Max length | Validation |
|-------|-----------|------------|
| `name` | 200 chars | Strip control characters |
| `email` | 254 chars | RFC 5321 format validation |
| `subject` | 500 chars | Required, min 5 chars |
| `body` | 10,000 chars | Required, min 10 chars |
| `page_url` | 2,048 chars | Must be `https://dangerousrobot.org/...` if present |
| `source_url` | 2,048 chars | Valid URL format if present |

**CORS**: The Worker must return `Access-Control-Allow-Origin: https://dangerousrobot.org` (not `*`). Validate the `Origin` header and reject requests from unlisted origins with 403. Allowlist: `https://dangerousrobot.org`, `https://www.dangerousrobot.org`.

**D1 queries**: Always use bound parameters (`db.prepare("...").bind(...)`), never string concatenation.

Response:
- `200 OK` -- submission accepted (always returns 200 to avoid leaking validation info to bots)
- Actual validation failures are silent (return 200 with a generic "thank you" message)
- The Worker should log rejection reasons (with request ID) to Workers Logs for admin debugging
- Response body shape and timing must be identical for success and failure to prevent side-channel leakage

### Cost estimate

| Service | Free tier | Expected usage | Monthly cost |
|---------|-----------|----------------|--------------|
| Cloudflare Workers | 100K req/day | < 100 req/day | $0 |
| Cloudflare D1 | 5M reads, 100K writes/day | < 100 writes/day | $0 |
| Cloudflare KV | 100K reads/day | < 1000 reads/day | $0 |
| Cloudflare Turnstile | Unlimited | < 100/day | $0 |
| Resend emails | 100/day | < 5/day | $0 |
| GitHub API | 5000 req/hour (authenticated) | < 10/day | $0 |
| **Total** | | | **$0** |

## 7. Implementation Phases

### Phase 1: GitHub config + feedback form + Cloudflare backend

**Goal**: Working feedback form on the site, backed by Cloudflare Workers + D1, with GitHub issue templates redirecting content feedback to the form.

1. Set up GitHub issue templates with `blank_issues_enabled: false` and contact links to `/feedback`
2. Add PR template with DCO sign-off reminder and research content checklist
3. Add CODEOWNERS (`* @brandonfaloona`, `research/ @brandonfaloona`)
4. Add labels: use consistent colon-delimited namespace (`from:public`, `type:flag`, `type:feedback`, `type:claim`, `status:needs-triage`, `content`, `ai-generated`)
5. Add `SECURITY.md` with responsible disclosure process (email contact for vulnerability reports)
6. Add `CODE_OF_CONDUCT.md` (Contributor Covenant) -- sets behavioral expectations for GitHub contributors and feedback submitters
7. Expand `CONTRIBUTING.md`: feedback form path for content contributions, AI disclosure requirements, which directories map to which license, DCO sign-off instructions
8. Create `src/pages/feedback.astro` with form for all three types, `<noscript>` fallback, privacy notice, confirmation state, and query-param pre-population for deep links
9. Add "Report a problem" links to claim and source detail pages (deep-link to `/feedback?type=flag&page_url=...`)
10. Add "Feedback" link in site footer
11. Add Cloudflare Turnstile to the form
10. Set up Cloudflare Worker project in `workers/feedback/`
11. Create D1 database with the submissions schema
12. Implement the Worker: validation, input length limits, spam checks (honeypot, time, rate limit via KV, content heuristic, Turnstile server-side verification), CORS, D1 insert with bound parameters
13. Configure `api.dangerousrobot.org` DNS to route to the Worker
14. Enable branch protection on `main`: require CI status checks to pass, enforce linear history, set repo owner as bypass actor. Do NOT require reviews (impractical for solo maintainer).

**Deliverables**: Spam-resistant submission pipeline, structured data in D1, GitHub issue gating via templates, repo governance files (SECURITY.md, CODE_OF_CONDUCT.md, expanded CONTRIBUTING.md)

### Phase 2: Admin CLI + GitHub integration

**Goal**: Admin can review, accept/reject, and promote submissions to GitHub issues.

1. Build `scripts/feedback-admin.ts` -- queries D1 via Cloudflare API
2. Add npm scripts: `feedback:list`, `feedback:review`, `feedback:stats`
3. Implement GitHub issue creation on acceptance (using `gh` CLI or GitHub API)
4. Add email follow-up for accepted/rejected/inquired submissions (via Resend)
5. Add `from:public` and `feedback/{type}` labels to the repo

**Deliverables**: Complete admin workflow, GitHub issue promotion

### Phase 3 (optional): Admin dashboard

**Goal**: Web-based admin UI for reviewing submissions, if CLI proves insufficient.

1. Add authenticated route to the Worker (`/admin/*`)
2. Simple HTML dashboard: table of pending submissions, action buttons
3. Auth via a shared secret or Cloudflare Access (free for up to 50 users)

**Deliverables**: Browser-based admin review

### Phase sequencing

```
Phase 1: GH config + form + Worker + D1    [2-3 days] -- full pipeline
    |
Phase 2: Admin CLI + GH issue promotion    [1-2 days] -- complete workflow
    |
Phase 3: Admin dashboard (optional)        [1-2 days] -- defer unless needed
```

## 8. Feedback Form UX Design

### Discoverability

The feedback form lives at `/feedback`, but visitors need to find it:

- **Site-wide**: Add a "Feedback" link in the footer nav (not the main nav -- it's secondary to the research content)
- **Claim pages**: Add a "Report a problem with this page" link at the bottom of each claim detail page. This link should deep-link with pre-populated context: `/feedback?type=flag&page_url={current_page_url}`
- **Source pages**: Same pattern -- "Something wrong with this source?"

Deep-linking preserves context so the submitter doesn't have to re-find and paste the URL.

### Form wireframe

```
dangerousrobot.org/feedback

------------------------------------------------------------
SUBMIT FEEDBACK

We welcome corrections, commentary, and new evidence.
No account required. A maintainer will review your
submission. We'll only be able to respond if you
include your email.

[What would you like to do?] (radio buttons)
  (*) Report a problem -- something is wrong or outdated
  ( ) Share feedback -- commentary on our research
  ( ) Suggest new evidence -- something we should look into

[Which page has the problem?] (shown for "report" type, pre-filled from query param)
  [https://dangerousrobot.org/claims/...]

[Subject]
  [Brief summary]

[Details]
  [Textarea -- describe the issue, include evidence or links]

[Link to evidence] (shown for "suggest" type)
  If you have a link to a report, article, or dataset:
  [https://...]

[Your name] (optional)
  [                    ]

[Your email] (optional)
  Without an email, we can't let you know what we
  did with your feedback.
  [                    ]

<!-- hidden honeypot field, aria-hidden, tabindex=-1 -->

[Submit]

------------------------------------------------------------
PRIVACY: Your submission is stored securely and reviewed
by a maintainer. We store your name and email only if
provided. IP-derived data is stored in hashed form for
spam prevention and deleted after 90 days. We do not
share your information with third parties.
------------------------------------------------------------
```

### Confirmation state

After submission, replace the form with a confirmation message:

```
------------------------------------------------------------
THANK YOU

Your feedback has been received. A maintainer will
review it -- this typically happens within a few days.

[If email was provided:]
  We'll email you at a]***@example.com when there's
  an update.

[If no email was provided:]
  Since you didn't include an email, we won't be able
  to follow up with you directly.

[Submit another] (link back to /feedback)
------------------------------------------------------------
```

This message is the same whether the submission passed or failed spam checks (to avoid leaking validation state).

### JavaScript and accessibility

Turnstile requires JavaScript. This means the form cannot fully function without JS. Resolution:

- The form renders server-side with all fields visible (no conditional hide/show without JS)
- A `<noscript>` block at the top of the form displays: "This form requires JavaScript for spam prevention. If you cannot enable JavaScript, email feedback@dangerousrobot.org instead."
- With JS enabled: conditional fields show/hide based on type selection, Turnstile loads invisibly
- Keyboard navigation: all fields are standard HTML form elements with proper `<label>` associations
- Screen readers: honeypot field uses `aria-hidden="true"` and `tabindex="-1"`

### User-facing language

Avoid project jargon. The internal types map to user-facing labels:

| Internal type | User-facing label | Description shown |
|---------------|-------------------|-------------------|
| `flag` | "Report a problem" | Something is wrong or outdated |
| `feedback` | "Share feedback" | Commentary on our research |
| `claim` | "Suggest new evidence" | Something we should look into |

The word "claim" is project-internal. Users think in terms of problems, opinions, and evidence.

## 9. Resolved Decisions

1. **Worker location**: Same repo (`workers/feedback/`). Simpler for solo maintainer.
2. **Email provider**: Resend (free tier: 100/day). Set up in Phase 2 with admin CLI.
3. **Formspree**: Skipped. Going straight to Cloudflare Workers + D1.
4. **Turnstile**: Included. Form requires JS; `<noscript>` fallback provides an email contact alternative.
5. **Subdomain**: `api.dangerousrobot.org` for clean separation.
6. **Gating**: Strongly guided (templates + contact links). Hard gating workflow is documented above and can be activated if needed.
7. **Email verification**: Submitter emails are confirmed via a one-time link before follow-up emails are sent (prevents phishing via spoofed email addresses).
8. **Admin dashboard auth**: Cloudflare Access only (no shared secrets).
9. **Branch protection**: CI status checks + linear history. No review requirement (solo maintainer). Owner bypass enabled.
10. **Privacy notice**: Inline on the feedback form page. No separate privacy policy page needed at this scale.

## 10. Security Hardening

### Turnstile server-side validation (required)

The Worker must validate the Turnstile token server-side before accepting any submission. Without this, an attacker bypasses Turnstile by POSTing directly to the API.

```
POST https://challenges.cloudflare.com/turnstile/v0/siteverify
Body: { secret: TURNSTILE_SECRET, response: cf-turnstile-response, remoteip: client_ip }
```

- Reject if the token is missing, invalid, or already used (Turnstile tokens are single-use)
- The `TURNSTILE_SECRET` is stored via `wrangler secret put TURNSTILE_SECRET`

### IP hashing

Use `HMAC-SHA-256(IP, secret_key)` instead of bare `SHA-256(IP)`. The IPv4 keyspace (~4.3 billion values) is trivially reversible with a rainbow table. The HMAC key is stored as a Worker secret (`wrangler secret put IP_HMAC_KEY`).

### Email verification to prevent phishing

An attacker could submit with `email: victim@example.com`, causing the admin to send unsolicited email to someone who never submitted. Mitigation:

- On submission, if an email is provided, send a one-time confirmation link (token-based, expires in 24 hours)
- Only store the email in D1 and enable follow-up emails after the submitter clicks the confirmation link
- If unconfirmed, treat the submission as anonymous (no follow-up possible)

### GitHub issue content safety

When user-submitted text is placed into a GitHub issue body, wrap it in a blockquote with a clear label to prevent markdown injection, fake headers, misleading links, or `@mention` spam:

```markdown
> **User-submitted content (unverified):**
>
> [fenced user text here]
```

Strip `@` mentions from user content before inserting into the issue body.

### Time-check hardening

The `_loaded_at` timestamp is client-controlled and trivially spoofable. Two options:

- **Acceptable for now**: Keep client timestamp but acknowledge it only stops naive bots. The other four spam layers compensate.
- **Stronger (future)**: Issue a signed nonce via a `GET /api/feedback/init` endpoint. The nonce embeds the server timestamp and is verified on submission.

### GitHub token

Use a fine-grained PAT scoped to only the `dangerous-robot/site` repository with Issues read/write permission. Do not use a classic PAT with `repo` scope (grants full read/write to all repos). Store in system keychain or `.env` (already in `.gitignore`).

### Admin dashboard auth (Phase 3)

Use Cloudflare Access exclusively (free tier, up to 50 users). Remove the "shared secret" option -- it is vulnerable to browser history leakage and credential sharing. Cloudflare Access provides SSO and audit logging.

### Data retention policy

- Delete rejected/stale submissions after 90 days
- Anonymize accepted submissions after 1 year (remove name, email, ip_hash; keep content for audit trail)
- Add a `feedback:purge` CLI command that enforces these policies
- Document retention period in the privacy notice on the feedback form

### Rate limiting gaps (acknowledged)

IP-based rate limiting (5/hour via KV) is trivially bypassed with proxies. This is acceptable at current scale. Turnstile's built-in bot scoring is the primary defense against distributed attacks. Consider adding a secondary rate limit by email address (if provided) in the future.

## 11. Additional Resolved Decisions

1. **Turnstile keys**: Site key hardcoded in form page. Secret key as a Worker secret (`wrangler secret put TURNSTILE_SECRET`).
2. **Admin notifications**: Email per submission (not a digest). Low volume expected initially.
3. **CONTRIBUTING.md AI disclosure**: Added in Phase 1 alongside the GitHub config work.
