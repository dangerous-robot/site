"""Tests for terminal HTTP fetch behavior in the ingestor.

These cover the fail-fast path for 401/402/403/451 (terminal codes) and the
in-tool retry-once behavior for 429. See docs/plans/ingestor-fail-fast-403.md.
"""

from __future__ import annotations

import asyncio
import datetime
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
import respx
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from ingestor.agent import IngestorDeps, ingestor_agent, web_fetch
from ingestor.tools import wayback as wayback_module
from ingestor.tools.web_fetch import TERMINAL_STATUS_CODES, TerminalFetchError
from orchestrator.pipeline import VerifyConfig, _ingest_one


@contextmanager
def _noop_ctx():
    """No-op context manager used to neutralize nested agent overrides."""
    yield


def _make_ctx(client: httpx.AsyncClient) -> RunContext[IngestorDeps]:
    """Build a minimal RunContext sufficient for calling the web_fetch tool."""
    deps = IngestorDeps(
        http_client=client,
        repo_root="/tmp",
        skip_wayback=True,
        today=datetime.date(2026, 4, 19),
    )
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


class TestTerminalStatusCodes:
    def test_set_contains_expected_codes(self) -> None:
        assert TERMINAL_STATUS_CODES == frozenset({401, 402, 403, 404, 451})

    @pytest.mark.asyncio
    async def test_terminal_403_raises(self) -> None:
        url = "https://example.com/forbidden"
        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(403))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                with pytest.raises(TerminalFetchError) as exc_info:
                    await web_fetch(ctx, url)
        assert exc_info.value.status_code == 403
        assert exc_info.value.url == url

    @pytest.mark.asyncio
    async def test_terminal_401_raises(self) -> None:
        url = "https://example.com/login"
        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(401))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                with pytest.raises(TerminalFetchError) as exc_info:
                    await web_fetch(ctx, url)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_terminal_451_raises(self) -> None:
        url = "https://example.com/legal"
        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(451))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                with pytest.raises(TerminalFetchError) as exc_info:
                    await web_fetch(ctx, url)
        assert exc_info.value.status_code == 451

    @pytest.mark.asyncio
    async def test_terminal_402_raises(self) -> None:
        url = "https://example.com/paywall"
        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(402))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                with pytest.raises(TerminalFetchError) as exc_info:
                    await web_fetch(ctx, url)
        assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_terminal_404_raises(self) -> None:
        url = "https://example.com/missing"
        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(404))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                with pytest.raises(TerminalFetchError) as exc_info:
                    await web_fetch(ctx, url)
        assert exc_info.value.status_code == 404
        assert exc_info.value.url == url


class Test429Handling:
    @pytest.mark.asyncio
    async def test_429_single_retry_then_raise(self) -> None:
        """Two consecutive 429s: assert one retry, then TerminalFetchError."""
        url = "https://example.com/rate-limited"
        with respx.mock:
            route = respx.get(url).mock(
                side_effect=[httpx.Response(429), httpx.Response(429)]
            )
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                # Patch asyncio.sleep in the agent module so the test doesn't
                # actually wait 2 seconds.
                with patch("ingestor.agent.asyncio.sleep", autospec=True) as sleep_mock:
                    sleep_mock.return_value = None
                    with pytest.raises(TerminalFetchError) as exc_info:
                        await web_fetch(ctx, url)
            assert route.call_count == 2
            assert sleep_mock.await_count == 1
            assert sleep_mock.await_args.args[0] == 2.0
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_429_recovers_on_second_try(self) -> None:
        """429 then 200: assert success, no raise."""
        url = "https://example.com/flaky"
        html = "<html><head><title>Recovered</title></head><body><p>ok</p></body></html>"
        with respx.mock:
            route = respx.get(url).mock(
                side_effect=[
                    httpx.Response(429),
                    httpx.Response(200, text=html),
                ]
            )
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                with patch("ingestor.agent.asyncio.sleep", autospec=True) as sleep_mock:
                    sleep_mock.return_value = None
                    result = await web_fetch(ctx, url)
            assert route.call_count == 2
            assert sleep_mock.await_count == 1
        assert result["title"] == "Recovered"
        assert "error" not in result


