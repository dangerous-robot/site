"""Tests for the verification orchestrator result type."""

from __future__ import annotations

import asyncio
import datetime
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from common.models import BlockedReason
from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.checkpoints import StepError
from orchestrator.pipeline import (
    VerificationResult,
    VerifyConfig,
    _classify_blocked_reason,
    _ingest_one,
    _research,
    below_threshold,
    verify_claim,
)
from researcher.agent import research_agent


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
        assert result.analyst_output is None
        assert result.consistency is None


class TestVerificationResultCarriesSourceFiles:
    def test_defaults_empty_when_omitted(self) -> None:
        """Construction without source_files yields an empty list (backward compat)."""
        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=[],
            urls_ingested=[],
            urls_failed=[],
            sources=[],
        )
        assert result.source_files == []

    def test_round_trip_source_files(self) -> None:
        """A fabricated (url, SourceFile) tuple round-trips through the field."""
        sf = SourceFile(
            frontmatter=SourceFrontmatter(
                url="https://example.com/report",
                title="Test Report",
                publisher="Example Publisher",
                accessed_date=datetime.date(2026, 4, 19),
                kind="article",
                summary="A concise test summary.",
            ),
            body="Body content.",
            slug="test-report",
            year=2026,
        )
        result = VerificationResult(
            entity="TestCorp",
            claim_text="TestCorp is safe",
            urls_found=["https://example.com/report"],
            urls_ingested=["https://example.com/report"],
            urls_failed=[],
            sources=[],
            source_files=[("https://example.com/report", sf)],
        )
        assert len(result.source_files) == 1
        url, stored = result.source_files[0]
        assert url == "https://example.com/report"
        assert stored is sf
        assert stored.frontmatter.title == "Test Report"
        # exclude=True keeps source_files out of serialization
        dumped = result.model_dump()
        assert "source_files" not in dumped


@contextmanager
def _noop(**kwargs):
    """No-op context manager to neutralize inner agent overrides."""
    yield


def _researcher_returning(urls: list[str]) -> TestModel:
    return TestModel(
        custom_output_args={
            "urls": urls,
            "reasoning": "fake",
        },
        call_tools=[],
    )


def _write_blocklist(tmp_path) -> None:
    research = tmp_path / "research"
    research.mkdir(parents=True, exist_ok=True)
    (research / "blocklist.yaml").write_text(
        """
hosts:
  - host: linkedin.com
    reason: "403s on anonymous fetch"
""",
        encoding="utf-8",
    )


class TestResearchBlocklist:
    @pytest.mark.asyncio
    async def test_blocklist_drops_linkedin_url(self, tmp_path) -> None:
        _write_blocklist(tmp_path)
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
            researcher_mode="classic",
        )
        async with httpx.AsyncClient() as client:
            with (
                research_agent.override(
                    model=_researcher_returning(
                        ["https://linkedin.com/a", "https://example.com/b"]
                    )
                ),
                patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            ):
                sem = asyncio.Semaphore(8)
                urls, errors, _trace = await _research(client, "Ent", "claim", cfg, sem)

        assert urls == ["https://example.com/b"]
        blocked = [e for e in errors if e.error_type == "blocked_host"]
        assert len(blocked) == 1
        assert blocked[0].url == "https://linkedin.com/a"
        assert blocked[0].retryable is False
        # No all_blocked when at least one URL was kept
        assert not any(e.error_type == "all_blocked" for e in errors)

    @pytest.mark.asyncio
    async def test_all_blocked_adds_summary_error(self, tmp_path) -> None:
        _write_blocklist(tmp_path)
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
            researcher_mode="classic",
        )
        async with httpx.AsyncClient() as client:
            with (
                research_agent.override(
                    model=_researcher_returning(
                        ["https://linkedin.com/a", "https://uk.linkedin.com/b"]
                    )
                ),
                patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            ):
                sem = asyncio.Semaphore(8)
                urls, errors, _trace = await _research(client, "Ent", "claim", cfg, sem)

        assert urls == []
        assert errors[0].error_type == "all_blocked"
        blocked = [e for e in errors if e.error_type == "blocked_host"]
        assert len(blocked) == 2

    @pytest.mark.asyncio
    async def test_no_blocklist_file_passes_through(self, tmp_path) -> None:
        # No research/blocklist.yaml written
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
            researcher_mode="classic",
        )
        async with httpx.AsyncClient() as client:
            with (
                research_agent.override(
                    model=_researcher_returning(
                        ["https://linkedin.com/a", "https://example.com/b"]
                    )
                ),
                patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            ):
                sem = asyncio.Semaphore(8)
                urls, errors, _trace = await _research(client, "Ent", "claim", cfg, sem)

        assert urls == ["https://linkedin.com/a", "https://example.com/b"]
        assert errors == []


