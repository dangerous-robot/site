# dangerous-robot-pipeline

PydanticAI agent pipeline for dangerousrobot.org research automation.

This package provides shared infrastructure for research agents that ingest sources, check claim consistency, and maintain the structured Markdown+YAML content in `research/`.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync --locked
```

Run it from the repo root: `pipeline/` is a member of the uv workspace defined there, and the committed `uv.lock` at the root is the one CI installs. After changing `pipeline/pyproject.toml`, run `uv lock` at the root and commit the updated `uv.lock`.

## Running tests

Run inside `pipeline/`. The `acceptance` marker selects live tests that make paid model and search calls, so the default command leaves them out:

```bash
uv run python -m pytest -m 'not acceptance'
```

Run it from `pipeline/` (or `inv test` from the repo root). Do not run pytest from the repo root with no file argument: the root `pyproject.toml` sets no `asyncio_mode`, so unmarked async tests fail there; mark every new async test `@pytest.mark.asyncio`.

## Structure

- `common/` -- Shared models, frontmatter utilities, and content loaders
- `researcher/` -- Researcher agent: claim to candidate URLs
- `ingestor/` -- Ingestor agent: URL to source file
- `analyst/` -- Analyst agent: sources and claim to verdict and narrative
- `auditor/` -- The Evaluator agent (directory rename to `evaluator/` deferred to post-v1)
- `loop/` -- The one research run (`run`, `rerun`), `StepError`, the error policy (`policy.py`), the blind tie-breaker agent (`tiebreaker/`) and the restater agent (`restater/`, with `restate.py`); returns a result (with a finding when the run was abandoned, recovered, split or partial, the last being a failed restater on a claim that was still written) and writes nothing
- `orchestrator/` -- The `dr` commands (`cli.py`), routing and persistence (`persistence.py`, the one writer)
- `linter/` -- The static content checks behind `dr lint` (no LLM, no network)
- `tests/` -- Test suite

## Researcher host blocklist

The researcher output is filtered through an operator-editable host blocklist at `research/blocklist.yaml` before URLs reach the ingestor. Matching is case-insensitive, strips a leading `www.`, and is suffix-matched on a dot boundary, so `linkedin.com` matches `www.linkedin.com` and `uk.linkedin.com` but not `notlinkedin.com`. Dropped URLs surface as `StepError(error_type="blocked_host")` (`StepError` lives in `pipeline/loop/errors.py`) in the run result's errors; if every researcher URL is filtered, an additional `"all_blocked"` error is prepended and the run is abandoned at once and recorded under `research/findings/`. A missing file is treated as an empty blocklist. Filtering runs before the `max_sources` slice so capacity isn't wasted on known-bad hosts.
