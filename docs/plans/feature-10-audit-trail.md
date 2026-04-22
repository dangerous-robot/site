# Plan: AI Research Audit Trail

**Phase**: 4.8
**Status**: ready
**Depends on**: Phase 4.7 (entity-views IA)

---

## Goal

Write a structured sidecar file alongside each new claim file when the pipeline runs. Surface that data on the claim detail page as a collapsible "Research process" section showing pipeline provenance, analyst/auditor agreement, and human review status. The feature's trust signal is the human review indicator: when `human_review.reviewed_at` is non-null, readers can see that a human verified the pipeline's work. When it is null, the indicator reads "Pending human review" — the feature must ship with an enforced path for setting this field, or "Pending" becomes the permanent default.

---

## Terminology

- **Sidecar**: the `.audit.yaml` file paired with a claim `.md` file at the same path stem
- **Audit trail**: the full provenance record written by `_write_audit_sidecar`
- **Analyst verdict**: the verdict written by the analyst agent, stored in claim frontmatter as `verdict`
- **Auditor verdict**: the independent verdict from `ComparisonResult.assessed_verdict`
- **`dr review`**: new CLI subcommand in `pipeline/orchestrator/cli.py` that sets `human_review.reviewed_at`

---

## Scope decisions

- **Option B (sidecar) is the architecture.** Each claim at `research/claims/{entity}/{slug}.md` gets `research/claims/{entity}/{slug}.audit.yaml`.
- **Option B1 (custom Astro loader)** replaces the built-in `glob` loader for `claims`. Two code paths: sidecar present, sidecar absent. Pinned to Astro 6.x content layer API — flag for review on any Astro major version bump.
- **Sidecar files are committed to git alongside their claim files in the same PR.** Not gitignored. A fresh CI checkout must include sidecar files for the audit section to render. If a sidecar is gitignored, the build is correct locally but silently omits audit sections in CI.
- **Malformed sidecar behavior: skip with warning.** A YAML parse error in any `.audit.yaml` file must not break the build. The loader wraps sidecar reads in `try/catch`, emits `console.warn` with the path and error, sets `audit: undefined` for the affected entry, and continues. This is the decision; it must not be relitigated during implementation.
- **Phase 1 is new claims only.** Existing claims render without an audit section. No "Pending" placeholder for claims without sidecars.

---

## Non-goals

- Backfill of existing 51 claims (Phase 2)
- Extended audit fields: `auditor_reasoning`, `evidence_gaps`, URL ingest counts (Phase 2)
- Append-only history log for rechecks (Phase 3)
- Parallel pipeline runs or sidecar locking

---

## Architecture (overview)

```
research/claims/ecosia/renewable-energy-hosting.md
research/claims/ecosia/renewable-energy-hosting.audit.yaml   ← new in Phase 1
```

Pipeline writes `_write_audit_sidecar()` after the auditor step in both `research_claim()` and `onboard_entity()`. Astro custom loader reads the paired sidecar for each `.md` file at build time. The claim page renders a `<details class="audit-trail">` block when `claim.data.audit` is defined.

Data flow:
1. `pipeline/orchestrator/pipeline.py` → `_write_audit_sidecar()` in `pipeline/orchestrator/persistence.py`
2. `pipeline/orchestrator/cli.py` → `dr review` subcommand → `_write_audit_sidecar()` (partial update)
3. `src/content.config.ts` → custom loader → merges sidecar into `claim.data.audit`
4. `src/pages/claims/[...slug].astro` → renders `<details class="audit-trail">` if `claim.data.audit` is defined

---

## Phase 1: Sidecar infrastructure and UI (MVP)

### Schema (sidecar file format)

File path mirrors the claim exactly, replacing `.md` with `.audit.yaml`:

