# Contributing

## Setup

```bash
npm install
npm run dev
```

Requires Node 22+.

## Development

- `npm run dev` -- local dev server
- `npm run build` -- production build to `dist/`
- `npm run preview` -- preview the production build locally

## Conventions

- **Commits**: conventional commit format (`feat:`, `fix:`, `chore:`, `docs:`)
- **PRs**: squash merge to main
- **Research content**: changes to `research/claims/` should go through PRs

## First contribution: adding a claim about an existing entity

The minimal happy path for adding a new claim to an entity that already exists under `research/entities/`.

1. **(Optional) Queue the topic.** Append a URL or one-line topic to `research/QUEUE.md`. This step can be skipped for one-off contributions.
2. **Run the research pipeline.** `uv run dr research "your claim text here"` finds sources, runs the Analyst and Auditor agents, and writes files to disk. See [AGENTS.md](AGENTS.md) for other `dr` commands.
3. **Review the generated files.** Inspect the new source files under `research/sources/{yyyy}/` and the new or updated claim file under `research/claims/{entity-slug}/`. Confirm the verdict, sources, and `as_of` date match the evidence.
4. **Open a PR.** Commit the generated files (conventional commit prefix, e.g. `feat(claims):`) and push. Squash-merge to main after review.
5. **Expect CI checks.** The PR runs three gates: Astro build (schema validation), markdown lint, and citation integrity (every source slug resolves to a file). All three must pass before merge.

## Licensing

- Code contributions fall under MIT (`LICENSE`)
- Research content falls under CC-BY-4.0 (`LICENSE-CONTENT`)
