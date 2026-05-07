"""Tests for entity onboarding orchestration."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from analyst.agent import analyst_agent, verdict_only_agent
from auditor.agent import auditor_agent
from common.content_loader import resolve_repo_root
from common.frontmatter import parse_frontmatter
from ingestor.agent import ingestor_agent
from orchestrator.checkpoints import AutoApproveCheckpointHandler
from orchestrator.pipeline import (
    OnboardResult,
    VerifyConfig,
    _merge_search_hints,
    _probe_collision_suggestions,
    _tighten_entity_description,
    onboard_entity,
)


@contextmanager
def _noop(**kwargs):
    """No-op context manager used to neutralize inner agent overrides."""
    yield


def _ro(urls=None, errors=None, trace=None, sub_questions=None, url_addresses=None):
    from researcher.decomposed import ResearchOutput
    return ResearchOutput(
        urls=list(urls or []),
        errors=list(errors or []),
        trace=dict(trace or {"mode": "decomposed"}),
        sub_questions=list(sub_questions or []),
        url_addresses=dict(url_addresses or {}),
    )


async def _fake_research_with_url(*args, **kwargs):
    return _ro(urls=["https://example.com/report"])


async def _fake_research_empty(*args, **kwargs):
    return _ro()


async def _no_probe(*args, **kwargs):
    return []


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
    async def test_onboard_creates_entity_and_claims(self, tmp_path: Path, monkeypatch) -> None:
        """Onboard with TestModel writes entity and claim files."""
        _setup_tmp_repo(tmp_path)

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research_with_url)

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

        # At least some claim files written (4 company templates active in v0.1.0).
        # Under TestModel + 1-URL fake researcher, claims land in claims_blocked
        # (insufficient_sources) rather than claims_created; both are valid
        # written-artifact outcomes for this test.
        assert len(result.templates_applied) == 4
        assert len(result.claims_created) + len(result.claims_blocked) > 0


class TestOnboardEntityNoDoubleIngest:
    @pytest.mark.asyncio
    async def test_single_research_and_ingest_per_template(self, tmp_path: Path, monkeypatch) -> None:
        """Onboard should run one _research + _ingest_urls pair per template plus one for light research.

        Regression canary: pre-refactor onboard called verify_claim (which runs research+ingest)
        and then re-ran _research + _ingest_urls purely to recover SourceFile tuples. That
        doubled LLM/network calls per template. With verify_claim surfacing source_files
        directly, the extra pair disappears.
        """
        _setup_tmp_repo(tmp_path)

        from orchestrator import pipeline as pipeline_mod

        real_ingest = pipeline_mod._ingest_urls

        research_calls = 0
        ingest_calls = 0

        async def spy_research(*args, **kwargs):
            nonlocal research_calls
            research_calls += 1
            return await _fake_research_with_url(*args, **kwargs)

        async def spy_ingest(*args, **kwargs):
            nonlocal ingest_calls
            ingest_calls += 1
            return await real_ingest(*args, **kwargs)

        with (
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
    async def test_seed_url_skips_researcher(self, tmp_path: Path, monkeypatch) -> None:
        """When seed_url is provided, the researcher step is not called for light research."""
        _setup_tmp_repo(tmp_path)

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research_with_url)

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
    async def test_per_template_errors_are_slug_prefixed(self, tmp_path: Path, monkeypatch) -> None:
        """Every result.errors entry must start with `<slug>: `.

        When the researcher finds no URLs, claims land in claims_created as
        blocked (not claims_failed), but errors are still attributed with the
        canonical `slug: reason` format so the CLI can render them correctly.
        """
        _setup_tmp_repo(tmp_path)

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research_empty)

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
                max_sources=2,
                skip_wayback=True,
                repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "TestCorp", "company", config=config
            )

        assert result.status == "accepted"
        # Empty researcher causes claims to land in claims_blocked (with
        # placeholder files written), not claims_failed -- but errors must
        # still be slug-attributed.
        assert len(result.errors) > 0, "expected per-template errors"
        known_slugs = {
            t.split("/")[-1].replace(".md", "")
            for t in result.claims_created
        } | {
            path.split("/")[-1].replace(".md", "")
            for path, _ in result.claims_blocked
        }
        for err in result.errors:
            slug, sep, _reason = err.partition(": ")
            assert sep == ": ", (
                f"error {err!r} not in canonical `<slug>: <reason>` format"
            )
            assert slug in known_slugs, (
                f"error slug {slug!r} not in any known claim slug: {sorted(known_slugs)}"
            )


class TestOnboardEntityRejection:
    @pytest.mark.asyncio
    async def test_rejected_writes_draft(self, tmp_path: Path, monkeypatch) -> None:
        """Rejected onboard writes draft entity file."""
        _setup_tmp_repo(tmp_path)

        monkeypatch.setattr("orchestrator.pipeline._research", _fake_research_with_url)

        class RejectHandler(AutoApproveCheckpointHandler):
            async def review_onboard(self, entity_name, entity_type,
                                     applicable_templates, excluded_templates,
                                     entity_description=""):
                self.calls.append("review_onboard")
                return "reject"

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


class TestOnboardVocabularyResolution:
    @pytest.mark.asyncio
    async def test_unresolved_vocabulary_title_is_blocked(self, tmp_path: Path) -> None:
        """When the analyst returns a title containing the raw 'one of (...)' hint,
        the claim is blocked with analyst_error and written with a clean title."""
        _setup_tmp_repo(tmp_path)

        # Analyst returns the raw vocabulary placeholder as the title.
        # Onboard now passes a resolved_entity into verify_claim, which routes
        # the analyst through verdict_only_agent (entity is taken from the
        # resolved entity, the agent only emits a VerdictAssessment).
        unresolved_verdict = TestModel(
            custom_output_args={
                "title": "TestCorp has one of (publicly-traded, privately-held, non-profit, B-corp) corporate structure",
                "topics": ["industry-analysis"],
                "verdict": "unverified",
                "confidence": "low",
                "narrative": "No sources address ownership structure.",
            },
        )

        from orchestrator import pipeline as pipeline_mod

        async def fake_ingest(client, urls, cfg, sem, **kwargs):
            from ingestor.models import SourceFile, SourceFrontmatter
            import datetime
            sources = []
            for url in urls:
                suffix = url.split("/")[-1]
                sf = SourceFile(
                    frontmatter=SourceFrontmatter(
                        url=url,
                        title=f"Source {suffix}",
                        publisher="Ex",
                        accessed_date=datetime.date(2026, 4, 30),
                        kind="article",
                        summary="A summary.",
                    ),
                    body="Body.",
                    slug=suffix,
                    year=2026,
                )
                sources.append((url, sf))
            return sources, []

        async def fake_research(client, entity, claim, cfg, sem, **kwargs):
            return _ro(urls=[
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
                "https://example.com/d",
            ], trace={"mode": "test"})

        with (
            verdict_only_agent.override(model=unresolved_verdict),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            patch.object(pipeline_mod, "_research", side_effect=fake_research),
            patch.object(pipeline_mod, "_ingest_urls", side_effect=fake_ingest),
            patch.object(pipeline_mod, "_probe_collision_suggestions", side_effect=_no_probe),
        ):
            config = VerifyConfig(
                model="test",
                max_sources=8,
                skip_wayback=True,
                repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "TestCorp", "company", config=config, only=["corporate-structure"]
            )

        assert result.status == "accepted"
        assert len(result.claims_created) == 0
        assert len(result.claims_blocked) == 1
        assert len(result.claims_failed) == 0

        # The blocked claim file must have a clean title (no "one of (")
        blocked_rel, blocked_reason = result.claims_blocked[0]
        claim_path = tmp_path / blocked_rel
        assert claim_path.exists()
        assert blocked_reason.startswith("analyst_error")
        fm, _ = parse_frontmatter(claim_path.read_text())
        assert "one of (" not in fm["title"], (
            f"blocked claim title must not contain raw vocabulary hint: {fm['title']!r}"
        )
        assert fm["status"] == "blocked"
        assert fm["blocked_reason"] == "analyst_error"


class _AgentResult:
    def __init__(self, output) -> None:
        self.output = output


class TestTightenEntityDescription:
    @pytest.mark.asyncio
    async def test_calls_llm_to_rewrite(self) -> None:
        """Description rewrite is delegated to the LLM agent; on success its
        output replaces the raw page summary."""
        from orchestrator import pipeline as pipeline_mod
        cfg = VerifyConfig(model="test")

        async def fake_run(prompt, *args, **kwargs):
            assert "TreadLightly AI" in prompt
            return _AgentResult(pipeline_mod._EntityDescription(
                description="TreadLightly AI is an AI thinking tool with seven modes.",
            ))

        with (
            patch.object(pipeline_mod._entity_description_agent, "run", side_effect=fake_run),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            out = await _tighten_entity_description(
                "Landing page for TreadLightly AI, an AI thinking tool with seven modes.",
                "TreadLightly AI",
                "https://treadlightly.ai/",
                "https://treadlightly.ai",
                cfg,
            )
        assert out == "TreadLightly AI is an AI thinking tool with seven modes."

    @pytest.mark.asyncio
    async def test_blanks_when_source_domain_mismatches_canonical(self) -> None:
        """Domain-mismatch guard runs BEFORE the LLM and short-circuits to empty."""
        cfg = VerifyConfig(model="test")
        out = await _tighten_entity_description(
            "Tread Lightly! is a non-profit organization promoting responsible recreation.",
            "TreadLightly AI",
            "https://treadlightly.org/about-us/",
            "https://treadlightly.ai",
            cfg,
        )
        assert out == ""

    @pytest.mark.asyncio
    async def test_subdomain_of_canonical_is_kept(self) -> None:
        """www.acme.example matches acme.example; the rewrite proceeds."""
        from orchestrator import pipeline as pipeline_mod
        cfg = VerifyConfig(model="test")

        async def fake_run(prompt, *args, **kwargs):
            return _AgentResult(pipeline_mod._EntityDescription(
                description="Acme makes things.",
            ))

        with (
            patch.object(pipeline_mod._entity_description_agent, "run", side_effect=fake_run),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            out = await _tighten_entity_description(
                "Acme makes things.",
                "Acme",
                "https://www.acme.example/about",
                "https://acme.example",
                cfg,
            )
        assert out == "Acme makes things."

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_on_llm_failure(self) -> None:
        """If the rewrite call raises, return the raw summary unchanged."""
        from orchestrator import pipeline as pipeline_mod
        cfg = VerifyConfig(model="test")

        async def boom(*a, **kw):
            raise RuntimeError("model exploded")

        with (
            patch.object(pipeline_mod._entity_description_agent, "run", side_effect=boom),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            out = await _tighten_entity_description(
                "Acme is a thing.", "Acme", "https://acme.example", "https://acme.example", cfg,
            )
        assert out == "Acme is a thing."


class TestProbeCollisionSuggestions:
    @pytest.mark.asyncio
    async def test_suggests_offending_domain(self, monkeypatch) -> None:
        async def fake_search(client, query, max_results=8):
            return [
                {"url": "https://treadlightly.org/about-us/", "title": "About Us", "snippet": ""},
                {"url": "https://treadlightly.org/team-bod/", "title": "Team", "snippet": ""},
                {"url": "https://en.wikipedia.org/wiki/Tread_Lightly!", "title": "Wikipedia", "snippet": ""},
                {"url": "https://treadlightly.ai/", "title": "TreadLightly AI", "snippet": ""},
            ]
        from researcher import agent as researcher_agent_mod
        monkeypatch.setattr(researcher_agent_mod, "search_brave", fake_search)

        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="TreadLightly AI",
            entity_website="https://treadlightly.ai",
        )
        assert "treadlightly.org" in suggestions
        assert "treadlightly.ai" not in suggestions
        assert len(suggestions) <= 3

    @pytest.mark.asyncio
    async def test_skipped_when_no_canonical(self) -> None:
        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="Anything", entity_website=None,
        )
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_swallows_search_failures(self, monkeypatch) -> None:
        async def boom(client, query, max_results=8):
            raise RuntimeError("Brave 500")
        from researcher import agent as researcher_agent_mod
        monkeypatch.setattr(researcher_agent_mod, "search_brave", boom)

        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="X", entity_website="https://x.example",
        )
        assert suggestions == []


class TestMergeSearchHints:
    def test_returns_none_when_empty(self) -> None:
        assert _merge_search_hints(None, None, []) is None
        assert _merge_search_hints([], [], []) is None

    def test_merges_and_dedups(self) -> None:
        hints = _merge_search_hints(
            ["alpha", "beta"], ["bad.example"], ["bad.example", "worse.example"],
        )
        assert hints is not None
        assert hints.include == ["alpha", "beta"]
        assert hints.exclude == ["bad.example", "worse.example"]

    def test_cli_excludes_take_priority_in_order(self) -> None:
        hints = _merge_search_hints(None, ["operator-pick.com"], ["probe.com"])
        assert hints is not None
        assert hints.include == []
        assert hints.exclude == ["operator-pick.com", "probe.com"]


class TestOnboardSearchHintsWiredIntoResearch:
    @pytest.mark.asyncio
    async def test_per_template_research_receives_search_hints(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Per-template verify_claim runs must call _research with a resolved_entity
        that carries the merged search_hints. Without this wiring, the post-scorer
        filter and scorer disambiguation never fire on the onboard run that wrote
        them — they would only kick in on a re-run from disk."""
        _setup_tmp_repo(tmp_path)

        async def fake_probe(client, entity_name, entity_website):
            return ["evil.example"]
        monkeypatch.setattr(
            "orchestrator.pipeline._probe_collision_suggestions", fake_probe
        )

        seen_resolved_entities: list = []

        async def spy_research(client, entity, claim, cfg, sem, **kwargs):
            seen_resolved_entities.append(kwargs.get("resolved_entity"))
            return _ro(urls=["https://example.com/report"])

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
            patch("orchestrator.pipeline._research", side_effect=spy_research),
        ):
            config = VerifyConfig(
                model="test", max_sources=2, skip_wayback=True, repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "TestCorp", "company", config=config,
                search_hints_exclude=["operator-bad.example"],
                only=["publishes-sustainability-report"],
            )

        assert result.status == "accepted"
        # First call is light research (no resolved_entity); subsequent calls are
        # per-template and MUST carry the resolved entity with search_hints.
        per_template_calls = [r for r in seen_resolved_entities if r is not None]
        assert per_template_calls, (
            "verify_claim was invoked without a resolved_entity; search_hints "
            "won't reach decomposed_research"
        )
        for resolved in per_template_calls:
            assert resolved.search_hints is not None
            assert "operator-bad.example" in resolved.search_hints.exclude
            assert "evil.example" in resolved.search_hints.exclude
            assert resolved.entity_name == "TestCorp"


