# Plan: cleaner `dr` CLI output — phase 2

**Status**: Draft
**Created**: 2026-05-08
**Revised**: 2026-05-08 (scoped down after review — see History)
**Predecessor**: `docs/plans/completed/dr-cli-output-cleanup_completed.md` (Phase 1 shipped in commit `5616aaa`)

## Context

Phase 1 silenced third-party transport noise (`httpx` / `httpcore` / `urllib3` clamped to WARNING in `pipeline/common/logging_setup.py:227-228`), collapsed the wayback warning to one structured line, added a `Brave search:` per-query INFO log (`pipeline/researcher/agent.py:30`), de-duplicated `progress()` under `--verbose` via a console-handler filter (`logging_setup.py:140-142, 224`), and added the missing `Onboard step 4: per-template research` L1 marker (`pipeline/orchestrator/pipeline.py:1366`). Net result: default-mode noise is gone and `--verbose` no longer double-prints progress lines.

After review, phase 2 is trimmed to two items: a glyph + horizontal-rule vocabulary that replaces the eight `=` × 60 dividers across command report blocks, and a reconciliation of the `Step N/4` vs `Step N/5` L3 sub-step strings into a shared verb label set. Both are call-site label changes; together they're the entire visible win without taking on a new dependency.

Items deliberately deferred (with reasoning in the History section): a unified `Renderer` abstraction, `--json` output mode, a live `rich` status panel, a per-template ingest progress bar, and a sweep across the other `dr` commands.

## Goal

Apply the planned glyph + horizontal-rule vocabulary to the existing call sites, and rename the L3 sub-step strings to a shared verb-only set indented under the L2 line. Operators absorb a one-time text diff; the file log keeps `Step N/M` so post-hoc grep is unaffected.

## Approach

Two items. Independently shippable, but small enough to land together in one commit.

### C. Reconcile L3 sub-step format

**What.** `verify_claim` emits `Step 1/4`–`Step 4/4` at `pipeline/orchestrator/pipeline.py:278, 298, 373, 388`. `research_claim` emits `Step 1/5`–`Step 5/5` at `pipeline.py:823, 840, 893, 905, 956`. Numerator changes because `research_claim` adds a "Write source files" step. Replace with shared verb labels (no numerator), indented two spaces under the L2 line:

- `verify_claim`: `  › Searching` / `  › Ingesting` / `  › Analysing` / `  › Auditing`
- `research_claim`: `  › Searching` / `  › Ingesting` / `  › Writing sources` / `  › Analysing` / `  › Auditing`

Visual hierarchy reads: `[i/N] Researching: <slug>` (L2) then `  › Searching` (L3).

**Where.** `pipeline/orchestrator/pipeline.py:278, 298, 373, 388, 823, 840, 893, 905, 956` — nine `progress(...)` / `say(...)` call sites, label change only.

**File-log behavior.** Console gets the indented verb form; `info.log` keeps the `Step N/M` strings unchanged. Implementation: emit the indented form via the console-bound `progress()` path and continue logging the structured numerator separately, OR pass both as kwargs the formatter can pick from. Simplest path: route the verb label through `progress()` (console-only after the §1.4 filter) and keep a `logger.info("Step %d/%d: …", n, total)` alongside for the file log. Decide at implementation; both shapes are local to `pipeline.py`.

**Out of scope.** The `Step 1 — Query planning` strings in `dr step-research` (`cli.py:227, 235, 240`) — same exclusion as phase 1.

**Effort.** ~0.5 day.

### D. Glyph + horizontal-rule vocabulary

**What.** Sparse glyph set: `▶` phase start, `›` sub-step (paired with item C), `✓` ok, `!` warn, `✗` fail. Dim-cyan horizontal rules between L1 phases and around the onboard report block, replacing the eight `=` × 60 dividers at `pipeline/orchestrator/cli.py:541, 543, 605, 731, 733, 754, 1563, 1565, 1620`.

**Where.**

- `pipeline/common/logging_setup.py` — add `hr()` helper (writes a divider to stderr, dim-cyan when stderr is a TTY and color is allowed) and a `glyph=` kwarg on `progress()`.
- `pipeline/orchestrator/cli.py` — replace the nine divider sites listed above with `hr()`.
- `pipeline/orchestrator/pipeline.py:1245, 1290, 1314, 1366` — `hr()` between L1 phases; `glyph="▶"` on the per-template `[i/N] Researching:` line at `pipeline.py:1370`.
- Existing glyph-equivalents at `cli.py:1593, 1599, 1605, 1611, 1618` get aligned to the new vocabulary (`✓` / `!` / `-`).

