"""Shared fixtures and project root resolution for pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.content_loader import resolve_repo_root


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Resolve the repository root once per test session."""
    return resolve_repo_root()


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
