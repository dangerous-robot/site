# Flow diagrams: documented vs implemented

Companion to [`../ANALYSIS.md`](../ANALYSIS.md). These diagrams pair what the
architecture docs promise with what the code stores and executes. Finding ids refer to
[`../data/findings.json`](../data/findings.json).

## Claim lifecycle — documented vs storable

Why it matters: `docs/architecture/research-flow.md` presents a six-state lifecycle, but
the schema (`ClaimStatus` in `pipeline/common/models.py`, mirrored by the `status` Zod enum
in `src/content.config.ts`) can store only four states. `under_review` and `stale` exist
only in prose: a claim "in review" is indistinguishable on disk from a draft, and staleness
is recomputed from `next_recheck_due` on every lint run rather than being a state (TAXD-04).

Documented (research-flow.md §1):

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> blocked: threshold gate fails
    blocked --> archived: dr review --archive
    draft --> under_review: PR opened
    under_review --> draft: PR closed
    under_review --> published: approve + merge
    published --> stale: recheck_cadence_days elapsed
    stale --> under_review: refresh + PR
    published --> archived: dr review --archive
    archived --> [*]
```

Storable today (`ClaimStatus`: `draft | published | archived | blocked`):

```mermaid
stateDiagram-v2
    [*] --> draft: dr claim-draft / onboard
    draft --> blocked: threshold gate (status + blocked_reason written)
    draft --> published: dr review --approve / dr publish (bulk)
    blocked --> archived: dr review --archive
    published --> archived: dr review --archive
    published --> draft: dr claim-refresh rewrites
    archived --> [*]

    note right of published
        "stale" is a lint-time computation
        (next_recheck_due in the past),
        not a stored state
    end note
```

## verify_claim — the implemented sequence

Why it matters: this is the money path (`pipeline/orchestrator/pipeline.py`, hotspot #1).
The documented sequence in research-flow.md §3 matches this shape, but two things the docs
do not show: the `dr step-*` commands re-enter the agents *around* this engine with
diverged timeouts and validation (AT-02), and the auditor is asked to apply a confidence
cap without receiving the independence/kind data the cap depends on (AT-01).

```mermaid
sequenceDiagram
    actor Op as Operator (dr claim-*)
    participant E as verify_claim()
    participant R as Researcher (planner->search->scorer)
    participant I as Ingestor (one per URL, concurrent)
    participant H as Checkpoint handler
    participant A as Analyst
    participant X as Auditor ("Evaluator")
    participant P as persistence.py

    Op->>E: claim text + entity ref + VerifyConfig
    E->>R: decomposed_research()
    R-->>E: scored URLs + sub-questions
    E->>E: dedup + blocklist + max_sources cap

    par one ingest per URL
        E->>I: URL
        I-->>E: SourceFile (or failure)
    end

    E->>H: review_sources checkpoint
    H-->>E: proceed / halt

    alt usable sources < 4
        E->>P: claim written status=blocked + blocked_reason
    else proceed
        E->>A: sources + entity context
        A-->>E: AnalystOutput (verdict, narrative, overrides)
        E->>X: analyst output + sources (minus independence/kind data - AT-01)
        X-->>E: IndependentAssessment -> ComparisonResult
        opt verdicts disagree
            E->>H: review_disagreement checkpoint
            H-->>E: accept / flag
        end
        E->>P: claim + .audit.yaml sidecar written
    end
    E-->>Op: VerificationResult

    Note over Op,P: dr step-research / step-ingest / step-analyze / step-audit<br/>call R, I, A, X directly, bypassing this engine's<br/>validation, timeouts, and persistence (AT-02)
```

## The quality gate — three definitions of "check"

Why it matters: "run the checks" resolves to three different command sets depending on
where you stand (SCI-02), and none of them runs the pipeline's unit tests in CI (SCI-01).

```mermaid
flowchart TB
    subgraph gates ["Three 'check' definitions"]
        npm["npm run check<br/>build + lint:md + check:citations"]
        inv["inv check<br/>build + lint + unit tests"]
        ci["ci.yml<br/>build + lint:md + citations + dr lint --severity error"]
    end
    deploy["deploy.yml -> GitHub Pages"]
    tests["pipeline unit tests<br/>(pytest, ~45 modules)"]

    ci --> deploy
    inv -->|"only gate that runs"| tests
    ci -.->|"never runs (SCI-01)"| tests
```
