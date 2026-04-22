# Backlog: dangerousrobot.org

Last updated: 2026-04-22

This file tracks the phased progression for standing up dangerousrobot.org. Each phase lists its work items with links to detailed plan files. Status is tracked here; details live in the individual plans.

## Guiding Principle

Defer big decisions about *what* to research. Focus on documenting the *types* of things that could be researched, and implement a small set to prove out the architecture end-to-end.

## Pruning

Prune this file regularly to keep it scannable. When a phase is fully done, collapse it to a short summary block:

```
## Phase N: Title (done)

One-to-two line description of what was delivered and when. Link to completed plan(s) if they exist in `plans/completed/`.
```

Remove the work-item table, status notes, and any "Next" subsections. The completed plans and git history are the detailed record.

## Decisions Log

| Decision | Choice | Date | Notes |
|----------|--------|------|-------|
| Static site generator | Astro | 2026-04-18 | Content Collections + Zod schema validation |
| Agent orchestration | PydanticAI (Python) | 2026-04-18 | Model-agnostic, testable, typed. Polyglot repo (TS site + Python agents). |
| Repo structure | All-in-one | 2026-04-18 | `research/` lives alongside `src/` in this repo. May split research to its own repo later. |
| Page builder | TS build script | 2026-04-18 | No LLM needed -- plain data transformation. |
| Schema source of truth | Zod (in Astro) | 2026-04-18 | Astro Content Collections enforce schemas at build time. JSON Schema files only if CI validation beyond Astro is needed later. |
| `as_of` granularity | Per-claim | 2026-04-18 | Add per-cell override later if needed |
| Sources visibility | Public pages | 2026-04-18 | Transparency aligns with TreadLightly ethos |
| Review cadence | 60 days default | 2026-04-18 | Pricing claims: 14-30 days. Policy claims: 90-180 days. |
| Content license | CC-BY-4.0 | 2026-04-18 | Code stays MIT |

## Follow-up: session 2026-04-22

Four features implemented (methodology page, confidence explainer, source type indicators + 146-file backfill, scope page). Two plans written (public participation forms, audit trail). All need browser testing and content review before being considered done. Scheduling decisions needed for Phase 4.6 vs 4.8 ordering and Phase 6 bundling.

**See [`docs/follow-up-2026-04-22.md`](follow-up-2026-04-22.md) for the full checklist.**

---

## Blockers

- **Custom domain in GitHub Pages UI** -- Cannot set `dangerousrobot.org` in Settings > Pages. DNS records are correct. May be a free-tier org limitation. See `TODO.md` for troubleshooting steps. **Does not block development work** -- site builds and deploys; the domain just doesn't resolve yet.

## Approved Issues

Open issues labeled `approved` are part of the backlog. Query them with:

    gh issue list --label approved --state open

When starting work on an approved issue, reference it in the relevant phase table (e.g., "Fixes #42"). Do not copy issue descriptions here -- the issue is the source of truth.

## MVP Milestone

Phases 1-4 constitute the MVP: a deployed site with structured research content, CI quality gates, governance docs, and agent-assisted content ingestion.

1. Define schemas (Zod in `src/content.config.ts`) -- done
2. Create 2-3 real content files in `research/` -- done
3. Add Astro page templates for claims, sources, entities -- done
4. Deploy via existing `deploy.yml` -- done
5. CI pipeline with build, lint, and citation checks -- done
6. Plan lifecycle rules, architecture docs, repo governance -- done
7. PydanticAI agent pipeline for source ingestion and verdict consistency checks -- done

### MVP complete

All MVP phases (1-4) are implemented and extended. The `pipeline/` package has 171 passing unit tests across shared infrastructure, ingestor, researcher, analyst, auditor, orchestrator, and entity onboarding. Single `dr` CLI entry point.

---

## Phase 1: Foundation (done)

Repo hygiene: CLAUDE.md, LICENSE-CONTENT, CONTRIBUTING.md. See [repo-hygiene.md](plans/completed/repo-hygiene.md).

---

## Phase 2: Schemas, Content & Site (done)

Zod schemas in `src/content.config.ts`, 5 entities, 9 sources, 4 claims. See [research-schemas.md](plans/completed/research-schemas.md), [astro-site.md](plans/completed/astro-site.md), [content-seeding.md](plans/completed/content-seeding.md).

