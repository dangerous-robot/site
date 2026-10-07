# Content Model

How research content is structured, stored, and related in the dangerousrobot.org site.

Schemas are defined in `src/content.config.ts` and enforced at build time by Astro's content layer. All research content lives under `research/` as Markdown files with YAML frontmatter.

## Content Types

| Type | Purpose | Base path |
|------|---------|-----------|
| **Entity** | A stable subject we make claims about (company, product, or subject) | `research/entities/` |
| **Claim** | A single factual assertion about an entity, with verdict and evidence | `research/claims/` |
| **Source** | A citable reference -- cite once, reference from many claims | `research/sources/` |
| **Criterion** | A reusable claim template applied uniformly across entities | `research/templates.yaml` |

## Directory Conventions

```
research/
  entities/
    companies/{slug}.md      # e.g. anthropic.md
    products/{slug}.md
    subjects/{slug}.md
  claims/
    {entity-slug}/            # matches the entity filename
      {claim-id}.md           # e.g. existential-safety-score.md
  sources/
    {yyyy}/                   # year directory
      {slug}.md               # e.g. fli-safety-index.md
```

**Naming rules:**

- Lowercase kebab-case for all slugs
- Entity files sit in a subdirectory matching their type (`companies/`, `products/`, `subjects/`)
- Claim files are grouped by entity slug (the entity filename without extension)
- Source files are grouped by publication year

## Schemas

### Entity

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | yes | Display name |
| `type` | enum | yes | `company`, `product`, or `subject` |
| `website` | URL string | no | Official website |
| `legal_name` | string | no | Registered legal name; must be non-empty when present |
| `verification_status` | enum | no | `verified`, `unverified-startup`, or `unverified-other` |
| `aliases` | string[] | no | Alternate names (e.g. product names associated with a company) |
| `description` | string | yes | Short description of the entity |
| `founded` | number | no | Founding year; integer between 1800 and the current year (checked at build time) |
| `parent_company` | string | no | Slug ref of the form `companies/{slug}` pointing at another entity |
| `search_hints` | object | no | Optional `include` and `exclude` string arrays; hints for the pipeline's source searches |
| `sec_cik` | string | no | SEC CIK identifier; must be a 10-digit string |

The Markdown body provides extended context about the entity.

