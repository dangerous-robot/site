# Source Pool Expansion — Tier 1 — Search Backend (Tavily)

**Status**: Done. Tavily backend landed 2026-05-08 in commit `ac2dfac` behind `RESEARCH_SEARCH_BACKEND=tavily`; default flipped to `tavily` in `653f5b6` after one operator-validated cycle. The frozen-replay harness was deferred — Brave-vs-Tavily decision was made operationally on the first validation run rather than via the rubric (the candidate-pool quality and 0-rate-limit-error result was unambiguous). Follow-on prefetch passthrough at [`ingestor-tavily-prefetch.md`](ingestor-tavily-prefetch.md) lands the `raw_content` short-circuit. Brave remains available behind the flag.
**Family**: `source-pool-expansion-tier1` — companion to [`source-pool-expansion-tier1.md`](../source-pool-expansion-tier1.md).
**Created**: 2026-05-08
**Last revised**: 2026-05-08

## Context

Originally Path 4 of [`source-pool-expansion-tier1.md`](../source-pool-expansion-tier1.md). Split into its own plan because:

1. The evaluation methodology (frozen-replay harness, decision rubric) is search-backend-specific and not reusable by Tier 1's Paths 1–3.
2. Tavily is now the only candidate (Exa deferred per operator decision 2026-05-08), simplifying a 2-way bake-off into a Tavily-vs-Brave comparison.
3. Bundling held Paths 1–3 hostage to evaluation work they don't need.

The shared infrastructure this work originally forced (throttle layer, URL canonicalizer, audit-trail `acquisition` slot, error-type vocabulary) lives in [`source-pool-expansion-tier1.md`](../source-pool-expansion-tier1.md) § Shared infrastructure as the prerequisite for all paths.

## Problem

Brave's general-web ranking mixes vendor-sponsored content, content farms, and stale aggregator pages into the candidate list. The host blocklist ([`researcher-host-blocklist.md`](researcher-host-blocklist.md)) drops the worst offenders but doesn't change ranking quality or add surface area.

Tavily delivers cached/extracted content alongside URLs, which sidesteps some paywalls and reduces fetch failures on returned URLs. Hypothesis: an agent-optimized search returns a better candidate pool with fewer wasted fetches.

## Goal

Add Tavily as a selectable search backend in `pipeline/researcher/decomposed.py:execute_searches`, gate behind `RESEARCH_SEARCH_BACKEND` env var (default `brave`), and use a frozen-claim replay to decide whether to flip the default to `tavily`. Brave stays available as a fallback regardless of the outcome.

## Prerequisites

Depends on `source-pool-expansion-tier1.md` § Schema prerequisites and § Shared infrastructure landing first:

- `audit.acquisition` field in `src/content.config.ts` and `pipeline/common/models.py`
- `pipeline/common/throttle.py` — Tavily monthly cap and per-second budget
- `pipeline/common/canonical_url.py` — URL dedup across backends
- error-type vocabulary additions

Does **not** depend on Paths 1–3 of the tier1 plan. Once the prerequisites above are merged, this plan and Paths 1–3 can all run in parallel.

## Implementation

**Swap point**: `pipeline/researcher/decomposed.py:53` (`execute_searches`). Currently fans `search_brave(client, q)` calls in parallel via `asyncio.gather`. The swap routes each per-query call through a small backend dispatcher driven by `RESEARCH_SEARCH_BACKEND`.

**New tool function**: `pipeline/researcher/tools/tavily.py`. Calls Tavily's `/search` endpoint, normalizes the response into the existing `SearchCandidate` shape (mapping Tavily's pre-extracted `content` into the candidate's content field), and emits one `acquisition: {path: "tavily", query}` entry per kept URL.

**Auth**: `TAVILY_API_KEY` env var. The Tavily path aborts (logged, falls back to Brave for that query) if unset.

**Data-handling note**: claim text and entity names are sent to Tavily on each query. The published research is already public, but verify Tavily's retention/reuse posture before flipping the default. Document under `AGENTS.md` § Tooling.

## Evaluation

**Decision rubric** (2 metrics + 1 gate, simplified from the original 4):

1. **Pool-level coverage vs Brave baseline**: Tavily's kept-source share (post-blocklist, post-scorer) at least matches Brave's on the frozen-replay set. Tavily's pre-extracted content counts as fetch success, so this single metric subsumes the original "independence ratio" and "fetch success" criteria.
2. **Verdict stability**: on the frozen-replay set, no swing in `verification_level` distribution beyond the noise floor.
3. **Cost gate** (pass/fail): under $50/mo at current claim throughput. Tavily's free research tier should pass; failure flips the decision regardless of metrics 1–2.

**Noise floor** definition: re-run the frozen-replay harness over Brave twice with different seeds, measure the inter-run delta in `verification_level` distribution per claim. The noise floor is the 95th-percentile of that delta. Compute and record once before the comparison; reuse across the run.

### Frozen-claim replay harness

New helper at `pipeline/tests/replay/__init__.py`.

**Interface**:

- **Input**: `claims.jsonl` (one claim per line: `{slug, text, criterion, entity}`) + `seed: int` + `backend: "brave" | "tavily"`.
- **Behavior**: replays the Researcher (only) deterministically over each claim. Records the candidate list and scorer rationale. A second optional pass runs the full pipeline on the kept URLs to capture `verification_level` for the verdict-stability check.
- **Output**: `replay-{backend}-{seed}.jsonl` with one record per claim: `{slug, urls_found, scorer_kept, scorer_dropped, scorer_rationale, verdict?, verification_level?}`.
- **Determinism**: LLM seed fixed. If LLM-tester replay (`completed/llm-tester-refactor.md`) is reusable, it is; otherwise the harness uses recorded fixtures.

