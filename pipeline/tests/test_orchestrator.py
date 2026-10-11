"""Tests for the verification orchestrator result type."""

from __future__ import annotations

import asyncio
import datetime
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from pydantic_ai import Agent

from common.models import BlockedReason
from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.checkpoints import StepError
from orchestrator.pipeline import (
    VerificationResult,
    VerifyConfig,
    _apply_blocklist_cap,
    _classify_blocked_reason,
    _ingest_one,
    _record_threshold_block,
    _summarize_terminal_fetch,
    below_threshold,
    verify_claim,
)


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


def _ro(urls=None, errors=None, trace=None):
    from researcher.decomposed import ResearchOutput
    return ResearchOutput(
        urls=list(urls or []),
        errors=list(errors or []),
        trace=dict(trace or {"mode": "decomposed"}),
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
    """`_apply_blocklist_cap` is the join point between researcher output and
    the orchestrator. These tests exercise it directly with raw URL lists."""

    def test_blocklist_drops_linkedin_url(self, tmp_path) -> None:
        _write_blocklist(tmp_path)
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        urls, errors = _apply_blocklist_cap(
            ["https://linkedin.com/a", "https://example.com/b"], cfg
        )
        assert urls == ["https://example.com/b"]
        blocked = [e for e in errors if e.error_type == "blocked_host"]
        assert len(blocked) == 1
        assert blocked[0].url == "https://linkedin.com/a"
        assert blocked[0].retryable is False
        # No all_blocked when at least one URL was kept
        assert not any(e.error_type == "all_blocked" for e in errors)

    def test_all_blocked_adds_summary_error(self, tmp_path) -> None:
        _write_blocklist(tmp_path)
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        urls, errors = _apply_blocklist_cap(
            ["https://linkedin.com/a", "https://uk.linkedin.com/b"], cfg
        )
        assert urls == []
        assert errors[0].error_type == "all_blocked"
        blocked = [e for e in errors if e.error_type == "blocked_host"]
        assert len(blocked) == 2

    def test_no_blocklist_file_passes_through(self, tmp_path) -> None:
        # No research/blocklist.yaml written
        cfg = VerifyConfig(
            model="test",
            max_sources=4,
            skip_wayback=True,
            repo_root=str(tmp_path),
        )
        urls, errors = _apply_blocklist_cap(
            ["https://linkedin.com/a", "https://example.com/b"], cfg
        )
        assert urls == ["https://linkedin.com/a", "https://example.com/b"]
        assert errors == []

    @pytest.mark.asyncio
    async def test_pool_cut_keeps_a_thin_sub_questions_low_ranked_urls(self, monkeypatch, tmp_path) -> None:
        """40 kept URLs, a pool of 32, and the only sq2 URLs ranked 33-40."""
        from common.models import SubQuestion
        from orchestrator.pipeline import _research
        from researcher.decomposed import ResearchOutput

        urls = [f"https://example.com/{i}" for i in range(1, 41)]
        addresses = {u: (["sq2"] if i >= 32 else [f"sq{1 + 2 * (i % 2)}"]) for i, u in enumerate(urls)}

        async def _fake_decomposed(*args, **kwargs):
            return ResearchOutput(
                urls=list(urls), url_addresses=dict(addresses),
                sub_questions=[SubQuestion(id=s, question=f"{s}?", rationale="r") for s in ("sq1", "sq2", "sq3")],
                trace={"mode": "test"},
            )

        monkeypatch.setattr("researcher.decomposed.decomposed_research", _fake_decomposed)
        cfg = VerifyConfig(model="test", skip_wayback=True, repo_root=str(tmp_path), candidate_pool_size=32)
        out = await _research(None, "Acme", "A claim", cfg, asyncio.Semaphore(1))

        assert len(out.urls) == 32
        assert [u for u in out.urls if "sq2" in out.url_addresses[u]] == urls[32:34]
        # Survivors keep their rank order.
        assert out.urls == [u for u in urls if u in set(out.urls)]

    def test_pool_cut_keeps_a_high_ranked_url_that_addresses_no_sub_question(self, tmp_path) -> None:
        from orchestrator.pipeline import _coverage_pool

        urls = [f"https://example.com/{i}" for i in range(1, 11)]
        addresses = {u: ["sq1"] for u in urls[1:8]} | {u: ["sq2"] for u in urls[8:]}

        pool = _coverage_pool(urls, addresses, ["sq1", "sq2"], 5)

        assert pool == [urls[0], urls[1], urls[2], urls[8], urls[9]]


_OWN_POST = (
    "https://www.linkedin.com/posts/earthly-insight_responsibility-in-the-age-of-ai-turning-"
    "activity-7417951275817918464-H7h7"
)
_OTHER_POST = "https://www.linkedin.com/posts/earth-insight_other-activity-2"
_SITE = "https://earthlyinsight.com/about"


async def _blocklist_research(tmp_path, monkeypatch, bodies, resolved=True):
    """Run ``_research`` on Earthly Insight's pool with a linkedin.com blocklist."""
    from common.models import EntityType, SubQuestion
    from orchestrator.entity_resolution import ResolvedEntity
    from orchestrator.pipeline import _research
    from researcher.decomposed import ResearchOutput

    _write_blocklist(tmp_path)
    urls = [_SITE, _OWN_POST, _OTHER_POST]

    async def _fake_decomposed(*args, **kwargs):
        return ResearchOutput(
            urls=list(urls), url_addresses={u: ["sq1"] for u in urls},
            sub_questions=[SubQuestion(id="sq1", question="q?", rationale="r")],
            prefetched_bodies=dict(bodies), trace={"mode": "test"},
        )

    monkeypatch.setattr("researcher.decomposed.decomposed_research", _fake_decomposed)
    entity = ResolvedEntity(
        entity_ref="companies/earthly-insight", entity_name="Earthly Insight",
        entity_type=EntityType.COMPANY, entity_description="",
        website="https://earthlyinsight.com",
    ) if resolved else None
    cfg = VerifyConfig(model="test", skip_wayback=True, repo_root=str(tmp_path))
    return await _research(
        None, "Earthly Insight", "A claim", cfg, asyncio.Semaphore(1), resolved_entity=entity
    )


class TestBlocklistSparesEntityProfilePost:
    @pytest.mark.asyncio
    async def test_entity_post_with_page_text_passes_blocklist(self, tmp_path, monkeypatch) -> None:
        out = await _blocklist_research(
            tmp_path, monkeypatch, {_OWN_POST: "We run on renewable power.", _OTHER_POST: "Other text."}
        )
        assert out.urls == [_SITE, _OWN_POST]
        assert out.prefetched_bodies == {_OWN_POST: "We run on renewable power."}
        assert [e.url for e in out.errors if e.error_type == "blocked_host"] == [_OTHER_POST]
        spared = out.trace["blocklist_spared"]
        assert [s["url"] for s in spared] == [_OWN_POST]
        assert "linkedin.com" in spared[0]["reason"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bodies", [{}, {_OWN_POST: "  \n"}], ids=["no-body", "blank-body"])
    async def test_entity_post_without_page_text_drops(self, tmp_path, monkeypatch, bodies) -> None:
        out = await _blocklist_research(tmp_path, monkeypatch, bodies)
        assert out.urls == [_SITE]
        assert [e.url for e in out.errors if e.error_type == "blocked_host"] == [_OWN_POST, _OTHER_POST]
        assert "blocklist_spared" not in out.trace

    @pytest.mark.asyncio
    async def test_third_party_linkedin_post_with_page_text_drops(self, tmp_path, monkeypatch) -> None:
        out = await _blocklist_research(tmp_path, monkeypatch, {_OTHER_POST: "Other text."})
        assert _OTHER_POST not in out.urls
        assert _OTHER_POST in [e.url for e in out.errors if e.error_type == "blocked_host"]

    @pytest.mark.asyncio
    async def test_no_resolved_entity_spares_nothing(self, tmp_path, monkeypatch) -> None:
        out = await _blocklist_research(
            tmp_path, monkeypatch, {_OWN_POST: "We run on renewable power."}, resolved=False
        )
        assert out.urls == [_SITE]
        assert "blocklist_spared" not in out.trace


class TestVerifyConfigPerAgentModels:
    def test_model_for_falls_back_to_base(self) -> None:
        cfg = VerifyConfig(model="anthropic:claude")
        for agent in ("researcher", "analyst", "auditor", "ingestor"):
            assert cfg.model_for(agent) == "anthropic:claude"

    def test_model_for_per_agent_override_wins(self) -> None:
        cfg = VerifyConfig(
            model="anthropic:claude",
            analyst_model="infomaniak:swiss-ai/Apertus-70B-Instruct-2509",
            auditor_model="infomaniak:mistral24b",
        )
        assert cfg.model_for("researcher") == "anthropic:claude"
        assert cfg.model_for("analyst") == "infomaniak:swiss-ai/Apertus-70B-Instruct-2509"
        assert cfg.model_for("auditor") == "infomaniak:mistral24b"
        assert cfg.model_for("ingestor") == "anthropic:claude"


class TestVerifyConfigResearchOrigins:
    """Cover the activation list added for source-pool-expansion-tier1.md."""

    def test_default_includes_tavily_and_arxiv(self) -> None:
        cfg = VerifyConfig()
        assert cfg.research_origins == ["tavily", "arxiv"]

    def test_explicit_list_round_trips(self) -> None:
        cfg = VerifyConfig(research_origins=["brave", "arxiv"])
        assert cfg.research_origins == ["brave", "arxiv"]

    def test_empty_list_is_valid(self) -> None:
        """No 'must include a backend' guard - empty list permitted for testing."""
        cfg = VerifyConfig(research_origins=[])
        assert cfg.research_origins == []

    def test_default_is_not_shared_mutable(self) -> None:
        """field(default_factory=...) gives each instance its own list."""
        cfg_a = VerifyConfig()
        cfg_b = VerifyConfig()
        assert cfg_a.research_origins is not cfg_b.research_origins
        cfg_a.research_origins.append("edgar")
        assert cfg_b.research_origins == ["tavily", "arxiv"]


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

    def test_summarize_terminal_fetch_single_status(self) -> None:
        errors = [
            StepError(step="ingest", url=f"https://h{i}", error_type="http_403",
                      message="forbidden", retryable=False)
            for i in range(4)
        ]
        assert _summarize_terminal_fetch(errors) == "4 URLs (4× http_403)"

    def test_summarize_terminal_fetch_multiple_statuses_sorted_desc(self) -> None:
        errors = [
            StepError(step="ingest", url="https://a", error_type="http_403",
                      message="forbidden", retryable=False),
            StepError(step="ingest", url="https://b", error_type="http_404",
                      message="not found", retryable=False),
            StepError(step="ingest", url="https://c", error_type="http_403",
                      message="forbidden", retryable=False),
            StepError(step="ingest", url="https://d", error_type="http_403",
                      message="forbidden", retryable=False),
        ]
        # 3× http_403 dominates; comes first.
        assert _summarize_terminal_fetch(errors) == "4 URLs (3× http_403, 1× http_404)"

    def test_summarize_terminal_fetch_ignores_non_ingest(self) -> None:
        errors = [
            StepError(step="ingest", url="https://a", error_type="http_403",
                      message="forbidden", retryable=False),
            StepError(step="research", url=None, error_type="planner_failed",
                      message="oops"),
        ]
        assert _summarize_terminal_fetch(errors) == "1 URLs (1× http_403)"

    def test_record_threshold_block_inserts_histogram_for_terminal(self) -> None:
        result = VerificationResult(
            entity="T", claim_text="c", urls_found=[], urls_ingested=[],
            urls_failed=[], sources=[],
        )
        result.errors.append("research planner timed out")
        ingest_errors = [
            StepError(step="ingest", url=f"https://h{i}", error_type="http_403",
                      message="forbidden", retryable=False)
            for i in range(3)
        ]
        _record_threshold_block(result, ingest_errors)
        assert result.blocked_reason is BlockedReason.TERMINAL_FETCH_ERROR
        # Histogram is inserted at index 0 so the label builder picks it up.
        assert result.errors[0] == "3 URLs (3× http_403)"
        assert "research planner timed out" in result.errors

    def test_record_threshold_block_no_histogram_for_insufficient(self) -> None:
        result = VerificationResult(
            entity="T", claim_text="c", urls_found=[], urls_ingested=[],
            urls_failed=[], sources=[],
        )
        ingest_errors = [
            StepError(step="ingest", url="https://a", error_type="timeout",
                      message="timed out"),
        ]
        _record_threshold_block(result, ingest_errors)
        assert result.blocked_reason is BlockedReason.INSUFFICIENT_SOURCES
        # Insufficient_sources path leaves errors untouched.
        assert result.errors == []

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
            return _ro(urls=["https://example.com/one"], trace={"mode": "test"})

        async def _fake_ingest(client, urls, cfg, sem, **kwargs):
            return [("https://example.com/one", sf)], []

        analyst_called = False

        async def _fake_analyse(*args, **kwargs):
            nonlocal analyst_called
            analyst_called = True
            return None, None

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
            return _ro(urls=["https://a", "https://b"], trace={"mode": "test"})

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
            return _ro(urls=[
                "https://example.com/a", "https://example.com/b",
                "https://example.com/c", "https://example.com/d",
            ], trace={"mode": "test"})

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
            return None, None

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
            return _ro(urls=["https://example.com/a"] * 4)

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
            return None, None

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
            return _ro()

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
            return _ro(urls=["https://example.com/a"] * 4)

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
        from common.models import Confidence, EntityType, Verdict, Category, VerificationLevel

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
                    verification_level=VerificationLevel.PARTIALLY_VERIFIED,
                    seo_title="ChatGPT trains on data",
                ),
            ), None

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
            return _ro(urls=["https://example.com/a"] * 4)

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
        from common.models import Confidence, EntityType, Verdict, Category, VerificationLevel

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
                    verification_level=VerificationLevel.PARTIALLY_VERIFIED,
                    seo_title="ChatGPT trains on data",
                ),
            ), None

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


