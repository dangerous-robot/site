# Known Issues

Tracked, non-fatal issues with a known workaround or expected fix. New entries go at the top.

## Ingestor not retried on Infomaniak null-body responses

**Symptom:** During `dr onboard` (or any pipeline path that runs the ingestor against an Infomaniak-hosted model), a single URL fails with:

```
WARNING [orchestrator.pipeline] Failed to ingest <url>: Invalid response from openai chat completions endpoint: 4 validation errors for ChatCompletion
  id      Input should be a valid string [input_value=None]
  choices Input should be a valid list   [input_value=None]
  model   Input should be a valid string [input_value=None]
  object  Input should be 'chat.completion' [input_value=None]
```

**Cause:** The Infomaniak gateway occasionally returns a 200 OK with a null/empty body. PydanticAI's `OpenAIChatModel._process_response` then fails to validate the response and raises `UnexpectedModelBehavior` (see `pydantic_ai/models/openai.py:913`).

**Impact:** Non-fatal. The pipeline logs a `StepError(error_type="model_error")` for that URL and continues with the rest of the candidate pool.

**Existing partial mitigation:** `_run_with_null_retry` in `pipeline/orchestrator/pipeline.py` retries on this exact error pattern (2 retries, 45s delay). Used by the analyst and auditor paths; **not yet wired into the ingest path** (`_ingest_one` calls `ingestor_agent.run(...)` directly). Line numbers omitted deliberately; locate by function name.

**Open work to fully fix:** Extend `_run_with_null_retry` to accept `deps` and reset the mutating side-channel buffers on `IngestorDeps` (`acquisition_writes`, `wayback_failures`) between attempts.
