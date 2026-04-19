# Content Model

How research content is structured, stored, and related in the dangerousrobot.org site.

Schemas are defined in `src/content.config.ts` and enforced at build time by Astro's content layer. All research content lives under `research/` as Markdown files with YAML frontmatter.

## Content Types

| Type | Purpose | Base path |
|------|---------|-----------|
| **Entity** | A stable subject we make claims about (company, product, or topic) | `research/entities/` |
| **Claim** | A single factual assertion about an entity, with verdict and evidence | `research/claims/` |
| **Source** | A citable reference -- cite once, reference from many claims | `research/sources/` |

## Directory Conventions

```
research/
  entities/
    companies/{slug}.md      # e.g. anthropic.md
    products/{slug}.md
    topics/{slug}.md
  claims/
    {entity-slug}/            # matches the entity filename
      {claim-id}.md           # e.g. existential-safety-score.md
  sources/
    {yyyy}/                   # year directory
      {slug}.md               # e.g. fli-safety-index.md
```

**Naming rules:**

- Lowercase kebab-case for all slugs
- Entity files sit in a subdirectory matching their type (`companies/`, `products/`, `topics/`)
- Claim files are grouped by entity slug (the entity filename without extension)
- Source files are grouped by publication year

## Schemas

### Entity

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | yes | Display name |
| `type` | enum | yes | `company`, `product`, or `topic` |
| `website` | URL string | no | Official website |
| `aliases` | string[] | no | Alternate names (e.g. product names associated with a company) |
| `description` | string | yes | Short description of the entity |

The Markdown body provides extended context about the entity.

### Claim

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | yes | Human-readable claim statement |
| `entity` | string | yes | Path-style reference to entity: `{type}/{slug}` (e.g. `companies/anthropic`) |
| `category` | enum | yes | One of the taxonomy slugs (see below) |
| `verdict` | enum | yes | `true`, `mostly-true`, `mixed`, `mostly-false`, `false`, `unverified` |
| `confidence` | enum | yes | `high`, `medium`, `low` |
| `as_of` | date | yes | Date the verdict was last evaluated |
| `sources` | string[] | yes | List of source IDs (e.g. `2025/fli-safety-index`) |
| `recheck_cadence_days` | number | no | Days between reviews; defaults to 60 |
| `next_recheck_due` | date | no | When this claim should next be reviewed |

The Markdown body contains the claim narrative -- the human-readable explanation of the verdict and evidence.

### Source

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `url` | URL string | yes | Original source URL |
| `archived_url` | URL string | no | Wayback Machine or permanent archive link |
| `title` | string | yes | Source title |
| `publisher` | string | yes | Publishing organization |
| `published_date` | date | no | Original publication date |
| `accessed_date` | date | yes | When the source was retrieved |
| `kind` | enum | yes | `report`, `article`, `documentation`, `dataset`, `blog`, `video`, `index` |
| `summary` | string | yes | Max 200 characters; must not paraphrase beyond 30 words |
| `key_quotes` | string[] | no | Notable direct quotes from the source |

The Markdown body provides additional context or analysis of the source.

## Relationships

```
Entity  <----  Claim  ---->  Source(s)
  1          many      many-to-many
```

- **Claim to Entity:** Each claim has an `entity` field that references an entity by its path relative to `research/entities/` (without `.md`). Example: `companies/anthropic`.
- **Claim to Source:** Each claim has a `sources` array containing source IDs. A source ID is its path relative to `research/sources/` (without `.md`). Example: `2025/fli-safety-index`.
- **Source to Claim:** Sources are referenced by ID from claims. There is no back-reference in the source file -- the relationship is one-directional in the data, resolved at query time.

Claims never contain raw URLs for evidence. All citations go through source files so that metadata, archive links, and quotes are maintained in a single place.

## Claim Category Taxonomy

| Slug | Description |
|------|-------------|
| `ai-safety` | Independent evaluations of AI company/provider safety |
| `environmental-impact` | Energy, emissions, water, renewable energy claims |
| `product-comparison` | Feature/practice comparisons across AI products |
| `consumer-guide` | How to opt out, disable, or limit AI features |
| `ai-literacy` | Decision frameworks, when/how to use AI thoughtfully |
| `data-privacy` | What happens to your data across AI services |
| `industry-analysis` | Corporate structure, business models, ownership |
| `regulation-policy` | Government oversight, AI policy landscape |

## Frontmatter Examples

### Minimal Entity

```yaml
---
name: Anthropic
type: company
description: AI safety company and developer of the Claude family of large language models.
---
```

### Minimal Claim

```yaml
---
title: No AI company scores above D on existential safety
entity: companies/anthropic
category: ai-safety
verdict: "true"
confidence: high
as_of: 2026-04-18
sources:
  - 2025/fli-safety-index
---
```

### Minimal Source

```yaml
---
url: https://futureoflife.org/ai-safety-index-winter-2025/
title: AI Safety Index, Winter 2025
publisher: Future of Life Institute
accessed_date: 2026-04-18
kind: index
summary: Independent safety assessment grading 8 AI companies across 6 domains.
---
```

## Build-Time Validation

Astro's content layer validates all frontmatter against the Zod schemas in `src/content.config.ts` during `astro build` and `astro dev`. Invalid frontmatter -- missing required fields, wrong enum values, malformed URLs -- will fail the build with a descriptive error.
