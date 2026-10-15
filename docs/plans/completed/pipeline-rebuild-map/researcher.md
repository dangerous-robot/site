# Pipeline map: the researcher

Phase 1 (Challenge) reader output for the pipeline rebuild. Facts carry `file:line` against the working tree on 2026-10-14 (HEAD `40ba781`). Paths are relative to the repo root. "Not found" means the reader looked and found nothing on disk.

Scope: `pipeline/researcher/` (`decomposed.py` 612 lines, `scorer.py` 133, `planner.py` 48, `agent.py` 85, `entity_verifier.py` 127, `entity_enricher.py` 127, `tools/tavily.py` 155, `tools/arxiv.py` 117) plus the orchestrator code that consumes its output (`pipeline/orchestrator/pipeline.py`, `cli.py`).

## 1. Entry points

| Entry | Location | What calls it | Notes |
|---|---|---|---|
| `decomposed_research(claim_text, entity_name, cfg, sem, client, resolved_entity, topics)` | `pipeline/researcher/decomposed.py:355-516` | `_research` in `pipeline/orchestrator/pipeline.py:1004-1048`; `dr step-research` in `pipeline/orchestrator/cli.py:298-310` | The only research function. Returns `ResearchOutput` (`decomposed.py:51-70`). |
| `_research(...)` (orchestrator wrapper) | `pipeline/orchestrator/pipeline.py:1004-1048` | `verify_claim` at `pipeline.py:401-403` (passes `topics`); `research_claim` at `pipeline.py:1672` (no `topics`); `gather_light_research` at `pipeline.py:2022` (query `"<entity> official website"`, no entity, no topics) | Adds the blocklist filter and pool cap (`_apply_blocklist_cap`, `pipeline.py:786-860`), then trims `url_addresses` and `prefetched_bodies` to the kept URLs (`pipeline.py:1045-1048`). |
| `execute_searches(queries, client, backend, extra_origins, acquisition_out, errors_out, tool_outcomes_out)` | `decomposed.py:186-352` | `decomposed_research` at `decomposed.py:417-425` | Fans out web plus arXiv searches, dedups by canonical URL. |
| `research_planner_agent` | `pipeline/researcher/planner.py:43-48` | `decomposed.py:387-391` | Claim to 2-5 sub-questions and tagged queries. |
| `url_scorer_agent` | `pipeline/researcher/scorer.py:90-95` | `decomposed.py:491-495` | Scores each candidate per sub-question from title and snippet only. |
| `entity_verifier_agent` | `pipeline/researcher/entity_verifier.py:100-105` | `onboard_entity` Phase B, `pipeline.py:2386-2399` | Verified / needs-disambiguation / unverified. |
| `entity_enricher_agent` | `pipeline/researcher/entity_enricher.py:97-102` | `enrich_entity` at `pipeline.py:2238-2245` (`dr entity-enrich`); `onboard_entity` at `pipeline.py:2484-2490` | Drafts `founded`, `description`, `history_markdown`. |
| `search_brave` | `pipeline/researcher/agent.py:17-85` | `_dispatch_one_query` (`decomposed.py:178,182`); `_probe_collision_suggestions` directly at `pipeline.py:2106-2107` | The second caller bypasses the researcher entirely (bare entity name, `max_results=8`). |
| `search_tavily` | `pipeline/researcher/tools/tavily.py:69-155` | `_dispatch_one_query` (`decomposed.py:157`) | Default backend. |
| `search_arxiv` | `pipeline/researcher/tools/arxiv.py:87-117` | `_dispatch_arxiv_one_query` (`decomposed.py:117`) | Also imported by `pipeline/ingestor/arxiv_affiliation.py:23` for the throttle constants. |
| CLI flags | `cli.py:195` (`--researcher-model`, env `DR_RESEARCHER_MODEL`); `cli.py:885,941,1040,1775` (`--max-initial-queries` on claim-probe, claim-draft, claim-refresh, onboard) | | `research_origins` and `search_backend` have no CLI flag; `search_backend` reads env `RESEARCH_SEARCH_BACKEND` (`pipeline.py:299-301`). |

## 2. The research step, in order

All line numbers in `pipeline/researcher/decomposed.py` unless stated.

