# Graphify Knowledge Graph

How the [graphify](https://pypi.org/project/graphifyy/) knowledge-graph tool is configured and used for this repository. Graphify turns the codebase and docs into a queryable graph (nodes for symbols/concepts, edges for relationships) with community detection and a plain-language report. Use it to answer "how does X work", "what calls Y", or "trace the flow through Z" without hand-reading files.

## Scope: code and documentation only

Graphify indexes the repo root but **excludes `research/`** (the large, regenerated research corpus, likely moving to its own repo) and `public/` (static assets). In-scope corpus is roughly 292 files (167 code, 125 docs, ~335k words), well under graphify's warning thresholds, so a single root build is fine.

Scope is enforced by `.graphifyignore` at the repo root (gitignore syntax). Because that file exists, graphify no longer falls back to the root `.gitignore`, so `.graphifyignore` also re-lists the meaningful `.gitignore` patterns (env files, logs, drafts, `.claude/`, etc.). Build noise (`node_modules/`, `dist/`, `.venv/`, `__pycache__/`, `graphify-out/`, lock files) is skipped by graphify's built-in rules and does not need listing.

`graphify-out/` (graph.json, report, HTML, caches) is generated and git-ignored.

## Install and interpreter

`graphifyy` is installed into this project's uv-managed venv (not a project dependency, matching how it is used elsewhere). From the repo root:

```
VIRTUAL_ENV=.venv uv pip install graphifyy
```

**Interpreter pinning matters.** The global `~/.local/bin/graphify` has a shebang pointing at a *different* project's venv, and the graphify skill's auto-detect can resolve to it. To keep this repo on its own interpreter, `graphify-out/.graphify_python` is pinned to this venv's Python. Always invoke graphify through this venv:

```
.venv/bin/graphify <command>
```

## Extraction backend: GreenPT gpt-oss-120b

Semantic extraction (the LLM pass over docs) uses **GreenPT's `gpt-oss-120b`** model. GreenPT is an OpenAI-compatible provider registered as a trusted custom backend in `~/.graphify/providers.json`; the API key is read from `GREENPT_API_KEY` (kept in this repo's `.env`). Code files use free deterministic AST extraction and do not hit the LLM.

Building the graph is **two steps** (extract, then label) that need *different* token caps — see the caveats below for why. Run from the repo root with `GREENPT_API_KEY` in the environment:

```
set -a; . ./.env; set +a

# 1. Extract + cluster: needs a high output cap. Writes graph.json with
#    community indices, but defers community *naming* to step 2.
GRAPHIFY_MAX_OUTPUT_TOKENS=32768 \
  .venv/bin/graphify extract . --backend greenpt --model gpt-oss-120b

# 2. Name communities + write report/html: DEFAULT cap (do NOT export the override).
.venv/bin/graphify label . --backend greenpt --model gpt-oss-120b
```

`extract` runs AST + semantic extraction + clustering and writes `graphify-out/graph.json` (every node gets a community index; names are left blank). It honors `.graphifyignore`. `label` re-clusters, names each community, and writes `GRAPH_REPORT.md`, `graph.html`, and an updated `graph.json`. Community *names* live in the report and HTML; `graph.json` stores each node's community as an index, so `query`/`explain` show a community number that maps to a named section in the report.

Run `label` immediately after `extract`, on the freshly-clustered graph. Because `extract` already de-duplicated same-named symbols, `label`'s re-cluster produces the same node count and rewrites `graph.json` cleanly, keeping graph.json and the report on the same clustering. Running `label` on a raw (`--no-cluster`) graph, or re-running it repeatedly, can shrink the node count via further dedup and trip graphify's "Refusing to overwrite ... fewer nodes" guard: the report and html regenerate but `graph.json` is left stale, so the two drift apart. If that happens, rebuild from step 1.

**Caveat 1 - extraction needs `GRAPHIFY_MAX_OUTPUT_TOKENS=32768`.** GreenPT registers `gpt-oss-120b` with an 8192-token output cap, but gpt-oss is a reasoning model that spends output budget on reasoning before emitting JSON. At the default cap, extraction responses truncate, chunks get dropped, and the phase thrashes in a slow split-and-retry loop. Raising the cap lets a full chunk (reasoning + JSON) fit in one response.

**Caveat 2 - labeling must use the DEFAULT cap (no override).** The OpenAI client rejects any non-streaming request whose `max_tokens` is large enough to risk a >10-minute response ("Streaming is required for operations that may take longer than 10 minutes"). The community-labeling call batches 100 communities at once, so with the 32k override it trips this guard and every community falls back to a "Community N" placeholder. The fix is the cap, not the model: at the default 8192 cap, `gpt-oss-120b` names communities fine (labels are short). This is why naming is a separate command run without the override.

## Querying

Once built, query without rebuilding:

```
.venv/bin/graphify query "How does the vision state machine work?"
.venv/bin/graphify path "claim" "source"          # shortest path between two concepts
.venv/bin/graphify explain "SourceQuality"        # plain-language node explanation
.venv/bin/graphify affected "content-model"       # reverse traversal: what depends on X
```

The graphify skill (`/graphify "<question>"`) uses `graphify-out/graph.json` directly when it exists.

## Publishing the interactive graph

The interactive `graph.html` is served via GitHub Pages at
`dangerousrobot.org/graphify/graph.html`, unlisted (not linked from the site)
and non-indexed. Because `graphify-out/` is git-ignored, publishing means
copying the built HTML into `public/` (which Astro copies verbatim into
`dist/`) and re-applying the noindex guard:

```
mkdir -p public/graphify
cp graphify-out/graph.html public/graphify/graph.html
# re-inject the noindex meta (regenerated graph.html does not carry it)
.venv/bin/python -c "from pathlib import Path; p=Path('public/graphify/graph.html'); h=p.read_text('utf-8'); \
p.write_text(h.replace('<head>', '<head>\n<meta name=\"robots\" content=\"noindex, nofollow\">', 1)) if 'name=\"robots\"' not in h else None"
```

`public/robots.txt` also disallows `/graphify/`, so crawling is blocked even if
the meta is ever dropped. The file is 2.6MB and re-commits as a large diff each
time it is republished, so republish deliberately, not on every rebuild.

## Keeping it current

- **After code or doc changes:** re-run both steps (extract, then label). Extraction is cache-accelerated, so only new or changed files hit GreenPT; a warm-cache rebuild of the full corpus is a couple of minutes and ~$0.05. Always pair them so graph.json and the report stay on one clustering (see the guard note above).
- **Quick code-only refresh:** `.venv/bin/graphify update .` re-extracts code via AST with no LLM, but it re-clusters and does not regenerate names or the report, which then drift from graph.json. Prefer the two-step rebuild unless you only need the raw node/edge structure.
- The post-commit git hook (`graphify hook install`) is **not** installed: it would embed whichever interpreter it resolves at install time, reintroducing the cross-venv fragility. Rebuild manually until that is addressed.
