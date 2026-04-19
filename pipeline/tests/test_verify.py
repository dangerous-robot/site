"""Tests for the end-to-end verification orchestrator."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from common.models import Category, Confidence, Verdict, VerdictSeverity
from verify.drafter import ClaimDraft, drafter_agent
from verify.orchestrator import VerificationResult, VerifyConfig
from verify.researcher import ResearchResult, research_agent


class TestResearchAgent:
    @pytest.mark.asyncio
    async def test_output_type(self) -> None:
        assert research_agent.output_type is ResearchResult

    @pytest.mark.asyncio
    async def test_produces_urls(self) -> None:
        with research_agent.override(
            model=TestModel(
                custom_output_args={
                    "urls": ["https://example.com/report"],
                    "reasoning": "Found a relevant report.",
                },
                call_tools=[],
            )
        ):
            from verify.researcher import ResearchDeps
            import httpx

            async with httpx.AsyncClient() as client:
                deps = ResearchDeps(http_client=client)
                result = await research_agent.run("test query", deps=deps)

            assert isinstance(result.output, ResearchResult)
            assert len(result.output.urls) == 1
            assert result.output.urls[0] == "https://example.com/report"


class TestDrafterAgent:
    @pytest.mark.asyncio
    async def test_output_type(self) -> None:
        assert drafter_agent.output_type is ClaimDraft

    @pytest.mark.asyncio
    async def test_produces_draft(self) -> None:
        with drafter_agent.override(
            model=TestModel(
                custom_output_args={
                    "title": "Test claim about renewable energy",
                    "category": "environmental-impact",
                    "verdict": "mixed",
                    "confidence": "medium",
                    "narrative": "The evidence is mixed on this claim.",
                },
            )
        ):
            from verify.drafter import DrafterDeps, build_drafter_prompt

            deps = DrafterDeps()
            prompt = build_drafter_prompt("TestCorp", "TestCorp uses renewables", [])
            result = await drafter_agent.run(prompt, deps=deps)

            draft = result.output
            assert isinstance(draft, ClaimDraft)
            assert draft.verdict == Verdict.MIXED
            assert draft.confidence == Confidence.MEDIUM
            assert draft.category == Category.ENVIRONMENTAL_IMPACT


class TestDrafterPrompt:
    def test_includes_entity_and_claim(self) -> None:
        from verify.drafter import build_drafter_prompt

        prompt = build_drafter_prompt(
            "Ecosia",
            "Ecosia runs on renewable energy",
            [{"title": "Report", "publisher": "Org", "summary": "A report", "body": "Details"}],
        )
        assert "Ecosia" in prompt
        assert "Ecosia runs on renewable energy" in prompt
        assert "Report" in prompt
        assert "Org" in prompt

    def test_handles_no_sources(self) -> None:
        from verify.drafter import build_drafter_prompt

        prompt = build_drafter_prompt("X", "Claim", [])
        assert "No sources were found" in prompt


class TestVerificationResult:
    def test_construction(self) -> None:
        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=["https://example.com"],
            urls_ingested=["https://example.com"],
            urls_failed=[],
            sources=[],
        )
        assert result.entity == "TestCorp"
        assert result.draft is None
        assert result.consistency is None
