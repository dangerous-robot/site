# Migration: `sector` → `subject`

**Status**: shipped 2026-05-09 — atomic schema/code/content rename in commit `a0edbec`; follow-up cleanup in `156fdba`. New subject template `using-generative-ai-harms-cognitive-ability` added in `1c2b9b5`; the `ai-llm-producers` → `ai-model-producers` slug fix and `ai-producers-existential-score` claim landed in `12bec94`.

## Context

The `sector` entity_type currently holds two semantically different things:
- A literal industry sector (`AI Model Producers`: a group of companies)
- An idea/practice/technology (`Generative AI`: a phenomenon, not a group)

Future entries widen the overload further: "In-Person Learning", "Renewable Energy", etc. Rename the slot to `subject` so it honestly covers the broader space. Keep the entity slot (don't omit it): it carries description, aliases, and search hints the Researcher needs.

Two related decisions land in the same migration:
1. **Drop the unused `topic` entity_type.** It's reserved-but-unused and collides terminologically with the cross-cutting `topics:` taxonomy field on claims/criteria.
2. **Encode subject↔template pairings explicitly.** The current `templates_for_entity_type()` fan-out is illogical for subjects (subjects are heterogeneous; no single template applies to every subject). Templates with `entity_type: subject` get a new `subjects: [list]` field naming the subject(s) they apply to. Fan-out filters by membership.

Out of scope: the broader "decouple subject from entity model" idea in `docs/UNSCHEDULED.md`, renaming the cross-cutting `topics:` taxonomy field, renaming the `ENTITY` placeholder string in template texts.

## Constraints

- v1.0.0 pre-beta: commit directly to `main`, no PR workflow.
- Tree must not stay half-renamed: rename lands as one atomic change set (single commit, or multi-commit only if each leaves the build green).
- Use `inv dev` (port 4321) for the dev server.
- WIP currently exists on `pipeline/tests/test_orchestrator.py`, `pipeline/tests/test_researcher_decomposed.py`, `research/templates.yaml`, `research/entities/sectors/ai-model-producers.md`. Investigation shows the WIP edits are orthogonal (researcher origins / arXiv). Apply rename edits on top of WIP, do not stash. Diff each file against HEAD before editing to confirm no drift since this plan was written. The `templates.yaml` step (Group C, step 29) must land before re-running pytest, because the new Pydantic validator on `Template.subjects` (Group A, step 7) fires on every Template load and will fail if `subjects:` lists are missing.
- Untracked sector content (`research/entities/sectors/generative-ai.md`, `research/claims/sectors/generative-ai/`) needs `git add` before `git mv` to preserve renames.
- Untracked source files under `research/sources/` are unrelated; don't entangle.
- Public route `/sectors/` becomes `/subjects/`; pre-launch, no redirect needed.
- Slug drift in old docs: `ai-llm-producers` (in prose/examples) vs the actual on-disk slug `ai-model-producers`. Fix in passing where docs touch.
- Historical artifacts to leave alone: `docs/plans/completed/*.md` (including the filename `sector-claims.md`); the "Superseded" block at `docs/plans/drafts/v0.1.0-mvp-definition.md:398`; industry-sector prose in source files, FAQ, and `research/claims/treadlightlyai/realtime-energy-display.md:31`.

## Decisions

### D1. Topic entity_type: DROP

Remove `topic` from the entity_type enum. After migration: only `company | product | subject` in entity_type enums. Remove from:
- TS enum (`src/content.config.ts:223`)
- Python enum (`pipeline/common/models.py:176`)
- `src/lib/entityTypes.ts:4,12` (label + `/topics` href)
- Topic test in `pipeline/tests/test_entity_resolution.py:71-72`
- Empty `research/entities/topics/.gitkeep` (and the directory)

The cross-cutting `topics:` taxonomy field on claims/criteria stays: separate concept.

### D2. Subject fan-out: encode N:M pairings on templates

Subject templates declare which subject(s) they apply to via a new `subjects: [list]` field. Fan-out filters by membership:
- Onboarding `subjects/<slug>` queues claims for every template whose `subjects:` list contains that slug.
- Adding a new template with `entity_type: subject` queues claims for every subject named in its `subjects:` list.
- Many-to-many: a template can target multiple subjects; a subject can be targeted by multiple templates. (The current sector data already exhibits this: `subjects/ai-model-producers` is targeted by two templates.)

**Schema additions** (`src/content.config.ts` criteria schema and `pipeline/common/models.py:Template`):
- New optional field `subjects: list[str]` where each entry is a slug ref like `subjects/generative-ai`.
- Validator: required (non-empty) when `entity_type == "subject"`; forbidden otherwise.

**Fan-out logic** (`templates_for_entity_type` and its callers):
- For `entity_type in {"company", "product"}`: existing behavior (all `core: true` templates of that type apply to every entity of that type).
- For `entity_type == "subject"`: filter templates to those whose `subjects:` list contains the entity's slug ref.
- Inverse direction (template added): same filter, applied as `subject_slug in template.subjects`.

**Concrete pairings written into `research/templates.yaml` during this migration:**
```yaml
- slug: ai-producers-signed-safety-commitments
  entity_type: subject
  subjects: [subjects/ai-model-producers]
  ...
- slug: ai-producers-existential-score
  entity_type: subject
  subjects: [subjects/ai-model-producers]
  ...
- slug: using-generative-ai-harms-cognitive-ability
  entity_type: subject
  subjects: [subjects/generative-ai]
  ...
```

Future cross-subject templates just add more entries to the list.

## Inventory

**Schema (TS):**
- `src/content.config.ts:223`: entities `type` enum
- `src/content.config.ts:248`: criteria `entity_type` enum

**Astro:**
- `src/lib/entityTypes.ts:4-5,9,12`: ENTITY_TYPE_PARENTS / ENTITY_TYPE_LABELS
- `src/pages/sectors/index.astro`: entire file (renamed dir)
- `src/pages/index.astro:22,25,36,46-47,50-51,54,89,91,96,188`: homepage filter, breadcrumbs, highlights filter (load-bearing prefix on lines 47 and 51), variable names
- `src/layouts/Base.astro:125`: global nav `<a href="/sectors">Sectors</a>`
- `src/components/EntityCard.astro:6,12`
- `src/components/ObjectTypeIcon.astro:24`

**Python pipeline:**
- `pipeline/common/models.py:176-177`: `TOPIC` and `SECTOR`; also `Template` class (add `subjects` field + validator)
- `pipeline/common/templates.py:65,81-85`: `templates_for_entity_type()` and entity-name substitution branch
- `pipeline/orchestrator/entity_resolution.py:19`: dir → enum map
- `pipeline/orchestrator/persistence.py:36,196`: enum → dir map and layout comment
- `pipeline/orchestrator/cli.py:792,1186,1193,1488,1531,1539`: Choice values and help text
- `pipeline/orchestrator/pipeline.py:1450`: onboard fan-out call site (subject filter passes through here)
- `pipeline/linter/checks.py:31`
- `pipeline/researcher/planner.py:40`: prose

**Python tests:**
- `pipeline/tests/test_models.py:97`
- `pipeline/tests/test_entity_resolution.py:64-72` (sector + topic tests)
- `pipeline/tests/test_cli.py:366-406, 537-558`
- `pipeline/tests/fixtures/known_good/well-supported-true.md:12`: prose only, no test asserts on it (verified: leave alone)
- `pipeline/tests/test_templates.py`: add D2 schema validator test
- `pipeline/tests/test_onboard.py`: add D2 fan-out test
- WIP (orthogonal arXiv changes): `pipeline/tests/test_orchestrator.py:192-216`, `pipeline/tests/test_researcher_decomposed.py:750-757`

**Research content:**
- `research/templates.yaml:99,105,115` (three `entity_type: sector` entries; comments on 95 and 111)
- `research/entities/sectors/{ai-model-producers,generative-ai}.md`
- `research/claims/sectors/ai-model-producers/ai-producers-existential-score.md` (+ `.audit.yaml`)
- `research/claims/sectors/generative-ai/using-generative-ai-harms-cognitive-ability.md` (+ `.audit.yaml`)
- (Note: template `ai-producers-signed-safety-commitments` exists but no claim file on disk yet)

**Active docs (update):**
- `AGENTS.md:11`, `README.md:15`
- `docs/architecture/{content-model.md, glossary.md, open-issues.md, research-workflow.md, site.md}`: multiple lines each
- `docs/v1.0.0-roadmap.md:118,199-204,418` (also fix slug drift `ai-llm-producers` → `ai-model-producers`)
- `docs/UNSCHEDULED.md:9,368-377` (delete the rename-section header on 368-377; keep the broader "decouple from entity model" follow-up)
- `docs/plans/{claim-detail-ui-restructure.md, dr-command-redesign.md, dr-command-redesign-support.md, seo-copy.md, source-quality-followups.md, parent-company-inference.md}`: surgical line-level edits
- `docs/plans/drafts/{refresh-entity.md, v0.1.0-mvp-definition.md}` (line 398 historical: leave)

**Historical (leave):**
- `docs/plans/completed/sector-claims.md` and `page-icon-anchoring_completed.md`
- `research/sources/**` prose mentions of "sector"
- `src/pages/faq/index.astro:121` ("AI sector": industry meaning)
- `research/claims/treadlightlyai/realtime-energy-display.md:31` ("sector-wide": industry meaning)

**False positives (leave; verified during review):** these files match `topic` but on the cross-cutting `topics:` taxonomy field (claim/criterion frontmatter), not on `topic` as an entity_type. They should NOT be touched by this rename:
- `pipeline/orchestrator/stats.py`: `academic_topic_coverage` and `topics:` array reads
- `pipeline/tests/test_cli_stats.py`: fixture builders for `topics: [...]`
- `pipeline/tests/test_content_loader.py`: `topic` filter tests on `list_claims`
- `src/components/ClaimRow.astro`: `topics: string[]` prop and `data-topic` attribute
- `src/pages/criteria/index.astro`: `topicFacet`, `data-topic`, topic labels

**CI / templates:**
- `.github/ISSUE_TEMPLATE/submit-source.md:15,19,20`

## Sequenced execution

Atomic single change set. Steps grouped only for review; the tree must not be committed half-done.

### Pre-flight
1. `git status` and `git diff --stat` to confirm WIP scope.
2. Diff `research/templates.yaml` and `research/entities/sectors/ai-model-producers.md` against HEAD; merge rename into WIP rather than overwriting.
3. `git add research/entities/sectors/generative-ai.md research/claims/sectors/generative-ai/` to bring untracked sector content under tracking so `git mv` preserves renames. Do NOT add the untracked `research/sources/` files.
4. Bootstrap-order check: the Pydantic validator added in step 7 fires on every `Template` load, so `research/templates.yaml` must carry `subjects:` lists by the time pytest re-collects. Within the change set, land Group C step 29 (the templates.yaml edit) in the same working tree as Group A step 7. If reordering execution for incremental verification, run `pytest --collect-only` after step 7 to surface validator errors before full test runs.

### Group A: Schema, enums, code identifiers
4. `src/content.config.ts:223`: entities enum: drop `'sector'` and `'topic'`, add `'subject'`. After: `z.enum(['company', 'product', 'subject'])`.
5. `src/content.config.ts:248`: criteria enum: replace `'sector'` with `'subject'`. Add new optional `subjects` field plus an object-level `.superRefine()` (not a field-level `.refine()`, which can't see sibling fields):
   ```ts
   subjects: z.array(z.string().regex(/^subjects\/[a-z0-9-]+$/)).optional(),
   // ...other fields...
   }).superRefine((data, ctx) => {
     const isSubject = data.entity_type === 'subject';
     const hasSubjects = !!data.subjects && data.subjects.length > 0;
     if (isSubject && !hasSubjects) {
       ctx.addIssue({
         code: z.ZodIssueCode.custom,
         path: ['subjects'],
         message: "subjects: required and non-empty when entity_type === 'subject'",
       });
     }
     if (!isSubject && hasSubjects) {
       ctx.addIssue({
         code: z.ZodIssueCode.custom,
         path: ['subjects'],
         message: "subjects: forbidden when entity_type !== 'subject'",
       });
     }
   });
   ```
   The Python-side equivalent (Pydantic validator in step 7) enforces the same rule. The test added in step 21 (`pipeline/tests/test_templates.py`) exercises both branches.
6. `pipeline/common/models.py:176`: remove `TOPIC = "topic"`. Line 177: `SECTOR = "sector"` → `SUBJECT = "subject"`.
7. `pipeline/common/models.py:Template`: add optional `subjects: list[str] | None = None`; add a Pydantic validator enforcing presence iff `entity_type == "subject"` and that each entry matches `^subjects/[a-z0-9-]+$`.
8. `pipeline/common/templates.py:85`: `"sector"` → `"subject"`.
9. `pipeline/common/templates.py:65` (`templates_for_entity_type`): extend signature with optional `entity_slug: str | None = None`. Behavior by entity_type:
   - `company` / `product`: ignore `entity_slug`; return all `core: true` templates of that type. Existing callers don't change.
   - `subject` with a slug: return templates whose `subjects:` list contains `f"subjects/{entity_slug}"`.
   - `subject` with `entity_slug=None`: return `[]`. Subject fan-out without a slug is undefined, so an empty list is the correct conservative answer (returning all subject templates would silently break N:M filtering).
   Add a unit test for the subject-with-None case alongside the fan-out test in step 20.
10. `pipeline/orchestrator/entity_resolution.py:19`: `"sectors": EntityType.SECTOR` → `"subjects": EntityType.SUBJECT`. Remove any topic entry if present.
11. `pipeline/orchestrator/persistence.py:36,196`: `EntityType.SECTOR: "sectors"` → `EntityType.SUBJECT: "subjects"`; comment update.
12. `pipeline/orchestrator/cli.py`: Choice values on 1186 and 1488: `["company", "product", "sector"]` → `["company", "product", "subject"]`; placeholder map key on 1193 (`"sector"` → `"subject"`, value `"ENTITY"` unchanged); help text examples on 792, 1531, 1539 (`sectors/...` → `subjects/...`, slug `ai-llm-producers` → `ai-model-producers`).
13. `pipeline/linter/checks.py:31`: `"sectors": "sector"` → `"subjects": "subject"`.
14. `pipeline/researcher/planner.py:40`: prose: "sector-level or abstract entities" → "subject-level or abstract entities".
15. `src/lib/entityTypes.ts` (verified line numbers from current file):
    - Line 4: `topic:   { label: "Topics",    href: "/topics"    },` → DELETE entire line.
    - Line 5: `sector:  { label: "Sectors",   href: "/sectors"   },` → `subject: { label: "Subjects",  href: "/subjects"  },`.
    - Line 9: `sector:    "Sector",` → `subject:   "Subject",`.
    - Line 12: `topic:     "Topic",` → DELETE entire line.
    Note: the `EntityType` type on line 18 derives from `ENTITY_TYPE_PARENTS` keys, so it updates automatically.
16. `src/components/EntityCard.astro:6,12`: type union and route map.
17. `src/components/ObjectTypeIcon.astro:24`: sector → subject icon branch. Note: line 46 (topic icon branch) is for the cross-cutting `/topics/` taxonomy view, NOT entity_type=topic; leave it alone.

### Group B: D2 onboarding semantics
18. `pipeline/orchestrator/pipeline.py:onboard_entity`: pass the entity slug to `templates_for_entity_type` so subject fan-out filters to templates that name this subject. Confirm any code that fans out a newly-added template across entities also respects the `subjects:` filter for `entity_type=subject` templates.
19. `pipeline/orchestrator/cli.py:onboard` docstring (line 1528): note that subject claims are gated by templates' `subjects:` field (no claims fan out for subjects not referenced by any template).
20. Add a test in `pipeline/tests/test_onboard.py` (or `test_pipeline.py`): onboarding `subjects/generative-ai` queues only the templates that name it; onboarding a subject not referenced by any template queues zero claims.
21. Add a template-validation test in `pipeline/tests/test_templates.py`: a template with `entity_type: subject` and missing/empty `subjects:` fails validation; a non-subject template with `subjects:` set fails; a subject template with valid refs passes.

### Group C: Content moves and frontmatter
22. `git mv research/entities/sectors research/entities/subjects`
23. `git mv research/claims/sectors   research/claims/subjects`
24. `git mv src/pages/sectors         src/pages/subjects`
25. `research/entities/subjects/{ai-model-producers,generative-ai}.md` line 3: `type: sector` → `type: subject`.
26. `research/claims/subjects/ai-model-producers/ai-producers-existential-score.md:4`: `entity: sectors/...` → `entity: subjects/...`.
27. `research/claims/subjects/generative-ai/using-generative-ai-harms-cognitive-ability.md:3`: same.
28. Read each `.audit.yaml` and update any internal `sectors/...` path refs (likely metadata-only; verify).
29. `research/templates.yaml:95,99,105,111,115`: three `entity_type: sector` → `subject`; section comments. Add `subjects:` field to each:
    - `ai-producers-signed-safety-commitments`: `subjects: [subjects/ai-model-producers]`
    - `ai-producers-existential-score`: `subjects: [subjects/ai-model-producers]`
    - `using-generative-ai-harms-cognitive-ability`: `subjects: [subjects/generative-ai]`
    Merge with existing WIP edits.
30. `rm research/entities/topics/.gitkeep` and remove the empty `research/entities/topics/` directory.

### Group D: Astro pages, components, layout, homepage
31. Edit renamed `src/pages/subjects/index.astro` lines 8, 23, 24, 31, 37: type checks, titles, EmptyState copy.
32. `src/pages/index.astro`: rename variables (`sectorEntities` → `subjectEntities`, `sectorHighlights` → `subjectHighlights`, `isSector` → `isSubject`); update labels, hrefs (`/sectors` → `/subjects`), filter type strings (`'sector'` → `'subject'`); **critically lines 47 and 51: `c.id.startsWith('sectors/')` → `'subjects/'`** (load-bearing: homepage carousel goes empty if missed).
33. `src/layouts/Base.astro:125`: global nav `<a href="/sectors">Sectors</a>` → `/subjects`.

### Group E: Tests
34. `pipeline/tests/test_models.py:97`: expected set: drop `"sector"` and `"topic"`, add `"subject"`. After: `{"company", "product", "subject"}`.
35. `pipeline/tests/test_entity_resolution.py:64-67`: rename method `test_valid_sector_ref` → `test_valid_subject_ref`; update fixture writes and `EntityType.SECTOR` → `EntityType.SUBJECT`. Drop the topic test on lines 71-72.
36. `pipeline/tests/test_cli.py:366,367,372,376,379,406,537,553,558`: method rename; sector path/type/text → subject (placeholder string `ENTITY` unchanged). The fixture template at line 537 needs a `subjects:` list to validate (e.g., `subjects: ["subjects/the-subject"]`).
37. New tests for the D2 schema/validator and fan-out (Group B steps 20 and 21) land in `pipeline/tests/test_onboard.py` and `pipeline/tests/test_templates.py`.

### Group F: Docs and CI
38. Active doc edits per the inventory (line-level surgical replacements). Each citation is `path:line: current text → replacement` so a reviewer can validate without opening the file. Where a line cluster is contiguous, only the first line is shown.
    - `AGENTS.md:11`: entity-types prose mentions "sectors exist but aren't yet an intake" → "subjects exist but aren't yet an intake".
    - `README.md:15`: entity-types list reference: `sector` → `subject`.
    - `docs/architecture/content-model.md:24,36,47`: schema enum + dir layout references; `sector` → `subject`, `sectors/` → `subjects/`.
    - `docs/architecture/glossary.md:7,15`: entity-types definition; drop topic, rename sector → subject.
    - `docs/architecture/open-issues.md:24`: open-issue reference to sector decoupling; rename to subject.
    - `docs/architecture/research-workflow.md:7`: entity slot reference: `sector` → `subject`.
    - `docs/architecture/site.md:27,49,82`: route table and entity-type table: `/sectors` → `/subjects`; `sector` → `subject`.
    - `docs/v1.0.0-roadmap.md:118,199-204,418`: milestone notes referencing sectors. Also fix `ai-llm-producers` slug drift to `ai-model-producers` in the same edit.
    - `docs/UNSCHEDULED.md:9`: rename `sector` → `subject` in the entity-types reference. Delete the now-completed rename section at lines 368-377; keep the "decouple from entity model" follow-up as a separate bullet (don't lose it).
    - `docs/plans/claim-detail-ui-restructure.md:35,41,223,233`: type checks and route refs.
    - `docs/plans/dr-command-redesign.md:85,87,92,96,159,168`: CLI design refs to `sector`.
    - `docs/plans/dr-command-redesign-support.md:84,100`: same.
    - `docs/plans/seo-copy.md:109`: page title / breadcrumb prose.
    - `docs/plans/parent-company-inference.md:24`: example entity_type.
    - `docs/plans/source-quality-followups.md:133,135,137` (ONLY the technical sector-as-enum lines; leave 120, 122, 362, 364, which are industry-prose meaning of "sector").
    - `docs/plans/drafts/refresh-entity.md:153`: refresh logic entity_type ref.
    - `docs/plans/drafts/v0.1.0-mvp-definition.md:236`: entity-type list (leave line 398: Superseded historical block).
39. `.github/ISSUE_TEMPLATE/submit-source.md:15,19,20`: entity_type field options; drop topic, rename sector → subject.
40. CI gating for the new template validator: add `pipeline/tests/test_templates.py::test_subject_template_schema` to whatever job runs on changes to `research/templates.yaml` (or a pre-commit hook). Without this, malformed `subjects:` lists only surface at manual onboard time. If no per-path CI exists yet, this lives as a TODO to wire up; the test itself still runs with the rest of pytest.

## Critical files to read before each edit

- `src/content.config.ts` (schema authority)
- `pipeline/orchestrator/pipeline.py` lines 1330-1500 (`onboard_entity` flow: D2 lands here)
- `pipeline/common/templates.py` lines 60-90 (`templates_for_entity_type`, `_substitute_entity`)
- `pipeline/common/models.py` Template class (validator addition)
- `research/templates.yaml` (merge rename with WIP)
- `research/entities/sectors/ai-model-producers.md` (merge rename with WIP)
- `src/pages/index.astro` lines 1-100 and 180-200 (homepage variable rename + filter prefix)
- `pipeline/tests/test_cli.py:366-410, 530-565` (largest test diff)

## Verification

```bash
# Pipeline
cd pipeline && pytest -x

# Invalidate Astro's content-collections schema cache before checking
# (enum changes in src/content.config.ts can be missed by a stale cache).
cd .. && rm -rf node_modules/.astro .astro 2>/dev/null || true

# Astro schema validation (catches enum/frontmatter mismatch)
npx astro check

# Build (catches route resolution and broken layout links)
npx astro build

# Smoke (manual)
inv dev   # port 4321
#   GET /                           - homepage subject highlights non-empty (see grep below)
#   GET /subjects                   - index renders
#   GET /entities/subjects/ai-model-producers
#   GET /entities/subjects/generative-ai
#   GET /sectors                    - 404 expected (confirms no stale route)

# Homepage carousel content check (catches a silently-empty carousel
# from missing the load-bearing filter prefix on src/pages/index.astro:47,51).
# Expect the count to be >= 2 (one per subject entity in the highlights set).
test "$(curl -s http://localhost:4321/ | grep -c 'href="/entities/subjects/')" -ge 2

# D2 verification (manual)
dr onboard subjects/generative-ai           # expect: 1 claim queued
dr onboard subjects/ai-model-producers      # expect: 2 claims queued
dr onboard subjects/unreferenced-test-subject
                                            # expect: entity created, 0 claims
```

## Risks

| Risk | Mitigation |
|---|---|
| Group A or C alone leaves the build red | Atomic commit; don't commit between groups. |
| `src/pages/index.astro` filter prefix not updated (lines 47, 51) silently empties homepage carousel | Smoke `/` after build; explicitly inspect those lines. |
| `git mv` fails on untracked content | Pre-flight `git add` for untracked sector files only. |
| Stomping WIP edits in `templates.yaml` and `entities/sectors/ai-model-producers.md` | Diff-against-HEAD before editing; merge into WIP. |
| Slug confusion `ai-llm-producers` vs `ai-model-producers` in old docs | Step 38 explicitly fixes slugs in roadmap/mvp docs. |
| Encoded `subjects:` list parsed but not enforced: invalid template silently fans out wrong | Validator tests in step 21 cover required-iff and forbidden-otherwise. |
| Removing `topic` without checking for callers | Final inventory pass before commit, broadened to catch YAML keys and dict literals: `rg -nP '\b(TOPIC\|["'\''`]topic["'\''`])\b' pipeline/ src/` and `rg -n '^topic:' research/ pipeline/tests/fixtures/`. Beware `--topic` flag on `dr reassess` / `dr step-audit` at cli.py:1450, which is a different `topic` (the cross-cutting taxonomy filter); do not touch. |
| `templates_for_entity_type` signature change breaks existing call sites | Make `entity_slug` optional (default `None`) with a default that preserves company/product behavior. Ripgrep for all callers before editing. For `entity_type='subject'` with `entity_slug=None`, return `[]` (see step 9). |
| Malformed `subjects:` field in templates.yaml fans out wrong onboarding | The Pydantic validator (step 7) and Zod superRefine (step 5) catch shape errors at load time. Step 40 adds `pipeline/tests/test_templates.py::test_subject_template_schema` to CI gating on `research/templates.yaml` so a broken template can't be merged. |

## Commit message

```
rename sector → subject; encode subject↔template pairings on templates

The `sector` slot held both literal industry groups (AI Model
Producers) and abstract topics (Generative AI). Renaming to `subject`
generalizes the slot for entries like "In-Person Learning",
"Renewable Energy", etc.

Schema: src/content.config.ts entity.type and criteria.entity_type;
EntityType enum in pipeline/common/models.py. Topic enum value
dropped (was reserved-but-unused; conflicted with the cross-cutting
topics: taxonomy field).

Content moved via git mv: research/entities/sectors → subjects,
research/claims/sectors → subjects, src/pages/sectors → subjects.
Frontmatter type: and entity: refs updated.

Subject onboarding: templates with entity_type=subject now declare
their target subjects via a new subjects: [list] field. Fan-out
filters by membership, so onboarding subjects/<slug> queues exactly
the templates that name that subject (zero, one, or many: N:M
pairing). Subjects are heterogeneous, so the previous "all templates
of this type apply to every entity of this type" rule was illogical
for them.

Out of scope: the broader "decouple subject from entity model" idea
remains in docs/UNSCHEDULED.md as a follow-up. The placeholder string
ENTITY in template texts is unchanged. Cross-cutting topics: taxonomy
field is unchanged.

URL preservation: skipped. Pre-launch, no inbound /sectors/ links.
```

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-09 | agent (claude-opus-4-7) | deep, implementation, iterated | Parallel Explore pass verified all cited line numbers (`content.config.ts`, `models.py`, `templates.py`, `entity_resolution.py`, `persistence.py`, `cli.py`, `pipeline.py`, `index.astro`, `Base.astro`); confirmed promotion mechanics. Applied edits: em dash sweep per AGENTS.md style; D2 Zod schema rewritten as `.superRefine` with sibling-field check; Pydantic validator boot-order pre-flight added (step 4); Astro content-collections cache invalidation added to verification; homepage carousel smoke strengthened to grep rendered HTML; `entity_slug=None` default behavior pinned (returns `[]` for subject); inventory false-positives documented (`stats.py`, `test_cli_stats.py`, `test_content_loader.py`, `ClaimRow.astro`, `criteria/index.astro` all match cross-cutting `topics:` taxonomy, not entity_type); `entityTypes.ts` per-line edits enumerated (lines 4, 5, 9, 12); `ObjectTypeIcon.astro:46` left-alone note; topic-residue grep broadened to YAML keys and dict literals; Group F line-by-line substitution context added; CI validator gate added as step 40 and as a Risks row. |
