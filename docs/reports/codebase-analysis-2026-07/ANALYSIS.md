# Codebase analysis: dangerousrobot.org

An adversarial architecture review of the site (Astro 6, `src/`) and the research pipeline
that feeds it (Python/PydanticAI, `pipeline/`), including the research flow and schemas —
not the research content itself. Method, data sources, and how to regenerate everything are
in [`README.md`](README.md). Full detail lives in the data files and the three interactive
artifacts linked there; this document is the narrative synthesis.

**Pipeline:** 16 subsystem/pattern/taxonomy analysts, each required to cite verbatim
evidence and propose a concrete alternative → mechanical evidence-grep screen → 16
refute-minded verifiers (independent of the original analyst) → 13 clean-slate designs each
stress-tested by a separate skeptic for dependency reality and honest migration cost. 188
findings raised, 185 survived verification (3 rejected as overstated, kept visible in
[`data/findings.json`](data/findings.json) as the audit trail).

## The one-sentence version

The architecture's central bet — a static site reading Markdown+YAML that a Python pipeline
writes, with Git as the audit trail — is sound and the review's strongest evidence-backed
conclusion. Two decisions fight it: a hand-copied schema at the pipeline/site boundary that
only fails *after* the write, and an orchestrator that grew into two 2,000+ line files
instead of the small step-workers the project's own vision doc asks for. Fix the boundary
and split the orchestrator; the rest is real but secondary.

## Architectural shape

```
Operator --dr CLI--> pipeline/ (4 PydanticAI agents) --writes--> research/ (Markdown+YAML)
                                                                        |
                                                                   reads at build
                                                                        v
                                                          src/ (Astro 6, Zod schemas) --> dist/ --> GitHub Pages
```

Full diagrams (L1 context, L2 containers current/proposed, L3 focal views, sequence and
state-machine comparisons) are in [`diagrams/architecture.md`](diagrams/architecture.md) and
[`diagrams/flows.md`](diagrams/flows.md); the same structure is explorable interactively in
the **architecture explorer** artifact with a current-vs-proposed toggle.

The two stacks never call each other. They agree only by convention: whatever the pipeline
writes to `research/`, the site's Zod schemas in `src/content.config.ts` must accept at
build time. That convention is enforced in exactly one place, after the fact.

## Congestion: where change is hardest

`data/metrics.json` combines churn (commits touching a file, full history), cyclomatic
complexity (lizard), and graphify graph centrality into a hotspot score. The top of the list
is unambiguous:

| Rank | File | Churn | Complexity (CCN) | Centrality |
|---|---|---|---|---|
| 1 | `pipeline/orchestrator/pipeline.py` | 77 commits | 288 | highest in the pipeline |
| 2 | `pipeline/orchestrator/cli.py` | 56 commits | 354 | high |
| 3 | `pipeline/orchestrator/persistence.py` | 36 commits | 95 | high |

