# Phase 0: foundation

**Status**: `in progress` (phase 0 implemented, deploy checks open; phase 0.1 pull-forwards added 2026-10-03, not started; see both Status checklists)
**Last updated**: 2026-10-03
**Source of truth**: the discovery records in the Google Drive folder "Dangerous Robot — Vision & Discovery" (Decisions Log; "07 — Early Roadmap"). Every copy string those records decided is reproduced here verbatim, so this plan can be implemented without reading them.

Phase 0 is the first release that reflects the 2026-10-01 to 2026-10-03 discovery decisions. It is copy and trust work on the repo as it stands: no new content type, no schema change beyond two optional fields, no URL change, no redirect. It ships quietly (no announcement). The chatbot guide and the public relaunch are phase 1, which is planned separately when it opens.

## Status checklist

Ticked as items land (AGENTS.md rule 4). Item ids are the Scope table ids below.

- [x] A1 to A5, A7: copy items (title tag, meta description, tagline, north star, footer, brand spelling)
- [x] A6: "sponsored by" retired in `src/` and `README.md`
- [x] A8: README intro and GitHub repository description set (description confirmed via `gh repo view`, 2026-10-03)
- [x] B1 to B5: `/about`, `/corrections`, issue form (`config.yml` blocks blank issues), contact alias on About, `corrections` field on claims
- [x] B6: runbook "Corrections" note done; interaction limits set to `existing_users`, expires 2027-04-03 (renew before then)
- [x] B3 labels: `correction` and `source-submission` labels created
- [x] C1 to C5: reviewer display, verdict badge link, verdict statement, `<details>` auto-open, signed Values page
- [x] D1, D2: `ai_assisted` field and byline wording
- [x] D3: set on `why-dangerous-robot-exists`; pledge post settled by Brandon 2026-10-03 (no `ai_assisted` field; the post is untracked and `draft: true`)
- [x] E1 to E3: disclosure sentence, corrections link, product note kept
- [x] F1, F2: roadmap section 9, `architecture/site.md`, `runbook.md`
- [x] F3: `docs/discovery/` deleted (Brandon, 2026-10-03); AGENTS.md "Discovery records" points to the Drive folder
- [x] `src/lib/seo.ts`: no change needed, the alpha-noindex patterns do not match `/about` or `/corrections` (checked in code; `dist/` check pending)
- [ ] Verification checklist: items 2 to 12 verified against `dist/`; 13 and 14 need a deploy
- [x] Needs from Brandon, item 1: `contact@dangerousrobot.org` alias created (Brandon, 2026-10-03)
- [ ] Needs from Brandon, items 4 and 5: review the two draft About paragraphs; confirm `main` is pushed and deployed

## Goal

After this plan lands, the site says what the discovery records decided it says (tagline, title, descriptions, footer), names the person who reviews every claim, has an About page and a Corrections page, states what a verdict is where every verdict label links, and carries the decided conflict-of-interest wording wherever TreadLightlyAI appears. Nothing the homepage redesign (commit `c004d3e`) or the writing section (commit `5f460ff`) built is removed.

## Facts the plan relies on

- The homepage (`src/pages/index.astro`) is the two-dangers layout with a "Where to start" menu, two placed claim cards, a trust section and a colophon. It already dropped the "transparency index" line and the "AI Transparency Research" title, and its claim cards already use the seven-label verdict vocabulary. It renders with `chrome="minimal"`, so the site nav is not drawn there; the footer from `Base.astro` is.
- `src/layouts/Base.astro` renders `<title>{title} - Dangerous Robot</title>` (line 91), a default `description` that still reads "structured research hub ... Built for journalists, researchers, and policy teams." (line 28), the nav sections `Research` and `Resources` (lines 41 to 68), and a footer whose first paragraph is "Dangerous Robot is a research project sponsored by TreadLightly AI" (line 346) followed by Values · Methodology · Credits and GitHub · CC-BY-4.0 · version.
- The methodology section is `<details id="methodology">` on `src/pages/research/index.astro` (line 216); the footer already links to `/research#methodology`. There is no `/methodology` page and none is added.
- Claim pages (`src/pages/research/claims/[...slug].astro`) show a `<VerdictBadge>` in the meta row (line 133), a "✓ Reviewed" state when `audit.human_review.reviewer` is set (lines 91, 136 to 138), and in the audit trail "Reviewed {date} by {reviewer}" printing the raw reviewer value (line 224). The reviewer value today is an email address. Nothing in the pipeline data changes in this plan; the display maps the value to a name.
- The writing collection (`src/content.config.ts`, line 425) has `author` defaulting to `Brandon Faloona` and no field for AI assistance. The Sveltia config (`public/admin/config.yml`) mirrors the schema. `/writing/[...slug].astro` prints author and dates.
- `src/content/resources/responsible-ai.md` lists TreadLightlyAI in its matrix and ends with `<p class="resource-matrix__disclosure">FULL DISCLOSURE: Dangerous Robot is sponsored by TreadLightlyAI.</p>` (line 286); its intro offers `mailto:info@dangerousrobot.org` for errors (line 284).
- `src/pages/research/index.astro` spells the brand "TreadLightly AI" in the conflicts FAQ (lines 82, 365 to 366). The decided spelling everywhere is "TreadLightlyAI", one word.
- TreadLightlyAI is not a research product entity (`research/entities/products/` has brave-browser, chatgpt, claude, gemini, greenpt). It stays out in phase 0.
- `.github/ISSUE_TEMPLATE/` has `submit-source.md` only. GitHub Pages serves the site; redirects are meta-refresh pages, not 301s.
- The live site on 2026-10-03 still showed the pre-redesign homepage, so `main` either is not pushed or has not deployed. Phase 0 ships with the redesign.