class TestSoftStatuses:
    @pytest.mark.asyncio
    async def test_500_still_soft(self) -> None:
        """5xx should return an error dict (unchanged)."""
        url = "https://example.com/servererror"
        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(503))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                result = await web_fetch(ctx, url)
        assert "error" in result


class TestWaybackNotCalledOnTerminal:
    @pytest.mark.asyncio
    async def test_no_wayback_call_on_403(self) -> None:
        """Spy on check_wayback; a 403 fetch must not invoke it."""
        url = "https://example.com/forbidden2"
        calls: list[str] = []

        async def spy_check_wayback(client, u):
            calls.append(u)
            return {"available": False, "archived_url": None}

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(403))
            async with httpx.AsyncClient() as client:
                ctx = _make_ctx(client)
                with patch.object(wayback_module, "check_wayback", spy_check_wayback):
                    with pytest.raises(TerminalFetchError):
                        await web_fetch(ctx, url)
        assert calls == []


def _make_web_fetch_caller_model(url: str) -> FunctionModel:
    """Build a FunctionModel that calls web_fetch once with the given URL."""

    async def _fn(messages, info):
        return ModelResponse(
            parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})]
        )

    return FunctionModel(_fn)


class TestAgentRetryBudget:
    @pytest.mark.asyncio
    async def test_agent_does_not_retry_on_terminal(self) -> None:
        """Run the agent against a 403 URL; web_fetch should be called exactly
        once and the agent run should raise TerminalFetchError without the
        model being re-invoked (retry budget not consumed)."""
        url = "https://example.com/forbidden-agent"
        model_calls = 0
        fetch_calls = 0

        async def counting_fn(messages, info):
            nonlocal model_calls
            model_calls += 1
            return ModelResponse(
                parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})]
            )

        original_get = httpx.AsyncClient.get

        async def counting_get(self, *args, **kwargs):
            nonlocal fetch_calls
            fetch_calls += 1
            return await original_get(self, *args, **kwargs)

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(403))
            async with httpx.AsyncClient() as client:
                deps = IngestorDeps(
                    http_client=client,
                    repo_root="/tmp",
                    skip_wayback=True,
                    today=datetime.date(2026, 4, 19),
                )
                with patch.object(httpx.AsyncClient, "get", counting_get):
                    with ingestor_agent.override(model=FunctionModel(counting_fn)):
                        with pytest.raises(TerminalFetchError):
                            await ingestor_agent.run(
                                f"Ingest this URL: {url}", deps=deps
                            )
        # Model was invoked exactly once (to emit the tool call). After the
        # tool raised, the agent did NOT come back to the model for a retry.
        assert model_calls == 1
        assert fetch_calls == 1


class TestOrchestratorMapping:
    @pytest.mark.asyncio
    async def test_terminal_403_maps_to_step_error(self) -> None:
        """_ingest_one for a 403 URL returns StepError with error_type='http_403' and retryable=False."""
        url = "https://example.com/forbidden-orch"
        cfg = VerifyConfig(model="test", repo_root="/tmp", skip_wayback=True)

        with respx.mock:
            respx.get(url).mock(return_value=httpx.Response(403))
            async with httpx.AsyncClient() as client:
                # Neutralize the orchestrator's inner override of model="test"
                # so our FunctionModel stays in place.
                with ingestor_agent.override(model=_make_web_fetch_caller_model(url)):
                    with patch(
                        "orchestrator.pipeline.ingestor_agent.override",
                        side_effect=lambda **kw: _noop_ctx(),
                    ):
                        outcome = await _ingest_one(
                            client, url, cfg, datetime.date(2026, 4, 19), asyncio.Semaphore(8)
                        )
        # StepError (not a success tuple)
        assert not isinstance(outcome, tuple)
        assert outcome.step == "ingest"
        assert outcome.url == url
        assert outcome.error_type == "http_403"
        assert outcome.retryable is False
