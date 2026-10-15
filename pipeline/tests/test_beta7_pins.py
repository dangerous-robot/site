"""Beta.7 behaviour pins, driven through the loop's public entry (RE-AR, One loop, one writer).

Each case here was mined from a test that patched a private name in
``orchestrator/pipeline.py``; the original is deleted with that file. Every
case drives ``loop.run(ClaimSpec, VerifyConfig)`` with scripted agents and
``execute_searches`` patched, or a public writer function, never a private
loop helper. The source of each case is named in its docstring.
"""

from __future__ import annotations

import logging

import pytest

from common.frontmatter import parse_frontmatter
from common.models import BlockedReason
from tests.loop_harness import (
    ENTITY_REF,
    ENTITY_NAME,
    SENTENCE,
    URLS,
    analyst_args,
    claim_spec,
    fake_execute_searches,
    loop_config,
    scorer_args,
    scripted_agents,
    write_entity,
)


async def _run(tmp_path, **spec_kwargs):
    import loop

    return await loop.run(claim_spec(tmp_path, **spec_kwargs), loop_config(tmp_path))


async def loop_run(tmp_path, *, spec_kwargs: dict | None = None, **config_overrides):
    """``loop.run`` on the harness entity with config overrides."""
    import loop

    return await loop.run(
        claim_spec(tmp_path, **(spec_kwargs or {})), loop_config(tmp_path, **config_overrides)
    )


# --- Researcher outcomes (test_researcher_decomposed.py:308, test_orchestrator.py:396) ---


@pytest.mark.asyncio
async def test_scorer_dropping_every_candidate_blocks_the_claim(tmp_path) -> None:
    """From test_researcher_decomposed.py ``test_scorer_drops_all_sets_blocked_reason``."""
    write_entity(tmp_path)
    with scripted_agents(scorer=scorer_args(kept=False)):
        result = await _run(tmp_path)

    assert result.blocked_reason == BlockedReason.INSUFFICIENT_SOURCES
    assert result.urls_found == []
    assert result.analyst_output is None
    assert any("no relevant URLs" in e for e in result.errors)


@pytest.mark.asyncio
async def test_fewer_than_four_usable_sources_halts_before_the_analyst(tmp_path) -> None:
    """From test_orchestrator.py ``TestThresholdEnforcement.test_verify_claim_halts_when_one_source_ingested``."""
    write_entity(tmp_path)
    three = URLS[:3]
    with scripted_agents(scorer=scorer_args(three), search=fake_execute_searches(three)):
        result = await _run(tmp_path)

    assert result.blocked_reason == BlockedReason.INSUFFICIENT_SOURCES
    assert len(result.sources) == 3
    assert result.analyst_output is None
    assert result.consistency is None


@pytest.mark.asyncio
async def test_four_usable_sources_reach_the_analyst(tmp_path) -> None:
    """Positive control for the threshold case above: four ingested sources pass the gate."""
    write_entity(tmp_path)
    with scripted_agents():
        result = await _run(tmp_path)

    assert result.blocked_reason is None
    assert len(result.sources) == 4
    assert result.analyst_output is not None


# --- Sub-question coverage (test_orchestrator.py:1199, RE-AF) ---


@pytest.mark.asyncio
async def test_uncovered_sub_question_is_a_warning_not_an_error(tmp_path, caplog) -> None:
    """From test_orchestrator.py ``TestUncoveredSubQuestionWarning``."""
    write_entity(tmp_path)
    only_sq1 = {
        "kept": [{"url": u, "addresses": ["sq1"], "score": 4.0} for u in URLS],
        "dropped": [], "rationale": "sq1 only",
    }
    with caplog.at_level(logging.WARNING), scripted_agents(scorer=only_sq1):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert result.sub_question_coverage["sq2"] == []
    assert len(result.sub_question_coverage["sq1"]) == 4
    assert any("sq2" in r.getMessage() and "no ingested source" in r.getMessage() for r in caplog.records)
    assert not any("sq2" in e for e in result.errors)


# --- Cited source filter and the writer's persist_sources (test_orchestrator.py:1243, 1414; RE-AF) ---


@pytest.mark.asyncio
async def test_uncited_sources_are_left_off_and_never_written(tmp_path) -> None:
    """From ``TestCitedSourceFilter.test_research_claim_lists_only_cited_sources`` and
    ``TestPersistSourcesSkipsUncited``: the writer's ``persist_sources`` writes the cited
    files only and returns their ids in the researcher's URL order."""
    from orchestrator.persistence import persist_sources

    write_entity(tmp_path)
    cited = ["2026/second-report", "2026/report"]
    with scripted_agents(analyst=analyst_args(cited_sources=cited, level="partially-verified")):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert result.uncited_urls == {URLS[2], URLS[3]}
    url_index: dict[str, str] = {}
    ids = persist_sources(result, tmp_path, url_index)
    assert ids == ["2026/report", "2026/second-report"]
    written = sorted(p.stem for p in (tmp_path / "research" / "sources" / "2026").glob("*.md"))
    assert written == ["report", "second-report"]
    assert set(url_index.values()) == {"2026/report", "2026/second-report"}


@pytest.mark.asyncio
async def test_nothing_cited_keeps_every_source(tmp_path) -> None:
    """From ``TestCitedSourceFilter.test_nothing_cited_keeps_every_source``."""
    write_entity(tmp_path)
    with scripted_agents(analyst=analyst_args(cited_sources=[])):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert result.uncited_urls == set()


# --- The Evaluator grades the statement, whatever the analyst titles (RE-AD, one rule) ---


@pytest.mark.asyncio
async def test_the_evaluator_grades_the_statement_not_the_analysts_title(tmp_path) -> None:
    """From ``TestAuditorGradedStatement.test_verify_claim_grades_the_resolved_title``,
    rewritten to the one rule: a criterion-backed run grades ``spec.statement``."""
    from tests.loop_harness import auditor_args, capturing_model

    write_entity(tmp_path)
    prompts: list[str] = []
    with scripted_agents(
        analyst=analyst_args(title=f"{ENTITY_NAME} uses renewable energy"),
        auditor_model=capturing_model(prompts, auditor_args()),
    ):
        result = await _run(
            tmp_path, criteria_slug="uses-renewable-energy", grading_rule="mixed = offsets only",
        )

    assert result.consistency is not None, result.errors
    assert any(f"## Claim\n{SENTENCE}\n" in p for p in prompts)
    assert not any(f"## Claim\n{ENTITY_NAME} uses renewable energy" in p for p in prompts)


# --- URL dedup: cache hits (test_source_url_dedup.py:342-400) ---


@pytest.mark.asyncio
async def test_cache_hits_land_on_cached_sources(tmp_path) -> None:
    """From ``TestVerifyClaimSurfacesCachedSources``: a URL already on disk is reused, not fetched."""
    write_entity(tmp_path)
    stored = tmp_path / "research" / "sources" / "2026" / "report.md"
    stored.parent.mkdir(parents=True)
    stored.write_text(
        f"---\nurl: {URLS[0]}\ntitle: Stored report\npublisher: Example Publisher\n"
        "accessed_date: 2026-01-01\nkind: article\nindependence: independent\n"
        "summary: Stored.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    with scripted_agents():
        result = await _run(tmp_path)

    assert result.cached_source_ids == ["2026/report"]
    # Ingest runs two at a time, so fresh sources finish in no fixed order.
    assert {url for url, _sf in result.source_files} == set(URLS[1:])
    assert set(result.urls_ingested) == set(URLS)
    assert {sd["source_id"] for sd in result.sources} == {
        "2026/report", "2026/second-report", "2026/third-report", "2026/fourth-report",
    }


# --- Declared fields (plan § SP1: _code_relabel and _cap_rationale_fitted become declared) ---


def test_relabel_and_fit_markers_are_declared_excluded_fields() -> None:
    from analyst.agent import SourceOverride, VerdictAssessment

    assert SourceOverride.model_fields["code_relabel"].exclude is True
    assert VerdictAssessment.model_fields["cap_rationale_fitted"].exclude is True
    override = SourceOverride(source="2026/x", independence="unknown", reason="r")
    assert override.code_relabel is False
    assert "code_relabel" not in override.model_dump()


# --- Ingest order by sub-question coverage (test_ingest_urls.py:148-229; RE-AF) ---

_COVER_URLS = [f"https://example.org/cover-{c}" for c in "abcdef"]
_COVER_ADDRESSES = {
    _COVER_URLS[0]: ["sq1"], _COVER_URLS[1]: ["sq1"], _COVER_URLS[2]: ["sq1"],
    _COVER_URLS[3]: ["sq1"], _COVER_URLS[4]: ["sq2"], _COVER_URLS[5]: ["sq2"],
}
_COVER_TEXT = {u: f"Page {u}. Probe Subject data centers used power." for u in _COVER_URLS}


def _store_source(repo_root, url: str, slug: str) -> None:
    path = repo_root / "research" / "sources" / "2026" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nurl: {url}\ntitle: Stored {slug}\npublisher: Example Publisher\n"
        "accessed_date: 2026-01-01\nkind: article\nindependence: independent\n"
        "summary: Stored.\n---\n\nBody.\n",
        encoding="utf-8",
    )


