# Plan: Tighten HTTP and agent timeouts in the ingestor path

**Status**: Done (already implemented — `pipeline/common/timeouts.py` in place)

## Problem

Slow hosts eat 30s per fetch in `pipeline/ingestor/agent.py:45` (`web_fetch`). With 4 URLs x 6 templates during onboarding, one sluggish host can delay a run by minutes without producing usable pages. The ingestor agent's 90s wrapper in `pipeline/orchestrator/pipeline.py:197` is generous enough that the slow HTTP is the binding constraint, not the LLM.

`pipeline/ingestor/tools/web_fetch.py` does **no** network I/O -- it only parses HTML via BeautifulSoup. All HTTP happens in `agent.py` (fetch) and `tools/wayback.py` (availability + save).

This plan is complementary to:

- *ingestor fail-fast on 403* (403 returns ~instantly; tightening timeouts does not help that case)
- *researcher host blocklist* (removes slow/hostile hosts before ingest; timeouts are the backstop)

## Proposed timeout values

| Site | Current | Proposed | Rationale |
|---|---|---|---|
| `web_fetch` httpx | `timeout=30.0` (flat) | `httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)` | Legitimate pages respond <5s; 15s read is a generous ceiling. Connect=5s catches dead hosts fast. |
| `ingestor_agent.run` wait_for | `timeout=90` | `timeout=60` | HTTP read (15s) + wayback check (15s) + wayback save (30s, skipped by default) + one LLM call (<20s) = ~50s worst realistic. 60s leaves headroom. |
| `check_wayback` httpx | `timeout=15.0` | unchanged | Aligns with new fetch read timeout. |
| `save_to_wayback` httpx | `timeout=30.0` | unchanged | Save endpoint is slow by nature; skipped by default (`VerifyConfig.skip_wayback=True`). |
| Researcher / Analyst / Auditor wait_for | `timeout=60` | unchanged | Out of scope; LLM-bound, not HTTP-bound. |

## Timeout chain invariant

Ingestor agent total wall time must satisfy:

```
agent_timeout >= fetch_connect + fetch_read + wayback_check + (wayback_save if not skipped) + llm_call_budget
```

With `skip_wayback=True` (default): `5 + 15 + 0 + 0 + ~20 = ~40s` within a 60s agent budget. With wayback enabled: `5 + 15 + 15 + 30 + 20 = 85s`, exceeding 60s. **Decision**: if a user runs with `skip_wayback=False`, bump `ingest_timeout_s` conditionally to 120s (compute in `VerifyConfig.__post_init__` or at call site).

## Where to put the constants

**Split:**

1. `pipeline/common/timeouts.py` (new) -- internal constants not meant for CLI tuning:
   - `HTTP_CONNECT_S = 5.0`
   - `HTTP_READ_S = 15.0`
   - `HTTP_WRITE_S = 5.0`
   - `HTTP_POOL_S = 5.0`
   - `WAYBACK_CHECK_S = 15.0`
   - `WAYBACK_SAVE_S = 30.0`
   - Helper: `def default_httpx_timeout() -> httpx.Timeout`

2. `VerifyConfig` fields (in `pipeline/orchestrator/pipeline.py:49`) -- user-tunable wall-clock budgets:
   - `ingest_timeout_s: float = 60.0`
   - `research_timeout_s: float = 60.0`
   - `analyst_timeout_s: float = 60.0`
   - `auditor_timeout_s: float = 60.0`

   (The latter three are unchanged values but exposed for symmetry; makes future tuning single-file.)

No CLI flag is added in this plan -- `VerifyConfig` defaults cover the POC. A later plan can expose `--ingest-timeout` on `dr verify`.

## Implementation steps

1. Create `pipeline/common/timeouts.py` with the six constants and the `default_httpx_timeout()` helper.
2. In `pipeline/ingestor/agent.py:45`, replace `timeout=30.0` with `timeout=default_httpx_timeout()`. Import from `common.timeouts`.
3. In `pipeline/ingestor/tools/wayback.py`, replace the two literals with `WAYBACK_CHECK_S` and `WAYBACK_SAVE_S`. (Values unchanged; for discoverability.)
4. In `pipeline/orchestrator/pipeline.py`:
   - Add the four `*_timeout_s` fields to `VerifyConfig`.
   - Replace the literal `timeout=90` at line 197 with `cfg.ingest_timeout_s`.
   - Replace `timeout=60` at lines 160, 248, 277 with the corresponding `cfg.*_timeout_s`.
5. In `_ingest_one`, keep `except asyncio.TimeoutError` returning `StepError(step="ingest", error_type="timeout", ...)`. No change needed -- the branch already exists at line 201.

## Test plan

