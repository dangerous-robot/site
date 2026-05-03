# Plan: Token usage log

**Status**: Draft (2026-04-26)

Log every PydanticAI agent run's token usage to a single append-only JSONL file, tagged with the object the run was spent on (claim, source, entity, criterion, or routing). Add an `inv tokens.summary` task that aggregates the log by object or by time window.

> **Pointer (2026-04-27)**: parts of the plumbing this plan anticipates already
> shipped with the logging-infrastructure work
> (`/Users/brandon/.claude/plans/1-add-run-id-2-misty-glacier.md`). Inline
> pointers throughout this document tag the spots worth re-reading; they are
> for consideration, not prescriptive — the author of this plan may keep,
> drop, or rework the affected sections as they see fit. The headline items:
>
> - `VerifyConfig.run_id` already exists (`pipeline/orchestrator/pipeline.py`).
> - `new_run_id()` and `bind_run_id()` live in `pipeline/common/logging_setup.py`.
> - `bind_run_id(cfg.run_id)` already wraps `verify_claim`, `research_claim`,
>   and `onboard_entity` (per-template iteration uses
>   `dataclasses.replace(cfg, run_id=new_run_id())`).
> - `dr ingest` and `dr reassess` already bind a fresh `run_id` per invocation.
> - `/logs/` exists and is git-ignored.
>
> The wrapper described below can read `cfg.run_id` (and the contextvar, if
> useful) without re-introducing any of this.

## Goal

Record token cost (input, output, total, request count) for every `agent.run(...)` call in the dangerousrobot.org pipeline, attached to the artifact the run produced or modified. The log answers: which claims, sources, and entities are consuming the most tokens; what is the daily/weekly model spend; which agents dominate. This is the simplest version because there is one writer (a small wrapper), one schema (one JSONL line per run), and one reader (the `inv` task). No DB, no service, no live UI.

## Non-goals

- **Dollar-cost conversion.** `RunUsage` does not carry pricing. A per-model price table is future work; v1 reports token counts only.
- **Per-tool token attribution within a run.** PydanticAI's `RunUsage` is per-run, not per-tool-call. Sub-run breakdown is out of scope.
- **Real-time UI or dashboard.** Reading the JSONL with an `inv` task is enough. No web view in v1.
- **Retroactive backfill.** Historical runs that predate the log are gone; the log starts on the first call after rollout.
- **Multi-run rollup into sidecars in v1.** Recommendation below keeps audit-trail sidecars untouched. Rollup into `.audit.yaml` is a deferred follow-on (see Open questions).
- **Routing decisions.** The Router does not exist yet. The schema reserves `object_kind: "routing"` and `object_id: null`, but no call site emits it in v1.

## Architectural choices

### Sink format: single append-only JSONL (option a)

Recommendation: option (a), one JSONL file. Runner-up: option (c), JSONL canonical plus a `token_usage` rollup written into `.audit.yaml`.

Tradeoff: option (a) keeps the audit-trail schema (`schema_version: 1`) frozen and avoids a migration. The cost is that a per-claim view requires reading the full log (small in practice, grep-friendly, append-only). Option (c) gives instant per-claim totals at the cost of bumping `schema_version` and changing `_write_audit_sidecar`'s contract for an aggregation that `inv tokens.summary --by object` already produces. The user asked for the simplest version; option (a) wins on that criterion. If summary cost ever becomes painful (say, 10k+ runs), promoting (a) to (c) is additive: keep writing JSONL, also stamp a derived field into the sidecar.

Option (b) (sidecar-only) is rejected because sources have no sidecar today and adding one for token tallies alone is more disruption than the JSONL.

### Capture mechanism: thin wrapper in `pipeline/common/`

A new module `pipeline/common/token_log.py` exports one async helper. It calls `agent.run(...)`, reads `result.usage()`, appends a JSONL record, and returns the result. Migrating a call site is a one-line wrap.

```python
# pipeline/common/token_log.py
async def run_with_logging(
    agent,
    user_prompt,
    *,
    object_kind: ObjectKind,   # Literal["claim", "source", "entity", "criterion", "routing"]
    object_id: str | None,
    agent_name: str,           # "researcher" | "ingestor" | "analyst" | "auditor"
    run_id: str,
    model: str,
    **run_kwargs,
):
    started_at = datetime.datetime.now(datetime.timezone.utc)
    error: str | None = None
    usage_obj = None
    try:
        result = await agent.run(user_prompt, **run_kwargs)
        try:
            usage_obj = result.usage()
        except Exception:
            usage_obj = None  # _append_record writes zeros when usage_obj is None
        return result
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _append_record(
            run_id=run_id,
            object_kind=object_kind,
            object_id=object_id,
            agent=agent_name,
            model=model,
            usage=usage_obj,
            started_at=started_at,
            error=error,
        )
```