```yaml
schema_version: 1
pipeline_run:
  ran_at: "2026-04-22T14:32:00Z"   # ISO 8601 UTC; datetime of _write_audit_sidecar call
  model: "claude-opus-4-5"          # from VerifyConfig.model
  agents:
    - researcher
    - ingestor
    - analyst
    - auditor
sources_consulted:
  - id: "2026/ecosia-homepage"
    url: "https://ecosia.org"
    title: "Ecosia"
    ingested: true
audit:
  analyst_verdict: "true"           # ComparisonResult.primary_verdict.value
  auditor_verdict: "true"           # ComparisonResult.assessed_verdict.value
  analyst_confidence: "high"        # ComparisonResult.primary_confidence.value
  auditor_confidence: "high"        # ComparisonResult.assessed_confidence.value
  verdict_agrees: true              # ComparisonResult.verdict_agrees
  confidence_agrees: true           # ComparisonResult.confidence_agrees
  needs_review: false               # ComparisonResult.needs_review
human_review:
  reviewed_at: null                 # null until dr review runs; ISO 8601 date string when set
  reviewer: null                    # email or name of reviewer
  notes: null                       # optional free text
```

If `comparison` is `None` (auditor step failed or was skipped), write `audit: null`. The UI shows "Auditor check unavailable" rather than omitting the section entirely, since the pipeline run and sources are still recorded.

`schema_version: 1` is required from Phase 1. It is the migration signal for Phase 3's format change from a flat object to a list of entries.

### Pipeline changes

**New function in `pipeline/orchestrator/persistence.py`:**

```python
def _write_audit_sidecar(
    claim_path: Path,
    comparison: ComparisonResult | None,
    model: str,
    ran_at: datetime.datetime,       # passed in by caller, not computed here — allows test injection
    sources_consulted: list[dict],   # list of {id, url, title, ingested}
    agents_run: list[str],
) -> Path:
    """Write the audit sidecar alongside a claim file. Returns the sidecar path."""
```

`ran_at` is computed at the call site and passed in, not computed inside `_write_audit_sidecar`. This allows tests to inject a fixed timestamp for reproducible assertions.

The sidecar path is derived as `claim_path.with_name(claim_path.stem + '.audit.yaml')` — i.e., same directory, stem + `.audit.yaml`. Note: `with_suffix('').with_suffix('.audit.yaml')` raises `ValueError` for multi-part extensions and must not be used. This function does not call `_write_claim_file`; it is a parallel write with no dependency on the claim file's contents.

If `comparison is None`, the `audit` block is written as a YAML null scalar, not omitted.

**Call site in `research_claim()` (`pipeline/orchestrator/pipeline.py`):**

The current function writes the claim file at lines 452-463, then runs the auditor at lines 465-470. The sidecar write must occur **after** the auditor runs, not before, because `comparison` does not exist until line 470.

Add the call after line 470 (`result.consistency = comparison`):

```python
claim_path = _write_claim_file(...)           # line 452-463 (unchanged)
# ... auditor runs ...
comparison = result.consistency               # line 470

sidecar_sources = _build_sources_consulted(result.source_files)
_write_audit_sidecar(
    claim_path=claim_path,
    comparison=comparison,
    model=cfg.model,
    ran_at=datetime.datetime.now(datetime.timezone.utc),
    sources_consulted=sidecar_sources,
    agents_run=["researcher", "ingestor", "analyst", "auditor"],
)
```

The variable `claim_path` must be captured from the return value of `_write_claim_file` — currently the call at line 452 discards the return value. Change that call to `claim_path = _write_claim_file(...)`.

**Call site in `onboard_entity()` (`pipeline/orchestrator/pipeline.py`):**

`claim_path` is already captured at line 655. `vr.consistency` (a `ComparisonResult | None`) is available after `verify_claim` returns. Add the sidecar write inside the per-template try block, after line 667:

