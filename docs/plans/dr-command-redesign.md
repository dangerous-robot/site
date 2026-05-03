# Plan: `dr` CLI command redesign (claim-* namespace)

**Status**: Draft — design complete, implementation ready

---

## Problem

The current `dr` CLI has two naming problems and one missing command:

1. **`verify` vs `verify-claim` are confusingly similar.** Both run the full pipeline; the only difference is whether they write to disk. The names don't surface that distinction.
2. **`verify-claim` produces non-deterministic filenames.** The claim slug is derived from `slugify(analyst_out.verdict.title)` — an LLM output. Re-running `verify-claim` on the same claim may produce a different filename. Template-backed claims (via `onboard`) already solve this correctly by using the template slug as the filename.
3. **No full-pipeline re-run command for existing claims.** Re-running a specific claim requires either `onboard --only <template_slug> --force` (requires knowing the template slug as a separate input) or `step-analyze --write --force` (analyst only, no new research). A command that takes an existing claim path and re-runs the full pipeline is missing.

---

## Design decisions (from conversation 2026-05-03)

- `verify` and `verify-claim` are **hard-removed** (not deprecated). References in docs are updated; references in HISTORY.md are left as historical record.
- New commands share a `claim-*` namespace, consistent with how `step-*` names pipeline steps.
- `claim-refresh` always writes `status: draft` regardless of the existing claim's status — even if the claim was `published`. Resetting to `draft` signals that human review is needed after a pipeline re-run.
- `claim-draft` writes `status: draft` and no `criteria_slug`. The absence of `criteria_slug` is the canonical marker for ad-hoc claims. No new status value is added to the schema.
- `onboard --only <template_slug>` is preserved. It is the create path; `claim-refresh` is the update path. `claim-refresh` on a non-existent file fails with a clear error pointing at `onboard --only`.
- `claim-promote` is interactive: prompts the operator for a template slug, then appends to `research/templates.yaml`.

---

## Command map

| Old command | New command | Change |
|---|---|---|
| `dr verify <entity> <claim_text>` | `dr claim-probe <entity> <claim_text>` | Renamed; dry run, no writes |
| `dr verify-claim <entity_ref> <claim_text>` | `dr claim-draft <entity_ref> <claim_text>` | Renamed; writes `status: draft`, no `criteria_slug` |
| *(missing)* | `dr claim-refresh <entity/claim-slug>` | New; full pipeline re-run on existing claim |
| *(missing)* | `dr claim-promote <entity/claim-slug>` | New; generate template YAML from ad-hoc claim |

`step-*` commands and `onboard` are unchanged.

---

## Slug determinism

`claim-refresh` must produce a deterministic filename. The implementation follows the same pattern `onboard` uses:

1. Call `verify_claim` (no-write) to run the full pipeline.
2. Write the claim file explicitly with `claim_slug = existing_file.stem` (read from the path argument before the pipeline runs).

This avoids modifying `VerifyConfig` or `research_claim`. The LLM-generated title is written to the `title:` frontmatter field as usual; the filename is not derived from it.

---

## `claim-promote` mechanics

Reads the ad-hoc claim file:
- `title` → template `text`, with entity name replaced by `COMPANY` or `PRODUCT` based on entity type
- `topics` → template `topics`
- entity type (from entity file) → template `entity_type`

Then prompts interactively:
```
Template slug (e.g. publishes-sustainability-report): _
Core template? [Y/n]: _
Notes (optional): _
```

On confirmation, appends the new entry to `research/templates.yaml` under `templates:`.

---

## Full-pipeline lifecycle

```
dr onboard company/microsoft                           # create all template claims (first run)
dr onboard company/microsoft --only <template-slug>    # create one template claim (first run, or new template)
dr claim-refresh microsoft/publishes-sustainability-report  # re-run full pipeline on existing claim
dr claim-probe "Microsoft" "Microsoft publishes..."    # dry run, no writes
dr claim-draft company/microsoft "Microsoft does X"   # ad-hoc claim, writes status=draft, no criteria_slug
dr claim-promote microsoft/microsoft-does-x           # promote ad-hoc claim to template
```

---

## Implementation steps

### 0. Prerequisite fix: `_substitute_entity` for sector entities (`pipeline/common/templates.py`)

`_substitute_entity` (templates.py:78-84) falls through to `return text` for any `entity_type` other than `"product"` or `"company"`. Sector templates use `ENTITY` as the placeholder, so without this fix `render_claim_text` passes `"ENTITY has signed AI safety commitments"` to the LLM rather than the sector name.

Add before the final `return text` at line 84:

