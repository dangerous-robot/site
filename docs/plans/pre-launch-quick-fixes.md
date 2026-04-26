# Pre-launch quick fixes

**Status**: Ready
**Last updated**: 2026-04-24

A bundle of small reader-facing and operator-vocabulary fixes generated from the 2026-04-24 pre-launch triage. Each item is shippable in under a day. Larger items from the same triage are tracked in their own stub plans (see Cross-references).

> **Note (2026-04-26)**: P1 (Citation Auditor → "citation check") and ST4 (Page Builder removal) are bundled with the [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md) PR per its Dependencies section. They land via Lanes A and B of that plan rather than being re-done here.

## Goal

Land the cluster of small pre-launch polish items before tagging v0.1.0. Items are grouped by surface (reader-facing site, glossary/docs, content). Each is independently revertible.

## Scope

### Reader-facing site

| ID | Item | Files |
|---|---|---|
| S1 | ALPHA banner sitewide | `src/layouts/Base.astro` |
| S2 | Curate launch claim set to ~20 (random selection); homepage and list pages already filter to `status: published` | content; verify filtering on `src/pages/index.astro`, `src/pages/claims/index.astro` |
| S3 | COI disclosure on `/methodology` and `companies/treadlightlyai` (also on v0.1.0-roadmap §7) | methodology page, `research/entities/companies/treadlightlyai.md` |
| S4 | Create `/values` editorial page (uncited; cross-link to relevant claim categories per Q9). Note: page should include the public design principle paragraph as one of its core values entries (per [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md) Canonical paragraphs → Design principle (public, for `/values`)). | new `src/pages/values.astro` |
| S5 | Surface a consolidated pipeline diagram inside FAQ accordion or on `/methodology` | `src/pages/faq/index.astro` or `src/pages/methodology.astro`. Source: `docs/architecture/research-flow.md` (5 Mermaid diagrams already exist; pick one) |
| S6 | Audit sidecar: lock `models_used` field in schema and display on claim page | `src/content.config.ts`, `src/pages/claims/[...slug].astro`, `pipeline/orchestrator/persistence.py`. **Timing critical**: no `.audit.yaml` files exist yet (per roadmap §10). Lock the schema before the first sidecar is written. |
| S7 | Inputs taxonomy block on FAQ ("how does work enter this site?") listing the six intake types | `src/pages/faq/index.astro` |
| S8 | Reader-takeaway line under verdict badge (a single sentence: "what this means for the reader") | `src/pages/claims/[...slug].astro` + new optional frontmatter field, e.g., `takeaway:` |
| S9 | Footer links to `/values` and `/methodology` | `src/layouts/Base.astro` |

### Glossary, AGENTS.md, vocabulary, removals

| ID | Item | Files |
|---|---|---|
| P1 | Rename "Citation Auditor" → "citation check" (the CI integrity check). Resolves the three-way "audit" overload (audit sidecar / Citation Auditor / Auditor agent). | `AGENTS.md`, `docs/architecture/glossary.md`, `scripts/check-citations.ts` (script name already aligns), any plan/doc references |
| P2 | Rename `dr research` → `dr verify-claim`. Footgun: the command runs the entire pipeline, not just the Researcher role. | `pipeline/orchestrator/cli.py`, `AGENTS.md`, `docs/architecture/research-flow.md`, `docs/architecture/research-workflow.md`, smoke tests |
| P3 | Document model-tier discipline (small-by-default; medium for judgement; large rarely) in glossary + AGENTS.md | `AGENTS.md`, `docs/architecture/glossary.md`. Companion to S6 display. |
| P5 | Roadmap cleanup: visibly separate hard launch blockers from nice-to-haves | `docs/plans/v0.1.0-roadmap.md` |
| P6 | Glossary: add "Vocabulary layers" reader-facing summary mapping role ↔ pipeline agent ↔ CLI command | `docs/architecture/glossary.md` |
| ST4 | Remove "Page Builder" role from everywhere (operator: causing confusion) | `AGENTS.md` (role table), `docs/architecture/glossary.md` (Roles table), any other `rg "Page Builder"` hits |
| ST5 | Define what `high` / `medium` / `low` confidence concretely mean; render rubric on `/methodology` | `src/pages/methodology.astro`; reference from claim pages |

## Implementation notes

