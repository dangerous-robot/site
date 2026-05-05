# Source quality roadmap

> **Superseded**: This plan has been superseded by [`source-quality-robust-roadmap.md`](source-quality-robust-roadmap.md) (2026-05-05). The original is retained for reference. See [`source-quality-agent-review.md`](source-quality-agent-review.md) for the strategic critique that drove the rewrite.

**Status**: Superseded  
**Created**: 2026-05-05  
**Supersedes**: `source-trust-metadata.md` (v1 scope); retires `drafts/source-quality-do-now.md`  
**Survey**: [`source-quality_survey.md`](source-quality_survey.md) — full signal inventory and architectural analysis  

This plan defines the v1 source quality architecture: a verification scale, a simplified source schema, and a confidence cap. It consolidates items from `source-trust-metadata.md` (phases 1–5) and `drafts/source-quality-do-now.md` (groups 2–8) into a single ordered plan.

---

## Design decisions

| # | Decision |
|---|----------|
| 1 | Publish claims with self-reported-only sources. Show `verification_level` to readers as the primary quality signal. |
| 2 | **Soft confidence cap**: `verification_level: claimed` or `self-reported` → `confidence` capped at `low`. Analyst writes the narrative; cap enforced by lint. |
| 3 | v1 backfill is **partial**: only v1 launch sources (~20–50). Full 146+ source backfill is v1.x. |
| 4 | `docs/architecture/source-quality.md` is the single documentation location for source ranking methodology. |
| 5 | `site_trust` is populated only from the publisher-groups registry. Unknown publishers → `site_trust: unknown`. This is not a negative signal. |
| 6 | `document_type` is deferred to v1.x. The `claimed` vs `self-reported` distinction uses the existing `kind` field. |

---

## The verification scale

Single claim-level field, auto-derived from source `independence` + `kind`. The primary reader-facing quality signal.

```
claimed → self-reported → partially-verified → independently-verified → multiply-verified
```

| Level | Meaning | Derivation |
|-------|---------|------------|
| `claimed` | Entity makes marketing assertions; no formal documentation found | All `first-party` sources have `kind` in {blog, index, video, article} |
| `self-reported` | Entity has published formal documentation; no independent sources | ≥1 `first-party` source with `kind` in {report, documentation, dataset}; no `independent` sources |
| `partially-verified` | Mix of first-party documentation and independent sources | Both `first-party` and `independent` present |
| `independently-verified` | At least one independent source corroborates | ≥1 `independence: independent`; may include first-party |
| `multiply-verified` | Multiple independent sources corroborate | ≥2 `independence: independent` |

**`kind` already exists** on all sources (`SourceKind` enum: report, article, documentation, dataset, blog, video, index). No new schema field needed for the `claimed` vs `self-reported` distinction — the analyst derives `verification_level` from `independence` + `kind` together.

---

## Implementation plan

### 1. Architecture doc — single source of truth

Create `docs/architecture/source-quality.md`:
- The verification scale: definitions and derivation rules
- How `independence` is determined (source_type proxy + ingestor judgment)
- The `claimed` vs `self-reported` distinction (first-party + kind mapping)
- Confidence cap rule and lint enforcement
- Publisher registry: what `site_trust` means and what `unknown` means
- Why `site_trust: unknown` is not a negative signal for small publishers

All other plans cross-reference this doc rather than restating the rules.

**Files**: `docs/architecture/source-quality.md` (new)

---

### 2. Source schema — `independence`, `site_trust`, `publisher_group`

**Source frontmatter** (`pipeline/ingestor/models.py`, `src/content.config.ts`):
```yaml
independence: first-party | independent | unknown   # auto from source_type proxy
site_trust: high | medium | low | unknown           # auto from publisher-groups.yaml only
publisher_group: string                             # auto from publisher-groups.yaml
```

**`independence` auto-determination** (ingestor judgment, proxied from existing classification):
- `source_type: primary` → `independence: first-party`
- `source_type: secondary` → `independence: independent`
- `source_type: tertiary` → `independence: unknown`

**`site_trust`**: populated only from the publisher-groups registry (item 4). Domains not in the registry → `site_trust: unknown`. Not a negative signal.

**No `coi_with_subject` field in v1** — `first-party` is treated as implicit COI. Explicit COI fields deferred to v1.x.

**Claim frontmatter** (new field):
```yaml
verification_level: claimed | self-reported | partially-verified | independently-verified | multiply-verified
```
Set by the analyst agent at verdict time. Must be added to the Zod schema in `src/content.config.ts`.

