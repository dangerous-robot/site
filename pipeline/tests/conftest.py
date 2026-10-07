"""Shared fixtures and project root resolution for pipeline tests."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

from common.content_loader import resolve_repo_root
from common.logging_setup import run_id_var


@pytest.fixture(autouse=True)
def _reset_run_id_var():
    """Clear any run_id binding the test left behind.

    Without this, a test that calls `dr` via CliRunner (which sets run_id_var
    in the click callback) leaks the id into subsequent tests' log records.
    """
    yield
    run_id_var.set(None)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Resolve the repository root once per test session."""
    return resolve_repo_root()


@pytest.fixture(autouse=True, scope="session")
def _isolate_cli_logging():
    """Stop CLI tests (CliRunner.invoke) from writing to the real ``logs/``.

    ``orchestrator.cli.main`` calls ``configure_logging(repo_root=_safe_repo_root())``
    on every invocation. Without this fixture, tests that drive the CLI
    via ``CliRunner`` install RotatingFileHandlers pointing at the
    project's actual ``logs/`` directory and pollute it across runs.
    """
    mp = pytest.MonkeyPatch()
    mp.setattr("orchestrator.cli._safe_repo_root", lambda: None)
    try:
        yield
    finally:
        mp.undo()


@pytest.fixture()
def sample_frontmatter_text() -> str:
    """A minimal frontmatter markdown string for testing."""
    return (
        "---\n"
        "title: Test Claim\n"
        "verdict: \"false\"\n"
        "---\n"
        "\n"
        "Body content here.\n"
    )


@contextmanager
def _stubbed_ingest_model(*, call_wayback: bool):
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from ingestor.agent import ingestor_agent

    extra_frontmatter: dict = {}

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        prompt = next(p.content for p in parts if isinstance(p, UserPromptPart))
        url = prompt.split("URL: ", 1)[1].split("\n", 1)[0]
        called = [p.tool_name for p in parts if isinstance(p, ToolCallPart)]
        if not called:
            return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})])
        if call_wayback and "wayback_check" not in called:
            return ModelResponse(parts=[ToolCallPart(tool_name="wayback_check", args={"url": url})])
        source = {
            "frontmatter": {
                "url": url,
                "title": "The stored page",
                "publisher": "Example",
                "accessed_date": "2026-10-07",
                "kind": "article",
                "summary": "The stored page.",
                **extra_frontmatter,
            },
            "body": "The stored page.",
            "slug": "page",
            "year": 2026,
        }
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])

    with ingestor_agent.override(model=FunctionModel(_fn)):
        # Keep this model: callers enter their own override with the configured one.
        with patch.object(ingestor_agent, "override", side_effect=lambda **kw: nullcontext()):
            yield extra_frontmatter


@pytest.fixture
def stub_ingest_model():
    """Swap in an ingest model that fetches the requested URL, then returns a source for it.

    It never calls ``wayback_check``. The fixture value is a dict of extra
    frontmatter fields the model writes (e.g. ``archived_url``); tests may
    fill it before ingesting.
    """
    with _stubbed_ingest_model(call_wayback=False) as extra_frontmatter:
        yield extra_frontmatter


@pytest.fixture
def stub_ingest_model_calling_wayback():
    """Like ``stub_ingest_model``, but the model also calls ``wayback_check`` on the URL."""
    with _stubbed_ingest_model(call_wayback=True) as extra_frontmatter:
        yield extra_frontmatter
