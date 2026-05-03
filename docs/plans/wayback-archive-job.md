# Plan: Background jobs framework — wayback archival is the first job

**Status**: Interim flip done (skip_wayback=False in pipeline, commit 6409918). Full background-job framework is post-v1.

Introduce a lightweight convention for scheduled background jobs that produce content changes via PR. Each job is a flat `dr <verb>` Click subcommand plus a per-job GitHub Actions workflow that runs on cron and opens a PR with the resulting diff. **Wayback archival is the first job built on this convention.** The convention is whatever survives implementing the first job — no framework code beyond what wayback genuinely shares with later jobs.

> **Interim status (2026-04-28).** The in-pipeline `skip_wayback` default has been flipped to `False` in `VerifyConfig` and the `dr claim-probe` / `dr claim-draft` / `dr onboard` flag defaults. Reason: paywalled and auth-walled primary sources (e.g. `blogs.microsoft.com`) were terminating with 403 during synchronous runs and never reaching any archive — the analyst then evaluated claims against an evidence base missing the original announcements. Until this background job ships, archival happens in-band so the analyst sees those sources. When the job lands, flip the in-pipeline default back to `True` and delete this note. The plan's framing below ("In-pipeline `skip_wayback=True` default stays") describes the intended steady state, not current behavior.

## Goal

Two layered goals:

**Framework goal.** Establish a repeatable shape for "scheduled work that mutates `research/` content and surfaces the diff for operator review" so that the next job (broken-link sweep, source-freshness recheck, citation re-validation, etc.) is a focused content task and not a re-litigation of CLI shape, scheduling, failure logging, and PR conventions.

**Wayback goal.** Every committed source under `research/sources/` ends up with a populated `archived_url` field pointing at a `web.archive.org` snapshot. New sources picked up automatically by the daily run; historical sources backfilled by the same code path. In-pipeline `skip_wayback=True` default stays; archival happens out-of-band.

Note: most existing sources under `research/sources/` currently have no `archived_url` key in frontmatter (the Pydantic model defaults it to `None` and the serializer omits keys whose value is `None`). The first daily run is therefore a backfill that will *add* a new key to nearly every existing source file — expect a large inaugural PR (one-line addition per source × ~all sources). Subsequent runs should touch only newly-ingested sources.

## Why background-and-scheduled, not in-pipeline

`pipeline/orchestrator/pipeline.py:128` defaults `skip_wayback=True` with the comment "default True for faster POC runs". The `ingestor-tighten-timeouts.md` plan quantified the cost: enabling wayback inside the ingest path adds ~45s of HTTP budget per source (15s availability check + 30s save) and pushes the agent budget from ~40s to ~85s, exceeding the 60s default. Moving archival out of the synchronous ingest path keeps `dr` interactive while still producing wayback links.

Daily cadence is the starting cron; weekly is the expected steady state once historical backfill is done. Bursts during onboarding don't slam archive.org because the work happens in throttled batches outside the pipeline.

## Framework conventions

The conventions below are the framework. They're enforced by example, not by base classes or registries.

### CLI: flat Click subcommand per job

Each job is a top-level `dr` subcommand, registered with `@main.command()` in `pipeline/orchestrator/cli.py`. Wayback is `dr archive`. Future jobs are `dr <verb>` (e.g. `dr check-links`, `dr refresh-sources`). No `dr jobs` umbrella, no registry, no auto-discovery — adding a job is adding a Click command. This matches the existing pattern of `dr lint`, `dr review`, `dr ingest`.

Flag conventions every job should adopt:

- `--dry-run` — report would-be changes; zero HTTP, zero file writes.
- `--limit N` — cap per-run processing for pacing.
- `--repo-root PATH` — for testing against tmp checkouts.

Job-specific flags (e.g., `--pending` / `--force` for archival) are declared per job.

### Scheduling: one Actions workflow per job

