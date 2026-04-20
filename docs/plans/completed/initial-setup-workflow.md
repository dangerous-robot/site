# Initial Setup Workflow: dangerous-robot/site

Status: **superseded** | Created: 2026-04-18

> **This plan is historical context.** It was the original planning document. Decisions and work items have been absorbed into phase-specific plans. For current architecture, see `docs/architecture/`. For current status, see `docs/BACKLOG.md`.

This plan covers three workstreams for standing up dangerousrobot.org: the website (GitHub Pages + custom domain), the multi-agent research pipeline, and open-source repo best practices.

---

## 1. Website: GitHub Pages + Custom Domain

### 1.1 DNS Configuration -- COMPLETE

Set these records with your domain registrar for `dangerousrobot.org`:

| Type  | Host | Value                    |
|-------|------|--------------------------|
| A     | @    | 185.199.108.153          |
| A     | @    | 185.199.109.153          |
| A     | @    | 185.199.110.153          |
| A     | @    | 185.199.111.153          |
| CNAME | www  | `dangerous-robot.github.io.` |

Optional IPv6 support:

| Type  | Host | Value                    |
|-------|------|--------------------------|
| AAAA  | @    | 2606:50c0:8000::153      |
| AAAA  | @    | 2606:50c0:8001::153      |
| AAAA  | @    | 2606:50c0:8002::153      |
| AAAA  | @    | 2606:50c0:8003::153      |

- Configure **both** apex and www. GitHub auto-redirects one to the other.
- DNS propagation can take up to 48 hours, though usually completes in minutes. Use `dig dangerousrobot.org` to check.
- After propagation, GitHub auto-provisions an SSL certificate via Let's Encrypt. The "Enforce HTTPS" checkbox may be grayed out until the cert provisions.

### 1.2 Repository Configuration -- COMPLETE

1. **Settings > Pages**: set source to "GitHub Actions" (not branch-based deploy).
2. **Custom domain**: enter `dangerousrobot.org`, check "Enforce HTTPS."
3. `CNAME` file is at repo root (already committed). This works while GitHub Pages serves directly from the repo.

**CNAME gotcha**: Once an SSG + CI deploy pipeline is in place, move `CNAME` from repo root into the SSG's static directory (e.g., `public/CNAME` for Astro, `src/static/CNAME` for 11ty). The deploy workflow uploads the build output (`dist/`), and if CNAME isn't in that output, it overwrites the deployment and breaks the custom domain. This move is part of Phase 1, step 2 (SSG setup).

### 1.3 Static Site Generator -- COMPLETE (Astro)

**Decision needed.** Options ranked by fit for this project:

| Generator | Language | Why it fits | Tradeoffs |
|-----------|----------|-------------|-----------|
| **Astro** | JS/TS | Content Collections with built-in Zod schema validation for frontmatter. Outputs static HTML. Can generate JSON/TS data files at build time via integrations. Island architecture for interactive components. | Heavier dependency tree (Vite-based). Content Collections API has changed between major versions. |
| **11ty (Eleventy)** | JS | Mature, zero-config Markdown rendering. Extremely fast builds. Data cascade system (global data, directory data, frontmatter -- all composable) maps well to structured research content. Custom collections group content by type. v3.x uses ESM. | Less opinionated about component model. TS generation via `eleventy.after` event or custom templates rather than built-in. |
| **Next.js (static export)** | JS/TS | Already used by TreadLightly (parallax-ai). Familiar tooling. `output: 'export'` produces static files for GH Pages. | Heavier than needed for a content site. Static export mode loses ISR, API routes, image optimization. |
| **Custom Node.js script** | JS/TS | Purpose-built with `gray-matter` + `remark` + `fs`. Total control, minimal dependencies, 200-400 lines. | You own all the plumbing (dev server, incremental builds). No plugin ecosystem. |

**Recommendation**: Either **Astro** or **11ty** -- both are strong fits. Astro's Content Collections provide built-in schema validation via Zod, which reduces custom tooling. 11ty's data cascade is more lightweight and its "files in, files out" mental model is simpler to reason about. Both can generate TS data files alongside HTML.

If frontmatter schema enforcement is a priority (it is for this project), Astro's Content Collections give you that for free. If minimal dependencies and fast builds matter more, 11ty wins.

### 1.4 GitHub Actions Deploy Workflow -- COMPLETE

```yaml
# .github/workflows/deploy.yml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false  # don't cancel in-progress deploys

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist/

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

### 1.5 Downstream Sync to TreadLightly

The parallax-ai build syncs research content from this repo at build time (as described in `research/plans/initial-plans.md`). Two approaches:

- **Git clone in CI**: `git clone --depth 1 https://github.com/<org>/dangerous-robot-site.git content/research` during the parallax-ai build step.
- **GitHub Actions artifact**: This repo publishes a build artifact (generated TS data files) that parallax-ai's CI downloads.

