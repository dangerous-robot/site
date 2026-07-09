# Plan: Audit trail extensions (Phase 2 + Phase 3)

**Status**: Ready
**Last updated**: 2026-05-16
**Depends on**: Phase 1 (shipped; see [`completed/audit-trail.md`](completed/audit-trail.md))
**Reads against**: [`docs/architecture/vision-state-machine.md`](../architecture/vision-state-machine.md) (substrate); [`docs/plans/research-outputs-improvement-plan.md`](research-outputs-improvement-plan.md) (reader-facing surface).

Phase 2 (extended data + CI gates) and Phase 3 (append-only transition log) of the AI Research Audit Trail. Phase 1 (sidecar infrastructure, `_write_audit_sidecar`, `dr review` CLI, custom Astro loader, UI) shipped and is recorded in `completed/audit-trail.md`. This plan tracks the remaining work.

The terminology, architecture, and Phase 1 specs that this plan extends live in `completed/audit-trail.md`. Read that first if you need context.

### Role in the state-machine substrate

Phases 2 and 3 produce the append-only transition log described in `docs/architecture/vision-state-machine.md` principle 2 ("Transitions are first-class records"). Downstream consumers read from it:

- The **ClaimReview JSON-LD export** (research-outputs-improvement-plan.md near-term move 3) reads Phase 2 fields to populate `datePublished`, `author`, `reviewRating`, and `itemReviewed` per published claim. Build fails if any published claim cannot produce a valid `ClaimReview` document.
- The **build-time staleness gate** (research-outputs-improvement-plan.md near-term move 5; vision near-term item) reads `audit.analyst_verdict` and `human_review.reviewed_at` to enforce recheck cadence.
- **Supersession** (a named open-loop transition reserved for operator approval) appends to the Phase 3 log.

Phase 2 is the substrate the ClaimReview export reads. Phase 3 is the substrate supersession history reads. Both are sized so the same nudge agents the vision describes can run against them later without re-planning.

---

## Phase 2: Extended data and backfill

### What's added

**Extended sidecar schema** — new fields in `pipeline_run` and `audit` blocks:

```yaml
pipeline_run:
  urls_found: 6           # len(result.urls_found)
  urls_ingested: 4        # len(result.urls_ingested)
  urls_failed: 2          # len(result.urls_failed)
audit:
  auditor_reasoning: "..."    # ComparisonResult.reasoning
  evidence_gaps:
    - "..."                    # ComparisonResult.evidence_gaps
```

`auditor_reasoning` and `evidence_gaps` come from `ComparisonResult.reasoning` and `ComparisonResult.evidence_gaps`, both already available at the `_write_audit_sidecar` call site. Thread them through the function signature.

**Backfill script** at `pipeline/scripts/backfill_audit_sidecars.py`: iterates `research/claims/**/*.md`, skips any claim that already has a `.audit.yaml`, writes a partial sidecar with `schema_version: 1`, `pipeline_run.ran_at: null`, and `backfill: true` flag. The UI renders "Partial audit record" when `backfill: true` rather than showing fabricated data.

**UI addition**: an "Evaluator reasoning" sub-section in the expanded `<details>` block, rendered only when `audit.audit.auditor_reasoning` is defined. (Field name `auditor_reasoning` retained for v1 schema stability; prose uses "Evaluator" per AGENTS.md.)

### ClaimReview export data requirements

The ClaimReview JSON-LD export (research-outputs-improvement-plan.md near-term move 3) reads from claim frontmatter primary and the Phase 2 sidecar secondary. Field mapping:

| ClaimReview field | Source |
|---|---|
| `claimReviewed` | claim frontmatter `claim` text |
| `itemReviewed.Claim.datePublished` | claim `as_of` |
| `reviewRating.ratingValue` | claim `verdict` (= latest `audit.analyst_verdict` after operator approval; staleness gate enforces agreement) |
| `reviewRating.bestRating` / `worstRating` | rubric document (research-outputs near-term move 2) |
| `author` | claim `reviewer` or sidecar `human_review.reviewer` |
| `datePublished` | latest `pipeline_run.ran_at` or `human_review.reviewed_at` |
| `url` | canonical claim page URL |

