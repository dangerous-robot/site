"""Tests for the Tavily prefetch passthrough.

Covers ``IngestorDeps.prefetched_bodies`` short-circuiting ``web_fetch``
and the orchestrator handoff that threads bodies through ``_ingest_urls``
into per-URL ``IngestorDeps``.
"""

from __future__ import annotations

import asyncio
import datetime
from unittest.mock import patch

import httpx
import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from ingestor.agent import IngestorDeps, web_fetch
from orchestrator.pipeline import VerifyConfig, _ingest_urls


def _make_ctx(
    client: httpx.AsyncClient, prefetched_bodies: dict[str, str]
) -> RunContext[IngestorDeps]:
    deps = IngestorDeps(
        http_client=client,
        repo_root="/tmp",
        skip_wayback=True,
        today=datetime.date(2026, 5, 8),
        prefetched_bodies=prefetched_bodies,
    )
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


class TestWebFetchShortCircuit:
    @pytest.mark.asyncio
    async def test_returns_prefetched_body_without_http(self) -> None:
        """When ``prefetched_bodies[url]`` is set, ``web_fetch`` returns the
        body and does not call ``httpx.AsyncClient.get``."""
        url = "https://x.example/article"
        body = "# Title\n\nFull article body in Markdown."

        async def _no_get(self, *args, **kwargs):  # noqa: ANN001
            raise AssertionError("httpx.AsyncClient.get should not be called")

        async with httpx.AsyncClient() as client:
            ctx = _make_ctx(client, {url: body})
            with patch.object(httpx.AsyncClient, "get", _no_get):
                result = await web_fetch(ctx, url)

        assert result["text"] == body
        assert result["url"] == url
        assert result["title"] == ""
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_empty_body_falls_through_to_live_fetch(self) -> None:
        """An empty/missing prefetched body must not short-circuit; the
        normal httpx path runs."""
        url = "https://x.example/article"
        html = "<html><head><title>Live</title></head><body><p>ok</p></body></html>"
        gets: list[str] = []

        original_get = httpx.AsyncClient.get

        async def counting_get(self, *args, **kwargs):  # noqa: ANN001
            gets.append(args[0] if args else kwargs.get("url", ""))
            return await original_get(self, *args, **kwargs)

        import respx

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(200, text=html))
            async with httpx.AsyncClient() as client:
                # Empty string under the URL: must NOT short-circuit.
                ctx = _make_ctx(client, {url: ""})
                with patch.object(httpx.AsyncClient, "get", counting_get):
                    result = await web_fetch(ctx, url)
        assert gets == [url]
        assert result["title"] == "Live"

    @pytest.mark.asyncio
    async def test_unrelated_url_falls_through(self) -> None:
        """A prefetched body for one URL doesn't short-circuit a different URL."""
        prefetched_url = "https://other.example/page"
        target_url = "https://x.example/article"
        html = "<html><head><title>Target</title></head><body>ok</body></html>"

        import respx

        with respx.mock:
            respx.get(target_url).mock(return_value=httpx.Response(200, text=html))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client, {prefetched_url: "PRE"})
                result = await web_fetch(ctx, target_url)
        assert result["title"] == "Target"


class TestIngestUrlsPrefetched:
    @pytest.mark.asyncio
    async def test_ingest_urls_passes_per_url_body(self) -> None:
        """``_ingest_urls`` passes the per-URL prefetched body into
        ``_ingest_one`` so the short-circuit fires without network I/O."""
        urls = [f"https://x.example/{i}" for i in range(3)]
        bodies = {urls[0]: "BODY-0", urls[2]: "BODY-2"}
        cfg = VerifyConfig(
            model="test", repo_root="/tmp", max_sources=3, candidate_pool_size=3
        )
        sem = asyncio.Semaphore(2)
        seen: dict[str, str | None] = {}

        async def _fake_ingest_one(
            client, url, cfg, today, sem, prefetched_body=None
        ):
            seen[url] = prefetched_body
            from ingestor.models import SourceFile, SourceFrontmatter

            sf = SourceFile(
                frontmatter=SourceFrontmatter(
                    url=url,
                    title="t",
                    publisher="p",
                    accessed_date=datetime.date(2026, 5, 1),
                    kind="article",
                    summary="s",
                ),
                body="b",
                slug="slug",
                year=2026,
            )
            return (url, sf)

        with patch(
            "orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one
        ):
            results, errors = await _ingest_urls(
                None, urls, cfg, sem, prefetched_bodies=bodies
            )

        assert seen[urls[0]] == "BODY-0"
        assert seen[urls[1]] is None
        assert seen[urls[2]] == "BODY-2"
        assert len(results) == 3