```python
claim_path = _write_claim_file(...)           # line 655 (unchanged)
result.claims_created.append(...)             # line 667

sidecar_sources = _build_sources_consulted(vr.source_files)
_write_audit_sidecar(
    claim_path=claim_path,
    comparison=vr.consistency,
    model=cfg.model,
    ran_at=datetime.datetime.now(datetime.timezone.utc),
    sources_consulted=sidecar_sources,
    agents_run=["researcher", "ingestor", "analyst", "auditor"],
)
```

**Helper `_build_sources_consulted()`** (private, same module):

Takes `list[tuple[str, SourceFile]] | None`, returns `list[dict]`. Each dict: `{id: sf.year/sf.slug, url: url, title: sf.frontmatter.title, ingested: True}`. Returns empty list if input is None or empty. `VerificationResult.source_files` is confirmed as `list[tuple[str, SourceFile]]` (line 49 of `pipeline.py`), where the tuple's first element is the URL string — this is the input to this function at both call sites.

**`_write_audit_sidecar` import** must be added to the `from orchestrator.persistence import ...` block in both `research_claim` and `onboard_entity`.

### `dr review` CLI command (judge condition 1)

**Required in Phase 1.** Without this, `human_review.reviewed_at` is always null and the trust signal never resolves.

Add a `review` subcommand to `pipeline/orchestrator/cli.py`:

```
dr review --claim <entity-slug>/<claim-slug> [--reviewer <name>] [--notes <text>]
```

Behavior:
1. Resolves claim path: `research/claims/<entity-slug>/<claim-slug>.md`
2. Resolves sidecar path: same stem with `.audit.yaml`
3. If sidecar does not exist, exits with error: "No audit sidecar found. Run the pipeline first."
4. Reads the sidecar, sets `human_review.reviewed_at = today` (ISO 8601 date, not datetime), `human_review.reviewer = <value from --reviewer or git config user.email>`, `human_review.notes = <value from --notes or null>`.
5. Writes the updated sidecar back to disk (full overwrite of the file, preserving all other fields).
6. Prints: `Marked reviewed: research/claims/<entity-slug>/<claim-slug>.audit.yaml`

The `review` command reads and writes only the `.audit.yaml` file. It does not touch the `.md` file. The sidecar is written using `yaml.safe_load` / `yaml.safe_dump` — YAML comments and custom key ordering are not preserved. Sidecar files are machine-written and not intended for hand-editing; `dr review` is the only supported path for setting `human_review` fields.

Example:
```
dr review --claim ecosia/renewable-energy-hosting --reviewer brandon@faloona.net
```

### Astro loader changes

Replace the built-in `glob` loader for `claims` in `src/content.config.ts` with a custom loader. The existing `glob` loader for `sources` and the `file` loader for `standards` are unchanged.

The loader logic, approximately 40-60 lines:

1. Walk `research/claims/**/*.md` (exclude `*.audit.yaml` from the walk).
2. For each `.md` file, derive the sidecar path: same stem + `.audit.yaml`.
3. Read and parse the `.md` file (frontmatter + body) — same as the existing `glob` loader behavior.
4. Attempt to read and `js-yaml` parse the sidecar. Wrap in `try/catch`:
   - `FileNotFoundError` (ENOENT): set `audit = undefined`, no warning.
   - YAML parse error: set `audit = undefined`, emit `console.warn(\`[claims loader] malformed sidecar: ${auditPath} — ${err.message}\`)`.
5. Return the collection entry with `data.audit = parsedAudit ?? undefined`.

The loader is pinned to the Astro 6.x content layer API. If Astro releases a major version, the loader binding must be reviewed before upgrading.

**Zod schema extension** (add to `claims` collection schema in `src/content.config.ts`):

