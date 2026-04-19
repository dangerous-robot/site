# TODO

This file tracks blockers, deferred ideas, and improvement opportunities not yet associated with a backlog phase. Phased work items are tracked in `BACKLOG.md`.

## Blocked

- [ ] **Configure custom domain in GitHub Pages UI** -- `dangerousrobot.org` is verified at the account level, DNS records are set (A records + CNAME), repo is public, Pages is enabled (deploy from branch/main), but Settings > Pages still returns "You cannot set a custom domain at this time." CNAME file is committed to repo. Troubleshoot: check if the account is a free org (may need GitHub Pro/Team for custom domains on org repos), try the API (`gh api repos/dangerous-robot/site/pages -X PUT`), or contact GitHub Support.

## Deferred Content (unsourced)

- [ ] **Structure chatbot comparison table** -- Comparison data exists in `parallax-ai/frontend/src/lib/comparison-data.ts` (transparency + feature comparisons across 5 competitors). Treat as unsourced claims; need to create source files backing each cell before publishing. Decide on content collection approach (new collection vs. claims with `product-comparison` category).
- [ ] **Structure AI Product Card data** -- Transparency/nutrition-label data exists in `parallax-ai/frontend/src/app/transparency/page.tsx` (models, energy, ethics, commitments). Treat as unsourced claims; need source files for each assertion. Same collection design decision as comparison table.

## Site Gaps (from architectural review, 2026-04-18)

- [ ] **List/index pages** -- No pages exist at `/claims/`, `/sources/`, or `/entities/`. Nav links were removed to prevent 404s. Add index pages that list all entries in each collection. Add `/about` page.
- [ ] **Entity reference validation** -- Claims reference entities by path string (`companies/anthropic`) with no build-time validation. Use Astro's `reference('entities')` helper in `src/content.config.ts`, or add entity-ref checking to `scripts/check-citations.ts`.
- [ ] **Source reference upgrade** -- Replace `z.array(z.string())` with `z.array(z.string().min(1)).min(1)` for claims `sources` field. Optionally use Astro `reference('sources')` for build-time validation. Current schema permits empty arrays, contradicting AGENTS.md content rules.
- [ ] **Deploy workflow quality checks** -- `deploy.yml` only runs `npm run build`, skipping lint and citation checks. A direct push to `main` bypasses CI. Either add the checks to deploy.yml or require CI status checks via branch protection.
- [ ] **`verdictColors` deduplication** -- Same color map copy-pasted in `index.astro`, `claims/[...slug].astro`, `entities/[...slug].astro`. Extract to a shared module.
- [ ] **Homepage entity name resolution** -- Homepage displays raw entity slugs (`companies/anthropic`) instead of human-readable names. Fetch entities collection and resolve names.
- [ ] **`recheck_cadence_days` constraint** -- Schema accepts 0/negative values. Add `.int().min(1)` to the Zod definition.
- [ ] **GitHub Actions SHA pinning** -- All actions use mutable tags (`@v4`). Pin by full SHA for supply chain security.
- [ ] **SEO basics** -- No favicon, robots.txt, canonical URLs, Open Graph tags. `description` prop in Base.astro is never customized per page.
- [ ] **Accessibility** -- No skip-to-content link, no `aria-label` on nav, no `<header>` wrapper.

## Opportunities

- [ ] **Validation gaps** -- The current CI validates schema structure and citation integrity but does not test reasoning quality. Potential additions:
  - Confidence-to-verdict alignment (e.g., flag `confidence: low` paired with `verdict: true`)
  - Staleness detection using `as_of` + `recheck_cadence_days`
  - Source URL liveness checks
  - Archived URL (`archived_url`) population nudges
  - A check framework (Vitest) for scripted validators
- [ ] **Confidence rubric** -- Define what `high`/`medium`/`low` confidence concretely means (e.g., high = multiple independent sources with direct evidence; medium = single source or self-reported data; low = inference or indirect evidence). Use an LLM to check each claim against the rubric. The GreenPT claim already does this informally in prose -- a rubric would formalize it.
- [ ] **Claim Updater instruction quality** -- Consider adversarial review (argue the opposite verdict from the same sources), inter-rater consistency validation (same inputs to multiple LLM runs), and forbidden-combination gates (CI rejection of nonsensical confidence-verdict pairs like `high`/`unverified`). These test the architecture and instructions, not the LLM.