**Color and TTY behavior.** `click.style(..., dim=True, fg="cyan")` for dim-cyan; that path already honors `NO_COLOR`. ASCII fallback for non-TTY: `▶ › ✓ ! ✗` collapse to `>`, `-`, `OK`, `!`, `X`. Detect via `sys.stderr.isatty()`.

**Effort.** ~1 day.

## Sequencing

C and D land together in one PR. Both are call-site label changes through `pipeline.py` and `cli.py`; doing them paired avoids two passes through the same code, and the `›` glyph in D is the same one used in C's indented sub-step lines.

Total estimated effort: ~1.5 days.

## Verification

Manual smoke test (matches phase 1's verification posture — no new automated tests):

```
dr onboard "Anthropic" --type company --only contributes-to-environmental-causes
dr onboard "Anthropic" --type company --only contributes-to-environmental-causes --verbose
```

Expected: no `=` × 60 dividers in the report block; dim-cyan rules between L1 phases and around the report block; `[i/N] Researching:` lines prefixed with `▶`; per-template L3 lines appear as `  › Searching` / `  › Ingesting` / etc. (no `Step N/M` in console); `info.log` still contains `Step N/M` lines for grep.

Also run the existing tests; none assert user-facing strings, so they should pass unchanged:

```
cd pipeline && python -m pytest tests/test_logging_setup.py tests/test_onboard.py tests/test_terminal_fetch.py
```

## Out of scope

Inherited from phase 1:

- File-log format (`logs/info.log`, `logs/debug.log`) — keep as is.
- Rewriting `logger.info` call sites globally to use `progress()`.
- The `Step 1 — Query planning` strings in `dr step-research` (`cli.py:227, 235, 240`).

Cut from this phase 2:

- **Unified `Renderer` abstraction** (was item A) — premature for ~6 commands; revisit when there's a second consumer of report data (web UI, watch dashboard, Slack notifier).
- **`--json` output mode** (was item B) — no downstream consumer today; YAGNI. Revisit when a script, CI gate, or dashboard actually needs to parse a report.
- **Live `rich` status panel for onboard** (was item E) — needs `rich` (still absent from `pipeline/pyproject.toml`), and its visual value scales with concurrency. Defer until `docs/plans/onboard-parallelize-templates.md` ships.
- **Per-template ingest progress bar** (was item F) — solves the "perceived hang" complaint that ranked second behind the "I can't tell what query Brave is running" complaint phase 1 already addressed. Revisit if it comes back.
- **Sweep other `dr` commands** (was item G — `claim-probe`, `claim-draft`, `claim-refresh`, `step-ingest`, `review-queue`, `publish`) — opportunistic, not planned. Apply C/D's vocabulary when each command is touched for an unrelated reason.

## Cross-references

- Predecessor: `docs/plans/completed/dr-cli-output-cleanup_completed.md` (Phase 1, commit `5616aaa`).
- Concurrency intersection: `docs/plans/onboard-parallelize-templates.md` — the deferred live panel (was item E) wants this plan's deterministic-ordering buffer to land first.
- Dependency context: `docs/plans/wayback-archive-job.md` — interim `skip_wayback=False` made the wayback warning loud; phase 1 fixed that and nothing here reverts it.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-08 | agent (opus-4-7) | initial draft | Extracted from the combined Phase 1 + Phase 2 plan after Phase 1 shipped (commit `5616aaa`). Verified line numbers against post-Phase-1 code: `cli.py` divider sites are 541/543/605/731/733/754/1563/1565/1620 (eight, not the original plan's two); L3 step strings live at `pipeline.py:278/298/373/388` (verify_claim, 4-step) and `823/840/893/905/956` (research_claim, 5-step); `Onboard step 4` log is now at `pipeline.py:1366`; per-template loop starts at `pipeline.py:1367`; `_ingest_urls` waterfall at `pipeline.py:596-634` uses `dispatch_sem = asyncio.Semaphore(2)` not 8 (source plan's "8 concurrent" was conflating `llm_concurrency=8` with URL fetch concurrency — corrected). Confirmed `rich` is not currently in `pipeline/pyproject.toml` dependencies. Drafted seven items (A–G) with sequencing argument and dependency graph. |
| 2026-05-08 | parallel agent review (Explore + Plan) | scope cut | Verification agent confirmed all line-number references and factual claims are accurate. Design agent flagged the seven-item scope as ~3× the user-visible payoff, called the `Renderer` trinity speculative for ~6 commands, and recommended trimming to D+C+B. After clarifying questions: no consumer for `--json` exists, operators can absorb a one-time text diff, manual smoke test is the test policy. Cut to **C + D only** (~1.5 days). Items A, B, F, G dropped; E deferred until the parallelize-templates plan ships. |
