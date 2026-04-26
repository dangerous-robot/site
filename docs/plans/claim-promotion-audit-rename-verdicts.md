# Plan: Claim Promotion, `dr audit` Rename, Verdict Definitions

**Status**: `[ ] in progress`
**Created**: 2026-04-23
**Promoted**: 2026-04-23
**Supersedes**: items 2 and 4 in `docs/architecture/open-issues.md`; validates the "Verdict definitions" section in `docs/architecture/glossary.md`.

| Section | Status |
|---|---|
| 1. Claim promotion via `dr review` | `[ ] in progress` |
| 2. `dr audit` rename to `dr reassess` | `[ ] in progress` |
| 3. Verdict definitions validation | `[ ] in progress` |

---

## 1. Claim promotion: `dr review` owns status flip

### Problem

New claims are written with `status: draft` in `persistence.py` `_write_claim_file()` (line 130). Nothing flips them to `status: published`. `dr review` today (`pipeline/orchestrator/cli.py` lines 524-588) only writes `human_review.*` fields to the `.audit.yaml` sidecar and never touches the claim file. The v1.0.0 roadmap release criteria include: "CI check enforces `human_review.reviewed_at` non-null on all `status: published` claims" (`docs/v1.0.0-roadmap.md` release criteria checklist). A sidecar-only review produces a published-but-unreviewable (or never-published) state.

### Direction

Give `dr review` the power to flip claim status in one step. Justification: the human sign-off and the publish decision are the same decision. Splitting them into two manual acts (edit frontmatter, then run `dr review`) doubles the operator burden, invites drift (reviewed but not published, or published but not reviewed), and makes the CI gate incoherent. Deleting the command sounds lean but leaves the sidecar writable only by pipeline runs, which means a reviewer cannot record notes or a PR URL without a full re-run.

### Mechanics

`dr review` gains two mutually exclusive flags plus the existing sidecar write:

- `dr review --claim <entity-slug>/<claim-slug> --approve` : writes sidecar with `human_review.reviewed_at` set, then flips `status: draft` to `status: published` in the claim frontmatter. Rejects if current status is not `draft` (error: "claim already published; use --archive to retire").
- `dr review --claim <entity-slug>/<claim-slug> --archive` : writes sidecar (records the archive decision in `human_review.notes` with operator-supplied text or a default "archived" note), then flips `status: published` to `status: archived`. Rejects if current status is not `published`.
- `dr review --claim <entity-slug>/<claim-slug>` (no action flag) : current behavior preserved, writes sidecar only, does not touch the `.md`. Useful for recording a review on a claim that stays in draft (sign-off without publish).

The reviewer identity resolution (explicit `--reviewer`, else `git config user.email`, else hard error) already lives in `cli.py` lines 559-576 and is reused unchanged by `--approve` and `--archive`.

### Atomicity and ordering

Two files are mutated. Write order is fixed: **sidecar first, then `.md`**. Rationale:

- Sidecar write fails: claim remains `draft`, no `human_review.reviewed_at`. Clean, operator retries.
- `.md` write fails after sidecar write succeeds: claim is `reviewed but not promoted` (sidecar records the review, `.md` status unchanged). Recoverable by re-running the command, which is idempotent on sidecar updates and still finds the pre-action status.
- Reverse order (`.md` first) creates `published-but-unreviewed`, which is exactly the state the v1.0.0 CI gate exists to prevent.

Before either write, both files must pass a pre-flight check: sidecar exists, `.md` frontmatter parses, current status matches `expected_current`. Any failure in pre-flight aborts before touching either file.

### Edge cases

- **Missing `status` field** (older claim pre-dating the `status: draft` default): treat as `draft` for `--approve`; treat as error for `--archive` ("cannot archive: claim has no status field; publish first or edit the file manually").
- **Malformed frontmatter**: `parse_frontmatter` raises `ValueError`. Catch and raise `click.ClickException("malformed frontmatter in <path>: <message>")` with non-zero exit.
- **Already-terminal status**: `--approve` on an `archived` claim rejects ("cannot approve an archived claim"). Bare `dr review` on any status still writes sidecar only.

### Implementation steps