@pytest.mark.asyncio
async def test_rejected_review_names_the_real_flag_reason(monkeypatch) -> None:
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment
    from auditor.models import ComparisonResult
    from common.models import (
        Category, Confidence, EntityType, Verdict, VerdictSeverity, VerificationLevel,
    )
    from orchestrator.checkpoints import AutoApproveCheckpointHandler

    sf = SourceFile(
        frontmatter=SourceFrontmatter(
            url="https://example.com/a", title="Src", publisher="Pub",
            accessed_date=datetime.date(2026, 1, 1), kind="article", summary="Summary.",
        ),
        body="", slug="src", year=2026,
    )

    async def _fake_research(*args, **kwargs):
        return _ro(urls=["https://example.com/a"] * 4)

    async def _fake_ingest(*args, **kwargs):
        return [("https://example.com/a", sf)] * 4, []

    async def _fake_analyse(*args, **kwargs):
        return AnalystOutput(
            entity=EntityResolution(entity_name="X", entity_type=EntityType.PRODUCT, entity_description="d"),
            verdict=VerdictAssessment(
                title="X claim", verdict=Verdict.TRUE, confidence=Confidence.HIGH,
                narrative="n", topics=[Category("data-privacy")],
                verification_level=VerificationLevel.PARTIALLY_VERIFIED, seo_title="X claim",
            ),
        ), None

    async def _fake_audit(*args, **kwargs):
        return ComparisonResult(
            claim_id="x/claim", claim_file="research/claims/x/claim.md",
            primary_verdict=Verdict.TRUE, assessed_verdict=Verdict.TRUE,
            primary_confidence=Confidence.HIGH, assessed_confidence=Confidence.HIGH,
            reasoning="r", evidence_gaps=["g1", "g2"],
            verdict_agrees=True, confidence_agrees=True,
            verdict_severity=VerdictSeverity.MATCH, needs_review=True,
        )

    class _Reject(AutoApproveCheckpointHandler):
        async def review_disagreement(self, comparison):
            return False

    monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
    monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
    monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)
    monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)

    result = await verify_claim(
        entity_name="X", claim_text="X claim",
        config=VerifyConfig(model="test", repo_root="/tmp", skip_wayback=True),
        checkpoint=_Reject(),
    )

    assert "Flagged for human review: 2+ evidence gaps" in result.errors
    assert not any("disagree" in e for e in result.errors)


