# Plan: `e` (edit fields) action for `dr review-queue`

This is the Phase 2 polish item flagged in [`dr-review-queue.md`](dr-review-queue.md) ("quick edit-frontmatter-only mode"). Scope is intentionally narrower than the parent: a single new action, no new commands, no schema changes.

## Context

`dr review-queue` walks an operator through draft claims awaiting human sign-off. It already prints a header summarizing the editable frontmatter fields (`verdict`, `title`, `takeaway`, `seo_title`, `tags`) plus a sources count, and offers `[a]pprove [d]elete [s]kip [p]review [o]pen-in-editor [q]uit`. The proposal is an `e` action that lets the operator edit just those header fields in `$EDITOR` (vi by default), then preview the result before saving. Narrower and faster than `o`, which drops them into the whole `.md` file.

## Punchline

**~4–5 focused dev hours**, half-to-full calendar day with iteration. Low risk: every primitive needed already exists in the codebase. No new deps.

## Scope (what `e` does)

1. Build a small YAML buffer holding only the editable fields, with a comment header listing allowed verdict values and a note that the `highlight` tag controls homepage scatter inclusion (per AGENTS.md).
2. Open it in `$EDITOR` (blocking; `code` needs `--wait`).
3. On editor exit: YAML-parse, validate (verdict in allowed set, types match).
4. Splice changes into the claim's frontmatter via `parse_frontmatter` → mutate edited keys → `serialize_frontmatter` (body and unrelated keys untouched).
5. Re-render the header against the new values as preview; prompt `[s]ave / [r]e-edit / [d]iscard`.
6. On save: write file, refresh `items[i]` so the loop's next render reflects new values.

### Editable field set

Five frontmatter keys: `title`, `takeaway`, `seo_title`, `tags`, `verdict`. The audit-sidecar fields shown in the header (`analyst_verdict`, `auditor_verdict`, `needs_review`, sources counts) are read-only context; not editable here. Other frontmatter keys (`status`, `criteria_slug`, `entity`, etc.) are out of scope: approval gates depend on them and they should change only via the `o` (full-file) path.

`verdict` is editable because it's the operator's editorial decision; analyst/auditor verdicts are research inputs and remain unchanged. See "Open questions" for the design tension.

### Behaviors / edge cases

- **Editor exits non-zero or buffer unmodified** (vi `:q!`, mtime unchanged): treat as discard, no preview prompt, stay on item.
- **YAML parse error in edited buffer**: print error with line number; prompt `[r]e-edit / [d]iscard`. Re-edit reopens the operator's broken text intact (don't overwrite their work with the original).
- **Validation error** (unknown verdict, wrong type): same `[r]e-edit / [d]iscard` flow.
- **No editor available** (`$VISUAL`/`$EDITOR` unset and `code` not on `PATH`): print actionable error ("set $EDITOR or install VS Code's `code` CLI"), do not advance, do not silently fall through to `o`.
- **Claim file changed on disk** between editor open and save: compare mtime; abort save with warning, prompt re-edit / discard.
- **Race with `o`**: `e` does not coordinate with the non-blocking `o` editor. Operator should close the `o` window before running `e`. No locking in v1.
- **Save then quit** (`s` then `q`): edits are persisted before the quit; quit exits cleanly.

## Work breakdown

| # | Task | Est |
|---|---|---|
| 1 | Editable-field buffer (round-trip; `tags` as `FlowList` to keep flow style) | 30m |
| 2 | Blocking editor helper (handle `code --wait` vs vi-family; tempfile lifecycle) | 30m |
| 3 | Parse + validate (verdict whitelist, type checks, friendly errors) | 45m |
| 4 | Splice back into claim file (reuse `parse_frontmatter`/`serialize_frontmatter`) | 30m |
| 5 | Preview UX (re-render header from in-memory `QueueItem`; save/re-edit/discard prompt) | 30m |
| 6 | Wire `e` into `_ACTIONS` / `_PROMPT` / dispatch in `run_interactive` | 15m |
| 7 | Tests (round-trip, invalid verdict, FlowList preserved, body/other-keys untouched, parse-fail re-edit, no-editor path, mtime-conflict path, monkeypatched-editor functional) | 90–120m |
| 8 | Help text in `cli.py review_queue` docstring + `_PROMPT` | 15m |

**Total: ~4.5–5.5h.**

## Critical files

- `pipeline/orchestrator/review_queue.py` — add `_edit_fields()`; extend `_ACTIONS`, `_PROMPT`, dispatch in `run_interactive` (line 218 loop)
- `pipeline/orchestrator/cli.py:1648` — update help text in the `review_queue` command
- `pipeline/common/frontmatter.py` — reuse `parse_frontmatter`, `serialize_frontmatter`, `FlowList`. No changes expected.
- `pipeline/tests/test_review_queue.py` — add tests alongside existing ones

## Reuse, not rebuild

- `_resolve_editor()` (review_queue.py:163) — extract editor-resolution logic; add a `_run_editor_blocking()` sibling that returns once the editor exits (use `subprocess.run`, append `--wait` for VS Code).
- `parse_frontmatter` / `serialize_frontmatter` — already round-trip claim files cleanly; `set_claim_status` (persistence.py:403) is the reference pattern for "splice one field, write back."
- `_format_header()` — drives the preview by being called with a freshly-built `QueueItem`.

## Risks / gotchas

- **`code` is non-blocking by default.** Detect and append `--wait`; document the requirement for editors that fork (e.g. some GUI configurations).
- **FlowList loss on round-trip.** `tags` deserialize as plain `list`; rewrap to `FlowList` before serialize so the diff stays one line.
- **Restrict editable set.** Don't let `e` touch `criteria_slug`, `status`, `entity`. Approval gates rely on those; they should change only via `o`.
- **No write-on-cancel.** If the operator clears the buffer or exits the editor without changes, treat as discard.
- **`highlight` tag is behavioral.** Editing `tags` can flip homepage scatter inclusion (per AGENTS.md). Surface this in the buffer's comment header so it's not a silent side effect.
- **Editing `verdict` overrides research outputs.** Analyst/auditor verdicts stay in the sidecar but the operator's edit becomes the published verdict. Worth a one-line comment in the buffer header.

## Open questions

- **Should `e` allow adding new frontmatter keys, or only edit the existing five?** Recommendation: edit-only in v1; new keys via `o`. Prevents accidental schema drift.
- **Should `verdict` be editable here at all?** Argument for: it is the operator's editorial decision and the field is operator-owned. Argument against: editing verdict without re-running analysis bypasses the audit trail. Recommendation: keep editable in v1, with the buffer-header warning above. Revisit if we see operators silently flipping verdicts post-research.

## Verification

1. `inv test pipeline/tests/test_review_queue.py` passes
2. Hand test: `dr review-queue` → `e` → tweak `takeaway` in vi → `:wq` → preview shows new takeaway → `s` → reopen claim file, confirm only `takeaway` changed and YAML order/body preserved; tags still inline `[a, b, c]` if present
3. Hand test: invalid verdict ("yes") → friendly error → re-edit path retains broken text
4. Hand test: edit then `d` (discard) → file unchanged on disk
5. Hand test: `e` with `$EDITOR` unset and `code` absent → actionable error, no advance
6. Hand test: edit, modify file externally before saving (`echo >> file`) → mtime mismatch → save aborts with warning

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-05 | agent (claude-opus-4-7) | deep, implementation, iterated | initial draft; verified file paths, function names, FlowList behavior, parse_frontmatter ordering; expanded edge cases, scoped editable set, added open questions |
