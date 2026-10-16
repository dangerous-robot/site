# Content Model

How research content is structured, stored, and related in the dangerousrobot.org site.

Schemas are defined in `src/content.config.ts` and enforced at build time by Astro's content layer. All research content lives under `research/` as Markdown files with YAML frontmatter.

## Content Types

| Type | Purpose | Base path |
|------|---------|-----------|
| **Entity** | A stable thing we make claims about (a product or a subject); a company file is a read-only parent record, not a claim target | `research/entities/` |
| **Claim** | A single factual assertion about an entity, with verdict and evidence | `research/claims/` |
| **Source** | A citable reference -- cite once, reference from many claims | `research/sources/` |
| **Criterion** | A registry entry: a claim sentence applied uniformly across entities, with a `grading_rule` | `research/templates.yaml` |

## Directory Conventions

```
research/
  entities/
    companies/{slug}.md      # e.g. anthropic.md; read-only parent record, no claims
    products/{slug}.md
    subjects/{slug}.md
  claims/
    {entity-slug}/            # matches a product or subject filename; no company has one
      {claim-id}.md           # e.g. existential-safety-score.md
  sources/
    {yyyy}/                   # year directory
      {slug}.md               # e.g. fli-safety-index.md
  findings/
    {yyyy}/                   # year directory
      {run-id}.yaml           # one per abandoned, recovered, split or partial run; not a site collection
```

**Naming rules:**

- Lowercase kebab-case for all slugs
- Entity files sit in a subdirectory matching their type (`companies/`, `products/`, `subjects/`); only products and subjects are claim targets (`dr draft` refuses a company in every mode)
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
| `parent_company` | string | no | Slug ref of the form `companies/{slug}` pointing at a company record; the pipeline uses it to match first-party sources (`entity_identity_for`), and the company is not a claim target |
| `search_hints` | object | no | Optional `include` and `exclude` string arrays; hints for the pipeline's source searches |
| `sec_cik` | string | no | SEC CIK identifier; must be a 10-digit string |

The Markdown body provides extended context about the entity.