The second approach is cleaner because TreadLightly only needs the generated data, not the raw research tree.

---

## 2. Multi-Agent Research Pipeline

### 2.1 The Question: Do We Need a Framework?

This project already runs inside Claude Code, which provides:
- **Subagents** for parallelized, scoped work
- **Scheduled tasks / cron** for recurring jobs (audits, reviews)
- **Hooks** for event-driven automation
- **MCP servers** for external tool integration
- **Git-native workflow** -- agents read/write Markdown files and commit

The research pipeline described in `initial-plans.md` (ingestor, claim updater, citation auditor, page builder) maps naturally to Claude Code subagents and scheduled tasks. A dedicated multi-agent framework adds a dependency and abstraction layer that may not be needed.

**Recommendation**: Start with Claude Code's native orchestration. The workflows are fundamentally "read files, reason about content, write files, commit" -- which is exactly what Claude Code already does. Adding a framework introduces dependency management, API abstraction layers, and paradigm constraints that may not serve a file-processing pipeline.

**Concrete first test**: Build the "ingest URL as source file" agent using just Claude Code (subagent or script). Note the pain points. Those pain points will tell you exactly what kind of framework value you actually need, if any.

Evaluate a framework only if you hit one of these triggers:
- Need agents to maintain long-running state across sessions (not just file state)
- Need agents to negotiate/converse with each other (not just lead/follower)
- Need to run agents outside of Claude Code (e.g., in CI without Claude Code)
- Need complex branching/retry logic that's hard to express in sequential subagent calls
- Need to checkpoint/resume a large batch operation (e.g., 200-source ingestion that fails at item 150)

| Capability | Framework Provides | Claude Code Already Has |
|---|---|---|
| LLM-powered reasoning | Yes | Yes |
| File read/write | Via tools (you write them) | Native |
| YAML/Markdown parsing | Via tools (you write them) | Native |
| Git operations | Via tools (you write them) | Native |
| Task sequencing | Yes (main value-add) | Subagent chaining, scripts |
| State persistence | Yes (LangGraph checkpointing) | File system + git commits |
| Error recovery/retry | Yes (varies) | Manual but doable |
| Scheduling | No (external) | Cron/hooks |
| Human-in-the-loop | Yes (LangGraph) | PR review flow |

### 2.2 Framework Comparison

If a framework becomes necessary, here's the landscape:

#### Tier 1: Best Graduation Path (if Claude Code native proves insufficient)

**PydanticAI** -- MIT, Python, ~8-10k stars

The strongest fit if you need to move beyond Claude Code native. Type-safe agent framework built on Pydantic. Pydantic models map directly to your YAML frontmatter schemas. Native Anthropic/Claude support (no wrapper layer). Dependency injection makes agents testable -- relevant given your testing background. The newer "Graph" module handles multi-step workflows without the weight of LangGraph. Designed to be used as a library in scripts, not as a platform.

#### Tier 2: If Complexity Genuinely Demands It

**LangGraph** -- MIT, Python + JS/TS, ~12-15k stars

The most architecturally rigorous option. Explicit state machines with typed state, built-in checkpointing and persistence, cycles, conditional branching. First-class TypeScript support via LangGraph.js (relevant for downstream TS data files). Human-in-the-loop patterns are well-supported.

Tradeoff: tight coupling to LangChain ecosystem. You inherit its abstractions, dependency weight, and rapid iteration pace (frequent breaking changes). Likely more framework than a single-developer research repo needs.

**CrewAI** -- MIT, Python, ~25k stars

Simplest mental model: define agents with roles/goals, define tasks, run a crew. Good for sequential pipelines (ingest -> review -> audit -> generate). Supports Claude via LiteLLM.

Tradeoff: the role-playing abstraction (agents with "backstories") adds little value for file-processing pipelines. CrewAI Inc. controls project direction; enterprise product may pull features from open-source.

**Claude Agent SDK** -- MIT, Python, ~2-5k stars

Anthropic's own framework. Minimal abstraction over Claude's tool-use capability. If you're committed to Claude, this is the most direct path. Worth investigating maturity for multi-agent workflows.

#### Tier 3: Not Recommended for This Project

