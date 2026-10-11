# Plan: `dr claim-restate` (claim restatement proposals)

**Status**: design reviewed by the operator 2026-10-10; all questions answered. Not started. The us-data-centers worked example is on disk, untracked (RISK-4).
**Last updated**: 2026-10-10
**Serves**: RE-AC (Claim restatement) in `docs/v1.0.0-roadmap.md` (beta.8), theme 1, Responsible AI chatbots (`docs/priorities.md`, proposed on the theme's `Work:` line, operator to confirm).
**Line numbers** are as of HEAD `0b3d0a9`. Paths are repo-relative; `pipeline/` is omitted where obvious.
**Register** code work with `python3 scripts/release-gate/work_item.py start --title "RE-AC (Claim restatement)" --kind minor --release v1.0.0 --plan docs/plans/claim-restate.md` (AGENTS.md § Agent workflow tooling); one checkout holds one active item, so SITE-J's record must be finished first and re-registered by that line of work when it resumes.

## Goal

In the operator's words, the plan prioritizes "a) reusing existing sources (what can i already prove), and b) given the shape of the research data what's the best phrasing of the claim that highlights the problem (technology having a negative impact on our world) in a verifiable way."

An unverified claim is one whose sources circle the assertion without settling it (`docs/architecture/glossary.md:49`); often the pool on disk already settles a nearby statement. `dr claim-restate` reads one unverified claim plus the whole local source pool and proposes ranked restatements, each with the verdict the existing evidence would give it and the passages that give it; the operator picks the framing and acts with existing commands. The command does no web research, never rewrites the claim text, and writes nothing unless `--write` is given, which records the proposal in the claim's audit sidecar. `--write --accept N` turns the chosen candidate into a criterion in `research/templates.yaml` so the operator can onboard it as a template-backed claim with the existing commands.

Today there are five unverified claims: four `renewable-energy-hosting` claims (`chatgptree`, `earthly-insight`, `viro-ai`, `brave-browser`), three of which are cells on the Responsible AI chatbots page where an Unverified claim renders as "unknown" (D25, D26 in `docs/plans/responsible-ai-chatbots-claims.md`), and the subject claim `subjects/us-data-centers/there-are-fewer-than-10-...` (draft, analyst `unverified`, auditor `true`).

## Status checklist

- [ ] S1: retrieval module
- [ ] S2: models, instructions, agent, evaluate, report
- [ ] S3: the command
- [ ] S4: sidecar write, carry-over, closure
- [ ] S5: `--accept` writes the criterion
- [ ] S6: `restates` sidecar key
- [ ] S7: acceptance fixture and live test
- [ ] S8: docs and the operator runbook
- [ ] S9: run on the five worked examples and record the operator's picks

## Decisions

D1 to D10 and D13 to D17 are settled. D11 and D12 are content decisions pending from the operator; their answer changes S9 and `research/templates.yaml`, not the command.

- D1: the deliverable is a new `dr claim-restate` command plus a new agent, not a procedure.
- D2: the worked examples are the us-data-centers claim plus every other `verdict: unverified` claim (five today).
- D3: the source pool is the whole `research/sources/` pool, not only the claim's cited sources. No web research in v1.
- D4: polarity guard. The agent ranks candidates by how decisively the evidence settles them, in either direction; it is never given a thesis to prove. The operator chooses the framing. The sidecar records the original text and the reasons for restating.
- D5: input is a claim on disk with `verdict: unverified`; any other verdict is refused. `mixed` claims are out of scope in v1.
- D6: read-only by default; `--write` records the proposal in the `.audit.yaml` sidecar; the claim `.md` is never rewritten by this command.
- D7: the agent runs on the Evaluator's model slot (`--restater-model`, falling back to `--auditor-model`, then `--model`); `AGENT_NAMES` and `VerifyConfig` are not extended (see "The agent", Model tier).
- D8: nothing is rendered on the site in v1; the public trail is the new claim, the archived original and the `corrections` entry.
- D9: one `restatement` block per sidecar; `--write` replaces any earlier block; history lives in git (see RISK-2).
- D10: the `why_unverified` enum has five values: `quantifier-unsupported`, `term-mismatch`, `upstream-provider`, `entity-silent` (the recurring reasons R1 to R4 found in the evidence sweep) and `other` (see "Generalization").
- D11 (pending from the operator, content not design), wrapper products and the browser. For Earthly Insight, Viro and ChatGPTree (on third-party models) and for Brave (a browser), should `renewable-energy-hosting` resolve to `not-applicable` with the question moved to the provider entity, or be restated at product level? This also picks the template direction. Options: T1, keep "PRODUCT is hosted on renewable energy" and add to `notes` that a product on third-party models gets `not-applicable` with a pointer to the provider, and that "matched" or "purchased" renewable energy without facility supply evidence is `mostly-true` at most (GreenPT and Euria get re-read, likely hold or drop to `mostly-true`; the four unverified claims become `not-applicable` or stay unverified; nothing new to show readers); T2, a new controlled-vocabulary template "PRODUCT's renewable energy claim rests on MECHANISM" with the vocabulary on-site generation / direct supply contract / matched certificates or PPAs / offsets only / none stated, verdict `true` when a source names the mechanism, as with `corporate-structure` (GreenPT and Euria read "direct supply contract" or "matched", ChatGPTree "offsets only", Viro "matched", Brave and Earthly Insight "none stated"; the vocabulary does the work and the operator never picks a thesis; overlaps `discloses-energy-sourcing` for "none stated", so that template may fold in); T3, per-entity ad hoc claims (C1, C2, A1, A2 as one-offs; lint blocks publishing without `criteria_slug`; right fit only for the subject claim and the Evertreen finding). Recommendation: T2 for the template row, T3 for A1, A2 and C2; it is the one option that gives every product a checkable, non-polar fact. Decide before S9; the command itself is unchanged by the answer.
- D12 (pending from the operator, content not design), ChatGPTree. The template note says "mixed = offsets only"; the glossary says sources must engage. Options: (a) re-verdict to `mixed` by hand now (no restatement; the template-notes defect row covers the cause); (b) keep it `unverified` and in scope for S9. Recommendation: (b) for S9, since it is unverified on disk today and C1 is the clearest offsets-versus-supply example; re-verdict after.
- D13: `dr claim-restate --write --accept N` writes the chosen candidate as a criterion in `research/templates.yaml` (S5). It reuses the writer `dr claim-promote` has, factored out of that command; the entry is `core: false`, scoped to the original claim's entity type (and, for a subject, to that subject), and its `notes` name the claim it was restated from. The sidecar records the acceptance; the command prints the `dr onboard --only` command and does not run the pipeline. Template authorship stays a human act: the operator picks the candidate, and the text written is the candidate text with the entity name replaced by the placeholder, nothing more.
- D14: the agent never proposes a claim on a different entity. A candidate's `rationale` may name the upstream provider (OpenAI, AWS, Evertreen); the operator drafts there by hand. `RestatementCandidate` has no target-entity field.
- D15: a title-only change on `dr claim-refresh` does not require a `--correction` at approval in v1 (a follow-up in `docs/UNSCHEDULED.md`). Outcome B therefore leaves no public trail when only the title changes.
- D16: no lint rule in v1. A proposal with no action is visible in the sidecar and in the report; a `restatement-pending` rule is a follow-up in `docs/UNSCHEDULED.md`.
- D17: a new claim records which claim it replaces in its audit sidecar only, as a top-level `restates: <entity-dir>/<claim-slug>` key, not in its frontmatter. Operator data, not rendered, no `src/` change. The site schema is untouched by this plan.

## What the evidence sweep found

Hand sweep of the five claims against the whole pool (112 source files, 2016 to 2026), no network, no model. Source ids are paths under `research/sources/` without `.md`; `source:line` numbers refer to the source file.

Summary:

- Only one claim can be settled by evidence on disk in a way that still names the problem: the US data centers claim, restated as the published renewable share (A1).
- The four template claims fail for one structural reason: the entity never addresses hosting (Brave, ChatGPTree, Earthly Insight) or describes "clean energy" as procurement matched to an estimate (Viro). Restatement there yields "what the entity says and does not say" claims: true, capped at low confidence, and overlapping the `discloses-energy-sourcing` template.
- Three of the four product entities are wrappers over other companies' models (ChatGPTree on GPT-4; Earthly Insight and Viro on ChatGPT, Gemini, Claude). The hosting question belongs to OpenAI, Google and Anthropic, none of which have energy sources in the pool.
- Four of five sidecars show the auditor returning `true` with reasoning that rates the narrative, not the claim; they were written before RE-AD (Evaluator grades the claim) and keep that pattern until refreshed. The agent must not read `auditor_verdict: true` in such a sidecar as support for the original text.
- Off-entity sources sit in four of the five pools (GreenPT pages in ChatGPTree's, a 2016 Google page in Brave's and Earthly Insight's, OVHcloud in Viro's) and inflate `verification_level`.

### Claim A: US data centers, "fewer than 10 certified to run on 50%+ renewable"

File: `research/claims/subjects/us-data-centers/there-are-fewer-than-10-us-data-centers-that-are-certified-to-run-on-50-or-greater-renewable-energy-power-sources.md` (draft, no `criteria_slug`, subject entity). Analyst `unverified`/medium; auditor `true`/medium; `verdict_agrees: false`. The claim and its sidecar are on disk, untracked (`git status` shows `?? research/claims/subjects/us-data-centers/`); the entity file `research/entities/subjects/us-data-centers.md` is untracked too. S7 snapshots them into `pipeline/tests/fixtures/restate/us-data-centers/` so the acceptance test does not depend on the untracked files (RISK-4).

Why unverified: no source counts facilities (R1); "certified to run on" has no referent in the pool, where the certifications are building schemes (BREEAM, Green Globes) and the operators' word is "matched" (`2026/ironmountain-sustainability:12`, `2026/energy:17`) (R2); nobody has enumerated US data centers by energy mix, the EIA survey only began in 2024 (R1).

Sources: cited `2026/energy`, `2026/efficiency`, `2026/ironmountain-sustainability`, `2026/renewable-energy-for-data-centers`, `2026/datacenters`, `2021/data-center-sustainability-beyond-ppas`, `2026/clean-energy-resources-meet-data-center-electricity-demand`, `2026/sustainability`; uncited and carrying `2025/what-we-know-about-energy-use-at-us-data-centers-amid-the-ai-boom` (Pew citing IEA: natural gas over 40%, renewables about 24% of US data center electricity in 2024, lines 16-17), `2024/the-us-government-to-ask-data-centers-how-much-power-they-use`, `2026/ai-data-centers-us-electric-grid`, `2026/powering-us-data-centers-clean-energy-health-climate`, `2026/tracking-the-transition-to-renewable-energy-in-the-data-center-industry`, `2026/ai-data-centers-nevada-clean-energy-47d1b6633ed720962848f4b5b91e7d6b`, `2023/google-va-impact-reportpdf`; topic-only `2025/colt-dcs-sustainability-report-reveals-90-renewable-energy` (not US), `2026/data-center-power-play-report-finalpdf`, `2026/powering-data-centers-with-clean-energy`. Under a loose reading of "certified" (any operator claim of 100% matched renewable), Google and Iron Mountain alone put the count well above 10, so the loose reading leans `false`; under the strict reading no certification keyed to a renewable share exists in the pool.

| Rank | Candidate text | Expected verdict / confidence | Level | Carrying sources | Speaks to the problem? | New research? |
|---|---|---|---|---|---|---|
| A1 | Renewable sources supplied about a quarter of the electricity used by US data centers in 2024; natural gas supplied more than 40%. | `true` / medium (one independent source restating IEA; a second with the breakdown would lift it to high) | independently-verified | `2025/what-we-know-about-energy-use-at-us-data-centers-amid-the-ai-boom`; context `2026/clean-energy-resources-meet-data-center-electricity-demand`, `2026/ai-data-centers-us-electric-grid` | Yes: most data center power is fossil | No |
| A2 | Until 2024 the US government had no mandatory survey of how much electricity data centers use. | `true` / medium (WIRED alone for the survey; Belfer and UCS corroborate the opacity) | multiply-verified | `2024/the-us-government-to-ask-data-centers-how-much-power-they-use`; `2026/ai-data-centers-us-electric-grid`; `2026/powering-us-data-centers-clean-energy-health-climate` | Yes: nobody could have counted | No |
| A3 | Google, Microsoft and Iron Mountain describe their data center renewable energy as matched or purchased, and set their 24/7 carbon-free or zero-carbon targets for 2030 or later. | `true` / medium | partially-verified | `2026/energy`; `2026/efficiency`; `2026/ironmountain-sustainability`; `2023/google-va-impact-reportpdf`; `2026/renewable-energy-for-data-centers` (what "matched" means) | Yes: "100% renewable" rests on certificates and contracts | No |
| A4 | At least one US data center operator, Switch in Nevada, is reported to run entirely on renewable energy. | `true` / low to medium (two outlets likely restating Switch) | multiply-verified on paper, likely self-reported after the restatement test | `2026/ai-data-centers-nevada-clean-energy-47d1b6633ed720962848f4b5b91e7d6b`; `2026/tracking-the-transition-to-renewable-energy-in-the-data-center-industry` | No, neutral; shows the agent surfaces the positive case too | No |
| A0 | Original | stays `unverified` | n/a | none | n/a | Yes: a registry (EPA Green Power Partnership, Energy Star certified data centers, Green Web Foundation dataset) |

A1 and A2 are ad hoc claims on a subject entity (no template applies). `dr lint` requires `criteria_slug` on published claims (`published-without-criterion`, severity `error`, `pipeline/linter/checks.py:99-128`), so a restated subject claim needs a template entry before it can leave draft; `--accept` writes it (S5, D13).

### Claim B: Brave Browser is hosted on renewable energy

File: `research/claims/brave-browser/renewable-energy-hosting.md` (published, self-reported, low, `cap_rationale` set). Analyst `unverified`/low; auditor `true`/low; reviewed 2026-10-04 with no override.

Why unverified: no Brave document mentions energy and the pool is first-party only (R4); a browser runs on the reader's device, so "hosted" applies only to Brave's backend services (Sync, Search, Leo), and the one provider fact (AWS) comes from a community forum post (R3).

Sources: cited `2026/631793` (Brave Community: "Brave and Amazon (who host the servers) just store the scrambled data", lines 17-18), `2026/building-brave`, `2026/browser`, `2026/transparency`, `2026/soc2`, `2026/brave-browser-home`, `2016/announcement-100` (Google 2017 renewable match, off-entity), `2026/clean-energy-resources-meet-data-center-electricity-demand` (sector context, off-entity); uncited product pages `2026/faq`, `2026/6`, `2025/brave-website-challenge`, `2021/unstoppable-domains` (nothing on energy); uncited `2026/tracking-the-transition-to-renewable-energy-in-the-data-center-industry` (AWS aims to run entirely on renewable energy between 2025 and 2030, lines 14-15; "once fully transitioned", lines 20-21).

| Rank | Candidate text | Expected verdict / confidence | Level | Carrying sources | Speaks to the problem? | New research? |
|---|---|---|---|---|---|---|
| B1 | Brave's transparency report and privacy policy state where the electricity for Brave's servers comes from. | `false` / low (first-party pool; the two documents are on disk in full and cover usage, creators, token purchases and data handling, nothing on energy) | self-reported | `2026/transparency`; `2026/browser`; `2026/soc2` | Weakly: a disclosure gap, stated as a refuted affirmative because the candidate-form rule forbids "neither says". Overlaps the unused `discloses-energy-sourcing` template, which may be the cleaner move | No |
| B2 | Brave Sync stores user data on Amazon Web Services. | `true` / low (one forum post, kind blog, independence unknown) | claimed | `2026/631793` | No, neutral; a step toward a provider-level claim | No |
| B3 | Brave's Sync service runs on AWS, which has not reached 100% renewable energy. | `mixed` at best | partially-verified | `2026/631793`; `2026/tracking-the-transition-to-renewable-energy-in-the-data-center-industry` | Yes, not settleable today | Yes: AWS's current energy mix |
| B0 | Original | stays `unverified`; arguably `not-applicable` for a browser (D11) | n/a | none | n/a | Yes: AWS sustainability report; Brave posts naming regions and providers |

### Claim C: ChatGPTree is hosted on renewable energy

File: `research/claims/chatgptree/renewable-energy-hosting.md` (published, independently-verified, medium). Analyst `unverified`/medium; auditor `true`/high; reviewed 2026-10-10 with no override.

Why unverified: the entity's only environmental mechanism is offsets, and the template note "mixed = offsets only" (`research/templates.yaml`, `renewable-energy-hosting` notes) was not applied because the analyst prompt never sees template notes (R2, D12); inference runs on GPT-4, so the hosting question is OpenAI's (R3); two GreenPT pages kept for sq3 ("explicit details about hosting on renewable energy", `scorer_rationale`) are about a competitor and inflate `verification_level` to independently-verified (R5).

Sources: cited `2025/eco-friendly-chatgptree-sustainable-ai-chatbot` ("powered by GPT-4", summary line 9; trees via Evertreen and Veritree, body line 17), `2025/rooted-in-founders-belief-that-tech-can-do-good-chatgptree-is-an-ai-tool-with-a-regenerative-focus` (GeekWire, lines 9-10), `2026/building-regenerative-ai-with-chatgptree`, `2026/the-invisible-footprint-of-a-thought`, `2026/greenpt-privacy-first-ai-with-measured-energy-and-carbon` and `2026/greenpt-vs-chatgpt` (off-entity); uncited `2025/chatgptree-terms-of-use` (nothing on hosting), `2025/evertreen-non-transparent-tree-planting-and-dodgy-carbon-offs` (REDD-Monitor: 3,129,364 trees absorbing 3,025,356 tons, satellite data "not publicly available", Evertreen "reserves the absolute right ... to reallocate", `key_quotes`).

| Rank | Candidate text | Expected verdict / confidence | Level | Carrying sources | Speaks to the problem? | New research? |
|---|---|---|---|---|---|---|
| C1 | ChatGPTree addresses its AI's carbon footprint by planting trees through Evertreen and Veritree, one per subscriber per month, rather than by running on renewable power. | `true` / medium (first-party pages plus GeekWire) | independently-verified (GreenPT pages dropped) | `2025/eco-friendly-chatgptree-sustainable-ai-chatbot`; `2025/rooted-in-founders-belief-that-tech-can-do-good-chatgptree-is-an-ai-tool-with-a-regenerative-focus`; `2026/building-regenerative-ai-with-chatgptree` | Yes: offsets instead of supply, the greenwashing risk Uptime flags (`2026/renewable-energy-for-data-centers:13-14`). The "rather than" clause is an absence; cut after "per month" for a strictly positive form | No |
| C2 | ChatGPTree's offsets run through Evertreen, whose tree-planting claims an independent investigation found to rest on satellite data that is not public and on terms that let Evertreen reallocate contributions to other projects. | `true` / medium (one independent investigation quoting Evertreen's own figures) | independently-verified | `2025/evertreen-non-transparent-tree-planting-and-dodgy-carbon-offs`; `2025/eco-friendly-chatgptree-sustainable-ai-chatbot` (the partnership) | Yes: offset quality. Cleanest as a claim on a new `companies/evertreen` entity, which the operator drafts by hand (D14) | No |
| C3 | ChatGPTree runs on OpenAI's GPT-4. | `true` / low | claimed | `2025/eco-friendly-chatgptree-sustainable-ai-chatbot`; `2025/rooted-in-founders-belief-that-tech-can-do-good-chatgptree-is-an-ai-tool-with-a-regenerative-focus` | No, neutral; relocates the hosting question to OpenAI | No |
| C0 | Original | re-verdict to `mixed` per the template note, or stay `unverified` per the glossary (D12) | n/a | none | n/a | Yes: OpenAI or Azure energy disclosures for inference |

