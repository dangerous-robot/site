# Plan: Refactor `scripts/poc-multi-provider/` into a durable LLM tester toolset

## Context

`scripts/poc-multi-provider/` was the working directory for the multi-provider evaluation that produced [`docs/plans/multi-provider.md`](multi-provider.md) and [`docs/reports/API-PROVIDER-FINAL-REPORT.md`](../reports/API-PROVIDER-FINAL-REPORT.md). The directory is gitignored (`.gitignore:37`) and contains a mix of: two reusable harnesses (`run_tests.py` for Infomaniak, `run_greenpt.py` for GreenPT), a wire tracer (`trace_infomaniak.py`), seven one-off `probe_*.py` spikes, three rollup `SUMMARY-*.md` docs, eight `results-*.md` per-model reports, four `trace-*.json` dumps, an Infomaniak support ticket, and a shared `.env.poc`.

The harnesses still have ongoing utility — every time a new provider/model is considered (Part 3 of the multi-provider plan, future GreenPT promotion, any new Infomaniak model rollout), an agent or operator needs to fire T1-T5 at it and read the result. The probes and reports do not — they captured one-time findings that are now reflected in the final report and the multi-provider plan's "Observed quirks" section.

This refactor preserves the harnesses, retires the spikes, and gives an agent a single entry point.

## Goals

- One obvious place to look (`llm-tester/README.md`) and one obvious thing to run (`tester.py probe ...`) so a coding agent can test a new model in one shot.
- Keep both harnesses (Infomaniak, GreenPT) working with minimal code change — pass-through thin CLI wrapper, not a rewrite.
- Stay gitignored. The directory holds API keys (`.env.poc`) and ad-hoc results.
- Preserve historical artifacts (summaries, results, traces, support ticket) in an `archive/` subfolder so the new top level is uncluttered.

## Non-goals

- No new providers. Adding OpenRouter / Anthropic / Together / etc. is out of scope.
- No new tests. T1-T5 stay as-is. No streaming test, no vision test, no long-context test.
- No unified trace JSON schema. `trace_infomaniak.py` keeps its current output format.
- No CI. The directory stays gitignored; nothing should depend on it being checked in.
- No rewrite of working code. `run_tests.py` and `run_greenpt.py` are touched only for renaming and the shared env-loader extraction.
- No regression-run mode. `tester.py` tests one model per invocation; a bash loop suffices when an operator wants to re-run the matrix.
- No removal of the Infomaniak gemma3n support ticket. It's archived, not deleted — Brandon may still need to forward it.

## Final directory name

**`scripts/llm-tester/`**

Rationale: matches Brandon's working name, drops the "poc" framing (this is the post-POC durable form), and reads obviously to an agent skimming `scripts/`.

## Resolved decisions

These were open questions during drafting; all resolved before promotion.

1. **Env file stays `.env.poc`.** Renaming to `.env` would touch three scripts for zero functional gain; `.env.poc` is already covered by `.gitignore` via the directory-level rule.
2. **`tester.py` is Python**, consistent with the harnesses and `uv run`-friendly.
3. **Dispatch via `subprocess`**, not direct module import. Simpler and avoids argparse-in-imported-module surprises.
4. **All 7 probe scripts go to `archive/`.** Nothing is deleted in this refactor. Re-evaluate in a follow-up after 6 months.
5. **`trace/` accepts a symmetric `<provider>` arg** in the CLI shape, even though only `infomaniak` is wired up today. The dispatcher errors clearly on unknown providers.

## Proposed final layout

```
scripts/llm-tester/
├── README.md                   # NEW - the agent's first read
├── .env.poc                    # KEEP (name unchanged)
├── tester.py                   # NEW - thin CLI dispatcher (~50 LOC, Python, subprocess-based)
├── harness/
│   ├── __init__.py             # NEW - empty
│   ├── infomaniak.py           # MOVED from run_tests.py
│   ├── greenpt.py              # MOVED from run_greenpt.py
│   └── _env.py                 # NEW - shared _load_env() (~10 LOC)
├── trace/
│   └── infomaniak.py           # MOVED from trace_infomaniak.py
└── archive/
    ├── README.md               # NEW - one-paragraph index of what's here
    ├── INFOMANIAK-SUPPORT-TICKET.md
    ├── SUMMARY-cross-provider.md
    ├── SUMMARY-greenpt.md
    ├── SUMMARY-infomaniak.md
    ├── TRACE-gemma3n.md
    ├── results-greenpt-direct-green-l-raw.md
    ├── results-greenpt-direct-green-r-raw.md
    ├── results-greenpt-router-gemma-3-27b-it.md
    ├── results-greenpt-router-gpt-oss-120b.md
    ├── results-greenpt-router-mistral-small.md
    ├── results-greenpt-scraper.md
    ├── results-infomaniak-apertus70b.md
    ├── results-infomaniak-gemma3n-retry.md
    ├── results-infomaniak-gemma3n.md
    ├── results-infomaniak-gpt-oss-120b.md
    ├── results-infomaniak-mistral24b.md
    ├── trace-gemma3n-20260426T110114Z-1-gemma3n-nonstream.json
    ├── trace-gemma3n-20260426T110114Z-2-gemma3n-stream.json
    ├── trace-gemma3n-20260426T110114Z-3-sibling-gemma4-31B.json
    ├── trace-gemma3n-20260426T110114Z-summary.json
    ├── probe_gemma3n_retry_continue.py
    ├── probe_gemma3n_retry_continue_raw.json
    ├── probe_gemma3n_retry.py
    ├── probe_gemma3n_retry_raw.json
    ├── probe_t5_apertus.py
    ├── probe_t5_apertus_v2.py
    ├── probe_t5_apertus_v3.py
    ├── probe_t5_gemma3n.py
    └── probe_t5_variations.py
```