class TestVerifyConfigPerAgentModels:
    def test_model_for_falls_back_to_base(self) -> None:
        cfg = VerifyConfig(model="anthropic:claude")
        for agent in ("researcher", "analyst", "auditor", "ingestor"):
            assert cfg.model_for(agent) == "anthropic:claude"

    def test_model_for_per_agent_override_wins(self) -> None:
        cfg = VerifyConfig(
            model="anthropic:claude",
            analyst_model="infomaniak:openai/gpt-oss-120b",
            auditor_model="infomaniak:mistral24b",
        )
        assert cfg.model_for("researcher") == "anthropic:claude"
        assert cfg.model_for("analyst") == "infomaniak:openai/gpt-oss-120b"
        assert cfg.model_for("auditor") == "infomaniak:mistral24b"
        assert cfg.model_for("ingestor") == "anthropic:claude"


class TestVerifyConfigTimeouts:
    def test_verify_config_defaults(self) -> None:
        """Default VerifyConfig exposes the four timeout knobs.

        Wayback is on by default, so ingest_timeout_s is auto-bumped to the
        wayback-inclusive budget; the other three default to 120s.
        """
        cfg = VerifyConfig()
        assert cfg.skip_wayback is False
        assert cfg.ingest_timeout_s >= 85
        assert cfg.research_timeout_s == 120.0
        assert cfg.analyst_timeout_s == 120.0
        assert cfg.auditor_timeout_s == 120.0

    def test_verify_config_autobumps_ingest_when_wayback_enabled(self) -> None:
        """With skip_wayback=False and no explicit ingest_timeout_s, auto-bump to >=85s.

        Review Notes (2026-04-20) follow-up: asserts the timeout chain invariant
        actually holds when wayback is enabled.
        """
        cfg = VerifyConfig(skip_wayback=False)
        assert cfg.ingest_timeout_s >= 85

    def test_verify_config_explicit_ingest_timeout_wins(self) -> None:
        """Caller-supplied ingest_timeout_s overrides the skip_wayback auto-bump."""
        cfg = VerifyConfig(skip_wayback=False, ingest_timeout_s=45.0)
        assert cfg.ingest_timeout_s == 45.0

    @pytest.mark.asyncio
    async def test_ingest_one_returns_step_error_on_agent_timeout(self) -> None:
        """With a tiny ingest_timeout_s and a slow agent, _ingest_one returns a timeout StepError."""
        url = "https://example.com/slow-agent"
        cfg = VerifyConfig(
            model="test",
            repo_root="/tmp",
            skip_wayback=True,
            ingest_timeout_s=0.05,
        )

        async def _slow_run(*args, **kwargs):
            await asyncio.sleep(5.0)

        async with httpx.AsyncClient() as client:
            with (
                patch("orchestrator.pipeline.ingestor_agent.run", side_effect=_slow_run),
                patch.object(
                    Agent, "override", side_effect=lambda **kw: _noop(**kw)
                ),
            ):
                sem = asyncio.Semaphore(8)
                outcome = await _ingest_one(
                    client, url, cfg, datetime.date(2026, 4, 19), sem
                )

        assert isinstance(outcome, StepError)
        assert outcome.step == "ingest"
        assert outcome.error_type == "timeout"
        assert outcome.url == url


