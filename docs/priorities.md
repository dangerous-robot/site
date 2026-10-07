# Priorities

**Status**: Confirmed by Brandon, 2026-10-07  
**Last updated**: 2026-10-07

The project's themes, highest first. Each names the work that serves it and the source that sets it. Status stays in the active roadmap ([`v1.0.0-roadmap.md`](v1.0.0-roadmap.md)) and [`UNSCHEDULED.md`](UNSCHEDULED.md). Who changes this file, and when: `AGENTS.md` § Priorities.

How to read it:

- A known security issue (defined in § Known security issues) goes first in every release, ahead of every theme below.
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

## Known security issues

A known security issue is a weakness someone could use today, in something this project runs or publishes, whose fix needs no major-version upgrade. It jumps the queue. Other security work ranks under the Security theme.

Counts, when present now:

- Petition signer data (D1, exports) or reader data readable, changeable or kept in a way `/privacy` does not say, by anyone but Brandon.
- A secret, API key, token or private email in the repo, build output, logs or a place an agent or the public can read.
- A way for an outsider to change what dangerousrobot.org serves or runs: the deploy workflow, third-party GitHub Actions, Cloudflare settings, the Workers code or its endpoints.
- A Workers endpoint that allows something it should not, or that cannot stop abuse.
- A dependency advisory rated high or critical in code the site, Workers, pipeline or CI runs. In the pipeline, which handles fetched web content, a medium one counts too. Elsewhere, a lower one counts when its vulnerable code handles untrusted input here (say which).
- Published claims, verdicts or sources that pipeline output or fetched content can change without a person's review.

Does not count: an advisory in code this project never runs (write down why); hardening with no present weakness, such as narrower agent credentials (OPS-K), monitors, scans and security docs; anything whose fix needs a major-version upgrade (the Astro 7 upgrade with the `astro` AVIF and `sharp` advisories waits until after 1.0.0). Major-upgrade fixes are re-checked by the deeper security analysis instead.

Test: "Could someone, right now, read signer data, use a secret, change what the site serves or runs, or abuse a Worker, and does the fix avoid a major upgrade?" Yes to both: known security issue. Unsure whether it is a security issue at all: treat it as one and say why.
