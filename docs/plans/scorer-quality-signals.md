# Scorer quality signals

**Status**: `ready`
**Derived from**: [`plans/drafts/source-quality-do-now.md`](drafts/source-quality-do-now.md) Groups 1 and 3a
**Survey**: [`plans/source-quality_survey.md`](source-quality_survey.md) §1, §4, §6

Three changes to the scorer and query planner that can be implemented without architectural changes. Together they address the most direct quality bypasses in the current pre-ingest pipeline.

---

## Item A: Fix scorer fallback behavior

**Survey ref**: §6 (scoring and ranking)

### Problem

When the URL scorer drops all candidates (every URL scores <4), `decomposed.py` falls back to keeping all candidates. This silently bypasses quality filtering for the weakest queries — the ones that most need it. The behavior exists as a safety net to prevent pipeline stalls, but it means low-quality search results pass through unchecked when the scorer cannot find anything worth keeping.

### Change

When the scorer drops all candidates, return an empty URL list rather than passing all candidates to ingest. Log the failure in the research trace with a `scorer_dropped_all: true` flag and the query text.

**Downstream consequence caveat**: returning `[]` from `decomposed_research` causes the early-exit guard at the top of `verify_claim` / `research_claim` (`if not urls: return`) to fire before `below_threshold()` is ever reached. The claim exits without a `blocked_reason`, which causes `onboard_entity` to misclassify it as `ANALYST_ERROR`. The implementation must handle this: either propagate a `StepError` with `error_type="scorer_dropped_all"` that `_classify_blocked_reason` maps to `insufficient_sources`, or set `blocked_reason` on the early-exit path explicitly. Without this, the pipeline halt is correct but the cause label is wrong.

Do not trigger a re-plan. That requires the state machine. This change is scope-limited to removing the silent passthrough.

### Scope

- Code change in `pipeline/researcher/decomposed.py` (not `orchestrator/`). There are **three** fallback return paths in the current code (lines 128-139): the explicit drop-all branch (`if not scored.kept and candidates:`), the `asyncio.TimeoutError` except branch, and the general `Exception` except branch. All three currently return `[c.url for c in candidates]`. This item targets the **explicit drop-all branch only**; the timeout and exception branches should retain the existing fallback behavior (returning all candidates is preferable to losing the whole query on a transient LLM failure).
- Research trace extended with `scorer_dropped_all` field per query
- The `blocked_reason` mislabeling issue described in the Change section must be resolved as part of this item (see above)
- Unit test: scorer drops all → no candidates passed to ingest → trace logged → early-exit path sets `blocked_reason=insufficient_sources`, not `analyst_error`

### Out of scope

Triggering a re-plan when the scorer drops everything. That belongs in the state machine quality gate plan.

---

## Item B: Inject publisher quality hints into the scorer prompt

**Survey ref**: §4 (publisher and site quality), §6 (scoring and ranking)

### Problem

The scorer prompt receives URL, title, snippet, and source query. It has no awareness of domain type. A PR wire service press release with an on-topic headline scores identically to a regulatory filing or independent journalism piece. Community forum posts (Reddit, Quora, Hacker News) score high on relevance when the snippet is topically relevant, but are structurally low-quality evidence for research claims.

### Change

For each candidate URL, compute a publisher quality label before calling the scorer, and inject it as a per-candidate field in the scorer prompt.

Two components:

**1. Domain classification at candidate stage**: `pipeline/common/source_classification.py` operates on post-ingest `publisher` (string) and `kind` (SourceKind) fields — it does not inspect URLs or hostnames. At the candidate stage, only `url`, `title`, `snippet`, and `from_query` are available. There is no existing pre-ingest classifier to extract. Instead, draw on the publisher substring lists (`_PRIMARY_PUBLISHERS`, `_SECONDARY_PUBLISHERS`, `_TERTIARY_PUBLISHERS`) from that module as a seed and write new hostname-based logic: extract the registered domain from the candidate URL and substring-match it against the same lists. This produces an approximate `publisher_quality` label. It will be less accurate than the post-ingest classifier (no `kind` signal, hostname may not match publisher name), but is sufficient as a scoring hint.

**2. Forum domain soft-block**: Add a list of known community forum domains (reddit.com, quora.com, news.ycombinator.com, stackexchange.com, and subdomains) to the scorer prompt as a global instruction: "treat results from these domains as low-quality evidence; score them ≤3 unless no higher-quality alternatives exist in this candidate set." Alternatively, add these to the blocklist with a `soft: true` field that allows them through only when the blocklist would otherwise drop all candidates.

**Scorer prompt change**: Add a `publisher_quality` field per candidate (e.g., `primary`, `secondary`, `tertiary`, `forum`) and update the scorer instructions to use it as a tiebreaker and penalty signal: a `tertiary` or `forum` candidate should be scored lower than a `primary` candidate with equivalent topical relevance.

### Scope

- Domain classification logic extracted from `source_classification.py` for pre-ingest use (no changes to existing post-ingest behavior)
- Scorer prompt revised to accept and use `publisher_quality` per candidate
- Forum domain list defined (can start with the 4-5 most common; expand as needed)
- Unit tests: tertiary-domain candidate scores lower than equivalent primary-domain candidate; forum-domain candidate scored ≤3 when primary alternative exists

### Out of scope

Full integration with `source-trust-metadata.md` trust schema. That plan owns the full trust signal hierarchy. This change uses only the existing domain patterns and a forum list — no trust schema dependency.

---

