# Plan: Multi-provider POC (Infomaniak)

Draft. First phase is a proof-of-concept for running the pipeline against a non-Anthropic provider (Infomaniak) with minimal changes. Per-agent model tiering and a config/service layer are explicitly deferred.

## Goal

Enable runtime provider switching on the `dr` pipeline so that all four agents (`researcher`, `analyst`, `auditor`, `ingestor`) can run against an Infomaniak-hosted OpenAI-compatible model, using the existing `--model` flag / `DR_MODEL` env with a provider-prefixed string. Validate that tool use and structured outputs work end-to-end on a second provider before we commit to per-agent tiering.

## Non-goals

- **No new config layer.** No YAML/TOML file, no settings class, no provider registry.
- **No service/adapter layer.** PydanticAI's native `OpenAIModel` + `OpenAIProvider` is the only seam.
- **No energy or cost tracking.** Out of scope for every phase in this plan.
- **No tiny (Gemma-3n-E4B) or medium (Apertus-70B) models.** Only `small` (Mistral-Small-3.2-24B) and `large` (openai/gpt-oss-120b) are in scope.
- **No Infomaniak quirk workarounds in POC.** Role-alternation merging and the Gemma3n markdown-stripping workaround from parallax-ai are documented as risks; not ported.
- **No changes to instruction files** (`pipeline/*/instructions.md`) in POC. We test portability first; tune prompts only if the portability gate passes.

## Phase 1 -- POC (single model, all four agents)

### Objective

Prove that the existing pipeline can run end-to-end against `infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` on at least one representative `dr verify` run, producing a visible demo artifact.

### Acceptance bar: demo-able end-to-end

The POC ships when Brandon can screen-share **one** live run against one canned claim where all four agents (`researcher`, `analyst`, `auditor`, `ingestor`) visibly execute in sequence against Infomaniak-hosted Mistral-Small, and the run terminates with a written `.audit.yaml` sidecar (even if the verdict is weaker than the Claude baseline).

