# Sub-question decomposition

**Type**: Implementation plan
**Created**: 2026-05-07
**Trigger**: Verdict quality on the existing corpus is substandard pre-launch. The researcher's planner+scorer collapses the source pool onto a single semantic axis (entity match), so the analyst receives evidence dense on one axis and empty on others. Empirical case: `research/claims/brave-leo/discloses-energy-sourcing.audit.yaml`. Planner emitted 5 queries all on the "Brave Leo + energy" axis, scorer kept 20 product/feature articles and dropped the only sustainability candidate as off-topic, analyst returned `unverified` with `high` confidence on a pool that contained no source structurally capable of containing the answer.

## Summary

Push sub-question decomposition into the researcher only. The existing `query_planner_agent` is renamed to `research_planner_agent` and extended to emit a `ResearchPlan` containing **sub-questions** and **queries-per-sub-question**. The scorer becomes sub-question-aware: it tags each kept candidate with the sub-question(s) it addresses. The orchestrator threads sub-question identity through to the analyst, which receives sub-questions in the prompt and per-source `addresses` tags (the list of sub-question ids each source serves). The analyst is instructed to verify per-sub-question coverage before rendering a high-confidence verdict.

This is the smallest delta that addresses the brave-leo failure: search-axis collapse is fixed at the planner+scorer stage, and the analyst gets enough structure to refuse high confidence on uncovered axes. If spot-checks show this isn't enough, an escalation path (per-sub-question analysis pass, no new typed scaffolding) is documented in § Escalation path: A-minimal.

The change is data-shape-light and prompt-heavy. No state machine. The claim lifecycle in `docs/architecture/research-flow.md` is unchanged. No new agents.

## Goals

- Generate research queries along **multiple claim axes** rather than one entity-keyed axis.
- Score and tag each kept candidate by which sub-question(s) it addresses.
- Give the analyst an explicit per-sub-question coverage signal so it cannot render `true`/`false` with `high` confidence on a pool that doesn't address every sub-question.
- Make the sub-question structure visible in the audit sidecar so a reader can see the axes the pipeline considered.

## Non-goals

