# Unscheduled Work

Work known but not yet assigned to a release. Items here are candidates for the next release or future releases.

Items here can be planned but not coded. Before code starts, the `release-triage` skill moves an item into a release roadmap and removes it from this file (`AGENTS.md` § Release planning). An item held for a specific future release carries a `Target: vX.Y.Z` note.

**Triage marker.** A triaged item ends with `Triage: <theme>; <next>; YYYY-MM-DD`, at the end of its last table cell or bullet (never put `|` in it). Add one whenever you add an item. An item without one is untriaged. The process is in the `release-triage` skill, § Backlog triage.

- **theme**: the [`priorities.md`](priorities.md) theme it serves, by its bold name up to the first comma or period (`Responsible AI chatbots`, `Security`), or `none`.
- **next**: `keep` (stays here); `in <ID>` (detail for a checklist line of that roadmap item, which links here); or a proposal waiting for Brandon: `propose schedule`, `propose defer`, `propose drop`. His "no" is written `keep (Brandon)`.

"Deferred plans" rows carry no marker.

---

## Pipeline performance & hardening

Goal: Reduce onboarding wall time and wasted API calls.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Onboard: skip light research when the entity file exists | (none) | `dr onboard` runs light research, verifier and enricher on every call (`pipeline/orchestrator/pipeline.py`, `onboard_entity` Phase A) even for an existing entity; `dr entity-enrich` and `dr onboard --force` already cover the explicit refresh case. |
| Ingest: retry Infomaniak null-body responses | (none) | The Infomaniak gateway occasionally returns 200 OK with a null body; PydanticAI raises `UnexpectedModelBehavior` (log: `Failed to ingest <url>: Invalid response from openai chat completions endpoint: 4 validation errors for ChatCompletion`). Non-fatal: that URL gets a `StepError(error_type="model_error")` and the run continues. `_run_with_null_retry` (`pipeline/orchestrator/pipeline.py`) already covers the analyst and auditor; `_ingest_one` still calls `ingestor_agent.run` directly. Fix: let `_run_with_null_retry` take `deps` and reset the `IngestorDeps` buffers (`acquisition_writes`, `wayback_failures`) between attempts. |

The other four items in this group shipped and moved to `plans/completed/`: onboard-reuse-verify-sources, ingestor-fail-fast-403, researcher-host-blocklist, ingestor-tighten-timeouts.

---

## Pipeline observability

Goal: Make per-object model spend visible so we can see which claims, sources, and entities are consuming the most tokens, and what the daily/weekly burn looks like.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Token usage log + `inv tokens.summary` | [token-usage-log.md](plans/deferred/token-usage-log.md) | Append-only JSONL at `logs/token-log.jsonl` written by a thin wrapper around every `agent.run(...)`; `inv tokens.summary --by object\|time` reader; no DB, no UI Deferred 2026-10-06 (no reader-facing use yet). |

---

## Analyst decomposition (cost lever)

Goal: Split the Analyst's frontier-model call into smaller sub-decisions so cheaper models can handle the parts that don't need full reasoning. Aligns with the "small decisions, small models" principle in `AGENTS.md`.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Full 4-step decomposition (entity resolver, per-source stance, verdict synthesizer, narrative+title writer) | `analyst-decomposition_stub.md` (local draft) | Stub draft; needs token-usage baseline before committing. Keeps verdict+confidence on frontier; pushes the rest to Haiku-class. Biggest win is feeding frontier structured stances instead of raw source bodies (~10x smaller prompt). Source-trust Phase 2 (COI/independence weighting in analyst reasoning) is a forcing function: adding conditional source weighting further complicates analyst instructions and makes decomposition more urgent. |
| Narrative + title writer extraction (smallest slice) | (to be drafted from the stub) | Once verdict is fixed, this is structured writing with a mechanical title-polarity rule. Most defensibly Haiku-class sub-decision; could be promoted out of the broader plan as a single-step extraction. |

---

## Dedup detection on URL ingest and claim creation

Goal: Stop one source from being stored, and counted, twice. URL-level dedup shipped: canonical-URL matching and reuse of existing source files ([source-url-dedup_completed.md](plans/completed/source-url-dedup_completed.md), `pipeline/common/canonical_url.py`, `_apply_url_dedup`, `904c376`). What remains matters to the Responsible AI chatbots effort (roadmap item SITE-J): the same paper or page counted as two independent sources inflates `verification_level`.

| Work Item | Plan | Notes |
|-----------|------|-------|
| arXiv abs/html/pdf as one source | (no plan) | See "Canonicalize arXiv URLs at ingest" below; no arXiv rule in `canonical_url.py` yet. SITE-J (Responsible AI chatbots) prerequisite. Triage: Responsible AI chatbots; in SITE-J; 2026-10-07 |
| Stored redirect target (RF23 remainder) | (no plan) | An existing file that stored a redirect target is treated as a different page, so a duplicate is written. See RF23 below. SITE-J (Responsible AI chatbots) prerequisite. Triage: Responsible AI chatbots; in SITE-J; 2026-10-07 |
| Claim-level match on onboard | (no plan) | Before running a template, look up an existing claim by `(entity, criteria_slug)` and skip analyst + auditor on a hit. Operator time only; low priority. The design sketch was the local draft `pipeline-dedup-detection_stub.md`, now archived. |

Related (2026-10-04): URL dedup missed a different URL that landed on an existing slug, and the pipeline then cited the existing, unrelated file (RF1, fixed by [claim-refresh-integrity-fixes.md](plans/completed/claim-refresh-integrity-fixes.md)).

---

## arXiv ingest hardening (2026-05-10)

Goal: Stop the two arXiv-specific failure modes surfaced while auditing recent dr runs. Both leaked bad metadata into a then-published verdict; the motivating claim file (`research/claims/gemini/discloses-energy-sourcing.md`, whose cap_rationale described Google's own preprint as an "independent expert assessment") was removed in the 2026-05-11 launch-set prune, but the pipeline gaps remain.

| Work Item | Notes |
|-----------|-------|
| Canonicalize arXiv URLs at ingest | Treat `arxiv.org/abs/{id}`, `arxiv.org/html/{id}v{n}`, and `arxiv.org/pdf/{id}` as one source. Today both `arxiv:2508.15734` and `arxiv:2502.18505` exist as two separate source files (e.g., `2025/250815734.md` from `abs/` and `2025/250815734v1.md` from `html/v1`) with conflicting frontmatter. The `chatgpt/excludes-frontier-models` audit cites both variants of 2502.18505 as if they were independent evidence. Add it as one rule in `pipeline/common/canonical_url.py` (see Dedup detection above). SITE-J (Responsible AI chatbots) prerequisite. Triage: Responsible AI chatbots; in SITE-J; 2026-10-07 |
| Detect corporate authorship on arXiv abstracts | When an arXiv abstract names a corporate AI lab (Google/DeepMind, Anthropic, OpenAI, Meta, Microsoft Research, etc.) as an author affiliation, force `independence: first-party` and `source_type: primary` against that entity in the ingestor's frontmatter pass. Today the `abs/` ingestion of `2508.15734` (Google's own Gemini environmental-impact paper) was written as `publisher: arXiv / independence: independent / source_type: secondary`; the `html/v1` ingestion of the same paper was correctly written as `publisher: Google / independence: first-party / source_type: primary`. The wrongly-labeled variant is what flowed through to the published Gemini verdict. |

---

## PDF attachment as alternate source content surface

Goal: Let a locally-attached PDF stand in for an unreachable URL (401/402/403/451 origins) as a content surface for both the ingestion agent and the human reviewer. Pairs with the fail-fast plan — when the ingestor can't fetch, a pre-attached PDF is the fallback.

