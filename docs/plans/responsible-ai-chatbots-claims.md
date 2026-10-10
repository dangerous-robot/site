# Plan: Responsible AI chatbots, backed by claims

**Status**: in progress. S1 to S8, S8a and S11 to S13 done; S9 code done, its copy (stance sentences, intro) waits on Brandon; S10, S15 and S16 not started.
**Last updated**: 2026-10-10
**Serves**: SITE-J (Responsible AI chatbots) in `docs/v1.0.0-roadmap.md:143`; decided in `docs/decisions.md:26` (2026-10-06, "Next large effort")
**Page**: `src/content/resources/responsible-ai.md` (layout `matrix`), rendered by `src/pages/resources/[...slug].astro:75-93` and `src/components/ResponsibleAI*.astro`
**Mockup**: https://claude.ai/artifact/TVwDvNAKYN7gMdgEeNGoot (files: `docs/mockups/responsible-ai-chatbots-claims/`; a 3-product, 4-row slice with sample data)
**Line numbers** are as of HEAD `4c427fe`.
**Register** code work before S1: `python3 scripts/release-gate/work_item.py start --title "SITE-J (Responsible AI chatbots)" --kind <kind from release-triage> --release v1.0.0 --plan docs/plans/responsible-ai-chatbots-claims.md` (AGENTS.md § Agent workflow tooling).

Goal, in Brandon's words: add validity to the page's assertions; show yes/no plus good/bad with a level of research, without getting complicated; state the page's opinions about what responsible means and link each to its evidence.

## Status checklist

Ticked as items land (AGENTS.md rule 4). Ids match the step headings under "Steps".

