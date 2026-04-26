# API provider evaluation — final report

Date: 2026-04-26
Scope: provider evaluation spike. No project changes; no reusable code shipped. Goal was to determine which non-Anthropic providers and models can handle the LLM call shapes used by the `dr` pipeline (researcher / analyst / auditor / ingestor). Findings feed [`docs/plans/multi-provider.md`](../plans/multi-provider.md).

## Bottom line

**GreenPT is the better provider for this pipeline today.** Three of five GreenPT models pass every test cleanly with no client-side workarounds; only one of four working Infomaniak models matches that bar. GreenPT also exposes per-call energy telemetry (TreadLightly brand fit) and a hosted Scraper API that can replace the ingestor's `web_fetch` tool. Top picks: **`green-l-raw` for analyst/auditor**, **`gpt-oss-120b` (either provider) for researcher/ingestor**.

`gemma3n` on Infomaniak is currently broken at the gateway (HTTP 502 with empty body, ~58ms internal time) despite being advertised by `/v1/models`. A support ticket has been drafted locally with two recent failed `x-request-id`s for Infomaniak to look up.

## Test rubric

Five test types per model, mirroring real `dr` pipeline call shapes:

| Test | What it checks | DR pipeline analogue |
|---|---|---|
| T1 | plain completion (HTTP 200, non-empty content) | sanity |
| T2 | structured JSON output | analyst / auditor |
| T3 | tool definition acceptance (no schema rejection) | researcher / ingestor pre-flight |
| T4 | single-turn tool call emission | researcher / ingestor (call out) |
| T5 | multi-turn tool result handling (raw + stripped) | researcher / ingestor (loop close) |

T5 was tested both raw (echo assistant turn verbatim) and stripped (remove emitted-but-not-accepted fields like `reasoning_content`).

## Per-provider, per-model results

### Infomaniak

| Model | T1 | T2 | T3 | T4 | T5-raw | T5-stripped | T4 latency | Verdict |
|---|---|---|---|---|---|---|---|---|
| `gemma3n` | BLK | BLK | BLK | BLK | BLK | BLK | n/a | **gateway 502** — see ticket |
| `mistral24b` | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | 1.10s | usable with `reasoning_content` strip |
| `swiss-ai/Apertus-70B-Instruct-2509` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | 0.83s | single-turn only (server-side template crash on tool replay) |
| `openai/gpt-oss-120b` | ✅\* | ✅ | ✅ | ✅ | ✅ | ✅ | 0.49s | **clean across the board** |

\* `gpt-oss-120b` T1 needs `max_tokens >= ~50`; chain-of-thought consumes the budget.

### GreenPT

| Model | Tier | T1 | T2 | T3 | T4 | T5-raw | T5-stripped | T4 latency | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `mistral-small-3.2-24b-instruct-2506` | router | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 0.39s | clean |
| `gemma-3-27b-it` | router | ✅ | ✅ | ✅ | ✅ | ⚠ | ⚠ | 0.84s | single-turn only (re-emits tool call as plain text, ignores result) |
| `gpt-oss-120b` | router | ✅ | ✅ | ✅ | ✅ | ✅ | n/r | 0.51s | clean |
| `green-l-raw` | direct | ✅ | ✅ | ✅ | ✅ | ✅ | n/r | 0.43s | **clean, lowest latency, lowest energy** |
| `green-r-raw` | direct | ✅ | ✅ | ✅ | ❌ | BLK | BLK | 0.53s | T4 fails — no harmony tool-call adapter |

`green-l-raw` is wire-equivalent to `mistral-small-3.2-24b-instruct-2506` (same tool-call id format, same content for shared prompts). `green-r-raw` appears to be `gpt-oss-120b` without the harmony adapter.

### GreenPT Scraper API (separate endpoint)

`POST /v1/tools/crawl/scrape` returns clean markdown + metadata (title, source URL, status code, content type, OG tags). Tested on `anthropic.com/news`: 200 OK in 6.0s, 3,869 chars of clean markdown. **Verdict:** viable as `web_fetch` substitute; ~3x slower than hand-rolled `httpx + markdownify`; no `fetched_at`; no energy `impact` field. Best as fallback for SPA / JS-heavy sources.

## Pipeline-role recommendations