| Work Item | Plan | Notes |
|-----------|------|-------|
| PDF attachment core (ingestion + model) | [source-pdf-attachment.md](plans/deferred/source-pdf-attachment.md) | `pdfs:` frontmatter block, `_attachments.yaml` manifest, `pdf_read` tool, `dr attach-pdf` CLI, sha256 integrity lint |
| PDF attachment publish surface | [source-quality-followups.md § PDF publish surface](plans/deferred/source-quality-followups.md#pdf-publish-surface-drafted-post-attachment) | Site renders `republish: true` PDFs with download link; `_headers` `noindex`; depends on core landing |

---

## AI Research Audit Trail

Goal: On each `/claims/[slug]` page, show a collapsible section with which agent ran the research, what sources were consulted, when a human reviewed it, and whether the verdict changed from draft. Builds reader trust by making the AI+human process visible.

Architecture: sidecar `.audit.yaml` file per claim, written by the pipeline after the auditor runs, consumed by a custom Astro loader. Full 3-stage architectural review completed.

| Work Item | Plan | Notes |
|-----------|------|-------|
| ~~Sidecar format + pipeline write + Astro loader + UI (Stage 1)~~ | [audit-trail.md](plans/completed/audit-trail.md) | **Done** (2026-04-25, moved to `completed/`). `_write_audit_sidecar` in persistence.py; `dr review --claim` CLI; collapsible UI; 11 sidecars committed. |
| ~~Reader-facing slice: refresh trail, evaluator reasoning, verdict/sidecar lint~~ | [published-claim-refresh-trail.md](plans/published-claim-refresh-trail.md) | **Scheduled** in the roadmap, SITE-J (Responsible AI chatbots) (RF8, RF9) |
| ~~Extended fields, backfill, orphan CI (Stage 2); append-only history (Stage 3)~~ | [audit-trail-extensions.md](plans/deferred/audit-trail-extensions.md) | **Deferred** 2026-10-06; see Deferred plans |


---

## Security follow-ups

Deferred when the high and critical fixes landed in `3f69aed`.

| Work Item | Notes |
|-----------|-------|
| `astro` AVIF advisory and `sharp` (libvips) advisory | The fix needs the Astro 7 major upgrade. The site does not use Astro's image optimizer. Triage: Security; keep; 2026-10-07 |
| `markdownlint-cli2` (bundled `js-yaml` advisory) | The fix is a breaking major bump of a dev-only lint tool. Triage: Security; keep; 2026-10-07 |
| Medium-severity Python advisories | `pydantic-ai` / `pydantic-ai-slim`, `idna`, `pydantic-settings`. The 2026-10-02 pass applied high and critical fixes only. Triage: Security; keep; 2026-10-07 |

---

## Release gate follow-ups

Gaps in OPS-L (Release gate) from `docs/v1.0.0-roadmap.md`.

| Work Item | Notes |
|-----------|-------|
| One work item per checkout, shared by every session | `.claude/active-work.json` is one file per checkout, so parallel sessions in the same checkout share whatever item is registered: one session's registration lets another edit code. Options: key the record by session, or require a worktree per session. |

---

## Ops Runbook

Goal: One reference doc covering the dev loop, pipeline operations, deploy process, and content schema changes. `docs/runbook.md` exists (2026-05-04) and covers the dev loop; the rest is unwritten (its own TODO lists the same sections).

| Work Item | Notes |
|-----------|-------|
| Production CMS login | Register a GitHub OAuth app, deploy [sveltia-cms-auth](https://github.com/sveltia/sveltia-cms-auth) on Cloudflare Workers with its credentials, and set `backend.base_url` in `public/admin/config.yml` (commented out today) to the Worker URL. Local-repository mode works meanwhile. |
| Expand runbook.md | `dr` CLI reference, deploy steps, schema change checklist; also document the newer `inv audit`, `inv audit.prune`, `inv check` tasks |
| Expand source `kind` enum | Add `statement` (social posts, press releases, direct submissions) and `filing` (company invoices, certificates, contracts). Schema change touches `content.config.ts`, pipeline `SourceFrontmatter`, and `_classify_source_type`. |

---

## Automation (conditional)

Goal: Recurring audits, queue-based intake. Trigger: enough content exists that manual auditing is burdensome.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Scheduled citation audits | [source-quality-followups.md § Scheduled citation audits](plans/deferred/source-quality-followups.md#scheduled-citation-audits-drafted) | Scheduled workflows, QUEUE.md intake |

Downstream sync to parallax-ai: dropped 2026-10-06 (it ties the research repo to another codebase, and research may move to its own repo). The local draft is archived in `plans/drafts/archive/downstream-sync.md`.

---

## Deferred plans (2026-10-06)

Plans set aside because their remaining work does not serve the site's current focus (AGENTS.md, Plans & Backlog rule 8). Each file in `plans/deferred/` opens with the reason. Revive one by moving it back to `plans/` and scheduling it.

| Plan | Reason | Shipped already |
|---|---|---|
| [`public-feedback.md`](plans/deferred/public-feedback.md) | Pre-refocus `/feedback` form, admin CLI and GitHub promotion; the mailto path in roadmap RE-D (Research contribution paths) covers the reader need. Revisit if that inbox outgrows email | Its Worker, D1 and Resend stack shipped for petitions (`workers/api/`) |
| [`public-participation-forms.md`](plans/deferred/public-participation-forms.md) | Claim challenge, claim request and propose-a-criterion forms serve the archive's intake; depends on the feedback queue | nothing |
| External reviewer identity, roadmap RE-F (Human sign-off). No plan; local research in `plans/drafts/human-signoff-identity-research.md` | ORCID OAuth, IndieAuth, Mastodon/Bluesky for co-signing claims assume more than one reviewer. Revisit only if a decision adds reviewers beyond Brandon | nothing |
| [`sec-edgar-path3_stub.md`](plans/deferred/sec-edgar-path3_stub.md) | Investor filings serve partnership and investment claims, not the Responsible AI chatbots claims; no entity carries `sec_cik` | Prerequisites only (schema, throttle, enum slots: `a40a09f`, `9a26ba8`, `0e5b1ff`, `98d094c`) |
| [`wayback-archive-job.md`](plans/deferred/wayback-archive-job.md) | Operator throughput; the reader-facing gap is RF11, a prerequisite of roadmap SITE-J (Responsible AI chatbots) | In-pipeline lookup on (`6409918`), TimeGate recovery (`a8e5dd5`) |
| [`source-quality-followups.md`](plans/deferred/source-quality-followups.md) | Backlog of pipeline source-quality ideas (Tier 2 and 3, trust schema, PDF publish, citation audits) | Its on-focus items have their own rows in this file |
| [`source-pdf-attachment.md`](plans/deferred/source-pdf-attachment.md) | Operator ingest path; would commit PDFs into `research/` | nothing |
| [`parent-company-inference.md`](plans/deferred/parent-company-inference.md) | Operator convenience during onboarding | nothing |
| [`research-outputs-improvement-plan.md`](plans/deferred/research-outputs-improvement-plan.md) | Standards and operator-side work; its two on-focus items are in "Site gaps and deferred content", Opportunities | Inline ClaimReview (`1b9f3b7`), `verification_level` field |
| [`token-usage-log.md`](plans/deferred/token-usage-log.md) | Operator spend tracking, no reader use yet | nothing |
| [`audit-trail-extensions.md`](plans/deferred/audit-trail-extensions.md) | Sidecar infrastructure (backfill, orphan CI, v3 transition log, ClaimReview fields); its reader-facing slice moved to [`published-claim-refresh-trail.md`](plans/published-claim-refresh-trail.md) | Nothing from its checklist; its open question 2 (`reviewed_at` gate in CI) is done via `published-without-review` (`3ebc094`) |
| [`onboard-parallelize-templates.md`](plans/deferred/onboard-parallelize-templates.md) | Operator wall time only | nothing |
| [`acceptance-test-fixture_stub.md`](plans/deferred/acceptance-test-fixture_stub.md) | Test scaffolding as written; revive by retargeting it to a Responsible AI chatbots claim (verdict drift, RF6) | Related: `pipeline/tests/test_acceptance.py` (`72dcae8`), skipped without an Anthropic key |
| [`criterion-resolution-workflow_stub.md`](plans/deferred/criterion-resolution-workflow_stub.md) | `c` action in `dr review-queue` is operator ergonomics; template claims carry `criteria_slug` | Vocabulary-unresolvable claims are blocked (`26bd518`) |
| [`data-lifecycle-policy_stub.md`](plans/deferred/data-lifecycle-policy_stub.md) | Draft-time reprocessing policy; the published-claim case moved to the refresh-trail plan | nothing |
| [`model-tier-enforcement_stub.md`](plans/deferred/model-tier-enforcement_stub.md) | Cost discipline; revisit with `token-usage-log.md` | nothing |
| [`operator-queue-batch-workflow_stub.md`](plans/deferred/operator-queue-batch-workflow_stub.md) | Batch tooling; absorbs dr-lint Phase 3 (`ONBOARD_QUEUE.md` loop) and dr-review-queue Phase 3 (queue types) | nothing |
| dr-lint Phase 4: scheduled agent triage ([`dr-lint.md`](plans/completed/dr-lint.md)) | Scheduled agents opening fix PRs; pairs with the deferred background-job work | Phases 1-2 (`pipeline/linter/`, CI `lint-content` job) |
| dr-review-queue Phase 2 remainder: reject note, back, filters ([`dr-review-queue.md`](plans/completed/dr-review-queue.md)) | Operator polish | Phase 1 (`f64adc3`, `3abd112`) and the `e` action |

---

## Router (full implementation, post-v1)

Goal: Implement the Router role as a real dispatcher (small classifications; matching incoming sources to criteria/claims). The v1 surface shipped via [triage-agent.md](plans/completed/triage-agent.md); the full Router was explicitly deferred post-v1. AGENTS.md § Agent Roles points here for tracking.

| Work Item | Notes |
|-----------|-------|
| Full Router per the deferred scope in [triage-agent.md](plans/completed/triage-agent.md) | Needs a fresh plan (or a drafts/ stub) before scheduling; `pipeline/router/` does not exist yet |

---

## Responsible-ai matrix polish

Carry-forward items from [responsible-ai-overhaul.md](plans/completed/responsible-ai-overhaul.md) (all milestones shipped 2026-05; these were out of M8 scope).

| Work Item | Notes |
|-----------|-------|
| Ideal column tint in light theme | `--color-surface` is too close to `--color-bg` in light theme; needs a `--color-surface-subtle` (or similar) token. Deferred by the no-new-tokens constraint |
| Filter chip `aria-pressed` semantics | Filled accent chip currently means "this product is hidden", not "selected"; flip the model to "visible by default, clicking removes" or rename the toggle |

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

- **Configure custom domain in GitHub Pages UI** -- appears resolved: the site serves at `dangerousrobot.org` (Cloudflare redirects live and GSC baseline captured 2026-05-11). Confirm the Pages setting once, then delete this item.

### Deferred content (unsourced)

- **Structure chatbot comparison table** -- Comparison data exists in `parallax-ai/frontend/src/lib/comparison-data.ts` (transparency + feature comparisons across 5 competitors). Treat as unsourced claims; need source files backing each cell before publishing.
- **Structure AI Product Card data** -- Transparency/nutrition-label data exists in `parallax-ai/frontend/src/app/transparency/page.tsx` (models, energy, ethics, commitments). Treat as unsourced claims; need source files for each assertion.

### Site gaps

- ~~**`parent_company` not rendered**~~ -- Rendered as of [`plans/completed/entity-metadata-surface_completed.md`](plans/completed/entity-metadata-surface_completed.md) (2026-05-09). All five product entity pages and any claim whose subject is a product render "Made by [Parent]" linking back to the company entity page. Inference automation for `parent_company` itself remains in `plans/parent-company-inference.md` (post-v1).
- **Entity reference validation** -- Claims reference entities by path string with no build-time validation. Use Astro's `reference('entities')` helper or add entity-ref checking to `scripts/check-citations.ts`.
- **Source reference upgrade** -- Replace `z.array(z.string())` with `z.array(z.string().min(1)).min(1)` for claims `sources` field. Current schema permits empty arrays.
- **`recheck_cadence_days` constraint** -- Schema accepts 0/negative values. Add `.int().min(1)` to the Zod definition.
- **GitHub Actions SHA pinning** -- All actions use mutable tags (`@v4`). Pin by full SHA for supply chain security.
- **SEO basics** -- ~~No favicon, robots.txt, canonical URLs, Open Graph tags. `description` prop in Base.astro is never customized per page.~~ Done (2026-04-29): robots.txt, sitemap, canonical, OG tags, per-page descriptions, Organization/ClaimReview/FAQPage/BreadcrumbList/WebSite JSON-LD. Remaining: (1) `og:image` asset: see SEO post-restructure follow-ups, "OG image at 1200×630". (2) `SearchAction` wiring -- the WebSite JSON-LD declares a `SearchAction` at `/claims?q={search_term_string}` but `FilterBar.astro` doesn't read `?q=` from the URL on load; a small JS change is needed to make the schema functional.
- **Research hub wording after the About rewrite (2026-10-04)** -- beta.4 H2 rewrote only the first FAQ answer and the Limits line. The methodology steps, "Rechecks", the FAQ JSON-LD summary and the conflicts answer still say "an operator" / "the operator"; `src/pages/research/index.astro:121` still says the site "tracks claims about AI companies and products" though subject claims exist.
- **`ai-model-producers` index mismatch (2026-10-04)** -- the entity names the seven companies FLI graded in its Summer 2025 index; `/resources/ai-safety` covers the Winter 2025 index (eight, adding Alibaba Cloud, with Zhipu shown as Z.ai). Pick one index for the subject definition.
- **Sub-question coverage in claim bodies (2026-10-04)** -- the analyst can write a "Sub-question coverage" block with internal ids (`sq1` to `sq3`) into published bodies; one was removed by hand from `ai-producers-existential-score`. Stop it in the analyst prompt or cleaner, and consider a `dr lint` rule.

### Opportunities

- **Validation gaps** -- CI validates schema structure and citation integrity but not reasoning quality. Potential additions: confidence-to-verdict alignment, staleness detection, source URL liveness checks, archived URL population nudges, a check framework (Vitest) for scripted validators.
- **Confidence rubric** -- Define what `high`/`medium`/`low` confidence concretely means, in one place: extend the "Confidence levels" section of the methodology page (`src/pages/research/index.astro`). Use an LLM to check each claim against the rubric. Also proposed in [`research-outputs-improvement-plan.md`](plans/deferred/research-outputs-improvement-plan.md) (move 2).
- **ClaimReview validity check** -- claim pages already emit inline ClaimReview JSON-LD (`src/pages/research/claims/[...slug].astro`). Add a build or lint check that every published claim emits a valid ClaimReview (verdict maps to a rating, date and reviewer present). Matters once claim pages are indexed for the Responsible AI chatbots effort (roadmap item SITE-J). From [`research-outputs-improvement-plan.md`](plans/deferred/research-outputs-improvement-plan.md) (move 3). Triage: Responsible AI chatbots; propose schedule; 2026-10-07
- **Claim Updater instruction quality** -- Consider adversarial review, inter-rater consistency validation, and forbidden-combination gates (CI rejection of nonsensical confidence-verdict pairs).
- **Source freshness** -- confirm the ingestor reliably populates the optional `published_date` source field (`src/content.config.ts`); wire it if not. (Folded in from a scratch note, 2026-07-03.)
- **Least invasive anonymous analytics (2026-10-06)** -- consider adding page-view counts from the least invasive anonymous option available (no cookies, no personal data, no cross-site tracking). Today the site has none. Two promises would need updating: `src/pages/privacy.astro` ("Reading the site") says the site runs no analytics or tracking scripts, and `src/layouts/Base.astro:2` keeps pages free of third-party requests. A self-hosted or server-side counter keeps the second promise; a hosted script breaks it.

---

## Operator workflow and data lifecycle

Goal: Move from one-CLI-call-at-a-time to a queue + batch + error-file flow, and define how reprocessing interacts with existing content. Generated from the 2026-04-24 pre-launch triage; not v1 because manual operation suffices at the v1 launch scale (~20 claims).

| Work Item | Plan | Notes |
|-----------|------|-------|
| Source-triggered reassessment | (no plan yet) | v2; add a source, related claims re-evaluate. Operator confirmed v2. |

---

## Canonical verdict artifact (LLM-as-judge framing)

Goal: Treat the combined Analyst + Auditor output as the single trustworthy verdict, rather than the Analyst's draft with the audit sidecar as supporting metadata. Aligns with the evaluator-optimizer / LLM-as-judge pattern, where the *combined* judgment is the unit of trust. Pairs with audit-trail work but is a separate framing shift.

| Work Item | Notes |
|-----------|-------|
| Decide carrier | Either elevate `.audit.yaml` to "verdict record" (rename + reshape) or merge audit fields into claim frontmatter. Operator decision pending; previously deferred in `docs/plans/completed/v0.1.0-vocab-workflow-landing.md` Out-of-scope. |
| Update canonical paragraphs once carrier decision lands | Generalized + v1 paragraphs in `AGENTS.md` and `docs/architecture/glossary.md` need to reflect the new artifact name and ownership. |
| Schema migration | Whichever carrier wins, `src/content.config.ts` enum/shape needs updating; backfill all existing claims and `.audit.yaml` files. |

Scheduling note: blocked on operator decision; not v0.1.0. Touches the deferred audit-trail-extensions.md (Stage 2/3) and data-lifecycle-policy_stub.md (both in plans/deferred/).

---

## Source type classification — edge cases to revisit

Carried from the retired 2026-04-22 follow-up doc. Everything else in that doc shipped, was folded into the research-page accordion, or referenced content removed in the 2026-05-11 launch-set prune.

- **SEC EDGAR filings** -- classified as `primary`; verify this is correct when [SEC EDGAR as a research origin](plans/deferred/sec-edgar-path3_stub.md) is picked up (its filer-vs-subject rule covers this).
- **B Lab / B Corp profiles** -- classified as `secondary`; confirm.
- **UNESCO, NTIA, UNFCCC** -- classified as `secondary`; confirm.
- **IBM, Deloitte reports** -- classified as `secondary`; some may lean tertiary. Spot-check.
- **Entity's own pages** -- the classifier ignores the claim's entity, so brave.com pages on a Brave claim come out `secondary`, hence `independent` (RF3 in [claim-refresh review findings](#claim-refresh-review-findings-2026-10-04)).

---

## Claim detail page — deferred improvements

From UI redesign plan (2026-04-24). Current implementation shows reviewer count in the meta row; reviewer name in expanded research details.

| Work Item | Notes |
|-----------|-------|
| Multi-reviewer tracking | Change `human_review` from single object to array of `{ reviewed_at, reviewer, notes, pr_url }`. Meta row count (`✓ N reviewers`) derives from array length. Requires schema version bump and backfill script. |
| Sign-off count in list views | Once multi-reviewer array exists, surface count in `ClaimRow` and entity detail claim lists as a trust signal. |
| Verdict change history | Append-only `history` array in `.audit.yaml` recording each pipeline run's verdict+confidence output. Site renders a timeline on the claim detail page. Requires pipeline write changes. |
| Show-your-work reasoning panel (was Q11) | Reasoning-transparency scope carried over from the retired `pre-launch-questions.md`; partially implemented, treated as in flight. Open sub-decisions: inline analyst narrative on every claim vs. expand-on-click; auditor disagreement excerpts always visible vs. only when the verdict was contested; whether to expose the actual instruction text the analyst saw. |

Related (2026-10-04): `dr claim-refresh` on a published claim changed its verdict with no history or corrections entry (RF8 in [claim-refresh review findings](#claim-refresh-review-findings-2026-10-04)).

---

## v1 vocab/lifecycle follow-ups (2026-04-26)

Cleanup items surfaced during the v0.1.0 vocab + multi-topic + claim-lifecycle landings (commits `7943577`, `1394bc6`, `df7537e`, `020409f`, `2ec0ed3`). All non-blocking for v0.1.0; nice-to-have polish.

| Work Item | Notes |
|-----------|-------|
| Vocabulary sweep through `pipeline/orchestrator/pipeline.py` | Lingering "Auditor" references in `verify_claim`'s function docstring (line ~145), inline comments (lines ~221, ~551), and a log message (line ~420). The vocab landing PR was scoped to module-level docstrings only; this is the in-function follow-up. |
| Detail-page filter for `status: blocked` | `src/pages/research/claims/[...slug].astro` calls `getStaticPaths` over all claims regardless of status (path updated post-restructure; re-verify the behavior). Public list pages already exclude blocked, but direct URLs to blocked claims still resolve. Add a status filter to `getStaticPaths` if operator-only visibility should extend to detail URLs. |
| Multi-topic faceted filtering | `src/components/ClaimRow.astro` and `src/pages/criteria/index.astro` set `data-topic={topics[0]}` because `FilterBar` matches one attribute value per facet. Multi-topic claims/criteria filter only on their first topic. Fix needs richer `FilterBar` matching (split-by-space) or a different markup shape. |
| Delete `research/claims/.gitkeep` after first regen | The bridge file was added in commit `1394bc6` so Astro's `walkMdFiles` doesn't ENOENT before regeneration. Once regenerated claims exist, delete the bridge. |
| Consider `pipeline/auditor/` → `pipeline/evaluator/` directory rename | Doc rename Auditor → Evaluator landed in `7943577`; the Python package keeps its old name for v1. Tracked in `docs/plans/completed/v0.1.0-vocab-workflow-landing.md` as deferred. |
| Sweep stringly-typed `"blocked"` literals to `ClaimStatus.BLOCKED.value` | `pipeline/orchestrator/persistence.py` and `pipeline/orchestrator/cli.py` write/compare raw "blocked" strings. Consistent with existing style; cosmetic enum-everywhere upgrade. |
| Onboarding fallback for empty entity description | `pipeline/orchestrator/pipeline.py` lines 640 + 657 leave `entity_description = ""` when the seed source's `summary` is empty (fail-fast 401/403, unsummarizable body, etc.). The created entity then ships with `description: ''` until an operator hand-edits it. Add a fallback (e.g., synthesize from entity name + type + website, or block onboarding with a clear error). Surfaced 2026-04-26 during v1.0.0 content & disclosure pass; deleted `products/chatgpt.md` was the original symptom. |
| `ClaimFrontmatter` Pydantic model as Python-side source of truth | `pipeline/linter/checks.py::CANONICAL_CLAIM_KEYS` and `pipeline/orchestrator/persistence.py::_write_claim_file`'s frontmatter dict are two parallel definitions of the claim schema. Drift between them caused the 2026-04-27 `unknown-frontmatter-key blocked_reason` lint warning when the writer added `blocked_reason` but the linter set wasn't updated. Define a `ClaimFrontmatter` Pydantic model in `pipeline/common/models.py` (mirroring the existing `SourceFrontmatter`), derive `CANONICAL_CLAIM_KEYS = set(ClaimFrontmatter.model_fields.keys())`, optionally validate `_write_claim_file` output against it. Note: `src/content.config.ts` remains the *real* source of truth (Astro consumes it at build); this only collapses the Python-internal duplication. ~1-2 hours. |
| Wire `show_progress` into `research_claim()` | `pipeline/orchestrator/pipeline.py::research_claim` (lines ~712-905) has the same 4-step structure as `verify_claim` but is not wired to the `show_progress` flag added in `0477ef6` (2026-05-06). No CLI command currently invokes `research_claim` directly; if one is added, mirror the `progress()` plumbing or it will look hung from the first moment. |

---

## Pipeline code-quality refactors (2026-05-08)

Surfaced during the post-tier1 simplify pass (commit `ce045ce`). Both are pre-existing; neither is blocking.

| Work Item | Notes |
|-----------|-------|
| `_write_audit_sidecar` decomposition | `pipeline/orchestrator/persistence.py:356-474` is a 118-line function with 10 parameters (`claim_path`, `comparison`, `model`, `ran_at`, `sources_consulted`, `agents_run`, `models_used`, `research_trace`, `sub_questions_block`, `reset_review`) doing six things: human_review preservation, models_used resolution, acquisition grafting, sub_questions block insertion, sidecar dict assembly, write. Wrap inputs in a `SidecarInputs` dataclass and extract `_resolve_human_review` / `_resolve_models_used` helpers; the orchestration body should be ~20 lines. |
| `verify_claim` ↔ `research_claim` deduplication | `pipeline/orchestrator/pipeline.py:288-356` (verify) and `838-888` (research) share ~70 lines of near-identical Step 1 (research) + Step 2 (ingest+dedup+address-attach+coverage) logic, diverging only in `progress()`/`say()` plumbing. The new `research_origins` field will multiply the divergence as tier1 paths land. Extract a shared `_run_research_and_ingest(client, cfg, sem, ...) -> (urls, urls_failed, all_errors, sub_question_coverage, cached_sources, source_files)` callable from both entry points. |

---

## Pipeline markdown emitter bugs (2026-05-08)

Two markdownlint failures surfaced during a research-content WIP commit on 2026-05-08. Both originate from generated claim narratives, not hand-edited content. The two offending files were deleted to land the commit; regeneration after the fix should produce passing markdown.

| Work Item | Notes |
|-----------|-------|
| Empty-link references in claim narrative (MD042) | Narrative writer emits `[2026/claude](#)` and similar `(#)` placeholder links inline (4 occurrences in the deleted `research/claims/claude/excludes-image-generation.md`). Fix: emit plain-text source IDs (e.g., `[2026/claude]`) without the `(#)` href, or wire real internal links to the source pages. Suspect site of emission: the analyst/narrative writer prompt or a post-processing step that converts `[id]` references to links and falls back to `(#)` when no URL is resolved. |
| Lists missing surrounding blank lines (MD032) | Narrative writer emits a bullet list (`- Source 4 …`) immediately after a paragraph with no blank line between (1 occurrence in the deleted `research/claims/claude/realtime-energy-display.md` line 31). Fix: ensure the renderer inserts a blank line before any bulleted list. Likely a join/concat step in the narrative writer or a Markdown formatter post-step. |

Related (2026-10-04): raw `【id】` citation tokens and "Source N" references are a newer narrative-format bug, tracked as RF4 in [claim-refresh review findings](#claim-refresh-review-findings-2026-10-04). A stray `---` in an ingested source body renders as a heading (RF19).

---

## claim-refresh review findings (2026-10-04)

Goal: fix the pipeline bugs that let one `dr claim-refresh` cite the wrong file, keep a failed fetch as evidence, and label a claim "Independently verified" without any independent source.

Run: `dr claim-refresh brave-browser/renewable-energy-hosting`, run_id `e1cbe5ebd5634cb195b527ea590230f3`. Models: researcher and ingestor on Infomaniak Ministral-3-14B, analyst and auditor on GreenPT gpt-oss-120b. Status: reproduced = re-run or re-executed here with the result shown; isolated = cause pinned in code and run log, not re-executed. Paths are under `pipeline/` unless noted.

| ID | Sev | Issue | Status | Likely cause | Repro | Related |
|----|-----|-------|--------|--------------|-------|---------|
| RF1 | Critical | Source id collision. `aws.amazon.com/sustainability` got slug `sustainability`; an existing `2026/sustainability.md` (Microsoft datacenter page) blocked the write, but the id was still returned and cited. Claim body, sidecar ("AWS Sustainability") and file on disk (Microsoft) disagree; the claim page links the AWS title to the Microsoft page. Same-run duplicates (`aws.amazon.com/energy-utilities/sustainability` also slugs to `sustainability`) collapse silently. The "net-zero by 2040" text the claim cites was in the AWS key quotes the analyst saw, so it is lost only because of this collision. | Reproduced | `orchestrator/persistence.py:157-163` logs `FileExistsError` at INFO and still appends the id, no url comparison. Slug is the last URL path segment (`common/utils.py:17-27`, forced at `orchestrator/pipeline.py:691-693`). `orchestrator/cli.py:1087` `dict.fromkeys` merges same-run duplicate ids. `scripts/check-citations.ts` only checks the file exists. | Temp-dir call to `_write_source_files`: existing Microsoft file plus two AWS urls returns `['2026/sustainability', '2026/sustainability']`, disk url stays Microsoft. | [Improve source slug generation](#improve-source-slug-generation), [Dedup detection](#dedup-detection-on-url-ingest-and-claim-creation), [claim-refresh-integrity-fixes.md](plans/completed/claim-refresh-integrity-fixes.md) |
| RF2 | Critical | A failed fetch became a cited source. `builder.aws.amazon.com/...` failed DNS (Errno 8); the ingest model replied "this source is marked as skipped" plus garbled text, then still returned a SourceFile with an invented summary, `independence: independent`. Logged as `Ingested:`, written, cited, counted as fetched. | Isolated | `ingestor/agent.py:113-115` turns `httpx.HTTPError` into an error dict instead of raising; only 401/402/403/404/451/429 raise `TerminalFetchError`. `output_type=SourceFile` (`ingestor/agent.py:50`) gives the model no abort output. `_ingest_one` (`orchestrator/pipeline.py:684-694`) accepts any output; no fetch-success or `validate_source_file` check. | Run log: ERROR `Failed to fetch` (line 90), model "skipped" text (93), `Ingested:` (96). Host still fails DNS here while `aws.amazon.com` resolves. | `ingestor-decomposition_stub.md` (local draft), [claim-refresh-integrity-fixes.md](plans/completed/claim-refresh-integrity-fixes.md) |
| RF3 | High | Wrong independence labels raised `verification_level` to `independently-verified` while the narrative says no third party links Brave to renewables. brave.com transparency report and the failed builder.aws file got `independent` from the fallback classifier; the Brave forum thread got it from the ingest model. `cap_rationale` dropped as a result. | Reproduced | Main path: `common/source_classification.py:66-93` has no notion of the claim's entity; "Brave Software"/"AWS" with kind report/article/index fall to `secondary`, mapped to `independent` (`orchestrator/persistence.py:153`). Second path: the ingest model fills `independence` freely (only 1 of 8 outputs set it). Analyst applies `analyst/instructions.md:159-171` correctly to bad labels. | `classify_source_type('Brave Software','report')` and `('AWS','index')` both return `secondary`. Analyst replay with refresh-path source dicts: as labeled gives `independently-verified`; the two Brave pages set to first-party and the failed source removed gives `claimed` with a cap_rationale (one run each). | [Source type classification](#source-type-classification--edge-cases-to-revisit), [source-quality-followups.md](plans/deferred/source-quality-followups.md) (entity-match independence classifier), [claim-refresh-integrity-fixes.md](plans/completed/claim-refresh-integrity-fixes.md) |
| RF4 | High | Raw `【2026/631793】` citation tokens and "Source 1" references render on the site. The Sources list is an unordered list of ids, so "Source N" points at nothing. Also present in the local build of the published `subjects/ai-model-producers/ai-producers-existential-score` (deployed page not checked). | Reproduced | No post-processing or lint rule for narrative citations (`linter/checks.py`). The analyst prompt layout (`### Source N` plus `Source id:`, `analyst/agent.py:285-287`) likely nudges gpt-oss toward its native bracket format, against `analyst/instructions.md:110` ("cite by title"). "Source N" predates this run (in the committed Brave body) and the model writes it with a non-breaking space (U+00A0), so a lint regex must allow that. | Astro markdown render of the claim body keeps `【2026/631793】`; `dist/research/claims/subjects/ai-model-producers/ai-producers-existential-score/index.html` contains raw `【...】`. | [Pipeline markdown emitter bugs](#pipeline-markdown-emitter-bugs-2026-05-08), [claim-refresh-integrity-fixes.md](plans/completed/claim-refresh-integrity-fixes.md) |
| RF5 | High | Research drifted to generic AWS and Google pages; the two Brave-specific URLs the scorer kept (`brave.com/blog/ecosia`, `community.brave.app/.../ecological-footprint/404963`) were never attempted. Google pages were ingested and listed though no source says Brave uses Google. 3 of 8 frontmatter sources are uncited in the body. | Isolated | Ingest stops at 8 successes in the scorer's list order (`orchestrator/pipeline.py:782-786`); `ScoredCandidate` has no score field (`researcher/scorer.py:22-30`) though the docstring at `orchestrator/pipeline.py:733` says "score order". Planner sub-question 2 names AWS/Google before any evidence and queries drop the entity anchor (`researcher/planner.py`). Every ingested source goes into `sources:` (`orchestrator/cli.py:1086-1087`). | Run log: scorer kept list (line 32) puts the Brave URLs last; `Reached target 8 successes` (185). Not re-run: `step-research` output varies run to run. | |
| RF6 | High | Verdict is unstable on near-identical evidence: run `unverified`/medium; `dr step-analyze` `mostly-true`/low; analyst replay `true`/high; replay with corrected labels `unverified`/low. Prior committed verdict was `false`. Body also calls AWS's 2025 renewable matching a future "ambition". | Reproduced | Likely model variance plus prompt: the scope question (sync servers on AWS vs all Brave hosting) is left to the model each run and not stated in the body. Inputs differed slightly (step-analyze sees no labels; replays saw the Microsoft file under the colliding id). | Four analyst calls listed in Status; same claim, same source ids. | [Analyst decomposition](#analyst-decomposition-cost-lever) |
| RF7 | Medium | Refresh overwrote the operator's `seo_title` with "Brave Browser hosted on renewable energy" (reads as an affirmation of an unverified claim) and dropped the hand-written `cap_rationale`. | Isolated | `seo_title` is required (min length 1) on the analyst output, so the keep-existing branch at `orchestrator/persistence.py:315` never runs on refresh; `cap_rationale` has no keep path (`orchestrator/persistence.py:313`). | `VerdictAssessment.model_fields['seo_title'].is_required()` returns True. | |
| RF8 | Medium | Refresh of a published claim leaves no trail: verdict `false` to `unverified` with no `corrections` entry, `human_review` (2026-05-11) wiped, prior research trace replaced, the 6 old sources dropped with no reason and now orphaned (next prune deletes them). | Isolated | No code writes `previous_verdict`/corrections (no match in `orchestrator/` or `common/`); `reset_review=True` at `orchestrator/cli.py:1128` with `orchestrator/persistence.py:413-431`; refresh never reads prior `sources:`. Status reset to draft is by design. | Compare `git show HEAD:research/claims/brave-browser/renewable-energy-hosting.md` with the refreshed file. | [published-claim-refresh-trail.md](plans/published-claim-refresh-trail.md) (P1 to P4), [Claim detail page](#claim-detail-page--deferred-improvements) (verdict change history) |
| RF9 | Medium | Terminal says "auditor flagged this claim for review (verdict disagreement)" when verdicts agree; the real reason (2+ evidence gaps) is not saved anywhere. | Reproduced | Hardcoded message `orchestrator/cli.py:1133`; flag set by `len(evidence_gaps) > 1` (`auditor/compare.py:62-65`); `audit_block` omits reasoning and gaps (`orchestrator/persistence.py:401-409`); GreenPT responses are not body-logged (`common/models.py:271-281`). | `dr step-audit --claim brave-browser/renewable-energy-hosting --format json`: `verdict_agrees: true`, `needs_review: true`, 2 `evidence_gaps`. | [published-claim-refresh-trail.md](plans/published-claim-refresh-trail.md) (A1, A2) |
| RF10 | Medium | Source checks never run in claim-refresh; key quotes are not verbatim. AWS blog quote "AWS aims for 100% renewable energy by 2025..." is a paraphrase; the page says "AWS has a goal of operating all operations at 100% renewable energy by 2025...". | Reproduced | `validate_source_file` is called only from `dr step-ingest` (`orchestrator/cli.py:377`) and never with `page_text`, so `_check_key_quotes` (`ingestor/validation.py:81`) never runs. | Substring check of the quote against the fetched page text in the run log: no match; the "has a goal of" sentence matches. | |
| RF11 | Medium | No `archived_url` on any of the 7 new sources. Archive lookups that get HTTP 429 are treated as "no snapshot" with no error recorded. | Reproduced | `check_archive_org_timegate` returns a silent miss for any non-redirect, non-5xx status (`ingestor/tools/wayback.py:93`); `save_to_wayback` has no retry or throttle. | `curl -I` to web.archive.org returns 429 (also for an example.com control); `check_archive_org_timegate(client, 'https://brave.com/transparency')` returns `{'available': False, 'archived_url': None}` with no `error`. | [wayback-archive-job.md](plans/deferred/wayback-archive-job.md) (deferred; the RF11 fix itself is a prerequisite of roadmap SITE-J (Responsible AI chatbots)) Triage: Responsible AI chatbots; in SITE-J; 2026-10-07 |
| RF12 | Medium | One stalled LLM call held an ingest slot for the full ~112 s budget and delayed the run about 39 s after the 8-source target was met, then printed `! ingest: Ingest timed out` though nothing was missing. | Isolated | `stop.set()` does not cancel in-flight tasks and `gather` waits for all (`orchestrator/pipeline.py:786`, `:801`); the Infomaniak client sets no per-request timeout (`common/models.py:301`). | Run log: target reached 01:19:25, timeout logged 01:20:03. | [Pipeline performance & hardening](#pipeline-performance--hardening) |
| ~~RF13~~ | Medium | **Done** (07c34ac, 2026-10-04): step-analyze now uses `load_source_dict`. `dr step-analyze` is not a faithful replay of the refresh analyst: its source dicts omit `source_id`, `kind` and `independence`, and it never prints `verification_level`. With `--write` it would save a level the model chose without any independence labels. | Isolated | `orchestrator/cli.py:488-496` builds dicts by hand instead of using `load_source_dict` (`orchestrator/persistence.py:104`). | `dr step-analyze --claim brave-browser/renewable-energy-hosting` output has no level line and no source ids. | |
| RF14 | Low | Poor slugs: `renewable20energy20and20data20centers20at20aws` (`%20` not decoded), `631793` (forum thread number), generic one-word tails (`transparency`, `sustainability`). | Reproduced | `common/utils.py:23-27`: no `unquote`, last segment only, no fallback for numeric or generic segments; overrides the LLM slug. | `slug_from_url` on the builder.aws and forum urls prints the two slugs above. | [Improve source slug generation](#improve-source-slug-generation) |
| RF15 | Low | Progress line `failed=3` is 1 timeout plus 2 URLs never tried; the DNS failure (RF2) counts as fetched. | Isolated | `orchestrator/pipeline.py:382` counts every not-ingested URL as failed; no "skipped" category. | Run log line `ingested 8/11 (cached=0, fetched=8, failed=3)` with one timeout warning. | |
| RF16 | Low | Sidecar `pipeline_run.model` and the terminal line name `DR_MODEL`, which ran no agent; analyst and auditor ran the same model (weak auditor independence); 2 `sources_consulted` entries lack `acquisition`; `tool_outcomes: []`. | Isolated | `orchestrator/cli.py:911`, `:1117`; `orchestrator/persistence.py:475`. | Compare sidecar `models_used` with `pipeline_run.model`. | [model-tier-enforcement_stub.md](plans/deferred/model-tier-enforcement_stub.md) (deferred) |
| RF17 | Low | URL scorer silently omitted 4 of 113 candidates (11 kept + 98 dropped). | Isolated | No kept + dropped = input check in `researcher/decomposed.py:469-485`. | Run log lines 26 and 32. | |
| RF18 | Low | arXiv searched 7 queries for a single-product claim; all dropped. | Isolated | `environmental-impact` is in `ACADEMIC_TOPICS` (`common/models.py:126-130`). | Run log lines 19-25. | |
| RF19 | Low | `2024/new-approach-to-data-center-and-clean-energy-growth` body is wrapped in `---`, so its summary renders as an H2 heading on the source page. | Reproduced | Ingest model output; no body normalization before write. | Astro markdown processor on the file body outputs `<hr>` then `<h2 ...>`. | [Pipeline markdown emitter bugs](#pipeline-markdown-emitter-bugs-2026-05-08) |
| RF20 | Low | The analyst sees only the ingest model's 1-3 sentence body, labeled "Full text", never page text, so ingest-model errors (RF2, RF10) flow straight into the verdict. Also: `as_of` uses local date while `ran_at` is UTC, model text carries U+2011/U+00A0/U+202F characters, frontmatter style churn. | Isolated | `analyst/agent.py:302`; `orchestrator/persistence.py:319`. | Analyst request in the run log shows each source as summary, quotes and a short "Full text" paragraph. | [Analyst decomposition](#analyst-decomposition-cost-lever) |

Follow-ups from the code review of the RF1 to RF4 fixes (2026-10-04, [plan](plans/completed/claim-refresh-integrity-fixes.md)):

| ID | Sev | Issue | Likely cause | Related |
|----|-----|-------|--------------|---------|
| RF21 | Low | When the write-time guard renames a slug (another run wrote the same slug after `_ingest_urls` resolved it), the analyst prompt, `source_overrides` and sidecar keep the old id. Narrow window, needs two concurrent runs. Fix direction: make source ids final before anything downstream uses them (write source files right after ingest, or re-resolve slugs before building coverage and overrides). | `_write_source_files` returns the new id but source dicts were built earlier (`orchestrator/pipeline.py` `research_claim`) | RF1 |
| RF22 | Medium | `validate_source_file` in the refresh path drops whole sources for fixable problems: a year before 2000 (real older reports) or a model-written non-archive.org `archived_url`. | Validation errors map to `invalid_source`; no repair step (clear the bad field) before rejecting | RF2, RF10 |
| RF23 | Low | Slug resolution compares only the stored `url`; an existing file that stored a redirect target, or a URL that canonicalizes differently, is treated as another page, so a duplicate file is written instead of reusing it. **Partly done** (904c376, 2026-10-04): the dedup index now matches by canonical URL and same-page URLs in one batch collapse; the stored-redirect-target case remains. | `persistence.py` `_resolve_one_slug` and the exact-URL index | [Dedup detection](#dedup-detection-on-url-ingest-and-claim-creation) Triage: Responsible AI chatbots; in SITE-J; 2026-10-07 |
| ~~RF24~~ | Low | **Done** (07c34ac, 2026-10-04), with RF13. `_apply_entity_match` reads `sd["source_id"]`; `dr step-analyze` builds source dicts without it, so passing a resolved entity there would raise. Safe today only because step-analyze passes none. | `orchestrator/pipeline.py` `_apply_entity_match`; step-analyze source dicts | RF13 |
| RF25 | Low | `dr lint`'s level-vs-pool check counts a source as independent only from its file label or a claim override, like the site; the analyst falls back to a label derived from `source_type` when the file has none, so for a legacy source with no `independence` field the two can disagree. | `linter/checks.py` `check_verification_level_pool` vs `orchestrator/persistence.py` `load_source_dict` fallback | RF3 |

---

## Decouple subject from entity model

Goal: Today subjects resolve to entity files under `research/entities/subjects/`. Decide whether non-entity subjects get a lighter-weight record (e.g., `research/subjects/<slug>.md` with minimal frontmatter) or whether the entity collection grows a `kind: subject` variant. Either way, researcher/analyst/auditor must stop assuming the subject has a website, parent_company, or other entity-shaped fields. Subjects can be abstract or natural-world topics — e.g., *love*, *hurricanes* — not just a company, product, or industry sector.

| Work Item | Notes |
|-----------|-------|
| Lighter-weight subject record | Decide between `research/subjects/<slug>.md` with minimal frontmatter or an entity-collection `kind: subject` variant. |
| Update agent instructions for non-entity subjects | Researcher: don't try to find an "official" source for a subject like "love"; lean on encyclopedic/scholarly sources. Analyst: entity-stance reasoning collapses when the subject isn't an actor; verdict logic must handle subject-as-topic framing. Auditor: independence/COI heuristics keyed on the subject being an entity need a fallback path. |

---

## Improve source slug generation

Goal: Produce more readable, stable, less collision-prone slugs for source files. Today the URL-derived slug feature (shipped 2026-05-03) prevents *new* duplicates but still emits awkward names (e.g., `full.md`, `pmc12036037.md`, `lee2025aicriticalthinkingsurveypdf.md`).

Correction (2026-10-04): it does not prevent collisions between different URLs with the same path tail, and a collision makes a claim cite the wrong file (RF1). Undecoded `%20` and forum thread ids are further failure modes (RF14). Both in [claim-refresh review findings](#claim-refresh-review-findings-2026-10-04).

| Work Item | Notes |
|-----------|-------|
| Audit current slug derivation logic | Locate the slug builder in the ingestor and catalog the failure modes: bare path tails (`/full` → `full.md`), opaque IDs (`pmc12036037`), squashed/unhyphenated PDF filenames (`lee2025aicriticalthinkingsurveypdf`). |
| Prefer `<title>` or OG title over URL path | When the page yields a meaningful title, slugify *that* (truncated to ~6-8 words). Fall back to URL path tail only when title extraction fails. |
| Add domain prefix for generic path tails | When the URL tail is a stop-word-ish slug (`full`, `index`, `article`, `default`, `home`) or shorter than N chars, prefix with a short host token (e.g., `nature-full`, `pmc-12036037`). |
| Re-segment squashed PDF filenames | Detect `…YYYYsomethinglongstring` patterns and either insert hyphens at obvious boundaries or fall back to title-based slugs for PDFs. |
| Backfill rename pass (optional) | One-shot script to rename existing badly-named sources and update claim `sources:` references. Lower priority; new ingests benefit immediately from the fix.

---

## Local source-search prefilter (analysis only)

Goal: Decide whether the researcher should search the local source corpus *before* (or alongside) external searches. The intuition is that as the corpus grows, an existing source already covers a new sub-question often enough to justify the lookup cost — but de-dup on ingest already prevents repeated work, so the marginal value may be small.

| Work Item | Notes |
|-----------|-------|
| Quantify the opportunity | Sample N recent claim runs and count how many fetched sources turned out to overlap (post-dedup canonical URL or near-duplicate content) with sources already in the corpus. If overlap is rare, the feature isn't worth building. |
| Compare against dedup coverage | Dedup catches identical URLs after fetch. A local prefilter would catch them *before* fetch — savings = (avoided fetches × ingest cost). Estimate per-run savings vs. corpus-search latency added to every researcher call. |
| Sketch retrieval shape if it pencils out | Options: (a) keyword/title BM25 over `research/sources/**/*.md`, (b) embedding index, (c) tag/topic facet match. Each has different freshness + accuracy tradeoffs. Document, don't build, until the value analysis lands. |
| Decision artifact | A short memo in `docs/plans/drafts/` with the numbers and a build/skip recommendation. No implementation work is on the table until that exists.

---

## Curated list of exceptional sources/sites

Goal: Maintain a hand-curated allowlist (or "trusted set") of sources and sites known to be high-signal, primary, or otherwise exceptional — usable by researcher prompts as preferred starting points, by the auditor as a quality signal, and by readers as a transparency artifact.

Related: [`source-quality-followups.md`](plans/deferred/source-quality-followups.md) (deferred) tracks the same idea from the source-quality side ("Curated allowlist of independent AI research orgs"); reconcile when picked up.

| Work Item | Notes |
|-----------|-------|
| Define schema and storage | A YAML file (e.g., `research/exceptional-sources.yaml`) listing entries with `url`, `domain`, `name`, `kind` (primary/scholarly/regulator/etc), `why_exceptional`, optional `topics`. Decide whether entries are *sites* (domain-level), *sources* (URL-level), or both. |
| Seed the list | First pass: regulators/standards bodies (NIST, FTC, UNESCO), academic indexes (arXiv, PubMed Central), credible reporters/labs (FMTI, AI Lab Watch, Epoch AI), and any others surfaced during current research. |
| Wire into researcher prompts | Pass the curated list (or topic-filtered subset) into the researcher as a "prefer these when relevant" hint, not a hard filter. |
| Wire into auditor / source-trust signal | Use membership as one input to source independence/trust scoring. Avoid making it the sole signal — curated lists go stale. |
| Surface to readers (later) | A `/sources/exceptional` or `/about/sources` page renders the list with the `why_exceptional` rationale, making the editorial choice visible. Lower priority than backend wiring.

---

## SEO post-restructure follow-ups (2026-05-11)

Carved off [`plans/completed/seo-post-restructure.md`](plans/completed/seo-post-restructure.md) when the main implementation pass shipped. All require Google to recrawl since 2026-05-11.

| Work Item | Notes |
|-----------|-------|
| Re-run `scripts/seo/inspect-urls.sh` ~2026-05-18 | One week after the Cloudflare 301s went live and the sitemap was submitted. Compare against the 2026-05-11 baseline in `seo-runs/`: `googleCanonical` for `/claims` and `/companies` should flip from the trailing-slash old URL to `/research/...`, and `/research/*` should leave the "URL is unknown to Google" state. If old URLs are still in "Indexed" after 4 weeks, re-verify the redirect rule (`dr_redirects_rule`) and the list contents. |
| §5.3 Request Indexing pass | Drive Chrome through `scripts/seo/request-indexing-queue.txt` (10 URLs, priority-ordered). Pseudocode is in `plans/completed/seo-post-restructure.md` §5.3. Needs a Chrome profile already logged into `search.google.com/search-console`. Throttled by Google to ~10/day. |
| §5.4 Weekly coverage screenshots | For ~4 weeks after the 301s shipped: navigate to the GSC Pages report and capture the four count buckets (Indexed, Page with redirect, Crawled - not indexed, Discovered - not indexed) to `seo-runs/coverage-YYYY-MM-DD.json`. Expectations and re-investigation triggers are in §5.4 of the completed plan. |
| Single-hop redirect for deep claim URLs | Today `/claims/{x}/{y}` → `/research/claims/{x}/{y}` → `/research/claims/{x}/{y}/` (CF 301 + GH-Pages canonical-slash 301). Only fixable by changing Astro's `trailingSlash` mode and rebuilding URL handling site-wide. Low priority — Google handles 2-hop chains, but worth revisiting if other Astro work touches routing. |
| OG image at 1200×630 | Carried over from the completed plan's §6 backlog. `dr-logo.png` is square; Twitter/FB want 1200×630. All new `/research/` and `/resources/*` URLs inherit the same default, so share-card quality is uniformly low. One properly-sized image passed via `ogImage` from `Base.astro` (or per-section) fixes it. |
| End the pre-release noindex policy | The trigger is decided in the plan for roadmap SITE-J (Responsible AI chatbots, backed by claims). `INDEX_ALPHA_DETAIL_PAGES = false` in `src/lib/seo.ts` keeps detail pages noindexed until then; at that point flip to `true`, rebuild + redeploy, and follow the checklist in `docs/seo-and-cloudflare-playbook.md` § "When the pre-release noindex period ends." Triage: Responsible AI chatbots; in SITE-J; 2026-10-07 |

---

## Glossary of terms

Goal: Maintain a glossary covering AI, AI safety, data-center environmental technology, energy use, and energy-market terminology. The matrix and claim pages already lean on terms like RECs, PUE, additionality, and PPAs without defining them — a reader-facing glossary lets the rest of the site link to plain-language explanations instead of inlining them.

Initial tracking doc: [`reader-glossary.md`](reader-glossary.md) (working draft; not yet wired into the site).

| Work Item | Notes |
|-----------|-------|
| Grow the term list | Seed entries as they come up in research and matrix work. Group loosely by domain (AI / AI-safety / data-center / energy / energy-markets) once there are enough to justify it. Keep each definition short and source-backed where possible. |
| Decide reader-facing surface | Options: (a) standalone `/glossary` page, (b) per-term anchors that other pages link to, (c) tooltip/popover on first use. Pick once there are ~15+ terms. |
| Wire into matrix and claim pages | Replace inline parentheticals ("RECs", "PUE 1.06") with links to the glossary entry once the surface exists. |

---

## Petition Worker follow-ups

Deferred from the 2026-10-04 build review of `workers/api/` ([petition-signatures.md](plans/completed/petition-signatures.md), [architecture/petitions.md](architecture/petitions.md)). None block launch.

| Work Item | Notes |
|-----------|-------|
| Run Worker tests in CI | `workers/api` has its own `package.json`; `ci.yml` runs only the site build. Add a job: `npm ci` and `npm test` in `workers/api/`. |
| Deploy the Worker from GitHub Actions | Today `wrangler deploy` is manual (runbook "Petitions"). Needs a Cloudflare API token as a repo secret. |
| Cheaper public count reads if traffic grows | `GET /petitions/{slug}` is `no-store` (one D1 batch per page view). Options: `no-cache` plus an ETag (count plus newest `confirmed_at`), or Workers Cache API with a short TTL purged on confirm. |
| Cap the public names list | The JSON returns every opted-in name. Add a `LIMIT` and a "show all" fetch once the list is long. |
| Run the two deferred production tests | Testing table rows Export (runbook export query; CSV header must be exactly `name, email, display_consent, created_at, confirmed_at, petition_slug`) and No-JS path (sign with scripts off; expect the Worker's "check your email" page). Skipped at launch 2026-10-05; everything else passed. |
| Regular backup of signature data to Brandon's laptop | Today the only copy of the signatures is the `dr-api` D1 database (D1 Time Travel allows point-in-time restore, 7 days on the Workers Free plan and 30 on Paid, but only inside Cloudflare). Want a scheduled off-Cloudflare copy. Options to weigh: a local scheduled job (launchd) running `wrangler d1 export dr-api --remote --output <dated>.sql`, kept encrypted (it holds emails) with old copies pruned; or a Worker cron writing a dump to R2 that the laptop pulls. Open questions: how often, how many copies to keep, where the key lives, and how this squares with the privacy promises: the privacy page (`/privacy#petitions`) says Cloudflare stores the list, signers can remove themselves, and the daily cleanup deletes emails of closed petitions. Old backups would keep removed signers and deleted emails unless they are pruned or the notice says so. |
| Clear reminder to export before closed-petition emails are deleted | The daily cleanup (`workers/api/src/index.ts`, cron in `wrangler.toml`) clears emails of closed petitions within a day of closing, and closing is a hand-run SQL update (runbook "Close a petition"). The only warning today is one line in the runbook. Options: a script or `inv` task that exports the CSV and then closes, refusing to close without an export; or the cleanup waits a set number of days after `closed_at` and the Worker emails Brandon on close with the deletion date (a grace period changes what `/privacy#petitions` promises). |
| Keep Worker page colors in sync with `tokens.css` | `workers/api/src/pages.ts` copies hex values by hand. A test could read `src/styles/tokens.css` and compare. |
