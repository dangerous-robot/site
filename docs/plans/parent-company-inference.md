# Plan: infer `parent_company` during product onboarding

**Status**: ready
**Last updated**: 2026-04-27
**Depends on**: `parent_company` schema field on entities (landed 2026-04-27 in `src/content.config.ts`).

## Context

Product entities now carry an optional `parent_company` slug pointing at a company entity (e.g., `claude.md` → `parent_company: anthropic`). Today the operator fills this in by hand. This plan adds an inference step during `dr onboard` for products so the field is pre-populated before the operator hits the `review_onboard` checkpoint.

The question this plan answers: is parent-company inference a fit for the small-model tier in the cascade policy described in [`docs/architecture/glossary.md` § Model-tier discipline](../architecture/glossary.md), or does it need a frontier model?

**Short answer**: yes, it fits. The task is single-step classification with a constrained output (one slug or null), the input is short (entity name + website + first paragraph of description), and the most common cases (well-known products) are within a small model's training data.

## Goals

- After `dr onboard <product>` produces a draft entity, run a small-model call that returns one of: an existing company slug, a suggested-new-company slug + name, or `null`.
- Surface the result in the existing `review_onboard` checkpoint so the operator confirms or overrides before anything is written.
- Never write a `parent_company` value that doesn't resolve to an existing company entity. If the model returns a new candidate, the operator confirms onboarding the company first or skips the link.
- Cost ceiling: under one cent per onboard. Latency ceiling: under two seconds added to the onboard flow.

## Non-goals

- Inferring parent company for entities other than products. Companies, sectors, and topics don't have one.
- Reverse direction (`products: [...]` on company entities). Single-direction reference, written on the product side only.
- Backfilling existing product entities — they're already populated by hand (claude → anthropic, gemini → google) or have no parent (treadlightlyai).
- Maintaining the link over time. If a product changes ownership (Activision → Microsoft), the operator updates the field by hand. No watcher.

## Why a small model fits

Three properties of the task line up with the cascade policy's "smallest tier" criteria:

1. **Constrained output.** The model returns either a slug from a known list (existing company entities), a candidate name, or `null`. No long-form generation.
2. **Short input.** Entity name + website domain + first ~200 chars of description. Total prompt ≈ 100 tokens.
3. **High base-rate accuracy.** For well-known products (Claude, Gemini, ChatGPT, Copilot, Llama, Mistral) the parent company is in the model's training data. Tail products (Viro AI, GreenPT, Earthly Insight) need the website domain to disambiguate; that signal is in the prompt.

Reference: FrugalGPT cascade pattern (Chen et al. 2023) — start at the cheapest tier, escalate only on low-confidence outputs. Single-step classification is a textbook fit.

## When a small model breaks down

Edge cases worth knowing about:

- **Subsidiary chains.** "DeepMind" → Alphabet vs Google. Operator override matters here; don't over-trust the model's first answer.
- **Self-published products.** TreadLightlyAI runs on its own infrastructure with no separate company entity in the system. Correct answer is `null`.
- **Brand-new products** post-training-cutoff. Model may guess wrong or default to the most-recent owner it knows. Lower-confidence outputs should be flagged.
- **Multi-vendor products** (e.g., "ChatGPT" the API vs the consumer app). Slug ambiguity isn't the model's fault but does mean the operator should check.

Mitigation: include a short confidence note in the model's output (`"high" | "medium" | "low"`), surface it in the checkpoint, and require operator confirmation before writing.

## Approach

One new function `infer_parent_company(entity_name, website, description, known_company_slugs)` returning a `ParentCompanyGuess` Pydantic model:

```python
class ParentCompanyGuess(BaseModel):
    existing_slug: str | None  # one of known_company_slugs, or None
    suggested_new_slug: str | None  # if no existing match, candidate slug for a new company entity
    suggested_new_name: str | None  # display name for the new candidate (e.g., "Earthly Insight")
    confidence: Literal["high", "medium", "low"]
    rationale: str  # one short sentence; rendered in the operator checkpoint
```

Either `existing_slug` is set, or both `suggested_new_*` are set, or all are null. The model picks one of three branches.

### Where it runs

