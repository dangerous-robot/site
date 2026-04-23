# Unscheduled Work

Work known but not yet assigned to a release. Items here are candidates for the next release or future releases.

---

## Pipeline performance & hardening

Goal: Reduce onboarding wall time and wasted API calls.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Reuse verify_claim sources in onboard | [onboard-reuse-verify-sources.md](plans/onboard-reuse-verify-sources.md) | Eliminates duplicate research+ingest per template (~2x per-template speedup) |
| Ingestor fail-fast on 401/403/451 | [ingestor-fail-fast-403.md](plans/ingestor-fail-fast-403.md) | Terminal exception short-circuits PydanticAI agent run; no wayback escalation |
| Researcher host blocklist | [researcher-host-blocklist.md](plans/researcher-host-blocklist.md) | `research/blocklist.yaml` filters LinkedIn/WSJ/FT/etc before ingest |
| Tighten ingestor timeouts | [ingestor-tighten-timeouts.md](plans/ingestor-tighten-timeouts.md) | `httpx.Timeout(connect=5, read=15, …)`; agent wrapper 90s → 60s |
| Parallelize onboard templates | [onboard-parallelize-templates.md](plans/onboard-parallelize-templates.md) | `asyncio.Semaphore(3)`-guarded gather; interactive mode clamps to 1 |

Recommended implementation order: reuse sources → fail-fast → blocklist → timeouts → parallelize.

---

## AI Research Audit Trail

Goal: On each `/claims/[slug]` page, show a collapsible section with which agent ran the research, what sources were consulted, when a human reviewed it, and whether the verdict changed from draft. Builds reader trust by making the AI+human process visible.

Architecture: sidecar `.audit.yaml` file per claim, written by the pipeline after the auditor runs, consumed by a custom Astro loader. Full 3-stage architectural review completed.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Sidecar format + pipeline write + Astro loader + UI (Stage 1) | [audit-trail.md](plans/audit-trail.md) | `_write_audit_sidecar` in persistence.py; `dr review --claim` CLI; collapsible UI |
| Extended audit fields + staleness check + orphan CI gate (Stage 2) | [audit-trail.md](plans/audit-trail.md) | Requires: no stale sidecars, orphan check CI, backfill script |
| Append-only history (Stage 3) | [audit-trail.md](plans/audit-trail.md) | Full recheck history per claim |

Scheduling note: Stage 1 (pipeline write + Astro loader) depends on pipeline work (persistence.py). Decision needed: before or after pipeline hardening?

---

## Ops Runbook

Goal: A single reference doc (`docs/RUNBOOK.md`) covering the dev loop, pipeline operations, deploy process, and content schema changes.

| Work Item | Notes |
|-----------|-------|
| Write RUNBOOK.md | Dev loop (HMR, restart triggers), `dr` CLI reference, deploy steps, schema change checklist |
| Expand source `kind` enum | Add `statement` (social posts, press releases, direct submissions) and `filing` (company invoices, certificates, contracts). Schema change touches `content.config.ts`, pipeline `SourceFrontmatter`, and `_classify_source_type`. |

---

## Automation (conditional)

Goal: Recurring audits, queue-based intake. Trigger: enough content exists that manual auditing is burdensome.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Scheduled citation audits | [scheduled-citation-audits.md](plans/drafts/scheduled-citation-audits.md) | Scheduled workflows, QUEUE.md intake |

Downstream sync to parallax-ai: [future/downstream-sync.md](plans/future/downstream-sync.md) -- good idea, not needed now.

---

## Public Feedback & Contribution Gating

Goal: Members of the public can submit feedback on content without a GitHub account. GitHub issue/PR process is gated via templates that redirect content feedback to the site.

| Work Item | Plan | Notes |
|-----------|------|-------|
| GitHub config + feedback form + Cloudflare backend | [public-feedback.md](plans/public-feedback.md) | Issue templates, CODEOWNERS, Astro form, Worker + D1 + Turnstile, `api.dangerousrobot.org` |
| Admin CLI + GitHub issue promotion | [public-feedback.md](plans/public-feedback.md) | `scripts/feedback-admin.ts`, accept/reject/inquire, Resend email |
| Admin dashboard (optional) | [public-feedback.md](plans/public-feedback.md) | Web UI for reviewing submissions. Defer unless CLI proves insufficient. |
| Claim challenge form | [public-participation-forms.md](plans/public-participation-forms.md) | Per-claim refutation form; extends feedback D1 schema + Worker |
| Request a claim form | [public-participation-forms.md](plans/public-participation-forms.md) | Sitewide research request form |
| Propose a standard form | [public-participation-forms.md](plans/public-participation-forms.md) | `/standards` form for new claim templates |

Done when: Public can submit feedback at `dangerousrobot.org/feedback`, admin can review via CLI, approved feedback becomes a GitHub issue.

Scheduling note: challenge/request/propose forms (last three items) require the feedback backend (first three). Decision needed: bundle or treat as later add-on?

---

## Site gaps and deferred content

From architectural review (2026-04-18) and TODO.md:

### Blocked

- **Configure custom domain in GitHub Pages UI** -- `dangerousrobot.org` is verified at the account level, DNS records are set (A records + CNAME), repo is public, Pages is enabled, but Settings > Pages still returns "You cannot set a custom domain at this time." Troubleshoot: check if the account is a free org (may need GitHub Pro/Team for custom domains on org repos), try the API (`gh api repos/dangerous-robot/site/pages -X PUT`), or contact GitHub Support.