```python
if template.entity_type == "sector":
    return text.replace("ENTITY", entity_name)
```

This is required for `claim-refresh` correctness on sector claims and also fixes `render_blocked_title` for sectors.

### 1. CLI command renames and removals (`pipeline/orchestrator/cli.py`)

- Remove `verify` command (lines 555-599) and its entry in `_COMMAND_GROUPS` (lines 85-92).
- Remove `verify-claim` command (lines 606-692) and its entry in `_COMMAND_GROUPS`.
- Update `_COMMAND_GROUPS` (lines 85-92) to replace `"verify"` and `"verify-claim"` with `"claim-probe"` and `"claim-draft"`, and add `"claim-refresh"` and `"claim-promote"` to the appropriate group.
- Add `claim-probe`: copy of `verify` body, new name and docstring. Pipeline function called is `verify_claim` (pipeline.py:204).
- Add `claim-draft`: copy of `verify-claim` body, new name. Pipeline function called is `research_claim` (pipeline.py:659). Add CLI `click.echo` warning when no `criteria_slug` will be written.
- Add `claim-refresh`: new command (see §2 below).
- Add `claim-promote`: new command (see §3 below).

### 2. `claim-refresh` command

Signature: `dr claim-refresh <claim_ref>` where `claim_ref` is `entity/claim-slug`.

Steps in the handler:

1. Resolve the claim path via `_resolve_claim_path(claim_ref, claims_dir)` (defined at cli.py:1209; also used by `step-analyze` and `publish`).
2. Fail if the path does not exist: `"claim file not found: {path}. Use dr onboard --only to create it."`.
3. Parse frontmatter using `parse_frontmatter`. Check `fm.get("criteria_slug")`. If absent (or empty string), fail: `"cannot refresh an ad-hoc draft claim. Run dr claim-promote first to create a template, then dr onboard --only to create a template-backed claim."`. Claims with `status: blocked` but a present `criteria_slug` are allowed — the operator intent is "retry with fresh research."
4. Read `entity_ref` from `fm["entity"]`. Load entity via `parse_entity_ref(entity_ref, repo_root)` (entity_resolution.py:73).
5. Reconstruct claim text from the template:
   - `criteria_slug = fm["criteria_slug"]`
   - `templates = load_templates(root)`
   - `template = get_template(templates, criteria_slug)` — note: `get_template` returns `None` on miss (common/templates.py:68-75), not raises. Handle the None case explicitly.
   - If `template is not None`: `claim_text = render_claim_text(template, resolved_entity.entity_name)`
   - If `template is None`: `claim_text = fm["title"]` (same fallback used by `step-analyze` at cli.py:411)
6. Set `claim_slug_for_write = claim_path.stem`.
7. Build `VerifyConfig` from CLI context. Set `force_overwrite=True` (overwrite is always the intent for refresh; no `--force` flag needed).
8. Call `vr = await verify_claim(resolved_entity.entity_name, claim_text, cfg, gate, resolved_entity=resolved_entity)` (pipeline.py:204; signature accepts `resolved_entity=` keyword).
9. Mirror onboard's write pattern (pipeline.py:1216-1262), with three branches:

   **Branch A — threshold-blocked** (`vr.blocked_reason is not None`):
   - Write source files: `source_ids = _write_source_files(vr.source_files, repo_root) if vr.source_files else []`
   - Inherit topics from template (or fall back to `[]`): `inherited_topics = [Category(t) for t in template.topics] if template else []`
   - Write claim file: `_write_claim_file(..., claim_slug=claim_slug_for_write, status="blocked", blocked_reason=vr.blocked_reason, criteria_slug=criteria_slug, force=True)`
   - Write audit sidecar: `_write_audit_sidecar(..., agents_run=["researcher", "ingestor"])`

   **Branch B — analyst failed** (`vr.analyst_output is None` and no blocked_reason):
   - Same source/topic write as Branch A
   - Write claim file with `status="blocked"`, `blocked_reason=BlockedReason.ANALYST_ERROR`
   - Write audit sidecar: `_write_audit_sidecar(..., agents_run=["researcher", "ingestor", "analyst"])`

   **Branch C — success**:
   - Write source files: `source_ids = _write_source_files(vr.source_files, repo_root) if vr.source_files else []`
   - Inherit topics from template if available (with analyst fallback, mirroring pipeline.py:1224-1232): `inherited_topics = [Category(t) for t in template.topics] if template else list(vr.analyst_output.verdict.topics)`
   - Write claim file: `_write_claim_file(title=vr.analyst_output.verdict.title, ..., claim_slug=claim_slug_for_write, source_ids=source_ids, criteria_slug=criteria_slug, status="draft", force=True)` (persistence.py:175)
   - Build sources consulted: `sidecar_sources = _build_sources_consulted(vr.source_files)`
   - Write audit sidecar: `_write_audit_sidecar(claim_path=claim_path, comparison=vr.consistency, ..., agents_run=["researcher", "ingestor", "analyst", "auditor"], ...)`

