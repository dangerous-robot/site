# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**For architecture, research schemas, agent roles, and content rules, see [AGENTS.md](AGENTS.md).**

## Project Status

Astro 6.x site with GitHub Actions deploy workflow. Phase tracking is in `plans/BACKLOG.md`. Architecture docs are in `docs/architecture/`. See AGENTS.md for plan lifecycle and architecture doc rules.

## Custom Domain

`CNAME` lives in `public/` so it lands in `dist/` at build time. Maps to `dangerousrobot.org`.

## Git Conventions

- Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, etc.)
- Squash merge to main for clean history
- Research content changes to `research/claims/` should go through PRs

## Licensing

- **Code** (scripts, site source, configs): MIT License (`LICENSE`)
- **Research content** (`research/`): CC-BY-4.0 (`LICENSE-CONTENT`)
