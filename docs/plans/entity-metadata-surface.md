# Plan: Entity metadata surface — `legal_name` + `parent_company` rendering

**Status**: ready
**Created**: 2026-05-09
**Related plans**: `completed/scorer-quality-signals.md` (Item C: parent_company injection into scorer/planner already shipped); `completed/source-quality-robust-roadmap_completed.md` (independence + verification scale); `source-pool-expansion-tier1.md` (sec_cik schema landing); `parent-company-inference.md` (post-v1 automation, not a dependency)
**Promoted from**: `source-quality-followups.md` § Section 5 Bucket 2 (Entity metadata surface)
**Architecture doc**: `docs/architecture/source-quality.md` (amended by this plan)

## Goal

Deliver reader-visible value from the entity metadata bucket: schema → opportunistic backfill → pipeline reads → site rendering, in one plan.

Three reader-visible surfaces appear:

1. **Product entity page** (`/entities/products/<slug>`): "Made by [Anthropic]" linking to the company entity page.
2. **Company entity page** (`/entities/companies/<slug>`): legal name displayed alongside the existing display name; existing `website` field already rendered.
3. **Claim page** (`/claims/<slug>`): "Made by [Anthropic]" near the entity breadcrumb or in the metadata area when the claim's subject resolves to a product whose `parent_company` is populated.

Plus a verification badge on entity pages (all three types) when the entity carries a non-default `verification_status`.

Two new optional fields land on the entity Zod schema and the `ResolvedEntity` / linter mirrors: `legal_name` and `verification_status`. `parent_company` already exists on the schema; this plan is the first to read and render it.

The pipeline-quality half: the analyst instructions reference `legal_name` for COI/disambiguation framing, `parent_company` continues to flow through the scorer (already shipped per `scorer-quality-signals.md` Item C), and the analyst sees `verification_status` when not `verified` so it can weight sparse-evidence claims accordingly. The existing `website` field continues to play the canonical-website / primary-source-disambiguation role; this plan documents that explicitly in the architecture doc rather than adding a parallel `official_website` field.

`verification_status` is operator-set in this plan. The agent that automatically populates it (and the broader enrichment work) lives in [`drafts/entity-onboarding-research_stub.md`](drafts/entity-onboarding-research_stub.md). This plan creates the schema seat and the render surface so that follow-up plan plugs in cleanly.

## Why this scope, this size

The triage row in `source-quality-followups.md` § Section 5 estimates ~1 day. After grounding (see "Exploration" below), realistic effort is **~1.5 days end-to-end** with a viable **~half-day MVP** at schema-and-render-only (Steps 1–4 below). Pipeline-side instruction updates (Steps 5–6) can land as a follow-up commit on the same plan.

The bucket is small but spans four files in `pipeline/` and one Astro template, plus content backfill on five product files. Without the product backfill, "Made by X" has nothing to render — the rendering side and the per-product `parent_company` value have to land together, even though companies stay opportunistically backfilled.

## Exploration grounded in the current tree (verified 2026-05-09)

### What already exists on the entity schema

The Zod entity schema (`src/content.config.ts:219-236`) already carries:


| Field            | Type                                | Status                                                     |
| ------------------ | ------------------------------------- | ------------------------------------------------------------ |
| `name`           | `string`                            | required, display name                                     |
| `type`           | `'company' | 'product' | 'subject'` | required                                                   |
| `website`        | `string().url().optional()`         | **already plays the "official website" role** — see below |
| `aliases`        | `string[]?`                         | optional                                                   |
| `description`    | `string`                            | required                                                   |
| `parent_company` | `regex(/^companies\/[a-z0-9-]+$/)?` | optional,**schema-only today on products**                 |
| `search_hints`   | `{ include?, exclude? }?`           | optional                                                   |
| `sec_cik`        | `regex(/^\d{10}$/)?`                | optional, shipped via`source-pool-expansion-tier1.md`      |

The `ResolvedEntity` dataclass (`pipeline/orchestrator/entity_resolution.py:29-37`) mirrors this. The writer `_entity_frontmatter` (`pipeline/orchestrator/persistence.py:39-58`) emits seven keys (no `sec_cik`, no new fields).

There is **no Pydantic class for entity frontmatter on disk** — the file is parsed via `fm.get(...)` into the `ResolvedEntity` dataclass. The auditor and analyst carry their own `EntityContext` / `EntityResolution` Pydantic models, but those are agent-output contracts, not the on-disk surface. The "lockstep" surfaces that must move together for this bucket are:

- `src/content.config.ts` (Zod, the only on-disk schema)
- `ResolvedEntity` dataclass + `parse_entity_ref` (`pipeline/orchestrator/entity_resolution.py`)
- `_entity_frontmatter` writer (`pipeline/orchestrator/persistence.py:39`)
- `CANONICAL_ENTITY_KEYS` linter set (`pipeline/linter/checks.py:14`)
- `build_entity_context` planner-prompt builder + `build_scorer_prompt` scorer-prompt builder

### What is true about `parent_company` on products

