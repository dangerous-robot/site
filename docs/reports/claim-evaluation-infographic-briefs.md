# Claim-Evaluation Infographic Briefs

Five self-contained briefs describing how dangerousrobot.org evaluates a claim, each tuned for a different audience. Each brief is written to be handed to a downstream LLM that will design an infographic from it; the brief specifies the data model, message hierarchy, vocabulary level, and what to omit, but does not specify visual form beyond loose suggestions.

Ordering is most-technical to least-technical. Brief 4 is positioned as the most critical because it targets the actual site visitor whose trust the system exists to earn.

| # | Audience | Why this audience |
|---|----------|------------------|
| 1 | Graduate student in agentic systems | Compares this design against their own multi-agent research |
| 2 | Senior ML / platform engineer at an AI lab | Peer architectural judgment |
| 3 | Investigative journalist / AI-literacy educator | Skeptical non-engineer evaluating trustworthiness |
| 4 | Curious adult reading dangerousrobot.org (the actual end user — most critical) | Deciding whether to believe a specific claim on the site |
| 5 | 5th grader (≈10 years old) | Understanding the process without prior technical context |

---

## Brief 1 — Audience: graduate student in agentic systems

**Goal of the infographic.** Convey the full agent topology, control flow, gates, and human-in-the-loop seams of dangerousrobot.org's claim-evaluation pipeline at a level a research-track student can use to compare against their own multi-agent designs.

**What "the system" is.** A multi-agent orchestrator that turns a candidate claim about an AI company / product / subject into a published, sourced verdict. Roles are decoupled from packages; small models do classification, frontier-eligible models do verdict synthesis ("small decisions, small models"). The Evaluator is open-loop by design: disagreements surface to a human, they do not feed back to the Analyst.

**Entities (nodes) to render.**

- *Operator* (human Research Lead).
- *Orchestrator* — owns claim lifecycle, dispatches phases, enforces gates (no LLM).
- *Researcher* — decomposed: Query Planner (Haiku) → fan-out across `research_origins` → URL Scorer (Haiku). Origins: web spine (Tavily default, Brave fallback) plus academic origins (arXiv when claim topics ∩ `ACADEMIC_TOPICS` ≠ ∅; Tier 2 will add S2 / OpenAlex). All LLM calls are gated by an `llm_concurrency` semaphore.
- *Ingestor* — URL → source file, including an archive-recovery waterfall (archive.org TimeGate → Memento aggregator → Save Page Now). Side-channels record `recovered_via ∈ {archive_org, memento}`.
- *Analyst* — claim + sources → AnalystOutput (verdict, narrative, `seo_title`).
- *Evaluator* — independent assessment of the Analyst's output, returning a ComparisonResult; verdict and confidence each compared independently.
- *Citation check / dr lint / Astro build / markdown lint* — static CI gates, not agents.

**Claim state machine.** `[*] → draft → blocked|under_review`; `under_review → published | draft (PR closed)`; `published → stale → under_review`; `published|blocked → archived`. The transient `phase` field (`researching | ingesting | analyzing | evaluating`) decorates `draft` while the pipeline is in flight.

**Gates to mark explicitly.**

1. **Threshold gate** post-ingest: `< 4 usable sources` → `status: blocked`, `blocked_reason ∈ {insufficient_sources, terminal_fetch_error, analyst_error}`. Analyst is not invoked.
2. **CI gates** post-PR: Astro/Zod schema validation, markdown lint, citation integrity, `dr lint --severity error`.

**Human-in-the-loop checkpoints.** `review_sources`, `review_disagreement`, `review_onboard` (`CheckpointHandler` protocol); each can accept/halt/edit. Operator sign-off: `dr review --approve` (per-claim, writes `human_review` audit sidecar + flips draft→published) vs `dr publish` (bulk flip, no per-claim reviewer).

**Audit artifact to highlight.** Every claim has a paired `.audit.yaml` recording `pipeline_run`, models per agent, sources consulted with `acquisition.recovered_via`, both verdicts, and `human_review`. This is the lineage record.

**Suggested visual.** A swim-lane diagram: lane 1 = Operator, lane 2 = Orchestrator + small-model agents, lane 3 = frontier-eligible agents (Analyst, Evaluator), lane 4 = CI/static checks, lane 5 = Human review. Overlay the claim state machine as a strip below, time-aligned to lanes.

**Vocabulary.** Use technical terms verbatim: open-loop, semaphore, threshold gate, decomposed researcher, audit sidecar, blocklist.

