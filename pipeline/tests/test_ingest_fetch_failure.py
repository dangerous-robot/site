"""A failed fetch never becomes a source.

The ingest model can return a ``SourceFile`` even when ``web_fetch`` only
ever returned an error dict (DNS failure, 5xx) or when it never called the
tool at all; the summary is then invented. These tests pin the fetch
record on ``IngestorDeps`` and the checks that reject such outputs.
"""

from __future__ import annotations

import asyncio
import datetime
from contextlib import nullcontext
from unittest.mock import patch

import httpx
import pytest
import respx
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from ingestor.agent import IngestorDeps, fetch_failure_reason, ingestor_agent, web_fetch
from orchestrator.pipeline import VerifyConfig, _ingest_one

_TODAY = datetime.date(2026, 10, 4)
_DNS_ERROR = "[Errno 8] nodename nor servname provided, or not known"
_HTML = (
    "<html><head><title>Transparency</title></head>"
    "<body><p>Brave publishes a transparency report.</p></body></html>"
)


def _make_ctx(
    client: httpx.AsyncClient, requested_url: str, prefetched: dict[str, str] | None = None
) -> RunContext[IngestorDeps]:
    deps = IngestorDeps(
        http_client=client,
        repo_root="/tmp",
        requested_url=requested_url,
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
            ok_ctx = _make_ctx(client, ok_url)
            await web_fetch(ok_ctx, ok_url)

            dns_ctx = _make_ctx(client, dns_url)
            result = await web_fetch(dns_ctx, dns_url)

            pre_ctx = _make_ctx(client, pre_url, prefetched={pre_url: "Body from Tavily."})
            await web_fetch(pre_ctx, pre_url)

    assert ok_ctx.deps.fetched_text[ok_url]
    assert ok_ctx.deps.fetch_errors == []
    assert fetch_failure_reason(ok_ctx.deps) is None

    # The tool still returns an error dict so the model can try wayback.
    assert "error" in result
    assert dns_ctx.deps.fetched_text == {}
    assert len(dns_ctx.deps.fetch_errors) == 1
    assert "nodename" in dns_ctx.deps.fetch_errors[0]
    assert fetch_failure_reason(dns_ctx.deps) == dns_ctx.deps.fetch_errors[0]

    assert pre_ctx.deps.fetched_text[pre_url] == "Body from Tavily."
    assert fetch_failure_reason(pre_ctx.deps) is None


async def _fetch_one(requested_url: str, fetched: str) -> RunContext[IngestorDeps]:
    """Run ``web_fetch`` on ``fetched`` (which loads) while ingesting ``requested_url``."""
    with respx.mock:
        respx.get(fetched).mock(return_value=httpx.Response(200, html=_HTML))
        async with httpx.AsyncClient() as client:
            ctx = _make_ctx(client, requested_url)
            await web_fetch(ctx, fetched)
    assert ctx.deps.fetched_text[fetched]
    return ctx


@pytest.mark.parametrize(
    "fetched",
    [
        "https://www.brave.com/transparency",
        "https://web.archive.org/web/20250315000000/https://brave.com/transparency/",
        "http://web.archive.org/web/20250315id_/https://www.brave.com/transparency",
        "https://web.archive.org/web/https://brave.com/transparency/",
        "https://web.archive.org/web/20250315000000/http://brave.com/transparency/",
        "https://web.archive.org/web/2025/brave.com/transparency",
        "http://brave.com/transparency/",
    ],
)
@pytest.mark.asyncio
async def test_requested_page_or_its_archive_copy_counts(fetched: str) -> None:
    ctx = await _fetch_one("https://brave.com/transparency/", fetched)
    assert fetch_failure_reason(ctx.deps) is None


@pytest.mark.parametrize(
    "fetched",
    [
        "https://brave.com/privacy/",
        "https://web.archive.org/web/2025/https://brave.com/privacy/",
        "https://web.archive.org/web/2025/brave.com/privacy/",
    ],
)
@pytest.mark.asyncio
async def test_other_page_text_does_not_count(fetched: str) -> None:
    ctx = await _fetch_one("https://brave.com/transparency/", fetched)
    reason = fetch_failure_reason(ctx.deps)
    assert reason is not None
    assert "https://brave.com/transparency/" in reason


# ---------------------------------------------------------------------------
# _ingest_one: reject outputs with no fetched page text or failed validation
# ---------------------------------------------------------------------------


def _source_args(url: str, **overrides) -> dict:
    frontmatter = {
        "url": url,
        "title": "Brave transparency report",
        "publisher": "Brave Software",
        "accessed_date": _TODAY.isoformat(),
        "kind": "report",
        "summary": "Brave publishes a transparency report.",
    }
    frontmatter.update(overrides)
    return {
        "frontmatter": frontmatter,
        "body": "Brave publishes a transparency report.",
        "slug": "transparency",
        "year": 2025,
    }


def _scripted_model(fetch_urls: list[str], source: dict) -> FunctionModel:
    """Call ``web_fetch`` once per URL in order, then return ``source``."""
    step = 0

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        nonlocal step
        if step < len(fetch_urls):
            url = fetch_urls[step]
            step += 1
            return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})])
        return ModelResponse(
            parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)]
        )

    return FunctionModel(_fn)


async def _run_ingest_one(url: str, model: FunctionModel, tmp_path):
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), skip_wayback=True)
    async with httpx.AsyncClient() as client:
        with ingestor_agent.override(model=model):
            # Keep our FunctionModel: neutralize the orchestrator's own override.
            with patch(
                "orchestrator.pipeline.ingestor_agent.override",
                side_effect=lambda **kw: nullcontext(),
            ):
                return await _ingest_one(client, url, cfg, _TODAY, asyncio.Semaphore(8))