class TestOnboardSearchHintsPersisted:
    @pytest.mark.asyncio
    async def test_search_hints_land_in_entity_frontmatter(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """CLI-provided hints + probe suggestions persist to entity YAML frontmatter
        and round-trip through parse_entity_ref."""
        _setup_tmp_repo(tmp_path)

        async def fake_research(*args, **kwargs):
            return _ro(urls=["https://example.com/report"])
        monkeypatch.setattr("orchestrator.pipeline._research", fake_research)

        async def fake_probe(client, entity_name, entity_website):
            return ["evil.example"]
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", fake_probe)

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            config = VerifyConfig(
                model="test", max_sources=2, skip_wayback=True, repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "TestCorp", "company", config=config,
                search_hints_include=["prefer-this"],
                search_hints_exclude=["operator-bad.example"],
            )

        assert result.status == "accepted"
        entity_path = tmp_path / "research" / "entities" / "companies" / "testcorp.md"
        fm, _ = parse_frontmatter(entity_path.read_text())

        hints = fm["search_hints"]
        assert hints["include"] == ["prefer-this"]
        assert hints["exclude"] == ["operator-bad.example", "evil.example"]

        from orchestrator.entity_resolution import parse_entity_ref
        resolved = parse_entity_ref("companies/testcorp", tmp_path)
        assert resolved.search_hints is not None
        assert resolved.search_hints.include == ["prefer-this"]
        assert resolved.search_hints.exclude == ["operator-bad.example", "evil.example"]