class TestAuditorGradedStatement:
    """Which statement the auditor grades, and when the audit is skipped."""

    @staticmethod
    def _template():
        from common.templates import TemplateRecord
        return TemplateRecord(
            slug="corporate-structure", text="COMPANY has STRUCTURE corporate structure",
            entity_type="company", topics=["industry-analysis"], core=True,
            vocabulary={"STRUCTURE": ["publicly-traded", "privately-held"]},
        )

    @staticmethod
    def _patch_pipeline(monkeypatch, title: str, audit_calls: list):
        from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment
        from common.models import Category, Confidence, EntityType, Verdict, VerificationLevel

        sf = SourceFile(
            frontmatter=SourceFrontmatter(
                url="https://example.com/a", title="Src", publisher="Pub",
                accessed_date=datetime.date(2026, 1, 1), kind="article", summary="Summary.",
            ),
            body="", slug="src", year=2026,
        )

        async def _fake_research(*args, **kwargs):
            return _ro(urls=["https://example.com/a"] * 4)

        async def _fake_ingest(*args, **kwargs):
            return [("https://example.com/a", sf)] * 4, []

        async def _fake_analyse(*args, **kwargs):
            return AnalystOutput(
                entity=EntityResolution(entity_name="Acme", entity_type=EntityType.COMPANY, entity_description="d"),
                verdict=VerdictAssessment(
                    title=title, verdict=Verdict.TRUE, confidence=Confidence.HIGH,
                    narrative="n", topics=[Category("industry-analysis")],
                    verification_level=VerificationLevel.PARTIALLY_VERIFIED, seo_title="Acme claim",
                ),
            ), None

        async def _fake_audit(entity_name, statement, *args, **kwargs):
            audit_calls.append(statement)
            return None

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)
        monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)

    def test_vocabulary_claim_grades_the_resolved_title(self) -> None:
        from common.templates import render_claim_text
        from orchestrator.pipeline import _graded_statement

        template = self._template()
        claim_text = render_claim_text(template, "Acme")
        title = "Acme has privately-held corporate structure"
        assert _graded_statement(template, "Acme", claim_text, title) == title

    @pytest.mark.parametrize("title", [
        "Acme has state-owned corporate structure",
        "Acme has one of (publicly-traded, privately-held) corporate structure",
    ])
    def test_title_failing_the_template_skips_the_audit(self, title: str) -> None:
        from common.templates import render_claim_text
        from orchestrator.pipeline import _graded_statement

        template = self._template()
        claim_text = render_claim_text(template, "Acme")
        assert _graded_statement(template, "Acme", claim_text, title) is None

    def test_free_text_with_one_of_keeps_the_operator_text(self) -> None:
        from orchestrator.pipeline import _graded_statement

        claim = "Acme is one of (if not the) largest AI labs"
        assert _graded_statement(None, "Acme", claim, "Acme ranks among the largest labs") == claim

    @pytest.mark.asyncio
    async def test_verify_claim_skips_auditor_and_review_on_failing_title(self, monkeypatch) -> None:
        from common.templates import render_claim_text
        from orchestrator.checkpoints import AutoApproveCheckpointHandler

        audit_calls: list[str] = []
        review_calls: list = []
        self._patch_pipeline(monkeypatch, "Acme has state-owned corporate structure", audit_calls)

        class _Recording(AutoApproveCheckpointHandler):
            async def review_disagreement(self, comparison):
                review_calls.append(comparison)
                return True

        template = self._template()
        result = await verify_claim(
            entity_name="Acme", claim_text=render_claim_text(template, "Acme"),
            config=VerifyConfig(model="test", repo_root="/tmp", skip_wayback=True),
            checkpoint=_Recording(), template=template,
        )

        assert audit_calls == []
        assert review_calls == []
        assert result.consistency is None

    @pytest.mark.asyncio
    async def test_verify_claim_grades_the_resolved_title(self, monkeypatch) -> None:
        from common.templates import render_claim_text

        title = "Acme has publicly-traded corporate structure"
        audit_calls: list[str] = []
        self._patch_pipeline(monkeypatch, title, audit_calls)

        template = self._template()
        await verify_claim(
            entity_name="Acme", claim_text=render_claim_text(template, "Acme"),
            config=VerifyConfig(model="test", repo_root="/tmp", skip_wayback=True),
            template=template,
        )

        assert audit_calls == [title]

    @pytest.mark.asyncio
    async def test_research_claim_grades_the_title_it_writes(self, monkeypatch, tmp_path) -> None:
        """A later dr step-audit grades the claim file's title; the pipeline run grades the same."""
        title = "Acme powers its data centers with wind energy"
        audit_calls: list[str] = []
        written: dict = {}
        self._patch_pipeline(monkeypatch, title, audit_calls)

        def _fake_write_claim_file(**kwargs):
            written.update(kwargs)
            return tmp_path / "research" / "claims" / "acme" / "claim.md"

        monkeypatch.setattr("orchestrator.persistence._write_source_files", lambda *a, **k: ["sources/2026/src"])
        monkeypatch.setattr("orchestrator.persistence._write_claim_file", _fake_write_claim_file)
        monkeypatch.setattr("orchestrator.persistence._write_audit_sidecar", lambda **k: None)
        monkeypatch.setattr("orchestrator.persistence._write_entity_file", lambda **k: "companies/acme")
        monkeypatch.setattr("orchestrator.persistence._build_sources_consulted", lambda *a, **k: [])

        from orchestrator.pipeline import research_claim
        await research_claim(
            claim_text="Acme runs on 100% wind",
            config=VerifyConfig(model="test", skip_wayback=True, repo_root=str(tmp_path)),
        )

        assert written.get("title") == title
        assert audit_calls == [title]