Phase 2 must ensure these fields are reliably present on every claim with `status: published`. The build-time invariant lives in the export step, not in this plan, but the field availability gate does.

### Conditions that must be met before starting Phase 2

**Judge condition 3: build-time staleness check.** Before Phase 2 ships, add a check in the Astro custom loader (or a CI step) that compares `claim.data.verdict` against `claim.data.audit.audit.analyst_verdict` and emits a build error when they disagree. The check runs only when both values are present, a missing sidecar is not an error in Phase 1. This check is what makes the audit trail trustworthy rather than decorative: it catches manual edits to a claim's verdict that were not followed by a pipeline rerun.

**Judge condition 4: orphan sidecar prevention.** Before Phase 2 ships, add a CI check or pre-commit hook that:
- Verifies every `.audit.yaml` has a matching `.md` at the same path stem (catches renamed or deleted claim files that left orphaned sidecars).
- The inverse check (every `.md` without a sidecar is genuinely new) is advisory only in Phase 2, required in Phase 3 when all claims are expected to have sidecars.

Both checks can be a single script at `scripts/check-audit-pairs.ts` run in CI.

### Acceptance criteria

- [ ] `_write_audit_sidecar` accepts and writes `urls_found`, `urls_ingested`, `urls_failed`, `auditor_reasoning`, `evidence_gaps`.
- [ ] Backfill script writes partial sidecars for all claims that lack one; existing sidecars are not touched.
- [ ] UI renders auditor reasoning when present.
- [ ] UI renders "Partial audit record" for backfilled sidecars.
- [ ] Build-time staleness check fails the build when `claim.data.verdict` disagrees with `audit.analyst_verdict` on a claim that has a full sidecar.
- [ ] CI check script catches an `.audit.yaml` with no matching `.md`.
- [ ] Sidecar + frontmatter fields together are sufficient to emit a valid `ClaimReview` JSON-LD document for any `status: published` claim (verified by an export prototype or schema check; full export landing is research-outputs-improvement-plan.md move 3).

---

## Phase 3: Append-only transition log (recheck + supersede)

### What's added

Converts the sidecar from a single-run record to an append-only list of named transitions. Each entry records cause, agent, inputs, outputs, and resulting verdict — the shape the vision's principle 2 calls for. `schema_version: 3` signals this format change.

The list key remains `audit_entries` (v1 schema-field stability, same rationale as the `auditor_verdict` rename deferral). Each entry carries a `transition` discriminator naming which transition produced it.

```yaml
schema_version: 3
audit_entries:
  - transition_id: "01HXR2C8K9P7M3QWZ4VYBN5JF6"
    transition: "recheck"          # recheck | supersede | initial
    ran_at: "2026-04-22T14:32:00Z"
    model: "claude-opus-4-5"
    analyst_verdict: "true"
    auditor_verdict: "true"
    verdict_changed_from_previous: false
    human_review:
      reviewed_at: "2026-04-23"
      reviewer: "brandon@faloona.net"
  - transition_id: "01HZJ5T2N1A8VKD9F3MGCQR7H4"
    transition: "supersede"
    ran_at: "2026-07-01T09:15:00Z"
    model: "claude-opus-4-5"
    prior_verdict: "true"
    new_verdict: "mixed"
    analyst_verdict: "mixed"
    auditor_verdict: "mostly-true"
    trigger: "new primary source contradicts prior finding"
    approving_operator: "brandon@faloona.net"
    verdict_changed_from_previous: true
    human_review:
      reviewed_at: "2026-07-01"
      reviewer: "brandon@faloona.net"
```

