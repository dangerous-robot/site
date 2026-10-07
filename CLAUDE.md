# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**For architecture, research schemas, agent roles, and content rules, see [AGENTS.md](AGENTS.md).**

## Project Status

Astro 6.x site with GitHub Actions deploy workflow. Unscheduled work is in `docs/UNSCHEDULED.md`. Release roadmaps live at the top level of `docs/` as `docs/v*.*.*.md` (first release: `docs/v1.0.0-roadmap.md`). Sub-plans live under `docs/plans/`. Current version is in `VERSION.md`. Architecture docs are in `docs/architecture/`. See AGENTS.md for plan lifecycle and architecture doc rules.

Code edits are gated on a registered, scheduled work item (`scripts/release-gate/release_gate.py`). Before starting any code change that is not already the active item, invoke the `release-triage` skill. See AGENTS.md § Agent workflow tooling.

## Session handoff notes

Keep each session's running note in `handoff/` at the repo root (git-ignored), not in the harness scratchpad, which is deleted when the session ends.

- One file per line of work: `handoff/YYYY-MM-DD-<topic>.md` (no spaces). Continuing someone else's work: update their note rather than starting a new one.
- First line `# <topic>`, second line `Status: active | blocked | closed`. Then: done, in flight, blocked, decisions pending from Brandon, and the next concrete step, written so a fresh agent could resume cold.
- A SessionStart hook lists the newest notes. Read the ones that touch your task before starting.
- Keep secrets and sensitive findings out of the note; say where they live instead.

## Custom Domain

`CNAME` lives in `public/` so it lands in `dist/` at build time. Maps to `dangerousrobot.org`.

## Git Conventions

- Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, etc.)
- Squash merge to main for clean history
- Research content changes to `research/claims/` should go through PRs

## Licensing

- **Code** (scripts, site source, configs): MIT License (`LICENSE`)
- **Research content** (`research/`): CC-BY-4.0 (`LICENSE-CONTENT`)