# --------------------------------------------------------------------------- #
# Uncovered sub-questions and the cited source list                            #
# --------------------------------------------------------------------------- #

_TITLES = {
    "a": "Alpha Report", "b": "Beta Study", "c": "Gamma Dataset", "d": "Delta Notes",
}


def _sf(key: str, *, kind: str = "article", independence: str | None = None) -> SourceFile:
    return SourceFile(
        frontmatter=SourceFrontmatter(
            url=f"https://example.com/{key}", title=_TITLES[key], publisher=f"Pub {key}",
            accessed_date=datetime.date(2026, 4, 26), kind=kind, summary="A summary.",
            independence=independence,
        ),
        body="Body.", slug=key, year=2026,
    )


def _sq_ro(keys: list[str], addresses: dict[str, list[str]]):
    from common.models import SubQuestion
    from researcher.decomposed import ResearchOutput

    urls = [f"https://example.com/{k}" for k in keys]
    return ResearchOutput(
        urls=urls,
        url_addresses={f"https://example.com/{k}": a for k, a in addresses.items()},
        sub_questions=[
            SubQuestion(id="sq1", question="Per-prompt energy?", rationale="r1"),
            SubQuestion(id="sq2", question="Web-search energy?", rationale="r2"),
        ],
        trace={"mode": "test"},
    )


