# Entity Onboarding

How a new entity enters the research archive: the `dr onboard` flow, what each agent does, and where the human checkpoint lives.

## Command

```
dr onboard "Entity Name" [seed-url] --type {company|product} [--force]
```

- A second positional argument supplies a seed URL and skips the homepage search step (useful when the homepage is non-obvious or rate-limited).
- `--force` allows re-running over an existing entity directory; without it, the command refuses to overwrite.

## Flow

```
dr onboard "Ecosia AI" --type product
  |
  v
[Ingestor: light research]
  - Fetch homepage / seed URL
  - Create entity file (research/entities/products/ecosia-ai.md)
  - Screen core templates against entity context
  |
  v
>>> CHECKPOINT: review_onboard <<<
  "Onboarded Ecosia AI (product). N of M product templates applicable.
   Excluded: <slug>: <reason> ..."
  Accept / Edit / Reject
  |
  v (accept or edit)
For each applicable template:
  [Researcher] -> find sources
  [Ingestor]   -> URLs into source files
  [Analyst]    -> verdict + narrative
  [Evaluator]  -> independent assessment (open-loop)
  |
  v
Onboard report (N claims created, M flagged for review)
```

## Agent responsibilities (onboard-specific)

| Agent | Onboard role | Depth |
|-------|--------------|-------|
| **Ingestor** | Creates entity file, screens templates for applicability | Light — one web search, homepage scan |
| **Researcher** | Finds evidence for each applicable claim | Deep — multiple searches per claim |
| **Analyst** | Renders verdict from evidence | Deep |
| **Evaluator** | Independent assessment of the analyst's verdict (open loop) | Deep — adversarial review (`pipeline/auditor/`) |

The ingestor's screening is an LLM reasoning task, not deterministic filtering: deciding whether a template applies depends on understanding the entity (e.g. "does this product offer image generation?") and that understanding only becomes available after the light research step.

## Checkpoint protocol

`CheckpointHandler.review_onboard` returns one of:

- `"accept"` — proceed with all proposed templates
- `"reject"` — abort; entity file is saved as a draft under `research/entities/drafts/`, no claims are created, the report records the rejection reason
- `list[str]` — an edited list of template slugs to proceed with

See `pipeline/orchestrator/checkpoints.py` for the handler interface.

## Template applicability

- Templates are tagged `core: true` or `core: false` in `research/templates.yaml`. Core templates are screened automatically during onboard.
- Non-core templates are available for manual or topic-driven runs.
- Onboarding is per entity type: a company and its products are distinct `dr onboard` operations, each receiving the templates whose `entity_type` matches.

The active template set lives in `research/templates.yaml`. Refer to that file for the current core list — it changes more often than this doc and is the source of truth.

## Company–product relationships

Companies and products onboard independently. The entity schema does not enforce a parent relationship. When onboarding a product, the ingestor notes the parent company in the entity description; if the parent entity does not yet exist, the ingestor flags it in the onboard report but does not create it automatically — the operator decides whether to onboard the company separately. When `parent_company` is set on an entity file, the pipeline resolves it to a display name and injects it into both the Researcher's planner and scorer prompts, so queries and scoring account for the parent company relationship.

## Topic origin

Each template carries a `topics` array (1-3 slugs from the taxonomy in [content-model.md § Claim Topic Taxonomy](content-model.md#claim-topic-taxonomy)). Those topics are what initially populate a generated claim's frontmatter. Whether the analyst can later override them during verdict assessment is an open behavior question (see `docs/follow-up-2026-04-24.md`).

## File references

- CLI entry point: `pipeline/orchestrator/cli.py`
- Onboard implementation: `pipeline/orchestrator/pipeline.py:onboard_entity`
- Checkpoint handler: `pipeline/orchestrator/checkpoints.py`
- Template definitions: `research/templates.yaml`