These two files are the same congestion point seen from two sides: `pipeline.py` is the
verify/onboard engine, `cli.py` is the command surface that duplicates parts of it. Findings
**ORCH-01** (pipeline.py fuses three entry points and every step helper into one module) and
**OCLI-02**/**ORCH-02** (blocked/success claim persistence is duplicated across both files
and has *already diverged* — a blocked refresh drops failure diagnostics a fresh onboard
keeps) are the concrete cost of that duplication. This is not a hypothetical risk; it is a
bug in production today.

Everything downstream of these two files inherits their churn: `common/models.py` (the
enum/provider-gateway module, hotspot #8) and the CLI-adjacent test suites (#4, #7) all move
when the orchestrator moves.

## Pattern relationship: what's serving the project, what's fighting it

Full pattern list with evidence in `data/findings.json` `patterns`; six are load-bearing to
the review's conclusions.

**Serving the project:**
- **Blackboard architecture** (`research/` as the shared store) — the project's best
  architectural decision. Git history over the blackboard *is* the audit trail; human review
  is a file diff, not a database query.
- **Pipes-and-filters** — the four-stage pipeline (research → ingest → analyze → evaluate)
  gives each stage a typed, inspectable output.
- **Human-in-the-loop checkpoint** (the `CheckpointHandler` protocol) — well executed. It
  keeps the pipeline testable (`AutoApprove` swaps in for CI) while making human gates
  first-class rather than bolted on.
- **Static-site-as-read-model** — zero runtime attack surface, no cache-invalidation bug
  class, free hosting.

**Fighting the project:**
- **Schema-on-read without schema-on-write** (finding **SCH-01**, **PAT-01**) — the pipeline
  writes files with no schema check of its own; the only enforced contract is Zod, at site
  build, after the write already happened. A pipeline-written field the schema silently
  drops (confirmed: `research`, `sub_questions`, `pipeline_run.failure` in the audit
  sidecar) is invisible until someone happens to look.
- **Shotgun surgery** (finding **SCH-02**, **CMN-01**) — the claim vocabulary exists in 3-4
  hand-synced copies (Python enums, Zod schemas, the linter's field lists, display strings)
  guarded only by code comments. `data/enum-drift.json` shows 10 of 11 tracked enum pairs
  in sync today — real discipline, but discipline is not a mechanism, and drift has already
  reached `VerdictSeverity` (Python-only) and several sidecar fields.
- **God file** (`pipeline.py`, `cli.py`) — see Congestion above. The project's own
  `docs/architecture/vision-state-machine.md` names "composable, not orchestrated, no
  monolithic orchestrator" as the target shape this violates.
- **Leaky abstraction at the provider gateway** — every LLM-provider quirk fix lands in
  `pipeline.py` (the #1 hotspot) instead of the adapter that's supposed to own it.
- **Parallel hierarchies** (docs/roles vs. packages/files) — the Evaluator/`auditor`
  naming split alone costs every contributor (human or agent) a translation step on every
  session; see Taxonomy below.

**Checked and *not* found:** a global Big Ball of Mud. Even the two god-files are
structured monoliths with clear internal seams, not undifferentiated tangle — the honest
adversarial answer here is "no," which is itself useful signal.

## If it were rebuilt today

Each of the 13 subsystems got an independent "if rebuilt today" design, then an independent
skeptic tried to break it (dependency reality, honest migration cost, "does a simpler
version capture most of the value"). **Every one of the 13 came back `adapt`** — sound
direction, no proposal survived unmodified. That pattern is itself a finding: this is a
codebase with real structural problems and no easy full rewrites.

The whole-system version, **"Git-ledger research system"** (from the pattern-mapper agent):
keep the three decisions that carry the mission — Markdown-in-Git as the auditable store, a
fully static site, checkpoints that never auto-resolve — and replace the two that fight it:

1. **One generated schema.** A single committed contract (Zod exported to JSON Schema, or
   JSON Schema authored directly) generates the Python models, the Astro Zod schemas, and
   the linter's field sets. CI fails if any generated copy goes stale.
2. **Stateless step workers.** Four workers (research, ingest, analyze, evaluate), each
   declaring a pre-condition on claim state and a post-condition. A thin driver (the CLI
   today, a scheduler later) finds claims matching a pre-condition and runs the step.

The skeptic's stress test (`data/findings.json` → `clean_slates` → `pattern-mapper`) is
worth reading before adopting this: the codegen toolchain (`zod-to-json-schema`,
`datamodel-code-generator`) is real but not yet a dependency; `models.py` also holds
hand-written provider logic that codegen cannot produce, and the design doesn't say how
that coexists with generated enums; the append-only event log grows every Git diff and the
review surface. The per-subsystem designs (also all `adapt`) are individually smaller and
lower-risk — see the **findings dashboard** artifact, filtered to `category: pattern`, for
all 13 with their corrections attached.

## Taxonomy: where the words stop meaning one thing

Full concept table, sample quotes, and a proposed glossary are in
[`data/terminology.json`](data/terminology.json) and the **taxonomy explorer** artifact.
32 concepts tracked; every one carries a genuine collision or multi-name spread. The four
with the widest blast radius:

| Concept | Names in play | Where |
|---|---|---|
| The independent-check agent | Evaluator (docs, AGENTS.md), `auditor` (package, CLI `dr step-audit`), `reassess` (deprecated alias), `IndependentAssessment` (type) | Docs, code, CLI — 8 names total (**TAXC-01-dup2**) |
| Claim taxonomy tag | `Category` (Python enum class), `topics` (frontmatter field + Zod schema) | Python/TS boundary, exact split (**TAXC-01**) |
| Reusable claim spec | `criterion` (object), `templates.yaml` (file), "Criteria" (UI label) | Three names, one thing (**TAXC-08**) |
| "Verification" | `verification_level` (claim: source diversity) vs. `verification_status` (entity: identity) | Same word, two unrelated fields (**TAXR-02**) |

Two structural notes beyond individual terms:
- **`docs/reader-glossary.md` is a one-term stub** (RECs only, self-labeled "not yet wired
  into the site") sitting next to a 2,901-word `docs/architecture/glossary.md`. There is no
  overlap between them to conflict — the reader-facing glossary simply doesn't exist yet.
- **Dual branding is live in `src/` simultaneously**: nav and several pages show
  "TreadLightly AI" / "BETA RELEASE," while SEO metadata, breadcrumbs, and most docs say
  "Dangerous Robot" / dangerousrobot.org. Whichever is intended, a reader hits both.

The taxonomy explorer artifact turns this table into something a contributor can actually
use: search a term, see every variant, its layer, a verbatim occurrence, and the recommended
canonical form with a blast-radius note (how many files/layers a rename touches).

## Documentation accuracy

`docs/architecture/` is unusually well-maintained and self-flags most known gaps (the
Router package, the auditor/Evaluator rename, are called out in the docs themselves).
Confirmed problems the docs don't flag:

- **AGENTS.md contradicts running code** on two operational claims: arXiv search is
  documented "off by default" but is on by default, and the CLI reference table lists a
  command that doesn't exist (**DOCS-01**).
- **"Small decisions, small models"** is asserted as the operating model, but every agent
  defaults to the same model with no tier enforcement — the docs themselves concede this is
  "testable design intent," not current behavior (**DOCS-02**).
- **Role/status tables live in six places** and have already produced a contradiction (a
  "Citation Auditor" role referenced in one doc, absent from code) (**DOCS-04**).
- **`docs/UNSCHEDULED.md` links into a gitignored `drafts/` directory four times** — those
  designs exist on one machine and nowhere else in the repo (**DOCS-05**).
- **Six shipped plans still sit in active `docs/plans/`** rather than `completed/`, because
  the plan lifecycle has no rule for the tail end (**DOCS-07**).

## Testing gaps

- **The pipeline's ~46-file pytest suite never runs in CI** — only `inv check` runs it, and
  nothing requires a contributor to run `inv check` before merging (**TESTS-01**).
- **Vacuous assertions**: several tests assert inside an `if` guard that can silently become
  false, at which point the test stops testing anything and still passes (**TESTS-02**,
  confirmed by the verifier with a live CLI run).
- **The god-file CLI commands (`step-audit`, `step-research`, `step-analyze`, `reassess`)
  have zero test coverage** — exactly the commands findings AT-02/OCLI-02 show diverging
  from the main path (**TESTS-04**).

## Prioritized recommendations

Ranked by (severity × how many other confirmed findings reference the same root cause), not
by ease. Full list with effort/impact/migration sketch per item: findings dashboard,
`severity: high`.

1. **Fix the write-side/read-side schema gap** (SCH-01, CMN-01, PAT-01, TAXC-01). One
   generated contract, checked at write time, not discovered at build time. This is the
   single highest-leverage change — it also resolves the Category/topics and
   auditor/Evaluator naming splits as a side effect of picking one name per generated field.
2. **Split `orchestrator/pipeline.py` and `orchestrator/cli.py`** (ORCH-01, ORCH-02, OCLI-02,
   AT-02). Extract the shared persistence function first (cheap, fixes the diverged
   blocked-refresh bug immediately); route `step-*` commands through the same engine calls
   as the main path.
3. **Wire the pytest suite into CI** (TESTS-01). One workflow-file change; unblocks catching
   regressions in the two hotspot files before merge instead of after.
4. **Fix the onboarding data-loss bug** (ORCH-03: dedup-cached source ids dropped from
   written claim files) and the vacuous test assertions that would have caught it
   (TESTS-02).
5. **Reconcile AGENTS.md against running code** (DOCS-01, DOCS-02) and move the six
   shipped plans out of active `docs/plans/` (DOCS-07) — both cheap, both compounding
   (every session, human or agent, currently onboards from a doc that's wrong in
   specific, checkable ways).

## What this analysis did not cover

- `research/` content itself (claims, sources, entities) — by design; schemas and flow were
  in scope, the 5 claims / 36 sources / 14 entities currently on disk were not evaluated for
  accuracy. `data/data-conformance.json` has the mechanical shape check (frontmatter
  coverage, sidecar pairing, enum-value violations — none found in the current small
  corpus).
- Runtime/performance profiling — this review is static (code, docs, git history, the
  graphify structural graph); no pipeline run or site build was profiled for speed.
- Security review — out of scope for this pass; flag separately if wanted.
