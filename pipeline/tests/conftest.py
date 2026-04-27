"""Shared fixtures and project root resolution for pipeline tests."""

from __future__ import annotations

from pathlib import Path

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
