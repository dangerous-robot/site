# Backlog: dangerousrobot.org

Last updated: 2026-04-18

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
| 1.1 | Repo hygiene | [repo-hygiene.md](repo-hygiene.md) | not started | LICENSE-CONTENT, CLAUDE.md update, clean up deleted files |

**Parallelization**: Single work item. Quick -- most of it is already done (Astro installed, CNAME moved, files deleted in git).

**Done when**: CLAUDE.md is accurate, LICENSE-CONTENT exists, git status is clean.

---

## Phase 2: Schemas, Content & Site (MVP)

**Goal**: Zod schemas defined, proof-of-concept content created, Astro renders it, site deploys.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 2.1 | Research schemas & structure | [research-schemas.md](research-schemas.md) | not started | Category taxonomy, Zod schemas, directory scaffold |
| 2.2 | Astro site development | [astro-site.md](astro-site.md) | not started | Content collections, layouts, pages, DR visual identity |
| 2.3 | Content seeding | [content-seeding.md](content-seeding.md) | not started | 2-3 entities, 4-6 sources, 3-5 claims from seed data |

**Parallelization**: 2.1 and 2.2 should be co-authored (Zod schemas and content collections are the same design decision). 2.3 starts once schemas are stable. All three are tightly coupled -- this is one focused push.

**Done when**: `npm run build` produces pages from real research content. Site deploys to GitHub Pages. **This is the MVP.**

---

## Phase 3: CI & Quality (post-MVP)

**Goal**: PRs get automated feedback on content quality.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 3.1 | CI pipeline | [ci-pipeline.md](ci-pipeline.md) | not started | Build check, markdown lint, citation integrity script |

**Parallelization**: Can start as soon as Phase 2 content exists. Astro's Zod validation already catches schema errors at build time -- CI adds markdown lint and referential integrity checks.

**Done when**: PRs run `npm run build` + markdown lint + citation integrity check.

---

## Phase 4 (if needed): Agent Pipeline

**Goal**: PydanticAI agents automate source ingestion and citation auditing.

**Trigger**: Phase 2 content workflow proves too slow or error-prone for manual work. If manual works fine for the current scale, defer indefinitely.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 4.1 | Agent pipeline | [agent-pipeline.md](agent-pipeline.md) | not started | PydanticAI setup, Ingestor agent. Citation auditor is a deterministic script (see 3.1). |

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

## Phase Summary

```
Phase 1: Foundation             [repo-hygiene]
    |
Phase 2: Schemas + Site + Content  [research-schemas, astro-site, content-seeding]
    |                               ^^^ MVP milestone ^^^
    |
Phase 3: CI & Quality          [ci-pipeline]
    |
Phase 4 (if needed): Agents    [agent-pipeline]
    |
Phase 5 (if needed): Automation [automation, downstream-sync]
```

Phases 4 and 5 are speculative. They exist as plans to avoid re-research, but they are not committed work. The MVP is Phase 2.