Despite the followups doc stating "all three current product entities have it populated," `grep -l "parent_company" research/entities/products/*.md` returns empty as of 2026-05-09. `parent_company` is on the Zod schema and the linter accepts it, but **no product file carries it today**. This plan backfills all five product files (`claude` → `companies/anthropic`, `chatgpt` → `companies/openai`, `gemini` → `companies/google`, `greenpt` → `companies/greenpt`, `treadlightlyai` → `companies/treadlightlyai` — the latter two have same-named twin company entities, so the parent ref is unambiguous).

That's a one-time, in-scope edit on five files — not a sweep through every entity. The "lazy backfill" rule below applies to `legal_name` on companies, not to `parent_company` on the five products that need to demo the render surface.

### What is true about `website` vs the proposed `official_website`

Decision (2026-05-09, operator): **keep `website`, document its role; do not add `official_website`.** The existing field already plays the role the bucket assigned to `official_website`:

- Scorer prompt (`pipeline/researcher/scorer.py:60`) literally calls it "Official website" and uses it for entity disambiguation: *"when an `Official website` is provided, the entity is the organization at that domain..."*
- Planner-context builder (`pipeline/orchestrator/entity_resolution.py:64-69`) emits `Official website: {website}` and the disambiguation guidance string.
- The Zod schema validates `website` as a URL.

Adding a separate `official_website` field would either rename the working field (a churn-heavy change with no consumer benefit) or split a non-distinction into two near-identical fields that drift over time. The architecture doc amendment in Step 7 makes the dual role explicit so future contributors don't re-propose the rename.

### What lockstep tests exist today

None. There is no test that asserts the Zod schema and the linter's `CANONICAL_ENTITY_KEYS` agree. Adding a small lockstep test for the keys this plan touches is in scope (`pipeline/tests/test_entity_resolution.py` is the natural home).

## Design

### Schema changes (Zod-side, single commit)

Add two new optional fields to the entity Zod schema in `src/content.config.ts:221-235`:

```typescript
const entities = defineCollection({
  loader: glob({ pattern: '**/*.md', base: 'research/entities' }),
  schema: z.object({
    name: z.string(),
    type: z.enum(['company', 'product', 'subject']),
    website: z.string().url().optional(),          // unchanged; doubles as "official website"
    legal_name: z.string().min(1).optional(),       // NEW — COI/disambiguation
    verification_status: z.enum([                   // NEW — applies to all three types
      'verified',
      'unverified-startup',
      'unverified-other',
    ]).optional(),                                  // optional; absent === verified at read time
    aliases: z.array(z.string()).optional(),
    description: z.string(),
    parent_company: z.string().regex(/^companies\/[a-z0-9-]+$/, { /* unchanged */ }).optional(),
    search_hints: z.object({ /* unchanged */ }).optional(),
    sec_cik: z.string().regex(/^\d{10}$/, { /* unchanged */ }).optional(),
  }),
});
```

Validation:

- `legal_name`: `z.string().min(1)`. No format check beyond non-empty — legal names contain commas, periods, "LLC", "Inc.", "Limited", non-Latin scripts, etc.
- Display name (`name`) and `legal_name` may be equal; not enforced disjoint.
- `verification_status`: optional enum. Absence is read as `verified` (no migration needed; existing files round-trip unchanged). The render and analyst layers branch on the resolved value, so they treat absent and explicit `verified` identically.

### `ResolvedEntity` passthrough

Add one field to `ResolvedEntity` (`pipeline/orchestrator/entity_resolution.py:29-37`):

```python
@dataclass
class ResolvedEntity:
    entity_ref: str
    entity_name: str
    entity_type: EntityType
    entity_description: str
    aliases: list[str] = field(default_factory=list)
    parent_company: str | None = None
    website: str | None = None
    legal_name: str | None = None              # NEW
    verification_status: str = "verified"      # NEW; default at parse time
    search_hints: SearchHints | None = None
```

Populated in `parse_entity_ref` (lines 115-124):

```python
return ResolvedEntity(
    ...,
    legal_name=fm.get("legal_name") or None,
    verification_status=fm.get("verification_status") or "verified",
    ...,
)
```

The `or "verified"` fallback resolves the absent / explicit-`verified` cases identically downstream, so the analyst and render layers can branch on a single string.

### Writer + linter mirrors

`_entity_frontmatter` (`pipeline/orchestrator/persistence.py:39-58`) gains:

- `legal_name` emission when populated on the source `ResolvedEntity` — between `website` and `description`.
- `verification_status` emission when not equal to `"verified"` — directly after `type` to keep the operator-facing flag near the top.

Drop `None`-valued keys is already the round-trip behavior of `serialize_frontmatter` (`_clean_for_serialize` at `pipeline/common/frontmatter.py:90-100`), so existing files (which carry neither field) round-trip unchanged. The writer suppressing `verification_status: verified` keeps the default-state files visually identical to today.

**Coexistence with the existing `status` key.** `_entity_frontmatter` already emits a `status` key (`pipeline/orchestrator/persistence.py:56`) for draft entities. `status` is not declared in the Zod schema and is not in `CANONICAL_ENTITY_KEYS` today, so the linter currently warns on it. Step 3b adds `status` to `CANONICAL_ENTITY_KEYS` as a second drive-by fix; the new fields slot in alongside it without restructuring.

