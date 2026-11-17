# Research content: principles, queue and scouting

**Status**: Approved 2026-11-08; first queue run 2026-11-08 and 2026-11-09, budget spent; awaiting Brandon's walkthrough; rank 10 held for a pipeline fix; the homepage FLI claim's source refresh is RE-BS (FLI claim sources move to the Summer 2026 index) on beta.11  
**Stream**: research content (claims, sources, drafts, rechecks). Not the site, not the pipeline code.  
**Home**: `docs/research-content.md`, beside `priorities.md`; the dated decisions are in `docs/decisions.md` under 2026-11-08.

## Intent

The site has two published claims of the kind it exists for, the ones that test something most readers assume or never think to question: using generative AI harms cognitive ability, and no major AI model producer scores above D+ on existential safety. Brandon wants about ten. There is no written rule for which claims get drafted, which in-flight drafts get published, parked or archived, or how to vet a candidate sentence before paying for a pipeline run. This document is that rule set, the first candidate queue it produces, and the vetting step that feeds the queue.

Goal: a corpus of about ten published "elephant in the room" claims, both dangers covered, each one durable enough to survive a year of rechecks.

Gate: approved 2026-11-08. The queue's paid runs are delegated to an agent within the budget in § What the ten would cost (Brandon, 2026-11-08). Every `dr review --approve`, delete and archive is still Brandon's own act at the terminal: a sign-off needs a person typing the claim slug back, so an agent prepares the review queue and stops there.

Non-goals: homepage layout (the homepage keeps its two cards; ten is a corpus target, not a homepage feature); any pipeline code; product-comparison claims for the Responsible AI chatbots page, which keep their own slow track.

Anti-goals: a claim whose only lesson is "nobody knows"; a forecast in the site's own voice; a sentence whose verdict would flip within a quarter; a corpus that covers one danger and waves off the other.

## Principles

Source column: D = already decided in the repo (file and date), B = Brandon on 2026-11-08, A = the author's call, open to change.

| # | Principle | Source |
|---|---|---|
| P1 | The thesis picks the topic. A claim earns a place by backing a guide, one of the five Values positions, or one of the two kinds of danger. A claim with no page or position to serve is parked, however true. | D: `mission-and-voice.md` § What it is; `decisions.md` 2026-10-11, Brave Browser dropped as out of scope |
| P2 | Elephants first. A claim that tests something most readers assume, or never think to question, and that the public record can settle, goes ahead of everything else. | B |
| P3 | The verdict must teach. A claim is worth publishing when the reader learns something whichever way the verdict falls. "Unverified" teaches only when the missing evidence is itself the lesson: a certification that should exist and does not, a disclosure no company makes. | B. Example from Brandon: "uses certified renewable sources" unverified teaches (no certificate exists); "uses mostly renewable energy" unverified teaches nothing |
| P4 | Durable facts over moving ones. A claim should stay true for a year or more. A dated fact that stays true ("in 2024, X") counts as durable; a floating "typical" number does not, unless the sentence pins its year and its source. Each recheck is a paid run and a stale window. | B, plus the recheck cadence |
| P5 | Subjects and entities both qualify. Subject claims (generative AI, data centers, AI model producers) educate broadly. Entity claims may be drafted on their own merit; they do not need an existing guide to call for them. | B (loosened 2026-11-08 from "entities only when a guide compares them") |
| P6 | Independent sources or an honest cap. A claim resting on first-party sources alone stays `unverified` and says so. | D: verification levels; `decisions.md` 2026-10-11, "A source about the provider does not verify the entity" |
| P7 | Both dangers in the portfolio. The published set covers what AI does to the reader and what it does to everyone. Neither side is left to the other. | D: `mission-and-voice.md` voice rule 5 |
| P8 | No forecast in the site's voice. A claim built on a projection names the forecaster in the sentence ("the IEA projects..."). A sentence that cannot be rewritten that way is dropped. | B, confirming `mission-and-voice.md` voice rule 2 |

Not a principle, allowed case by case (B): a claim whose verdict cuts against the site's positions, such as "a typical text prompt uses about a third of a watt-hour". Brandon decides per claim whether the trust it earns is worth the place it takes.