def _coverage_case(tmp_path):
    """Two cached sq1 sources, two fresh slots; sq2's only URLs rank last."""
    write_entity(tmp_path)
    _store_source(tmp_path, _COVER_URLS[0], "cover-a")
    _store_source(tmp_path, _COVER_URLS[1], "cover-b")
    scorer = {
        "kept": [{"url": u, "addresses": _COVER_ADDRESSES[u], "score": 4.0} for u in _COVER_URLS],
        "dropped": [], "rationale": "ranked",
    }
    return scorer, fake_execute_searches(_COVER_URLS, _COVER_TEXT)


def _recording_ingest_model(first_calls: list[str], *, fail: set[str] = frozenset()):
    """The harness ingest model, recording each URL's first request; a URL in
    ``fail`` returns a source without fetching, which ingest rejects."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    from tests.loop_harness import ingest_model

    inner = ingest_model()

    async def _fn(messages, info):
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        prompt = next(p.content for p in parts if isinstance(p, UserPromptPart))
        url = prompt.split("URL: ", 1)[1].split("\n", 1)[0]
        if not any(isinstance(p, ToolCallPart) for p in parts):
            first_calls.append(url)
            if url in fail:
                source = {"frontmatter": {
                    "url": url, "title": "Unfetched", "publisher": "Example Publisher",
                    "accessed_date": "2026-10-14", "kind": "article", "summary": "Invented.",
                }, "body": "Body.", "slug": "page", "year": 2026}
                return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])
        return await inner.function(messages, info)

    return FunctionModel(_fn)


@pytest.mark.asyncio
async def test_thinnest_sub_question_is_ingested_first_and_cache_hits_count(tmp_path) -> None:
    """From test_ingest_urls.py ``test_ingest_claim_sources_prefers_thin_sub_question`` and
    the ``_order_by_coverage`` cases: cached sources cover sq1, so sq2's URLs, ranked
    last by the scorer, fill the fresh slots first."""
    scorer, search = _coverage_case(tmp_path)
    first_calls: list[str] = []
    with scripted_agents(scorer=scorer, search=search, ingestor=_recording_ingest_model(first_calls)):
        result = await loop_run(tmp_path, max_sources=4)

    assert result.cached_source_ids == ["2026/cover-a", "2026/cover-b"]
    assert set(first_calls[:2]) == {_COVER_URLS[4], _COVER_URLS[5]}
    assert {url for url, _sf in result.source_files} == {_COVER_URLS[4], _COVER_URLS[5]}
    assert sorted(result.sub_question_coverage["sq2"]) == ["2026/cover-e", "2026/cover-f"]


@pytest.mark.asyncio
async def test_second_thin_url_is_tried_early_when_the_first_fails(tmp_path) -> None:
    """From test_ingest_urls.py ``test_ingest_claim_sources_tries_second_thin_url_when_first_fails``."""
    scorer, search = _coverage_case(tmp_path)
    first_calls: list[str] = []
    model = _recording_ingest_model(first_calls, fail={_COVER_URLS[4]})
    with scripted_agents(scorer=scorer, search=search, ingestor=model):
        result = await loop_run(tmp_path, max_sources=4)

    assert set(first_calls[:2]) == {_COVER_URLS[4], _COVER_URLS[5]}
    fresh = {url for url, _sf in result.source_files}
    assert _COVER_URLS[5] in fresh
    assert _COVER_URLS[4] not in fresh


# The four cases below pin the rest of the ``_order_by_coverage`` rules
# (test_ingest_urls.py:148-175). ``llm_concurrency=1`` runs one Ingestor model
# call at a time, in dispatch order, so ``first_calls`` is the ingest order.
# Four URLs and ``max_sources=4`` ingest every URL, so the whole order shows.

_ORDER_URLS = {c: f"https://example.org/order-{c}" for c in "abcd"}
_ORDER_TEXT = {u: f"Page {u}. Probe Subject data centers used power." for u in _ORDER_URLS.values()}


def _order_planner(sub_question_ids: list[str]) -> dict:
    return {
        "sub_questions": [
            {"id": sq, "question": f"Question {sq}?", "rationale": "axis"} for sq in sub_question_ids
        ],
        "queries": [{"text": f"query {sq}", "sub_question_id": sq} for sq in sub_question_ids],
        "rationale": "axes",
    }


def _order_scorer(addresses: dict[str, list[str]]) -> dict:
    """Kept entries in the order given, at equal scores, so scorer order is input order."""
    return {
        "kept": [{"url": _ORDER_URLS[k], "addresses": v, "score": 4.0} for k, v in addresses.items()],
        "dropped": [], "rationale": "ranked",
    }


async def _ingest_order(tmp_path, addresses: dict[str, list[str]], sub_question_ids: list[str]) -> list[str]:
    write_entity(tmp_path)
    first_calls: list[str] = []
    urls = [_ORDER_URLS[k] for k in addresses]
    with scripted_agents(
        planner=_order_planner(sub_question_ids),
        scorer=_order_scorer(addresses),
        search=fake_execute_searches(urls, _ORDER_TEXT),
        ingestor=_recording_ingest_model(first_calls),
    ):
        result = await loop_run(tmp_path, max_sources=4, llm_concurrency=1)
    assert {url for url, _sf in result.source_files} == set(urls)
    by_url = {u: k for k, u in _ORDER_URLS.items()}
    return [by_url[u] for u in first_calls]


@pytest.mark.asyncio
async def test_ingest_order_ties_go_by_sub_question_order(tmp_path) -> None:
    """From test_ingest_urls.py ``test_order_by_coverage_ties_go_by_sub_question_order``:
    sq1 and sq2 both start at zero, so sq1's first URL leads although the scorer
    ranked sq2's URLs first; the two then alternate."""
    order = await _ingest_order(
        tmp_path, {"a": ["sq2"], "b": ["sq2"], "c": ["sq1"], "d": ["sq1"]}, ["sq1", "sq2"],
    )
    assert order == ["c", "a", "d", "b"]


@pytest.mark.asyncio
async def test_ingest_order_counts_a_multi_sub_question_url_for_each(tmp_path) -> None:
    """From test_ingest_urls.py ``test_order_by_coverage_multi_sub_question_url_counts_for_each``:
    "a" covers sq1 and sq2, so after it sq3 is the thinnest and its "c" comes
    before sq2's own URL "b"."""
    order = await _ingest_order(
        tmp_path, {"a": ["sq1", "sq2"], "b": ["sq2"], "c": ["sq3"], "d": ["sq1"]}, ["sq1", "sq2", "sq3"],
    )
    assert order == ["a", "c", "d", "b"]


@pytest.mark.asyncio
async def test_ingest_order_puts_unknown_and_empty_addresses_last(tmp_path) -> None:
    """From test_ingest_urls.py ``test_order_by_coverage_appends_unknown_ids_last`` and
    ``test_order_by_coverage_skips_sub_question_with_no_urls_left``: sq2 has no
    URL, so after "a" it is the thinnest but is skipped and sq1's "c" comes
    next; a URL that addresses an unknown sub-question id or none follows, in
    scorer order."""
    order = await _ingest_order(
        tmp_path, {"a": ["sq1"], "b": ["sq9"], "c": ["sq1"], "d": []}, ["sq1", "sq2"],
    )
    assert order == ["a", "c", "b", "d"]


@pytest.mark.asyncio
async def test_ingest_order_without_sub_questions_keeps_research_order(tmp_path) -> None:
    """From test_ingest_urls.py ``test_order_by_coverage_without_sub_questions_keeps_input_order``.

    The planner cannot return fewer than two sub-questions (``ResearchPlan``
    validation), so the research step is replaced through its public name to
    hand the loop URLs with no sub-questions. "a" addresses sq1 and would lead
    if sq1 were a known sub-question."""
    from unittest.mock import patch

    from researcher.decomposed import ResearchOutput

    write_entity(tmp_path)
    keys = ["b", "c", "d", "a"]
    urls = [_ORDER_URLS[k] for k in keys]
    research = ResearchOutput(
        urls=urls,
        url_addresses={_ORDER_URLS["a"]: ["sq1"], **{_ORDER_URLS[k]: [] for k in "bcd"}},
        sub_questions=[],
        trace={"mode": "decomposed", "acquisition": {}, "tool_outcomes": []},
        prefetched_bodies={u: _ORDER_TEXT[u] for u in urls},
    )

    async def _research(*_args, **_kwargs):
        return research.model_copy(deep=True)

    first_calls: list[str] = []
    with (
        scripted_agents(ingestor=_recording_ingest_model(first_calls)),
        patch("researcher.decomposed.decomposed_research", side_effect=_research),
    ):
        result = await loop_run(tmp_path, max_sources=4, llm_concurrency=1)

    assert {url for url, _sf in result.source_files} == set(urls)
    assert first_calls == urls


