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
- **Code from outside contributors**: open a PR; it is squash-merged to main
- **Research content**: committed to main after a person signs it off at `dr review`; no PR stands between a draft and the live site

## First contribution: adding a claim about an existing entity

The minimal happy path for adding a new claim to an entity that already exists under `research/entities/`.

1. **Run the research pipeline.** `uv run dr draft --entity <entity-ref> "your claim text here"` (for example `--entity products/chatgpt`) finds sources, runs the Analyst and Auditor agents, and writes files to disk. See [pipeline-commands.md](docs/architecture/pipeline-commands.md) for the other `dr` commands.
2. **Sign off at `dr review`.** At a terminal, run `uv run dr review`. It shows each draft's review packet (the verdict chain, every key quote beside its page passage, source independence, the searches) and records your sign-off; `a` approves the draft and flips it to `published`. To sign off one claim, run `uv run dr review --claim <ref> --approve`. Agents never run the sign-off.
3. **Commit to main.** Commit the generated files and the audit sidecar (conventional commit prefix, e.g. `feat(claims):`) on `main`. The pre-commit hook runs `dr lint` and `inv check` (site build and unit tests).
4. **Expect CI checks.** A push to main runs the CI gates (Astro build with schema validation, markdown lint, citation integrity, `dr lint`, pipeline unit tests) before the site deploys. All must pass for the deploy to go out. An outside contributor's PR runs the same gates before merge.

## Licensing

- Code contributions fall under MIT (`LICENSE`)
- Research content falls under CC-BY-4.0 (`LICENSE-CONTENT`)
