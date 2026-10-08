# Decisions

Settled product decisions for dangerousrobot.org, newest first. Plans in `docs/plans/` implement them and quote the wording they need. This repo is public: keep money, people and other private matters out of this file.

Decisions made before 2026-10-04 (mission, audience, positioning, trust model, content model, messaging, early roadmap) are in the private Drive discovery records and their Decisions Log, frozen on 2026-10-04 as history. The last Drive entries cover the version reset and the About and Values revision.

## 2026-10-07

- **Plain tagline.** The homepage tagline is a plain statement for a first-time visitor: "A guide to AI's dangers, and what you can do about it." The social title follows it. "Convenience runs on reliance and pays out in compliance." stays in `mission-and-voice.md` for use elsewhere. *(Final)*
- **About names the operator in full.** About says "Brandon Faloona (brandon-f)", the handle linking the profile; other reviewer mentions keep the handle alone. *(Final)*
- **Beta banner on research only.** The release-stage banner shows on `/research` pages only. *(Final)*
- **Review copy names no one.** Sentences about who reviews claims or correction reports say a person reviews, without naming one, so they hold when a second reviewer joins. The handle and profile link stay on each claim's reviewer line. *(Final)*
- **Reviewer named by handle.** Pages that name the claim reviewer show the reviewer's handle (`brandon-f`), linked to `/people/<handle>`, which carries the full name, bio and reviewed claims. The Values signature keeps the full name. *(Final)*
- **Indexing after 1.0.0.** Claim, source and entity pages stay noindexed until after 1.0.0; Brandon decides the trigger then. This replaces the 2026-10-06 line that left the trigger to the SITE-J plan. *(Final)*
- **No ClaimReview markup.** Claim pages stop emitting ClaimReview JSON-LD: Google dropped its fact-check rich results in 2025. Verdicts stay in the claim files, so it can return. *(Final)*
- **Archive links in code.** The pipeline looks up each new source's archive.org link in code after ingest, not through the ingest model, and a `dr` command backfills existing sources. *(Final)*
- **Priorities ranked.** The order in [`priorities.md`](priorities.md) is confirmed. Each later change to the order gets one line here. *(Final)*

## 2026-10-06

- **Next large effort: Responsible AI chatbots, backed by claims.** Enhance the Responsible AI Chatbots page so its comparisons are supported by claims and sources where possible (roadmap §10; no plan yet). This replaces the chatbot guide ("Before you trust an AI chatbot") as the next release; the guide and its Drive proposals become an undecided proposal (a local draft). The noindex flip trigger, which was the first guide, is decided in the §10 plan. *(Final)*
- **Footer adds Privacy.** The footer's row of links is About, Values, Methodology, Privacy, CC-BY-4.0. `/privacy` says what the site keeps from petition signers, who can read it, how long it is kept, and how to be removed; the sign form's note links to it. This amends the 2026-10-05 shorter footer. *(Final)*
- **Decided copy.** The copy strings below are the record; plans and `docs/mission-and-voice.md` quote them. Most were decided in the Drive discovery records (2026-10-01 to 2026-10-03) and first written down in [`plans/completed/refocus-foundation.md`](plans/completed/refocus-foundation.md); rows changed since then say so. Do not reword them without a new entry here. *(Final)*

