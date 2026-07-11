# Architecture diagrams

Companion to [`../ANALYSIS.md`](../ANALYSIS.md). Node inventory, metrics, and finding
references live in [`../data/architecture.json`](../data/architecture.json); the interactive
explorer renders the same data with zoom and drill-down. GitHub renders these Mermaid blocks
natively.

## L1 — System context

Why it matters: this is the audience-agnostic view. Everything the system does is a
consequence of one decision visible here: the pipeline and the site never talk to each
other — they share a folder of Markdown files.

```mermaid
flowchart LR
    operator(["Operator<br/>(runs dr CLI, reviews checkpoints)"])
    reader(["Reader"])

    subgraph sys ["dangerousrobot.org research system"]
        pipeline["Research pipeline<br/>(Python, PydanticAI)"]
        store[("research/<br/>Markdown + YAML")]
        site["Astro static site"]
    end

    llm["LLM providers<br/>Infomaniak · GreenPT · Anthropic · OpenAI · Google"]
    search["Search backends<br/>Tavily · Brave · arXiv"]
    wayback["Wayback Machine"]
    gh["GitHub Actions + Pages"]

    operator -->|commands + sign-off| pipeline
    pipeline -->|inference| llm
    pipeline -->|source discovery| search
    pipeline -->|archive lookups| wayback
    pipeline -->|writes claims, sources,<br/>entities, audit sidecars| store
    store -->|read at build time<br/>via content collections| site
    site -->|dist/| gh
    reader -->|dangerousrobot.org| gh
```

## L2 — Containers (current)

Why it matters: the five containers have very different change rates and quality gates.
CI builds and gates the site on every push, but the pipeline's unit tests run only on a
developer's machine (finding SCI-01), and the docs container maintains role tables in six
places (DOCS-04).

```mermaid
flowchart TB
    subgraph sys ["dangerousrobot.org research system"]
        direction LR
        pipeline["<b>pipeline/</b><br/>dr CLI + 4 agents<br/>researcher · ingestor · analyst · auditor"]
        store[("<b>research/</b><br/>claims + .audit.yaml sidecars<br/>sources · entities · templates.yaml")]
        site["<b>src/</b><br/>Astro 6 · Zod collections<br/>claims-with-audit loader"]
        tooling["<b>tooling</b><br/>tasks.py · npm scripts<br/>ci.yml · deploy.yml · scripts/"]
        docs["<b>docs/</b><br/>architecture reference · plans<br/>AGENTS.md"]
    end

    pipeline -->|writes| store
    site -->|reads| store
    tooling -->|astro build + Zod validation| site
    tooling -->|dr lint gate| pipeline
    tooling -.->|"unit tests NOT wired into CI (SCI-01)"| pipeline
    docs -.->|"describes (drift tracked in findings)"| pipeline
    docs -.->|describes| site
```

The dashed edges are the two weakest links: docs describe code without any freshness check,
and CI gates content but not pipeline behavior.

## L3 focal view — orchestrator internals

Why it matters: `pipeline/orchestrator/` is the congestion center of the repo. The two
god-files (`pipeline.py`, hotspot #1; `cli.py`, hotspot #2 — see `data/metrics.json`
`hotspots_top30`) both contain a copy of persistence decisions, which is how findings like
OCLI-02 (diverged blocked/success persistence) happen.

```mermaid
flowchart TB
    subgraph orch ["pipeline/orchestrator/"]
        cli["cli.py — dr command surface<br/>(claim-* commands, step-* commands,<br/>review, publish, stats)"]
        engine["pipeline.py — verify engine<br/>verify_claim() · onboard_entity()"]
        gates["checkpoints.py<br/>CheckpointHandler protocol<br/>(CLI-interactive / auto-approve)"]
        persist["persistence.py<br/>claim/source/entity/sidecar writers"]
        entres["entity_resolution.py<br/>ResolvedEntity from on-disk file"]
        queue["review_queue.py + review.py<br/>sign-off and queue"]
    end

    agents["agent packages<br/>researcher · ingestor · analyst · auditor"]
    common["common/<br/>models · frontmatter · content_loader"]
    store[("research/")]

    cli -->|"constructs VerifyConfig, runs"| engine
    cli -.->|"step-* commands bypass engine<br/>and call agents directly (AT-02)"| agents
    cli -.->|"claim-refresh embeds its own<br/>persistence branches (OCLI-02)"| store
    engine --> gates
    engine --> agents
    engine --> entres
    engine --> persist
    queue --> store
    persist --> store
    engine --> common
    cli --> common
```

## L3 focal view — the content integration boundary

Why it matters: this seam is where the repo's biggest structural bet lives. The pipeline
writes files with no schema check of its own; the only enforced contract is Zod at site
build — after the write already happened (PAT-01, SCH-01). Four hand-synced copies of the
vocabulary sit on this boundary (SCH-02).

```mermaid
flowchart LR
    subgraph write ["Write side (Python)"]
        agents["agents produce<br/>pydantic outputs"]
        persist["persistence.py<br/>+ frontmatter.py"]
        enums1["common/models.py<br/>enum vocabulary (mirror #1)"]
        linter["linter/checks.py<br/>hand-copied field rules (mirror #2)"]
    end

    subgraph filesystem ["research/ (the contract surface)"]
        claim["claim .md"]
        sidecar[".audit.yaml"]
        src["source .md"]
        ent["entity .md"]
    end

    subgraph read ["Read side (TypeScript)"]
        zod["content.config.ts<br/>Zod schemas (mirror #3 — only enforced copy)"]
        loader["claims-with-audit loader<br/>merges sidecar into claim.audit"]
        libs["src/lib/verdict.ts etc.<br/>display vocab (mirror #4)"]
        pages["pages render collections"]
    end

    agents --> persist
    enums1 --> persist
    persist -->|"write (unvalidated against Zod)"| claim & sidecar & src & ent
    linter -.->|"dr lint: optional, value-blind (LINT-01)"| filesystem
    claim & sidecar --> loader
    src & ent --> zod
    loader --> zod
    zod --> pages
    libs --> pages
    zod -.->|"strips pipeline-written fields:<br/>research, sub_questions, failure (SCH-01)"| sidecar
```
