"""Unit tests for _ingest_urls in orchestrator.pipeline."""

from __future__ import annotations

import asyncio
import datetime
from unittest.mock import AsyncMock, patch

import pytest

from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.checkpoints import StepError
from orchestrator.pipeline import VerifyConfig, _ingest_urls


def _make_source_file(url: str, slug: str) -> SourceFile:
    return SourceFile(
        frontmatter=SourceFrontmatter(
            url=url,
            title=slug.upper(),
            publisher="Test Publisher",
            accessed_date=datetime.date(2026, 5, 1),
            kind="article",
            summary="A test summary.",
        ),
        body="Body content.",
        slug=slug,
        year=2026,
    )


def _make_cfg(repo_root, max_sources: int = 6, candidate_pool_size: int = 24) -> VerifyConfig:
    # A per-test repo root: _ingest_urls resolves slug collisions against
    # research/sources/ under it, so a shared directory would leak state.
    return VerifyConfig(
        model="test",
        repo_root=str(repo_root),
        max_sources=max_sources,
        candidate_pool_size=candidate_pool_size,
    )


@pytest.mark.asyncio
async def test_ingest_urls_stops_at_target(tmp_path) -> None:
    """_ingest_urls returns exactly max_sources results and stops early."""
    urls = [f"https://example.com/{i}" for i in range(24)]
    cfg = _make_cfg(tmp_path, max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)
    call_count = 0

    async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
        nonlocal call_count
        call_count += 1
        sf = _make_source_file(url, f"source-{call_count}")
        return (url, sf)

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        results, errors = await _ingest_urls(None, urls, cfg, sem)

    assert len(results) == 6
    # target(6) + dispatch_sem(2) = 8 max calls before stop propagates
    assert call_count <= 8


@pytest.mark.asyncio
async def test_ingest_urls_all_fail(tmp_path) -> None:
    """When every URL fails, results is empty and all failures are in errors."""
    urls = [f"https://fail.example.com/{i}" for i in range(10)]
    cfg = _make_cfg(tmp_path, max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)

    async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
        return StepError(
            step="ingest",
            url=url,
            error_type="timeout",
            message="Ingest timed out",
        )

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        results, errors = await _ingest_urls(None, urls, cfg, sem)

    assert results == []
    assert len(errors) == 10


@pytest.mark.asyncio
async def test_ingest_urls_partial_success(tmp_path) -> None:
    """When only 3 of 24 URLs succeed, returns those 3 (fewer than target is fine)."""
    urls = [f"https://example.com/{i}" for i in range(24)]
    cfg = _make_cfg(tmp_path, max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)
    # First 3 URLs succeed; all others fail.
    successes = set(urls[:3])

    async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
        if url in successes:
            return (url, _make_source_file(url, f"source-{url[-1]}"))
        return StepError(
            step="ingest",
            url=url,
            error_type="http_error",
            message="fetch failed",
        )

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        results, errors = await _ingest_urls(None, urls, cfg, sem)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_ingest_urls_small_pool(tmp_path) -> None:
    """With fewer URLs than max_sources, all are attempted and none crash."""
    urls = [f"https://example.com/{i}" for i in range(5)]
    cfg = _make_cfg(tmp_path, max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)
    call_count = 0

    async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
        nonlocal call_count
        call_count += 1
        return (url, _make_source_file(url, f"source-{call_count}"))

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        results, errors = await _ingest_urls(None, urls, cfg, sem)

    assert call_count == 5
    assert len(results) == 5
    assert errors == []


# --------------------------------------------------------------------------- #
# Ingest order by projected sub-question coverage                              #
# --------------------------------------------------------------------------- #

from common.models import SubQuestion  # noqa: E402
from orchestrator.pipeline import (  # noqa: E402
    VerificationResult,
    _ingest_claim_sources,
    _order_by_coverage,
)
from researcher.decomposed import ResearchOutput  # noqa: E402

_SQS = ["sq1", "sq2", "sq3", "sq4"]


def test_order_by_coverage_lowest_projected_count_first() -> None:
    addrs = {"a": ["sq1"], "b": ["sq2"], "c": ["sq1"]}
    assert _order_by_coverage(["a", "b", "c"], addrs, ["sq1", "sq2"], {"sq1": 2, "sq2": 0}) == ["b", "a", "c"]


def test_order_by_coverage_ties_go_by_sub_question_order() -> None:
    addrs = {"a": ["sq2"], "b": ["sq1"]}
    assert _order_by_coverage(["a", "b"], addrs, ["sq1", "sq2"], {}) == ["b", "a"]