## Decisions recorded 2026-11-08

One line each; these are the entries proposed for `docs/decisions.md`.

- **Ten elephant claims.** The research corpus targets about ten published claims that pass P2; today it has two. A corpus target, not a homepage feature.
- **Forecasts name the forecaster.** The site publishes no forecast of its own. A claim that rests on a projection names who made it, in the claim sentence.
- **Entity claims need no guide.** A claim about a product or company may be drafted on its own merit (P5).
- **Seeding is allowed, corroboration is required.** A pipeline run may be started from a hand-picked source when agent search is blocked or thin. The seed never carries the verdict alone; the pipeline must find independent sources that corroborate it. A researcher that misses obvious evidence is still recorded as a pipeline finding. (A: a verdict resting only on seeds stays `unverified`, by the same rule as P6. Brandon's words were "a hand-picked source needs to be corroborated"; the cap is the author's reading of that.) Mechanics today: `dr draft --source URL` ingests one page into `research/sources/` and writes nothing else, so a seed is stored before the run; whether the loop then uses a stored source for a new ad hoc draft is for the builder to confirm. If it does not, seeding a new draft is pipeline work and this queue's new drafts run unseeded, accepting the verdict and filing a finding when search is thin.
- **Counter-thesis claims case by case.** Allowed, not a principle.
- **A scouting step before the pipeline.** One strong-model pass per candidate sentence, no search, before any paid run. Described below.

## Scouting: vetting a sentence before the pipeline

**What it is.** A fresh strong-model agent (Fable or Opus) reads the principles and a list of candidate sentences, works from its own knowledge only (no web search, no fetching, no repository reads), and writes one brief. For each candidate: the sentence, rewritten if it needs sharpening; P2, P3, P4 each pass, weak or fail with one line; the forecast check (none, named forecaster, unfixable); a prior on the verdict with a confidence and its reasons, saying plainly when knowledge may be stale; the kinds of source that would settle it; and run, hold or drop. It ends with a ranked shortlist.

**What it is for.** Killing and wording, not verdicts. The test run on 2026-11-08 (17 candidates, one agent, about eight minutes) earned its place on four candidates: it found a unit mismatch in a proposed sentence (energy demand compared against investment dollars), merged a duplicate, rewrote an unverifiable count as an absence claim, and reframed a famous ratio as a claim about where the number comes from. Its priors are recalled, not checked. One was already stale: it wanted to move the 4% electricity claim to 2023, while the pipeline's 2024 draft is multiply verified at 183 TWh. The pipeline is the check; the scout only picks what to check.

**Guard.** The scout never seeds the run it recommends. Its "what would settle it" list is for the operator reading the brief, not for the researcher. Seeding, when used, is a separate operator act under the seeding decision above.

**Where the brief goes.** `research/reports/YYYY-MM-DD-claim-scouting.md` with `report_type: brief`, `citable: false`, `method: single-model`, `human_review: pending` until Brandon has read it. Reports are working sources and the site never loads them (`research/reports/README.md`). The 2026-11-08 test run is in `handoff/2026-11-08-claim-scouting-spike.md` (gitignored); it is not promoted to a report, because it predates the rule and its numbers are unchecked.

**How it is invoked.** Open: a saved prompt in `docs/`, or a repo skill (`/scout-claims`) under `.claude/skills/`. Recommendation: the skill, because the prompt has seven fixed inputs (principles, vocabulary, output shape) and a fixed output path, and a skill keeps them from drifting between sessions. Left to Brandon.

## Changes in flight

Every planned, in-progress, waiting or unpublished change to research content, in four groups: Homepage (the two homepage claims), Responsible AI page (claims and sources the chatbots page links to), Elephant (the ranked queue below) and Other (everything else, reports and untracked sources included).

Rules:

- A row is added when a change is first planned, before any paid run, and names who does the next step and whether it is a paid run.
- State is one of: planned, in progress, waiting on Brandon, ready to publish, approved not yet live, held, draft report, untracked. "Held" names its blocker; a held row that blocks a beta says so.
- A row drops off when the beta that carries it is tagged; git history and the records under § Why each change was made keep it after that.
- No new Elephant candidates are added until Brandon's walkthrough of ranks 1 to 10 is done (Brandon, 2026-11-17).

