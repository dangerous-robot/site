# Plan: Parallelize per-template loop in `onboard_entity`

## Problem

`pipeline/orchestrator/pipeline.py:563` iterates applicable claim templates sequentially. Each iteration calls `verify_claim` (research + ingest + analyst + auditor) plus a second `_research` + `_ingest_urls` to persist sources. For 6 core company templates wall time is ~6x one template. We want bounded concurrency with a semaphore.

## Design

### 1. Concurrency primitive

- Use `asyncio.Semaphore(cfg.concurrency)` created inside `onboard_entity`, scoping it to Step 5 only (light research, screening, checkpoint, and entity-file write remain sequential).
- Add `concurrency: int = 3` to `VerifyConfig` in `pipeline/orchestrator/pipeline.py`. Validate `concurrency >= 1`.
- Add CLI flag `--concurrency N` (default 3) to `dr onboard` in `pipeline/orchestrator/cli.py` and thread into `VerifyConfig`. Do NOT add to `dr claim-probe` / `dr claim-draft` (single-claim commands); single-claim already parallelizes ingest via `_ingest_urls`.

### 2. Per-template worker

Extract the body of the current `for idx, slug` loop into `async def _run_template(slug, idx, total, template_lookup, ...) -> _TemplateOutcome`, where `_TemplateOutcome` is a small dataclass capturing: `slug`, `claim_path_rel | None`, `errors: list[str]`, `failed: bool`, `start_msg: str`, `done_msg: str`, `log_order_idx: int` (original position in `applicable_slugs`).

Wrap with semaphore:

```python
sem = asyncio.Semaphore(cfg.concurrency)
async def _guarded(slug, idx):
    async with sem:
        return await _run_template(slug, idx, total, ...)
outcomes = await asyncio.gather(
    *[_guarded(s, i) for i, s in enumerate(applicable_slugs, 1)],
    return_exceptions=False,  # _run_template catches all exc internally
)
```

Each worker should own its own `httpx.AsyncClient` (short-lived, per-template) rather than sharing; this matches current code's `async with httpx.AsyncClient()` and avoids contention on a shared client's connection pool.

### 3. Deterministic ordering

- Workers buffer their stderr lines (`start_msg`, `done_msg`, `fail_msg`) into the outcome rather than `click.echo` directly. After `gather`, iterate outcomes sorted by `log_order_idx` (i.e. by template slug order in `applicable_slugs`) and echo in that stable order. This preserves `[i/N] Researching ...` / `[i/N] Done ...` grouping but prints them after work completes rather than live.
  - Alt (live progress): echo a single-line `[i/N] started: slug` under a `logging_lock` at start, batch results at end. If we want live feedback, this is the cheap option -- keep `start_msg` under a lock and still sort final block.
- `result.claims_created`, `result.claims_failed`, `result.errors` are populated in order by iterating sorted outcomes, not by completion order. This keeps test assertions and report output stable.

### 4. Interactive checkpoints

`verify_claim` calls `gate.review_sources` and `gate.review_disagreement`. With N templates in flight, two concurrent `click.confirm` calls would interleave and corrupt TTY state.

Chosen approach: **clamp `--interactive` to concurrency=1 with a warning** (simpler than a per-handler lock; lock-serializes anyway negates the parallelism benefit for I/O-bound review steps).

Alternative (if needed later): add an `asyncio.Lock` attribute on `CLICheckpointHandler.__init__` and wrap `review_sources` / `review_disagreement` / `review_onboard` with `async with self._lock:`. Thread `slug` through the handler protocol as optional `context: str = ""` kwarg so banners can show which template is under review.

### 5. Rate limits

- Anthropic: at concurrency=3, peak concurrent Anthropic calls per template ≈ (1 research + max_sources ingest + 1 analyst + 1 auditor) ≈ 7, times 3 = ~21. Well within Tier 1+ RPM; TPM is the risk vector on large source bodies. Rely on pydantic_ai retry.
- Brave Search: at concurrency=3 we issue up to ~3 concurrent `web_search` tool calls. Brave free tier is 1 req/s; paid is 20 req/s. Document 3 as safe for paid; users on free tier should set `--concurrency 1`.
- Note: the duplicate `_research` + `_ingest_urls` at pipeline.py:587-590 roughly halves Brave/LLM load if eliminated (see companion plan `onboard-reuse-verify-sources.md`).

### 6. Tests (`pipeline/tests/test_onboard.py`)

- `TestOnboardEntityParallel`:
  - `test_parallel_completes_all_templates`: `config.concurrency=3`, assert `len(result.templates_applied) == 6` and `len(result.claims_created) == 6`.
  - `test_parallel_output_order_stable`: run twice with `concurrency=3`, assert `result.claims_created` identical across runs. Use a TestModel wrapper that sleeps random jitter to force interleaving.
  - `test_concurrency_one_matches_sequential`: `concurrency=1` produces byte-identical `OnboardResult` to current behavior.
- `TestOnboardInteractiveSerialization`:
  - `test_interactive_clamps_concurrency`: invoke CLI with `--interactive --concurrency 3`, assert warning to stderr and runtime concurrency = 1.
- Extend `TestOnboardEntityHappyPath` to pass `concurrency=3` explicitly in one variant.

### 7. Done When

- `VerifyConfig.concurrency` exists with default 3; CLI `--concurrency` option wired.
- `onboard_entity` Step 5 uses `asyncio.gather` under `asyncio.Semaphore(cfg.concurrency)`.
- Per-template work encapsulated in `_run_template` returning a result struct; no direct mutation of `result` inside the worker.
- Final `result.claims_created` / `claims_failed` / `errors` ordered by slug position in `applicable_slugs`.
- `--interactive` + `--concurrency > 1` emits warning and clamps to 1.
- All existing `test_onboard.py` tests pass unchanged; new parallel tests pass.
- Wall-clock: a 6-template run with TestModel-sleep-200ms per step drops from ~1.2s*6=7.2s to ~2.4s at concurrency=3 (smoke-test benchmark in a new test).

## Files to touch

- `pipeline/orchestrator/pipeline.py` -- `VerifyConfig`, `onboard_entity`, new `_run_template`.
- `pipeline/orchestrator/checkpoints.py` -- lock on `CLICheckpointHandler` (if lock approach chosen), optional `context` kwarg on Protocol.
- `pipeline/orchestrator/cli.py` -- `--concurrency` option, interactive clamp warning.
- `pipeline/tests/test_onboard.py` -- new parallelism + interactive tests.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (active review) | status + stub + duplicate check | No explicit status label present; content reads as ready to implement. Not a stub. Related plan: `onboard-reuse-verify-sources.md` also modifies the per-template loop and should land first (it eliminates the duplicate `_research`+`_ingest_urls` call referenced in section 5 of this plan). The plan already cross-references `onboard-reuse-verify-sources.md` at the rate-limits section. |
