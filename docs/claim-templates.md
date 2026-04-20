# Standardized Claim Templates

**Status**: Implemented. `research/templates.yaml` defines all 19 templates. `dr onboard "Entity" --type company|product` runs the full onboarding flow. Pass a seed URL as a second positional arg to skip the homepage search step: `dr onboard "Corp" example.com --type company`.

Templates define repeatable research questions that can be evaluated across multiple entities. Each template produces one claim file per entity, with the verdict scale (true through unverified) encoding degree and nuance in the narrative.

Templates define the research question, not the claim title. The analyst writes the title based on findings. For example, the template `renewable-energy-hosting` might produce a claim titled "Ecosia's renewable energy claim does not cover its AI chat backend."

## How templates work

A template like `renewable-energy-hosting` becomes concrete claims:

- `claims/greenpt/renewable-energy-hosting.md` (verdict: true)
- `claims/ecosia/renewable-energy-hosting.md` (verdict: mostly-true)
- `claims/chatgpt/renewable-energy-hosting.md` (verdict: unverified)

The entity type in the template determines the frontmatter path prefix: `companies/` or `products/`.

## Template file format

Templates are defined in `research/templates.yaml` (to be created). Each template has a stable slug used for references and claim filenames.

```yaml
templates:
  - slug: renewable-energy-hosting
    text: "PRODUCT is hosted on renewable energy"
    entity_type: product
    category: environmental-impact
    core: true
    notes: "Verdict encodes degree: true = 100%, mostly-true = significant with gaps, mixed = offsets only"

  - slug: discloses-energy-sourcing
    text: "PRODUCT discloses its energy sourcing"
    entity_type: product
    category: environmental-impact
    core: true
    notes: "Transparency meta-claim: does the company say where its energy comes from?"
```

The `slug` field determines the claim filename: `claims/{entity-slug}/{template-slug}.md`.

## Controlled vocabularies

### Jurisdiction values

Used in data storage claims. One or more per claim.

`EU` | `Switzerland` | `US` | `US-California` | `UK` | `Canada` | `Australia` | `multiple`

When `multiple`, the narrative lists specific jurisdictions and assesses data protection strength. When a broad value like `US` or `EU` is used, the narrative should note sub-jurisdiction nuances (e.g., CCPA in California, varying GDPR enforcement across EU member states) when relevant.

### Corporate structure values

Used in ownership/governance claims.

`publicly-traded` | `privately-held` | `non-profit` | `B-corp` | `employee-owned` | `steward-ownership` | `cooperative`

### Frontier-scale definition

Used in model selection claims. A model is frontier-scale if it meets either criterion at time of release:

- Top-5 performance on major benchmarks (MMLU, HumanEval, etc.)
- Greater than 100B parameters

This definition is a moving target. When evaluating claims, the narrative should state which criterion was applied and the date of assessment.

---

## Templates

### Environmental Impact

| Slug | Template | Entity type | Category | Notes |
|------|----------|-------------|----------|-------|
| `renewable-energy-hosting` | `PRODUCT` is hosted on renewable energy | product | environmental-impact | Verdict encodes degree: true = 100%, mostly-true = significant with gaps, mixed = offsets only |
| `discloses-energy-sourcing` | `PRODUCT` discloses its energy sourcing | product | environmental-impact | Transparency meta-claim: does the company say where its energy comes from? |
| `realtime-energy-display` | `PRODUCT` displays real-time energy usage | product | environmental-impact | Binary: the feature exists or it doesn't |
| `excludes-image-generation` | `PRODUCT` excludes image generation | product | environmental-impact | Image generation has the highest per-query energy cost; excluding it is an environmental stance |
| `publishes-sustainability-report` | `COMPANY` publishes a sustainability or ESG report | company | environmental-impact | Environmental analog of financial transparency |

### Data Privacy & Ethics

| Slug | Template | Entity type | Category | Notes |
|------|----------|-------------|----------|-------|
| `no-training-on-user-data` | `PRODUCT` does not use user data for training | product | data-privacy | Covers default behavior; opt-out options noted in narrative |
| `data-jurisdiction` | `PRODUCT` stores user data in `JURISDICTION` | product | data-privacy | Controlled vocabulary; assess data protection strength |
| `user-data-deletion` | `PRODUCT` allows users to delete their data | product | data-privacy | Basic GDPR/CCPA concern; binary but implementation quality varies |

### AI Safety & Transparency

| Slug | Template | Entity type | Category | Notes |
|------|----------|-------------|----------|-------|
| `publishes-ai-limitations` | `COMPANY` publishes known AI limitations | company | ai-literacy | Public documentation of what the product can't do or gets wrong |
| `donates-to-safety-environment` | `COMPANY` donates to AI safety or environmental causes | company | ai-safety | Verifiable from financial disclosures or public commitments |
| `anti-sycophancy-by-design` | `PRODUCT` implements anti-sycophancy by design | product | ai-safety | Documented design choices to reduce flattery/agreement bias |
| `labels-ai-generated-content` | `PRODUCT` labels AI-generated content | product | ai-safety | Watermarking, metadata, or visible labeling of AI outputs |

### Responsible Business

| Slug | Template | Entity type | Category | Notes |
|------|----------|-------------|----------|-------|
| `financial-transparency` | `COMPANY` provides financial transparency | company | industry-analysis | Public financials, revenue breakdowns, cost disclosures |
| `ai-alternatives-guidance` | `COMPANY` offers AI alternatives guidance | company | ai-literacy | Willingness to recommend not using your own product |
| `corporate-structure` | `COMPANY` has `STRUCTURE` corporate structure | company | industry-analysis | Controlled vocabulary; ownership determines incentives |