### Claim D: Earthly Insight is hosted on renewable energy

File: `research/claims/earthly-insight/renewable-energy-hosting.md` (published, independently-verified, high). Analyst and auditor both `unverified`/high; the only claim with agreement.

Why unverified: answers come from OpenAI, Google and Anthropic models, so "hosted" points at their data centers (R3); the entity is silent on hosting in the pool (R4); topic-circling sources (Green Web Foundation, Krystal, Google 2016) raise `verification_level` and `confidence` without engaging (R5). The narrative says the Green Web Foundation pages "do not list Earthly Insight as a verified green host"; neither GWF file lists any host, so that is an inference from an index page, not something a source states (R7). `research.entity_exclude_dropped` records a LinkedIn post scored 5 for sq1 ("generating more renewable energy than their AI features use from 100% clean sources like solar and wind", `scorer_rationale`): the one first-party renewable statement never entered the pool.

Sources: cited `2025/introducing-earthly-insight-more-conscious-143500454html` (press release: "consolidating ChatGPT, Gemini, and Claude", summary lines 9-11; plans real-time tracking, body line 21), `2025/earthly-insight-joins-global-rewilding-champions` (a funded partner; "avoiding energy-intensive features like image generation", body line 20), `2026/earthly-insight-conscious-ai-assistant`, `2026/green-web-foundation-index` (generic, lines 15-17), `2026/directory` (lists providers, not apps), `2026/green` (Krystal, off-entity), `2016/announcement-100` (off-entity, ten years old); uncited `2026/earthly-insight-app-ai` (App Store listing: GPT-4o and Claude 3.5 Sonnet, body line 16).

