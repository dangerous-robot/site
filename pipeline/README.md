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

```bash
uv run pytest tests/ -v
```

## Structure

- `common/` -- Shared models, frontmatter utilities, and content loaders
- `ingestor/` -- Source ingestion agent (Phase 4.1)
- `consistency/` -- Consistency checking agent (Phase 4.2)
- `loop/` -- The one research run (`run`, `rerun`), `StepError`, the error policy (`policy.py`), the blind tie-breaker agent (`tiebreaker/`) and the restater agent (`restater/`, with `restate.py`); returns a result (with a finding when the run was abandoned, recovered, split or partial, the last being a failed restater on a claim that was still written) and writes nothing
- `tests/` -- Test suite

## Researcher host blocklist

The researcher output is filtered through an operator-editable host blocklist at `research/blocklist.yaml` before URLs reach the ingestor. Matching is case-insensitive, strips a leading `www.`, and is suffix-matched on a dot boundary, so `linkedin.com` matches `www.linkedin.com` and `uk.linkedin.com` but not `notlinkedin.com`. Dropped URLs surface as `StepError(error_type="blocked_host")` (`StepError` lives in `pipeline/loop/errors.py`) in the run result's errors; if every researcher URL is filtered, an additional `"all_blocked"` error is prepended and the run is abandoned at once and recorded under `research/findings/`. A missing file is treated as an empty blocklist. Filtering runs before the `max_sources` slice so capacity isn't wasted on known-bad hosts.
