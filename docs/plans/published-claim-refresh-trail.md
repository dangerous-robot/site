# Plan: published-claim refresh trail (RF8, RF9)

**Status**: `in progress`
**Last updated**: 2026-10-07
**Reviewed by:** self-review, 2026-10-06 (see Review history)
**Serves**: Responsible AI chatbots, backed by claims (roadmap item SITE-J). This must ship before that page's claims are published and then refreshed.
**Findings**: RF8 and RF9 in [`docs/UNSCHEDULED.md` § claim-refresh review findings (2026-10-04)](../UNSCHEDULED.md#claim-refresh-review-findings-2026-10-04)
**Split from**: [`deferred/audit-trail-extensions.md`](deferred/audit-trail-extensions.md) (this plan takes its reader-facing slice: saving the evaluator's reasoning and gaps, and the verdict/sidecar check)

When `dr claim-refresh` re-runs a published claim, three things should hold:
- The public record keeps its history: the prior verdict and reviewer are saved.
- A verdict change becomes a dated correction on the claim page when the claim is approved again.
- The evaluator's reasons for flagging a claim are saved and shown.

A lint check also catches a published verdict that matches neither the pipeline's verdict nor a recorded reviewer override. This is the promise the `/corrections` page makes ("when a claim changes, ..."), carried into the pipeline.

Every step is test-first: write the failing test, confirm it fails for the stated reason, change the code, confirm it passes. Paths are under `pipeline/` unless they start with `docs/`, `src/` or `research/`. Line numbers are as of HEAD `081ec37`.

## Status checklist

Ticked as items land (AGENTS.md rule 4). Ids match the step headings below.

- [x] P1: snapshot the published state before a refresh overwrites it (RF8)
- [x] P2: record dropped sources in the snapshot (RF8)
- [x] P3: approval turns a verdict change into a `corrections` entry (RF8)
- [x] P4: `dr publish` skips refreshed claims whose verdict changed
- [x] P5: approval records a reviewer verdict override
- [x] A1: save the evaluator's reasoning, gaps and flag reasons in the sidecar (RF9)
- [x] A2: say the real flag reason in the terminal (RF9)
- [x] L1: lint `verdict-sidecar-mismatch` (error)
- [x] L2: lint `refresh-pending-review` (warning)
- [ ] U1: site schema and claim page show the evaluator's reasoning and flag reasons
- [ ] U2: `dr review-queue` header shows the published state for refreshed claims
- [ ] D1: docs (`docs/architecture/content-model.md` sidecar table, `docs/runbook.md` "Refreshing a published claim", UNSCHEDULED RF8 and RF9 rows)
- [ ] V1: verification section passes

## Facts the plan relies on

Checked against HEAD `081ec37` on 2026-10-06.

| Id | Fact | Where |
|----|------|-------|
| K1 | `claim_refresh` writes the claim with `force=True` and `status=draft` in all four branches (three blocked, one success), and calls `_write_audit_sidecar(..., reset_review=True)` in each. | `orchestrator/cli.py:798`, branches at `:944-1110`, `reset_review=True` at `:979`, `:1027`, `:1079`, `:1125` |
| K2 | `reset_review=True` replaces `human_review` with all-null fields. Nothing else in the sidecar keeps the prior reviewer or date. | `orchestrator/persistence.py:495-512` |
| K3 | `_write_claim_file` already keeps operator-owned `corrections` and `tags` on a forced overwrite, so a correction written at approval survives later refreshes. | `orchestrator/persistence.py:375-404` |
| K4 | No code writes a `corrections` entry or `previous_verdict`. The site schema and claim page already support them: `{date, summary, previous_verdict}`, rendered as "Corrected {date}: {summary}" plus "Previous verdict: {label}". | `src/content.config.ts:212-216`; `src/pages/research/claims/[...slug].astro:144-150` |
| K5 | `approve_claim` writes `human_review` and then flips draft to published. `dr review --approve` and the `a` action in `dr review-queue` both call it. | `orchestrator/review.py:87-134`; `orchestrator/cli.py:1807`; `orchestrator/review_queue.py:461` |
| K6 | `dr publish` bulk-flips drafts to published with `reviewer: null` and an `[auto-publish]` note. It does not call `approve_claim`. | `orchestrator/cli.py` `publish` command (`:2016`) |
| K7 | `ComparisonResult` carries `reasoning` and `evidence_gaps`, but `audit_block` writes neither. `needs_review` is true for a major or opposite verdict gap, an adjacent verdict gap with confidence 2+ steps apart, or more than one evidence gap. | `auditor/models.py:63-77`; `auditor/compare.py:61-65`; `orchestrator/persistence.py:482-493` |
| K8 | The refresh terminal line always says "verdict disagreement", whatever set the flag. | `orchestrator/cli.py:1129-1130` |
| K9 | The site's `auditSchema.audit` is a non-strict `z.object`. New optional keys pass through only if they are declared, and undeclared keys are stripped without error. | `src/content.config.ts:60-68` |
| K10 | Detail pages are built for every claim, drafts included: a draft shows a notice but renders. A committed, refreshed, unapproved claim therefore replaces the reviewed verdict at the same URL. Lists show published claims only. Unlike `actions` (`src/lib/actions.ts:7`), neither the claims loader nor the page drops drafts from production builds, so `completed/refocus-foundation.md` ("Drafts do not render in production") holds for lists only. | `src/pages/research/claims/[...slug].astro:20-26`, `:64-66`; `src/pages/research/claims/index.astro:11`; no draft filter in the `claims-with-audit` loader (`src/content.config.ts`) |
| K11 | The `e` action in `dr review-queue` can change `verdict` before approval, so a published verdict can legitimately differ from `audit.analyst_verdict`. | `orchestrator/review_queue.py:136` (`_EDITABLE_FIELDS` includes `verdict`) |
| K12 | All 3 committed claims are published, and each frontmatter verdict equals its sidecar `analyst_verdict`, so L1 lands without failing CI. `brave-browser/renewable-energy-hosting` went from `false` to `unverified` in the 2026-10-04 refresh and has no `corrections` entry (see Q1). | `research/claims/**` at HEAD |
| K13 | The local pre-commit hook runs `dr lint` over the whole working tree and exits 1 on any error, so an `error` lint on uncommitted research output blocks unrelated commits. The hook is not tracked, and `docs/runbook.md` lists "Linting and pre-commit hooks" as a section still to write. CI runs `dr lint --severity error` on the committed tree. | `.git/hooks/pre-commit` (local); `.github/workflows/ci.yml:41` |

## Design

### Sidecar additions

```yaml
refresh:                          # present only while a refreshed, previously published claim awaits re-approval
  refreshed_at: "2026-10-04T18:22:00+00:00"
  previous:                       # the last published state, read before the overwrite
    status: published
    verdict: "false"
    confidence: medium
    title: "..."
    as_of: "2026-05-11"
    sources: ["2025/...", "..."]
    reviewed_at: "2026-05-11"
    reviewer: "brandon@..."
    ran_at: "2026-05-11T..."      # previous pipeline_run.ran_at
  dropped_sources: ["2025/...", "..."]   # previous.sources not in the new sources
audit:
  # existing keys unchanged, plus:
  auditor_reasoning: "..."        # ComparisonResult.reasoning
  evidence_gaps: ["...", "..."]   # ComparisonResult.evidence_gaps
  needs_review_reasons: ["verdict disagreement", "2+ evidence gaps"]  # empty when needs_review is false
human_review:
  # existing keys unchanged, plus (written only by approve_claim, P5):
  verdict_override: {from: unverified, to: mostly-false}   # null when the approved verdict equals audit.analyst_verdict
```

`schema_version` stays `1`. All additions are optional, so older sidecars still validate (K9).

### Rules

1. **Snapshot once per published state.** If the claim on disk has `status: published`, the refresh writes `refresh.previous` from the current claim and sidecar. If the claim is not published but its sidecar already has a `refresh` block and `human_review.reviewed_at` is null (a second refresh before re-approval), the block carries forward unchanged and only `dropped_sources` is recomputed against `previous.sources`. Otherwise, no `refresh` block.
2. **Approval closes the refresh.** `approve_claim(mode="approve")` on a claim with a `refresh` block works as follows:
   - **Verdict changed** (current frontmatter `verdict` differs from `refresh.previous.verdict`): it requires a correction summary and appends `{date: today, summary, previous_verdict: refresh.previous.verdict}` to frontmatter `corrections`.
   - **Verdict unchanged:** it writes no correction.
   - **Either way**, it then deletes the `refresh` block. The `corrections` entry is the lasting public record; git history holds the rest.
3. **The correction summary is written by a person.** There is no generated default text on a reader-facing record. The CLI asks for it, and the review queue prompts for it.
4. **Overrides are recorded, not inferred.** At approval, if the frontmatter `verdict` differs from `audit.analyst_verdict`, `human_review.verdict_override` records `{from, to}`. L1 accepts a mismatch only when this override matches.

## Steps

### P1: snapshot the published state (RF8)

- **Test** (`tests/test_audit_trail.py`): `_write_audit_sidecar(..., previous_publication=<dict>)` writes `refresh.previous` with the given fields and `refresh.refreshed_at = ran_at`. Called with `previous_publication=None` on a sidecar that already has a `refresh` block and null `reviewed_at`, it carries the block forward. Called with `None` and no block, it writes no `refresh` key.
- **Test** (`tests/test_cli.py`, `CliRunner` with the pipeline stubbed as the existing refresh tests do): refreshing a published fixture claim leaves `refresh.previous.verdict`, `.reviewer` and `.reviewed_at` equal to the pre-run values, in the success branch and in one blocked branch.
- **Code:** add `_read_published_snapshot(claim_path) -> dict | None` in `orchestrator/persistence.py`. It reads frontmatter and the sidecar and returns `None` unless status is `published`. In `claim_refresh` (`orchestrator/cli.py:798`), call it once before `verify_claim` and pass the result to all four `_write_audit_sidecar` calls. Add the `previous_publication: dict | None = None` parameter. Write `refresh` between `sources_consulted` and `audit`.

### P2: record dropped sources (RF8)

- **Test:** with `previous.sources = [a, b, c]` and new `source_ids = [b, d]`, `refresh.dropped_sources == [a, c]` (order kept). On a carried-forward block, it is recomputed against `previous.sources`.
- **Code:** compute in `_write_audit_sidecar` from `previous.sources` and a new `current_source_ids` parameter (the `source_ids` that `claim_refresh` already holds).
- **Out of scope:** `inv audit.prune` (`linter/prune.py`) still deletes dropped sources once nothing cites them. Git history keeps them.

### P3: corrections on approval (RF8)

- **Tests** (`tests/test_review_queue.py`, plus the existing `approve_claim` tests):
  - (a) verdict changed, summary given: `corrections` gains one entry with today's date, the summary and `previous_verdict`; the `refresh` block is gone; status is `published`.
  - (b) verdict changed, no summary: raises `ClickException` naming `--correction`; nothing is written.
  - (c) verdict unchanged: no entry; the `refresh` block is gone.
  - (d) existing `corrections` entries are kept and the new one is appended.
  - (e) the review-queue `a` action on a changed-verdict item prompts for a summary (stdin `"a\nRe-checked: ...\nq\n"`) and passes it through.
  - (f) retry after a failed sidecar write (simulate one by making the sidecar write raise once): the second `--approve` adds no duplicate correction (same date and `previous_verdict` already present) and completes the approval.
- **Code:**
  - `approve_claim` gains `correction_summary: str | None = None`.
  - Add `set_claim_corrections(claim_path, entries)` next to `set_claim_status` in `orchestrator/persistence.py`.
  - Add `--correction TEXT` to `dr review` (`orchestrator/cli.py:1801`).
  - In `review_queue.py`, the `a` action prompts only when `item` shows a verdict change.
- **Order inside `approve_claim`:**
  1. Check (verdict changed and no summary: raise, nothing written).
  2. Write the frontmatter `corrections` entry.
  3. Update the sidecar (`human_review`, delete `refresh`).
  4. Flip the status.

  Today's comment at `orchestrator/review.py:128` calls the sidecar the commit point, and that still holds for the status flip. The new step 2 must be idempotent so a rerun after a failure at step 3 or 4 completes cleanly; test (f) covers this.

### P4: `dr publish` skips changed-verdict refreshes

- **Test:** `dr publish --all --yes` over a fixture with one changed-verdict refreshed draft skips it with a warning that names `dr review --approve --correction`. An unchanged-verdict refreshed draft is published, and its `refresh` block is deleted.
- **Code:** add a check in the `publish` command loop. Deleting the block reuses P3's helper.

### P5: record reviewer verdict overrides

- **Test:** approving a claim whose frontmatter verdict was edited (via `e`) away from `audit.analyst_verdict` writes `human_review.verdict_override: {from, to}`. Approving a matching claim writes `verdict_override: null`.
- **Code:** in `approve_claim`, after the preflight. `dr review` without `--approve` (sign-off only) also records it, so a later L1 run accepts the claim.

### A1: save the evaluator's reasoning and flag reasons (RF9)

- **Test** (`tests/test_compare.py`): add `needs_review_reasons(result) -> list[str]` in `auditor/compare.py` (pure). It returns `"verdict disagreement"` for a major or opposite gap, `"confidence gap"` for an adjacent verdict gap with confidence 2+ steps apart, and `"2+ evidence gaps"` for more than one gap; otherwise `[]`. The cases mirror the `needs_review` expression at `auditor/compare.py:61-65`. A drift test asserts `bool(reasons) == result.needs_review` over a grid of inputs.
- **Test** (`tests/test_audit_trail.py`): the sidecar `audit` block contains `auditor_reasoning`, `evidence_gaps` and `needs_review_reasons`.
- **Code:** extend `audit_block` in `_write_audit_sidecar` (`orchestrator/persistence.py:482-493`). This touches every caller that passes a `ComparisonResult` (refresh, onboard, verify, `dr step-audit --write`); none of them needs a code change.

### A2: say the real flag reason (RF9)

- **Test:** with a comparison that agrees on verdict but has two gaps, the refresh output says `Note: flagged for human review (2+ evidence gaps).` and does not contain "verdict disagreement".
- **Code:** `orchestrator/cli.py:1129-1130` joins `needs_review_reasons`. Apply the same change to any other hardcoded copy of the line (`rg "verdict disagreement" pipeline/orchestrator`).

### L1: lint `verdict-sidecar-mismatch` (error)

- **Test** (`tests/test_linter.py`, pure function over the pre-built maps):
  - Flags a published claim whose `verdict` differs from `audit.analyst_verdict` and has no matching `human_review.verdict_override`.
  - No issue when the override matches, when `audit` is null, when there is no sidecar (`published-without-review` covers that), or when the claim is not published.
- **Code:** `check_verdict_sidecar_mismatch` in `linter/checks.py`, registered in `linter/runner.py`. The hint reads: "re-run `dr claim-refresh`, or approve with `dr review` to record the override".
- **Rollout:** run `dr lint --severity error` on the current tree first. K12 says it passes.

### L2: lint `refresh-pending-review` (warning)

- **Test:** a claim whose sidecar has `refresh.previous.status == published` and whose own status is not `published` gets a warning naming the previous verdict and reviewed date.
- **Severity: warning, not error.** An error would block every unrelated commit while a refresh sits in the working tree (K13), and would stop the operator from committing a deliberate blocked or archived outcome. The runbook step (D1) says to approve before committing.

### U1: site shows the evaluator's reasoning and flag reasons

- **Code:**
  - Add optional `auditor_reasoning: z.string()`, `evidence_gaps: z.array(z.string())` and `needs_review_reasons: z.array(z.string())` to `auditSchema.audit` in `src/content.config.ts`. Add optional `verdict_override: z.object({from, to}).nullable()` to `human_review`.
  - In `src/pages/research/claims/[...slug].astro`, inside the existing audit section (`:219-231`), render "Evaluator reasoning" (a paragraph) and "Evidence gaps" (a list) when present. Replace "Flagged for human review" with "Flagged for human review: {reasons}" when reasons exist.
  - Use the existing `audit-muted` and `audit-section` classes and add no new styles. If the reviewer overrode the verdict, add one line under "Human review": "Reviewer changed the verdict from {from label} to {to label}." Labels come from `VERDICT_LABELS`.
- **Check:** `inv check`. On a fixture or local refresh, view the built page in light and dark, and confirm no other text in the `<details>` block changed.

### U2: review-queue header for refreshed claims

- **Test:** `_format_header` for an item with a `refresh` block includes `Was published: {verdict} (reviewed {date})`. When the verdict changed, it adds `verdict changed; approval will ask for a correction`.
- **Code:** read the block in `find_publication_queue` (`orchestrator/review_queue.py`) into `QueueItem`, and render it in `_format_header` (`:170`).

### D1: docs

- `docs/architecture/content-model.md` sidecar table (`:110-138`): add the `refresh.*`, `audit.auditor_reasoning`, `audit.evidence_gaps`, `audit.needs_review_reasons` and `human_review.verdict_override` rows.
- `docs/runbook.md`: a "Refreshing a published claim" section covering four steps. Run `dr claim-refresh`, then `dr review-queue`; for a changed verdict, write a one-line correction at the `a` prompt; commit only after approval.
- `docs/UNSCHEDULED.md`: mark RF8 and RF9 done with commit shas.

## Verification (V1)

1. `inv test` passes, and the new tests failed before their code changes (record the failing run in the commit message or PR notes).
2. `uv run dr lint --severity error` passes on the current tree (L1 rollout).
3. End-to-end on a scratch copy of a published claim:
   - `dr claim-refresh <claim>` writes a sidecar with `refresh.previous` equal to the pre-run published state.
   - `dr review-queue` shows the "Was published" line.
   - Approving with a correction adds the `corrections` entry and removes `refresh`.
   - `npm run build` renders "Corrected {date}: {summary}" and "Previous verdict: {label}" on that page.
4. `dr publish --dry-run --all` lists the changed-verdict refresh as skipped.

## Out of scope

- **RF7** (refresh overwrites `seo_title` and drops `cap_rationale`): the reviewer can fix both with `e` before approval, and it is tracked in UNSCHEDULED.
- The append-only transition log, ULIDs, backfill, orphan sidecar CI, and ClaimReview JSON-LD fields: [`deferred/audit-trail-extensions.md`](deferred/audit-trail-extensions.md).
- Keeping the published version live at its URL while a refresh awaits review (writing the refresh to a side file instead of in place). The runbook rule (approve before commit) plus L2 covers it at today's scale. Revisit if more than one person runs refreshes.
- Keeping dropped sources from `inv audit.prune`.

## Questions for Brandon

- **Q1:** `brave-browser/renewable-energy-hosting` changed from `false` to `unverified` in the 2026-10-04 refresh, was re-approved, and has no correction. Should a `corrections` entry be added by hand (operator-owned, kept by refresh per K3), with a summary you write? This plan does not add it.
- **Q2 (decided 2026-10-06, Brandon):** L2 stays a warning.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-10-06 | agent (claude-opus-5-5, plan review) | initial plan + self-review | Written from RF8 and RF9 (`docs/UNSCHEDULED.md`) and the reader-facing slice of `audit-trail-extensions.md`. Facts K1 to K13 checked against HEAD `081ec37`. Self-review changes:<br>- Added P5 and the `verdict_override` field after finding that the `e` action can legitimately change the verdict (K11), which would otherwise make L1 fail on valid claims.<br>- Made L2 a warning because pre-commit checks the whole tree (K13).<br>- Required a person-written correction summary rather than generated text.<br>- Added the P3 idempotency test for a sidecar write that fails after the frontmatter write.<br><br>Second pass (advisor):<br>- Confirmed K10 (no production draft filter for claims).<br>- Re-sourced K13 to the local hook.<br>- Spelled out the P3 write order.<br>- Added Q2. |