**Writer signature change.** `_entity_frontmatter` gains two kwargs: `legal_name: str | None = None` and `verification_status: str = "verified"`. The two callers `_write_entity_file` and `_write_draft_entity_file` (`pipeline/orchestrator/persistence.py:160`, `:528`) gain matching kwargs and pass `resolved_entity.legal_name` / `resolved_entity.verification_status` through. Existing call sites that don't pass the new kwargs round-trip unchanged thanks to the drop-`None` behavior cited above.

This positions the writer for the future onboarding-research agent tracked in [`drafts/entity-onboarding-research_stub.md`](drafts/entity-onboarding-research_stub.md) — without writer support, any future agent that researched `legal_name` or set `verification_status` would have nowhere to write it.

`CANONICAL_ENTITY_KEYS` in `pipeline/linter/checks.py:14`:

```python
CANONICAL_ENTITY_KEYS = {
    "name", "type", "website", "aliases", "description",
    "parent_company", "search_hints",
    "sec_cik",                # FIX: shipped via source-pool-expansion-tier1.md but never added here
    "status",                 # FIX: emitted by _entity_frontmatter for drafts (persistence.py:56) but never added here
    "legal_name",             # NEW
    "verification_status",    # NEW
}
```

`sec_cik` and `status` are bug-fix drive-bys — the linter currently warns "unrecognized entity field" on companies carrying `sec_cik` and on any draft entity emitted via `_write_draft_entity_file`. Mention both in the commit message; not a scope expansion.

### Pipeline reads

#### Analyst instructions (`pipeline/analyst/instructions.md`)

Add a short paragraph in the existing Entity section explaining: *when `legal_name` is provided, the entity name in COI / restatement-test reasoning is the legal name; the display `name` is for narrative prose. Do not invent or speculate when `legal_name` is absent.*

Add a second short paragraph: *when an entity carries `verification_status` other than `verified` (e.g., `unverified-startup`), be conservative about claims that depend on the entity's documented track record. Sparse public coverage is a valid reason to lower confidence, not a reason to manufacture or speculate.*

`build_analyst_prompt` (`pipeline/analyst/agent.py:136-203`) gains:

- a `Legal name: {legal_name}` line in the entity block when populated, immediately after `Aliases:`.
- a `Verification: {verification_status}` line when status ≠ `verified`. Suppressed in the default case to keep prompts identical for the common path.

Roughly six lines of code total.

#### Scorer prompt (`pipeline/researcher/scorer.py:72-101`)

`build_scorer_prompt` already accepts `entity` (display name), `parent_company`, `website`. Pass `legal_name` through as an optional field and emit `Legal name: {legal_name}` in the entity block when populated. Two lines added; instructions text is unchanged (the existing disambiguation guidance keys off `Official website`, which still refers to `website`).

#### `parent_company` (already wired)

`scorer-quality-signals.md` Item C already shipped `parent_company` injection into both the planner-context builder and the scorer prompt. Verify no regression: the scorer instruction at line 57 *"When parent company is provided, sources about the parent company are relevant to claims about the subsidiary"* remains valid. No change to scorer behavior in this plan.

#### `website` as primary-source signal — **deferred enhancement**

`pipeline/common/source_classification.py` classifies sources by publisher-name substring matching. Adding a per-entity domain-match override (e.g., `website: anthropic.com` → sources from `anthropic.com` get `independence: first-party`) is naturally paired with the Phase 6 / Phase 7 trust-block work in `source-quality-followups.md` § Section 3 — it's a classifier extension, not a metadata-plumbing job. Defer.

### Site rendering

The single entity template at `src/pages/entities/[...slug].astro` covers all three entity types. Rendering branches on `entity.data.type` inside that file. **No `<MadeByLink>` component is factored out in v1** — it's three lines of JSX in two locations; graduate to a component if a third surface grows the same pattern.

#### Product entity page

In `src/pages/entities/[...slug].astro`, after the `<p class="description">` line at line 83 inside `<PageHeader>`, add a `<p class="made-by">` block. Compute the resolver in the frontmatter (above the `---`), not as an inline IIFE in the template — the claim template already follows this pattern; the entity template is missing it, and mixing styles is reviewer noise.

The current entity template only loads the single `entity` via `Astro.props`; the collection-level `getCollection("entities")` lives inside `getStaticPaths()` at line 13 and is not in scope in the module body. **Add `getCollection("entities")` to the existing `Promise.all` at lines 23-26** (alongside `claims` and `criteria`) so the parent lookup has the full collection. Build a `Map<id, entity>` once for O(1) lookups (matters more on the claim page below, but mirror it here for consistency):

```astro
---
// existing imports + Astro.props destructure
const [claims, criteria, entities] = await Promise.all([
  getCollection('claims'),
  getCollection('criteria'),
  getCollection('entities'),
]);
const entityMap = new Map(entities.map(e => [e.id, e]));

const titleCaseSlug = (slug: string) =>
  slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const madeBy =
  entity.data.type === 'product' && entity.data.parent_company
    ? {
        href: `/entities/${entity.data.parent_company}`,
        label:
          entityMap.get(entity.data.parent_company)?.data.name ??
          titleCaseSlug(entity.data.parent_company.split('/').pop()!),
      }
    : null;
---
```