## Item C: Pass `parent_company` into the planner and scorer prompts

**Survey ref**: §1 (query generation), §6 (scoring and ranking)

### Problem

`parent_company` is present on the `ResolvedEntity` dataclass but not injected into any prompt. For subsidiary products and holding-company claims, queries without the parent name miss a large body of relevant coverage. The scorer also misses the relationship: a source about Anthropic is relevant to a claim about Claude, but the scorer only sees the entity name "Claude" and cannot infer the connection.

This gap is noted in `research-quality-ideas.md` under "Scoring with entity context." The dependency cited there is entity enrichment (entity having a usable `parent_company` field), not the trust schema.

**Data format note**: Entity files store `parent_company` as a ref string (e.g. `companies/anthropic`), not a display name. `parse_entity_ref` reads this raw string into `ResolvedEntity.parent_company`. Before injecting it into a prompt, the implementer must resolve the display name — either strip the `{type_dir}/` prefix and titlecase the slug, or load the parent entity file. The simpler approach (strip + titlecase) is sufficient for v1. The analyst already uses `resolved_entity.parent_company` directly in one path; if that emits the raw ref into the prompt it is a pre-existing bug, but Item C should not replicate it.

### Change

Two prompt changes:

**Planner prompt**: The planner context is assembled in `build_entity_context()` in `pipeline/orchestrator/entity_resolution.py` and injected in `pipeline/researcher/decomposed.py`. If `parent_company` is populated on the resolved entity, add a `Parent company: {name}` line to `build_entity_context()`. The planner system prompt should be updated to instruct the model to include the parent name in at least one query angle when it is relevant to the claim topic.

**Scorer prompt**: The scorer prompt is built by `build_scorer_prompt()` in `pipeline/researcher/scorer.py`. This function currently takes only `(entity: str | None, claim: str, candidates: list[SearchCandidate])` — it does not accept a `ResolvedEntity`. Extending it to include parent company requires either adding a `parent_company: str | None` parameter or accepting the full `ResolvedEntity`. The call site in `decomposed.py` must be updated accordingly. If `parent_company` is populated, add it to the entity context block and instruct the scorer that sources about the parent company are relevant to claims about the subsidiary.

### Scope

- `parent_company` display-name resolution added before prompt injection (strip type prefix + titlecase, or load parent entity file)
- `parent_company` injected into `build_entity_context()` for the planner prompt (conditional on field being populated)
- `build_scorer_prompt()` signature extended; `parent_company` injected into scorer entity context (conditional)
- No schema changes required; field already exists on `ResolvedEntity`
- Unit test: entity with `parent_company: companies/anthropic` set → planner prompt includes "Anthropic"; scorer prompt includes "Anthropic" (not the raw ref string)

### Out of scope

`query_angles` per-entity hints (separate item in do-now plan). Alias expansion beyond `parent_company`.

---

## Implementation order

A → C → B is the suggested order. A (fallback fix) is a code change with no prompt dependency. C (parent company) is two prompt additions with no external dependencies. B (publisher hints) depends on extracting the domain classification logic, which is slightly more involved.

All three can be implemented and tested independently and shipped together.

---

## Risks and edge cases

**Item A — increased block rate**: Removing the drop-all fallback means queries that currently surface only low-quality results now contribute zero candidates. With `max_initial_queries=5` and a threshold of 4 usable sources, losing even one query's worth of candidates can push a claim past `below_threshold`. This is the correct behavior, but it will increase the blocked-claim rate for claims with poor search coverage. Operators should expect more `blocked_reason: insufficient_sources` claims after this change ships.

**Item B — hostname heuristic false positives/negatives**: The publisher substring lists were not designed for hostname matching. Substrings like "google" will match `google.com` but also `googleblog.com`; "journal" will not match `wsj.com`. Treat the resulting labels as hints, not ground truth, and keep scorer instructions appropriately hedged ("use as a tiebreaker").

**Item C — raw ref injection risk**: If the `parent_company` ref string (`companies/anthropic`) is passed to a prompt without resolving the display name, the planner or scorer may treat it as a literal query term and produce malformed queries. Validate display-name resolution in the unit test.

---

## Acceptance

- A query where the scorer drops all candidates (explicit drop-all branch) results in: no candidates passed to ingest, a `scorer_dropped_all: true` trace entry, and a `blocked_reason` of `insufficient_sources` (not `analyst_error`) on the resulting claim file
- The timeout and exception fallback paths in `decomposed.py` still return all candidates (not changed by this item)
- A candidate URL from a known tertiary domain scores lower than a topically equivalent candidate from a primary domain in the scorer output
- A candidate URL from reddit.com or quora.com scores ≤3 when primary-domain alternatives are present
- An entity with `parent_company: companies/anthropic` results in planner and scorer prompts that include "Anthropic" (the resolved name, not the raw ref string)

---

## Review history

| Date | Reviewer | Scope | Changes |
|------|----------|-------|---------|
| 2026-05-02 | operator | Initial draft | — |
| 2026-05-02 | pipeline-engineer | Code-grounded review | Fixed file path (orchestrator → researcher); identified three fallback paths, scoped Item A to drop-all branch only; corrected blocked_reason mislabeling issue on early-exit path; rewrote Item B "extract" claim (no pre-ingest classifier exists; draw on publisher substrings for new hostname heuristic); corrected `parent_company` format (entity ref, not display name), named exact prompt construction sites, flagged scorer signature change needed; added Risks and edge cases section; tightened acceptance criteria |
