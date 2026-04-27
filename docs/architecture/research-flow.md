# Research Flow Diagrams

Visual reference for the research lifecycle. The first diagram is a state machine covering a claim from draft to archival. The remaining diagrams zoom into specific mechanisms: queue handling, pipeline execution, onboarding of new entities, and the sign-off path from PR open to merged and deployed.

Sections:

1. Claim lifecycle (state machine)
2. Queue lifecycle
3. Pipeline execution (sequence)
4. Onboard pipeline
5. Sign-off: before and after PR

---

## 1. Claim lifecycle

Every claim moves through the same set of states regardless of how it was initiated (`dr research`, `dr onboard`, or a manual edit). Transitions are driven by pipeline events, PR events, or time-based staleness.

```mermaid
stateDiagram-v2
    [*] --> draft: dr research / dr onboard / manual edit
    draft --> blocked: pipeline threshold gate (< 2 sources or terminal fetch error)
    blocked --> archived: dr review --archive
    draft --> under_review: PR opened
    under_review --> draft: PR closed without merge
    under_review --> published: dr review --approve (status flip) + PR merged
    published --> stale: recheck_cadence_days elapsed
    stale --> under_review: dr research re-run, PR opened
    published --> archived: dr review --archive (entity retired or claim superseded)
    archived --> [*]
```

Notes:

- `draft` covers both pipeline-written files awaiting a PR and hand-edited files on a feature branch.
- `blocked` is written by the orchestrator when the post-ingest threshold gate fails. The frontmatter carries `status: blocked` and `blocked_reason` (one of `insufficient_sources`, `terminal_fetch_error`).
- Stale claims are flagged today by `dr lint` (which surfaces a past `next_recheck_due` as `info`) and by `dr reassess` (which re-runs the Evaluator against current sources). No scheduler exists. See [research-workflow.md § Citation Auditor tools](research-workflow.md#citation-auditor-tools).
- Archived claims remain in the repo but are excluded from published output.
- `draft → published` and `published → archived` transitions are driven by `dr review` (per-claim) or `dr publish` (bulk). See § 5 below for sign-off semantics, and [`docs/plans/completed/audit-trail.md`](../plans/completed/audit-trail.md) for the CLI contract.

---

## 2. Queue lifecycle

How items enter and exit the queue:

```mermaid
flowchart LR
    A([Human or agent]) -->|adds URL or topic| B[research/QUEUE.md]
    B -->|operator picks item| C{Item type}
    C -->|URL| D[dr ingest URL]
    C -->|claim text| E[dr research claim-text]
    C -->|new entity| F[dr onboard entity type]
    D --> G[Source file written to research/sources/]
    E --> H[Source + claim files written]
    F --> I[Entity + claim files written per template]
    G --> J[Remove item from QUEUE.md]
    H --> J
    I --> J
    J --> K([Queue cleared])
```

---

## 3. Pipeline execution

The core four-step pipeline as a sequence of messages between agents and the two human checkpoints. Ingestor calls run concurrently, one per URL returned by the Researcher. The Evaluator role is implemented in `pipeline/auditor/`; the role and package names diverge intentionally in v1.

```mermaid
sequenceDiagram
    actor Operator
    participant Researcher
    participant Ingestor
    participant Analyst
    participant Evaluator
    actor Human

    Operator->>Researcher: claim text + entity
    Researcher-->>Operator: candidate URLs (post-blocklist)

    par concurrent ingest per URL
        Operator->>Ingestor: URL 1
        Ingestor-->>Operator: SourceFile 1
    and
        Operator->>Ingestor: URL 2
        Ingestor-->>Operator: SourceFile 2
    and
        Operator->>Ingestor: URL N
        Ingestor-->>Operator: SourceFile N
    end

    Operator->>Human: checkpoint review_sources
    Human-->>Operator: proceed or halt

    alt below_threshold (< 2 usable sources)
        Operator-->>Operator: status=blocked + blocked_reason; return
    else proceed
        Operator->>Analyst: sources
        Analyst-->>Operator: AnalystOutput (verdict, narrative)

        Operator->>Evaluator: analyst output + sources
        Evaluator-->>Operator: ComparisonResult (independent, open-loop)

        alt needs_review
            Operator->>Human: checkpoint review_disagreement
            Human-->>Operator: accept or flag
        end
    end

    Operator-->>Operator: VerificationResult
```

---

## 4. Onboard pipeline

New entity path. Runs light research, screens templates, then loops the core pipeline once per applicable template.

```mermaid
flowchart TD
    IN([dr onboard entity-name type]) --> LR

    LR["Light research
    — ingest seed URL or search for homepage
    — extract entity description"]
    LR --> TS

    TS["Template screening
    — load templates for entity type
    — filter to applicable slugs
    — MVP: all core templates pass"]
    TS --> CP

    CP{"`**Checkpoint**
    review_onboard`"}
    CP -->|reject| DRAFT["Write draft entity file
    — status: draft
    — no claims created"]
    CP -->|accept| WE
    CP -->|edit template list| WE

    WE["Write entity file
    research/entities/{type}/{slug}.md"]
    WE --> LOOP

    LOOP["For each template slug
    — render claim text
    — run verify_claim pipeline
    — write source files
    — write claim file
    — write audit sidecar"]

    LOOP -->|template succeeded| NEXT{More templates?}
    LOOP -->|template failed| FERR[Log error, continue]
    FERR --> NEXT
    NEXT -->|yes| LOOP
    NEXT -->|no| DONE

    DONE([OnboardResult: claims_created, claims_failed])
    DRAFT --> DONE2([OnboardResult: status=rejected])
```

---

## 5. Sign-off: before and after PR

Two zones separate pipeline-internal gates (run locally before a PR is opened) from CI gates and human review (run after the PR is opened). Rejections loop back to the zone that owns them.

```mermaid
flowchart TD
    subgraph before ["Before PR (local)"]
        direction TB
        START([Author runs pipeline or edits files]) --> PG1
        PG1{"review_sources
        (pipeline checkpoint)"}
        PG1 -->|halt: poor sources| START
        PG1 -->|proceed| PG2
        PG2{"review_disagreement
        (pipeline checkpoint)"}
        PG2 -->|flag for human review| START
        PG2 -->|accept| PG3
        PG3{"review_onboard
        (onboard only)"}
        PG3 -->|reject: draft only| START
        PG3 -->|accept| LOCAL
        LOCAL["Local checks
        — inv check
        — dr lint"]
        LOCAL -->|fails| START
        LOCAL -->|passes| OPEN([Open PR])
    end

    OPEN --> AFTER_ENTRY

    subgraph after ["After PR (remote)"]
        direction TB
        AFTER_ENTRY([PR opened]) --> CI1
        CI1["Astro build
        — Zod schema validation"]
        CI1 -->|fails| REWORK[Author revises]
        CI1 -->|passes| CI2
        CI2["Markdown lint
        — markdownlint-cli2"]
        CI2 -->|fails| REWORK
        CI2 -->|passes| CI3
        CI3["Citation integrity
        — scripts/check-citations.ts"]
        CI3 -->|fails| REWORK
        CI3 -->|passes| CI4
        CI4["dr lint --severity error
        — lint-content job
        — annotates errors"]
        CI4 -->|fails| REWORK
        CI4 -->|passes| REV
        REV{Human PR review}
        REV -->|changes requested| REWORK
        REV -->|approved| MERGE([Merge to main])
        REWORK --> AFTER_ENTRY
    end

    MERGE --> DEPLOY["GitHub Actions deploy
    — npm run build
    — publish to GitHub Pages"]
    DEPLOY --> LIVE([Live at dangerousrobot.org])
```

Notes:

- Human sign-off on a claim is recorded by `dr review` (writes `human_review` in the audit sidecar). `dr review --approve` additionally flips `status: draft` to `status: published`, so sign-off and publish are a single operator step. `dr review --archive` retires a published claim (or a blocked claim). Bare `dr review` records a sign-off without changing status. See [`docs/plans/completed/audit-trail.md`](../plans/completed/audit-trail.md) for the CLI contract.
- A separate operator command, `dr publish`, does a bulk `draft → published` flip without recording an individual reviewer. Affected claims render as "Unreviewed" on the site until a later `dr review` writes a reviewer in.
