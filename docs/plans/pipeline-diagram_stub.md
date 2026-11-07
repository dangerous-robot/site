# Pipeline diagram

**Status**: Implemented, awaiting Brandon's look at the rendered diagram (steps 1 to 4 done 2026-11-07)
**Last updated**: 2026-11-07
**Roadmap**: `docs/v1.0.0-roadmap.md` RE-G (Pipeline diagram), beta.10

A static diagram of how a claim gets from a question to a published verdict, placed in the methodology answer on `/research`. Brandon decided on 2026-11-03: RE-G stays on beta.10, drawn as inline SVG by hand. No Mermaid, no script.

## Placement

`src/pages/research/index.astro`: inside `<details id="methodology">` (`:185`), directly after the "How a claim is published" list (`<h3>` at `:193`, its `</ol>` at `:214`), before `<h3>Verdicts</h3>`.

## Nodes, top to bottom

Spine nodes are full width. Side steps are narrower, offset right, joined by an elbow line.

| # | Node | Kind | Label (role, then one line) | Checked against |
|---|---|---|---|---|
| N1 | Question | human | **Question**: a person names the claim and the product or subject it is about | `dr draft` modes, `docs/architecture/pipeline-commands.md:11` |
| N2 | Researcher | automated | **Researcher**: searches the web, and arXiv for academic topics | `pipeline/researcher/`; arXiv only when topics meet `ACADEMIC_TOPICS` (`pipeline/researcher/decomposed.py:82-89`) |
| N3 | Ingestor | automated | **Ingestor**: fetches and stores each source, from archive.org when the live page fails | `pipeline/ingestor/`; `docs/architecture/research-flow.md:62` |
| N3a | Stopped | side, muted | **Stopped**: fewer than 4 usable sources, or an agent failed after retries. Nothing is written | `MIN_USABLE_SOURCES = 4` (`pipeline/loop/run.py:45`); `BlockedReason` (`pipeline/common/models.py:111-116`); an abandoned Evaluator or tie-breaker also writes nothing (`pipeline-commands.md:75`) |
| N4 | Analyst | automated | **Analyst**: weighs the sources and drafts a verdict, confidence and summary | `pipeline/analyst/` |
| N5 | Evaluator | automated | **Evaluator**: grades the claim again from the same sources, without the draft's verdict | `pipeline/auditor/` (the site labels key `auditor` "Evaluator", `src/pages/research/claims/[...slug].astro:73-79`); bundle at `pipeline/loop/analyse.py:282-289` |
| N5a | Tie-breaker | side, automated | **Tie-breaker**: only when the two verdicts differ; a third blind grade settles it | `driver.step("tiebreak", ...)` (`run.py:447`); `settle_verdict` (`pipeline/auditor/compare.py:136`) |
| N6 | Human review | human | **Human review**: a person reads the draft and its sources and approves it | `dr review --approve` flips draft to published (`pipeline/orchestrator/cli.py`, `--approve` option at `:1965`) |
| N6a | Not approved | side, muted | **Not approved**: stays a draft for rework or a rerun (the list above says "leaves it as a draft for rework") | a draft left unapproved stays `draft`; `--archive` only retires a published claim |
| N7 | Published verdict | terminal | **Published verdict**: on the site with the reviewer's name | `status: published`; reviewer from `src/lib/reviewers.ts` |

Left off, on purpose:

- **Restater** (`driver.step("restate", ...)`, `run.py:478`): it never changes the claim (`AGENTS.md:124`); it writes candidate rewordings for the operator. One clause in the text alternative mentions it.
- **Rewriter** (RE-BM, Tie-broken claims get a matching narrative): not built yet. If RE-BM ships first, N5a's line gains "and the summary is rewritten to match".

## Color and style

All colors are CSS custom properties from `src/styles/tokens.css`, set through classes in the component's scoped `<style>`, not SVG presentation attributes. Light, dark and both high-contrast themes (`[data-contrast="high"]` at `tokens.css:146`, light at `:182`) then follow with no extra rules.

| Kind | Style |
|---|---|
| human (N1, N6) | stroke `--color-accent`, 2px; a small "Person" tag in the node, so the meaning does not rest on color alone |
| automated (N2-N5, N5a) | stroke `--color-border`, fill `--color-surface`, text `--color-text` |
| side, muted (N3a, N6a) | dashed stroke `--color-border`, text `--color-text-muted` |
| terminal (N7) | stroke `--color-text-heading`, 2px |
| lines and arrowheads | `--color-text-muted` |
| text | `font-family: var(--font-body)` |

