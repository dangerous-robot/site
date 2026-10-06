# SEC EDGAR as a research origin (Tier 1 Path 3)

**Deferred**: 2026-10-06, investor filings serve partnership and investment claims, not the Responsible AI chatbots claims; no committed entity carries `sec_cik`, so the path would fire on nothing today.

**Status**: stub. Path 3 of [`source-pool-expansion-tier1.md`](../completed/source-pool-expansion-tier1.md), split out when the rest of that plan was marked done. The spec below is moved from it unchanged.

## What already shipped (prerequisites)

- `sec_cik` (10-digit, optional) on company entities: `src/content.config.ts`, commit `a40a09f`.
- `edgar` value in the `acquisition.origin` enum and in `ACQUISITION_ORIGINS` (`pipeline/orchestrator/stats.py`): `a40a09f`, `ee63cae`.
- Per-host throttle (`pipeline/common/throttle.py`, EDGAR 10/s slot): `9a26ba8`.
- `edgar_ua_missing` and `edgar_rate_limited` documented in the `StepError` docstring (`pipeline/orchestrator/checkpoints.py`): `0e5b1ff`.
- `VerifyConfig.research_origins` activation list: `98d094c`. Path 3 activates by adding `'edgar'` to it.

## Not built

- `pipeline/researcher/tools/edgar.py` (filing index, full-text search, filing fetch; `SEC_EDGAR_USER_AGENT` env var).
- `pipeline/researcher/subject_relevance_classifier.py` (small-model `SubjectRelevance` check).
- Filer-vs-subject `independence` override in `pipeline/common/source_classification.py`; SEC publishers in `pipeline/common/publisher_quality.py`.
- `docs/architecture/source-quality.md` § Independence override rules; `AGENTS.md` § Tooling env var note.
- `sec_cik` values on the company entities that would use it (Amazon, Alphabet, Microsoft).
- Also check the open question in `docs/UNSCHEDULED.md` "Source type classification" that SEC EDGAR filings are correctly `primary`.

Success target (from the parent plan): at least 50% of public-investor company claims where `sec_cik` resolves surface one or more EDGAR documents, measured with `dr stats --format json`.

## Spec

Section references (§ Schema prerequisites, § Shared infrastructure, § Codebase touchpoints) point to the parent plan.

**Where**: Researcher, conditional on the entity (or its `parent_company`) carrying a `sec_cik` field. Activation is decided by the selector function described in § Codebase touchpoints, not by branching inside `execute_searches`.

**Schema dependency**: `sec_cik` on the company entity (per § Schema prerequisites). This is the first concrete field on the broader Company-metadata-enrichment idea collected in `source-quality-followups.md` § Company metadata enrichment; the other candidate fields there stay deferred.

**Endpoints**:
- Filing index: `https://data.sec.gov/submissions/CIK{cik}.json`
- Full-text search: `https://efts.sec.gov/LATEST/search-index?q={keywords}&ciks={cik}`
- Filings: `https://www.sec.gov/Archives/edgar/data/...`

**Compliance**: SEC requires a specific `User-Agent` header (`<Org> <contact-email>`) and rate-limits hard at 10 req/sec. Both wire through § Shared infrastructure's throttle and a `SEC_EDGAR_USER_AGENT` env var (no default — Path 3 is skipped if unset, with `edgar_ua_missing` emitted).

**False-positive handling (small-model disambiguation)**: full-text search returns filings *containing* the keywords, not *about* them. Inside `tools/edgar.py`, before merging into the candidate list, run a small classifier per match: `(entity_name, surrounding_paragraph) → SubjectRelevance(label: 'about' | 'mentioned' | 'unclear', rationale)`. Drop `mentioned` (or downweight before the URL scorer sees it); keep `about` and `unclear`. The classifier is a Haiku-class call, deterministic prompt, no tools — same shape as the existing planner/scorer agents. The label and rationale ride on the per-URL `acquisition` audit entry. This keeps subject-vs-keyword disambiguation out of the URL scorer (which works from title + snippet) and out of the analyst's hands.

**Investor-corroboration use case**: Anthropic and OpenAI are private companies and don't file with the SEC themselves. Their commercial-partnership and investment claims **are** corroborated through public-investor filings:

- Anthropic via **Amazon** (CIK 0001018724) and **Alphabet/Google** (CIK 0001652044).
- OpenAI via **Microsoft** (CIK 0000789019).

Path 3's value for these claims is the regulator-authority distinction: a 10-K that quantifies a partnership commitment is a stronger source than a press release announcing it.

### Architecture amendment (regulator-authority)

`source-quality.md` documents this failure mode: *"Regulator filings about (not by) the entity are `primary` by publisher rule (sec.gov, ftc.gov) and proxied to `first-party`. The document originates outside the entity but speaks with regulator authority — neither label fits cleanly."*

Tier 1's resolution: keep the existing two-field model (`source_type` + `independence`) and route the distinction through `independence`:

- Filing **by** the subject entity (the entity is the filer, CIK matches): `source_type: primary`, `independence: first-party` — unchanged.
- Filing **about** the subject entity by another filer (subject mentioned but not the filer): `source_type: primary`, `independence: independent`. The override is recorded as a per-source classification at ingest time.

No new `source_type` enum value. The override is a publisher-rule extension in `pipeline/common/source_classification.py`, gated on the EDGAR-ingest path knowing the subject CIK vs the filer CIK. The CIK comparison is a string equality check on structured data — correctly deterministic, not a model call.

Record the amendment in the same commit as the Path 3 implementation, in `docs/architecture/source-quality.md` § Independence override rules.

**Effort**: 5–7 days (entity-loader plumbing for `sec_cik`, UA/throttle, filing parser, subject-relevance classifier, classification override, tests). Gates on § Schema prerequisites + § Shared infrastructure.
