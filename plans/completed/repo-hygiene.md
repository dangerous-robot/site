# Work Item: Repo Hygiene

**Phase**: 1 (Foundation)
**Status**: not started (but partially done in git -- see below)
**Depends on**: nothing
**Blocks**: Phase 2

## Goal

Bring repo documentation and licensing up to date with decisions made. Most of Phase 1 is already accomplished in the working tree.

## Already Done (in git working tree, needs commit)

- Astro scaffolded (`package.json`, `astro.config.ts`, `src/pages/index.astro`)
- CNAME moved to `public/CNAME`
- Root `index.html` deleted (shown as `D` in git status)
- Root `CNAME` deleted (shown as `D` in git status)
- `.github/workflows/deploy.yml` created
- `AGENTS.md` created
- `.gitignore` configured

## Remaining Tasks

- [ ] Update `CLAUDE.md` Project Status to reflect Astro setup, deploy workflow, and current state
- [ ] Update `CLAUDE.md` to remove stale CNAME migration guidance and point plan reference to `plans/BACKLOG.md`
- [ ] Create `LICENSE-CONTENT` with CC-BY-4.0 text
- [ ] Add dual-license note to `README.md`
- [ ] Create `CONTRIBUTING.md` with setup instructions (`npm install`, `npm run dev`) and PR conventions
- [ ] Commit all working tree changes (the already-done items above + new files)

## Explicitly Deferred

- `CODE_OF_CONDUCT.md` -- premature for a single-developer project. Add when external contributors arrive.
- `CODEOWNERS` -- no team to assign to yet.
- `.github/ISSUE_TEMPLATE/` -- add when the site is public and accepting feedback.

## Estimated Scope

Small. ~30 minutes of writing and one commit.
