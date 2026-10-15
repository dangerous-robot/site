# Source quality

Reference for how the pipeline classifies sources, derives a per-claim verification level, and caps confidence on weakly-sourced claims.

This is the single source of truth for source-quality methodology. Plans, instructions, and lint rules cross-reference this file rather than restating its rules.

## What the verification scale measures

The `verification_level` field on each claim is derived from the diversity and kind of its source pool. **It measures source-type diversity, not claim corroboration.** "Independently verified" means independent-origin sources exist in the pool, not that independent analysis confirmed the underlying claim.

This is a bounded representation of what the system can determine without access to internal company systems. The cap-and-rationale machinery below is how we keep that boundedness honest in the verdict.

## Verification scale

Single claim-level field, set by the analyst. Each row's "Derivation" describes the *pool composition* required: each source in the pool has its own `independence` value (`first-party | independent | unknown`), and the level reflects how those values are distributed across the pool — never a property of any single source.

**Selection rule**: evaluate strongest to weakest; the first row whose derivation matches the pool wins. The rules overlap by design (a pool with two independent sources matches both `independently-verified` and `multiply-verified`); the cascade picks the strongest accurate label.

| Schema value (strongest first) | Display copy: **label** — gloss | Derivation |
|-------|----------------------------------------|------------|
| `multiply-verified` | **Cross-verified** — Multiple independent sources corroborate this claim. | The pool contains two or more `independent` sources. |
| `independently-verified` | **Independently verified** — At least one independent source corroborates this claim. | The pool contains at least one `independent` source. The pool may also contain `first-party` sources. |
| `partially-verified` | **Partially verified** — A mix of entity documentation and independent sources. | The pool contains at least one `first-party` source and at least one `independent` source. (Mechanically a subset of `independently-verified`; the cascade routes mixed pools to the stronger label, so this row is selected only when the analyst judges the independent source provides supplementary context rather than corroboration.) |
| `self-reported` | **Self-reported** — The entity has published formal documentation; no independent source was found to corroborate. | The pool has zero `independent` sources and at least one `first-party` source whose `kind` is in {report, documentation, dataset}. |
| `claimed` | **Claimed** — The entity asserts this; no formal documentation or independent source was found. | The pool has zero `independent` sources and every `first-party` source has `kind` in {blog, index, video, article}. |

The display-copy column is what the claim page shows readers under each level. Both the label and the gloss are mirrored from `src/lib/sourceQuality.ts`; editing those strings here means editing them on the site too.

An `unknown` source counts as neither `independent` nor `first-party`. A pool with zero `independent` and zero `first-party` sources is `claimed`.

### Level fit to the written sources

The analyst picks the level from every source it was shown; the claim cites only the sources written to its `sources:` list, and the site counts that list. The fit runs inside the loop, once, after the cited filter has fixed the final source ids and before the Evaluator (`fit_verdict_to_written_pool` in `pipeline/loop/fit.py`), so the Evaluator grades the fitted verdict. `dr step-analyze` reaches the same fit through the loop's analyst rerun, against every source stored on the claim. The fit:

- drops `source_overrides` entries for sources not in the written list;
- counts each written source ref's effective `independence` (its override, else its label after the entity match) with `effective_independence` in `pipeline/common/source_classification.py`, the same function the `verification-level-pool-mismatch` lint check uses; a ref listed twice counts twice, as on the site;
- lowers a level that needs more `independent` sources than the list has (`partially-verified` and `independently-verified` need one, `multiply-verified` two): to `independently-verified` with one, else to `self-reported` when a written `first-party` source has `kind` in {report, documentation, dataset}, else to `claimed`;
- lowers `self-reported` to `claimed` when the list has no `independent` source and no `first-party` source with `kind` in {report, documentation, dataset, article}. A first-party `article` keeps `self-reported`, since the analyst may judge one self-reported (see the boundary below).

The fit lowers confidence only when it lowers the level. A capped level the analyst chose itself keeps the confidence the analyst gave it, and `dr lint` warns (`confidence-cap-violation`). A lowered level of `self-reported` or `claimed` also sets `confidence: low` and, when the analyst wrote none, the `cap_rationale` "Confidence is capped at low: no source on this claim independently addresses <entity>." A `self-reported` level lowered to `claimed` always gets that rationale, since the analyst's describes a first-party report the list no longer has. A rationale the operator wrote on the claim is kept over the fit's, even when the level or confidence changes, until the operator edits it (`docs/architecture/content-model.md`, `cap_rationale`). The writer records why under `pipeline_run.level_clamp` from the loop's result. Because the fit runs before the Evaluator, `audit.analyst_confidence` is the post-fit confidence.

