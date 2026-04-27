# v1 launch claim set

Curated list of claims targeted for the `v1.0.0` release. This file is the deliberate tracking surface that replaces the stale "flagship claim audit" item in [`docs/v1.0.0-roadmap.md`](../docs/v1.0.0-roadmap.md).

**Source of truth:** the on-disk files under `research/claims/`. This file records *intent* (what we want to ship) and *gaps* (what's still draft, blocked, or not yet onboarded). Any divergence between this list and the on-disk set is a tracking bug — fix the file, not the disk.

**Last refreshed:** 2026-04-27

## Legend

- **Target**: `published` — render in the launch set; `defer` — leave out of v1; `tbd` — undecided.
- **Status**: current `status:` frontmatter on the claim file.
- **Sidecar**: `.audit.yaml` exists next to the claim file (research is complete).
- **Signoff**: `human_review.reviewed_at` is non-null in the sidecar (`dr review --approve` has run). Pre-GA this is informational; flips to a `dr lint` error at v1 final per [`docs/plans/dr-lint.md`](../docs/plans/dr-lint.md).

## Active entities

Currently on disk: `anthropic` (company), `claude` (product), `gemini` (product), `treadlightlyai` (product), plus `google` (company, no claims yet). The smaller-player entities listed in the [original v0.1.0 §3 flagship list](../docs/plans/drafts/v0.1.0-mvp-definition.md) were deleted during the 2026-04-26 prep pass and need to be re-onboarded if their candidate claims (table below) are kept.

## Active claims (already on disk)

| Entity / claim | Target | Status | Sidecar | Signoff |
|---|---|---|---|---|
| anthropic / donates-to-environmental-causes | tbd | draft | no | no |
| anthropic / publishes-sustainability-report | tbd | draft | yes | no |
| claude / discloses-energy-sourcing | tbd | draft | no | no |
| claude / discloses-models-used | tbd | draft | yes | no |
| claude / excludes-image-generation | tbd | draft | yes | no |
| claude / no-training-on-user-data | published | published | yes | no |
| claude / realtime-energy-display | published | published | yes | no |
| claude / renewable-energy-hosting | published | published | yes | no |
| gemini / discloses-energy-sourcing | tbd | draft | yes | no |
| gemini / excludes-frontier-models | tbd | draft | yes | no |
| gemini / excludes-image-generation | published | published | yes | no |
| gemini / no-training-on-user-data | published | published | yes | no |
| gemini / realtime-energy-display | published | published | yes | no |
| gemini / renewable-energy-hosting | published | published | yes | no |
| treadlightlyai / realtime-energy-display | defer | blocked | no | no |

## Candidate claims (need onboarding before they can ship)

Carried over from the original [v0.1.0 §3 flagship list](../docs/plans/drafts/v0.1.0-mvp-definition.md). Verdicts in the "Prior verdict" column reflect the deleted-set state and may not survive a fresh pipeline run. Each candidate requires at least `dr onboard <entity>` (and possibly `dr verify-claim` for the specific claim text) before it appears under `research/claims/`.

Coverage rationale: smaller players, sector-level claims, and a strong negative (OpenAI sustainability report) are what made the original set illustrative. Trim freely.

| Entity / claim | Target | Prior verdict | Onboarding action |
|---|---|---|---|
| companies/ecosia / publishes-sustainability-report | tbd | true, high — best-supported company claim | `dr onboard "Ecosia" --type company` |
| companies/ecosia / corporate-structure | tbd | pending review (B-corp, publicly checkable) | piggybacks on the ecosia onboard |
| companies/openai / publishes-sustainability-report | tbd | false, medium — compelling negative; pairs with ecosia | `dr onboard "OpenAI" --type company` |
| products/ecosia-ai / renewable-energy-hosting | tbd | true, medium — best-supported product claim | `dr onboard "Ecosia AI" --type product` |
| products/ecosia-ai / no-training-on-user-data | tbd | pending review — high reader interest | piggybacks on ecosia-ai onboard |
| products/viro-ai / renewable-energy-hosting | tbd | mostly-false, medium — offset vs direct hosting nuance | `dr onboard "Viro AI" --type product` |
| products/chatgpt / renewable-energy-hosting | tbd | unverified, medium — market leader, least transparency | `dr onboard "ChatGPT" --type product` |
| companies/greenpt / renewable-energy-hosting | tbd | true, medium — smaller player, Infomaniak ISO-cert hosting | `dr onboard "GreenPT" --type company` |
| sectors/ai-llm-producers / existential-safety-score | tbd | true, high — FLI-sourced, one of the best-sourced claims | requires sector-onboarding flow (see [`sector-claims.md`](../docs/plans/sector-claims.md)) |
| companies/anthropic / donates-to-safety-environment | tbd | mostly-true, medium — concrete sourcing on a transparency claim | already on disk as `anthropic/donates-to-environmental-causes` (verify whether the rename keeps the original sourcing) |

## Gaps to close before tag

- [ ] Resolve `tbd` rows in **Active claims**: pick `published` or `defer` for each currently-`draft` claim.
- [ ] Trim **Candidate claims** to the subset worth onboarding for v1 (each one is a non-trivial pipeline run plus a fresh verdict that may differ from the prior one).
- [ ] For every `target: published` row, decide whether to require sign-off pre-tag (operator policy — currently the `dr lint` rule is `warning` until v1 GA).
- [ ] `treadlightlyai/realtime-energy-display` is `blocked` (insufficient sources). Either find more sources and re-run the pipeline, or leave as `defer` for v1.

## Update protocol

When a claim is added, removed, or changes target:

1. Edit this file in the same commit as the on-disk change.
2. Re-run the inventory snippet to verify the table matches disk:

   ```bash
   for f in research/claims/*/*.md; do
     st=$(grep -m1 '^status:' "$f" | sed 's/status: //')
     rel=${f#./}
     has_audit="no"; [ -f "${f%.md}.audit.yaml" ] && has_audit="yes"
     reviewed="no"
     if [ "$has_audit" = "yes" ]; then
       grep -q "reviewed_at: [0-9]" "${f%.md}.audit.yaml" 2>/dev/null && reviewed="yes"
     fi
     echo "$rel | status=${st:-unset} | sidecar=$has_audit | signoff=$reviewed"
   done
   ```
3. Update the "Last refreshed" date at the top.

A future `dr lint` rule could enforce parity automatically; tracked under [`docs/plans/dr-lint.md`](../docs/plans/dr-lint.md) Phase 3.
