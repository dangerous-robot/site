# Plan: SEO copy and content standards

| Milestone | Status |
|-----------|--------|
| Title strategy | `[ ] ready to implement` |
| Meta description templates | `[ ] ready to implement` |
| og:image strategy | `[ ] planned` |
| Content depth guidance | `[ ] editorial / ongoing` |
| Keyword targeting guidance | `[ ] editorial / ongoing` |

---

## Background

This plan covers editorial decisions and schema additions for SEO. It does not cover code implementation; a companion plan handles the Astro template changes needed to apply these decisions.

Audience: journalists, researchers, and policy people fact-checking AI sustainability claims. Search queries the site should rank for include things like "Microsoft carbon negative claim", "Is Claude carbon neutral", "Anthropic environmental commitments", "AI company energy use". The site's advantage is specificity and sourcing; the title and description strategy should reinforce that.

### Current state summary

`Base.astro` renders `<title>{title} - Dangerous Robot</title>`. Each page type passes a different `title` prop:

| Page type | Current title passed |
|-----------|---------------------|
| Homepage | `"Dangerous Robot — AI transparency research"` (renders as `"Dangerous Robot — AI transparency research - Dangerous Robot"` — doubled brand name, bug) |
| Claim | `claim.data.title` — verbatim claim text |
| Entity | `entity.data.name` — e.g., `"Microsoft"` |
| Topic | topic label — e.g., `"Environmental Impact"` |
| Criteria | `std.data.text` — verbatim criterion text |
| Source | `source.data.title` — source document title |

No `description` prop is passed by any page type. The layout default is: `"Structured research backing claims about AI products and companies."` Every page uses this same description.

No `og:image` tag exists anywhere.

---

## Milestone: Title strategy

**Status:** `[ ] ready to implement`

The layout appends ` - Dangerous Robot` to whatever title is passed. Decisions below define what each page type should pass.

### Claim pages

**Problem:** Claim titles are written as full sentences and often exceed 60 characters. Google truncates `<title>` at approximately 600px (~60–65 characters). Examples from current content:

- `"Claude discloses its energy sourcing"` — 37 chars, fine
- `"Claude is hosted on renewable energy"` — 37 chars, fine
- `"Anthropic donates to environmental causes"` — 42 chars, fine
- Expected future titles like `"Does Microsoft disclose its AI energy sourcing?"` — 49 chars, marginal
- Longer claim titles from the criteria vocabulary like `"Microsoft has publicly-traded corporate structure"` — 50 chars, marginal

The truncation risk is real but not universal. Options:

**Option A — `seo_title` field in claim frontmatter (manually authored, replaces the full `<title>` value)**
- Highest quality. The short title can be written to include the entity name and a keyword cluster naturally.
- Most operator effort. Every new claim requires a second title field.
- Tradeoff: operators must write two titles; the `seo_title` may drift from the research label over time.

**Option B — Auto-truncate at 50 chars + ellipsis for `<title>` only; full text in `<h1>`**
- Zero editorial effort. Automatically handles any length.
- Tradeoff: truncation is dumb — it cuts at the character limit, not at a word boundary or meaning boundary. A title like `"Anthropic publishes a sustainability report"` would truncate to `"Anthropic publishes a sustainabili…"`. That reads poorly in SERPs.

**Option C — Template-based: `"{Entity} — {verdict label} | Dangerous Robot"` auto-generated**
- Zero editorial effort, predictable format, includes entity name (good for disambiguation).
- Tradeoff: loses the specific claim in the title entirely. A user searching for "Microsoft carbon negative claim" won't see a title that reflects the specific claim they're looking for. Also, verdict labels change — a title built on the current verdict will be stale after reassessment without a rebuild.

**Decision: Option A** for published claims; treat `seo_title` as optional during the pipeline alpha and add a `dr lint` check (`missing-seo-title`) at info severity once the field exists. When `seo_title` is absent, fall back to the full `title` (current behavior). This means no regression for existing claims.

**Title construction when `seo_title` is present:** `seo_title` replaces the value passed to the layout entirely. The layout still appends ` - Dangerous Robot` (18 chars). So `seo_title` must leave room for that suffix within the ~60-char SERP limit: `seo_title` must be 42 characters or fewer (`60 - 18 = 42`).

**Schema addition:** `seo_title: z.string().max(42).optional()`

**Examples:**

