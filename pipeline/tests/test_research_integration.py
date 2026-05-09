"""Integration test for the research_claim orchestrator pipeline."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
import yaml
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from analyst.agent import analyst_agent
from auditor.agent import auditor_agent
from common.frontmatter import parse_frontmatter
from common.models import SubQuestion
from ingestor.agent import ingestor_agent
from orchestrator.pipeline import VerifyConfig, research_claim


@contextmanager
def _noop(**kwargs):
    """No-op context manager used to neutralize inner agent overrides."""
    yield


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
                "verification_level": "partially-verified",
                "seo_title": "test-claim",
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
async def test_research_claim_writes_artifacts(tmp_path, monkeypatch):
    """research_claim with TestModel writes source, entity, and claim files."""

    from researcher.decomposed import ResearchOutput

    sub_questions = [
        SubQuestion(id="sq1", question="Does TestCorp publish energy data?", rationale="first-party axis"),
        SubQuestion(id="sq2", question="Do third-party sources confirm it?", rationale="independent axis"),
    ]
    urls = [
        "https://example.com/report",
        "https://example.com/second-report",
        "https://example.com/third-report",
        "https://example.com/fourth-report",
    ]

    async def _fake_research(client, entity, claim, cfg, sem, **kwargs):
        return ResearchOutput(
            urls=list(urls),
            url_addresses={
                urls[0]: ["sq1"],
                urls[1]: ["sq1", "sq2"],
                urls[2]: ["sq2"],
                urls[3]: ["sq1"],
            },
            sub_questions=list(sub_questions),
            queries_by_sub_question={
                "sq1": ["TestCorp energy report"],
                "sq2": ["TestCorp energy independent"],
            },
            trace={"mode": "decomposed"},
        )

    monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)

    with (
        ingestor_agent.override(model=_ingestor_model()),
        analyst_agent.override(model=_analyst_model()),
        auditor_agent.override(model=_auditor_model()),
        patch.object(
            Agent, "override", side_effect=lambda **kw: _noop(**kw)
        ),
    ):
        config = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        result = await research_claim("TestCorp uses renewable energy", config)

    # -- No fatal errors --
    assert not result.errors, f"Unexpected errors: {result.errors}"

    # -- Source file written with valid frontmatter --
    # Slug is derived from the URL path segment ("report"), not the ingestor's
    # LLM-generated slug ("test-report"), per the URL-derived slug override in
    # _ingest_one.
    source_path = tmp_path / "research" / "sources" / "2026" / "report.md"
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
    assert "2026/report" in fm["sources"]

    # -- Result fields populated --
    assert result.entity == "TestCorp"
    assert result.analyst_output is not None
    assert result.consistency is not None

    # -- Audit sidecar carries the sub_questions block in the right slot --
    audit_path = claim_path.with_name(claim_path.stem + ".audit.yaml")
    assert audit_path.exists(), f"Audit sidecar not found at {audit_path}"
    sidecar = yaml.safe_load(audit_path.read_text())
    keys = list(sidecar.keys())
    assert "sub_questions" in sidecar
    # sub_questions must sit between research and sources_consulted
    assert keys.index("sub_questions") == keys.index("research") + 1
    assert keys.index("sub_questions") == keys.index("sources_consulted") - 1
    block = sidecar["sub_questions"]
    assert len(block) == 2
    for entry in block:
        assert {"id", "question", "rationale", "queries", "citations"} <= set(entry)
    sq1_entry = next(e for e in block if e["id"] == "sq1")
    # sq1 should have citations from the three urls that addressed it
    assert len(sq1_entry["citations"]) >= 1
