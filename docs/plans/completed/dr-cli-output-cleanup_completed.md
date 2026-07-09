# Plan: cleaner `dr` CLI output — phase 1 (now) and phase 2 (future)

**Status**: Done — phase 1 shipped (`pipeline/common/logging_setup.py`); phase 2 shipped separately (see `dr-cli-output-cleanup_phase2_completed.md`, commit 2839537).

**Scope decision**: phase 1 covers `dr onboard` only. Other commands (`claim-refresh`, `claim-probe`, `ingest`) inherit the third-party-logger silencing and the per-query Brave line for free, but their existing one-line summaries are unchanged.

---

## Context

`dr` (the pipeline CLI under `pipeline/orchestrator/cli.py`) currently mixes operator-facing progress with Python's stdlib logging. With `--verbose` the console fills with `INFO [httpx] HTTP Request: …` per-call lines and a multi-line `httpx` 503 hint from Wayback failures; without `--verbose` the operator can't tell what the pipeline is searching for. A few lines duplicate because `progress()` writes both directly to stderr and via `logger.info()`. The outer onboard logs `Onboard step 1`, `step 2`, `step 3` and then drops into the per-template loop with no L1 marker — phase 4 of onboard has no log line of its own.

Phase 1 prunes the noise, fixes the duplication, and adds the missing onboard L1 marker. Visual hierarchy (glyphs, horizontal rules, L3 sub-step renaming) is held for phase 2. Stay on `click` styling — no new dependency.

Two-mode contract:

- **default**: clear high-level progress + summary; no per-request transport logs, no INFO from app loggers
- **`--verbose`**: high-level INFO from app loggers (`orchestrator.*`, `researcher.*`, `ingestor.*`) plus a per-query Brave search line; still silences `httpx` per-request chatter

Phase 2 will adopt a richer renderer (likely `rich`) for live status panels and a structured `--json` output mode for scripting, and will reconcile the L3 step formats. Held until phase 1 lands.

---

## Current state (read-only findings)

- `pipeline/common/logging_setup.py:168` — root logger at `DEBUG`.
- `pipeline/common/logging_setup.py:211-212` — console handler is `WARNING` by default, `INFO` when `--verbose`. Format string: `"%(levelname)s [%(name)s] %(message)s"`. No per-module silencing.
- `pipeline/common/logging_setup.py:133` — `progress()` writes directly to stderr (line 146) **and** calls `logger.info()` via `_progress_logger` (line 148). With `--verbose`, the console handler then re-prints the same line. This is the `[1/4]` duplication.
- `pipeline/orchestrator/cli.py:176` — global `--verbose` flag already wired.
- `pipeline/orchestrator/pipeline.py:272` — `say = progress if cfg.show_progress else logger.info` is the existing per-command progress switch.
- `pipeline/ingestor/tools/wayback.py:38, 71` — `logger.warning("…: %s", exc)` interpolates the full `httpx` exception string, which includes the "For more information check: …mozilla…" trailer. Line 67-68 already uses structured fields and is fine.
- `pipeline/researcher/agent.py:17` — `search_brave` does not log anything user-facing per call; the only per-query signal today is httpx's per-request line.
- `pipeline/orchestrator/pipeline.py:1245, 1290, 1314` — outer onboard logs `Onboard step 1/2/3`; the per-template phase that begins around line 1360 has only a code-comment ("Step 5: Per-template research pipeline") and no L1 log line. The L2 `[i/N] Researching:` line at `pipeline.py:1369` substitutes for it.
- `pipeline/orchestrator/cli.py:1563, 1620` — onboard report renderer brackets the report block with `=` × 60 dividers.
- No tests assert CLI output formatting (checked `test_logging_setup.py`, `test_onboard.py`, `test_cli.py`, `test_terminal_fetch.py`). `test_console_level_respects_verbose` (`test_logging_setup.py:124-141`) asserts logger pass-through but does not pin any user-facing string.

---

## Phase 1 — do now

Goal: kill the noise the user listed; fix the `progress()` duplication; expose a per-query Brave line; add the missing onboard L1 marker so the outer flow reads 1→2→3→4 instead of 1→2→3→drop. Stay on `click` styling.

### 1.1 Silence noisy third-party loggers by default

In `configure_logging()` (`pipeline/common/logging_setup.py`), unconditionally clamp transport/library loggers regardless of `--verbose`:

```python
for noisy in ("httpx", "httpcore", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
```

