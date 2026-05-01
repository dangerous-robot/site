# Entity pre-resolution for `dr verify-claim`

**Status:** Promoted
**Scope:** v1.0.0
**Created:** 2026-05-01

---

## Context

### Why this change

The analyst agent currently runs two tasks in one LLM call: it infers the entity from the claim and its sources (`EntityResolution`), then produces the verdict (`VerdictAssessment`). Merging these creates several problems:

- The claim's disk path (`research/claims/{entity_slug}/{claim_slug}.md`) is unknown until the analyst returns, preventing any pre-flight validation or workspace allocation before LLM inference.
- Entity type can be misclassified (`product` vs. `company`) because the analyst works from claim text and source bodies, not from operator-supplied structured metadata.
- `parent_company` and other entity metadata stored in `research/entities/{type_dir}/{slug}.md` frontmatter are unavailable to the researcher (which queries without entity context) and the analyst (which infers rather than reads).
- State machine: the job key `(entity_slug, criteria_slug)` is ambiguous until the LLM call completes. This blocks a proper state machine architecture where each job slot has a deterministic identity at submission time.

### What pre-resolution achieves

When an entity file already exists on disk, the operator can supply `products/chatgpt` as a short entity reference at the CLI. The pipeline then:

1. Loads entity frontmatter before any LLM runs.
2. Passes structured entity data (name, type, description, aliases, parent_company) to the analyst prompt as authoritative context.
3. Directs the analyst to produce only a `VerdictAssessment` (skips `EntityResolution` inference).
4. Skips `_write_entity_file` (entity already exists).
5. Knows the claim directory before the researcher runs.

The job key `(entity_slug, criteria_slug)` is determined at CLI invocation time, not after a frontier-model call.

---

## Entity reference format

A short entity reference is a two-segment string: `{type_dir}/{slug}`.

```
products/chatgpt
companies/openai
sectors/ai-llm-producers
topics/ai-safety
```

The `type_dir` component must be one of the four values in `_ENTITY_TYPE_DIR`: `companies`, `products`, `topics`, `sectors`.

Resolution rule:
```
{repo_root}/research/entities/{type_dir}/{slug}.md
```

The `EntityType` is derived by inverting `_ENTITY_TYPE_DIR`:
```python
_DIR_ENTITY_TYPE: dict[str, EntityType] = {v: k for k, v in _ENTITY_TYPE_DIR.items()}
```

### Error cases (raise `ValueError`; CLI wraps as `UsageError`)

| Condition | Message |
|---|---|
| No slash in string | `"Invalid entity ref '{ref}': expected '{type_dir}/{slug}'"` |
| `type_dir` not recognized | `"Unknown entity type dir '{type_dir}': must be one of companies, products, sectors, topics"` |
| File does not exist | `"Entity file not found: {path}"` |
| Frontmatter parse failure | `"Failed to parse entity frontmatter at {path}: {exc}"` |
| `name` missing from frontmatter | `"Entity file {path} missing required field 'name'"` |

---

## New module: `pipeline/orchestrator/entity_resolution.py`

New file. No imports from `orchestrator/` -- only `common/` and stdlib -- to avoid circular imports. This means `_DIR_ENTITY_TYPE` is defined standalone here (not imported from `persistence.py`). The two maps are logically inverse; they live in separate modules.

```python
from dataclasses import dataclass, field
from pathlib import Path
from common.models import EntityType

_DIR_ENTITY_TYPE: dict[str, EntityType] = {
    "companies": EntityType.COMPANY,
    "products": EntityType.PRODUCT,
    "topics": EntityType.TOPIC,
    "sectors": EntityType.SECTOR,
}

@dataclass
class ResolvedEntity:
    entity_ref: str            # e.g. "products/chatgpt"
    entity_name: str           # frontmatter 'name'
    entity_type: EntityType    # derived from type_dir
    entity_description: str    # frontmatter 'description'
    aliases: list[str] = field(default_factory=list)
    parent_company: str | None = None
    website: str | None = None

def parse_entity_ref(entity_ref: str, repo_root: Path) -> ResolvedEntity:
    """Parse 'products/chatgpt' → ResolvedEntity. Raises ValueError on error."""
    ...
```

