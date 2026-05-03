# Sector-wide claims

**Status**: Implementation complete. All four steps done as of 2026-05-03. This plan is now a future-work tracker.
**Last updated**: 2026-05-03

The entity `type` enum needs to be extended to include `'sector'` to support sector-wide claims. The immediate use case is moving the `existential-safety-score` claim from `anthropic/` to a new `sectors/ai-llm-producers/` entity, as that criterion applies across the AI/LLM industry rather than to a single company.

The term `sector` was chosen over `industry` after evaluation -- `sector` is more precise in common usage and avoids conflation with `category: 'industry-analysis'` already in the claims schema.

---

## Scope

**Schema changes**: two files, one decision deferred.

**Display**: Sector entities don't belong under `/companies` or `/products`. For v0.1.0, surface them via `/claims` and cross-links from company entity pages. A dedicated `/sectors/` route is a post-v0.1.0 item.

**Ordering constraint**: the schema change and entity file must land before the claim migration. A single atomic commit satisfies this; if split into two commits, schema + entity must come first.

---

## Implementation

### Step 1 -- Schema change

**File**: `src/content.config.ts`, entities collection, line 65.

Change:
```ts
type: z.enum(['company', 'product', 'topic']),
```
To:
```ts
type: z.enum(['company', 'product', 'topic', 'sector']),
```

No other schema file needs updating for v0.1.0. The `entity_type` enum in `research/templates.yaml` (standards/criteria collection) currently only covers `['company', 'product']`. Sector-level criteria templates are possible in the future, but no sector-specific template exists for v0.1.0 -- the `existential-safety-score` claim uses the `entity:` field to reference the sector entity and does not require a sector template. Leave `entity_type` unchanged for now; add `'sector'` when a sector-scoped template is created.

### Step 2 -- New entity file

Create the directory and file:

```
research/entities/sectors/ai-llm-producers.md
```

File content:

```md
---
name: AI/LLM Producers
type: sector
aliases:
  - AI companies
  - large language model providers
  - foundation model companies
description: Companies that develop and operate large language model products offered to consumers or businesses. Includes both API providers and consumer-facing product operators.
---
```

The five entity schema fields: `name` (required), `type` (required), `website` (omitted -- no authoritative URL for a sector), `aliases` (optional, included), `description` (required).

### Step 3 -- Create initial sector claim

~~Claim migration~~ -- the `existential-safety-score` claim that was originally scoped for migration was deleted in the 2026-04-26 prep pass and does not exist in `research/claims/anthropic/` or anywhere else. There is nothing to migrate.

Instead, create an initial claim at the correct path from the start:

```
research/claims/sectors/ai-llm-producers/has-signed-safety-commitments.md
```

Set `entity: sectors/ai-llm-producers` in the frontmatter. A demo claim was created on 2026-05-01; see the Demo implementation section below.

### Step 4 -- Cross-links (v0.1.0 scope)

No new route is needed for v0.1.0. Verify that:

- The sector entity appears in the `/claims` list once the entity file exists and a claim references it.
- Company entity pages that share scope with this claim (e.g., `anthropic`) can link to it via the existing cross-link pattern. No code change needed if the claim's `entity:` field is correct.

---

## Future work

**Total estimate**: ~3-6 hours, mostly frontend scaffolding. The data model already supports sectors.

### Dedicated `/sectors/` route (~2-4 hours)

The entity schema (`content.config.ts`, line 193) and content collection already support `type: sector`. This is a page scaffolding task only.

- Create `src/pages/sectors/index.astro` -- sector list page, mirrors `src/pages/companies/index.astro`
- Create `src/pages/sectors/[...slug].astro` -- sector entity page, mirrors `src/pages/entities/[...slug].astro`
- Register routes in nav and sitemap config
- Verdict distribution and claim list components already work generically -- wire up the sector entity slug

Acceptance bar: `/sectors/ai-llm-producers` renders with its claim list and verdict distribution. The sector appears in the `/sectors/` index. Navigation links to it from relevant company pages.

### Sector-scoped criteria templates (~1-2 hours)

