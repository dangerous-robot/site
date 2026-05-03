# Plan: `dr` CLI redesign — docs, tests, and scripts

**Status**: Draft — implementation plan at `docs/plans/drafts/dr-command-redesign.md`; this file covers only the support work (docs, tests, tooling). No architecture or CLI implementation details here.

---

## Goal

After the CLI changes in `dr-command-redesign` land (removal of `verify` and `verify-claim`; addition of `claim-probe`, `claim-draft`, `claim-refresh`, `claim-promote`), update all references in documentation, tests, and AGENTS.md so that no active reference file points at removed commands.

---

## Non-goals

- Modifying `pipeline/orchestrator/cli.py` or any pipeline source. That is the code plan's job.
- Updating completed plans, HISTORY.md, or historical roadmaps. See the rule below.
- Updating the API-provider final report or reports in `docs/reports/`. These are evaluation artifacts, not operator instructions.

---

## Rule: what gets updated vs left alone

**Update**: any file whose audience is an operator, agent, or test runner acting on the current state of the codebase. This includes architecture docs, active plans (non-completed), AGENTS.md, README-like docs, and test files.

**Leave as-is**: files that are historical records of decisions, completed work, or evaluation artifacts:
- `docs/HISTORY.md`
- `docs/v1.0.0-roadmap.md` (lines 112-113 note verified below; acceptable as record)
- All files under `docs/plans/completed/`
- `docs/reports/API-PROVIDER-FINAL-REPORT.md`

---

## 1. Test updates

### 1.1 `pipeline/tests/test_cli_smoke.py`

**Change**: Replace the `@pytest.mark.parametrize` subcommand list on line 10.

Current list: `["", "verify", "verify-claim", "reassess", "ingest"]`

New list:
```python
["", "claim-probe", "claim-draft", "claim-refresh", "claim-promote", "reassess", "ingest"]
```

Both `"verify"` and `"verify-claim"` are removed. The test suite asserting `No such command` (item 7 of the verification checklist) implicitly comes from these names being absent from the parametrize list — do not add them with a negative assertion; just delete them. If explicit "hard-removed" coverage is wanted, it belongs in `test_cli.py` (see §1.2 new scenarios below).

### 1.2 `pipeline/tests/test_cli.py`

#### Rename class

Rename `TestVerifyClaimCLI` to `TestClaimDraftCLI` at the class definition site.

#### Replace `TestVerifyOptions` test

Replace the one method in `TestVerifyOptions` that calls `["verify", "--help"]`:

| Method | Old command | New command |
|---|---|---|
| `test_verify_help_lists_candidate_pool_size` (line 92) | `["verify", "--help"]` | `["claim-probe", "--help"]` |

Rename the class `TestVerifyOptions` → `TestClaimProbeOptions` to stay consistent.

#### Replace `TestClaimDraftCLI` (was `TestVerifyClaimCLI`) methods

All five methods below call `["verify-claim", ...]`. Each must be updated to call `["claim-draft", ...]` instead. The test logic is otherwise unchanged.

| Method (line) | Old invocation | New invocation |
|---|---|---|
| `test_dash_sentinel_passes_none_resolved_entity` (132) | `["verify-claim", "-", "some claim"]` | `["claim-draft", "-", "some claim"]` |
| `test_valid_entity_ref_parsed_before_asyncio_run` (163) | `["verify-claim", "products/widget", "some claim"]` | `["claim-draft", "products/widget", "some claim"]` |
| `test_invalid_entity_ref_raises_usage_error` (179) | `["verify-claim", "invalid-no-slash", "test claim"]` | `["claim-draft", "invalid-no-slash", "test claim"]` |
| `test_unknown_type_dir_raises_usage_error` (194) | `["verify-claim", "badtype/foo", "test claim"]` | `["claim-draft", "badtype/foo", "test claim"]` |
| `test_missing_entity_file_raises_usage_error` (209) | `["verify-claim", "products/nonexistent", "test claim"]` | `["claim-draft", "products/nonexistent", "test claim"]` |

#### New class: `TestClaimRefreshCLI`

Add a new class with the following five test methods. All use `CliRunner` and monkeypatch to avoid live pipeline calls.

1. `test_not_found_path_exits_with_error`: invoke `["claim-refresh", "microsoft/nonexistent-claim"]`, assert `exit_code != 0`, assert `"onboard --only"` appears in output.
2. `test_ad_hoc_draft_rejected`: create a claim file with no `criteria_slug` in frontmatter; invoke `claim-refresh` on it; assert `exit_code != 0`, assert `"claim-promote"` appears in output.
3. `test_blocked_claim_with_criteria_slug_allowed`: create a claim file with `status: blocked` and a `criteria_slug` present; monkeypatch the pipeline call to succeed; assert `exit_code == 0`.
4. `test_template_backed_claim_writes_same_path`: create a claim file with `status: published` and a `criteria_slug`; monkeypatch the write call to capture the `claim_slug` argument; assert the written slug matches the original filename stem.
5. `test_sector_entity_claim_refresh`: create a claim file backed by a sector template (e.g. `sectors/ai-llm-producers`, `criteria_slug: signed-ai-safety-commitments`); monkeypatch `render_claim_text` to return a sector-name-substituted string; assert the pipeline call receives the substituted claim text (not the raw `ENTITY ...` placeholder text).