## Decided copy (verbatim; do not reword)

| Key | Text |
|---|---|
| Tagline | Act while the choice is still yours. |
| North star | The biggest decisions about AI are being made by a few people, without you. Act while the choice is still yours. |
| Homepage title tag | Dangerous Robot - A guide to AI's dangers, with evidence you can check |
| Meta description (homepage, and the `Base.astro` default) | A guide to AI's dangers, with evidence you can check: what AI does to you and to everyone, what its makers say they cannot control, and what you can do about it. |
| Project description (GitHub repo "About", README intro) | A guide to AI's dangers for people deciding whether to trust AI with something that matters. Evidence you can check, a named person behind every claim, and what you can do about it. |
| Footer method line | Built with the help of AI. Every claim has a source, and a person who stands behind it. |
| Footer maker line | A community project from the maker of TreadLightlyAI. |
| About, "Who runs this" | Dangerous Robot is run by one person, Brandon Faloona, who reviews and approves every claim on it. He also makes TreadLightlyAI, an AI chatbot. TreadLightlyAI appears on this site under the same criteria and sources as every other product, and the site publishes no verdict on claims about it. |
| Positioning statement (About, "What this site is") | For people deciding whether to trust AI with something that matters, Dangerous Robot is a guide to the danger, with evidence you can check. It shows the source and the person behind every claim, and says what you can do about it. |
| What the site does not do (About) | Not a news site. Not a thought-leadership or policy shop. Not a fact-checking organization, though its research record carries verdicts. Not a position organization; one page states what it advocates. No verdict on claims about TreadLightlyAI. Does not state the size, likelihood or timing of existential risk as settled. Does not rank the two risk axes. Does not claim AI-free production. |
| Disclosure sentence (above any list or comparison that includes TreadLightlyAI) | TreadLightlyAI is made by the same person who makes Dangerous Robot. It is listed under the same criteria and sources as every other product, and we publish no verdict on claims about it. |
| Verdict statement (methodology section) | A verdict is our reading of the public record as of the date shown. AI agents draft it; the person named on the claim approves it. Every source is listed, and you can check them. One person reviews everything today. If we are wrong, tell us here. |
| Reviewer line (claim pages) | Reviewed and approved by Brandon Faloona |
| Byline (posts, AI drafted the text) | Written by Brandon Faloona, with AI assistance |
| Byline (posts, no AI drafting) | Written by Brandon Faloona |

In the verdict statement, "tell us here" links to `/corrections`. In the footer maker line, "TreadLightlyAI" links to `https://treadlightly.ai`. The reviewer line links to `/about#who-runs-this`.

Two About sections have no decided wording and need copy. Drafts below follow the records' content; Brandon reviews them before merge (they are editorial copy in his name).

- "Where it stands" (draft): Dangerous Robot holds that AI carries some existential risk, because the people building these systems say so on the record. How large that risk is, how likely, and when, this site does not state as settled. The full position is on the Values page.
- "How it is made" (draft): Dangerous Robot is built with the help of AI. Agents search for sources and draft each verdict. Brandon Faloona reviews and approves every claim before it is published. Every source is listed, and you can check them. The pipeline and the models it uses are described in the methodology section.

Copy rules for anything else written under this plan: plain words, no em dashes, no stacked fragments, not alarmist. Spell out "general superintelligence" (never "GSI"). Incidents are "unauthorized access", never "felony". "TreadLightlyAI" is one word.