---

## Pipeline changes (`pipeline/orchestrator/pipeline.py`)

### `_analyse_claim`

The current signature is `entity_name: str`. This change corrects it to `entity_name: str | None`, which also fixes a latent type mismatch: `research_claim` already passes `None` at line 678 (`await _analyse_claim(None, claim_text, ...)`). Add the `resolved_entity` parameter at the same time:

```python
async def _analyse_claim(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
    cfg: VerifyConfig,
    resolved_entity: ResolvedEntity | None = None,
) -> AnalystOutput | None:
```

When `resolved_entity` is provided:
- Call `build_analyst_prompt(entity_name, claim_text, sources, resolved_entity=resolved_entity)`.
- Run `verdict_only_agent` (new, `output_type=VerdictAssessment`) instead of `analyst_agent`.
- Wrap result into `AnalystOutput` with a synthetic `EntityResolution` populated from `resolved_entity` fields. This keeps all downstream code (`_audit_claim`, `_write_claim_file`) unmodified.

```python
entity_resolution = EntityResolution(
    entity_name=resolved_entity.entity_name,
    entity_type=resolved_entity.entity_type,
    entity_description=resolved_entity.entity_description,
    aliases=resolved_entity.aliases,
)
return AnalystOutput(entity=entity_resolution, verdict=verdict_assessment)
```

### `verify_claim`

Add optional parameter:

```python
async def verify_claim(
    entity_name: str,
    claim_text: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    sem: asyncio.Semaphore | None = None,
    resolved_entity: ResolvedEntity | None = None,
) -> VerificationResult:
```

When `resolved_entity` is provided, pass `resolved_entity.entity_name` as the entity hint to `_research()`, and pass `resolved_entity` to `_analyse_claim()`.

`dr onboard` calls `verify_claim(entity_name, claim_text, ...)` without the new parameter. No change to `dr onboard` or `onboard_entity`.

### `research_claim`

Add optional parameter:

```python
async def research_claim(
    claim_text: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    sem: asyncio.Semaphore | None = None,
    resolved_entity: ResolvedEntity | None = None,
) -> VerificationResult:
```

When `resolved_entity` is provided:
- Pass `resolved_entity.entity_name` to `_research()`.
- Pass `resolved_entity` to `_analyse_claim()`.
- Skip `_write_entity_file` entirely.
- Use `resolved_entity.entity_ref` as the entity path for `_write_claim_file`.

### `_write_entity_file` call site

The current call site is at `pipeline.py` lines 688--694. Replace it with:

```python
# Skip when entity is pre-resolved (file already exists on disk).
if resolved_entity is None:
    entity_ref = _write_entity_file(
        entity_name=analyst_out.entity.entity_name,
        entity_type=analyst_out.entity.entity_type,
        entity_description=analyst_out.entity.entity_description,
        repo_root=repo_root,
        aliases=analyst_out.entity.aliases or None,
    )
else:
    entity_ref = resolved_entity.entity_ref
```

---

## Analyst prompt changes (`pipeline/analyst/agent.py`)

### New `verdict_only_agent`

```python
verdict_only_agent = Agent(
    "test",
    output_type=VerdictAssessment,
    system_prompt=_INSTRUCTIONS,
    retries=2,
)
```

Same instructions as `analyst_agent`. The `output_type=VerdictAssessment` at the schema level enforces verdict-only output; the pre-resolved entity block in the user prompt reinforces it. The `"test"` placeholder is the existing convention for `analyst_agent` (line 51 of `agent.py`) and is overridden at call time via `agent.override(model=...)`.

### `build_analyst_prompt` extended signature

The current signature is `build_analyst_prompt(entity_name: str | None, claim_text: str, sources: list[dict])`. `entity_resolution.py` is a sibling orchestrator module, so it can be imported normally without a `TYPE_CHECKING` guard. However, a forward-reference string or `TYPE_CHECKING` guard avoids a potential circular import if `agent.py` is ever imported before `entity_resolution.py` is registered:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from orchestrator.entity_resolution import ResolvedEntity

