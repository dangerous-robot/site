# History

Completed phases and resolved decisions for dangerousrobot.org. Detailed records live in `docs/plans/completed/` and git history.

---

## Completed phases

### Phase 1: Foundation (done)

Repo hygiene: CLAUDE.md, LICENSE-CONTENT, CONTRIBUTING.md. See [repo-hygiene.md](plans/completed/repo-hygiene.md).

### Phase 2: Schemas, Content & Site (done)

Zod schemas in `src/content.config.ts`, 5 entities, 9 sources, 4 claims. See [research-schemas.md](plans/completed/research-schemas.md), [astro-site.md](plans/completed/astro-site.md), [content-seeding.md](plans/completed/content-seeding.md).

### Phase 3: CI & Quality (done)

CI pipeline: build + markdownlint + citation integrity check. See [ci-pipeline.md](plans/completed/ci-pipeline.md).

### Phase 3.5: Repo Governance & Documentation (done)

Plan lifecycle rules, architecture docs (`docs/architecture/`), completed plan migration, public feedback plan review. See [initial-setup-workflow.md](plans/completed/initial-setup-workflow.md).

### Cross-cutting: Naming Conventions (done)

Consistent vocabulary: `recheck_cadence_days` field rename, `agents/` to `pipeline/` directory rename. See [naming-conventions.md](plans/completed/naming-conventions.md).

### Phase 4: Agent Pipeline (done)

PydanticAI agents for source ingestion and LLM-assisted content validation. See [agent-pipeline.md](plans/completed/agent-pipeline.md) (parent), [agent-pipeline-ingestor.md](plans/completed/agent-pipeline-ingestor.md) (4.1), [narrative-verdict-consistency.md](plans/completed/narrative-verdict-consistency.md) (4.2), [verify-claim-poc.md](plans/completed/verify-claim-poc.md) (POC orchestrator).

### Phase 4.5: Pipeline Refactor + Entity Onboarding (done)

Full pipeline refactor: agents promoted to top-level packages (`researcher/`, `ingestor/`, `analyst/`, `auditor/`), instruction files extracted, human-in-the-loop checkpoints added, four CLIs consolidated into single `dr` command. Added entity onboarding pipeline (`dr onboard`) with standardized claim templates, `onboard_entity()` orchestrator, and interactive operator approval. 171 unit tests passing. See [pipeline-agent-refactor.md](plans/completed/pipeline-agent-refactor.md).

### Phase 4.7: Site IA, detail views, and tokenized CSS (done)

Browsable research hub: companies, products, claims, standards, topics list/detail pages with filter bars, standards matrix, cross-links, and tokenized CSS + a11y control (light/dark/high-contrast, font scale, FAB). See [entity-views.md](plans/entity-views.md) and [a11y-tokens.md](plans/a11y-tokens.md).

### MVP milestone (done)

All MVP phases (1-4) implemented and extended. The `pipeline/` package has 171 passing unit tests across shared infrastructure, ingestor, researcher, analyst, auditor, orchestrator, and entity onboarding. Single `dr` CLI entry point.

---

## Decisions

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

---

## Resolved blockers

- **GitHub Actions SHA pinning** -- Actions used mutable tags (`@v4`). Bumped to node22-compatible versions (commit `1e1335f`).