## Scope

### A. Site-wide copy

| ID | Item | Files |
|---|---|---|
| A1 | Homepage title tag is exactly the decided string. `Base.astro` appends " - Dangerous Robot" to every title, which would put the name last; add an opt-in prop (for example `titleIsFull: boolean`) so a page can supply the whole `<title>`. Use it only on the homepage. `og:title` for the homepage: "Dangerous Robot: Act while the choice is still yours." (the tagline on social cards). | `src/layouts/Base.astro` (lines 26 to 36, 91, 105 to 113), `src/pages/index.astro` (line 204) |
| A2 | Meta description: the homepage `pageDescription` (index.astro line 184) and the `websiteSchema.description` (line 192) become the decided meta description. The `Base.astro` default description (line 28) becomes the same string, so pages without their own description stop describing a research hub for journalists. | `src/pages/index.astro`, `src/layouts/Base.astro` |
| A3 | Tagline under the name on the homepage: below the wordmark (`.hero-title`) and above the hero line "The tools arrived before the lessons.", add the tagline as a short line. Keep the hero line. Inner pages are unchanged (the nav stays as it is by decision). | `src/pages/index.astro` (hero, lines 232 to 250) |
| A4 | North star closes the trust section: replace the `trust__quote` text "Trust should be earned. Right now it is being decided for you." (line 310) with the north star's two sentences. Keep the trust title and the `trust__text` line. | `src/pages/index.astro` |
| A5 | Footer: replace the sponsor paragraph (line 346) with two lines, the method line and the maker line (TreadLightlyAI linked). Add `About` as the first link in the Values · Methodology · Credits row. The homepage colophon is removed: the footer, drawn on the homepage too, already carries the method line (changed 2026-10-03, after the colophon duplicated it). | `src/layouts/Base.astro`, `src/pages/index.astro` |
| A6 | "Sponsored by" retires everywhere. `rg -n "sponsor" src/ README.md` and remove every reader-facing "sponsored by" phrasing. The research FAQ's "No verdict is paid, sponsored, or commissioned." is a different sense and stays. | `src/`, `README.md` |
| A7 | Brand spelling: "TreadLightly AI" becomes "TreadLightlyAI" in reader-facing copy (`src/pages/research/index.astro` lines 82 and 365 to 366, and anything else `rg -n "TreadLightly AI" src/` finds). In the conflicts FAQ, replace the first paragraph with the second and third sentences of "Who runs this" (third person) and link "About" to `/about#who-runs-this`; keep the rest of the answer. | `src/pages/research/index.astro` |
| A8 | Project description: GitHub repository description (`gh repo edit dangerous-robot/site --description "..."`) and the README's opening paragraph. | `README.md`, repo settings |

### B. About and Corrections