### Claim

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | yes | Human-readable claim statement |
| `seo_title` | string | no | Short title for `<title>` tags (≤42 chars, leaving room for ` - Dangerous Robot`). Analyst writes this on every generated claim; falls back to `title` if absent. |
| `entity` | string | yes | Path-style reference to entity: `{type}/{slug}` (e.g. `companies/anthropic`) |
| `topics` | enum[] | yes | 1-3 slugs from the topic taxonomy (see [Claim Topic Taxonomy](#claim-topic-taxonomy) below) |
| `verdict` | enum | yes | `true`, `mostly-true`, `mixed`, `mostly-false`, `false`, `unverified`, `not-applicable` |
| `confidence` | enum | yes | `high`, `medium`, `low` |
| `verification_level` | enum | no | Source-pool diversity signal, set by the analyst from `independence` and `kind` on the claim's sources: `claimed`, `self-reported`, `partially-verified`, `independently-verified`, `multiply-verified`. See [source-quality.md](source-quality.md) |
| `cap_rationale` | string | no | One-sentence explanation when the confidence cap fires (a `verification_level` of `claimed` or `self-reported` caps `confidence` at `low`); max 400 chars. See [source-quality.md](source-quality.md) |
| `source_overrides` | object[] | no | Per-claim overrides of source-level fields, used when a source classified `independent` is actually restating a primary disclosure for this claim. Each entry: `source`, `reason`, optional `independence`. See [source-quality.md § Source overrides on claims](source-quality.md#source-overrides-on-claims) |
| `takeaway` | string | no | Optional reader-facing one-liner; max 200 chars; rendered under the verdict badge |
| `criteria_slug` | string | no | Optional back-reference to the criterion template this claim was generated from |
| `status` | enum | yes (default: `draft`) | Publication status: `draft`, `published`, `archived`, `blocked`. Production builds a claim page only for `published` and `archived`; the dev server builds all four |
| `phase` | enum | no | Pipeline progress while in flight; absent on terminal states. One of `researching`, `ingesting`, `analyzing`, `evaluating` |
| `blocked_reason` | enum | no | Set together with `status: blocked`; one of `insufficient_sources`, `terminal_fetch_error`, `analyst_error` |
| `as_of` | date | yes | Date the verdict was last evaluated |
| `sources` | string[] | yes | List of source IDs (e.g. `2025/fli-safety-index`) |
| `recheck_cadence_days` | number | no | Days between reviews; defaults to 60 |
| `next_recheck_due` | date | no | When this claim should next be reviewed |
| `tags` | string[] | no | Free-form operator-set tags; defaults to `[]`. Behavioral tags are defined in [AGENTS.md § Claim Tags](../../AGENTS.md#claim-tags) |
| `audit` | object | no | Pipeline audit sidecar data, loaded from a paired `.audit.yaml` file (see below) |

The Markdown body contains the claim narrative -- the human-readable explanation of the verdict and evidence.

### Source

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `url` | URL string | yes | Original source URL |
| `archived_url` | URL string | no | Wayback Machine or permanent archive link. The pipeline sets it after each ingest (archive.org TimeGate, then Save Page Now; a link the ingest model writes itself is dropped); `dr wayback-backfill` adds it to existing files. Commands that write nothing (`dr claim-probe`, `dr step-ingest` without `--write`) check TimeGate only and never ask archive.org to capture a page |
| `title` | string | yes | Source title |
| `publisher` | string | yes | Publishing organization |
| `published_date` | date | no | Original publication date |
| `accessed_date` | date | yes | When the source was retrieved |
| `kind` | enum | yes | `report`, `article`, `documentation`, `dataset`, `blog`, `video`, `index`, `paper` |
| `source_type` | enum | no | Classification of source authority: `primary`, `secondary`, `tertiary` |
| `independence` | enum | no | Whether the source is authored by the covered entity or independently of it: `first-party`, `independent`, `unknown`. Feeds claim-level `verification_level`. See [source-quality.md](source-quality.md) |
| `summary` | string | yes | Max 200 characters; must not paraphrase beyond 30 words |
| `key_quotes` | string[] | no | Notable direct quotes from the source |

The Markdown body provides additional context or analysis of the source.

### Claim Audit Sidecar

The claims collection uses a custom loader (`claims-with-audit`) that reads each `.md` file and, if a paired `.audit.yaml` file exists at the same path, merges its contents into the claim's `audit` field. This is the mechanism behind the AI Research Audit Trail feature.

The `audit` object has the shape:

| Field | Type | Notes |
|-------|------|-------|
| `schema_version` | number | Sidecar format version |
| `pipeline_run.ran_at` | date | When the pipeline run occurred |
| `pipeline_run.model` | string | Model used |
| `pipeline_run.agents` | string[] | Agents that participated |
| `models_used` | map | Per-agent model lineage (agent name to model string). Optional during the v1 transition: sidecars written before the field landed validate without it; new sidecars always carry it |
| `sources_consulted` | array | Sources the pipeline considered (`id`, `url`, `title`, `ingested`, optional `acquisition` and `archive`) |
| `sources_consulted[].acquisition` | object | Optional record of how the source was acquired |
| `sources_consulted[].acquisition.stage` | enum | Pipeline stage that acquired the source: `research` or `ingest` |
| `sources_consulted[].acquisition.origin` | enum | Optional provider the source came from: `brave`, `tavily`, `arxiv`, `s2`, `openalex`, `edgar` |
| `sources_consulted[].acquisition.recovered_via` | enum | Optional: `archive_org`, set when the source was recovered via archive.org |
| `sources_consulted[].acquisition.outcome` | enum | Optional: `matched` or `recovered` |
| `sources_consulted[].acquisition.query` | string | Optional search query used |
| `sources_consulted[].acquisition.paper_id` | string | Optional paper identifier |
| `sources_consulted[].acquisition.filing_accession` | string | Optional filing accession identifier |
| `sources_consulted[].archive` | object | Optional. Outcome of the archive.org lookup the pipeline runs after ingesting a source; absent on sources reused from disk. `dr step-audit --write` carries it over |
| `sources_consulted[].archive.status` | enum | `found` (the source got an `archived_url`), `failed` (rate-limited after one retry, Save Page Now returned no dated snapshot, another error, or the lookup's time limit) or `not-attempted` (run with `--skip-wayback`) |
| `sources_consulted[].archive.error` | string | Optional. Why a `failed` lookup failed, e.g. `archive.org TimeGate check failed (HTTP 429)` |
| `audit` | object or null | Analyst/Evaluator verdict comparison block; may be `null` |
| `audit.analyst_verdict` | string | Verdict from the Analyst agent |
| `audit.auditor_verdict` | string | Verdict from the Auditor agent |
| `audit.analyst_confidence` | string | Confidence from the Analyst agent |
| `audit.auditor_confidence` | string | Confidence from the Auditor agent |
| `audit.verdict_agrees` | boolean | Whether the analyst and evaluator verdicts agreed |
| `audit.confidence_agrees` | boolean | Whether the analyst and evaluator confidence levels agreed |
| `audit.needs_review` | boolean | Whether human review is flagged |
| `audit.auditor_reasoning` | string | Optional. The Evaluator's reasoning, shown on the claim page |
| `audit.evidence_gaps` | string[] | Optional. Gaps the Evaluator found in the evidence, shown on the claim page |
| `audit.needs_review_reasons` | string[] | Optional. Why the claim was flagged: `verdict disagreement`, `confidence gap`, `2+ evidence gaps`; empty when `needs_review` is false |
| `human_review.reviewed_at` | date or null | When a human reviewed |
| `human_review.reviewer` | string or null | Reviewer identity |
| `human_review.notes` | string or null | Human review notes |
| `human_review.pr_url` | URL or null | PR where the review happened |
| `human_review.verdict_override` | object or null | Optional. `{from, to}` when the reviewer's verdict differs from `audit.analyst_verdict`; written by `dr review`. Lint `verdict-sidecar-mismatch` accepts a published verdict that differs from the analyst's only when this matches |

`dr claim-refresh` on a published claim also writes a top-level `refresh` block, which the site does not read. It is present only while the refresh awaits re-approval; approval or archiving removes it, and `dr publish` skips the claim while it is present. If the verdict changed, approval requires a one-line summary and adds a `corrections` entry to the claim (`date`, `summary`, `previous_verdict`), newest first.

| Field | Type | Notes |
|-------|------|-------|
| `refresh.refreshed_at` | timestamp | When the refresh that took the snapshot ran |
| `refresh.previous` | object | The last published state, read before the overwrite: `status`, `verdict`, `confidence`, `title`, `as_of`, `sources`, `reviewed_at`, `reviewer`, `ran_at`. A second refresh before re-approval keeps it unchanged |
| `refresh.dropped_sources` | string[] | Source ids in `refresh.previous.sources` that the latest run no longer cites |

Sidecar files are optional. Claims without a sidecar have no `audit` field.

The Evaluator role is implemented in `pipeline/auditor/`; sidecar field names retain the `auditor_` prefix in v1 and will be renamed when the package directory is renamed (post-v1).

### Criterion

Criteria are loaded from a single YAML file (`research/templates.yaml`), not via glob. Each criterion defines a claim template that can be applied uniformly across entities of a given type.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `slug` | string | yes | Unique identifier |
| `text` | string | yes | The claim template text |
| `entity_type` | enum | yes | `company`, `product`, or `subject` |
| `subjects` | string[] | conditional | Required and non-empty when `entity_type === 'subject'`; forbidden otherwise. Each value is a path of the form `subjects/{slug}` pinning the criterion to specific subject entities. |
| `topics` | enum[] | yes | 1-3 slugs from the topic taxonomy (see [Claim Topic Taxonomy](#claim-topic-taxonomy)) |
| `core` | boolean | yes (default: false) | Whether this is a core/required criterion |
| `notes` | string | no | Editorial notes |
| `vocabulary` | map | no | Entity-type-specific vocabulary substitutions |

Subject-type criteria use `subjects` for explicit pairing with subject entities; company/product criteria match by `entity_type` alone.

## Relationships

```
Entity  <----  Claim  ---->  Source(s)
  1          many      many-to-many
               |
           Criterion (optional)
```

- **Claim to Entity:** Each claim has an `entity` field that references an entity by its path relative to `research/entities/` (without `.md`). Example: `companies/anthropic`.
- **Claim to Source:** Each claim has a `sources` array containing source IDs. A source ID is its path relative to `research/sources/` (without `.md`). Example: `2025/fli-safety-index`.
- **Source to Claim:** Sources are referenced by ID from claims. There is no back-reference in the source file -- the relationship is one-directional in the data, resolved at query time.
- **Claim to Criterion:** A `criteria_slug` on a claim links it back to the criterion template it was generated from. The relationship is optional and one-directional.

Claims never contain raw URLs for evidence. All citations go through source files so that metadata, archive links, and quotes are maintained in a single place.

## Claim Topic Taxonomy

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
topics:
  - ai-safety
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

## Editorial Collections

Hand-authored content under `src/content/` is defined in the same `src/content.config.ts` but is not part of the research model above: it has no entity, claim, or source references. The `resources` collection is described in [site.md](site.md#content-collections).

### Writing

Blog posts for `/writing`. One Markdown file per post at `src/content/writing/{slug}.md`, loaded by `glob()`; the filename (without `.md`) is the post id and URL slug (`/writing/{slug}`). Posts can be written by hand or through the Sveltia CMS admin, whose `public/admin/config.yml` mirrors this schema.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | yes | |
| `description` | string | yes | Max 200 characters; longer fails the build. Used in the post list, meta description, and RSS item |
| `pubDate` | date | yes | Coerced from `YYYY-MM-DD`; sorts the list and feed newest first |
| `updatedDate` | date | no | Shown in the byline when present |
| `author` | string | no | Default `Brandon Faloona` |
| `ai_assisted` | boolean | no | Default `false`; adds "with AI assistance" to the byline |
| `draft` | boolean | no | Default `false` |
| `tags` | string[] | no | Default `[]`; free-form (no enum). Emitted as RSS categories |
| `featured` | boolean | no | Default `false`. "Feature on homepage": the newest featured entry across writing, actions and resources fills the homepage spotlight, with its `description` under the title. Resources carry the same field |

**Draft behaviour.** Pages read posts through `getPosts()` in `src/lib/writing.ts`: in dev (`astro dev`) drafts are listed and rendered with a "Draft" tag so authors can preview them; in production builds they are filtered out, so no page is generated. The RSS feed (`/writing/rss.xml`) excludes drafts in both dev and production.

### Actions

Things a reader can do. Every action is a petition today, served at `/petitions/{slug}` (no index page). One Markdown file per action at `src/content/actions/{slug}.md`; the Sveltia admin lists the collection as "Petitions". The page renders like a writing post (shared `src/components/PostArticle.astro`) with the sign block under the body. How signatures work: [petitions.md](petitions.md).

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title`, `description`, `pubDate`, `updatedDate`, `author`, `ai_assisted`, `draft` | | | As for writing posts |
| `petition` | string | yes | Slug of the petition row in the dr-api Worker |
| `petition_statement` | string | no | The sentence signers put their name to; set large in the sign block |
| `featured` | boolean | no | As for writing posts. A featured petition quotes `petition_statement` (its description when empty) and adds the count and sign button |

**Draft behaviour.** `getActions()` in `src/lib/actions.ts` applies the same rule as writing: drafts render in dev and are dropped from production builds, including the homepage spotlight.

## Build-Time Validation

Astro's content layer validates all frontmatter against the Zod schemas in `src/content.config.ts` during `astro build` and `astro dev`. Invalid frontmatter -- missing required fields, wrong enum values, malformed URLs -- will fail the build with a descriptive error.