**Frozen claim set**: a curated sample of 20–50 claims covering each topic in `src/content.config.ts:238`'s criterion enum. Default sample lives at `pipeline/tests/replay/fixtures/frozen-claims.jsonl`. Revisit size if signal is noisy.

### `dr stats` is a follow-up

The plan originally called for a `dr stats` Click subcommand on `pipeline/orchestrator/cli.py`, deferred during the [`dr-cli-output-cleanup_phase2_completed.md`](dr-cli-output-cleanup_phase2_completed.md) work to avoid merge friction. That cleanup is now complete, so the merge-friction concern is moot — but `dr stats` is still scoped as a separate follow-up plan, because the search-backend evaluation only needs the replay harness's JSONL output (parsed ad-hoc) to apply the rubric. Promote `dr stats` whenever observability becomes the bottleneck.

## Rollout

1. **Day 1**: Land Tavily backend behind `RESEARCH_SEARCH_BACKEND=tavily`, default `brave`. Ship behind the flag-disabled-by-default; one operator-validated cycle on at least 5 claims.
2. **Day 2–3**: Build the frozen-replay harness; capture Brave-on-Brave noise floor (same backend, two seeds).
3. **Day 4**: Run frozen-replay against Tavily; apply the rubric; write the decision.
4. **Day 5**: If Tavily wins all three checks, flip default to `tavily`. Brave stays available behind the flag. If Tavily fails any check, keep default `brave`, document the failure in this plan's review history, and revisit when Tavily's posture changes.

## Effort

| Item | Days |
|---|---|
| Backend dispatch + Tavily tool | 1 |
| Frozen-replay harness (spec'd) | 2 |
| Evaluation + decision write-up | 1 |
| **Total** | **~4 days** |

Drops 2 days from the original 6-day Path 4 estimate by removing Exa.

## File touches

| File | Change |
|---|---|
| `pipeline/researcher/decomposed.py` | Backend dispatch in `execute_searches`; emit `acquisition: {path, query}` per kept URL. |
| `pipeline/researcher/tools/tavily.py` (new) | Tavily search wrapper. |
| `pipeline/tests/replay/__init__.py` (new) | Frozen-claim replay harness. |
| `pipeline/tests/replay/fixtures/frozen-claims.jsonl` (new) | Curated 20–50 claim sample. |
| `pipeline/orchestrator/pipeline.py` | New `VerifyConfig.search_backend` field if env-var lookup at boundary is preferred over inline `os.environ.get`. |
| `AGENTS.md` § Tooling | Add `RESEARCH_SEARCH_BACKEND`, `TAVILY_API_KEY`; data-handling note. |

Does **not** touch `pipeline/orchestrator/cli.py` — `dr stats` is a separate follow-up plan.

## Out of scope

- **Exa integration.** Deferred. Revisit if Tavily fails the rubric.
- **`dr stats` subcommand.** Tracked as a follow-up plan; not required for the search-backend evaluation.
- **Replacing Brave entirely.** Brave stays as fallback regardless of the decision.
- **Fetch backend swap.** Owned by [`multi-provider.md`](multi-provider.md) § Part 3 (GreenPT Scraper API).

## Open questions

- **Frozen claim set selection.** Default to 20–50 curated claims; revisit if results are noisy or topic coverage is uneven.
- **Tavily monthly-cap behavior on overrun.** When the free tier is exceeded, does the plan abort to Brave per-query, or stop the run? Default: per-query fallback to Brave with a `tavily_rate_limited` error emission.

## Cross-references

- Main Tier 1 plan (Paths 1–3 + shared infrastructure prerequisites): [`source-pool-expansion-tier1.md`](../source-pool-expansion-tier1.md)
- Follow-on prefetch passthrough: [`ingestor-tavily-prefetch.md`](ingestor-tavily-prefetch.md)
- Recently-completed CLI cleanup (cleared the way for a future `dr stats`): [`dr-cli-output-cleanup_phase2_completed.md`](dr-cli-output-cleanup_phase2_completed.md)
- Fetch-backend distinction: [`multi-provider.md`](multi-provider.md) § Part 3
- Researcher internals: [`research-flow.md`](../../architecture/research-flow.md) § 6
- Pipeline configuration: [`research-workflow.md`](../../architecture/research-workflow.md) § Pipeline configuration knobs
- Host blocklist interaction: [`researcher-host-blocklist.md`](researcher-host-blocklist.md)

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-08 | agent (opus-4-7) | implementation, iterated | Split from `source-pool-expansion-tier1.md` § Path 4. Reduced to Tavily-only (Exa deferred). Decision rubric simplified to 2 metrics + 1 gate. Frozen-replay harness interface spec'd. Noise-floor calculation defined. `dr stats` initially deferred behind the (now-completed) `dr-cli-output-cleanup_phase2` plan; reframed as a future follow-up plan since the search-backend evaluation only needs replay-harness JSONL. |
| 2026-05-08 | agent (opus-4-7) | landed + default-flipped | Tavily wrapper shipped in `ac2dfac` (`pipeline/researcher/tools/tavily.py`); `execute_searches` dispatches via new `VerifyConfig.search_backend` field with per-query Brave fallback on Tavily 429/RuntimeError/exception; per-URL `acquisition.origin` records the actual backend used. Made default in `653f5b6` after one operator-validated `dr onboard` cycle on `contributes-to-environmental-causes` (7/7 queries fired, 51 candidates, no rate-limit errors). The frozen-replay harness was deferred — operational evidence on the validation run was unambiguous and the harness work didn't justify the day-2/3 budget. Marking the plan done; if a future regression suspects Tavily quality, the harness can be revived as a separate follow-up. Follow-on prefetch plan (`ingestor-tavily-prefetch.md`) implements the `raw_content` short-circuit Brave doesn't support. |
