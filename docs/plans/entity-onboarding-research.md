# Entity onboarding research: enrich-then-verify agents

**Status**: ready (drafted 2026-05-09; reviewed in three parallel passes)
**Created**: 2026-05-09 (promoted from `drafts/entity-onboarding-research_stub.md`)
**Architecture docs touched**: `docs/architecture/onboarding.md`, `docs/architecture/glossary.md`, `docs/architecture/source-quality.md` (entity-metadata section)
**Hard prerequisite**: [`completed/entity-metadata-surface_completed.md`](completed/entity-metadata-surface_completed.md) — schema slot for `verification_status` and writer-side emission already shipped (`cf93b87`, `67b1dc4`).

## Goal

Make entity pages worth reading, end to end. Two automated agents fill the structured fact and narrative content that the operator currently has nowhere to put, plus a thin gate that prevents name-collision pollution at intake. Reader-visible value drives every step.

Three reader-facing surfaces gain content:

1. **Company entity page** (`/entities/companies/<slug>`): founded year, narrative `history` body block, and a derived "Products" list (computed from existing `parent_company` refs, no new schema field).
2. **Product entity page** (`/entities/products/<slug>`): founded year and narrative `history` body block, alongside the existing "Made by" link from `entity-metadata-surface`.
3. **Subject entity page** (`/entities/subjects/<slug>`): narrative `history` body block.

Two pipeline-quality surfaces also gain content:

4. **Analyst prompt**: `founded` injected when populated. Helps verdicts on tenure-of-operation claims ("X has been running since Y").
5. **Verification badge accuracy**: the verifier auto-fills `verification_status` so the badge from `entity-metadata-surface` reflects an actual signal, not just operator omission.

## Operator usage

After this plan ships, the operator types these commands:

```
# Onboard a new entity
dr onboard "Acme Corp" --type company
  → Phase A light research → Phase B verifier (halts on disambiguation)
    → Phase C enricher (operator reviews draft) → Phase D template screening
    → review_onboard checkpoint → per-template claim research

# Re-enrich an existing entity (focused)
dr entity-enrich entities/companies/acme-corp
  → Phase A light research → Phase C enricher (operator reviews) → write

# Re-enrich while re-onboarding (covers other --force needs too)
dr onboard "Acme Corp" --type company --force
```

The two re-enrich entry points share the same `enrich_entity` helper.

## Scope decisions (operator, 2026-05-09)

| Decision | Choice |
|---|---|
| Sequencing | Enrichment first, gate is thin. Drop the non-interactive `--resume` protocol. |
| Subject onboarding | Include subjects as a first-class `dr onboard --type subject` intake, with a type-conditioned prompt section. |
| Agent decomposition | Two agents: `entity_verifier` and `entity_enricher`. Each has a typed Pydantic output and its own prompt builder, mirroring `planner.py` / `scorer.py`. |
| Package | Add `entity_verifier.py` and `entity_enricher.py` inside the existing `pipeline/researcher/` package. No new package; reuse the established agent-construction pattern. |
| `headquarters` schema field | **Dropped** after simplicity review — no concrete claim-axis demands jurisdictional reasoning today, and the field would have pulled the entire per-type linter rule with it. Add later if a real consumer appears. |
| `_tighten_entity_description` | Subsumed into the enricher (it already takes the same inputs and produces a sibling output). The standalone agent is removed in the same change. |

## Reader-facing surfaces (load-bearing)

If a field doesn't render, it doesn't ship in v1 of this plan.

### Company entity page

After the existing description / "Legal name" / website / verification-badge block in `src/pages/entities/[...slug].astro`, render a "Facts" subsection when `founded` or the derived products list is populated:

```
Founded: 2021
Products: Claude · Claude Code · Claude Haiku
```

