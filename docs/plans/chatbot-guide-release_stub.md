# The chatbot guide release ("Before you trust an AI chatbot")

**Status**: Stub. Not implementation-ready: it lists the inputs and the decisions the full plan must make.
**Last updated**: 2026-10-06
**Roadmap**: [`v1.0.0-roadmap.md`](../v1.0.0-roadmap.md) §10

The release after `1.0.0-beta.4`: the first guide, "Before you trust an AI chatbot", with the claims it cites published, and the soft public launch (still beta). The refocus plan ([`completed/refocus-foundation.md`](completed/refocus-foundation.md)) deferred several items to this release; they are collected here so the full plan can be written without re-reading it.

## What the records already say

| Source | Content |
|---|---|
| [`docs/mission-and-voice.md`](../mission-and-voice.md) "How the site works on that" | Guides are the primary content. A guide cites claims where claims exist and sources otherwise, and says what you can do. No composite score or ranking. Every source links to an archived copy where one exists. |
| `src/lib/seo.ts` (flip-trigger comment), roadmap §9 | `INDEX_ALPHA_DETAIL_PAGES` flips when the first guide is live and its claims are published, by a decision recorded in this plan. |
| refocus plan, "Out of scope" | The scope field; the guides type restructure and its format values; lifecycle status on claims; the claim submission form; TreadLightlyAI as a research product entity and the "no verdict published" claim state; showing one strength label only (hiding the verification label), the source-mix line, per-source retrieval status and archived copies, the confidence ceiling; nav changes, the "Where to start" menu and scopes in the nav; renaming the resources section or the writing directory. (The actions type is no longer on this list: it shipped 2026-10-05, `docs/decisions.md`.) |
| refocus plan, Implementation notes (C1) | Reviewer data in the audit sidecar schema, or rewriting audit files, is pipeline work for this release; beta.3 mapped the reviewer on the display side only. |
| refocus plan, H4 | This plan writes its own research-load tracker: products times criteria. |
| refocus plan, H (note) | A gate for draft claims that pair `verdict: unverified` with `confidence: high` or `medium` (the `subjects/us-data-centers` drafts). |
| refocus plan, I | The nav decision: Guides, Claims, Act, About; scopes once two have a guide. |
| [`docs/UNSCHEDULED.md`](../UNSCHEDULED.md) "Deferred content (unsourced)" | Chatbot comparison data exists in parallax-ai but is unsourced; each cell needs a source file before use. |
| Drive "07 — Early Roadmap" (frozen, private) | The original proposals for this release. History only. |

## Prerequisites (from the 2026-10-06 plan review)

- Refreshing a published claim keeps its review and leaves a trail: [`published-claim-refresh-trail.md`](published-claim-refresh-trail.md) (RF8, RF9 in `docs/UNSCHEDULED.md`).
- RF11: archive lookups that get HTTP 429 are recorded as failures and retried, and each source the guide cites has an `archived_url` (one-time backfill).
- Dedup remainder: arXiv abs/html/pdf pages counted as one source, and the stored-redirect-target case in RF23.
- External SEO for the guide ([`seo-external.md`](seo-external.md)): after the indexing flip, the validation milestone, sitemap resubmission and indexing requests. The Fact Check program stays gated.
- The indexing flip decision itself.

## Decisions the full plan must make

- Q1: Guide format: a content type (and its fields and URL), or a `resources` article.
- Q2: The claim set: which products and criteria the guide cites, and the research-load tracker that follows them.
- Q3: Which items from the "Out of scope" list ship here and which wait.
- Q4: The nav: whether Guides, Claims, Act, About replaces today's top row in this release.
- Q5: When to flip indexing, and what "its claims are published" means (all cited claims reviewed, or a minimum).
- Q6: What the soft public launch includes (announcement or none).

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-06 | agent (claude-opus-5-5, plan review with Brandon) | basic | Stub written from the refocus plan, roadmap, `seo.ts`, `mission-and-voice.md`, `decisions.md` and `UNSCHEDULED.md`. Lists inputs and open decisions only; nothing here is decided. |
