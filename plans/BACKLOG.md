# Backlog: dangerousrobot.org

Last updated: 2026-04-18 (session 2)

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
7. PydanticAI agent pipeline for source ingestion and verdict consistency checks -- not started

### Remaining MVP work

Phase 4 is the only remaining MVP phase. Two work items:

- **4.1 Ingestor agent**: Takes a URL and produces a valid source file. Plans: [agent-pipeline.md](agent-pipeline.md) (parent), [agent-pipeline-ingestor.md](agent-pipeline-ingestor.md) (detailed).
- **4.2 Narrative-verdict consistency check**: LLM-assisted validation comparing independent assessment against claim verdicts. Plan: [narrative-verdict-consistency.md](narrative-verdict-consistency.md). Depends on 4.1 shared infrastructure.

**Done when**: Ingestor agent produces a valid source file from a URL, AND consistency checker runs against all claims and produces a classified report.

---

## Phase 1: Foundation (done)

Repo hygiene: CLAUDE.md, LICENSE-CONTENT, CONTRIBUTING.md. See [repo-hygiene.md](completed/repo-hygiene.md).

---

## Phase 2: Schemas, Content & Site (done)

Zod schemas in `src/content.config.ts`, 3 entities, 5 sources, 3 claims. Build produces 12 pages. See [research-schemas.md](completed/research-schemas.md), [astro-site.md](completed/astro-site.md), [content-seeding.md](completed/content-seeding.md).

Content expansion opportunity: chatbot comparison table, AI Product Card data, and 12 URLs exist in `parallax-ai` that can be structured. See TODO.md "Deferred Content."

---

## Phase 3: CI & Quality (done)

CI pipeline: build + markdownlint + citation integrity check. See [ci-pipeline.md](completed/ci-pipeline.md).

---

## Phase 3.5: Repo Governance & Documentation (done)

Plan lifecycle rules, architecture docs (`docs/architecture/`), completed plan migration, public feedback plan review. See [initial-setup-workflow.md](completed/initial-setup-workflow.md) for historical context.

---

## Phase 4: Agent Pipeline

**Goal**: PydanticAI agents automate source ingestion and provide LLM-assisted content validation.

**Prerequisites before starting**: Reconcile shared infrastructure (`pipeline/common/`) between 4.1 and 4.2 directory structures. Plans promoted.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 4.1 | Ingestor agent | [agent-pipeline-ingestor.md](agent-pipeline-ingestor.md) | not started | PydanticAI setup, Ingestor agent. Parent: [agent-pipeline.md](agent-pipeline.md). |
| 4.2 | Narrative-verdict consistency check | [narrative-verdict-consistency.md](narrative-verdict-consistency.md) | not started | Depends on 4.1 shared infra. |

**Done when**:
- 4.1: Ingestor agent takes a URL and produces a source file that passes `npm run build` validation. Test suite passes.
- 4.2: Consistency checker runs against all claims and produces a classified text/JSON report. Test suite passes.

---

## Phase 5 (if needed): Automation & Integration

**Goal**: Recurring audits, queue-based intake, downstream data sync to parallax-ai.

**Trigger**: Enough content exists that manual auditing is burdensome, and parallax-ai is ready to consume structured data.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 5.1 | Automation & scheduling | [automation.md](automation.md) | not started | Scheduled workflows, QUEUE.md intake |
| 5.2 | Downstream sync | [downstream-sync.md](downstream-sync.md) | not started | TS data generation, parallax-ai integration. Needs discovery spike first. |

**Parallelization**: 5.1 and 5.2 can run in parallel. 5.2 requires understanding parallax-ai's build process (open question).

---

## Phase 6: Public Feedback & Contribution Gating

**Goal**: Members of the public can submit feedback on content without a GitHub account. GitHub issue/PR process is gated via templates that redirect content feedback to the site.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 6.1 | GitHub config + feedback form + Cloudflare backend | [public-feedback.md](public-feedback.md) | not started | Issue templates, CODEOWNERS, Astro form, Worker + D1 + Turnstile, `api.dangerousrobot.org` |
| 6.2 | Admin CLI + GitHub issue promotion | [public-feedback.md](public-feedback.md) | not started | `scripts/feedback-admin.ts`, accept/reject/inquire, Resend email |
| 6.3 | Admin dashboard (optional) | [public-feedback.md](public-feedback.md) | not started | Web UI for reviewing submissions. Defer unless CLI proves insufficient. |

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
