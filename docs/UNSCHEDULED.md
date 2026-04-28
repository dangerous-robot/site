# Unscheduled Work

Work known but not yet assigned to a release. Items here are candidates for the next release or future releases.

---

## Per-entity detail pages

Goal: Render company / product / sector detail pages so entity body content (e.g. the COI blockquote on `research/entities/products/treadlightlyai.md`) is actually visible to readers. Today only `index.astro` exists for `companies/` and `products/`, and the entity body is dropped at build. The treadlightlyai COI block was added 2026-04-27 in anticipation of these pages; until they ship, the canonical disclosure is the FAQ accordion.

Also unlocks: rendering `parent_company` cross-links from product pages back to the company page (and vice versa via a query of the entity collection).

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

## Pipeline observability

Goal: Make per-object model spend visible so we can see which claims, sources, and entities are consuming the most tokens, and what the daily/weekly burn looks like.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Token usage log + `inv tokens.summary` | [token-usage-log.md](plans/token-usage-log.md) | Append-only JSONL at `logs/token-log.jsonl` written by a thin wrapper around every `agent.run(...)`; `inv tokens.summary --by object\|time` reader; no DB, no UI |

---

## Analyst decomposition (cost lever)

Goal: Split the Analyst's frontier-model call into smaller sub-decisions so cheaper models can handle the parts that don't need full reasoning. Aligns with the "small decisions, small models" principle in `AGENTS.md`.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Full 4-step decomposition (entity resolver, per-source stance, verdict synthesizer, narrative+title writer) | [analyst-decomposition_stub.md](plans/drafts/analyst-decomposition_stub.md) | Stub draft; needs token-usage baseline before committing. Keeps verdict+confidence on frontier; pushes the rest to Haiku-class. Biggest win is feeding frontier structured stances instead of raw source bodies (~10x smaller prompt). |
| Narrative + title writer extraction (smallest slice) | (to be drafted from the stub) | Once verdict is fixed, this is structured writing with a mechanical title-polarity rule. Most defensibly Haiku-class sub-decision; could be promoted out of the broader plan as a single-step extraction. |

---

## Dedup detection on URL ingest and claim creation

Goal: Stop creating duplicate sources/claims when the pipeline encounters a URL or claim that already exists. Today the pipeline writes a new file or fails on a path collision rather than reusing the existing object.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Match-and-return-existing for URL ingest and claim creation | [pipeline-dedup-detection_stub.md](plans/drafts/pipeline-dedup-detection_stub.md) | URL match: canonicalize (lowercase scheme/host, strip default ports, drop fragment + `utm_*`/`fbclid`/etc, strip trailing slash) and look up existing source by `canonical_url` frontmatter. Claim match: `(entity_slug, criteria_slug)` from frontmatter (already present today). On hit: `dr ingest` prints existing id, exits 0; onboard skips analyst+auditor and logs the dedup hit in the sidecar. `--force` bypasses dedup. Composes with onboard-reuse-verify-sources.md. |

---

## PDF attachment as alternate source content surface

Goal: Let a locally-attached PDF stand in for an unreachable URL (401/402/403/451 origins) as a content surface for both the ingestion agent and the human reviewer. Pairs with the fail-fast plan — when the ingestor can't fetch, a pre-attached PDF is the fallback.

| Work Item | Plan | Notes |
|-----------|------|-------|
| PDF attachment core (ingestion + model) | [source-pdf-attachment.md](plans/source-pdf-attachment.md) | `pdfs:` frontmatter block, `_attachments.yaml` manifest, `pdf_read` tool, `dr attach-pdf` CLI, sha256 integrity lint |
| PDF attachment publish surface | [source-pdf-publish.md](plans/drafts/source-pdf-publish.md) | Site renders `republish: true` PDFs with download link; `_headers` `noindex`; depends on core landing |

---

## AI Research Audit Trail

Goal: On each `/claims/[slug]` page, show a collapsible section with which agent ran the research, what sources were consulted, when a human reviewed it, and whether the verdict changed from draft. Builds reader trust by making the AI+human process visible.

Architecture: sidecar `.audit.yaml` file per claim, written by the pipeline after the auditor runs, consumed by a custom Astro loader. Full 3-stage architectural review completed.

| Work Item | Plan | Notes |
|-----------|------|-------|
| ~~Sidecar format + pipeline write + Astro loader + UI (Stage 1)~~ | [audit-trail.md](plans/completed/audit-trail.md) | **Done** (2026-04-25, moved to `completed/`). `_write_audit_sidecar` in persistence.py; `dr review --claim` CLI; collapsible UI; 11 sidecars committed. |
| Extended audit fields + staleness check + orphan CI gate (Stage 2) | [audit-trail-extensions.md](plans/audit-trail-extensions.md) | Requires: no stale sidecars, orphan check CI, backfill script |
| Append-only history (Stage 3) | [audit-trail-extensions.md](plans/audit-trail-extensions.md) | Full recheck history per claim |