Add a `@media (forced-colors: active)` rule mapping strokes and text to `CanvasText`, so Windows contrast themes keep the boxes.

## Where the SVG lives

`src/components/PipelineDiagram.astro`, no props, imported once in `index.astro`. Reasons: the page is 619 lines, and the diagram brings its own scoped styles. No SVG diagram component exists yet (the `<svg>` files in `src/components/` are icons).

## Accessibility

- `<figure class="pipeline-diagram">` around `<svg role="img" aria-labelledby="pipeline-diagram-title" aria-describedby="pipeline-diagram-desc">`. Naming the image by both ids made Chromium's accessible name the title plus the whole description (checked 2026-11-07); with `aria-describedby` the name is the title and the description is separate.
- `<title id="pipeline-diagram-title">`: "How a claim moves from a question to a published verdict".
- `<desc id="pipeline-diagram-desc">`: the full flow in order, including N3a, N5a, N6a and one clause on the restater. It is the text alternative, because the list above the diagram has four steps and no stopped or tie-breaker branch.
- No information only in the picture: every label is real `<text>`, not a path.

## Responsive rule

- `viewBox` about 320 units wide; `width: 100%; height: auto; max-width: 28rem`.
- Text at least 12 units, so at a 320px viewport (288px after the 16px gutters) no label renders below about 11px. SVG text does not wrap, so labels are broken by hand with `<tspan>`, at most about 34 characters per line.
- The page must not scroll sideways at 320px.

## Test plan

| ID | Check | Pass |
|---|---|---|
| V1 | `inv check` | green |
| V2 | Screenshots of the opened methodology answer at 375px wide: dark, light, high contrast dark, high contrast light | every node legible; human nodes in the accent color; dashed side steps visible in all four |
| V3 | At 320px: `document.documentElement.scrollWidth <= document.documentElement.clientWidth` | true |
| V4 | Accessibility tree (devtools snapshot) | one `img` named by the title, with the description |
| V5 | `forced-colors` emulation | boxes and lines visible |
| V6 | Built page has no new `<script>` or external request | `dist/research/index.html` diff shows the SVG and styles only |

Phone width needs the Chrome DevTools MCP (`emulate` or `resize_page`); the headless Chrome command-line fallback has a minimum width near 500px. Switch themes with the page's accessibility control or by setting `data-theme` and `data-contrast` on `<html>` (`src/layouts/Base.astro:75`).

## Steps

- [x] 1. Register the work item (`release-triage` skill)
- [x] 2. `src/components/PipelineDiagram.astro`: nodes N1-N7 with side steps, classes per the style table, `<title>` and `<desc>`
- [x] 3. Import and place it after `</ol>` at `index.astro:214`
- [x] 4. V1-V6 (2026-11-07; screenshots under `handoff/re-g-screenshots/`, gitignored; V3's page-level test fails for a reason outside the diagram: the nav toggle and explainer cards already overflow a 320px viewport with the figure hidden, filed in `UNSCHEDULED.md` § Site gaps; the figure itself is 284px wide at 320px)
- [ ] 5. Roadmap RE-G: status and commit ref; drop `_stub` from this file's name (and fix the roadmap link) once the plan is reviewed; the rename must update the path in `pipeline/tests/test_run_rules.py:677` (it reads this file by name) in the same commit

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §6 |
| 2026-10-06 | agent (claude-opus-5-5, plan review) | rewrite | Lifted the design spec from the local draft `v0.1.0-mvp-definition.md` §6; replaced the Router/Orchestrator/Evaluator flow with the agents in `pipeline/`; placement moved from the old FAQ page to `/research#methodology`. Still a stub. |
| 2026-11-03 | agent (claude-opus-5-5, plan writer) | implementation, iterated | Rewritten as a checklist plan on Brandon's 2026-11-03 decisions (beta.10, hand-drawn inline SVG); every node checked against the code; placement moved to `index.astro:186`; open questions removed; restater left off the spine; component, accessibility, responsive and test rules added. |
| 2026-11-07 | agent (claude-fable-5-1, implementer) | implementation | Built as planned. Changes while building: `aria-describedby` for the description (see Accessibility); N6a wording matched to the list above; the stale copy note removed (RE-D fixed the list and the JSON-LD on 2026-11-07). |