def build_analyst_prompt(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
    resolved_entity: "ResolvedEntity | None" = None,
) -> str:
```

When `resolved_entity` is provided, replace the `## Entity: {entity_name}` header with:

```
## Entity (pre-resolved — do not infer)

Name: {resolved_entity.entity_name}
Type: {resolved_entity.entity_type.value}
Description: {resolved_entity.entity_description}
Aliases: {", ".join(resolved_entity.aliases) if resolved_entity.aliases else "none"}
Parent company: {resolved_entity.parent_company or "none"}

The entity above is authoritative. Produce only a VerdictAssessment.
```

When `resolved_entity` is None, prompt is identical to today.

---

## CLI changes (`pipeline/orchestrator/cli.py`)

### `dr verify-claim`

Change `CLAIM_TEXT` from the first positional argument to the second. Add `ENTITY_REF` as the first required positional:

```python
@main.command("verify-claim")
@click.argument("entity_ref")   # required; use "-" to trigger analyst inference
@click.argument("claim_text")
# ... existing options unchanged ...
def verify_claim_cmd(ctx, entity_ref: str, claim_text: str, ...):
```

The sentinel `-` means "no pre-resolution -- let the analyst infer the entity and create the file if needed." Any other value is parsed as `{type_dir}/{slug}`.

Resolution logic before `asyncio.run`:

```python
resolved_entity = None
if entity_ref != "-":
    from orchestrator.entity_resolution import parse_entity_ref
    from common.content_loader import resolve_repo_root
    repo_root_path = Path(repo_root) if repo_root else resolve_repo_root()
    try:
        resolved_entity = parse_entity_ref(entity_ref, repo_root_path)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
```

Pass `resolved_entity` to `research_claim(...)`. When `resolved_entity` is not None, display entity name in the report immediately (before analyst result is available).

Updated docstring with both forms:
```
dr verify-claim products/chatgpt "ChatGPT excludes frontier models from user data training"
dr verify-claim - "Some AI company makes a sustainability claim"
```

### `dr verify`

`dr verify` already takes `ENTITY CLAIM` as positional arguments, where `ENTITY` is an unvalidated name string. Upgrade `parse_entity_ref` to also be called when the `ENTITY` argument matches the `{type_dir}/{slug}` pattern (contains a `/` and has a recognized type_dir). When it matches, structured entity data overrides the bare name hint.

`dr verify` has no `--repo-root` option, so use `resolve_repo_root()` directly:

```python
# In the dr verify handler, before calling verify_claim:
resolved_entity = None
if "/" in entity:
    from orchestrator.entity_resolution import parse_entity_ref
    from common.content_loader import resolve_repo_root
    try:
        resolved_entity = parse_entity_ref(entity, resolve_repo_root())
    except ValueError:
        pass  # fall back to bare name hint; not an error for dr verify
```

No sentinel needed for `dr verify` -- it is read-only (no writes) so entity creation is irrelevant. Both `products/chatgpt` and `ChatGPT` remain valid inputs.

---

## Persistence changes (`pipeline/orchestrator/persistence.py`)

No changes required. `_DIR_ENTITY_TYPE` is defined independently in `entity_resolution.py` (see above). `_ENTITY_TYPE_DIR` remains the canonical forward map in `persistence.py`.

---

## Test changes

### New: `pipeline/tests/test_entity_resolution.py`

```
TestParseEntityRef::test_valid_company_ref
TestParseEntityRef::test_valid_product_ref
TestParseEntityRef::test_valid_sector_ref
TestParseEntityRef::test_valid_topic_ref
TestParseEntityRef::test_missing_slash_raises
TestParseEntityRef::test_unknown_type_dir_raises
TestParseEntityRef::test_file_not_found_raises
TestParseEntityRef::test_frontmatter_parse_failure_raises
TestParseEntityRef::test_missing_name_raises
TestParseEntityRef::test_aliases_defaults_to_empty_list
TestParseEntityRef::test_parent_company_none_when_absent
```

