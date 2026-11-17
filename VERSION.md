1.0.0-beta.10

Pre-release stage (toward 1.0.0):
- `beta.N`: a deployed release before 1.0.0. Content, features and schema may still change. Each beta release bumps N.
- `1.0.0`: the beta label is dropped, by Brandon's call. There are no alpha or rc stages in this line.

Use dotted numeric identifiers (`beta.3`, `beta.4`) so they sort numerically. Tag each push of `main` (`v1.0.0-beta.3`).

A site push takes a fourth number (`beta.6.1`), which sorts between `beta.6` and `beta.7`, so the planned beta keeps its name. It is allowed only when nothing but site files changed since the last tag. A push that carries any research, pipeline or claim change is a beta release and takes the next N. The weekly rebuild changes neither number. Rules and checks: `docs/runbook.md` § Releasing.

History: 1.0.0 did not ship. `1.0.0-beta.2` was the last build deployed before the refocus; the repo briefly used `1.1.0-alpha.1` (2026-10-02 to 2026-10-04) and was reset to `1.0.0-beta.3`.

Version semantics (post-1.0):
- Major: breaking change to verdict enum, criterion definitions, or entity URL structure
- Minor: new entity type, new criterion, new feature shipped
- Patch: content corrections, verdict updates, bug fixes, source additions

Before 1.0.0 the same three kinds classify each change for release triage (AGENTS.md § Agent workflow tooling), but none of them changes the version number; only a push does (a beta release bumps N, a site push adds a fourth number). A patch goes to the active roadmap. A minor rides the next beta, waits for a later beta, or goes to the backlog (ask). A major is a question for Brandon, not an automatic new release line.

The first line of this file and the "Active release:" line are read by `scripts/release-gate/`. Keep both formats as they are.

Active release: docs/v1.0.0-roadmap.md
Future release plans live at docs/v{semver}-roadmap.md.
