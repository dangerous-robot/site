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

- Commits use conventional commit format (`feat:`, `fix:`, `chore:`, `docs:`)
- Code from outside contributors arrives as a PR and is squash-merged to main
- Research content is committed to main after a person signs it off at `dr review`; no PR stands between a draft and the live site

## Suggesting a source

Open a [Submit a source](https://github.com/dangerous-robot/site/issues/new?template=submit-source.md) issue. It asks for the URL, what the source says, the company, product, or subject it relates to, and its kind (primary, secondary, or tertiary). A person reviews each submission before the source is ingested; not every submission becomes a citation.

Without a GitHub account, email <contact@dangerousrobot.org> with the subject "Source submission: [page or claim]" and include the same details.

## Requesting a claim

Open a [Request a claim](https://github.com/dangerous-robot/site/issues/new?template=request-claim.md) issue. Write the claim as one sentence the public record can show to be true or false, and name the company, product, or subject it is about. A person reads each request and decides whether to research it. A researched request runs through the pipeline below like any other claim.

Without a GitHub account, email <contact@dangerousrobot.org> with the subject "Claim request: [the claim in one sentence]".

## First contribution: adding a claim about an existing entity

The entity must already exist under `research/entities/`.

1. **Run the research pipeline.** `uv run dr draft --entity <entity-ref> "your claim text here"` (for example `--entity products/chatgpt`) finds sources, runs the Analyst and Auditor agents, and writes files to disk. See [pipeline-commands.md](docs/architecture/pipeline-commands.md) for the other `dr` commands.
2. **Sign off at `dr review`.** At a terminal, run `uv run dr review`. It shows each draft's review packet (the verdict chain, every key quote beside its page passage, source independence, the searches) and records your sign-off; `a` approves the draft and flips it to `published`. To sign off one claim, run `uv run dr review --claim <ref> --approve`. Agents never run the sign-off.
3. **Commit to main.** Commit the generated files and the audit sidecar (conventional commit prefix, e.g. `feat(claims):`) on `main`. The pre-commit hook runs `dr lint` and `inv check` (site build and unit tests).
4. **Expect CI gates.** A push to main runs the CI gates (Astro build with schema validation, markdown lint, citation integrity, `dr lint`, pipeline unit tests) before the site deploys. An outside contributor's PR runs the same gates before merge.

## Licensing

- Code contributions fall under MIT (`LICENSE`)
- Research content falls under CC-BY-4.0 (`LICENSE-CONTENT`)