### `claimed` vs `self-reported` boundary

The boundary turns on whether a `first-party` source contains formal documentation:

- `kind: report`, `documentation`, `dataset` → `self-reported` qualifies.
- `kind: blog`, `index`, `video` → `claimed` only.
- `kind: article` (first-party) → defaults to `claimed`. The analyst may upgrade to `self-reported` only when the article contains methodology, data, or signed commitments. Marketing framing and announcements are not enough.

## The `independence` field

Each source carries `independence: first-party | independent | unknown`. The ingestor proxies it from `source_type`:

- `source_type: primary` → `independence: first-party`
- `source_type: secondary` → `independence: independent`
- `source_type: tertiary` → `independence: unknown`

The proxy is a starting classification. It has a known failure mode (next section).

### Entity match: the claim entity's own pages

The proxy knows nothing about the claim's entity, so a page published by the entity itself can arrive labelled `independent` (a "Brave Software" report on brave.com proxies to `secondary`, and the ingest model can also set the label). When the pipeline knows the claim's entity (`dr draft` and `dr step-analyze`: every path runs the one loop with a resolved entity), it applies a deterministic match once, before the analyst runs (`apply_entity_match` in `pipeline/loop/analyse.py`, using `entity_first_party_reason` in `pipeline/common/source_classification.py`). A source is `first-party` for the claim when either:

- **Host**: its URL host (without `www.`) equals or is a subdomain of the host of the entity's `website` or its parent company's `website`. `search.brave.com` matches `brave.com`; `notbrave.com` and `brave.com.example.net` do not.
- **Profile**: the URL is the entity's own account on LinkedIn, X, Twitter, Facebook, Instagram or YouTube: the account handle in the path (`linkedin.com/company/<handle>`, `linkedin.com/posts/<handle>_...`, `x.com/<handle>`, `youtube.com/@<handle>`) equals an entity name with its words joined by `-`, `_` or nothing. The publisher of such a page is usually the platform.
- **Publisher**: its `publisher`, lowercased with punctuation and a trailing `inc`/`llc`/`ltd` removed, equals the entity's `name`, `legal_name` or an alias, or the same fields on the parent company (`parent_company` on the entity file). Equality, not substring: "Meta" does not match "Metacritic".
- **Newswire**: a publisher naming a press-wire service (PR Newswire, Business Wire, GlobeNewswire, ACCESS Newswire, EIN Presswire, PRWeb, Marketwired, Newsfile, Cision, or any publisher with "newswire" in the name; the other names match only as whole words, so "Decision Lab" is not Cision; `NEWSWIRE_ORIGINS` in `pipeline/common/source_classification.py`) is the issuer's own statement. `classify_source_type` puts such a publisher in `primary`, so the proxy label is `first-party` from ingest. For a company or product entity, a release whose title, summary, key quotes or body name the entity is `first-party` for the claim (reason "Entity match: newswire release", with an override recorded when the stored label was `independent`); a release that does not name the entity is off-entity like any other `first-party` source. A subject entity has no off-entity check, so the newswire rule adds nothing for it.

A source that does not match is about someone else, and for a company or product entity it does not count for the entity either way:

