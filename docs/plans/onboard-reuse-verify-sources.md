# Plan: Eliminate duplicate research+ingest in onboard flow

## Problem

`onboard_entity` (pipeline/orchestrator/pipeline.py:563-609) iterates templates, calls `verify_claim` (runs researcher + ingestor + analyst + auditor), then immediately re-runs `_research()` + `_ingest_urls()` at lines 587-590 solely to recover `list[tuple[str, SourceFile]]` for `_write_source_files`. This doubles LLM calls, web fetches, and 403 retries per template.

Root cause: `VerificationResult.sources` (pipeline/orchestrator/pipeline.py:41) is `list[dict]` built by `_build_source_dict` (line 225). The raw `SourceFile` objects and their source-URL pairings are dropped on the floor in `verify_claim` at line 101-103.

## Approach

Make `verify_claim` expose the `(url, SourceFile)` pairs it already computed. Simplest change: add a new field on `VerificationResult`. Keep the existing `sources: list[dict]` for backward compat with `cli.py` display (lines 52-57), `_analyse_claim`, `_audit_claim`, and `test_orchestrator.py`.

### Data-flow change

In `pipeline/orchestrator/pipeline.py`:

1. **VerificationResult (lines 33-46)**: add

   ```python
   source_files: list[tuple[str, SourceFile]] = Field(default_factory=list, exclude=True)
   ```

   `exclude=True` keeps it out of any future JSON serialization (tuples are not JSON-friendly and are an internal handoff). `arbitrary_types_allowed=True` is already set. Default empty list preserves constructability from existing tests (test_orchestrator.py:10-17).

2. **verify_claim (line 101-103)**: after populating `result.sources.append(_build_source_dict(sf))`, also keep the tuple:

   ```python
   result.source_files.append((url, sf))
   ```

   (Single added line, inside the existing `for url, sf in source_files:` loop.)

3. **research_claim (lines 340-343)**: mirror the same append so both entry points stay consistent. (It already has the tuples locally at line 338 and writes them at line 364, so this is one-line parity for future reuse.)

4. **onboard_entity (lines 585-592)**: delete the redundant block

   ```python
   async with httpx.AsyncClient() as client:
       urls, _ = await _research(client, entity_name, claim_text, cfg)
       if urls:
           source_tuples, _ = await _ingest_urls(client, urls, cfg)
   source_ids = _write_source_files(source_tuples, repo_root) if source_tuples else []
   ```

   Replace with:

   ```python
   source_ids = _write_source_files(vr.source_files, repo_root) if vr.source_files else []
   ```

No changes to `persistence.py` (`_write_source_files` already takes `list[tuple[str, SourceFile]]`), `ingestor/models.py`, or any agent module.

### Commits

Single-commit change is fine. Suggested message:

- `refactor(pipeline): reuse verify_claim sources in onboard to avoid double ingest`

## Test Plan

Target file: `pipeline/tests/test_onboard.py`.

1. **Existing `TestOnboardEntityHappyPath.test_onboard_creates_entity_and_claims`** must still pass unchanged -- templates_applied == 6, claims_created > 0, entity file present.
2. **New `TestOnboardEntityNoDoubleIngest`**: spy on `_ingest_urls` and assert its call count is bounded.
   - Use `patch("orchestrator.pipeline._ingest_urls", wraps=real_ingest_urls)` (or a per-test counter) and run the happy-path flow (6 templates).
   - Assert: total calls to `_ingest_urls` == `1 (light research) + 6 (verify_claim, one per template)` = **7**, not 13. Equivalently, assert `_research` call count <= 7.
   - This is the canary against regression to the duplicate path.
3. **New `TestVerificationResultCarriesSourceFiles`** in `test_orchestrator.py`: construct a `VerificationResult` with a fabricated `SourceFile` tuple and assert round-trip attribute access; also assert backward-compatible construction without `source_files` (existing test at line 10-17 already proves this when the field defaults to `[]`).
4. **Manual verification suggested (not a unit test)**: run `dr onboard "Acme" --type company --only publishes-sustainability-report` with network and eyeball that only one research+ingest pair occurs per template in logs.

## Risks

- **Memory footprint**: `SourceFile.body` is a full markdown body (unbounded). Holding up to `max_sources` (default 4) per verify call inside `VerificationResult` is fine; onboard discards the `VerificationResult` at end of each loop iteration, so no accumulation across templates. Low risk.
- **Shared-state aliasing**: `result.sources[i]` (dict) and `result.source_files[i][1]` (SourceFile) describe the same underlying ingest, but `_build_source_dict` copies fields rather than referencing -- no aliasing bug risk.
- **Pydantic serialization**: adding a field with `tuple[str, SourceFile]` requires `arbitrary_types_allowed` (already set) and `exclude=True` on the Field to avoid breaking any future `.model_dump()` callers. Verify no current caller serializes `VerificationResult`; grep shows only `cli.py` attribute access and tests -- safe.
- **research_claim still writes sources inline** (line 364) -- it does not consume `result.source_files` downstream, so the new field is redundant there but harmless and keeps the invariant "VerificationResult always carries its source tuples."

## Done When

- `onboard_entity` makes exactly one `_research` + `_ingest_urls` pair per template (verified by spy test).
- All existing pipeline tests pass (`pytest pipeline/tests/`).
- Happy-path onboard still writes one entity file + N claim files + correct source files.
- `VerificationResult(...)` construction works both with and without `source_files` kwarg.
- A manual `dr onboard --only <slug>` run shows roughly halved wall-clock time vs. pre-change baseline.

## Critical files

- `pipeline/orchestrator/pipeline.py`
- `pipeline/orchestrator/persistence.py`
- `pipeline/tests/test_onboard.py`
- `pipeline/tests/test_orchestrator.py`
- `pipeline/ingestor/models.py`
