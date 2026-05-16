# Architectural Vision: The Project as a State Machine

## Framing

This project already behaves like a state machine, but only implicitly. Claims move through lifecycle states (draft, blocked, published, archived) and transient pipeline phases (researching, ingesting, analyzing, evaluating). Entities and sources have their own lifecycles (proposed, active, flagged, retired). Operators intervene at well-defined checkpoints. The vision is to make this implicit structure explicit, and to treat it as the central organizing model for the whole system.

By "state machine" we mean the union of three things: the **claim lifecycle** (the durable status of a research output), the **pipeline phase** (where a claim currently sits in the four-agent process), and the **operator decision points** (the human-in-the-loop transitions that the pipeline is forbidden from auto-resolving). Together these form a single graph of named states and named transitions. Every agent action is a transition. Every operator review is a transition. Nothing moves without being a transition.

## Current shape

The pieces that already exist:

- **Claim status** (`draft | blocked | published | archived`) with a `blocked_reason` enum captures durable lifecycle.
- **Claim phase** (`researching | ingesting | analyzing | evaluating`) captures transient pipeline position.
- **General object lifecycle** (`proposed | active | flagged | retired`) applies to entities and sources.
- **Queue lifecycle** (intake, operator action, written, removed) captures candidate flow.
- **Audit sidecar** (`.audit.yaml` schema v1) records the most recent pipeline run, both verdicts, agreement flag, and human review block.

What is missing is a unified statement that these are facets of one model, and a discipline that every change to any of them is a named, recorded transition.

## Vision: five principles

**1. Small atomic transitions.** Every agent action is one minimal state change with explicit pre-conditions (what must be true to start) and post-conditions (what must be true on success). A Researcher does not "investigate a claim"; it advances `phase: researching` to `phase: ingesting` after writing a sources-consulted list. An Analyst does not "produce a verdict and audit"; it writes a verdict given inputs that already satisfy a pre-condition. Small transitions match small models: each step is sized for the smallest model that can perform it correctly.

**2. Transitions are first-class records.** State changes today are implicit in commit diffs and the audit sidecar's latest run. The vision is an append-only transition log per claim, recording cause (agent or operator), inputs read, outputs written, and resulting state. This is the substrate the improvement plan calls on for recheck history and supersession (see `docs/plans/research-outputs-improvement-plan.md`).

**3. Open-loop at decision points.** Certain transitions are reserved for the operator: Analyst/Evaluator disagreement, novel blocked reasons, supersession of a published verdict. The pipeline halts and surfaces the question; it never auto-resolves. This is already the project's stance; the state-machine framing makes the halt points enumerable rather than ad-hoc.

**4. Build-time validation.** Invariants belong in CI, not only in runtime checks. A claim with `verdict: supported` and zero sources should fail the build, not be quietly corrected. Staleness past `recheck_cadence_days` should fail or warn at build time. Zod in `src/content.config.ts` is the schema authority; transition rules should compile down to checks that run alongside it.

**5. Composable, not orchestrated.** Agents read state, do one thing, write state. There is no monolithic orchestrator that "runs the pipeline." The pipeline is what emerges when small agents respond to states they recognize. A new agent that handles a new phase plugs in by recognizing a pre-condition and writing a post-condition; no central registry needs editing.

## Scheduled agents and the orchestration question

A composable state machine raises an obvious question: who ticks it? If agents only act when a pre-condition is met, something has to notice that a pre-condition is met. Today that something is the operator typing a command. A natural next step is scheduled cloud agents (Cloudflare Workers with Cron Triggers, or equivalent) that observe state and either alert or nudge.

Three roles such agents could play, in increasing intrusiveness:

- **Observe.** A scheduled Worker reads the published research tree (via GitHub, an R2 mirror, or a built index), checks invariants (claims past `next_recheck_due`, claims in `blocked` longer than N days, queue depth, sidecar staleness), and emits alerts: an issue, a Slack ping, a status page. No state is changed.
- **Nudge.** The same Worker, on finding a transition that should fire (a claim due for recheck, a queue item old enough to escalate), dispatches a GitHub Action or webhook that triggers the existing Python pipeline. The Worker does not run the LLM work; it requests it. Pre/post-conditions still live in the pipeline.
- **Execute.** Workers run the agent calls themselves, write back to the repo (or a D1/R2 store), and close the loop without operator involvement. This is the orchestration layer; it is also where simplicity is at greatest risk.

How much does this change the current plan? **Very little, by design.** The five principles already accommodate it: if every transition has explicit pre/post-conditions and a recorded outcome, the question of *what triggers the transition* is decoupled from the question of *what the transition does*. The same agent code runs whether a human, a GitHub Action, or a Cron Trigger called it. Build-time validation still gates publication regardless of who pressed the button.

**Should these questions be settled now? No.** Ad-hoc scheduled actions can start at Observe (lowest cost, highest immediate value, reversible) and evolve as the state machine fills out. A premature orchestration layer is the failure mode this vision is written against: it would re-introduce the implicit transitions and central coordinator the principles reject. The recommended posture: build the transition substrate first (Audit Trail Phases 2 and 3, build-time validation), let scheduled Observe agents accumulate against that substrate, and only consider Nudge or Execute when the same nudge has been performed manually enough times to have a known shape.

What this implies for near-term work: nothing new needs to be planned to keep this path open. The Phase 2 and Phase 3 audit-trail work, plus the build-time staleness gate, are exactly the substrate a scheduled agent would read against. Decide later whether the ticker is a Cron Trigger, a GitHub Actions schedule, or an operator's daily routine.

## Trade-offs and what this is not

This is not BPMN, not a workflow engine, not event sourcing in the database sense. We are not adopting a runtime. The state machine lives in the file shapes (frontmatter, sidecars, transition log entries) and in the CI checks. Costs: more discipline about naming states and transitions; some upfront work to migrate implicit transitions into recorded ones. Benefits: a researcher reading the repository can answer "what is the state of this claim and how did it get there" without reading agent code.

## Near-term direction

- **Audit Trail Phase 2 and Phase 3** (`docs/plans/audit-trail-extensions.md`) extends sidecars with the fields a transition log needs, and introduces append-only recheck history.
- **Build-time staleness gate**, the first CI invariant in the state-machine spirit.
- **Verification-level taxonomy** (`multiply-verified | independently-verified | partially-verified | self-reported | claimed`) names a state currently inferred from source independence.
- **Schema migration log**, required for transitions of the schema itself.
- **Decision-chain visibility**, surfacing sub-agent model choices so transitions are not opaque.

## Review history

| Date       | Reviewer                | Notes         |
|------------|-------------------------|---------------|
| 2026-05-16 | Claude (planning agent) | Initial draft |