| Framework | Stars | Why Not |
|-----------|-------|---------|
| **Microsoft AutoGen/AG2** | ~38k | Conversational paradigm is a poor fit for file-processing pipelines. Major community fragmentation in late 2024-early 2025: the original community forked to create "AG2" (ag2.ai) after disagreements with Microsoft's direction. API instability from the 0.2 -> 0.4 rewrite broke most existing tutorials. |
| **Mastra** | ~8-12k | **Elastic License 2.0** (not true open-source) -- a non-starter for open-source projects. Optimized for API/webhook workflows, not file processing. |
| **MetaGPT** | ~48k | Designed for simulating software dev teams (PM, architect, engineer roles). Wrong problem domain. |
| **OpenAI Agents SDK** | ~25k | Tightly coupled to OpenAI models. Using with Claude requires unsupported workarounds. |
| **CAMEL-AI** | ~6-8k | Research-focused framework for studying agent communication patterns. Not production-oriented. |
| **Agency Swarm** | ~3-5k | Smaller community, built specifically around OpenAI's Assistants API. Not model-agnostic. |

*Star counts are approximate, based on mid-2025 data. Verify current numbers on GitHub.*

### 2.3 Agent Role Mapping

Regardless of framework choice, the agent roles from `initial-plans.md` map as follows:

```
Research Lead (orchestrator)
  |
  +-- Ingestor Agent
  |     Input:  URL from QUEUE.md
  |     Output: research/sources/{yyyy}/{slug}.md
  |     Tools:  web fetch, Wayback Machine archive, YAML writer
  |
  +-- Claim Updater Agent
  |     Input:  claim file + relevant source files
  |     Output: updated claim with new verdict, as_of, rationale
  |     Tools:  file reader, YAML parser, LLM reasoning
  |
  +-- Citation Auditor Agent
  |     Input:  all claims/ files
  |     Output: audit report (claims with 0 sources, stale as_of, broken URLs)
  |     Tools:  file walker, URL checker, date comparison
  |
  +-- Page Builder Agent
        Input:  all claims/ files
        Output: generated TS data files for TreadLightly
        Tools:  file reader, TS code generator
```

### 2.4 Scheduling

Using Claude Code's scheduling capabilities:

| Task | Cadence | Implementation |
|------|---------|----------------|
| Citation audit | Weekly (Monday) | Claude Code cron or GitHub Actions scheduled workflow |
| Stale claim check | Daily | Script that checks `next_review_due <= today` |
| Queue triage | On-demand | Manual Claude Code session or PR-triggered |
| Page rebuild | On claim change | GitHub Actions `on: push` to `research/claims/**` |

For scheduled GitHub Actions that produce changes, use `peter-evans/create-pull-request` to auto-create PRs with the results:

```yaml
- name: Create PR if changes
  uses: peter-evans/create-pull-request@v6
  with:
    title: "chore: scheduled claim audit results"
    branch: auto/claim-audit
    commit-message: "chore: update claim audit data"
```

Note: GitHub Actions cron schedules can be delayed up to 15 minutes during high-load periods. Scheduled workflows only run on the default branch.

---

## 3. Open-Source Repository Best Practices

### 3.1 Repository Structure

```
dangerous-robot/site/
  .github/
    workflows/
      deploy.yml           # Build + deploy to GH Pages
      audit.yml            # Scheduled content audits
      ci.yml               # PR checks (lint, validate schemas)
    ISSUE_TEMPLATE/
      bug_report.yml
      claim_correction.yml  # For reporting outdated/incorrect claims
    pull_request_template.md
    CODEOWNERS               # Auto-assign reviewers by content area
  research/
    entities/
      companies/
      products/
      topics/
    claims/
    sources/
    QUEUE.md
    schemas/               # JSON Schema files for frontmatter validation
  site/                    # Astro (or chosen SSG) source
    src/
    astro.config.mjs
    package.json
  scripts/
    audit.ts               # Citation auditor CLI
    validate-schemas.ts    # Frontmatter schema validation
    generate-data.ts       # Builds TS data files from claims
  CLAUDE.md                # Agent instructions for this repo
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md
  LICENSE                  # MIT (code)
  LICENSE-CONTENT          # CC-BY-4.0 (research content)
  CNAME                    # dangerousrobot.org
  README.md
  .gitignore
  package.json
```

### 3.2 Dual Licensing

- **Code** (scripts, site source, configs): MIT License (already in place)
- **Research content** (entities, claims, sources): CC-BY-4.0

Add a `LICENSE-CONTENT` file and note the split in README:

> Code is MIT-licensed. Research content under `research/` is licensed under CC-BY-4.0.

### 3.3 CLAUDE.md

Create a project-level `CLAUDE.md` with:
- Repository purpose and architecture overview
- Research content schema descriptions
- Agent role definitions and constraints
- File naming conventions (slugs, dates)
- Rules: never edit claims without citing sources, always set `as_of` to today's date, etc.

### 3.4 Content Quality Automation

| Check | Tool | When |
|-------|------|------|
| YAML frontmatter schema validation | `ajv` or custom script with JSON Schema | PR CI |
| Markdown lint | `markdownlint-cli2` | PR CI |
| Link checking | `lychee` (fast, Rust-based) | Weekly scheduled + PR CI |
| Claim-source integrity | Custom script (every claim references existing sources) | PR CI |
| Stale content report | Custom script (`next_review_due` check) | Weekly cron |

