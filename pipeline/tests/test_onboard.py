"""Tests for entity onboarding orchestration."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from analyst.agent import analyst_agent
from auditor.agent import auditor_agent
from common.content_loader import resolve_repo_root
from common.frontmatter import parse_frontmatter
from ingestor.agent import ingestor_agent
from orchestrator.checkpoints import AutoApproveCheckpointHandler
from orchestrator.pipeline import OnboardResult, VerifyConfig, onboard_entity
from researcher.agent import research_agent


@contextmanager
def _noop(**kwargs):
    """No-op context manager used to neutralize inner agent overrides."""
    yield


def _research_model() -> TestModel:
    return TestModel(
        custom_output_args={
            "urls": ["https://example.com/report"],
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
                "category": "environmental-impact",
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


def _setup_tmp_repo(tmp_path: Path) -> None:
    """Copy templates.yaml into a tmp_path-based repo structure."""
    real_root = resolve_repo_root()
    templates_src = real_root / "research" / "templates.yaml"
    templates_dst = tmp_path / "research" / "templates.yaml"
    templates_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(templates_src, templates_dst)


class TestAutoApproveReviewOnboard:
    @pytest.mark.asyncio
    async def test_returns_accept(self) -> None:
        handler = AutoApproveCheckpointHandler()
        result = await handler.review_onboard(
            entity_name="TestCorp",
            entity_type="company",
            applicable_templates=["publishes-sustainability-report"],
            excluded_templates=[],
        )
        assert result == "accept"

    @pytest.mark.asyncio
    async def test_records_in_calls(self) -> None:
        handler = AutoApproveCheckpointHandler()
        await handler.review_onboard(
            entity_name="TestCorp",
            entity_type="company",
            applicable_templates=["publishes-sustainability-report"],
            excluded_templates=[("some-slug", "not relevant")],
        )
        assert "review_onboard" in handler.calls


class TestOnboardEntityHappyPath:
    @pytest.mark.asyncio
    async def test_onboard_creates_entity_and_claims(self, tmp_path: Path) -> None:
        """Onboard with TestModel writes entity and claim files."""
        _setup_tmp_repo(tmp_path)

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
            result = await onboard_entity(
                "TestCorp", "company", config=config
            )

        assert result.status == "accepted"
        assert result.entity_name == "TestCorp"
        assert result.entity_type == "company"
        assert result.entity_ref is not None
        assert "companies/testcorp" in result.entity_ref

        # Entity file exists
        entity_path = tmp_path / "research" / "entities" / "companies" / "testcorp.md"
        assert entity_path.exists()

        # At least some claims created (6 company templates)
        assert len(result.templates_applied) == 6
        assert len(result.claims_created) > 0


class TestOnboardEntityRejection:
    @pytest.mark.asyncio
    async def test_rejected_writes_draft(self, tmp_path: Path) -> None:
        """Rejected onboard writes draft entity file."""
        _setup_tmp_repo(tmp_path)

        class RejectHandler(AutoApproveCheckpointHandler):
            async def review_onboard(self, entity_name, entity_type,
                                     applicable_templates, excluded_templates,
                                     entity_description=""):
                self.calls.append("review_onboard")
                return "reject"

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
            handler = RejectHandler()
            result = await onboard_entity(
                "TestCorp", "company", config=config, checkpoint=handler
            )

        assert result.status == "rejected"
        assert result.entity_ref is not None
        assert "drafts/" in result.entity_ref
        assert result.claims_created == []

        # Draft entity file exists
        draft_path = (
            tmp_path / "research" / "entities" / "drafts" / "companies" / "testcorp.md"
        )
        assert draft_path.exists()
        fm, _ = parse_frontmatter(draft_path.read_text())
        assert fm["name"] == "TestCorp"
        assert fm["status"] == "draft"

        # Checkpoint was recorded
        assert "review_onboard" in handler.calls
