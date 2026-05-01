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


def _make_cfg(max_sources: int = 6, candidate_pool_size: int = 24) -> VerifyConfig:
    return VerifyConfig(
        model="test",
        repo_root="/tmp",
        max_sources=max_sources,
        candidate_pool_size=candidate_pool_size,
    )


@pytest.mark.asyncio
async def test_ingest_urls_stops_at_target() -> None:
    """_ingest_urls returns exactly max_sources results and stops early."""
    urls = [f"https://example.com/{i}" for i in range(24)]
    cfg = _make_cfg(max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)
    call_count = 0

    async def _fake_ingest_one(client, url, cfg, today, sem):
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
async def test_ingest_urls_all_fail() -> None:
    """When every URL fails, results is empty and all failures are in errors."""
    urls = [f"https://fail.example.com/{i}" for i in range(10)]
    cfg = _make_cfg(max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)

    async def _fake_ingest_one(client, url, cfg, today, sem):
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
async def test_ingest_urls_partial_success() -> None:
    """When only 3 of 24 URLs succeed, returns those 3 (fewer than target is fine)."""
    urls = [f"https://example.com/{i}" for i in range(24)]
    cfg = _make_cfg(max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)
    # First 3 URLs succeed; all others fail.
    successes = set(urls[:3])

    async def _fake_ingest_one(client, url, cfg, today, sem):
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
async def test_ingest_urls_small_pool() -> None:
    """With fewer URLs than max_sources, all are attempted and none crash."""
    urls = [f"https://example.com/{i}" for i in range(5)]
    cfg = _make_cfg(max_sources=6, candidate_pool_size=24)
    sem = asyncio.Semaphore(8)
    call_count = 0

    async def _fake_ingest_one(client, url, cfg, today, sem):
        nonlocal call_count
        call_count += 1
        return (url, _make_source_file(url, f"source-{call_count}"))

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        results, errors = await _ingest_urls(None, urls, cfg, sem)

    assert call_count == 5
    assert len(results) == 5
    assert errors == []