# --- URL dedup through the loop (test_source_url_dedup.py:140-250, 273-400, 533-705) ---


@pytest.mark.asyncio
async def test_a_variant_of_a_stored_url_reuses_the_stored_source(tmp_path) -> None:
    """From ``TestApplyUrlDedup.test_apply_url_dedup_matches_canonical_form`` and
    ``test_invert_addresses_uses_source_addresses_over_disk_url``: www., a trailing
    slash and tracking params still hit the file, and coverage comes from the
    researcher's URL, not the URL on disk."""
    write_entity(tmp_path)
    variant = "https://www.example.net/a/?utm_source=y"
    _store_source(tmp_path, "https://example.net/a", "a")
    scorer = {"kept": [{"url": variant, "addresses": ["sq2"], "score": 4.0}], "dropped": [], "rationale": "r"}
    with scripted_agents(scorer=scorer, search=fake_execute_searches([variant], {variant: "text"})):
        result = await _run(tmp_path)

    assert result.cached_source_ids == ["2026/a"]
    assert result.source_files == []
    assert result.sub_question_coverage["sq2"] == ["2026/a"]


@pytest.mark.asyncio
async def test_any_form_of_an_arxiv_paper_reuses_the_committed_source(tmp_path) -> None:
    """From ``TestApplyUrlDedup.test_apply_url_dedup_matches_any_form_of_an_arxiv_paper``."""
    from pathlib import Path

    write_entity(tmp_path)
    committed = Path(__file__).resolve().parents[2] / "research" / "sources" / "2025" / "250212447v1.md"
    dest = tmp_path / "research" / "sources" / "2025" / "250212447v1.md"
    dest.parent.mkdir(parents=True)
    dest.write_text(committed.read_text(encoding="utf-8"), encoding="utf-8")
    abs_url = "http://arxiv.org/abs/2502.12447v1"
    scorer = {"kept": [{"url": abs_url, "addresses": ["sq1"], "score": 4.0}], "dropped": [], "rationale": "r"}
    with scripted_agents(scorer=scorer, search=fake_execute_searches([abs_url], {abs_url: "text"})):
        result = await _run(tmp_path)

    assert result.cached_source_ids == ["2025/250212447v1"]
    assert result.source_files == []


@pytest.mark.asyncio
async def test_every_url_cached_runs_no_ingest(tmp_path) -> None:
    """From ``TestTargetCap.test_dedup_skips_ingest_when_all_cached`` and
    ``TestVerifyClaimSurfacesCachedSources``: the sidecar's ``sources_consulted``
    lists the cache hits."""
    from pydantic_ai.models.function import FunctionModel

    write_entity(tmp_path)
    for i, url in enumerate(URLS):
        _store_source(tmp_path, url, f"cached-{i}")

    async def _no_ingest(messages, info):
        raise AssertionError("ingest must not run when every URL is cached")

    with scripted_agents(ingestor=FunctionModel(_no_ingest)):
        result = await _run(tmp_path)

    assert result.source_files == []
    assert result.cached_source_ids == [f"2026/cached-{i}" for i in range(4)]
    consulted = result.sources_consulted()
    assert [e["id"] for e in consulted] == [f"2026/cached-{i}" for i in range(4)]
    assert all(e["ingested"] is True for e in consulted)
    assert result.analyst_output is not None, result.errors


_OLD = "https://example.org/old"
_NEW = "https://example.org/new"
_PAGE = "<html><head><title>New</title></head><body><p>The stored page.</p></body></html>"


def _mock_redirect(mock) -> None:
    import httpx

    mock.get(_OLD).mock(return_value=httpx.Response(301, headers={"Location": "/new"}))
    mock.get(_NEW).mock(return_value=httpx.Response(200, html=_PAGE))


def _sources_on_disk(root) -> list[str]:
    return sorted(
        str(p.relative_to(root / "research" / "sources"))
        for p in (root / "research" / "sources").glob("*/*.md")
    )


def _live_fetch_search(urls: list[str]):
    """Search results without page text, so ingest fetches each page (served by respx)."""
    return fake_execute_searches(urls, {})


@pytest.mark.asyncio
async def test_a_fetch_that_redirects_to_a_stored_page_reuses_it(tmp_path) -> None:
    """From ``TestRedirectToStoredSource.test_verify_claim_reuses_the_stored_redirect_target``."""
    import respx

    from orchestrator.persistence import persist_sources

    write_entity(tmp_path)
    _store_source(tmp_path, _NEW, "new")
    scorer = {"kept": [{"url": _OLD, "addresses": ["sq1"], "score": 4.0}], "dropped": [], "rationale": "r"}
    with scripted_agents(scorer=scorer, search=_live_fetch_search([_OLD])), respx.mock as mock:
        _mock_redirect(mock)
        result = await _run(tmp_path)

    assert result.cached_source_ids == ["2026/new"]
    assert result.source_files == []
    assert result.urls_failed == []
    assert result.sources[0]["addresses"] == ["sq1"]
    assert persist_sources(result, tmp_path) == ["2026/new"]
    assert _sources_on_disk(tmp_path) == ["2026/new.md"]


@pytest.mark.asyncio
async def test_a_url_that_does_not_redirect_still_writes_a_file(tmp_path) -> None:
    """From ``TestRedirectToStoredSource.test_a_url_that_does_not_redirect_still_writes_a_file``."""
    import httpx
    import respx

    from orchestrator.persistence import persist_sources

    write_entity(tmp_path)
    _store_source(tmp_path, _NEW, "new")
    other = "https://example.org/page"
    scorer = {"kept": [{"url": other, "addresses": ["sq1"], "score": 4.0}], "dropped": [], "rationale": "r"}
    with scripted_agents(scorer=scorer, search=_live_fetch_search([other])), respx.mock as mock:
        mock.get(other).mock(return_value=httpx.Response(200, html=_PAGE))
        result = await _run(tmp_path)

    assert result.cached_sources == []
    assert persist_sources(result, tmp_path) == ["2026/page"]
    assert _sources_on_disk(tmp_path) == ["2026/new.md", "2026/page.md"]


@pytest.mark.asyncio
async def test_a_redirect_to_a_cached_source_does_not_count_toward_the_target(tmp_path) -> None:
    """From ``TestRedirectToACachedSourceDoesNotCount.test_claim_reaches_its_target``: the
    redirect is an alias of the cached source, and the claim still fills its slot."""
    import asyncio

    import httpx
    import respx

    write_entity(tmp_path)
    _store_source(tmp_path, _NEW, "new")
    other = "https://example.org/page"
    scorer = {"kept": [
        {"url": _NEW, "addresses": ["sq1"], "score": 4.0},
        {"url": _OLD, "addresses": ["sq2"], "score": 4.0},
        {"url": other, "addresses": ["sq1"], "score": 4.0},
    ], "dropped": [], "rationale": "r"}

    async def _slow_page(request):
        # Lets the redirect finish first, so it is the one that would count.
        await asyncio.sleep(0.05)
        return httpx.Response(200, html=_PAGE)

    with scripted_agents(scorer=scorer, search=_live_fetch_search([_NEW, _OLD, other])), respx.mock as mock:
        _mock_redirect(mock)
        mock.get(other).mock(side_effect=_slow_page)
        result = await loop_run(tmp_path, max_sources=2)

    assert result.cached_source_ids == ["2026/new"]
    assert [u for u, _sf in result.source_files] == [other]
    assert result.urls_failed == []
    assert result.sources[0]["addresses"] == ["sq1", "sq2"]
    assert result.url_aliases == {_OLD: _NEW}


# --- Archive lookup after ingest (test_archive_after_ingest.py:116-186, 218-310; RE-AI) ---
#
# The ingest model is the conftest stub (it fetches the page, served by respx);
# archive.org is mocked with respx, so these cases make no network call.

import datetime as _dt  # noqa: E402
import re as _re  # noqa: E402


def _ts(days_ago: float) -> str:
    when = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days_ago)
    return when.strftime("%Y%m%d%H%M%S")


_ARCH_PAGE_URL = "https://example.org/page"
_ARCH_PAGE = "<html><head><title>Page</title></head><body><p>The stored page.</p></body></html>"
# A recent capture, so the freshness refresh after a live fetch leaves it alone.
_SNAPSHOT = f"https://web.archive.org/web/{_ts(1)}/https://example.org/page"
_TIMEGATE = _re.compile(r"https://web\.archive\.org/web/\d{14}/.+")
_SAVE = _re.compile(r"https://web\.archive\.org/save/.+")
_ARCH_CACHED = [f"https://example.com/cached-{i}" for i in range(3)]


@pytest.fixture
def archive_case(tmp_path, monkeypatch):
    """Three cached sources and one page fetched live; archive.org waits are skipped."""

    async def _no_wait(seconds: float) -> None:
        return None

    monkeypatch.setattr("ingestor.tools.wayback._wait", _no_wait)
    write_entity(tmp_path)
    for i, url in enumerate(_ARCH_CACHED):
        _store_source(tmp_path, url, f"cached-{i}")
    return tmp_path


