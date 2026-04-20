# Backlog: dangerousrobot.org

Last updated: 2026-04-19

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
7. PydanticAI agent pipeline for source ingestion and verdict consistency checks -- done

### MVP complete

All MVP phases (1-4) are implemented. The `pipeline/` package has 122 passing tests across shared infrastructure, ingestor agent, consistency check agent, and a proof-of-concept end-to-end verification orchestrator.

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

PydanticAI agents for source ingestion and LLM-assisted content validation. Shared infrastructure in `pipeline/common/`, ingestor in `pipeline/ingestor/`, consistency check in `pipeline/consistency/`. 122 tests passing. See [agent-pipeline.md](plans/completed/agent-pipeline.md) (parent), [agent-pipeline-ingestor.md](plans/completed/agent-pipeline-ingestor.md) (4.1), [narrative-verdict-consistency.md](plans/completed/narrative-verdict-consistency.md) (4.2).

Also includes a POC end-to-end verification orchestrator (`pipeline/verify/`) that chains research, ingest, draft, and consistency check agents. See [verify-claim-poc.md](plans/completed/verify-claim-poc.md).

---

## Phase 5 (if needed): Automation

**Goal**: Recurring audits, queue-based intake.

**Trigger**: Enough content exists that manual auditing is burdensome.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 5.1 | Automation & scheduling | [automation.md](plans/automation.md) | not started | Scheduled workflows, QUEUE.md intake |

Downstream sync to parallax-ai moved to [future/downstream-sync.md](plans/future/downstream-sync.md) -- good idea, not needed now.

---

## Phase 6: Public Feedback & Contribution Gating

**Goal**: Members of the public can submit feedback on content without a GitHub account. GitHub issue/PR process is gated via templates that redirect content feedback to the site.

| # | Work Item | Plan | Status | Notes |
|---|-----------|------|--------|-------|
| 6.1 | GitHub config + feedback form + Cloudflare backend | [public-feedback.md](plans/public-feedback.md) | not started | Issue templates, CODEOWNERS, Astro form, Worker + D1 + Turnstile, `api.dangerousrobot.org` |
| 6.2 | Admin CLI + GitHub issue promotion | [public-feedback.md](plans/public-feedback.md) | not started | `scripts/feedback-admin.ts`, accept/reject/inquire, Resend email |
| 6.3 | Admin dashboard (optional) | [public-feedback.md](plans/public-feedback.md) | not started | Web UI for reviewing submissions. Defer unless CLI proves insufficient. |

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