| Step | Lines | What happens | Error path |
|---|---|---|---|
| R0 Init | 374-377 | `ResearchOutput` with `trace = {mode: decomposed, acquisition: {}, tool_outcomes: []}`. | |
| R1 Planner prompt | 379-384 | `build_entity_context(resolved_entity, entity_name)` (`pipeline/orchestrator/entity_resolution.py:78-103`: name, description, aliases, parent company, official website, search hint include/exclude) + `Claim: ...` + `Generate up to {cfg.max_initial_queries} search queries.` | |
| R2 Planner call | 386-410 | Under the `llm_concurrency` semaphore, model `cfg.model_for("researcher")`, timeout `cfg.research_timeout_s` (120 s, `pipeline.py:307`). Output `ResearchPlan` (`planner.py:17-25`): 2-5 `SubQuestion`s, `PlannedQuery(text, sub_question_id)`, `rationale`. Queries hard-truncated to `max_initial_queries` (395; default 7, `pipeline.py:312`). `queries_by_sub_question` grouped at 397 and 571-575. | `timeout` (405), `model_error` (408): return with no URLs. `no_queries` (413). |
| R3 Origin select | 416, 77-95 | `_select_research_origins`: arXiv only when `topics` intersects `ACADEMIC_TOPICS` (`pipeline/common/models.py:126-130`: ai-safety, environmental-impact, industry-analysis) and `"arxiv"` is in `cfg.research_origins` (default `["tavily","arxiv"]`, `pipeline.py:293`). `ACADEMIC_ORIGINS = {"arxiv"}` (`models.py:134`). | |
| R4 Search fan-out | 417-425, 186-352 | One task per query on the web backend (248-250), one per (origin, query) for arXiv (257-266). `asyncio.gather` for both (275-278). Dedup key `canonicalize(url)` (295; `pipeline/common/canonical_url.py:54`); first contributor wins (299-304), web results processed before arXiv (329-350). Each candidate gets `publisher_quality` from the hostname (311; `pipeline/common/publisher_quality.py:21-38`). `acquisition_out[url] = {stage: research, origin, query, paper_id?}` (314-323). | Per query: Tavily 429 twice -> `tavily_rate_limited` StepError then Brave (159-167); Tavily RuntimeError (no key) or any exception -> Brave silently (168-179). arXiv: `timeout` or `http_error` StepError, no fallback (117-128); empty feed -> `tool_outcomes` entry (130-134). Unknown backend -> Brave with a warning (231-236). |
| R5 Empty check | 426-431 | `candidates_seen` trace; `no_results` StepError when zero. | |
| R6 Scorer prompt | 433-452 | `build_scorer_prompt` (`scorer.py:98-133`): entity block (name, legal name, founded, parent company, official website, "Avoid results about" from `search_hints.exclude`), claim, sub-question list with rationales, candidates as URL + title + snippet + publisher quality. | |
| R7 Scorer call | 489-509 | Under the semaphore, same model and timeout. Output `ScoredURLs(kept: [ScoredCandidate(url, addresses, score)], dropped: [url], rationale)` (`scorer.py:28-60`). Trace: `urls_kept`, `urls_dropped`, `scorer_rationale`. | `scorer_dropped_all` when kept is empty (504-508): returns no URLs. `timeout` or `model_error` (510-516): fallback tags every candidate with every sub-question id, scores empty (453-460). |
| R8 Merge | 509, 526-554 | `_merge_kept`: map each kept URL back to the candidate's own URL by page key (537, 545), merge forms of one page by `canonical_key` (546; arXiv forms share a key, `canonical_url.py:171-198`), union `addresses`, keep the highest score (550-553). | |
| R9 Commit | 477-487 | `_apply_entity_exclude` (578-612): domain-shaped `search_hints.exclude` entries (contain `.`, no space) become `BlocklistEntry(reason="entity_exclude")` and drop matching hosts; a URL that is the entity's own profile page (`profile_url_names_entity`, `pipeline/common/source_classification.py:191`) is spared and listed under `trace.entity_exclude_spared` (598-605); dropped ones under `trace.entity_exclude_dropped` (606-607). Then `_rank_kept` (557-568): entity's own website host first, then score (missing = `DEFAULT_SCORE` 3.0), then scorer order; parent host gets no boost. `prefetched_bodies` kept for surviving URLs (486). | |
| R10 Orchestrator cap | `pipeline.py:1029-1048`, `786-860` | `_apply_blocklist_cap`: `research/blocklist.yaml` filter (`filter_urls`, `pipeline/common/blocklist.py:72`), spare the entity's own profile post when it has a prefetched body (`pipeline.py:806-824`, `trace.blocklist_spared`), then `_coverage_pool` cut to `candidate_pool_size` (32, `pipeline.py:278`) keeping each sub-question's first two URLs (`pipeline.py:761-783`). `blocked_host` StepError per dropped URL, `all_blocked` when nothing is left (841-858). `urls_after_blocklist` trace (1048). | |

