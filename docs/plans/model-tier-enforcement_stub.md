# Plan (stub): Enforce small-by-default model tiers

**Status**: Stub — scaffolded from Q4 of the retired `pre-launch-questions.md` (2026-07-09). Not implementation-ready; flesh out before building.

**Suffix**: `_stub` — placeholder. Committed at `docs/plans/` top level (not `drafts/`) because committed docs link to it (`docs/v1.0.0-roadmap.md`, `docs/architecture/glossary.md`).

## Problem

"Small decisions, small models" is stated as a principle (glossary § Model-tier discipline; `AGENTS.md` § How the system works) but is **not enforced**. Today it holds only because `DEFAULT_MODEL` happens to be small — nothing caps escalation.

## Current state (verified 2026-07-09)

| Piece | Reality |
|---|---|
| Default | `DEFAULT_MODEL = "infomaniak:openai/gpt-oss-120b"` (`pipeline/common/models.py:187`) — already small/mid. |
| Per-agent overrides | `VerifyConfig.{researcher,analyst,auditor,ingestor}_model` with `model_for()` fallback (`pipeline/orchestrator/pipeline.py:212`). Landed in multi-provider Part 2. |
| Enforcement | **None.** Any `--{agent}-model <big-model>` is accepted with no ceiling. |
| Visibility | The `.audit.yaml` sidecar records `models_used` per agent (`cli.py:971`) — escalation is auditable after the fact, not prevented. |

So the repo is effectively at "option (a) by omission": principle documented, default small, sidecar shows what ran.

## Chosen approach: option (b) — per-agent tier caps in config

Rejected alternatives (from the Q4 writeup):
- **(a) instructions only** — soft convention, no guarantee. This is the status quo; the point of the plan is to move past it.
- **(c) cost-per-claim ceilings + escalation gates** — the "real" cost control, but depends on the token-usage log (unbuilt; see `docs/plans/token-usage-log.md`). Deferred to v1.x+.

### Design sketch (to be verified during implementation)

1. **Tier map.** A `MODEL_TIER` lookup (`small` / `mid` / `large`) keyed by model-id substring, mirroring the existing substring-keyed model-profile registry in `pipeline/common/models.py` (the Mistral scrubber uses the same pattern).
2. **Ceiling field.** Add `max_tier` to `VerifyConfig` (default `small` or `mid` — decide during flesh-out). Checked in `resolve_model` (or a thin wrapper the CLI calls): a spec resolving above `max_tier` is either rejected with a clear error or downgraded to the ceiling — decide which (reject is safer/clearer; downgrade is friendlier). An explicit escape hatch (env var or flag) should allow deliberate override so the cap never fully blocks a needed run.
3. **Tests.** Extend `test_models.py` (tier lookup, ceiling reject/downgrade, escape hatch, unknown-model default tier) mirroring the existing tier/key cases.

### Open questions to resolve before implementing

- Ceiling behavior: hard reject vs. silent downgrade vs. warn-and-proceed.
- Default `max_tier`: `small` (strict) or `mid` (accommodates analyst/auditor judgement)?
- Where tiers are defined for non-Anthropic providers (Infomaniak/GreenPT model ids carry no canonical tier) — substring heuristics vs. an explicit per-model table.
- Interaction with the audit sidecar `models_used` display (S6) — surface the cap that was in effect?

## Downstream / related

- Feeds the audit sidecar `models_used` display and multi-provider Part 2 machinery (`docs/plans/completed/multi-provider.md`).
- Cost-ceiling successor work depends on `docs/plans/token-usage-log.md`.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-07-09 | agent (claude-opus-4-8) | stub scaffold | Created from Q4 of the retired `pre-launch-questions.md`. Current-state table verified against `models.py`/`pipeline.py`/`cli.py`. Not yet fleshed to an implementation-ready plan. |
