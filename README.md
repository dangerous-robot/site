# dangerous-robot/site

The home of [dangerousrobot.org](https://dangerousrobot.org) and the research that backs it.

Dangerous Robot is a structured research project that evaluates claims made by and about
AI companies and AI products: environmental impact, safety practices, transparency, and
responsible-AI commitments. A Python pipeline of LLM agents finds sources, fetches and
archives them, drafts a verdict, and routes it to a human reviewer before anything is
published. Every published claim cites its sources and records when it was last reviewed.

## What's here

- `src/` — Astro 6.x site source. Public pages: `/`, `/companies`, `/products`, `/criteria`,
  `/claims`, `/sources`, `/topics`, `/faq`.
- `research/` — the corpus. `entities/` (companies, products, sectors), `claims/`
  (verdicts), `sources/` (citable references), `templates.yaml` (reusable claim templates).
- `pipeline/` — Python agents (Researcher, Ingestor, Analyst, Evaluator) plus the
  Orchestrator and the `dr` CLI.
- `docs/` — release roadmaps (`docs/v*.*.*.md`), architecture docs, sub-plans.
- `AGENTS.md` — instructions for AI coding agents working in this repo. Start here if you
  are an LLM.

## Getting started

```
inv setup     # install all dependencies (npm + uv)
inv dev       # start the Astro dev server
inv test      # run pipeline unit tests
inv check     # build + lint + test (pre-push gate)
```

The pipeline CLI is `dr`. After `inv setup`, run `uv run dr --help` for a full command
list, or see `AGENTS.md` § Tooling.

## Contributing

External contributions are welcome. The lowest-friction paths:

- **Submit a source.** Open an issue using the source-submission template
  (`.github/ISSUE_TEMPLATE/`).
- **Request a claim.** Propose a specific assertion you want evaluated, with at least one
  source.
- **Report a problem.** Open a regular issue for typos, broken links, schema errors, or
  verdicts that look wrong.

## Conflicts of interest

This project is operated by Brandon Faloona, who also founded
[TreadLightly AI](https://treadlightly.ai). Many claims here back assertions made on the
TreadLightly AI site. See the [FAQ](https://dangerousrobot.org/faq#conflicts-of-interest)
for the full disclosure.

## License

- **Code** (scripts, site source, configs) — MIT License. See [`LICENSE`](LICENSE).
- **Research content** (`research/`) — CC-BY-4.0. See [`LICENSE-CONTENT`](LICENSE-CONTENT).