Effect: drops the "INFO [httpx] HTTP Request: …" line per Brave/Infomaniak/Wayback call. App loggers (`orchestrator.*`, `researcher.*`, `ingestor.*`) are unaffected.

### 1.2 Stop the wayback multi-line spam

In `pipeline/ingestor/tools/wayback.py` lines 38 and 71, replace `logger.warning("…: %s", exc)` with structured fields:

```python
status = getattr(getattr(exc, "response", None), "status_code", "?")
logger.warning("Wayback unavailable (HTTP %s) for %s", status, url)
```

The "For more information check: …mozilla…" tail goes away because we no longer interpolate the full `httpx` exception string. Combined with §1.1, the upstream `INFO [httpx]` line preceding this warning also disappears. The status-only warning at lines 67-68 is already structured; leave it.

### 1.3 Add a per-query Brave log line

In `pipeline/researcher/agent.py:search_brave` (defined at line 17), before the first request:

```python
logger.info("Brave search: %s", query)
```

This is the line that takes the place of httpx's URL-encoded request log. INFO level so it shows under `--verbose` only; default mode relies on the existing "Search executor: N candidates from M queries" summary.

### 1.4 Stop the `progress()` dual-print duplication

`progress()` at `pipeline/common/logging_setup.py:133` writes directly to stderr **and** calls `logger.info()`, which the console handler re-prints under `--verbose`. We need to remove the stderr duplication without losing the `progress()` calls from `info.log` — `info.log` is the operator's post-hoc grep target, and several `progress()` call sites have no parallel `logger.info` (`pipeline.py:1369 "[i/N] Researching"`, `1392 "Skipped"`, `1462/1522/1579 "Blocked"`, `1644 "Done"`, `1646 "FAILED"`, plus the inline `"  ingested N/M …"` and `"  ! ingest:"` lines around `pipeline.py:336-347`). Dropping `logger.info()` from `progress()` outright would silently drop those from the file log.

Instead: keep `progress()` writing through its dedicated `_progress_logger` (already at `logging_setup.py:130`), but install a filter on the **console** handler that drops records originating from that logger. File handlers continue to capture everything; the console only sees the direct `sys.stderr.write()`. Concretely, in `configure_logging()` after the console handler is constructed (`logging_setup.py:210-214`):

```python
class _DropProgressOnConsole(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name != _progress_logger.name

console.addFilter(_DropProgressOnConsole())
```

Result: `progress()` is stderr-once and file-logged; `--verbose` still surfaces other INFO records.

### 1.5 Add the missing onboard L1 marker

The outer onboard logs three L1 lines (`pipeline.py:1245, 1290, 1314` — `Onboard step 1/2/3`) and then drops into the per-template loop with no L1 message — only an in-code comment "Step 5: Per-template research pipeline" at `pipeline.py:1360`. Add an L1 line at the top of that loop:

```python
logger.info("Onboard step 4: per-template research (%d templates)", total)
```

placed just after the existing `total = len(applicable_slugs)` at `pipeline.py:1365`. No reformatting of the other three lines, no glyph, no rule. The L2 `[i/N] Researching:` lines at `pipeline.py:1369` continue unchanged.

The three different "step" formats interleaved in onboard output (L1 `Onboard step N:`, L2 `[i/N] Researching:`, L3 `Step N/4:` / `Step N/5:` from `pipeline.py:278/298/373/388` and `pipeline.py:823/840/893/905/956`) are not phase-1 noise; reconciling them is deferred to phase 2.

The `Step 1 — Query planning` strings in `dr step-research` (`cli.py:227, 235, 240`) are out of scope per the "onboard only" decision; leave them alone.

### 1.6 Verbose-mode behaviour summary

| mode        | console level | httpx | wayback         | progress lines | Brave-query line | onboard report |
|-------------|---------------|-------|-----------------|----------------|------------------|----------------|
| default     | WARNING       | OFF   | one-line warn   | YES            | NO               | YES            |
| `--verbose` | INFO          | OFF   | one-line warn   | YES (no dup)   | YES              | YES            |

Loggers that stay loud at INFO under `--verbose` (per the "keep" list): `orchestrator.pipeline`, `orchestrator.persistence`, `researcher.decomposed`, `ingestor.agent`.

### Files modified in phase 1

