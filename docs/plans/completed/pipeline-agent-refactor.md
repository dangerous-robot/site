# Pipeline Agent Architecture Refactor

## Problem

The pipeline has four agents with inconsistent organization: `ingestor` and `consistency` are top-level packages, but `researcher` and `drafter` are buried under `verify/`. Names don't convey roles clearly ("drafter" sounds like copywriting, "consistency" is vague). The orchestrator lives inside `verify/` despite coordinating all agents.

## Goals

- Promote all agents to top-level packages with clear names
- Extract system prompts to editable instruction files
- Add human-in-the-loop checkpoints before analysis and on reviewer disagreement
- Establish configurability patterns for future use (claim templates, per-agent instruction variants)

## Target structure

```
pipeline/
  common/              # shared models, frontmatter, content_loader, instructions loader
  ingestor/            # Agent: URL -> SourceFile
  researcher/          # Agent: claim -> relevant URLs (moved from verify/)
  analyst/             # Agent: sources + claim -> verdict + narrative (renamed from drafter)
  auditor/             # Agent: independent second opinion (renamed from consistency)
  orchestrator/        # Python routing logic, checkpoints, persistence, CLIs (moved from verify/)
  tests/
```

### Naming decisions

| Old name | New name | Rationale |
|----------|----------|-----------|
| `drafter` | `analyst` | "Drafter" implies copywriting; this agent assesses evidence and renders verdicts |
| `consistency` | `auditor` | "Reviewer" collides with code review / PR review terminology; "auditor" conveys independent, adversarial assessment |
| `verify/` | `orchestrator/` | The verify package contained routing logic, not a single agent; "orchestrator" reflects its coordination role |

## Agent roles

| Agent | Input | Output | Tools |
|-------|-------|--------|-------|
| **Researcher** | Claim text | URLs + reasoning | `web_search` (Brave API) |
| **Ingestor** | URL | SourceFile (frontmatter + body) | `web_fetch`, `wayback_check` |
| **Analyst** | Sources + claim | Verdict, confidence, narrative | None (LLM reasoning) |
| **Auditor** | Sources + claim (no verdict) | Independent assessment | None (LLM reasoning) |

### Analyst output decomposition

`ClaimDraft` currently bundles two concerns: entity resolution and verdict assessment. Split the output model:

```python
class EntityResolution(BaseModel):
    entity_name: str
    entity_type: str   # company | product | topic
    entity_description: str

class VerdictAssessment(BaseModel):
    title: str
    verdict: Verdict
    confidence: Confidence
    narrative: str

class AnalystOutput(BaseModel):
    entity: EntityResolution
    verdict: VerdictAssessment
```

This separates entity discovery from verdict reasoning so that future entity-as-input pipelines can skip the resolution step. The analyst agent still runs once, but downstream code consumes `.entity` and `.verdict` independently.

Slug generation should move out of the LLM entirely -- generate it in Python from the claim title using a deterministic slugify function.

### Auditor bundle factory

The orchestrator currently imports `SourceContext`, `EntityContext`, and `ClaimBundle` from the auditor to construct its input. Instead, the auditor package should expose a factory function:

```python
# auditor/bundle.py
def build_bundle(entity_name, entity_type, description, category, narrative, sources) -> ClaimBundle:
```

The orchestrator passes primitives; the auditor owns how those map to its internal types.

## Pipeline flow with checkpoints

```
Input (claim text)
  |
  v
[Researcher] -> URLs
  |
  v
[Ingestor] -> SourceFiles (parallel per URL)
  |
  v
>>> CHECKPOINT: review sources <<<
  "Found N sources (M failed). Proceed to analysis?"
  Shows failure reasons (timeout vs. 404 vs. API error)
  If no: halt, return partial result with populated urls_found/urls_ingested
  |
  v
[Analyst] -> verdict + narrative
  |
  v
[Auditor] -> independent assessment (always runs)
  |
  v
>>> CHECKPOINT (on disagreement): review conflict <<<
  "Analyst: mostly-false (medium). Auditor: mixed (low). Resolve?"
  If no: flag for human review, do not publish
  |
  v
Output (VerificationResult)
```

### Checkpoint protocol

Use a typed Protocol with two methods so each gate receives the data it needs:

```python
@runtime_checkable
class CheckpointHandler(Protocol):
    async def review_sources(
        self,
        urls_found: int,
        urls_ingested: int,
        errors: list[StepError],
    ) -> bool:
        """Return True to proceed to analysis, False to halt."""
        ...

    async def review_disagreement(
        self,
        comparison: ComparisonResult,
    ) -> bool:
        """Return True to accept result, False to flag for human review."""
        ...
```