### What stays, moves, gets deleted, gets renamed

| Current file | Action | Destination / notes |
|---|---|---|
| `run_tests.py` | rename + move | `harness/infomaniak.py` |
| `run_greenpt.py` | rename + move | `harness/greenpt.py` |
| `trace_infomaniak.py` | move | `trace/infomaniak.py` |
| `.env.poc` | keep in place | name unchanged |
| `__pycache__/` | delete | regenerated on next run |
| `INFOMANIAK-SUPPORT-TICKET.md` | move | `archive/` |
| `SUMMARY-*.md` (3 files) | move | `archive/` |
| `TRACE-gemma3n.md` | move | `archive/` |
| `results-*.md` (11 files) | move | `archive/` |
| `trace-*.json` (4 files) | move | `archive/` |
| `probe_*.py` (7 files) | move | `archive/` |
| `probe_*_raw.json` (2 files) | move | `archive/` |

Nothing is deleted in this refactor. The 7 `probe_*.py` scripts are duplicative one-shots, but archiving costs nothing and one of them (`probe_t5_gemma3n.py`) might be useful as a reference if Infomaniak ever fixes gemma3n. Re-evaluate deletion in a follow-up after 6 months.

## The one obvious entry point

```
python -m scripts.llm-tester.tester probe <provider> <model> [harness-specific flags...]
python -m scripts.llm-tester.tester trace <provider> <model>
python -m scripts.llm-tester.tester list
```

Or, equivalently from the directory: `uv run python tester.py probe ...`.

`tester.py` is a thin Python dispatcher (~50 LOC) that:

1. Parses `<provider>` (`infomaniak` | `greenpt`) and shells out via `subprocess` to `harness/<provider>.py` with the residual argv. Unknown providers produce a clear error.
2. The `trace` subcommand also takes a `<provider>` arg for symmetric CLI shape; today only `infomaniak` is implemented and any other value errors out.
3. The `list` subcommand prints the known-tested models from the README's matrix (hardcoded list, ~10 lines) so an agent can see what's been verified before picking a model.

The existing `argparse` in each harness stays. The dispatcher just passes through `argv[2:]`. Per-harness flags continue to work as they do today:

- `harness/infomaniak.py` (from `run_tests.py`): `--model`, `--t1-only`, `--retries`.
- `harness/greenpt.py` (from `run_greenpt.py`): `--model`, `--t1-only`, `--skip-after-t2`, `--t5-mode {raw,stripped,both,skip}`.

The dispatcher does not unify these flag sets; each harness owns its own argparse.

**Output:** stdout JSON (same as today). No file writes. An agent that wants a file pipes to one (`tester.py probe ... > /tmp/run.json`). This stays consistent with the harnesses' current behaviour and avoids adding a results directory the user has to clean up.

## README/index file (sections only — content for the next step)

The README is the agent's single entry point. It should contain, in order:

1. **What this is** — one paragraph: an ad-hoc, gitignored, throwaway tester for probing LLM providers and models against the T1-T5 capability matrix used by the `dr` pipeline. Points at `docs/plans/multi-provider.md` and `docs/reports/API-PROVIDER-FINAL-REPORT.md` for context.
2. **Quickstart** — three commands: `tester.py list`, `tester.py probe infomaniak openai/gpt-oss-120b`, `tester.py probe greenpt mistral-small-3.2-24b-instruct-2506`.
3. **What T1-T5 mean** — one-line each: T1 plain completion, T2 structured JSON, T3 tool def acceptance, T4 single-turn tool call, T5 multi-turn tool result handling.
4. **Known-tested models** — small table (provider, wire id, T1-T5 pass/fail, last-tested date). Sourced from `archive/SUMMARY-cross-provider.md`. ~10 rows.
5. **Adding a new provider** — explicit "don't, unless you're prepared to write a new `harness/<name>.py` mirroring the structure of `infomaniak.py`."
6. **Where results go** — stdout JSON. No persistence. Agents should pipe to a temp file if they need to grep.
7. **Env vars** — what `.env.poc` must contain (`INFOMANIAK_API_KEY`, `INFOMANIAK_PRODUCT_ID`, `GREENPT_API_KEY`).
8. **Archive notes** — one paragraph: `archive/` holds the original POC artifacts (probe spikes, per-model reports, support ticket, traces). Don't run anything from `archive/` unless you're explicitly reproducing a historical finding.