1. Update `pipeline/orchestrator/cli.py` `review` command (lines 524-588):
   - Add `--approve` and `--archive` Boolean flags. Use a manual guard in the command body (the codebase has no `MutuallyExclusiveOption` pattern and no `ClickException` uses today; stick to a plain `if approve and archive: raise click.ClickException(...)`).
   - If `--approve` or `--archive`: call `_set_claim_status()` from `persistence.py` after the sidecar write succeeds. Pre-flight validation (parse `.md`, verify status) happens before the sidecar write.
   - Update the success message to name both files when status changed: `Marked reviewed and published: research/claims/<slug>.md (+ .audit.yaml)`. Bare review keeps the existing sidecar-only message.
2. Add `_set_claim_status(claim_path: Path, new_status: str, expected_current: str | None) -> None` to `pipeline/orchestrator/persistence.py`. Uses `common.frontmatter.parse_frontmatter` / `serialize_frontmatter` (confirmed to exist with these signatures). Raises `ValueError` if current status does not match `expected_current`. When `expected_current is None`, skips the check (not needed for v1.0.0 but keeps the helper composable).
3. Add tests to `pipeline/tests/test_audit_trail.py` (existing location for `dr review` tests, pattern: `CliRunner().invoke(main, [...])` with `tmp_path` fixtures, see lines 235-302):
   - `--approve` flips `draft` to `published`, writes both files.
   - `--approve` on already-`published` claim exits non-zero, leaves both files unchanged (status bytes and sidecar bytes compared).
   - `--approve` on claim with no `status` field (frontmatter lacks the key) succeeds and writes `status: published`.
   - `--archive` flips `published` to `archived`.
   - `--archive` on `draft` claim exits non-zero.
   - Bare `dr review` writes only the sidecar, `.md` bytes unchanged.
   - Malformed frontmatter (no delimiters) exits non-zero with a clear message and neither file is mutated.
   - `--approve` and `--archive` together exits non-zero before any write.
   - Atomicity: mid-flight failure simulation where the `.md` write step raises leaves the sidecar in its *updated* state (sidecar is the commit point); document this behavior in the test docstring. Operator guidance: rerun with `--approve`, which re-detects still-`draft` and completes the flip.
4. Update `docs/plans/audit-trail.md` §"`dr review` CLI command" (lines 172-194) to document the new flags and the sidecar-first ordering. Mark the previous "writes only the sidecar" behavior as the no-flag path. Update acceptance checklist entries at lines 281-282 and 290 to cover the new flags.
5. Update `docs/v1.0.0-roadmap.md` §5 ("Human sign-off", bullet list at line ~100) to note `dr review --approve` as the supported promotion path.
6. Update `docs/architecture/research-workflow.md` "Maintain" section and `docs/architecture/research-flow.md` section 6 (human review) to document the `--approve` / `--archive` lifecycle.
7. The CI gate for `status: published` + `human_review.reviewed_at` non-null (release criteria, `v1.0.0-roadmap.md`) is a downstream consumer of this work. Writing that CI check is out of scope here but blocked by this section.

### Dependencies

- `Verdict.NOT_APPLICABLE` already exists in `pipeline/common/models.py` (line 13). `status` enum already exists in `src/content.config.ts` (line 159). No schema work needed before this section.
- `claim-status_stub.md` Step 11 (pipeline writes `status: draft` on new claims) is already landed in `persistence.py:130`. The input state this section expects is real.

### Out of scope

- PR automation (opening a PR from the CLI). The reviewer runs `git commit` / `gh pr create` by hand, same as today.
- Multi-reviewer or quorum logic.
- Undoing a status change (`--revert`). Not needed for v1.0.0; use `git revert`.

---

## 2. Rename `dr audit` to `dr reassess`

### Problem

`dr audit` (`pipeline/orchestrator/cli.py` lines 189-307) re-runs the Auditor agent against existing claim files to check whether the verdict still holds. The name collides with the "Citation Auditor" role (broken refs, missing sources, stale dates), whose scope is actually covered by `scripts/check-citations.ts` and `dr lint`. Contributors reading `AGENTS.md` reasonably assume `dr audit` is the Citation Auditor's tool. It is not.

### Direction