Implementations:
- `CLICheckpointHandler` -- interactive prompts via `click.confirm()`
- `AutoApproveCheckpointHandler` -- for tests and CI, with a `calls: list[str]` spy attribute

The orchestrator takes `checkpoint: CheckpointHandler | None = None`, defaulting to `None` (auto-approve, backward compatible).

### Typed errors

Replace `errors: list[str]` with typed step errors:

```python
class StepError(BaseModel):
    step: str        # "research", "ingest", "analyst", "auditor"
    url: str | None = None  # for per-URL ingest failures
    error_type: str  # "timeout", "http_error", "model_error", "api_key_missing"
    message: str
    retryable: bool = False
```

This enables the source-review checkpoint to distinguish "2 URLs 404'd" (probably fine) from "Brave API key expired" (halt everything). Change `_ingest_urls` to return both successes and per-URL errors.

## Orchestrator module layout

The orchestrator currently mixes pipeline routing, result types, file I/O, and CLIs. Split into focused modules:

```
orchestrator/
  __init__.py
  pipeline.py        # verify_claim(), research_claim(), VerificationResult, VerifyConfig
  checkpoints.py     # CheckpointHandler protocol, CLICheckpointHandler, AutoApproveCheckpointHandler
  persistence.py     # _write_source_files(), _write_entity_file(), _write_claim_file(), _slugify()
  cli.py             # Click commands
```

`VerificationResult` and `VerifyConfig` stay in the orchestrator -- they depend on agent output types, so moving them to `common/` would create upward dependencies.

## CLI design

Single `dr` CLI with subcommands instead of 4 separate script entry points:

```toml
[project.scripts]
dr = "orchestrator.cli:main"
```

```
dr verify "iPhone 20 reads your mind"
dr research "iPhone 20 reads your mind"
dr audit apple-mind-control
dr ingest https://example.com/article
```

Benefits: `dr --help` shows all commands, shared options (`--model`, `--verbose`) defined once, single tab-completion install. The `ingest` subcommand imports from `ingestor/` lazily.

## Implementation steps

### Phase 0: Safety net (before any moves)

#### 0a. Split test_verify.py
Split `test_verify.py` into `test_researcher.py`, `test_analyst.py`, and `test_orchestrator.py` so each file tracks one moving piece. Run the full suite to confirm the split is clean.

#### 0b. Write research_claim integration test
Write an integration test for `research_claim` that uses `TestModel` for all four agents, points `repo_root` at `tmp_path`, and asserts that source files, entity file, and claim file are all written to disk with valid frontmatter. This is the test most likely to catch regression during the refactor.

#### 0c. Add CLI smoke tests
Add `--help` smoke tests for every CLI entry point in `pyproject.toml`:

```python
@pytest.mark.parametrize("entry_point", ["verify-claim", "research", "consistency-check", "ingest"])
def test_cli_help(entry_point):
    result = subprocess.run(["uv", "run", entry_point, "--help"], capture_output=True)
    assert result.returncode == 0
```

### Phase 1: Move agents (each step includes its test update)

#### 1. Create new directory structure
New top-level packages: `researcher/`, `analyst/`, `auditor/`, `orchestrator/`

Do NOT create `config/` -- defer until there's something to put in it.

#### 2. Instructions loader utility
`common/instructions.py` with `load_instructions(agent_dir: Path) -> str`.
Each agent loads its system prompt from `instructions.md` in its own directory.

The loader must:
- Raise `FileNotFoundError` with the expected path if the file is missing
- Raise `ValueError` if the file is empty or whitespace-only
- Use `encoding="utf-8"` explicitly

Test cases:
- Missing file raises clear error
- Empty/whitespace file raises clear error
- Non-ASCII content preserved
- Literal curly braces preserved (regression tripwire for future template support)
- Each agent's system prompt matches its `instructions.md` content after wiring

#### 3. Move researcher + update tests
`verify/researcher.py` -> `researcher/agent.py` + `researcher/instructions.md`

Update `test_researcher.py` imports. Run suite.

#### 4. Move and rename drafter -> analyst + update tests
`verify/drafter.py` -> `analyst/agent.py` + `analyst/instructions.md`

Split `ClaimDraft` into `EntityResolution` + `VerdictAssessment` + `AnalystOutput`.
Move slug generation to a deterministic Python function (not LLM output).

Renames: `drafter_agent` -> `analyst_agent`, `DrafterDeps` -> `AnalystDeps`, `build_drafter_prompt` -> `build_analyst_prompt`