- **S6 timing critical** (repeated for emphasis). Lock `models_used` in `audit_sidecar` schema BEFORE the first `.audit.yaml` is written. No backfill needed if the first write produces the locked shape. Q4 (model-tier rubric) does not need to be answered to land the field — it's just metadata.
- **S5 source material**: `docs/architecture/research-flow.md` already has 5 Mermaid diagrams. The most reader-friendly one is the pipeline-execution sequence; the most rigorous is the claim-lifecycle state machine. Pick one for v1.
- **P1 naming**: "citation check" is suggested. Alternatives: "citation lint", "citation integrity check". The script `scripts/check-citations.ts` already aligns with "citation check"; pick that for least churn.
- **P2 naming**: "verify-claim" is suggested. Note `dr verify` already exists for verifying a known claim+entity pair, so the new name needs to not collide. Alternatives: `dr investigate`, `dr research-claim`. Decide before P2 lands.
- **S2 (curation)**: operator picks the set. No script needed; mark out-of-scope claims with `status: archived` or remove. Verify the homepage and `/claims/` index already filter to published (per roadmap §2; should be done).
- **ST4 (Page Builder removal)**: run `rg "Page Builder" -n` first to confirm scope before edits. Known hits: `AGENTS.md` agent-roles table, `docs/architecture/glossary.md` Roles table.
- **P5 cleanup**: this is a small editorial pass on `v0.1.0-roadmap.md`. Move "decision needed" and "future" items out of the active checklist; the only items in the release-criteria block at the top should be true launch blockers.

## Out of scope

The following triage items are NOT in this plan; they have their own plans or destinations:

- Vocabulary cohesion deeper pass beyond P1+P2 → [`vocab-rename-pass_stub.md`](vocab-rename-pass_stub.md)
- Acceptance test fixture (Anthropic/Claude per Q8) → [`acceptance-test-fixture_stub.md`](acceptance-test-fixture_stub.md)
- Source trust metadata (4 axes) → [`source-trust-metadata_stub.md`](source-trust-metadata_stub.md)
- Multi-provider plan (Infomaniak first; GreenPT considered) → existing [`multi-provider.md`](multi-provider.md)
- Polarity normalization (Q2) → [`docs/pre-launch-questions.md`](../pre-launch-questions.md)
- Operator queue + batch workflow → [`operator-queue-batch-workflow_stub.md`](operator-queue-batch-workflow_stub.md) (v2)
- Data lifecycle policy → [`data-lifecycle-policy_stub.md`](data-lifecycle-policy_stub.md) (v2)

## Verification checklist

After all items in scope land:

1. `inv check` (build + lint + tests) passes.
2. Homepage shows ALPHA banner; only `published` claims visible.
3. `/values` exists, is uncited, links back to relevant claim categories.
4. Pipeline diagram visible on `/faq` or `/methodology`.
5. A new claim run produces an audit sidecar containing `models_used`.
6. Claim pages show a one-line takeaway under the verdict badge.
7. `rg "Citation Auditor" -n` zero hits in `AGENTS.md`, `docs/`, `scripts/`.
8. `rg "dr research" -n` zero hits in `pipeline/`, `docs/`, scripts (allow `dr verify-claim` instead).
9. `rg "Page Builder" -n` zero hits.
10. Footer shows `/values` and `/methodology` links.

## Cross-references

| Triage ID | Where it landed |
|---|---|
| S1–S9, P1, P2, P3, P5, P6, ST4, ST5 | This plan |
| ST1 source trust metadata | [`source-trust-metadata_stub.md`](source-trust-metadata_stub.md) |
| P4 acceptance test fixture | [`acceptance-test-fixture_stub.md`](acceptance-test-fixture_stub.md) |
| PT4 vocab cohesion deeper pass | [`vocab-rename-pass_stub.md`](vocab-rename-pass_stub.md) |
| Multi-provider plan | [`multi-provider.md`](multi-provider.md) |
| ST2 polarity normalization | [Q2](../pre-launch-questions.md) |
| ST3 in-page feedback | [`public-feedback.md`](public-feedback.md) (v2) |
| PT1 operator queue + batch | [`operator-queue-batch-workflow_stub.md`](operator-queue-batch-workflow_stub.md) (v2) |
| PT2 data lifecycle policy | [`data-lifecycle-policy_stub.md`](data-lifecycle-policy_stub.md) (v2) |
| PT3 source-triggered reassessment | UNSCHEDULED.md (v2) |
| Q11 show-your-work panel | in flight per operator |

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-24 | agent (claude-opus-4-7) | basic, generated from triage | Initial scaffold from operator brain-dump and triage answers |