| Claim title (full) | `seo_title` (max 42 chars) | Full `<title>` |
|--------------------|---------------------------|----------------|
| `"Claude discloses its energy sourcing"` | `"Claude: energy sourcing disclosure"` (35) | `"Claude: energy sourcing disclosure - Dangerous Robot"` (52) |
| `"Claude is hosted on renewable energy"` | `"Claude: renewable energy hosting"` (33) | `"Claude: renewable energy hosting - Dangerous Robot"` (51) |
| `"Anthropic donates to environmental causes"` | `"Anthropic: environmental donations"` (35) | `"Anthropic: environmental donations - Dangerous Robot"` (52) |
| `"Microsoft commits to carbon negative by 2030"` | `"Microsoft: carbon negative by 2030"` (35) | `"Microsoft: carbon negative by 2030 - Dangerous Robot"` (52) |

Note: the fourth example uses `"Microsoft commits to carbon negative by 2030"` as the claim title — the aspirational framing (`"commits to"`) is accurate; stating the target as present fact would not be.

This is a schema field addition, not a code change for this plan. Document here, implement in the companion code plan.

### Entity pages

**Problem:** `"Microsoft - Dangerous Robot"` is too generic. It does not signal the page's research purpose, and it won't compete for queries like "Microsoft AI sustainability claims".

**Decision:** Use `"{Name} AI {type} Claims"` passed to the layout, which appends ` - Dangerous Robot`. The word "AI" scopes the context; "Claims" signals the research purpose.

**Template:** `"{entity.data.name} AI {entity.data.type === 'company' ? 'Company' : 'Product'} Claims"`

**Examples:**

| Entity | Title passed to layout | Full `<title>` |
|--------|------------------------|----------------|
| Microsoft (company) | `"Microsoft AI Company Claims"` (27) | `"Microsoft AI Company Claims - Dangerous Robot"` (45) |
| Anthropic (company) | `"Anthropic AI Company Claims"` (28) | `"Anthropic AI Company Claims - Dangerous Robot"` (46) |
| Claude (product) | `"Claude AI Product Claims"` (24) | `"Claude AI Product Claims - Dangerous Robot"` (43) |
| Gemini (product) | `"Gemini AI Product Claims"` (24) | `"Gemini AI Product Claims - Dangerous Robot"` (43) |

All full titles are under 50 chars. Well within the SERP limit.

**Edge case — long entity names:** If `entity.data.name` exceeds 25 characters, the title may approach 60 chars before the layout suffix. Example: `"Google DeepMind AI Company Claims - Dangerous Robot"` = 52 chars — fine. No special handling needed for current entities; note the constraint for future onboarding.

**Edge case — topic and sector entities:** The entity `type` field includes `topic` and `sector`. These are not publicly routed as `/companies/` or `/products/` pages (the topics directory is currently empty). If an entity page ever renders for a topic or sector type, fall back to `"{entity.data.name} — Dangerous Robot"` rather than emitting an awkward `"X AI Topic Claims"` title.

### Topic pages

**Problem:** `"Environmental Impact - Dangerous Robot"` is generic. The site's topic pages are claim indexes, not general topic references — the title should signal that.

**Decision:** `"AI {label} Claims | Dangerous Robot"` pattern.

**Template:** `"AI {label} Claims"` where `label` is the human-readable topic label (e.g., `"Environmental Impact"`, `"Data Privacy"`).

**Examples:**

| Topic | Title passed to layout | Full `<title>` |
|-------|------------------------|----------------|
| `environmental-impact` | `"AI Environmental Impact Claims"` (30) | `"AI Environmental Impact Claims - Dangerous Robot"` (49) |
| `data-privacy` | `"AI Data Privacy Claims"` (22) | `"AI Data Privacy Claims - Dangerous Robot"` (41) |
| `ai-safety` | `"AI Safety Claims"` (16) | `"AI Safety Claims - Dangerous Robot"` (35) |
| `industry-analysis` | `"AI Industry Analysis Claims"` (27) | `"AI Industry Analysis Claims - Dangerous Robot"` (46) |
| `regulation-policy` | `"AI Regulation & Policy Claims"` (29) | `"AI Regulation & Policy Claims - Dangerous Robot"` (48) |

All full titles are under 50 chars. No edge cases.

### Source pages

**Current state:** `source.data.title` is passed verbatim. Source titles can be long (e.g., `"2024 Microsoft Environmental Sustainability Report"` = 51 chars). With the layout suffix, this becomes `"2024 Microsoft Environmental Sustainability Report - Dangerous Robot"` = 68 chars — marginal but acceptable for sources, which are not primary SEO targets.