def _analyst(narrative: str = "n", *, cited=None, overrides=None, level=None):
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment
    from common.models import Category, Confidence, EntityType, Verdict, VerificationLevel

    level = level or VerificationLevel.CLAIMED
    return AnalystOutput(
        entity=EntityResolution(entity_name="Acme", entity_type=EntityType.COMPANY, entity_description="d"),
        verdict=VerdictAssessment(
            title="Acme claim title", verdict=Verdict.MIXED, confidence=Confidence.LOW,
            narrative=narrative, topics=[Category("environmental-impact")],
            verification_level=level, seo_title="Acme claim",
            cap_rationale="Confidence is capped at low: entity sources only.",
            cited_sources=list(cited or []), source_overrides=overrides,
        ),
    )


def _patch_run(monkeypatch, files, ro, analyst_out, audit_sources: list | None = None):
    async def _fake_research(*args, **kwargs):
        return ro

    async def _fake_ingest(*args, **kwargs):
        return [(sf.frontmatter.url, sf) for sf in files], []

    async def _fake_analyse(*args, **kwargs):
        return analyst_out, None

    async def _fake_audit(entity_name, statement, ao, sources, cfg, criterion_notes=None):
        if audit_sources is not None:
            audit_sources.append(list(sources))
        return None

    monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
    monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
    monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)
    monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)


