"""A failed fetch never becomes a source.

The ingest model can return a ``SourceFile`` even when ``web_fetch`` only
ever returned an error dict (DNS failure, 5xx) or when it never called the
tool at all; the summary is then invented. These tests pin the fetch
record on ``IngestorDeps`` and the checks that reject such outputs.
"""

from __future__ import annotations

import datetime

import httpx
import pytest
import respx
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from ingestor.agent import IngestorDeps, fetch_succeeded, web_fetch

_DNS_ERROR = "[Errno 8] nodename nor servname provided, or not known"
_HTML = (
    "<html><head><title>Transparency</title></head>"
    "<body><p>Brave publishes a transparency report.</p></body></html>"
)


def _make_ctx(
    client: httpx.AsyncClient, prefetched: dict[str, str] | None = None
) -> RunContext[IngestorDeps]:
    deps = IngestorDeps(
        http_client=client,
        repo_root="/tmp",
        skip_wayback=True,
        today=datetime.date(2026, 10, 4),
        prefetched_bodies=prefetched or {},
    )
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


@pytest.mark.asyncio
async def test_web_fetch_records_success_and_failure() -> None:
    ok_url = "https://brave.com/transparency/"
    dns_url = "https://builder.aws.amazon.com/renewable"
    pre_url = "https://example.com/prefetched"

    with respx.mock:
        respx.get(ok_url).mock(return_value=httpx.Response(200, html=_HTML))
        respx.get(dns_url).mock(side_effect=httpx.ConnectError(_DNS_ERROR))
        async with httpx.AsyncClient() as client:
            ok_ctx = _make_ctx(client)
            await web_fetch(ok_ctx, ok_url)

            dns_ctx = _make_ctx(client)
            result = await web_fetch(dns_ctx, dns_url)

            pre_ctx = _make_ctx(client, prefetched={pre_url: "Body from Tavily."})
            await web_fetch(pre_ctx, pre_url)

    assert ok_ctx.deps.fetched_text[ok_url]
    assert ok_ctx.deps.fetch_errors == []
    assert fetch_succeeded(ok_ctx.deps)

    # The tool still returns an error dict so the model can try wayback.
    assert "error" in result
    assert dns_ctx.deps.fetched_text == {}
    assert len(dns_ctx.deps.fetch_errors) == 1
    assert "nodename" in dns_ctx.deps.fetch_errors[0]
    assert not fetch_succeeded(dns_ctx.deps)

    assert pre_ctx.deps.fetched_text[pre_url] == "Body from Tavily."
    assert fetch_succeeded(pre_ctx.deps)
