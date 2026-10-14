# Content Model

How research content is structured, stored, and related in the dangerousrobot.org site.

Schemas are defined in `src/content.config.ts` and enforced at build time by Astro's content layer. All research content lives under `research/` as Markdown files with YAML frontmatter.

## Content Types

| Type | Purpose | Base path |
|------|---------|-----------|
| **Entity** | A stable subject we make claims about (company, product, or subject) | `research/entities/` |
| **Claim** | A single factual assertion about an entity, with verdict and evidence | `research/claims/` |
| **Source** | A citable reference -- cite once, reference from many claims | `research/sources/` |
| **Criterion** | A registry entry: a claim sentence applied uniformly across entities, with a `grading_rule` | `research/templates.yaml` |

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
| `title` | string | yes | Human-readable claim statement; equals `statement` on every claim the pipeline writes |
| `statement` | string | no | The sentence the loop re-runs and the Evaluator grades. For `dr draft --criterion` it is the criterion's text rendered once with the entity name and the file is `<entity-dir>/<criteria_slug>.md`; for an ad hoc claim it is the operator's sentence and the file is `<entity-dir>/<slugify(statement)>.md`; `dr draft --claim --force` re-runs it and keeps the existing path. Claims written before it existed fall back to `title` |
| `seo_title` | string | no | Short title for `<title>` tags (≤42 chars, leaving room for ` - Dangerous Robot`). Analyst writes this on every generated claim; a forced rewrite (`dr draft --claim --force`) keeps an operator's value (one that differs from the analyst's last `seo_title`, recorded in the sidecar's `analyst_record`) while the claim's statement is unchanged; `analyst_record.title` records the statement. Falls back to `title` if absent. |
| `entity` | string | yes | Path-style reference to entity: `{type}/{slug}` (e.g. `companies/anthropic`) |
| `topics` | enum[] | yes | 1-3 slugs from the topic taxonomy (see [Claim Topic Taxonomy](#claim-topic-taxonomy) below) |
| `verdict` | enum | yes | `true`, `mostly-true`, `mixed`, `mostly-false`, `false`, `unverified`, `not-applicable` |
| `confidence` | enum | yes | `high`, `medium`, `low` |
| `verification_level` | enum | no | Source-pool diversity signal, set by the analyst from `independence` and `kind` on the claim's sources: `claimed`, `self-reported`, `partially-verified`, `independently-verified`, `multiply-verified`. See [source-quality.md](source-quality.md) |
| `cap_rationale` | string | no | One-sentence explanation when the confidence cap fires (a `verification_level` of `claimed` or `self-reported` caps `confidence` at `low`); max 400 chars. A forced rewrite (`dr draft --claim --force`) keeps an operator's value (one that differs from the pipeline's last, recorded in the sidecar's `analyst_record`) on every rewrite, even when `verification_level` or `confidence` changed or the write-time level fit lowered the level again, until the operator edits it. A rewrite to an uncapped level or a blocked write keeps it too: the claim page shows it only on a capped level, so it stays unseen until a later rewrite caps the claim again (deleting it from the claim lets the next rewrite take the pipeline's). With no recorded rationale, the existing value is kept only on a capped level while `verification_level` and `confidence` are both unchanged, and not when the level fit wrote the only rationale this run proposed. See [source-quality.md](source-quality.md) |
| `source_overrides` | object[] | no | Per-claim overrides of source-level fields, used when a source classified `independent` is actually restating a primary disclosure for this claim. Each entry: `source`, `reason`, optional `independence`. See [source-quality.md § Source overrides on claims](source-quality.md#source-overrides-on-claims) |
| `takeaway` | string | no | Optional reader-facing one-liner; max 200 chars; rendered under the verdict badge. A forced rewrite keeps the existing value when the analyst gives none, and keeps an operator's (one that differs from the analyst's last, recorded in the sidecar's `analyst_record`) while the analyst's verdict is unchanged |
| `criteria_slug` | string | no | Optional back-reference to the criterion this claim was drafted from (`dr draft --criterion`) or had attached (`dr draft --claim --criterion`, which appends the criterion to `research/templates.yaml` for an ad hoc draft). It is the publish gate: lint reports `published-without-criterion` without it |
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
| `archived_url` | URL string | no | Wayback Machine or permanent archive link. The pipeline sets it after each ingest, and only to a capture that archive.org replays with HTTP 200 for the same page (path case counts): TimeGate's nearest capture, else the newest 200 capture in the CDX index, else a checked Save Page Now capture; a link the ingest model writes itself is dropped. When the live fetch succeeded, a capture older than 90 days or than `published_date` is replaced by a fresh checked capture when one succeeds. `dr wayback-backfill` adds it to existing files, and `dr wayback-backfill --recheck` replaces or removes a link that fails the check. Commands that write nothing (`dr draft --dry-run`, `dr step-ingest` without `--write`) use existing captures only and never ask archive.org to capture a page |
| `title` | string | yes | Source title |
| `publisher` | string | yes | Publishing organization |
| `published_date` | date | no | Original publication date |
| `accessed_date` | date | yes | When the source was retrieved |
| `kind` | enum | yes | `report`, `article`, `documentation`, `dataset`, `blog`, `video`, `index`, `paper` |
| `source_type` | enum | no | Classification of source authority: `primary`, `secondary`, `tertiary` |
| `independence` | enum | no | Whether the source is authored by the covered entity or independently of it: `first-party`, `independent`, `unknown`. Feeds claim-level `verification_level`. See [source-quality.md](source-quality.md) |
| `summary` | string | yes | Max 200 characters; must not paraphrase beyond 30 words |
| `key_quotes` | string[] | no | Notable direct quotes from the source, as bare page text (no wrapping quotation marks or attribution) |

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
| `pipeline_run.run_id` | string | Optional. One id per claim run (one per `dr draft`); written by every full run |
| `pipeline_run.level_clamp` | string | Present only when the write-time level fit lowered the analyst's `verification_level`; says from what to what and why (see `docs/architecture/source-quality.md` § Level fit to the written sources) |
| `models_used` | map | Per-agent model lineage (agent name to model string). Optional during the v1 transition: sidecars written before the field landed validate without it; new sidecars always carry it. `dr step-audit --write` replaces only the `auditor` entry and keeps the others; every other write records only the agents that run |
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
| `sources_consulted[].archive.status` | enum | `found` (the source got an `archived_url`), `failed` (no capture replays with HTTP 200 for the same page, rate-limited after one retry, Save Page Now returned no dated snapshot or captured an error page, another error, or the lookup's time limit) or `not-attempted` (run with `--skip-wayback`) |
| `sources_consulted[].archive.error` | string | Optional. Why a `failed` lookup failed, e.g. `archive.org TimeGate check failed (HTTP 429)` or `archive.org capture is an error page (HTTP 404)` |
| `audit` | object or null | Analyst/Evaluator verdict comparison block; `null` when the Evaluator did not grade the analysis on disk: a blocked run, or `dr step-analyze --write --force`, which clears it until `dr step-audit --write` grades the new analysis (the claim page then shows the Evaluator check as unavailable, and `dr review --approve` records no `verdict_override`) |
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

The forced rewrites `dr draft --claim --force`, `dr step-analyze --write --force` and `dr draft --force`, on a published claim return it to `status: draft`, reset `human_review` and write a top-level `refresh` block, which the site does not read (on an archived or blocked claim they reset `human_review` the same way, with no `refresh` block). It is present only while the refresh awaits re-approval; approval or archiving removes it, and `dr publish` skips the claim while it is present. A blocked or failed run writes nothing, so the claim and its sidecar stay as they were. If the verdict changed, approval requires a one-line summary and adds a `corrections` entry to the claim (`date`, `summary`, `previous_verdict`), newest first.

| Field | Type | Notes |
|-------|------|-------|
| `refresh.refreshed_at` | timestamp | When the refresh that took the snapshot ran |
| `refresh.previous` | object | The last published state, read before the overwrite: `status`, `verdict`, `confidence`, `title`, `as_of`, `sources`, `reviewed_at`, `reviewer`, `ran_at`. A second refresh before re-approval keeps it unchanged |
| `refresh.dropped_sources` | string[] | Source ids in `refresh.previous.sources` that the latest run no longer cites |

The pipeline also writes a top-level `analyst_record` block, which the site does not read: what the analyst last proposed for the claim (`title`, which records the claim's statement, and `seo_title`, `verdict`, `takeaway`, and `cap_rationale` after the level fit), never a value a keep rule left on disk. A forced rewrite compares against it to tell an operator's `seo_title`, `takeaway` or `cap_rationale` from the pipeline's; a blocked write leaves it unchanged, and a field the analyst leaves out keeps its last value. A claim whose sidecar has no `analyst_record` treats any `seo_title` or `takeaway` on disk as the operator's, so that value is kept on every later rewrite while the claim's statement (for `seo_title`) or the analyst's verdict (for `takeaway`) is unchanged; deleting the field from the claim lets the next rewrite take the analyst's. `scripts/backfill_analyst_record.py` writes the record for such claims from each claim's last pipeline-written version in git (dry run by default; the script's docstring states how that commit is chosen).

Sidecar files are optional. Claims without a sidecar have no `audit` field.

The Evaluator role is implemented in `pipeline/auditor/`; sidecar field names retain the `auditor_` prefix in v1 and will be renamed when the package directory is renamed (post-v1).

### Criterion

Criteria are loaded from a single YAML file (`research/templates.yaml`), not via glob. Each criterion defines a claim sentence that can be applied uniformly across entities of a given type.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `slug` | string | yes | Unique identifier |
| `text` | string | yes | The claim sentence, with a placeholder for the entity name that `dr draft --criterion` replaces once and stores as the claim's `statement` |
| `entity_type` | enum | yes | `company`, `product`, or `subject` |
| `subjects` | string[] | conditional | Required and non-empty when `entity_type === 'subject'`; forbidden otherwise. Each value is a path of the form `subjects/{slug}` pinning the criterion to specific subject entities. |
| `topics` | enum[] | yes | 1-3 slugs from the topic taxonomy (see [Claim Topic Taxonomy](#claim-topic-taxonomy)) |
| `core` | boolean | yes (default: false) | Whether this is a core/required criterion |
| `notes` | string | no | Shown on the public criteria page; the pipeline no longer sends it to the agents (`grading_rule` replaces that); write it as public text |
| `grading_rule` | string | no | Grading guidance sent to the Analyst and the Evaluator with the claim text (scope, verdict mapping, narrative coverage), never cited as evidence. Seeded from `notes` for the active criteria that had one, each marked `# TODO Brandon: rewrite as a grading rule` |
| `vocabulary` | map | no | Site-only: the home page bolds its terms and the matrix check reads it. The pipeline ignores it and no slot is rendered into a claim's `statement` |

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
- **Claim to Criterion:** A `criteria_slug` on a claim links it back to the criterion it was drafted from or had attached. The relationship is optional and one-directional.

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