async def _archive_run(tmp_path, **config_overrides):
    """``loop.run`` over the cached sources and the live page; return the result."""
    urls = [*_ARCH_CACHED, _ARCH_PAGE_URL]
    with scripted_agents(scorer=scorer_args(urls), search=fake_execute_searches(urls, {})):
        return await loop_run(tmp_path, max_sources=8, **config_overrides)


async def _archive_write(tmp_path, **config_overrides) -> tuple[dict, dict]:
    """Run the loop and the writer; return the fresh source's frontmatter and the sidecar."""
    import yaml

    from common.sidecar import sidecar_path_for
    from common.utils import slugify
    from orchestrator.persistence import write_claim_run

    import loop

    urls = [*_ARCH_CACHED, _ARCH_PAGE_URL]
    spec = claim_spec(tmp_path)
    cfg = loop_config(tmp_path, max_sources=8, **config_overrides)
    with scripted_agents(scorer=scorer_args(urls), search=fake_execute_searches(urls, {})):
        result = await loop.run(spec, cfg)
    assert result.analyst_output is not None, result.errors
    claim_path = write_claim_run(
        result, spec, cfg, repo_root=tmp_path, claim_slug=slugify(result.analyst_output.verdict.title),
    )
    source_fm, _ = parse_frontmatter(
        (tmp_path / "research" / "sources" / "2026" / "page.md").read_text(encoding="utf-8")
    )
    sidecar = yaml.safe_load(sidecar_path_for(claim_path).read_text(encoding="utf-8"))
    return source_fm, sidecar


def _entries(sidecar: dict) -> dict[str, dict]:
    return {e["id"]: e for e in sidecar["sources_consulted"]}


@pytest.mark.asyncio
async def test_snapshot_found_sets_archived_url_and_records_found(
    archive_case, stub_ingest_model, mock_capture_replay
) -> None:
    """From test_archive_after_ingest.py ``test_snapshot_found_sets_archived_url_and_records_found``."""
    import httpx
    import respx

    with respx.mock as mock:
        mock_capture_replay()
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        mock.get(_TIMEGATE).mock(return_value=httpx.Response(302, headers={"location": _SNAPSHOT}))
        source_fm, sidecar = await _archive_write(archive_case, skip_wayback=False)

    assert source_fm["archived_url"] == _SNAPSHOT
    entries = _entries(sidecar)
    assert entries["2026/page"]["archive"] == {"status": "found"}
    # A lookup in code is not a recovery of a lost page.
    assert "acquisition" not in entries["2026/page"]
    # Dedup hits were not looked up.
    for i in range(3):
        assert "archive" not in entries[f"2026/cached-{i}"]


@pytest.mark.asyncio
async def test_rate_limited_lookup_records_failed_and_clears_model_link(
    archive_case, stub_ingest_model
) -> None:
    """From ``test_rate_limited_lookup_records_failed_and_clears_model_link``."""
    import httpx
    import respx

    stub_ingest_model["archived_url"] = "https://web.archive.org/web/2020/https://example.org/page"
    with respx.mock as mock:
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(429))
        save = mock.get(_SAVE).mock(return_value=httpx.Response(200))
        source_fm, sidecar = await _archive_write(archive_case, skip_wayback=False)

    assert "archived_url" not in source_fm
    archive = _entries(sidecar)["2026/page"]["archive"]
    assert archive["status"] == "failed"
    assert "429" in archive["error"]
    assert timegate.call_count == 2
    assert save.called is False


@pytest.mark.asyncio
async def test_skip_wayback_records_not_attempted(archive_case, stub_ingest_model) -> None:
    """From ``test_skip_wayback_records_not_attempted``."""
    import httpx
    import respx

    with respx.mock as mock:
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(404))
        _source_fm, sidecar = await _archive_write(archive_case, skip_wayback=True)

    assert _entries(sidecar)["2026/page"]["archive"] == {"status": "not-attempted"}
    assert timegate.called is False


@pytest.mark.asyncio
async def test_lookup_time_limit_records_failed(archive_case, stub_ingest_model, monkeypatch) -> None:
    """From ``test_lookup_time_limit_records_failed``."""
    import asyncio

    import httpx
    import respx

    async def _slow(request):
        await asyncio.sleep(1)
        return httpx.Response(404)

    monkeypatch.setattr("ingestor.tools.wayback.archive_lookup_budget_s", lambda: 0.01)
    with respx.mock as mock:
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        mock.get(_TIMEGATE).mock(side_effect=_slow)
        source_fm, sidecar = await _archive_write(archive_case, skip_wayback=False)

    assert "archived_url" not in source_fm
    archive = _entries(sidecar)["2026/page"]["archive"]
    assert archive["status"] == "failed"
    assert "timed out" in archive["error"]


@pytest.mark.asyncio
async def test_no_capture_when_saves_are_off(archive_case, stub_ingest_model_calling_wayback) -> None:
    """From ``test_no_capture_when_saves_are_off``: ``allow_save=False`` (``dr draft
    --dry-run``) keeps both the model's tool and the lookup in code to TimeGate."""
    import httpx
    import respx

    with respx.mock as mock:
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(404))
        save = mock.get(_SAVE).mock(return_value=httpx.Response(302, headers={"location": _SNAPSHOT}))
        result = await _archive_run(archive_case, skip_wayback=False, allow_save=False)

    assert [url for url, _sf in result.source_files] == [_ARCH_PAGE_URL]
    assert timegate.call_count == 2
    assert save.called is False
    assert result.archive[_ARCH_PAGE_URL]["status"] == "failed"


@pytest.mark.asyncio
async def test_an_unexpected_lookup_error_keeps_the_source(
    archive_case, stub_ingest_model, monkeypatch
) -> None:
    """From ``test_an_unexpected_lookup_error_keeps_the_source``: an error the wayback
    helpers do not catch (httpx.InvalidURL) must not drop a good ingest."""
    import httpx
    import respx

    async def _raise(client, url, *, allow_save=True, **kwargs):
        raise httpx.InvalidURL("Invalid non-printable ASCII character in URL")

    monkeypatch.setattr("ingestor.agent.archive_with_time_limit", _raise)
    stub_ingest_model["archived_url"] = _SNAPSHOT
    with respx.mock as mock:
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        result = await _archive_run(archive_case, skip_wayback=False)

    assert [url for url, _sf in result.source_files] == [_ARCH_PAGE_URL]
    assert result.source_files[0][1].frontmatter.archived_url is None
    archive = result.archive[_ARCH_PAGE_URL]
    assert archive["status"] == "failed"
    assert "InvalidURL" in archive["error"]


@pytest.mark.asyncio
async def test_a_model_written_non_archive_link_does_not_reject_the_ingest(
    archive_case, stub_ingest_model, mock_capture_replay
) -> None:
    """From ``test_a_model_written_non_archive_link_does_not_reject_the_ingest``."""
    import httpx
    import respx

    stub_ingest_model["archived_url"] = "https://archive.ph/abc123"
    with respx.mock as mock:
        mock_capture_replay()
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        mock.get(_TIMEGATE).mock(return_value=httpx.Response(302, headers={"location": _SNAPSHOT}))
        source_fm, sidecar = await _archive_write(archive_case, skip_wayback=False)

    assert source_fm["archived_url"] == _SNAPSHOT
    assert _entries(sidecar)["2026/page"]["archive"] == {"status": "found"}


@pytest.mark.asyncio
async def test_skip_wayback_drops_a_model_written_link(archive_case, stub_ingest_model) -> None:
    """From ``test_skip_wayback_drops_a_model_written_link``."""
    import httpx
    import respx

    stub_ingest_model["archived_url"] = _SNAPSHOT
    with respx.mock as mock:
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        source_fm, _sidecar = await _archive_write(archive_case, skip_wayback=True)

    assert "archived_url" not in source_fm


@pytest.mark.asyncio
async def test_live_fetch_refreshes_a_stale_capture_the_model_found(
    archive_case, stub_ingest_model_calling_wayback, mock_capture_replay
) -> None:
    """From ``test_live_fetch_refreshes_a_stale_capture_the_model_found``: with the page
    live, the model's wayback_check link is not reused, and an old capture is refreshed."""
    import httpx
    import respx

    stale = f"https://web.archive.org/web/{_ts(120)}/https://example.org/page"
    fresh = f"https://web.archive.org/web/{_ts(0)}/https://example.org/page"
    with respx.mock as mock:
        mock_capture_replay()
        mock.get(_ARCH_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCH_PAGE))
        mock.get(_TIMEGATE).mock(return_value=httpx.Response(302, headers={"location": stale}))
        save = mock.get(_SAVE).mock(return_value=httpx.Response(302, headers={"location": fresh}))
        source_fm, sidecar = await _archive_write(archive_case, skip_wayback=False)

    assert source_fm["archived_url"] == fresh
    assert save.call_count == 1
    assert _entries(sidecar)["2026/page"]["archive"] == {"status": "found"}


# --- Entity match on the claim's pool (test_entity_independence.py:167-400, 556-604, 703-724; RE-AE) ---

