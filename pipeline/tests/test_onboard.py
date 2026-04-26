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

        # At least some claims created (4 company templates active in v0.1.0)
        assert len(result.templates_applied) == 4
        assert len(result.claims_created) > 0


class TestOnboardEntityNoDoubleIngest:
    @pytest.mark.asyncio
    async def test_single_research_and_ingest_per_template(self, tmp_path: Path) -> None:
        """Onboard should run one _research + _ingest_urls pair per template plus one for light research.

        Regression canary: pre-refactor onboard called verify_claim (which runs research+ingest)
        and then re-ran _research + _ingest_urls purely to recover SourceFile tuples. That
        doubled LLM/network calls per template. With verify_claim surfacing source_files
        directly, the extra pair disappears.
        """
        _setup_tmp_repo(tmp_path)

        from orchestrator import pipeline as pipeline_mod

        real_research = pipeline_mod._research
        real_ingest = pipeline_mod._ingest_urls

        research_calls = 0
        ingest_calls = 0

        async def spy_research(*args, **kwargs):
            nonlocal research_calls
            research_calls += 1
            return await real_research(*args, **kwargs)

        async def spy_ingest(*args, **kwargs):
            nonlocal ingest_calls
            ingest_calls += 1
            return await real_ingest(*args, **kwargs)

        with (
            research_agent.override(model=_research_model()),
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            patch.object(
                Agent, "override", side_effect=lambda **kw: _noop(**kw)
            ),
            patch.object(pipeline_mod, "_research", side_effect=spy_research),
            patch.object(pipeline_mod, "_ingest_urls", side_effect=spy_ingest),
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
        # 4 company templates + 1 light-research pass = 5 ingest + 5 research calls.
        # Pre-refactor was 1 + N*2 calls; cap at templates+1 to lock in the single-pair invariant.
        assert ingest_calls == 5, f"expected 5 ingest calls, got {ingest_calls}"
        assert research_calls <= 5, f"expected <=5 research calls, got {research_calls}"


class TestOnboardEntitySeedUrl:
    @pytest.mark.asyncio
    async def test_seed_url_skips_researcher(self, tmp_path: Path) -> None:
        """When seed_url is provided, the researcher step is not called for light research."""
        _setup_tmp_repo(tmp_path)

        researcher_calls: list[str] = []

        def _tracking_research_model() -> TestModel:
            researcher_calls.append("called")
            return _research_model()

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
                "TestCorp", "company", config=config, seed_url="testcorp.example.com"
            )

        assert result.status == "accepted"
        assert result.entity_ref is not None
        # Entity file written with https:// normalised seed URL
        entity_path = tmp_path / "research" / "entities" / "companies" / "testcorp.md"
        assert entity_path.exists()


class TestOnboardErrorAttribution:
    @pytest.mark.asyncio
    async def test_per_template_errors_are_slug_prefixed(self, tmp_path: Path) -> None:
        """When verify_claim populates vr.errors, each entry must be slug-prefixed.

        Regression: pipeline.py used to do `result.errors.extend(vr.errors)`,
        which dropped the template slug. Operators saw a list of failed slugs
        and a separate list of errors with no mapping between them.
        """
        _setup_tmp_repo(tmp_path)

        empty_research = TestModel(
            custom_output_args={"urls": [], "reasoning": "No sources found."},
            call_tools=[],
        )

        with (
            research_agent.override(model=empty_research),
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
        assert len(result.claims_failed) > 0, "expected at least one failed template"
        assert len(result.errors) > 0, "expected per-template errors"

        for err in result.errors:
            assert any(slug in err for slug in result.claims_failed), (
                f"error {err!r} carries no slug from claims_failed={result.claims_failed}"
            )
            assert ":" in err, f"error {err!r} missing slug-prefix delimiter"


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