```typescript
const auditSchema = z.object({
  schema_version: z.number(),
  pipeline_run: z.object({
    ran_at: z.coerce.date(),
    model: z.string(),
    agents: z.array(z.string()),
  }),
  sources_consulted: z.array(z.object({
    id: z.string(),
    url: z.string().url(),
    title: z.string(),
    ingested: z.boolean(),
  })),
  audit: z.object({
    analyst_verdict: z.string(),
    auditor_verdict: z.string(),
    analyst_confidence: z.string(),
    auditor_confidence: z.string(),
    verdict_agrees: z.boolean(),
    confidence_agrees: z.boolean(),
    needs_review: z.boolean(),
  }).nullable(),
  human_review: z.object({
    reviewed_at: z.coerce.date().nullable(),
    reviewer: z.string().nullable(),
    notes: z.string().nullable(),
  }),
});
```

Add `audit: auditSchema.optional()` to the existing `claims` schema object. All current claims that have no sidecar produce `data.audit === undefined` — the schema passes, and the UI omits the section.

### UI

Add a `<details class="audit-trail">` block in `src/pages/claims/[...slug].astro`, positioned between the Sources section (line 104) and the Review cadence section (line 106). Renders only when `claim.data.audit` is defined.

Collapsed summary line: "Research process: {date}, {model}" using `claim.data.audit.pipeline_run.ran_at` and `claim.data.audit.pipeline_run.model`.

Expanded content — three sub-sections:

**Sources**: compact list, one item per `sources_consulted` entry: title + ingested/not-ingested indicator.

**Verdict check**: two rows:
- "Analyst: {analyst_verdict} ({analyst_confidence})"
- "Auditor: {auditor_verdict} ({auditor_confidence})"

If `audit.audit` is null (auditor failed): show "Auditor check unavailable."
If `audit.audit.verdict_agrees` is true: green indicator.
If false: yellow flag.
If `audit.audit.needs_review` was true: add "Flagged for human review" in muted text below.

**Human review**: 
- If `human_review.reviewed_at` is non-null: show the date and reviewer name.
- If null: show "Pending human review" in muted text.

Style using existing CSS variables and the `.confidence-details` pattern already in `[...slug].astro`.

### Acceptance criteria

- [ ] `pipeline/orchestrator/persistence.py` has `_write_audit_sidecar()` and `_build_sources_consulted()`.
- [ ] `dr research` writes a `.audit.yaml` sidecar alongside the claim file after the auditor step runs.
- [ ] `dr onboard` writes a `.audit.yaml` sidecar for each claim created after the auditor step.
- [ ] Sidecar path is `{claim_stem}.audit.yaml` in the same directory as the claim.
- [ ] If `comparison is None`, sidecar is still written with `audit: null`.
- [ ] `dr review --claim ecosia/renewable-energy-hosting` sets `human_review.reviewed_at` to today's date and writes the sidecar without touching the `.md` file.
- [ ] `dr review` with no existing sidecar exits non-zero with a clear error.
- [ ] `npm run build` succeeds with a mix of claims that have sidecars and claims that do not.
- [ ] A YAML parse error in any single sidecar emits `console.warn` and does not break the build.
- [ ] Claim pages with a sidecar render the `<details class="audit-trail">` block.
- [ ] Claim pages without a sidecar render normally with no audit section and no placeholder text.
- [ ] When `human_review.reviewed_at` is set, the UI shows the date and reviewer.
- [ ] When `human_review.reviewed_at` is null, the UI shows "Pending human review."
- [ ] Tests for `_write_audit_sidecar`: one test with a valid `ComparisonResult` (assert all fields written, assert sidecar path derived correctly), one with `comparison=None` (assert `audit: null` written), one with a fixed injected `ran_at` timestamp (assert round-trips).
- [ ] Tests for `dr review`: sets `reviewed_at` to today, preserves all existing fields, exits non-zero with error on missing sidecar.
- [ ] Astro loader test fixtures (required before shipping, not just before Phase 2):
  - Fixture with a valid sidecar: assert `claim.data.audit` is defined and `schema_version` is correct.
  - Fixture with no sidecar: assert `claim.data.audit === undefined` and build succeeds.
  - Fixture with a malformed YAML sidecar: assert `console.warn` fires with the sidecar path, `claim.data.audit === undefined`, build succeeds.