Each job gets `.github/workflows/<job-name>.yml`. Workflows are independent: own cron, own concurrency group, own permissions block. Disabling or rescheduling one job is a one-file edit. Standard GitHub Actions pattern — the platform's scheduling primitive is per-workflow.

Each workflow runs `uv sync` (under `working-directory: pipeline`), then `uv run dr <job> <flags>`, then `peter-evans/create-pull-request@v6`. The pipeline subdirectory pattern matches the existing `lint-content` job in `.github/workflows/ci.yml:32-34`. The PR title, branch name, and body are job-specific but follow this template:

- Branch: `chore/<job-name>-${{ github.run_id }}`
- Title: `chore(<scope>): <job description> YYYY-MM-DD`
- Body: each job's CLI writes a structured summary file (e.g., `pipeline/<job>-summary.md`) and the workflow passes `body-path:` to `peter-evans/create-pull-request@v6` so the action reads the file directly. This avoids `$GITHUB_OUTPUT` heredoc encoding for multi-line output and the 1MB-per-output limit.
- Labels: `automated`, `<job-name>` so existing tooling can filter.

`workflow_dispatch:` is always enabled alongside the cron so operators can trigger a run on demand.

### Failure logs: per-job JSONL under `logs/`

Each job writes failures to `logs/<job-name>-failures.jsonl`. One JSON object per line. Job-specific schema, but every entry includes `ts` (ISO 8601 UTC) and `kind` (a short stable enum the job defines). `logs/` is gitignored.

A unified failure-log shape is deferred until the second job exists and we can see what's actually shared.

### Configurable knobs: env vars, per-job prefix

Knobs use `<JOB_PREFIX>_<NAME>` env-var naming with `<UNIT>` suffix where applicable. For wayback: `WAYBACK_RATE_LIMIT_S`, `WAYBACK_MAX_RETRIES`, `WAYBACK_BACKOFF_MAX_S`, `WAYBACK_API_KEY` (anonymous for v1; documented for future use). Each job documents its env vars in its own help text and in `AGENTS.md` § Tooling.

### Bot identity for commits

PRs are opened under the GitHub Actions bot identity (`github-actions[bot]`). Commits in the auto-generated branch are also bot-authored. The repo accepts bot-authored content commits to `research/` for these scheduled jobs; this is recorded in `AGENTS.md` so it's not relitigated per job.

### Atomic writes for content mutations

Any job that mutates a checked-in content file uses temp-then-rename: `Path.write_text(<tmp>)` then `os.replace(<tmp>, <final>)`. POSIX guarantees the rename is atomic, so a SIGKILL or runner pre-emption mid-write never leaves a half-written file. This is a hard convention for any job in this framework.

### What the framework deliberately doesn't include

- **No base class for jobs.** A job is a Click subcommand; no `Job` superclass, no `run() -> JobResult` protocol, no shared dispatcher.
- **No declarative `jobs.yaml`.** Discovery is "what's registered with `@main.command()`."
- **No shared throttle/retry library.** Wayback gets its own throttle. If the second job needs throttling, factor a helper out then.
- **No central failure-log schema.** Each job defines its JSONL fields.

The first refactor opportunity arrives when the second job lands. Until then the framework is conventions in this plan, not code.

## Wayback archival: the first job

### Acceptance bar

- `dr archive --pending` walks `research/sources/` and writes `archived_url` into the frontmatter of every source missing one. Idempotent for successful runs: re-runs over already-archived sources are no-ops (zero HTTP, zero writes). Sources that previously failed archival are skipped for `WAYBACK_COOLDOWN_DAYS` (default 7) per the cooldown cache (see "Cooldown cache" below). After the cooldown lapses, they retry. `--force` ignores cooldown and re-attempts immediately.
- A scheduled GitHub Actions workflow runs `dr archive --pending --limit 10` daily, commits the diff to a fresh branch, and opens one PR per execution. The `--limit 10` cap is **deliberately small** to spread the inaugural backfill across many days, give the operator a steady stream of small, easy-to-review PRs, and validate the daily-cron rhythm before throughput matters.
- Failures are logged to `logs/wayback-failures.jsonl` and the source frontmatter is left untouched. The PR body summarises failures alongside successes.
- `pipeline/ingestor/tools/wayback.py` (`check_wayback`, `save_to_wayback`) is reused without behavioural change.
- `skip_wayback` default in `VerifyConfig` and the three CLI flags stays `True`. This plan does not change in-pipeline behaviour.

