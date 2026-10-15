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


@pytest.fixture(autouse=True)
def _no_live_tiebreaker(monkeypatch):
    """Keep a developer's ``DR_TIEBREAKER_MODEL`` out of the unit tests.

    The tie-breaker runs inside ``dr draft`` and ``dr step-audit`` whenever the
    Evaluator disagrees, and ``.env`` may name a frontier model for it. A CLI
    test that scripts only the analyst and the Evaluator would otherwise send
    the third pass to that model. Tests that set the variable themselves
    still can.
    """
    monkeypatch.delenv("DR_TIEBREAKER_MODEL", raising=False)


@pytest.fixture(autouse=True)
def _no_live_restater(monkeypatch):
    """Keep a developer's ``DR_RESTATER_MODEL`` out of the unit tests.

    The restater runs inside ``dr draft`` on every weak or tie-broken verdict
    (RE-AU, Restate inside the loop), so the same leak as the tie-breaker's
    applies. Tests that set the variable themselves still can.
    """
    monkeypatch.delenv("DR_RESTATER_MODEL", raising=False)


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


@pytest.fixture
def human_at_terminal(monkeypatch):
    """Stand in for the person `dr review` requires: a tty, and the right slug typed back.

    `approve_claim` refuses to write unless stdin is a tty and the operator
    types the claim slug (`orchestrator.review.confirm_person_present`).
    Tests that sign off as a side effect use this; `test_review_gate.py`
    exercises the gate itself.
    """
    import orchestrator.review as review_mod

    monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(review_mod, "_prompt_slug", lambda verb, slug: slug)


_CAPTURE_REPLAY_RE = r"https://web\.archive\.org/web/\d{14}id_/.+"


@pytest.fixture
def mock_capture_replay():
    """Return a function that mocks the ``id_`` replay HEAD check of archive.org captures.

    Every capture the archive lookup records (a TimeGate hit or a Save Page
    Now result) is first checked with a HEAD on its ``id_`` replay. respx
    routes by method, so a test that mocks a capture must mock that HEAD too,
    inside its ``respx.mock`` block. ``url`` narrows the route to one replay
    URL (exact string or pattern) when a test needs different statuses for
    different captures; respx uses the first route that matches, so narrow
    routes go first.
    """
    import re

    import httpx
    import respx

    def _mock(status: int = 200, url=None, *, memento: bool = True):
        headers = {"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT"} if memento else {}
        pattern = url if url is not None else re.compile(_CAPTURE_REPLAY_RE)
        return respx.head(pattern).mock(return_value=httpx.Response(status, headers=headers))

    return _mock