#### New class: `TestRemovedCommands`

Add a small separate class for explicit "hard removed" coverage, distinct from `TestClaimRefreshCLI`:

1. `test_verify_removed`: invoke `["verify", "--help"]` via `CliRunner`; assert `exit_code != 0`.
2. `test_verify_claim_removed`: invoke `["verify-claim", "--help"]` via `CliRunner`; assert `exit_code != 0`.

#### New class: `TestClaimPromoteCLI`

Add a new class with the following four test methods. Use a temporary `templates.yaml` and monkeypatch `resolve_repo_root`.

1. `test_already_template_backed_rejected`: claim file has `criteria_slug` set; assert `exit_code != 0`, assert `"already template-backed"` in output.
2. `test_slug_collision_rejected`: claim file has no `criteria_slug`; templates.yaml already has the slug the user enters; assert `exit_code != 0`, assert "already exists" or similar in output.
3. `test_happy_path_appends_template_yaml`: happy path with interactive input; assert `exit_code == 0`, assert new YAML entry exists in templates.yaml with field order `slug/text/entity_type/topics/core/notes`.
4. `test_placeholder_substituted_by_entity_type`: parametrize over all three entity types. For `company`: assert `COMPANY` appears in the written `text` field. For `product`: assert `PRODUCT`. For `sector`: assert `ENTITY`. Use a distinct claim title per variant so the substitution is unambiguous.

---

## 2. Documentation updates

### Active-reference files (update)

Each row is a separate edit. "What to change" is described at the field level; exact wording is left to the implementer.

#### `AGENTS.md`

| Line | Current text | Change |
|---|---|---|
| 109 | `dr verify`, `dr verify-claim`, `dr onboard` in `--interactive` note | Replace `dr verify` with `dr claim-probe`, `dr verify-claim` with `dr claim-draft` |
| 117 | table row: "Pipeline operations: verify, verify-claim, evaluate, ingest" | Update to list `claim-probe`, `claim-draft`, `claim-refresh`, `claim-promote` |
| 123 | `uv run dr verify "Entity" "claim text"` | Change to `uv run dr claim-probe "Entity" "claim text"` |
| 124-125 | two `uv run dr verify-claim ...` examples | Change both to `uv run dr claim-draft ...` |
| 135 | `dr verify` bullet description | Rename to `dr claim-probe`; update description to "dry run, no writes" |
| 136 | `dr verify-claim` bullet description | Rename to `dr claim-draft`; update description to "writes status: draft, no criteria_slug". Add bullets for `dr claim-refresh` and `dr claim-promote`. |

#### `docs/architecture/glossary.md`

| Lines | Change |
|---|---|
| 59-62 | In the pipeline components table, four rows reference `dr verify-claim` and `dr verify` as the invocation. Update to `dr claim-draft`/`dr claim-probe`; add `dr claim-refresh` for Researcher, Ingestor, and Analyst rows (those three agents run under `claim-refresh`). Do NOT add `dr claim-promote` to those rows — `claim-promote` only edits `research/templates.yaml` and does not invoke any pipeline agent. |
| 152 | "Verify" term row: update CLI entry from `dr verify` to `dr claim-probe` |
| 153 | "Verify-claim" term row: rename the term to "Claim-draft"; update CLI entry from `dr verify-claim` to `dr claim-draft`; update description. Add new rows for "Claim-refresh" and "Claim-promote". |

#### `docs/architecture/research-flow.md`

| Lines | Change |
|---|---|
| 17 | Prose referencing `dr verify-claim` → `dr claim-draft` |
| 21 | Mermaid state transition label: `dr verify-claim / dr onboard / manual edit` → `dr claim-draft / dr claim-refresh / dr onboard / manual edit` |
| 28 | Mermaid transition: `dr verify-claim re-run` → `dr claim-refresh` |
| 52 | Flow diagram node: `dr verify-claim claim-text` → `dr claim-draft claim-text` |

#### `docs/architecture/open-issues.md`

| Lines | Change |
|---|---|
| 58 | Description of `dr verify` (no writes) and `dr verify-claim` (file-writing): update to `dr claim-probe` and `dr claim-draft`. Note: this issue describes a historical design concern about shared code paths. The framing can stay; only the command names update. |
| 62 | Same paragraph: `dr verify` → `dr claim-probe` |

#### `docs/pre-launch-triage.md`

| Line | Change |
|---|---|
| 33 | Row P2 references `dr research` → `dr verify-claim` rename. Update to note the command is now `dr claim-draft` (second rename). Keep destination column pointing at `pre-launch-quick-fixes.md` (which is completed and records the first rename; the second rename is this plan). |

