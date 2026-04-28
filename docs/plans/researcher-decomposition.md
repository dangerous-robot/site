# Plan: Decompose the Researcher into small, effort-controlled agent calls

## Context

The Researcher agent (`pipeline/researcher/agent.py`) is currently a single PydanticAI agent that runs a free-form `web_search` tool loop internally. The LLM decides how many queries to run, when to stop, and which URLs to return — all invisible to the operator. Effort is controlled only by the system prompt instruction ("try 2-3 more queries if you find fewer than 6"), which fires non-deterministically.

The goal is to replace this with a fixed 3-step pipeline of small, tool-free LLM decisions (each suited to a Haiku-class model), where the operator explicitly controls effort via `max_initial_queries`. Because this multiplies the number of LLM calls per claim, a concurrency semaphore is added to keep parallel `dr onboard` sessions within provider rate limits.

The classic agent is temporary scaffolding: it runs in parallel during validation, then is deleted once the decomposed path proves comparable on real claims. The decomposed path becomes the only researcher implementation.

---

## Decomposed steps

The single tool-using agent call becomes a 3-step pipeline. **None of the LLM calls use tools** — the orchestrator handles all HTTP, then injects results into each model's prompt as structured input.

```
Step 1 — Query Planner (Haiku, structured output, no tools)
  Input:  claim_text, entity_name
  Output: QueryPlan(queries: list[str], rationale: str)
  The model generates N search queries from the claim text.
  N is capped by max_initial_queries: injected into the system prompt AND
  enforced by hard-truncating plan.queries[:max_initial_queries] post-call.
  Both guards are required; structured-output models can exceed count instructions.

Step 2 — Search Executor (orchestrator, no LLM)
  Input:  QueryPlan.queries
  Output: list[SearchCandidate(url, title, snippet, from_query)]
  Orchestrator calls Brave API for each query in parallel (asyncio.gather).
  Deduplicates by exact URL string match before returning.
  No model involved — pure HTTP.

Step 3 — URL Scorer (Haiku, structured output, no tools)
  Input:  claim_text, entity_name, list[SearchCandidate]
  Output: ScoredURLs(kept: list[str], dropped: list[str], rationale: str)
  Model sees title + snippet only (body fetching is the ingestor's job).
  Scores 1-5 relevance; kept = score >= 3.
  Returns the full kept list; the orchestrator applies cfg.max_sources cap
  (same as the classic path — keeping the cap in one place).
```

**Effort lever:** `max_initial_queries: int = 3` — more queries means a wider first-pass net. Setting `--max-initial-queries 5` is the "work harder" dial. No feedback loop; quality control shifts to the downstream ingestor (already tolerates partial yield).

**Why tool-free by design:** Steps 1 and 3 are pure structured-output calls. The orchestrator owns all side effects (HTTP, deduplication). This makes both steps compatible with any provider that supports structured output, including Infomaniak's gemma3n — which cannot use `tool_choice`. This is a stricter guarantee than the `tool-free-researcher-ingestor_stub.md`, which retrofits tool-free behavior onto the existing monolithic agent as a provider workaround.

---

## Concurrency / queuing

Each decomposed researcher call spawns 2 small LLM calls instead of 1 tool-using call. With `dr onboard` parallelizing 6 templates (per `plans/onboard-parallelize-templates.md`), peak concurrent LLM sessions across all agents in one run can reach 20+.

**Solution: a shared `asyncio.Semaphore` passed explicitly through the call chain.**

`VerifyConfig` stores the concurrency cap as a plain `int`:

```python
llm_concurrency: int = 8  # new field on VerifyConfig — int only, not a Semaphore
```

The semaphore itself is never stored on `VerifyConfig`. It is created at the top-level entry point and passed explicitly:

```python
# In verify_claim / research_claim (single-claim entry points):
sem = asyncio.Semaphore(cfg.llm_concurrency)

# In onboard_entity (parallel-template entry point):
# one semaphore shared across ALL concurrent verify_claim calls
sem = asyncio.Semaphore(cfg.llm_concurrency)
```

The semaphore is threaded as an explicit kwarg through the modified call chain:

```python
# pipeline.py
async def _research(client, entity_name, claim_text, cfg, sem) -> tuple[list[str], list[StepError]]:
    ...

# researcher/decomposed.py
async def decomposed_research(claim_text, entity_name, cfg, sem, client) -> tuple[list[str], list[StepError]]:
    async with sem:
        plan = await QueryPlannerAgent.run(...)
    results = await execute_searches(plan.queries, client)  # no sem; pure HTTP
    async with sem:
        scored = await URLScorerAgent.run(...)
    ...

# pipeline.py (ingest)
async def _ingest_one(client, url, cfg, today, sem) -> tuple[str, SourceFile] | StepError:
    ...
    async with sem:
        res = await asyncio.wait_for(ingestor_agent.run(prompt, deps=deps), ...)
    ...

async def _ingest_urls(client, urls, cfg, sem) -> ...:
    outcomes = await asyncio.gather(
        *[_ingest_one(client, url, cfg, today, sem) for url in urls]
    )
    ...
```

