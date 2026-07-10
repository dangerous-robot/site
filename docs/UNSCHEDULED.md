# Unscheduled Work

Work known but not yet assigned to a release. Items here are candidates for the next release or future releases.

---

## Pipeline performance & hardening

Goal: Reduce onboarding wall time and wasted API calls.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Parallelize onboard templates | [onboard-parallelize-templates.md](plans/onboard-parallelize-templates.md) | `asyncio.Semaphore(3)`-guarded gather; interactive mode clamps to 1. Plan predates the researcher decomposition: re-verify line refs and reconcile its `concurrency` knob with the shipped `llm_concurrency` before implementing |

The other four items in this group shipped and moved to `plans/completed/`: onboard-reuse-verify-sources, ingestor-fail-fast-403, researcher-host-blocklist, ingestor-tighten-timeouts.

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
| Full 4-step decomposition (entity resolver, per-source stance, verdict synthesizer, narrative+title writer) | [analyst-decomposition_stub.md](plans/drafts/analyst-decomposition_stub.md) | Stub draft; needs token-usage baseline before committing. Keeps verdict+confidence on frontier; pushes the rest to Haiku-class. Biggest win is feeding frontier structured stances instead of raw source bodies (~10x smaller prompt). Source-trust Phase 2 (COI/independence weighting in analyst reasoning) is a forcing function: adding conditional source weighting further complicates analyst instructions and makes decomposition more urgent. |
| Narrative + title writer extraction (smallest slice) | (to be drafted from the stub) | Once verdict is fixed, this is structured writing with a mechanical title-polarity rule. Most defensibly Haiku-class sub-decision; could be promoted out of the broader plan as a single-step extraction. |

---

## Model-tier enforcement (was Q4)

Goal: Enforce "small-by-default" model selection instead of relying on the default value alone. Today nothing caps escalation — any agent can be pointed at a large model. Chosen approach is option (b): per-agent tier caps in config.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Per-agent tier ceiling in `VerifyConfig` | [model-tier-enforcement_stub.md](plans/model-tier-enforcement_stub.md) | Stub carried over from the retired `pre-launch-questions.md` Q4. Add a `MODEL_TIER` map + `max_tier` ceiling checked in `resolve_model`; most machinery (per-agent fields, `model_for`) already exists from multi-provider Part 2. Cost-ceiling successor (option c) waits on `token-usage-log.md`. |

---

## Dedup detection on URL ingest and claim creation

Goal: Stop creating duplicate claims when the pipeline encounters a claim that already exists. URL-level source dedup shipped 2026-05-03 ([source-url-dedup_completed.md](plans/completed/source-url-dedup_completed.md), including a `--force` bypass); the remaining gap is claim-level match-and-return plus richer URL canonicalization.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Match-and-return-existing for URL ingest and claim creation | [pipeline-dedup-detection_stub.md](plans/drafts/pipeline-dedup-detection_stub.md) | URL match: canonicalize (lowercase scheme/host, strip default ports, drop fragment + `utm_*`/`fbclid`/etc, strip trailing slash) and look up existing source by `canonical_url` frontmatter. Claim match: `(entity_slug, criteria_slug)` from frontmatter (already present today). On hit: `dr ingest` prints existing id, exits 0; onboard skips analyst+auditor and logs the dedup hit in the sidecar. `--force` bypasses dedup. Composes with onboard-reuse-verify-sources.md. |

---

## arXiv ingest hardening (2026-05-10)

Goal: Stop the two arXiv-specific failure modes surfaced while auditing recent dr runs. Both leaked bad metadata into a then-published verdict; the motivating claim file (`research/claims/gemini/discloses-energy-sourcing.md`, whose cap_rationale described Google's own preprint as an "independent expert assessment") was removed in the 2026-05-11 launch-set prune, but the pipeline gaps remain.

| Work Item | Notes |
|-----------|-------|
| Canonicalize arXiv URLs at ingest | Treat `arxiv.org/abs/{id}`, `arxiv.org/html/{id}v{n}`, and `arxiv.org/pdf/{id}` as one source. Today both `arxiv:2508.15734` and `arxiv:2502.18505` exist as two separate source files (e.g., `2025/250815734.md` from `abs/` and `2025/250815734v1.md` from `html/v1`) with conflicting frontmatter. The `chatgpt/excludes-frontier-models` audit cites both variants of 2502.18505 as if they were independent evidence. Composes with the existing URL-dedup work in [pipeline-dedup-detection_stub.md](plans/drafts/pipeline-dedup-detection_stub.md) — arXiv canonicalization is one specific rule in the broader canonicalizer. |
| Detect corporate authorship on arXiv abstracts | When an arXiv abstract names a corporate AI lab (Google/DeepMind, Anthropic, OpenAI, Meta, Microsoft Research, etc.) as an author affiliation, force `independence: first-party` and `source_type: primary` against that entity in the ingestor's frontmatter pass. Today the `abs/` ingestion of `2508.15734` (Google's own Gemini environmental-impact paper) was written as `publisher: arXiv / independence: independent / source_type: secondary`; the `html/v1` ingestion of the same paper was correctly written as `publisher: Google / independence: first-party / source_type: primary`. The wrongly-labeled variant is what flowed through to the published Gemini verdict. |

