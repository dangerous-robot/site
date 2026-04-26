# Plan: Multi-provider support (Infomaniak first, GreenPT considered)

Phased plan to run the `dr` pipeline against non-Anthropic providers. The pure POC framing has been retired -- the [API provider evaluation report](../reports/API-PROVIDER-FINAL-REPORT.md) (2026-04-26) supplied the empirical groundwork; this plan now lays out shippable parts.

**Primary motivation:** Infomaniak's data centres reuse waste heat to warm Swiss buildings, which aligns directly with TreadLightly's environmental-transparency brand. That's why Infomaniak leads in Part 1 even though the GreenPT path scored marginally cleaner on raw test results.

## Goal

Enable per-agent and per-provider model selection on the `dr` pipeline so that all four agents (`researcher`, `analyst`, `auditor`, `ingestor`) can be pointed at non-Anthropic providers via the existing `--model` flag / `DR_MODEL` env. Build it in shippable slices: a single Infomaniak model in v1, then per-agent model preference, then global fallback and a second provider.

## Non-goals (revised post-evaluation)

- **No new config layer in v1.** Plain env vars and the existing `--model` flag remain the only knobs through Part 2. A `pipeline/common/providers.py` registry only appears once Part 3 lands.
- **No energy or cost tracking.** Out of scope for every part in this plan.
- **No Apertus-70B.** The evaluation found a server-side `TypeError` in Infomaniak's vLLM chat-template renderer; reconsider only after Infomaniak fixes it.
- **No prompt re-tuning per provider in Part 1.** Test portability first; tune `pipeline/*/instructions.md` only if drift on the analyst/auditor outputs becomes load-bearing.