The wrapper does not own `agent.override(model=...)`; that stays at the call site exactly as today. The wrapper is purely additive.

## Schema

One JSON object per line. UTF-8, newline-delimited, never rewritten.

```json
{
  "schema_version": 1,
  "run_id": "8b2c1f3a4d5e4f6a7b8c9d0e1f2a3b4c",
  "started_at": "2026-04-26T18:32:14.512Z",
  "object_kind": "claim",
  "object_id": "ecosia/renewable-energy-hosting",
  "agent": "analyst",
  "model": "anthropic:claude-haiku-4-5",
  "input_tokens": 4821,
  "output_tokens": 612,
  "total_tokens": 5433,
  "cache_read_tokens": 0,
  "cache_write_tokens": 0,
  "requests": 1,
  "error": null
}
```

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | int | `1` for this format. Bump on breaking changes. |
| `run_id` | str | UUID4 hex (no dashes), shared by all agent runs in one top-level pipeline call. |
| `started_at` | str | ISO-8601 UTC, with fractional seconds, when the wrapper entered the call. |
| `object_kind` | str | One of `"claim"`, `"source"`, `"entity"`, `"criterion"`, `"routing"`. |
| `object_id` | str or null | Normalized id; see below. `null` only for `routing` runs that have not yet matched a target (placeholder for the future Router). |
| `agent` | str | One of `"researcher"`, `"ingestor"`, `"analyst"`, `"auditor"`. (Add `"router"` when it lands.) |
| `model` | str | Resolved model spec passed via `cfg.model` (e.g., `"anthropic:claude-haiku-4-5"`, `"infomaniak:openai/gpt-oss-120b"`). |
| `input_tokens` | int | `RunUsage.input_tokens` (zero on error if unavailable). |
| `output_tokens` | int | `RunUsage.output_tokens` (zero on error if unavailable). |
| `total_tokens` | int | `RunUsage.total_tokens`. |
| `cache_read_tokens` | int | `RunUsage.cache_read_tokens`; relevant once prompt caching lands. Zero today. |
| `cache_write_tokens` | int | `RunUsage.cache_write_tokens`; same as above. |
| `requests` | int | `RunUsage.requests` -- count of underlying API calls (PydanticAI may retry). |
| `error` | str or null | `null` on success; `"<ExcType>: <msg>"` on raise. |

### `object_id` normalization

| object_kind | `object_id` shape | Source of value |
|---|---|---|
| `claim` (persisted) | `{entity-slug}/{claim-id}` | `claim_path.relative_to(repo_root / "research/claims").with_suffix("")`, e.g., `ecosia/renewable-energy-hosting`. Use this for `verify_claim` (entity is known up front) and any post-persistence run. |
| `claim` (in-flight) | `slugify(claim_text)[:60]` (no slash) | Used when no entity is known yet, principally `research_claim`'s researcher and ingestor calls before the analyst names the entity. The slash-or-no-slash convention distinguishes persisted from in-flight; v1 does not auto-merge them. |
| `source` | `{yyyy}/{slug}` or the URL | Matches `_write_source_files` output (`f"{sf.year}/{sf.slug}"`) once the SourceFile is built. For the ingest call itself (URL → SourceFile), use the URL as the id for that one record. |
| `entity` | `entity_ref` as written by `_write_entity_file` | E.g., `companies/ecosia` for promoted entities, `drafts/companies/ecosia` for drafts. The pipeline already computes this string; reuse it verbatim, do not re-normalize. |
| `criterion` | `{slug}` | Template slug, e.g., `renewable-energy-hosting`. |
| `routing` | `null` (v1) | Reserved; emitted only when the Router lands. |

A run that operates on multiple objects (e.g., the analyst run touches a claim *and* its sources) is recorded once against its primary object. The analyst's primary is the claim; the ingestor's primary is the source it is producing; the researcher's primary is the claim being researched; the auditor's primary is the claim being audited. This keeps each run-to-object link deterministic.

## Capture path

Wrapper file: `pipeline/common/token_log.py`. Constants:

- `TOKEN_LOG_PATH` defaults to `<repo_root>/logs/token-log.jsonl`. Override via `DR_TOKEN_LOG` env var.
- `_append_record(...)` opens with `"a"` mode, writes `json.dumps(record) + "\n"`, calls `os.fsync(f.fileno())` only when `DR_TOKEN_LOG_FSYNC=1` (default off; the cost is rarely worth it for a local dev log). When `usage` is `None`, the four token fields and `requests` are written as `0`.

