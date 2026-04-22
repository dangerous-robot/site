# Work Item: CI Pipeline

**Phase**: 3 (CI & Quality -- post-MVP)
**Status**: not started
**Depends on**: Phase 2 (content exists to validate)
**Blocks**: nothing (quality improvement, not functionality)

## Goal

PR checks that validate content quality beyond what Astro's build-time Zod validation catches. The build check (`npm run build`) already enforces schema correctness via Content Collections -- CI adds linting and referential integrity.

## What Astro Already Provides (no extra work)

- **Schema validation**: Zod schemas in `src/content.config.ts` reject invalid frontmatter at build time. If a claim has an invalid `verdict` value or a missing `entity` field, `npm run build` fails. This is the primary quality gate.

## What CI Adds

- **Build check**: `npm run build` must pass (catches schema + template errors)
- **Markdown lint**: Style consistency across content files
- **Citation integrity**: Every source slug referenced in a claim's `sources[]` array corresponds to an existing file in `research/sources/`

## Tasks

- [ ] Create `.github/workflows/ci.yml` triggered on PRs:
  ```yaml
  jobs:
    check:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-node@v4
          with: { node-version: 22, cache: npm }
        - run: npm ci
        - run: npm run build          # schema + template validation
        - run: npx markdownlint-cli2 "research/**/*.md"
        - run: npx tsx scripts/check-citations.ts
  ```
- [ ] Add `markdownlint-cli2` as dev dependency
- [ ] Create `.markdownlint.jsonc` config (reasonable defaults, allow YAML frontmatter)
- [ ] Write `scripts/check-citations.ts`:
  - For each claim file, check that every slug in `sources[]` has a corresponding file
  - Report mismatches with file path and field
  - ~50 lines, no external deps beyond `gray-matter` for frontmatter parsing
- [ ] Add npm scripts: `"lint:md"`, `"check:citations"`, `"check"` (runs both)

## Explicitly Deferred

- **Custom schema validation script** (`validate-schemas.ts` with `ajv`): Not needed. Astro's Zod validation at build time catches these errors. Add JSON Schema + `ajv` only if PydanticAI agents need a shared schema format (Phase 4).
- **Link checking** (`lychee`): Too slow for PR CI. Add as a separate weekly scheduled workflow when content volume justifies it.
- **Stale claim detection** (`next_review_due` check): Belongs in automation (Phase 5), not PR CI.

## Design Decisions

**`tsx` for scripts**: Use `tsx` (esbuild-based) to run TypeScript scripts directly. Add as a dev dependency. Simpler than a compile step, fast enough for CI.

**Citation integrity as a script, not a PydanticAI agent**: This is deterministic file-checking logic. No LLM needed. Runs in ~1 second. Keep it as a Node script in the existing TS toolchain.

## Open Questions

1. **Python in CI**: When Phase 4 adds PydanticAI agents, CI will need a Python setup step. Not needed now, but note for future.

## Estimated Scope

Small. The CI workflow is straightforward. The citation check script is ~50 lines.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (cursory review) | completed-check | Added review history section; status is "not started" but file is in completed/; all tasks remain unchecked (5 items) |