### Deferred content (unsourced)

- **Structure chatbot comparison table** -- Comparison data exists in `parallax-ai/frontend/src/lib/comparison-data.ts` (transparency + feature comparisons across 5 competitors). Treat as unsourced claims; need source files backing each cell before publishing.
- **Structure AI Product Card data** -- Transparency/nutrition-label data exists in `parallax-ai/frontend/src/app/transparency/page.tsx` (models, energy, ethics, commitments). Treat as unsourced claims; need source files for each assertion.

### Site gaps

- **List/index pages** -- No pages exist at `/claims/`, `/sources/`, or `/entities/`. Add index pages listing all entries. Add `/about` page.
- **Entity reference validation** -- Claims reference entities by path string with no build-time validation. Use Astro's `reference('entities')` helper or add entity-ref checking to `scripts/check-citations.ts`.
- **Source reference upgrade** -- Replace `z.array(z.string())` with `z.array(z.string().min(1)).min(1)` for claims `sources` field. Current schema permits empty arrays.
- **Deploy workflow quality checks** -- `deploy.yml` only runs `npm run build`, skipping lint and citation checks. Add checks to deploy.yml or require CI status checks via branch protection.
- **`verdictColors` deduplication** -- Same color map copy-pasted in `index.astro`, `claims/[...slug].astro`, `entities/[...slug].astro`. Extract to a shared module.
- **Homepage entity name resolution** -- Homepage displays raw entity slugs instead of human-readable names.
- **`recheck_cadence_days` constraint** -- Schema accepts 0/negative values. Add `.int().min(1)` to the Zod definition.
- **GitHub Actions SHA pinning** -- All actions use mutable tags (`@v4`). Pin by full SHA for supply chain security.
- **SEO basics** -- No favicon, robots.txt, canonical URLs, Open Graph tags. `description` prop in Base.astro is never customized per page.
- **Accessibility** -- No skip-to-content link, no `aria-label` on nav, no `<header>` wrapper.

### Opportunities

- **Validation gaps** -- CI validates schema structure and citation integrity but not reasoning quality. Potential additions: confidence-to-verdict alignment, staleness detection, source URL liveness checks, archived URL population nudges, a check framework (Vitest) for scripted validators.
- **Confidence rubric** -- Define what `high`/`medium`/`low` confidence concretely means. Use an LLM to check each claim against the rubric.
- **Claim Updater instruction quality** -- Consider adversarial review, inter-rater consistency validation, and forbidden-combination gates (CI rejection of nonsensical confidence-verdict pairs).

---

## Follow-up items (2026-04-22)

From `docs/follow-up-2026-04-22.md`:

### Browser testing -- implemented features

Four features were implemented and the build passes. Each needs a browser walkthrough before the work is considered done.

**Feature 1: `/methodology`**
- [ ] Read through the page -- does the voice match the site? Does it cover the actual pipeline steps accurately?
- [ ] Check the link to `/scope` resolves
- [ ] Check readable at narrow viewport

**Feature 5: Confidence inline explainer (claim detail pages)**
- [ ] Open a claim page (e.g., `/claims/anthropic/publishes-sustainability-report`)
- [ ] Expand the confidence `<details>` -- does the copy make sense for this specific claim?
- [ ] Verify the collapsed state looks the same as the old confidence span (flex row not broken)
- [ ] Check on mobile

**Feature 6: Source type badges**
- [ ] Open several source detail pages and spot-check `source_type` classification
- [ ] Check badge appears before the `kind` badge in the header
- [ ] Check tooltip appears on hover
- [ ] Review a handful of the 146 backfilled files for classification accuracy

**Feature 9: `/scope`**
- [ ] Read through -- does it accurately reflect what the site actually covers?
- [ ] Add or remove scope items if anything is wrong
- [ ] Check the link to `/methodology` resolves

### Content review -- draft copy on new pages

- [ ] `/methodology` -- are the three confidence level descriptions accurate to how the pipeline actually works?
- [ ] `/scope` -- are the out-of-scope items the ones you actually intend?
- [ ] Both pages -- does the brand voice feel right?

### Nav/discoverability

- [ ] Add `/methodology` and `/scope` to the footer alongside the TreadLightly and license links
- [ ] Confirm the cross-links between the two pages are in place

### Source type classification -- edge cases to revisit

- **SEC EDGAR filings** -- classified as `primary`; verify this is correct.
- **B Lab / B Corp profiles** -- classified as `secondary`; confirm.
- **UNESCO, NTIA, UNFCCC** -- classified as `secondary`; confirm.
- **IBM, Deloitte reports** -- classified as `secondary`; some may lean tertiary. Spot-check.

### Scheduling decisions

| Item | Decision |
|------|----------|
| Pipeline performance & hardening | v0.1.0 blocker (resolved 2026-04-22) |
| Audit trail (sidecar + pipeline write + Astro loader + UI) | v0.1.0 blocker (resolved 2026-04-22; prerequisite for audit trail CI gates) |
| Public feedback (Worker + D1 + admin CLI) | Post-v0.1.0 (resolved 2026-04-22) |
| Participation forms (challenge/request/propose) | Open -- depends on public feedback timing; bundle or after decision still needed |
