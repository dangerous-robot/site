# Claim lifecycle states (blocked, threshold, phase)

**Status**: Done (commit df7537e — `phase` field, `blocked_reason` field, `blocked` status enum, `>= 2` threshold)
**v1.0.0 surface**: full schema work lands in v1 per operator 2026-04-26 (`phase` frontmatter field, `blocked` status enum value, `blocked_reason` top-level frontmatter); only auto-recheck is post-v1.
**Last updated**: 2026-04-26

Schema and pipeline implementation for the new claim lifecycle vocabulary landed by `v0.1.0-vocab-workflow-landing.md`. That plan locked the prose; this plan implements the schema and orchestrator changes.

---

## Important framing correction (2026-04-26)

The parent landing plan and earlier drafts of this stub described `current_step → phase` as a "frontmatter field rename." It is not. **Repo-wide grep for `current_step` returns zero hits** (verified 2026-04-26 across `src/`, `pipeline/`, `AGENTS.md`, `docs/architecture/glossary.md`). There is nothing to rename.

What "vocab item D" actually means: when the `phase` field is added (in this plan), the field name shall be `phase`, **not** `current_step`. It is a naming decision for new code, not a rename of existing code. The Verification grep `rg -n current_step ...` (in landing plan #14) is vacuous as written and should be removed or reframed when the landing plan is corrected.

---

## Cross-stub structural decision (operator + advisor 2026-04-26)

One decision shared with `docs/plans/triage-agent.md`:

- **Threshold check (`>= 2 usable sources`) lives in the Orchestrator**, post-Ingestor. The Orchestrator queries source count and transitions the claim to `blocked` itself. This avoids requiring Router code to ship for the threshold to enforce. (Router can move the check later if/when it lands; cheap change.)

The earlier "phase as in-memory state" decision is **reversed by operator 2026-04-26**: `phase` ships as a top-level claim frontmatter field in v1.0.0. See § V1.0.0 minimum scope below.

---

## Operator decisions applied (2026-04-26)

| Decision | Choice | Source |
|---|---|---|
| `blocked_reason` carrier | **Option B**: top-level claim frontmatter (`z.string().optional()`) | Operator BF: YES on Option B |
| `blocked_reason` value shape | **Enum**: `insufficient_sources`, `terminal_fetch_error` | Operator BF: ENUM |
| `phase` frontmatter field | **Lands in v1** (not deferred) | Operator BF: NOT DEFERRED |
| `blocked` status enum value | **Lands in v1** (not deferred) | Operator BF: NOT DEFERRED |
| Auto-recheck for blocked claims | **Deferred** (post-v1) | Operator BF: DEFERRED |
| Acceptance test additions in this stub | **Skipped** (handled separately) | Operator BF: SKIP |

---

## V1.0.0 scope

The schema-and-pipeline work below all lands in v1.0.0. There is no v1-minimum / post-v1 split for this stub anymore (operator decision 2026-04-26).

### Behavior change

- **Orchestrator enforces `>= 2 usable sources` after Ingestor returns.** "Usable" = ingested successfully (not blocklisted, not 403/404, parsed). If `usable_sources < 2`, the orchestrator halts the claim with status `blocked` and `blocked_reason: insufficient_sources` before invoking the Analyst.
- **Orchestrator advances `phase` on each pipeline transition**: `researching → ingesting → analyzing → evaluating`. Cleared (or set to a terminal value) when the claim moves to `drafted`, `blocked`, or any terminal state.

### Schema (`src/content.config.ts`)

The claim schema gains three things; the criterion schema is untouched.

1. **`status` enum**: add `'blocked'` to the existing `['draft', 'published', 'archived']` enum. Updated declaration:
   ```ts
   status: z.enum(['draft', 'published', 'archived', 'blocked']).default('draft'),
   ```
2. **`phase` field**: optional enum at the top level:
   ```ts
   phase: z.enum(['researching', 'ingesting', 'analyzing', 'evaluating']).optional(),
   ```
3. **`blocked_reason` field**: optional enum at the top level:
   ```ts
   blocked_reason: z.enum(['insufficient_sources', 'terminal_fetch_error']).optional(),
   ```
   Use `z.enum` (not `z.string`) so adding new reasons is a deliberate schema change rather than free-text drift.

### Pydantic mirror (`pipeline/common/models.py`)

- Add a `Phase` enum: `RESEARCHING`, `INGESTING`, `ANALYZING`, `EVALUATING`.
- Add a `BlockedReason` enum: `INSUFFICIENT_SOURCES`, `TERMINAL_FETCH_ERROR`.
- Whatever class mirrors the claim frontmatter today (likely the `VerdictAssessment` writer or a separate `ClaimFrontmatter` model) gains:
  - `status: ClaimStatus` widened to include `BLOCKED`.
  - `phase: Phase | None`.
  - `blocked_reason: BlockedReason | None`.

### Pipeline (`pipeline/orchestrator/`)

- New helper (placement: `pipeline/orchestrator/pipeline.py` or a small `lifecycle.py` module): `def below_threshold(usable_sources: list) -> bool: return len(usable_sources) < 2`.
- `verify_claim` (lines 81–170 in `pipeline.py`): after Ingestor returns, count usable sources; if below threshold, set `status='blocked'`, `blocked_reason='insufficient_sources'`, clear `phase`, persist, and return without invoking Analyst.
- `verify_claim` advances `phase` before each step (researcher / ingestor / analyst / evaluator) and clears or terminalizes it on exit.
- `set_claim_status` (`persistence.py:248–275`) accepts `'blocked'` as a valid status. Add a parallel `set_claim_phase` and `set_claim_blocked_reason` helper, or extend `set_claim_status` to take optional `phase` and `blocked_reason` arguments — implementer's call.
- Add a CLI log line: "Claim halted: < 2 usable sources" so operators see why a claim didn't progress.

### Site code (page filters and rendering)

- Any page that filters on `status` and assumed `draft / published / archived` may need to learn about `blocked`. Audit:
  - `src/pages/claims/index.astro` — does it list blocked claims, hide them, or render them in a separate group? Operator decision; recommend hide-by-default with an opt-in filter.
  - Claim detail page — render `phase` and `blocked_reason` if present.
- Search broadly: `rg "data\.status" src/` to find every consumer of the status field.

### Glossary alignment

The renamed `## Lifecycle` table (per landing plan §"Files to modify → glossary.md") must reflect the v1-actual schema state:

- `blocked` row: "Pipeline halted; insufficient sources (`< 2`) or terminal fetch error. **v1: `status: 'blocked'`; reason in top-level `blocked_reason` field.**"
- `in-progress` row: "Pipeline is working it; `phase` ∈ {researching, ingesting, analyzing, evaluating}. **v1: `phase` is a top-level claim frontmatter field.**"

The schema-status column in the lifecycle table needs to be updated from "(no schema field; v1 doc-only)" to actual fields shipped:

| State | Schema status (v1) |
|---|---|
| queued | (no schema field; QUEUE.md only) |
| in-progress | `phase` ∈ {researching, ingesting, analyzing, evaluating} |
| blocked | `status: 'blocked'` + `blocked_reason: <enum>` |
| drafted | `status: 'draft'` (existing) |
| published | `status: 'published'` (existing) |
| archived | `status: 'archived'` (existing) |

### Tests

- New unit tests in `pipeline/tests/`: orchestrator halts when usable_sources < 2; `status='blocked'` and `blocked_reason='insufficient_sources'` are written; Analyst is not invoked.
- New unit tests for `phase` advancement: each pipeline step advances the field; terminal states clear it.
- **Acceptance test (`pipeline/tests/test_acceptance.py`)**: out of scope for this stub per operator (BF: SKIP). Acceptance test handling is decoupled and tracked separately.

---

## Post-v1 (deferred)

### Auto-recheck for blocked claims

If/when blocked claims should periodically retry (sources may become available later):

- Cadence-based scheduler (similar to `recheck_cadence_days`) that picks blocked claims and retries the pipeline.
- Distinct from `next_recheck_due` for published claims; the cadence and conditions differ.

Why deferred: not required for v1.0.0; operators can manually re-run the pipeline via `dr verify` or `dr onboard`.

---

## Ordering and dependencies

**Must precede this work**:

- The vocab + role landing PR settles the names this stub references (`Orchestrator`, `Evaluator`, `blocked`, `phase`). If implementation runs before the vocab PR, prose comments and module docstrings will use older terms. Cheap to update post-hoc but ugly.

**This work blocks**:

- `docs/plans/triage-agent.md` Router scope: Cross-stub decision 1 places threshold in Orchestrator. If the operator overrides and puts the threshold in the Router, this stub's Pipeline section moves to the Router stub.

**Independence from multi-topic**:

- This stub does not touch `category` or `topics`. Can land before, after, or alongside `docs/plans/multi-topic.md`.

**Pipeline → workflow directory rename**:

- See `docs/plans/drafts/pipeline-to-workflow-rename_stub.md` (new). If that rename lands first, every `pipeline/...` path in this stub becomes `workflow/...`. If this stub lands first, the rename plan picks up the new files. Either order works; flag a sweep at execution time.

---

## Rollback (operator-decided 2026-04-26: accept content sweep)

Single-PR change. Schema-touching, so blast radius is moderate but bounded:

1. Revert the merge commit. Three new schema fields disappear (`phase`, `blocked_reason`, `'blocked'` enum value); orchestrator halts revert to "always invoke Analyst regardless of source count."
2. Existing claim files written by the new pipeline carry `phase` / `blocked_reason` / `status: blocked` and will fail schema validation on next build after revert. **Pair the revert with a content sweep**: run a small script that strips those three fields from all `research/claims/**/*.md` and resets `status: blocked` to `status: draft`. Per operator 2026-04-26 (BF: 3b), feature-gating was rejected in favor of the explicit content sweep.
3. Acceptance tests do not need updating either way (out of scope per operator).

The content sweep is a one-off cost during revert; it does not need to be pre-built. Spec for the sweep (write at revert time):
- `for f in research/claims/**/*.md: parse YAML; remove keys phase, blocked_reason; if status==blocked, set status=draft; rewrite frontmatter`.
- Keep a backup of the pre-sweep claim files so the sweep itself is reversible.

---

## Verification

```bash
# `current_step` is gone (was zero hits before, must stay zero)
rg -n "current_step" src/ pipeline/                                  # zero hits

# v1 schema additions
rg -n "blocked_reason" src/content.config.ts                         # at least one hit
rg -n "z\\.enum\\(\\[.*'blocked'\\]\\)" src/content.config.ts        # at least one hit (status enum widened)
rg -n "phase: z\\.enum" src/content.config.ts                        # at least one hit
rg -n "blocked_reason: z\\.enum" src/content.config.ts               # at least one hit

# Pydantic mirror
rg -n "class Phase" pipeline/common/models.py                        # at least one hit
rg -n "class BlockedReason" pipeline/common/models.py                # at least one hit
rg -n "BLOCKED" pipeline/common/models.py                            # at least one hit (status enum)

# Pipeline writes the new fields
rg -n "blocked_reason|phase" pipeline/orchestrator/persistence.py    # at least 2 hits (write sites)

# Threshold check exists in orchestrator
rg -n "usable_sources|< 2|len\\(.*sources.*\\) < 2" pipeline/orchestrator/   # at least one hit

# Glossary lifecycle table reflects v1 state
rg -n "phase" docs/architecture/glossary.md                          # at least one hit (Lifecycle table)
rg -n "blocked_reason" docs/architecture/glossary.md                 # at least one hit (Lifecycle table)

# Tests cover the new behavior
rg -n "below.*threshold|usable_sources|test.*blocked|test.*phase" pipeline/tests/   # at least 2 hits
inv test                                                              # exit 0 (unit + integration; acceptance out of scope)
```

---

## Acceptance criteria

This stub is "done" when:

1. All Verification checks pass.
2. A pipeline run on a synthetic case with 0 or 1 ingestable sources halts the claim with `status: blocked, blocked_reason: insufficient_sources` and does not invoke the Analyst.
3. A pipeline run on a real case with `>= 2` usable sources behaves identically to today (no regression) AND advances `phase` through {researching, ingesting, analyzing, evaluating}.
4. The glossary `## Lifecycle` table description matches the v1-actual carrier choices (top-level `phase` field, top-level `blocked_reason` enum, `status: 'blocked'`).
5. `inv test` is green (acceptance tests excluded per operator).

---

## Out of scope

- Auto-recheck for blocked claims (deferred to post-v1).
- Acceptance test changes — handled separately (operator BF: SKIP).
- `pipeline/auditor/` → `pipeline/evaluator/` directory rename (vocab item B; tracked separately).
- `pipeline/` → `workflow/` directory rename (tracked in `docs/plans/drafts/pipeline-to-workflow-rename_stub.md`).
- UI work for blocked claims beyond minimum filter audit (operator's call on whether `/claims` lists or hides blocked).

---

## Cross-references

- Parent plan: `docs/plans/v0.1.0-vocab-workflow-landing.md` (vocab item D, claim Lifecycle table, threshold ≥ 2 decision).
- Sibling plan: `docs/plans/triage-agent.md` (Router/Orchestrator role split). Cross-stub decision 1 above pins the threshold-check location to Orchestrator.
- Sibling stub: `docs/plans/drafts/pipeline-to-workflow-rename_stub.md` (directory rename; deferred to post-v1; sequencing note in § Ordering).
- Acceptance fixture: `docs/plans/acceptance-test-fixture_stub.md`. Out of scope per operator BF: SKIP.

---

## Review history

| Date | Reviewer | Scope | Changes |
| --- | --- | --- | --- |
| 2026-04-25 | agent | stub creation | Initial scaffolding with `phase` rename framing |
| 2026-04-26 | agent (claude-opus-4-7) | finalization | Reframed `current_step` non-rename. Adopted advisor's v1-minimum/full-implementation split. Added Option A vs B operator decision. Removed `pipeline/audit/` typo. |
| 2026-04-26 | brandon | scope changes | Operator BF annotations: Option B, enum reasons, `phase` and `blocked` enum NOT deferred, auto-recheck deferred, acceptance tests skipped |
| 2026-04-26 | agent (claude-opus-4-7) | applied BF decisions | Rewrote V1.0.0 scope to incorporate full schema work. Removed v1-minimum/post-v1 split. Added Pydantic enum classes. Added schema-status column update. Added rollback caveat (feature gate or content sweep). Added pipeline → workflow rename cross-reference. |
| 2026-04-26 | agent (light corrections + promotion) | promotion | Ready; moved from drafts/claim-lifecycle-states_stub.md to docs/plans/claim-lifecycle-states.md; cross-references updated to point at promoted siblings (multi-topic.md, triage-agent.md). |
