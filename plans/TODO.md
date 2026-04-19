# TODO

## Blocked

- [ ] **Configure custom domain in GitHub Pages UI** -- `dangerousrobot.org` is verified at the account level, DNS records are set (A records + CNAME), repo is public, Pages is enabled (deploy from branch/main), but Settings > Pages still returns "You cannot set a custom domain at this time." CNAME file is committed to repo. Troubleshoot: check if the account is a free org (may need GitHub Pro/Team for custom domains on org repos), try the API (`gh api repos/dangerous-robot/site/pages -X PUT`), or contact GitHub Support.

## Deferred Content (unsourced)

- [ ] **Structure chatbot comparison table** -- Comparison data exists in `parallax-ai/frontend/src/lib/comparison-data.ts` (transparency + feature comparisons across 5 competitors). Treat as unsourced claims; need to create source files backing each cell before publishing. Decide on content collection approach (new collection vs. claims with `product-comparison` category).
- [ ] **Structure AI Product Card data** -- Transparency/nutrition-label data exists in `parallax-ai/frontend/src/app/transparency/page.tsx` (models, energy, ethics, commitments). Treat as unsourced claims; need source files for each assertion. Same collection design decision as comparison table.

## Opportunities

- [ ] **Validation gaps** -- The current CI validates schema structure and citation integrity but does not test reasoning quality. Potential additions:
  - Confidence-to-verdict alignment (e.g., flag `confidence: low` paired with `verdict: true`)
  - Staleness detection using `as_of` + `review_cadence_days`
  - Source URL liveness checks
  - Archived URL (`archived_url`) population nudges
  - A test framework (Vitest) for scripted validators
- [ ] **Confidence rubric** -- Define what `high`/`medium`/`low` confidence concretely means (e.g., high = multiple independent sources with direct evidence; medium = single source or self-reported data; low = inference or indirect evidence). Use an LLM to check each claim against the rubric. The GreenPT claim already does this informally in prose -- a rubric would formalize it.
- [ ] **Claim Updater instruction quality** -- Consider adversarial review (argue the opposite verdict from the same sources), inter-rater consistency testing (same inputs to multiple LLM runs), and forbidden-combination gates (CI rejection of nonsensical confidence-verdict pairs like `high`/`unverified`). These test the architecture and instructions, not the LLM.