Target length: under 100 lines. An agent should be able to read it in 30 seconds.

## Step-by-step refactor checklist

Each step is independently verifiable. After each step, the harnesses should still run end-to-end (the goal is no behaviour change, only file moves and a wrapper).

1. **Update `.gitignore`.** Replace `scripts/poc-multi-provider/` with `scripts/llm-tester/` on line 37. Comment above remains accurate.
2. **Create the new directory tree.** `mkdir -p scripts/llm-tester/{harness,trace,archive}`. No files yet.
3. **Move and rename the two harnesses.** `git mv` is wrong here (the directory is gitignored), so plain `mv`:
   - `scripts/poc-multi-provider/run_tests.py` → `scripts/llm-tester/harness/infomaniak.py`
   - `scripts/poc-multi-provider/run_greenpt.py` → `scripts/llm-tester/harness/greenpt.py`
4. **Move the tracer.** `scripts/poc-multi-provider/trace_infomaniak.py` → `scripts/llm-tester/trace/infomaniak.py`.
5. **Move env file.** `scripts/poc-multi-provider/.env.poc` → `scripts/llm-tester/.env.poc`. Update the `Path(__file__).resolve().parent / ".env.poc"` lines in the three relocated scripts to walk up one directory (`.parent.parent / ".env.poc"`). Verify each script still loads its env.
6. **Move all archive content** to `scripts/llm-tester/archive/`: 3 SUMMARY-*.md, 11 results-*.md, 4 trace-*.json, 1 TRACE-gemma3n.md, 1 INFOMANIAK-SUPPORT-TICKET.md, 7 probe_*.py, 2 probe_*_raw.json, and the `__pycache__/` (or just delete it).
7. **Add `harness/__init__.py`** (empty) and `harness/_env.py` containing the shared `_load_env()` function copied from one of the harnesses. Update `infomaniak.py` and `greenpt.py` to `from ._env import load_env`. Delete the inlined copies. This is the only code consolidation in the refactor; if it gets fiddly, skip it and leave the duplicated `_load_env()` in both files.
8. **Write `tester.py`.** ~50 LOC, Python, subprocess-based. Three subcommands: `probe <provider> <model> [...]`, `trace <provider> <model>`, `list`. Errors clearly on unknown providers.
9. **Write `archive/README.md`.** One paragraph: "Frozen artifacts from the 2026-04-25 multi-provider POC. See `../README.md` for the live tester. The probe scripts here are one-off spikes; do not run them — use `tester.py` instead."
10. **Write the top-level `README.md`** (sections per the list above).
11. **Smoke test.**
    - `cd scripts/llm-tester && python tester.py list` — prints the known-tested models table.
    - `python tester.py probe infomaniak openai/gpt-oss-120b --t1-only` — returns a T1 result with `pass: true` (or whatever Infomaniak currently returns; the test is that the harness loads env, hits the network, and prints JSON).
    - `python tester.py probe greenpt mistral-small-3.2-24b-instruct-2506 --t1-only` — same.
12. **Delete the old directory.** `rm -rf scripts/poc-multi-provider/`. (It's already empty after step 6 except for `__pycache__/`.)
13. **Commit.** Single commit, message: `refactor: rename poc-multi-provider to llm-tester, archive POC artifacts`. The only tracked file in the diff is `.gitignore`. Everything else is gitignored on both sides of the rename.

Steps 1, 2, 3, 4, 5, 6 can be done in one shell session with no ambiguity. Steps 7, 8, 9, 10 are the writing work. Step 11 is verification. Steps 12, 13 are cleanup.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-04-27 | agent (claude-opus-4-7) | basic | Applied 5 resolved decisions (keep `.env.poc`, Python `tester.py` via subprocess, archive all probes, symmetric `trace <provider>`, no regression mode); fixed flag list (split per-harness; `--retries` is infomaniak-only, `--skip-after-t2`/`--t5-mode` are greenpt-only); fixed relative links for promoted location. |

## Critical files for implementation

- `/Users/brandon/dev/ai/dangerous-robot/site/.gitignore` (line 37 rename)
- `/Users/brandon/dev/ai/dangerous-robot/site/scripts/poc-multi-provider/run_tests.py` (becomes `harness/infomaniak.py`)
- `/Users/brandon/dev/ai/dangerous-robot/site/scripts/poc-multi-provider/run_greenpt.py` (becomes `harness/greenpt.py`)
- `/Users/brandon/dev/ai/dangerous-robot/site/scripts/poc-multi-provider/trace_infomaniak.py` (becomes `trace/infomaniak.py`)
- `/Users/brandon/dev/ai/dangerous-robot/site/scripts/poc-multi-provider/.env.poc` (move + path-fix in three scripts)