### CLI subcommand

```
dr archive [--pending|--force] [--limit N] [--dry-run] [--repo-root PATH]
```

- `--pending` (default true): only sources where `archived_url` is missing or empty AND not currently in cooldown.
- `--force`: re-archive even if already populated, and ignore cooldown. Useful if a wayback URL goes stale, to replace an existing `archived_url` that doesn't point at `web.archive.org`, or to push past a cooldown entry the operator wants to retry now.
- `--limit N`: cap per-run processing. **Default 10** (deliberately small for the daily backfill cadence).
- `--dry-run`: report would-be-archived list; no HTTP, no writes, no cooldown updates.
- Exit code 0 on success (including partial — some failures), non-zero only on catastrophic config errors.

### Throttle and retry

- Sleep `WAYBACK_RATE_LIMIT_S` (default 2s) between archive.org calls.
- Per-URL retry: one retry on transient failure (HTTP 5xx, connection error). Terminal failures (4xx other than 429, malformed response) skipped immediately.
- 429 from archive.org triggers exponential backoff capped at `WAYBACK_BACKOFF_MAX_S` (default 60s) for at most `WAYBACK_MAX_RETRIES` (default 3) attempts; on persistent 429 the run halts cleanly with a "rate-limited" exit message and partial progress is committed.
- Anonymous archive.org auth in v1. The `WAYBACK_API_KEY` env var hook is wired but unused by default; populating it raises archive.org's per-IP limit (S3-style key from archive.org). Documented for future enabling.

  > **Reviewer note (deferred):** Archive.org's S3-style API actually needs two values (access key + secret key). When wiring real auth, expect to split the single env-var hook into `WAYBACK_S3_ACCESS_KEY` + `WAYBACK_S3_SECRET_KEY`. Not a plan blocker; flagged for the eventual implementation.

### Cooldown cache

`pipeline/wayback-cooldown.json` is a **committed** state file (initial content: `{}`). On every failure, the worker writes/updates an entry. On every success, the worker removes the entry. On every run start, the worker reads the file and skips any source whose entry is younger than `WAYBACK_COOLDOWN_DAYS` (default 7).

Shape:

```json
{
  "2026/voluntary-commitments": {
    "last_failed_at": "2026-04-26T19:30:00Z",
    "kind": "save_failed",
    "attempts": 3
  },
  "2025/google-gemini-3-flash": {
    "last_failed_at": "2026-04-25T19:35:00Z",
    "kind": "rate_limited",
    "attempts": 1
  }
}
```

Why committed and not gitignored: the cooldown is meaningful only across runs, and CI runners start with a fresh workspace — a gitignored cooldown file would be empty in CI on every run and the cooldown would never apply. Committing it lets each daily PR include the cooldown updates alongside the source updates, giving the operator a visible audit trail of why a source was skipped. The diff is small (one entry per failure or success).

Edge cases:

- Missing or malformed `pipeline/wayback-cooldown.json`: log a warning, treat as empty `{}`, proceed.
- Source removed from `research/sources/` but still in cooldown: orphan entry; v1 leaves it in place (no pruning step). Cleanup is a future enhancement if the file grows large.
- `--dry-run` reads cooldown but does not write it.
- `--force` ignores cooldown for the read (re-attempts the source) and still updates cooldown on outcome (success removes the entry, failure refreshes the timestamp).

### Failure log

`logs/wayback-failures.jsonl`. One line per failure:

```json
{"ts": "2026-04-26T19:30:00Z", "source_id": "2026/voluntary-commitments", "url": "https://...", "kind": "save_failed", "detail": "HTTP 502 from /save"}
```