**Decision:** Keep the current pattern (`source.data.title`), but add the publisher name when the title is short enough. If `source.data.title.length + source.data.publisher.length + 4` (for ` — `) is ≤ 50 chars, use `"{title} — {publisher}"`. Otherwise, use `source.data.title` alone.

**Examples:**

| Source title | Publisher | Result |
|---|---|---|
| `"About Us"` | `"Tread Lightly!"` | `"About Us — Tread Lightly!"` (25 chars) — use combined |
| `"2024 Microsoft Environmental Sustainability Report"` | `"Microsoft"` | Title alone (51 chars, combined would be 63) — use title alone |

This is a code-side decision. Document here; implement in companion plan.

### Criteria pages

**Problem:** Criterion text is written as a question or statement scoped to an entity type, not a specific entity. Examples:

- `"COMPANY publishes a sustainability or ESG report"` — 49 chars
- `"COMPANY has STRUCTURE corporate structure"` — 41 chars
- `"COMPANY donates to AI safety organizations"` — 43 chars

The placeholder `COMPANY` or `PRODUCT` appears literally in the criterion text. Rendering this verbatim in `<title>` is misleading for SERPs.

**Decision:** Replace the entity-type placeholder with the site scope in the title: `"COMPANY"` → `"AI Company"`, `"PRODUCT"` → `"AI Product"`. Use the vocabulary-substituted form when `vocabulary` values are short enough; otherwise use the base text with placeholder replaced.

**Template logic:**

```
title = std.data.text
  .replace('COMPANY', 'AI Company')
  .replace('PRODUCT', 'AI Product')
  .replace(/\s+[A-Z_]+\s+/, ' ')   // drop remaining vocabulary placeholders (STRUCTURE, etc.)
  .replace(/\s+/, ' ')              // clean up any double spaces
  .trim()
```

The resulting string is passed to the layout, which appends ` - Dangerous Robot` (18 chars). Target: title passed to layout must be 42 chars or fewer to keep the full `<title>` within 60 chars.

**Examples:**

| Criterion text | Title passed to layout | Full `<title>` |
|---|---|---|
| `"COMPANY publishes a sustainability or ESG report"` | `"AI Company sustainability or ESG report"` (40) | `"AI Company sustainability or ESG report - Dangerous Robot"` (57) |
| `"COMPANY has STRUCTURE corporate structure"` | `"AI Company has corporate structure"` (35) | `"AI Company has corporate structure - Dangerous Robot"` (52) |
| `"COMPANY donates to AI safety organizations"` | `"AI Company donates to AI safety orgs"` (37) | `"AI Company donates to AI safety orgs - Dangerous Robot"` (54) |

For the first example, the full criterion text `"COMPANY publishes a sustainability or ESG report"` is too long after substitution (53 chars with prefix + suffix). The template trims `"publishes a"` from the middle: the constructed title becomes `"AI Company sustainability or ESG report"` (40 chars). This requires a fallback trim step in the template logic, not just a plain replace. The companion code plan should handle this.

For the `STRUCTURE` case: `STRUCTURE` is a vocabulary placeholder that expands to multiple values on the criteria page. The regex rule drops it, yielding `"AI Company has corporate structure"` (35 chars).

**Note on criteria title quality:** Unlike claim `seo_title`, there is no manually authored short-form field for criteria. The template output is a best-effort representation. If a criterion's text produces a confusing title after transformation, the criterion's `notes` field can document the expected title and the code plan can add a special-case override path.

### Homepage

**Problem:** The homepage currently passes `title="Dangerous Robot — AI transparency research"` to the layout. The layout wraps it as `"Dangerous Robot — AI transparency research - Dangerous Robot"` — the brand name appears twice. This is a bug, not an editorial issue.

**Decision:** Fix the duplication. The homepage should pass a title that does not repeat the brand name, since the layout appends it. Or the layout should detect and suppress the suffix when the title already ends with `"Dangerous Robot"`. The simplest fix: pass `title="AI Transparency Research"` from the homepage, letting the layout render `"AI Transparency Research - Dangerous Robot"`.

This is a code fix, noted here for completeness.

---

## Milestone: Meta description templates

**Status:** `[ ] ready to implement`

All descriptions should be 120–155 characters. Below 120 chars, Google may supplement with on-page text; above 155, SERP truncation is likely.

### Homepage

Current default: `"Structured research backing claims about AI products and companies."`

This is 67 characters — too short, and it does not mention the fact-checking or transparency angle.