Update `test_analyst.py` imports. Run suite.

#### 5. Move and rename consistency -> auditor + update tests
`consistency/{agent,models,compare,report}.py` -> `auditor/` + `auditor/instructions.md`

Add `auditor/bundle.py` with `build_bundle()` factory function.

Renames: `consistency_agent` -> `auditor_agent`, `ConsistencyDeps` -> `AuditorDeps`

Rename `compare()` parameters from `actual_*` to `primary_*` to reflect both "ground truth vs. assessment" and "analyst vs. auditor" usage.

Audit `repo_root` in `AuditorDeps` -- if the agent itself doesn't use it, remove it from deps. Pass `repo_root` directly to persistence functions from the orchestrator.

Update `test_auditor_agent.py`, `test_auditor_models.py`, `test_compare.py` imports. Run suite.

#### 6. Extract ingestor instructions
Add `ingestor/instructions.md`, update `ingestor/agent.py` to load from file.

#### 7. Move orchestrator + update tests
`verify/orchestrator.py` -> split into `orchestrator/pipeline.py` and `orchestrator/persistence.py`

Update all import paths to new module locations.

**This is the riskiest step.** The orchestrator imports from every agent package. If any of Steps 3-6 didn't land cleanly, this is where it surfaces. The `research_claim` integration test from Phase 0 is the critical safety net here.

Update `test_orchestrator.py` and `test_acceptance.py` imports. Run suite.

### Phase 2: New capabilities

#### 8. Add checkpoint protocol
`orchestrator/checkpoints.py`:
- `CheckpointHandler` Protocol
- `CLICheckpointHandler` -- CLI prompts via `click.confirm()`
- `AutoApproveCheckpointHandler` -- for tests, with spy `calls` list

Wire into `verify_claim()` and `research_claim()`.

#### 9. Add typed errors
Add `StepError` model to orchestrator. Update `VerificationResult.errors` from `list[str]` to `list[StepError]`. Categorize exceptions by type (timeout, http_error, model_error, api_key_missing).

Change `_ingest_urls` to return `tuple[list[tuple[str, SourceFile]], list[StepError]]`.

#### 10. Consolidate CLIs
Build `dr` CLI group in `orchestrator/cli.py`:
- `dr verify` (was `verify-claim`)
- `dr research` (was `research`)
- `dr audit` (was `consistency-check`)
- `dr ingest` (was `ingest`)

Update `pyproject.toml` to single entry point.

### Phase 3: Cleanup

#### 11. Delete old directories
Remove `verify/` and `consistency/` entirely.

#### 12. Update pyproject.toml
Packages list: `["common", "ingestor", "researcher", "analyst", "auditor", "orchestrator"]`

#### 13. Update AGENTS.md
Document new agent roles, directory layout, instruction file convention, checkpoint behavior, `dr` CLI usage.

## Designed for but not yet implemented

- **Claim templates**: Standardized claim patterns with entity slots (e.g., `ENTITY(Company) is carbon negative`)
- **Multiple instruction sets per agent**: Strict vs. lenient modes, domain-specific variants
- **Non-CLI checkpoint backends**: Webhooks, PR gates, queue-based approval
- **URL-as-input pipeline**: Ingest URL, determine which existing claims it affects, re-evaluate (no structural changes needed -- orchestrator coordinates `ingestor -> claim lookup -> verify_claim` loop)
- **Entity-as-input pipeline**: Discover claims to investigate for a new entity (enabled by `EntityResolution` split -- orchestrator can skip entity resolution when entity is pre-resolved)
- **`config/` package**: Claim templates, per-agent defaults. Create when implementing claim templates.
- **Shared prompt fragments**: `common/verdict.py` with verdict scale and confidence definitions, composed into agent prompts to avoid duplication across analyst and auditor instructions

## Verification

1. `uv lock && uv sync --dev` resolves
2. Unit tests: `python -m pytest tests/ -m "not acceptance" -q` (all pass)
3. Acceptance test: `python -m pytest tests/ -m acceptance -v -s` (live API test)
4. CLI smoke: `uv run dr --help`, `uv run dr verify --help`, `uv run dr research --help`, `uv run dr audit --help`, `uv run dr ingest --help`
5. Each agent loads from `instructions.md`
6. Checkpoints prompt during `verify` and `research` flows
7. `research_claim` integration test writes valid artifacts to disk
8. Acceptance test asserts checkpoint handler was reached (spy attribute)

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (cursory review) | completed-check | Added review history section; no unfinished work found |