Each test creates a minimal entity file in `tmp_path/research/entities/{type_dir}/{slug}.md`. No mocking needed.

### Extend: `pipeline/tests/test_agent.py`

```
TestBuildAnalystPrompt::test_with_resolved_entity_emits_pre_resolved_block
TestBuildAnalystPrompt::test_with_resolved_entity_no_inference_instruction
TestBuildAnalystPrompt::test_without_resolved_entity_output_unchanged
```

### Extend: `pipeline/tests/test_orchestrator.py`

```
TestVerifyClaimWithResolvedEntity::test_resolved_entity_passed_to_analyse_claim
TestVerifyClaimWithResolvedEntity::test_resolved_entity_skips_write_entity_file
TestResearchClaimWithResolvedEntity::test_entity_ref_flows_to_write_claim_file
TestResearchClaimWithResolvedEntity::test_write_entity_file_not_called
```

Use `unittest.mock.patch` to verify call behavior. All existing tests pass unchanged (`resolved_entity` defaults to `None`).

### CLI tests (add to `pipeline/tests/test_cli.py`)

The existing file (`pipeline/tests/test_cli.py`) covers `dr ingest` and env/key checks. Add a new standalone class:

```
TestVerifyClaimCLI::test_dash_sentinel_passes_none_resolved_entity
TestVerifyClaimCLI::test_valid_entity_ref_parsed_before_asyncio_run
TestVerifyClaimCLI::test_invalid_entity_ref_raises_usage_error
TestVerifyClaimCLI::test_unknown_type_dir_raises_usage_error
TestVerifyClaimCLI::test_missing_entity_file_raises_usage_error
```

Use Click's `CliRunner` to test the CLI surface directly without running the pipeline.

---

## Documentation changes

### `AGENTS.md` — `dr` command table

Update `dr verify-claim` entry and examples:

```
- `dr verify-claim` -- Run the full pipeline for a claim: find sources, evaluate verdict, write everything to disk.
  First argument is ENTITY_REF: use 'products/chatgpt' to pre-resolve entity from disk (deterministic claim path, skips LLM inference), or '-' to let the analyst infer and create the entity.
```

Update the tooling examples block:
```
uv run dr verify-claim products/chatgpt "ChatGPT excludes frontier models from user data training"
uv run dr verify-claim - "Some new AI product makes a sustainability claim"
```

No architecture doc changes required. The canonical pipeline description (researcher → ingestor → analyst → evaluator) remains accurate. Entity pre-resolution is an operator-supplied input optimization, not a new agent.

---

## Backward compatibility

`dr verify-claim` is a **breaking change** to the CLI signature: `CLAIM_TEXT` moves from the first to the second positional argument. Any scripts calling `dr verify-claim "claim text"` directly must be updated to `dr verify-claim - "claim text"`.

| Invocation | Behavior |
|---|---|
| `dr verify-claim - "claim text"` | Sentinel: analyst infers entity, `_write_entity_file` called (old behavior, new syntax) |
| `dr verify-claim products/chatgpt "claim text"` | New: entity loaded from disk, analyst skips inference |
| `dr verify "ChatGPT" "claim text"` | Unchanged: bare name hint passed to analyst |
| `dr verify products/chatgpt "claim text"` | New: structured entity data parsed and used if type_dir recognized |
| `dr onboard` | Unchanged: `resolved_entity` defaults to `None` throughout |

---

## Verification steps