Then a "History" subsection that renders the markdown body (the entity file's body is currently empty for most companies; this plan starts using it).

### Product entity page

Mirror the company page's "Facts" + "History" pattern, with `founded` as the only structured field. The existing "Made by" link from `entity-metadata-surface` stays.

### Subject entity page

"History" body block.

### Pages that intentionally do **not** change in v1

- Claim pages do not render the new fields. The verification badge on claim-page-when-subject-unverified was already deferred by `entity-metadata-surface` and stays deferred. `dr onboard` improving badge accuracy is the indirect win.
- Homepage scatter and category pages do not render founded year. The entity page is the canonical surface; cross-linking can come later if it earns its keep.

## Schema additions

Lockstep across Zod (`src/content.config.ts`), `ResolvedEntity` dataclass (`pipeline/orchestrator/entity_resolution.py`), the writer (`pipeline/orchestrator/persistence.py:_entity_frontmatter`), and `CANONICAL_ENTITY_KEYS` (`pipeline/linter/checks.py`).

| Field | Type | Applies to | Rationale |
|---|---|---|---|
| `founded` | `z.number().int().min(1800).max(<currentYear>).optional()` | company, product (subject ignored at render time) | Reader cue + analyst signal. Scorer date-filters sources by it. |

Narrative `history` lives in the **markdown body**, not frontmatter. No schema change for it; the entity collection already loads body content. The renderer learns to surface the body under a "History" heading when present.

### Explicitly **not** added to the schema

- `near_homophones` — dropped 2026-05-09. The fishing/phishing trigger only matters with audio input, which the system doesn't have.
- `headquarters` — dropped 2026-05-09 per simplicity review. No concrete claim-axis demands jurisdictional reasoning today; reintroduce when one does.
- `employee_count_band` — band edges drift fast and reader value is low.
- `products: z.array(<ref>)` on company — derivable at render time by scanning the entities collection for products whose `parent_company === thisCompany.id`. All five products carry `parent_company` after `entity-metadata-surface`. Adding a redundant schema field invites drift.
- `subsidiaries` — same logic but blocked on schema (`parent_company` regex disallows company → company). Defer until COI work needs it.
- An expanded `verification_status` enum. The three values from `entity-metadata-surface` (`verified`, `unverified-startup`, `unverified-other`) are sufficient.

## Two-agent design

Both agents live in `pipeline/researcher/` and mirror the inline-system-prompt convention of `planner.py` / `scorer.py`. Each is Haiku-class, tool-free at the agent level (web search runs in the orchestrator and feeds candidates in), with typed Pydantic output and `retries=2`. Both consume the **same** `LightResearchBundle` (see § Shared input below) — neither agent issues its own search.

### `LightResearchBundle` (shared input)

Frozen dataclass in `pipeline/orchestrator/pipeline.py` (or a new `pipeline/orchestrator/light_research.py` if pipeline.py is already too long):

```python
@dataclass(frozen=True)
class LightResearchBundle:
    entity_name: str
    entity_type: EntityType
    raw_description: str            # untightened webpage summary
    entity_website: str | None
    description_source_url: str | None
    probe_excludes: list[str]       # name-collision hints from search probe
    search_candidates: list[SearchCandidate]  # top-N from Brave/Tavily
```

`gather_light_research(entity_name, entity_type, cfg, sem, client) -> LightResearchBundle` lives next to `_tighten_entity_description` in `pipeline.py`. Both `onboard_entity` (Phase A) and `enrich_entity` call it. Replaces the in-line block currently at `pipeline.py:1393-1435`.

### `entity_verifier.py`

- **Input**: `LightResearchBundle`.
- **Output**: `VerificationOutcome` Pydantic model — `status: 'verified' | 'needs-disambiguation' | 'unverified'`, `candidates: list[str]` (alphabetical; populated only on `needs-disambiguation`), `reasoning: str`.
- **Per-type prompt section** swaps signal lists by `entity_type`.
- **Outcomes → frontmatter contract**:

| Verifier returns | Onboarding action | Frontmatter `verification_status` |
|---|---|---|
| `verified` | proceed to Phase C | absent (defaults to verified per `entity-metadata-surface`) |
| `needs-disambiguation` | halt; surface candidates to operator | nothing written; operator picks a name and re-runs |
| `unverified` | halt; operator picks `unverified-startup` or `unverified-other` | the operator's pick is written |

The `'unverified'` runtime status is transient — it never appears in frontmatter. The two schema enums (`unverified-startup`, `unverified-other`) are operator-set at the halt-and-confirm step.

### `entity_enricher.py`

- **Input**: `LightResearchBundle`. The enricher does not depend on the verifier's output — the orchestrator decides whether to run it.
- **Output**: `EnrichmentDraft` Pydantic model — `founded: int | None`, `description: str` (1 sentence — subsumes `_tighten_entity_description`), `history_markdown: str` (2–4 paragraphs).
- **Per-type prompt section** selects field guidance: company / product solicit `founded`; subject solicits `history_markdown` only.
- **Operator review** before commit (see § Operator-review UX).

### Orchestration phases inside `onboard_entity`

The new agents slot into `pipeline/orchestrator/pipeline.py:onboard_entity`. Naming uses **phases** (A–F) for runtime steps, distinct from the numbered Implementation steps below:

```
Phase A: Light research                  (existing — refactored to return LightResearchBundle)
Phase B: entity_verifier                 (NEW — halts on needs-disambiguation or unverified)
Phase C: entity_enricher                 (NEW — operator-review checkpoint)
Phase D: Template screening              (existing)
Phase E: review_onboard checkpoint       (existing)
Phase F: Per-template claim research     (existing)
```

Verifier runs first because if the name resolves to the wrong entity, enrichment is wasted compute. Enricher runs second because its operator-review checkpoint is heavier than the verifier's disambiguation prompt.

## Per-type prompt sections

Each agent carries three short type-conditioned sections (~10 lines each) selected at prompt-build time by `entity_type`. The shared scaffold around them stays type-agnostic.

### Company

- Verifier signals: official site resolves; SEC EDGAR / Companies House registry hit; substantive Wikipedia article; news coverage from independent outlets in the last 5 years; identifiable leadership.
- Verifier disambiguation triggers: name collides with a known product or another company.
- Enricher fields: `founded`, `description`, `history_markdown`. Note: `legal_name` is **not** populated by the enricher — operator-set per `entity-metadata-surface`'s lazy-backfill rule.

### Product

- Verifier signals: product page on a recognized parent company's official site; independent reviews; app-store / GitHub presence where relevant.
- Verifier disambiguation triggers: same name as a competing product; ambiguous version naming. The same-name-as-parent case (e.g., `greenpt` / `treadlightlyai`) is **not** a halt — that pattern is the documented self-publication signal.
- Enricher fields: `founded`, `description`, `history_markdown`.

### Subject

- Verifier signals: encyclopedic / academic / dictionary consensus; distinct from a brand using the term as a product name.
- Verifier disambiguation triggers: term has multiple unrelated definitions.
- Enricher fields: `description`, `history_markdown` only.

Subjects ship a pilot pass with the two existing subject entities (`ai-model-producers`, `generative-ai`) plus 2–3 new subjects added during implementation.

## Operator-review UX

Two new `CheckpointHandler` methods (`pipeline/orchestrator/checkpoints.py`):

- `review_entity_disambiguation(entity_name: str, candidates: list[str]) -> Literal["accept", "reject"] | str` — mirrors `review_onboard`'s sentinel-or-payload idiom. `"accept"` means "use the first candidate as-is"; `"reject"` aborts; a returned `str` is the operator's chosen name (one of the candidates, or a free-text override). The free-text override doubles as the channel for the `unverified` halt: when the verifier returns `unverified`, the orchestrator calls this method with the two-element list `['unverified-startup', 'unverified-other']`, and the operator's pick becomes the `verification_status` written to frontmatter.
- `review_entity_enrichment(entity_name: str, draft: EnrichmentDraft) -> Literal["accept", "reject"]` — prints the draft (frontmatter scalars + history markdown) to stdout, reads `[a]ccept / [r]eject` from stdin. Intentionally lighter than a `git rebase -i`-style temp-file flow: the entity file is on disk, the operator can refine prose by editing it after `accept`. Auto-approve handler returns `"accept"`.

This is two new methods, not three: the `unverified` outcome reuses `review_entity_disambiguation` rather than introducing a third method for a tiny choice.

## Pipeline-side reads

Once the schema and writer support `founded`, pipeline agents that already read `ResolvedEntity` learn to use it:

### Analyst (`pipeline/analyst/agent.py:build_analyst_prompt`)

Add one optional line to the existing entity block when populated:

```
Founded: {founded}
```

Plus one paragraph in `pipeline/analyst/instructions.md`: *founded year is authoritative for "X has been operating since Y" claims.*

### Scorer (`pipeline/researcher/scorer.py:build_scorer_prompt`)

Add `Founded: {founded}` when populated. Helps the scorer date-filter sources (a 2024 source about an entity founded in 2021 has a 3-year horizon; a 2024 source about an entity founded in 1985 has a 39-year horizon). Two lines.

### Renderer (`src/pages/entities/[...slug].astro`)

Type-conditioned subsections per § Reader-facing surfaces. The renderer already loads the entity body via the content collection; this plan starts using it. Mirror `description` styling.

## Implementation steps

Each step is tagged **(Commit 1)** or **(Commit 2)**. Commit 1 is the MVP — reader-visible enrichment via `dr entity-enrich` against the existing corpus. Commit 2 wires it into `dr onboard`.

1. **Schema + ResolvedEntity + writer + linter (Commit 1).**
   - `src/content.config.ts`: add `founded` to the entity Zod schema.
   - `pipeline/orchestrator/entity_resolution.py:ResolvedEntity` + `parse_entity_ref`: passthrough `founded`.
   - `pipeline/orchestrator/persistence.py:_entity_frontmatter` + the two `_write_*entity_file` callers: kwarg and emission. Field ordering: `founded` after `description`. The narrative `history` is written by a new `_write_entity_history` helper in the same file.
   - `pipeline/linter/checks.py:CANONICAL_ENTITY_KEYS`: add `founded`.
   - Lockstep test in `pipeline/tests/test_entity_resolution.py`.

2. **Renderer subsections (Commit 1).**
   - `src/pages/entities/[...slug].astro`: render "Facts" and "History" subsections per § Reader-facing surfaces. Compute the derived products list at render time by scanning `entities` for `data.parent_company === entity.id`. Add CSS in the existing `<style>` block; mirror `.description` and `.legal-name` discipline.
   - **Manual backfill of one company entity** (e.g., `anthropic.md` with `founded: 2021` and a 2-paragraph history body) seeds the render surface for review and styling before the enricher exists. This is a deliberate one-shot operator action; `dr entity-enrich` (Step 7) is the long-term backfill mechanism.

3. **`LightResearchBundle` extraction (Commit 1).**
   - Lift the existing in-line block at `pipeline/orchestrator/pipeline.py:1393-1435` into `gather_light_research(entity_name, entity_type, cfg, sem, client) -> LightResearchBundle`.
   - `onboard_entity` Phase A becomes a single call to this helper.
   - `gather_light_research` returns the **raw** webpage summary in `LightResearchBundle.raw_description`; it does **not** call `_tighten_entity_description`. The enricher (Step 4) produces the tightened `description`. Removal of the standalone `_tighten_entity_description` happens in Step 7, after Phase C wiring lands so the description path stays continuous.

4. **Enricher agent (`pipeline/researcher/entity_enricher.py`, Commit 1).**
   - Pydantic model `EnrichmentDraft { founded?, description, history_markdown }`. `description` subsumes the output of `_tighten_entity_description`.
   - Per-type prompt section per § Per-type prompt sections; subject prompt solicits `description` and `history_markdown` only.
   - Agent constructor mirrors `planner.py:research_planner_agent` (Haiku, tool-free, retries=2, inline system prompt).
   - `build_entity_enricher_prompt(bundle: LightResearchBundle) -> str`.
   - `review_entity_enrichment` added to `CheckpointHandler` protocol + both handlers (CLI: stdout draft + `[a]/[r]` prompt; auto-approve: returns `"accept"`).
   - Unit tests cover prompt construction; one recorded-fixture integration test (similar to `pipeline/tests/test_researcher_decomposed.py`).

5. **`enrich_entity` helper + `dr entity-enrich` CLI + `dr onboard --force` extension (Commit 1).**
   - `enrich_entity(entity_ref, cfg, checkpoint) -> EnrichmentResult` lives in `pipeline/orchestrator/pipeline.py` next to `onboard_entity`. Loads the entity, calls `gather_light_research`, calls the enricher agent, runs the `review_entity_enrichment` checkpoint, writes back via `_write_entity_file` + `_write_entity_history`.
   - `pipeline/researcher/entity_enricher.py` stays a pure agent module (Pydantic + agent + prompt builder), mirroring `planner.py`/`scorer.py`. It does not import from `orchestrator/`.
   - `pipeline/orchestrator/cli.py`: new `dr entity-enrich <entity-ref>` subcommand. Refuses without `--force` when the entity's `history` body is non-empty.
   - `pipeline/orchestrator/cli.py`: extend `dr onboard --force` to also call `enrich_entity` after the existing `--force` overwrite work. Update the option's help text from "Overwrite existing claim files if present" to "Overwrite existing claim files **and re-run the enricher on the entity**."
   - Add `_render_enrichment_outcome(result: EnrichmentResult)` to `cli.py` next to the existing onboard-report rendering helpers (~`cli.py:1607`). Both CLI surfaces call it; prevents drift.

6. **Pipeline reads (Commit 1).**
   - `pipeline/analyst/agent.py:build_analyst_prompt`: emit `Founded:` when populated. ~2 lines.
   - `pipeline/analyst/instructions.md`: paragraph on founded-year semantics for tenure claims.
   - `pipeline/researcher/scorer.py:build_scorer_prompt`: emit `Founded:` when populated. ~2 lines.
   - `pipeline/researcher/decomposed.py`: pass `resolved_entity.founded` through to the scorer prompt.

7. **Phase C wiring into `onboard_entity` + remove `_tighten_entity_description` (Commit 1).**
   - `onboard_entity` gains Phase C (enricher) between Phase A (light research) and Phase D (template screening). Phase C calls the enricher agent directly with the `LightResearchBundle`, runs the `review_entity_enrichment` checkpoint, and threads `EnrichmentDraft` fields into `_write_entity_file` in Phase D. (Phase B verifier wiring lands in Commit 2.)
   - The enricher's `description` field replaces what `_tighten_entity_description` produced. After Phase C is wired, the standalone `_tighten_entity_description` agent has no callers and is removed in this same step.
   - Without this step, Commit 1 would write entity files with the raw webpage summary as `description` — Phase C wiring closes that gap so new onboards get tightened descriptions and rich History bodies from the start.
   - **Interim risk between Commit 1 and Commit 2**: every `dr onboard` call runs Phase C (enrichment) without a Phase B verification gate. The operator-review checkpoint at Phase C is the interim defense: if the enricher draft describes the wrong entity (because the name was ambiguous), the operator rejects the draft and re-runs with a more specific name. The cost is one wasted enrichment LLM call. Acceptable for the ~1.5 day exposure window; Commit 2 closes it permanently.

8. **Verifier agent (`pipeline/researcher/entity_verifier.py`, Commit 2).**
   - Pydantic model `VerificationOutcome { status, candidates, reasoning }`.
   - Agent constructor mirrors the enricher.
   - `build_entity_verifier_prompt(bundle: LightResearchBundle) -> str`.
   - `review_entity_disambiguation` added to `CheckpointHandler` protocol + both handlers (CLI: numbered list + free-text override prompt; auto-approve: returns `"reject"`).
   - Unit tests cover prompt construction (one per type) and outcome routing.

9. **Phase B wiring into `onboard_entity` (Commit 2).**
   - `onboard_entity` gains Phase B (verifier) between Phase A and Phase C.
   - Phase B halt path: returns from `onboard_entity` with `result.status = "rejected"` and a clear `errors` entry naming the disambiguation candidates.
   - Phase B `unverified` path: orchestrator calls `review_entity_disambiguation` with the two-element list `['unverified-startup', 'unverified-other']`; operator's pick becomes the `verification_status` kwarg passed to `_write_entity_file`.

10. **Subject onboarding documentation + verification (Commit 2).**
   - The CLI already accepts `--type subject` and the orchestrator already routes subject templates by their `subjects:` array (verified via `cli.py:1546-1548` and `pipeline.py:1451-1458`). `_screen_templates` is a passthrough today; subject onboarding inherits that behavior. **No new screening logic required for subjects in this plan.**
   - Verify the path end-to-end with a 2–3 subject pilot pass: `dr onboard "<subject>" --type subject` should run the verifier, enricher, and any pinned subject templates without orchestrator changes beyond the Phase B/C wiring from Step 8.
   - Update `docs/architecture/onboarding.md` line 68 ("Subjects are not yet a `dr onboard` intake in v1") to reflect that subjects are now first-class. Add a subject example to the flow diagram. Document that `dr onboard --force` re-runs the enricher.
   - When a subject is onboarded but no template's `subjects:` array references it, surface a warning row in the report (do not halt).

11. **Architecture docs (Commit 2).**
    - `docs/architecture/onboarding.md`: Phase A–F flow updated; `dr onboard --force` re-enrich behavior documented; subject caveat removed.
    - `docs/architecture/glossary.md`: brief entry for `founded`. The verifier/enricher are agent-internal helpers within the **Researcher** role, not new roles, so they don't get glossary entries.
    - `docs/architecture/source-quality.md` § Entity metadata: extend with one sentence on the enricher.

## Test plan

### Unit tests (Python, pytest)

- `pipeline/tests/test_entity_resolution.py`:
  - One round-trip test for `founded` (covers Pydantic ↔ frontmatter parity; the existing `_clean_for_serialize` round-trip is already covered by prior plans).
  - Lockstep: `founded` is in `CANONICAL_ENTITY_KEYS` and in the Zod schema (read source and grep).
- `pipeline/tests/test_entity_enricher.py` (new):
  - Prompt-construction test selects the right per-type section.
  - Recorded-fixture integration test for one entity per type (3 tests).
  - Subsumption test: enricher output's `description` is non-empty and replaces the previous `_tighten_entity_description` output for a fixture page summary.
- `pipeline/tests/test_entity_verifier.py` (new, Commit 2):
  - Prompt-construction test selects the right per-type section.
  - Outcome-routing tests: `verified` / `needs-disambiguation` / `unverified` against fixture LLM responses.
- `pipeline/tests/test_checkpoints.py`:
  - `AutoApproveCheckpointHandler.review_entity_enrichment` returns `"accept"`.
  - (Commit 2) `AutoApproveCheckpointHandler.review_entity_disambiguation` returns `"reject"`. Integration with `onboard_entity`: `needs-disambiguation` + auto-approve handler → `OnboardResult.status == "rejected"` with the candidates in the errors entry.

### Site / build tests

- Build with the current tree → succeeds.
- Build with the manual `anthropic.md` backfill (`founded` + history body) → succeeds; rendered page shows Facts and History subsections.

### Manual rendering verification

Run `inv dev` and confirm:

1. `/entities/companies/anthropic` shows Facts (Founded, derived Products list) and History.
2. `/entities/products/claude` shows Facts (Founded only) and History after `dr entity-enrich`.
3. `/entities/subjects/generative-ai` shows History after `dr entity-enrich`.
4. Entities without any new fields render exactly as today (no empty subsections).
5. The derived Products list on `/entities/companies/anthropic` shows products whose `parent_company === companies/anthropic`. Adding a new product with that parent makes it appear without a backfill.

### End-to-end CLI tests (Commit 1)

- `dr entity-enrich entities/companies/openai` against a recorded fixture → `openai.md` gains `founded` and a history body; existing fields round-trip unchanged.
- `dr entity-enrich entities/companies/openai` (no `--force`) when the file already has a history body → refuses with a clear message.

### End-to-end CLI tests (Commit 2)

- `dr onboard "Anthropic" --type company` against a recorded-LLM fixture → verifier returns verified, enricher produces a draft, auto-approve handler accepts, entity file lands with Facts and History.
- `dr onboard "Apple" --type product` (a known disambiguation case: company name collides) → verifier returns needs-disambiguation; with auto-approve handler the run rejects with a useful errors entry.
- `dr onboard "OpenAI" --type company --force` against an existing OpenAI entity → re-runs the enricher and persists updated fields, in addition to the existing `--force` overwrite behavior.

### Subject pilot (manual, pre-merge of Commit 2)

Run `dr entity-enrich` (Commit 1) and then `dr onboard` (Commit 2) on the two existing subjects (`ai-model-producers`, `generative-ai`) plus 2–3 pilot subjects. Goal: per-type prompt produces drafts the operator accepts (with light edits) at least 80% of the time. Lower acceptance triggers a prompt revision pass before Commit 2 merges.

## Done when

### Commit 1 (MVP — reader-visible enrichment, including new onboards)

1. Zod schema accepts `founded`. Build passes against current tree and against the manual backfill.
2. `ResolvedEntity.founded` populated by `parse_entity_ref`; existing entity files round-trip unchanged.
3. `_entity_frontmatter` emits `founded` when populated; `_write_entity_history` writes markdown body when the enricher returns non-empty `history_markdown`.
4. `CANONICAL_ENTITY_KEYS` includes `founded`; `dr lint` issues no warnings on the manually-backfilled `anthropic.md`.
5. `LightResearchBundle` + `gather_light_research` extracted from `onboard_entity`; the in-line block at `pipeline.py:1393-1435` is replaced by a single call.
6. `entity_enricher.py` exists with typed Pydantic output, retries=2, Haiku-class default, per-type prompt sections, and unit tests.
7. `dr entity-enrich <entity-ref>` re-enriches an existing entity; refuses without `--force` on a non-empty history body.
8. `dr onboard --force` re-runs the enricher in addition to its existing overwrite behavior; help text updated.
9. `_render_enrichment_outcome` exists in `cli.py` and is used by both CLI surfaces.
10. `onboard_entity` Phase C wires the enricher; new onboards get tightened descriptions and rich History bodies in the same pass. (Phase B verifier wiring is Commit 2; until then, all names go to enrichment without a verification gate.)
11. `_tighten_entity_description` is removed; the enricher's `description` field replaces it. No caller remains.
12. Analyst and scorer prompts emit `Founded:` when populated; analyst instructions paragraph in place; scorer change verified by the existing `test_researcher_decomposed.py` pattern.
13. Render surfaces (Facts + History) work for at least three existing entities (one per type) backfilled via `dr entity-enrich`.

### Commit 2 (verification gate + subject onboarding hardening)

14. `entity_verifier.py` exists with typed Pydantic output and per-type sections.
15. `review_entity_disambiguation` added to `CheckpointHandler` and both handler implementations; reuses `review_onboard`'s sentinel-or-payload signature.
16. `onboard_entity` Phase B wires the verifier; halts with a useful candidates list on `needs-disambiguation`; `unverified` halt routes through `review_entity_disambiguation` with the two-element schema-enum list.
17. `dr onboard --type subject` works end-to-end with a 2–3 subject pilot pass.
18. Subject onboarding with no template `subjects:` hit emits a warning row.
19. `docs/architecture/onboarding.md`, `docs/architecture/glossary.md`, `docs/architecture/source-quality.md` updated.

## Out of scope

- Non-interactive `--resume` protocol for `dr onboard`. Operators run `dr onboard` interactively; CI uses the auto-approve handler.
- `headquarters`, `employee_count_band`, `subsidiaries`, `near_homophones`, automated `legal_name` filling, COI agent. Each is a separate plan when it earns reader value.
- Verification badge on **claim pages** when the claim's subject is unverified. Already deferred by `entity-metadata-surface`.
- Re-verification cadence (running the verifier periodically against existing entities).
- LLM-driven template screening. `_screen_templates` stays a passthrough; LLM screening is its own plan.
- Migrating the verifier/enricher to a persisted workspace (`pipeline-state-machine_stub.md`). The two agents are typed-input/typed-output and will plug in cleanly when the workspace pattern lands; this plan does not depend on or block that work.
- `EntityMetadata` dataclass refactor. Suggested in review but expands scope; the writer's kwarg list is acceptable for one more field. Worth a dedicated cleanup plan when the next field arrives.
- Renaming `pipeline/auditor/` → `pipeline/evaluator/`.

## Effort estimate

**~5 days end-to-end.** Commit 1 (MVP) lands in ~3.5 days; Commit 2 in ~1.5 more.

- Commit 1:
  - Schema + ResolvedEntity + writer + linter + render + manual backfill (Steps 1, 2): ~1 day.
  - `LightResearchBundle` extraction (Step 3): ~0.3 day.
  - Enricher agent + prompts + tests (Step 4): ~1 day.
  - `enrich_entity` helper + CLI + `_render_enrichment_outcome` + analyst/scorer reads (Steps 5, 6): ~0.5 day.
  - Phase C wiring + `_tighten_entity_description` removal (Step 7): ~0.5 day.
- Commit 2:
  - Verifier agent + checkpoint + tests (Step 8): ~1 day.
  - Phase B wiring + subject pilot + arch docs (Steps 9, 10, 11): ~0.5 day.

Subject pilot is the riskiest slice. If prompt acceptance is low, allocate buffer for a revision pass.

## Dependencies

- [`completed/entity-metadata-surface_completed.md`](completed/entity-metadata-surface_completed.md) — schema slot for `verification_status`, writer-side emission, render badge. Hard prerequisite (already shipped).
- A search backend for the verifier/enricher's input bundle (Tavily or Brave; both currently used by the Researcher). No new env var; reuse `RESEARCH_SEARCH_BACKEND`.
- LLM agent infrastructure already shipped via `pipeline/researcher/scorer.py` / `planner.py`.

## Critical files (implementation phase)

- `pipeline/researcher/entity_enricher.py` — new (Commit 1)
- `pipeline/researcher/entity_verifier.py` — new (Commit 2)
- `pipeline/orchestrator/pipeline.py` — `LightResearchBundle`, `gather_light_research`, `enrich_entity`, `onboard_entity` Phase B/C wiring; removal of `_tighten_entity_description`
- `pipeline/orchestrator/checkpoints.py` — `review_entity_enrichment` (Commit 1) and `review_entity_disambiguation` (Commit 2) on the protocol and both handlers
- `pipeline/orchestrator/persistence.py` — `_entity_frontmatter` learns `founded` kwarg; new `_write_entity_history` helper
- `pipeline/orchestrator/cli.py` — `dr entity-enrich` subcommand; `dr onboard --force` extension; `_render_enrichment_outcome` helper
- `pipeline/linter/checks.py` — `CANONICAL_ENTITY_KEYS` extension
- `pipeline/orchestrator/entity_resolution.py` — `ResolvedEntity` passthrough
- `src/content.config.ts` — `founded` schema field
- `src/pages/entities/[...slug].astro` — Facts and History subsections; derived products list
- `pipeline/analyst/agent.py` + `pipeline/analyst/instructions.md` — `Founded:` line + paragraph
- `pipeline/researcher/scorer.py` + `pipeline/researcher/decomposed.py` — `Founded:` line in scorer prompt
- `docs/architecture/onboarding.md`, `docs/architecture/glossary.md`, `docs/architecture/source-quality.md` — doc updates

## Cross-references

- Stub origin: `drafts/entity-onboarding-research_stub.md` (deleted on promotion).
- Schema-and-render prerequisite: `completed/entity-metadata-surface_completed.md`.
- Parallel agent-shape precedent: `pipeline/researcher/planner.py`, `pipeline/researcher/scorer.py`.
- Adjacent work that could ride along but is **not** scoped here: `headquarters`, `subsidiaries`, COI agent, claim-page verification badge, LLM-driven template screening, `EntityMetadata` dataclass refactor.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-09 | agent (opus-4-7) | initial stub | Created during `entity-metadata-surface` planning. Substance pulled from `source-quality-followups.md` § Section 1 entries. |
| 2026-05-09 | agent (opus-4-7) | iterated, deep | Promoted from stub to plan. Operator decisions folded in: enrichment-first (reader-visible), thin verifier, subjects as first-class onboarding intake, two agents (verifier + enricher), files inside existing `pipeline/researcher/` package. Dropped non-interactive `--resume` protocol, `unverified-acknowledged` outcome, `employee_count_band` / `subsidiaries` / explicit `products` schema field. Added derived products list, `dr entity-enrich`, manual-backfill MVP cut, subject pilot acceptance criterion. |
| 2026-05-09 | advisor pass | iterated | Three fixes: (1) MVP cut was internally inconsistent (claimed `dr entity-enrich` MVP without the enricher agent) — Step 4 added explicitly; (2) type-conditioned schema corrected from Zod-level to convention + linter; (3) Step 7 (subject onboarding) reframed as doc-only after verifying `_screen_templates` is a passthrough and the CLI already accepts `--type subject`. |
| 2026-05-09 | operator review | iterated | Renamed `dr enrich` → `dr entity-enrich`; `dr onboard --force` re-runs the enricher; **dropped `near_homophones` entirely** (audio-input rationale didn't apply). |
| 2026-05-09 | three-pass review (simplicity, reusability, workflow clarity) | iterated, deep | Substantial pass. **Simplicity**: dropped `headquarters` (no concrete claim-axis demand); dropped per-type linter rule; dropped `$EDITOR` temp-file UX in favor of stdout draft + `[a]/[r]`; resolved all five open questions in-place; dropped explicit "step-shaped for future state machine" framing. **Reusability**: introduced `LightResearchBundle` shared by both new agents (no duplicate fetch); subsumed `_tighten_entity_description` into the enricher; `review_entity_disambiguation` reuses `review_onboard`'s sentinel-or-payload signature (also covers `unverified` halt); pinned `enrich_entity` to `pipeline/orchestrator/pipeline.py`; added `_render_enrichment_outcome` CLI helper. **Workflow clarity**: added §Operator usage block with literal commands; renamed runtime sequence to Phases A–F (distinct from numbered Implementation steps); tagged each Implementation step with `(Commit 1)`/`(Commit 2)`; added verifier-output → frontmatter contract table; split Done-when into Commit 1 / Commit 2 sections per `entity-metadata-surface` precedent; reworded the "staged change" claim. **Deferred**: `EntityMetadata` dataclass refactor and `ENTITY_TYPE_PROFILE` central registry — both real cleanups, but expand scope without delivering reader value this plan; moved to Out-of-scope and Cross-references. |
| 2026-05-09 | advisor consistency check | iterated | Three follow-up fixes after the synthesis pass: (1) Phase C wiring moved from Commit 2 to Commit 1 — without it, `dr onboard` (no `--force`) would have written entities with raw page summary as `description` between Commit 1 and Commit 2, since `_tighten_entity_description` was being removed; new Step 7 in Commit 1 wires Phase C and removes the standalone helper atomically; (2) enricher input dropped its dependency on `VerificationOutcome` — `dr entity-enrich` doesn't run the verifier, so the dependency was overspec'd; the orchestrator decides whether to run the enricher; (3) Step 3 rewritten so `gather_light_research` returns the raw description and never calls `_tighten_entity_description` (Step 7 removes it). Done-when restructured: Commit 1 now includes Phase C wiring (item 10) and `_tighten_entity_description` removal (item 11); Commit 2 only adds Phase B verifier wiring. Effort split adjusted: Commit 1 ~3.5 days, Commit 2 ~1.5 days. Phase typo (A–E → A–F) corrected. |