Content expansion opportunity: chatbot comparison table, AI Product Card data, and 12 URLs exist in `parallax-ai` that can be structured. See TODO.md "Deferred Content."

---

## Phase 3: CI & Quality (done)

CI pipeline: build + markdownlint + citation integrity check. See [ci-pipeline.md](plans/completed/ci-pipeline.md).

---

## Phase 3.5: Repo Governance & Documentation (done)

Plan lifecycle rules, architecture docs (`docs/architecture/`), completed plan migration, public feedback plan review. See [initial-setup-workflow.md](plans/completed/initial-setup-workflow.md) for historical context.

---

## Cross-cutting: Naming Conventions (done)

Consistent vocabulary across the project: `recheck_cadence_days` field rename, `agents/` to `pipeline/` directory rename. See [naming-conventions.md](plans/completed/naming-conventions.md).

---

## Phase 4: Agent Pipeline (done)

PydanticAI agents for source ingestion and LLM-assisted content validation. See [agent-pipeline.md](plans/completed/agent-pipeline.md) (parent), [agent-pipeline-ingestor.md](plans/completed/agent-pipeline-ingestor.md) (4.1), [narrative-verdict-consistency.md](plans/completed/narrative-verdict-consistency.md) (4.2), [verify-claim-poc.md](plans/completed/verify-claim-poc.md) (POC orchestrator).

**Phase 4.5: Pipeline Refactor + Entity Onboarding (done)**

Full pipeline refactor: agents promoted to top-level packages (`researcher/`, `ingestor/`, `analyst/`, `auditor/`), instruction files extracted to `instructions.md`, human-in-the-loop checkpoints added, four CLIs consolidated into a single `dr` command. See [pipeline-agent-refactor.md](plans/completed/pipeline-agent-refactor.md).

Added entity onboarding pipeline (`dr onboard`): standardized claim templates data layer, `onboard_entity()` orchestrator that runs all applicable templates through the research pipeline, writes entity + claim files, and supports interactive operator approval. 171 unit tests passing.

---

## Phase 4.6: Pipeline performance & hardening

**Goal**: Reduce onboarding wall time and wasted API calls. Observed during live `dr onboard` runs that terminal output crawled while 30s+ fetches piled up on known-403 domains, and the per-template loop was serial. Cross-reviewed plans cover the top five wins.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 4.6.1 | Reuse verify_claim sources in onboard | [onboard-reuse-verify-sources.md](plans/onboard-reuse-verify-sources.md) | not started | Eliminates duplicate research+ingest per template (~2x per-template speedup) |
| 4.6.2 | Ingestor fail-fast on 401/403/451 | [ingestor-fail-fast-403.md](plans/ingestor-fail-fast-403.md) | not started | Terminal exception short-circuits PydanticAI agent run; no wayback escalation |
| 4.6.3 | Researcher host blocklist | [researcher-host-blocklist.md](plans/researcher-host-blocklist.md) | not started | `research/blocklist.yaml` filters LinkedIn/WSJ/FT/etc before ingest |
| 4.6.4 | Tighten ingestor timeouts | [ingestor-tighten-timeouts.md](plans/ingestor-tighten-timeouts.md) | not started | `httpx.Timeout(connect=5, read=15, …)`; agent wrapper 90s → 60s |
| 4.6.5 | Parallelize onboard templates | [onboard-parallelize-templates.md](plans/onboard-parallelize-templates.md) | not started | `asyncio.Semaphore(3)`-guarded gather; interactive mode clamps to 1 |

Recommended implementation order: 4.6.1 → 4.6.2 → 4.6.3 → 4.6.4 → 4.6.5 (the parallelism plan benefits most from the others landing first).

---

## Phase 4.7: Site IA, detail views, and tokenized CSS (done)

Browsable research hub: companies, products, claims, standards, topics list/detail pages with filter bars, standards matrix, cross-links, and tokenized CSS + a11y control (light/dark/high-contrast, font scale, FAB). See [entity-views.md](plans/entity-views.md) and [a11y-tokens.md](plans/a11y-tokens.md).

---

## Ops Runbook

