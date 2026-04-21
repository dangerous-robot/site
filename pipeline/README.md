# dangerous-robot-pipeline

PydanticAI agent pipeline for dangerousrobot.org research automation.

This package provides shared infrastructure for research agents that ingest sources, check claim consistency, and maintain the structured Markdown+YAML content in `research/`.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
cd pipeline
uv sync
```

## Running tests

```bash
uv run pytest tests/ -v
```

## Structure

- `common/` -- Shared models, frontmatter utilities, and content loaders
- `ingestor/` -- Source ingestion agent (Phase 4.1)
- `consistency/` -- Consistency checking agent (Phase 4.2)
- `tests/` -- Test suite

## Researcher host blocklist

The researcher output is filtered through an operator-editable host blocklist at `research/blocklist.yaml` before URLs reach the ingestor. Matching is case-insensitive, strips a leading `www.`, and is suffix-matched on a dot boundary, so `linkedin.com` matches `www.linkedin.com` and `uk.linkedin.com` but not `notlinkedin.com`. Dropped URLs surface as `StepError(error_type="blocked_host")` in the `review_sources` checkpoint and in `OnboardResult.errors`; if every researcher URL is filtered, an additional `"all_blocked"` error is prepended. A missing file is treated as an empty blocklist. Filtering runs before the `max_sources` slice so capacity isn't wasted on known-bad hosts.