| Rank | Candidate text | Expected verdict / confidence | Level | Carrying sources | Speaks to the problem? | New research? |
|---|---|---|---|---|---|---|
| D1 | Earthly Insight's answers come from ChatGPT, Gemini and Claude rather than from models it hosts itself. | `true` / low (entity-written press release and listing) | self-reported after overrides | `2025/introducing-earthly-insight-more-conscious-143500454html`; `2026/earthly-insight-app-ai` | Partly: relocates the hosting question to providers the pool has nothing current on | No |
| D2 | Earthly Insight leaves out image and video generation to cut its energy use. | `true` / medium (press release plus a funded partner's article) | partially-verified | `2025/introducing-earthly-insight-more-conscious-143500454html`; `2025/earthly-insight-joins-global-rewilding-champions` | Yes, but it is the existing `excludes-image-generation` template: run that instead | No |
| D3 | Earthly Insight says it plans real-time tracking of energy, water and carbon per query. | `true` / low; reports a plan, which the voice rules discourage ("never write a forecast the site cannot evidence") | claimed | `2025/introducing-earthly-insight-more-conscious-143500454html` | No; shows the agent ranks plan-reporting last | No |
| D0 | Original | stays `unverified`; or `not-applicable` for a wrapper (D11) | n/a | none | n/a | Yes: earthlyinsight.com pages (the dropped LinkedIn statement); OpenAI, Google, Anthropic current sourcing |

### Claim E: Viro AI is hosted on renewable energy

File: `research/claims/viro-ai/renewable-energy-hosting.md` (draft, claimed, low, `cap_rationale` set). Analyst `unverified`/low; auditor `true`/low.

Why unverified: the pool is first-party only (R4); "100% clean energy" is, by Viro's own methodology, procurement matched to a token-based estimate, not a statement about the power at its servers (R2); the ChatGPT, Claude and Gemini chats run on other providers (R3); the hosting provider is unnamed, OVHcloud being a guess the scorer admits ("lacks Viro AI-specific validation") (R3). Data note: `verification_level: claimed` is wrong by the source-quality rules; `2026/viro-energy-and-impact-methodology` is first-party `kind: documentation`, which makes the pool `self-reported`.

Sources: cited `2026/viro-ai-planet-focused-platform` ("Powered by 100% clean energy", line 12; profits to wind, solar and battery projects, line 13), `2026/viro-energy-and-impact-methodology` ("measures operational energy from inference", lines 12-13; "renewable procurement as structural fossil displacement", line 14; mapping to solar, wind, hydro, body line 20), `2025/viro-ai-privacy-policy-2025` (encrypted cloud storage, no provider), `2025/viro-ai-terms-conditions`, `2024/ai-server` (OVHcloud, off-entity), `2025/why-does-ai-use-so-much-energy`, `2024/ai-climate-impact-energy` ("Most major AI companies do not disclose meaningful, comparable data", lines 15-16), `2025/how-much-energy-do-your-ai-prompts-really-use`; uncited `2026/viro-eco-friendly-ai-app` (App Store: "powered by clean energy"; "published energy methodology, which measures real usage data", body line 19). No source names the model providers the entity file lists.

| Rank | Candidate text | Expected verdict / confidence | Level | Carrying sources | Speaks to the problem? | New research? |
|---|---|---|---|---|---|---|
| E1 | Viro AI's "100% clean energy" claim rests, by its own methodology, on estimating the energy of each answer from token counts and buying renewable energy to match it. | `true` / low (all first-party) | self-reported | `2026/viro-energy-and-impact-methodology`; `2026/viro-ai-planet-focused-platform`; `2026/viro-eco-friendly-ai-app` | Yes: matching is not supply, as in A3; checkable against two pages | No |
| E2 | Viro AI publishes a methodology for estimating the energy its answers use and says it funds wind, solar and battery projects with its profits. | `true` / low | self-reported | `2026/viro-energy-and-impact-methodology`; `2026/viro-ai-planet-focused-platform` | No, neutral to positive; shown so the operator sees the favorable framing next to E1 | No |
| E3 | Viro AI routes chats to ChatGPT, Claude and Gemini, so part of its inference runs on OpenAI, Anthropic and Google infrastructure. | needs a source: the entity description says it, no source does | n/a | none on disk | Partly: relocates the hosting question | Yes, cheap: ai.viro.app |
| E0 | Original | stays `unverified` | n/a | none | n/a | Yes: Viro's provider, and the providers' energy mix |

### Generalization

Recurring reasons, the restatement move for each, and the signals the agent or the code can detect. R1 to R4 are reasons a claim is unverified and become the `why_unverified` enum; R5 to R7 are pool and pipeline conditions the command handles in code or instructions, not reasons the agent reports.

| Id | Reason | Claims | Restatement move | Detectable signals (sidecar and sources) |
|---|---|---|---|---|
| R1 | A count, threshold or population nobody publishes | A | Restate as the aggregate figure that is published (A1), or as what the named sources do and do not disclose (A3) | Title has a comparator or number ("fewer than", "N%"); narrative says "no source provides a concrete count/tally"; a sub-question starting "How many" with `citations: []` or only topic-circling citations |
| R2 | Concept mismatch: the claim's word (certified, hosted, clean) is not the sources' word (matched, purchased, offset, procurement) | A, C, E | Restate using the mechanism the sources name; or move to a vocabulary template (T2, under D11) | `key_quotes` contain "matched", "match", "purchase", "procurement", "offset", "certificates", "PPA"; claim text contains "certified", "hosted on", "runs on", "100%"; template `notes` encode degree ("mixed = offsets only") |
| R3 | Entity level vs upstream provider (wrapper products, cloud hosts), provider named or not | B, C, D, E | Restate as "built on X" (neutral, low); name the provider in the rationale so the operator can draft the hosting claim on the provider entity by hand (D14); flag that settling it needs the provider's sources | Entity `description` or sources say "integrates/consolidates ChatGPT, Gemini, Claude", "powered by GPT-4", "who host the servers"; sq3 ("which provider") citations name a third party; `sources_consulted` includes a cloud vendor's own pages (OVHcloud, Google Sustainability) |
| R4 | Entity silent; pool first-party only | B, C, D | Restate as what the named documents cover and omit (B1); better, run `discloses-energy-sourcing` or T2 "none stated" instead | `cap_rationale` present; every sq1 citation is `first-party` or `unknown`; narrative "none of the sources mention"; `evidence_gaps` "none identifies the provider" |
| R5 | Off-entity sources inflating the pool | B, C, D, E | Not a restatement: drop them before ranking and recompute `verification_level` on what remains (retrieval, `search_hints.exclude`, and the independence relabel in "Source pool retrieval") | `publisher` is neither the entity nor a provider named by sq3; `scorer_rationale` phrases "potential host or competitor", "relevant if ... uses", "insight into how cloud providers disclose"; no `source_overrides` for a page whose host differs from the entity website |
| R6 | Auditor grades the narrative, not the claim | A, B, C, E | Not a restatement: the bundle carries no auditor verdict, so `auditor_verdict: true` on an `unverified` analyst verdict cannot read as support for the original text | `verdict_agrees: false` with `analyst_verdict: unverified` and `auditor_verdict: 'true'`; `auditor_reasoning` matches "narrative correctly notes", "the claim that the evidence does not support ... is well-supported". Cause: the Evaluator instruction to base its verdict only on the narrative. RE-AD (Evaluator grades the claim) replaces it with grading the claim statement; sidecars written before RE-AD keep the pattern until refreshed |
| R7 | Narrative asserts an absence the sources do not state | D | Instructions: re-derive "silent on" from source text, not from the narrative | Narrative "does not list X" where the cited source is `kind: index` with no entity names in `key_quotes` or body |

Where the pool is too thin for restatement to help: A's original count (needs a registry of facilities by renewable share); B (AWS's current energy mix; which Brave services run where); C (OpenAI's energy sourcing); D (Earthly Insight's own renewable statement; OpenAI, Google, Anthropic current sourcing; the 2016 Google page fails the as-of rule); E (Viro's hosting provider; the providers behind its third-party chats). A1 is the one restatement that disk evidence settles decisively while naming a problem; everything else on disk settles only "what the entity says" claims at low confidence.

## Command contract

```
dr claim-restate CLAIM_REF [--write] [--accept N] [--format text|json] [--max-candidates N]
                 [--max-sources N] [--pool all|cited] [--dry-run] [--repo-root PATH]
```

| Argument or flag | Meaning | Default |
|---|---|---|
| `CLAIM_REF` | `<entity-dir>/<claim-slug>` as `dr claim-refresh` takes it (`orchestrator/cli.py:910-911`), resolved by `_resolve_claim_path` (`cli.py:2058`). Subject claims need the full path (`subjects/us-data-centers/<slug>`); the bare-slug form globs one directory level only (`cli.py:2068`) | required |
| `--write` | Write the `restatement` block to the sidecar (replaces any earlier block) | off |
| `--accept` | Accept candidate `N` (its `rank` in the sidecar's `restatement` block): append a criterion to `research/templates.yaml`, record `accepted` in the block, print the `dr onboard --only` command. Requires `--write`; calls no model and does not re-run the proposal; refused when the sidecar has no `restatement` block or `N` is out of range (S5) | unset |
| `--format` | `text` (report) or `json` (the `RestatementProposal` dump plus retrieval stats) | `text` |
| `--max-candidates` | Upper bound on candidates the agent returns; stated in the prompt. The model's `max_length=5` is the hard cap, so values above 5 are rejected by the CLI | 5 |
| `--max-sources` | Sources sent to the agent after retrieval ranking; cited sources are always included and count toward it | 24 |
| `--pool` | `all` ranks the whole pool; `cited` sends only the claim's `sources` | `all` |
| `--dry-run` | Print the retrieval ranking and the prompt size; call no model (mirrors `dr step-audit --dry-run`, `cli.py:1368`) | off |
| `--repo-root` | As every other command (`cli.py:1371`) | git toplevel |
| `--restater-model` (group option on `dr`) | Model for this agent; falls back to `--auditor-model`, then `--model` | unset |

Exit codes: `0` report produced, or criterion written with `--accept`; `1` precondition failed (claim not found, verdict not `unverified`, claim has no entity file, zero sources after retrieval; with `--accept`: no `--write`, no `restatement` block in the sidecar, `N` out of range, criterion slug already in `templates.yaml`, entity name absent from the candidate text); `2` provider keys missing (`_check_provider_api_keys`, `cli.py:83-98`); `3` the model returned nothing after retries (`_run_with_null_retry` returned `None`). `--write` never happens on a non-zero exit. Keys are checked only when a model call will happen, so `--dry-run` and `--accept` need none.

Help group: add `claim-restate` to the "Read-only" row of `_COMMAND_GROUPS` (`cli.py:119-126`), next to `step-audit`, which has the same read-by-default, `--write`-to-sidecar contract.

Examples:

```
uv run dr claim-restate brave-browser/renewable-energy-hosting
uv run dr claim-restate subjects/us-data-centers/there-are-fewer-than-10-us-data-centers-that-are-certified-to-run-on-50-or-greater-renewable-energy-power-sources --format json
uv run dr claim-restate viro-ai/renewable-energy-hosting --pool cited --max-candidates 3
uv run dr claim-restate chatgptree/renewable-energy-hosting --write
uv run dr claim-restate subjects/us-data-centers/there-are-fewer-than-10-us-data-centers-that-are-certified-to-run-on-50-or-greater-renewable-energy-power-sources --write --accept 1
```

Text report sketch (candidates sorted in code by decisiveness, then by fewer `needs_new_research`, then by candidate text; the model's own order is not trusted):

```
============================================================
Restatement proposal: brave-browser/renewable-energy-hosting
============================================================
Original:  "Brave Browser is hosted on renewable energy"  (unverified, low, as of 2026-10-04)
Why unverified: upstream-provider
  No source names the data centers behind Brave's services beyond "sync runs on AWS";
  renewable sourcing is never stated by Brave or a third party.
Pool: 112 sources on disk, 8 cited, 24 sent (16 uncited, ranked by entity, title and topic terms)
Model: greenpt:gpt-oss-120b

#1  decisiveness 4/4  expected: false (low)  level: self-reported
    "Brave Browser's transparency report and privacy policy state where the electricity for Brave Browser's servers comes from."
    frame: disclosure
    supports:  2026/transparency  "...lists token metrics..." [quote verified]
               2026/brave-browser-home  (no matching passage; quote unverified)
    contradicts: none
    rationale: Brave's transparency report and site cover tokens, security and privacy; none mention energy sourcing.

#2  decisiveness 3/4  expected: mostly-true (low)  level: claimed
    "Brave Browser's sync service runs on Amazon Web Services."
    frame: supplier
    supports:  2026/631793  "...servers are located on AWS..." [quote verified]
    ...

#4  decisiveness 1/4  expected: unverified  NEEDS NEW RESEARCH
    "Amazon Web Services matched 100% of Brave's hosting electricity with renewable energy in 2025."
    frame: supplier
    ...

Next: see docs/runbook.md § Restating an unverified claim. Nothing written (add --write to record this proposal;
      then --write --accept <n> turns candidate n into a criterion).
```

`--write --accept 1` output for the us-data-centers claim, after a proposal whose candidate 1 is A1 has been written:

```
Accepted candidate #1 of the proposal from 2026-10-10 for subjects/us-data-centers/there-are-fewer-than-10-us-data-centers-that-are-certified-to-run-on-50-or-greater-renewable-energy-power-sources.
Criterion written to research/templates.yaml: renewable-sources-supplied-about-a-quarter-of-the-electricity-used-by-us-data-centers-in-2024-natural-gas-supplied-more-than-40
  text: "Renewable sources supplied about a quarter of the electricity used by ENTITY in 2024; natural gas supplied more than 40%."
Run: dr onboard subjects/us-data-centers --only renewable-sources-supplied-about-a-quarter-of-the-electricity-used-by-us-data-centers-in-2024-natural-gas-supplied-more-than-40
```

## Source pool retrieval (no LLM)

Deterministic ranking in a new module `pipeline/restater/retrieval.py` (pure functions; disk reads only through `load_source_dict`, `orchestrator/persistence.py:109`, so the source dict shape stays the one the analyst and auditor see).

Pool size today: 112 source files, bodies are the ingest model's short text (UNSCHEDULED RF20). The whole pool would fit one prompt; the cap exists for predictable cost and so the ranking is testable.

Query terms, all read from disk:

| Term source | Where | Weight |
|---|---|---|
| Entity name, `aliases`, `legal_name`, parent company name and its aliases | `parse_entity_ref` (`orchestrator/entity_resolution.py:105`) and the parent entity file | 3 per distinct term hit |
| Claim `title` tokens (minus stopwords and the entity's own tokens) | claim frontmatter | 2 |
| Criterion `text` tokens when `criteria_slug` is set | `get_template` (`common/templates.py:110`) | 2 |
| Sidecar `research.queries[]` and `sub_questions[].question` tokens | `read_sidecar` (`common/sidecar.py`) | 1 |
| `search_hints.include` terms | entity frontmatter | 2 |
| Claim `topics` | a small per-topic synonym list in the module (for `environmental-impact`: renewable, energy, carbon, emissions, electricity, data center, PUE, offset) | 1 |

Document text per source: `title`, `publisher`, `summary`, `key_quotes`, `body`. Tokenizer: lowercase, split on non-word characters, drop a fixed English stopword list, strip a trailing `s`, `es`, `ed`, `ing` when the stem is at least 4 characters. Score = sum of weight × min(hits, 3) per term, divided by log(2 + token count) so long bodies do not win by length. Ties break by source id. Sources whose URL host matches a `search_hints.exclude` entry are dropped (`host_matches`, `common/utils.py:44`; the researcher drops the same domain-shaped `exclude` entries through blocklist entries in `_apply_entity_exclude`, `researcher/decomposed.py:534`).

Selection: every cited source first (in claim order), then uncited sources by score descending while score > 0, until `--max-sources`. The report prints the counts and, in `--dry-run`, the full ranked list with scores.

Independence labels: before the bundle is built, run `_apply_entity_match(sources, resolved_entity, repo_root)` (`orchestrator/pipeline.py:511`, called at `:1194`) so the agent sees per-claim corrected labels; the claim's own `source_overrides` are applied on top for cited sources. This is what the analyst sees (`pipeline.py:1188-1190`); without it the agent's `verification_level_estimate` repeats RF3 (wrong independence labels inflating `verification_level`). Off-entity sources (R5) are not removed by code beyond `search_hints.exclude`; the corrected labels plus the `cited` marker let the agent weigh them, and the counts in `--dry-run` show them.

Relationship to "Local source-search prefilter (analysis only)" (`docs/UNSCHEDULED.md:424`): that item asks for a value analysis before building a corpus search for the researcher. This module is option (a) from its sketch (keyword over `research/sources/**`), built for one bounded consumer; the researcher is not changed. The counts this command prints (uncited sources with score > 0 per claim) are part of the data that memo wants; the backlog row under "Release-triage inputs" says so.

## The agent

Package `pipeline/restater/`, mirroring `pipeline/auditor/`:

| File | Role | Analog |
|---|---|---|
| `__init__.py` | empty | `auditor/__init__.py` |
| `models.py` | bundle and output models | `auditor/models.py` |
| `bundle.py` | `build_bundle(...)` from primitives | `auditor/bundle.py` |
| `agent.py` | `restater_agent = Agent("test", system_prompt=..., output_type=RestatementProposal, retries=2)`, `build_restater_prompt(bundle)` | `auditor/agent.py:15-20` |
| `instructions.md` | system prompt, loaded with `load_instructions(dir, common("verdict-scale.md"))` | `auditor/agent.py:13` |
| `retrieval.py` | the ranking above | none (new) |
| `evaluate.py` | code-side checks on the output: quote verification, decisiveness caps, sorting | `auditor/compare.py` |
| `report.py` | `format_text_report`, `format_json_report` | `auditor/report.py` |

Input bundle (`models.py`):

```
class RestateSource(BaseModel):          # the auditor's SourceContext fields plus labels
    id: str; title: str; publisher: str; kind: str; independence: Independence
    cited: bool; summary: str; key_quotes: list[str]; body: str

class RestateBundle(BaseModel):
    claim_id: str
    entity: EntityContext                # reuse auditor.models.EntityContext
    topics: list[Category]
    original_text: str                   # the claim title, verbatim
    original_narrative: str              # claim body
    original_verdict: Verdict            # always unverified in v1 (D5)
    cap_rationale: str | None
    evidence_gaps: list[str]             # sidecar audit.evidence_gaps, may be empty
    criterion_text: str | None           # template text with PRODUCT/COMPANY substituted
    sources: list[RestateSource]
```

The bundle carries the original verdict because the agent needs to know it is explaining a gap, not re-judging the claim. It carries no auditor verdict or reasoning (R6) and no hint about which verdict any candidate should get.

Output models:

```
class EvidenceRef(BaseModel):
    source: str                          # source id; must be in the bundle (validated)
    quote: str = Field(max_length=300)   # verbatim passage the candidate relies on
    note: str = Field(max_length=200)    # what the passage establishes

class Frame(str, Enum):                  # what the candidate asserts; neutral names
    NARROWED = "narrowed"                # same assertion, smaller scope (one service, one year, one site)
    DISCLOSURE = "disclosure"            # what the entity has or has not published
    SUPPLIER = "supplier"                # a named supplier's practice
    COMMITMENT = "commitment"            # a stated goal or pledge, not a practice
    MEASUREMENT = "measurement"          # a number a source reports
    OTHER = "other"

class WhyUnverified(str, Enum):          # one value per recurring reason R1 to R4
    QUANTIFIER_UNSUPPORTED = "quantifier-unsupported"   # R1: a count, threshold or population no source tallies
    TERM_MISMATCH = "term-mismatch"                      # R2: the claim's word is not the sources' word
    UPSTREAM_PROVIDER = "upstream-provider"              # R3: the fact belongs to a provider, named or not
    ENTITY_SILENT = "entity-silent"                      # R4: the entity publishes nothing on it; pool first-party only
    OTHER = "other"

class RestatementCandidate(BaseModel):
    text: str = Field(max_length=200)    # one affirmative sentence with the entity as subject;
                                         # no question, no added negation (polarity lives in the verdict,
                                         # same rule as analyst/instructions.md:60-70)
    frame: Frame
    expected_verdict: Verdict
    expected_confidence: Confidence
    verification_level_estimate: VerificationLevel
    decisiveness: int = Field(ge=0, le=4)
    supporting: list[EvidenceRef]
    contradicting: list[EvidenceRef]
    needs_new_research: bool
    rationale: str = Field(max_length=400)   # reader-facing, cites sources by title, no ids or "Source N"
                                             # (reuse analyst.citations.has_citation_reference as a validator)

class RestatementProposal(BaseModel):
    why_unverified: WhyUnverified
    why_unverified_note: str = Field(max_length=400)
    candidates: list[RestatementCandidate] = Field(min_length=1, max_length=5)
```

Decisiveness rubric (in `instructions.md`, enforced partly in `evaluate.py`):

| Score | Meaning |
|---|---|
| 4 | A quoted passage states the candidate's fact directly, in either direction, from an independent source, or from the entity's own formal document when the frame is `disclosure` |
| 3 | A quoted passage states it directly but only first-party or only one source; verdict clear, confidence at most medium |
| 2 | Two or more passages are needed and an inference joins them; verdict likely but contestable |
| 1 | Sources touch the topic; the candidate would still be `unverified` |
| 0 | Nothing in the pool addresses it |

Code-side checks (`evaluate.py`, pure functions, tested without a model):

- Every `EvidenceRef.source` must be a bundle source id; unknown ids drop the ref and add a report note.
- Quote verification: `quote` is searched, whitespace-collapsed and case-insensitive, in the source's title, summary, key quotes and body. A ref whose quote is not found is kept but marked `quote_verified: false`. A candidate with no verified supporting quote has decisiveness capped at 2 (key quotes on disk are not always verbatim, RF10, so a miss is informative, not fatal).
- A candidate with decisiveness 0 or 1 gets `needs_new_research = True` regardless of what the model said.
- `expected_verdict: unverified` forces decisiveness at most 1.
- A candidate whose `expected_confidence` is `medium` or `high` while `verification_level_estimate` is `claimed` or `self-reported` is lowered to `low` with a note (the confidence cap, `docs/architecture/source-quality.md` § Confidence cap).
- Candidates are sorted as the report states; the model's order is discarded.

`instructions.md` outline:

1. Role: you propose restatements of a claim whose existing sources do not settle it. You do not judge the original claim and you do not pick which restatement is best; a person does.
2. Inputs: the original claim and why its verdict is `unverified`; the entity; sources, some cited by the claim and some from the same archive, each with `independence` and `kind`.
3. Polarity guard, verbatim: "Rank candidates only by how decisively these sources settle them. A candidate the sources refute is as valuable as one they confirm. You have not been told what any candidate should say or which verdict is wanted. Do not prefer candidates that make the entity look better or worse. Give the expected verdict the evidence gives, including `false`."
4. Spread: give between 2 and `max_candidates` candidates using at least three different frames when the sources allow; one candidate keeps the original's scope as close as the evidence permits (frame `narrowed`). Spread decides which candidates you produce, never their order or their decisiveness scores; a frame is not a reason to score a candidate higher.
5. Candidate form: one sentence, entity as subject, written with the entity name exactly as shown (so `--accept` can put the template placeholder in its place), affirmative, no question, no "does not" (the verdict carries polarity; same rule as the analyst title rule), no vocabulary placeholders.
6. Evidence: every supporting or contradicting passage is quoted verbatim from the source text shown; never from memory. Cite by source id in `source`; in `rationale` cite by title. Derive "silent on" from the source text, not from the original narrative (R7).
7. Verdict and confidence: the appended verdict scale (`common/verdict-scale.md`); `unverified` is allowed for a candidate and ranks last. Confidence cap and `verification_level` derivation as the analyst applies them (`analyst/instructions.md:155`, SOURCE QUALITY), from the labels shown. Sources about another entity (R5) support a candidate only when the candidate names that entity's practice (frame `supplier`).
8. `why_unverified`: pick one value, one or two sentences of note; name the missing fact, not the missing source.
9. `needs_new_research`: true when the pool cannot settle the candidate; say in `rationale` what kind of source would.
10. Entity: every candidate is about the entity shown. When the fact belongs to a provider or partner (frame `supplier`), the candidate still has this entity as its subject and the rationale names the provider; never propose a claim about another entity (D14).

Priority (b) of the Goal is served by items 4 and 5, not by a thesis: a `disclosure` or `supplier` candidate about what the entity has not published, or what its supplier does, is the usual decisive framing for an unverified environmental claim, and it appears as one ranked candidate alongside the rest. The instructions never name "negative impact".

Model tier: this is Evaluator-class work. Reading a dozen or more passages and judging, per candidate, whether they settle a statement and how strongly is the Evaluator's job (`AGENTS.md:121`, "independent evaluation"), not a classification the Router could make (`AGENTS.md:17`). The Router-class model used for research and ingest (Ministral 14B) produced the garbled sub-question "What sontent" in `research/claims/brave-browser/renewable-energy-hosting.audit.yaml` (`sub_questions[0].question`), the quality band to expect from it on multi-passage judgment. So the agent runs on the Evaluator's slot: `--restater-model`, falling back to `--auditor-model`, then `--model` (default `greenpt:gpt-oss-120b`, `common/models.py:DEFAULT_MODEL`). The option is added to the `dr` group next to `--auditor-model` (`cli.py:197`) with `envvar="DR_RESTATER_MODEL"`. `AGENT_NAMES` (`common/models.py:73`) and `VerifyConfig` are not extended: that tuple enumerates agents that run inside `verify_claim`, and this agent never does. The sidecar records the model in `restatement.model`.

Concurrency and retries: one model call per invocation, so `llm_concurrency` does not apply (the semaphore exists for fan-out inside `verify_claim`, `research_claim` and `onboard_entity`, `orchestrator/pipeline.py:346, 1312, 1808`). Call the agent through `_run_with_null_retry(restater_agent, prompt, RESTATE_TIMEOUT_S)` (`pipeline.py:1124`) so Infomaniak null bodies and rate limits are retried the same way as the analyst and auditor; `RESTATE_TIMEOUT_S = 180.0` as a module constant in `restater/agent.py` (the auditor's 120 s is for an 8-source prompt; this one sends up to 24). `dr step-audit` calls `auditor_agent.run` directly without the retry wrapper or the semaphore (`cli.py:1477-1478`); the new command follows the pipeline path, not that shortcut.

## Sidecar changes

A top-level `restatement` block in `.audit.yaml`, written only by `dr claim-restate --write`:

```
restatement:
  schema_version: 1
  proposed_at: '2026-10-10T23:40:12+00:00'
  model: greenpt:gpt-oss-120b
  pool:
    mode: all                      # all | cited
    on_disk: 112
    cited: 8
    sent: 24
  original:
    title: Brave Browser is hosted on renewable energy
    verdict: unverified
    confidence: low
    as_of: '2026-10-04'
  why_unverified: upstream-provider
  why_unverified_note: ...
  candidates:
  - rank: 1
    text: ...
    frame: disclosure
    expected_verdict: 'false'
    expected_confidence: low
    verification_level_estimate: self-reported
    decisiveness: 4
    needs_new_research: false
    supporting:
    - source: 2026/transparency
      quote: ...
      quote_verified: true
      note: ...
    contradicting: []
    rationale: ...
  accepted:                        # present only after --write --accept N (S5)
    candidate: 1
    criterion_slug: brave-browsers-transparency-report-and-privacy-policy-state-where-the-electricity-for-brave-browsers-servers-comes-from
    accepted_at: '2026-10-11T09:02:40+00:00'
```

Rules:

- One block per claim. `--write` replaces an earlier block (the report says "replacing proposal from <date>"); replacing a block that carries `accepted` prints a warning naming the criterion slug, since the template entry stays. History lives in git (D9).
- `--write --accept N` edits the existing block in place (adds or replaces `accepted`) and does not touch the rest of it.
- Written by a targeted read-modify-write (`yaml.safe_load`, set the key, `yaml.safe_dump(sort_keys=False, allow_unicode=True)`), the way `approve_claim` edits `human_review` (`orchestrator/review.py:269-282`). It must not go through `_write_audit_sidecar` (`persistence.py:542`), which rebuilds the whole file and would reset `pipeline_run` and `models_used` to a run that did not happen.
- `_write_audit_sidecar` carries an existing `restatement` block forward unchanged, as it does `refresh` (`persistence.py:514-539, 671-672`), so a later `dr claim-refresh` or `dr step-audit --write` does not silently drop operator-visible work (the RF8 lesson: a refresh once changed a published verdict with no trail). The report shows when a proposal predates the latest run (`proposed_at` earlier than `pipeline_run.ran_at`).
- `approve_claim` removes the block on `--approve` and `--archive`, as it removes `refresh` (`review.py:276-277`): approving publishes the claim as it stands, archiving retires it; either closes the proposal. A bare `dr review` sign-off leaves it.
- `--write` is allowed on draft, published and blocked claims; the precondition is the verdict, not the status.

Site build: no `src/content.config.ts` change is needed for the block. `auditSchema` (`src/content.config.ts:38-90`) is a plain `z.object`, which strips unknown keys (the loader passes the raw YAML as `audit`, parsed by the claims schema at `content.config.ts:225`); `research`, `sub_questions` and `refresh` already live in sidecars without appearing in the schema or in `docs/architecture/content-model.md` § Claim Audit Sidecar, and builds pass. When the site should render a proposal, add an optional `restatement: z.object({...}).optional()` to `auditSchema`; that edit is under `src/` and release-gated. This plan touches nothing under `src/` (D17).

Doc updates: `docs/architecture/content-model.md` § Claim Audit Sidecar gains a `restatement` table beside the `refresh` one; the same section should also list `research` and `sub_questions` as present-but-unrendered.

## Linter

None in v1 (D16). A `restatement-pending` rule (a proposal older than 30 days with no action) is in the Follow-ups row of the `docs/UNSCHEDULED.md` section "Claim restatement (`dr claim-restate`)". Existing rules are unchanged by the sidecar block; `published-without-criterion` (`checks.py:99-128`) is what makes S5 necessary.

## Writing the criterion (`--accept`)

What exists: `dr claim-promote` (`cli.py:1207-1356`) prompts for slug, entity type, topics, core and notes (`click.prompt`, `cli.py:1272-1278`), replaces the entity name in the claim title with the placeholder from `_ENTITY_TYPE_PLACEHOLDERS` (`cli.py:38-42`: company `COMPANY`, product `PRODUCT`, subject `ENTITY`; `cli.py:1280-1281`, exact-case `str.replace`), checks the slug against the existing entries, and appends the entry as a text fragment under `templates:` so comments and field order survive (`cli.py:1283-1353`; bare-list files, used by its tests, are rebuilt instead). Everything after the prompts is inline in the command body: there is no function another command can call, and the slug is typed by the operator, not derived.

S5 factors the writer out as `append_template_entry(templates_path: Path, entry: dict) -> None` in `pipeline/common/templates.py`, next to `load_templates` (`templates.py:66-83`): it does the duplicate-slug check (raising `ValueError`), the dict-versus-list format detection and the fragment append, and it serializes `text` and `notes` with `yaml.safe_dump` so a candidate containing double quotes (E1 does) stays valid YAML. `_ENTITY_TYPE_PLACEHOLDERS` moves beside it. `claim_promote` keeps its prompts and calls the function; its tests (`tests/test_cli.py:633-790`) must still pass.

The entry `--accept N` writes, from candidate `N` (`rank == N`) of the sidecar block and the original claim:

| Field | Value | Source |
|---|---|---|
| `slug` | `slugify(candidate text)` (`common/utils.py:9`), the function that names ad hoc claim files (`pipeline.py:1446`); refused when it exists | candidate `text` |
| `text` | candidate text with the first match of the entity `name` or an `aliases` entry (longest first, case-insensitive; "US Data Centers" must match "US data centers") replaced by the placeholder for the entity type; refused when none matches, with a hint to use `dr claim-draft` and `dr claim-promote` instead (the sweep's B1, "Brave's ...", would be refused: the entity name is "Brave Browser" and the entity file lists no aliases, which is why instructions item 5 asks for the name as shown) | candidate `text`, entity file |
| `entity_type` | from the claim's `entity` ref prefix (`parse_entity_ref`, `entity_resolution.py:105`) | claim frontmatter |
| `subjects` | `[subjects/<slug>]`, only when the entity is a subject (required by `TemplateRecord`, `templates.py:46-52`) | claim `entity` |
| `topics` | copied | claim frontmatter |
| `core` | `false` | fixed |
| `notes` | `restated from <entity-dir>/<claim-slug>, candidate N` | claim path |

`dr onboard --only` today accepts only core templates: the slug check at `pipeline.py:2139-2147` looks in `typed_templates`, which `templates_for_entity_type` (`templates.py:86-107`) filters to `core`. S5 widens that check to every template of the entity type (for a subject, every template whose `subjects:` names it); the fan-out without `--only` stays core-only, so a `core: false` restatement is never created for another entity by accident.

The command then writes `accepted: {candidate, criterion_slug, accepted_at}` into the sidecar block and prints `Run: dr onboard <type>/<slug> --only <criterion-slug>`. It does not run the pipeline; the onboard call is the operator's, and the researcher there reuses sources already on disk by URL.

## Operator loop after the report

Three outcomes. In each, the original claim's sidecar already holds the proposal (after `--write`), so the reasons for restating are on record before the first new file exists.

**A. New claim from an accepted candidate (the original stays or is archived).** Use when the chosen candidate is a one-off for this entity.

1. `uv run dr claim-restate <ref> --write`
2. `uv run dr claim-restate <ref> --write --accept <n>`: writes the criterion (`core: false`, scoped to this entity type and, for a subject, this subject) and records `accepted` in the sidecar (S5).
3. `uv run dr onboard <type>/<entity-slug> --only <criterion-slug>` (printed by step 2). The researcher runs again; sources already on disk are reused by URL (`url_index`), so the new claim cites existing files where the researcher finds the same pages. The new claim is template-backed, so `dr publish` accepts it (`cli.py:2232`).
4. Add `restates: <entity-dir>/<original-slug>` at the top level of the new claim's audit sidecar (S6, D17).
5. `uv run dr review --claim <new-ref> --approve`.
6. `uv run dr review --claim <original-ref> --archive --notes "restated as <new-ref>"` if the original should leave the site. The archive closes the proposal block.

A candidate the operator wants to edit before using goes through `dr claim-draft <entity-ref> "<edited text>"` (`cli.py:798`) and `dr claim-promote` instead; `--accept` writes the candidate text as it stands.

**B. Template text change (template-backed claim).** Use when the candidate should replace the criterion for every entity.

1. `uv run dr claim-restate <ref> --write`
2. Edit the criterion's `text` in `research/templates.yaml` (for `renewable-energy-hosting`, `templates.yaml:53-58`).
3. `uv run dr claim-refresh <ref>` (`cli.py:897`): the claim text is rendered from the template (`render_claim_text`, `cli.py:993`), the analyst's title is validated against it (`validate_analyst_title`, `cli.py:1133`), and a published original is snapshotted in the sidecar's `refresh` block (`persistence.py:486-539`).
4. `uv run dr review-queue`, approve. If the verdict changed, approval asks for `--correction` (`review.py:239-246`). If only the title changed, nothing asks (D15; a follow-up in `docs/UNSCHEDULED.md`), so the operator who wants a public trail passes `--correction` by hand.
5. Siblings: a template edit changes nothing on disk for other entities' claims. Each sibling keeps its old title until it is refreshed, at which point its new title must match the new text or the claim blocks (`pipeline.py:2417-2423`). No lint rule checks a claim title against its template text today, so a half-migrated criterion is visible only by reading titles (follow-up row). For the renewable-hosting row this is 6 product claims plus Brave; refresh them one at a time and approve each. Keeping `criteria_slug: renewable-energy-hosting` on a retitled claim keeps it in the same comparison-matrix row (`src/lib/matrixCheck.ts:82`), so readers would see different wording per entity under one criterion.

**C. Keep the original, record the analysis.** `--write` only. The claim stays `unverified`; the proposal is on record for the next refresh. Nothing reminds the operator in v1 (D16).

Audit-trail link between old and new claim. What exists: `corrections` on claim frontmatter (`date`, `summary`, `previous_verdict`; `content.config.ts:228-233`, `content-model.md:146`), written at approval of a refresh whose verdict changed; `refresh.previous.title` in the sidecar; `human_review.notes`. Nothing links two claim files. Proposal:

- New optional top-level sidecar key `restates: <entity-dir>/<claim-slug>` on the new claim's `.audit.yaml` (outcome A), set by hand in v1 (D17). `_write_audit_sidecar` carries it forward the way it carries `refresh` and `restatement` (S4), so a later refresh keeps it; `approve_claim` leaves it alone. Documented in `content-model.md` § Claim Audit Sidecar. Not in frontmatter, not in the site schema, not rendered. `superseded_by` on the archived original is not added: it would mean editing an archived file, and the original's sidecar `restatement` block (with `accepted` after S5) plus `human_review.notes` already point forward.
- Outcome B has a public trail through `corrections` only when the verdict changed (D15).
- A later `dr claim-draft --restates <ref>` flag that writes the key and copies the proposal block to the new sidecar is a follow-up, noted in the backlog row.

## Tests

All under `pipeline/tests/`, run by `uv run pytest` (`inv test`). Patterns: `TestModel(custom_output_args=...)` for a scripted structured output (`tests/test_analyst.py:18-31`), `agent.override(model=TestModel())` for a round trip (`tests/test_auditor_agent.py:40-48`), `CliRunner().invoke(main, ["--model", "test", ...])` with a `tmp_path` repo (`tests/test_cli.py:1369-1422`), lint checks called directly with dicts (`tests/test_linter.py`).

| Test file | Covers | Model |
|---|---|---|
| `test_restater_retrieval.py` | tokenizer and stemmer; cited sources always first; entity alias hits outrank title hits; `search_hints.exclude` drops a host; cap honored; deterministic order on ties; empty pool returns only cited; a tmp repo with 6 sources and one claim, asserting the exact ranked ids | none |
| `test_restater_evaluate.py` | quote found with different whitespace and case; quote not found marks `quote_verified: false` and caps decisiveness at 2; unknown source id dropped; decisiveness 0 or 1 forces `needs_new_research`; `unverified` candidate capped at 1; confidence cap applied; sort order | none |
| `test_restater_agent.py` | prompt contains the original text, the `cited` marker, independence labels, no auditor verdict and no verdict hint for candidates (`"expected"` not in prompt); round trip with `TestModel()` yields a `RestatementProposal`; a scripted `custom_output_args` with 3 candidates round-trips; `rationale` with a `【...】` token is rejected (the analyst's citation validator) | TestModel |
| `test_restater_report.py` | text report lists candidates in evaluated order with the "NEEDS NEW RESEARCH" marker and the unverified-quote marker; json report is `model_dump(mode="json")` plus `pool` counts | none |
| `test_cli.py` (new class `TestClaimRestateCli`) | precondition exits: missing claim, verdict `true` and verdict `mixed` (exit 1); `--dry-run` calls no model and prints the ranking; `--write` adds `restatement` to an existing sidecar and leaves `pipeline_run`, `human_review` and `refresh` unchanged; a second `--write` replaces the block; no sidecar on disk creates none without `--write` and exits 0 | `--model test` |
| `test_cli.py` (`TestClaimRestateCli`, the `--accept` cases) | `--accept 1` without `--write` exits 1 and writes nothing; `--accept` with no `restatement` block exits 1; `--accept 9` with three candidates exits 1; happy path on a tmp repo with a dict-format `templates.yaml`: the entry is appended, `load_templates` returns it with the expected `slug`, `text`, `entity_type`, `subjects`, `topics`, `core: false` and `notes` (the round trip), the sidecar gains `accepted` with the right `candidate` and `criterion_slug`, the rest of the block and `pipeline_run` are unchanged, the output names the `dr onboard --only` command, and no model is called; a duplicate slug exits 1 and leaves both files unchanged; a candidate text containing double quotes round-trips; the entity name is matched case-insensitively ("US Data Centers" against "US data centers") and an alias matches; no match exits 1 | none |
| `test_templates.py` | `append_template_entry` on a dict-format file keeps the comment lines above the first entry and appends at the end; on a bare-list file rebuilds a valid list; raises on a duplicate slug. `test_loads_active_templates_from_yaml` (`test_templates.py:23-25`, asserts `len == 16`) is changed to compare against the length of the raw `templates:` list so an accepted entry landing in `research/templates.yaml` at S9 does not break it | none |
| `test_onboard.py` | `only=[<non-core slug>]` passes the slug check and fans out that template; the existing counts of 5 company templates (`test_onboard.py:194, 250, 309`) use the core-only fan-out and are not changed by a `core: false` entry | TestModel |
| `test_cli.py` (`TestClaimPromote`, `test_cli.py:633-790`) | unchanged and still passing after the writer is factored out | none |
| `test_cli_smoke.py` | add `"claim-restate"` to the parametrize list (`tests/test_cli_smoke.py:10`) | none |
| `test_audit_trail.py` | `_write_audit_sidecar` carries `restatement` forward, `accepted` included; `approve_claim` removes it on approve and archive and keeps it on bare review (`human_at_terminal` fixture, `tests/conftest.py:122`) | none |
| `test_restater_acceptance.py` | fixture copy of the us-data-centers claim, its sidecar, its entity and its 8 cited sources under `tests/fixtures/restate/us-data-centers/` (the research files are on disk but untracked and may be regenerated; the fixture is a snapshot taken in S7). (1) `TestModel(custom_output_args=...)` scripting a 3-candidate proposal whose quotes are real passages from the fixture sources: the CLI writes a block whose `candidates[0]` has `quote_verified: true` and `decisiveness: 4`, and a candidate quoting invented text comes out capped at 2. (2) marked `acceptance` (`pyproject.toml:26-29`, skipped by default): runs the real model from `DR_*` env and asserts only shape: at least 2 candidates, at least 2 frames, every `source` id in the fixture, and a `why_unverified` value | (1) scripted, (2) live |

## Steps

Each step is one commit, test-first. Line numbers as of HEAD `0b3d0a9`.

#### S1: retrieval module
Files: `pipeline/restater/__init__.py`, `pipeline/restater/retrieval.py`, `pipeline/tests/test_restater_retrieval.py`.
Done when: the retrieval tests pass; a script call `rank_sources(repo_root, claim_path, max_sources=24)` on the real repo lists the 8 cited brave sources first, and `--dry-run` style output can print it.
Size: about 150 lines plus tests.

#### S2: models, instructions, agent, evaluate, report
Files: `pipeline/restater/{models,bundle,agent,evaluate,report}.py`, `pipeline/restater/instructions.md`, `pipeline/tests/test_restater_{agent,evaluate,report}.py`.
Done when: the three test files pass with `TestModel`; `load_instructions` loads the file with the verdict scale appended; the polarity-guard sentence from "instructions.md outline" item 3 is present verbatim (a test greps for it); the `WhyUnverified` values are exactly the five listed in D10.
Size: about 300 lines plus the instructions and tests. Independent of S1 (the bundle takes source dicts; S1 only decides which ones).

#### S3: the command
Files: `pipeline/orchestrator/cli.py` (new command, `--restater-model` group option, `_COMMAND_GROUPS`), `pipeline/tests/test_cli.py`, `pipeline/tests/test_cli_smoke.py`.
Done when: `TestClaimRestateCli` passes; `uv run dr claim-restate --help` shows the contract; `uv run dr claim-restate brave-browser/renewable-energy-hosting --dry-run` prints the ranking without a model call and without a provider key.
Depends on S1 and S2.

#### S4: sidecar write, carry-over, closure
Files: `pipeline/orchestrator/persistence.py` (`write_restatement_block`, carry-over in `_write_audit_sidecar`), `pipeline/orchestrator/review.py` (pop on approve and archive), `pipeline/tests/test_audit_trail.py`, `docs/architecture/content-model.md`.
Done when: the carry-over and closure tests pass; `--write` on a copy of the brave sidecar leaves every other key byte-identical after a YAML round trip.
Depends on S3 for the CLI path; the persistence functions can be written in parallel with S3.

#### S5: `--accept` writes the criterion
Files: `pipeline/common/templates.py` (`append_template_entry`, `_ENTITY_TYPE_PLACEHOLDERS` moved here), `pipeline/orchestrator/cli.py` (`claim_promote` calls the function; `--accept` on `claim-restate`), `pipeline/orchestrator/persistence.py` (`accepted` written into the block by the same read-modify-write as S4), `pipeline/orchestrator/pipeline.py` (`--only` slug check widened to non-core templates, `pipeline.py:2139-2147`), `pipeline/tests/test_cli.py` (`TestClaimRestateCli` `--accept` cases), `pipeline/tests/test_templates.py` (`append_template_entry`; the count test made robust), `pipeline/tests/test_onboard.py` (`only` with a non-core slug).
Done when: the tests in the "Tests" rows for `--accept`, `test_templates.py`, `test_onboard.py` and `TestClaimPromote` pass; on a tmp repo, `--write --accept 1` appends an entry that `load_templates` reads back, writes `accepted`, and prints the `dr onboard --only` command; `uv run dr claim-promote --help` and its tests are unchanged in behavior; `uv run dr lint` on the repo reports nothing new.
Depends on S4 (reads the block from the sidecar and edits it in place).

#### S6: `restates` sidecar key
Files: `pipeline/orchestrator/persistence.py` (`restates` added to the keys `_write_audit_sidecar` carries forward, beside `refresh` and `restatement`), `pipeline/tests/test_persistence.py` (carry-over case), `docs/architecture/content-model.md` § Claim Audit Sidecar (one row: `restates`, optional, operator-set, the original claim's ref).
Done when: a sidecar with a top-level `restates:` keeps it after `dr step-audit --write` and `dr claim-refresh` on a tmp repo; `dr lint` and `npm run build` are unchanged by its presence.
Depends on the carry-over half of S4 (D17).

#### S7: acceptance fixture and live test
Files: `pipeline/tests/fixtures/restate/us-data-centers/**`, `pipeline/tests/test_restater_acceptance.py`.
The us-data-centers claim, sidecar and entity are on disk, untracked (RISK-4); this step snapshots them and the 8 cited sources into the fixture directory so the test does not depend on the untracked files.
Done when: the scripted test passes in `inv test`; the live test passes once with `uv run pytest -m acceptance -k restate` and its proposal is pasted into the plan's review history row (model, candidate texts, decisiveness), as the record of the first real run.
Depends on S3 and S4.

#### S8: docs and the operator runbook
Files: `AGENTS.md` (command list after `dr step-audit`, `AGENTS.md:181`; `--restater-model` under the model options if they are listed), `docs/architecture/glossary.md` (cross-walk row under Evaluator, `glossary.md:64`; § Workflow term row "Restate", `glossary.md:86-92`), `docs/runbook.md` (new section "Restating an unverified claim" with outcomes A, B, C), `pipeline/README.md` structure list (also stale today: it lists `consistency/` and "Phase 4.x" labels that no longer exist).
Done when: every command in the runbook section has been run once against the repo (with `--dry-run` where a model would be called; `--accept` against a tmp copy) and the help text matches.
Depends on S1 to S7.

#### S9: run on the five worked examples and record the operator's picks
Files: the five sidecars under `research/claims/` (`--write`), this plan (a "Worked examples" table: claim, `why_unverified` the agent chose, the candidate the operator picked or "none", the outcome A, B or C, and whether the pick matched the sweep's top candidate A1, B1, C1, D1 or E1).
Done when: `uv run dr claim-restate <ref> --write` has run on all five claims; the operator has chosen a candidate or declined for each; for at least the us-data-centers claim, `--write --accept <n>` and the printed `dr onboard --only` command have been run and `dr lint` passes with the new entry in `research/templates.yaml`. This step is the acceptance of the whole plan: it shows whether the command's ranking agrees with a hand sweep and whether the output changes what the operator does.
Depends on S8 and on D11 and D12.

Parallel: S1 and S2 together; the persistence half of S4 alongside S3, S6 right after it; S5 after S4; S7 after S3 and S4; S9 last. Estimated size: about 750 lines of code and tests plus docs; two to three sessions plus the S9 review session.

## Pipeline defects found on the way (not in scope)

Each becomes a `docs/UNSCHEDULED.md` row; none is fixed by this plan.

- Sidecars written before RE-AD (Evaluator grades the claim) show the Evaluator grading the narrative instead of the claim: 4 of 5 unverified sidecars return `auditor_verdict: true` with reasoning such as "the narrative correctly notes the absence". RE-AD makes the Evaluator grade the claim statement; these sidecars keep the old pattern until refreshed.
- Template `notes` never reach the analyst prompt: `renewable-energy-hosting` says "mixed = offsets only", and ChatGPTree (offsets only) came out `unverified`.
- Off-entity pool contamination: GreenPT pages in ChatGPTree's pool, `2016/announcement-100` in Brave's and Earthly Insight's, `2024/ai-server` (OVHcloud) in Viro's; they lift `verification_level` to independently-verified on claims with no engaging source.
- The narrative asserts an absence a source does not state: Earthly Insight's "GWF does not list" rests on index pages that list no host at all.
- The entity exclude rule dropped Earthly Insight's only first-party renewable statement (a LinkedIn post scored 5, `research.entity_exclude_dropped`).
- Viro's `verification_level: claimed` should be `self-reported` under the source-quality rules (first-party `kind: documentation` in the pool).
- The Router-class model produced a garbled sub-question ("What sontent") in `research/claims/brave-browser/renewable-energy-hosting.audit.yaml`.
- Docs versus code: `docs/architecture/research-flow.md` § 6 says all LLM calls are guarded by the `llm_concurrency` semaphore, but `dr step-audit` calls `auditor_agent.run` directly with neither the semaphore nor `_run_with_null_retry` (`orchestrator/cli.py:1477-1478`); `docs/architecture/content-model.md` § Claim Audit Sidecar does not list the `research` and `sub_questions` blocks every pipeline-written sidecar carries (`persistence.py:666-669`), which `auditSchema` strips at build (`src/content.config.ts:38`); `AGENTS.md:181` and `_COMMAND_GROUPS` (`cli.py:120-121`) file `dr step-audit` under read-only although `--write` rewrites the sidecar; `pipeline/README.md` § Structure lists `consistency/` and "Phase 4.x" labels that do not exist; `common/models.py:70-73` says adding an agent means extending `AGENT_NAMES` and `VerifyConfig`, which this plan's CLI-only agent deliberately does not do.

## Risks

- RISK-1, quote fidelity. Source bodies are the ingest model's short text, not page text (RF20), and key quotes are not always verbatim (RF10), so candidates may rest on paraphrase. Mitigation: the `quote_verified` mark and the decisiveness cap; the report says so. Design changes only if the operator wants unverified-quote candidates dropped rather than capped.
- RISK-2, model variance (RF6). The same pool gave `unverified`, `mostly-true` and `true` across analyst runs. A proposal is advisory and the operator picks, so variance costs a re-run, not a wrong publication. D9 keeps only the last run in the sidecar; earlier runs are in git.
- RISK-3, low ceiling for four of five claims. The sweep found that only A1 is settled decisively by disk evidence while naming a problem; the template claims yield low-confidence "what the entity says" candidates. S9 may show the command confirms the ceiling rather than lifting it, which is still the answer to priority (a).
- RISK-4, the primary worked example is untracked. The claim and sidecar under `research/claims/subjects/us-data-centers/` and the entity file are on disk but not committed, and research files are regenerated by pipeline runs, so they can change or vanish before S7 and S9 run. Mitigation: S7 snapshots them into `pipeline/tests/fixtures/restate/us-data-centers/`, so the acceptance test never depends on the untracked files; S9 runs against whatever is on disk then and records the result. If the files are gone at S9, `dr claim-draft subjects/us-data-centers "<original title>"` regenerates a claim whose sidecar and verdict may differ from the sweep.

## Questions for the operator

None open. Q1, Q3, Q5, Q6 and Q7 are answered and recorded as D13, D14, D17, D15 and D9. D11 and D12 (content, not design) are decided before S9.

## Release-triage inputs

- Kind: `minor` (VERSION.md: "new feature shipped"; a new command, a new agent, a new sidecar block, criteria written by `--accept`). Before 1.0.0 a minor "either rides the beta line or waits for after 1.0.0 (ask)", `VERSION.md:14-18`.
- Theme: 1, Responsible AI chatbots. Three of the page's six renewable-hosting cells cite Unverified claims and render "unknown" (`docs/plans/responsible-ai-chatbots-claims.md`, D25 and D26, and the status line for S15, the renewable-hosting cells), and S16 (the remaining feature rows) will produce more of the same shape. This command is how an "unknown" cell becomes a cited answer without new research. Theme 6 (visible method) is served too: the sidecar records why a claim was restated and `corrections` makes the change public, but theme 1 is the ranking argument. The SITE-J (Responsible AI chatbots) plan limits its pipeline changes to S11, S12 and S13a (its own pipeline fixes; D32 there), so this is a separate roadmap item, listed on theme 1's `Work:` line in `docs/priorities.md` as "(Proposed, operator to confirm)".
- Proposed roadmap item: `RE-AC (Claim restatement)`. Verified against `docs/v1.0.0-roadmap.md` at HEAD `0b3d0a9`: letters A to Z, AA and AB are all taken (M twice, by SEC-M and SITE-M), so AC is the next unused letter. Re-check before merge; peers take letters in parallel.
- `docs/UNSCHEDULED.md` section "Claim restatement (`dr claim-restate`)", after "claim-refresh review findings (2026-10-04)" (`docs/UNSCHEDULED.md:397`), as it reads today:

```
## Claim restatement (`dr claim-restate`)

Goal: turn an `unverified` claim into one the sources on disk can settle, without new research. A new command and agent read one unverified claim plus the whole `research/sources/` pool, rank restatements by how decisively the existing evidence settles them (either direction), and record the proposal in the claim's audit sidecar; the operator chooses the framing and acts with `dr claim-draft`, a template edit plus `dr claim-refresh`, or `dr review --archive`. Design: `docs/plans/claim-restate.md`.

| Work Item | Plan | Notes |
|-----------|------|-------|
| Command, agent, sidecar block, `--accept` writes the criterion, runbook | `claim-restate.md` | Evaluator-class model (`--restater-model`, falls back to the auditor's). Retrieval is deterministic keyword ranking over `research/sources/`, cited sources first; its counts feed the "Local source-search prefilter" analysis above. `--accept` appends a `core: false` criterion to `research/templates.yaml` through the writer factored out of `dr claim-promote`. Serves the Responsible AI chatbots page: 3 of 6 renewable-hosting cells cite Unverified claims. Triage: Responsible AI chatbots; propose schedule; 2026-10-10 |
| Follow-ups | | `dr claim-draft --restates <ref>` writes the link and copies the proposal; a lint check that a template-backed claim's title matches its criterion text (needed once a criterion's text is edited); bounded web research for candidates marked `needs_new_research` (one `dr step-research` call per candidate, operator-triggered); a title-only change on `dr claim-refresh` requires a `--correction` at approval (cut from v1); lint rule `restatement-pending` for a proposal older than 30 days with no action (cut from v1). Triage: Responsible AI chatbots; keep; 2026-10-10 |
```

- The "Pipeline defects found on the way" list above is the section "Unverified-claim sweep findings (2026-10-10)" in the same file (`docs/UNSCHEDULED.md:408`).

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-10-10 | agent (claude-fable-5-1) | iterated | Merge of the evidence sweep and design drafts, both written against HEAD `0b3d0a9`. Reconciled: the `why_unverified` enum now follows reasons R1 to R4 (see D10); pool size 112 on disk (the sweep's 120 was wrong); plan path `claim-restate.md`. |
| 2026-10-10 | agent (claude-fable-5-1, fresh-eyes review) | citations, consistency, polarity wording, conventions | Verified 30 `path:line` citations against HEAD `0b3d0a9` and fixed 12 (`cli.py` CLAIM_REF and glob lines, `checks.py` ranges, `runner.py`, `content.config.ts` range, `common/models.py`, `pyproject.toml`, `decomposed.py` wording, `glossary.md`); B1 and the report sketch rewritten in the affirmative candidate form (`false`/low) and the sidecar example aligned with the confidence cap; spread rule now says it never affects ranking; Q2 and Q4 demoted to D11 and D12; RISK-4 added because the us-data-centers claim is not on disk; S5b and S8 files corrected; bare IDs given names. |
| 2026-10-10 | agent (claude-fable-5-1) | operator answers applied | Q1 (b): S5 `--accept` writes the criterion through a writer factored out of `dr claim-promote`, `dr onboard --only` widened to non-core templates (D13); Q3: no claims on another entity, no target-entity field (D14); Q6: S5b (title-only correction) cut to the follow-ups row (D15); Q7: D9 stands; reviewer cuts: `--allow-mixed` and `mixed-split` removed (`why_unverified` has five values), lint rule `restatement-pending` cut to the follow-ups row (D16); steps renumbered (`restates` key is S6; lint step removed); Q5 reworded in plain words and left open; RISK-4, the Claim A note and S7 updated for the untracked files now on disk. |
| 2026-10-10 | agent (claude-fable-5-1) | operator answer applied; promotion | Q5 (b): the `restates` link lives in the new claim's audit sidecar only (D17); S6 rewritten as the sidecar key with carry-over, no `src/` edit anywhere in the plan; questions section closed; plan promoted from `docs/plans/drafts/` to `docs/plans/`. |