_BRAVE_TRANSPARENCY = "https://brave.com/transparency/"
_BRAVE_FORUM = "https://community.brave.app/t/brave-sync-servers-location/631793"
_AWS_SUSTAIN = "https://aws.amazon.com/sustainability"
_GOOGLE_REPORTS = "https://sustainability.google/reports/"
_AWS_RENEWABLE = "https://aws.amazon.com/blogs/renewable"
_AWS_DOCS = "https://docs.aws.amazon.com/customers/brave"
_INFOMANIAK = "https://www.infomaniak.com/en/ecology"
_REVIEW = "https://www.example-news.com/brave-review"

# url -> (publisher, independence or None, body, summary, kind)
_BRAVE_DEFAULT_PAGES = {
    _BRAVE_FORUM: ("Brave Software", "independent", "Body.", "A page.", "article"),
    _AWS_SUSTAIN: ("AWS", None, "Body.", "A page.", "article"),
    _GOOGLE_REPORTS: ("Google", None, "Body.", "A page.", "article"),
    _AWS_RENEWABLE: ("AWS", "independent", "AWS hosts Brave Browser on renewable power.", "A page.", "article"),
}
_BRAVE_OFF_ENTITY_PAGES = {
    _GOOGLE_REPORTS: ("Google", "first-party", "Body.", "A page.", "article"),
    _AWS_SUSTAIN: ("AWS", "independent", "Body.", "A page.", "article"),
    _AWS_DOCS: ("Amazon Web Services", "first-party", "Brave Browser is an AWS customer.", "A page.", "documentation"),
    _REVIEW: ("Example News", "independent", "Body.", "A look at how Brave Browser powers its servers.", "article"),
    _INFOMANIAK: ("Infomaniak", "first-party", "Body.", "A page.", "article"),
}


def _brave_entity():
    from common.models import EntityType
    from orchestrator.entity_resolution import ResolvedEntity

    return ResolvedEntity(
        entity_ref="products/brave-browser",
        entity_name="Brave Browser",
        entity_type=EntityType.PRODUCT,
        entity_description="",
        website="https://brave.com",
        parent_company="companies/brave-software",
    )


def _brave_repo(repo_root) -> None:
    """The parent company file and a cached Brave transparency report labelled independent."""
    parent = repo_root / "research" / "entities" / "companies" / "brave-software.md"
    parent.parent.mkdir(parents=True, exist_ok=True)
    parent.write_text(
        "---\nname: Brave Software\ntype: company\n"
        "website: https://brave.com/about/#company-info\n---\n",
        encoding="utf-8",
    )
    path = repo_root / "research" / "sources" / "2025" / "transparency.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nurl: {_BRAVE_TRANSPARENCY}\ntitle: Brave transparency report\n"
        "publisher: Brave Software\naccessed_date: 2026-01-01\nkind: report\n"
        "independence: independent\nsummary: Brave publishes a transparency report.\n---\n\nBody.\n",
        encoding="utf-8",
    )