**Omit.** Marketing framing. Site routing. Per-template details.

---

## Brief 2 — Audience: senior ML / platform engineer at an AI lab evaluating the design

**Goal.** Show a peer engineer the data flow, where automation ends and humans begin, and what's deliberately decoupled. They will judge whether they trust the verdict pipeline architecturally.

**Core message.** "Claims here are made by small composable agents under human gates, not by a single chat model. Disagreement surfaces, it does not get hidden."

**Entities (nodes).**

- Three intake paths into a queue: a URL submission, a new entity (`dr onboard`), or a claim-text draft.
- A four-step automated pipeline: **Researcher → Ingestor → Analyst → Evaluator**. Make it visually obvious the Evaluator runs *independently*; it does not write back to the Analyst.
- Two human checkpoints inline: *review sources* (after ingest), *review disagreement* (after evaluator). One more for entity onboarding: *review onboard*.
- A static CI lane: schema build, markdown lint, citation check, content lint. All four must pass on the PR.
- A sign-off step: `dr review --approve` writes a record into the audit sidecar and publishes.

**Key facts to encode.**

- Sources are first-class. Claims cite sources by ID, never by raw URL. Each source has an archived URL (recovered through TimeGate → Memento → Save Page Now if the live page is gone).
- A claim halts at `blocked` if fewer than four usable sources survive scoring. Reasons: insufficient sources, terminal fetch error, analyst error.
- Every claim ships with an audit sidecar (`.audit.yaml`) capturing which model ran each step, what sources were consulted, both verdicts, and the human reviewer.
- Researcher fans out across web search (Tavily default) and arXiv when topics warrant; this is configurable per run.
- Different model classes per role: query planning + URL scoring on small models; verdict synthesis only at the Analyst/Evaluator step.

**HITL emphasis.** Show the three checkpoints as physical gates, not optional UI. Show that `dr publish` is a separate bulk path that does not write a reviewer (used for backfills); contrast with `dr review --approve`.

**Suggested visual.** Left-to-right pipeline with two horizontal bands: above the pipeline is the agent flow; below it is the audit trail being assembled in parallel — every step writes into the sidecar. End on a "PR opens → CI gates → human review → published" tail.

**Vocabulary.** Engineering register. Terms like pipeline, semaphore, state, gate, sidecar, fanout, dispatcher are fine. Avoid framework-specific jargon (PydanticAI, Astro) unless contextualizing tooling.

**Omit.** State enum names and field-level schema. Mermaid syntax. Detailed CLI subcommand list.

---

## Brief 3 — Audience: investigative journalist / AI-literacy educator

**Goal.** Show a non-engineer who writes about AI accountability *what makes a published claim trustworthy here*. They are skeptical of automated fact-checking and need to see where humans intervene and where the work is auditable.

**Core message.** "Two AIs evaluate the claim independently, a human reviews disagreements, and every step is recorded so you can replay how a verdict was reached."

**Entities to depict (in plain language).**

- A *claim* — a single sentence about an AI company or product, like "Anthropic publishes a sustainability report."
- An *evidence pool* — the sources gathered to evaluate the claim. Sources are saved with archived copies in case the original page disappears.
- Two AI roles, shown as distinct characters:
  - The **Analyst** reads the sources and proposes a verdict and a written explanation.
  - The **Evaluator** reads the same sources independently and writes its own verdict — without seeing the Analyst's answer.
- A **human reviewer** who looks at any disagreement and decides whether to publish.
- An **audit record** kept alongside every published claim showing which AI did what, which sources were used, and who reviewed.

**Trust beats to land.**

- A claim is **blocked** rather than published if fewer than four credible sources can be found.
- The two AIs cannot collaborate. If they disagree, that surfaces — it is not silently averaged or hidden.
- Sources are always preserved in archive form, so a published claim does not rot when a webpage changes.
- Publishing requires an explicit human approval step (`dr review --approve`) that is recorded with the claim. Anyone reading the site can see whether a claim was reviewed.

**Suggested visual.** A journey diagram with five stops: *Claim proposed → Sources gathered → Two independent verdicts → Human reviews → Published with audit trail*. Mark blocked / failure paths with diversions, not dead-ends.

**Vocabulary.** Plain English. Use "AI agent" or "AI worker," not "LLM." Avoid words like sidecar, semaphore, schema. Say "saved evidence" rather than "archived URL."

