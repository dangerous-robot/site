# Phase 4: Agent Pipeline (PydanticAI)

**Phase**: 4
**Status**: not started
**Depends on**: Phases 1-3.5 (all done)
**Prerequisites**: Naming conventions applied (`pipeline/` directory, `recheck_cadence_days` field rename)

## Goal

Automate source ingestion and provide LLM-assisted content validation using PydanticAI (Python). Two work items:

- **4.1 Ingestor agent**: Takes a URL, produces a valid source file. First agent that needs LLM reasoning.
- **4.2 Narrative-verdict consistency check**: Compares LLM's independent assessment against editorial verdicts. Surfaces disagreements for human review.

## Sub-Plans

Detailed implementation specs live in draft sub-plans. These are authoritative for task-level detail; this parent plan covers scope, shared infrastructure, and coordination.

| # | Work Item | Detailed Plan | Notes |
|---|-----------|---------------|-------|
| 4.1 | Ingestor agent | [agent-pipeline-ingestor.md](agent-pipeline-ingestor.md) | Promote before implementation |
| 4.2 | Consistency check | [narrative-verdict-consistency.md](narrative-verdict-consistency.md) | Promote before implementation |

## Done When

- 4.1: Ingestor agent takes a URL and produces a source file that passes `npm run build` validation. Test suite passes without live LLM calls.
- 4.2: Consistency checker runs against all claims and produces a classified text/JSON report. Test suite passes without live LLM calls.
- Pydantic models validate successfully against all existing research files.
- `pipeline/` package installs cleanly via `uv sync`.

## What Moved Out of This Plan

- **Citation Auditor**: Deterministic script, no LLM needed. Now lives in ci-pipeline.md as `scripts/check-citations.ts`.
- **Page Builder**: TS build script (`scripts/generate-data.ts`). Now lives in downstream-sync.md.

## Runners (prioritized)

### 4.1: Ingestor
- Input: URL (from CLI or QUEUE.md)
- Steps: fetch page, extract metadata, check Wayback Machine, generate summary via LLM
- Output: `research/sources/{yyyy}/{slug}.md` with valid frontmatter
- This is the first runner that justifies PydanticAI -- it needs LLM reasoning to summarize and extract metadata
- See [detailed plan](drafts/agent-pipeline-ingestor.md)

### 4.2: Narrative-Verdict Consistency Check
- Input: claim files + their referenced sources and entities
- Steps: strip verdict/confidence from claim, bundle with sources, get LLM's independent assessment, compare against actual values
- Output: classified report (text or JSON) flagging disagreements
- Read-only -- does not modify any files
- See [detailed plan](drafts/narrative-verdict-consistency.md)

### Deferred: Claim Updater
- Input: claim file + relevant source files
- Steps: reason about whether verdict should change, propose update
- Output: PR with proposed changes (human reviews)
- Build only when claim volume makes manual updates burdensome

## Shared Infrastructure

Both 4.1 and 4.2 share a `pipeline/common/` module. This must be designed before either sub-plan is implemented.

```
pipeline/
  pyproject.toml
  common/
    __init__.py
    frontmatter.py      # YAML parse, strip, serialize utilities
    content_loader.py   # Load claim, source, entity files by slug
    models.py           # Shared Pydantic models (Verdict, Confidence, Category enums)
  ingestor/             # 4.1
  consistency/          # 4.2
  tests/
```

Shared concerns:
- **Pydantic models for all three content types** (source, claim, entity). Source model owned by 4.1, claim/entity models owned by 4.2. Shared enums (Verdict, Confidence, Category, SourceKind) live in `common/models.py`.
- **YAML frontmatter read/write**: Both runners need to parse frontmatter. The ingestor also needs to write it. Use `pyyaml` with custom representers for dates and URLs.
- **File path resolution**: Resolving slugs to file paths under `research/`.

## Tasks

Task-level detail lives in the sub-plans. High-level sequence:

1. Scaffold `pipeline/` with `pyproject.toml`, `common/`, `tests/`
2. Implement shared models and frontmatter utilities
3. Implement 4.1 or 4.2 (see sequencing decision below)
4. Implement the other
5. Update architecture docs

## Design Decisions

**Language**: Python (PydanticAI is Python-only). Polyglot repo accepted.

**Python tooling**: `uv`. Already installed, faster than pip, single tool for venv + deps + scripts.

**Invocation**: CLI scripts, not a service. Run locally or in GitHub Actions.

**State**: File system + git. No database.

**Testing**: PydanticAI dependency injection for mocking LLM calls. Integration tests against real files.

**Model**: Sonnet default for both runners (summarization quality and analytical rigor matter). Haiku available via `--model` flag for cost-sensitive runs.

**Pydantic model maintenance**: Manual. Pydantic models mirror Zod schemas and must be updated when schemas change. An integration test parses existing research files with the Pydantic models to catch drift. JSON Schema as an intermediary is overkill at 3 schemas.

**YAML library**: `pyyaml` with custom representers for dates (`YYYY-MM-DD`) and URLs (plain strings). `ruamel.yaml` preserves comments but adds complexity not needed here since the pipeline only writes new files, not edits existing ones.

**Directory layout**: Flat package layout (`pipeline/ingestor/`, `pipeline/common/`, etc.) rather than nested `src/` layout. Simpler for a CLI tool in a monorepo. Both sub-plans use the same structure.

## Open Questions

1. **4.1 vs 4.2 sequencing**: The ingestor (4.1) was assumed to go first, but the consistency check (4.2) is read-only and lower risk -- it could be a better starting point for shaking out PydanticAI scaffolding and shared infrastructure. Decide before implementation.
2. **PydanticAI version pinning**: PydanticAI's API has changed between versions (e.g., `result_type` vs `output_type`). Pin to a specific minor version in `pyproject.toml` and verify the API parameter names match. Currently targeting `result_type` / `.data` API.
3. **CI Python setup**: The 4.2 plan includes a label-gated GitHub Actions workflow. This means `actions/setup-python` is needed in Phase 4, not Phase 5 as originally assumed.

## Estimated Scope

Medium. Ingestor is ~200-300 lines, consistency check is ~300-400 lines, shared infrastructure ~150 lines. The PydanticAI scaffolding is the learning curve.