Rename `dr audit` to `dr reassess`. Justification: "reassess" accurately names the function (re-evaluate an existing verdict against current sources), is a single word (matches the one-word `verify`, `research`, `ingest`, `onboard`, `review`, `lint` sibling commands), and frees "audit" for potential future use by the Citation Auditor scope without ambiguity. "recheck-verdict" is accurate but verbose and introduces a hyphen no other subcommand uses. "re-audit" doubles down on the conflicting vocabulary.

No deprecation alias. The command has one known user (the operator) and the pipeline is pre-1.0. A hard rename avoids carrying a confusing alias forward. If a muscle-memory invocation fails, Click prints the list of valid commands.

### Implementation steps

1. In `pipeline/orchestrator/cli.py`:
   - Rename the `audit` function at line 198 and the `@main.command()` at line 189 to `reassess`. Update the docstring examples at lines 211-212 (`dr audit --entity ecosia` → `dr reassess --entity ecosia`, `dr audit --claim ...` → `dr reassess --claim ...`). Update the comment banner at line 186 to `# dr reassess`.
   - The function body is self-contained; no other code reference in `cli.py` needs to change.
2. Update the following active references (verified by grep; paths and lines are the full set):
   - `AGENTS.md:100` — `uv run dr audit --entity ecosia` example.
   - `AGENTS.md:111` — `dr audit` bullet in command list.
   - `docs/architecture/research-workflow.md:54` — table row for `dr audit`.
   - `docs/architecture/research-workflow.md:56` — rename note ("will be renamed to `dr reassess`"); replace with past-tense wording, and remove the forward reference to this plan §2 now that the rename has landed.
   - `docs/architecture/open-issues.md:10` — "`dr audit` rename -> same plan §2" line; mark the rename as complete or leave the back-reference since the open-issues doc is the resolved-items ledger.
   - `docs/plans/arch-docs-pipeline-improvements.md:49` — lists `dr audit` as an implemented command.
   - `docs/plans/arch-docs-pipeline-improvements.md:113` — `dr audit: verdict re-evaluation` description line.
   - `docs/plans/arch-docs-pipeline-improvements.md:115` — cross-reference paragraph.
   - `docs/plans/dr-lint.md:263` — Phase 5 Surface Agent bullet referencing `dr lint` + `dr audit`.
   - `pipeline/tests/test_cli_smoke.py:10` — `pytest.mark.parametrize("subcommand", ["", "verify", "research", "audit", "ingest"])` — replace `"audit"` with `"reassess"`.
3. The `.audit.yaml` sidecar filename is unrelated and stays. The file is an audit trail (provenance record), not output of `dr audit`. Do not rename it.
4. The "Auditor agent" role name and `pipeline/auditor/` package stay. The agent runs during `verify`, `research`, `onboard`, and `reassess`; its identity as the Auditor is independent of the CLI verb.
5. Do not rewrite `docs/plans/completed/pipeline-agent-refactor.md` (contains `dr audit` at lines 184, 292, 323). Completed plans are historical artifacts.
6. `.github/workflows/*.yml` and `scripts/` contain no `dr audit` invocations (verified by grep). No CI or cron changes needed.

### Out of scope

- Adding a new `dr cite-audit` or similar that unifies `scripts/check-citations.ts` and `dr lint`. The existing two-tool split is fine; combining them is a separate decision.
- Any changes to `scripts/check-citations.ts`.

---

## 3. Verdict definitions

### Problem

`docs/architecture/glossary.md` (lines 26-38) has a "Verdict definitions" table with one-line definitions for all 7 verdict enum values. These were synthesized by an agent and not validated. Three cases are flagged as uncertain: the `mostly-true` vs `mixed` threshold, `unverified` vs "no sources cited", and `not-applicable` scope.

### Resolutions

**`mostly-true` vs `mixed`**: the split point is whether the claim's main thrust is supported. `mostly-true` means the core assertion holds and deviations are scoped to caveats, minor factual drift, or outdated specifics that do not change the reader's takeaway. `mixed` means a reader acting on the claim would be misled about at least one material element; different parts of the claim pull in opposite directions. Justification: this is the split that matches how the site will display the verdict (readers see a one-word label). A claim that is "75% correct" is not mixed; a claim with two independent factual parts (one true, one false) is mixed regardless of percentage.

