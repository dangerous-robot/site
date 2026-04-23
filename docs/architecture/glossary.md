# Project Glossary

Canonical vocabulary for the dangerousrobot.org project. See also [AGENTS.md](../../AGENTS.md) for role definitions and content rules.

## Research Objects

| Term | What it is | Lives at |
|---|---|---|
| **Entity** | A stable subject (company, product, sector, or topic) that claims are about | `research/entities/{type}/{slug}.md` |
| **Claim** | A single factual assertion with a verdict, confidence, evidence links, and recheck schedule | `research/claims/{entity-slug}/{claim-id}.md` |
| **Source** | A citable reference -- "cite once, reference many" | `research/sources/{yyyy}/{slug}.md` |
| **Criterion** | A reusable claim template applied uniformly across entities | `research/templates.yaml` |

## Research Object Fields

| Term | On | Meaning |
|---|---|---|
| **Verdict** | Claim | Assessment: true, mostly-true, mixed, mostly-false, false, unverified, not-applicable |
| **Confidence** | Claim | Certainty level: high, medium, low |
| **Category** | Claim | Taxonomy: ai-safety, environmental-impact, product-comparison, etc. (8 total) |
| **Kind** | Source | Classification: report, article, documentation, dataset, blog, video, index |
| **as_of** | Claim | Date when verdict was last evaluated |
| **recheck_cadence_days** | Claim | Days between scheduled re-evaluations (default 60) |
| **criteria_slug** | Claim | Optional back-reference linking a claim to the criterion template it was generated from |

## Roles

Roles describe *what* should happen. They can be filled by humans or automation. Defined in [AGENTS.md](../../AGENTS.md).

| Role | Responsibility |
|---|---|
| **Research Lead** | Orchestrator; assigns tasks, never edits claims directly |
| **Researcher** | Finds relevant URLs for a given claim topic |
| **Ingestor** | Converts a URL into a source file |
| **Analyst** | Proposes verdict and narrative given a claim and its sources |
| **Auditor** | Provides an independent second opinion on the analyst's output |
| **Citation Auditor** | Finds claims with zero sources, stale dates, broken references |
| **Page Builder** | Generates TypeScript data files for downstream consumption |

## Pipeline

The pipeline implements roles as runnable code. Lives in `pipeline/`.

| Term | Meaning |
|---|---|
| **Researcher agent** | Takes claim text, returns relevant URLs (`pipeline/researcher/`) |
| **Ingestor agent** | Takes a URL, produces a source file (`pipeline/ingestor/`) |
| **Analyst agent** | Takes sources + claim, produces verdict + narrative (`pipeline/analyst/`) |
| **Auditor agent** | Independent second-opinion assessment (`pipeline/auditor/`) |
| **Orchestrator** | Routes claim work through the four agents (`pipeline/orchestrator/`) |
| **Pipeline** | The collective automation: agents + CLI + shared utilities |

## Lifecycle

| Term | Meaning |
|---|---|
| **Queue** | Intake list of URLs/topics to process (`QUEUE.md`) |
| **Ingest** | Fetching a URL, archiving it, producing a source file |
| **Recheck** | Scheduled re-evaluation of a claim per `recheck_cadence_days` |
| **Submitted claim** | A claim proposed through public feedback (planned feature, pending public-participation work), pending review |

## Governance Rules

| Term | Meaning |
|---|---|
| **Content rules** | Constraints on research objects (e.g., summary word limits, citation requirements) |
| **Schema authority** | Zod in `content.config.ts` is the single source of truth for field shapes |
| **Plan lifecycle** | `docs/plans/drafts/` -> `docs/plans/` -> `docs/plans/completed/` |
| **AGENTS.md** | Defines roles, content rules, and schema authority |

## Vocabulary Layers

| Layer | Collective noun | Examples |
|---|---|---|
| Content | "research objects" | entity, claim, source |
| People/AI doing work | "roles" (defined in AGENTS.md) | Research Lead, Ingestor |
| Python automation | "pipeline" (code in `pipeline/`) | researcher agent, ingestor agent, analyst agent, auditor agent |
| Constraints/policies | "governance rules" | content rules, schema authority, plan lifecycle |
| Verification | "tests" (code) / "checks" (CI/content) | unit tests, citation check, build validation |

## Tests and Checks

| Term | Meaning |
|---|---|
| **Build validation** | Zod schemas enforced during `astro build` |
| **Citation check** | CI verification that source slugs in claims resolve to real files |
| **Markdown lint** | CI verification of Markdown formatting |
| **Unit/integration tests** | pytest tests for pipeline code (runners, models, tools) |

## Infrastructure

| Term | Meaning |
|---|---|
| **Content Collection** | Astro's system for loading research Markdown as typed data |
| **Zod schema** | TypeScript schema in `content.config.ts` defining valid frontmatter |
| **Pydantic model** | Python mirror of Zod schema, used by pipeline runners |
