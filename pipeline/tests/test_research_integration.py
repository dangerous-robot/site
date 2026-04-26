"""Integration test for the research_claim orchestrator pipeline."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from analyst.agent import analyst_agent
from auditor.agent import auditor_agent
from common.frontmatter import parse_frontmatter
from ingestor.agent import ingestor_agent
from orchestrator.pipeline import VerifyConfig, research_claim
from researcher.agent import research_agent


@contextmanager
def _noop(**kwargs):
    """No-op context manager used to neutralize inner agent overrides."""
    yield


def _research_model() -> TestModel:
    # Two URLs so research_claim clears the >=2 usable-source threshold the
    # Orchestrator enforces post-ingest (docs/plans/claim-lifecycle-states.md).
    return TestModel(
        custom_output_args={
            "urls": [
                "https://example.com/report",
                "https://example.com/second-report",
            ],
            "reasoning": "Found a relevant report.",
        },
        call_tools=[],
    )


def _ingestor_model() -> TestModel:
    return TestModel(
        custom_output_args={
            "frontmatter": {
                "url": "https://example.com/report",
                "title": "Test Report",
                "publisher": "Example Publisher",
                "accessed_date": "2026-04-19",
                "kind": "article",
                "summary": "A factual summary of the test report.",
            },
            "body": "Additional context about the report.",
            "slug": "test-report",
            "year": 2026,
        },
        call_tools=[],
    )


def _analyst_model() -> TestModel:
    return TestModel(
        custom_output_args={
            "entity": {
                "entity_name": "TestCorp",
                "entity_type": "company",
                "entity_description": "A test company",
            },
            "verdict": {
                "title": "test-claim",
                "topics": ["environmental-impact"],
                "verdict": "mixed",
                "confidence": "medium",
                "narrative": "The evidence is mixed.",
            },
        },
    )


def _auditor_model() -> TestModel:
    return TestModel(
        custom_output_args={
            "verdict": "mixed",
            "confidence": "medium",
            "reasoning": "Independent assessment agrees.",
            "evidence_gaps": [],
        },
    )


@pytest.mark.asyncio
async def test_research_claim_writes_artifacts(tmp_path):
    """research_claim with TestModel writes source, entity, and claim files."""
    # Set up outer overrides with TestModel instances per agent, then
    # neutralize the orchestrator's inner override calls so they don't
    # replace our custom TestModel instances with a default TestModel.
    with (
        research_agent.override(model=_research_model()),
        ingestor_agent.override(model=_ingestor_model()),
        analyst_agent.override(model=_analyst_model()),
        auditor_agent.override(model=_auditor_model()),
        patch.object(
            Agent, "override", side_effect=lambda **kw: _noop(**kw)
        ),
    ):
        config = VerifyConfig(
            model="test",
            max_sources=2,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        result = await research_claim("TestCorp uses renewable energy", config)

    # -- No fatal errors --
    assert not result.errors, f"Unexpected errors: {result.errors}"

    # -- Source file written with valid frontmatter --
    source_path = tmp_path / "research" / "sources" / "2026" / "test-report.md"
    assert source_path.exists(), f"Source file not found at {source_path}"
    fm, _ = parse_frontmatter(source_path.read_text())
    assert fm["title"] == "Test Report"
    assert fm["url"] == "https://example.com/report"

    # -- Entity file written with valid frontmatter --
    entity_path = tmp_path / "research" / "entities" / "companies" / "testcorp.md"
    assert entity_path.exists(), f"Entity file not found at {entity_path}"
    fm, _ = parse_frontmatter(entity_path.read_text())
    assert fm["name"] == "TestCorp"
    assert fm["type"] == "company"

    # -- Claim file written with valid frontmatter --
    # Slug is derived from analyst title "test-claim" via slugify
    claim_path = tmp_path / "research" / "claims" / "testcorp" / "test-claim.md"
    assert claim_path.exists(), f"Claim file not found at {claim_path}"
    fm, _ = parse_frontmatter(claim_path.read_text())
    assert fm["verdict"] == "mixed"
    assert fm["confidence"] == "medium"
    assert "2026/test-report" in fm["sources"]

    # -- Result fields populated --
    assert result.entity == "TestCorp"
    assert result.analyst_output is not None
    assert result.consistency is not None