@pytest.mark.asyncio
async def test_dns_failure_returns_fetch_failed(tmp_path) -> None:
    url = "https://builder.aws.amazon.com/renewable"
    with respx.mock:
        respx.get(url).mock(side_effect=httpx.ConnectError(_DNS_ERROR))
        outcome = await _run_ingest_one(url, _scripted_model([url], _source_args(url)), tmp_path)
    assert not isinstance(outcome, tuple)
    assert outcome.error_type == "fetch_failed"
    assert outcome.step == "ingest"
    assert outcome.url == url
    assert "nodename" in outcome.message


@pytest.mark.asyncio
async def test_model_skips_fetch_returns_fetch_failed(tmp_path) -> None:
    url = "https://brave.com/transparency/"
    outcome = await _run_ingest_one(url, _scripted_model([], _source_args(url)), tmp_path)
    assert not isinstance(outcome, tuple)
    assert outcome.error_type == "fetch_failed"
    assert "without fetching" in outcome.message


@pytest.mark.asyncio
async def test_wayback_recovery_still_ingests(tmp_path) -> None:
    url = "https://brave.com/transparency/"
    archive = "https://web.archive.org/web/2025/https://brave.com/transparency/"
    with respx.mock:
        respx.get(url).mock(side_effect=httpx.ConnectError(_DNS_ERROR))
        respx.get(archive).mock(return_value=httpx.Response(200, html=_HTML))
        outcome = await _run_ingest_one(
            url,
            _scripted_model([url, archive], _source_args(url, archived_url=archive)),
            tmp_path,
        )
    assert isinstance(outcome, tuple)
    assert outcome[0] == url


@pytest.mark.asyncio
async def test_unrelated_page_fetched_returns_fetch_failed(tmp_path) -> None:
    url = "https://builder.aws.amazon.com/renewable"
    unrelated = "https://brave.com/transparency/"
    with respx.mock:
        respx.get(url).mock(side_effect=httpx.ConnectError(_DNS_ERROR))
        respx.get(unrelated).mock(return_value=httpx.Response(200, html=_HTML))
        outcome = await _run_ingest_one(
            url, _scripted_model([url, unrelated], _source_args(url)), tmp_path
        )
    assert not isinstance(outcome, tuple)
    assert outcome.error_type == "fetch_failed"
    # The requested page's own error, not the unrelated page's success.
    assert "nodename" in outcome.message


@pytest.mark.asyncio
async def test_invalid_archived_url_returns_invalid_source(tmp_path) -> None:
    url = "https://brave.com/transparency/"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, html=_HTML))
        outcome = await _run_ingest_one(
            url,
            _scripted_model([url], _source_args(url, archived_url="https://archive.ph/abc")),
            tmp_path,
        )
    assert not isinstance(outcome, tuple)
    assert outcome.error_type == "invalid_source"
    assert "archived_url" in outcome.message


@pytest.mark.asyncio
async def test_model_url_replaced_with_requested_url(tmp_path) -> None:
    url = "https://brave.com/transparency/"
    echoed = "https://brave.com/transparency-report/"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, html=_HTML))
        outcome = await _run_ingest_one(url, _scripted_model([url], _source_args(echoed)), tmp_path)
    assert isinstance(outcome, tuple)
    assert outcome[1].frontmatter.url == url


# ---------------------------------------------------------------------------
# dr step-ingest
# ---------------------------------------------------------------------------


def _invoke_step_ingest(tmp_path, url: str, mock_kwargs: dict, model_url: str):
    from click.testing import CliRunner

    from orchestrator.cli import main

    (tmp_path / "research" / "sources").mkdir(parents=True)
    with respx.mock:
        respx.get(url).mock(**mock_kwargs)
        with ingestor_agent.override(model=_scripted_model([url], _source_args(model_url))):
            with patch(
                "ingestor.agent.ingestor_agent.override",
                side_effect=lambda **kw: nullcontext(),
            ):
                return CliRunner().invoke(
                    main,
                    [
                        "--model", "test", "--ingestor-model", "test",
                        "step-ingest", url, "--write", "--skip-wayback",
                        "--repo-root", str(tmp_path),
                    ],
                )


def test_step_ingest_fetch_failure_writes_nothing(tmp_path) -> None:
    url = "https://builder.aws.amazon.com/renewable"
    result = _invoke_step_ingest(
        tmp_path, url, {"side_effect": httpx.ConnectError(_DNS_ERROR)}, url
    )
    assert result.exit_code == 1, result.output
    error_lines = [ln for ln in result.output.splitlines() if ln.startswith("Error:")]
    assert len(error_lines) == 1
    assert "fetch failed" in error_lines[0]
    assert "nodename" in error_lines[0]
    assert list((tmp_path / "research" / "sources").rglob("*.md")) == []


def test_step_ingest_keeps_requested_url_when_model_echoes_redirect(tmp_path) -> None:
    url = "https://brave.com/transparency/"
    result = _invoke_step_ingest(
        tmp_path, url, {"return_value": httpx.Response(200, html=_HTML)},
        "https://brave.com/transparency-report/",
    )
    assert result.exit_code == 0, result.output
    written = list((tmp_path / "research" / "sources").rglob("*.md"))
    assert len(written) == 1
    assert f"url: {url}" in written[0].read_text()
