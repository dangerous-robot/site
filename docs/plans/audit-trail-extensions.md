# Plan: Audit trail extensions (Phase 2 + Phase 3)

**Status**: Ready
**Last updated**: 2026-04-25
**Depends on**: Phase 1 (shipped; see [`completed/audit-trail.md`](completed/audit-trail.md))

Phase 2 (extended data + CI gates) and Phase 3 (append-only recheck history) of the AI Research Audit Trail. Phase 1 (sidecar infrastructure, `_write_audit_sidecar`, `dr review` CLI, custom Astro loader, UI) shipped and is recorded in `completed/audit-trail.md`. This plan tracks the remaining work.

The terminology, architecture, and Phase 1 specs that this plan extends live in `completed/audit-trail.md`. Read that first if you need context.

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

**UI addition**: "Auditor reasoning" sub-section in the expanded `<details>` block, rendered only when `audit.audit.auditor_reasoning` is defined.

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

---

## Phase 3: Append-only recheck history

### What's added

Converts the sidecar from a single-run record to a list of `audit_entries`. Each pipeline recheck appends a new entry. `schema_version: 3` signals this format change.

```yaml
schema_version: 3
audit_entries:
  - ran_at: "2026-04-22T14:32:00Z"
    model: "claude-opus-4-5"
    analyst_verdict: "true"
    auditor_verdict: "true"
    verdict_changed_from_previous: false
    human_review:
      reviewed_at: "2026-04-23"
      reviewer: "brandon@faloona.net"
  - ran_at: "2026-07-01T09:15:00Z"
    model: "claude-opus-4-5"
    analyst_verdict: "mixed"
    auditor_verdict: "mostly-true"
    verdict_changed_from_previous: true
    human_review:
      reviewed_at: null
```

The claim frontmatter `verdict` is always the current (latest) value. The sidecar provides the history. `_write_audit_sidecar` becomes a read-modify-append operation: read existing sidecar, append new entry, write. Migration from `schema_version: 1` to `schema_version: 3` is handled by a one-time migration script.

UI: renders latest entry's details in the collapsed panel with a "View history" toggle revealing prior entries.

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
- [ ] `schema_version: 1` sidecars are migrated correctly by the migration script.
- [ ] Migration script is idempotent.

---

## Vocabulary alignment

After `v0.1.0-vocab-workflow-landing.md` lands, this plan's wording should be reviewed for consistency:
- "Auditor" / "auditor agent" → **Evaluator** (vocab item B). The sidecar field name `auditor_verdict` keeps its name in v1 (schema-field rename deferred); only prose vocabulary changes.
- The `pipeline/audit/` directory rename to `pipeline/evaluator/` is a separate follow-on, not part of these phases.
- "Auditor verdict" in the Phase 3 example YAML stays as a field name (schema stability) but the surrounding prose should read "Evaluator's independent evaluation" where it describes the role.

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

1. **Loader path configurability for research repo split**: `docs/BACKLOG.md:29` notes a possible future research repo split. When that happens, the loader's `research/claims` base path must become configurable rather than hardcoded. Defer until the split is actively planned, but note the coupling point.

2. **`reviewed_at` non-null CI enforcement**: Decision (2026-04-22): use a CI check, not branch protection. A CI step (or `scripts/check-audit-pairs.ts` extension) must verify that every `status: published` claim with a sidecar has `human_review.reviewed_at` set. Branch protection alone is not sufficient; it depends on operator discipline. **This gate was a v0.1.0 blocker per the original Phase 1 plan; verify whether it actually shipped with Phase 1, and if not, treat it as a Phase 2 prerequisite.**

---

## Cross-references

- Phase 1 (shipped): [`completed/audit-trail.md`](completed/audit-trail.md)
- Vocabulary alignment: [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md)
- Canonical-verdict-artifact framing: see `docs/UNSCHEDULED.md` § "Canonical verdict artifact (LLM-as-judge framing)". If that lands first, the carrier (sidecar vs. claim frontmatter vs. new verdict-record file) may shift, and these phases inherit the new carrier.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-25 | agent (split from `audit-trail.md`) | initial | Extracted Phase 2 + Phase 3 from `completed/audit-trail.md` after Phase 1 shipped. Phase 1 record stays in `completed/`. |