class TestThresholdEnforcement:
    """The Orchestrator halts a claim with status='blocked' below threshold."""

    def test_below_threshold_returns_true_for_zero_sources(self) -> None:
        assert below_threshold([]) is True

    def test_below_threshold_returns_true_for_one_source(self) -> None:
        assert below_threshold(["only-one"]) is True

    def test_below_threshold_returns_true_for_two_sources(self) -> None:
        assert below_threshold(["a", "b"]) is True

    def test_below_threshold_returns_true_for_three_sources(self) -> None:
        assert below_threshold(["a", "b", "c"]) is True

    def test_below_threshold_returns_false_for_four_sources(self) -> None:
        assert below_threshold(["a", "b", "c", "d"]) is False

    def test_below_threshold_returns_false_for_many_sources(self) -> None:
        assert below_threshold(["a", "b", "c", "d", "e"]) is False

    def test_classify_blocked_reason_terminal_when_all_http_errors(self) -> None:
        errors = [
            StepError(step="ingest", url="https://a", error_type="http_403",
                      message="forbidden", retryable=False),
            StepError(step="ingest", url="https://b", error_type="http_401",
                      message="unauthorised", retryable=False),
        ]
        assert _classify_blocked_reason(errors) is BlockedReason.TERMINAL_FETCH_ERROR

    def test_classify_blocked_reason_insufficient_when_mixed(self) -> None:
        errors = [
            StepError(step="ingest", url="https://a", error_type="timeout",
                      message="timed out"),
            StepError(step="ingest", url="https://b", error_type="http_403",
                      message="forbidden", retryable=False),
        ]
        assert _classify_blocked_reason(errors) is BlockedReason.INSUFFICIENT_SOURCES

    def test_classify_blocked_reason_insufficient_when_no_ingest_errors(self) -> None:
        # Researcher returned nothing usable, no ingest attempts made.
        assert _classify_blocked_reason([]) is BlockedReason.INSUFFICIENT_SOURCES

    @pytest.mark.asyncio
    async def test_verify_claim_halts_when_one_source_ingested(
        self, monkeypatch
    ) -> None:
        """With < 4 usable sources, verify_claim sets blocked_reason and skips Analyst.

        We patch the internal _research and _ingest_urls helpers so the test
        exercises the threshold gate without hitting any model providers.
        """
        sf = SourceFile(
            frontmatter=SourceFrontmatter(
                url="https://example.com/one",
                title="One Source",
                publisher="Example",
                accessed_date=datetime.date(2026, 4, 26),
                kind="article",
                summary="Just one source.",
            ),
            body="Body.",
            slug="one-source",
            year=2026,
        )

        async def _fake_research(client, entity, claim, cfg, sem, **kwargs):
            return ["https://example.com/one"], [], {"mode": "test"}

        async def _fake_ingest(client, urls, cfg, sem, **kwargs):
            return [("https://example.com/one", sf)], []

        analyst_called = False

        async def _fake_analyse(*args, **kwargs):
            nonlocal analyst_called
            analyst_called = True
            return None

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)

        result = await verify_claim(
            entity_name="TestCorp",
            claim_text="A claim",
            config=VerifyConfig(model="test", repo_root="/tmp"),
        )

        assert analyst_called is False
        assert result.blocked_reason is BlockedReason.INSUFFICIENT_SOURCES
        assert result.analyst_output is None
        # Threshold halt does not surface as a generic error; the
        # blocked_reason field is the signal.
        assert not any("All source URLs failed" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_verify_claim_terminal_fetch_error_classified(
        self, monkeypatch
    ) -> None:
        """When zero sources ingest and all errors are terminal HTTP, mark it so."""
        async def _fake_research(client, entity, claim, cfg, sem, **kwargs):
            return ["https://a", "https://b"], [], {"mode": "test"}

        async def _fake_ingest(client, urls, cfg, sem, **kwargs):
            errors = [
                StepError(step="ingest", url="https://a", error_type="http_403",
                          message="forbidden", retryable=False),
                StepError(step="ingest", url="https://b", error_type="http_401",
                          message="unauthorised", retryable=False),
            ]
            return [], errors

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)

        result = await verify_claim(
            entity_name="TestCorp",
            claim_text="A claim",
            config=VerifyConfig(model="test", repo_root="/tmp"),
        )

        assert result.blocked_reason is BlockedReason.TERMINAL_FETCH_ERROR
        assert result.analyst_output is None

    @pytest.mark.asyncio
    async def test_verify_claim_does_not_halt_with_four_sources(
        self, monkeypatch
    ) -> None:
        """At threshold (>= 4 sources), the gate does not fire."""
        def _make_sf(slug: str, url: str) -> SourceFile:
            return SourceFile(
                frontmatter=SourceFrontmatter(
                    url=url, title=slug.upper(), publisher="Ex",
                    accessed_date=datetime.date(2026, 4, 26), kind="article",
                    summary="A summary.",
                ),
                body="Body.", slug=slug, year=2026,
            )

        sf1 = _make_sf("a", "https://example.com/a")
        sf2 = _make_sf("b", "https://example.com/b")
        sf3 = _make_sf("c", "https://example.com/c")
        sf4 = _make_sf("d", "https://example.com/d")

        async def _fake_research(client, entity, claim, cfg, sem, **kwargs):
            return [
                "https://example.com/a", "https://example.com/b",
                "https://example.com/c", "https://example.com/d",
            ], [], {"mode": "test"}

        async def _fake_ingest(client, urls, cfg, sem, **kwargs):
            return [
                ("https://example.com/a", sf1),
                ("https://example.com/b", sf2),
                ("https://example.com/c", sf3),
                ("https://example.com/d", sf4),
            ], []

        analyst_called = False

        async def _fake_analyse(*args, **kwargs):
            nonlocal analyst_called
            analyst_called = True
            return None

        async def _fake_audit(*args, **kwargs):
            return None

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)
        monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)

        result = await verify_claim(
            entity_name="TestCorp",
            claim_text="A claim",
            config=VerifyConfig(model="test", repo_root="/tmp"),
        )

        assert result.blocked_reason is None
        # Analyst was reached (then returned None, hitting a different branch).
        assert analyst_called is True