- `pipeline/common/logging_setup.py` — clamp `httpx`/`httpcore`/`urllib3` to WARNING (§1.1); add a console-handler filter that drops records from `_progress_logger` (§1.4).
- `pipeline/ingestor/tools/wayback.py` — collapse the two full-`exc` warnings (lines 38, 71) to status-only one-liners (§1.2).
- `pipeline/researcher/agent.py` — add `logger.info("Brave search: %s", query)` at the top of `search_brave` (§1.3).
- `pipeline/orchestrator/pipeline.py` — add the missing `Onboard step 4` log line just before the per-template loop at line 1365-1366 (§1.5). No other edits.

### Phase 1 verification

End-to-end manual:

```
dr onboard "Anthropic" --type company --only contributes-to-environmental-causes
dr onboard "Anthropic" --type company --only contributes-to-environmental-causes --verbose
```

Expected default output: no `INFO [httpx]` lines, no `For more information check …mozilla…` URL, no duplicate `[1/4] Researching:` line under any setting, the existing `Onboard step 1/2/3` plus the new `Onboard step 4: per-template research (N templates)` line, the existing `[i/N] Researching:` / `[i/N] Done` / `[i/N] Blocked` etc. lines, summary block at end.

Expected `--verbose` output: same skeleton plus the application INFO logs (`Brave search: <q>`, `Search executor: N unique candidates`, `Ingested: <url> -> <title>`), with each `progress()` line appearing exactly once. No httpx per-request lines, no mozilla-doc hint.

Expected file-log: `logs/info.log` should contain every `progress()` line from the run (this validates the §1.4 filter approach — the file log captures what the console drops).

Tests:

```
cd pipeline && python -m pytest tests/test_logging_setup.py tests/test_onboard.py tests/test_terminal_fetch.py
```

No existing tests assert CLI output formatting. New tests, both in `tests/test_logging_setup.py`:

1. After `configure_logging(verbose=True)`, `logging.getLogger("httpx").level == logging.WARNING`.
2. After `configure_logging(verbose=True)`, calling `progress("hello")` produces exactly one `"hello"` on stderr and one record on the info-log file (no duplicate stderr line).

---

## Phase 2 — future (do not implement now)

Defer until phase 1 has been used in real onboard runs and gaps are clear.

- **Live status panel** for `dr onboard`: a `rich.live.Live` region showing per-template state (▶ researching / ✓ done / ! blocked) updating in place. Adds `rich` as a dependency. Falls back to plain `progress()` when stderr isn't a TTY (CI).
- **`--json` output mode** for `dr onboard`, `dr claim-refresh`, `dr ingest` — emit a single JSON document on stdout with the same content as the current report block. Useful for downstream scripting.
- **Per-template progress bar** during onboard's ingest waterfall, since fetching 8 URLs concurrently currently looks like a hang.
- **Unified `Renderer` abstraction** so all commands share one text/json/rich output strategy instead of each command's `click.echo` block.
- **Reconcile the L3 sub-step format.** `verify_claim` (`pipeline.py:277-388`) emits `Step N/4`; `research_claim` (`pipeline.py:822-956`) emits `Step N/5`. Converge on a shared label set (`Searching`, `Ingesting`, `Writing sources`, `Analysing`, `Auditing`) without numerator, drop the L1/L2/L3 numeric suffix entirely, and indent L3 under L2 with two spaces. Held for phase 2 because it's restructuring, not noise removal, and the live-panel renderer would supersede ad-hoc indent anyway.
- **Glyph and horizontal-rule vocabulary.** Sparse glyphs (`▶` phase, `›` sub-step, `✓` ok, `!` warn, `✗` fail) and dim-cyan rules between L1 phases / L2 iterations / around the onboard report block (replacing the `=` × 60 dividers at `cli.py:1563, 1620`). Defer alongside the L3 reconciliation so the glyph helpers (`hr()`, `glyph=` kwarg in `logging_setup.py`) land once with a known set of call sites instead of being added speculatively.
- **Sweep other `dr` commands** (`claim-refresh`, `claim-probe`, `ingest`, `review-queue`) into the same vocabulary established for onboard in phase 2.

---

## Out of scope (now and future)

- Changing the file-log format (`logs/info.log`, `logs/debug.log`) — keep as is for post-hoc grep.
- Rewriting `logger.info` call sites globally to use `progress()` instead — phase 1 only touches the duplicated/noisy ones.
- Colour-blind / no-color flag — defer; `click` already honours `NO_COLOR`.
- The `Step 1 — Query planning` strings in `dr step-research` (`cli.py:227, 235, 240`).
