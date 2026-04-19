# Work Item: Agent Pipeline (PydanticAI)

**Phase**: 4
**Status**: not started
**Depends on**: Phases 1-3.5 (all done)

## Goal

Automate source ingestion using PydanticAI (Python). Start with the Ingestor agent -- the first agent that actually needs LLM reasoning.

## What Moved Out of This Plan

- **Citation Auditor**: Deterministic script, no LLM needed. Now lives in ci-pipeline.md as `scripts/check-citations.ts`.
- **Page Builder**: TS build script (`scripts/generate-data.ts`). Now lives in downstream-sync.md.

## Agents (prioritized)

### Tier 1: Ingestor
- Input: URL (from CLI or QUEUE.md)
- Steps: fetch page, extract metadata, check Wayback Machine, generate summary via LLM
- Output: `research/sources/{yyyy}/{slug}.md` with valid frontmatter
- This is the first agent that justifies PydanticAI -- it needs LLM reasoning to summarize and extract metadata

### Tier 2: Claim Updater (deferred)
- Input: claim file + relevant source files
- Steps: reason about whether verdict should change, propose update
- Output: PR with proposed changes (human reviews)
- Build only when claim volume makes manual updates burdensome

## Tasks

### Setup
- [ ] Add Python project structure:
  ```
  agents/
    ingestor.py
    common/           # frontmatter parser, file writer
    pyproject.toml    # using uv or pip
  ```
- [ ] Install PydanticAI + dependencies
- [ ] Define Pydantic models matching Zod schemas from Phase 2
- [ ] Create shared frontmatter reader/writer utilities

### Ingestor Agent
- [ ] CLI invocation: `python -m agents.ingestor https://example.com/report`
- [ ] Fetch page content, extract title/publisher/date
- [ ] Check Wayback Machine `save/` endpoint for archived URL
- [ ] LLM-generate summary (max 30 words per AGENTS.md rule)
- [ ] Write `research/sources/{yyyy}/{slug}.md`
- [ ] Validate output against schema

## Design Decisions

**Language**: Python (PydanticAI is Python-only). Polyglot repo accepted.

**Invocation**: CLI scripts, not a service. Run locally or in GitHub Actions.

**State**: File system + git. No database.

**Testing**: PydanticAI dependency injection for mocking LLM calls. Integration tests against real files.

**Model**: Ingestor needs summarization -- Haiku or Sonnet. Claim Updater (if built) needs stronger reasoning -- Sonnet.

## Open Questions

1. **Python tooling**: `uv` (fast, modern) vs standard `pip` + `venv`. Decide when scaffolding.
2. **CI Python setup**: When agents run in CI (Phase 5), GitHub Actions needs `actions/setup-python`. Not needed until then.

## Estimated Scope

Medium. Ingestor is ~200-300 lines including shared utilities. The PydanticAI scaffolding is the learning curve.