Config: `force_overwrite` is always `True` for `claim-refresh`. No `--force` flag exposed.

### 3. `claim-promote` command

Signature: `dr claim-promote <claim_ref>`.

Steps:
1. Resolve and parse claim file. Fail if `criteria_slug` is already set: `"claim is already template-backed (criteria_slug: {criteria_slug}). Nothing to promote."`.
2. Load entity file via `parse_entity_ref` to get `entity_type`.
3. Replace entity name in title with the type-appropriate placeholder to produce template `text`:
   - `company`: `template_text = fm["title"].replace(entity_name, "COMPANY")`
   - `product`: `template_text = fm["title"].replace(entity_name, "PRODUCT")`
   - `sector`: `template_text = fm["title"].replace(entity_name, "ENTITY")`
4. Print proposed template fields to terminal.
5. Prompt: `Template slug:`, `Core template? [Y/n]:`, `Notes (optional):`.
6. Validate slug is unique in `research/templates.yaml` (load via `load_templates`, check for collision).
7. Append to `research/templates.yaml` under `templates:` using this field order (matching existing entries in research/templates.yaml):

```yaml
  - slug: <slug>
    text: "<template text with COMPANY/PRODUCT placeholder>"
    entity_type: <company|product|sector>
    topics: [<topic1>]
    core: <true|false>
    notes: "<operator-supplied notes>"
```

`vocabulary` is omitted unless the promoted claim's title contains a controlled-value slot — not prompted for interactively in v1.
8. Print: `"Template written. Run: dr onboard {entity_ref} --only {slug} --force"`.

---

## Scope decisions

- `_COMMAND_GROUPS` write-semantics labels in `cli.py` (lines 85-92) need updating to reflect new command names.
- The pipeline functions `verify_claim` and `research_claim` in `pipeline.py` are **not renamed**. Only the CLI entry-point commands change.
- `onboard --only` is unchanged in behavior and signature.
- No changes to `content.config.ts` schema (no new status values).

---

## Non-goals

- Bulk refresh across all claims for an entity (future `dr claim-refresh-all` or background job).
- Interactive diff of old vs new claim content after a refresh.
- Automated promotion of ad-hoc claims to templates via LLM suggestion.

---

## Verification

1. `dr claim-probe` runs the full pipeline in memory and prints the verdict; no files written.
2. `dr claim-draft company/microsoft "..."` writes a claim file with `status: draft` and no `criteria_slug`. CLI prints a warning that the claim is not template-backed.
3. `dr claim-refresh microsoft/publishes-sustainability-report` on an existing template-backed claim writes a new version to the same path with `status: draft`, regardless of previous status. Audit sidecar is updated.
4. `dr claim-refresh` on a non-existent path exits with a clear error and `onboard --only` suggestion.
5. `dr claim-refresh` on an ad-hoc draft exits with a clear error and `claim-promote` suggestion.
6. `dr claim-refresh` on a claim where the rerun is blocked writes a `status: blocked` placeholder to the same path (no silent failure).
7. `dr claim-promote microsoft/some-ad-hoc-claim` interactively writes a new entry to `research/templates.yaml` and prints the follow-up `onboard --only` command.
8. `dr verify` and `dr verify-claim` exit with `No such command` (hard-removed).
9. Smoke tests pass for `claim-probe`, `claim-draft`, `claim-refresh`, `claim-promote`.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-05-03 | agent (claude-sonnet-4-6) | initial draft | Design walk from conversation. Captures command map, slug-determinism approach, claim-promote mechanics, implementation steps, and open questions. |
| 2026-05-03 | Brandon | decisions | Resolved open questions: (1) claim-refresh allowed on blocked claims; (2) claim-promote writes YAML from scratch using field order slug/text/entity_type/topics/core/notes. Removed open questions section. |
| 2026-05-03 | agent (claude-sonnet-4-6) | architecture/code review | Verified all function signatures, line numbers, and call patterns against actual source. Corrected claim-refresh write pattern to mirror onboard (3 writes: sources, claim, sidecar); added three failure branches (blocked/analyst-error/success); corrected get_template None-return behavior; corrected _COMMAND_GROUPS line reference; added topics-inheritance note; removed stale test/doc sub-sections (belong in separate plan). |
