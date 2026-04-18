# Work Item: Research Schemas & Content Structure

**Phase**: 2 (Schemas, Content & Site -- MVP)
**Status**: not started
**Depends on**: Phase 1 (repo hygiene)
**Co-authored with**: astro-site.md (Zod schemas and Content Collections are the same design decision)

## Goal

Define the research category taxonomy, create Zod schemas in Astro's content config, set up the directory structure. The schemas are defined once in `src/content.config.ts` and enforced at build time by Astro -- no separate JSON Schema files needed for MVP.

## Critical First Step: Spike Content Collections

Before building the schema layer, verify that Astro can load Content Collections from `research/` (outside `src/`). Create one test collection, one test file, run `npm run build`. If it fails, evaluate fallbacks (symlinks, `src/content/` location, copy step).

## Research Category Taxonomy

Types of research dangerousrobot.org could host. This taxonomy informs the `category` field on claims -- it doesn't commit us to covering all categories.

| Category | Description | Example from existing content |
|----------|-------------|-------------------------------|
| **AI Safety Assessments** | Independent evaluations of AI company/provider safety | FLI Safety Index scorecard |
| **Environmental Impact** | Energy, emissions, water, renewable energy claims | TL transparency page, energy estimation review |
| **Product Comparisons** | Feature/practice comparisons across AI products | Chatbot comparison table |
| **Consumer Guides** | How to opt out, disable, limit AI features | "Turn Off AI" guide |
| **AI Literacy** | Decision frameworks, when/how to use AI thoughtfully | "Should I Use AI?" decision tree |
| **Data Privacy** | What happens to your data across AI services | (placeholder on responsible-ai page) |
| **Industry Analysis** | Corporate structure, business models, ownership | Comparison table footnotes |
| **Regulation & Policy** | Government oversight, AI policy landscape | (placeholder on responsible-ai page) |

## Directory Structure

```
research/
  entities/
    companies/
    products/
    topics/
  claims/
    {entity-slug}/
  sources/
    {yyyy}/
  QUEUE.md
```

No `research/schemas/` directory needed -- schemas live in `src/content.config.ts`.

## Schema Definitions (Zod, in `src/content.config.ts`)

### Source

```typescript
const sources = defineCollection({
  type: 'content',
  schema: z.object({
    url: z.string().url(),
    archived_url: z.string().url().optional(),
    title: z.string(),
    publisher: z.string(),
    published_date: z.coerce.date().optional(),
    accessed_date: z.coerce.date(),
    kind: z.enum(['report', 'article', 'documentation', 'dataset', 'blog', 'video', 'index']),
    summary: z.string().max(200),
    key_quotes: z.array(z.string()).optional(),
  }),
})
```

### Claim

```typescript
const claims = defineCollection({
  type: 'content',
  schema: z.object({
    entity: z.string(),              // slug ref to entity
    category: z.string(),            // from taxonomy above, kebab-case
    verdict: z.enum(['true', 'mostly-true', 'mixed', 'mostly-false', 'false', 'unverified']),
    confidence: z.enum(['high', 'medium', 'low']),
    as_of: z.coerce.date(),
    sources: z.array(z.string()),    // slug refs to source files
    review_cadence_days: z.number().default(60),
    next_review_due: z.coerce.date().optional(),
  }),
})
```

### Entity

```typescript
const entities = defineCollection({
  type: 'content',
  schema: z.object({
    name: z.string(),
    type: z.enum(['company', 'product', 'topic']),
    website: z.string().url().optional(),
    aliases: z.array(z.string()).optional(),
    description: z.string(),
  }),
})
```

Body content: prose rationale for claims, extended notes for sources, background context for entities.

## Tasks

- [ ] Spike: verify Astro Content Collections load from `research/` outside `src/`
- [ ] Create directory scaffold under `research/`
- [ ] Write Zod schemas in `src/content.config.ts`
- [ ] Document category taxonomy in `AGENTS.md` (add `schemas/` reference)

## Design Considerations

**ID strategy**: Filename slug is the ID. No `id` field in frontmatter.

**Category as a field, not a directory**: Claims grouped by entity in filesystem, `category` as frontmatter field.

**Entity subtypes**: Companies, products, topics live in subdirectories but share one `entities` collection. Subtype determined by `type` field, not directory. Routing uses flat slugs (`/entities/openai`), not nested (`/entities/companies/openai`).

**JSON Schema files**: Deferred. Astro's Zod validation at build time is sufficient for MVP. Add JSON Schema files later if PydanticAI agents need a shared schema format (Phase 4).

## Estimated Scope

Medium. Schema design requires thought; directory creation is mechanical. Co-author with astro-site.md to avoid drift.