`asyncio.Semaphore` is loop-bound; creating it inside `asyncio.run()` (or inside the coroutine that `asyncio.run()` drives) is correct. Do not create it before `asyncio.run()`.

---

## Transition and removal

The classic `research_agent` runs alongside the decomposed path only during validation. Exit condition: run both paths against the current v1 launch claim set; if output URL overlap is >= 50% and downstream ingest yield is comparable, delete:

- `pipeline/researcher/agent.py` (the PydanticAI classic agent)
- The `researcher_mode` branch in `_research()`
- `researcher_mode` from `VerifyConfig` and the CLI flag

At that point the decomposed path is the only researcher path. No mode switch; no bifurcation in `_research()`.

---

## New `VerifyConfig` fields

Add to `pipeline/orchestrator/pipeline.py:VerifyConfig` (additive, no existing fields changed):

```python
researcher_mode: Literal["classic", "decomposed"] = "classic"  # temporary; removed post-validation
max_initial_queries: int = 3   # effort lever: more queries = wider net
llm_concurrency: int = 8       # int cap; Semaphore created at call site
```

CLI flags added to `dr verify-claim` (and passed through `dr onboard` via shared `VerifyConfig`):

```
--researcher-mode [classic|decomposed]   (default: classic; removed post-validation)
--max-initial-queries N                  (default: 3)
--llm-concurrency N                      (default: 8)
```

---

## New modules

| File | Purpose |
|------|---------|
| `pipeline/researcher/planner.py` | `QueryPlannerAgent` (Haiku, structured output). Models: `QueryPlan(queries: list[str], rationale: str)`. |
| `pipeline/researcher/scorer.py` | `URLScorerAgent` (Haiku, structured output). Models: `SearchCandidate(url, title, snippet, from_query)`, `ScoredURLs(kept: list[str], dropped: list[str], rationale: str)`. |
| `pipeline/researcher/decomposed.py` | `decomposed_research(claim_text, entity_name, cfg, sem, client) → tuple[list[str], list[StepError]]`. Orchestrates steps 1-3. Houses `execute_searches(queries, client) → list[SearchCandidate]` — the Brave fan-out. |
| `pipeline/tests/test_researcher_decomposed.py` | Unit + integration tests (see verification section). |

## Modified files

| File | Change |
|------|--------|
| `pipeline/researcher/agent.py` | Rename `_search_brave` → `search_brave` (public). `decomposed.py` imports it. Existing `research_agent` untouched. |
| `pipeline/orchestrator/pipeline.py` | Add new `VerifyConfig` fields (`researcher_mode`, `max_initial_queries`, `llm_concurrency` — int only). Create `sem` at the top of `verify_claim`/`research_claim`/`onboard_entity`. Thread `sem` into `_research`, `_ingest_one`, `_ingest_urls`. Add decomposed branch inside `_research`. |
| `pipeline/orchestrator/cli.py` | Add `--researcher-mode`, `--max-initial-queries`, `--llm-concurrency` to `dr verify-claim`. Thread into `VerifyConfig`. |

---

## What stays unchanged

- `research_agent` (classic path) — untouched during validation; deleted post-validation
- `_research()` return contract — both paths return `tuple[list[str], list[StepError]]`
- `max_sources` cap applied in orchestrator (`_research`) for both paths, not in the scorer
- Ingestor, Analyst, Auditor agents — no behavior changes (only `_ingest_one`/`_ingest_urls` gain a `sem` kwarg)
- All existing `VerifyConfig` fields — additive only

---

## Implementation order

Build in this sequence to keep the diff reviewable and tests runnable at each step:

1. **`researcher/agent.py`** — rename `_search_brave` to `search_brave` (public). Pure refactor; no behavior change. Existing tests pass.
2. **`researcher/planner.py`** — `QueryPlannerAgent` + `QueryPlan` model. Unit-testable in isolation with `TestModel`.
3. **`researcher/scorer.py`** — `URLScorerAgent` + `SearchCandidate` + `ScoredURLs`. Unit-testable in isolation.
4. **`researcher/decomposed.py`** — wire steps 1-3 into `decomposed_research`. `execute_searches` calls `search_brave` per query, deduplicates by exact URL string, returns `list[SearchCandidate]`. Integration-testable with mocked Brave.
5. **`VerifyConfig` fields + CLI flags** — add `researcher_mode`, `max_initial_queries`, `llm_concurrency`. No routing yet; classic path unaffected.
6. **`_research` branch + semaphore plumbing** — add `sem` kwarg to `_research`, `_ingest_one`, `_ingest_urls`. Create `sem` at top of `verify_claim`/`research_claim`. Add `if cfg.researcher_mode == "decomposed"` branch.
7. **`dr onboard` semaphore threading** — create single shared `sem` in `onboard_entity` above the parallel gather; thread into per-template `verify_claim` calls.
8. **Tests** — write alongside each step; see verification section.
9. **Validation + removal** — run both paths against the v1 launch claim set. If parity confirmed: delete `research_agent`, remove `researcher_mode` branch from `_research()`, remove `researcher_mode` from `VerifyConfig` and CLI.