| DR agent | Call shape | Top pick | Fallback | Skip |
|---|---|---|---|---|
| analyst | single-turn structured | GreenPT `green-l-raw` | Infomaniak `mistral24b` or `gpt-oss-120b` | gemma3n, green-r-raw |
| auditor | single-turn structured | GreenPT `green-l-raw` | Infomaniak `gpt-oss-120b` | gemma3n, green-r-raw |
| researcher | multi-turn `web_search` | GreenPT `gpt-oss-120b` or `green-l-raw` | Infomaniak `gpt-oss-120b` | gemma-3-27b-it, apertus70b, green-r-raw |
| ingestor | multi-turn `web_fetch` + `wayback_check` | GreenPT `gpt-oss-120b` (or GreenPT Scraper API to replace the tool entirely) | Infomaniak `gpt-oss-120b` | apertus70b, gemma-* |

## Key non-obvious findings

1. **Same weights, different gateway.** Mistral-Small-3.2-24b passes T5-raw on GreenPT and fails T5-raw on Infomaniak. The BUG-082 issue parallax-ai documented is gateway-specific, not weights-specific. Infomaniak emits `reasoning_content` and rejects it on input; GreenPT does not have that asymmetry.
2. **`gpt-oss-120b` is the universal winner.** T5-clean on both providers; sub-second latency. Caveat: chain-of-thought needs `max_tokens >= ~50` or completions silently truncate.
3. **Apertus-70B has a server-side bug.** All sanitization variants returned a Python `TypeError` from Infomaniak's vLLM chat-template renderer. No client-side fix.
4. **GreenPT energy telemetry differs router-vs-direct by 2.2x on identical prompts.** Unexplained. If energy claims become user-facing, this needs investigation.
5. **GreenPT Scraper API** is viable for `web_fetch` but ~3x slower; best as fallback for SPA / JS-heavy sources.

## Open item: `gemma3n` 502 on Infomaniak

`gemma3n` returns HTTP 502 with empty body for product 107457 across every variant tried (default v2, v1 endpoint, minimal payload, larger `max_tokens`, streaming, 60-second cooldown, multiple HF-style slugs). The same account on the same minute returns 200 OK for `google/gemma-4-31B-it` (sibling control), so authentication, payload shape, and routing are healthy. The `/v1/models` endpoint lists `gemma3n` as available, but `/chat/completions` cannot route it. Internal `x-query-time: ~58ms` indicates the gateway fast-fails before reaching inference.

**Status:** support ticket drafted locally; two failed `x-request-id`s captured for Infomaniak to look up (both 2026-04-26 11:01:15 UTC). Awaiting send.

**Pipeline impact:** none. Working Infomaniak alternatives (`mistral24b`, `gpt-oss-120b`) cover the small/large slots; `gemma3n` was a nice-to-have, not a critical-path model.

## Plan implications (for `docs/plans/multi-provider.md`)

- The "no adapter layer" non-goal needs to relax. Different models on the same provider need different serialization (mistral24b on Infomaniak needs `reasoning_content` stripped; gpt-oss-120b benefits from preserving it). At minimum a thin per-model serialization scrubber is required.
- BUG-082 risk treatment can be downgraded. Tool calling is not blanket-broken on non-Anthropic providers — it's gateway-specific. Three T5-clean models exist across the two providers tested.
- The plan's `mistral24b` (small) + `gpt-oss-120b` (large) Infomaniak-only direction should be revisited in light of GreenPT's energy telemetry, scraper API, and cleaner tool-loop behavior. A combined GreenPT-primary + Infomaniak-failover strategy may better fit the TreadLightly brand.
- Apertus-70B should not be used in a multi-turn role until Infomaniak fixes its chat template.

## What's NOT in scope of this POC

- PydanticAI integration: confirm `OpenAIProvider` does not re-emit `reasoning_content` on outbound assistant messages, and that tool-call ids without `call_` prefix do not break PydanticAI validation.
- Pricing per-token; rate-limit characterization (POC volume was tiny).
- Scraper behavior on 4xx / 5xx / PDFs / rate-limited sources.
- Investigation of GreenPT router-vs-direct 2.2x energy delta.
- Real `dr verify` end-to-end run against any chosen model.

## Artifacts

Raw evidence (per-model results, per-provider rollups, gemma3n trace, the Infomaniak support ticket draft, and probe scripts) lives in `scripts/poc-multi-provider/` on the operator's machine. That directory is **gitignored** (api keys + ad-hoc scripts) and not part of this published report; ask Brandon if you need to inspect a specific run.

No tracked project files were modified by the spike itself. Only change in tracked git from the spike: one block added to `.gitignore` for the scratch directory.
