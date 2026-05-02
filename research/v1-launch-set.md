# v1 launch claim set

Curated list of claims targeted for the `v1.0.0` release. This file is the deliberate tracking surface that replaces the stale "flagship claim audit" item in [`docs/v1.0.0-roadmap.md`](../docs/v1.0.0-roadmap.md).

**Source of truth:** the on-disk files under `research/claims/`. This file records *intent* (what we want to ship) and *gaps* (what's still draft, blocked, or not yet onboarded). Any divergence between this list and the on-disk set is a tracking bug — fix the file, not the disk.

**Last refreshed:** 2026-05-01

## Legend

- **Target**: `published` — render in the launch set; `defer` — leave out of v1; `tbd` — undecided.
- **Status**: current `status:` frontmatter on the claim file.
- **Sidecar**: `.audit.yaml` exists next to the claim file (research is complete).
- **Signoff**: `human_review.reviewed_at` is non-null in the sidecar (`dr review --approve` has run). Pre-GA this is informational; flips to a `dr lint` error at v1 final per [`docs/plans/dr-lint.md`](../docs/plans/dr-lint.md).

## Active entities

Currently on disk: `brave-leo` (product), `brave-software` (company), `chatgpt` (product), `microsoft` (company), `openai` (company), `anthropic` (company). Entity files also exist for `claude` (product) and `gemini` (product) but neither has claims on disk yet.

## Active claims (already on disk)

| Entity / claim | Target | Status | Sidecar | Signoff |
|---|---|---|---|---|
| anthropic / donates-to-environmental-causes | tbd | draft | no | no |
| brave-leo / discloses-energy-sourcing | tbd | published | yes | yes |
| brave-leo / discloses-models-used | tbd | published | yes | yes |
| brave-leo / excludes-frontier-models | tbd | blocked | no | no |
| brave-leo / excludes-image-generation | tbd | published | yes | yes |
| brave-leo / no-training-on-user-data | tbd | published | yes | yes |
| brave-leo / realtime-energy-display | tbd | published | yes | yes |
| brave-leo / renewable-energy-hosting | tbd | published | yes | yes |
| brave-software / corporate-structure | tbd | blocked | no | no |
| brave-software / donates-to-ai-safety | tbd | published | yes | yes |
| brave-software / donates-to-environmental-causes | tbd | published | yes | yes |
| brave-software / publishes-sustainability-report | tbd | blocked | no | no |
| chatgpt / discloses-energy-sourcing | tbd | published | yes | yes |
| chatgpt / discloses-models-used | tbd | published | yes | yes |
| chatgpt / excludes-frontier-models | tbd | draft | yes | no |
| chatgpt / excludes-image-generation | tbd | published | yes | yes |
| chatgpt / no-training-on-user-data | tbd | published | yes | yes |
| chatgpt / realtime-energy-display | tbd | published | yes | yes |
| chatgpt / renewable-energy-hosting | tbd | published | yes | yes |
| microsoft / corporate-structure | tbd | published | yes | yes |
| microsoft / donates-to-ai-safety | tbd | published | yes | yes |
| microsoft / donates-to-environmental-causes | tbd | published | yes | yes |
| microsoft / publishes-sustainability-report | tbd | published | yes | yes |
| openai / corporate-structure | tbd | published | yes | yes |
| openai / donates-to-ai-safety | tbd | published | yes | yes |
| openai / donates-to-environmental-causes | tbd | published | yes | yes |
| openai / publishes-sustainability-report | tbd | published | yes | yes |

**Entity files with no claims on disk:** `claude` (product), `gemini` (product). Decision needed: onboard before v1 tag or defer to v1.1.

## Candidate claims (needs decision before v1 tag)

These are not yet on disk. Trim freely — each one is a non-trivial pipeline run.

| Entity / claim | Target | Notes |
|---|---|---|
| claude / (any) | tbd | Entity exists; no claims. Onboard or explicitly defer for v1. |
| gemini / (any) | tbd | Entity exists; no claims. Onboard or explicitly defer for v1. |

## Gaps to close before tag

- [ ] Resolve `tbd` rows in **Active claims**: pick `published` or `defer` for each row.
- [ ] Decide whether `blocked` claims (`brave-leo/excludes-frontier-models`, `brave-software/corporate-structure`, `brave-software/publishes-sustainability-report`) should show as `blocked` on the live site or be deferred.
- [ ] Decide whether `chatgpt/excludes-frontier-models` (draft + sidecar) should be published or deferred.
- [ ] Decide whether to onboard claims for `claude` and/or `gemini` before the v1 tag.
- [ ] For every `target: published` row, decide whether to require sign-off pre-tag (operator policy — currently the `dr lint` rule is `warning` until v1 GA).

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
