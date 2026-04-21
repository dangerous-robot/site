# Plan: Ingestor fail-fast on terminal HTTP responses

## Problem

`web_fetch` (pipeline/ingestor/agent.py:42) returns `{"error": ...}` on any `HTTPError`, so the LLM interprets 401/403/451 identically to a transient failure: it calls `wayback_check` (which rarely helps for auth walls), and PydanticAI's `retries=2` may re-drive the agent loop. Each dead URL burns ~30-60s during onboarding.

## Design: tool-level raise with a distinct exception

Prefer a **non-retryable exception** over a sentinel dict. PydanticAI retries tool calls when the tool raises `ModelRetry` or the tool result fails validation; other exceptions propagate out of `agent.run()`. A raised `TerminalFetchError` therefore short-circuits the entire agent run for that URL -- no further tool calls, no retry budget consumed -- and the orchestrator's existing `except Exception` in `_ingest_one` converts it to a `StepError`.

## Status code policy

| Code | Class | Behavior |
|------|-------|----------|
| 401 | Auth required | **Terminal**. Wayback won't help -- origin requires creds; archive.org usually respects robots/auth walls. |
| 403 | Forbidden | **Terminal**. Often bot block / Cloudflare / region; retrying from same client won't change outcome. |
| 451 | Legal block | **Terminal**. Legally unavailable; wayback usually excluded too. |
| 402 | Payment required | **Terminal** (paywall). Typically not archivable. |
| 410 | Gone | **Soft**. Resource permanently gone; wayback_check is still worth attempting -- keep existing behavior. |
| 429 | Rate limited | **Soft**. Single retry with 2s backoff inside the tool; if still 429, raise `TerminalFetchError`. |
| 404 | Not found | **Soft**. Keep existing behavior (returns error dict) -- LLM should try wayback. |
| 5xx | Server error | **Soft**. Keep existing behavior. |

## Implementation

1. **New exception** in `pipeline/ingestor/tools/web_fetch.py`:

   ```python
   class TerminalFetchError(Exception):
       def __init__(self, url: str, status_code: int, reason: str):
           self.url = url
           self.status_code = status_code
           self.reason = reason
           super().__init__(f"Terminal fetch failure: {status_code} {reason} for {url}")

   TERMINAL_STATUS_CODES = frozenset({401, 402, 403, 451})
   ```

2. **Update `web_fetch` tool** in `pipeline/ingestor/agent.py`:
   - After `ctx.deps.http_client.get(...)`, before `raise_for_status()`, inspect `resp.status_code`.
   - If in `TERMINAL_STATUS_CODES`: raise `TerminalFetchError(url, code, resp.reason_phrase)`.
   - If `429`: sleep 2s, retry once. If still 429, raise `TerminalFetchError`.
   - Otherwise fall through to existing `raise_for_status()` + error-dict path.
   - Do NOT wrap `TerminalFetchError` in the `except httpx.HTTPError` branch (not a subclass).

3. **Agent retry handling**: `retries=2` at agent creation only re-invokes the model on validation failures / `ModelRetry`. Raising `TerminalFetchError` out of the tool is not caught by the agent's retry logic, so it propagates. No change to the `Agent(...)` construction.

4. **Orchestrator mapping** in `pipeline/orchestrator/pipeline.py:_ingest_one` (~line 205): add a branch before the generic `Exception`:

   ```python
   except TerminalFetchError as exc:
       logger.info("Skipped terminal fetch (%d): %s", exc.status_code, url)
       return StepError(
           step="ingest", url=url,
           error_type=f"http_{exc.status_code}",
           message=exc.reason, retryable=False,
       )
   ```

   `StepError(retryable=False)` field is already defined in `checkpoints.py`.

5. **Instructions update** in `pipeline/ingestor/instructions.md`:
   > If `web_fetch` raises or returns an error indicating an auth wall or paywall (401/403/451), do NOT call `wayback_check` -- these pages are not archived. Abort the ingestion. The orchestrator will record this as a skipped source.

   Defense-in-depth; primary mechanism is the raise.

6. **Do not call `wayback_check` for terminal errors**: guaranteed because the raise terminates the agent run before the LLM gets another turn.

## Test plan

Using `pytest` + `httpx.MockTransport` or `respx`:

- `test_terminal_403_raises`: mock 403; assert `web_fetch` raises `TerminalFetchError` with `status_code == 403`; assert `wayback_check` was not called (spy on `check_wayback`).
- `test_terminal_401_raises`: same for 401.
- `test_terminal_451_raises`: same for 451.
- `test_429_single_retry_then_raise`: 429 twice. Assert two HTTP calls, then `TerminalFetchError`. Elapsed ~2s.
- `test_429_recovers`: 429 then 200. Assert success, no raise.
- `test_404_still_soft`: 404 returns error dict (unchanged behavior).
- `test_orchestrator_maps_to_step_error`: call `_ingest_one` with a mocked 403 URL; assert returned `StepError` has `error_type == "http_403"` and `retryable is False`.
- `test_agent_does_not_retry_on_terminal`: fake model that counts tool calls; assert `web_fetch` is called exactly once; the agent does not re-invoke the tool after `TerminalFetchError`.

## Done when

1. `TerminalFetchError` raised for 401/402/403/451, and for 429 after one retry.
2. Orchestrator returns `StepError(error_type="http_4xx", retryable=False)` for those URLs; pipeline continues on other URLs.
3. No `wayback_check` call occurs in the agent run for a terminal URL (verified by test spy).
4. Agent retry budget is not consumed for terminal URLs (verified by test counting model invocations).
5. Onboarding CLI output shows terminal URLs complete in <3s each.
6. Existing tests for 404/5xx/timeout behavior continue to pass.
7. `instructions.md` updated with the guidance paragraph.

## Out of scope

- Researcher-side host blocklist to pre-filter known-dead domains (separate plan: `researcher-host-blocklist.md`).
- Per-domain backoff / circuit breaker across pipeline runs.
- Retrying terminal errors behind a residential-proxy escape hatch.

## Critical files

- `pipeline/ingestor/agent.py`
- `pipeline/ingestor/tools/web_fetch.py`
- `pipeline/orchestrator/pipeline.py`
- `pipeline/ingestor/instructions.md`
- `pipeline/orchestrator/checkpoints.py`
