1.0.0-beta.4

Pre-release stage (toward 1.0.0):
- `beta.N`: a deployed release before 1.0.0. Content, features and schema may still change. Each deploy bumps N.
- `1.0.0`: the beta label is dropped, by Brandon's call. There are no alpha or rc stages in this line.

Use dotted numeric identifiers (`beta.3`, `beta.4`) so they sort numerically. Tag each deploy (`v1.0.0-beta.3`).

History: 1.0.0 did not ship. `1.0.0-beta.2` was the last build deployed before the refocus; the repo briefly used `1.1.0-alpha.1` (2026-10-02 to 2026-10-04) and was reset to `1.0.0-beta.3`.

Version semantics (post-1.0):
- Major: breaking change to verdict enum, criterion definitions, or entity URL structure
- Minor: new entity type, new criterion, new feature shipped
- Patch: content corrections, verdict updates, bug fixes, source additions

Before 1.0.0 the same three kinds classify each change for release triage (AGENTS.md § Agent workflow tooling), but none of them changes the version number; only a deploy does (bumps N). A patch goes to the active roadmap. A minor either rides the beta line or waits for after 1.0.0 (ask). A major is a question for Brandon, not an automatic new release line.

The first line of this file and the "Active release:" line are read by `scripts/release-gate/`. Keep both formats as they are.

Active release: docs/v1.0.0-roadmap.md
Future release plans live at docs/v{semver}-roadmap.md.