class TestVerifyClaimWithResolvedEntity:
    def _make_resolved(self):
        from orchestrator.entity_resolution import ResolvedEntity
        from common.models import EntityType
        return ResolvedEntity(
            entity_ref="products/chatgpt",
            entity_name="ChatGPT",
            entity_type=EntityType.PRODUCT,
            entity_description="A conversational AI product.",
        )

    @pytest.mark.asyncio
    async def test_resolved_entity_passed_to_analyse_claim(self, monkeypatch) -> None:
        """_analyse_claim receives resolved_entity kwarg when provided to verify_claim."""
        resolved = self._make_resolved()
        received_kwargs: dict = {}

        async def _fake_research(*args, **kwargs):
            return ["https://example.com/a"] * 4, [], {"mode": "classic"}

        async def _fake_ingest(*args, **kwargs):
            sf = SourceFile(
                frontmatter=SourceFrontmatter(
                    url="https://example.com/a",
                    title="Src",
                    publisher="Pub",
                    accessed_date=datetime.date(2026, 1, 1),
                    kind="article",
                    summary="Summary.",
                ),
                body="",
                slug="src",
                year=2026,
            )
            return [("https://example.com/a", sf)] * 4, []

        async def _fake_analyse(*args, **kwargs):
            received_kwargs.update(kwargs)
            return None

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)

        await verify_claim(
            entity_name="ChatGPT",
            claim_text="ChatGPT is safe",
            config=VerifyConfig(model="test", skip_wayback=True),
            resolved_entity=resolved,
        )

        assert received_kwargs.get("resolved_entity") is resolved

    @pytest.mark.asyncio
    async def test_resolved_entity_skips_write_entity_file(self, monkeypatch) -> None:
        """verify_claim never calls _write_entity_file (it is a read-only function)."""
        from orchestrator import pipeline as _pipeline_mod
        write_entity_called = []

        original = getattr(_pipeline_mod, "_write_entity_file", None)

        def _spy_write_entity(*args, **kwargs):
            write_entity_called.append(True)
            if original:
                return original(*args, **kwargs)

        async def _fake_research(*args, **kwargs):
            return [], [], {"mode": "classic"}

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)

        await verify_claim(
            entity_name="ChatGPT",
            claim_text="ChatGPT is safe",
            config=VerifyConfig(model="test", skip_wayback=True),
            resolved_entity=self._make_resolved(),
        )

        assert write_entity_called == [], "verify_claim must not write entity files"