#### `docs/plans/token-usage-log.md`

| Lines | Change |
|---|---|
| 323 | `Run dr verify once on a canned claim` → `Run dr claim-probe once on a canned claim` |
| 324 | `running a full dr verify` → `running a full dr claim-probe` |

#### `docs/plans/multi-provider.md`

Both Part 1 and Part 2 are marked complete. Their acceptance bars and validation runs describe what was done to close those gates — that is historical narrative, not forward-looking instruction. Leave all `dr verify` and `dr verify-claim` references in this file unchanged.

Part 3 (global fallback + multi-provider) contains no `dr verify` or `dr verify-claim` references; no edits needed there either.

#### `docs/plans/wayback-archive-job.md`

| Line | Change |
|---|---|
| 7 | Interim-status note: `dr verify` / `dr verify-claim` / `dr onboard` flag defaults → `dr claim-probe` / `dr claim-draft` / `dr onboard` |

#### `docs/plans/onboard-parallelize-templates.md`

| Line | Change |
|---|---|
| 13 | "Do NOT add to `dr verify` / `dr research` (single-claim commands)" → "Do NOT add to `dr claim-probe` / `dr claim-draft` (single-claim commands)" |

#### `docs/plans/researcher-host-blocklist.md`

| Line | Change |
|---|---|
| 203 | `dr verify` / `dr onboard` run → `dr claim-probe` / `dr onboard` run |

#### `docs/plans/data-lifecycle-policy_stub.md`

| Line | Change |
|---|---|
| 18 | Table row: `Re-run dr research (post-rename: dr verify-claim) on an existing claim` → `Re-run dr claim-draft on an existing claim` |

#### `docs/plans/drafts/pipeline-dedup-detection_stub.md`

| Lines | Change |
|---|---|
| 9 | `dr verify-claim` / `dr onboard` ingestor reference → `dr claim-draft` / `dr onboard` |
| 10 | `dr verify-claim "<text>"` → `dr claim-draft ...` |
| 36 | `dr verify-claim` claims → `dr claim-draft` claims |
| 43 | `dr verify-claim`: ad-hoc claims note → `dr claim-draft` |
| 45 | in-pipeline ingestor note → update `verify-claim/onboard` to `claim-draft/onboard` |

#### `docs/plans/drafts/pipeline-state-machine_stub.md`

| Line | Change |
|---|---|
| 83 | `dr verify-claim` vs `dr onboard` question → `dr claim-draft` vs `dr onboard` |

### Files confirmed as historical record (no change)

- `docs/HISTORY.md` — changelog; leave all entries intact
- `docs/v1.0.0-roadmap.md` lines 112-113 — checked; references are in the completed checklist as historical items; leave as-is
- `docs/plans/completed/*.md` — all files under this directory; historical
- `docs/reports/API-PROVIDER-FINAL-REPORT.md` line 93 — evaluation artifact; leave as-is

### CI and tooling

A grep of `tasks.py`, `.github/`, `Makefile`, and `.pre-commit-config.yaml` found zero references to `dr verify` or `dr verify-claim`. No changes needed there.

---

## 3. Verification checklist

After implementing the code plan and this support plan:

1. `pytest pipeline/tests/test_cli_smoke.py` passes; the parametrize list contains `claim-probe`, `claim-draft`, `claim-refresh`, `claim-promote` and does not contain `verify` or `verify-claim`.
2. `pytest pipeline/tests/test_cli.py` passes; all `TestVerifyClaimCLI` / `TestVerifyOptions` references are renamed; all five new `TestClaimRefreshCLI` and four new `TestClaimPromoteCLI` tests pass.
3. `grep -r "dr verify\b\|dr verify-claim" AGENTS.md docs/ --include="*.md"` returns only lines in `docs/HISTORY.md`, `docs/v1.0.0-roadmap.md`, `docs/plans/completed/`, `docs/reports/`, and `docs/plans/drafts/dr-command-redesign.md` (the code plan itself, which documents the old names in its command-map table). Zero hits outside those paths.
4. `grep -r "\"verify\"\|\"verify-claim\"" pipeline/tests/ --include="*.py"` returns zero hits (all replaced in test invocations).

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-05-03 | agent (claude-sonnet-4-6) | initial draft | Created from `docs/plans/drafts/dr-command-redesign.md` §4-5; expanded doc file list via grep; enumerated test methods by name; added historical-record rule; added CI/tooling section (confirmed no changes needed). |
| 2026-05-03 | advisor (claude-opus) | review pass | Four fixes applied: (1) verification grep now excludes `drafts/dr-command-redesign.md`; (2) `multi-provider.md` left entirely unchanged (Parts 1+2 are complete history, Part 3 has no hits); (3) glossary lines 59-62 instruction tightened to exclude `claim-promote` from agent-invocation rows; (4) `TestRemovedCommands` split into its own class, out of `TestClaimRefreshCLI`. |