## 3. Sub-question coverage (the `addresses` tags) downstream

| Where | Location | Fact |
|---|---|---|
| Tag origin | `scorer.py:30-36, 74-76` | `addresses` = sub-question ids on which the scorer gave >= 3, judged from title and snippet only. Non-empty by instruction, not by validator (the field has no `min_length`). |
| Ingest order | `pipeline.py:957-968` | `remaining = max_sources - len(cached_sources)`; `cached_counts` counts cached (dedup-hit) URLs' `addresses`; `_order_by_coverage` (`pipeline.py:727-758`) fills the thinnest sub-question first, greedy, so the ingest loop (which stops at `remaining` successes in list order) reaches thin sub-questions. |
| Pool cut | `pipeline.py:761-783`, `839-841` | `_coverage_pool` reserves each sub-question's first two URLs before the ranked fill. |
| Tag carried onto sources | `pipeline.py:436, 443` (verify_claim) and `1699, 1706` (research_claim) | `sd["addresses"] = _addresses_with_aliases(url, ro.url_addresses, notes.aliases)` (`pipeline.py:993-1000`): a URL that redirected to the same page as another contributes its tags too. |
| Coverage map | `pipeline.py:456-459`, `1715-1718`, `676-698` | `_invert_addresses` builds `sub_question_coverage: {sq_id: [source_id]}` from the post-ingest sources' `addresses`. Empty list = uncovered. `_warn_uncovered` (`701-714`) logs a warning only; not a `result.errors` entry. |
| Analyst prompt | `pipeline/analyst/agent.py:310-325` | Sub-questions listed; an uncovered one is marked "(no source addresses this sub-question; describe this gap in plain words and never write the sub-question id)". Sources loaded from disk carry no `addresses`, so `dr step-analyze` marks nothing (comment at 311-312). |
| Sidecar | `pipeline.py:650-673`, written at `1850-1853`, `2786-2789`, `2842-2845`, `2895-2898`, `2959-2962` | `sub_questions: [{id, question, rationale, queries, citations}]`; `research:` block is `ResearchOutput.trace` verbatim. `VerificationResult` fields at `pipeline.py:149-156`. |
| Consumers that do not read tags | `pipeline/linter/checks.py`, `pipeline/auditor/` | grep for `sub_question`, `addresses`, `coverage` returns nothing in either package. The Evaluator and lint never see coverage. |
| Site schema | `src/content.config.ts:58` | `acquisition` is in the sidecar Zod schema; `sub_questions` is not matched by grep there (not found). |

Live example (`research/claims/subjects/generative-ai/answering-a-generative-ai-prompt-uses-roughly-ten-times-the-electricity-of-a-web-search.audit.yaml`): 7 queries (`:18-25`), `candidates_seen: 57`, `urls_kept: 17`, `urls_after_blocklist: 16` (`:30-32, 62`); sq2, the web-search baseline, got one of the seven queries and one citation (`:80-88`), and that citation is a per-prompt article. All 8 ingested sources have `origin: tavily`, none `arxiv`, although the claim's topic is environmental-impact (see hazard H3).

## 4. Query decomposition (planner) facts