**Proposed:** `"Dangerous Robot is a structured research hub tracking AI company environmental and safety claims. Built for journalists, researchers, and policy teams."`

Character count: 151. Covers the audience, the purpose, and the content type.

### Claim pages

No description is currently passed. The layout default fires for every claim.

**Template:** `"{entity_name} — {verdict_label}. {claim_title}. Sourced research as of {as_of_year}. Dangerous Robot."`

**Construction rules:**
- `entity_name`: `entityEntry.data.name` (e.g., `"Microsoft"`)
- `verdict_label`: human-readable form of the verdict enum, e.g., `"Unverified"`, `"True"`, `"Mostly False"`
- `claim_title`: `claim.data.title` — the full claim sentence
- `as_of_year`: four-digit year from `claim.data.as_of`

**Examples:**

| Claim | Description |
|---|---|
| Claude / discloses-energy-sourcing | `"Claude — Unverified. Claude discloses its energy sourcing. Sourced research as of 2026. Dangerous Robot."` (105 chars — add topic context to reach 120) |
| Claude / renewable-energy-hosting | `"Claude — Unverified. Claude is hosted on renewable energy. Environmental impact claim. Sourced research as of 2026. Dangerous Robot."` (133 chars) |

**Adjusted template:** `"{entity_name} — {verdict_label}. {claim_title}. {topic_label} claim. Sourced research as of {as_of_year}. Dangerous Robot."`

Where `topic_label` is the first topic's human-readable label (e.g., `"Environmental impact"`).

Verify length at build time: if the assembled string exceeds 155 characters, truncate `claim_title` at the last word boundary before the limit.

### Entity pages

The entity `description` field is already in the schema and is required. Current examples:

- Microsoft: `"Microsoft is a multinational technology corporation that has set ambitious renewable-energy and carbon-neutral goals, using both direct renewable-energy procurement and carbon-credit mechanisms."` — 192 chars, too long.
- Anthropic: `"Homepage for Anthropic, an AI safety and research company building reliable, interpretable, and steerable AI systems including Claude."` — 133 chars, good length but starts with "Homepage for" which is a pipeline artifact.
- Claude: `"Claude is Anthropic's family of language models. It includes Haiku, Sonnet, and Opus."` — 86 chars, too short.

**Decision:** Use `entity.data.description` as the base, trimmed to 155 chars at the last word boundary. Prepend `"Dangerous Robot tracks {entity_name} AI claims. "` if the description alone is under 80 chars.

**Template:** `"Dangerous Robot tracks {entity_name} AI {type} claims. {description}"` trimmed to 155 chars.

**Examples:**

| Entity | Description |
|---|---|
| Microsoft | `"Dangerous Robot tracks Microsoft AI company claims. Microsoft is a multinational technology corporation that has set ambitious renewable-energy and carbon-neutral goals…"` — trim to 155 |
| Claude | `"Dangerous Robot tracks Claude AI product claims. Claude is Anthropic's family of language models. It includes Haiku, Sonnet, and Opus."` (135 chars) |

**Editorial note for the pipeline:** Entity descriptions should be written in 1–2 sentences, 80–140 characters. Descriptions starting with "Homepage for" or similar are pipeline artifacts and should be corrected during human review. The `dr lint` check `placeholder-website` is analogous; a future `placeholder-description` lint check would flag these.

### Topic pages

**Template:** `"Browse AI {label} claims on Dangerous Robot. {claim_count} claims across {entity_count} entities, with verdict and sourcing for each."`

**Examples:**

| Topic | Description |
|---|---|
| Environmental Impact, 5 claims, 3 entities | `"Browse AI Environmental Impact claims on Dangerous Robot. 5 claims across 3 entities, with verdict and sourcing for each."` (121 chars) |
| Data Privacy, 1 claim, 1 entity | `"Browse AI Data Privacy claims on Dangerous Robot. 1 claim across 1 entity, with verdict and sourcing for each."` (111 chars — slightly short; acceptable) |

Note: claim and entity counts are dynamic (computed at build time from the collection). `claim_count` is the count of published claims for that topic. `entity_count` is the count of distinct entities that have at least one published claim for that topic (matching what the page already computes as `entityGroups.length`). The template works for any count.

### Criteria pages

**Template:** `"Does {entity_type_label} {action_phrase}? Dangerous Robot tracks this criterion across {entity_count} entities with sourced verdicts."`