### Call sites to migrate

| File | Approx. line | Agent | Wrap? |
|---|---|---|---|
| `pipeline/orchestrator/pipeline.py` | 185 | `research_agent` | yes |
| `pipeline/orchestrator/pipeline.py` | 255 | `ingestor_agent` | yes |
| `pipeline/orchestrator/pipeline.py` | 315 | `analyst_agent` | yes |
| `pipeline/orchestrator/pipeline.py` | 344 | `auditor_agent` | yes |
| `pipeline/orchestrator/cli.py` | 309 | `auditor_agent` (in `dr reassess`) | yes |
| `pipeline/orchestrator/cli.py` | 391 | `ingestor_agent` (in `dr ingest`) | yes |

`onboard_entity` runs `verify_claim` per template, so its agent calls go through the four `pipeline.py` sites above. No new wrap needed inside `onboard_entity`; it just generates a fresh `run_id` per template iteration and threads it down.

### Call-site delta example (analyst in `pipeline.py`)

Before:

```python
async def _analyse_claim(entity_name, claim_text, sources, cfg):
    prompt = build_analyst_prompt(entity_name, claim_text, sources)
    try:
        with analyst_agent.override(model=resolve_model(cfg.model)):
            res = await asyncio.wait_for(
                analyst_agent.run(prompt), timeout=cfg.analyst_timeout_s
            )
        return res.output
    ...
```

After:

```python
async def _analyse_claim(entity_name, claim_text, sources, cfg):
    prompt = build_analyst_prompt(entity_name, claim_text, sources)
    try:
        with analyst_agent.override(model=resolve_model(cfg.model)):
            res = await asyncio.wait_for(
                run_with_logging(
                    analyst_agent, prompt,
                    object_kind="claim",
                    object_id=cfg.run_object_id,
                    agent_name="analyst",
                    run_id=cfg.run_id,
                    model=cfg.model,
                ),
                timeout=cfg.analyst_timeout_s,
            )
        return res.output
    ...
```

Net change: one import, swap `analyst_agent.run(prompt)` for `run_with_logging(analyst_agent, prompt, ...)`. The other five sites follow the same pattern with their own `agent_name` and `object_kind`.

## `run_id` semantics

> **Pointer**: most of this section already describes installed behaviour as
> of the logging-infrastructure work. `VerifyConfig.run_id` exists with
> `new_run_id` as its default factory; the entry-point bindings and the
> per-template `dataclasses.replace(cfg, run_id=new_run_id())` are in
> `pipeline/orchestrator/pipeline.py`; the CLI-side bindings are in
> `pipeline/orchestrator/cli.py`. What remains specific to *this* plan is
> `run_object_id` (the field below), which logging does not need.

- Generated as `uuid.uuid4().hex` (32 hex chars, no dashes) at the top-level pipeline entry: `verify_claim`, `research_claim`, `onboard_entity` (one per template iteration), and the CLI handlers for `dr ingest` and `dr reassess`.
- Threaded via two new fields on `VerifyConfig`:

```python
run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
run_object_id: str | None = None   # set by entry point once known
```

Config-object propagation is preferred over a function arg because `cfg` already flows through every `_research`, `_ingest_one`, `_analyse_claim`, `_audit_claim` helper. No new parameters cross the helper signatures.

For `dr reassess` and `dr ingest`, which do not build a `VerifyConfig`, the wrapper is called with a locally generated `run_id` and the resolved object id (claim slug for reassess, URL-then-source-slug for ingest).

For `onboard_entity`, the per-template loop creates a fresh `cfg` copy with a new `run_id` each iteration; the four downstream agent runs in that template's `verify_claim` share that id.

## Persistence concerns