- A `first-party` source is another organization's self-report (AWS documentation naming a customer, a Google paper benchmarking ChatGPT). It becomes `unknown`, even when it mentions the entity, unless the claim text names its publisher as a provider ("Euria is hosted on renewable energy by Infomaniak"). One exception keeps the entity's own pages on a sibling host or under a publisher variant: a source that names the entity and whose publisher names the entity or its parent as whole words, or whose URL has the same registrable label as an entity website host (`platform.claude.com` and `claude.ai`, `ai.google.dev` and `gemini.google.com`), stays `first-party` with no override (`entity_affiliated`).
- An `independent` source becomes `unknown` unless its title, summary, key quotes or body name the entity (a whole-word match on a name, legal name or alias, its parent's, or a website host) or the claim text names its publisher.
- An `unknown` source is left alone.

A subject entity is a topic, not an organization, so only the match above applies to it. The match beats any label, including an analyst override for the same source. The analyst sees the corrected label, and each correction is recorded on the claim as a `source_overrides` entry with a reason starting "Entity match:" or "Off-entity:" (see [Source overrides on claims](#source-overrides-on-claims)). The source file's `independence` is not changed: a brave.com page is first-party on a Brave claim and may be independent evidence on another entity's claim. `parent_company` and `aliases:` on the entity files are the levers: without `parent_company`, a forum thread published by "Brave Software" on another host does not match a Brave Browser claim. The mention test reads the ingested text, which is short, so a source that names the entity only deep in the page is marked `unknown`; the "Off-entity:" reason shows this on review.

### `source_type` and `independence`: why both?

Two fields, two different questions:

- **`source_type`** (`primary | secondary | tertiary`, set by `pipeline/common/source_classification.py`): how close is this source to the originating authority? Older field; used by the scorer and surfaced in the audit trail.
- **`independence`** (`first-party | independent | unknown`): is this source authored by the entity (or by someone with structural COI to the entity) or not? v1 field; feeds the verification scale and confidence cap.

For most of the corpus the two coincide:

| `source_type` | `independence` | Typical case |
|---|---|---|
| `primary` | `first-party` | Company press release, the entity's own SEC 10-K |
| `secondary` | `independent` | Newspaper article, peer-reviewed journal |
| `tertiary` | `unknown` | Personal blog, foundation site, content aggregator |

That coincidence is why the ingestor mechanically derives `independence` from `source_type`. The mapping is a v1 proxy, not a definition — the two fields answer related but distinct questions and could disagree.

Edges where the proxy is imprecise:

- **Regulator filings about (not by) the entity** are `primary` by publisher rule (sec.gov, ftc.gov) and proxied to `first-party`. The document originates outside the entity but speaks with regulator authority — neither label fits cleanly. Today the proxy treats them as first-party; the analyst can correct per-claim if it matters.
- **Academic articles authored by entity employees** are `secondary` by publisher (arxiv, IEEE) and proxied to `independent`. They may functionally be entity-authored content disclosed through a third-party venue. Independent venue, not independent author. For arXiv papers this is handled: at ingest, `arxiv_corporate_lab` (`pipeline/ingestor/arxiv_affiliation.py`) reads the author block of the paper's HTML render, and when it names Google, DeepMind, Anthropic, OpenAI, Meta AI, FAIR or Microsoft Research (or an email at one of their domains), the lab becomes the `publisher` and the paper `first-party`, so `source_type` is `primary`. The `abs/` and `html/` ingests of one paper agree. The first lab in author order wins, but only when no academic affiliation (a university, institute, college, `.edu` or `.ac.xx` email) comes before it: a paper whose first affiliation is academic keeps the ingest model's labels even with a lab co-author. Footnotes and thanks are ignored, and a paper with no HTML render keeps the ingest model's labels.
- **Secondary sources that restate primary numbers without original analysis** — by far the most common edge — are addressed per-claim via `source_overrides` (see § Source overrides on claims). Other edges currently rely on the analyst flagging them in the narrative.
- **The claim entity's own pages** labelled `independent` (by the proxy or the ingest model) are handled: the entity match above relabels them `first-party` for that claim and records a `source_overrides` entry.

When the v1.x publisher-groups registry lands and the deferred `coi_with_subject` field is added, the proxy can be tightened. For v1, the analyst's restatement test and the entity match are the only persistent correction mechanisms.

### Known failure mode: independent restatement of primary disclosures

The proxy's biggest gap is on the most common real case: a secondary source (a journalist, an analyst) restating a number from a company's own press release or report. The source originates outside the entity, so the proxy classifies it `independent`, but it adds no independent corroboration: the only place the number actually exists is the entity's own document.

**The analyst applies a restatement test on each `independent` source**: does this source conduct original analysis of the claim, or does it restate a number the entity itself published? If it only restates, the analyst overrides `independence` to `first-party` for that source's contribution to this claim's `verification_level`, and records the override on the claim.

The override is per-claim, not on the source file itself. A source may add genuine independent analysis on one claim and restate primary disclosures on another. See [Source overrides on claims](#source-overrides-on-claims).

## Confidence cap

When `verification_level` is `claimed` or `self-reported`, `confidence` is capped at `low`. The analyst applies the cap, and the level fit applies it when it lowers a level; `dr lint` catches drift (`confidence-cap-violation`). The cap fires regardless of how comprehensive or auditable the entity's self-report appears. Cap quality is communicated through the rationale, not through cap level.

### Rationale templates

When the cap fires, the analyst writes a one-sentence rationale matching one of these templates and puts it in the `cap_rationale` field on the claim. The exact words are not required; the structure and honesty are.

- "Confidence is capped at low — all sources originate from entity documentation; no independent source was found that conducts original analysis of this claim."
- "Confidence is capped at low — the independent sources found restate entity-published numbers without conducting original analysis; no source independently confirms this claim."
- "Confidence is capped at low — sources are informal entity communications (blog posts, announcements); no formal documentation or independent source was found."

The display layer surfaces the rationale beneath the verdict, in plain text.

### Editorial policy on absence of evidence

When the evidentiary basis is "no contradicting evidence found" rather than corroborating evidence (no breach disclosures, no regulatory findings, no public lawsuits), the analyst notes this explicitly: "No contradicting evidence was found; this does not constitute independent confirmation."

Claims where absence of evidence is the primary basis should use `verdict: unverified` rather than forcing a positive or negative verdict.

### Lint enforcement

`dr lint` issues a warning when `confidence` is `medium` or `high` and `verification_level` is `claimed` or `self-reported`, and (`verification-level-pool-mismatch`) when a level needs more `independent` sources than the claim's written list has, or the level is `self-reported` and the list has neither an `independent` source nor a `first-party` report, documentation, dataset or article. The warnings surface drift; the analyst sets the cap and the [level fit](#level-fit-to-the-written-sources), run inside the loop before the Evaluator, lowers an unsupported level.

## Source overrides on claims

A claim may carry an optional `source_overrides:` list to record per-claim overrides of source-level fields. Two things write it: the analyst, for the restatement failure mode above, and the pipeline's entity match (see [Entity match](#entity-match-the-claim-entitys-own-pages)), whose entries have a reason starting "Entity match:" or "Off-entity:". Example of an analyst override:

```yaml
source_overrides:
  - source: 2025/some-secondary-restatement
    independence: first-party
    reason: restates Anthropic RSP without original analysis
```

The analyst sets these. They have two purposes:

1. They make the analyst's per-claim judgment legible — a reader can see why a source the file says is `independent` was treated as `first-party` for this claim.
2. They are honest in the data: `verification_level` derivation uses the overridden values, not the raw source-file values.

The source file's `independence` is unchanged; the override is scoped to the one claim it was recorded on.

## Entity metadata

The entity-level `website` field doubles as the canonical-website / primary-source-disambiguation signal. The scorer treats sources whose URL matches `website` as the entity's first-party content (see `pipeline/researcher/scorer.py`'s "ENTITY DISAMBIGUATION" rule). When an entity carries a `legal_name` distinct from its display `name`, COI and restatement-test reasoning in the analyst use the legal name. When an entity carries `verification_status` other than the default `verified` (e.g., `unverified-startup`), the analyst weights sparse-evidence claims about that entity more conservatively, and the entity page renders an "unverified" badge.

`founded` and the entity's narrative `history` body are hand-written in the entity file (no agent populates them); `founded` is injected into the analyst and scorer prompts so source-date horizons can be reasoned about against the entity's actual lifespan.

## Publisher registry

Bigger registry-driven trust signals (`site_trust`, `publisher_group`) are deferred to v1.x. The reasoning:

- `site_trust` would map domains to a trust band (high / medium / low). Without a registry it would be inconsistent or wholly absent on most sources.
- `publisher_group` would identify ownership clusters (so two outlets owned by the same conglomerate don't appear as two independent corroborations).

When the registry lands, `site_trust: unknown` will be the default for any domain not in it. **`unknown` is not a negative signal** — it means "this publisher is not yet tracked," not "this publisher is untrusted." The display layer must not penalize unknown publishers.

Until then, low-trust sources are handled by the blocklist (PR wire services, content farms) for hard drops.

## What the system cannot do

Some claim categories are inherently unverifiable without insider access — energy contracts, training data practices, internal safety protocols. Independent sources covering these claims often restate the entity's own numbers. The verification scale will sometimes show `independently-verified` or `multiply-verified` for such claims even though every source ultimately traces to the entity's own document. The analyst's restatement test (above) is the only mitigation.

When the analyst recognizes that the entire pool is restatement, the right move is the cap rationale plus a narrative caveat, or `verdict: unverified` if the claim cannot be supported even at low confidence.

## Cross-references

- Plan that introduced this v1 scope: [`docs/plans/completed/source-quality-robust-roadmap_completed.md`](../plans/completed/source-quality-robust-roadmap_completed.md).
- Strategic critique that drove the rewrite: [`docs/plans/completed/source-quality-agent-review_completed.md`](../plans/completed/source-quality-agent-review_completed.md).
- Survey of all source-quality signals considered: [`docs/plans/completed/source-quality_survey_completed.md`](../plans/completed/source-quality_survey_completed.md).
- Active follow-up backlog (ideas, drafted plans, v1.x trust schema digest): [`docs/plans/deferred/source-quality-followups.md`](../plans/deferred/source-quality-followups.md).
- Canonical schema: `src/content.config.ts` (sources, claims).
- Analyst behavior: `pipeline/analyst/instructions.md`.
- Lint rules: `pipeline/linter/checks.py`.