def _page_ingest_model(pages: dict):
    """An ingest model that fetches the URL, then returns that page's source."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    async def _fn(messages, info):
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        prompt = next(p.content for p in parts if isinstance(p, UserPromptPart))
        url = prompt.split("URL: ", 1)[1].split("\n", 1)[0]
        if not any(isinstance(p, ToolCallPart) for p in parts):
            return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})])
        publisher, independence, body, summary, kind = pages[url]
        fm = {"url": url, "title": f"{publisher} page", "publisher": publisher,
              "accessed_date": "2026-10-04", "kind": kind, "summary": summary}
        if independence:
            fm["independence"] = independence
        source = {"frontmatter": fm, "body": body, "slug": "page", "year": 2026}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])

    return FunctionModel(_fn)


def _brave_verdict(overrides: list[dict] | None = None, *, level: str = "claimed",
                   confidence: str = "low", cap_rationale: str | None = "Only Brave's own pages address the claim.") -> dict:
    out = {
        "title": "Brave hosts on renewable energy", "verdict": "unverified", "confidence": confidence,
        "narrative": "No third party links Brave to renewable hosting.", "topics": ["environmental-impact"],
        "verification_level": level, "seo_title": "Brave renewable hosting claim",
    }
    if cap_rationale is not None:
        out["cap_rationale"] = cap_rationale
    if overrides is not None:
        out["source_overrides"] = overrides
    return out


def _brave_agents(pages: dict, analyst: dict):
    urls = [_BRAVE_TRANSPARENCY, *pages]
    return scripted_agents(
        scorer=scorer_args(urls), search=fake_execute_searches(urls, {u: "Page text." for u in urls}),
        ingestor=_page_ingest_model(pages), analyst=analyst,
    )


async def _brave_run(tmp_path, claim: str, pages: dict, analyst: dict):
    import loop

    from loop import ClaimSpec

    _brave_repo(tmp_path)
    spec = ClaimSpec(statement=claim, entity=_brave_entity())
    with _brave_agents(pages, analyst):
        return await loop.run(spec, loop_config(tmp_path, max_sources=8))


@pytest.mark.asyncio
async def test_entity_sources_are_first_party_and_others_off_entity(tmp_path) -> None:
    """From test_entity_independence.py ``test_verify_claim_marks_entity_sources_first_party``."""
    from common.models import Independence

    result = await _brave_run(
        tmp_path, "Brave is hosted on renewable energy", _BRAVE_DEFAULT_PAGES, _brave_verdict(),
    )

    labels = {s["url"]: s["independence"] for s in result.sources}
    assert labels[_BRAVE_TRANSPARENCY] == "first-party"  # cached hit
    assert labels[_BRAVE_FORUM] == "first-party"  # model said independent
    assert labels[_AWS_SUSTAIN] == "unknown"  # says nothing about Brave
    assert labels[_GOOGLE_REPORTS] == "unknown"  # Google's own page, not Brave's
    assert labels[_AWS_RENEWABLE] == "independent"  # names Brave Browser

    by_source = {o.source: o for o in result.analyst_output.verdict.source_overrides}
    assert set(by_source) == {"2025/transparency", "2026/631793", "2026/sustainability", "2026/reports"}
    assert by_source["2025/transparency"].independence == Independence.FIRST_PARTY
    assert by_source["2026/631793"].independence == Independence.FIRST_PARTY
    assert "brave.com" in by_source["2025/transparency"].reason
    assert "Brave Software" in by_source["2026/631793"].reason
    for sid in ("2026/sustainability", "2026/reports"):
        assert by_source[sid].independence == Independence.UNKNOWN
        assert by_source[sid].reason.startswith("Off-entity")


@pytest.mark.asyncio
async def test_an_analyst_override_for_the_same_source_is_not_duplicated(tmp_path) -> None:
    """From ``test_verify_claim_does_not_duplicate_analyst_override``."""
    analyst_override = {"source": "2025/transparency", "independence": "first-party",
                        "reason": "Brave's own report."}
    result = await _brave_run(
        tmp_path, "Brave is hosted on renewable energy", _BRAVE_DEFAULT_PAGES,
        _brave_verdict([analyst_override]),
    )

    overrides = result.analyst_output.verdict.source_overrides
    assert sorted(o.source for o in overrides) == [
        "2025/transparency", "2026/631793", "2026/reports", "2026/sustainability",
    ]
    kept = next(o for o in overrides if o.source == "2025/transparency")
    assert kept.reason == "Brave's own report."


@pytest.mark.asyncio
async def test_off_entity_sources_are_unknown_unless_the_claim_names_them(tmp_path) -> None:
    """From ``test_verify_claim_marks_off_entity_sources_unknown``."""
    from common.models import Independence

    result = await _brave_run(
        tmp_path, "Brave is hosted on renewable energy by Infomaniak", _BRAVE_OFF_ENTITY_PAGES,
        _brave_verdict(),
    )

    labels = {s["url"]: s["independence"] for s in result.sources}
    assert labels[_GOOGLE_REPORTS] == "unknown"  # Google first-party, no Brave mention
    assert labels[_AWS_SUSTAIN] == "unknown"  # AWS independent, no Brave mention
    assert labels[_AWS_DOCS] == "unknown"  # another organization's own docs naming Brave
    assert labels[_REVIEW] == "independent"  # names Brave Browser
    assert labels[_INFOMANIAK] == "first-party"  # the claim names Infomaniak

    by_source = {o.source: o for o in result.analyst_output.verdict.source_overrides}
    for sid in ("2026/reports", "2026/sustainability", "2026/brave"):
        assert by_source[sid].independence == Independence.UNKNOWN
        assert by_source[sid].reason.startswith("Off-entity")
    assert "2026/brave-review" not in by_source
    assert "2026/ecology" not in by_source


@pytest.mark.asyncio
async def test_off_entity_override_beats_the_analysts_first_party(tmp_path) -> None:
    """From ``test_off_entity_override_beats_analyst_first_party``."""
    from common.models import Independence

    analyst_override = {"source": "2026/reports", "independence": "first-party",
                        "reason": "Google restates its own numbers."}
    result = await _brave_run(
        tmp_path, "Brave is hosted on renewable energy", _BRAVE_DEFAULT_PAGES,
        _brave_verdict([analyst_override]),
    )

    reports = [o for o in result.analyst_output.verdict.source_overrides if o.source == "2026/reports"]
    assert len(reports) == 1
    assert reports[0].independence == Independence.UNKNOWN
    assert reports[0].reason.startswith("Off-entity")


def _brave_entity_file(repo_root) -> str:
    path = repo_root / "research" / "entities" / "products" / "brave-browser.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nname: Brave Browser\ntype: product\nwebsite: https://brave.com\n"
        "parent_company: companies/brave-software\ndescription: A browser.\n---\n",
        encoding="utf-8",
    )
    return "products/brave-browser"


def test_draft_writes_the_entity_overrides_and_keeps_the_file_label(tmp_path) -> None:
    """From ``test_research_claim_writes_entity_overrides``: through ``dr draft``."""
    from click.testing import CliRunner

    from orchestrator.cli import main

    _brave_repo(tmp_path)
    ref = _brave_entity_file(tmp_path)
    with _brave_agents(_BRAVE_DEFAULT_PAGES, _brave_verdict()):
        result = CliRunner().invoke(main, [
            "--model", "test", "draft", "--entity", ref, "Brave is hosted on renewable energy",
            "--skip-wayback", "--repo-root", str(tmp_path),
        ])

    assert result.exit_code == 0, result.output
    claim_path = tmp_path / "research" / "claims" / "brave-browser" / "brave-is-hosted-on-renewable-energy.md"
    claim_fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    written = {o["source"]: o["independence"] for o in claim_fm["source_overrides"]}
    assert written == {
        "2025/transparency": "first-party",
        "2026/631793": "first-party",
        "2026/sustainability": "unknown",
        "2026/reports": "unknown",
    }
    # The source file keeps its entity-agnostic label.
    forum_fm, _ = parse_frontmatter(
        (tmp_path / "research" / "sources" / "2026" / "631793.md").read_text(encoding="utf-8")
    )
    assert forum_fm["independence"] == "independent"


def test_draft_writes_the_fitted_level_and_its_note(tmp_path) -> None:
    """From ``test_research_claim_writes_the_fitted_level``: through ``dr draft``."""
    import yaml
    from click.testing import CliRunner

    from orchestrator.cli import main

    _brave_repo(tmp_path)
    ref = _brave_entity_file(tmp_path)
    analyst = _brave_verdict(level="multiply-verified", confidence="medium", cap_rationale=None)
    with _brave_agents(_BRAVE_DEFAULT_PAGES, analyst):
        result = CliRunner().invoke(main, [
            "--model", "test", "draft", "--entity", ref, "Brave is hosted on renewable energy",
            "--skip-wayback", "--repo-root", str(tmp_path),
        ])

    assert result.exit_code == 0, result.output
    claim_path = tmp_path / "research" / "claims" / "brave-browser" / "brave-is-hosted-on-renewable-energy.md"
    claim_fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    # One written source (the AWS page naming Brave) is independent.
    assert claim_fm["verification_level"] == "independently-verified"
    assert claim_fm["confidence"] == "medium"
    sidecar = yaml.safe_load(claim_path.with_name(claim_path.stem + ".audit.yaml").read_text())
    assert "multiply-verified" in sidecar["pipeline_run"]["level_clamp"]


# --- From test_orchestrator.py, moved with the import re-pointed at the loop's public names ---


class TestVerificationResult:
    def test_construction(self) -> None:
        from loop import VerificationResult

        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=["https://example.com"],
            urls_ingested=["https://example.com"],
            urls_failed=[],
            sources=[],
        )
        assert result.entity == "TestCorp"
        assert result.analyst_output is None
        assert result.consistency is None


class TestVerificationResultCarriesSourceFiles:
    def test_defaults_empty_when_omitted(self) -> None:
        """Construction without source_files yields an empty list (backward compat)."""
        from loop import VerificationResult

        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=[],
            urls_ingested=[],
            urls_failed=[],
            sources=[],
        )
        assert result.source_files == []

    def test_round_trip_source_files(self) -> None:
        """A fabricated (url, SourceFile) tuple round-trips through the field."""
        import datetime

        from ingestor.models import SourceFile, SourceFrontmatter
        from loop import VerificationResult

        sf = SourceFile(
            frontmatter=SourceFrontmatter(
                url="https://example.com/report",
                title="Test Report",
                publisher="Example Publisher",
                accessed_date=datetime.date(2026, 4, 19),
                kind="article",
                summary="A concise test summary.",
            ),
            body="Body content.",
            slug="test-report",
            year=2026,
        )
        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=["https://example.com/report"],
            urls_ingested=["https://example.com/report"],
            urls_failed=[],
            sources=[],
            source_files=[("https://example.com/report", sf)],
        )
        assert len(result.source_files) == 1
        url, stored = result.source_files[0]
        assert url == "https://example.com/report"
        assert stored is sf
        assert stored.frontmatter.title == "Test Report"
        # exclude=True keeps source_files out of serialization
        dumped = result.model_dump()
        assert "source_files" not in dumped


class TestVerifyConfigPerAgentModels:
    def test_model_for_falls_back_to_base(self) -> None:
        from loop import VerifyConfig

        cfg = VerifyConfig(model="anthropic:claude")
        for agent in ("researcher", "analyst", "auditor", "ingestor"):
            assert cfg.model_for(agent) == "anthropic:claude"

    def test_model_for_per_agent_override_wins(self) -> None:
        from loop import VerifyConfig

        cfg = VerifyConfig(
            model="anthropic:claude",
            analyst_model="infomaniak:swiss-ai/Apertus-70B-Instruct-2509",
            auditor_model="infomaniak:mistral24b",
        )
        assert cfg.model_for("researcher") == "anthropic:claude"
        assert cfg.model_for("analyst") == "infomaniak:swiss-ai/Apertus-70B-Instruct-2509"
        assert cfg.model_for("auditor") == "infomaniak:mistral24b"
        assert cfg.model_for("ingestor") == "anthropic:claude"


class TestVerifyConfigResearchOrigins:
    """Cover the activation list added for source-pool-expansion-tier1.md."""

    def test_default_includes_tavily_and_arxiv(self) -> None:
        from loop import VerifyConfig

        cfg = VerifyConfig()
        assert cfg.research_origins == ["tavily", "arxiv"]

    def test_explicit_list_round_trips(self) -> None:
        from loop import VerifyConfig

        cfg = VerifyConfig(research_origins=["brave", "arxiv"])
        assert cfg.research_origins == ["brave", "arxiv"]

    def test_empty_list_is_valid(self) -> None:
        """No 'must include a backend' guard - empty list permitted for testing."""
        from loop import VerifyConfig

        cfg = VerifyConfig(research_origins=[])
        assert cfg.research_origins == []

    def test_default_is_not_shared_mutable(self) -> None:
        """field(default_factory=...) gives each instance its own list."""
        from loop import VerifyConfig

        cfg_a = VerifyConfig()
        cfg_b = VerifyConfig()
        assert cfg_a.research_origins is not cfg_b.research_origins
        cfg_a.research_origins.append("edgar")
        assert cfg_b.research_origins == ["tavily", "arxiv"]


class TestVerifyConfigTimeouts:
    def test_verify_config_defaults(self) -> None:
        """Default VerifyConfig exposes the four timeout knobs.

        Wayback is on by default, so ingest_timeout_s is auto-bumped to the
        wayback-inclusive budget; the other three default to 120s.
        """
        from loop import VerifyConfig

        cfg = VerifyConfig()
        assert cfg.skip_wayback is False
        assert cfg.ingest_timeout_s >= 85
        assert cfg.research_timeout_s == 120.0
        assert cfg.analyst_timeout_s == 120.0
        assert cfg.auditor_timeout_s == 120.0

    def test_verify_config_autobumps_ingest_when_wayback_enabled(self) -> None:
        """With skip_wayback=False and no explicit ingest_timeout_s, auto-bump to >=85s."""
        from loop import VerifyConfig

        cfg = VerifyConfig(skip_wayback=False)
        assert cfg.ingest_timeout_s >= 85

    def test_verify_config_explicit_ingest_timeout_wins(self) -> None:
        """Caller-supplied ingest_timeout_s overrides the skip_wayback auto-bump."""
        from loop import VerifyConfig

        cfg = VerifyConfig(skip_wayback=False, ingest_timeout_s=45.0)
        assert cfg.ingest_timeout_s == 45.0

    @pytest.mark.asyncio
    async def test_ingest_one_returns_step_error_on_agent_timeout(self) -> None:
        """With a tiny ingest_timeout_s and a slow agent, ``ingest_one`` returns a timeout StepError."""
        import asyncio
        import datetime
        from contextlib import nullcontext
        from unittest.mock import patch

        import httpx

        from ingestor.agent import ingestor_agent
        from loop import StepError, VerifyConfig, ingest_one

        url = "https://example.com/slow-agent"
        cfg = VerifyConfig(model="test", repo_root="/tmp", skip_wayback=True, ingest_timeout_s=0.05)

        async def _slow_run(*args, **kwargs):
            await asyncio.sleep(5.0)

        async with httpx.AsyncClient() as client:
            with (
                patch.object(ingestor_agent, "run", side_effect=_slow_run),
                patch.object(ingestor_agent, "override", side_effect=lambda **kw: nullcontext()),
            ):
                outcome = await ingest_one(client, url, cfg, datetime.date(2026, 4, 19), asyncio.Semaphore(8))

        assert isinstance(outcome, StepError)
        assert outcome.step == "ingest"
        assert outcome.error_type == "timeout"
        assert outcome.url == url


def test_persist_sources_leaves_uncited_cached_and_fresh_entries_out(tmp_path) -> None:
    """From ``TestPersistSourcesSkipsUncited``, through the writer's public ``persist_sources``."""
    import datetime

    from ingestor.models import SourceFile, SourceFrontmatter
    from loop import VerificationResult
    from orchestrator.persistence import persist_sources

    def _sf(key: str) -> SourceFile:
        return SourceFile(
            frontmatter=SourceFrontmatter(
                url=f"https://example.com/{key}", title=f"Title {key}", publisher="Pub",
                accessed_date=datetime.date(2026, 1, 1), kind="article", summary="Summary.",
            ),
            body="Body.", slug=key, year=2026,
        )

    result = VerificationResult(
        entity="Acme", claim_text="c", urls_found=[], urls_ingested=[], urls_failed=[], sources=[],
        cached_sources=[
            ("https://example.com/x", "2025/x", {"source_id": "2025/x"}),
            ("https://example.com/y", "2025/y", {"source_id": "2025/y"}),
        ],
        source_files=[("https://example.com/a", _sf("a")), ("https://example.com/b", _sf("b"))],
        uncited_urls={"https://example.com/y", "https://example.com/b"},
    )
    url_index: dict[str, str] = {}

    ids = persist_sources(result, tmp_path, url_index)

    assert ids == ["2025/x", "2026/a"]
    assert (tmp_path / "research" / "sources" / "2026" / "a.md").exists()
    assert not (tmp_path / "research" / "sources" / "2026" / "b.md").exists()
    assert set(url_index.values()) == {"2026/a"}