**`unverified`**: keep it as a verdict. It means sources were sought and were insufficient to judge either direction. "No sources cited" is a lint error (already covered by `dr lint`'s missing-sources checks), not a verdict. Justification: `unverified` communicates a real state (we looked, we cannot say) that `dr lint` cannot express. Collapsing the two would lose that signal. The glossary already states this correctly; preserve it.

**`not-applicable`**: covers two sub-cases that share a resolution (the claim has no verdict to assign because the question does not meaningfully apply to this entity):
- Template targets the wrong entity type (e.g., a pricing template applied to a non-commercial project).
- The claim is semantically inapplicable to this specific entity even within the right type (e.g., data retention policy for a hardware company that stores no user data).

Both are `not-applicable`. The distinction between them is operational (the first is caught by Template Screening once implemented; the second requires the Analyst agent to recognize inapplicability from sources), not semantic. From a reader's perspective both render as "this question does not apply."

### Implementation steps

1. Update `docs/architecture/glossary.md` rows (lines 33, 34, 37, 38):
   - `mostly-true` (line 33): "The claim's main thrust is supported by sources. Deviations are scoped to caveats, minor factual drift, or outdated specifics that do not change the reader's takeaway."
   - `mixed` (line 34): "A reader acting on the claim would be misled about at least one material element. Different parts of the claim are supported and contradicted by evidence."
   - `unverified` (line 37): no change; current text already matches the resolution.
   - `not-applicable` (line 38): "The claim does not apply to this entity, either because the template targets a different entity type or because the question is semantically inapplicable to this specific entity."
2. Add a single-line comment above the `verdict` enum in `src/content.config.ts` (line 148) pointing to `docs/architecture/glossary.md` as the operational definition source. Do not duplicate the definitions in the Zod schema comment. There is no existing `describe()` call on the enum; no existing text to preserve.
3. Revise (do not add; the existing `VERDICT SCALE` sections already contain one-liners) the relevant lines in both agent instruction files to match the sharpened glossary wording:
   - `pipeline/analyst/instructions.md` lines 22, 23, 26 — replace the `mostly-true`, `mixed`, `unverified` one-liners with the glossary's sharpened versions. Append a `not-applicable:` line after `unverified:` in the `VERDICT SCALE:` block.
   - `pipeline/auditor/instructions.md` lines 13, 14, 17 — same replacements, same appended line. The Auditor applies the same thresholds when dissenting.
   The `Verdict` enum in `pipeline/common/models.py` already includes `NOT_APPLICABLE` (line 13), so the appended line references an extant enum value.
4. Update `research/templates.yaml` notes or any template docs that discuss expected verdicts (grep for `not-applicable` in `research/templates.yaml` before editing; skip if absent).
5. Spot-check 2-3 existing claims in `research/claims/` near the `mostly-true` / `mixed` boundary and verify that the new framing does not require re-labeling. If it does, file those re-labels as a follow-up content task (not part of this plan).

### Out of scope

- Changing the enum itself (adding or removing values). The enum is fixed by `src/content.config.ts` and `pipeline/common/models.py`; the addition of `not-applicable` is tracked by `claim-status_stub.md`.
- Reviewing every published claim against the new definitions. Spot-check only; re-label work is separate.

---

## Dependencies and ordering

- Section 1 (claim promotion) is a prerequisite for the v1.0.0 roadmap release criterion "CI check enforces `human_review.reviewed_at` non-null on all `status: published` claims" (see release criteria checklist in `docs/v1.0.0-roadmap.md`). That gate cannot be correctly specified until `dr review --approve` exists.
- Section 2 (rename) is independent of Sections 1 and 3. Can land in any order.
- Section 3 (verdict definitions) should land before or together with the v1.0.0 claim-curation pass (roadmap §3). Curation requires operators to confidently apply the definitions, particularly `mostly-true` / `mixed`.
- The audit-trail plan's `dr review` section (lines 172-194) must be updated to reference the new `--approve` / `--archive` flags as part of Section 1's documentation work.
- The `dr-lint.md:263` reference to `dr audit` should be updated as part of Section 2's rename sweep.