| Key | Text |
|---|---|
| Tagline | A guide to AI's dangers, and what you can do about it. (2026-10-07; was "Convenience runs on reliance and pays out in compliance.") |
| Hero line | The algorithm got your attention. The robot wants the wheel. (2026-10-05; one sentence per line) |
| North star (closes the homepage trust section) | The biggest decisions about AI are being made by a few people, without you. Act while the choice is still yours. |
| Homepage title tag | Dangerous Robot - A guide to AI's dangers, with evidence you can check |
| Homepage social title | Dangerous Robot: A guide to AI's dangers, and what you can do about it. (follows the tagline) |
| Meta description (homepage, and the default for pages without their own) | A guide to AI's dangers, with evidence you can check: what AI does to you and to everyone, what its makers say they cannot control, and what you can do about it. |
| Project description (GitHub repository "About", README intro) | A guide to AI's dangers for people deciding whether to trust AI with something that matters. Evidence you can check, a named person behind every claim, and what you can do about it. |
| Footer maker line | A community project from the maker of TreadLightlyAI. ("TreadLightlyAI" links to https://treadlightly.ai) |
| Positioning statement (source copy; not quoted on About since 2026-10-04) | For people deciding whether to trust AI with something that matters, Dangerous Robot is a guide to the danger, with evidence you can check. It shows the source and the person behind every claim, and says what you can do about it. |
| Disclosure sentence (above any list or comparison that includes TreadLightlyAI) | TreadLightlyAI is made by the same person who makes Dangerous Robot. It is listed under the same criteria and sources as every other product, and we publish no verdict on claims about it. |
| Verdict statement (first paragraph of the methodology section) | A verdict is our reading of the public record as of the date shown. AI agents draft it; the person named on the claim approves it. Every source is listed, and you can check them. One person reviews everything today. If we are wrong, tell us here. ("tell us here" links to `/corrections`) |
| Reviewer line (claim pages) | Reviewed and approved by brandon-f (the handle links to `/people/brandon-f`) (2026-10-07; was "Reviewed and approved by Brandon Faloona") |
| Byline (posts, AI drafted the text) | Written by Brandon Faloona, with AI assistance |
| Byline (posts, no AI drafting) | Written by Brandon Faloona |

Retired: the footer method line "Built with the help of AI. Every claim has a source, and a person who stands behind it." (left the footer 2026-10-05). Copy rules: plain words, no em dashes, not alarmist; "TreadLightlyAI" is one word; "general superintelligence", never "GSI"; incidents are "unauthorized access", never "felony".

## 2026-10-05

- **Homepage copy.** Tagline: "Convenience runs on reliance and pays out in compliance." Hero line: "The algorithm got your attention. The robot wants the wheel." (one sentence per line). The north star in the trust section is unchanged. *(Final)*
- **Actions type, pulled forward.** Petitions are an `actions` content collection served at `/petitions/{slug}`, ahead of the chatbot guide release that first scheduled the type. The pledge moved from `/writing/pledge-prohibit-ai-self-improvement-pledge` (which redirects) to `/petitions/prohibit-ai-self-improvement`, and petition fields left the `writing` schema. *(Final)*
- **Homepage spotlight.** A band between the hero and "Where to start" features one entry: the newest writing post, petition or resource with "Feature on homepage" switched on, shown with its description (a petition shows its statement, count and sign button). The pledge leaves the menu. This reverses the beta.4 rule that the menu is the only place the homepage lists destinations. *(Final)*
- **Shorter footer.** The footer keeps the maker line and one row of links: About, Values, Methodology, CC-BY-4.0. The method line ("Built with the help of AI. Every claim has a source, and a person who stands behind it.") leaves the footer; About's "How it is made" covers the same ground. Credits, GitHub and the version move to a "The project" section on About. *(Final)*
- **Three destinations out of the primary nav and homepage menu** until they are reworked: Research ("Company claims, checked"), Turn off AI, and Should I use AI. The pages stay published; Research keeps its sub-nav on its own pages, and the footer still links Methodology. *(Final)*

## 2026-10-04

- **Planning lives in the repo.** New product decisions are recorded here; plans and the roadmap stay in `docs/`. The Drive discovery records and Decisions Log are frozen as history and no longer edited. The discovery handoff in the claude.ai project is retired. *(Final)*
- **Pledge signatures are collected on the site.** A Cloudflare Worker and D1 database (the stack `docs/plans/deferred/public-feedback.md` chose) take name and email, confirm by email, and show a signer's name publicly only if they opt in. Only Brandon receives the signer list. No hosted form in the meantime: the pledge post and its homepage menu entry wait for the Worker, and beta.4 waits with them. Plan: [`docs/plans/completed/petition-signatures.md`](plans/completed/petition-signatures.md). *(Final)*
- **beta.4 scope.** Companies and Products list only entities with at least one published claim (detail pages stay); Values stays in the footer and homepage menu, not the top nav; `research/v1-launch-set.md` is deleted. Details in `docs/plans/completed/refocus-foundation.md`. *(Final)*
