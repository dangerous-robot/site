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