- **Append-only.** No record is ever rewritten. A new run on the same claim simply appends another line.
- **Partial failure.** The wrapper's `finally` block always writes a record. On exception, fields default to: `input_tokens=0`, `output_tokens=0`, `total_tokens=0`, `requests=0`, `error="<ExcType>: <msg>"`. The exception still propagates; logging never swallows it. Goal: no silent loss.
- **fsync.** Off by default. Opt-in via `DR_TOKEN_LOG_FSYNC=1` for paranoid runs.
- **File location.** `<repo_root>/logs/token-log.jsonl`. The `logs/` directory is local operator telemetry, not research content. Add `/logs/` to `.gitignore` as part of this plan. Rationale: the log is operator-local, mixes with no research content, and is regenerated continuously. Future operator-facing logs can co-locate here without further plumbing. *Pointer: `/logs/` is already in `.gitignore` and is already populated by `logs/info.log` and `logs/debug.log` from the logging-infrastructure work; this plan can drop the gitignore step.*
- **Concurrency.** `pipeline.py:_ingest_urls` ingests URLs concurrently via `asyncio.gather`. Append writes from multiple coroutines to the same file are unsafe at the byte level. Use a module-level `asyncio.Lock` guarding the append. Cross-process concurrency is not a v1 concern (one `dr` invocation per shell). *Pointer: stdlib `RotatingFileHandler` (used by the logging streams) handles this with internal locks; if the JSONL writer wants the same robustness without a hand-rolled `asyncio.Lock`, it could lift `_open` / `emit` patterns from the logging handler.*

## `inv tokens.summary`

Add a `tokens` namespace to `tasks.py` matching the `test_ns` precedent. The task body shells to `pipeline/common/token_log.py`'s `__main__` entry (matching the existing `inv` style of running `uv run python -m ...` inside `pipeline/`). No second CLI module: the wrapper file owns both the runtime helper and the summary CLI.

### Signature

```
inv tokens.summary
inv tokens.summary --by object [--limit N]
inv tokens.summary --by time --bucket {day|week|month}

Filters (any combination):
  --since YYYY-MM-DD            inclusive lower bound on started_at
  --until YYYY-MM-DD            inclusive upper bound on started_at
  --agent {researcher|ingestor|analyst|auditor}
  --object-kind {claim|source|entity|criterion|routing}
  --log-path PATH               override DR_TOKEN_LOG / default
```

### Behaviour

- Default (`inv tokens.summary`, no `--by`): groups by `object_kind`, sums `input_tokens`, `output_tokens`, `total_tokens`, and `runs`. Prints one row per kind plus a total row.
- `--by object`: groups by `(object_kind, object_id)`. Sorts descending by `total_tokens`. Honours `--limit` (default 20).
- `--by time --bucket day`: groups by date in UTC (`started_at[:10]`). `--bucket week` uses ISO week (`%G-W%V`). `--bucket month` uses `started_at[:7]`. Sorted ascending by bucket.
- Output: aligned plain-text table to stdout. No JSON output mode in v1.
- Empty log: prints `No token records found.` and exits 0.

### Example output

```
$ inv tokens.summary --by object --limit 3
object_kind  object_id                              runs   input    output   total
claim        ecosia/renewable-energy-hosting          12   42,118    5,732   47,850
claim        claude/no-training-on-user-data           8   28,944    3,120   32,064
source       2026/polytechnique-energy                 4   11,201    1,498   12,699
```

### Task wiring

```python
# tasks.py (additions, sketched)
@task
def _tokens_summary(ctx, by=None, bucket="day", limit=20,
                    since=None, until=None, agent=None,
                    object_kind=None, log_path=None):
    """Summarize token usage by object or time window."""
    with ctx.cd("pipeline"):
        cmd = "uv run python -m common.token_log summary"
        # ...append flags as provided...
        ctx.run(cmd, pty=True)

tokens_ns = Collection("tokens")
tokens_ns.add_task(_tokens_summary, name="summary", default=True)
ns.add_collection(tokens_ns)
```

`pipeline/common/token_log.py` ends with an `if __name__ == "__main__":` block using stdlib `argparse` (no new dependency) that dispatches to the same `iter_records()` and `summarize(...)` helpers used in tests. One file, two surfaces: the runtime wrapper for the pipeline and the summary CLI for `inv`.

## Testing

All in `pipeline/tests/`. No live API calls; `RunUsage` is already imported in two existing tests for fixture use.

| Test | Asserts |
|---|---|
| `test_token_log_wrapper.py::test_appends_one_record_per_run` | After `run_with_logging` against a `TestModel` agent, the JSONL file has exactly one line with the expected `object_kind`, `object_id`, `agent`, `run_id`, and non-negative token counts. |
| `test_token_log_wrapper.py::test_records_error_on_exception` | When the wrapped agent raises, the line is still appended with `error` populated and zeros for token fields, and the exception propagates. |
| `test_token_log_wrapper.py::test_concurrent_appends_no_corruption` | Run N coroutines through the wrapper concurrently; assert the file has N parseable JSON lines. |
| `test_token_summary.py::test_summary_by_object_kind` | Build a fixture log with mixed kinds; assert the default summary's per-kind totals match. |
| `test_token_summary.py::test_summary_by_object_sorts_and_limits` | Fixture with several claims; assert top-N order by `total_tokens` descending, limit honoured. |
| `test_token_summary.py::test_summary_by_time_buckets` | Records spanning two days, two weeks, two months; assert each bucket variant groups correctly. |
| `test_token_summary.py::test_filters` | `--since`, `--agent`, `--object-kind` filters narrow the record set as expected. |