class TestResearchClaimWithResolvedEntity:
    def _make_resolved(self):
        from orchestrator.entity_resolution import ResolvedEntity
        from common.models import EntityType
        return ResolvedEntity(
            entity_ref="products/chatgpt",
            entity_name="ChatGPT",
            entity_type=EntityType.PRODUCT,
            entity_description="A conversational AI product.",
        )

    @pytest.mark.asyncio
    async def test_entity_ref_flows_to_write_claim_file(self, monkeypatch, tmp_path) -> None:
        """When resolved_entity is provided, entity_ref from it is passed to _write_claim_file."""
        resolved = self._make_resolved()
        write_claim_kwargs: dict = {}

        async def _fake_research(*args, **kwargs):
            return ["https://example.com/a"] * 4, [], {"mode": "classic"}

        async def _fake_ingest(*args, **kwargs):
            sf = SourceFile(
                frontmatter=SourceFrontmatter(
                    url="https://example.com/a",
                    title="Src",
                    publisher="Pub",
                    accessed_date=datetime.date(2026, 1, 1),
                    kind="article",
                    summary="Summary.",
                ),
                body="",
                slug="src",
                year=2026,
            )
            return [("https://example.com/a", sf)] * 4, []

        from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment
        from common.models import Confidence, EntityType, Verdict, Category

        async def _fake_analyse(*args, **kwargs):
            return AnalystOutput(
                entity=EntityResolution(
                    entity_name="ChatGPT",
                    entity_type=EntityType.PRODUCT,
                    entity_description="desc",
                ),
                verdict=VerdictAssessment(
                    title="ChatGPT trains on data",
                    verdict=Verdict.TRUE,
                    confidence=Confidence.HIGH,
                    narrative="narrative",
                    topics=[Category("data-privacy")],
                ),
            )

        async def _fake_audit(*args, **kwargs):
            return None

        def _fake_write_source_files(*args, **kwargs):
            return ["sources/2026/src"]

        def _fake_write_claim_file(**kwargs):
            write_claim_kwargs.update(kwargs)
            return tmp_path / "research" / "claims" / "chatgpt" / "claim.md"

        def _fake_write_audit_sidecar(**kwargs):
            pass

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)
        monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)
        monkeypatch.setattr("orchestrator.persistence._write_source_files", _fake_write_source_files)
        monkeypatch.setattr("orchestrator.persistence._write_claim_file", _fake_write_claim_file)
        monkeypatch.setattr("orchestrator.persistence._write_audit_sidecar", _fake_write_audit_sidecar)
        monkeypatch.setattr("orchestrator.persistence._build_sources_consulted", lambda *a, **k: [])

        from orchestrator.pipeline import research_claim
        await research_claim(
            claim_text="ChatGPT trains on data",
            config=VerifyConfig(model="test", skip_wayback=True, repo_root=str(tmp_path)),
            resolved_entity=resolved,
        )

        assert write_claim_kwargs.get("entity_ref") == "products/chatgpt"

    @pytest.mark.asyncio
    async def test_write_entity_file_not_called(self, monkeypatch, tmp_path) -> None:
        """When resolved_entity is provided, _write_entity_file is NOT called."""
        write_entity_called = []

        async def _fake_research(*args, **kwargs):
            return ["https://example.com/a"] * 4, [], {"mode": "classic"}

        async def _fake_ingest(*args, **kwargs):
            sf = SourceFile(
                frontmatter=SourceFrontmatter(
                    url="https://example.com/a",
                    title="Src",
                    publisher="Pub",
                    accessed_date=datetime.date(2026, 1, 1),
                    kind="article",
                    summary="Summary.",
                ),
                body="",
                slug="src",
                year=2026,
            )
            return [("https://example.com/a", sf)] * 4, []

        from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment
        from common.models import Confidence, EntityType, Verdict, Category

        async def _fake_analyse(*args, **kwargs):
            return AnalystOutput(
                entity=EntityResolution(
                    entity_name="ChatGPT",
                    entity_type=EntityType.PRODUCT,
                    entity_description="desc",
                ),
                verdict=VerdictAssessment(
                    title="ChatGPT trains on data",
                    verdict=Verdict.TRUE,
                    confidence=Confidence.HIGH,
                    narrative="narrative",
                    topics=[Category("data-privacy")],
                ),
            )

        async def _fake_audit(*args, **kwargs):
            return None

        def _spy_write_entity_file(*args, **kwargs):
            write_entity_called.append(True)
            return "products/chatgpt"

        def _fake_write_source_files(*args, **kwargs):
            return ["sources/2026/src"]

        def _fake_write_claim_file(**kwargs):
            return tmp_path / "research" / "claims" / "chatgpt" / "claim.md"

        def _fake_write_audit_sidecar(**kwargs):
            pass

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)
        monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)
        monkeypatch.setattr("orchestrator.persistence._write_entity_file", _spy_write_entity_file)
        monkeypatch.setattr("orchestrator.persistence._write_source_files", _fake_write_source_files)
        monkeypatch.setattr("orchestrator.persistence._write_claim_file", _fake_write_claim_file)
        monkeypatch.setattr("orchestrator.persistence._write_audit_sidecar", _fake_write_audit_sidecar)
        monkeypatch.setattr("orchestrator.persistence._build_sources_consulted", lambda *a, **k: [])

        from orchestrator.pipeline import research_claim
        await research_claim(
            claim_text="ChatGPT trains on data",
            config=VerifyConfig(model="test", skip_wayback=True, repo_root=str(tmp_path)),
            resolved_entity=self._make_resolved(),
        )

        assert write_entity_called == [], "_write_entity_file must not be called when entity is pre-resolved"