Render in the template:

```astro
{madeBy && (
  <p class="made-by">
    Made by <a href={madeBy.href}>{madeBy.label}</a>
  </p>
)}
```

`titleCaseSlug` is the JS mirror of `resolve_parent_name` (`pipeline/orchestrator/entity_resolution.py:40-48`, which calls `.replace("-", " ").title()`). Document the parity in a one-line comment so future contributors don't drift one side. The Zod regex `^companies\/[a-z0-9-]+$` guarantees the ref string has a slug component, so `.split('/').pop()!` is non-null-safe.

#### Company entity page

Same template, branch on `entity.data.type === 'company'`. After the existing `website-link` block, render `legal_name` when present:

```astro
{entity.data.type === 'company' && entity.data.legal_name && entity.data.legal_name !== entity.data.name && (
  <p class="legal-name">Legal name: <span>{entity.data.legal_name}</span></p>
)}
```

Hidden when `legal_name` equals the display `name` to avoid noise. The existing `website` link is unchanged.

#### Verification badge (all entity types)

In the same `src/pages/entities/[...slug].astro`, render a small status row near the top of the page (between `<PageHeader>` description and the type-specific blocks above) when `verification_status` is set and ≠ `verified`:

```astro
{entity.data.verification_status && entity.data.verification_status !== 'verified' && (
  <p class="verification-badge" data-status={entity.data.verification_status}>
    {entity.data.verification_status === 'unverified-startup'
      ? 'Unverified — sparse public documentation (early-stage / startup)'
      : 'Unverified — limited public corroboration'}
  </p>
)}
```

CSS in the same `<style>` block: italic, muted color, small icon optional. Mirror the established legal-name / website-link styling discipline.

This is the entity-page surface only. Showing the verification status on claim pages whose subject is unverified is a render decision deferred to the follow-up plan.

#### Claim page

In `src/pages/claims/[...slug].astro`, the `entities` collection is already loaded at line 32 and `entityEntry` is computed at line 39. Build the same Map-based resolver as the entity page (factor `titleCaseSlug` if you prefer; for v1 duplicating the four-line helper across two files is fine).

In the frontmatter, after `entityLabel` (line 41):

```astro
const entityMap = new Map(entities.map(e => [e.id, e]));

const titleCaseSlug = (slug: string) =>
  slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const madeBy = (() => {
  if (!entityEntry || entityEntry.data.type !== 'product') return null;
  const parentRef = entityEntry.data.parent_company;
  if (!parentRef) return null;
  return {
    href: `/entities/${parentRef}`,
    label:
      entityMap.get(parentRef)?.data.name ??
      titleCaseSlug(parentRef.split('/').pop()!),
  };
})();
```

Render in the `<PageHeader>` body, near `claimCrumbs`:

```astro
{madeBy && (
  <p class="made-by">
    Made by <a href={madeBy.href}>{madeBy.label}</a>
  </p>
)}
```

The branch is `entityEntry.data.type !== 'product'` — claim subjects that are companies, subjects, or unresolved entities are explicitly skipped (no "Made by undefined"). The `entityMap` lookup is O(1) per claim build, which matters because claims are the high-cardinality page.

### Astro build posture: graceful, not loud

Optional fields render conditionally. A company without `legal_name` renders no legal-name row; a product without `parent_company` renders no "Made by" link; a missing parent ref falls back to the title-cased slug. **The build does not fail** on absent or partially-backfilled fields. This matches the lazy-backfill posture below.

The build *does* fail loudly when:

- An entity carries a malformed `parent_company` ref that fails the Zod regex (`/^companies\/[a-z0-9-]+$/`).
- An entity carries `legal_name: ""` or non-string (Zod `min(1)` enforces).

The product backfill below uses real refs (e.g., `companies/anthropic`); the loud-fail mode is reserved for typos in operator hand-edits, not for missing data.

### Operator-driven backfill posture

**Lazy rule (companies):** when an operator opens a company entity file for any reason, fill in `legal_name` if it's missing and they know it. No sweep, no checklist, no automation. Example pattern (compare existing `research/entities/companies/anthropic.md` which has just `name`, `type`, `website`, `description`, `search_hints`):

```yaml
---
name: Anthropic
type: company
website: https://anthropic.com
legal_name: Anthropic, PBC
description: Anthropic is an AI research company...
search_hints:
  exclude:
  - en.wikipedia.org
---
```

`legal_name` is inserted between `website` and `description` to mirror the writer's frontmatter ordering convention.

**One-time edit (products):** all five files under `research/entities/products/` get `parent_company` populated:
- `claude.md` → `companies/anthropic`
- `chatgpt.md` → `companies/openai`
- `gemini.md` → `companies/google`
- `greenpt.md` → `companies/greenpt` (a same-named company entity exists at `research/entities/companies/greenpt.md`; the product is published by the same-named org)
- `treadlightlyai.md` → `companies/treadlightlyai` (same-named company entity exists at `research/entities/companies/treadlightlyai.md`; operator-aligned)