def _patch_research_claim_writes(monkeypatch, tmp_path, written: dict, *, rename: dict | None = None):
    rename = rename or {}

    def _spy_write_source_files(source_files, repo_root):
        ids = []
        for _url, sf in source_files:
            sf.slug = rename.get(sf.slug, sf.slug)
            ids.append(f"{sf.year}/{sf.slug}")
        written.setdefault("source_files", []).extend(u for u, _sf in source_files)
        return ids

    def _spy_write_claim_file(**kwargs):
        written["claim"] = kwargs
        return tmp_path / "research" / "claims" / "acme" / "claim.md"

    monkeypatch.setattr("orchestrator.persistence._write_source_files", _spy_write_source_files)
    monkeypatch.setattr("orchestrator.persistence._write_claim_file", _spy_write_claim_file)
    monkeypatch.setattr(
        "orchestrator.persistence._write_audit_sidecar", lambda **k: written.__setitem__("sidecar", k),
    )
    monkeypatch.setattr("orchestrator.persistence._write_entity_file", lambda **k: "companies/acme")


class TestUncoveredSubQuestionWarning:
    FILES = ["a", "b", "c", "d"]

    @pytest.mark.asyncio
    async def test_verify_claim_warns_and_records_no_error(self, monkeypatch, caplog, capsys) -> None:
        ro = _sq_ro(self.FILES, {k: ["sq1"] for k in self.FILES})
        _patch_run(monkeypatch, [_sf(k) for k in self.FILES], ro, _analyst())

        with caplog.at_level("WARNING", logger="orchestrator.pipeline"):
            result = await verify_claim(
                entity_name="Acme", claim_text="A claim",
                config=VerifyConfig(model="test", repo_root="/tmp", skip_wayback=True, show_progress=True),
            )

        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("sq2" in m and "no ingested source" in m for m in warnings), warnings
        # The console shows the warning itself; progress adds only the count line.
        assert "no ingested source" not in capsys.readouterr().err
        assert not any("sq1" in m and "no ingested source" in m for m in warnings)
        assert not any("sq2" in e for e in result.errors)
        assert result.sub_question_coverage["sq2"] == []

    @pytest.mark.asyncio
    async def test_research_claim_warns_and_sidecar_shows_gap(self, monkeypatch, tmp_path, caplog) -> None:
        from orchestrator.pipeline import research_claim

        ro = _sq_ro(self.FILES, {k: ["sq1"] for k in self.FILES})
        _patch_run(monkeypatch, [_sf(k) for k in self.FILES], ro, _analyst())
        written: dict = {}
        _patch_research_claim_writes(monkeypatch, tmp_path, written)

        with caplog.at_level("WARNING", logger="orchestrator.pipeline"):
            result = await research_claim(
                claim_text="A claim",
                config=VerifyConfig(model="test", skip_wayback=True, repo_root=str(tmp_path)),
            )

        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("sq2" in m and "no ingested source" in m for m in warnings), warnings
        assert not any("sq2" in e for e in result.errors)
        block = {e["id"]: e for e in written["sidecar"]["sub_questions_block"]}
        assert block["sq2"]["citations"] == []


