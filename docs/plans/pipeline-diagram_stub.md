# Pipeline diagram

**Status**: Stub (design spec settled; implementation steps and the format choice still open)
**Last updated**: 2026-10-06
**Roadmap**: `docs/v1.0.0-roadmap.md` RE-G (Pipeline diagram)

A static diagram of the research pipeline for the methodology answer on `/research`. It gives a first-time reader a picture of how a claim gets from a question to a published verdict, and makes the human step visible. The prose steps already describe the pipeline; the diagram is a reader aid, not a blocker.

The design spec below is lifted from the local draft `v0.1.0-mvp-definition.md` §6 (2026-04), updated to the agents and commands in `pipeline/` today. An earlier version of this stub described a Router, an Orchestrator lane and an "Evaluator"; none of those exist as agents (`pipeline/` has `researcher`, `ingestor`, `analyst`, `auditor`, and the `orchestrator` runs them in order), and the Router is post-v1 in `docs/UNSCHEDULED.md`.

---

## Flow

Top to bottom, so it fits a phone without horizontal scroll:

```
[Question]            human: claim text + entity + criterion
    |
[Researcher]          finds candidate sources (web search; arXiv for academic topics)
    |
[Ingestor]            fetches each source (archive.org copy when the live page fails), writes a source file
    |
    +--> [Blocked]    fewer than 2 usable sources, a fetch error, or an analyst error
    |
[Analyst]             weighs the evidence, drafts verdict, confidence and narrative
    |
[Auditor]             checks the draft against the sources; flags disagreement
    |
[Human review]        human: `dr review --approve`, or revise, or archive
    |
[Published verdict]   status `published`, reviewer named on the page
```

Facts behind each node, checked 2026-10-06:

| Node | Source in HEAD |
|---|---|
| Researcher, Ingestor, Analyst, Auditor | `pipeline/researcher/`, `pipeline/ingestor/`, `pipeline/analyst/`, `pipeline/auditor/` |
| Blocked branch | `BlockedReason` in `pipeline/common/models.py:106` (`insufficient_sources`, `terminal_fetch_error`, `analyst_error`); claim `status` enum includes `blocked` (`src/content.config.ts:197`) |
| Auditor output | sidecar `analyst_verdict`, `auditor_verdict`, `needs_review` (`pipeline/orchestrator/persistence.py:484-490`) |
| Human review | `dr review` (`pipeline/orchestrator/cli.py:1807`): `--approve` flips draft to published, `--archive` flips published to archived; reviewer shown by name via `src/lib/reviewers.ts` |

## Edges: what passes between steps

| Edge | Data |
|---|---|
| Question → Researcher | Claim text, entity slug, criterion slug |
| Researcher → Ingestor | Candidate source URLs |
| Ingestor → Analyst | Stored source content, key quotes, source type and independence |
| Analyst → Auditor | Draft verdict, confidence, narrative |
| Auditor → Human review | Draft claim file plus audit sidecar (both verdicts, `needs_review`) |
| Human review → Published verdict | `status: published`, `human_review` block filled |
| Human review → revise | Notes; likely a re-run (`dr claim-refresh`) or a hand edit before approval |

## Visual treatment

- Automated steps (Researcher, Ingestor, Analyst, Auditor): one plain node style.
- Human steps (Question, Human review): the site accent color or a dashed border.
- Decision after Human review: a branch, not a diamond-heavy flowchart.
- Blocked: a side branch, labeled, in a muted style.
- Published verdict: terminal node with a distinct "done" style.
- Label nodes by role (Researcher, Analyst), not "AI agent"; the prose above the diagram already says AI agents draft and a person approves.

## Format and placement

- **Format**: inline SVG preferred over Mermaid. It uses the CSS tokens in `src/styles/tokens.css` (light, dark, high contrast) and needs no script, which keeps the page free of third-party requests (`src/layouts/Base.astro:2`). Mermaid text is easier to edit but needs a render script or a build step.
- **Placement**: inside `<details id="methodology">` on `/research` (`src/pages/research/index.astro:215`), directly under the "How a claim is published" list. The FAQ page the original spec named no longer exists.
- **Accessibility**: a text alternative that matches the ordered list (or `aria-describedby` pointing at it).

## Open before this is implementation-ready

- SVG by hand, or Mermaid rendered to SVG at build time.
- Whether the diagram is worth the space while Research is out of the primary nav (decisions 2026-10-05). It could wait for the Responsible AI chatbots effort (roadmap item SITE-J), if that page links to the methodology answer.
- Test plan: rendered-page check in light, dark and high-contrast modes at phone width; `inv check` passes.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §6 |
| 2026-10-06 | agent (claude-opus-5-5, plan review) | rewrite | Lifted the design spec from the local draft `v0.1.0-mvp-definition.md` §6; replaced the Router/Orchestrator/Evaluator flow with the agents in `pipeline/`; placement moved from the old FAQ page to `/research#methodology`. Still a stub. |