Two sector templates are already active in `research/templates.yaml`: `ai-producers-signed-safety-commitments` and `fli-2025-safety-index-existential-score`. The `entity_type: sector` value is already in the `criteria` collection schema (`content.config.ts`, line 216). No schema change is needed.

Remaining work:

- Decide which criteria make sense at sector level vs. company level before adding more templates
- Add templates to `research/templates.yaml` under `templates` (not `inactive_templates`) as new sectors are created
- Consider a sector-level sustainability transparency claim (does the sector have a shared reporting standard?) as a next candidate

Acceptance bar: at least one new sector template is active and generates a claim via the pipeline.

---

## New sectors to consider

Candidates for future sector entities, evaluated against the `ai-llm-producers` precedent.

### Hyperscaler data centers

Companies operating massive cloud and AI compute infrastructure: AWS, Azure, Google Cloud, Oracle Cloud, CoreWeave.

- What makes it a sector: these companies share infrastructure-level responsibility for AI energy and water consumption regardless of which AI products run on top
- Relevant claim topics: energy use and renewable energy pledges (`environmental-impact`), water consumption and water stress (`environmental-impact`), embodied carbon in hardware (`environmental-impact`), PUE (power usage effectiveness) disclosure
- Overlap with `ai-llm-producers`: some companies (Google, Microsoft/Azure) appear in both; claims at the hyperscaler level are about infrastructure, not model behavior
- Content collection note: claims would live under `research/claims/sectors/hyperscaler-data-centers/`; entity file at `research/entities/sectors/hyperscaler-data-centers.md`

### Frontier models

Large foundation models offered via API or consumer product: GPT-4/4o, Claude 3/4, Gemini 1.5/2, Grok, Command R+.

- What makes it a sector: frontier-scale capability and safety properties apply across models regardless of which company built them; the `fli-2025-safety-index-existential-score` template already targets this scope
- Relevant claim topics: safety commitments and evaluations (`ai-safety`), training energy and compute (`environmental-impact`), capability evaluation disclosure (`ai-safety`, `industry-analysis`)
- Overlap with `ai-llm-producers`: significant -- `ai-llm-producers` covers the companies; `frontier-models` would cover the models as a class; keep them separate only if you have claims that apply to models-as-artifacts rather than companies-as-actors
- Content collection note: consider whether this is better handled as a `topic` entity or a `sector` entity; `sector` fits if you want verdict distributions across frontier models as a class

### Open weight models

Model families with publicly released weights: Llama, Mistral, Falcon, Qwen, Gemma.

- What makes it a sector: shared property (public weights) creates shared claim space around auditability, dual-use risk, and downstream energy cost
- Relevant claim topics: safety evaluations and red-teaming disclosure (`ai-safety`), dual-use risk documentation (`ai-safety`, `regulation-policy`), training energy and dataset transparency (`environmental-impact`, `ai-safety`)
- Overlap with `ai-llm-producers`: most open weight producers are also `ai-llm-producers`; the sector claim is about the open-weight release decision, not the company's overall product portfolio
- Content collection note: claims would sit alongside frontier-model claims structurally; `research/claims/sectors/open-weight-models/`

---

## Demo implementation (2026-05-01)

Created to verify the UI renders sector entities correctly before building the `/sectors/` route.

- Entity: `research/entities/sectors/ai-llm-producers.md`
- Claim: `research/claims/sectors/ai-llm-producers/has-signed-safety-commitments.md`

Verdict: true, confidence: medium. Sources the UK Frontier AI Safety Commitments (2023) and FLI open letter co-signed by major AI/LLM producers. Confidence is medium because the commitments are voluntary with no enforcement mechanism.

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (stub creation) | initial | Stub scaffolded from v0.1.0-roadmap.md §4 |
| 2026-04-22 | agent | expansion | Expanded from industry-claims_stub.md; renamed to sector-claims.md |
| 2026-05-01 | agent | status update | Updated status; rewrote Step 3 (migration moot); expanded Future work with estimates; added Demo implementation section |
| 2026-05-03 | agent | expansion | Reflected completed implementation; expanded future work with acceptance bars; added new sector candidates section |