The same-named twin pattern (`products/<x>` ↔ `companies/<x>`) is treated as an unambiguous self-publication signal in v1. Five-of-five backfill gives the render surface full demo coverage.

**`verification_status` backfill:** `research/entities/products/treadlightlyai.md` gets `verification_status: unverified-startup` set by hand during this plan. The field lives on the **product** file (not the company) so the badge renders on `/entities/products/treadlightlyai` (Done-when item 10). It exercises the badge render path and reflects the operator's assessment of the entity's public-documentation state. All other current entities default to `verified` (no field needed).

**Architecture doc amendment:** `docs/architecture/source-quality.md` gains a new H2 section `## Entity metadata` (placed after the existing source-overrides region; not folded into it — the topic is entity-side, not source-side):

> The entity-level `website` field doubles as the canonical-website / primary-source-disambiguation signal. The scorer treats sources whose URL matches `website` as the entity's first-party content (see `pipeline/researcher/scorer.py`'s "ENTITY DISAMBIGUATION" rule). When an entity carries a `legal_name` distinct from its display `name`, COI and restatement-test reasoning in the analyst use the legal name. When an entity carries `verification_status` other than the default `verified` (e.g., `unverified-startup`), the analyst weights sparse-evidence claims about that entity more conservatively, and the entity page renders an "unverified" badge.

## Implementation steps

1. **Zod schema add.** `src/content.config.ts:221-235` gains `legal_name` and `verification_status`.
2. **`ResolvedEntity` passthrough.** Add `legal_name: str | None = None` and `verification_status: str = "verified"` to the dataclass; populate in `parse_entity_ref`. Test in `pipeline/tests/test_entity_resolution.py`.
3. **Writer + linter mirrors.**
   a. `_entity_frontmatter` (`pipeline/orchestrator/persistence.py:39-58`) gains kwargs `legal_name: str | None = None` and `verification_status: str = "verified"`. Emits `legal_name` between `website` and `description` when populated; emits `verification_status` after `type` when ≠ `verified`. The two callers `_write_entity_file` and `_write_draft_entity_file` (`persistence.py:160`, `:528`) gain matching kwargs and pass `resolved_entity.legal_name` / `resolved_entity.verification_status` through.
   b. `CANONICAL_ENTITY_KEYS` in `pipeline/linter/checks.py:14` gains `legal_name`, `verification_status`, `sec_cik`, AND `status`. The latter two are bug-fix drive-bys: `sec_cik` shipped via `source-pool-expansion-tier1.md` without a linter add; `status` is emitted by `_entity_frontmatter` for draft entities (`persistence.py:56`) but is not in the linter set today, so the linter currently warns "unrecognized entity field" on any draft. Mention both in the commit message; not a scope expansion.
4. **Render surfaces (3 sites + verification badge).**
   a. `src/pages/entities/[...slug].astro` — product-page "Made by" block; company-page legal-name row; verification badge for any entity type when status ≠ `verified`.
   b. `src/pages/claims/[...slug].astro` — `madeBy` resolver + render.
   c. CSS for `.made-by`, `.legal-name`, and `.verification-badge` in the same `<style>` blocks (small additions; mirror `.website-link` styling at `src/pages/entities/[...slug].astro:150-154`). No shared stylesheet extraction in v1 — three classes with a few rules each don't justify it.
5. **Pipeline reads.**
   a. `pipeline/researcher/scorer.py` — `build_scorer_prompt` accepts `legal_name`; emits one line. `verification_status` not consumed by the scorer in v1 (search relevance is independent of verification).
   b. `pipeline/researcher/decomposed.py:430-438` — pass `resolved_entity.legal_name` through to the scorer.
   c. `pipeline/analyst/agent.py:136-203` — `build_analyst_prompt` emits `Legal name:` and `Verification:` lines when applicable.
   d. `pipeline/analyst/instructions.md` — add the COI/disambiguation paragraph and the verification-awareness paragraph.
6. **Backfill (operator pass).**
   a. **Products (one-time, in scope, all five):** `research/entities/products/claude.md` → `companies/anthropic`; `chatgpt.md` → `companies/openai`; `gemini.md` → `companies/google`; `greenpt.md` → `companies/greenpt`; `treadlightlyai.md` → `companies/treadlightlyai`. The last two pair with same-named twin company entities — that pairing is treated as the self-publication signal in v1.
   b. **Companies (lazy, optional):** any company file the operator touches gets `legal_name` filled in if known. Not gated.
   c. **`treadlightlyai` verification:** set `verification_status: unverified-startup` on `research/entities/products/treadlightlyai.md` (the product file, so the badge renders on `/entities/products/treadlightlyai` per Done-when item 10). Reflects the operator's existing assessment of the entity's public-documentation state.
7. **Architecture doc.** `docs/architecture/source-quality.md` — add the entity-metadata amendment described above.
8. **Followups + UNSCHEDULED bookkeeping.** Per § Done when below.

### MVP cut (half day)