---

## Phase 2: Extended data and backfill

### What's added

**Extended sidecar schema** — new fields in `pipeline_run` and `audit` blocks:

```yaml
pipeline_run:
  urls_found: 6           # len(result.urls_found)
  urls_ingested: 4        # len(result.urls_ingested)
  urls_failed: 2          # len(result.urls_failed)
audit:
  auditor_reasoning: "..."    # ComparisonResult.reasoning
  evidence_gaps:
    - "..."                    # ComparisonResult.evidence_gaps
```

`auditor_reasoning` and `evidence_gaps` come from `ComparisonResult.reasoning` and `ComparisonResult.evidence_gaps`, both already available at the `_write_audit_sidecar` call site. Thread them through the function signature.

**Backfill script** at `pipeline/scripts/backfill_audit_sidecars.py`: iterates `research/claims/**/*.md`, skips any claim that already has a `.audit.yaml`, writes a partial sidecar with `schema_version: 1`, `pipeline_run.ran_at: null`, and `backfill: true` flag. The UI renders "Partial audit record" when `backfill: true` rather than showing fabricated data.

**UI addition**: "Auditor reasoning" sub-section in the expanded `<details>` block, rendered only when `audit.audit.auditor_reasoning` is defined.

### Conditions that must be met before starting Phase 2

**Judge condition 3: build-time staleness check.** Before Phase 2 ships, add a check in the Astro custom loader (or a CI step) that compares `claim.data.verdict` against `claim.data.audit.audit.analyst_verdict` and emits a build error when they disagree. The check runs only when both values are present — a missing sidecar is not an error in Phase 1. This check is what makes the audit trail trustworthy rather than decorative: it catches manual edits to a claim's verdict that were not followed by a pipeline rerun.

**Judge condition 4: orphan sidecar prevention.** Before Phase 2 ships, add a CI check or pre-commit hook that:
- Verifies every `.audit.yaml` has a matching `.md` at the same path stem (catches renamed or deleted claim files that left orphaned sidecars).
- The inverse check (every `.md` without a sidecar is genuinely new) is advisory only in Phase 2 — required in Phase 3 when all claims are expected to have sidecars.

Both checks can be a single script at `scripts/check-audit-pairs.ts` run in CI.

### Acceptance criteria

- [ ] `_write_audit_sidecar` accepts and writes `urls_found`, `urls_ingested`, `urls_failed`, `auditor_reasoning`, `evidence_gaps`.
- [ ] Backfill script writes partial sidecars for all claims that lack one; existing sidecars are not touched.
- [ ] UI renders auditor reasoning when present.
- [ ] UI renders "Partial audit record" for backfilled sidecars.
- [ ] Build-time staleness check fails the build when `claim.data.verdict` disagrees with `audit.analyst_verdict` on a claim that has a full sidecar.
- [ ] CI check script catches an `.audit.yaml` with no matching `.md`.

---

## Phase 3: Append-only recheck history

### What's added

Converts the sidecar from a single-run record to a list of `audit_entries`. Each pipeline recheck appends a new entry. `schema_version: 3` signals this format change.

```yaml
schema_version: 3
audit_entries:
  - ran_at: "2026-04-22T14:32:00Z"
    model: "claude-opus-4-5"
    analyst_verdict: "true"
    auditor_verdict: "true"
    verdict_changed_from_previous: false
    human_review:
      reviewed_at: "2026-04-23"
      reviewer: "brandon@faloona.net"
  - ran_at: "2026-07-01T09:15:00Z"
    model: "claude-opus-4-5"
    analyst_verdict: "mixed"
    auditor_verdict: "mostly-true"
    verdict_changed_from_previous: true
    human_review:
      reviewed_at: null
```

The claim frontmatter `verdict` is always the current (latest) value. The sidecar provides the history. `_write_audit_sidecar` becomes a read-modify-append operation: read existing sidecar, append new entry, write. Migration from `schema_version: 1` to `schema_version: 3` is handled by a one-time migration script.