- Per-sub-question mini-analysis pass (see § Escalation path: A-minimal — only used if this plan's prompt-only approach proves unstable).
- Synthesizer/analyst split (deferred).
- Audit sidecar version bump (additive only).
- Claim-page UI surfacing of sub-questions (defer until corpus rerun confirms verdict-quality gain).
- Code-level verdict aggregation rules (instructions-only for first release).
- Iterative gap-fill / second research round (deferred; tracked in `docs/plans/research-quality-ideas.md`).
- Tool-using analyst with a `gap_search` tool (deferred; tracked in `docs/plans/research-quality-ideas.md`).

## Naming changes

Pre-existing names that don't fit after the change. New types named in the right column are defined in § Schema additions below; this table is the rename map.

| Today | After | Reason |
|---|---|---|
| `QueryPlan` | `ResearchPlan` | Plan now contains sub-questions, not just queries. |
| `query_planner_agent` | `research_planner_agent` | Symmetry with the renamed type. |
| `_PLANNER_INSTRUCTIONS` | `_RESEARCH_PLANNER_INSTRUCTIONS` | Local constant in `planner.py`. |
| `ScoredURLs.kept: list[str]` | `ScoredURLs.kept: list[ScoredCandidate]` | Each kept URL now carries an `addresses: list[str]` of sub-question ids. |
| `ResearchResult` (entire class, classic path) | retired | Classic path is dropped; see § 7. |
| `cfg.researcher_mode` | retired | The decomposed path is the only path. |

Internal function `decomposed_research()` keeps its name. The word "decomposed" now refers to sub-question fan-out at scoring/attribution time (it previously referred only to per-query parallel fetch). The new meaning is a superset of the prior one; renaming would touch `pipeline/orchestrator/pipeline.py:_research` and test imports for cosmetic gain.

## Schema additions

### New: `SubQuestion` (Pydantic, `pipeline/common/models.py`)

```python
class SubQuestion(BaseModel):
    id: str = Field(
        pattern=r"^sq\d+$",
        description="Stable id within a claim. Format: 'sq1', 'sq2', ... (sequential within a ResearchPlan)."
    )
    question: str = Field(description="An independently answerable factual question.")
    rationale: str = Field(
        description="One-sentence justification for why this sub-question belongs in the decomposition; surfaced in the audit sidecar."
    )
```

No `criticality`, no `expected_source_classes`. Add later if needed.

### Extended: `ResearchPlan` (renamed from `QueryPlan`, in `pipeline/researcher/planner.py`)

```python
class PlannedQuery(BaseModel):
    text: str
    sub_question_id: str = Field(description="Matches a SubQuestion.id within the same ResearchPlan.")

class ResearchPlan(BaseModel):
    sub_questions: list[SubQuestion] = Field(min_length=2, max_length=5)
    queries: list[PlannedQuery] = Field(
        description="Search queries, each tagged with the sub-question it serves."
    )
    rationale: str = Field(description="One-line justification for why these sub-questions cover the claim.")
```

Cap: 2–5 sub-questions, total queries truncated by `cfg.max_initial_queries` (default 5) — but the truncation now spreads across sub-questions rather than emitting 5 single-axis queries.

### Extended: `ScoredCandidate` (new, in `pipeline/researcher/scorer.py`)

```python
class ScoredCandidate(BaseModel):
    url: str
    addresses: list[str] = Field(
        description="Sub-question ids (each matches a SubQuestion.id within the same ResearchPlan) this candidate is judged to address. Non-empty by construction; only kept candidates carry `addresses`."
    )

class ScoredURLs(BaseModel):
    kept: list[ScoredCandidate]
    dropped: list[str]
    rationale: str
```

A candidate may address more than one sub-question (a Brave transparency-report page might address both "does Brave publish energy data?" and "does Brave publish training-data policies?"). Empty `addresses` is invalid by construction.

### Extended: in-memory source dict

The orchestrator already builds a list of source dicts for the analyst via `pipeline/orchestrator/pipeline.py:_build_source_dict`. Add one field:

```python
source_dict["addresses"] = ["sq1", "sq3"]  # list of SubQuestion.id values this source serves
```

`_build_source_dict` itself does not have the URL→addresses map in scope, so the orchestrator mutates `addresses` onto the dict after calling `_build_source_dict`, joining each ingested URL back to the corresponding `ScoredCandidate.addresses` list. **Not persisted on the source frontmatter**: this is per-claim attribution, not a property of the source.

### Extended: `VerificationResult` (in-memory, `pipeline/orchestrator/pipeline.py`)

Add:

```python
sub_questions: list[SubQuestion] = Field(default_factory=list)
sub_question_coverage: dict[str, list[str]] = Field(
    default_factory=dict,
    description="Map SubQuestion.id -> list of source_ids that addressed it after ingest. "
                "Example: {'sq1': ['2026/brave-transparency-report'], 'sq2': []}.",
)
```

Both populated by the orchestrator after research+ingest, before analyst. An empty list value signals an uncovered sub-question.

## Sidecar additions (additive, no version bump)

`schema_version: 1` stays. The existing `research:` block is preserved verbatim: `mode`, `queries` (flat union), `planner_rationale`, `candidates_seen`, `urls_kept` (count), `urls_dropped` (count), `scorer_rationale`, `urls_after_blocklist`. Note: `urls_kept`/`urls_dropped` stay as integer counts; per-candidate `addresses` flow through the new top-level `sub_questions:` block only. Add one new top-level key, sibling to `research:`, named `sub_questions:`:

```yaml
# sub_questions: per-sub-question record of the decomposition the planner emitted.
# `citations` is the post-ingest list of source-ids that addressed this sub-question
# (sources whose ScoredCandidate.addresses included this id AND that ingested successfully).
# An empty `citations` list signals an uncovered axis; it is what the analyst's
# coverage rule keys off, and what `dr lint` will key off later.
sub_questions:
  - id: sq1
    question: "Does Brave publish energy sourcing information for Leo's hosted models?"
    rationale: "Direct restatement of the claim's central assertion."
    queries:
      - "Brave transparency report energy"
      - "Brave sustainability disclosure"
    citations:
      - 2026/brave-transparency-report
      - 2026/brave-about-page
  - id: sq2
    question: "Do third-party ESG databases profile Brave Software's energy disclosures?"
    rationale: "Independent corroboration channel for entity-level disclosure."
    queries: [...]
    citations: []
```

Naming note: `citations` (in the sidecar) is the sub-question→sources view; `addresses` (on each in-memory source dict and on `ScoredCandidate`) is the source→sub-questions view. Same data, transposed.

Sidecars written before this change have no `sub_questions:` key; readers should treat their coverage as unknown.

## Implementation

Order of work:

### 1. Type and naming changes (`pipeline/common/models.py`, `pipeline/researcher/planner.py`, `pipeline/researcher/scorer.py`)

- Add `SubQuestion` to `common/models.py`.
- Rename `QueryPlan` → `ResearchPlan` in `planner.py`. Add `PlannedQuery` and the new `sub_questions: list[SubQuestion]` field. Update prompt instructions to emit sub-questions and tagged queries (see § Planner prompt below).
- Rename `query_planner_agent` → `research_planner_agent` in `planner.py` and at all call sites: `pipeline/researcher/decomposed.py` (import + `.override()` + `.run()`), `pipeline/tests/test_researcher_decomposed.py`, and `pipeline/tests/test_acceptance.py`.
- Add `ScoredCandidate` to `scorer.py`. Change `ScoredURLs.kept` from `list[str]` to `list[ScoredCandidate]`. The downstream consumers in `decomposed.py` and `pipeline.py:_research` must be updated to read `c.url` rather than treating each item as a string. Update prompt to require per-candidate `addresses` tags (see § Scorer prompt below).
- Classic-path retirement is its own work item; see § 7 for the full list of files and symbols to remove.

### 2. Planner prompt (`pipeline/researcher/planner.py`)

Replace `_PLANNER_INSTRUCTIONS`. New prompt:

> You are a research planner. Given a claim and entity, decompose the claim into 2–5 **sub-questions**, then generate search queries per sub-question.
>
> A good sub-question is independently answerable, factually framed, and covers one axis of the claim. The union of sub-questions should cover the whole claim. Sub-question ids are sequential (`sq1`, `sq2`, ...).
>
> For environmental, privacy, and disclosure claims, sub-questions typically include: (1) the entity's own first-party publication channels (transparency reports, sustainability pages), (2) third-party databases (ESG aggregators, regulator filings, model cards), (3) the underlying technical or factual mechanism (e.g. hosting provider, training pipeline). Cover all three when applicable.
>
> Then generate 2–`max_initial_queries` total search queries, distributed across sub-questions. Each query is tagged with `sub_question_id`. Queries must follow Brave query format (no `site:`, no `intitle:`, no chained quoted phrases — see existing instructions).

Keep the existing Brave query-format guidance from `_PLANNER_INSTRUCTIONS` verbatim (no `site:`, no `intitle:`, no chained quoted phrases).

### 3. Scorer prompt (`pipeline/researcher/scorer.py`)

Replace `_SCORER_INSTRUCTIONS` to:

- Receive a list of sub-questions in addition to claim and entity.
- Score each candidate per sub-question (5-point scale, same as today).
- Keep candidates that score ≥4 on **at least one** sub-question.
- Tag each kept candidate with `addresses` = sub-question ids where it scored ≥4.
- Drop candidates that score <4 on every sub-question.
- Use `publisher_quality` as a per-sub-question tiebreaker as today.

Build prompt updated in `build_scorer_prompt(...)`: takes `sub_questions: list[SubQuestion]` parameter and prepends a sub-question block to the prompt. The candidate listing is unchanged.

### 4. Orchestrator wiring (`pipeline/orchestrator/pipeline.py`, `pipeline/researcher/decomposed.py`)

- Today `decomposed_research()` returns a flat `list[str]` of URLs plus a trace dict, which discards per-candidate `addresses`. Change it to return a structured `ResearchOutput` carrying both the URL list and the URL→addresses mapping derived from `ScoredURLs.kept`:

  ```python
  class ResearchOutput(BaseModel):
      urls: list[str]
      url_addresses: dict[str, list[str]] = Field(
          description="Map url -> SubQuestion.id values this URL was scored as addressing."
      )
      sub_questions: list[SubQuestion]
      errors: list[StepError]
      trace: dict
  ```

  (Pydantic `BaseModel` for consistency with the other new types in this plan.)

- `_research()` returns the full `ResearchOutput`; `verify_claim` stores `sub_questions` and the URL→addresses map.
- After ingest, the orchestrator inverts `url_addresses` (url → sq-ids) into `sub_question_coverage` (sq-id → source-ids), keying off ingested source-ids only. This is the value stored on `VerificationResult.sub_question_coverage`.
- The source-pool dict built for the analyst gets each source's `addresses: list[str]` populated from the same URL→addresses map (the inverse of the coverage map).
- After ingest, log per-sub-question coverage. Do **not** block on partial coverage; the analyst handles partial gaps editorially via verdict + confidence (see § 5, rule 3). The existing `< 4 usable sources` threshold stays as the all-empty backstop.

### 5. Analyst prompt extension (`pipeline/analyst/instructions.md`, `pipeline/analyst/agent.py`)

Add a new instructions section after `RULES:`:

> SUB-QUESTION COVERAGE:
>
> The user prompt lists 2–5 sub-questions that decompose the claim, and each source carries an `addresses` field listing which sub-questions it serves. Before deciding the verdict:
>
> 1. For each sub-question, count how many sources address it.
> 2. If every sub-question has ≥1 addressing source, treat the pool as fully covered. Verdict and confidence follow the normal rules.
> 3. If any sub-question has zero addressing sources, the pool has a coverage gap. The narrative MUST name the uncovered sub-question(s). The verdict cannot be `true` or `false` with `high` confidence; choose `unverified` (when the gap dominates) or render the available verdict at `medium` confidence with the gap explicit. The confidence cap is editorial, not mechanical: a single uncovered supporting axis on an otherwise multi-source claim does not force `unverified`.
> 4. The `verification_level` derivation is unchanged — it is computed on the union pool's `independence` distribution as before. Coverage gaps are reflected in `confidence` and narrative, not in `verification_level`.

Update `build_analyst_prompt(...)` in `analyst/agent.py`:

- After the entity block, before the source materials section, insert a `## Sub-questions` block listing each sub-question's id, question, and rationale.
- In each `## Source N:` block, add an `Addresses:` line listing the sub-question ids this source serves.

### 6. Audit sidecar writer (`pipeline/orchestrator/persistence.py`)

`_write_audit_sidecar(...)` gains one new optional parameter: `sub_questions_block: list[dict] | None = None`. When non-None, it's added as a top-level `sub_questions:` key in `sidecar_data` between `research` and `sources_consulted`. `schema_version` stays `1`.

The block is built by the orchestrator from `VerificationResult.sub_questions` and `sub_question_coverage`. Format matches § Sidecar additions above.

### 7. Classic researcher path retirement

Drop, in order:

- `cfg.researcher_mode` from `VerifyConfig` in `pipeline/orchestrator/pipeline.py` (today flagged in the source as a temporary validation scaffold).
- The `classic` branch in `pipeline/orchestrator/pipeline.py:_research`, plus the now-unused `ResearchDeps` import from `pipeline/researcher/agent.py`.
- The classic-path artifacts in `pipeline/researcher/agent.py`: `research_agent`, `ResearchResult`, `_INSTRUCTIONS`, `web_search`, and the `load_instructions(...)` call that loads the classic-path system prompt. Keep `search_brave` (the Brave API client used by `decomposed.py`).
- `pipeline/researcher/instructions.md` (the classic-path system prompt file).

### 8. Threshold

Existing `below_threshold(usable_sources) < 4` rule is kept verbatim — it's the all-empty backstop. **No new `insufficient_coverage` `BlockedReason`.** The analyst handles partial coverage editorially.

### 9. Checkpoints

`review_sources` checkpoint stays where it is, fires after ingest. Update its display payload to include the per-sub-question coverage summary so the operator sees `sq1: 3 sources, sq2: 1 source, sq3: 0 sources` alongside the existing source list. No new checkpoint.

### 10. CLI

No CLI surface changes. `dr claim-refresh`, `dr claim-probe`, `dr onboard` all work unchanged. Internal verbose logs gain a per-sub-question coverage line.

## Migration & corpus rerun

1. Land changes 1–9 on a feature branch (`feat/sub-question-research`).
2. Run `dr claim-probe` against `brave-leo/discloses-energy-sourcing` and `brave-leo/no-training-on-user-data`. Inspect sidecars: confirm `sub_questions:` block populated, confirm coverage matches expectation, confirm verdict shifts in the expected direction.
3. Spot-check 4–6 more representative claims (one from each topic area: env, privacy, training data, regulation, industry analysis, consumer guide). Inspect verdicts and narratives.
4. If verdict drift on any spot-check is unexplained or wrong, pause and pivot to A-minimal (escalation path § below).
5. Once spot-checks look right, merge the feature branch.
6. Open a separate branch `rerun-sub-question-mode`. Run `dr claim-refresh --entity=<name>` per entity. Commit per-entity. Use the per-entity commits for verdict-diff inspection against `main`.
7. After all entities rerun, diff verdicts and verification levels in aggregate. Spot-check the 10–15 claims whose verdict or confidence changed. Reject and reroll any that look wrong.
8. Merge `rerun-sub-question-mode` to `main`.

## Tests

### New: planner fixture (`pipeline/tests/test_research_planner.py`)

Curated 6–10 claim corpus. For each claim, assert on the planner output **shape**, not exact text:

- 2 ≤ `len(plan.sub_questions)` ≤ 5.
- Each sub-question has `id`, `question`, `rationale` populated.
- All `query.sub_question_id` values reference a sub-question id.
- For known claim shapes, assert sub-question count matches expectation (e.g. compound claims should produce ≥3, single-axis claims should produce 2).
- For environmental disclosure claims, assert at least one sub-question text contains a transparency/ESG/sustainability keyword (a soft check via case-insensitive substring match).

### New: scorer per-sub-question test (`pipeline/tests/test_scorer.py` or extension of an existing scorer test)

Synthesize a claim with 3 sub-questions and 6 candidates with known relevance per sub-question. Assert each kept candidate's `addresses` matches expectation. Existing scorer fixtures must also be updated for the `kept: list[ScoredCandidate]` shape.

### Existing: prompt-builder tests

Update `pipeline/tests/test_analyst.py` (where `build_analyst_prompt` is exercised today) to assert the `## Sub-questions` block renders and per-source `Addresses:` lines render.

### Existing: pipeline integration test

Update integration test fixtures to construct `ResearchPlan` instead of `QueryPlan`: specifically `pipeline/tests/test_researcher_decomposed.py` (the `QueryPlan(queries=...)` call sites) and the stage harness in `pipeline/tests/test_acceptance.py`. Confirm the resulting sidecar contains the `sub_questions:` block.

## Rollback

Branch-based. The feature branch can be reverted before `rerun-sub-question-mode`. After rerun-merge, rollback requires either reverting both branches or rerunning the corpus on the pre-change pipeline. Acceptable risk pre-launch; the site is unlaunched.

## Documentation (last)

- `docs/architecture/research-flow.md` § 6 — replace the decomposed researcher diagram. New diagram shows planner emitting sub-questions, scorer tagging candidates, source pool carrying `addresses`, analyst consuming sub-questions block.
- `docs/architecture/source-quality.md` — short note in § "What the system cannot do" or a new § that the source pool is now per-sub-question relevant; `verification_level` derivation is unchanged.
- `pipeline/researcher/planner.py` — embedded prompt is the source of truth for planner behavior.
- `pipeline/researcher/scorer.py` — embedded prompt is the source of truth for scorer behavior.
- `pipeline/analyst/instructions.md` — new SUB-QUESTION COVERAGE section.
- `AGENTS.md` — update if it lists planner/scorer responsibilities.
- Drop `pipeline/researcher/instructions.md` (classic-path artifact).
- Update one or two recent claim audit sidecars by hand in `docs/` if any are referenced as examples.

Documentation is the last work item, after the corpus rerun confirms the change holds up.

## Escalation path: A-minimal

If the existing analyst, even with sub-question awareness in its prompt, produces unstable verdicts on the spot-check sample (e.g. averages across mixed-axis pools, fails to flag coverage gaps in narrative, drifts on `verification_level` derivation), pivot to A-minimal:

1. Add a per-sub-question analysis pass: reuse the analyst agent infrastructure with a narrow prompt that produces, per sub-question, a short prose `finding` and a `citations: list[str]`.
2. Persist findings under each sub-question entry in the sidecar (`finding: "…"`).
3. Pass findings to the claim-level analyst pass as additional structured input. The claim-level pass continues to use the existing analyst prompt (with one new section instructing it to consider findings + union pool together).
4. No `SubQuestionStance`, no `SubQuestionCoverage`, no `SubQuestionFinding` typed model — just a prose string + citations. No sidecar version bump.

Cost: one extra analyst-shape call per sub-question (~3× narrow analyst calls per claim). Most of B+'s plumbing is reused; only the per-sub-question prompt + the orchestrator fan-out are new.

## Open questions

These are tunable defaults, not blockers. `OPEN-N` ids match the open-questions register in `docs/plans/research-quality-ideas.md`.

1. `OPEN-2`: Per-sub-question source budget. Today: `max_sources=8` total, `candidate_pool_size=24` total. Soft per-sub-question caps may help avoid one axis dominating the pool. Tune empirically after the rerun.
2. `OPEN-7`: Threshold floor numbers. Today's `< 4 usable sources` claim-level floor is preserved; revisit if rerun shows it's too strict for the per-sub-question regime.
3. `OPEN-11`: Whether to surface sub-question coverage in the audit-page UI is tracked separately. Out of scope for this plan; see Non-goals.

## Critical files for implementation

- `pipeline/common/models.py` — add `SubQuestion`.
- `pipeline/researcher/planner.py` — rename + extend `ResearchPlan`, update prompt.
- `pipeline/researcher/scorer.py` — `ScoredCandidate.addresses`, update prompt, update `build_scorer_prompt`.
- `pipeline/researcher/decomposed.py` — return `ResearchOutput` (new Pydantic model in this file) with sub-questions + URL addresses.
- `pipeline/researcher/agent.py` — drop classic-path artifacts, keep `search_brave`.
- `pipeline/researcher/instructions.md` — delete (classic-path system prompt).
- `pipeline/orchestrator/pipeline.py` — drop `researcher_mode`, thread sub-questions + addresses, populate `VerificationResult.sub_questions` and `sub_question_coverage`, build per-source `addresses`, update analyst prompt builder call.
- `pipeline/orchestrator/persistence.py` — `_write_audit_sidecar` accepts `sub_questions_block`.
- `pipeline/orchestrator/checkpoints.py` — `review_sources` payload includes per-sub-question coverage.
- `pipeline/analyst/instructions.md` — new SUB-QUESTION COVERAGE section.
- `pipeline/analyst/agent.py` — `build_analyst_prompt` renders `## Sub-questions` block + per-source `Addresses:` line.
- `pipeline/tests/test_research_planner.py` (new) — planner fixture corpus.
- `docs/architecture/research-flow.md` — diagram update (last).
- `docs/architecture/source-quality.md` — short note (last).

## Cross-references

- `docs/plans/research-quality-ideas.md` — ideas backlog this draws from
- `docs/plans/drafts/analyst-decomposition_stub.md` — orthogonal decomposition (decomposes the analyst itself)
- `docs/architecture/research-flow.md` — current pipeline diagrams
- `docs/architecture/source-quality.md` — verification scale, cap_rationale (unchanged by this plan)
- `pipeline/researcher/decomposed.py` — the existing decomposed researcher being extended
- `pipeline/analyst/instructions.md` — current analyst editorial discipline (preserved)
- Scoping context (alternatives considered, simplification path) was decided in unpersisted conversation; no external doc to cite.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-07 | agent (claude-opus-4-7) | basic | initial stub (Path A) |
| 2026-05-07 | agent (claude-opus-4-7) | rewrite | scope shift to Path B+; renames; implementation details |