```bash
# Unit tests
uv run pytest pipeline/tests/test_entity_resolution.py -v
uv run pytest pipeline/tests/test_agent.py -v -k "resolved"
uv run pytest pipeline/tests/test_orchestrator.py -v -k "resolved"
uv run pytest pipeline/tests/ -q  # full suite, confirm no regressions

# CLI error handling
dr verify-claim invalid-no-slash "test claim"
# → UsageError: Invalid entity ref 'invalid-no-slash': expected '{type_dir}/{slug}'

dr verify-claim badtype/foo "test claim"
# → UsageError: Unknown entity type dir 'badtype': must be one of companies, products, sectors, topics

dr verify-claim products/nonexistent "test claim"
# → UsageError: Entity file not found: research/entities/products/nonexistent.md

# Sentinel: analyst infers entity (creation path)
dr verify-claim - "Some AI company makes a sustainability claim"
# → Analyst infers entity; _write_entity_file called if entity is new

# Integration: pre-resolved entity
dr verify-claim products/claude "Claude does not train on conversation data"
# → Claim written to research/claims/claude/; entity file NOT modified; audit sidecar written

# dr verify: structured ref auto-detected
dr verify products/chatgpt "ChatGPT excludes image generation for free users"
# → Structured entity data used; read-only output

# Confirm dr onboard unaffected
dr onboard "Test Entity" --type company
# → Identical behavior to pre-change
```

---

## File summary

| File | Change |
|---|---|
| `pipeline/orchestrator/entity_resolution.py` | New -- `ResolvedEntity`, `parse_entity_ref`, `_DIR_ENTITY_TYPE` (standalone, not imported from persistence) |
| `pipeline/orchestrator/pipeline.py` | Modify -- `verify_claim`, `research_claim`, `_analyse_claim` signatures; fix `entity_name: str | None` type; skip `_write_entity_file` |
| `pipeline/orchestrator/cli.py` | Modify -- `ENTITY_REF` positional (with `-` sentinel) on `dr verify-claim`; auto-detect `type/slug` on `dr verify` |
| `pipeline/analyst/agent.py` | Modify -- `verdict_only_agent`; extend `build_analyst_prompt` |
| `pipeline/orchestrator/persistence.py` | No changes |
| `pipeline/tests/test_entity_resolution.py` | New -- 11 unit tests |
| `pipeline/tests/test_agent.py` | Modify -- 3 new tests |
| `pipeline/tests/test_orchestrator.py` | Modify -- 4 new tests |
| `pipeline/tests/test_cli.py` | Modify -- 5 CLI-level tests in new `TestVerifyClaimCLI` class |
| `AGENTS.md` | Modify -- `dr verify-claim` description and examples |

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-01 | agent (claude-sonnet-4-6) | deep, implementation | Initial draft: entity ref format, `ResolvedEntity` dataclass, pipeline/CLI/analyst/persistence changes, backward compat, full test and verification coverage |
| 2026-05-01 | human (Brandon) | iterated | Changed `--entity` option to required positional `ENTITY_REF`; `-` sentinel triggers analyst inference / entity creation (old behavior); `dr verify` auto-detects `type/slug` format without sentinel; added CLI tests for sentinel and error cases; updated backward compat to call out breaking signature change |
| 2026-05-01 | agent (claude-sonnet-4-6) | implementation | Corrected four inaccuracies against live code: (1) `_DIR_ENTITY_TYPE` defined standalone in `entity_resolution.py` only -- importing from `persistence.py` would violate the no-orchestrator-imports rule; persistence.py section removed; (2) `dr verify` `repo_root_path` snippet now calls `resolve_repo_root()` directly (no `--repo-root` option on that command); (3) `_analyse_claim` type change noted as also fixing a latent `str` vs `str | None` mismatch (already called with `None` from `research_claim`); (4) CLI test section clarifies the 5 new tests are a standalone `TestVerifyClaimCLI` class, not an extension of existing classes |
| 2026-05-01 | agent (claude-sonnet-4-6) | implementation | Implemented all files per plan: `entity_resolution.py` (new), `analyst/agent.py` (`verdict_only_agent` + extended `build_analyst_prompt`), `pipeline.py` (three signature changes + skip-write site), `cli.py` (`ENTITY_REF` positional + `-` sentinel on `verify-claim`; auto-detect on `verify`), `AGENTS.md` (updated command description and examples). 25 new tests across 4 test files (13 entity_resolution + 3 test_agent + 4 test_orchestrator + 5 test_cli); 440 passing, 0 regressions. |