# --- Blocklist and the candidate pool (test_orchestrator.py:120-290; RE-AE, RE-AF) ---


def _write_blocklist(repo_root) -> None:
    research = repo_root / "research"
    research.mkdir(parents=True, exist_ok=True)
    (research / "blocklist.yaml").write_text(
        """
hosts:
  - host: linkedin.com
    reason: "403s on anonymous fetch"
""",
        encoding="utf-8",
    )


def _kept(urls: list[str], addresses: dict | None = None) -> dict:
    addresses = addresses or {}
    return {
        "kept": [{"url": u, "addresses": addresses.get(u, ["sq1"]), "score": 4.0} for u in urls],
        "dropped": [], "rationale": "r",
    }


async def _research_only(tmp_path, urls, *, bodies=None, addresses=None, entity=None, **config):
    """``loop.run`` for its research outcome; the pool cut and blocklist run before ingest."""
    import loop
    from loop import ClaimSpec

    text = bodies if bodies is not None else {u: "Page text." for u in urls}
    if entity is None:
        write_entity(tmp_path)
    spec = ClaimSpec(statement="A claim", entity=entity) if entity else claim_spec(tmp_path)
    with scripted_agents(scorer=_kept(urls, addresses), search=fake_execute_searches(urls, text)):
        return await loop.run(spec, loop_config(tmp_path, **config))


def _blocked_messages(result) -> list[str]:
    return [e for e in result.errors if e.startswith("Dropped by blocklist")]


@pytest.mark.asyncio
async def test_blocklist_drops_a_listed_host(tmp_path) -> None:
    """From ``TestResearchBlocklist.test_blocklist_drops_linkedin_url``."""
    _write_blocklist(tmp_path)
    kept = [f"https://example.com/{c}" for c in "bcde"]
    result = await _research_only(tmp_path, ["https://linkedin.com/a", *kept])

    assert result.urls_found == kept
    assert len(_blocked_messages(result)) == 1
    assert "linkedin.com" in _blocked_messages(result)[0]
    assert not any(e.startswith("All ") and "blocklist" in e for e in result.errors)


@pytest.mark.asyncio
async def test_every_url_blocked_reports_it_and_stops(tmp_path) -> None:
    """From ``TestResearchBlocklist.test_all_blocked_adds_summary_error``."""
    _write_blocklist(tmp_path)
    result = await _research_only(tmp_path, ["https://linkedin.com/a", "https://uk.linkedin.com/b"])

    assert result.urls_found == []
    assert result.errors[0] == "All 2 researcher URLs matched blocklist; returning empty."
    assert len(_blocked_messages(result)) == 2
    assert result.analyst_output is None


@pytest.mark.asyncio
async def test_no_blocklist_file_passes_every_url(tmp_path) -> None:
    """From ``TestResearchBlocklist.test_no_blocklist_file_passes_through``."""
    urls = ["https://linkedin.com/a", "https://example.com/b", "https://example.com/c", "https://example.com/d"]
    result = await _research_only(tmp_path, urls)

    assert result.urls_found == urls
    assert _blocked_messages(result) == []


@pytest.mark.asyncio
async def test_pool_cut_keeps_a_thin_sub_questions_low_ranked_urls(tmp_path) -> None:
    """From ``TestResearchBlocklist.test_pool_cut_keeps_a_thin_sub_questions_low_ranked_urls``:
    40 kept URLs, a pool of 32, and the only sq2 URLs ranked 33-40."""
    urls = [f"https://example.com/{i}" for i in range(1, 41)]
    addresses = {u: (["sq2"] if i >= 32 else ["sq1"]) for i, u in enumerate(urls)}
    result = await _research_only(tmp_path, urls, addresses=addresses, candidate_pool_size=32)

    assert len(result.urls_found) == 32
    assert [u for u in result.urls_found if u in urls[32:]] == urls[32:34]
    # Survivors keep their rank order.
    assert result.urls_found == [u for u in urls if u in set(result.urls_found)]


@pytest.mark.asyncio
async def test_pool_cut_keeps_a_high_ranked_url_that_addresses_no_sub_question(tmp_path) -> None:
    """From ``TestResearchBlocklist.test_pool_cut_keeps_a_high_ranked_url_that_addresses_no_sub_question``."""
    urls = [f"https://example.com/{i}" for i in range(1, 11)]
    addresses = {urls[0]: []} | {u: ["sq1"] for u in urls[1:8]} | {u: ["sq2"] for u in urls[8:]}
    result = await _research_only(tmp_path, urls, addresses=addresses, candidate_pool_size=5)

    assert result.urls_found == [urls[0], urls[1], urls[2], urls[8], urls[9]]


_OWN_POST = (
    "https://www.linkedin.com/posts/earthly-insight_responsibility-in-the-age-of-ai-turning-"
    "activity-7417951275817918464-H7h7"
)
_OTHER_POST = "https://www.linkedin.com/posts/earth-insight_other-activity-2"
_SITE = "https://earthlyinsight.com/about"


def _earthly_insight():
    from common.models import EntityType
    from orchestrator.entity_resolution import ResolvedEntity

    return ResolvedEntity(
        entity_ref="companies/earthly-insight", entity_name="Earthly Insight",
        entity_type=EntityType.COMPANY, entity_description="",
        website="https://earthlyinsight.com",
    )


async def _earthly_research(tmp_path, bodies: dict, **config):
    _write_blocklist(tmp_path)
    return await _research_only(
        tmp_path, [_SITE, _OWN_POST, _OTHER_POST], bodies={_SITE: "About us.", **bodies},
        entity=_earthly_insight(), **config,
    )


@pytest.mark.asyncio
async def test_the_entitys_own_post_with_page_text_passes_the_blocklist(tmp_path) -> None:
    """From ``TestBlocklistSparesEntityProfilePost.test_entity_post_with_page_text_passes_blocklist``."""
    result = await _earthly_research(
        tmp_path, {_OWN_POST: "We run on renewable power.", _OTHER_POST: "Other text."}
    )

    assert result.urls_found == [_SITE, _OWN_POST]
    assert len(_blocked_messages(result)) == 1
    spared = result.research_trace["blocklist_spared"]
    assert [s["url"] for s in spared] == [_OWN_POST]
    assert "linkedin.com" in spared[0]["reason"]


@pytest.mark.asyncio
async def test_a_spared_post_cut_by_the_pool_cap_is_not_listed(tmp_path) -> None:
    """From ``TestBlocklistSparesEntityProfilePost.test_spared_post_cut_by_the_pool_cap_is_not_listed``."""
    result = await _earthly_research(
        tmp_path, {_OWN_POST: "We run on renewable power."}, candidate_pool_size=1, max_sources=1,
    )

    assert result.urls_found == [_SITE]
    assert "blocklist_spared" not in result.research_trace