The claim frontmatter `verdict` is always the current (latest) value. The sidecar provides the history. `_write_audit_sidecar` becomes a read-modify-append operation: read existing sidecar, append new entry, write. Migration from `schema_version: 1` to `schema_version: 3` is handled by a one-time migration script (which writes the historical entry with `transition: initial`).

**Supersession.** A `supersede` transition is reserved for operator approval (one of the vision's open-loop decision points). Pre-condition: a prior published verdict exists. Post-condition: a new entry records `prior_verdict`, `new_verdict`, `trigger`, and `approving_operator`; the claim ID is unchanged; frontmatter `verdict` is updated to the new value. The ClaimReview export reads the latest entry; older entries remain readable for the chain.

**Identifiers.** `transition_id` is a ULID (or `<claim_id>:<ran_at>` if ULID dependency is undesirable in the pipeline). It exists so the JSON-LD export, alerts, and operator commands can reference a specific transition. This is the FAIR-Findable hook for the transition log.

UI: renders latest entry's details in the collapsed panel with a "View history" toggle revealing prior entries. Supersession entries render with the prior→new verdict chain visible.

### Conditions that must be met before starting Phase 3

- Phase 2 acceptance criteria all pass.
- Orphan check passes cleanly for all claims (no `.audit.yaml` without a matching `.md`).
- A migration script for `schema_version: 1` → `schema_version: 3` is written and tested before any existing sidecars are converted.

### Acceptance criteria

- [ ] New pipeline runs append to `audit_entries` rather than overwriting.
- [ ] `schema_version: 3` is written on first append.
- [ ] `verdict_changed_from_previous` is computed correctly.
- [ ] UI renders latest entry in collapsed state.
- [ ] "View history" toggle renders all prior entries.
- [ ] `schema_version: 1` sidecars are migrated correctly by the migration script (historical entry written with `transition: initial`).
- [ ] Migration script is idempotent.
- [ ] `supersede` transitions append an entry with `prior_verdict`, `new_verdict`, `trigger`, and `approving_operator`; the claim ID is unchanged; frontmatter `verdict` is updated to the new value.
- [ ] Every entry carries a unique `transition_id` and a `transition` discriminator.

---

## Vocabulary alignment

Prose uses **Evaluator** per AGENTS.md and the vision. Sidecar field names (`auditor_verdict`, `auditor_reasoning`) and the `pipeline/audit/` directory keep their names in v1 for schema/path stability; the directory rename and field rename are separate follow-ons, not part of these phases.

## FAIR alignment notes

The audit trail is the substrate for the Phase 2/3 outputs to be FAIR-aligned per `docs/plans/research-outputs-improvement-plan.md`. This plan does not adopt FAIR as a vocabulary; it uses the four principles as a quality lens.

- **Findable.** Sidecars live at a predictable path (`research/claims/<slug>.audit.yaml`) paired with the claim. Phase 3 adds `transition_id` per entry so individual transitions are addressable. ClaimReview JSON-LD exports (per research-outputs move 3) make published claims discoverable to standards-aware crawlers; a sitemap lists them.
- **Accessible.** Artifacts are plain YAML/Markdown/JSON-LD served over HTTPS with no auth. Licensing is CC-BY-4.0 per `LICENSE-CONTENT`. No retrieval-time access barriers.
- **Interoperable.** Sidecar schema is bespoke YAML by design (matching the source-of-truth pattern). The JSON-LD layer uses Schema.org `ClaimReview` vocabulary; the transition log shape (cause, agent, inputs, outputs) follows PROV-O discipline without adopting the namespace, per the research-outputs-improvement-plan stance.
- **Reusable.** Every transition records the agent (model or human) and the inputs it consumed (research-outputs move 1 promises this; Phase 2/3 deliver it). Per-artifact license is implicit from the repo license; an explicit `license:` field per claim is deferred until a consumer needs it.

---

## File plan

### New files

| File | Purpose |
|------|---------|
| `pipeline/scripts/backfill_audit_sidecars.py` | Phase 2: write partial sidecars for existing claims |
| `scripts/check-audit-pairs.ts` | Phase 2: CI check for orphaned or missing sidecars |
| `pipeline/scripts/migrate_audit_schema_v1_to_v3.py` | Phase 3: one-time migration of existing v1 sidecars to v3 |

### Edited files

| File | Phase | Change |
|------|-------|--------|
| `pipeline/orchestrator/persistence.py` | 2 | Extend `_write_audit_sidecar()` signature with new fields |
| `pipeline/orchestrator/persistence.py` | 3 | Convert `_write_audit_sidecar` to read-modify-append |
| `pipeline/orchestrator/pipeline.py` | 2 | Pass new fields at call sites |
| `src/content.config.ts` | 2 | Extend `auditSchema` with new fields; staleness check in loader |
| `src/content.config.ts` | 3 | Schema bump to `schema_version: 3`; loader handles list shape |
| `src/pages/claims/[...slug].astro` | 2 | Render auditor reasoning section; "Partial audit record" indicator |
| `src/pages/claims/[...slug].astro` | 3 | Render "View history" toggle |

---

## Open questions (carry-forward from Phase 1)

1. **Loader path configurability for research repo split**: a possible future research repo split is a standing constraint (see the repo-separation note in AGENTS.md § Editorial content). When that happens, the loader's `research/claims` base path must become configurable rather than hardcoded. Defer until the split is actively planned, but note the coupling point.

2. **`reviewed_at` non-null CI enforcement**: Decision (2026-04-22): use a CI check, not branch protection. A CI step (or `scripts/check-audit-pairs.ts` extension) must verify that every `status: published` claim with a sidecar has `human_review.reviewed_at` set. Branch protection alone is not sufficient; it depends on operator discipline. **This gate was a v0.1.0 blocker per the original Phase 1 plan; verify whether it actually shipped with Phase 1, and if not, treat it as a Phase 2 prerequisite.**

---

## Cross-references

- Phase 1 (shipped): [`completed/audit-trail.md`](completed/audit-trail.md)
- State-machine vision (substrate): [`docs/architecture/vision-state-machine.md`](../architecture/vision-state-machine.md)
- Reader-facing surface: [`docs/plans/research-outputs-improvement-plan.md`](research-outputs-improvement-plan.md). The ClaimReview JSON-LD export (move 3) is the canonical machine-readable verdict artifact; it reads frontmatter primary and the Phase 2 sidecar secondary. This supersedes the earlier "canonical verdict artifact" note in `docs/UNSCHEDULED.md`.
- Vocabulary alignment: [`v0.1.0-vocab-workflow-landing.md`](completed/v0.1.0-vocab-workflow-landing.md)

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-25 | agent (split from `audit-trail.md`) | initial | Extracted Phase 2 + Phase 3 from `completed/audit-trail.md` after Phase 1 shipped. Phase 1 record stays in `completed/`. |
| 2026-05-16 | parallel review agents (ClaimReview lens + FAIR lens) | alignment with vision-state-machine.md and research-outputs-improvement-plan.md | Added "Role in the state-machine substrate" intro and "Reads against" header. Reframed Phase 3 as the append-only transition log with named transitions (`recheck`, `supersede`, `initial`); added `transition` discriminator and `transition_id` per entry; added supersession sub-section, acceptance criteria, and YAML example. Added ClaimReview export data-requirements table to Phase 2 with a sufficiency acceptance criterion. Added FAIR alignment notes section. Tightened Vocabulary alignment (Evaluator rename is settled in prose; field/path names retained for v1 stability). Replaced the UNSCHEDULED "canonical verdict artifact" cross-reference with a pointer to ClaimReview JSON-LD export in research-outputs-improvement-plan.md. |