In `pipeline/orchestrator/onboard.py` (or wherever the onboard pipeline currently lives), after the Researcher's homepage extract and before the `review_onboard` checkpoint. Only fires when `entity_type == "product"`.

The known-company-slug list is built by `pipeline/common/content_loader.py` — read all files under `research/entities/companies/` and collect filename stems.

### Operator UX

In the existing `review_onboard` checkpoint output, add a section:

```
Parent company: anthropic (existing) — confidence high
  Rationale: claude.ai redirects to anthropic.com; description names Anthropic.
[a]ccept  [c]hange to existing slug  [n]onew company  [s]kip link  [q]uit  >
```

When the result is a `suggested_new_*`, the prompt becomes:

```
Parent company: NEW candidate "Earthly Insight" (slug: earthly-insight) — confidence medium
  Rationale: domain earthlyinsight.ai resolves to a company homepage; no matching entity exists.
[o]nboard now (run dr onboard for the new company first)  [s]kip link  [q]uit  >
```

`[o]nboard now` chains a new `dr onboard` invocation for the company before the product onboard finalizes.

## Phasing

### Phase 1 — inference step (no operator UX changes)

Add `infer_parent_company()` and call it after homepage extract. Write the guess into the entity dict before the checkpoint, but *do not* gate on the result. The current `review_onboard` checkpoint already shows the entity frontmatter; the new field appears as one more line for the operator to eyeball. No new prompts.

This phase ships a working inference loop without any UX work. Ship in one PR.

### Phase 2 — operator prompt for ambiguous cases

Add the explicit `[a]/[c]/[n]/[s]` prompt described above, but only when confidence is `medium` or `low`. High-confidence existing-slug matches go straight through. This phase needs a small extension to `pipeline/orchestrator/checkpoints.py`.

### Phase 3 — chained company onboarding

When the operator picks `[n]onew company`, the pipeline runs `dr onboard <name> --type company` automatically before completing the product onboard. Requires re-entrancy in the onboard flow (today's onboard is a single-shot pipeline). Defer until Phase 2 surfaces this case often enough to be worth it.

## Files changed (Phase 1)

| File | Change |
|------|--------|
| `pipeline/researcher/parent_company.py` | New — `infer_parent_company()` agent + Pydantic output type |
| `pipeline/orchestrator/onboard.py` | Add the inference call after homepage extract, before checkpoint; write `parent_company` into the entity frontmatter dict |
| `pipeline/common/content_loader.py` | New helper `list_company_slugs(repo_root) -> set[str]` |
| `pipeline/tests/test_parent_company.py` | New — fixture cases for known-product (anthropic/claude), tail-product with website signal (greenpt → infomaniak? null?), self-published (treadlightlyai → null), and ambiguous-subsidiary (deepmind → google? alphabet?) |

## Verification

1. Unit test: `infer_parent_company()` returns the expected slug/null/new-candidate for each fixture case.
2. Integration test: a fresh `dr onboard "Claude" --type product` against a temp repo populates `parent_company: anthropic` in the entity frontmatter.
3. Astro build still passes after a `parent_company: <unknown-slug>` is introduced and then corrected — no schema regression.
4. Cost: log the small-model token spend per onboard; confirm under one cent.

## Model selection

For Phase 1, target the same cascade tier the Router uses (per [`v0.1.0-vocab-workflow-landing.md`](v0.1.0-vocab-workflow-landing.md) and the model-tier discipline subsection in `glossary.md`). On Anthropic this is Haiku 4.5; on Infomaniak the smallest available `gpt-oss-120b` works. The exact model name is configured via `--model` and recorded in `models_used` on the audit sidecar (per [`pre-launch-quick-fixes.md`](pre-launch-quick-fixes.md) S6).

## Open questions

1. **Confidence threshold for auto-accept in Phase 2.** Proposal: `high` always auto-accepts; `medium` and `low` prompt. Could be tightened to "always prompt" if false positives bite.
2. **Subsidiary disambiguation policy.** When the model guesses Alphabet but the existing entity is `google`, should the inference normalize to the existing slug? Probably yes — match against the known slug list first, only suggest a new company if no match.
3. **`treadlightlyai` and similar self-published products.** Should `parent_company: null` be the output, or should the system prompt the operator to onboard a company entity (TreadLightly AI LLC)? Defer; the field is optional.