@pytest.mark.asyncio
@pytest.mark.parametrize("bodies", [{}, {_OWN_POST: "  \n"}], ids=["no-body", "blank-body"])
async def test_the_entitys_own_post_without_page_text_is_dropped(tmp_path, bodies) -> None:
    """From ``TestBlocklistSparesEntityProfilePost.test_entity_post_without_page_text_drops``."""
    result = await _earthly_research(tmp_path, bodies)

    assert result.urls_found == [_SITE]
    assert len(_blocked_messages(result)) == 2
    assert "blocklist_spared" not in result.research_trace


@pytest.mark.asyncio
async def test_a_third_party_post_with_page_text_is_dropped(tmp_path) -> None:
    """From ``TestBlocklistSparesEntityProfilePost.test_third_party_linkedin_post_with_page_text_drops``."""
    result = await _earthly_research(tmp_path, {_OTHER_POST: "Other text."})

    assert _OTHER_POST not in result.urls_found
    assert len(_blocked_messages(result)) == 2


# --- Threshold and terminal fetch (test_orchestrator.py:555); the review pin moved to test_tiebreaker.py ---


@pytest.mark.asyncio
async def test_every_fetch_refused_is_a_terminal_fetch_block(tmp_path) -> None:
    """From ``TestThresholdEnforcement.test_verify_claim_terminal_fetch_error_classified``:
    when every page answers 403, the block names the terminal fetch and counts the codes."""
    import httpx
    import respx

    write_entity(tmp_path)
    with scripted_agents(search=fake_execute_searches(URLS, {})), respx.mock as mock:
        for url in URLS:
            mock.get(url).mock(return_value=httpx.Response(403))
        result = await _run(tmp_path)

    assert result.blocked_reason == BlockedReason.TERMINAL_FETCH_ERROR
    assert result.errors[0] == "4 URLs (4× http_403)"
    assert result.analyst_output is None


# --- Statement the Evaluator grades without a template (test_orchestrator.py:1026; RE-AD) ---


@pytest.mark.asyncio
async def test_free_text_with_one_of_is_graded_as_the_operator_wrote_it(tmp_path) -> None:
    """From ``TestAuditorGradedStatement.test_free_text_with_one_of_keeps_the_operator_text``."""
    from tests.loop_harness import auditor_args, capturing_model

    write_entity(tmp_path)
    claim = "Probe Subject is one of (if not the) largest AI labs"
    prompts: list[str] = []
    with scripted_agents(
        analyst=analyst_args(title="Probe Subject ranks among the largest labs"),
        auditor_model=capturing_model(prompts, auditor_args()),
    ):
        result = await loop_run(tmp_path, spec_kwargs={"sentence": claim})

    assert result.consistency is not None, result.errors
    assert any(f"## Claim\n{claim}" in p for p in prompts)
    assert not any("ranks among the largest labs" in p.split("## Claim\n", 1)[1].split("\n", 1)[0] for p in prompts)


# --- The cited filter on real pools (test_orchestrator.py:1289-1382; RE-AF) ---


@pytest.mark.asyncio
async def test_a_code_entity_override_does_not_keep_an_uncited_source(tmp_path) -> None:
    """From ``TestCitedSourceFilter.test_code_entity_override_does_not_keep_an_uncited_source``."""
    from orchestrator.persistence import persist_sources

    analyst = _brave_verdict()
    analyst["cited_sources"] = ["2026/631793", "2026/renewable"]
    result = await _brave_run(tmp_path, "Brave is hosted on renewable energy", _BRAVE_DEFAULT_PAGES, analyst)

    # The entity match relabelled the uncited AWS and Google pages; that does not cite them.
    assert {_AWS_SUSTAIN, _GOOGLE_REPORTS, _BRAVE_TRANSPARENCY} <= result.uncited_urls
    assert persist_sources(result, tmp_path) == ["2026/631793", "2026/renewable"]


@pytest.mark.asyncio
async def test_an_analyst_override_corrected_by_the_entity_match_stays_cited(tmp_path) -> None:
    """From ``TestCitedSourceFilter.test_analyst_override_corrected_by_entity_match_stays_cited``."""
    from orchestrator.persistence import persist_sources

    analyst = _brave_verdict([{"source": "2026/sustainability", "independence": "independent",
                               "reason": "Independent test lab."}])
    analyst["cited_sources"] = ["2026/631793"]
    result = await _brave_run(tmp_path, "Brave is hosted on renewable energy", _BRAVE_DEFAULT_PAGES, analyst)

    sustain = next(o for o in result.analyst_output.verdict.source_overrides if o.source == "2026/sustainability")
    assert sustain.independence.value == "unknown"  # corrected by the entity match
    assert persist_sources(result, tmp_path) == ["2026/631793", "2026/sustainability"]


_POOL_PAGES = {
    URLS[0]: ("Alpha Lab", "independent", "Body.", "A page.", "report"),
    URLS[1]: ("Beta Lab", "independent", "Body.", "A page.", "report"),
    URLS[2]: ("Probe Subject Inc", "first-party", "Body.", "A page.", "report"),
    URLS[3]: ("Probe Subject Docs", "first-party", "Body.", "A page.", "report"),
}


async def _pool_run(tmp_path, analyst: dict):
    write_entity(tmp_path)
    with scripted_agents(ingestor=_page_ingest_model(_POOL_PAGES), analyst=analyst):
        return await _run(tmp_path)


@pytest.mark.asyncio
async def test_a_cited_subset_that_would_lower_the_level_keeps_the_full_list(tmp_path, caplog) -> None:
    """From ``TestCitedSourceFilter.test_level_guard_keeps_full_list``."""
    analyst = analyst_args(level="multiply-verified", cited_sources=["2026/third-report", "2026/fourth-report"])
    with caplog.at_level(logging.WARNING):
        result = await _pool_run(tmp_path, analyst)

    assert result.analyst_output is not None, result.errors
    assert result.uncited_urls == set()
    assert any("verification_level" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_a_level_needing_no_independent_source_uses_the_cited_subset(tmp_path) -> None:
    """From ``TestCitedSourceFilter.test_level_needing_no_independent_source_uses_subset``."""
    analyst = analyst_args(level="claimed", confidence="low", cited_sources=["2026/third-report", "2026/fourth-report"])
    result = await _pool_run(tmp_path, analyst)

    assert result.uncited_urls == {URLS[0], URLS[1]}


@pytest.mark.asyncio
async def test_a_renamed_slug_keeps_the_cited_source(tmp_path) -> None:
    """From ``TestCitedSourceFilter.test_renamed_slug_keeps_the_cited_source``: a fresh
    source whose slug is taken by another page's file is renamed before the analyst
    sees it, and citing it by title keeps it."""
    from orchestrator.persistence import persist_sources

    write_entity(tmp_path)
    _store_source(tmp_path, "https://other.example/second-report", "second-report")
    analyst = analyst_args(narrative="Per *Report at report* and *Report at second-report*, it is mixed.")
    with scripted_agents(analyst=analyst):
        result = await _run(tmp_path)

    renamed = next(sd["source_id"] for sd in result.sources if sd["url"] == URLS[1])
    assert renamed != "2026/second-report"
    assert persist_sources(result, tmp_path) == ["2026/report", renamed]


# --- A refused write leaves no orphan source (plan § Run rules, half-claim) ---


def test_a_draft_refused_for_an_existing_claim_writes_no_source(tmp_path) -> None:
    """``dr draft`` without ``--force`` over an existing claim refuses before any write,
    so the fresh pages of the refused run never reach ``research/sources/``."""
    from click.testing import CliRunner

    from orchestrator.cli import main
    from tests.loop_harness import ENTITY_REF, SENTENCE, written_sources

    write_entity(tmp_path)
    args = ["--model", "test", "draft", "--entity", ENTITY_REF, SENTENCE, "--skip-wayback",
            "--repo-root", str(tmp_path)]
    with scripted_agents():
        first = CliRunner().invoke(main, args)
    assert first.exit_code == 0, first.output
    before = written_sources(tmp_path)

    other = [f"https://example.net/other-{i}" for i in range(4)]
    with scripted_agents(scorer=scorer_args(other), search=fake_execute_searches(other, {u: "Text." for u in other})):
        second = CliRunner().invoke(main, args)

    assert second.exit_code == 1
    assert "--force" in second.output
    assert written_sources(tmp_path) == before


# --- An index entry whose file cannot be read falls back to ingest (test_source_url_dedup.py:186) ---


@pytest.mark.asyncio
async def test_an_index_entry_with_no_readable_file_is_ingested(tmp_path) -> None:
    """From ``TestApplyUrlDedup.test_apply_url_dedup_falls_back_on_bad_file``, through
    ``loop.run``'s ``url_index``."""
    import loop
    from common.canonical_url import canonical_key

    write_entity(tmp_path)
    url_index = {canonical_key(URLS[0]): "2024/missing-file"}
    with scripted_agents():
        result = await loop.run(claim_spec(tmp_path), loop_config(tmp_path), url_index=url_index)

    assert result.cached_sources == []
    assert URLS[0] in {url for url, _sf in result.source_files}
