# Backlog: dangerousrobot.org

Last updated: 2026-04-18 (session 2)

This file tracks the phased progression for standing up dangerousrobot.org. Each phase lists its work items with links to detailed plan files. Status is tracked here; details live in the individual plans.

## Guiding Principle

Defer big decisions about *what* to research. Focus on documenting the *types* of things that could be researched, and implement a small set to prove out the architecture end-to-end.

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

## Technical Risk to Spike Early

**Astro Content Collections outside `src/`**: The plan assumes Astro can load collections from `research/` (outside `src/`). Astro v5+ supports this via `base` in `defineCollection`, but it should be verified before building the schema layer. Run a quick spike: one collection pointing at `research/test.md`, confirm `npm run build` succeeds. If it fails, fallback options: symlinks, content under `src/content/`, or a copy step.

---

## MVP Milestone

The minimum viable path from placeholder to "site renders structured research content":

1. Define schemas (Zod in `src/content.config.ts`)
2. Create 2-3 real content files in `research/`
3. Add Astro page templates for claims, sources, entities
4. Deploy via existing `deploy.yml`

Everything below this line is post-MVP.

---

## Phase 1: Foundation

**Goal**: Repo documentation and licensing are accurate.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 1.1 | Repo hygiene | [repo-hygiene.md](completed/repo-hygiene.md) | done | Committed in `ac247c0` |

**Done.** CLAUDE.md updated, LICENSE-CONTENT created, CONTRIBUTING.md added, all files committed.

---

## Phase 2: Schemas, Content & Site (MVP)

**Goal**: Zod schemas defined, proof-of-concept content created, Astro renders it, site deploys.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 2.1 | Research schemas & structure | [research-schemas.md](completed/research-schemas.md) | done | Zod schemas in `src/content.config.ts`, directory scaffold, QUEUE.md |
| 2.2 | Astro site development | [astro-site.md](completed/astro-site.md) | done | Base layout, index, claim/source/entity detail pages |
| 2.3 | Content seeding | [content-seeding.md](completed/content-seeding.md) | done | 3 entities, 5 sources, 3 claims. Build produces 12 pages. |

**Done.** `npm run build` produces 12 pages. `npm run check` passes (build + lint + citations). Deployment blocked by GitHub Pages custom domain issue (see Blockers above) but does not affect development.

### Next: Expand content

More claims and sources exist in `parallax-ai` that can be structured:
- Chatbot comparison table (`parallax-ai/frontend/src/app/robot/responsible-ai/page.tsx`)
- AI Product Card data (`parallax-ai/frontend/src/app/transparency/page.tsx`)
- 12 URLs in `parallax-ai/docs/dangerous-robot/links-to-add.txt`

---

## Phase 3: CI & Quality (post-MVP)

**Goal**: PRs get automated feedback on content quality.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 3.1 | CI pipeline | [ci-pipeline.md](completed/ci-pipeline.md) | done | `.github/workflows/ci.yml`, markdownlint, `scripts/check-citations.ts` |

**Done.** PRs run build + markdown lint + citation integrity check via `npm run check`.

---

## Phase 3.5: Repo Governance & Documentation

**Goal**: Plan lifecycle rules, architecture docs, and agent instruction improvements.

| # | Work Item | Status | Notes |
|---|-----------|--------|-------|
| 3.5.1 | Plan lifecycle rules in AGENTS.md | done | Draft/final/completed directories, backlog update rules, approved issues integration |
| 3.5.2 | Architecture docs (`docs/architecture/`) | done | site.md, content-model.md, ci-deploy.md, research-workflow.md + README index |
| 3.5.3 | Move completed plans to `plans/completed/` | done | 5 plans moved: repo-hygiene, research-schemas, astro-site, content-seeding, ci-pipeline |
| 3.5.4 | Public feedback plan review | done | Security hardening, UX improvements, open source standards applied to `public-feedback.md` |

**Done.**

---

## Phase 4 (if needed): Agent Pipeline

**Goal**: PydanticAI agents automate source ingestion and citation auditing.

**Trigger**: Phase 2 content workflow proves too slow or error-prone for manual work. If manual works fine for the current scale, defer indefinitely.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 4.1 | Agent pipeline | [agent-pipeline.md](agent-pipeline.md) | not started | PydanticAI setup, Ingestor agent. Citation auditor is a deterministic script (see 3.1). |
| 4.2 | Narrative-verdict consistency check | -- | not started | LLM-assisted validation: feed claim body + sources (without frontmatter) to an LLM, compare its independent verdict/confidence assessment against the actual values. Disagreements surface claims for human review. |

**Done when**: Ingestor agent takes a URL and produces a valid source file.

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
    |                               ^^^ MVP milestone ^^^
    |
Phase 3: CI & Quality          [ci-pipeline]
    |
Phase 3.5: Governance & Docs   [plan lifecycle, architecture docs]
    |
Phase 4 (if needed): Agents    [agent-pipeline]
    |
Phase 5 (if needed): Automation [automation, downstream-sync]
    |
Phase 6: Public Feedback        [public-feedback]
```

Phases 4-6 are not committed work. They exist as plans to avoid re-research. The MVP is Phase 2.
