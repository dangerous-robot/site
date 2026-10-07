# Priorities

**Status**: Confirmed by Brandon, 2026-10-07  
**Last updated**: 2026-10-07

The project's themes, highest first. Each names the work that serves it and the source that sets it. Status stays in the active roadmap ([`v1.0.0-roadmap.md`](v1.0.0-roadmap.md)) and [`UNSCHEDULED.md`](UNSCHEDULED.md). Who changes this file, and when: `AGENTS.md` § Priorities.

How to read it:

- A known security issue goes first in every release, ahead of every theme below.
- When two pieces of work compete, the one serving the higher-ranked theme goes first.
- A roadmap item takes the rank of the theme whose `Work:` line names it; work listed under that item shares its rank. A backlog item takes the rank of the theme in its triage marker. A roadmap item no `Work:` line names takes the rank of the theme it fits; propose adding it to that line.
- Work that fits no theme ranks below every theme. It still has to pass the focus test (`AGENTS.md` Plans & Backlog rule 8) before it is scheduled.
- An entry marked "(Proposed, Brandon to confirm)" keeps its listed place; any answer that depends on it says so.

## Ranked

1. **Responsible AI chatbots, backed by claims.** Work: SITE-J (Responsible AI chatbots) and the prerequisites listed under it in the roadmap. Source: [`decisions.md`](decisions.md) 2026-10-06, "Next large effort".
2. **Security, a deeper analysis.** Work: `UNSCHEDULED.md` "Security follow-ups" (the deeper security analysis row), OPS-K (Separate agent credentials). Known issues found by the analysis go first in a release (rule above). Source: [`decisions.md`](decisions.md) 2026-10-07.
3. **Refocus foundation, finished.** Work: `UNSCHEDULED.md` "Refocus foundation completion" (required refocus updates first, then contradiction scan, sparse research areas, SEO updates), "SEO post-restructure follow-ups". Builds on SITE-I (The refocus) ([`plans/completed/refocus-foundation.md`](plans/completed/refocus-foundation.md)). Source: [`decisions.md`](decisions.md) 2026-10-07.
4. **Simplicity and clarity, including good observability.** Work: `UNSCHEDULED.md` "Pipeline observability", "Pipeline code-quality refactors". Applies to the pipeline, agent tooling and these planning docs alike: fewer moving parts, plainer docs, runs you can see into. Source: [`decisions.md`](decisions.md) 2026-10-07.
5. **Performance and cost.** Work: `UNSCHEDULED.md` "Pipeline performance & hardening", "Analyst decomposition (cost lever)". Source: [`decisions.md`](decisions.md) 2026-10-07.
6. **Reader participation and a visible method.** Work: RE-D (Research contribution paths), RE-G (Pipeline diagram). Source: [`decisions.md`](decisions.md) 2026-10-07; [`mission-and-voice.md`](mission-and-voice.md) § How the site works ("Corrections are public").

## Not a priority now

Deferred work: the roadmap's § Deferred and the "Deferred plans" section of `UNSCHEDULED.md`. Reason, from the roadmap: "operator throughput, not reader value".
