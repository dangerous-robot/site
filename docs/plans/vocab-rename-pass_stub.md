# Vocabulary cohesion deeper pass

**Status**: Stub
**Priority**: Urgent (operator-flagged 2026-04-24 as "most important and very urgent"); v1
**Last updated**: 2026-04-24

A focused pass to reduce vocabulary fragmentation across roles, agent names, CLI commands, schema fields, and content frontmatter. Goal: a contributor reading AGENTS.md + glossary should grasp the system in 10 minutes.

## Why now

- Pre-launch is the last cheap moment to rename. No external readers, no inbound links, no command-history habits to break (operator answer to Q5: "change anything now").
- Three concrete known overloads:
  - "audit" means three things (audit sidecar / Citation Auditor / Auditor agent).
  - "research" overlaps as a CLI command name (`dr research`) and a role (Researcher).
  - "auditor" vs "Citation Auditor" reads as the same concept but is two unrelated jobs.
- Operator flagged the language as confusing during triage and prioritized this ahead of nearly everything else.

## Prerequisites

These should land or be in flight before this pass executes safely:

1. **Acceptance test fixture** ([`acceptance-test-fixture_stub.md`](acceptance-test-fixture_stub.md)). Without a known-good case (Anthropic/Claude per Q8), a rename can break the pipeline silently. The fixture is the regression check.
2. **Quick-fix renames** (P1: Citation Auditor → citation check; P2: `dr research` → `dr verify-claim`) in [`pre-launch-quick-fixes.md`](pre-launch-quick-fixes.md). These are the two known overloads. Land them first; this stub addresses what the inventory turns up beyond those.
3. **Multi-provider POC decision** ([`multi-provider-poc.md`](multi-provider-poc.md)). If the POC is mid-flight, that plan references several pipeline files. Either complete the POC first, or include POC-touched files in the inventory and rename atomically.

## Scope (TBD until inventory done)

### Stage 1 — Inventory

Grep-driven list of every overloaded or footgun term and where it appears.

Surfaces to inventory:

- `pipeline/` Python: module names, class names, agent names, function names
- CLI subcommands (`dr ...`)
- `src/content.config.ts`: Zod schemas, collection names, field names
- `research/` content: frontmatter fields, file paths, queue file names
- `docs/`: AGENTS.md, glossary, plans, README, architecture docs
- `pipeline/*/instructions.md`: agent self-references
- Test names

Output: a Markdown table per term showing current location, occurrence count, and proposed new name.

### Stage 2 — Rename decisions

For each row in the inventory, decide:

- New name (or "leave as-is")
- Whether the rename touches schema (cascades to research content + Pydantic mirror)
- Whether the rename touches URLs/routes (cascades to redirects, but pre-launch the cost is low)
- Whether the rename is reversible without re-running the pipeline

### Stage 3 — Sequence and execute

Renames that touch schema + content must land atomically (per the [`criteria-rename_stub.md`](criteria-rename_stub.md) precedent). Renames that touch only docs can ship as separate PRs. Sequencing question: do all schema renames in one branch, or one rename per branch with the acceptance fixture run between each?

### Stage 4 — Verify

- Run acceptance test fixture (P4).
- Build site (`inv build`).
- Run `dr lint`, pipeline unit tests.
- Re-run `dr verify` on the fixture claim and compare verdict + audit sidecar against the locked-in expected values.

## Open design questions

- **Inventory format**: spreadsheet, Markdown table, or JSON? Markdown table is most reviewable and version-controllable.
- **Rename target naming convention**: do we adopt a domain-specific style (e.g., "agent" suffix on all PydanticAI agents, "check" suffix on all CI verifications) or keep names diverse? A convention helps consistency but can read robotic.
- **Glossary as authority**: should glossary.md become the single source of truth that the inventory cross-checks against, or is the inventory the new authority? Probably the latter, with glossary regenerated from it.
- **Routes**: pre-launch URL renames are cheap. Should this pass also rationalize `/criteria`, `/topics`, `/companies`, `/products`, `/sectors` (no route yet), `/entities`?

## Out of scope

- The two already-known renames (P1 Citation Auditor, P2 `dr research`) — those land in `pre-launch-quick-fixes.md`.
- New features.
- Any rename that requires retraining or significant prompt rewriting.

## Critical files

To be populated by Stage 1.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-24 | agent (claude-opus-4-7) | initial stub from triage | Scaffolded with prerequisites identified per operator question |