- Output quality does not need to match Claude. Terser reasoning, looser citations, and `needs_review` verdicts are acceptable.
- Imperfect tool use is acceptable **if** the pipeline visibly attempts the tool, logs the failure, and continues (e.g., researcher returns zero sources but the run doesn't crash).
- **Fallback demo (if tool use is fully broken):** run `dr reassess` on a pre-ingested published claim that already has sources on disk. This exercises `analyst` + `auditor` against Mistral without depending on `web_search` or `web_fetch`, and still demonstrates provider-switching for the two agents that don't use tools. Ingestor + researcher become a separate follow-up.

### Recommended demo claim (proposed -- revisit if needed)

`research/claims/chatgpt/renewable-energy-hosting.md` -- already committed with `status: draft`, has a recent Claude-Haiku audit sidecar (`renewable-energy-hosting.audit.yaml`) for drift comparison, four diverse sources already ingested (so `dr reassess` fallback works), and the subject matter is unambiguously on-topic for TreadLightly. Alternates: `chatgpt/discloses-models-used.md` or `anthropic/publishes-sustainability-report.md` if that claim proves awkward.

Gate for go/no-go beyond the demo bar: tool calls on the researcher and ingestor agents must execute and structured outputs must parse on all four agents if we want to proceed to Phase 2 production use (see "Go/no-go criteria" below). The demo can ship under the fallback path; Phase 2 cannot.

### First task: base-URL probe (do this before any code changes)

Confirm which base-URL path shape Infomaniak accepts. Run both curls with real `$INFOMANIAK_API_KEY` and `$INFOMANIAK_PRODUCT_ID`; whichever returns a 200 with a non-empty body is the shape we pass to `OpenAIProvider(base_url=...)` (drop `/chat/completions` from the winner -- PydanticAI appends it).

Candidate A -- `.../openai/v1` (PydanticAI will append `/chat/completions`):

```sh
curl -sS -X POST \
  "https://api.infomaniak.com/2/ai/$INFOMANIAK_PRODUCT_ID/openai/v1/chat/completions" \
  -H "Authorization: Bearer $INFOMANIAK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mistralai/Mistral-Small-3.2-24B-Instruct-2506","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
```

Candidate B -- full path already includes `/chat/completions` (i.e., Infomaniak does **not** follow the standard OpenAI suffix pattern):

```sh
curl -sS -X POST \
  "https://api.infomaniak.com/2/ai/$INFOMANIAK_PRODUCT_ID/openai/v1/chat/completions/chat/completions" \
  -H "Authorization: Bearer $INFOMANIAK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mistralai/Mistral-Small-3.2-24B-Instruct-2506","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
```

Candidate A is the expected winner (matches parallax-ai's usage). Record the result in the plan's review history; this 30-second step eliminates what was previously an open question.

### Model-string syntax

Extend the existing `--model` flag to accept a provider prefix:

- `anthropic:claude-haiku-4-5-20251001` (current behavior, default, unchanged)
- `infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` (new)
- `infomaniak:openai/gpt-oss-120b` (Phase 2)

The prefix is parsed in a single helper; anything without a recognized prefix falls through to PydanticAI's native string resolution (preserves backward compatibility for `test`, `anthropic:...`, `openai:...`, etc. used in unit tests).

### Code paths that change

One new helper file plus one import per `.override(...)` site. No agent file is modified.

| File | Change |
|---|---|
| `pipeline/common/models.py` | Add `resolve_model(spec: str) -> Model \| str` helper. For `infomaniak:...` build `OpenAIModel(...)` + `OpenAIProvider(base_url=..., api_key=...)`. For anything else, return the string unchanged. Keep `DEFAULT_MODEL` as-is. |
| `pipeline/orchestrator/pipeline.py` | At each of the four `.override(model=cfg.model)` sites (`pipeline.py:182`, `:252`, `:312`, `:341`), replace `cfg.model` with `resolve_model(cfg.model)`. `VerifyConfig.model` stays `str`. |
| `pipeline/orchestrator/cli.py` | At the `ingestor_agent.override(model=model)` site (`cli.py:367`) and the `auditor_agent.override(model=model)` site (`cli.py:291`), same substitution. |
| `.env.example` / README snippet | Document `INFOMANIAK_API_KEY`, `INFOMANIAK_PRODUCT_ID`, `INFOMANIAK_API_VERSION` (default `2`). |

Illustrative wiring (≤10 lines):

```python
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

def resolve_model(spec: str):
    if spec.startswith("infomaniak:"):
        model_id = spec.split(":", 1)[1]
        pid = os.environ["INFOMANIAK_PRODUCT_ID"]
        ver = os.environ.get("INFOMANIAK_API_VERSION", "2")
        base = f"https://api.infomaniak.com/{ver}/ai/{pid}/openai/v1"
        return OpenAIModel(model_id, provider=OpenAIProvider(
            base_url=base, api_key=os.environ["INFOMANIAK_API_KEY"]))
    return spec
```

Note: the Infomaniak base URL in parallax-ai ends at `.../openai/v1/chat/completions`. PydanticAI's `OpenAIProvider` appends `/chat/completions` itself, so we pass `.../openai/v1` as the base URL. Confirmed (or corrected) by the first task of Phase 1 -- the two-candidate curl probe.

### API-key enforcement

`cli.py` currently `sys.exit(2)` if `ANTHROPIC_API_KEY` is missing. For POC we soften these checks: if `--model` starts with `infomaniak:`, require `INFOMANIAK_API_KEY` + `INFOMANIAK_PRODUCT_ID` instead. Keep the default path (`anthropic:...`) requiring `ANTHROPIC_API_KEY`. `BRAVE_WEB_SEARCH_API_KEY` is unrelated to provider selection and stays mandatory for `dr research`.

### Validation runs (go/no-go gate)

Run each of the following against Mistral-Small. Each step's success criterion is on the right.

| Step | Command | Pass criterion |
|---|---|---|
| 1 | `dr ingest <known-good URL> --model infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` | Tool use works (`web_fetch`); valid `SourceFile` parsed; file written. |
| 2 | `dr verify "Ecosia" "<claim text>" --model infomaniak:mistralai/...` | Tool use works on researcher (`web_search`) and ingestor (`web_fetch`); analyst + auditor produce valid `AnalystOutput` / `IndependentAssessment`. |
| 3 | `dr reassess --claim <existing claim> --model infomaniak:mistralai/...` | Auditor returns structured output; no empty responses. |

### Go/no-go criteria

**Proceed to Phase 2 only if ALL of the following hold:**

1. Researcher completes at least one `web_search` tool call per run without empty responses.
2. Ingestor completes `web_fetch` (and optionally `wayback_check`) and returns a parsed `SourceFile` for a representative URL.
3. Analyst and auditor each return structured outputs that pass Pydantic validation on at least 3 distinct claims.
4. No role-alternation errors (`400 Bad Request`) and no empty-body 200 responses more than 1-in-3 runs.

**If any of the above fail**, the POC has hit the risk flagged below. The plan then pivots to one of:

- (a) Try `infomaniak:openai/gpt-oss-120b` first (some evidence suggests larger models are more tool-use robust; unverified on Infomaniak's vLLM deployment -- see risks).
- (b) Port the role-alternation workaround from parallax-ai (`_merge_consecutive_roles`, `_ensure_alternation`) as a custom PydanticAI `HTTPClient` or model subclass -- this breaks the "no adapter" non-goal and should trigger a plan revision, not silent scope creep.
- (c) Abandon Infomaniak for multi-turn/tool-use workloads and scope a different second provider.

## Phase 2 -- per-agent tiering

### Objective

After POC passes, wire researcher/analyst to `large` and auditor/ingestor to `small`. Keep surface area minimal: no new CLI flags, no config file.

### Proposed mechanism

`VerifyConfig` currently holds a single `model: str`. Extend minimally with overrides that default to `None`:

```python
@dataclass
class VerifyConfig:
    model: str = DEFAULT_MODEL
    researcher_model: str | None = None   # fallback to model
    analyst_model: str | None = None
    auditor_model: str | None = None
    ingestor_model: str | None = None
```

Each `_research` / `_ingest_one` / `_analyse_claim` / `_audit_claim` helper in `pipeline/orchestrator/pipeline.py` reads its own field, falling back to `cfg.model`. The CLI supplies these from env vars.

**Recommendation (proposed -- revisit if needed):** per-agent env vars with `DR_MODEL` fallback.

- `DR_RESEARCHER_MODEL`, `DR_ANALYST_MODEL`, `DR_AUDITOR_MODEL`, `DR_INGESTOR_MODEL` (each optional)
- `DR_MODEL` (existing) remains the baseline; any unset per-agent var falls through to it.

Rationale: four discrete env vars are trivially greppable in shell history and CI, avoid the parsing burden of a single `DR_MODEL_MAP=researcher=...,analyst=...` style string, and keep CLI surface identical (no new `click` options). If this bloats we can collapse into a map-string later without breaking anyone.

### Target mapping (final, locked by user)

| Agent | Tier | Model string |
|---|---|---|
| researcher | large | `infomaniak:openai/gpt-oss-120b` |
| analyst | large | `infomaniak:openai/gpt-oss-120b` |
| auditor | small | `infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` |
| ingestor | small | `infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506` |

### Phase 2 gate

Same tool-use / structured-output validation as Phase 1 but against the `large` model, plus a mixed-tier `dr verify` run confirming all four agents cooperate.

## Deferred phases (not detailed)

Listed so future plans can slot in; no commitment here.

- **Phase 3: Config layer.** Move provider + per-agent mapping into a `pipeline/common/providers.py` or YAML file when there are 3+ providers or 3+ environments.
- **Phase 4: Service/adapter layer.** Only if PydanticAI native `OpenAIModel` turns out to be insufficient (e.g., we need Infomaniak quirk workarounds in the POC pivot path, or a second OpenAI-compatible provider has different quirks).
- **Phase 5: Quirk workarounds.** Role alternation merging, Gemma3n markdown sanitization. Port from `parallax-ai/backend/app/services/llm/_infomaniak.py` only if specific models we actually use require it.
- **Phase 6: Additional models.** Gemma-3n-E4B (tiny) for throwaway linting-style calls, Apertus-70B (medium), other providers (GreenPT, OpenAI direct, local Ollama).
- **Phase 7: Energy / cost telemetry.** Explicitly deferred per user decision.

## Risks

### Critical: tool use likely broken on Infomaniak

**This is the POC's single biggest risk.** Evidence from parallax-ai (2026-03-26, Phase 0.42):

- `parallax-ai/docs/BUGS.md` BUG-082 ("Tool history causes empty LLM responses on non-Anthropic providers"): multi-turn `role:"tool"` histories produced HTTP 200 with 0 tokens on both GreenPT and Infomaniak. Resolution was to **revert the OpenAI-compat tool calling architecture entirely** and switch to "search-then-ask" (inject search results into the system prompt instead of using function-calling).
- `parallax-ai/docs/BUGS.md` BUG-083: `role:"tool"` → `role:"user"` flattening produced visible artifacts and role-alternation violations.
- `parallax-ai/backend/app/config/model_registry.py`: **every Infomaniak model is flagged `supports_tools=False`**, including `gemma3n`. GreenPT's Mistral Small 3.2 (`green-l-raw`) and GPT-OSS 120B (`green-r-raw`) are also `supports_tools=False`.
- `parallax-ai/docs/UNSCHEDULED.md`: "Multi-turn tool conversations are unreliable across GreenPT and Infomaniak. Empty responses, role alternation violations, and artifact leaks made the architecture unsuitable for production. Three independent reviews (architecture, security, product) recommended search-then-ask as the interim approach."

**What this means for us:** the researcher and ingestor agents rely on tool calls (`web_search` in `pipeline/researcher/agent.py:42`; `web_fetch` and `wayback_check` in `pipeline/ingestor/agent.py:52, :87`). If the Infomaniak-served Mistral-Small behaves the same way it did in parallax-ai, these two agents will break in Phase 1. The analyst and auditor agents do not use tools (they rely only on structured output via Pydantic), so they are more likely to work.

**Caveats that partially soften the evidence:**

- Parallax-ai tested via their own direct HTTPX adapter, not PydanticAI's `OpenAIModel`. PydanticAI handles tool loops and message sequencing differently; it may emit a cleaner sequence that Infomaniak tolerates.
- The `backend/scripts/spike_tool_calling.py` test (Phase 0.42 start gate) tested tool *definition acceptance* and *tool result acceptance* -- it's worth reading its logged output before Phase 1 to see which specific step failed.
- Infomaniak's vLLM deployment may have been upgraded since March 2026.

**Mitigation:** Phase 1's validation Step 1 (`dr ingest` -- single tool call) is the earliest, cheapest check. If it fails, stop before running `dr verify`. Capture raw HTTP request/response bodies during the spike so we can tell empty-response vs. role-alternation vs. some third failure mode.

### Secondary risks

- **Role alternation.** Parallax-ai's adapter merges consecutive same-role messages and ensures the first non-system message is `user`. PydanticAI's tool loop produces assistant-message-with-tool-calls followed by tool-role messages, which may or may not pass Infomaniak's alternation check. Documented, not ported.
- **Gemma3n markdown quirk (BUG-080).** Not in Phase 1/2 scope (we're not using gemma3n). Documented for Phase 6.
- **Anthropic-specific behaviors.** Analyst/auditor prompts in `pipeline/analyst/instructions.md` and `pipeline/auditor/instructions.md` were tuned against Claude. Mistral may be terser or looser about Pydantic schema adherence. PydanticAI's `retries=2` on each agent gives two retries on validation failures, which should soak up minor drift; larger drift would show up as `needs_review` disagreement-rate spikes.
- **Context limits.** Mistral-Small is 128K tokens (per `parallax-ai/docs/research/INFOMANIAK_MODEL_REPORT.md`). Large analyst prompts with 4 full source bodies can get chunky; unlikely to overflow but worth noting if we expand `--max-sources`.
- **Brave Search coupling.** `BRAVE_WEB_SEARCH_API_KEY` remains required for `dr research` regardless of LLM provider. No change.
- **Base-URL path shape.** Infomaniak's published endpoint is `.../openai/v1/chat/completions`. PydanticAI `OpenAIProvider` expects a base URL and appends `/chat/completions`. Resolved via the two-candidate curl probe that opens Phase 1.

## Resolved questions

- **POC purpose (Q1).** Demo-able end-to-end against one canned claim -- between "just switch provider" and "full production parity." See acceptance bar in Phase 1. (2026-04-23)
- **Credentials (Q2).** Infomaniak API key + product ID available; Mistral-Small and GPT-OSS-120B both enabled. (2026-04-23)
- **Demo claim (Q3, proposed).** `research/claims/chatgpt/renewable-energy-hosting.md`. (2026-04-23)
- **Per-agent selector shape (Q4, proposed).** Four per-agent env vars with `DR_MODEL` fallback. (2026-04-23)
- **Base URL shape (Q5).** Moved into Phase 1 as the first task; two-candidate curl probe documented above. (2026-04-23)

## Open questions

1. **Disagreement-rate baseline.** Before Phase 1 we should capture the current Claude-Haiku disagreement rate from existing `.audit.yaml` sidecars so we have a comparison number for Mistral-small's analyst/auditor drift. This is a short spike, not a blocker for the POC itself.

## Critical files

- `pipeline/common/models.py` -- add `resolve_model()` helper
- `pipeline/orchestrator/pipeline.py` -- update four `.override(model=...)` sites
- `pipeline/orchestrator/cli.py` -- update two `.override(model=...)` sites; soften API-key check
- `pipeline/researcher/agent.py` -- no change; source of tool-use risk
- `pipeline/ingestor/agent.py` -- no change; source of tool-use risk
- `pipeline/analyst/agent.py` -- no change
- `pipeline/auditor/agent.py` -- no change

## References

- `parallax-ai/backend/app/services/llm/_infomaniak.py` -- quirk workarounds (role alternation, markdown sanitization)
- `parallax-ai/backend/app/config/model_registry.py` -- `supports_tools=False` on all Infomaniak + GreenPT models
- `parallax-ai/backend/scripts/spike_tool_calling.py` -- Phase 0.42 start-gate spike for tool-definition + tool-result acceptance
- `parallax-ai/docs/BUGS.md` -- BUG-080 (gemma3n empty response), BUG-082 (tool history empty response), BUG-083 (role artifact leaks)
- `parallax-ai/docs/research/INFOMANIAK_MODEL_REPORT.md` -- 2026-03-12 evaluation of Mistral-Small, Gemma3n, Apertus
- `parallax-ai/docs/UNSCHEDULED.md` -- rationale for reverting OpenAI-compat tool calling architecture

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-23 | agent (opus-4-7) | draft, implementation-referenced | Initial draft. File/line references verified against pipeline source. Tool-use risk grounded in parallax-ai BUG-082/083 and `supports_tools=False` registry entries. Not yet human-reviewed; promote from draft after review. |
| 2026-04-23 | agent (opus-4-7) | user-answers pass | Resolved Q1 (demo-able acceptance bar with fallback), Q2 (creds available). Proposed defaults for Q3 (demo claim: `chatgpt/renewable-energy-hosting.md`), Q4 (per-agent env vars), Q5 (curl probe moved to first task of Phase 1). Only the Claude-baseline disagreement-rate spike remains open. |