**Files**: `pipeline/ingestor/models.py`, `src/content.config.ts`

---

### 3. Partial backfill — v1 launch sources

Add `independence` to all v1 launch sources. Use `source_type` as the starting point — mostly mechanical. Spot-check and correct misclassifications.

`site_trust` and `publisher_group` are populated by registry lookup (item 4); no additional per-source manual work for those fields.

**Files**: `research/sources/` (per `research/v1-launch-set.md`)

---

### 4. Publisher groups registry

New file: `research/publisher-groups.yaml`. Maps domains to group name + trust level.

```yaml
reuters.com:
  group: Thomson Reuters
  site_trust: high
prnewswire.com:
  group: Cision
  site_trust: low
businesswire.com:
  group: Berkshire Hathaway Media
  site_trust: low
```

Ingestor checks source URL domain against this file and populates `publisher_group` and `site_trust` on match. Uses substring matching (same approach as the blocklist).

**Bootstrap scope**: publishers in the v1 launch source set + major PR wire services (~10–20 entries). Not a comprehensive registry — grows over time.

**Files**: `research/publisher-groups.yaml` (new), ingestor domain-lookup code

---

### 5. Blocklist extension

Extend `research/blocklist.yaml` with:
- PR wire services: prnewswire.com, businesswire.com, globenewswire.com, accesswire.com
- Known content farms and aggregators that republish without original reporting

The publisher-groups registry handles low-trust domains that should score down but not be hard-dropped. The blocklist handles hard drops.

**Files**: `research/blocklist.yaml`

---

### 6. Pre-ingest publisher classification

Apply `source_classification.py` domain patterns at the candidate stage (before scoring, before ingest tokens spent). Inject a `publisher_quality` label per candidate into the scorer prompt as a soft signal. Pairs with the scorer's existing `publisher_quality` hints (landed in `scorer-quality-signals.md`).

**Survey ref**: `source-quality_survey.md` §4; `source-quality-do-now.md` Group 2b  
**Files**: `pipeline/researcher/decomposed.py` or scorer call site

---

### 7. Planner angle guidance

Update planner prompt: instruct the model to include at least one query targeting coverage by parties other than the entity ("independent coverage angle"). Pairs with the `parent_company` injection that already landed.

**Survey ref**: `source-quality_survey.md` §1; `source-quality-do-now.md` Group 3b  
**Files**: planner prompt in `pipeline/researcher/decomposed.py`

---

### 8. Ingestor quality signals

Add to ingestor instructions and `SourceFrontmatter`:
- **Thin content detection**: body below word-count threshold after stripping boilerplate → `thin_content: true`
- **Soft-paywall detection**: "subscribe to continue" body patterns → `soft_paywall: true`

Both are optional fields on existing sources — no validation impact.

Author/byline extraction (`source-quality-do-now.md` Group 4c) deferred to v1.x — adds data without changing filtering behavior; pairs with `authority` which is v1.x.

**Survey ref**: `source-quality_survey.md` §5; `source-quality-do-now.md` Groups 4a, 4b  
**Files**: ingestor instructions, `pipeline/ingestor/models.py`

---

### 9. Analyst instructions + confidence cap

Update analyst instructions to:
- Derive and set `verification_level` from the source pool (`independence` + `kind` mapping per the scale above)
- Cap `confidence` at `low` when `verification_level` is `claimed` or `self-reported`
- Pass `source_type` (primary/secondary/tertiary) into analyst context; note when verdict relies on secondary or tertiary sources
- Use `site_trust: low` and `publisher_group` signals to flag when the source pool is predominantly low-trust publishers
- Narrative for `self-reported`: "The company asserts X and has published documentation; no independent source was found to corroborate."
- Narrative for `claimed`: "The company asserts X; no formal documentation or independent source was found."

**Lint rule**: warn if `confidence: medium|high` and `verification_level: claimed|self-reported`.

**Risk**: this changes existing verdicts. Re-run all v1 claims and review verdict deltas before proceeding to display (item 11).

**Survey ref**: `source-quality_survey.md` §6–7; `source-quality-do-now.md` Group 7a  
**Files**: `pipeline/analyst/instructions.md`, `pipeline/linter/checks.py`

---

### 10. Threshold check improvements