Fixtures use `pydantic_ai.usage.RunUsage(input_tokens=..., output_tokens=..., total_tokens=..., requests=...)` and a `TestModel`-backed agent.

## Rollout order

> **Pointer**: step 5's `/logs/` gitignore line is already done. The wrapper
> in step 1 can import `new_run_id` and (optionally) `run_id_var` from
> `pipeline/common/logging_setup.py` rather than duplicating uuid plumbing.
> The `cfg.run_id` reads in steps 2-3 already work with no further wiring;
> `dr reassess` and `dr ingest` already bind a `run_id` per invocation, so
> step 3's "twice" footnote for the CLI sites no longer requires generating
> the id at the wrapper call.

1. **Wrapper and schema.** Add `pipeline/common/token_log.py` with `run_with_logging`, `_append_record`, `iter_records`, the schema constants, and unit tests for the wrapper.
2. **Migrate analyst.** Wrap the analyst call in `pipeline.py:_analyse_claim` first; it is the lowest-risk call site (no concurrency, no tools, fastest path to a real record on disk). Run `dr claim-probe` once on a canned claim and inspect the JSONL.
3. **Migrate the rest.** Wrap researcher, ingestor (twice: pipeline.py and cli.py), and auditor (twice). Verify `run_id` propagation by running a full `dr claim-probe` and confirming all four agent runs share one id.
4. **Add `inv tokens.summary`.** Implement the `tasks.py` namespace and the `__main__` block in `pipeline/common/token_log.py`. Add aggregation tests.
5. **Gitignore + docs.** Add `/logs/` to `.gitignore`; add a one-paragraph note in `AGENTS.md` § "Tooling: dr vs inv" pointing at `inv tokens.summary`.
6. **Optional sidecar rollup (deferred).** If/when option (c) is wanted, write a follow-on plan to add a `token_usage` block to `.audit.yaml` derived from the JSONL on every audit-sidecar write. Bump `schema_version` to `2` at that point.

## Open questions / deferred

1. **Dollar-cost conversion.** Needs a per-model price table keyed on `model` strings. Likely lives in `pipeline/common/models.py` next to `resolve_model`. Out of v1.
2. **Per-tool attribution within a run.** `RunUsage` is per-run; PydanticAI does not split tokens per tool call. Would need PydanticAI hooks or instrumentation we have not investigated.
3. **Multi-run aggregation across re-runs of the same claim.** Today, `inv tokens.summary --by object` already sums across re-runs. If a "current run vs. lifetime" split is wanted, add a `--latest-run-only` filter later.
4. **Log rotation / size cap.** A JSONL line is ~250 bytes; 10k runs = ~2.5 MB. No rotation in v1. Revisit at 100k records.
5. **Routing object_kind.** Reserved but unused until the Router agent lands (`docs/plans/triage-agent.md`). When it does, the only change is one new `run_with_logging` call site with `object_kind="routing"`.
6. **Multiple pipelines per process.** The module-level `asyncio.Lock` assumes one event loop. If `dr` ever forks workers, replace with a file lock (`fcntl.flock`).

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-04-26 | agent (claude-opus-4-7) | deep, implementation, iterated | Verified all six call sites against `pipeline.py` and `cli.py`; corrected ingestor CLI line (384 → 391); reused `entity_ref` instead of normalizing entity ids; split `claim` `object_id` shape into persisted vs. in-flight; added `cache_read_tokens`/`cache_write_tokens` to schema; collapsed `inv` task wiring to a single `__main__` in `pipeline/common/token_log.py` (no separate `token_log_cli.py`); switched log location from `.dr/` to `logs/`; tightened wrapper's `result.usage()` error path. |
| 2026-04-27 | agent (claude-opus-4-7) | non-prescriptive pointers | Logging-infrastructure work shipped first and incidentally implemented `VerifyConfig.run_id`, the `bind_run_id`/`new_run_id` helpers, the entry-point bindings, the per-template `run_id` per onboard iteration, and `/logs/` gitignore. Added pointer callouts (top, run_id semantics, persistence concerns, rollout) noting which sections of this plan now describe already-installed behaviour. No prescriptive edits; the plan author can fold or rewrite affected sections at their discretion. |