`kind` enum: `availability_check_failed`, `save_failed`, `rate_limited`, `parse_error`, `unsupported_url`.

### Scheduled workflow

`.github/workflows/wayback-archive.yml`:

- `schedule: cron: '0 6 * * *'` (daily at 06:00 UTC). Likely tightening to weekly once steady state is reached.
- `workflow_dispatch:` for manual kick-off.
- Steps: checkout, `actions/setup-python@v5`, `pip install uv`, `uv sync` (under `pipeline/`), `uv run dr archive --pending --limit 10`, `peter-evans/create-pull-request@v6`.
- PR title: `chore(sources): wayback archival YYYY-MM-DD`
- PR branch: `chore/wayback-archive-${{ github.run_id }}`
- PR body: the CLI writes `pipeline/wayback-summary.md` (a known path) in addition to its stdout. The workflow passes `body-path: pipeline/wayback-summary.md` to `peter-evans/create-pull-request@v6` so the action reads the file directly.
- PR labels: `automated`, `wayback-archive`.
- Permissions: `contents: write`, `pull-requests: write`. No push to main; PR-only.
- Concurrency: `group: wayback-archive` with default `cancel-in-progress: false`, so a manual `workflow_dispatch` issued during a cron run queues behind it rather than racing or interrupting. Do **not** set `cancel-in-progress: true`: a mid-run kill could leave the runner with successfully-archived sources committed locally but no PR opened.

### Code paths that change

| File | Change |
|---|---|
| `pipeline/orchestrator/cli.py` | New `@main.command()` `dr archive` subcommand. |
| `pipeline/orchestrator/jobs/wayback.py` (new) | Walks `research/sources/**/*.md` (skipping dotfiles). Sources are organized as `research/sources/<year>/<slug>.md` (years 2015, 2021–2026 currently present); the walker does not assume that layout — it discovers any `.md` under the tree. Reads `pipeline/wayback-cooldown.json` to skip sources still in cooldown. Parses frontmatter via `common.frontmatter.parse_frontmatter`, calls `check_wayback` / `save_to_wayback` per source, writes back via `common.frontmatter.serialize_frontmatter` using the temp-then-rename pattern. Holds the throttle, retry, cooldown-update, and failure-logging logic. Also writes `pipeline/wayback-summary.md` for the workflow's PR body. |
| `pipeline/wayback-cooldown.json` (new, committed) | Initial content `{}`. Updated in-place by each run; included in the daily PR diff alongside source updates. |
| `pipeline/ingestor/tools/wayback.py` | No change. Tool consumed as-is. |
| `pipeline/common/timeouts.py` | No change. `WAYBACK_CHECK_S` (line 24) and `WAYBACK_SAVE_S` (line 25) already exist. |
| `.github/workflows/wayback-archive.yml` (new) | Cron-scheduled workflow per the conventions above. |
| `pipeline/tests/test_wayback_archive.py` (new) | Unit tests for the walker, idempotency, failure-log shape, frontmatter round-trip, throttle and retry behaviour. |
| `AGENTS.md` § Tooling | New row for `dr archive`; new short subsection naming the background-jobs convention so the next job's plan can reference it. |

The directory `pipeline/orchestrator/jobs/` is established by this plan as the location for per-job worker modules. The CLI subcommand stays in `cli.py`; only the work moves into `jobs/<name>.py`. Future jobs follow the same split.

### Implementation steps