Constructing `action_phrase` from the criterion text is complex — the text includes `COMPANY`/`PRODUCT` placeholders and vocabulary sub-placeholders. Simpler approach:

**Template:** `"Dangerous Robot evaluates whether {criterion_text_with_placeholder_replaced}. Coverage across {entity_count} entities with sourced verdicts."`

Where `criterion_text_with_placeholder_replaced` substitutes `COMPANY` → `"an AI company"` and `PRODUCT` → `"an AI product"`, and vocabulary placeholders are dropped.

`entity_count` here is the count of all entities whose `type` matches the criterion's `entity_type` (i.e., the full matrix size shown on the criteria page), not just those with an existing claim. This is the more informative number for a prospective reader.

**Examples:**

| Criterion | Description |
|---|---|
| `"COMPANY publishes a sustainability or ESG report"` | `"Dangerous Robot evaluates whether an AI company publishes a sustainability or ESG report. Coverage across 4 entities with sourced verdicts."` (139 chars) |
| `"COMPANY has STRUCTURE corporate structure"` | `"Dangerous Robot evaluates whether an AI company has a given corporate structure. Coverage across 4 entities with sourced verdicts."` (130 chars) |

### Source pages

**Template:** `"{publisher} {kind}: {title}. Referenced in Dangerous Robot claims on AI company environmental and safety reporting."`

**Examples:**

| Source | Description |
|---|---|
| Microsoft 2024 Sustainability Report | `"Microsoft report: 2024 Microsoft Environmental Sustainability Report. Referenced in Dangerous Robot claims on AI company environmental and safety reporting."` (155 chars — exact) |
| Tread Lightly! About Us | `"Tread Lightly! index: About Us. Referenced in Dangerous Robot claims on AI company environmental and safety reporting."` (118 chars) |

If the assembled string exceeds 155 chars, trim the title portion at the last word boundary before the overflow.

---

## Milestone: og:image strategy

**Status:** `[ ] planned`

No `og:image` tag exists. When the site is shared on social platforms, the preview renders with no image; platform default behavior varies (often a blank card or a scraped logo). This reduces click-through from social sharing.

**Options:**

- **Option A — Single static fallback image** (`/og-default.png`): one image for all pages. Simple. No per-page differentiation. Works immediately.
- **Option B — Per-page-type static images**: one image each for claims, entities, topics, criteria. Moderate effort. Differentiates claim pages from entity pages visually, but all claim pages still share one image.
- **Option C — Dynamic image generation**: Astro's experimental image generation or a serverless function generates a per-page OG image with the page title and verdict. Significant effort. Overkill for a static site at this stage.

**Decision: Option A.** The site's value is in the content, not the visual. A single static image establishes brand presence in social previews without engineering overhead. Revisit Option B when the entity count grows beyond 10 and there's a meaningful visual distinction to make.

**Image spec:**
- Dimensions: 1200 × 630 px (standard OG image size)
- Content: site name ("Dangerous Robot"), logo, and a short tagline. The tagline should match the brand voice — e.g., `"Sourced research on AI company claims"` — not marketing copy.
- Background: should work on both light and dark platform previews; use the site's accent color or a dark neutral.
- This is a design task. The plan records the decision; the design and file creation are out of scope here.

**Implementation note (for companion code plan):** Add the full OG and Twitter Card tag set to `Base.astro` in one pass. None of these tags currently exist:

```
og:title        — same value as <title>
og:description  — same value as <meta name="description">
og:type         — "website" for most pages
og:image        — "/og-default.png"
og:image:width  — "1200"
og:image:height — "630"

twitter:card    — "summary_large_image"
twitter:title   — same as og:title
twitter:description — same as og:description
twitter:image   — "/og-default.png"
```

Twitter Card and OG tags are distinct but share the same values here. Adding both at the same time avoids a second pass.

---

## Milestone: Content depth guidance

**Status:** `[ ] editorial / ongoing`

This milestone is guidance for the research pipeline and content operators. No schema changes.

### Current state

Published claim rationale sections average 150–160 words based on sampled content. The renewable-energy-hosting claim rationale is 113 words. For a site targeting journalists and researchers, this is on the thin side for topical authority and for ranking on queries with any competition.

### Target length

250–400 words per rationale. This range is enough to substantiate the verdict without padding. Below 250 words, the rationale risks reading as conclusory. Above 400 words, it risks burying the verdict under detail better left to linked sources.

### What to include

Adding word count alone is not the goal. Content that adds substance:

1. **Direct source quotes.** Pull the specific sentence or passage from the source that most directly supports or refutes the claim. Paraphrase is fine for summaries; quotes are necessary for a fact-checking site.
2. **Timeline context.** When did the company make the claim? When was the source published? Has the company's position changed over time? A single-point-in-time verdict is less useful than a verdict that acknowledges the trajectory.
3. **What the claim omits.** A claim that is technically true may be misleading by omission. Note what is not disclosed, what the source does not address, or what a full-picture answer would require.
4. **Confidence explanation.** The `confidence` field is `high`, `medium`, or `low`, but the rationale should explain *why*, not just assert it. Low confidence should explain what evidence is missing. High confidence should note what makes the sourcing strong.
5. **What would change the verdict.** A brief note on what new disclosure or evidence would shift the rating. This is useful for rechecks and for readers who want to know what to look for.

### What not to do

- Do not add background sections about the company that are not relevant to the specific claim. Each claim is scoped.
- Do not repeat the claim title verbatim in the rationale opening sentence. Start with the evidence, not a restatement.
- Do not hedge every sentence. The rationale should support a verdict, not avoid one.

### Application to the research pipeline

The Analyst agent prompt should include the target length and the five content elements above. The Auditor agent should flag rationales below 200 words as a quality concern, not a blocking error. Human review should check that at least elements 1 and 4 are present before publishing.

---

## Milestone: Keyword targeting guidance

**Status:** `[ ] editorial / ongoing`

This milestone is guidance for operators and the research pipeline. No schema changes.

### Primary keyword clusters

The site is positioned for three clusters:

1. **Company + claim type queries:** `"Microsoft carbon negative claim"`, `"Anthropic environmental commitments"`, `"Google AI energy use"`, `"OpenAI training data disclosure"`. These are navigational/research queries from people who already know what they're looking for.

2. **Category research queries:** `"Is [company] carbon neutral"`, `"AI company sustainability report"`, `"AI energy consumption facts"`, `"AI water usage"`. These are informational queries from people researching the topic broadly.

3. **Fact-checking queries:** `"[company] claim true or false"`, `"[company] greenwashing"`, `"AI sustainability claims verified"`. These are evaluative queries from journalists and policy researchers.

### How claim titles and entity descriptions should incorporate keyword clusters

Claim titles are research labels, not SEO copy. They must remain accurate. The rule is: if the natural research label happens to match a query people search for, that is good. Do not contort the label to include keywords.

Specifically:
- Claim `title` is authored to describe the claim accurately. Do not keyword-stuff it.
- `seo_title` (the new optional field) is where natural keyword variation can be introduced, within the constraint that it must still accurately represent the claim.
- Entity `description` is where keyword clusters should appear naturally. A description for Microsoft should mention "carbon neutral", "renewable energy", and "sustainability report" if those are the domains the entity is tracked on. This is not keyword stuffing; it is accurate description.

**Example — entity description with keyword coverage:**

Current: `"Microsoft is a multinational technology corporation that has set ambitious renewable-energy and carbon-neutral goals, using both direct renewable-energy procurement and carbon-credit mechanisms."`

This is 192 chars (too long for a meta description used directly) and is reasonably keyword-dense already. A revised version that fits the 80–140 char guidance: `"Microsoft is a tech company with public carbon-neutral and renewable energy goals tracked by Dangerous Robot."` (109 chars). But this loses specificity. The tradeoff: a longer, more specific description used for the entity page body, with the meta description trimmed from it programmatically. This is the approach documented in the Meta description templates milestone above.

**Example — `seo_title` with keyword coverage:**

| Claim title | `seo_title` (keyword variant) |
|---|---|
| `"Claude is hosted on renewable energy"` | `"Claude renewable energy hosting claim"` — adds "claim" as a keyword signal |
| `"Microsoft is carbon negative by 2030"` | `"Microsoft carbon negative 2030 claim"` |

### What not to do

- Do not add a `seo_title` that changes the meaning of the claim. `"Microsoft renewable energy — True"` is not acceptable if the verdict is `unverified`.
- Do not insert keywords into `criteria_slug`, `topics`, or other structured fields for SEO purposes. These fields drive site behavior and must remain semantically accurate.
- Do not use the same `seo_title` for multiple claims to target the same query. Duplicate titles harm rankings and are confusing.
- Do not add keyword phrases to the claim `title` that are not part of the natural research label. The claim title is the unit of research; accuracy is the first constraint.

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-04-28 | agent (claude-sonnet-4-6) | initial draft, all milestones | First version |