### Claim

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | yes | Human-readable claim statement; equals `statement` on every claim the pipeline writes |
| `statement` | string | no | The sentence the loop re-runs and the Evaluator grades. For `dr draft --criterion` it is the criterion's text rendered once with the entity name and the file is `<entity-dir>/<criteria_slug>.md`; for an ad hoc claim it is the operator's sentence and the file is `<entity-dir>/<slugify(statement)>.md`; `dr draft --claim --force` re-runs it and keeps the existing path. Claims written before it existed fall back to `title` |
| `seo_title` | string | no | Short title for `<title>` tags (≤42 chars, leaving room for ` - Dangerous Robot`). Analyst writes this on every generated claim; a forced rewrite (`dr draft --claim --force`) keeps an operator's value (one that differs from the analyst's last `seo_title`, recorded in the sidecar's `analyst_record`) while the claim's statement is unchanged; `analyst_record.title` records the statement. Falls back to `title` if absent. |
| `entity` | string | yes | Path-style reference to entity: `{type}/{slug}` (e.g. `products/claude`); a `companies/` ref is refused by `dr draft` |
| `topics` | enum[] | yes | 1-3 slugs from the topic taxonomy (see [Claim Topic Taxonomy](#claim-topic-taxonomy) below) |
| `verdict` | enum | yes | `true`, `mostly-true`, `mixed`, `mostly-false`, `false`, `unverified`, `not-applicable` |
| `confidence` | enum | yes | `high`, `medium`, `low` |
| `verification_level` | enum | no | Source-pool diversity signal, set by the analyst from `independence` and `kind` on the claim's sources: `claimed`, `self-reported`, `partially-verified`, `independently-verified`, `multiply-verified`. See [source-quality.md](source-quality.md) |
| `cap_rationale` | string | no | One-sentence explanation when the confidence cap fires (a `verification_level` of `claimed` or `self-reported` caps `confidence` at `low`); max 400 chars. A forced rewrite (`dr draft --claim --force`) keeps an operator's value (one that differs from the pipeline's last, recorded in the sidecar's `analyst_record`) on every rewrite, even when `verification_level` or `confidence` changed or the level fit lowered the level again, until the operator edits it. A rewrite to an uncapped level keeps it too: the claim page shows it only on a capped level, so it stays unseen until a later rewrite caps the claim again (deleting it from the claim lets the next rewrite take the pipeline's). With no recorded rationale, the existing value is kept only on a capped level while `verification_level` and `confidence` are both unchanged, and not when the level fit wrote the only rationale this run proposed. See [source-quality.md](source-quality.md) |
| `source_overrides` | object[] | no | Per-claim overrides of source-level fields, used when a source classified `independent` is actually restating a primary disclosure for this claim. Each entry: `source`, `reason`, optional `independence`. See [source-quality.md § Source overrides on claims](source-quality.md#source-overrides-on-claims) |
| `takeaway` | string | no | Optional reader-facing one-liner; max 200 chars; rendered under the verdict badge. A forced rewrite keeps the existing value when the analyst gives none, and keeps an operator's (one that differs from the analyst's last, recorded in the sidecar's `analyst_record`) while the analyst's verdict is unchanged |
| `criteria_slug` | string | no | Optional back-reference to the criterion this claim was drafted from (`dr draft --criterion`) or had attached (`dr draft --claim --criterion`, which appends the criterion to `research/templates.yaml` for an ad hoc draft). It is the publish gate: lint reports `published-without-criterion` without it |
| `status` | enum | yes (default: `draft`) | Publication status: `draft`, `published`, `archived`; any other value fails the site build and is a `dr lint` error (`invalid-claim-status`). Production builds a claim page only for `published` and `archived`; the dev server builds all three |
| `phase` | enum | no | Pipeline progress while in flight; absent on terminal states. One of `researching`, `ingesting`, `analyzing`, `evaluating` |
| `as_of` | date | yes | Date the verdict was last evaluated |
| `sources` | string[] | yes | List of source IDs (e.g. `2025/fli-safety-index`) |
| `recheck_cadence_days` | number | no | Days between reviews; defaults to 60. The writer carries an existing value forward and does not write the default |
| `next_recheck_due` | date | no | When this claim should next be rechecked: `as_of` plus `recheck_cadence_days`. The writer sets it on every claim write; claims written before it existed have none and are due when `as_of` plus the cadence has passed (`dr recheck --due`) |
| `tags` | string[] | no | Free-form operator-set tags; defaults to `[]`. Behavioral tags are defined in [AGENTS.md § Claim Tags](../../AGENTS.md#claim-tags) |
| `audit` | object | no | Pipeline audit sidecar data, loaded from a paired `.audit.yaml` file (see below) |

The Markdown body contains the claim narrative -- the human-readable explanation of the verdict and evidence.

### Source

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `url` | URL string | yes | Original source URL |
| `archived_url` | URL string | no | Wayback Machine or permanent archive link. The pipeline sets it after each ingest, and only to a capture that archive.org replays with HTTP 200 for the same page (path case counts): TimeGate's nearest capture, else the newest 200 capture in the CDX index, else a checked Save Page Now capture; a link the ingest model writes itself is dropped. When the live fetch succeeded, a capture older than 90 days or than `published_date` is replaced by a fresh checked capture when one succeeds. `dr recheck --sources <id>...` adds it to existing files and checks an existing link, replacing it with an existing capture that passes the check and keeping the old link when none does. `dr draft --paid-dry-run` and `dr draft --source --paid-dry-run` write nothing, use existing captures only and never ask archive.org to capture a page; `dr draft --dry-run` makes no archive.org call |
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
| `pipeline_run.level_clamp` | string | Present only when the level fit, run inside the loop before the Evaluator, lowered the analyst's `verification_level`; says from what to what and why (see `docs/architecture/source-quality.md` § Level fit to the written sources) |
| `models_used` | map | Per-agent model lineage (agent name to model string). Optional during the v1 transition: sidecars written before the field landed validate without it; new sidecars always carry it. `dr draft --claim <ref> --rerun evaluator` replaces the `auditor` entry, writes `tiebreaker` when the disagreement went to the tie-breaker and drops an older one otherwise, and keeps the others, and `--rerun analyst` replaces the `analyst` entry, drops the `auditor` and `tiebreaker` entries (its `audit` is null) and keeps the others; every other write records only the agents that run |
| `research` | object or null | Optional, top level. The research step's trace, which `src/content.config.ts` declares loosely (the pipeline owns its fields; the review packet reads `rejected`). The fields below are the ones a decomposed run writes; `null` on a sidecar whose run recorded no trace |
| `research.mode` | string | `decomposed` |
| `research.queries` | string[] | The search queries the planner produced |
| `research.planner_rationale` | string | The planner's reasoning for the plan |
| `research.candidates_seen` | number | Candidate URLs the searches returned before scoring |
| `research.urls_kept`, `research.urls_dropped` | number | How many candidates the scorer kept and dropped |
| `research.scorer_rationale` | string | The scorer's reasoning |
| `research.scorer_dropped_all` | boolean | Present and `true` when the scorer dropped every candidate |
| `research.tool_outcomes` | array | Searches that ran cleanly and found nothing, each `{tool, query, outcome}` |
| `research.rejected` | array | The candidates the scorer dropped, each `{url, title, score, reason}`. `score` is `null` because the scorer gives its dropped URLs one shared rationale and no score each; `reason` is the scorer's drop rule (`scored below 3 on every sub-question`). The review packet prints them under the searches. `[]` when the scorer dropped none |
| `research.entity_exclude_dropped`, `research.entity_exclude_spared` | string[] | Optional. URLs removed by the entity's `search_hints.exclude` domains, and the entity's own profile URLs that matched one of those domains but were kept |
| `sources_consulted` | array | Sources the pipeline considered (`id`, `url`, `title`, `ingested`, `quotes`, optional `acquisition`, `archive` and `shared_with`) |
| `sources_consulted[].quotes` | array | Every key quote of the source and the automated check the pipeline ran on it, each `{text, found, checked_against, passage, reason}`. For a fresh source `found` says whether the quote is in the fetched page text, `checked_against` says which text (`page`, `archive` or `page-and-archive`), and `passage` is the matched sentence with a bounded window of the page text around it (`null` when not found); a quote that was not found carries the `reason` and was dropped from the source file. For a source reused from disk `found` is `null`, `checked_against` is `not-rechecked` and `passage` is `null`. The review packet prints each quote beside its passage, with a link to the archived copy when the source has an `archived_url` |
| `sources_consulted[].recheck` | object | Optional. Written by `dr recheck` on a source cached on disk and older than the claim's cadence: `refetched` (whether the live page was fetched again), `checked_at`, `archive` (the archive link's check: `ok`, `bad`, `unverified`, `none` or `skipped`) and `reason` (why a fetch failed). A re-fetched source also gets fresh `quotes` checks in place of `not-rechecked`. The shared source file is never rewritten by a claim recheck. The review packet's Recheck row counts these |
| `sources_consulted[].shared_with` | string[] | Optional. Ids of the other consulted sources on the same canonical publisher host or from the same newswire origin; left out when there are none. The review packet shows it under source independence |
| `sources_consulted[].acquisition` | object | Optional record of how the source was acquired |
| `sources_consulted[].acquisition.stage` | enum | Pipeline stage that acquired the source: `research` or `ingest` |
| `sources_consulted[].acquisition.origin` | enum | Optional provider the source came from: `brave`, `tavily`, `arxiv`, `s2`, `openalex`, `edgar` |
| `sources_consulted[].acquisition.recovered_via` | enum | Optional: `archive_org`, set when the source was recovered via archive.org |
| `sources_consulted[].acquisition.outcome` | enum | Optional: `matched` or `recovered` |
| `sources_consulted[].acquisition.query` | string | Optional search query used |
| `sources_consulted[].acquisition.paper_id` | string | Optional paper identifier |
| `sources_consulted[].acquisition.filing_accession` | string | Optional filing accession identifier |
| `sources_consulted[].archive` | object | Optional. Outcome of the archive.org lookup the pipeline runs after ingesting a source; absent on sources reused from disk. `dr draft --claim <ref> --rerun evaluator` (and `--rerun analyst`) carries it over |
| `sources_consulted[].archive.status` | enum | `found` (the source got an `archived_url`), `failed` (no capture replays with HTTP 200 for the same page, rate-limited after one retry, Save Page Now returned no dated snapshot or captured an error page, another error, or the lookup's time limit) or `not-attempted` (run with `--skip-wayback`) |
| `sources_consulted[].archive.error` | string | Optional. Why a `failed` lookup failed, e.g. `archive.org TimeGate check failed (HTTP 429)` or `archive.org capture is an error page (HTTP 404)` |
| `audit` | object or null | Analyst/Evaluator verdict comparison block; `null` when the Evaluator did not grade the analysis on disk: `dr draft --claim <ref> --rerun analyst` clears it until `--rerun evaluator` grades the new analysis (the claim page then shows the Evaluator check as unavailable, and `dr review --approve` records no `verdict_override`) |
| `audit.analyst_verdict` | string | Verdict from the Analyst agent |
| `audit.auditor_verdict` | string | Verdict from the Auditor agent |
| `audit.analyst_confidence` | string | Confidence from the Analyst agent after the level fit (the Evaluator compared against this value) |
| `audit.auditor_confidence` | string | Confidence from the Auditor agent |
| `audit.verdict_agrees` | boolean | Whether the analyst and evaluator verdicts agreed |
| `audit.confidence_agrees` | boolean | Whether the analyst and evaluator confidence levels agreed |
| `audit.needs_review` | boolean | Whether human review is flagged |
| `audit.auditor_reasoning` | string | Optional. The Evaluator's reasoning, shown on the claim page |
| `audit.evidence_gaps` | string[] | Optional. Gaps the Evaluator found in the evidence, shown on the claim page |
| `audit.pipeline_verdict` | string | Optional. The verdict the pipeline settled on: the agreed verdict, or the tie-breaker's rule result. Readers (lint, `dr review --approve`, the claim page) use `audit.analyst_verdict` when it is absent |
| `audit.pipeline_confidence` | string | Optional. Confidence that goes with `pipeline_verdict` |
| `audit.rule_applied` | string | Optional. Which rule settled the verdict: `agreed`, `tiebreaker-matched-analyst`, `tiebreaker-matched-evaluator` or `three-way-split-weakest` |
| `audit.tiebreaker_verdict` | string | Optional. Written only when the tie-breaker ran |
| `audit.tiebreaker_confidence` | string | Optional. Written only when the tie-breaker ran |
| `audit.tiebreaker_reasoning` | string | Optional. The tie-breaker's reasoning; written only when it ran |
| `audit.needs_review_reasons` | string[] | Optional. Why the claim was flagged: `verdict disagreement`, `confidence gap`, `2+ evidence gaps`; empty when `needs_review` is false |
| `human_review.reviewed_at` | date or null | When a human reviewed |
| `human_review.reviewer` | string or null | Reviewer identity |
| `human_review.notes` | string or null | Human review notes |
| `human_review.pr_url` | URL or null | Written by `dr review` only when `--pr-url` is given; sign-off is `dr review`, not a PR |
| `human_review.verdict_override` | object or null | Optional. `{from, to}` when the reviewer's verdict differs from `audit.pipeline_verdict` (`audit.analyst_verdict` when absent); written by `dr review`. Lint `verdict-sidecar-mismatch` accepts a published verdict that differs from the pipeline verdict only when this matches |
| `sub_questions` | array | Optional, top level. The planner's sub-questions, declared in `src/content.config.ts` (older sidecars lack some keys) |
| `sub_questions[].id`, `question`, `rationale` | string | The sub-question's id, text and why it matters |
| `sub_questions[].kind` | enum | Optional: `coverage` or `counter-evidence`. Each plan has exactly one `counter-evidence` sub-question, which asks what evidence would falsify the claim; absent on older sidecars |
| `sub_questions[].queries` | string[] | The search queries planned for it |
| `sub_questions[].citations` | string[] | Source ids whose fetched text confirmed the scorer's tag for this sub-question (empty when none did) |
| `sub_questions[].snippet_only` | string[] | Optional. Source ids the scorer tagged for this sub-question but whose fetched text never mentions its terms (its question and query words, minus stop words, the entity's name and any word that appears in two or more sub-questions' terms; a sub-question left with no terms keeps every tag); the tag came from a search snippet only, so it does not count as coverage |

A forced rewrite (`dr draft --claim --force`, `dr draft --force`) of a published or archived claim is refused with a pointer to `dr recheck --claim <ref>`; only a draft is rewritten in place. A recheck, or `dr draft --claim <ref> --rerun analyst|evaluator` on a published or archived claim, writes the rerun as a pending draft (a `--rerun` on a draft rewrites it in place, keeping the other agents' `models_used` and the sidecar's `research`, `sub_questions`, `acquisition` and `archive`): claim plus `.audit.yaml` sidecar at `research/pending/<entity-dir>/<claim-slug>.md`, tracked in git and outside the site's claims loader, linted as a draft, with `status: draft`, `human_review` reset and no `refresh` block. The live pair is never opened for writing. The pending pair is written in a `.dr-recheck-*` directory at the repo root and moved into `research/pending/` only after every write succeeds, claim first, so a writer failure leaves any earlier pending pair as it was and a stop between the two moves leaves a pending claim with no sidecar, which `dr findings` lists. `dr review --approve` promotes the pending pair: the writer first merges the live claim's operator fields into the pending claim (below), then adds the top-level `refresh` block (the live claim's published state and the `dropped_sources`) to the pending sidecar, then moves the sidecar and then the claim over the live paths, and the same approval completes the sign-off (on a claim whose verdict changed, with the one-line correction) and removes the block. The site does not read `refresh`. It survives only if the process stops between the moves and the approval; a second `--approve` finishes it (including a promotion that stopped after the sidecar move and before the claim move), and `dr lint` warns `refresh-pending-review` while it is present. No command writes a published or archived claim's sidecar in place. A failed or abandoned run writes nothing but its finding, so the claim and its sidecar stay as they were. Promotion keeps the operator fields edited on the live claim after the pending draft was seeded, against the values the pending sidecar recorded under `seeded_live` (below). `tags` and `corrections` edited on the live claim are taken from it, unless the pending draft's list also changed, when the additions on both sides are kept and the removals on both sides applied. `takeaway`, `seo_title` and `cap_rationale` edited on the live claim are taken only while the pending draft still has the value recorded for it, and under the keep rules: `takeaway` while the verdict is unchanged, `seo_title` while the analyst's title is unchanged, `cap_rationale` always. A field unchanged on the live claim keeps the pending value, so a review edit on the pending draft survives, and when both sides changed one of those three fields the review edit wins and the live edit is dropped with no message. A pending draft whose `seeded_live` lacks a field keeps its pending value for it, so an edit made on the live claim after seeding is lost. The merge runs before anything moves, so a claim that does not parse stops the promotion with both pairs as they were. It writes the merged claim to a sibling `<claim>.md.<token>.merge` copy, records its result as `seeded_live.next` (naming the copy), then moves the copy over the pending claim. A promotion stopped at any of its writes is finished by a second `--approve`, which reads `seeded_live` as the last write left it (the copy still on disk means it never replaced the claim) and keeps or drops a review edit on the pending draft and an edit on the live claim made in between exactly as a promotion that never stopped would; between the two moves the record is on the live sidecar, and the retry merges against it before moving the claim. `seeded_live` is removed from the live sidecar after the claim move, and an approval removes one a stop left there. Two cases still lose a live edit: an archived claim whose promotion stopped between its moves (the hand fix moves the pending claim without a merge), and a recheck that stopped between moving its pending claim and its sidecar, whose rerun (`dr recheck --claim`) writes a pending pair with no `seeded_live`. If the verdict changed, approval requires a one-line summary and adds a `corrections` entry to the claim (`date`, `summary`, `previous_verdict`), newest first.

| Field | Type | Notes |
|-------|------|-------|
| `refresh.refreshed_at` | timestamp | When the refresh that took the snapshot ran |
| `refresh.previous` | object | The live claim's published state, read at promotion before the pending pair is moved over it: `status`, `verdict`, `confidence`, `title`, `as_of`, `sources`, `reviewed_at`, `reviewer`, `ran_at`. A block already on the live sidecar (left by a promotion that stopped between its two moves) carries forward unchanged, so a recheck run before the next approval keeps the prior sign-off |
| `refresh.dropped_sources` | string[] | Source ids in `refresh.previous.sources` that the latest run no longer cites |

A draft whose pipeline verdict is `unverified`, `mixed` or `not-applicable`, or that went to the tie-breaker, also carries one top-level `restatement` block, written by the Restater (see `docs/architecture/research-flow.md` § Pipeline execution). The site does not read it; `src/content.config.ts` declares it as an optional, loose object. The original statement is never changed. Later sidecar writes carry the block forward unchanged (a rerun never restates); a full run that does not restate drops an old block; approval or archiving removes it, except while `picked` is set and no claim's sidecar has `restates` naming this claim, so `dr draft --restates` can still read the pick; the kept block then stays until a later approval, archive or full rerun. A run whose Restater failed writes no block and records a `partial` finding (`dr findings`; `dr review --format json` carries it as `restatement_unavailable: <run-id>`, and the packet prints "Restatement unavailable (finding <run-id>)" in place of the candidates).

| Field | Type | Notes |
|-------|------|-------|
| `restatement.schema_version` | number | Block format version |
| `restatement.model` | string | The Restater's model |
| `restatement.trigger` | enum | `weak-verdict` or `tie-broken` (a weak verdict wins when both apply) |
| `restatement.original` | object | `statement`, `verdict`, `confidence`: what was drafted and the verdict the pipeline settled on |
| `restatement.pool` | object | `consulted` (sources the run read), `on_disk` (matching sources in `research/sources/` not read by the run), `sent` (sources the Restater received) |
| `restatement.why_unverified` | enum | `quantifier-unsupported`, `term-mismatch`, `upstream-provider`, `entity-silent` or `other` |
| `restatement.why_unverified_note` | string | The Restater's one-paragraph explanation |
| `restatement.candidates` | array | Ranked from 1; each has `rank`, `text`, `frame`, `expected_verdict`, `expected_confidence`, `verification_level_estimate`, `decisiveness` (0 to 4), `needs_new_research`, `supporting`, `contradicting` (each a list of `source`, `quote`, `quote_verified`, `note`) and `rationale` |
| `restatement.dropped` | array | Candidates removed by the same-entity rule, each with `text` and `reason` |
| `restatement.picked` | number or null | The rank an operator ran as a new claim. Set by the `r` key in `dr review` (the operator's pick, before the run) and by `dr draft --restates --pick` after the new claim is written |
| `restates` | string | Top-level key in the new claim's sidecar: the ref of the claim it restates; written by `dr draft --restates`. Carried forward by later writes and never removed |

The pipeline also writes a top-level `analyst_record` block, which the site does not read (`src/content.config.ts` declares it as an optional, loose object so the sidecar validates): what the analyst last proposed for the claim (`title`, which records the claim's statement, and `seo_title`, `verdict`, `takeaway`, and `cap_rationale` after the level fit, plus `uncited_by_title`: the ids in the analyst's `cited_sources` whose title the narrative never names, which breaks the cite-by-title rule; an empty list when none). `verdict` is the verdict as written (the tie-breaker's, when it overrules the analyst). When `dr draft --claim <ref> --rerun evaluator` writes the tie-breaker's verdict into the claim, the record takes the new verdict and the `takeaway` on disk, `takeaway_verdict` names the verdict an operator's takeaway was written for, and `rewritten_from` names the verdict replaced (a sidecar with no record first gets the claim's own title and old verdict with no `seo_title`, as below). A record whose verdict differs from the claim's while `rewritten_from` equals it (the rerun stopped before the claim write, or the verdict was set back by hand) is read with the claim's verdict, so a takeaway written for the verdict the claim shows is kept while the analyst returns it; an analyst rerun clears `rewritten_from`. A later analyst rerun then keeps that operator takeaway only when it returns that verdict, and keeps a takeaway the operator writes after the rewrite while the verdict holds; an analyst takeaway clears `takeaway_verdict`. The record is written before the claim, so a rerun that stops part-way leaves it in place. A forced rewrite compares against it to tell an operator's `seo_title`, `takeaway` or `cap_rationale` from the pipeline's; a field the analyst leaves out keeps its last value. A claim whose sidecar has no `analyst_record` treats any `seo_title` or `takeaway` on disk as the operator's, so that value is kept on every later rewrite while the claim's statement (for `seo_title`) or the analyst's verdict (for `takeaway`) is unchanged; deleting the field from the claim lets the next rewrite take the analyst's.

A pending draft's sidecar (under `research/pending/`) seeded from the live claim also carries a top-level `seeded_live` block: the live claim's `takeaway`, `seo_title`, `cap_rationale`, `corrections` and `tags` when the pending draft was seeded, the live analyst title (`analyst_title`), and under `pending` the pending draft's `takeaway`, `seo_title` and `cap_rationale` as the run wrote them (a rerun from the pending pair moves each value the reviewer had not changed to what it wrote). Promotion compares both sides with it to find an edit made since; its merge records the values it leaves under `next`, with the token of its merge copy. The block moves with the sidecar and is removed from the live sidecar after the claim move, so a sidecar under `research/claims/` carries it only when a promotion stopped after the sidecar move: the next `--approve` finishes the promotion or the approval and removes it. For an archived claim, whose stopped promotion is not detected, the hand fix is to move the pending claim over the live one and approve. The site never reads it.

Sidecar files are optional. Claims without a sidecar have no `audit` field.

The Evaluator role is implemented in `pipeline/auditor/`; sidecar field names retain the `auditor_` prefix in v1 and will be renamed when the package directory is renamed (post-v1).

### Findings file

A run that is abandoned, recovered, split or partial (the claim was written but the restater failed) leaves one YAML record at `research/findings/<yyyy>/<run-id>.yaml`. The directory is tracked in git, sits outside every site collection loader (they read `claims/`, `entities/` and `sources/` only) and is skipped by `dr lint`. `dr findings` lists, counts, closes and replays the records (`dr findings --replay` re-runs an abandoned or half-claim record's `claim_spec` and `config` through the loop).

| Field | Type | Notes |
|-------|------|-------|
| `run_id` | string | One id per claim run; also the file name |
| `date` | date | When the run happened |
| `command` | string or null | The command that ran it: `dr draft`, `dr recheck`, or `dr draft --rerun analyst` / `dr draft --rerun evaluator` for a one-agent rerun (`dr findings --replay` skips those) |
| `claim_spec` | object | `statement`, `entity`, `criteria_slug`, `topics`, `grading_rule`: what a replay needs |
| `claim_ref` | string or null | Set when a claim file exists for the run (a recovered, split or half-claim run) |
| `config` | object | The run settings that shape results (`max_sources`, `candidate_pool_size`, `max_initial_queries`, `search_backend`, `research_origins`, `model`, `skip_wayback`) |
| `models_used` | map | Agent name to model string |
| `step` | enum | `research`, `ingest`, `analyse`, `evaluate`, `tiebreak`, `restate` or `write` |
| `rule` | enum | `flaw-retry`, `transport-retry`, `config-fatal`, `half-claim`, `tiebreaker` or `replay` (a `dr findings --replay` run that raised, or that failed without recording a finding of its own) |
| `error` | object | `error_type` and `message` |
| `attempts` | number | How many times the step ran |
| `outcome` | enum | `recovered`, `abandoned`, `split`, `half-claim` or `partial` |
| `retries` | array | Every step that was retried on the way: `step`, `error_type`, `rule`, `attempts`. A half-claim after a tie-broken run also lists the split here (`step: tiebreak`, `error_type: verdict_split`) with its `message`, the three verdicts |
| `replays` | string or null | Set on a finding a replay recorded: the run id of the finding that was replayed. Older records read as null |
| `closed` | object or null | `{date, by, note}` once `dr findings --close` has triaged it (`by: hand`) or a replay succeeded (`by: replay`) |

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
| `inactive` | boolean | no (default: false) | The pipeline's per-type list (`templates_for_entity_type`) skips the criterion; the site still loads it by slug. `dr draft --criterion` refuses an inactive criterion for every entity type ("no active criterion"), and `dr findings --replay` does not replay a criterion draft whose criterion is now inactive; a company entity is refused earlier, by the company refusal. Used only by `corporate-structure`, which the Responsible AI matrix's ownership row is keyed on; `dr draft` refuses a company entity in any case |

Subject-type criteria use `subjects` for explicit pairing with subject entities; product criteria match by `entity_type` alone (a `company` criterion is never drafted: companies are not a claim target).

## Relationships

```
Entity  <----  Claim  ---->  Source(s)
  1          many      many-to-many
               |
           Criterion (optional)
```

- **Claim to Entity:** Each claim has an `entity` field that references an entity by its path relative to `research/entities/` (without `.md`). Example: `products/claude`.
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
entity: subjects/ai-model-producers
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