UI: renders latest entry's details in the collapsed panel with a "View history" toggle revealing prior entries.

### Conditions that must be met before starting Phase 3

- Phase 2 acceptance criteria all pass.
- Orphan check passes cleanly for all claims (no `.audit.yaml` without a matching `.md`).
- A migration script for `schema_version: 1` → `schema_version: 3` is written and tested before any existing sidecars are converted.

### Acceptance criteria

- [ ] New pipeline runs append to `audit_entries` rather than overwriting.
- [ ] `schema_version: 3` is written on first append.
- [ ] `verdict_changed_from_previous` is computed correctly.
- [ ] UI renders latest entry in collapsed state.
- [ ] "View history" toggle renders all prior entries.
- [ ] `schema_version: 1` sidecars are migrated correctly by the migration script.
- [ ] Migration script is idempotent.

---

## File plan

### New files

| File | Purpose |
|------|---------|
| `pipeline/scripts/backfill_audit_sidecars.py` | Phase 2: write partial sidecars for existing claims |
| `scripts/check-audit-pairs.ts` | Phase 2: CI check for orphaned or missing sidecars |

### Edited files

| File | Change |
|------|--------|
| `pipeline/orchestrator/persistence.py` | Add `_write_audit_sidecar()`, `_build_sources_consulted()` |
| `pipeline/orchestrator/pipeline.py` | Capture `claim_path` return value from `_write_claim_file`; add `_write_audit_sidecar` calls after auditor in `research_claim()` and `onboard_entity()`; add import |
| `pipeline/orchestrator/cli.py` | Add `dr review` subcommand |
| `src/content.config.ts` | Replace `glob` loader for `claims` with custom loader; add `auditSchema` and `audit: auditSchema.optional()` to claims schema |
| `src/pages/claims/[...slug].astro` | Add `<details class="audit-trail">` block and styles |

---

## Execution (Phase 1)

Recommended order:

1. **`persistence.py`**: Write `_write_audit_sidecar()` and `_build_sources_consulted()`. Write tests (valid `ComparisonResult`, null comparison, sidecar path derivation). No pipeline changes yet — function is dead code until step 2.

2. **`pipeline.py`**: Capture `claim_path` from `_write_claim_file` in `research_claim` (currently discarded). Add `_write_audit_sidecar` call after auditor step (after line 470, not after line 463). Add `_write_audit_sidecar` call in `onboard_entity` after line 667. Add import.

3. **`cli.py`**: Add `dr review` subcommand. Test against a hand-written `.audit.yaml` fixture.

4. **`content.config.ts`**: Write custom loader. Test `npm run build` with one claim that has a sidecar fixture and verify `claim.data.audit` is defined. Test with a malformed sidecar and verify `console.warn` fires and build does not fail.

5. **`[...slug].astro`**: Add `<details class="audit-trail">` block. Verify rendering with `claim.data.audit` defined and undefined. Style to match existing `.confidence-details` pattern.

6. Manual integration test: run `dr onboard "Test Entity" --type company` against a real entity, verify `.audit.yaml` is written, verify `npm run build` succeeds, verify the audit section renders on the claim page, verify `dr review` sets `reviewed_at` and the UI updates.

---

## Open questions (carry-forward)

1. **`dr review` reviewer default**: **Decision: fall back to `git config user.email`, fail explicitly if that also returns empty.** The command runs `git config user.email`; if non-empty, use it as the reviewer default. If `--reviewer` is not passed and `git config` returns empty, the command exits with an error rather than writing `reviewer: null`. This prevents silent null writes while avoiding a mandatory flag for operators who have git configured.

2. **Loader path configurability for research repo split**: `docs/BACKLOG.md:29` notes a possible future research repo split. When that happens, the loader's `research/claims` base path must become configurable rather than hardcoded. Defer until the split is actively planned, but note the coupling point.