**Goal**: A single reference doc (`docs/RUNBOOK.md`) covering the dev loop, pipeline operations, deploy process, and content schema changes. Currently undocumented — operators must piece this together from CLAUDE.md and code.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| — | Write RUNBOOK.md | — | not started | Dev loop (HMR, restart triggers), `dr` CLI reference, deploy steps, schema change checklist |
| — | Expand source `kind` enum | — | not started | Add `statement` (social posts, press releases, direct submissions) and `filing` (company invoices, certificates, contracts) as self-reported unverified evidence types. Both get `source_type: primary`. Schema change touches `content.config.ts`, pipeline `SourceFrontmatter`, and `_classify_source_type`. |

---

## Phase 5 (if needed): Automation

**Goal**: Recurring audits, queue-based intake.

**Trigger**: Enough content exists that manual auditing is burdensome.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 5.1 | Automation & scheduling | [automation.md](plans/automation.md) | not started | Scheduled workflows, QUEUE.md intake |

Downstream sync to parallax-ai moved to [future/downstream-sync.md](plans/future/downstream-sync.md) -- good idea, not needed now.

---

## Phase 4.8: AI Research Audit Trail

**Goal**: On each `/claims/[slug]` page, show a collapsible section with which agent ran the research, what sources were consulted, when a human reviewed it, and whether the verdict changed from draft. Builds reader trust by making the AI+human process visible.

Architecture: sidecar `.audit.yaml` file per claim, written by the pipeline after the auditor runs, consumed by a custom Astro loader. Full 3-stage architectural review completed.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 4.8.1 | Sidecar format + pipeline write + Astro loader + UI (Phase 1) | [feature-10-audit-trail.md](plans/feature-10-audit-trail.md) | not started | `_write_audit_sidecar` in persistence.py; `dr review --claim` CLI; collapsible UI |
| 4.8.2 | Extended audit fields + staleness check + orphan CI gate (Phase 2) | [feature-10-audit-trail.md](plans/feature-10-audit-trail.md) | not started | Requires: no stale sidecars, orphan check CI, backfill script |
| 4.8.3 | Append-only history (Phase 3) | [feature-10-audit-trail.md](plans/feature-10-audit-trail.md) | not started | Full recheck history per claim |

---

## Phase 6: Public Feedback & Contribution Gating

**Goal**: Members of the public can submit feedback on content without a GitHub account. GitHub issue/PR process is gated via templates that redirect content feedback to the site.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 6.1 | GitHub config + feedback form + Cloudflare backend | [public-feedback.md](plans/public-feedback.md) | not started | Issue templates, CODEOWNERS, Astro form, Worker + D1 + Turnstile, `api.dangerousrobot.org` |
| 6.2 | Admin CLI + GitHub issue promotion | [public-feedback.md](plans/public-feedback.md) | not started | `scripts/feedback-admin.ts`, accept/reject/inquire, Resend email |
| 6.3 | Admin dashboard (optional) | [public-feedback.md](plans/public-feedback.md) | not started | Web UI for reviewing submissions. Defer unless CLI proves insufficient. |
| 6.4 | Claim challenge form | [public-participation-forms.md](plans/public-participation-forms.md) | not started | Per-claim refutation form; extends 6.1 D1 schema + Worker |
| 6.5 | Request a claim form | [public-participation-forms.md](plans/public-participation-forms.md) | not started | Sitewide research request form |
| 6.6 | Propose a standard form | [public-participation-forms.md](plans/public-participation-forms.md) | not started | `/standards` form for new claim templates |

**Done when**: Public can submit feedback at `dangerousrobot.org/feedback`, admin can review via CLI, approved feedback becomes a GitHub issue.

---

## Phase Summary

```
Phase 1: Foundation             [repo-hygiene]
    |
Phase 2: Schemas + Site + Content  [research-schemas, astro-site, content-seeding]
    |
Phase 3: CI & Quality          [ci-pipeline]
    |
Phase 3.5: Governance & Docs   [plan lifecycle, architecture docs]
    |
Phase 4: Agents                [agent-pipeline]
    |                               ^^^ MVP milestone ^^^
    |
Phase 5 (if needed): Automation [automation, downstream-sync]
    |
Phase 6: Public Feedback        [public-feedback]
```

Phases 5-6 are not committed work. They exist as plans to avoid re-research.