| Group | Claim | Change | Why | State | Blocker or next step | Target beta |
|---|---|---|---|---|---|---|
| Homepage | Using generative AI harms cognitive ability (`subjects/generative-ai/using-generative-ai-harms-cognitive-ability`) | recheck | scheduled recheck; as_of 2026-11-07, confidence medium to high | approved not yet live | none | beta.10 |
| Homepage | None of the major AI model producers score above D+ on existential safety in the latest FLI AI Safety Index (`subjects/ai-model-producers/ai-producers-existential-score`) | reword and recheck | the sentence now says "the latest FLI index" while its sources are the 2025 edition; the Summer 2026 index is out | planned | RE-BS (FLI claim sources move to the Summer 2026 index): pipeline fix for the 2026-11-17 misread, then a paid rerun (Brandon's budget OK). The live claim ships unchanged in beta.10; FLI's own 2026 table gives D+ at most, so the sentence holds | beta.11 |
| Responsible AI page | Earthly Insight renewable-energy hosting, second version (`research/pending/earthly-insight/renewable-energy-hosting.md`) | recheck | rerun of the published claim, as_of 2026-10-14, verdict unverified | waiting on Brandon | sign-off or delete at the terminal | the beta after sign-off |
| Responsible AI page | Rows with a criterion and no claims: real-time energy display, no image generation, ownership structure | new claims | the cells rest on sources only | planned | not scheduled; product-comparison claims keep their own slow track | none |
| Elephant | Ranks 2, 3, 4 (three product claims), 5, 6, 8 and 9 | new claims | § Elephant ranked queue | waiting on Brandon | his walkthrough sign-off | beta.10 if signed off before it ships |
| Elephant | Rank 1, "100% renewable" means certificates | new claim | § Elephant ranked queue | held | RE-BM (Tie-broken claims get a matching narrative) | beta.11 |
| Elephant | Rank 7, a third of a watt-hour per prompt | new claim | counter-thesis, case by case | waiting on Brandon | rerun as rewritten (paid) or archive | none yet |
| Elephant | Rank 10, the four US labs train on your chats by default | new claim | § Elephant ranked queue | held | analyst instruction fix (pipeline stream), then one paid rerun | none yet |
| Elephant | Superseded drafts: the 2026-10-14 drafts behind ranks 1 and 9, the two earlier rank 8 wordings, the rank 10 first run | delete | replaced by the ranked wordings | waiting on Brandon | `d` in the walkthrough | none |
| Elephant | Reserves and the § Triage of the eight subject drafts holds and archives | new claims or archive | § Triage of the eight subject drafts | planned | the walkthrough, then a new paid-run budget | none yet |
| Other | Microsoft AI humanist code of conduct critique (`research/reports/2026-11-03-microsoft-ai-humanist-code-of-conduct.md`) and `research/reports/README.md` | new report | adversarial review | draft report | Brandon's read; files untracked | none |
| Other | Four Summer 2026 FLI AI Safety Index sources (`research/sources/2026/ai-safety-index-*.md`, `the-2026-ai-safety-index-nine-ai.md`) | new sources | needed by the homepage FLI claim's rerun | untracked | commit with that rerun | beta.11 |

### Why each change was made

Each change carries its own reason in three places that already exist: the sign-off note (`dr review --claim REF --notes "<why>"`, stored as `human_review.notes` in the claim's audit file), the conventional commit message that names the claim and the reason, and, when a published verdict changes, the claim's `corrections` list (date, summary, previous verdict), which readers see.

### Elephant ranked queue

The first queue, produced by the 2026-11-08 scouting run and the author's read of it. Sentences are the rewritten forms; the scout's recalled numbers are not carried here. "Criterion" says whether a criterion in `research/templates.yaml` already covers the sentence (there are 23 criteria; 20 have no claim).

Sentence length: a claim sentence stays well under 150 characters, 150 is too long (B, 2026-11-08); detail that does not fit goes to the narrative. Sentences here are the shortened forms.

Rank order is the scout's shortlist with one change: C2 (gas against renewables) is kept as the ninth, ahead of the reserves, because it pairs with C1 (the "100% renewable" claim) and is a dated fact.

| Rank | Sentence | Where it stands | Criterion | Earns its place by | Recommendation |
|---|---|---|---|---|---|
| published | Using generative AI harms cognitive ability. | published, true, 2026-11-07 | `using-generative-ai-harms-cognitive-ability` | P2 | keep |
| published | None of the major AI model producers score above D+ on existential safety in the latest FLI AI Safety Index. | published, true, 2026-05-10 | `ai-producers-existential-score` | P2 | keep; RE-BS (FLI claim sources move to the Summer 2026 index) brings its sources to the Summer 2026 index in beta.11 |
| 1 | Data centers' "100% renewable" claims mean certificates matched to a year's use, not renewable power hour by hour. | draft, mostly-true (low), run 2026-11-08, tie-broken; the narrative argues mixed | none; ad hoc | P2, the most-assumed badge in the environmental case | hold for RE-BM (Tie-broken claims get a matching narrative) on beta.11; the 2026-10-14 draft awaits Brandon's `d` |
| 2 | In April 2025 OpenAI rolled back a ChatGPT update that agreed with harmful ideas to please users, a flaw its tests missed. | draft, true (high), run 2026-11-08 | ad hoc under `subjects/ai-model-producers` (A: it is about what a maker admitted, not a product comparison; `anti-sycophancy-by-design` stays a product criterion) | P2 and P3: the "grants wishes" thesis plus a maker's admission | approve |
| 3 | In 2023 the heads of OpenAI, Anthropic and Google DeepMind signed a statement calling extinction risk from AI a global priority. | draft, true (high), run 2026-11-08; criterion `ai-producers-signed-extinction-risk-statement` attached | ad hoc under `subjects/ai-model-producers`, then a new criterion attached (A: the existing `ai-producers-signed-safety-commitments`, "Most major ENTITY have signed AI safety commitments", asks a vaguer question and is left alone) | P2: the second danger, on the record from the builders | approve |
| 4 | Consumer ChatGPT and Gemini train on your chats unless you opt out, and Meta AI gives US users no opt-out. | drafts, run 2026-11-08: ChatGPT false (medium), Meta AI false (high), Gemini mixed (medium: the consumer default is off in the EU, UK and Switzerland and on elsewhere); Gemini analyst and Evaluator rerun 2026-11-09 after the grading rule dropped "account type" | three product claims from the existing criterion `no-training-on-user-data`, for `products/chatgpt`, `products/gemini` and a new `products/meta-ai` (B, 2026-11-08); the inverted, US-scoped sentence became a claim of its own on 2026-11-09 (rank 10 below), superseding the note that the summary sentence was not one | P2: the strongest individual-side elephant; the reader can act on it the same day | approve all three as the comparison rows (ChatGPT false, Meta AI false, Gemini mixed with the regional default explained); rank 10 carries the lesson |
| 5 | In a 2025 US survey, most teens had used an AI companion and a third had picked one over a person for a serious talk. | draft, true (medium), run 2026-11-08, two sources | ad hoc under `subjects/generative-ai` (A) | P3: speaks to the staying-human position | approve |
| 6 | US data centers used more than 4% of the country's electricity in 2024. | draft, true, multiply verified, as of 2026-10-14 | none; ad hoc | P4: the dated anchor for the environmental claims (P2 weak on its own) | publish as is |
| 7 | By Google's and OpenAI's own 2025 figures, a typical text prompt uses about a third of a watt-hour. | draft, mixed, as of 2026-10-15 (original wording) | none; ad hoc | counter-thesis, case by case; the rewrite names the year and the companies as the source (P4, P8) | Brandon decides: rerun as rewritten, or archive |
| 8 | By mid-2026, courts worldwide had caught AI-invented citations in more than a thousand filings. | draft, true (high), multiply verified, run 2026-11-09 (the short sentence; the floor wording with "and some lawyers were fined" ran earlier that day, also true, and the 2025 wording ran 2026-11-08, unverified) | ad hoc under `subjects/generative-ai` (A) | P3: hallucination reaching high-stakes use by trained professionals | approve; the two earlier drafts await Brandon's `d` |
| 9 | Measured by grid power actually drawn, US data centers in 2024 got more electricity from gas than from all renewables combined. | draft, true (medium), run 2026-11-08 (rewritten wording; the narrative draws the grid-mix line) | none; ad hoc | P2 and P4; pairs with rank 1 | approve; the 2026-10-14 draft awaits Brandon's `d` |
| 10 | In the US, OpenAI, Google, Anthropic and Meta all train their AI assistants on your chats by default. | draft, false (medium), run 2026-11-09 (second run, Meta clause dropped, seeded): Google, Anthropic and Meta verified as training by default; OpenAI again graded from its enterprise privacy page, which decided the verdict. The first run (with the Meta clause) is a separate draft, mixed | none; ad hoc under `subjects/ai-model-producers` (Brandon, 2026-11-09: the inverted form, US consumer default, Anthropic and Meta included) | P2: the strongest individual-side elephant, stated once for all four | hold, not publish: the verdict rests on a source misread the pipeline repeated; `d` the first-run draft; rerun after the analyst instruction fix (pipeline stream), with one run added to the budget (Brandon). The three rank 4 criterion rows carry the lesson meanwhile |

Reserves, in order: the number of organizations lobbying the US federal government on AI roughly tripled from 2022 to 2023 (P2, "decided by a few"); in 2025 OpenAI and MIT researchers found the heaviest users of ChatGPT for personal conversation reported more loneliness (P3); answering prompts (inference) uses more of the electricity behind today's models than training did (P2, P4 weak; `unverified` would teach); no independent certification tells the public what share of a US data center's electricity is renewable (P3, the absence is the lesson).

## Triage of the eight subject drafts

All eight are ad hoc (no `criteria_slug`), so a rewording is a new draft with the new sentence and the old draft archived; retro-attaching a criterion is `dr draft --claim <ref> --criterion <slug>` (AGENTS.md § research workflow). The builder confirms the exact commands.

| Draft | Verdict | Recommendation | Reason |
|---|---|---|---|
| "100% renewable" means certificates and contracts | mostly-true | run as rewritten (rank 1) | wording now names the mechanism (annual matching) |
| Gas outweighed renewables, 2024 | true | run as rewritten or publish (rank 9) | needs the grid-mix clause, or a narrative that already draws it |
| Over 4% of US electricity, 2024 | true | publish (rank 6) | multiply verified, dated |
| Inference exceeds training | true | reserve; hold | P4 weak; `unverified` would be an acceptable teaching outcome |
| A third of a watt-hour per prompt | mixed | Brandon's call (rank 7) | counter-thesis; the rank 7 rewrite names the year and the companies as the source |
| Ten times a web search | mixed | hold, then reframe or archive | as written it returns mixed and teaches little; the honest claim is about where the 10x number comes from (a 2009 Google figure and a 2023 executive remark) |
| Fewer than 10 certified 50%+ renewable data centers | unverified | archive; reserve carries the rewrite | unverifiable by construction; the absence claim replaces it |
| (pending) Earthly Insight renewable-energy hosting | unverified | out of scope here | an entity claim on the chatbots track; Brandon's sign-off since 2026-10-15 |

## What the ten would cost, and when a run comes back weak

Eleven pipeline runs or reruns (ranks 1 to 3, three for rank 4, 5, 7 to 9, and one reserve), paid runs an agent may start within the budget below. Scouting adds one strong-model call per batch. No code changes.

Weak outcomes are normal: the pipeline writes `mixed` and `unverified` verdicts and proposes restatements for them, and a capped or failed paid run is never retried without asking Brandon. Rule per outcome and budget, decided by Brandon 2026-11-08:

| Outcome | Then |
|---|---|
| `true`, `mostly true`, or a `mixed` that the narrative explains | review and publish |
| `false` or `mostly-false` | review and publish; a sentence the evidence contradicts is the lesson (the rank 4 product claims expect it) |
| `unverified` where P3 says the gap is the lesson (the queue marks these: inference versus training, no renewable certification) | publish the honest `unverified` |
| any other weak verdict | take the top restatement once (one more paid run); still weak, archive and pull the next reserve |
| abandoned or capped run | ask Brandon before any retry (standing rule) |

Budget: 14 paid runs for this queue (11 planned, 3 for restatements; Brandon approved 12 for the nine-run shape, raised by two with the three product claims). Done: ten published, or the budget spent, whichever comes first; a shortfall is reported, not chased. Spent: 14 of 14 as of 2026-11-09: nine runs on 2026-11-08; on 2026-11-09 the Gemini analyst and Evaluator reruns (counted together as one run), the rank 8 floor run, the rank 10 combined claim, the rank 8 short-sentence rerun, and the rank 10 rerun without the Meta clause (seeded; two source ingests outside the run count).

Releases: a new or changed published claim goes live only with a beta release (`1.0.0-beta.N`), never with a site push (`runbook.md` § Releasing); no claim gets its own release. A claim waits at most one beta between approval and the site.

## Left to the builder

- Archiving or deleting a draft is a sign-off action (the walkthrough's `d`; `dr review --claim REF --archive` for a published claim), so it is Brandon's. The replacement is `dr draft --subject <slug> "<sentence>"`, which searches and ingests afresh and does not need the old draft's sources.
- The scouting skill or prompt, once Brandon picks the form.
- A `--seed <url>` option for `dr draft`, if wanted, belongs to the pipeline stream and is not designed here.

## Decisions and author's calls

Decided by Brandon 2026-11-08: the weak-verdict rule and budget in § What the ten would cost; rank 4 as three product claims; the document approved as written, author's calls included. The budget raise from 12 to 14 that the three product claims imply is the author's arithmetic.

Decided by Brandon 2026-11-09: the `no-training-on-user-data` grading rule grades the consumer default only ("account type" dropped; a regional difference still makes `mixed`), and the Gemini draft's analyst and Evaluator were rerun under it; rank 8 ran as a floor rewrite ("more than a thousand filings by mid-2026") instead of its top restatement, an exact count that grows daily, an approved exception to the weak-verdict rule's "take the top restatement once".

Also decided by Brandon 2026-11-09: the training-default lesson is stated in the inverted form as its own claim, scoped to the US consumer default and naming OpenAI, Google, Anthropic and Meta (rank 10); the four are named rather than "every major US AI lab" so the pipeline grades four defaults, not a definition of major (author's call). Rank 8 drops "and some lawyers were fined" and reruns so the sentence matches everywhere.

Rank 10 after its `mixed`, decided by Brandon 2026-11-09: keep all four companies, drop "and only Meta offers no opt-out", seed OpenAI's consumer data-controls page, rerun. Author's calls in carrying it out: the rerun is a new claim, since `--force` keeps the stored sentence; OpenAI's own pages refused the fetch (403), so the seed is an independent explainer of the "Improve the model for everyone" default; a second seed, an independent report on Anthropic's August 2025 consumer-terms change, was added because the first run read Anthropic's own post as opt-in. Both seeds are named in the handoff note and need corroboration from the run's own search.

Finding from that rerun (2026-11-09): a fresh `dr draft` run does not consult sources already on disk; `--source` ingests are reused only by `--rerun` and the restater. Neither seed reached the run. The seeding rule in § Principles has no mechanism until a `--seed` option exists (§ Left to the builder), so until then a seed is a stored source, not a starting point.

Author's calls, approved with the document and open to change later: the home at `docs/research-content.md`; a verdict resting only on seeds stays `unverified`; the gas-against-renewables claim ranked ninth, ahead of the reserves; the third-of-a-watt-hour draft held rather than archived; rank 2 under `subjects/ai-model-producers`, ranks 5 and 8 under `subjects/generative-ai`; rank 3 gets a new criterion rather than rewording the existing one; claims ship with the next beta rather than one release each.
