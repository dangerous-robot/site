# Data lifecycle policy

**Deferred**: 2026-10-06, draft-time reprocessing policy with no reader-facing value yet; the published-claim case (refreshing a claim readers can see) moved to [`published-claim-refresh-trail.md`](../completed/published-claim-refresh-trail.md).


**Status**: Stub
**Priority**: v2 (design pre-launch is cheap; implementation after content stabilizes)
**Last updated**: 2026-04-24

Define how research data is overwritten, partially fixed, and skipped during reprocessing. Not yet urgent (operator currently fine deleting `research/` files), but worth designing before content durability matters.

## Why design now, implement later

- Pre-launch, deleting `research/` files is fine. Once readers cite specific claims, deletion costs trust.
- Designing the policy is free now. Designing it under pressure (after a botched reprocess) is expensive.

## Cases to cover

| Scenario | Current behavior | Desired behavior |
|---|---|---|
| Re-run `dr claim-draft` on an existing claim | Raises unless `--force` (`_write_claim_file` in `pipeline/orchestrator/persistence.py`; checked 2026-10-06) | Configurable: skip-if-exists (default), force-overwrite, or write to `*.next.md` for diff review |
| Run `dr ingest` on a URL with an existing source file | In-pipeline ingest reuses the existing file by canonical URL (`_apply_url_dedup`); `dr step-ingest` overwrites only the same URL with `--force` | Skip (idempotent) or force-refresh based on flag |
| Run `dr onboard` on an existing entity | TBD | Skip claims already published; only run for missing templates |
| Fix one specific claim error without re-running the full pipeline | Manual edit only | Targeted command: `dr fix --claim <slug>` or similar |
| Re-evaluate after a source updates | Manual `dr step-audit` (was `dr reassess`) | Source-triggered reassessment (separate plan; UNSCHEDULED.md) |

## Open design questions

- **Default policy**: skip-existing or overwrite? Skip is safer; overwrite matches current implicit behavior.
- **Audit sidecar interaction**: does a re-run produce a new sidecar with full history (`completed/audit-trail.md` Stage 3) or replace the existing one?
- **Lockfile / in-progress markers**: prevent two concurrent runs on the same claim?
- **Dry-run mode**: `--dry-run` that shows what would be overwritten without writing?

## Out of scope

- Source-triggered reassessment (separate item; UNSCHEDULED.md).
- Branching/versioning of claim files (audit-trail Stage 3 already covers history).

## Cross-references

- [`audit-trail.md`](../completed/audit-trail.md) Stage 3 (append-only history, now [`audit-trail-extensions.md`](audit-trail-extensions.md) Phase 3) overlaps; coordinate semantics.
- [`operator-queue-batch-workflow_stub.md`](operator-queue-batch-workflow_stub.md) — batch flow needs lifecycle decisions to be coherent.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-24 | agent (claude-opus-4-7) | initial stub from triage | Scaffolded |
| 2026-10-06 | agent (claude-opus-5-5, plan review) | refocus triage | Deferred with a one-line reason; corrected stale facts; relative links adjusted for `deferred/`. |
