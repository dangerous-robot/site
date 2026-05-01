# Criterion-resolution workflow

**Status**: Stub
**Priority**: Follow-on to the publish-time criterion gate
**Last updated**: 2026-04-30

## Context

The publish-time gate (`approve_claim` refuses draft -> published when `criteria_slug` is missing; `published-without-criterion` lint check; `dr publish` skips per-claim) makes criteria a hard requirement at publish. This plan covers the *resolution* workflow — how an operator gets from a criterion-less draft to a tagged claim — which today is fully manual (edit `research/templates.yaml` + edit the claim frontmatter, then re-run approve).

This stub is the holding pen for ergonomic improvements to that flow. None of it is required to ship the gate.

## Design space (in increasing automation)

### A. Manual edit (today)

Operator drops out of the queue (`q`), opens `research/templates.yaml` to find or add a slug, opens the claim frontmatter to set `criteria_slug:`, then re-runs `dr review --approve --claim ...` (or returns to `dr review-queue` and presses `a`).

- Pros: zero new code.
- Cons: full context-switch out of the queue every time; no discoverability of existing slugs from the queue; no guard against typos against the catalog.

### B. `c` action in `dr review-queue` (recommended next step)

When the operator hits `c` on a draft missing a criterion, the queue:

1. Lists existing template slugs from `research/templates.yaml`, optionally filtered by entity type.
2. Operator picks an existing slug, or selects "create new" → drops into `$EDITOR` on `research/templates.yaml` (waits for the editor to close).
3. Writes the chosen slug into the claim's frontmatter (`criteria_slug:` field).
4. Re-displays the queue header so the operator can immediately press `a`.

Implementation lives in `pipeline/orchestrator/review_queue.py` next to the existing actions. New helper `set_criteria_slug(claim_path, slug)` in `pipeline/orchestrator/review.py`.

- Pros: keeps the operator in the queue; existing-slug picker prevents typos; the `a` action immediately validates.
- Cons: the "create new" path still requires a manual templates.yaml edit. Acceptable starting point.

### C. Normalizer agent (future)

A new agent reads the claim text + analyst output and proposes `(slug, canonical question, topics, applicable_entity_types)`. The operator approves or edits the proposal in `dr review-queue`. Until approved, the claim stays draft (no separate `criteria_slug: pending` state — drafts simply tolerate absence).

- Pros: lowest friction; helps the operator articulate the question.
- Cons: needs deduplication against the existing catalog or it sprawls. Worth building once the catalog is large enough that a similarity check is meaningful.

A hybrid worth keeping in mind: the `c` action could call the normalizer in the background to *suggest* slug + wording when "create new" is picked, so the operator gets `use suggested / edit / skip` instead of starting from a blank file.

## Singleton escape (manual only)

Some claims genuinely don't generalize (one-off observations like "Anthropic published the Constitutional AI paper in Dec 2022"). For those, the operator should be able to set `criteria_slug: singleton` (or a named singleton like `singleton:anthropic-cai-paper-2022`) by hand — but no command should *offer* to set this for them. Automating singleton creation defeats the gate's purpose. Manual edit only; if the lint check needs special handling for singletons later, design that explicitly when the case actually arises.

## Vocabulary claims: unresolvable placeholder → blocked

Some criteria use a vocabulary placeholder in the claim text: "one of (A, B, C ...)". The analyst is expected to resolve the placeholder to whichever option the evidence supports and write the title accordingly. When no option can be supported, the current instructions have no defined behavior -- the analyst either invents a vacuous title ("has an undetermined X") or outputs the raw template form. Both are wrong.

**Decision needed:** an unresolvable vocabulary claim should become `status: blocked`, not a drafted claim with a bad title.

### Required pieces

1. **Analyst signal.** The analyst instructions should tell the analyst to output a structured "unresolvable" flag (e.g., a boolean `vocabulary_unresolvable: true` on the assessment, or a sentinel string as the title) rather than attempting to write a title when no option is supported.

2. **Orchestrator handling.** The orchestrator's `_handle_analyst_output` (or equivalent) checks for this flag and calls `_mark_claim_blocked(reason="vocabulary placeholder could not be resolved")` instead of writing a drafted claim file.

3. **Review queue surfacing.** `dr review-queue` should show blocked vocabulary claims with their `blocked_reason` so the operator can decide: add more sources and re-run, or manually resolve the placeholder and re-queue.

### What "unresolvable" means here

This is distinct from `verdict: unverified`. `unverified` means sources were found, analyzed, and don't engage with the claim's central assertion -- a meaningful output. An unresolvable vocabulary claim means the analyst cannot produce a valid title at all, so no draft should be written. The blocking is about the *form* of the output, not the epistemic state of the evidence.

### Out of scope for this section

- The broader question of analyst authority to rewrite other parts of claim text (narrative wording, topic drift). That belongs in `analyst-decomposition_stub.md` under the narrative + title writer sub-decision.

## Out of scope for this stub

- Renaming/migrating an existing slug across many claims (covered by [`criteria-rename_stub.md`](criteria-rename_stub.md) if/when that lands).
- Cross-entity comparison views in the site UI that consume `criteria_slug` (separate frontend plan).
- A `dr criterion create <slug> --question "..."` CLI command. Possible, but Phase B's "drop into editor" approach gets us there with zero new commands.

## Cross-references

- Built on top of: gate landed in this conversation (lint check `published-without-criterion`, `approve_claim` preflight, `dr publish` skip).
- Phase 2 of [`dr-review-queue.md`](dr-review-queue.md) lists the `c` action; this stub is the design.
- Adjacent: [`criteria-rename_stub.md`](criteria-rename_stub.md) handles the case after slugs exist and need to evolve.