(Removed from non-goals: "no adapter/serialization layer." See Part 2 -- a thin per-model serialization scrubber is now required, not deferred. Justification in the report's "Plan implications" section.)

## GreenPT consideration (deferred to Part 3, not abandoned)

The evaluation found GreenPT cleaner on tool-loop tests (3-of-5 models pass T5 vs 1-of-4 on Infomaniak), faster, and equipped with two relevant bonuses: per-call energy telemetry and a hosted Scraper API that could replace `web_fetch`. It is a strong candidate for Part 3's second provider. Two open questions before promoting it:

1. The unexplained 2.2x energy delta between GreenPT's router and direct endpoints on identical prompts. Without a reason, energy telemetry is not yet trustworthy enough to surface.
2. Whether GreenPT's Swiss/EU posture matches Infomaniak's heat-reuse story closely enough that operating two providers buys us anything beyond redundancy.

## Part 1 -- v1 release: switch to Infomaniak `gpt-oss-120b`

### Objective

Ship a `dr verify` end-to-end run against `infomaniak:openai/gpt-oss-120b` for all four agents on at least one canned claim, producing a written `.audit.yaml` sidecar. This is a **v0.1.0 release item**; tracked from [`v0.1.0-roadmap.md`](v0.1.0-roadmap.md).

The model choice changed from the original POC plan (`mistral24b`) to `gpt-oss-120b` because the evaluation showed it is the only Infomaniak model that passes every test cleanly, including the multi-turn tool loop (T5) that the researcher and ingestor agents depend on. Mistral-Small needed a `reasoning_content` strip to pass T5; that complication moves into Part 2.

### Acceptance bar

The release ships when Brandon can run **one** live `dr verify` against one canned claim where all four agents (`researcher`, `analyst`, `auditor`, `ingestor`) execute in sequence against Infomaniak-hosted `gpt-oss-120b` and the run terminates with a written `.audit.yaml` sidecar.

- Output quality does not need to match Claude. Terser reasoning, looser citations, and `needs_review` verdicts are acceptable.
- Imperfect tool use is acceptable **if** the pipeline visibly attempts the tool, logs the failure, and continues.
- **Caveat:** `gpt-oss-120b` T1 silently truncates if `max_tokens < ~50` because chain-of-thought consumes the budget. PydanticAI defaults are likely fine, but verify on first run and bump if needed.

### Recommended demo claim

`research/claims/claude/renewable-energy-hosting.md` -- `status: draft`, has a 2026-04-25 Claude-Haiku audit sidecar for drift comparison, on-topic for TreadLightly. It currently has only two ingested sources, so `dr reassess` against it exercises analyst + auditor on a thin evidence base. If a richer reassess fallback is wanted at run time, any of these four-source `claude/` drafts can stand in (each has a Claude-Haiku audit sidecar): `excludes-frontier-models`, `excludes-image-generation`, `no-training-on-user-data`, `realtime-energy-display`.

### Code paths that change

One new helper file plus one import per `.override(...)` site. No agent file is modified.

| File | Change |
|---|---|
| `pipeline/common/models.py` | Add `resolve_model(spec: str) -> Model | str` helper. For `infomaniak:...` build `OpenAIModel(...)` + `OpenAIProvider(base_url=..., api_key=...)`. For `anthropic:...` and any unprefixed string, return the spec unchanged so PydanticAI's native string handling continues to work. Keep `DEFAULT_MODEL` as-is. |
| `pipeline/orchestrator/pipeline.py` | At each of the four `.override(model=cfg.model)` sites (`pipeline.py:183`, `:253`, `:313`, `:342`), replace `cfg.model` with `resolve_model(cfg.model)`. `VerifyConfig.model` stays `str`. |
| `pipeline/orchestrator/cli.py` | At the `auditor_agent.override(model=model)` site (`cli.py:293`) and the `ingestor_agent.override(model=model)` site (`cli.py:369`), same substitution. |
| `.env.example` / README snippet | Document `INFOMANIAK_API_KEY`, `INFOMANIAK_PRODUCT_ID`, `INFOMANIAK_API_VERSION` (default `2`). The repo currently has no `.env.example`; create one as part of this work. |

Illustrative wiring (sketch, not final):

```python
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

def resolve_model(spec: str) -> Model | str:
    if spec.startswith("infomaniak:"):
        model_id = spec.split(":", 1)[1]
        try:
            pid = os.environ["INFOMANIAK_PRODUCT_ID"]
            api_key = os.environ["INFOMANIAK_API_KEY"]
        except KeyError as e:
            raise RuntimeError(f"Infomaniak provider requires {e.args[0]}") from e
        ver = os.environ.get("INFOMANIAK_API_VERSION", "2")
        base = f"https://api.infomaniak.com/{ver}/ai/{pid}/openai/v1"
        return OpenAIModel(model_id, provider=OpenAIProvider(base_url=base, api_key=api_key))
    return spec  # anthropic:..., bare strings, etc. -- PydanticAI handles natively
```

The base URL `.../openai/v1` (without `/chat/completions`) was confirmed against Infomaniak during the evaluation; PydanticAI's `OpenAIProvider` appends the suffix. PydanticAI 1.84.1's `OpenAIProvider.__init__` signature is `(base_url=None, api_key=None, openai_client=None, http_client=None)`, so the kwargs above are stable for the installed version.

### API-key enforcement

`cli.py` enforces `ANTHROPIC_API_KEY` at four sites (`verify` 113, `research` 146, `ingest` 334, `onboard` 460). Site 334 already has the right shape: `if not os.environ.get("ANTHROPIC_API_KEY") and "test" not in ctx.obj["model"]`. Generalize that pattern across all four sites, keyed on the **resolved** model (`ctx.obj["model"]`, which already reflects `--model` or `DR_MODEL`):

- `infomaniak:...` -> require `INFOMANIAK_API_KEY` and `INFOMANIAK_PRODUCT_ID` (gate both, so `resolve_model` never raises `KeyError` deep in the call stack).
- `anthropic:...` or unprefixed -> require `ANTHROPIC_API_KEY` (current behavior).
- contains `"test"` -> skip the check (current behavior, used by `TestModel` paths).

`BRAVE_WEB_SEARCH_API_KEY` is unrelated to provider selection and stays mandatory for `dr research` regardless of model spec.

### Validation runs

`--model` is a group-level option on the `dr` CLI (`cli.py:22`), so it must precede the subcommand or be provided via `DR_MODEL`. The commands below assume `export DR_MODEL=infomaniak:openai/gpt-oss-120b` for brevity; the explicit form is `dr --model infomaniak:openai/gpt-oss-120b <subcommand> ...`.

| Step | Command | Pass criterion |
|---|---|---|
| 1 | `dr ingest <known-good URL>` | Tool use works (`web_fetch`); valid `SourceFile` parsed; file written. |
| 2 | `dr verify "Ecosia" "<claim text>"` | Tool use works on researcher (`web_search`) and ingestor (`web_fetch`); analyst + auditor produce valid `AnalystOutput` / `IndependentAssessment`; `.audit.yaml` sidecar written. |
| 3 | `dr reassess --claim claude/renewable-energy-hosting` | Auditor returns structured output; no empty responses. |

If Step 1 emits `max_tokens` truncation, raise the cap at the agent definition site rather than at the call site; this is a model property, not a per-call concern.

**Rollback:** If `gpt-oss-120b` fails the acceptance bar mid-run (e.g., a regression on Infomaniak's gateway, or PydanticAI's `OpenAIProvider` shape changes), unset `DR_MODEL` to fall back to `DEFAULT_MODEL` (Claude Haiku). The Anthropic path is untouched by Part 1, so reverting is environment-only.

## Part 2 -- two Infomaniak models, per-agent preference

### Objective

Add `infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` as a second supported model and let each agent pick its own model independently. Mistral-Small is the small/cheap tier; `gpt-oss-120b` is the large/robust tier.

### Required: per-model serialization scrubber

The evaluation found that even within a single Infomaniak account the two models have asymmetric serialization needs:

- `mistral24b` emits `reasoning_content` on assistant turns and rejects it on input. The T5-raw test fails; T5-stripped passes. We must strip `reasoning_content` from assistant messages before sending them back as history.
- `gpt-oss-120b` benefits from preserving `reasoning_content`; stripping it is harmless but not required.

This is a per-model concern, not a per-provider concern. The original "no adapter layer" non-goal cannot survive Part 2 -- a thin scrubber is required on day one. Likely shape: a small dispatch table in `pipeline/common/models.py` keyed on the model id, applied via PydanticAI's request-modification hook or a custom `OpenAIModel` subclass. Keep it under ~30 lines and tested in isolation; this is not a "service layer," just a sanitizer.

### Per-agent model preference

`VerifyConfig` currently holds a single `model: str`. Extend minimally with overrides that default to `None`:

```python
@dataclass
class VerifyConfig:
    model: str = DEFAULT_MODEL
    researcher_model: str | None = None   # falls back to model
    analyst_model: str | None = None
    auditor_model: str | None = None
    ingestor_model: str | None = None
```

Each `_research` / `_ingest_one` / `_analyse_claim` / `_audit_claim` helper in `pipeline/orchestrator/pipeline.py` reads its own field, falling back to `cfg.model`. CLI wiring: per-agent env vars with `DR_MODEL` fallback.

- `DR_RESEARCHER_MODEL`, `DR_ANALYST_MODEL`, `DR_AUDITOR_MODEL`, `DR_INGESTOR_MODEL` (each optional)
- `DR_MODEL` (existing) remains the baseline.

Four discrete env vars are trivially greppable, avoid the parsing burden of a single map-string, and keep the CLI surface identical. Collapse to a map later only if the env-var list bloats.

### Recommended target mapping (revisit before locking)

| Agent | Tier | Model string |
|---|---|---|
| researcher | large | `infomaniak:openai/gpt-oss-120b` |
| analyst | large | `infomaniak:openai/gpt-oss-120b` |
| auditor | small | `infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` |
| ingestor | small | `infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` |

Rationale: tool-using agents (researcher, ingestor multi-turn) get the more robust model; structured-output-only agents (auditor) can use the cheaper one. Ingestor sits in the small column despite using tools because its tool loop is shorter and Mistral-Small handles single-turn tool calls cleanly.

### Part 2 gate

Same tool-use / structured-output validation as Part 1, but against Mistral-Small as well, plus a mixed-tier `dr verify` run confirming all four agents cooperate across the two models.

## Part 3 -- global fallback + multiple providers

### Objective

Add a second provider (likely GreenPT) and a fallback policy so a transient outage on one provider does not block a `dr verify` run. This is where the "no config layer" non-goal finally relaxes.

### Likely shape (sketch only -- design when Part 2 is shipped)

- New `pipeline/common/providers.py` with a small registry: provider id -> base URL + env-var names + per-model scrubber map.
- New model-spec syntax for fallback chains: `infomaniak:openai/gpt-oss-120b||greenpt:gpt-oss-120b`. The resolver tries the first; on connect/HTTP error it tries the next.
- GreenPT base URL + auth wired into the registry.
- Optional: surface GreenPT's Scraper API as an alternate `web_fetch` implementation, gated by an env var. Decide based on whether `httpx + markdownify` is hitting failure modes the Scraper would handle better.
- Energy telemetry from GreenPT remains shelved until the router/direct 2.2x delta is explained.

### Open questions for Part 3

1. Fallback granularity: per-call (every single LLM hit retries through the chain) vs per-run (one provider per `dr verify`, decided at start). Per-call is more resilient; per-run is cheaper to reason about.
2. Whether GreenPT's `green-l-raw` (cleanest single model in the evaluation) or `gpt-oss-120b` (cross-provider portability) leads on GreenPT.

## Risks (revised)

### Tool-use risk: downgraded from critical

**The pre-evaluation framing of BUG-082 as "tool calling broken on non-Anthropic providers" was too strong.** The evaluation showed the failure is **gateway-specific, not weights-specific** -- Mistral-Small-3.2 passes the multi-turn tool test (T5-raw) on GreenPT and fails it on Infomaniak. Three T5-clean models exist across the two providers tested (`gpt-oss-120b` on both, `green-l-raw` on GreenPT, `mistral24b` on Infomaniak with the scrubber). For Part 1's chosen model (`gpt-oss-120b` on Infomaniak), tool calling works cleanly with no client-side workaround.

**Residual risk for Part 2:** Mistral-Small needs the `reasoning_content` scrubber. If the scrubber regresses (e.g., a future PydanticAI version starts forwarding the field again), the ingestor agent could go silent. Mitigation: add a smoke test that runs a multi-turn tool exchange against `mistral24b` and asserts non-empty content.

### Other risks

- **Anthropic-specific prompt drift.** Analyst/auditor instructions in `pipeline/analyst/instructions.md` and `pipeline/auditor/instructions.md` were tuned against Claude. Mistral and `gpt-oss-120b` may be terser or looser about Pydantic schema adherence. PydanticAI's `retries=2` should soak up minor drift; larger drift would show up as `needs_review` disagreement-rate spikes.
- **Context limits.** Mistral-Small is 128K tokens; `gpt-oss-120b` is in the same ballpark. Unlikely to overflow on current claims but worth noting if `--max-sources` is expanded.
- **`gemma3n` Infomaniak gateway 502.** Documented in the evaluation report; not on the critical path because we are not using `gemma3n`. Support ticket drafted.
- **Brave Search coupling.** `BRAVE_WEB_SEARCH_API_KEY` remains required for `dr research` regardless of provider. Quota exhaustion mid-run surfaces as a researcher tool error and is not provider-related.
- **Infomaniak account/billing.** The evaluation used Brandon's account at low volume. A single `dr verify` run is well below any plausible rate limit, but production-cadence reassess loops would need a billing/quota check before scaling.
- **`.env` loading.** `cli.py` calls `load_dotenv()` at import (line 14), so `INFOMANIAK_*` vars in `.env` are picked up automatically. Shell-exported vars override `.env` per python-dotenv defaults; mismatched values between the two are a possible foot-gun on a developer machine.

## Resolved questions

- **POC purpose (Q1).** Demo-able end-to-end against one canned claim. Closed by the evaluation report. (2026-04-23)
- **Credentials (Q2).** Infomaniak API key + product ID available; Mistral-Small and `gpt-oss-120b` both enabled. (2026-04-23)
- **Demo claim (Q3).** `research/claims/claude/renewable-energy-hosting.md`. (2026-04-23, path corrected 2026-04-26 -- the original `chatgpt/...` path never existed in the repo)
- **Per-agent selector shape (Q4).** Four per-agent env vars with `DR_MODEL` fallback. (2026-04-23)
- **Base URL shape (Q5).** `.../openai/v1`; confirmed during evaluation. (2026-04-26)
- **Part 1 model choice.** `gpt-oss-120b`, not `mistral24b` -- the only Infomaniak model that passes T5 raw. Mistral-Small is deferred to Part 2 once the scrubber lands. (2026-04-26)
- **Provider order.** Infomaniak first because of waste-heat reuse alignment with TreadLightly's brand, despite GreenPT's marginally cleaner test results. (2026-04-26)

## Open questions

1. **Disagreement-rate baseline.** Before Part 2 we should capture the current Claude-Haiku disagreement rate from existing `.audit.yaml` sidecars so we have a comparison number for the Infomaniak models' analyst/auditor drift. Short spike, not a Part 1 blocker.
2. **GreenPT 2.2x router/direct energy delta.** Needs investigation before energy telemetry can be surfaced. Blocks any user-facing energy claim derived from GreenPT.
3. **Part 3 fallback granularity.** Per-call vs per-run; design when Part 2 ships.

## Critical files

- `pipeline/common/models.py` -- add `resolve_model()` helper (Part 1); add per-model scrubber map (Part 2)
- `pipeline/orchestrator/pipeline.py` -- update four `.override(model=...)` sites; add per-agent fields to `VerifyConfig` (Part 2)
- `pipeline/orchestrator/cli.py` -- update two `.override(model=...)` sites; soften API-key check; wire per-agent env vars (Part 2)
- `pipeline/researcher/agent.py` -- no change in Part 1; smoke-test target for Part 2 scrubber
- `pipeline/ingestor/agent.py` -- no change in Part 1; smoke-test target for Part 2 scrubber
- `pipeline/analyst/agent.py` -- no change
- `pipeline/auditor/agent.py` -- no change
- `pipeline/common/providers.py` -- new file in Part 3

## References

- [`docs/reports/API-PROVIDER-FINAL-REPORT.md`](../reports/API-PROVIDER-FINAL-REPORT.md) -- 2026-04-26 evaluation: per-model results, GreenPT vs Infomaniak, BUG-082 reframing
- `parallax-ai/backend/app/services/llm/_infomaniak.py` -- prior-art quirk workarounds (role alternation, markdown sanitization); kept as a reference, not a dependency
- `parallax-ai/backend/app/config/model_registry.py` -- `supports_tools=False` registry entries (now known to be over-broad; see report)
- `parallax-ai/docs/BUGS.md` -- BUG-080 (gemma3n), BUG-082 (tool history), BUG-083 (role artifact leaks); BUG-082 risk treatment is downgraded by the evaluation

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-23 | agent (opus-4-7) | draft, implementation-referenced | Initial draft. File/line references verified against pipeline source. Tool-use risk grounded in parallax-ai BUG-082/083 and `supports_tools=False` registry entries. |
| 2026-04-23 | agent (opus-4-7) | user-answers pass | Resolved Q1 (acceptance bar with fallback), Q2 (creds), proposed Q3 (demo claim), Q4 (per-agent env vars), Q5 (curl probe moved to Phase 1 first task). |
| 2026-04-26 | agent (opus-4-7) | post-evaluation rewrite | POC framing retired; replaced with three shippable parts (Part 1 = v1; Part 2 = per-agent + scrubber; Part 3 = fallback + multi-provider). Part 1 model switched from `mistral24b` to `gpt-oss-120b` per evaluation. BUG-082 risk downgraded from critical to "Mistral-Small needs scrubber" (Part 2). "No adapter layer" non-goal removed; per-model serialization scrubber required in Part 2. GreenPT consideration added with deferral rationale (2.2x energy delta unexplained). Provider order locked to Infomaniak-first on waste-heat brand alignment. References evaluation report at `docs/reports/API-PROVIDER-FINAL-REPORT.md`. |
| 2026-04-26 | agent (opus-4-7) | Part 1 review pass, implementation | Verified all Part 1 file/line references against pipeline source. Corrected line numbers: `pipeline.py` 182/252/312/341 -> 183/253/313/342; `cli.py` 367 -> 369 and 291 -> 293. Demo claim path corrected: `chatgpt/renewable-energy-hosting.md` (does not exist) -> `claude/renewable-energy-hosting.md`; flagged that it has 2 sources rather than the 4 originally claimed and surfaced the choice as a Brandon question. Validation-runs commands corrected: `--model` is a group-level Click option and must precede the subcommand or be set via `DR_MODEL`. API-key enforcement section expanded: four `ANTHROPIC_API_KEY` sites (113, 146, 334, 460), generalize the existing `"test" not in ctx.obj["model"]` exemption at site 334, gate on the resolved model and require `INFOMANIAK_PRODUCT_ID` alongside `INFOMANIAK_API_KEY`. `resolve_model` sketch given a return annotation, friendly `KeyError` handling, and an explicit pass-through note for `anthropic:...`. Added rollback note (unset `DR_MODEL`). Added Infomaniak account/billing risk and a `.env` loading note (cli.py already calls `load_dotenv()` at line 14). Flagged unverified PydanticAI `OpenAIProvider` API shape as a Brandon question. |
