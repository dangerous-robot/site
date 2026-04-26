# Pre-launch open questions

Status: open as of 2026-04-24, derived from the pre-launch triage. Captures questions for operator decision and broader discussion. Each question carries enough context to act on independently. Closed questions are recorded at the bottom for context.

---

## Currently open

### Q2. Polarity normalization

Should claim titles be rewritten so TRUE = "better" reads consistently? Operator preference is yes ("X excludes wasteful features" rather than "X has wasteful features"). Tradeoffs:

- **For**: a reader scanning the homepage gets a quick "more green checks = better" signal.
- **Against**: forced polarity produces awkward titles or loses nuance ("no training" loses the caveat that some training is permitted).

Cleaner alternative being implemented in v1: keep claim text natural; expose a separate "what this means for the reader" line under the badge ([`pre-launch-quick-fixes.md`](plans/pre-launch-quick-fixes.md) S8). Decide after that ships whether full polarity normalization is still wanted.

### Q3. Trust metadata: who scores the four axes?

Site trust, marketing-vs-research, authority, COI. Each axis has a different best-scorer:

- Site trust → agent-classifiable from publisher signal.
- Marketing vs research → agent-classifiable from document signal.
- Authority → operator + agent hybrid; subject-matter authority is hardest.
- COI → operator judgment.

Decision feeds Stage 1 of [`source-trust-metadata_stub.md`](plans/source-trust-metadata_stub.md).

### Q4. Model-tier rubric: how is "small-by-default" enforced?

Stated as a principle (P3 in [`pre-launch-quick-fixes.md`](plans/pre-launch-quick-fixes.md) adds it to glossary), but not yet enforced. Options:

- (a) Instructions only — Claude is told to prefer small.
- (b) Per-agent model caps in config — `pipeline/orchestrator/cli.py` or `VerifyConfig` enforces tier ceilings.
- (c) Cost-per-claim ceilings with escalation gates.

Option (b) is the cheapest enforceable form. Decision feeds the audit sidecar `models_used` display (S6) and Part 2 of [`multi-provider.md`](plans/multi-provider.md).

### Q12. v1 feedback channel: what ships?

Operator answer: v1 unclear; full solution is v2 ([`public-feedback.md`](plans/public-feedback.md)).

v1 minimums under consideration:

- GitHub issue templates only (already on roadmap).
- GitHub issue templates + mailto fallback for non-GitHub users.
- Skip v1 entirely; rely on the alpha banner to suggest "talk to me directly."

Decision needed before launch since it determines whether S9 footer links include a "Feedback" item.

---

## Open in the long term

### Q11. Show-your-work reasoning panel: scope and depth

Per operator: partially implemented; another agent improving. Out of scope for re-decision here. Tracked open scope:

- Inline analyst narrative on every claim, or expand-on-click?
- Auditor disagreement excerpts always visible, or only when verdict was contested?
- Prompt visibility (the actual instruction text the analyst saw)?

Currently treated as in flight.

---

## Closed (operator answers, 2026-04-25)

- **Q1 — Reader test scope**: source list + audit sidecar + reader-takeaway is sufficient for v1; ST1 trust metadata defers to v2. (Uses "audit sidecar" — the current carrier name; the canonical-verdict-artifact rename is deferred per UNSCHEDULED.)
- **Workflow + vocab decisions** (per [`plans/v0.1.0-vocab-workflow-landing.md`](plans/v0.1.0-vocab-workflow-landing.md)):
  - Object types locked at four: criterion, entity, source, claim.
  - Intake set locked to criterion / entity / source (claim is output-only).
  - Item 3 resolved to option (a) split: Orchestrator (lifecycle) and Router (dispatch) are named as two distinct roles.
  - Internal design principle "Small decisions, small models." adopted; public `/values` variant captured for landing on the values page.

---

## Closed (operator answers, 2026-04-24)

- **Q5 — Vocab churn budget**: change anything now. Pre-launch is the cheap moment.
- **Q6 — Brand alignment with TreadLightly**: DR is its own thing. May feed TL but that is not its purpose. Additional sponsors welcome.
- **Q7 — Onboarding scale**: semi-automated, mostly manual for now. Operator queue + batch workflow is v2.
- **Q8 — Acceptance test fixture entity**: Anthropic / Claude.
- **Q9 — `/values` page**: editorial, uncited; cross-link to relevant claim categories.
- **Q10 — Launch curation**: random selection.

---

## Process-level concerns surfaced during triage

These don't need decisions but are recorded for awareness:

- "Audit" overloaded three ways (audit sidecar / Citation Auditor / Auditor agent). Two of three are addressed in [`pre-launch-quick-fixes.md`](plans/pre-launch-quick-fixes.md) (P1 + P2). The third (Auditor agent vs audit sidecar) may still be confusing; revisit during the [vocab rename pass](plans/vocab-rename-pass_stub.md).
- Plan sprawl: 20+ plans pre-launch is heavy for a solo operator. Cleanup pass scheduled in P5.
- Roadmap mixes hard blockers and nice-to-haves; P5 separates them.
- Vocabulary fragmentation across roles, agent names, CLI commands; addressed systematically in [`vocab-rename-pass_stub.md`](plans/vocab-rename-pass_stub.md).

---

## When to delete this doc

When all "currently open" questions have been answered or moved into specific plan stubs. Q11 and the closed list can be archived to git history.