Honest labels (no new research)
- [x] S1: site-side unit tests run in `inv check` and CI
- [x] S2: pure functions for tier, stance and verdict agreement
- [x] S3: schema for cell evidence, row stances and product entities
- [x] S4: build check that fails on bad citations
- [x] S5: cells colored by the row's stance, feature rows neutral, `no-good` retired
- [x] S6: evidence marks with a detail popup, and the Evidence section
- [x] S7: today's inline links become source files (6 of 9; see S7 for the 3 left as links)
- [x] S8: content fixes for the findings (F10 and the lab-page half of F14 wait on sources; see S8)
- [x] S8a: apply the post-S8 answers (A1 to A8 under Decisions; 5 launch dates and GPT-OSS's source left for S10, see S8a)

Sources for every stance row
- [ ] S9: stance sentences and their evidence (code done; copy pending Brandon)
- [ ] S10: one source per stance-row cell, then feature rows and the summary
- [x] S11: the research linter counts sources the page cites

Claims, row by row
- [x] S12: activate the inactive criteria the page needs
- [x] S13: entities for the page's products and companies
- [ ] S15: first row backed by published claims (renewable hosting)
- [ ] S16: remaining claim rows, one at a time

S14 and S17 (indexing) are not part of SITE-J and have no checkbox; their notes stay under "Steps" for reference.

## Decisions

Brandon's answers: Q1 to Q13 on 2026-10-08, P1 to P6 and R1 to R4 on 2026-10-09.

- Q1: T1. TreadLightlyAI evidence is capped at the "Source" tier; no claims are researched for it.
- Q2: D1 (evidence marks in cells plus an Evidence section), plus a hover popup on each mark with a small amount of detail; this plan makes it open by keyboard and touch too.
- Q3: claims and sources are cited as rendered URL paths (`/research/claims/...`).
- Q4: a fact checked by using the product cites the product's own page as a source where one exists; otherwise the cell records `last_checked` ("Checked by Dangerous Robot, <date>") and stays "Not yet sourced". No fourth tier.
- Q5: stance rows are renewable hosting, real-time energy display, no image generation, published financials, data used for training (stance: no), open-source models, accessibility, models (stance: large models are bad; P5 defines large) and ownership structure (stance: non-profit is good; P6 refines). Feature rows take no stance: free tier, agent web search, normal web search, pricing, maturity, image and document analysis, data jurisdiction. Feature rows are marked by having no "We prefer" line, plus one legend sentence: "Rows without a “We prefer” line compare facts only; we take no position on them." No new table sections.
- Q6: tier names "Reviewed claim", "Source" and "Not yet sourced".
- Q7: keep the summary table, source its assertions as far as possible, remove no products.
- Q8: the indexing flip waits until after 1.0.0 and is Brandon's call (`docs/decisions.md:19`).
- Q9: product columns in alphabetical order.
- Q10: accessibility is source-only: an audit report, a "Checked by Dangerous Robot, <date>" record, or the product's own accessibility statement. No WCAG criterion.
- Q11: a stance may link a Values position, labeled as a position, not a source.
- Q12: renewable hosting is the first row backed by claims.
- Q13: add site-side unit tests (Node's test runner through `tsx`) to `inv check` and CI.
- P1: "large" means the latest and biggest models from every lab, not the glossary's frontier-scale definition (`docs/architecture/glossary.md:178-185`). P5 makes it exact.
- P2: good = non-profit, steward-ownership, cooperative, B-corp, employee-owned; mixed = independent and small businesses; bad = huge corporations and conglomerates. P6 makes it exact.
- P3: data jurisdiction is sourced only; no claims, and `data-jurisdiction` stays inactive.
- P4: accessibility is Yes when the evidence states WCAG 2.x Level AA conformance; Partial for a lower or partial level, or barriers found by our check; Unknown with no evidence. This defines the cell's answer; Q10 still holds (no research criterion and no claims for this row).
- P5: large = the most capable tier in each lab's current lineup, per the lab's own model page (for example Fable, Opus, Gemini Pro). Smaller tiers (Sonnet, Haiku, Flash, mini) are not large. The page keeps a dated list of which models count.
- P6: bad = publicly traded, or owned by a publicly traded company or a conglomerate. Mixed = any other privately held company (independent and small businesses). Good = non-profit, steward-ownership, cooperative, B-corp, employee-owned.
- R1: a models cell is bad if the product offers any large model; good only when none is large (no mixed on this row).
- R2: a model is large if it was its lab's most capable tier when released; in a size family only the largest size is. Each call is recorded in the dated list. This amends P5's "current lineup".
- R3: `owned_by.kind: conglomerate` only when a cited source describes the owner as one.
- R4: the row is labeled "Open-weight models"; S12 rewords the criterion text to "PRODUCT uses only open-weight models" (slug unchanged).

Post-S8 answers, Brandon 2026-10-09 (open questions from the S1 to S8 build and its review; S8a applies them):

- A1 (F15): the page description stays "Side-by-side comparison of AI chatbots that call themselves green or responsible: hosting, models, data use, ownership and cost, with the evidence behind each cell." Already on main.
- A2 (F7): the Maturity row shows each product's launch month and year ("Launched Oct 2025"), not an age; the row label drops "as of March 2026". A launch date without a source shows "Not yet sourced".
- A3 (F13): until S10, the accessibility row shows the earlier answers again, unsourced (tier "Not yet sourced"): Ecosia AI and TreadLightlyAI Yes, "Level AA+"; Euria, Viro AI and ChatGPTree Partial.
- A4 (F13, P4): GreenPT and Earthly Insight, earlier "Yes, Level A", are Partial with the detail "Level A", since P4 counts only Level AA as Yes.
- A5 (R2): GPT-4o is large (OpenAI's top tier at its release), so ChatGPTree's models cell is bad; GPT-OSS is not large. Each call still needs its lab's model page as a source (S10).
- A6 (F12): Ecosia's ownership term is steward-ownership (cell text keeps "Non-profit, Steward-ownership"). Already on main.
- A7: the two dead summary links (ChatGPTree's Evertreen criticism, a redmonitor Substack post; Euria's "environmental commitments", an infomaniak.com page) get replacement sources, ingested as source files. Where none is found, the link and the sentence it backs come out; the Evertreen allegation does not stand unsourced.
- A8 (review F6): in the dark theme only, `--color-stance-bad` gets its own lighter red (about #e05555, 4.7:1 on `#19191b`; WCAG 1.4.11 asks 3:1) instead of `--color-verdict-false` (#b22222, 2.6:1). Verdict colors are unchanged, so "False" stays distinct from "Mostly false".

## What the page asserts today

The page makes three kinds of assertions. Almost none carry evidence.

| Part | Where | Size | Evidence today |
|---|---|---|---|
| Comparison table | `responsible-ai.md:87-273` | 16 rows x 7 products = 112 cells | 4 cells have a link: two hedged privacy-policy links ("probably?", "probably not?", `:157`, `:158`) and two kSuite product links that are not evidence (`:177`, `:188`) |
| Summary table | `responsible-ai.md:23-86` (`summary:` under each product) | 4 free-text fields x 7 products = 28 entries | 9 inline links (Euria receipts and commitments, Ecosia blog and financial reports, Evertreen substack, Global Rewilding Alliance, Terrapass Wikipedia, Viro methodology, DFPI order) |
| Footnotes | `responsible-ai.md:274-280` | 3 | none |

The 3 published claims (`research/claims/brave-browser/renewable-energy-hosting.md` and two subject claims) cover no product on the page. Each product except TreadLightlyAI has a product entity and a company entity (S13; GreenPT's pair predates the plan).

### Rows: stance, criterion, evidence

A **stance row** says which answer the page counts as responsible (the row's `ideal`). A **feature row** compares a fact and takes no stance. Groups stay as they are.

| Row (`key`) | Kind | Responsible answer | Criterion (`research/templates.yaml`) | Evidence planned |
|---|---|---|---|---|
| Hosted on renewable energy (`renewable-hosting`) | stance | Yes | `renewable-energy-hosting` (product, `:46`) | claims (first row, S15) |
| Real-time energy display (`real-time-energy-display`) | stance | Yes | `realtime-energy-display` (product, `:74`) | claims |
| No image generation (`no-image-generation`) | stance | Yes | `excludes-image-generation` (product, `:81`) | claims |
| Published financials (`financial-transparency`) | stance | Yes | `financial-transparency` (company, `:44`); the criterion says "financial transparency", broader than "published financials" | claims |
| Data used for training (`data-used-for-training`) | stance | No | `no-training-on-user-data` (product, `:53`); polarity inverted: a True verdict means the answer is No | claims |
| Open-weight models (`open-source-models-only`) | stance | Yes | `open-source-models-only` (product, `:102`; text "PRODUCT uses only open-weight models", R4) | claims |
| Models (`models`) | stance, text cells | no large models (P5) | none: see "Why the models row has no criterion" | sources: each product's model list, and each lab's model page for the dated large-model list |
| Ownership structure (`corporate-structure`) | stance, text cells | non-profit or similar (P6) | `corporate-structure` (company, `:14`, vocabulary `:20-28`) | claims; sources for an owner (P6) |
| Accessibility (`accessibility`) | stance | Yes (P4) | none (Q10) | sources or a check record only |
| Free tier, Agent web search, Normal web search, Image and document analysis | feature | none | none | sources |
| Pricing, Maturity | feature, text cells | none | none | sources |
| Data jurisdiction (`data-jurisdiction`) | feature, text cells | none | none (P3; `data-jurisdiction`, `:134`, stays inactive) | sources |

**Why the models row has no criterion.** `excludes-frontier-models` (`templates.yaml:88`, active) defers to the glossary's frontier-scale definition: top-5 on major benchmarks, or more than 100B parameters (`glossary.md:178-185`). P5's rule is different: the top tier of each lab's current lineup. The two can disagree on the same model. For example, OpenAI publishes GPT-OSS in a 120B size, over the glossary's parameter line, while it is not OpenAI's top tier (which size GreenPT runs is unverified). A claim under the criterion would then contradict the cell, and the build check (S4) would fail by design. So the row cites sources only: each product's own model list, and the lab model pages behind the page's dated large-model list. The glossary and the criterion stay as they are; this page does not use them.

**Label wording for ownership.** "Non-profit" no longer covers the good answers, so the row's short answer is "non-profit or similar" (21 characters, about two lines in the 7rem phone label column); the stance sentence and the Evidence entry list all five good structures.

Free tier, agent web search and normal web search carry `ideal: yes` today; S5 removes it.

**Inactive** means the slug sits under `inactive_templates:` (`templates.yaml:142`), which neither the pipeline nor the Astro criteria loader reads (`templates.yaml:138-140`; `content.config.ts:262-268`). A claim citing one fails `dr lint` `broken-criteria-slug` (`pipeline/linter/checks.py:270-287`, which gets only `templates` slugs from `pipeline/linter/runner.py:54-64`). The two criteria the page needs are active (S12); `data-jurisdiction` stays inactive (P3).

### Findings to verify or fix (F-)

| Id | Finding | Where | Fixed in |
|---|---|---|---|
| F1 | GreenPT data jurisdiction says "Swiss (FADP + GDPR)", while its summary says "GreenPT BV, Netherlands" and hosting at Scaleway in France. Unverified which is right. | `responsible-ai.md:255` vs `:30-31` | S8 |
| F2 | Earthly Insight's product URL is `.com`; its privacy link is `.ai`. | `:71` vs `:158` | S8 |
| F3 | The `ideal` field is in the schema and data but nothing renders it. The mobile CSS comment still describes an "Ideal column". | `content.config.ts:349-352`; `ResponsibleAIMatrix.astro:540-543` | S5 |
| F4 | `no-good` reads "No (negative)" to screen readers but "No (preferred)" in the legend: screen reader users hear the opposite of what sighted users see. | `ResponsibleAIMatrix.astro:22` vs `:216` | S5 |
| F5 | Yes is always green and No always red, including rows with no stance (e.g. "Image and document analysis"), so the colors state opinions the page never states. | `ResponsibleAIMatrix.astro:459-466`; `responsible-ai.md:204-214` | S5 |
| F6 | The cell `footnote` field exists but nothing renders it and no cell sets it. | `content.config.ts:325` | S3 (removed) |
| F7 | Maturity values ("2 months (Beta)") are relative to an unstated date and go stale. | `responsible-ai.md:193-203` | S8 |
| F8 | The row says "Open-source models" while summaries say "open-weight"; the criterion note describes public weights. | `:262-263`, `:29`; `templates.yaml:199-204` | S8, S12 (wording: R4) |
| F9 | Typo "committments". | `:41` | S8 |
| F10 | Model names may be stale (Ecosia "GPT-4 mini" in the summary, "GPT mini" in the cell). Unverified. | `:47`, `:141` | S8 |
| F11 | Product columns are not in alphabetical order, so the order can read as a ranking. Order by name: ChatGPTree, Earthly Insight, Ecosia AI, Euria, GreenPT, TreadLightlyAI, Viro AI. | `:23-86` | S8 |
| F12 | Ecosia's ownership cell names two structures ("Non-profit, Steward-ownership"); the `corporate-structure` vocabulary takes one. Unverified which applies; both are good under P6, so the choice changes no color. | `:164`; `templates.yaml:20-28` | S8 |
| F13 | Accessibility details assert WCAG levels ("Level A", "Level AA+") with no evidence. Under Q10 each level needs an audit report, a check record or the product's own statement, or it comes out; under P4 a stated Level A is Partial, not Yes. | `:244-250` | S8, S10 |
| F14 | Several model cells name a family, not a model ("GPT", "Claude", "Gemini", "Qwen 3", "Llama 3"), which P5's tier rule cannot classify. | `:140-146` | S8 |
| F15 | The page `description` names 4 of the 7 products, not in alphabetical order. | `:3` | S8 |
| F16 | `collectFreshestDate` walks a YAML date (a `Date` object) as an object and never counts it, so an unquoted `last_checked: 2026-10-12` would not reach `dateModified`. The one page that uses the key quotes its dates (`turn-off-ai.md:38`). Likely, not yet shown by a test. | `src/lib/resourceSchema.ts:22-30` | S3 |
| F17 | The `planned` cell type has an icon and color but no cell uses it, no legend entry, and no place in the stance or verdict rules. | `content.config.ts:316`; `ResponsibleAIMatrix.astro:24`, `:465` | S3 (removed) |

## Design

### Evidence tiers

Each cell has exactly one tier, derived from what it cites (no separate `tier` field that could disagree with the citations):

| Tier | Rule | What the reader gets |
|---|---|---|
| Reviewed claim | the cell cites a claim that is `status: published` and whose sidecar names a reviewer that `resolveReviewer` maps to a person (`src/lib/reviewers.ts:45`), the same test as the claim page's "Reviewed and approved by" line (`src/pages/research/claims/[...slug].astro:109-110`) | the claim page: verdict, confidence, sources, reviewer |
| Source | no claim; the cell cites one or more files in `research/sources/` | the source page: publisher, accessed date, archived copy where one exists |
| Not yet sourced | cites nothing | the author's assertion, marked as such; a `last_checked` record shows in the Evidence section when present |

`reviewed_at` alone is not enough: `dr publish` sets it with `reviewer: null`, and the claim page then shows "Unreviewed" (`pipeline/orchestrator/cli.py:2118-2124`). Page claims are approved with `dr review --approve`, never `dr publish`.

An ownership cell with an owner (P6, `owned_by` in "Data model") has two parts of evidence; its tier is the lower of the two.

**Tier "Source" reuses `research/sources`; no bare URLs.** Reasons:
- `docs/mission-and-voice.md:33` requires every source to link to an archived copy where one exists. A source file carries `archived_url`, `publisher` and `accessed_date` (`content.config.ts:9-33`); a bare URL carries none of them.
- The build can check a source exists; it cannot check a bare URL is still the page the author read.
- Intake already exists: `dr step-ingest <url> --write` writes the file (`pipeline/orchestrator/cli.py:321-323`), and AGENTS.md:72 lets pipeline commands write under `research/`.
- A later claim on the same cell can cite the same source file.

Costs: one ingest per URL, and two side effects. `dr lint` warns `unreferenced-source` for any source no claim cites (`pipeline/linter/checks.py:616-639`; fixed in S11). Source pages list the claims that cite them (`src/lib/citations.ts`) and will not list this page (accepted; out of scope).

**Facts checked by using the product** (Q4): cite the product's own feature, help or pricing page as a source where one exists. Otherwise the cell records `last_checked`, its Evidence entry reads "Checked by Dangerous Robot, <date>", and the tier stays "Not yet sourced".

**TreadLightlyAI** (Q1): the product carries `max_tier: source`. Its cells show answers and stance colors like every other product, cite sources only, and no claims are researched for it, so it needs no research entity. The disclosure sentence stays above both tables (`responsible-ai.md:285`; `docs/decisions.md:41`).

### How a cell shows answer, good/bad and tier

Three parts per cell:
- **Answer** (the fact): yes, no, partial, unknown, n/a, or text. The icon shape carries it, as today (`ResponsibleAIMatrix.astro:16-26`).
- **Good or bad** (the page's opinion), stance rows only:
  - Yes/no rows: set once per row by `ideal.value`. The cell is good when its answer equals the stance, bad when it is the opposite, mixed when partial, neutral when unknown or n/a.
  - Text rows (models, ownership): text has no yes or no, so the match (good, mixed, bad, unknown) is computed from structured fields in the cell, never set by hand (see "Data model"). Models: from the models the cell lists and the row's dated large-model list (P5). Ownership: from the cell's vocabulary word and any owner (P6).
  - Accessibility (P4): answers are yes, partial or unknown only; `no` is rejected by the build check.
  - Feature rows: every cell is neutral (text color).
- **Tier**: an evidence mark after the answer (D1, below).

No totals, no per-product counts, no sorting by color. That keeps to "no composite score or ranking" (`docs/mission-and-voice.md:28`).

### Display (D1 plus a popup)

- **Cell**: icon colored by stance, optional detail text, then a small evidence mark: a scale icon (lucide `scale`) for "Reviewed claim" (not a check, which would read as a Yes answer; the site's claim icon in `ObjectTypeIcon.astro` becomes the same scale, SITE-AA (Scale claim icon)), a link icon for "Source", nothing for "Not yet sourced". Adds roughly 1.5rem per cell (estimate, check in S6); the table already extends past the page at 640px (`ResponsibleAIMatrix.astro:540-576`).
- **Row label**: stance rows get a second line, "We prefer:" then the preferred answer's icon (check or x) in the good stance color, with the word ("Yes", "No") as visually hidden text; text rows keep words (e.g. "We prefer: no large models"), kept to a few words because the label column is 7rem on phones (`ResponsibleAIMatrix.astro:546`); the full rule goes in the stance sentence and the Evidence entry. Feature rows get no second line.
- **Legend**: the icons, the two evidence marks, "No mark: not yet sourced", and one sentence: "Rows without a “We prefer” line compare facts only; we take no position on them." Legend text at `--font-size-sm` with 18px icons (up from `--font-size-xs` and 14px).
- **Evidence section** below the table: one collapsed entry per row. The entry opens with the stance sentence and its evidence (stance rows), then one item per product (id `ev-<row>-<product>`) showing the claim's `VerdictBadge` (size `sm`), confidence and as-of date, or each source with publisher, accessed date and archived copy, or the check record, or "Not yet sourced". The models entry also shows the dated large-model list with its sources. A last group covers the summary table (ids `ev-summary-<field>-<product>`, `<field>` being the summary key such as `environmental`). It lists every product whatever the product filter hides, since the filter (`ResponsibleAIFilters.astro`) acts on the table only.
- **Popup on the mark**: small detail without leaving the table.

| Part | Specification |
|---|---|
| Content (under about 40 words) | Tier name. Reviewed claim: `VerdictBadge` `sm`, confidence, as-of date. Source: the first source's publisher and accessed date, plus "and N more" when there are more. One link: a reviewed claim's says "Open claim page" and goes to the claim's page; a source's says "See sources below" and goes to `#ev-<row>-<product>`. Each has visually hidden text naming the product and row ("Open claim page for GreenPT, hosted on renewable energy") so the page's many such links are distinct out of context (WCAG 2.4.4). Built by a pure function, `popupContent`, in `matrixEvidence.ts`. |
| Trigger | The mark is a `<button type="button">` with `aria-expanded` and `aria-controls`, followed in the DOM by the popup (`<div hidden>`), the same disclosure pattern as `A11yControl.astro:8-26`. Accessible name, e.g. "Evidence for GreenPT, hosted on renewable energy: reviewed claim". |
| Open | Click, tap, Enter or Space toggles it. A mouse hover opens it after a short delay, only where `(hover: hover) and (pointer: fine)` matches and only for `pointerType` mouse, so a tap does not open and close it at once. A click on a mark whose popup hover opened pins it open (it does not close). Focus alone does not open it, so tabbing through the table stays quiet. |
| WCAG 1.4.13 | Dismissible: Esc closes the open popup without moving the pointer; focus returns to the mark if it was inside the popup. Hoverable: the popup touches the mark (no gap) and a short grace period covers the move, so the pointer can reach it. Persistent: a hover-opened popup stays until the pointer leaves both mark and popup, Esc, or another popup opens; a click-opened one stays until Esc, a click or tap outside, focus leaving both mark and popup (Keyboard row), or the mark is pressed again. |
| Keyboard | Tab from the open mark moves into the popup's link (DOM order). Focus moving outside both mark and popup closes it, so an open popup never covers the next focused mark (WCAG 2.4.11). One popup open at a time. |
| Placement | Below the mark, inside a `position: relative` cell, shifted to stay inside the viewport; width at most `min(16rem, 100vw - 32px)`; z-index 4: above the sticky header and row label (2 and 3, `ResponsibleAIMatrix.astro:343`, `:352`, `:365`), below the stuck pill nav (5, `src/styles/resources.css:172`), which it scrolls under. The table has no scroll container (`ResponsibleAIMatrix.astro:299-305`), so nothing clips the popup. |
| Style | `--color-popover-bg`, `--color-popover-border`, `--shadow-popover`, `--radius-md` (`tokens.css:37`, `:73-78`, `:112-117`). Mark states (as the mockup's states sheet): at rest no background; hover `--color-radio-selected-bg`; keyboard focus the site ring (`global.css:105`, 2px `--color-accent`, 3px offset); open the hover tint plus a 1px `--color-popover-border` outline. Claim mark `--color-accent`, source mark `--color-text-muted`. High contrast has no popover tokens of its own and inherits these; check contrast in S6. No animation under `prefers-reduced-motion` or `[data-motion="reduce"]` (as `A11yControl.astro:310`). |
| Script | One delegated listener set, on `document` rather than the matrix root because the summary table's marks sit outside it (`ResponsibleAIEvidenceMark.astro`). No new dependency. |
| Without JavaScript | Marks do nothing; the Evidence section (in the pill nav) holds the same detail. |

**Accessibility and themes**:
- Not color only: the "We prefer" line repeats in text what the color shows (WCAG 1.4.1). Each cell's hidden text reads, for example, "Yes, what we prefer." or "<cell text>. Not what we prefer."; mixed reads "Partly what we prefer."; unknown and feature-row cells read only the answer. A cell with no mark adds "Not yet sourced." so screen reader users get what the missing mark shows. Fixes F4.
- Marks are distinct shapes (scale vs link) with accessible names, and a 32 by 32 px hit area by padding (WCAG 2.2, 2.5.8 asks for at least 24).
- Colors come from tokens that already have dark, light and both high-contrast values (`src/styles/tokens.css:190-243`).

**Drift from site patterns (DR-)**:

| Id | Drift | Standards-consistent choice |
|---|---|---|
| DR1 | Verdict color tokens (`--color-verdict-true/false/mixed`) are used to mean "good/bad for responsibility", as today (`ResponsibleAIMatrix.astro:459-466`). Next to `VerdictBadge` chips in the popup and Evidence section, green would mean two things on one page. | Add alias tokens `--color-stance-good`, `--color-stance-bad`, `--color-stance-mixed` in `tokens.css`, set to the verdict values, so the meaning is named and can diverge later. No visual change. |
| DR2 | The "We prefer" line under each row label is a new text style. | Use `--font-size-xs` and `--color-text-faint` (the legend's style before this plan, `ResponsibleAIMatrix.astro:521-527`). |
| DR3 | The Evidence section is a new long list. | Collapsed `<details>` per row with `DisclosureIndicator.astro`, and the hash-opens-details script pattern from `src/pages/research/index.astro:395-407`, changed in two ways: it opens `el.closest('details')`, because the `ev-` ids sit on items inside the row's `<details>`, not on the `<details>` itself; and it also runs on a click of an in-page `#ev-` link, because following the same hash twice fires no `hashchange`. Targets get `scroll-margin-top: 5rem` like the page's other sections (`ResponsibleAIMatrix.astro:285`), so the stuck pill nav does not cover them. Heading style matches the Comparison table's `h2` with the return-to-top link. |
| DR4 | The site's hover help today is the native `title` attribute (`VerdictBadge.astro:14`; `src/pages/research/sources/[...slug].astro:67`), which keyboard and touch users cannot open. A non-modal popup is new. | Do not reuse `title`. Reuse `A11yControl`'s button, `aria-expanded`, `aria-controls` and `hidden` pattern and its popover tokens; leave out its modal parts (`role="dialog"`, `aria-modal`, focus trap, backdrop, phone bottom sheet). |

No drift: `VerdictBadge` size `sm`; lucide icons at the existing 14px and 18px sizes.

### How the page states its opinions

- Each stance row's `ideal` gets a one-sentence stance (`ideal.note`, already in the schema) and its own evidence (`ideal.sources`, new): sources for why the attribute matters (for example, why image generation costs more energy; the note at `templates.yaml:86` has no source today).
- A stance may link a Values position instead (Q11), shown as "Position: <heading>", never in the source list. Candidates: "AI is fueling environmental destruction" (`src/pages/values.astro:32`, whose text names "Frontier AI models") for the models and energy rows; "AI outcomes are being decided by a small group of people" (`:40`) for ownership. The Values headings have no ids today; S9 adds them.
- Rendered: the "We prefer" line in the row label, and the full stance sentence with its evidence at the top of the row's Evidence entry.
- The intro gets one or two sentences saying the page takes positions and where to find the reasons. Copy: TBD, Brandon to write. Copy rules apply (`docs/decisions.md:47`).
- The stance evidence is checked by the same build check as cell evidence.

### Data model

Cell data stays in the page's frontmatter (`data:` payload). Reasons: the page is hand-authored editorial content (AGENTS.md:61-75), the answer and detail are editorial, and deriving cells from claims cannot cover the tiers without claims. Claims are cited, not copied.

Changes to `matrixDataSchema` (`src/content.config.ts:303-412`):

```yaml
products:
  - key: greenpt
    entity: products/greenpt            # new, optional: the research entity, for the claim-entity check
  - key: treadlightly
    max_tier: source                    # new, optional: no claims may be cited for this product (Q1)
features:
  - key: renewable-hosting
    label: "Hosted on renewable energy"
    group: environmental
    criterion: renewable-energy-hosting # new, optional: the criteria slug claims in this row must carry
    polarity: same                      # new: same | inverted (inverted for data-used-for-training)
    ideal:
      value: "yes"
      note: "Stance sentence, Brandon to write."
      sources: [/research/sources/2026/example]        # new
      position: /values#ai-is-fueling-environmental-destruction   # new, optional (Q11)
    cells:
      greenpt:
        type: "yes"
        claim: /research/claims/greenpt/renewable-energy-hosting  # new
        sources: [/research/sources/2026/example]                 # new
        last_checked: "2026-10-12"                                # new; quoted, as `turn-off-ai.md:38` does (F16)
  - key: accessibility
    answers: ["yes", partial, unknown]  # new, optional: the only answers this row's cells may use (P4)
    ideal: { value: "yes" }
  - key: models                         # no criterion: sources only (P5)
    ideal:
      answer: "no large models"         # new: the short answer for a text stance row
      note: "Stance sentence, Brandon to write."
      large_models:                     # new (P5): the dated list the page shows in the models Evidence entry
        last_checked: "2026-10-12"
        sources: [/research/sources/2026/example-lab-models]   # each lab's own model page
        large: [Claude Opus, Gemini Pro]  # names in the form cells use; S5 seeds, S8 sources
        not_large: [Claude Sonnet, Claude Haiku, Gemini Flash]
    cells:
      example: { type: text, detail: "Claude Sonnet", models: [Claude Sonnet], sources: [...] }  # new: match computed
  - key: corporate-structure
    criterion: corporate-structure
    ideal:
      answer: "non-profit or similar"
      terms:                            # new (P6): must split the criterion's vocabulary, each word once
        good: [non-profit, steward-ownership, cooperative, B-corp, employee-owned]
        mixed: [privately-held]
        bad: [publicly-traded]
    cells:
      euria: { type: text, detail: "B Corp", term: B-corp, claim: ... }    # new: match computed from term
      example:
        type: text
        term: privately-held
        owned_by:                       # new, optional (P6): the owner, when the company is owned by another
          name: "Owner name"
          kind: publicly-traded         # publicly-traded | conglomerate (R3)
          sources: [...]
```

- Citations are rendered URL paths (Q3), following AGENTS.md:73. The check strips the prefix to find the entry.
- `ideal` takes `value` (yes/no rows) or `answer` (text rows), not both. A row with no `ideal` is a feature row.
- Models match: from the cell's `models` and the row's `large_models` lists. No `models` (the cell names only a family, F14): unknown. None large: good. Any large: bad (R1). Every model a cell lists must be in exactly one of the two lists, so a new or misspelled name fails the build instead of passing as "not large".
- Ownership match: any `owned_by` makes it bad (P6 states this whatever the company's own structure); otherwise the `terms` list holding the cell's `term` decides. `owned_by` is evidenced by its own sources. When a company fits several words (F12), its claim takes the word that decides its color, checked in the order bad, good, mixed; `dr review --approve` is where that is enforced.
- `last_checked` reuses the name `collectFreshestDate` already reads, so the page's JSON-LD `dateModified` follows the freshest check (`src/lib/resourceSchema.ts:13-37`; F16 fixes its date handling).
- Summary fields accept a string (as today) or `{ text, sources, last_checked }`; summary entries cite sources only, no claims. The schema's non-empty check on summary fields (`content.config.ts:390-409`) reads the `text` of the object form. Footnotes get the same optional `sources`. Inline links in text that are not evidence (for example the kSuite product link, `:177`) stay as links.
- `no-good` and `planned` (F17) leave `matrixCellType` (`content.config.ts:311-320`); the 5 `no-good` cells become `no`, and the row's stance is `no`. The unused cell `footnote` field (`:325`) is removed (F6).
- Product order in the data is alphabetical by name (Q9); both tables follow it.

**Answer and claim agreement.** The answer stays hand-entered (it must exist for every tier), and the build fails when a cited claim's verdict disagrees with it. Only rows with a `criterion` cite claims: the six yes/no rows other than accessibility, and ownership.

| Verdict | Answer allowed, polarity `same` | Answer allowed, polarity `inverted` |
|---|---|---|
| True | yes | no |
| Mostly true | yes, partial | no, partial |
| Mixed | partial | partial |
| Mostly false | no, partial | yes, partial |
| False | no | yes |
| Unverified | unknown | unknown |
| N/A | na | na |

Ownership: the cited claim must be True or Mostly true, and its title must contain the cell's `term`. The pipeline only accepts a title that resolves the template's vocabulary slot to one allowed word (`validate_analyst_title`, `pipeline/common/templates.py:184-203`, e.g. "Ecosia has steward-ownership corporate structure"), so the build can find the word in the title by matching the criterion's vocabulary.

**The build check** (S4) lives in a pure function in `src/lib/matrixCheck.ts` (its lookups are built from the research collections by `src/lib/matrixLookups.ts`), called from `src/pages/resources/[...slug].astro` right after `matrixDataSchema.parse` (`:37`), where a schema error already fails the build. It collects every problem and throws once. Deploy runs CI (`.github/workflows/deploy.yml:18`, which includes `dr lint`) and then the build (`:30`), so both gates sit in front of a deploy. It fails when:
- a cited claim does not exist;
- a cited claim is not `published` (draft, archived, blocked);
- a cited published claim has no reviewer that `resolveReviewer` maps to a person (stricter than `dr lint` `published-without-review`, `checks.py:128-157`, which checks only `reviewed_at`; see "Evidence tiers");
- a cited source does not exist (in a cell, a summary entry, a footnote, `ideal.sources`, `large_models.sources` or `owned_by.sources`);
- a cell in a row with no `criterion` cites a claim (models, accessibility and every feature row);
- the claim's `criteria_slug` differs from the row's `criterion`;
- the claim's `entity` is neither the product's `entity` nor its `parent_company`;
- the verdict disagrees with the answer (table above), or an ownership claim's title names a different vocabulary word than the cell's `term`;
- a product with `max_tier: source` cites a claim, in a cell or its summary;
- an ownership cell has no `term`, or a `term` outside the criterion's vocabulary; or the row's `terms` lists do not split that vocabulary with each word exactly once;
- a models cell lists a model that is in neither `large_models` list, or a name is in both lists;
- a cell outside those two rows sets `term`, `owned_by` or `models`;
- a cell's answer is not in its row's `answers`, where the row sets one;
- a row lacks a cell for an active product, or has a cell for a key that is no product (today a missing cell renders silently as "n/a", `ResponsibleAIMatrix.astro:168`);
- an `ideal.position` is not one of the Values position ids (kept in one exported list that `values.astro` also reads, S9).

A side effect, intended: when a refresh corrects a claim's verdict (the corrections-on-approval step in `docs/plans/completed/published-claim-refresh-trail.md`), the build fails until the cell's answer is updated, so the page cannot silently contradict its own evidence.

Alternatives considered: extending `scripts/check-citations.ts` (runs in CI but not in the deploy build; reads raw frontmatter), or a Python `dr lint` check (would parse the page data outside Astro's schema, so the check and the rendering could read it differently). The Astro route keeps the check next to the rendering and uses the same parsed data.

## Claim set and research load

Claims cover the 7 stance rows that have a criterion: renewable hosting, real-time energy display, image generation, published financials, data used for training, open-source models, ownership. Models (P5) and accessibility (Q10) are source-only stance rows; feature rows are source-only (data jurisdiction: P3). Products with claims: 6 (TreadLightlyAI has none, Q1).

| Item | Count | Notes |
|---|---|---|
| Claims | 42 (7 rows x 6 products) | 30 product claims (5 rows) and 12 company claims (published financials and ownership, one company per product). Today: 3 published claims, none for these products |
| Product entities created | 5 | Euria, Ecosia AI, ChatGPTree, Earthly Insight, Viro AI (S13) |
| Company entities created | 5 | for the 2 company rows: Infomaniak, Ecosia, ChatGPTree, Earthly Insight and Viro (S13; legal names from each company's own pages). GreenPT's exists. An owner named in `owned_by` needs no entity (sources only) |
| Criteria activated | 2 | `financial-transparency`, `open-source-models-only` (S12, done). The page uses neither `excludes-frontier-models` nor `data-jurisdiction` |
| Sources, stance-row cells | up to 63 (9 rows x 7) | fewer in practice: one privacy policy can back several rows |
| Sources, large-model list | one per lab named in the models row | each lab's own model page (P5) |
| Sources, feature-row cells | up to 49 (7 rows x 7) | as far as possible (S10) |
| Sources, summary entries | up to 28 (4 x 7) | S7 covers the 9 existing links; the rest as far as possible (Q7) |

Claims run row by row across all products, not product by product, so each row compares like with like. `dr onboard "<name>" --type product --only <slugs>` limits onboarding to the page's criteria (`pipeline/orchestrator/cli.py:1609`); without `--only` it drafts every active product criterion (8) or company criterion (5).

The prerequisites (published-claim refresh trail and claims readiness CR1 to CR6) are done: `docs/plans/completed/published-claim-refresh-trail.md`, `docs/plans/completed/site-j-claims-readiness.md`.

## Steps

Each step is a small commit. Test-first where there is code: write the test, watch it fail for the stated reason, then change the code.

### Honest labels (no new research)

#### S1: site-side unit tests run in `inv check` and CI
The site has no JS unit test runner for `src/`; the only test file is `workers/api/test/petitions.test.ts`, and `inv test` runs pytest. Add `"test:site": "tsx --test 'src/lib/**/*.test.ts'"` (Node's built-in test runner through `tsx`, already a dev dependency, `package.json:42`; Node 22+, `package.json:17-18`; confirm `tsx --test` with a glob works on this Node before relying on it), call it from `inv check` (`tasks.py:40-45`) and `.github/workflows/ci.yml` (next to `:17-19`).
Verify: locally, with one deliberately failing test (not committed), `npm run test:site` and `inv check` exit non-zero, and zero once it is removed; after the next push Brandon approves, the CI run log shows the `test:site` step running and passing.

#### S2: pure functions for tier, stance and verdict agreement
`src/lib/matrixEvidence.ts`: `cellTier(cell, product, lookups)` (honors `max_tier`; the lower tier when an ownership cell has `owned_by`), `cellStance(cell, feature)` (good, bad, mixed, neutral; yes/no rows from `ideal.value`, models from `models` and `large_models`, ownership from `term`, `terms` and `owned_by`, feature rows always neutral), `verdictAgrees(verdict, answer, polarity)` (the table above), `popupContent(cell, product, feature, lookups)` for S6, and `tierCounts(data)` for S10. Plain types only; no `astro:content` import, so the tests run outside Astro (`src/lib/reviewers.ts` is plain and can be imported).
Verify: table-driven tests for every verdict x polarity pair, every answer x stance pair, the models rule (no models, none large, all large, some large), every ownership term plus `owned_by` over a good term, each tier (including a published claim with `reviewed_at` set and `reviewer: null`, which is not "Reviewed claim"), and the TreadLightlyAI cap.

#### S3: schema for cell evidence, row stances and product entities
Move the matrix schema (`content.config.ts:303-412`) to `src/lib/matrixSchema.ts`, imported by `content.config.ts` and the route (which already imports it from `content.config`, `[...slug].astro:14`), so tests can load it: `content.config.ts` imports Astro's loaders, which a plain Node test cannot load (confirm `astro/zod` resolves under `tsx`; if not, add `zod` as a direct dependency at the version Astro uses, since today it is only a transitive one). Add the fields in "Data model"; remove `no-good` and migrate its 5 cells (`responsible-ai.md:152-156`) and the row's `ideal.value` (`:150`) to `no`; remove `planned` (F17) and the cell `footnote` field (F6), in the schema and in the component's `CellType` and `Cell` types (`ResponsibleAIMatrix.astro:6-32`). Fix F16: `collectFreshestDate` checks for a `Date` before it walks objects.
Verify: `npm run build` passes; unit tests show the schema rejects `type: "no-good"`, `type: "planned"`, an unknown `polarity`, an `ideal` with both `value` and `answer`, and an unknown `owned_by.kind`, and accepts the migrated page data and a summary entry in object form; a `collectFreshestDate` test fails before the F16 fix with an unquoted YAML date and passes after.

#### S4: build check that fails on bad citations
`validateMatrixEvidence(data, { claims, sources, entities, criteria, valuesPositions })` in `src/lib/matrixCheck.ts`, called from `[...slug].astro:37`.
Verify: a fixture test for each failure in "The build check", each asserting the message names the row and product; one passing fixture; today's page data passes (until S5 the models and ownership rows have no `ideal`, so they are feature rows and set none of the new fields). Then one real cell pointed at a missing source fails `npm run build`, reverted. Run once from a clean checkout (CI, or `git worktree add --detach` of HEAD), because the main checkout holds untracked research files that CI does not have.

#### S5: cells colored by the row's stance, feature rows neutral, `no-good` retired
Rendering uses `cellStance`; feature rows render in the neutral text color (fixes F5). Remove `ideal` from free tier, agent web search and normal web search (Q5). Add `ideal` to models (`answer`; `models` only on cells whose every model is named specifically, the rest unknown until S8, F14; `large_models` seeded by sorting every model those cells name, Mistral and GPT-OSS ones included, into `large` or `not_large` by P5 and R2, with no `sources` until S8) and ownership (`answer`, `terms`, a `term` per cell read from today's text: "B Corp" is `B-corp`, "Private", the LLCs and "Sole proprietorship" are `privately-held`, Ecosia's pair is either good word until F12). Add `answers: [yes, partial, unknown]` to accessibility (P4); its `yes` cells stay until S8 (F13). Add the "We prefer" line, the hidden cell text (fixes F4), the "No mark: not yet sourced" legend entry and the legend sentence "Rows without a “We prefer” line compare facts only; we take no position on them." Alias tokens per DR1. Remove the `no-good` and `planned` icons, legend entry and CSS (`ResponsibleAIMatrix.astro:22`, `:24`, `:215-217`, `:463-465`, `:536`); remove the stale mobile comment (F3).
Verify: a Lighthouse accessibility audit of the page before the change, recorded here as the baseline (2026-10-09, desktop, score 93; two failures, neither in the table: `color-contrast` on the site nav links, `link-in-text-block` on the summary table's inline links; after S5 the same score and the same two failures); after: build; Chrome DevTools screenshots of the table in dark, light, dark high contrast and light high contrast at 1280px and 375px; the Lighthouse audit shows no failure missing from the baseline; the accessibility tree for one real cell in each stance the page has (good, bad, mixed, neutral, feature row, text good, text mixed, text unknown) reads as specified; stances with no real cell yet (likely text bad) are covered by S2's tests.

#### S6: evidence marks with a detail popup, and the Evidence section
Per "Display (D1 plus a popup)". New `ResponsibleAIEvidence.astro`; pill nav gains "Evidence" (`[...slug].astro:80-87`); entries have ids `ev-<row>-<product>` and open on hash. Summary entries get the same marks (`ResponsibleAISummary.astro`).
Verify:
- unit tests of `popupContent` with fixtures for each tier, a reviewed claim included (no page cell cites a claim until S15, which repeats this check on real cells);
- build; for one cell temporarily citing an existing source file (no cell cites one until S7; reverted after), the popup shows the right content and its "See sources below" link lands on an open Evidence entry, also when followed twice; a reviewed-claim popup's "Open claim page" link goes to that claim's page; a "Not yet sourced" cell has no mark and its Evidence item says so;
- keyboard only: Tab to a mark, Enter opens, Tab reaches the link, Esc closes and focus is on the mark, focus alone opens nothing; Tab past the link closes the popup and the next mark is not covered;
- mouse: hover opens; the pointer moves from mark onto popup without it closing; leaving both closes it; hover then click the mark: it stays open, and leaving no longer closes it;
- touch (DevTools touch emulation at 375px): tap opens, tap outside closes, no open-then-close flicker;
- one popup open at a time; the popup stays inside the viewport at 375px, over the sticky row label and under the stuck pill nav;
- popup contrast in all four themes; no motion with reduced motion set;
- screen reader names for one mark of each tier and for each popup link ("Open claim page", "See sources below");
- an Evidence item for a product hidden by the product filter still shows.

#### S7: today's inline links become source files
`dr step-ingest <url> --write` for each of the 9 summary links counted in "What the page asserts today" (at most 9 files; one already ingested is reused); cite them in the summary entry's `sources`. The 2 kSuite links stay plain product links. The 2 hedged privacy-policy links are not cited here: a citation would give an "unknown" cell the "Source" tier, so S10 reads those policies, sets the answer and cites them together.
Verify: build passes the S4 check; each new source file has `archived_url` or a recorded reason it has none (`site-j-claims-readiness.md` CR4); each cited summary entry shows the Source mark.
Result (2026-10-09): 6 ingested, each with `archived_url`, cited from 5 summary entries. Not ingested, left as inline links for S8 or S10 to resolve: Infomaniak commitments (`/en/ecology/commitments`, 404, no Wayback snapshot); Redmonitor Substack on Evertreen (404, no Wayback snapshot); Wikipedia TerraPass (live, but the ingestor's fetch gets 403; a tertiary source, so S10 may prefer the DFPI record already cited).

#### S8: content fixes for the findings
F1, F2, F7 to F15, each with a source where it changes a fact. F11: reorder `products` alphabetically by name. F12: one `term` per ownership cell. F13: under P4, "Level A" becomes partial and a WCAG level stays only where its evidence states it; with no evidence the cell becomes unknown. F14: name every model specifically enough for P5's rule, and replace the seeded `large_models` lists with the model names the cells use, each checked against its lab's own model page (ingested and cited in `large_models.sources`), with today's date in `last_checked`. F15: a description that names no subset of products (copy: Brandon to approve; max 200 characters, `content.config.ts` resources schema).
Verify: a unit test that `products` is in alphabetical order by name (Q9), written first and watched fail on today's order, passes after F11; build; rendered-page check of each changed cell; every models cell has `models`, or its detail text says the product does not name its models.
Result (2026-10-09): F1 fixed to "EU (GDPR)" from GreenPT's privacy page (ingested, cited). F2: both Earthly Insight domains serve the same site; no change. F7: the row is labeled "Maturity (as of March 2026)", the page's publication month, since the ages cannot be recomputed without launch dates. F8, F9, F11 (with the test), F12 (one `term`, done in S5), F13 (every accessibility cell is unknown until S10's checks) and F15 (new description, Brandon to approve) done. F10: Ecosia's page returns 403 to a plain fetch; unverified, unchanged. F14: ChatGPTree's cell names GPT-4o from its home page (ingested, cited) and GPT-4o joins `large` (OpenAI's top tier when released, R2); Euria, Viro and Earthly Insight cells still name families, their pages render client-side and show no model names to a fetch; the lab model pages behind `large_models.sources` and `last_checked` are not ingested yet. The remaining F10 and F14 work moves to S10 with the other source work.

#### S8a: apply the post-S8 answers
A1 to A8 under Decisions. Each changed fact cites a source; a launch date with none shows "Not yet sourced".
Verify: build passes the S4 check; each new source file has `archived_url` or a recorded reason; rendered-page check of each changed cell; the dark-theme stance red computed against the background it renders on.
Result (2026-10-10): A1 and A6 were already on main (description; Ecosia `term: steward-ownership`); unchanged. A2: Maturity is labeled "Maturity"; Ecosia AI "Launched Oct 2023 (beta)" (Ecosia's blog, 2023-10-16, lists AI Chat among "these new, planet-approved features", "currently in beta") and Euria "Launched Dec 2025" (Infomaniak's launch post, 2025-12-09), both ingested and cited; the other 5 are "Not yet sourced": ChatGPTree (GeekWire, 2025-06-09, says the beta launched days earlier, but the ingestor's fetch gets 403), Earthly Insight (sources disagree: a press release of 2025-12-10 calls it "a new AI assistant now available", the Global Rewilding Alliance described its platform on 2025-08-27, and the summary's unsourced note says October 2025), GreenPT (Product Hunt says only "Launched in 2025"), TreadLightlyAI and Viro AI (none found). A3 and A4: accessibility shows the earlier answers, tier "Not yet sourced": Ecosia AI and TreadLightlyAI Yes "Level AA+"; GreenPT and Earthly Insight Partial "Level A"; Euria, Viro AI and ChatGPTree Partial. A5: GPT-4o (large) cites OpenAI's GPT-4o model page ("our versatile, high-intelligence flagship model"); GPT-OSS (not large) has no source yet: OpenAI's gpt-oss model card (a PDF, which says gpt-oss-120b "approaches OpenAI o4-mini accuracy") cannot be ingested (unsupported content type), and openai.com returns 403; S10 sources it and the Mistral and Anthropic names, and only then sets `large_models.last_checked`. A7: the Evertreen link had a typo (`redmonitor`, not `reddmonitor`); the REDD-Monitor post (2025-12-18) is ingested and the sentence now says what it says, noting Evertreen's response. Infomaniak's commitments page is gone; its Environment page (`/en/ecology`) is ingested and cited with the existing certificates source, and "Certified by myClimate.org" became "Offsets 200% of its CO2 emissions through myclimate.org", which both sources state (neither says certified). A8: dark theme only (`:root[data-theme="dark"]:not([data-contrast="high"])`), `--color-stance-bad` is #e05555: 4.68:1 on #19191b (the computed background behind the cells), 4.24:1 on `--color-surface` #212226; the old #b22222 was 2.63:1 (WCAG 1.4.11 asks 3:1). Computed icon color per theme in the browser: dark #e05555, light #8b0000, dark high contrast #ff3333, light high contrast #660000; `--color-verdict-false` is still #b22222. Every new source has an `archived_url`, but the GPT-4o one points at a capture of a 404 page (not hand-edited; the lookup bug is RF26 in `docs/UNSCHEDULED.md`). All 13 sources the page cites were checked for a live `archived_url` (HTTP 200); only the GPT-4o one fails. Commits `30c102f`, `8a882ae`, `9022f61`.

### Sources for every stance row

#### S9: stance sentences and their evidence
Brandon writes `ideal.note` for each of the 9 stance rows; each gets `ideal.sources` or a Values `position` (Q11). Add ids to the four position headings in `src/pages/values.astro` (`:21`, `:32`, `:40`, `:48`) from one exported list that the S4 check also reads. Intro sentences (copy TBD, Brandon to write).
Verify: build check passes; each Values heading id resolves; the Evidence section shows each stance with its sources or its labeled position.
Result (2026-10-10), code only: `src/lib/valuesPositions.ts` lists the four position headings; `values.astro` renders their text and ids from it, and the matrix lookups pass the same ids to the build check (before, the route passed none, so any `position` would have failed). Unit tests (`valuesPositions.test.ts`): the ids, the heading lookup, each listed position passes the check, "our-contradictions" fails. With a temporary `position` on the renewable-hosting row, `npm run build` failed before the change ("is not a Values position") and passed after; the Evidence entry read "Position: AI is fueling environmental destruction." and its link's id resolved on `/values`; reverted. The built Values page differs only by the four `id` attributes. Copy pending: draft stance sentences and intro sentences for Brandon are in `handoff/2026-10-10-site-j-build.md`; no row carries a note or position until he approves them. Commit `96997f7`.

#### S10: one source per stance-row cell, then feature rows and the summary
Ingest and cite a source for every stance-row cell, row by row; then feature rows and summary entries as far as possible. The two hedged data-training cells (`responsible-ai.md:157-158`) start here: read the policy, set the answer, cite it. Facts checked by using the product follow Q4. Accessibility cells follow Q10 and P4; a "barriers found by our check" Partial records in the check record what was checked (tool, pages, date), so it can be repeated. Ownership cells add `owned_by` with its sources wherever a source shows an owner (P6).
Verify: a count of cells per tier printed by `tierCounts` through a small script, recorded in this plan after each row (no count on the page itself); each new source file has `archived_url` or a recorded reason (CR4, as the roadmap's SITE-J entry requires for every source the page cites).
Result (2026-10-10), rows 1 to 5 of the stance rows; rows 6 to 9 (open-weight models, accessibility, models, ownership), the feature rows and the summary are pending. Page counts before: 0 reviewed claim, 4 source, 108 not yet sourced (112 cells). A cell is sourced only where a page states the fact; a page that leaves something out is not a source for a negative answer. Each new source's `archived_url` was checked: HTTP 200, and the CDX record for that exact timestamp shows status 200 for the same URL.

| Row | Cells sourced | Cells not yet sourced | Page tier counts after (claim / source / none) |
|---|---|---|---|
| Data used for training | 4 (GreenPT, Euria, TreadLightlyAI, Viro AI) | 3 (ChatGPTree, Earthly Insight, Ecosia AI) | 0 / 8 / 104 |
| Hosted on renewable energy | 3 (GreenPT, Euria, TreadLightlyAI) | 4 (ChatGPTree, Earthly Insight, Ecosia AI, Viro AI) | 0 / 11 / 101 |

Data used for training:
- Sourced: GreenPT (its privacy page, already a source: "We never use your data to train our AI models"); Euria (Infomaniak's launch post, already a source: "your data is never used to train models"); TreadLightlyAI (its privacy policy, new: "never use your conversations to train AI models"); Viro AI (its Viro AI privacy policy, new: "We don't train AI models on your chats"). Viro's detail now says what the policy says, "Ads may be based on the current message" (the policy: "Ads may be based on the content of the current message or session context"), in place of "Ads based on chat content".
- ChatGPTree, unknown, not yet sourced: its privacy policy (https://www.chatgptree.ai/legal/privacy, "Last updated October 29 20205" as printed) and terms (https://www.chatgptree.ai/legal/terms) do not mention training. The hedged "probably?" link is removed.
- Earthly Insight, unknown, not yet sourced: its two documents disagree. The privacy policy (https://www.earthlyinsight.ai/privacy-policy, "Updated September 30th, 2026") says "Your User Input (Prompts) are used solely to generate AI responses from our third-party AI model providers for your current session"; the terms (https://www.earthlyinsight.ai/terms-and-conditions, "Updated June 27th, 2025"), section 9, license "your User Content", "such as your prompts", for "our internal service improvement (e.g., AI model training where anonymized or aggregated and subject to privacy commitments)". Both pages render by script, so the ingestor fetches an empty page: its run wrote "A privacy policy page with no substantive content" with a 2025-08-09 capture; the file was deleted. The text above was read from the site's JavaScript bundle. The hedged "probably not?" link is removed.
- Ecosia AI, "no", not yet sourced: no current Ecosia page says chats are not used for training. The help article on its AI (https://support.ecosia.org/article/1006-ai-search) says only that image prompts are "not used to train AI models"; the privacy policy (403 to a plain fetch; read from the Wayback capture `20260921142100`) says a "limited sample of anonymised conversation data" goes to Langfuse for quality assurance, and nothing on training. The older help article that said "Your data is not used to train the AI" (`/article/534-ecosia-chat-ai`, last updated 2025-11-13, when OpenAI was the provider) now returns 404.

Hosted on renewable energy:
- Sourced: GreenPT (its sustainability page, new: "Every chat, every API call, and every document processed on GreenPT runs on data centers powered by 100% renewable energy"); Euria (Infomaniak's launch post: "100% powered by renewable energy"); TreadLightlyAI, partial (its home page, new: "Free, Starter and Builder all use renewable energy"; the page also offers Anthropic's models). TreadLightlyAI's detail now says "On Free, Starter and Builder plans", the page's words, in place of "All but Anthropic": no page fetched says where Anthropic's models run.
- ChatGPTree, Earthly Insight and Ecosia AI, "no", not yet sourced: no page of theirs says what energy the chatbot runs on. Ecosia's privacy policy names Mistral AI as its main model provider and OpenAI as a fallback; its AI blog post (already a source) says it has "invested €18M in renewable energy projects", which is not a statement about hosting.
- Viro AI, "no", not yet sourced: its methodology page (already a source) says Viro "matches estimated inference energy with verified renewable energy generation", "currently global-average, not yet region- or time-specific", with "no offsets or carbon credits". That describes matching, not where the service runs; whether matching makes the answer "no" or "partial" is a question for Brandon (handoff note).

#### S11: the research linter counts sources the page cites
`check_unreferenced_sources` (`checks.py:616-639`) also collects the `/research/sources/...` paths cited anywhere in `src/content/resources/*.md` frontmatter, reading only, and skips that step when the directory is absent (so a research repo split off later still lints). AGENTS.md:72 limits what the pipeline writes, not what it reads. Without this, `dr lint` warns on every page-only source with the hint "remove the file" (`checks.py:637`), which an agent could follow.
Verify: a pytest case with a source cited only by a page fixture produces no warning; an uncited source still warns; a fixture with no `src/content/resources` directory runs without error.
Result (2026-10-10): `page_cited_source_ids` in `checks.py`, passed `repo_root` by the runner; the warning now reads "not cited by any claim or page". Five pytest cases, all failing first (no `repo_root` argument; the runner warned on the page-cited source): page-only source, uncited source, a path in the page body (does not count), no resources directory, and a runner case. `dr lint` on the real tree: 18 `unreferenced-source` warnings before, 5 after (0 errors both times), which is the 13 sources the page cites. `inv audit.prune --apply` reads the same check, so it no longer deletes page-cited sources. Commit `0d812fb`.

### Claims, row by row

#### S12: activate the inactive criteria the page needs
Move `financial-transparency` and `open-source-models-only` from `inactive_templates` into `templates` (`research/templates.yaml:128`), with the `open-source-models-only` text worded per R4 (no claim cites it yet, so the slug stays). Before moving, find out how criterion intake fans out: AGENTS.md:11 says a new criterion generates a claim for each entity it applies to, so activation may queue drafts for Anthropic, Google, Microsoft, OpenAI and the existing products, beyond this page. Record what actually happens here. Each activated criterion also gets a public page under `/research/criteria/`, and later `dr onboard` runs without `--only` on any entity include them.
Verify: `dr lint` reports no errors; a claim fixture with `criteria_slug: open-source-models-only` no longer raises `broken-criteria-slug`; both criteria pages build; no drafts appear for entities outside the page unless intended.
Result (2026-10-10): activation queues no claims. The code that reads `templates` from `templates.yaml`: the linter's slug set (`pipeline/linter/runner.py:54`); `dr onboard`'s template step (`pipeline/orchestrator/pipeline.py:2070`, the only caller of `templates_for_entity_type`); `dr step-analyze` and `dr claim-refresh`, which look up an existing claim's slug (`pipeline/orchestrator/cli.py:586`, `:993`); and the Astro criteria loader (`content.config.ts:262`). No command, hook or workflow turns a new criterion into claims; AGENTS.md:11 describes the planned Router, not shipped code. Claims under the two criteria appear only when `dr onboard` runs: with `--only`, for the slugs named; without it, a product now gets 8 criteria and a company 5. The effect beyond this page: each criterion's public page lists every entity of its type as "No claim on file" (`src/pages/research/criteria/[slug].astro:24`): `financial-transparency` lists Anthropic, Brave Software, Google, GreenPT, Microsoft and OpenAI; `open-source-models-only` lists Brave Browser, ChatGPT, Claude, Gemini and GreenPT; S13's entities join them. `open-source-models-only` reads "PRODUCT uses only open-weight models" (R4); its notes and the `financial-transparency` entry are unchanged. The two page rows carry no `criterion:` yet; S16 adds it with their claims. Verify: `TestResponsibleAIPageCriteria` (`pipeline/tests/test_templates.py`) failed first, a fixture claim under each slug raising `broken-criteria-slug` (`criteria_slug "financial-transparency" not found in research/templates.yaml`) and the old wording failing, and passes after; the tests that count active templates follow the new set (`test_templates.py`: 16, 8 product, 5 company; `test_onboard.py`: a company onboard applies 5 and ingests 6 times); `dr lint` 0 errors; `npm run build` writes `dist/research/criteria/financial-transparency/index.html` and `dist/research/criteria/open-source-models-only/index.html` (heading "PRODUCT uses only open-weight models"); `git status research/claims` shows no new files after activation, lint and build. Commit `08dc73a`.

#### S13: entities for the page's products and companies
Create the 5 product and 5 company entity files in the research-load table, following the GreenPT pair (`research/entities/products/greenpt.md`, `companies/greenpt.md`): name, type, website, description, and `parent_company` on each product; then `dr entity-enrich <ref>` fills founded, description and history (`cli.py:1810`). Add `entity:` to each product on the page except TreadLightlyAI.
Verify: `dr lint` reports no errors (new entities raise `unreferenced-entity` at severity info until claims cite them, `checks.py:659`); build; each entity page renders.
Result (2026-10-10): 10 entity files, frontmatter only (no body), each description in the site's own words: products `euria`, `ecosia-ai`, `chatgptree`, `earthly-insight`, `viro-ai`, each with `parent_company`; companies `infomaniak`, `ecosia`, `chatgptree`, `earthly-insight`, `viro`, each with `legal_name`. The page's 6 products other than TreadLightlyAI carry `entity:` (GreenPT's included). Legal names, read 2026-10-10:

| Company | `legal_name` | Where |
|---|---|---|
| Infomaniak | Infomaniak Network SA | https://www.infomaniak.com/en/legal: "Data controller : Infomaniak Network SA, Rue Eugène-Marziano 25, 1227 Les Acacias (GE), Switzerland" |
| Ecosia | Ecosia GmbH | https://www.ecosia.org/imprint (403 to a plain fetch; read from the Wayback capture `20260730211843`): "Imprint Ecosia GmbH Gerichtstrasse 23 (courtyard 4) 13347 Berlin, Germany" |
| ChatGPTree | ChatGPTree, Inc | https://chatgptree.ai/legal/terms: "This website is operated by ChatGPTree, Inc."; the App Store lists the seller of its app as "ChatGPTree, Inc." |
| Earthly Insight | Earthly Insight LLC | https://www.earthlyinsight.ai/terms-and-conditions (rendered by script; the text is in the site's JavaScript): "Welcome to Earthly Insight LLC! These Terms and Conditions ..."; the home page footer reads "© 2025 Earthy Insight LLC" |
| Viro | Viro LLC | https://www.viro.app/terms-conditions-viro-ai (last updated May 27, 2026): "owned by Viro LLC or its licensors". No "Viro Climate Action, Inc", which the page's Viro summary names, appears on viro.app ("Viro - Climate Action" is a page title); the summary is unchanged, a question for Brandon |

`dr entity-enrich <ref> --no-interactive` ran on all 10 (exit 0, 3 to 12 s each); every draft was discarded and the hand-written file kept. None set `founded`. Ecosia's site returned 403 to both seed fetches; for Ecosia AI the enricher still wrote a description and two paragraphs, saying Ecosia uses renewable energy for data centers, which no input said and which the page's "Conventional cloud hosting" contradicts; for the company it wrote nothing. The other drafts mixed site marketing stated as fact (Viro AI "clean-energy-powered"), notes about their own missing inputs ("The inputs do not provide specific details ..."), guesses ("likely reflects") and garbled text (Euria "itsExistingFoundedFounded in 2003background", Earthly Insight "AUCtively"). Verify: `dr lint` 0 errors, 10 new `unreferenced-entity` infos (12 to 22); `npm run build` passes; each of the 10 pages is in `dist/research/entities/<type>/<slug>/index.html`, each product page links its company, each company page links its product and shows its legal name; each page `entity:` ref names a file on disk (the S4 check resolves `entity` only when a cell cites a claim). Commit `184b77a`.

#### S15: first row backed by published claims
Renewable hosting (Q12). `dr onboard products/<slug> --only renewable-energy-hosting` per product (6, not TreadLightlyAI); Brandon approves each with `dr review --approve` (never `dr publish`, which records no reviewer and leaves the claim "Unreviewed"); cite in the cells.
Verify: `dr lint` reports no errors; build check passes; each cell shows the claim mark, and its popup and Evidence entry show verdict, confidence and as-of date matching the claim page, which shows "Reviewed and approved by".

#### S16: remaining claim rows, one at a time
Same as S15 for real-time energy display, image generation, published financials, data used for training, open-source models and ownership (company claims use `companies/<slug>` with `--only financial-transparency` or `--only corporate-structure`); the research-load table in this plan records progress.
Verify: as S15, per row; for ownership, each claim's title word matches the cell's `term`.

### Indexing (not part of SITE-J; kept for reference)

Claim, source and entity pages stay noindexed until after 1.0.0, on Brandon's call (`docs/decisions.md:19`). This page does not depend on either step.

#### S14: noindex for archived claim pages, by status
Production builds make pages only for `published` and `archived` claims (`src/pages/research/claims/[...slug].astro:20-32`), so drafts and blocked claims have none. `shouldNoindex` looks only at the path (`src/lib/seo.ts:46-48`), and the sitemap filter only at the URL (`astro.config.ts:32-36`). Before the flip, decide whether archived claim pages are indexed; if not, the claim page passes its status and the sitemap filter skips archived claims (read claim statuses from disk in `astro.config.ts`, since content collections are not available there).
Verify: unit tests on the status rule; with the flag set to true in a scratch build, an archived claim page has `noindex` and is absent from `sitemap-0.xml`, a published one is present. Reverted after.

#### S17: the indexing flip
Set `INDEX_ALPHA_DETAIL_PAGES` to true (`src/lib/seo.ts:23`) on the trigger Brandon picks after 1.0.0; update the flag comment (`:12-17`). Then the external SEO milestones (`docs/plans/seo-external.md`).
Verify: built claim, source and entity pages have no `noindex`; the sitemap lists published claim pages.

## Out of scope

- The chatbot guide proposal (`docs/plans/drafts/chatbot-guide-proposal.md`, local), including adding ChatGPT, Claude, Gemini, Copilot or Brave Browser to this page (their entities, and the Brave claim, exist but stay off it).
- Claims about TreadLightlyAI (Q1).
- New verdict labels, composite scores, rankings, or per-product counts of good cells.
- Importing the parallax-ai comparison data (`docs/UNSCHEDULED.md:228`); it is unsourced.
- Listing this page on source pages' "cited by" lists.
- Editing the matrix in Sveltia CMS (it lists only article layouts, `docs/architecture/site.md:201`).
- Pipeline changes beyond S11 and S12.
- Indexing (S14, S17).

## Questions for Brandon

None open.

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-06 | agent (claude-opus-5-5) | implementation | First draft, written against HEAD `a353ec0`: the page data, matrix components, `content.config.ts`, claim page, `seo.ts`, `astro.config.ts`, templates, linter checks, `cli.py`, CI and deploy workflows, `mission-and-voice.md`, `decisions.md`, AGENTS.md and the roadmap. |
| 2026-10-06 | agent (claude-opus-5-5), self-review | deep, iterated | Fresh-eyes pass. S3 moves the matrix schema to its own module, because tests cannot import `content.config.ts`; S2 forbids `astro:content` imports for the same reason. S1 notes `tsx --test` is unconfirmed. S7's link count is "at most 13". Width estimate in D1 marked as an estimate. Added the intended effect of the build check on claim corrections. Scope question about other chatbots became an out-of-scope line. |
| 2026-10-06 | agent (claude-opus-5-5), advisor review | implementation, iterated | Found three criteria under `inactive_templates`, so claims citing them fail `dr lint`; added S12 and corrected the research load and onboarding counts. |
| 2026-10-08 | agent (claude-opus-5-5) | implementation, iterated | Recorded Brandon's answers to Q1 to Q13 as Decisions. Rewrote the rows table (9 stance rows, 7 feature rows), the display (D1 plus an accessible popup, DR4), text-row stance (`match`, `term`), the TreadLightlyAI cap (`max_tier`), the data model, the build check and the research load (48 claims, 2 activations, 5 + 5 entities). Added F12 to F14. S14 and S17 left the checklist as reference notes (drafts no longer get production pages; flip after 1.0.0). Rechecked every file:line reference against HEAD `81591b3`. New questions P1 to P4. |
| 2026-10-08 | agent (claude-opus-5-5), self-review | deep, iterated | Fresh-eyes pass. Example data no longer implies a stance result for a real product (models `match`, hidden-text example). Q2's Decisions line states Brandon's answer and marks keyboard and touch as this plan's addition. S5 notes its models and ownership parts wait on P1 and P2. DR4 no longer claims `title` is the only hover help. Fixed two Values heading lines and the glossary range. Checked: checklist ids match step headings; no em dashes; no two lists share a prefix. |
| 2026-10-08 | agent (claude-opus-5-5), advisor review | deep, iterated | S14 and S17 have no checkbox, so the plan can close. The popup pins open when a hover-opened mark is clicked (and S6 tests it). The ownership check reads the vocabulary word from the claim title, which the pipeline already constrains. Text-row labels shortened to Brandon's words ("no large models", "non-profit"). P1 hedges its rationale, applies both glossary tests to every model, and names S18 for the archive-wide glossary change; P4 says it defines the answer only and offers a simpler alternative. |
| 2026-10-09 | agent (claude-opus-5-5), cross-review | deep, implementation, iterated | Folded P1 to P6 into Decisions. Models row: P5's top-tier rule replaces frontier-scale, so the row has no criterion and is sourced only (claims 48 to 42; S18 and the glossary change dropped); match is computed from a dated large-model list, never hand-set. Ownership: `terms` split the `corporate-structure` vocabulary (good, mixed `privately-held`, bad `publicly-traded`), `owned_by` with sources for P6's owner test; label "non-profit or similar". Accessibility answers limited to yes, partial, unknown (P4). Fixes: "Reviewed claim" needs a named reviewer, since `dr publish` sets `reviewed_at` with no reviewer; hash script opens the enclosing `<details>`; popup closes when focus leaves it, sits under the pill nav, has distinct link names; "not yet sourced" in legend and hidden text; S6 and S7 Verify steps made passable before claims exist; hedged links moved from S7 to S10; S11 option chosen; new build-check rules (no claims in rows without a criterion, missing cells, row answer sets); F15 to F17 (description, `collectFreshestDate` date bug, unused `planned`). Line refs rechecked at `4c427fe`. New questions R1 to R4. |
| 2026-10-09 | agent (claude-opus-5-5) | design, from mockup feedback | Brandon reviewed a mockup of the page (Claude design canvas). Changed: the row line and legend wording ("We prefer: Yes"; "Rows without a “We prefer” line compare facts only; we take no position on them.") and the hidden cell text to match; the popup link splits (a reviewed claim opens its claim page, a source jumps to its Evidence entry); marks get a 32px hit area; legend text and icons move up one size. The exact wording is the agent's; Brandon asked only that "the responsible answer" and "feature row" be replaced. |
| 2026-10-09 | agent (claude-opus-5-5) | design, from mockup feedback | Second mockup round. The reviewed-claim mark is a scale, not a check, because a check beside a Yes answer reads as two answers (Brandon). The "We prefer" line shows the preferred answer's icon in the good color instead of the word. The mockup gained a states sheet (each mark state, each popup kind) and a claim-icon comparison. |
| 2026-10-10 | agent (claude-opus-5-5) | implementation | S8a applied (A1 to A8; launch dates for Ecosia AI and Euria sourced, 5 left "Not yet sourced"; GPT-OSS's source left for S10; dark-theme stance red 4.68:1). S9 code: Values position ids from one list shared with the build check; copy left for Brandon. S11: the linter counts page-cited sources (18 warnings to 5). Status line brought up to date. |
| 2026-10-10 | agent (claude-opus-5-5) | implementation | S12: the two criteria activated (`open-source-models-only` worded per R4); checked in code that activation queues no claims and recorded its one effect beyond the page (criteria pages list every entity of the type). S13: 10 entities with legal names from each company's own pages; `dr entity-enrich` drafts discarded, reasons recorded. Rows table, research load, status line and stale `templates.yaml` references brought up to date. The archive-lookup finding from S8a is RF26 in `docs/UNSCHEDULED.md`. |
