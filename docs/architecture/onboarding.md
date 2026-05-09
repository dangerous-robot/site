# Entity Onboarding

How a new entity enters the research archive: the `dr onboard` flow, what each agent does, and where the human checkpoint lives.

## Command

```
dr onboard "Entity Name" [seed-url] --type {company|product|subject} [--force]
```

- A second positional argument supplies a seed URL and skips the homepage search step (useful when the homepage is non-obvious or rate-limited).
- `--force` allows re-running over an existing entity directory; without it, the command refuses to overwrite. `--force` additionally re-runs the enricher and splices the new `founded`, `description`, and `history` body into the existing file.

## Flow

```
dr onboard "Ecosia AI" --type product
  |
  v
Phase A: light research
  - Fetch homepage / seed URL
  - Probe Brave for name-collision exclusions
  |
  v
Phase B: entity_verifier
  - Classify as verified | needs-disambiguation | unverified
  - On needs-disambiguation: surface candidates via review_entity_disambiguation
      reject -> halt (operator picks a new name and re-runs)
      accept -> proceed with the first candidate
      str    -> proceed with the operator's chosen name
  - On unverified: same checkpoint with [unverified-startup, unverified-other]
      reject -> halt
      str    -> persisted as verification_status on the entity file
  |
  v
Phase C: entity_enricher (operator-review checkpoint)
  - Drafts founded, tightened description, history_markdown
  - review_entity_enrichment: accept writes the draft, reject keeps the raw summary
  |
  v
Phase D: template screening
  - Filter core templates by entity_type
  - For subjects: filter by templates whose subjects: array names this subject
    (no match -> warn, do not halt; entity lands with zero claims)
  |
  v
>>> Phase E: CHECKPOINT review_onboard <<<
  "Onboarded Ecosia AI (product). N of M product templates applicable.
   Excluded: <slug>: <reason> ..."
  Accept / Edit / Reject
  |
  v (accept or edit)
Phase F: per-template research pipeline
  For each applicable template:
    [Researcher] -> find sources
    [Ingestor]   -> URLs into source files
    [Analyst]    -> verdict + narrative
    [Evaluator]  -> independent assessment (open-loop)
  |
  v
Onboard report (N claims created, M flagged for review, plus warnings)
```

Subject example:

```
dr onboard subjects/ai-model-producers
  |
  v
Phase A: light research (seed URL inferred from the existing entity file)
Phase B: verifier (encyclopedic-consensus signals)
Phase C: enricher writes a History body for the subject
Phase D: filter templates whose subjects: includes subjects/ai-model-producers
Phase E: review_onboard
Phase F: per-template research, one claim per matching template
```

## Agent responsibilities (onboard-specific)

| Agent | Onboard role | Depth |
|-------|--------------|-------|
| **Researcher (light pass)** | Fetches the homepage / seed URL and assembles a `LightResearchBundle` | Light — one web search, homepage scan |
| **Researcher (`entity_verifier`)** | Classifies a candidate as verified / needs-disambiguation / unverified | Light — tool-free, one Haiku call per onboard |
| **Researcher (`entity_enricher`)** | Drafts `founded`, tightened `description`, and `history_markdown` | Light — tool-free, one Haiku call per onboard |
| **Researcher (per-template)** | Finds evidence for each applicable claim | Deep — multiple searches per claim |
| **Analyst** | Renders verdict from evidence | Deep |
| **Evaluator** | Independent assessment of the analyst's verdict (open loop) | Deep — adversarial review (`pipeline/auditor/`) |

Both verifier and enricher live inside `pipeline/researcher/` as agent-internal helpers. Each consumes the same `LightResearchBundle`, so neither issues its own search; the orchestrator gathers candidates once.

Template screening (Phase D) is a passthrough today: every core template of the entity's type is queued. LLM-driven screening is its own future plan.

## Checkpoint protocol

The onboard flow surfaces three checkpoints. See `pipeline/orchestrator/checkpoints.py` for the handler interface.

`CheckpointHandler.review_entity_disambiguation(entity_name, candidates) -> Literal["accept", "reject"] | str`

- `"accept"` — proceed using the first candidate
- `"reject"` — abort the run
- `str` — proceed with this name verbatim (for `needs-disambiguation`) or persist this verification_status (for `unverified`)

Auto-approve handler returns `"reject"` — the conservative default in CI / tests.

`CheckpointHandler.review_entity_enrichment(entity_name, draft) -> Literal["accept", "reject"]`

- `"accept"` — write the draft (`founded`, `description`, `history_markdown`) to the entity file
- `"reject"` — keep the raw page summary; do not write the new fields

Auto-approve handler returns `"accept"`.

`CheckpointHandler.review_onboard(entity_name, entity_type, applicable_templates, excluded_templates, entity_description) -> Literal["accept", "reject"] | list[str]`

- `"accept"` — proceed with all proposed templates
- `"reject"` — abort; entity file is saved as a draft under `research/entities/drafts/`, no claims are created
- `list[str]` — an edited list of template slugs to proceed with

## Template applicability

- Templates are tagged `core: true` or `core: false` in `research/templates.yaml`. Core templates are screened automatically during onboard.
- Non-core templates are available for manual or topic-driven runs.
- Onboarding is per entity type: a company and its products are distinct `dr onboard` operations, each receiving the templates whose `entity_type` matches.
- Subjects are first-class: `dr onboard --type subject` (or `dr onboard subjects/<slug>`) runs the same Phase A–F flow. Subject templates additionally require their `subjects:` array to name the onboarded subject; an unreferenced subject onboards successfully but emits a warning row in the report and creates zero claims.

The active template set lives in `research/templates.yaml`. Refer to that file for the current core list — it changes more often than this doc and is the source of truth.

## Company–product relationships

Companies and products onboard independently. The entity schema does not enforce a parent relationship. When onboarding a product, the ingestor notes the parent company in the entity description; if the parent entity does not yet exist, the ingestor flags it in the onboard report but does not create it automatically — the operator decides whether to onboard the company separately. When `parent_company` is set on an entity file, the pipeline resolves it to a display name and injects it into both the Researcher's planner and scorer prompts, so queries and scoring account for the parent company relationship.

## Topic origin

Each template carries a `topics` array (1-3 slugs from the taxonomy in [content-model.md § Claim Topic Taxonomy](content-model.md#claim-topic-taxonomy)). Those topics are what initially populate a generated claim's frontmatter. Whether the analyst can later override them during verdict assessment is an open behavior question (see `docs/follow-up-2026-04-24.md`).

## File references

- CLI entry point: `pipeline/orchestrator/cli.py` (`dr onboard`, `dr entity-enrich`)
- Onboard implementation: `pipeline/orchestrator/pipeline.py:onboard_entity`
- Verifier agent: `pipeline/researcher/entity_verifier.py`
- Enricher agent: `pipeline/researcher/entity_enricher.py`
- Light-research helper: `pipeline/orchestrator/pipeline.py:gather_light_research`
- Checkpoint handler: `pipeline/orchestrator/checkpoints.py`
- Template definitions: `research/templates.yaml`
