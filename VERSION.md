1.0.0-alpha.2

Pre-release stages (toward 1.0.0):
- `alpha.N`: roadmap checklist still has open items; schema may still change.
- `beta.N`: checklist complete, schema frozen, bug fixes and content only.
- `rc.N`: would-ship candidate; promote to `1.0.0` if no blockers surface.

Use dotted numeric identifiers (`alpha.1`, `alpha.2`) so they sort numerically.
Examples: `1.0.0-alpha.2` → `1.0.0-beta.1` → `1.0.0-rc.1` → `1.0.0`.

Version semantics (post-1.0):
- Major: breaking change to verdict enum, criterion definitions, or entity URL structure
- Minor: new entity type, new criterion, new phase shipped
- Patch: content corrections, verdict updates, bug fixes, source additions

Active release: docs/v1.0.0-roadmap.md
Future release plans live at docs/v{semver}.md.