class TestCitedSourceFilter:
    FILES = ["a", "b", "c", "d"]

    @staticmethod
    def _override(key: str, reason: str = "Restates the entity's own figure.", *, code: bool = False, independence=None):
        from analyst.agent import SourceOverride
        from common.models import Independence

        override = SourceOverride(
            source=f"2026/{key}", independence=independence or Independence.FIRST_PARTY, reason=reason,
        )
        override._code_relabel = code
        return override

    async def _research_claim(self, monkeypatch, tmp_path, analyst_out, *, rename=None):
        from orchestrator.pipeline import research_claim

        ro = _sq_ro(self.FILES, {k: ["sq1", "sq2"] for k in self.FILES})
        audit_sources: list = []
        _patch_run(monkeypatch, [_sf(k) for k in self.FILES], ro, analyst_out, audit_sources)
        written: dict = {}
        _patch_research_claim_writes(monkeypatch, tmp_path, written, rename=rename)
        result = await research_claim(
            claim_text="A claim",
            config=VerifyConfig(model="test", skip_wayback=True, repo_root=str(tmp_path)),
        )
        return result, written, audit_sources

    @pytest.mark.asyncio
    async def test_research_claim_lists_only_cited_sources(self, monkeypatch, tmp_path) -> None:
        ao = _analyst(
            "Per *Alpha Report* and *Beta Study*, it is offsets.",
            overrides=[self._override("c")],
        )
        result, written, audit_sources = await self._research_claim(monkeypatch, tmp_path, ao)

        assert written["claim"]["source_ids"] == ["2026/a", "2026/b", "2026/c"]
        assert [o["source"] for o in written["claim"]["source_overrides"]] == ["2026/c"]
        assert written["source_files"] == [
            "https://example.com/a", "https://example.com/b", "https://example.com/c",
        ]
        assert [sd["source_id"] for sd in audit_sources[0]] == ["2026/a", "2026/b", "2026/c"]
        # The sidecar still records every ingested source.
        assert len(result.sources_consulted()) == 4

    @pytest.mark.asyncio
    async def test_code_entity_override_does_not_keep_an_uncited_source(self, monkeypatch, tmp_path) -> None:
        ao = _analyst(
            "Per *Alpha Report* and *Beta Study*, it is offsets.",
            overrides=[self._override("d", "The source does not mention Acme.", code=True)],
        )
        _result, written, _audit = await self._research_claim(monkeypatch, tmp_path, ao)

        assert written["claim"]["source_ids"] == ["2026/a", "2026/b"]
        assert written["claim"]["source_overrides"] is None

    @pytest.mark.asyncio
    async def test_renamed_slug_keeps_the_cited_source(self, monkeypatch, tmp_path) -> None:
        ao = _analyst("Per *Alpha Report* and *Beta Study*, it is offsets.")
        _result, written, _audit = await self._research_claim(
            monkeypatch, tmp_path, ao, rename={"b": "example-b"},
        )

        assert written["claim"]["source_ids"] == ["2026/a", "2026/example-b"]

    @pytest.mark.asyncio
    async def test_analyst_failure_still_writes_every_fresh_file(self, monkeypatch, tmp_path) -> None:
        result, written, _audit = await self._research_claim(monkeypatch, tmp_path, None)

        assert result.analyst_output is None
        assert written["source_files"] == [f"https://example.com/{k}" for k in self.FILES]
        assert "claim" not in written

    @pytest.mark.asyncio
    async def test_nothing_cited_keeps_every_source(self, monkeypatch, tmp_path) -> None:
        _result, written, _audit = await self._research_claim(monkeypatch, tmp_path, _analyst("No titles."))

        assert written["claim"]["source_ids"] == [f"2026/{k}" for k in self.FILES]

    @staticmethod
    def _result_with_pool():
        """Two independent and two first-party sources, all cached."""
        from orchestrator.pipeline import VerificationResult

        labels = {"a": "independent", "b": "independent", "c": "first-party", "d": "first-party"}
        cached = [
            (f"https://example.com/{k}", f"2026/{k}", {
                "source_id": f"2026/{k}", "title": _TITLES[k], "url": f"https://example.com/{k}",
                "independence": lab, "kind": "report",
            })
            for k, lab in labels.items()
        ]
        return VerificationResult(
            entity="Acme", claim_text="c", urls_found=[], urls_ingested=[], urls_failed=[],
            sources=[sd for _u, _s, sd in cached], cached_sources=cached,
        )

    def test_level_guard_keeps_full_list(self, caplog) -> None:
        from common.models import VerificationLevel
        from orchestrator.pipeline import _apply_cited_filter

        result = self._result_with_pool()
        ao = _analyst(
            "Per *Gamma Dataset* and *Delta Notes*, it holds.",
            level=VerificationLevel.MULTIPLY_VERIFIED,
        )
        with caplog.at_level("WARNING", logger="orchestrator.pipeline"):
            kept = _apply_cited_filter(result, ao, "Acme")

        assert [sd["source_id"] for sd in kept] == ["2026/a", "2026/b", "2026/c", "2026/d"]
        assert result.uncited_urls == set()
        assert any("verification_level" in r.getMessage() for r in caplog.records)

    def test_analyst_override_corrected_by_entity_match_stays_cited(self) -> None:
        from common.models import Independence
        from orchestrator.pipeline import _apply_cited_filter, _merge_entity_overrides

        result = self._result_with_pool()
        ao = _analyst(
            "Per *Gamma Dataset*, it holds.",
            overrides=[self._override("a", "Independent test lab.", independence=Independence.INDEPENDENT)],
        )
        _merge_entity_overrides(ao.verdict, [
            self._override("a", "Entity match: acme.com.", code=True),
            self._override("b", "Entity match: acme.com.", code=True),
        ])
        kept = _apply_cited_filter(result, ao, "Acme")

        assert [sd["source_id"] for sd in kept] == ["2026/a", "2026/c"]

    def test_level_needing_no_independent_source_uses_subset(self) -> None:
        from orchestrator.pipeline import _apply_cited_filter

        result = self._result_with_pool()
        ao = _analyst("Per *Gamma Dataset* and *Delta Notes*, it holds.")
        kept = _apply_cited_filter(result, ao, "Acme")

        assert [sd["source_id"] for sd in kept] == ["2026/c", "2026/d"]
        assert result.uncited_urls == {"https://example.com/a", "https://example.com/b"}