Scheduling note: Stage 1 (pipeline write + Astro loader) depends on pipeline work (persistence.py). Decision needed: before or after pipeline hardening?

---

## Ops Runbook

Goal: A single reference doc (`docs/RUNBOOK.md`) covering the dev loop, pipeline operations, deploy process, and content schema changes.

| Work Item | Notes |
|-----------|-------|
| Write RUNBOOK.md | Dev loop (HMR, restart triggers), `dr` CLI reference, deploy steps, schema change checklist |
| Expand source `kind` enum | Add `statement` (social posts, press releases, direct submissions) and `filing` (company invoices, certificates, contracts). Schema change touches `content.config.ts`, pipeline `SourceFrontmatter`, and `_classify_source_type`. |

---

## Developer tooling

Goal: Convert ad-hoc POC scripts into durable, agent-friendly tools that future model evaluations can reuse.

| Work Item | Plan | Notes |
|-----------|------|-------|
| `llm-tester` refactor of `scripts/poc-multi-provider/` | [llm-tester-refactor.md](plans/llm-tester-refactor.md) | Rename to `scripts/llm-tester/`, single `tester.py` dispatcher (`probe`/`trace`/`list`), archive POC artifacts. Stays gitignored. Minimal-change refactor of existing harnesses. |

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

## Style guide page (`/styles`)

Goal: A living style reference page at `/styles` (converted from `public/font-preview.html`) that renders inside the site layout with the full a11y controller, showing all typography, colors, verdict badges, spacing tokens, and component states. Lets designers and contributors verify visual changes in context.

| Work Item | Notes |
|-----------|-------|
| Convert `public/font-preview.html` → `src/pages/styles/index.astro` | Move into site layout, wire up `<A11yControl>`, cover all design tokens and component variants |

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

## Operator workflow and data lifecycle

Goal: Move from one-CLI-call-at-a-time to a queue + batch + error-file flow, and define how reprocessing interacts with existing content. Generated from the 2026-04-24 pre-launch triage; not v1 because manual operation suffices at the v1 launch scale (~20 claims).

| Work Item | Plan | Notes |
|-----------|------|-------|
| Operator queue + batch + error-file workflow | [operator-queue-batch-workflow_stub.md](plans/operator-queue-batch-workflow_stub.md) | v2; aligns operator-facing intake files with the six-input taxonomy |
| Data lifecycle policy (skip-existing, overwrite, partial-fix) | [data-lifecycle-policy_stub.md](plans/data-lifecycle-policy_stub.md) | v2; design pre-launch is cheap. Pairs with audit-trail-extensions.md Phase 3 |
| Source-triggered reassessment | (no plan yet) | v2; add a source, related claims re-evaluate. Operator confirmed v2. |

---

## Canonical verdict artifact (LLM-as-judge framing)

Goal: Treat the combined Analyst + Auditor output as the single trustworthy verdict, rather than the Analyst's draft with the audit sidecar as supporting metadata. Aligns with the evaluator-optimizer / LLM-as-judge pattern, where the *combined* judgment is the unit of trust. Pairs with audit-trail work but is a separate framing shift.

| Work Item | Notes |
|-----------|-------|
| Decide carrier | Either elevate `.audit.yaml` to "verdict record" (rename + reshape) or merge audit fields into claim frontmatter. Operator decision pending; previously deferred in `docs/plans/drafts/v0.1.0-vocab-workflow-landing.md` Out-of-scope. |
| Update canonical paragraphs once carrier decision lands | Generalized + v1 paragraphs in `AGENTS.md` and `docs/architecture/glossary.md` need to reflect the new artifact name and ownership. |
| Schema migration | Whichever carrier wins, `src/content.config.ts` enum/shape needs updating; backfill all existing claims and `.audit.yaml` files. |

Scheduling note: blocked on operator decision; not v0.1.0. Touches audit-trail Stage 2/3 and the data-lifecycle-policy stub.

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

### Claim re-label candidates under sharpened verdict definitions

Plan 2 (`claim-promotion-audit-rename-verdicts`) sharpened the `mostly-true` vs `mixed` split to hinge on "main thrust vs. material element." The following claim surfaced during a spot-check as a potential re-label (currently `mostly-true`, borderline `mixed` under the new framing):

- `research/claims/gemini/discloses-models-used.md` -- FMTI low-score finding and the TechCrunch "very sparse" criticism of the Gemini 2.5 Pro technical report read as material elements about transparency depth, not caveats. A reader taking `mostly-true` as endorsement of Gemini's disclosure would be misled about those elements.

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

---

## Claim detail page — deferred improvements

