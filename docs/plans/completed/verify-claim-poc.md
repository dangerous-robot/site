# POC: End-to-End Claim Verification

**Status**: done
**Depends on**: Phase 4 (done)
**Scope**: Proof of concept -- validate the pipeline architecture, not production-ready

## Goal

A single CLI command that takes an entity name and a claim statement, then orchestrates four agents to research, ingest, draft, and consistency-check the claim. The output is a human-readable report.

```bash
uv run verify-claim "Ecosia" "Ecosia's AI chat runs on renewable energy"
```

## Architecture

```
CLI input (entity + claim text)
  |
  v
1. Research agent (NEW)
   - Searches DuckDuckGo for relevant URLs
   - Returns 2-5 ranked URLs with reasoning
  |
  v
2. Ingestor agent (EXISTING, called programmatically)
   - Fetches each URL, extracts metadata
   - Returns SourceFile objects (not written to disk)
   - Failed URLs are skipped
  |
  v
3. Claim drafter agent (NEW)
   - Reads source materials + claim statement
   - Produces structured ClaimDraft: title, category, verdict, confidence, narrative
  |
  v
4. Consistency check agent (EXISTING, called programmatically)
   - Independently assesses the claim (information asymmetry preserved)
   - Compares its verdict against the drafter's verdict
  |
  v
Report: sources, draft claim, consistency comparison
```

## What this POC validates

- PydanticAI agents compose programmatically (not just via CLI)
- Shared infrastructure (common/) supports the full chain
- The consistency check provides genuine second-opinion value
- Error handling at each stage doesn't cascade (failed URLs skipped, missing sources noted)

## What this POC does NOT validate

- Verdict correctness (requires manual evaluation against known claims)
- Search quality (DuckDuckGo HTML scraping is a placeholder)
- Scale behavior (tested with 1 claim, 2-5 sources)

## Known shortcuts

| Shortcut | Risk | Fix when |
|----------|------|----------|
| DuckDuckGo HTML scraping | Will break when DDG changes HTML | Before any regular use. Swap for Brave Search API or similar. |
| Sequential URL ingestion | Slow with many URLs | When latency matters. Use `asyncio.gather`. |
| No file persistence | Draft not saved to `research/` | Add `--save` flag when workflow is validated. |
| Entity type hardcoded to "company" | Wrong for products/topics | When verifying non-company claims. Look up existing entity files. |
| No deduplication | Same content ingested twice from different URLs | When source volume increases. |
| No cost tracking | Unknown per-run cost | Before frequent use. Log token counts. |

## Files

```
pipeline/verify/
  __init__.py
  researcher.py      # Research agent + DuckDuckGo search tool
  drafter.py          # Claim drafter agent
  orchestrator.py     # Chains all four agents
  cli.py              # CLI entry point
pipeline/tests/
  test_verify.py      # 7 tests (mocked LLM, no network calls)
```

## How to run

```bash
# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run verification
uv run --directory pipeline verify-claim "Ecosia" "Ecosia's AI chat runs on renewable energy"

# With options
uv run --directory pipeline verify-claim --max-sources 2 "Anthropic" "Anthropic has the best safety score among AI companies"
```

## Evaluation plan

Run against 3 existing claims where we already know the verdict:

1. `ecosia/renewable-energy-hosting` (verdict: false) -- "Ecosia's AI chat runs on renewable energy"
2. `anthropic/existential-safety-score` (verdict: true) -- "Anthropic scores poorly on existential safety"
3. `greenpt/renewable-energy-hosting` (verdict: true) -- "GreenPT runs on renewable energy"

For each: does the drafter reach a similar verdict? Does the consistency check flag disagreements? Are the sources reasonable?

## Next steps (post-POC, not committed)

1. **Replace DuckDuckGo scraping** with a proper search API
2. **Add `--save` flag** to persist source files and claim draft to `research/`
3. **Entity resolution** -- look up existing entity files, create stubs for new entities
4. **Cost tracking** -- log token usage per agent per run
5. **Batch mode** -- verify multiple claims from a file or QUEUE.md