### 3.5 Branch Protection (Repository Rulesets)

Use GitHub's newer **repository rulesets** (GA since 2023) instead of legacy branch protection rules. Rulesets are more flexible, support org-level inheritance, and can target tags and branches via patterns.

- Require PR reviews for changes to `research/claims/` (verdicts should be reviewed)
- Require CI checks to pass before merge
- Require linear history (squash merge) for a clean log
- Allow direct pushes to `research/sources/` for automated ingestion (with audit trail via git history)
- Use `CODEOWNERS` to auto-assign reviewers by content area (e.g., `research/claims/ @research-team`)

### 3.6 Issue Templates

Create a `claim_correction.yml` template for external contributors:
- Which claim is incorrect?
- What is the correct information?
- Source/evidence URL

### 3.7 Dependency Management and Security

- **Renovate** or **Dependabot** for automated dependency updates (configure via `.github/dependabot.yml`)
- **Pin GitHub Actions by SHA**, not tag (`uses: actions/checkout@<sha>`) -- supply-chain security measure. Use `pinact` or Dependabot to keep SHA pins current.
- Use `npm` lockfile for reproducible builds
- Enable **GitHub's native secret scanning and push protection** in repo settings
- Consider **OSSF Scorecard** action periodically to assess repo security posture (checks branch protection, dependency updates, CI practices)

### 3.8 Content Versioning

Traditional semver is awkward for content repos. Options:
- **CalVer** (e.g., `2026.04.18`) -- signals "this is how fresh the data is"
- **No formal releases** -- use `main` as the canonical source, tag periodically for snapshots
- **GitHub Releases as snapshots** -- monthly or quarterly with auto-generated changelogs

For downstream consumption, tag content releases that trigger downstream deploys.

### 3.9 Git Hooks (Local)

Use **lefthook** (modern, fast, cross-platform) for local pre-commit checks:
- Validate frontmatter schema
- Run markdownlint
- Check for broken internal links
- Keep hooks fast (under 5 seconds) or contributors will bypass them
- Document setup in CONTRIBUTING.md (`lefthook install`)

---

## 4. Implementation Order

### Phase 1: Foundation (do first)

1. [ ] Create `CLAUDE.md` with repo conventions and agent constraints
2. [ ] Set up Astro project in `site/` with basic config
3. [ ] Configure GitHub Pages: add CNAME file, set up DNS records
4. [ ] Create `.github/workflows/deploy.yml`
5. [ ] Add `LICENSE-CONTENT` (CC-BY-4.0)
6. [ ] Create `research/schemas/` with JSON Schema for source, claim, and entity frontmatter

### Phase 2: Research Pipeline MVP

7. [ ] Create `research/sources/` directory and convert first 10 links from TreadLightly's `links-to-add.txt`
8. [ ] Create `research/claims/` for 5 high-risk comparison rows
9. [ ] Build `scripts/audit.ts` (citation auditor CLI)
10. [ ] Build `scripts/validate-schemas.ts` (frontmatter validation)
11. [ ] Add `.github/workflows/ci.yml` with schema validation + markdown lint

### Phase 3: Site Content

12. [ ] Build Astro pages that render research content (claims with linked sources)
13. [ ] Build `scripts/generate-data.ts` to output TS data files for TreadLightly
14. [ ] Wire parallax-ai CI to consume generated data from this repo

### Phase 4: Automation

15. [ ] Set up scheduled citation audit (weekly GitHub Actions or Claude Code cron)
16. [ ] Set up stale claim checker (daily)
17. [ ] Create `research/QUEUE.md` intake workflow
18. [ ] Evaluate whether Claude Code native orchestration is sufficient or a framework is needed (revisit Section 2)

---

## 5. Open Decisions

All resolved as of 2026-04-18.

| Decision | Chosen | Notes |
|----------|--------|-------|
| Static site generator | **Astro** | Implemented. |
| Agent orchestration | **PydanticAI** | Non-Claude-specific requirement rules out Claude Agent SDK and weakens Claude Code native as the backbone. PydanticAI provides a typed, testable, model-agnostic "model to follow" without the LangChain ecosystem weight. Scheduling moves to GitHub Actions scheduled workflows (see §2.4) since orchestration is no longer Claude Code native. |
| `as_of` granularity | **Per-claim** | Simpler; add a per-cell override field later if needed. |
| `sources/` visibility | **Public pages** | Transparency aligns with TreadLightly ethos; near-free given Astro Content Collections. |
| Review cadence default | **60 days, per-claim override** | Pricing claims get 14–30; policy claims get 90–180. |
| Content license | **CC-BY-4.0** | Less restrictive; avoids SA complications for downstream reuse. |
