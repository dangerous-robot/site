# Pre-launch quick fixes

**Status**: Done — closed 2026-04-27. S5 (pipeline diagram) deferred as stretch; ST5 dropped (no /methodology page).
**Last updated**: 2026-04-27

A bundle of small reader-facing and operator-vocabulary fixes generated from the 2026-04-24 pre-launch triage. Each item is shippable in under a day. Larger items from the same triage are tracked in their own stub plans (see Cross-references).

> **Note (2026-04-26)**: P1 (Citation Auditor → "citation check") and ST4 (Page Builder removal) are bundled with the [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md) PR per its Dependencies section. They land via Lanes A and B of that plan rather than being re-done here.

> **Note (2026-04-27)**: This pass closes out the open items. **Done**: P2 (`dr research` → `dr verify-claim`), S3 (COI on `treadlightlyai` re-instated as a product entity), plus admin checkboxes for items already shipped (S4, S9, P1, ST4). **Stretch / not blocking v1**: S5 (pipeline diagram). **Dropped**: ST5 (confidence rubric — no `/methodology` page exists; the FAQ accordion covers methodology and rubric work moves to a future plan).

## Goal

Land the cluster of small pre-launch polish items before tagging v0.1.0. Items are grouped by surface (reader-facing site, glossary/docs, content). Each is independently revertible.

## Scope

### Reader-facing site

| ID | Item | Files |
|---|---|---|
| S1 | ALPHA banner sitewide | **Done (2026-04-26).** Top-of-body banner in `src/layouts/Base.astro` renders on every chrome variant; links to `/faq#methodology`. Uses `--color-accent` on `--color-surface` for theme/contrast compatibility. |
| S2 | Curate launch claim set; homepage and list pages already filter to `status: published`. **Replaced by deliberate tracking in [`research/v1-launch-set.md`](../../research/v1-launch-set.md)** (2026-04-27); not random. | content; verify filtering on `src/pages/index.astro`, `src/pages/claims/index.astro` |
| S3 | **Done (2026-04-27).** COI disclosure on the `treadlightlyai` product entity (`research/entities/products/treadlightlyai.md`) — entity was deleted then re-instated as a product. Inline blockquote points readers at `/faq#conflicts-of-interest`. Original "companies/treadlightlyai" target is obsolete; FAQ accordion already carries the canonical disclosure (covered by §7 in v1.0.0-roadmap). |
| S4 | **Done (commit `619dfe5`).** `/values` editorial page lives at `src/pages/values.astro` and includes the public design-principle paragraph. Footer link in `Base.astro:114`. |
| S5 | **Stretch — not a v1 blocker.** Surface a consolidated pipeline diagram inside FAQ accordion. Source: `docs/architecture/research-flow.md` (5 Mermaid diagrams already exist; pick one). FAQ already describes the pipeline in prose, which is enough for v1; the diagram is a polish item to land post-tag. |
| S6 | Audit sidecar: lock `models_used` field in schema and display on claim page | **Done (2026-04-26).** `models_used: dict[str, str]` written by `_write_audit_sidecar` (`pipeline/orchestrator/persistence.py`); optional in Astro schema (`src/content.config.ts`) so the 12 in-flight sidecars validate without it; rendered as a "Models used" subsection on the claim audit-trail (`src/pages/claims/[...slug].astro`). Optional now, will be promoted to required once all sidecars carry it. |
| S7 | Inputs taxonomy block on FAQ ("how does work enter this site?") listing the six intake types | **Done (2026-04-26).** New "How does work enter this site?" accordion in `src/pages/faq/index.astro`, six items: criterion / company-or-product / source / topic-or-URL drop / public source submission / public claim request (planned). Operator should review the list — the canonical "six" wasn't enumerated in the source plan, so this draws from the v1 workflow paragraph in [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md) plus the public submission paths. |
| S8 | Reader-takeaway line under verdict badge (a single sentence: "what this means for the reader") | **Done (2026-04-26).** Optional `takeaway: z.string().max(200).optional()` added to claim schema in `src/content.config.ts`; rendered as `<p class="takeaway">` under the meta row in `src/pages/claims/[...slug].astro` with a left-accent rule. Pipeline-side generation deferred — operators add the line by hand during review. |
| S9 | **Done.** Footer links to `/values` (`Base.astro:114`) and `/faq#methodology` (`Base.astro:116`). No standalone `/methodology` page exists; the FAQ accordion is the methodology surface. |

