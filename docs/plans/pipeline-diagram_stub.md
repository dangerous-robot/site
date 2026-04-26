# Pipeline diagram

**Status**: Stub
**Last updated**: 2026-04-22

A static diagram of the research pipeline is needed to accompany the FAQ methodology description. This is a design/documentation task and is not a v0.1.0 blocker — the FAQ text describes the pipeline adequately for now. The full spec is in `drafts/v0.1.0-mvp-definition.md §6`.

---

## Scope

**Format**: Static SVG or Mermaid flowchart. SVG preferred for CSS token compatibility (light/dark/high-contrast themes).

**Flow**: Intake (criterion / entity / source) → Router (dispatch + small classifications) → Orchestrator (lifecycle) → Researcher → Ingestor → Analyst → Evaluator (open-loop) → Human Review → Published verdict

**Visual treatment**: Human checkpoints rendered in accent color to distinguish them from automated pipeline steps.

**Placement**: Inside the FAQ "What methodology is used for research?" accordion.

**Notes for the diagram author**:

- Router and Orchestrator should appear visually distinct from the linear pipeline steps (e.g., as control-plane lanes around the pipeline rather than steps inside it).
- "Open-loop" is the deliberate choice: the Evaluator does not feed back into the Analyst in v1; disagreements surface to Human Review.
- The `blocked` side-branch from Orchestrator (when `< 2` usable sources) should appear as a labeled fork.
- Use the term "verdict" for the published artifact (combined post-review), not "Published Claim".

---

## Implementation

TBD

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §6 |
