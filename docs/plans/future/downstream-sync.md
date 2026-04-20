# Work Item: Downstream Sync to TreadLightly

**Phase**: 5 (if needed)
**Status**: not started
**Trigger**: parallax-ai is ready to consume structured data from this repo
**Depends on**: Phase 2 (schemas and content exist)

## Goal

TreadLightly's parallax-ai site consumes research data from this repo at build time.

## Prerequisite: Discovery Spike

Before this plan can be executed, understand parallax-ai's build process:
- What data shape does it need? (TypeScript interfaces, JSON, raw Markdown?)
- Where in its build does it consume external data?
- What triggers a rebuild?

This spike can happen anytime -- it's independent of dangerousrobot.org's phases.

## Tasks

- [ ] Discovery spike: understand parallax-ai's build and data needs
- [ ] Define the TS data contract (shared types/interfaces)
- [ ] Build `scripts/generate-data.ts`:
  - Reads claim files from `research/claims/`
  - Outputs typed TS data files for parallax-ai
  - Runs standalone or as part of `npm run build`
- [ ] Determine sync mechanism:
  - **Option A (simple)**: parallax-ai CI clones this repo at build time
  - **Option B (clean)**: This repo publishes generated data as a release artifact
  - Start with Option A; upgrade to Option B if coupling becomes a problem
- [ ] Wire parallax-ai CI to consume the data

## Design Decisions

**Page builder as TS script**: No LLM reasoning needed -- pure data transformation. Lives in `scripts/`, not in the PydanticAI agent directory.

**Start simple**: Clone-at-build-time (Option A) works today with zero infrastructure. Don't build artifact pipelines until the data contract is stable.

## Open Questions

1. **parallax-ai build process**: Not yet investigated. Blocks execution of this plan.
2. **Rebuild trigger**: Should parallax-ai rebuild when this repo updates? (`repository_dispatch`, scheduled, or manual?)

## Estimated Scope

Medium. The generate-data script is the main work. CI integration depends on parallax-ai's setup.
