# Operator queue + batch workflow

**Status**: Stub
**Priority**: v2 (manual operation is fine through v1 launch at ~20 claims)
**Last updated**: 2026-04-24

Move the operator from one-CLI-call-at-a-time to a queue-driven batch flow. Operator drops entries into a queue file; `dr` batch-processes; errors and rejects flow into review files for triage.

## Why v2

- v1 scale (~20 claims) is hand-runnable. The lift to build queue + batch + error-file infrastructure is large.
- Building this prematurely locks in a workflow before the operator has lived through the manual one long enough to know what they want.
- Operator answer to Q7: "semi-automated now, aka mostly manual."

## Sketch

### Inputs

Operator-facing intake files (one per work type), aligned with the six-input taxonomy operator described:

- `research/QUEUE.md` — URL + topic intake (partial; exists)
- `research/ONBOARD_QUEUE.md` — entity + type intake (to be re-created on first use; previous aspirational version deleted 2026-04-24)
- `research/CRITERIA_QUEUE.md` — proposed criterion templates (?)
- `research/SOURCES_QUEUE.md` — manual source submissions (?)
- `research/REVIEW_QUEUE.md` — claims awaiting human sign-off (?)
- `research/blocklist.yaml` — already exists for host blocklist

### Batch runner

- A new `dr` subcommand (e.g., `dr process`) reads each queue file in order, dispatches to the appropriate pipeline, and removes processed entries on success.
- Errors and rejects move to a sibling file (`QUEUE.errors.md`, `QUEUE.rejects.md`) instead of console-only output.
- Operator reviews the error/reject files, edits to fix, re-runs.

### Acceptance criteria

- Operator can paste 5–10 entries into a queue file, run one command, walk away, and come back to a review file showing what worked and what needs attention.

## Open design questions

- **Lockfile semantics**: prevent concurrent batch runs?
- **Re-run policy**: how does this interact with [`data-lifecycle-policy_stub.md`](data-lifecycle-policy_stub.md) (skip-existing vs overwrite)?
- **Failure granularity**: per-entry rollback or whole-batch rollback?
- **Concurrency**: parallelize across queue entries with `asyncio.Semaphore` (matches existing `onboard-parallelize-templates.md`) or strictly serial?

## Out of scope

- Public-facing intake forms (separate `public-feedback.md`).
- A web UI for queue management.

## Cross-references

- Pairs with [`data-lifecycle-policy_stub.md`](data-lifecycle-policy_stub.md) (lifecycle policy controls reprocessing inside this batch flow).
- Six-input taxonomy is also surfaced briefly on FAQ in v1 (see [`pre-launch-quick-fixes.md`](pre-launch-quick-fixes.md) S7).

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-24 | agent (claude-opus-4-7) | initial stub from triage | Scaffolded |