class TestTitleBlockedClaimKeepsEverySource:
    FILES = ["a", "b", "c", "d"]

    async def _verify(self, monkeypatch, tmp_path, template):
        from common.templates import render_claim_text

        ro = _sq_ro(self.FILES, {k: ["sq1", "sq2"] for k in self.FILES})
        _patch_run(monkeypatch, [_sf(k) for k in self.FILES], ro, _analyst("Per *Alpha Report*, it holds."))
        claim_text = render_claim_text(template, "Acme") if template else "A claim"
        return await verify_claim(
            entity_name="Acme", claim_text=claim_text,
            config=VerifyConfig(model="test", repo_root=str(tmp_path), skip_wayback=True),
            template=template,
        )

    @pytest.mark.asyncio
    async def test_failing_title_leaves_the_source_list_whole(self, monkeypatch, tmp_path) -> None:
        # The analyst title "Acme claim title" fails this template.
        result = await self._verify(monkeypatch, tmp_path, TestAuditorGradedStatement._template())

        assert result.uncited_urls == set()
        assert result.persist_sources(tmp_path) == [f"2026/{k}" for k in self.FILES]

    @pytest.mark.asyncio
    async def test_without_template_the_filter_applies(self, monkeypatch, tmp_path) -> None:
        result = await self._verify(monkeypatch, tmp_path, None)

        assert result.persist_sources(tmp_path) == ["2026/a"]


class TestPersistSourcesSkipsUncited:
    def test_uncited_cached_and_fresh_entries_left_out(self, tmp_path) -> None:
        from orchestrator.pipeline import VerificationResult

        result = VerificationResult(
            entity="Acme", claim_text="c", urls_found=[], urls_ingested=[], urls_failed=[], sources=[],
            cached_sources=[
                ("https://example.com/x", "2025/x", {"source_id": "2025/x"}),
                ("https://example.com/y", "2025/y", {"source_id": "2025/y"}),
            ],
            source_files=[("https://example.com/a", _sf("a")), ("https://example.com/b", _sf("b"))],
            uncited_urls={"https://example.com/y", "https://example.com/b"},
        )
        url_index: dict[str, str] = {}

        ids = result.persist_sources(tmp_path, url_index)

        assert ids == ["2025/x", "2026/a"]
        assert (tmp_path / "research" / "sources" / "2026" / "a.md").exists()
        assert not (tmp_path / "research" / "sources" / "2026" / "b.md").exists()
        assert set(url_index.values()) == {"2026/a"}