**Omit.** Anything about model classes, code packages, or CLI commands. The decomposed researcher internals. CI/build gates.

---

## Brief 4 — Audience: a curious adult reading dangerousrobot.org *(the actual end user; this is the most critical brief)*

**Goal.** Help a thoughtful but non-technical site visitor — someone deciding whether to trust a green AI claim, a privacy claim, or a safety claim on the site — see in one image *how the claim they are looking at got there*. They are not here to learn AI; they are here to decide whether to believe what they read.

**Core message.** "Every claim on this page was researched by AI workers, double-checked by a different AI, reviewed by a person, and is dated so you know how fresh it is."

**What to show.**

- A *claim card* on the left — the same kind of card the visitor just read on the site, with a verdict (true / mixed / false / etc.) and a confidence level.
- An arrow back in time showing how the claim was made:
  1. **Sources are collected** (at least four). The system saves a permanent copy so the link will not break later.
  2. **An AI writes a verdict and a short explanation, citing the sources.**
  3. **A different AI checks the same sources and writes its own verdict** — without seeing the first one.
  4. **A person looks at the result.** If the two AIs disagreed, the person decides which to trust.
  5. **The claim is published** with a date, the sources, and a "Reviewed by" label.
- A *recheck* loop: every claim has an expiration. After it expires, the cycle starts again so the page does not go stale.

**Trust elements to spotlight.**

- The verdict scale (true → mostly-true → mixed → mostly-false → false → unverified) is shown as a strip of badges so readers know what each label means.
- The "Reviewed" badge means a person has signed off; "Unreviewed" means the claim was published but no individual reviewer signed it yet.
- "Blocked" claims (those without enough evidence) never get published as facts.

**Suggested visual.** A short comic-strip-style horizontal flow with five panels, ending in the claim card the user just read. Use everyday icons: a magnifying glass (search), a folder with a lock (archived sources), two robots facing away from each other (independent evaluation), a person with a checkmark (review), a calendar (recheck).

**Vocabulary.** Conversational, second-person ("the claim you're reading," "the date you see"). No engineering terms. "AI agent" → "AI worker" or just "the AI." Avoid "audit," "sidecar," "pipeline."

**Tone.** Reassuring without being marketing-y. Honest about limits: the AIs can be wrong, that is why a person reviews.

**Omit.** Anything internal: model classes, search backends, CI, CLI commands, `blocked_reason` enums. Nothing about arXiv vs Tavily. Nothing about phase fields.

---

## Brief 5 — Audience: a 5th grader (≈10 years old)

**Goal.** Help a curious kid understand that the words on this website did not just appear — they came from a careful process where two computer helpers and a grown-up worked together.

**Core message.** "A computer looks things up. Two AI helpers each write down what they think the answer is. A grown-up double-checks. Then it gets posted."

**What to show.**

- **The Question.** A speech bubble: "Is this AI company really good for the planet?"
- **The Detective.** A character (could be a robot with a magnifying glass) goes out to find evidence. It needs to find *at least four* good clues. If it cannot, it stops and says "Not enough proof yet" — and nothing gets posted.
- **The Library.** All the clues get filed away so they can be looked at again later, even if the original sign falls down.
- **Two Helpers, Same Question.** Two AI helper characters each read the clues *on their own* and write down the answer. They are not allowed to peek at each other's work.
- **The Grown-up.** A person looks at both answers. If the helpers agree, great. If they disagree, the grown-up decides what is right.
- **The Sticker.** Once approved, the answer gets a "Checked!" sticker and a date, and goes on the website. After a while, the date gets old and the whole team starts over so the answer stays fresh.

**Things to spotlight.**

- Two AI helpers, not one. They do not share answers.
- A person is always the last word.
- Every answer has a date.
- "Not enough proof" is allowed. The system would rather say "we don't know" than guess.

**Suggested visual.** A picture-book / storybook layout, five scenes left to right, each with one cartoon character and a one-sentence caption. Bright friendly colors. Use a question-mark symbol for "blocked" outcomes so kids see "no answer" is a real choice.

**Vocabulary.** Short sentences. Words a 5th grader knows: clues, helpers, grown-up, library, sticker, fresh. Avoid: AI model, source, verdict, evaluator, audit, pipeline, schema. Say "answer" instead of "verdict," "clues" instead of "sources," "double-check" instead of "evaluate."

**Omit.** Everything technical. The state machine. The CI gates. The recheck mechanism beyond "we do it again so it stays fresh."