- Instructions at `planner.py:27-41`: 2-5 sub-questions, "independently answerable, factually framed, one axis of the claim", ids `sq1..`; for environmental, privacy and disclosure claims the suggested axes are first-party channels, third-party databases, and the technical mechanism (`:32`); queries 3-7 words in Brave format, no `site:` operators, at most one quoted phrase (`:36-39`); subject entities skip the entity name (`:40`).
- The prompt tells the model `max_initial_queries` once (`decomposed.py:383`); the instruction text says "2 to `max_initial_queries`" literally (`planner.py:34`), the number is only in the user prompt.
- `ResearchPlan.sub_questions` has `min_length=2, max_length=5` (`planner.py:18`); `SubQuestion.id` must match `^sq\d+$` (`pipeline/common/models.py:23-26`). Nothing checks that a `PlannedQuery.sub_question_id` names an existing sub-question; `_group_queries_by_sq` (`decomposed.py:571-575`) groups whatever id the model wrote, and `_build_sub_questions_block` (`pipeline.py:665-671`) looks up by the sub-question's id, so a query tagged with an unknown id silently disappears from the sidecar.
- The planner is told nothing about the claim's topic, criterion notes, or prior sources on disk; its inputs are the entity context block and the claim sentence only (`decomposed.py:379-384`).
- `search_hints.include` reaches the planner as "Prefer queries including: ..." (`entity_resolution.py:98-99`); `search_hints.exclude` reaches both planner ("Avoid results about", `:100-101`) and scorer (`decomposed.py:437-441, 449`).

## 5. Scoring facts

- Scale 1-5 per sub-question; keep at >= 3 on at least one (`scorer.py:66-76`). `docs/architecture/research-flow.md:277` says ">= 4" (doc drift, see section 11).
- Forum hosts (`publisher_quality.py:12-19`) score <= 2 unless nothing better exists (`scorer.py:85`); publisher quality is a tiebreaker only (`:85`).
- Parent-company sources count as relevant to the subsidiary (`:83`).
- Entity disambiguation rule: a different organization at a different domain scores 1 (`:86`).
- The scorer is told "never drop a candidate because it repeats another" (`:78`) and "every input URL must appear in kept or dropped" (`:80`); nothing in code verifies the second rule (grep for a kept+dropped-equals-input check in `decomposed.py` returns nothing; backlog row RF17 in `docs/UNSCHEDULED.md:358`).
- `score` coercion (`scorer.py:42-54`): bool, unparseable, or non-finite values become 3.0 so validation never retries over a bad number.
- Agent `retries=2` on both planner and scorer (`planner.py:47`, `scorer.py:94`); each is declared with the `"test"` model and overridden per call (`decomposed.py:387, 491`).
- Scoring is relevance only. There is no stance, polarity, or "supports vs contradicts the claim" field in `ScoredCandidate` (`scorer.py:28-54`).

## 6. Counter-evidence search

Not found. A case-insensitive grep for `counter-evidence`, `counterevidence`, `disconfirm`, `contrary evidence`, `opposing`, `rebut` over `pipeline/**/*.py` and `pipeline/**/*.md` (tests excluded) returns nothing. The planner instructions (`planner.py:27-41`) ask for sub-questions that "cover the whole claim" and never for a query that would falsify it; the scorer (`scorer.py:63-88`) scores topical relevance. The only places the phrase appears are the interview note (`handoff/2026-10-13-pipeline-improvement-interview.md:15, 26`) and the C1 probe note (`handoff/2026-10-10-ai-energy-subject-claims.md:30, 32`).

## 7. The baseline-half problem for comparative claims