### Model Selection

| Slug | Template | Entity type | Category | Notes |
|------|----------|-------------|----------|-------|
| `discloses-models-used` | `PRODUCT` discloses which models it uses | product | ai-safety | Some products don't say what's running behind the API |
| `excludes-frontier-models` | `PRODUCT` excludes frontier-scale models | product | ai-safety | See controlled vocabulary for frontier-scale definition |
| `open-source-models-only` | `PRODUCT` uses only open-source models | product | ai-safety | Auditability: weights and architecture are publicly available |
| `documents-model-selection` | `PRODUCT` documents model selection criteria | product | ai-safety | Meta-transparency: why these models and not others? |

---

## Entity onboarding

**Status**: Implemented. See `pipeline/orchestrator/pipeline.py:onboard_entity` and `pipeline/orchestrator/cli.py`.

When a new entity enters the system, the **ingestor** handles onboarding. The ingestor's role is "intake" for anything entering the research archive -- URLs become source files, entities become entity files with screened template lists.

### Onboard flow

```
dr onboard "Ecosia AI" --type product
  |
  v
[Ingestor: light research]
  - Fetch company/product homepage
  - Create entity file (research/entities/products/ecosia-ai.md)
  - Screen core templates against entity context
  |
  v
>>> CHECKPOINT: review_onboard <<<
  "Onboarded Ecosia AI (product). 9 of 12 product templates applicable.
   Excluded:
   - excludes-image-generation: Ecosia AI does not offer image generation
   - anti-sycophancy-by-design: not a conversational AI product
   - labels-ai-generated-content: search product, no generated content
   Accept / Edit / Reject?"
  |
  v (accept or edit)
For each applicable template (parallelism TBD per orchestrator config):
  [Researcher] -> find sources (deep investigation)
  [Ingestor]   -> turn URLs into source files
  [Analyst]    -> assess verdict + write narrative
  [Auditor]    -> independent second opinion
  |
  v
Output: onboarding report (N claims created, M flagged for review)
```

### Rejection path

If the operator rejects at the checkpoint:
- Entity file is saved as a draft (`research/entities/drafts/`)
- No claims are created
- Onboard report notes the rejection reason for future reference

### Agent responsibilities

| Agent | Role in onboard flow | Depth |
|-------|---------------------|-------|
| **Ingestor** | Creates entity file, screens templates for applicability | Light -- one web search, homepage scan |
| **Researcher** | Finds evidence for each applicable claim | Deep -- multiple searches per claim |
| **Analyst** | Renders verdict from evidence | Deep -- evidence analysis |
| **Auditor** | Independent check on analyst's verdict | Deep -- adversarial review |

The ingestor does light research to onboard correctly (understanding what the entity is, what it offers). The researcher is dedicated to the deeper work of finding and evaluating evidence for specific claims.

### Checkpoint protocol addition

The onboard flow requires a new method on `CheckpointHandler`:

```python
async def review_onboard(
    self,
    entity_name: str,
    entity_type: str,
    applicable_templates: list[str],   # slugs
    excluded_templates: list[tuple[str, str]],  # (slug, reason)
) -> Literal["accept", "reject"] | list[str]:
    """Return 'accept', 'reject', or an edited list of template slugs."""
    ...
```

### Template applicability

Templates are tagged `core: true` or `core: false`. Core templates are screened automatically during onboard. Non-core templates are available for manual or category-based research runs.

All 19 current templates are core. Future templates (feature comparisons, regulatory claims) may be non-core.

Entities are onboarded separately by type. A company and its products are distinct onboard operations, each receiving the templates matching their entity type:

- **Company** (7 core templates): `corporate-structure`, `publishes-ai-limitations`, `donates-to-safety-environment`, `financial-transparency`, `ai-alternatives-guidance`, `publishes-sustainability-report`
- **Product** (12 core templates): `renewable-energy-hosting`, `discloses-energy-sourcing`, `realtime-energy-display`, `excludes-image-generation`, `no-training-on-user-data`, `data-jurisdiction`, `user-data-deletion`, `anti-sycophancy-by-design`, `labels-ai-generated-content`, `discloses-models-used`, `excludes-frontier-models`, `open-source-models-only`, `documents-model-selection`

The ingestor's template screening is an LLM reasoning task, not deterministic filtering. Whether a template applies depends on understanding the entity -- e.g., "does this product offer image generation?" requires knowledge that may only be available after the light research step.

### Company-product relationships

Companies and products are onboarded independently. The entity schema does not currently enforce a parent relationship. When onboarding a product, the ingestor should note the parent company in the entity description. If the parent company entity does not yet exist, the ingestor should flag this in the onboard report but not create it automatically -- the operator decides whether to onboard the company separately.

---

## Coverage by DR category

| Category | Templates |
|----------|-----------|
| environmental-impact | `renewable-energy-hosting`, `discloses-energy-sourcing`, `realtime-energy-display`, `excludes-image-generation`, `publishes-sustainability-report` |
| data-privacy | `no-training-on-user-data`, `data-jurisdiction`, `user-data-deletion` |
| industry-analysis | `corporate-structure`, `financial-transparency` |
| ai-literacy | `publishes-ai-limitations`, `ai-alternatives-guidance` |
| ai-safety | `donates-to-safety-environment`, `anti-sycophancy-by-design`, `labels-ai-generated-content`, `discloses-models-used`, `excludes-frontier-models`, `open-source-models-only`, `documents-model-selection` |
| product-comparison | -- |
| consumer-guide | -- |
| regulation-policy | -- |

Templates intentionally focus on ethics, environment, and AI safety. Product feature comparisons and regulatory claims are out of scope for this initial set.
