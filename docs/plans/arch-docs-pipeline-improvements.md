# Plan: Architecture docs and pipeline improvements

**Status**: ready
**Created**: 2026-04-23
**Source**: agent architecture review of `docs/architecture/` and `pipeline/`

Items are grouped by area. Each item is independent unless noted. Open questions that need design decisions first live in [`docs/architecture/open-issues.md`](../architecture/open-issues.md).

---

## 1. Quick wins: dead code and stale references

### 1.1 Delete orphan `pipeline/ingestor/cli.py`

`pipeline/ingestor/cli.py` duplicates the `dr ingest` command (defined in `orchestrator/cli.py`) but is not wired to any entry point in `pyproject.toml`. No tests or scripts reference it.

- Delete the file.

### 1.2 Remove dead package entries from `pyproject.toml`

`pipeline/pyproject.toml` line 31 lists `consistency` and `verify` under `[tool.hatch.build.targets.wheel] packages`. Neither directory exists (likely remnants from before the `auditor` and `orchestrator` renames).

- Remove `"consistency"` and `"verify"` from the packages list.
- Confirm with `uv build --dry-run` or `pip install -e .` that nothing breaks.

---

## 2. AGENTS.md reconciliation

AGENTS.md has three inconsistencies with the current codebase.

### 2.1 Merge the two agent role tables

AGENTS.md has two overlapping tables:

- `## Agent Roles` (Research Lead, Ingestor, Claim Updater, Citation Auditor, Page Builder)
- `## Pipeline Agents` (Researcher, Ingestor, Analyst, Auditor)

"Claim Updater" maps to no pipeline code and is absent from `research-workflow.md` and the glossary. "Researcher", "Analyst", and "Auditor" are absent from the first table.

Replace both with a single table listing each active role, its automation status, and its pipeline package (if any). Use the seven-role list in `research-workflow.md` as the source of truth.

### 2.2 Add `review_onboard` to the checkpoints list

The checkpoint section in AGENTS.md lists `review_sources` and `review_disagreement`. A third checkpoint, `review_onboard`, exists in `pipeline/orchestrator/checkpoints.py` (`CheckpointHandler.review_onboard`, plus CLI and auto-approve implementations) and is shown in the `research-flow.md` onboard diagram. Add it.

### 2.3 Add missing `dr` commands to the CLI table

The CLI section lists `dr verify`, `dr research`, `dr reassess`, `dr ingest`. Three implemented commands are missing: `dr onboard`, `dr lint`, `dr review`. Add them with input/output descriptions matching the existing format.

---

## 3. Pipeline code gaps

### 3.1 Add `SECTOR` to `EntityType`

`content.config.ts` and `pipeline/linter/checks.py` treat `sector` as a valid entity type (see commit `73f40d2`). The pipeline enum was missed.

- Add `SECTOR = "sector"` to `EntityType` in `pipeline/common/models.py`.
- Add `EntityType.SECTOR: "sectors"` to `_ENTITY_TYPE_DIR` in `pipeline/orchestrator/persistence.py`.
- Add `"sector"` to the `--type` choices on `dr onboard` in `pipeline/orchestrator/cli.py`.

### 3.2 Apply `source_type` classification in standalone `dr ingest`

`_classify_source_type()` in `pipeline/orchestrator/persistence.py` (line 73) is only called from `_write_source_files()` (line 150), which is used by `research_claim` and `onboard_entity`. Source files written by `dr ingest` directly skip the classification and get no `source_type` field.

- Move `_classify_source_type()` and its three publisher frozensets into `pipeline/common/` as a shared utility.
- Call it from both `_write_source_files()` and the standalone `dr ingest` write path.
- Update `pipeline/tests/test_classify_source_type.py` imports.

Pairs naturally with 3.1 (both touch `persistence.py`).

---

## 4. Architecture diagrams

`docs/architecture/research-flow.md` has seven Mermaid diagrams. They are individually accurate but fragmented: a contributor reading in order does not build one coherent mental model. Three targeted replacements improve this.

### 4.1 Consolidate claim lifecycle into one state machine

Replace sections 1, 6, and 7 (initiation, publish, recheck) with a single Mermaid `stateDiagram-v2`. States: `draft`, `under_review` (open PR), `published`, `stale` (recheck due), `archived`. Transitions: PR open, PR merge, staleness threshold, `dr research` re-run, archival.

### 4.2 Convert pipeline execution flowchart to a sequence diagram

Section 3 currently shows agents as nodes and checkpoint decisions as diamonds, which blurs the line between automated pipeline and human judgment.

Replace with a Mermaid `sequenceDiagram`. Actors: Operator, Researcher, Ingestor (xN), Analyst, Auditor, Human. The two checkpoint handoffs to Human become visible, and concurrent ingest calls can use `par`/`and` blocks.

### 4.3 Split the sign-off diagram into two zones

Section 5 mixes pipeline-internal pre-PR rejections with post-PR CI and human review gates.

Replace with a two-zone flowchart: "Before PR" (local pipeline checkpoints, `inv check`) and "After PR" (CI gates, human approval, merge). Rejection arrows loop back to their entry zone. The two pipeline-internal rejection boxes currently floating at the bottom move into "Before PR".

---

## 5. Content orientation

### 5.1 Add a "What this is" section to `research-workflow.md`

Add a 3-4 sentence intro above the Content Model table covering: what dangerousrobot.org is, who reads the published claims, and why the structured process exists. The current doc assumes mission context.

### 5.2 Define verdict values in the glossary

`glossary.md` does not distinguish the verdict levels. A contributor choosing between `mostly-true` and `mixed`, or deciding when `unverified` applies vs. having zero sources, has no guidance. Add a "Verdict definitions" section with a one-line rule for each of the 7 verdicts.

### 5.3 Map Citation Auditor to its three tools

`research-workflow.md` describes the Citation Auditor role without noting that its scope is split across three tools:

- `scripts/check-citations.ts`: broken source refs
- `dr lint`: missing fields, orphaned claims, stale recheck dates
- `dr reassess`: verdict re-evaluation against current sources

Add a note or table on the Citation Auditor row showing which tool covers which responsibility. See also [`claim-promotion-audit-rename-verdicts.md`](claim-promotion-audit-rename-verdicts.md) §2 (rename of `dr audit` to `dr reassess`, landed).

### 5.4 Add a "first contribution" walkthrough

Add a short walkthrough (in `research-workflow.md` or `CONTRIBUTING.md`) showing the exact steps a new contributor takes to add a claim about an existing entity: `dr research`, review generated files, open PR, expect these CI checks. Currently a new contributor has to infer this from agent-facing docs.

---

## Dependencies and ordering

- 3.1 and 3.2 both touch `persistence.py`; batch them.
- 4.x items are independent diagram rewrites and can land incrementally.
- 5.3 reads best after 2.1, which fixes the role vocabulary.