From UI redesign plan (2026-04-24). Current implementation shows reviewer count in the meta row; reviewer name in expanded research details.

| Work Item | Notes |
|-----------|-------|
| Multi-reviewer tracking | Change `human_review` from single object to array of `{ reviewed_at, reviewer, notes, pr_url }`. Meta row count (`✓ N reviewers`) derives from array length. Requires schema version bump and backfill script. |
| Sign-off count in list views | Once multi-reviewer array exists, surface count in `ClaimRow` and entity detail claim lists as a trust signal. |
| Verdict change history | Append-only `history` array in `.audit.yaml` recording each pipeline run's verdict+confidence output. Site renders a timeline on the claim detail page. Requires pipeline write changes. |

---

## v1 vocab/lifecycle follow-ups (2026-04-26)

Cleanup items surfaced during the v0.1.0 vocab + multi-topic + claim-lifecycle landings (commits `7943577`, `1394bc6`, `df7537e`, `020409f`, `2ec0ed3`). All non-blocking for v0.1.0; nice-to-have polish.

| Work Item | Notes |
|-----------|-------|
| Vocabulary sweep through `pipeline/orchestrator/pipeline.py` | Lingering "Auditor" references in `verify_claim`'s function docstring (line ~145), inline comments (lines ~221, ~551), and a log message (line ~420). The vocab landing PR was scoped to module-level docstrings only; this is the in-function follow-up. |
| Detail-page filter for `status: blocked` | `src/pages/claims/[...slug].astro` still calls `getStaticPaths` over all claims regardless of status. Public list pages already exclude blocked, but direct URLs to blocked claims still resolve. Add a status filter to `getStaticPaths` if operator-only visibility should extend to detail URLs. |
| Multi-topic faceted filtering | `src/components/ClaimRow.astro` and `src/pages/criteria/index.astro` set `data-topic={topics[0]}` because `FilterBar` matches one attribute value per facet. Multi-topic claims/criteria filter only on their first topic. Fix needs richer `FilterBar` matching (split-by-space) or a different markup shape. |
| Delete `research/claims/.gitkeep` after first regen | The bridge file was added in commit `1394bc6` so Astro's `walkMdFiles` doesn't ENOENT before regeneration. Once regenerated claims exist, delete the bridge. |
| Consider `pipeline/auditor/` → `pipeline/evaluator/` directory rename | Doc rename Auditor → Evaluator landed in `7943577`; the Python package keeps its old name for v1. Tracked in `docs/plans/v0.1.0-vocab-workflow-landing.md` as deferred. |
| Sweep stringly-typed `"blocked"` literals to `ClaimStatus.BLOCKED.value` | `pipeline/orchestrator/persistence.py` and `pipeline/orchestrator/cli.py` write/compare raw "blocked" strings. Consistent with existing style; cosmetic enum-everywhere upgrade. |
| Onboarding fallback for empty entity description | `pipeline/orchestrator/pipeline.py` lines 640 + 657 leave `entity_description = ""` when the seed source's `summary` is empty (fail-fast 401/403, unsummarizable body, etc.). The created entity then ships with `description: ''` until an operator hand-edits it. Add a fallback (e.g., synthesize from entity name + type + website, or block onboarding with a clear error). Surfaced 2026-04-26 during v1.0.0 content & disclosure pass; deleted `products/chatgpt.md` was the original symptom. |
| `ClaimFrontmatter` Pydantic model as Python-side source of truth | `pipeline/linter/checks.py::CANONICAL_CLAIM_KEYS` and `pipeline/orchestrator/persistence.py::_write_claim_file`'s frontmatter dict are two parallel definitions of the claim schema. Drift between them caused the 2026-04-27 `unknown-frontmatter-key blocked_reason` lint warning when the writer added `blocked_reason` but the linter set wasn't updated. Define a `ClaimFrontmatter` Pydantic model in `pipeline/common/models.py` (mirroring the existing `SourceFrontmatter`), derive `CANONICAL_CLAIM_KEYS = set(ClaimFrontmatter.model_fields.keys())`, optionally validate `_write_claim_file` output against it. Note: `src/content.config.ts` remains the *real* source of truth (Astro consumes it at build); this only collapses the Python-internal duplication. ~1-2 hours. |
| Backfill `criteria_slug` on 7 published claims (lint blocker) | The new `published-without-criterion` lint check (2026-04-27) errors on these 7 published claims that lack `criteria_slug`: `research/claims/claude/{no-training-on-user-data,realtime-energy-display,renewable-energy-hosting}.md`, `research/claims/gemini/{excludes-image-generation,no-training-on-user-data,realtime-energy-display,renewable-energy-hosting}.md`. CI is red until each gets a slug from `research/templates.yaml` (or is reverted to `status: draft`). |
