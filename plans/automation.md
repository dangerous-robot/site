# Work Item: Automation & Scheduling

**Phase**: 5 (if needed)
**Status**: not started
**Trigger**: Content volume makes manual auditing burdensome; agents from Phase 4 exist
**Depends on**: Phase 4 (agents must exist to automate)

## Goal

Set up recurring automated tasks: citation audits, stale claim detection, and source ingestion queue.

## Tasks

- [ ] Create `.github/workflows/audit.yml`:
  - Scheduled weekly (Monday)
  - Runs citation integrity check + stale claim detection
  - Creates PR with results using `peter-evans/create-pull-request`
- [ ] Implement stale claim checker:
  - Check claims where `next_review_due <= today`
  - Output: list of claims due for review
- [ ] Implement `QUEUE.md` intake workflow:
  - Define QUEUE.md format (append-only with processed/unprocessed flag)
  - On PR merge with QUEUE.md changes, run ingestor for new URLs
  - Ingestor output committed to branch, PR opened for review
- [ ] Pin GitHub Actions by SHA (supply-chain security)
- [ ] Set up Dependabot for dependency updates

## Design Decisions

**GitHub Actions for scheduling**: Since agents are PydanticAI (not Claude Code native), scheduling uses GitHub Actions.

**PR-based output**: All automated changes go through PRs. Human reviews verdicts.

**QUEUE.md format**: Append-only Markdown list. Each entry has a URL and a status (`[ ]` pending, `[x]` processed). Workflow diffs against previous commit to find new entries.

## Open Questions

1. **API key for LLM in CI**: PydanticAI agents need an API key. GitHub Actions secrets, but which provider/key?
2. **Notification**: Stale claim alerts via GitHub Issues, or just a PR?

## Estimated Scope

Medium. Mostly GitHub Actions YAML + connecting existing agent scripts.