---

## Relationship to existing stubs and plans

| Plan | Relationship |
|------|-------------|
| `tool-free-researcher-ingestor_stub.md` | Orthogonal. That plan retrofits tool-free onto the existing monolithic agent for provider compatibility. This plan is tool-free by construction for different reasons (small decisions, effort control). Compatible but independent. |
| `analyst-decomposition_stub.md` | Same pattern applied to the Analyst. Shares the "structured-output sub-call" shape and the `llm_concurrency` semaphore. |
| `onboard-parallelize-templates.md` | That plan adds `VerifyConfig.concurrency` for template-level parallelism; this plan adds `llm_concurrency` for call-level parallelism. They stack: `concurrency=3` templates, each bounded by `Semaphore(llm_concurrency)`. The shared semaphore must be created in `onboard_entity` so all templates and all their sub-calls share one instance. |

---

## Verification

1. **Unit: Query Planner cap enforcement**
   - Call `QueryPlannerAgent` with `TestModel` configured to return 6 queries; pass `max_initial_queries=3`. Assert `QueryPlan.queries` has exactly 3 entries (post-call hard-truncation active).

2. **Unit: each sub-agent in isolation**
   - `test_query_planner_output_shape`: `QueryPlannerAgent` with `TestModel` returns a valid `QueryPlan`; `rationale` is a non-empty string.
   - `test_url_scorer`: `URLScorerAgent` scores a fixture set of 5 candidates; `kept` contains only candidates with score >= 3; `kept + dropped` equals full input set.

3. **Unit: `decomposed_research` step sequencing**
   - Patch `execute_searches` to return a fixed 4-candidate list (with 1 duplicate URL pre-dedup). Assert scorer is called with 3 unique candidates. Assert final output is the kept subset, capped at `max_sources=2` by the orchestrator (not the scorer).

4. **Semaphore: concurrency is bounded**
   - Launch 10 concurrent `decomposed_research` calls behind `Semaphore(3)`; assert via an atomic counter that no more than 3 LLM calls execute simultaneously.

5. **Parity: classic vs decomposed return same shape**
   - Run both paths against the same claim with mocked Brave + `TestModel`. Assert both return `list[str]`; URL overlap >= 50% on a reproducible fixture.

6. **CLI smoke: `dr verify-claim --researcher-mode decomposed` exits 0** with mocked Brave + `TestModel`.

7. **Regression: existing `test_research_integration.py` and `test_orchestrator.py` pass unchanged** (classic path untouched).

---

## Open questions

Decisions to make before starting implementation:

1. **URL dedup canonicalization.** The plan commits to exact-string match for v1 (matches what Brave returns, zero ambiguity). If Brave returns the same article with and without a trailing slash, duplicates slip through. Decide before implementation: keep exact-string (simplest, upgrade later), or add a minimal canonical form (lowercase host, strip fragment, normalize trailing slash) in `execute_searches`.

2. **`execute_searches` home.** Currently placed in `decomposed.py`. If it grows (pagination, retry, per-query result cap as config), it warrants its own `researcher/search.py`. Evaluate at step 4 of implementation order; promote if the function exceeds ~40 lines.

3. **Brave per-query `max_results`.** `_search_brave` hardcodes `max_results=8`. With the decomposed path this becomes the only control on candidates-per-query. Should it be a `VerifyConfig` field, or is 8 a safe fixed constant? Decide before wiring `execute_searches`.

4. **Semaphore scope for `onboard_entity`.** The plan says one shared semaphore across all templates. Confirm with the `onboard-parallelize-templates.md` implementation that `onboard_entity` is the correct creation site, and that `verify_claim` receives `sem` as an optional kwarg (defaulting to `asyncio.Semaphore(cfg.llm_concurrency)` when None, for single-claim callers that don't pre-create it).

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-04-27 | agent (claude-sonnet-4-6) | initial | First draft |
| 2026-04-27 | operator | revision | Removed refinement loop and quality threshold; `max_initial_queries` is the sole effort lever; added tool-free-by-design section |
| 2026-04-27 | agent (claude-opus-4-7) | architect review | Fixed semaphore plumbing (int on config, Semaphore at call site, explicit kwarg threading); clarified scorer does not apply max_sources cap (orchestrator does); committed to exact-string dedup for v1; added belt-and-suspenders max_initial_queries enforcement (prompt + hard truncation); added Open Questions section; added Implementation order section; spelled out _ingest_one/_ingest_urls signature changes |
| 2026-04-27 | operator | revision | Classic path reframed as temporary validation scaffolding with defined removal condition; `researcher_mode` marked for deletion post-validation; removal step added to implementation order |
