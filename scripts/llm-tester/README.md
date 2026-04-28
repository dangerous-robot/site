# llm-tester

Ad-hoc, gitignored, throwaway tester for probing LLM providers and models against the T1-T5 capability matrix used by the `dr` pipeline. See [`docs/plans/multi-provider.md`](../../docs/plans/multi-provider.md) and [`docs/reports/API-PROVIDER-FINAL-REPORT.md`](../../docs/reports/API-PROVIDER-FINAL-REPORT.md) for background.

## Quickstart

```
python tester.py list
python tester.py probe infomaniak openai/gpt-oss-120b
python tester.py probe greenpt mistral-small-3.2-24b-instruct-2506
```

## What T1-T5 mean

- T1: plain completion
- T2: structured JSON output (verdict/reasoning shape)
- T3: tool definition acceptance
- T4: single-turn tool call emission
- T5: multi-turn tool result handling (the BUG-082 zone — critical path for any agent that loops on tool results)

## Known-tested models

| Provider | Model | T1 | T2 | T3 | T4 | T5 | Last tested | Notes |
|---|---|---|---|---|---|---|---|---|
| Infomaniak | gemma3n | ✅ | ✅ | ❌ | ❌ | BLK | 2026-04-28 | alias → google/gemma-3n-E4B-it; tool use not enabled at gateway |
| Infomaniak | mistral24b | ✅ | ✅ | ✅ | ✅ | ❌ | 2026-04-28 | T5 now hard 500 (was fixable ⚠ with reasoning_content strip) |
| Infomaniak | swiss-ai/Apertus-70B-Instruct-2509 | ✅ | ✅ | ✅ | ✅ | ❌ | 2026-04-25 | server-side template crash on T5 |
| Infomaniak | openai/gpt-oss-120b | ✅ | ✅ | ✅ | ✅ | ✅ | 2026-04-28 | chain-of-thought model; requires max_tokens≥200 or T1 burns budget before output |
| Infomaniak | google/gemma-4-31B-it | ✅ | ✅ | ✅ | ✅ | ✅ | 2026-04-27 | clean across all five |
| GreenPT (router) | mistral-small-3.2-24b-instruct-2506 | ✅ | ✅ | ✅ | ✅ | ✅ | 2026-04-25 | |
| GreenPT (router) | gemma-3-27b-it | ✅ | ✅ | ✅ | ✅ | ⚠ | 2026-04-25 | re-emits tool call as plain text |
| GreenPT (router) | gpt-oss-120b | ✅ | ✅ | ✅ | ✅ | ✅ | 2026-04-25 | |
| GreenPT (direct) | green-l-raw | ✅ | ✅ | ✅ | ✅ | ✅ | 2026-04-25 | |
| GreenPT (direct) | green-r-raw | ✅ | ✅ | ✅ | ❌ | BLK | 2026-04-25 | tool-call args leak into content |

`gemma3n`, `mistral24b`, and `openai/gpt-oss-120b` do not appear in the `/models` endpoint as of 2026-04-28 but still respond when called directly — likely ongoing instability rather than permanent removal.

## Adding a new provider

Don't, unless you're prepared to write a new `harness/<name>.py` mirroring the structure of `harness/infomaniak.py` and register it in `tester.py`'s `KNOWN_PROVIDERS`.

## Where results go

stdout JSON. No persistence. Pipe to a temp file if you need to grep:

```
python tester.py probe infomaniak openai/gpt-oss-120b > /tmp/run.json
```

## Env vars

`.env.poc` must contain:

```
INFOMANIAK_API_KEY=...
INFOMANIAK_PRODUCT_ID=...
GREENPT_API_KEY=...
```

## Archive notes

`archive/` holds the original POC artifacts (probe spikes, per-model reports, support ticket, traces). Don't run anything from `archive/` unless you're explicitly reproducing a historical finding.