- **6a — blocked-reason taxonomy**: Add `low_quality_sources` to the `blocked_reason` enum. Schema + code change; does not change when blocking occurs — enables future quality gates.
- **6b — non-blocking quality warnings**: After threshold passes on source count, check if the pool is predominantly tertiary or low-trust. Log a non-blocking warning in the claim sidecar.

**Survey ref**: `source-quality_survey.md` §7; `source-quality-do-now.md` Groups 6a, 6b  
**Files**: claim frontmatter schema, `pipeline/pipeline.py` threshold check

---

### 11. Backfill `verification_level` on existing claims

Re-run v1 launch claims (after item 9) to populate `verification_level`. Set manually on any that can't be re-run.

**Files**: `research/claims/` (v1 launch set)

---

### 12. Display — claim page only

No panels, no expand/collapse. Two additions to the claim page:

- **Verification level label**: one line — e.g., `Self-reported` or `Independently verified` — from `verification_level`
- **Source count line**: "N sources (X company-published, Y independent)" — computed from `independence` values

Source detail pages unchanged in v1.

**Files**: claim page component(s) in `src/`

---

### 13. Lint for new sources

`dr lint` warns on missing `independence` for sources with `accessed_date` ≥ 2026-05-01. Grace period exempts older sources.

**Files**: `pipeline/linter/checks.py`

---

## Plan management

### On approval, also:

- **Create** `docs/architecture/source-quality.md` — methodology reference (item 1)
- **Update** `docs/plans/source-trust-metadata.md` — status → `superseded (v1 scope)`; add note that v1 schema is defined here. Full trust block (document_type, authority, coi_with_subject, coi_notes, publisher_group detailed spec) moves to v1.x; phases 6–8 of that plan remain valid v1.x cross-references.
- **Move** `docs/plans/drafts/source-quality-do-now.md` → `docs/plans/completed/`; add note: Groups 1+3a shipped in `scorer-quality-signals.md`; Groups 2a, 2b, 3b, 4a, 4b, 6a, 6b, 7a, 8 incorporated here; Groups 5a, 5b deferred to v1.x.

### Leave unchanged
- `source-quality_survey.md` — reference doc, not a plan
- `research-quality-ideas.md` — idea backlog, not a plan

---

## v1.x

| Item | Prior plan ref | Notes |
|------|----------------|-------|
| `document_type` field on sources | `source-trust-metadata.md` phases 1, 6 | Formalizes the `kind`-to-claimed/self-reported mapping as an explicit schema field |
| `coi_with_subject` + `coi_notes` | `source-trust-metadata.md` | Explicit COI badge; currently implicit from `first-party` |
| `authority` field + author/byline | `source-trust-metadata.md`, do-now 4c | Ingestor schema addition; pairs with authority |
| `site_trust` beyond registry | `source-trust-metadata.md` | Manual or agent-classified for unknown publishers |
| Research trace quality signals | do-now Groups 5a, 5b | Per-query overlap + source type distribution; operator-facing |
| Agent classifier for trust fields | `source-trust-metadata.md` Phase 6 | Full backfill of 146+ sources |
| State machine quality gates | `pipeline-state-machine_stub.md` | Block on `verification_level`, not just count |

---

## Open question

**`claimed` vs `self-reported` boundary using `kind`**: the mapping is clear for `kind: report` (self-reported) and `kind: blog` (claimed). `kind: article` is ambiguous — a first-party article may be a press release (claimed) or a substantive technical piece (self-reported). Resolve at implementation time when writing item 9 (analyst instructions): define whether `article` defaults to `claimed` when `independence: first-party`, or whether the analyst makes a case-by-case call.

---

## Verification

- Source files accept `independence`, `site_trust`, `publisher_group`; existing files pass validation unchanged
- Registry lookup populates `site_trust` + `publisher_group` on matched sources; unmatched → `unknown`
- `thin_content` and `soft_paywall` flags appear on qualifying ingest results
- `dr lint` warns on missing `independence` for sources accessed after 2026-05-01
- `dr lint` warns on `confidence > low` when `verification_level` is `claimed` or `self-reported`
- Claim pages show verification level label + source count breakdown
- All v1 claims have `verification_level` populated and confidence consistent with cap rule
- `docs/architecture/source-quality.md` exists and covers the full methodology

---

## Review history

| Date | Reviewer | Scope |
|------|----------|-------|
| 2026-05-05 | human (Brandon) | Initial design session — verification scale, confidence cap, publisher registry, schema simplification; consolidated from source-trust-metadata.md and source-quality-do-now.md |