New tests in `pipeline/tests/test_tools.py` (HTTP fetch) and `pipeline/tests/test_orchestrator.py` (agent wrapper):

1. **`test_web_fetch_read_timeout_within_window`** (test_tools.py)
   - Use `respx` to mock a slow host, or simulate `httpx.ReadTimeout` directly.
   - Assert `web_fetch` returns `{"error": ...}` within ~16s wall clock (`@pytest.mark.timeout(20)`).

2. **`test_web_fetch_connect_timeout_fast_fail`** (test_tools.py)
   - Point at a blackhole IP (e.g. `http://10.255.255.1/`) or mock `httpx.ConnectTimeout`.
   - Assert error dict within ~6s.

3. **`test_ingest_one_returns_step_error_on_agent_timeout`** (test_orchestrator.py)
   - Patch `ingestor_agent.run` to `asyncio.sleep(120)`.
   - Set `cfg.ingest_timeout_s = 1.0`.
   - Call `_ingest_one`; assert returns `StepError(step="ingest", error_type="timeout")`.

4. **`test_verify_config_defaults`** (test_orchestrator.py)
   - Assert `VerifyConfig().ingest_timeout_s == 60.0` and pipeline threads it through (inspect via monkeypatch on `asyncio.wait_for` or via a spy).

All tests must be deterministic (no real network) and run under 5s wall time.

## Done when

- `pipeline/common/timeouts.py` exists with the six constants and `default_httpx_timeout()`.
- `web_fetch` uses `httpx.Timeout(connect=5, read=15, write=5, pool=5)`.
- `VerifyConfig` has the four `*_timeout_s` fields; all four `asyncio.wait_for` sites read from it.
- Wayback timeouts moved to named constants (values unchanged).
- Four new tests pass; existing `test_tools.py` and `test_orchestrator.py` suites still green.
- Manual smoke: `dr verify` run against a known-slow host (e.g. a `httpbin.org/delay/30` URL) fails within ~17s per URL instead of 30s+, and the ingestor agent wrapper fails within ~60s instead of 90s.
- Timeout chain invariant documented in a comment above `VerifyConfig`.

## Critical files

- `pipeline/ingestor/agent.py`
- `pipeline/ingestor/tools/web_fetch.py` (no HTTP I/O; no change)
- `pipeline/ingestor/tools/wayback.py`
- `pipeline/orchestrator/pipeline.py`
- `pipeline/common/timeouts.py` (new)
- `pipeline/tests/test_tools.py`
- `pipeline/tests/test_orchestrator.py`

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-20 | agent (cross-review) | code verification | Verified timeout values and call sites against actual code; promoted to ready with follow-ups (see review notes below). |
| 2026-04-22 | agent (active review) | status + stub + duplicate check | No top-level status label present; cross-review notes from 2026-04-20 indicate "Promoting" (i.e., ready). Not a stub. Part of a complementary triad with `ingestor-fail-fast-403.md` and `researcher-host-blocklist.md`; not duplicates. Added this table; preserved original review notes below. |

## Review Notes (2026-04-20)

Cross-review verified against code. Promoting with minor follow-ups the implementer should address.

**Verified correct:**
- `pipeline/ingestor/agent.py:45` has `timeout=30.0`.
- `pipeline/ingestor/tools/web_fetch.py` has no network I/O (pure BeautifulSoup parsing).
- `pipeline/ingestor/tools/wayback.py` timeouts are 15.0 (line 25) and 30.0 (line 49).
- Four `asyncio.wait_for` sites exist at lines 160, 197, 248, 277 with the documented current values.
- `VerifyConfig` is a dataclass; all existing kwargs-based constructors (cli.py x3, test_onboard.py x3, test_research_integration.py, test_acceptance.py) will continue to work after adding new fields with defaults.
- `respx>=0.22` is already in `[dependency-groups].dev` -- no dependency add needed.
- `httpx.AsyncClient.get(url, timeout=httpx.Timeout(...))` is valid; httpx accepts a `Timeout` object at the request level.

**To address during implementation:**
1. Plan is vague on where the conditional `skip_wayback=False` -> 120s bump happens. Recommend `VerifyConfig.__post_init__` with a comment, so callers that pass `ingest_timeout_s` explicitly override the auto-bump. Document this precedence.
2. 5s connect timeout is fine for US hosts; may be tight for some international or overloaded hosts. Acceptable for a POC with fail-fast goals; mention it in the commit body so the next operator knows the tradeoff.
3. Test 4 (`test_verify_config_defaults`) should also assert that `VerifyConfig(skip_wayback=False)` yields an `ingest_timeout_s` >= 85 (if the auto-bump is implemented) -- otherwise the invariant goes untested.