### Glossary, AGENTS.md, vocabulary, removals

| ID | Item | Files |
|---|---|---|
| P1 | **Done** (landed via [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md) bundle). Zero hits in `AGENTS.md`, `docs/architecture/glossary.md`, `scripts/check-citations.ts`. |
| P2 | **Done (2026-04-27).** `dr research` → `dr verify-claim` renamed in `pipeline/orchestrator/cli.py:217-225`, `pipeline/tests/test_cli_smoke.py:10`, `AGENTS.md:99,107,114,125`, `docs/architecture/glossary.md:59-62,150`, `docs/architecture/research-flow.md:17,21,28,52`, `docs/architecture/open-issues.md:58`. The internal `research_claim()` Python function name is unchanged (not externally visible). Smoke tests pass. |
| P3 | Document model-tier discipline (small-by-default; medium for judgement; large rarely) in glossary + AGENTS.md | **Done (2026-04-26).** Canonical statement at [`AGENTS.md` § How the system works](../../AGENTS.md) (line 17, "Small decisions, small models"). New "Model-tier discipline" subsection in `docs/architecture/glossary.md` cross-links to it and to the `models_used` audit field. Concrete tiers/enforcement deferred to Q4 in [`pre-launch-questions.md`](../pre-launch-questions.md). |
| P5 | Roadmap cleanup: visibly separate hard launch blockers from nice-to-haves | `docs/v1.0.0-roadmap.md` |
| P6 | Glossary: add "Vocabulary layers" reader-facing summary mapping role ↔ pipeline agent ↔ CLI command | **Done (2026-04-26).** New "Role / agent / CLI cross-walk" subsection in `docs/architecture/glossary.md`, placed above Roles, gives a single 7-row table covering all three vocabularies. (Heading renamed from "Vocabulary layers" to avoid collision with the existing meta-table further down.) |
| ST4 | **Done** (landed via [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md) bundle). Zero hits in `AGENTS.md` and `docs/architecture/glossary.md`. |
| ST5 | **Dropped (2026-04-27).** Confidence rubric placement assumed a `/methodology` page that does not exist (methodology lives in the FAQ accordion). Re-scope to a future plan if needed; not a v1 blocker. |

## Implementation notes

- **S6 timing critical** (repeated for emphasis). Lock `models_used` in `audit_sidecar` schema BEFORE the first `.audit.yaml` is written. No backfill needed if the first write produces the locked shape. Q4 (model-tier rubric) does not need to be answered to land the field — it's just metadata.
- **S5 source material**: `docs/architecture/research-flow.md` already has 5 Mermaid diagrams. The most reader-friendly one is the pipeline-execution sequence; the most rigorous is the claim-lifecycle state machine. Pick one for v1.
- **P1 naming**: "citation check" is suggested. Alternatives: "citation lint", "citation integrity check". The script `scripts/check-citations.ts` already aligns with "citation check"; pick that for least churn.
- **P2 naming**: "verify-claim" is suggested. Note `dr verify` already exists for verifying a known claim+entity pair, so the new name needs to not collide. Alternatives: `dr investigate`, `dr research-claim`. Decide before P2 lands.
- **S2 (curation)**: operator picks the set. No script needed; mark out-of-scope claims with `status: archived` or remove. Verify the homepage and `/claims/` index already filter to published (per roadmap §2; should be done).
- **ST4 (Page Builder removal)**: run `rg "Page Builder" -n` first to confirm scope before edits. Known hits: `AGENTS.md` agent-roles table, `docs/architecture/glossary.md` Roles table.
- **P5 cleanup**: this is a small editorial pass on `docs/v1.0.0-roadmap.md`. Move "decision needed" and "future" items out of the active checklist; the only items in the release-criteria block at the top should be true launch blockers.

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