If the operator wants to ship in stages, Steps 1–4 + 6a + 6c + 8 ship as one commit titled `feat(entity): legal_name + verification_status + render entity-metadata surfaces`. Step 5 (pipeline reads) and Step 6b (lazy company backfill) land as a follow-up commit on the same plan. The done-when list calls out the MVP cut explicitly.

The MVP-cut commit omits the analyst/scorer prompt unit tests (`test_legal_name_injected_into_scorer_prompt`, `test_analyst_prompt_emits_*`); those belong with Step 5 in the follow-up commit. The MVP commit still includes the entity-resolution + lockstep tests from Step 2/3 and the build / render verification.

## Test plan

### Unit tests (Python, pytest)

- `pipeline/tests/test_entity_resolution.py`:

  - `test_resolved_entity_legal_name_populated`: entity file with `legal_name: "OpenAI, LLC"` → `ResolvedEntity.legal_name == "OpenAI, LLC"`.
  - `test_resolved_entity_legal_name_absent`: entity file without the field → `ResolvedEntity.legal_name is None`.
  - `test_resolved_entity_verification_status_default`: entity file with no `verification_status` → `ResolvedEntity.verification_status == "verified"`.
  - `test_resolved_entity_verification_status_explicit`: entity file with `verification_status: unverified-startup` → field carries through.
  - `test_canonical_entity_keys_lockstep`: assert that the keys this plan adds or fixes (`legal_name`, `verification_status`, `sec_cik`, `status`) are in `CANONICAL_ENTITY_KEYS`. Cheap regression guard.
  - `test_verification_status_enum_lockstep`: assert that the three string literals the writer's suppression branch and the analyst-prompt branch compare against (`verified`, `unverified-startup`, `unverified-other`) match the Zod enum at `src/content.config.ts`. Read the Zod source and grep for the literals; failure means a typo in writer or analyst code went silent. Cheap drift guard.
- `pipeline/tests/test_researcher_decomposed.py` (extends existing Item C tests at line 328+):

  - `test_legal_name_injected_into_scorer_prompt`: `ResolvedEntity` with `legal_name="OpenAI, LLC"` → scorer prompt contains the legal name.
  - `test_legal_name_absent_no_line_in_prompt`: scorer prompt has no `Legal name:` line when the field is `None`.
- `pipeline/tests/test_agent.py` (analyst):

  - `test_analyst_prompt_emits_legal_name`: `build_analyst_prompt` with `ResolvedEntity.legal_name` set → "Legal name:" appears in the prompt block.
  - `test_analyst_prompt_omits_legal_name_when_absent`: no line emitted.
  - `test_analyst_prompt_emits_verification_when_not_verified`: status `unverified-startup` → "Verification:" line appears.
  - `test_analyst_prompt_omits_verification_when_verified`: default status → no line emitted (keeps the common-path prompt identical).

### Site / build tests