1. **Add `dr archive` skeleton** to `cli.py`. Flags + Click wiring + a stub that prints "would archive N sources." Wire `--dry-run` and the source-walking logic first; no HTTP yet. Unit-test the walker.
2. **Create `pipeline/orchestrator/jobs/wayback.py`** and move the walker there. Keep CLI thin: parse flags, call into the worker.
3. **Add live archival**: import `check_wayback` and `save_to_wayback`, plumb httpx client + retry/throttle. Add the failure-log writer.
4. **Add frontmatter write-back**: read source via `common.frontmatter.parse_frontmatter`, set `archived_url`, write via `serialize_frontmatter` using the temp-then-rename pattern. Round-trip test against a real source file fixture: assert no semantic field changes (parse-then-compare-as-dict). Note: byte-stable preservation is **not** guaranteed — PyYAML's dumper may reflow long strings, change quote style, and drops keys with `None` values; this is documented for the implementer so re-serialize diffs in the first PR are not surprising.
5. **Tests**: idempotency over a successful run; idempotency over a partially-failed run (failed URLs in cooldown stay skipped, succeeded ones don't retry); `--limit` honoured (verify default 10); `--dry-run` writes nothing (no source writes, no cooldown writes) and emits zero HTTP; failure-log shape; retry on transient 5xx; halt on 429 with backoff exhausted; **source with no frontmatter at all** (skipped + logged with `kind: parse_error`); **source with existing malformed `archived_url`** (not under `web.archive.org`) — under `--pending` it is treated as present and skipped, under `--force` it is replaced; **non-markdown file in the sources tree** is skipped silently; **interrupted run mid-write** (simulate `os.replace` failure) leaves the original file intact; **cooldown lifecycle**: failure adds entry, subsequent run within `WAYBACK_COOLDOWN_DAYS` skips it, success removes entry, `--force` ignores cooldown read but still updates it on outcome; **missing `pipeline/wayback-cooldown.json`** treated as empty `{}` with warning logged; **malformed cooldown JSON** treated as empty `{}` with warning logged.
6. **GitHub Actions workflow**: write `wayback-archive.yml`. Test by `workflow_dispatch` first; only enable the daily cron after one successful PR cycle.
7. **Document** the new subcommand in `AGENTS.md` § Tooling. Add the short "Background jobs convention" subsection there. Add a one-line entry to `docs/UNSCHEDULED.md` to record the v1 wayback-coverage gap as scheduled work, or this plan replaces that entry.

## Out of scope

- **Changing the in-pipeline `skip_wayback` default.** Stays `True`. This plan adds a parallel path; flipping the default is a separate decision.
- **Backfill of source-derived audit-sidecar fields.** Sidecars don't carry `archived_url`; only source files do.
- **Audit-sidecar staleness interaction.** Verified: `*.audit.yaml` sidecars exist only for claims (`research/claims/`), not sources. The audit-trail-extensions staleness check compares fields on a claim against its sidecar; writing `archived_url` to a source's frontmatter does not trigger any sidecar staleness logic. No sidecar bookkeeping needed.
- **Replacing `web.archive.org` with another archival service.** Provider abstraction is post-v1.
- **Surfacing wayback links in the dr lint static check.** Could naturally extend `dr lint` later to flag missing `archived_url`, but that belongs in the linter's plan, not here.
- **Real-time archival.** A user-facing claim that a source is archived "as of upload" requires per-ingest synchronous wayback — not this plan's design.
- **A second job.** This plan ships the framework conventions and the first concrete job. The second job (whichever it is) gets its own plan and validates the framework.
- **PR auto-merge.** Default is operator review. Auto-merge for clean diffs is a separate decision after the workflow has weeks of run history.
- **Cooldown orphan pruning.** v1 leaves orphan entries (sources removed from `research/sources/` but still in `pipeline/wayback-cooldown.json`) in place. A pruning step is straightforward but adds complexity; defer until the file shows real bloat.

## Resolved questions

| ID | Question | Answer | Decided |
|---|---|---|---|
| Q0 | Should the design be wayback-specific or a generic background-jobs framework? | Generic framework; wayback is the first concrete job. Framework is conventions, not code. | 2026-04-26 |
| Q-A | CLI shape: flat subcommands or `dr jobs` umbrella? | Flat. Each job is a top-level `dr <verb>` subcommand. | 2026-04-26 |
| Q-B | Workflow shape: one per job or umbrella? | One Actions workflow per job. | 2026-04-26 |
| Q-C | Anything else missing from the framework concept? | No; defer job-result interface, unified failure log, and discovery/registry until the second job lands. | 2026-04-26 |
| Q1 | Cadence? | Daily for now; likely weekly once steady state is reached. | 2026-04-26 |
| Q2 | Configurable knobs? | Yes; rate limit, retry count, backoff cap, per-run cap, schedule. Env-var-driven with `WAYBACK_*` prefix. | 2026-04-26 |
| Q3 | Archive.org API key? | Anonymous for v1. `WAYBACK_API_KEY` hook is wired but unused by default. (Real S3 auth will need access+secret split — see reviewer note.) | 2026-04-26 |
| Q4 | PR scope? | One PR per execution, with all changes batched. | 2026-04-26 |
| Q5 | Bot-authored commits to `research/`? | Yes, OK. Recorded in `AGENTS.md` so future jobs don't relitigate. | 2026-04-26 |
| Q6 | Per-URL failure cooldown cache? | Yes, add it. Path: `pipeline/wayback-cooldown.json` (committed, not gitignored, so it persists across CI runs). Period: `WAYBACK_COOLDOWN_DAYS` env var, default 7. | 2026-04-26 |
| Q7 | Default per-run page limit? | 10 (deliberately small) so the inaugural backfill spreads across many days, the operator gets steady small reviewable PRs, and the daily-cron rhythm is validated before throughput matters. | 2026-04-26 |
| Q8 | S3-style auth split for `WAYBACK_API_KEY`? | Acknowledged. Real archive.org auth will need `WAYBACK_S3_ACCESS_KEY` + `WAYBACK_S3_SECRET_KEY`; v1 stays anonymous, the split happens when real auth is wired. | 2026-04-26 |

## Open questions

None remaining.

## Verification

1. `uv run dr archive --pending --dry-run` lists sources missing `archived_url` and exits without HTTP.
2. After one full live run on a tmp checkout: every previously-empty `archived_url` is populated; `parse_frontmatter` of every touched file shows no semantic change to other fields (compare as dict, not byte-diff).
3. Re-running with `--pending` is a no-op for previously-successful sources (zero HTTP calls, zero file writes against those sources). Previously-failed sources within `WAYBACK_COOLDOWN_DAYS` are also skipped; older failures retry.
4. `--limit 5` processes exactly 5 sources, leaves the rest untouched. Default limit is 10 (verify CLI help output and workflow command).
5. Manual `workflow_dispatch` of the Actions workflow opens a PR titled `chore(sources): wayback archival YYYY-MM-DD` with at least one file diff and labels `automated`, `wayback-archive`.
6. A simulated 429 (mock the httpx response) causes the run to halt after backoff exhaustion with exit code 0 and a "rate-limited" stderr message; partial progress is preserved.
7. `logs/wayback-failures.jsonl` is appended to on failures and is gitignored.
8. `AGENTS.md` § Tooling lists `dr archive` and the "Background jobs convention" subsection.
9. Concurrency check: starting a `workflow_dispatch` run while a cron run is in progress queues behind it rather than racing or cancelling.
10. Atomic-write check: simulated `os.replace` failure (e.g., disk full) leaves the original source file byte-identical.
11. Cooldown lifecycle check: a failure adds an entry to `pipeline/wayback-cooldown.json`; the next run within `WAYBACK_COOLDOWN_DAYS` skips that source; a success removes the entry; `--force` ignores the cooldown read but still updates the cooldown on outcome.

## References

- `pipeline/ingestor/tools/wayback.py:18` — existing `check_wayback`.
- `pipeline/ingestor/tools/wayback.py:43` — existing `save_to_wayback`.
- `pipeline/ingestor/agent.py` — current in-pipeline use (skipped by default).
- `pipeline/common/frontmatter.py:60` — `parse_frontmatter`.
- `pipeline/common/frontmatter.py:80-90` — `_clean_for_serialize` (drops `None`-valued keys).
- `pipeline/common/frontmatter.py:93` — `serialize_frontmatter`.
- `pipeline/common/frontmatter.py:100` — `sort_keys=False` (preserves key order).
- `pipeline/common/timeouts.py:24-25` — `WAYBACK_CHECK_S`, `WAYBACK_SAVE_S` constants.
- `pipeline/orchestrator/cli.py` — pattern for adding subcommands; existing `dr review`, `dr ingest`, `dr lint` are templates.
- `.github/workflows/ci.yml:32-34` — existing `lint-content` job demonstrates the `working-directory: pipeline` + `uv sync` pattern.
- `peter-evans/create-pull-request@v6` GitHub Action — standard PR-output mechanism. Uses `body-path:` input (added in v5) to read multi-line body from a file.
- `docs/plans/ingestor-tighten-timeouts.md` — timeout-budget reasoning that motivates moving archival out of the synchronous ingest path.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-04-26 | agent (opus-4-7) | initial draft | Stub created from in-conversation design discussion: scheduled `dr archive` + per-job Actions workflow + PR-output flow. Open questions 1–5 surfaced. |
| 2026-04-26 | agent (opus-4-7) | iterated, scope expansion | Reframed as a background-jobs framework with wayback as the first concrete implementation per operator decision Q0. Added "Framework conventions" section: flat Click subcommands, one workflow per job, per-job JSONL failure logs, env-var knobs with `<JOB>_*` prefix, bot-authored commits OK. Cadence set to daily (Q1). Configurable knobs enumerated (Q2). Anonymous archive.org auth confirmed (Q3). One PR per execution (Q4). Bot-authored commits accepted (Q5). All earlier Open questions moved to Resolved. New `pipeline/orchestrator/jobs/` directory established as the per-job worker module location. |
| 2026-04-26 | agent (opus-4-7, Plan reviewer) | review pass before promotion | Verified all source-code references (file paths, function names, line numbers) — all accurate. Replaced `inv setup` with explicit `uv sync` (Python-only job; `inv setup` runs unnecessary `npm ci`). Pinned `peter-evans/create-pull-request@v6` (was `@vN`) and specified `body-path:` mechanism for the PR body to avoid `$GITHUB_OUTPUT` heredoc encoding. Added atomic-write requirement (temp-then-`os.replace`) as a framework-wide convention. Made idempotency claim precise: failed URLs retry on every run; successes are no-ops. Made source-walk glob explicit (`**/*.md`, skip dotfiles). Softened "byte-stable" frontmatter round-trip claim to "semantically stable" — verified PyYAML dumper drops `None` keys, may reflow strings/dates. Expanded test coverage list (no-frontmatter source, malformed existing `archived_url`, non-md files in tree, interrupted-write). Made concurrency stance explicit (`cancel-in-progress: false`, manual dispatch queues). Documented that source files have no `.audit.yaml` sidecar so writing source frontmatter has zero staleness-check interaction. Flagged inaugural-PR volume (most existing sources lack `archived_url` entirely; first run touches almost every source file). Added two reviewer notes for operator decisions before promotion: failure-cache punt-to-v2, and S3-style auth split for future real-auth wiring. |
| 2026-04-26 | agent (opus-4-7) | iterated, operator decisions Q6–Q8 | Added per-URL cooldown cache (Q6): `pipeline/wayback-cooldown.json` committed (not gitignored, so it persists across CI runs); `WAYBACK_COOLDOWN_DAYS` env var, default 7; success removes entry, failure adds/refreshes; `--force` ignores read but updates on outcome; missing/malformed treated as empty with warning. Lowered default `--limit` from 50 to 10 (Q7) to spread inaugural backfill across many days and validate the daily-cron rhythm. S3 auth split (Q8) recorded as resolved; remaining as a known follow-up at real-auth-wiring time. Tests, verification, code-paths, and out-of-scope sections updated to match. Cooldown orphan pruning explicitly deferred to v2. |