| ID | Item | Files |
|---|---|---|
| B1 | New page `/about` with these sections in this order, each with a stable id: `#who-runs-this` (decided copy), `#what-this-site-is` (the positioning statement), `#what-this-site-does-not-do` (the list, as a list), `#where-it-stands` (draft copy above; links to `/values`), `#how-it-is-made` (draft copy above; links to `/research#methodology`), `#corrections` (one line linking to `/corrections`), `#contact` (the legal and safety alias, see B4). `layout="reading"`, breadcrumb Home › About, title "About". | `src/pages/about.astro` (new) |
| B2 | New page `/corrections`. Copy: a short page that says corrections go through a GitHub issue form asking for the page or claim URL, what is wrong, and a link to the evidence; that reports are reviewed by Brandon Faloona; that when a claim changes, the claim page shows "Corrected [date]: what changed" and keeps the prior verdict visible; that the full history is in the public repository; and that filing needs a GitHub account. No response window is stated. Link the form with the `template=correction.yml` query so the form opens directly. | `src/pages/corrections.astro` (new) |
| B3 | GitHub issue form for corrections: `.github/ISSUE_TEMPLATE/correction.yml` with required fields `Page or claim URL` (input), `What is wrong` (textarea), `Evidence` (input, a link), label `correction`, title prefix `[Correction] `. Add `.github/ISSUE_TEMPLATE/config.yml` with `blank_issues_enabled: false` if blank issues are not wanted (operator call). | `.github/ISSUE_TEMPLATE/correction.yml` (new), optionally `config.yml` |
| B4 | Contact path for legal and safety matters: a domain email alias (operator creates it; see "Needs from Brandon"), shown on About under `#contact` as the only non-public path, scoped to legal and safety matters, with corrections pointed at the form. Do not publish any other address. | `src/pages/about.astro` |
| B5 | Correction note on claim pages: add an optional `corrections` array to the claims schema (`date`, `summary`, `previous_verdict`), rendered under the meta row as "Corrected {date}: {summary}" with "Previous verdict: {label}". No claim carries one yet; the field is optional so nothing else changes. | `src/content.config.ts` (claims schema), `src/pages/research/claims/[...slug].astro` |
| B6 | Interaction limits on the repo are an operator setting, not code (`gh api -X PUT repos/dangerous-robot/site/interaction-limits -f limit=existing_users -f expiry=six_months`, or the repo's Moderation settings). They expire (one day to six months) and must be renewed. Note this in the runbook under a new "Corrections" heading. | `docs/runbook.md`, repo settings |

### C. Claim pages and the methodology section

| ID | Item | Files |
|---|---|---|
| C1 | Reviewer display: add `src/lib/reviewers.ts` mapping the raw `audit.human_review.reviewer` value (an email address; read the exact value from an existing `research/claims/**/*.audit.yaml`) to `{ name: "Brandon Faloona", href: "/about#who-runs-this" }`. On the claim page, the "✓ Reviewed" span (lines 136 to 138) becomes the reviewer line "Reviewed and approved by Brandon Faloona" with the name linked; the audit-trail paragraph (line 224) prints the mapped name, never the raw value. An unmapped value prints "Reviewed" with no name (do not leak an address). "Unreviewed" stays for claims with no reviewer. | `src/lib/reviewers.ts` (new), `src/pages/research/claims/[...slug].astro` |
| C2 | Verdict labels link to the verdict statement: on the claim detail page only, wrap the `<VerdictBadge>` in `<a href="/research#methodology">` (or add an `href` prop to the component). List rows (`ClaimRow.astro`) and homepage cards already sit inside a link to the claim; leave them unlinked to avoid nested anchors. | `src/pages/research/claims/[...slug].astro`, `src/components/VerdictBadge.astro` |
| C3 | Verdict statement at the top of the methodology section: insert it as the first paragraph inside the `#methodology` answer div, before "How a claim is published", with "tell us here" linking to `/corrections`. | `src/pages/research/index.astro` (line 216 onward) |
| C4 | A `<details>` targeted by a fragment does not open on its own. Add a small script to the research hub page: on load and on `hashchange`, if `location.hash` names a `details` element, set `open`. Readers arriving from a verdict label then see the statement. | `src/pages/research/index.astro` |
| C5 | Values page signed: a closing line "Brandon Faloona" linked to `/about#who-runs-this`. | `src/pages/values.astro` |

### D. Writing bylines

| ID | Item | Files |
|---|---|---|
| D1 | Add `ai_assisted: z.boolean().default(false)` to the `writing` schema and a matching boolean field (label "AI assisted", hint "On when AI drafted the text") to the Sveltia config. | `src/content.config.ts`, `public/admin/config.yml` |
| D2 | Post pages print "Written by {author}, with AI assistance" when the flag is on and "Written by {author}" otherwise, in place of the bare author in the byline. Guest authors keep their own names. | `src/pages/writing/[...slug].astro`, `src/pages/writing/index.astro` if it shows bylines |
| D3 | Set the flag on the existing posts (operator call; see "Needs from Brandon"). | `src/content/writing/*.md` |

### E. Responsible AI matrix

| ID | Item | Files |
|---|---|---|
| E1 | Replace the disclosure paragraph text (line 286) with the decided disclosure sentence; keep the `resource-matrix__disclosure` class. Move the paragraph so it renders directly above the matrix, if it does not already. | `src/content/resources/responsible-ai.md`, `src/components/ResponsibleAIMatrix.astro` if placement needs it |
| E2 | Replace the `mailto:info@dangerousrobot.org` in the intro (line 284) with a link to `/corrections`. | `src/content/resources/responsible-ai.md` |
| E3 | The product note "Beta product from same founder as Dangerous Robot." (line 60) may stay; it is consistent with the disclosure. | none |

### F. Roadmap and docs

| ID | Item | Files |
|---|---|---|
| F1 | Add a section to the active release roadmap: "9. Phase 0: foundation (discovery decisions)", status `in progress`, linking to this plan, and tick items here as they land (AGENTS.md rule 4). | `docs/v1.1.0-roadmap.md` |
| F2 | `docs/architecture/site.md`: update the Layout structure note ("footer: TreadLightly AI attribution") and the route table with `/about` and `/corrections`. `docs/runbook.md`: add "Corrections" (B6) and the byline flag (D1). | `docs/architecture/site.md`, `docs/runbook.md` |
| F3 | `docs/discovery/` in the repo holds three orphan files from before the records moved to Drive. Replace them with a one-line `README.md` pointing at the Drive folder, or delete them (operator call). | `docs/discovery/` |

## Needs from Brandon

1. The legal and safety alias address on the domain (decided: `contact@dangerousrobot.org`), created and forwarding where he chooses, before B4 ships. Until it exists, build About without the `#contact` section and add it when the address is known.
2. Whether the GitHub repository should refuse blank issues (B3 `config.yml`).
3. The `ai_assisted` value for each existing post (D3).
4. Review of the two draft About paragraphs ("Where it stands", "How it is made") before merge.
5. Confirmation that `main` is pushed and deployed, since the live site still showed the old homepage on 2026-10-03.
6. Create the `correction` and `source-submission` issue labels on the repo (commands in `docs/runbook.md` "Corrections").

## Implementation notes

- Do the copy items (A) first and build; they are one commit and carry no risk. Then About and Corrections (B), then claim pages (C), then the small schema additions (B5, D1), then the matrix (E) and docs (F).
- Keep every change inside the decided wording. Where this plan gives no copy (page intros, link text), write the minimum and keep it plain. Do not add a caveat sentence beside verdicts on claim pages or guides; the methodology link is the only caveat by decision.
- `rg` is the check for leftovers: `rg -n "sponsored by|TreadLightly AI|transparency index|journalists, researchers" src/ README.md` should return nothing reader-facing when done.
- The reviewer mapping (C1) is deliberately display-side. Changing the sidecar schema or rewriting audit files is pipeline work and belongs to phase 1.
- Nested anchors (C2): check the rendered claim page HTML for `<a>` inside `<a>` after the change.
- `src/lib/seo.ts` decides which paths are noindexed as alpha detail pages; make sure `/about` and `/corrections` are indexable and appear in the sitemap.
- No URL changes in this plan, so no redirects.

## Out of scope (phase 1 and later; decided elsewhere, do not start here)

- The scope field, the guides type restructure and its format values, the actions type (the pledge moving out of writing), lifecycle status on claims, the claim submission form.
- TreadLightlyAI as a research product entity and the "no verdict published" claim state.
- Showing one strength label only (hiding the verification label), the source-mix line, per-source retrieval status and archived copies, the confidence ceiling. These are decided in the trust record but scheduled with the pipeline work.
- Any change to the site nav (`Base.astro` sections), the "Where to start" menu, or the nav question (scopes in the nav).
- Renaming the resources section or the writing directory.
- The pipeline source-acquisition work (Tier 1 remainder).

## Verification checklist

1. `inv check` (build, lint, citations) passes.
2. Rendered `/index.html`: `<title>` is exactly "Dangerous Robot - A guide to AI's dangers, with evidence you can check"; `<meta name="description">` is exactly the decided meta; the tagline appears under the wordmark; the hero line "The tools arrived before the lessons." is still present; the trust section ends with the north star's two sentences; the method line appears once, in the footer.
3. A page without its own description (for example `/research/claims/`) carries the decided meta as its description.
4. Every page's footer shows the method line, the maker line with "TreadLightlyAI" linked to https://treadlightly.ai, and an About link. `rg -n "sponsored by" src/ README.md` returns nothing reader-facing.
5. `rg -n "TreadLightly AI" src/` returns nothing.
6. `/about` renders the seven sections with the ids listed in B1 and the decided copy verbatim; `/corrections` renders and its form link opens the correction issue form on GitHub with the three required fields.
7. A published claim page shows "Reviewed and approved by Brandon Faloona" linked to `/about#who-runs-this`; `rg -o "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}" dist/research/claims -g "*.html"` finds no email address (run it on `dist/about` first as a positive control; a bare `@` matches JSON-LD `@context`).
8. On a claim page the verdict badge links to `/research#methodology`; following it opens the methodology details and the verdict statement is its first paragraph, with "tell us here" linking to `/corrections`. No `<a>` nests inside another `<a>` on claim pages.
9. A post with `ai_assisted: true` shows "Written by Brandon Faloona, with AI assistance"; one without shows "Written by Brandon Faloona". The Sveltia admin shows the new field.
10. `/resources/responsible-ai` shows the decided disclosure sentence above the matrix and no mailto.
11. `/values` ends with the signed line linked to About.
12. `/about` and `/corrections` are in `dist/sitemap-0.xml` and not noindexed.
13. The GitHub repository description matches the decided project description.
14. After deploy, the live homepage matches item 2.

## Phase 0.1: pull-forwards (added 2026-10-03)

Phase 0 ships as checked above; the deploy gate does not move. Phase 0.1 is a second checklist in the same plan, run after the phase 0 deploy, for work that became worth doing once there was more time. Each item either needs no decision beyond the records (G, H, I1, I2, I4, J, K) or carries its decision in "Needs from Brandon, phase 0.1" below (I3). Nothing here uses phase 1 vocabulary: no scope field, no guides rename, no actions type, no lifecycle status, no nav relabel. The rules in "Decided copy" and "Implementation notes" apply.

### Status checklist, phase 0.1

- [ ] G1, G2: pledge post finished and on the homepage
- [ ] H1 to H5: research record hygiene
- [ ] I1, I2, I4: one navigation source, About in the top row, docs synced
- [ ] I3: claimless entities (after the operator call below)
- [ ] J1: indexing trigger rewritten
- [ ] K1: `resources` collection in the CMS (articles only)
- [ ] Verification checklist, phase 0.1
- [ ] Needs from Brandon, phase 0.1: items 1 to 5

### G. Pledge on the homepage

The content record (05) puts the pledge on the homepage after the lead guide; the early roadmap record (07) says the pledge "joins as it exists". The post exists at `src/content/writing/pledge-prohibit-ai-self-improvement-pledge.md` (`draft: true`, author Wade Hudson, no `ai_assisted` field by Brandon's decision). Its URL stays `/writing/pledge-prohibit-ai-self-improvement-pledge`; the move to an actions URL, with a redirect, is phase 1.

| ID | Item | Files |
|---|---|---|
| G1 | Finish the post: the editor's note ends "add yourself as a signatory to the pledge at ..." with no destination; link the signatory form (URL in "Needs from Brandon, phase 0.1", item 1) and set `draft: false`. Keep the guest author. Write the minimum: the note's existing sentences plus the link. | `src/content/writing/pledge-prohibit-ai-self-improvement-pledge.md` |
| G2 | Homepage: add the pledge to the `menu` array as the eighth entry, after Values: `label` "Sign the pledge", `short` "Pledge", `note` one plain sentence naming what the pledge asks for (legislation prohibiting AI systems from improving their own capabilities without human control). The link target is the post, unless item 1 says the form directly. No new homepage section in phase 0.1: the menu is the one place the homepage lists destinations, and a new block is the kind of ad hoc layout change AGENTS.md "UI & Design Standards" asks us to check first. | `src/pages/index.astro` |

### H. Research record hygiene

Reader-facing defects in the research record found on 2026-10-03. None changes a verdict, so `as_of` dates stay.

| ID | Item | Files |
|---|---|---|
| H1 | `brave-browser/renewable-energy-hosting` is published and tagged `highlight`, and three fields are cut off mid-word: `takeaway` ends "was found, let .", `seo_title` is "Brave Browser Hosting Not on Renewable, S!" (it is the page `<title>`), `cap_rationale` ends "independent v." Rewrite each by hand from the claim body and its sources, plain words, each a complete sentence; `seo_title` at most 42 characters. Sources and verdict unchanged. | `research/claims/brave-browser/renewable-energy-hosting.md` |
| H2 | Research hub copy that contradicts About: the FAQ "What is this site?" opens "Dangerous Robot is a structured research project" and says every claim "aspires to be reviewed and approved by a human operator"; the Limits list says "Operators approve." Rewrite the first answer to open with the positioning statement's second sentence ("Dangerous Robot is a guide to the danger, with evidence you can check."), say the research record is the evidence behind it, link `/about`, and state that Brandon Faloona reviews and approves every published claim. In Limits, "Operators approve. Human reviewers can be wrong." becomes "One person approves, and can be wrong." Keep everything else in the FAQ. | `src/pages/research/index.astro` |
| H3 | The `ai-model-producers` subject entity's `description` and body are generated filler ("landscape", "leading the charge", "sharper focus") on a public page. Replace both with three plain sentences: what the term covers (companies that train and release large AI models), the examples the site uses it for (the six named in the FLI index claim), and that claims under this subject are about the group, not one company. Keep `aliases` and `search_hints`. | `research/entities/subjects/ai-model-producers.md` |
| H4 | `research/v1-launch-set.md` lists 27 claims, including `brave-leo/*`, that are not on disk (disk: 3 published, 2 draft). Delete it (`git rm`). The phase 1 plan writes its own research-load tracker (products times criteria). Check for links first: `rg -n "v1-launch-set" docs/ research/ AGENTS.md README.md` and fix any that remain. | `research/v1-launch-set.md`, any file that links it |
| H5 | Nine empty, untracked directories under `research/claims/` (anthropic, brave-software, chatgpt, claude, gemini, google, greenpt, openai, treadlightlyai). Remove them: `find research/claims -type d -empty -delete`. No commit results. | local filesystem only |

Noted, not an item: the two draft `subjects/us-data-centers` claims carry `verdict: unverified` with `confidence: high` and `medium`. Drafts do not render in production; the pairing is a pipeline question for phase 1's gates.

### I. Navigation: one source, no relabels

Three lists disagree today: `Base.astro` (`TOP_LINKS`: Research, Resources, Writing; `SECTIONS` with Values under Research), the homepage `menu` (seven entries whose `short` labels are meant to match the sections), and the footer (About, Values, Methodology, Credits). The phase 1 nav decision (Guides, Claims, Act, About; scopes once two have a guide) is not made here; no label or URL changes except adding About.

| ID | Item | Files |
|---|---|---|
| I1 | New `src/lib/nav.ts` exporting `TOP_LINKS`, `SECTIONS`, and `FOOTER_LINKS`. `Base.astro` imports all three and renders the footer links from `FOOTER_LINKS` (today they are literal anchors). `index.astro` keeps its editorial `menu` array (labels and notes are editorial) but takes each entry's `short` label from `nav.ts` by `href`, so the hamburger and the site nav cannot drift. | `src/lib/nav.ts` (new), `src/layouts/Base.astro`, `src/pages/index.astro` |
| I2 | About joins `TOP_LINKS` as the last entry (Research, Resources, Writing, About). Values leaves the Research sub-nav; it stays in the footer and the homepage menu. Whether Values also joins the top row is item 3 in "Needs from Brandon, phase 0.1"; default is footer and menu only. | `src/lib/nav.ts` |
| I3 | Claimless entities. Six companies and four of five products have no published claims, and Companies and Products are sub-nav links. Option A (default): `/research/companies` and `/research/products` list only entities with at least one published claim; detail URLs stay and render as they do today. Option B: drop Companies and Products from the Research sub-nav until the guide's claims exist; list pages unchanged. Item 2 in "Needs from Brandon, phase 0.1" picks. Either way `/research/entities/[...slug]` is untouched. | `src/pages/research/companies/index.astro`, `src/pages/research/products/index.astro`, or `src/lib/nav.ts` |
| I4 | Docs that lag the code: roadmap §3 says RSS autodiscovery "is not emitted yet" and "Writing ... is not in the site-wide nav"; `architecture/site.md` says the same in the Homepage and Writing sections. `Base.astro` emits the `<link rel="alternate">` (line 108) and lists Writing in `TOP_LINKS`. Fix both docs, then update `architecture/site.md` Layout and Structure for `nav.ts`, the About link, and I3's outcome. | `docs/v1.1.0-roadmap.md`, `docs/architecture/site.md` |

### J. Indexing trigger

| ID | Item | Files |
|---|---|---|
| J1 | `src/lib/seo.ts` keeps `INDEX_ALPHA_DETAIL_PAGES = false` (decided 2026-10-03: claim, source and entity pages stay noindexed for now). Its comment names the flip trigger as "GA (the 1.0.0 release)", which no longer describes anything: `VERSION.md` is `1.1.0-alpha.1` and `docs/v1.0.0-roadmap.md` never moved to `completed/`. Rewrite the comment: the flag flips when the first guide ("Before you trust an AI chatbot", phase 1) is live and its claims are published, by a decision recorded in the phase 1 plan. Add the same sentence to roadmap §9. Keep the flag name and the patterns. | `src/lib/seo.ts`, `docs/v1.1.0-roadmap.md` |

### K. CMS: editorial articles

| ID | Item | Files |
|---|---|---|
| K1 | Add a second Sveltia collection, `resources`, for `layout: article` entries only, so plain guides and explainers can be written in the admin. Mirror `src/content.config.ts`: `title` (string), `description` (string, maxlength 200, same hint as writing), `pubDate` (date, UTC), `layout` (hidden, default `article`), `wallpaper` (select: default, ai-safety, responsible-ai, none), `topics` (select, multiple, min 1 max 3: ai-literacy, ai-safety, consumer-guide, responsible-ai), `noindex` (boolean, default false), `further_reading` (list of title, url, publisher optional, last_checked optional date), `body` (markdown). Omit `data`. Set `filter: { field: layout, value: article }` so the matrix, guide and tool entries do not open in the admin; their `data` payloads are not editable there. Media folder: `public/images/resources` (create it with a `.gitkeep`). Add "Resources" to the runbook's "Writing posts" section. Production login stays the roadmap §3 follow-up; it is not duplicated here. | `public/admin/config.yml`, `public/images/resources/.gitkeep` (new), `docs/runbook.md` |

### Needs from Brandon, phase 0.1

1. The pledge signatory form's URL, and whether the homepage menu entry links to the post (default) or to the form directly.
2. Claimless entities (I3): option A, hide them from the Companies and Products lists (default), or option B, drop the two sub-nav links.
3. Values: footer and homepage menu only (default), or also in the nav top row.
4. Whether 1.0.0 shipped. If it did, `git mv docs/v1.0.0-roadmap.md docs/plans/completed/` and reword `VERSION.md`'s "Pre-release stages (toward 1.0.0)" to the current release; if it did not, say so in `VERSION.md` so the version string and the stage notes agree.
5. Confirm H4 (delete `research/v1-launch-set.md` now) rather than keep it until the phase 1 tracker exists.

### Verification checklist, phase 0.1

15. `inv check` passes.
16. `/writing/pledge-prohibit-ai-self-improvement-pledge` renders in a production build (not a draft), the editor's note links to the form, and the homepage "Where to start" list and hamburger both show the pledge entry with its label and short label.
17. The `brave-browser/renewable-energy-hosting` page shows a complete takeaway, a `<title>` that is a complete phrase, and a complete cap rationale; `rg -n "let \.|, S!|independent v\." research/claims` returns nothing.
18. `/research`: the first FAQ answer links `/about` and names Brandon Faloona as the reviewer; `rg -n "structured research project|aspires to be|Operators approve" src/` returns nothing.
19. `/research/entities/subjects/ai-model-producers` shows the rewritten description; `rg -n "landscape|leading the charge|sharper focus" research/entities` returns nothing.
20. `research/v1-launch-set.md` is gone and `rg -n "v1-launch-set" docs/ research/ AGENTS.md README.md` returns nothing; `find research/claims -type d -empty` returns nothing.
21. Every standard-chrome page's top row reads Research, Resources, Writing, About; Values is not under Research; the footer links come from `nav.ts`; each homepage hamburger label equals the `nav.ts` label for the same `href`.
22. I3's chosen option is in effect: either the Companies and Products lists show only entities with published claims, or the two sub-nav links are gone. Entity detail URLs still resolve.
23. `src/lib/seo.ts`'s comment and roadmap §9 name the first guide as the indexing trigger; `rg -n "1\.0\.0" src/lib/seo.ts` returns nothing.
24. The admin at `http://localhost:4321/admin/index.html` lists Writing and Resources; Resources opens `ai-safety` and does not list `responsible-ai`, `should-i` or `turn-off-ai`; a test article saved from the admin passes the build, then is deleted.
25. Roadmap §3 and `architecture/site.md` no longer say RSS autodiscovery is missing or that Writing is outside the site nav.

## Cross-references

- Discovery records (Drive): "07 — Early Roadmap" (phase 0 decisions and the phase 1 proposals), "06 — Messaging" (copy), "04 — Trust & Transparency Model" (reviewer, corrections, disclosure placement), "05 — Content Model & Structure" (homepage order, amended for phase 0 by 07), Decisions Log (newest first).
- `docs/v1.1.0-roadmap.md` §2 (homepage redesign) and §3 (writing section) for what this plan builds on.
- `docs/plans/public-participation-forms.md` for the later submission form (out of scope here).

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-03 | agent (claude-fable-5-1, Cowork session with Brandon) | implementation, iterated | Written from the discovery records after reading `Base.astro`, `index.astro`, `claims/[...slug].astro`, `research/index.astro`, `content.config.ts`, `public/admin/config.yml`, `responsible-ai.md`, `v1.1.0-roadmap.md`, `architecture/site.md`. Line numbers are as of 2026-10-03. Decisions and scope confirmed by Brandon in the Area 7 session; the two draft About paragraphs await his review. |
| 2026-10-03 | agent (claude-fable-5-1, Cowork session with Brandon) | implementation, iterated | Added "Phase 0.1: pull-forwards" (sections G to K, their checklist, needs list and verification items 15 to 25) after reading `Base.astro`, `index.astro`, `seo.ts`, `content.config.ts`, `public/admin/config.yml`, `research/index.astro`, the five claim files, `templates.yaml`, `v1-launch-set.md` and the Drive record "07 — Early Roadmap". Phase 0 scope and gate unchanged. Decisions by Brandon the same day: pledge signatory form is the homepage addition; claim pages stay noindexed with a new trigger; pull-forwards tracked in this file. |