- Build with the current `research/` tree → succeeds. (Lazy posture: missing fields don't break the build.)
- Build with the in-scope product backfill applied (`claude.md`, `chatgpt.md`, `gemini.md` carrying `parent_company`) → succeeds. `npm run build` exit 0.
- Build with a fixture entity carrying `legal_name: ""` → fails on Zod `min(1)`.
- Build with a fixture entity carrying `parent_company: "companies/Does Not Exist"` → fails on the existing Zod regex (uppercase rejected).
- Build with a product whose `parent_company` references a non-existent company entity → succeeds, render falls back to the title-cased slug (e.g., `companies/nonexistent-co` → "Made by Nonexistent Co"). Documented as graceful-degrade behavior; verified by a fixture test.
- Build with a company entity where `legal_name === name` → legal-name row hidden (the `name !== legal_name` branch skips render). Verified manually or via an Astro snapshot test if available.

### Manual rendering verification (the load-bearing acceptance step)

Run `inv dev` and confirm:

1. `/entities/products/claude` shows "Made by [Anthropic]" with the Anthropic link working.
2. `/entities/companies/anthropic` shows the existing description and website. If the operator filled in `legal_name: Anthropic, PBC` during backfill, the legal-name row renders; otherwise it doesn't (and the build still passes).
3. A claim about Claude (e.g., any existing `research/claims/claude/*`) shows "Made by [Anthropic]" near the breadcrumb.
4. A claim whose subject is a company (e.g., an Anthropic-direct claim, or any `companies/*` subject) does NOT render "Made by" — the resolver returns `null`.
5. A claim whose subject is a subject-type entity (e.g., `subjects/generative-ai`) does NOT render "Made by".
6. The 4-and-5 cases are explicit acceptance criteria, not just "no regression" — the failure mode of an over-eager resolver is "Made by undefined" on real claim pages.
7. `/entities/products/treadlightlyai` shows the verification badge ("Unverified — sparse public documentation"). All other entity pages do NOT show the badge.

### Lint and round-trip

- `dr lint` over the repo after backfill → no `unrecognized entity field` warnings on `legal_name`, `verification_status`, or `sec_cik`.
- An entity file edited to add `legal_name` then re-saved through the writer round-trips with the field preserved (frontmatter ordering may differ; semantic dict equality is the test).

## Done when

1. Zod entity schema accepts `legal_name: z.string().min(1).optional()` and `verification_status: z.enum([...]).optional()`. Build passes against the current tree.
2. `ResolvedEntity.legal_name: str | None` and `ResolvedEntity.verification_status: str = "verified"` populated by `parse_entity_ref`; existing six entity files load without error.
3. `CANONICAL_ENTITY_KEYS` in the linter includes `legal_name`, `verification_status`, and the drive-by fixes `sec_cik` and `status`. `dr lint` issues no `unrecognized entity field` warnings on any of them.
4. `build_scorer_prompt` accepts `legal_name`; when populated, the prompt contains a `Legal name: ...` line. Verified by unit test.
5. `build_analyst_prompt` emits `Legal name: ...` when populated AND `Verification: ...` when status ≠ `verified`. Verified by unit tests.
6. `pipeline/analyst/instructions.md` has paragraphs explaining `legal_name` use for COI/disambiguation reasoning AND verification-status awareness for sparse-evidence weighting.
7. **Render surface 1 (product entity page):** `/entities/products/claude` shows "Made by [Anthropic]" linking to `/entities/companies/anthropic`. Same for `chatgpt` → openai, `gemini` → google, `greenpt` → greenpt, `treadlightlyai` → treadlightlyai.
8. **Render surface 2 (company entity page):** when `legal_name` is set on a company file, `/entities/companies/<slug>` renders a "Legal name: ..." row. When unset, no row renders and the build passes.
9. **Render surface 3 (claim page):** a claim about a product with `parent_company` set renders "Made by [Anthropic]" (or equivalent). A claim whose subject is a company-type or subject-type entity renders **no** "Made by" element (verified manually on at least two claims).
10. **Verification badge:** `/entities/products/treadlightlyai` renders the `unverified-startup` badge. All other entity pages render no badge (status defaults to `verified`).
11. All five product entity files (`claude`, `chatgpt`, `gemini`, `greenpt`, `treadlightlyai`) carry `parent_company` pointing at their corresponding company entity. `research/entities/products/treadlightlyai.md` additionally carries `verification_status: unverified-startup`.
12. `docs/architecture/source-quality.md` has the entity-metadata amendment describing `website`'s dual role, `legal_name`'s COI/disambiguation use, and `verification_status`'s analyst-weighting use.
13. `docs/plans/source-quality-followups.md` § Section 5 Bucket 2 stub points to this plan; the bucket sequencing block is replaced; a Review history row is added. The two new ideas (enrichment + verification gate) point to [`drafts/entity-onboarding-research_stub.md`](drafts/entity-onboarding-research_stub.md).
14. `docs/UNSCHEDULED.md` "parent_company not rendered" line is removed (or amended to "rendered as of `entity-metadata-surface.md`").

**MVP cut (half-day commit):** items 1, 2, 3, 7, 8, 9, 10, 11, 13, 14. Items 4, 5, 6, 12 land as a follow-up commit on this plan.

## Out of scope

- **The agent that auto-fills `verification_status`.** Tracked in [`drafts/entity-onboarding-research_stub.md`](drafts/entity-onboarding-research_stub.md). This plan only establishes the schema slot, render surface, and analyst awareness. Operators set the value by hand in v1.
- **Interactive `dr onboard` clarification / disambiguation gates.** Same stub.
- **Enrichment fields** (`founded`, `employee_count_band`, `headquarters`, `products`, narrative `history`). Same stub. Without the agent there's nothing useful to add — operators won't hand-research employee counts.
- **Verification badge on claim pages** (when the claim's subject is unverified). Render decision deferred to the follow-up plan; entity-page render is in scope here.
- `subsidiaries` field — explicitly punted from this bucket. Remains in `source-quality-followups.md` § Section 1 (Schema quality) as a candidate field; revisit when COI work activates it. May ride along with the enrichment agent.
- Renaming `website` → `official_website`. Operator-decided 2026-05-09: not happening. Architecture doc clarifies that `website` doubles as the canonical-website / primary-source-disambiguation signal; future contributors should not re-propose the rename without a concrete consumer that needs the distinction.
- Domain-keyed primary-source classification driven by entity `website` (extending `pipeline/common/source_classification.py`). Belongs with the deferred Phase 6/7 trust-block work in `source-quality-followups.md` § Section 3.
- A typed `EntityFrontmatter` Pydantic model to replace the `fm.get(...)` pattern in `parse_entity_ref`. Natural cleanup; not required for this bucket.
- Phase 7 `publisher_groups` (separate plan).
- Phase 6 trust-block agent classifier (separate plan).
- COI agent (separate plan).
- Inferring `parent_company` automatically — tracked in `parent-company-inference.md` (post-v1).
- A `<MadeByLink>` shared component. Three lines duplicated in two files; revisit if a third surface adopts the pattern.

## Effort estimate

**~2 days end-to-end** (up from 1.5 with the verification-status fold-in). Half-day MVP at schema + render + product/treadlightlyai backfill (Steps 1–4, 6a, 6c, 8). Pipeline reads + analyst instructions + lazy company backfill + arch-doc amendment as the second-day commit (Steps 5, 6b, 7).

Re-baseline the second-day estimate at planning time: the analyst instruction paragraphs and the architecture doc amendment are prose changes that may attract review iterations. Allocate buffer.

## Open questions

None remaining for v1 of this plan. Resolved 2026-05-09:

- **Writer-side handling of `legal_name`** → YES. Writer emits when populated. Folded into Step 3.
- **`treadlightlyai` parent_company** → YES (revised 2026-05-09 during review pass). Same-named company entity exists at `research/entities/companies/treadlightlyai.md`; backfill `products/treadlightlyai` → `companies/treadlightlyai`. The same-named twin pattern also applies to `greenpt`. Folded into Step 6a (now backfills all five products).
- **Lightweight verification-gate fold-in** → YES. `verification_status` enum field, render badge, analyst awareness, manual operator-set values. Agent + interactive UX + enrichment fields stay in the followup stub.

### Adjacent followup

[`drafts/entity-onboarding-research_stub.md`](drafts/entity-onboarding-research_stub.md) holds the post-v1 work: a single onboarding-research agent (one workflow, type-conditioned prompts for company / product / subject) that fills `verification_status`, halts on clarification / disambiguation cases, and populates enrichment fields. This plan's writer-side `legal_name` and `verification_status` emission is the prerequisite plumbing.

## Critical files for implementation

- `src/content.config.ts` — Zod schema add.
- `src/pages/entities/[...slug].astro` — product page "Made by" + company page legal-name row.
- `src/pages/claims/[...slug].astro` — claim-page "Made by" resolver and render.
- `pipeline/orchestrator/entity_resolution.py` — `ResolvedEntity.legal_name` passthrough in `parse_entity_ref`.
- `pipeline/linter/checks.py` — `CANONICAL_ENTITY_KEYS` set update (`legal_name`, `verification_status`, drive-by `sec_cik` and `status`).
- `pipeline/researcher/scorer.py` — `build_scorer_prompt` legal-name line.
- `pipeline/analyst/agent.py` + `pipeline/analyst/instructions.md` — analyst legal-name handling.
- `pipeline/researcher/decomposed.py` — pass `resolved_entity.legal_name` to `build_scorer_prompt`.
- `docs/architecture/source-quality.md` — entity-metadata amendment.
- `research/entities/products/{claude,chatgpt,gemini,greenpt,treadlightlyai}.md` — one-time `parent_company` backfill across all five products. `treadlightlyai.md` additionally gets `verification_status: unverified-startup`.

## Review history


| Date       | Reviewer         | Scope         | Changes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------ | ------------------ | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-05-09 | agent (opus-4-7) | initial draft | Promoted from`source-quality-followups.md` § Section 5 Bucket 2. Scope: `legal_name` schema add (operator decided 2026-05-09 not to add `official_website` — existing `website` field already plays that role); rendering on three surfaces; one-time `parent_company` backfill on five product files; analyst-instruction + scorer-prompt update for legal-name handling; arch-doc amendment. Drive-by: `sec_cik` added to `CANONICAL_ENTITY_KEYS`. `subsidiaries` deferred. Effort re-baselined to 1.5 days from triage row's 1 day, with explicit half-day MVP cut.                                                                |
| 2026-05-09 | agent (opus-4-7) | folded in     | Lightweight verification-gate fold-in per operator decision. Added`verification_status` enum field (applies to all three entity types), writer + linter mirrors, render badge on entity pages when status ≠ `verified`, analyst-prompt `Verification:` line + instructions paragraph, manual `treadlightlyai` → `unverified-startup` backfill. Effort bumped to 2 days. The agent that auto-fills the field, the interactive `dr onboard` clarification/disambiguation flow, and enrichment fields (`founded`, `size`, `headquarters`, `products`, narrative `history`) are split out to `drafts/entity-onboarding-research_stub.md`. |
| 2026-05-09 | 2× review agents (opus-4-7) | grounding + design pass | Grounding fixes: corrected stale line cites (`parse_entity_ref` lines 115-124, frontmatter `_clean_for_serialize` at 90-100); fixed the stale "`entities` already on line 23" claim — the entity template only loads the single `entity` via `Astro.props`, so add `getCollection("entities")` to the existing `Promise.all` at lines 23-26. Design improvements: replaced inline IIFE pattern with frontmatter-scope `madeBy` + `Map<id, entity>` resolver (O(1) per claim build, matches the claim template's existing idiom); added explicit `titleCaseSlug` JS helper mirroring `resolve_parent_name`; added explicit writer signature change to Step 3a (`_entity_frontmatter` kwargs + caller passthrough). Drive-by additions: `status` joins `sec_cik` in `CANONICAL_ENTITY_KEYS` (writer emits it for drafts but linter rejected it). Backfill scope corrected: same-named twin entities exist for `greenpt` and `treadlightlyai`, so all five products carry `parent_company` rather than three. Test plan additions: missing-parent-ref fallback test, `name === legal_name` hidden-row test, verification-status enum lockstep test. Architecture-doc destination tightened to a new H2 `## Entity metadata`. MVP-cut clarification: analyst/scorer prompt unit tests belong with the follow-up commit. |