- Reported: `handoff/2026-10-10-ai-energy-subject-claims.md:16` (C1 ingested 8 per-prompt sources, no web-search figure) and `:30` (probe missed the 2025 Google and Epoch AI measurements). Roadmap text at `docs/v1.0.0-roadmap.md:270`.
- What RE-AF (Sub-question coverage and the cited source list) did about it: ingest reorder by thinnest sub-question (`pipeline.py:727-758`), pool reservation of two URLs per sub-question (`pipeline.py:761-783`), uncovered warning and analyst marking. It did not change the planner or scorer, and "coverage still counts the scorer's snippet-based `addresses`" (`roadmap.md:270`, last sentence).
- Why the fix cannot reach the baseline when the planner under-queries it: in the C1 sidecar the baseline sub-question sq2 got one query out of seven (`...web-search.audit.yaml:80-86`). The planner distributes queries freely across sub-questions (`planner.py:34`); nothing enforces a minimum per sub-question. If every candidate the scorer tags with sq2 is a per-prompt article (sq2's one citation is `2025/the-hidden-cost-of-ai-conversations...`, a per-prompt source, `:87-88`), the reorder faithfully ingests the wrong page first. RE-AL (Source pool and coverage quality) names this at `roadmap.md:334`: "Scorer tags count as sub-question coverage without the evidence".
- No post-ingest check compares what a source actually says against the sub-question it was tagged for; the tag is set before fetch and never revised (`scorer.py:74`, `pipeline.py:676-698`).

## 8. Entity verifier and enricher facts

- Both consume `LightResearchBundle` (`pipeline.py:1964-1986`: name, type, raw page summary, website, probe excludes, fetch errors). `gather_light_research` (`pipeline.py:1991-2060`) runs the full decomposed researcher (planner + scorer, two model calls) with the query `"<entity> official website"` and no entity context (`:2021-2022`), takes the first http(s) URL as the website (`:2024-2026`), ingests one page, then runs `_probe_collision_suggestions` (`:2051-2053`).
- `_probe_collision_suggestions` (`pipeline.py:2085-2130`) calls `search_brave` directly on the bare entity name (always Brave, never Tavily), takes the top 5, and suggests up to 3 hosts outside the entity's site domain and shared platforms as excludes. RE-AL row at `roadmap.md:337`: it treats coverage of the entity as a collision.
- Verifier per-type sections include COMPANY (`entity_verifier.py:81-85`); enricher per-type sections include COMPANY (`entity_enricher.py:75-81`). Interview Q8(C) (drop company entities) touches both dicts and the `EntityType.COMPANY` branches.
- Both run on the researcher model and `research_timeout_s` (`pipeline.py:2240-2245, 2394-2399, 2485-2490`).
- Enricher refusal when no page summary: `enrich_entity` returns `failed` (`pipeline.py:2226-2236`); onboard skips (`pipeline.py:2475-2481`). Verifier still runs on an empty bundle (backlog row `docs/UNSCHEDULED.md:433`).
- Gate hooks: `review_entity_enrichment` (`pipeline/orchestrator/checkpoints.py:135, 246`) and `review_entity_disambiguation` (`:148, 264`).

## 9. Search tool facts

| Tool | Facts |
|---|---|
| Tavily (`tools/tavily.py`) | Default backend (`pipeline.py:300`). `max_results=10`, `search_depth: basic`, `include_raw_content: True` (`:70, 99-107`); the raw body becomes `SearchCandidate.raw_content` and then `ResearchOutput.prefetched_bodies` so the ingestor can skip a live fetch (`decomposed.py:462-464, 486`). Throttle 5 req/s burst 5 (`:37-38, 50-66`). One 429 retry honoring `Retry-After` else 30 s, second 429 raises `TavilyRateLimitError` (`:119-131`). Missing key raises `RuntimeError` (`:88-90`). Timeout 15 s per call (`:115`). |
| Brave (`agent.py`) | `max_results=10` (`:18`). One 429 retry (`:47-59`). Zero results on a quoted query retries once unquoted (`:75-83`). Returns `{url, title, snippet}` with no `raw_content` key (`:61-70`), so `item.get("raw_content")` is `None` at `decomposed.py:312`. Key `BRAVE_WEB_SEARCH_API_KEY` (`:31-33`). No throttle bucket (contrast Tavily and arXiv). |
| arXiv (`tools/arxiv.py`) | Unauthenticated Atom query, `max_results=10` (`:88, 101-105`), throttle 1 request per 3 s burst 1 (`:27-28, 43`), timeout `HTTP_READ_S` = 15 s (`pipeline/common/timeouts.py:23`). Version suffix stripped into `paper_id` (`:38, 46-47, 67`). The raw query text is sent as `search_query` with no field prefix (`:101-105`), the same 3-7 word Brave-style query the planner wrote. Fires for every query when selected (`decomposed.py:259-266`): with 7 queries that is 7 arXiv calls, at least 18 s of throttle wait, and the backlog row RF18 (`docs/UNSCHEDULED.md:359`) records all 7 dropped on a product claim. |

## 10. Where RE-AE, RE-AF and RE-AL touch this code

| Item | Touchpoints in researcher code | Status |
|---|---|---|
| RE-AE (Source pool independence), done beta.7 | `_apply_entity_exclude` spares the entity's own profile URL (`decomposed.py:598-605`, tests `test_researcher_decomposed.py:1185-1256`); `_apply_blocklist_cap` spares a blocklisted entity post with a prefetched body (`pipeline.py:806-824`); `_probe_collision_suggestions` skips shared platforms (`pipeline.py:2118-2121`). The off-entity independence relabel and the arXiv affiliation rule are outside this package (`pipeline/ingestor/arxiv_affiliation.py`, `pipeline/common/source_classification.py`). | Live before/after refresh runs shelved to the backlog (`docs/UNSCHEDULED.md:443`). |
| RE-AF (Sub-question coverage and the cited source list), done beta.7 | `ScoredCandidate.score` and coercion (`scorer.py:37-54`); scorer "never drop duplicates" rule (`scorer.py:78`); `_merge_kept` (`decomposed.py:526-554`); `_rank_kept` (`:557-568`); orchestrator reorder, pool reservation, uncovered warning (`pipeline.py:701-783`). | The planner half of RF5 (sub-questions that name a provider before any evidence; queries that drop the entity anchor) stays open (`docs/UNSCHEDULED.md:347`). |
| RE-AL (Source pool and coverage quality), ready beta.8, to be absorbed by the new loop | Row "Scorer tags count as sub-question coverage without the evidence" (`roadmap.md:334`): `scorer.py:74-76` plus `pipeline.py:676-698`. Row "Dedup hits from a sibling claim shrink the ingest target" (`:336`): `pipeline.py:957`. Row "Collision probe treats coverage of the entity as a name collision" (`:337`): `pipeline.py:2085-2130`. The other four rows (newswire independence, sidecar confidence, cite-by-title, template notes) are outside this package. | None of the seven rows has code yet. |
| RE-AC (Claim restatement), ready beta.8 | `docs/plans/claim-restate.md:240` reuses the researcher's domain-shaped exclude logic by description only (cites `_apply_entity_exclude` at a stale line, `decomposed.py:534`; it is at `:578` now) and says "the researcher is not changed" (`:246`). | No researcher code. |

## 11. Docs versus code (drift found while reading)

| Doc | Says | Code |
|---|---|---|
| `docs/architecture/research-flow.md:273` | "deduplicate by exact URL string" | `canonicalize` key (`decomposed.py:295`). |
| `research-flow.md:277` | "ScoredURLs (kept >= 4, dropped < 4)" | keep at >= 3 (`scorer.py:75`). |
| `research-flow.md:258` | planner returns "QueryPlan (queries list, rationale)" | `ResearchPlan` with sub-questions and per-query tags (`planner.py:17-25`). |
| `research-flow.md:281` | "apply max_sources cap, blocklist filter" | cap is `candidate_pool_size` (`pipeline.py:839-841`); `max_sources` applies at ingest (`:957`). |
| `AGENTS.md:118` | Researcher "returns relevant URLs for ingestion (`web_search` tool)" | tool-free planner and scorer with code-dispatched searches. |
| `docs/plans/claim-restate.md:240` | `_apply_entity_exclude` at `decomposed.py:534` | now `:578`. |
| `docs/architecture/glossary.md:81` | "effort controlled by `max_initial_queries`" and both prompts get entity context | matches; `search_hints`, `legal_name`, `founded`, `website` also reach the scorer (`decomposed.py:442-452`). |

## 12. Duplication

| What | Locations |
|---|---|
| Three research call sites with the same `ro` unpacking into `VerificationResult` (`urls_found`, `research_trace`, `sub_questions`, `queries_by_sub_question`) | `pipeline.py:401-410` (verify_claim), `pipeline.py:1672-1678` (research_claim), `pipeline.py:2022` (light research, partial) |
| `addresses` stamping onto cached and fresh source dicts, then `_invert_addresses` and `_warn_uncovered` | `pipeline.py:436-459` and `pipeline.py:1699-1718` |
| `_build_sub_questions_block` called with the same three arguments at five sidecar write sites | `pipeline.py:1850-1853, 2786-2789, 2842-2845, 2895-2898, 2959-2962` |
| 429 retry-once-with-Retry-After logic | `agent.py:47-59` (Brave) and `tools/tavily.py:119-131` (Tavily) |
| Per-type prompt section dicts and prompt builders with the same shape (name, type, website, excludes, summary, section) | `entity_verifier.py:80-127` and `entity_enricher.py:74-127` |
| Entity-identity and parent-name resolution done twice per run | `decomposed.py:433, 467-473` and again in `_research` at `pipeline.py:1029-1033` |
| Profile-URL sparing logic (drop by host unless it is the entity's own profile page) | `_apply_entity_exclude` (`decomposed.py:596-605`) and `_apply_blocklist_cap` (`pipeline.py:806-824`) |
| Entity exclude host matching in the restater plan re-describes the researcher's | `docs/plans/claim-restate.md:240` versus `decomposed.py:593` |
| Throttle registration at import and again defensively at call time | `tools/tavily.py:50-66, 92` and `tools/arxiv.py:43, 99` |

## 13. Hazards (what a rewrite could silently lose or break)

| Id | Hazard | Location |
|---|---|---|
| H1 | `dr step-research` is already broken: `urls, errors, trace = asyncio.run(_run())` unpacks a `ResearchOutput` with seven fields and raises `ValueError: too many values to unpack (expected 3)` (verified in the venv 2026-10-14). The CLI line dates from `8cffbec` (2026-04-28); `ResearchOutput` replaced the tuple in `17ac9d7` (2026-05-07). No test in `pipeline/tests/test_cli.py` mentions `step-research`. A rewrite that keeps the command name must not copy this. | `pipeline/orchestrator/cli.py:310` |
| H2 | Scorer fallback on timeout or model error tags every candidate with every sub-question and keeps all of them with equal score; downstream coverage then reads as complete and the ingest order is the search order. Nothing in the sidecar says the fallback fired except the `errors` entry. | `decomposed.py:453-460, 510-516` |
| H3 | `research_claim` (`dr claim-draft`) passes no `topics`, so arXiv never fires for ad hoc claims even on environmental-impact subjects; the C1 sidecar shows 8 Tavily sources and 0 arXiv. Only `verify_claim` (refresh, onboard) threads `template.topics`. A rewrite with one claim path decides this once. | `pipeline.py:1672` versus `pipeline.py:401-403`; `cli.py:1166-1170`; sidecar `...web-search.audit.yaml:116+` |
| H4 | The `acquisition` map is keyed by the raw URL the search returned, and `_merge_kept` may replace the scorer's URL with the candidate's form; `_write_audit_sidecar` grafts by URL. Changing which URL form survives breaks the per-URL acquisition record the stats aggregate reads (`pipeline/orchestrator/stats.py:36-43, 164`). | `decomposed.py:314-323, 537-546` |
| H5 | `prefetched_bodies` (Tavily `raw_content`) is the only way a blocklisted entity post is kept (RE-AE exemption) and the way the ingestor skips a fetch; a backend switch to Brave removes both silently. | `decomposed.py:462-464, 486`; `pipeline.py:806-824` |
| H6 | The entity exclude rule keys on `search_hints.exclude` entries that look like domains; free-text entries are left to the scorer prompt. The collision probe writes those entries at onboard time, so a bad probe suggestion drops independent coverage on every later run (RE-AL row at `roadmap.md:337`). | `decomposed.py:593`; `pipeline.py:2085-2130` |
| H7 | Coverage is defined by title-and-snippet tags set before fetch and never revised after the page is read; every downstream consumer (ingest order, pool cut, analyst marking, sidecar citations) treats them as evidence. | `scorer.py:74-76`; `pipeline.py:676-698, 727-783`; `analyst/agent.py:310-325` |
| H8 | Sources loaded from disk carry no `addresses`, so any path that re-analyzes from disk (`dr step-analyze`) has no coverage and the analyst sees no gap marks. A loop that persists coverage would need to store tags on the source or sidecar. | `analyst/agent.py:311-314` |
| H9 | arXiv dispatch runs every planner query against arXiv with a 3 s throttle; a rewrite that adds origins without per-origin query selection multiplies this. | `decomposed.py:257-266`; `tools/arxiv.py:27-28` |
| H10 | `ResearchPlan` validation caps sub-questions at 5 and `retries=2`; a planner that returns 6 fails validation twice then raises `model_error`, which ends the run with no URLs. | `planner.py:18, 47`; `decomposed.py:407-410` |
| H11 | `_select_research_origins` compares `topics` strings against `Category` enum values; callers pass `template.topics` (strings) at `pipeline.py:2728` and `cli.py:1166`, but `analyst_out.verdict.topics` is `list[Category]` (`cli.py:755`), so a future caller passing enum members would never match. | `decomposed.py:89`; `models.py:126-130` |
| H12 | The verifier and enricher per-type dicts are the only place company-specific prompt text lives; removing `EntityType.COMPANY` (interview Q8(C)) also touches `_PER_TYPE_SECTIONS.get(...)` which returns `""` for an unknown type, so the agents would run with no per-type guidance rather than fail. | `entity_verifier.py:80-97, 110`; `entity_enricher.py:74-94, 107` |
| H13 | The light-research pass spends two researcher model calls (planner, scorer) to find one homepage URL. | `pipeline.py:2021-2022` |
| H14 | Nothing in the researcher looks at `research/sources/` on disk before searching; dedup against stored sources happens later in the orchestrator by URL. The backlog "Local source-search prefilter" row (`docs/UNSCHEDULED.md:474-481`) and the restater's keyword retrieval (`claim-restate.md:223-246`) are the only designs for that. | `decomposed.py` (no disk reads) |

## 14. Tests that pin researcher behavior

| File | What it pins |
|---|---|
| `pipeline/tests/test_researcher_decomposed.py` (1339 lines) | planner shape and cap (67, 98); scorer shape (136); dedup (161); step order (179); semaphore (216); drop-all (279, 308); parent company in prompts (333); forum scoring label (389); entity exclude drop and spare (401, 1185-1256); backend dispatch and fallbacks (520-657); `search_backend` config (659-677); acquisition trace (680); origin selection (724-768); arXiv dispatch, no-results, timeout, http error (770-935); topics plumbing (937, 973); legal name and founded in prompt (1008-1084); `_merge_kept` (1086-1133, 1325); arXiv abs/html kept apart (1134); ranking (1258, 1285); odd scores (1298, 1335) |
| `test_scorer.py` | per-sub-question addresses (38); prompt blocks (76-109) |
| `test_research_planner.py` | shape only over a curated corpus (138) |
| `test_research_integration.py` | `research_claim` end to end with TestModel, sidecar key order `research` then `sub_questions` (152-205) |
| `test_tavily_search.py`, `test_brave_search.py`, `test_arxiv_search.py` | transport, 429, quoted fallback, Atom parsing |
| `test_entity_verifier.py`, `test_entity_enricher.py` | per-type prompt sections, agent round trips |
| Not covered | `dr step-research` (H1); the scorer "every input URL appears in kept or dropped" rule (RF17); any live-provider run (all tests use TestModel or FunctionModel) |

## 15. Open questions

- OQ1: Should the planner be required to emit at least N queries per sub-question (the C1 baseline got one of seven), or should the loop re-plan for an uncovered sub-question after ingest? Neither exists today.
- OQ2: Where does a counter-evidence query belong in the new loop: a planner instruction (one sub-question that would falsify the claim), a second scorer pass with a stance field, or a separate search after the analyst drafts? No code or doc decides this.
- OQ3: Does the new loop keep arXiv for ad hoc subject claims (H3), and if so, should academic dispatch use its own query form instead of the Brave-style text?
- OQ4: Should coverage tags be re-derived after ingest from the fetched text (RE-AL row at `roadmap.md:334`), and if so by the ingestor model or by a cheap keyword check?
- OQ5: Does `dr step-research` survive the fold to about five commands (interview Q8(D))? If it does, H1 needs a fix and a test; if not, delete it with the old path.
- OQ6: Is the light-research pass (two model calls to find a homepage) worth keeping when products and subjects are the only entity types, or does onboarding take the website as operator input?