---

## PDF attachment as alternate source content surface

Goal: Let a locally-attached PDF stand in for an unreachable URL (401/402/403/451 origins) as a content surface for both the ingestion agent and the human reviewer. Pairs with the fail-fast plan — when the ingestor can't fetch, a pre-attached PDF is the fallback.

| Work Item | Plan | Notes |
|-----------|------|-------|
| PDF attachment core (ingestion + model) | [source-pdf-attachment.md](plans/source-pdf-attachment.md) | `pdfs:` frontmatter block, `_attachments.yaml` manifest, `pdf_read` tool, `dr attach-pdf` CLI, sha256 integrity lint |
| PDF attachment publish surface | [source-quality-followups.md § PDF publish surface](plans/source-quality-followups.md#pdf-publish-surface-drafted-post-attachment) | Site renders `republish: true` PDFs with download link; `_headers` `noindex`; depends on core landing |

---

## AI Research Audit Trail

Goal: On each `/claims/[slug]` page, show a collapsible section with which agent ran the research, what sources were consulted, when a human reviewed it, and whether the verdict changed from draft. Builds reader trust by making the AI+human process visible.

Architecture: sidecar `.audit.yaml` file per claim, written by the pipeline after the auditor runs, consumed by a custom Astro loader. Full 3-stage architectural review completed.

| Work Item | Plan | Notes |
|-----------|------|-------|
| ~~Sidecar format + pipeline write + Astro loader + UI (Stage 1)~~ | [audit-trail.md](plans/completed/audit-trail.md) | **Done** (2026-04-25, moved to `completed/`). `_write_audit_sidecar` in persistence.py; `dr review --claim` CLI; collapsible UI; 11 sidecars committed. |
| Extended audit fields + staleness check + orphan CI gate (Stage 2) | [audit-trail-extensions.md](plans/audit-trail-extensions.md) | Requires: no stale sidecars, orphan check CI, backfill script |
| Append-only history (Stage 3) | [audit-trail-extensions.md](plans/audit-trail-extensions.md) | Full recheck history per claim |


---

## Ops Runbook

Goal: One reference doc covering the dev loop, pipeline operations, deploy process, and content schema changes. `docs/runbook.md` exists (2026-05-04) and covers the dev loop; the rest is unwritten (its own TODO lists the same sections).

| Work Item | Notes |
|-----------|-------|
| Expand runbook.md | `dr` CLI reference, deploy steps, schema change checklist; also document the newer `inv audit`, `inv audit.prune`, `inv check` tasks |
| Expand source `kind` enum | Add `statement` (social posts, press releases, direct submissions) and `filing` (company invoices, certificates, contracts). Schema change touches `content.config.ts`, pipeline `SourceFrontmatter`, and `_classify_source_type`. |

---

## Automation (conditional)

Goal: Recurring audits, queue-based intake. Trigger: enough content exists that manual auditing is burdensome.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Scheduled citation audits | [source-quality-followups.md § Scheduled citation audits](plans/source-quality-followups.md#scheduled-citation-audits-drafted) | Scheduled workflows, QUEUE.md intake |

Downstream sync to parallax-ai: [downstream-sync.md](plans/drafts/downstream-sync.md) (local draft) -- good idea, not needed now.

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

- **`/about` page** -- still missing. (The list/index pages this bullet originally asked for shipped under `/research/*`.)
- ~~**`parent_company` not rendered**~~ -- Rendered as of [`plans/completed/entity-metadata-surface_completed.md`](plans/completed/entity-metadata-surface_completed.md) (2026-05-09). All five product entity pages and any claim whose subject is a product render "Made by [Parent]" linking back to the company entity page. Inference automation for `parent_company` itself remains in `plans/parent-company-inference.md` (post-v1).
- **Entity reference validation** -- Claims reference entities by path string with no build-time validation. Use Astro's `reference('entities')` helper or add entity-ref checking to `scripts/check-citations.ts`.
- **Source reference upgrade** -- Replace `z.array(z.string())` with `z.array(z.string().min(1)).min(1)` for claims `sources` field. Current schema permits empty arrays.
- **`recheck_cadence_days` constraint** -- Schema accepts 0/negative values. Add `.int().min(1)` to the Zod definition.
- **GitHub Actions SHA pinning** -- All actions use mutable tags (`@v4`). Pin by full SHA for supply chain security.
- **SEO basics** -- ~~No favicon, robots.txt, canonical URLs, Open Graph tags. `description` prop in Base.astro is never customized per page.~~ Done (2026-04-29): robots.txt, sitemap, canonical, OG tags, per-page descriptions, Organization/ClaimReview/FAQPage/BreadcrumbList/WebSite JSON-LD. Remaining: (1) `og:image` asset -- code accepts an `ogImage` prop but `/dr-logo.png` is a narrow logo; a proper 1200×630 `og-default.png` is needed for social sharing previews. (2) `SearchAction` wiring -- the WebSite JSON-LD declares a `SearchAction` at `/claims?q={search_term_string}` but `FilterBar.astro` doesn't read `?q=` from the URL on load; a small JS change is needed to make the schema functional.

### Opportunities

- **Validation gaps** -- CI validates schema structure and citation integrity but not reasoning quality. Potential additions: confidence-to-verdict alignment, staleness detection, source URL liveness checks, archived URL population nudges, a check framework (Vitest) for scripted validators.
- **Confidence rubric** -- Define what `high`/`medium`/`low` confidence concretely means. Use an LLM to check each claim against the rubric.
- **Claim Updater instruction quality** -- Consider adversarial review, inter-rater consistency validation, and forbidden-combination gates (CI rejection of nonsensical confidence-verdict pairs).
- **Source freshness** -- confirm the ingestor reliably populates the optional `published_date` source field (`src/content.config.ts`); wire it if not. (Folded in from a scratch note, 2026-07-03.)

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
| Decide carrier | Either elevate `.audit.yaml` to "verdict record" (rename + reshape) or merge audit fields into claim frontmatter. Operator decision pending; previously deferred in `docs/plans/completed/v0.1.0-vocab-workflow-landing.md` Out-of-scope. |
| Update canonical paragraphs once carrier decision lands | Generalized + v1 paragraphs in `AGENTS.md` and `docs/architecture/glossary.md` need to reflect the new artifact name and ownership. |
| Schema migration | Whichever carrier wins, `src/content.config.ts` enum/shape needs updating; backfill all existing claims and `.audit.yaml` files. |

Scheduling note: blocked on operator decision; not v0.1.0. Touches audit-trail Stage 2/3 and the data-lifecycle-policy stub.

---

## Source type classification — edge cases to revisit

Carried from the retired 2026-04-22 follow-up doc. Everything else in that doc shipped, was folded into the research-page accordion, or referenced content removed in the 2026-05-11 launch-set prune.

- **SEC EDGAR filings** -- classified as `primary`; verify this is correct.
- **B Lab / B Corp profiles** -- classified as `secondary`; confirm.
- **UNESCO, NTIA, UNFCCC** -- classified as `secondary`; confirm.
- **IBM, Deloitte reports** -- classified as `secondary`; some may lean tertiary. Spot-check.

---

## Claim detail page — deferred improvements

From UI redesign plan (2026-04-24). Current implementation shows reviewer count in the meta row; reviewer name in expanded research details.

| Work Item | Notes |
|-----------|-------|
| Multi-reviewer tracking | Change `human_review` from single object to array of `{ reviewed_at, reviewer, notes, pr_url }`. Meta row count (`✓ N reviewers`) derives from array length. Requires schema version bump and backfill script. |
| Sign-off count in list views | Once multi-reviewer array exists, surface count in `ClaimRow` and entity detail claim lists as a trust signal. |
| Verdict change history | Append-only `history` array in `.audit.yaml` recording each pipeline run's verdict+confidence output. Site renders a timeline on the claim detail page. Requires pipeline write changes. |
| Show-your-work reasoning panel (was Q11) | Reasoning-transparency scope carried over from the retired `pre-launch-questions.md`; partially implemented, treated as in flight. Open sub-decisions: inline analyst narrative on every claim vs. expand-on-click; auditor disagreement excerpts always visible vs. only when the verdict was contested; whether to expose the actual instruction text the analyst saw. |

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

Related: [`source-quality-followups.md`](plans/source-quality-followups.md) tracks the same idea from the source-quality side ("Curated allowlist of independent AI research orgs"); reconcile when picked up.

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
| End the pre-release noindex policy at GA | Flip trigger decided: **GA (1.0.0)**. `INDEX_ALPHA_DETAIL_PAGES = false` in `src/lib/seo.ts` keeps detail pages noindexed until then; at the 1.0.0 release, flip to `true`, rebuild + redeploy, and follow the checklist in `docs/seo-and-cloudflare-playbook.md` § "When the pre-release noindex period ends." |

---

## Glossary of terms

Goal: Maintain a glossary covering AI, AI safety, data-center environmental technology, energy use, and energy-market terminology. The matrix and claim pages already lean on terms like RECs, PUE, additionality, and PPAs without defining them — a reader-facing glossary lets the rest of the site link to plain-language explanations instead of inlining them.

Initial tracking doc: [`reader-glossary.md`](reader-glossary.md) (working draft; not yet wired into the site).

| Work Item | Notes |
|-----------|-------|
| Grow the term list | Seed entries as they come up in research and matrix work. Group loosely by domain (AI / AI-safety / data-center / energy / energy-markets) once there are enough to justify it. Keep each definition short and source-backed where possible. |
| Decide reader-facing surface | Options: (a) standalone `/glossary` page, (b) per-term anchors that other pages link to, (c) tooltip/popover on first use. Pick once there are ~15+ terms. |
| Wire into matrix and claim pages | Replace inline parentheticals ("RECs", "PUE 1.06") with links to the glossary entry once the surface exists. |