def test_order_by_coverage_multi_sub_question_url_counts_for_each() -> None:
    # "a" covers sq1 and sq2, so after it both are at 1 and sq3's "c" wins
    # over sq1's second URL "b".
    addrs = {"a": ["sq1", "sq2"], "b": ["sq1"], "c": ["sq3"]}
    assert _order_by_coverage(["a", "b", "c"], addrs, ["sq1", "sq2", "sq3"], {}) == ["a", "c", "b"]


def test_order_by_coverage_skips_sub_question_with_no_urls_left() -> None:
    addrs = {"a": ["sq1"], "b": ["sq1"]}
    assert _order_by_coverage(["a", "b"], addrs, ["sq1", "sq2"], {}) == ["a", "b"]


def test_order_by_coverage_appends_unknown_ids_last() -> None:
    addrs = {"a": ["sq9"], "b": ["sq1"], "c": []}
    assert _order_by_coverage(["a", "b", "c"], addrs, ["sq1"], {}) == ["b", "a", "c"]


def test_order_by_coverage_without_sub_questions_keeps_input_order() -> None:
    assert _order_by_coverage(["b", "a"], {"a": ["sq1"]}, [], {}) == ["b", "a"]


def _thin_sq2_case(tmp_path):
    """The logged claim-draft case: six cached sources, two fresh slots.

    Cached coverage is sq1 5, sq2 1, sq3 3, sq4 3; the only sq2 URLs are at
    fresh positions 4 and 5.
    """
    cached_addrs = [
        ["sq1", "sq3"], ["sq1", "sq4"], ["sq1", "sq3"], ["sq1", "sq4"], ["sq1", "sq3", "sq4"], ["sq2"],
    ]
    fresh_addrs = [
        ["sq1", "sq3"], ["sq1", "sq4"], ["sq1"], ["sq2", "sq3"], ["sq2"],
        ["sq1"], ["sq3"], ["sq1"], ["sq4"], ["sq1"],
    ]
    cached = [
        (f"https://cached.example/{i}", f"2026/cached-{i}", {"source_id": f"2026/cached-{i}"})
        for i in range(len(cached_addrs))
    ]
    fresh = [f"https://fresh.example/{i}" for i in range(1, len(fresh_addrs) + 1)]
    url_addresses = {u: a for (u, _sid, _sd), a in zip(cached, cached_addrs)}
    url_addresses.update(dict(zip(fresh, fresh_addrs)))
    ro = ResearchOutput(
        urls=[u for u, _s, _d in cached] + fresh,
        url_addresses=url_addresses,
        sub_questions=[SubQuestion(id=s, question=f"{s}?", rationale="r") for s in _SQS],
    )
    result = VerificationResult(
        entity="E", claim_text="c", urls_found=[], urls_ingested=[], urls_failed=[], sources=[],
    )
    cfg = _make_cfg(tmp_path, max_sources=8, candidate_pool_size=24)
    return cached, fresh, ro, result, cfg


@pytest.mark.asyncio
async def test_ingest_claim_sources_prefers_thin_sub_question(tmp_path) -> None:
    cached, fresh, ro, result, cfg = _thin_sq2_case(tmp_path)

    async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
        return (url, _make_source_file(url, url.rsplit("/", 1)[-1]))

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        source_files, _errors, _notes = await _ingest_claim_sources(
            None, fresh, list(cached), ro, result, cfg, asyncio.Semaphore(8), {}, tmp_path,
        )

    ingested = [u for u, _sf in source_files]
    assert len(ingested) == 2
    assert {fresh[3], fresh[4]} & set(ingested), ingested


@pytest.mark.asyncio
async def test_ingest_claim_sources_tries_second_thin_url_when_first_fails(tmp_path) -> None:
    cached, fresh, ro, result, cfg = _thin_sq2_case(tmp_path)
    calls: list[str] = []

    async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
        calls.append(url)
        if url == fresh[3]:
            return StepError(step="ingest", url=url, error_type="http_error", message="fetch failed")
        return (url, _make_source_file(url, url.rsplit("/", 1)[-1]))

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        source_files, _errors, _notes = await _ingest_claim_sources(
            None, fresh, list(cached), ro, result, cfg, asyncio.Semaphore(8), {}, tmp_path,
        )

    assert calls[:2] == [fresh[3], fresh[4]]
    assert fresh[4] in [u for u, _sf in source_files]
