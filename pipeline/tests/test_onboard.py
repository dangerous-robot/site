"""Tests for entity onboarding orchestration."""

from __future__ import annotations

import datetime
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
from ingestor.models import SourceFile, SourceFrontmatter
from orchestrator.checkpoints import AutoApproveCheckpointHandler
from loop import VerifyConfig
from orchestrator.pipeline import (
    _merge_search_hints,
    _probe_collision_suggestions,
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


_URL = "https://example.com/report"
_URLS = [f"https://example.com/report-{i}" for i in range(1, 5)]


@pytest.fixture
def claim_research():
    """Script the claim researcher: planner and scorer on TestModel, the search
    executor patched (``researcher.decomposed.execute_searches``).

    Call it with the URLs the search returns (each with page text); the
    returned mock counts the searches. Light research and every claim run
    share it, as they share the researcher. The overrides are entered here,
    outside the test's event loop, so they are left in the context that set them.
    """
    from contextlib import nullcontext

    from researcher.planner import research_planner_agent
    from researcher.scorer import url_scorer_agent
    from tests.loop_harness import fake_execute_searches, planner_args, scorer_args

    state: dict = {"urls": []}
    scorer_model = TestModel(custom_output_args=scorer_args([]))

    async def _search(queries, client, **kwargs):
        urls = state["urls"]
        fake = fake_execute_searches(urls, {u: f"Page text of {u}." for u in urls})
        return await fake(queries, client, **kwargs)

    with (
        research_planner_agent.override(model=TestModel(custom_output_args=planner_args())),
        url_scorer_agent.override(model=scorer_model),
        patch.object(research_planner_agent, "override", side_effect=lambda **kw: nullcontext()),
        patch.object(url_scorer_agent, "override", side_effect=lambda **kw: nullcontext()),
        patch("researcher.decomposed.execute_searches", side_effect=_search) as searches,
    ):
        def _install(urls: list[str]):
            state["urls"] = list(urls)
            scorer_model.custom_output_args = scorer_args(list(urls))
            return searches

        yield _install


def _fetching_ingest_model():
    """The harness ingest model for the search's URLs; any other URL (a light
    research seed) gets a source without a fetch, which ingest rejects."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    from tests.loop_harness import ingest_model

    inner = ingest_model()

    async def _fn(messages, info):
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        prompt = next(p.content for p in parts if isinstance(p, UserPromptPart))
        url = prompt.split("URL: ", 1)[1].split("\n", 1)[0]
        if url.startswith("https://example.com/"):
            return await inner.function(messages, info)
        source = {"frontmatter": {"url": url, "title": "Unfetched", "publisher": "P",
                                  "accessed_date": "2026-10-14", "kind": "article", "summary": "S."},
                  "body": "B.", "slug": "page", "year": 2026}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])

    return FunctionModel(_fn)


def _echo_title_analyst(**extra):
    """A verdict-only analyst whose title is the claim it was asked about, so it passes the template."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    async def _fn(messages, info):
        prompt = next(
            str(p.content) for m in messages for p in getattr(m, "parts", []) if isinstance(p, UserPromptPart)
        )
        claim = prompt.split("## Claim to evaluate: ", 1)[1].split("\n", 1)[0].strip()
        args = {"title": claim, "topics": ["environmental-impact"], "verdict": "mixed",
                "confidence": "medium", "narrative": "The evidence is mixed.",
                "verification_level": "partially-verified", "seo_title": "Claim", **extra}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(_fn)


def _fake_gather(raw_description: str, fetch_errors: list[str] | None = None):
    """Stand-in for gather_light_research with a fixed page summary.

    The onboard enricher only runs when light research collected a summary,
    so tests that exercise the enricher must supply one.
    """
    async def fake(entity_name, entity_type, cfg, sem, client, seed_url=None):
        from orchestrator.pipeline import LightResearchBundle
        return LightResearchBundle(
            entity_name=entity_name,
            entity_type=entity_type,
            raw_description=raw_description,
            entity_website="https://example.com/report",
            probe_excludes=[],
            fetch_errors=list(fetch_errors or []),
        )
    return fake


def _make_source_file(url: str, slug: str) -> SourceFile:
    return SourceFile(
        frontmatter=SourceFrontmatter(
            url=url, title="Report", publisher="Example", accessed_date=datetime.date(2026, 5, 1),
            kind="report", summary="A test summary.",
        ),
        body="Body content.",
        slug=slug,
        year=2026,
    )


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
    async def test_onboard_creates_entity_and_claims(self, tmp_path: Path, monkeypatch, claim_research) -> None:
        """Onboard with TestModel writes entity and claim files."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])

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

        # At least some claim files written (5 company templates active).
        # Under TestModel + 1-URL fake researcher, claims land in claims_blocked
        # (insufficient_sources) rather than claims_created; both are valid
        # written-artifact outcomes for this test.
        assert len(result.templates_applied) == 5
        assert len(result.claims_created) + len(result.claims_blocked) > 0


class TestOnboardEntityNoDoubleIngest:
    @pytest.mark.asyncio
    async def test_single_research_and_ingest_per_template(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """Onboard runs one research and one ingest per template plus one pair for light research.

        Regression canary: the per-template loop run must surface its source
        files, so onboard never re-runs research and ingest to recover them.
        """
        _setup_tmp_repo(tmp_path)

        import loop.ingest as ingest_mod
        from orchestrator import pipeline as pipeline_mod

        searches = claim_research([_URL])
        ingest_calls = 0
        real_light_ingest = pipeline_mod._ingest_urls
        real_claim_ingest = ingest_mod.ingest_urls

        async def spy_light_ingest(*args, **kwargs):
            nonlocal ingest_calls
            ingest_calls += 1
            return await real_light_ingest(*args, **kwargs)

        async def spy_claim_ingest(*args, **kwargs):
            nonlocal ingest_calls
            ingest_calls += 1
            return await real_claim_ingest(*args, **kwargs)

        monkeypatch.setattr(pipeline_mod, "_ingest_urls", spy_light_ingest)
        monkeypatch.setattr(ingest_mod, "ingest_urls", spy_claim_ingest)
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
        # 5 company templates + 1 light-research pass = 6 ingest + 6 research calls.
        assert ingest_calls == 6, f"expected 6 ingest calls, got {ingest_calls}"
        assert searches.call_count <= 6, f"expected <=6 research calls, got {searches.call_count}"


class TestOnboardKeepsSourcesOnDisk:
    @pytest.mark.asyncio
    async def test_claims_list_sources_already_on_disk(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """Researcher URLs already stored as sources must still be listed on the claim."""
        _setup_tmp_repo(tmp_path)
        for i, url in enumerate(_URLS, 1):
            existing = tmp_path / "research" / "sources" / "2025" / f"report-{i}.md"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text(
                f"---\nurl: {url}\ntitle: Report {i}\npublisher: Example\n"
                "accessed_date: 2025-01-01\nkind: report\nsummary: A stored report.\n---\nBody.\n",
                encoding="utf-8",
            )
        claim_research(_URLS)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        with (
            ingestor_agent.override(model=_fetching_ingest_model()),
            verdict_only_agent.override(model=_echo_title_analyst()),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            config = VerifyConfig(model="test", max_sources=4, skip_wayback=True, repo_root=str(tmp_path))
            result = await onboard_entity(
                "TestCorp", "company", config=config, only=["publishes-sustainability-report"],
            )

        assert result.claims_created, (result.claims_blocked, result.errors)
        for rel in result.claims_created:
            fm, _ = parse_frontmatter((tmp_path / rel).read_text(encoding="utf-8"))
            assert fm["sources"] == [f"2025/report-{i}" for i in range(1, 5)], rel


    @pytest.mark.asyncio
    async def test_later_templates_reuse_a_source_written_earlier(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        _setup_tmp_repo(tmp_path)
        import loop.ingest as ingest_mod

        claim_research(_URLS)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)
        ingested: list[list[str]] = []
        real_ingest = ingest_mod.ingest_urls

        async def spy_ingest(client, urls, cfg, sem, **kwargs):
            ingested.append(list(urls))
            return await real_ingest(client, urls, cfg, sem, **kwargs)

        monkeypatch.setattr(ingest_mod, "ingest_urls", spy_ingest)
        with (
            ingestor_agent.override(model=_fetching_ingest_model()),
            verdict_only_agent.override(model=_echo_title_analyst()),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            config = VerifyConfig(model="test", max_sources=4, skip_wayback=True, repo_root=str(tmp_path))
            result = await onboard_entity(
                "TestCorp", "company", config=config,
                only=["publishes-sustainability-report", "contributes-to-ai-safety"],
            )

        # The first claim fetches the four pages; the second reuses the files the first wrote.
        assert ingested == [_URLS], ingested
        assert len(result.claims_created) == 2, (result.claims_blocked, result.errors)


class TestOnboardEntitySeedUrl:
    @pytest.mark.asyncio
    async def test_seed_url_skips_researcher(self, tmp_path: Path, monkeypatch, claim_research) -> None:
        """When seed_url is provided, the researcher step is not called for light research."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])

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
    async def test_per_template_errors_are_slug_prefixed(self, tmp_path: Path, monkeypatch, claim_research) -> None:
        """Every result.errors entry must start with `<slug>: `.

        When the researcher finds no URLs, claims land in claims_created as
        blocked (not claims_failed), but errors are still attributed with the
        canonical `slug: reason` format so the CLI can render them correctly.
        """
        _setup_tmp_repo(tmp_path)

        claim_research([])

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
    async def test_rejected_writes_draft(self, tmp_path: Path, monkeypatch, claim_research) -> None:
        """Rejected onboard writes draft entity file."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])

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
    async def test_unresolved_vocabulary_title_is_blocked(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """When the analyst returns a title containing the raw 'one of (...)' hint,
        the claim is blocked with analyst_error and nothing is written."""
        _setup_tmp_repo(tmp_path)

        # Analyst returns the raw vocabulary placeholder as the title. Onboard
        # runs the loop on a resolved entity, so the analyst is the
        # verdict-only agent.
        unresolved_verdict = TestModel(
            custom_output_args={
                "title": "TestCorp has one of (publicly-traded, privately-held, non-profit, B-corp) corporate structure",
                "topics": ["industry-analysis"],
                "verdict": "unverified",
                "confidence": "low",
                "narrative": "No sources address ownership structure.",
            },
        )
        claim_research(_URLS)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        with (
            ingestor_agent.override(model=_fetching_ingest_model()),
            verdict_only_agent.override(model=unresolved_verdict),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
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
        assert len(result.claims_failed) == 0
        assert result.claims_blocked == [("corporate-structure", result.claims_blocked[0][1])]
        assert result.claims_blocked[0][1].startswith("analyst_error")
        # A blocked claim writes nothing: no placeholder claim, no source file.
        assert not (tmp_path / "research" / "claims").exists()
        assert not (tmp_path / "research" / "sources").exists()


class _AgentResult:
    def __init__(self, output) -> None:
        self.output = output


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
    async def test_never_suggests_own_or_parent_domain(self, monkeypatch) -> None:
        """Viro AI's website is ai.viro.app; viro.app is its own parent domain."""
        async def fake_search(client, query, max_results=8):
            return [
                {"url": "https://www.viro.app/terms-conditions-viro-ai", "title": "Terms", "snippet": ""},
                {"url": "https://viro.app/privacy-policy", "title": "Privacy", "snippet": ""},
                {"url": "https://ai.viro.app/data-centers", "title": "Data centers", "snippet": ""},
                {"url": "https://docs.ai.viro.app/faq", "title": "FAQ", "snippet": ""},
                {"url": "https://viro-pharma.example/", "title": "Viro Pharma", "snippet": ""},
            ]
        from researcher import agent as researcher_agent_mod
        monkeypatch.setattr(researcher_agent_mod, "search_brave", fake_search)

        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="Viro AI",
            entity_website="https://ai.viro.app",
        )
        assert "viro.app" not in suggestions
        assert "ai.viro.app" not in suggestions
        assert "docs.ai.viro.app" not in suggestions
        assert suggestions == ["viro-pharma.example"]

    @pytest.mark.asyncio
    async def test_never_suggests_a_sibling_subdomain(self, monkeypatch) -> None:
        """help.viro.app and ai.viro.app are both under Viro's own viro.app."""
        async def fake_search(client, query, max_results=8):
            return [
                {"url": "https://help.viro.app/is-viro-ai-eco-friendly", "title": "Help", "snippet": ""},
                {"url": "https://shop.example.co.uk/viro", "title": "Shop", "snippet": ""},
            ]
        from researcher import agent as researcher_agent_mod
        monkeypatch.setattr(researcher_agent_mod, "search_brave", fake_search)

        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="Viro AI",
            entity_website="https://ai.viro.app",
        )
        assert suggestions == ["shop.example.co.uk"]

        # Two sites under one country-code suffix are not one entity.
        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="Viro AI",
            entity_website="https://viro.co.uk",
        )
        assert suggestions == ["help.viro.app", "shop.example.co.uk"]

    @pytest.mark.asyncio
    async def test_probe_skips_shared_platform_hosts(self, monkeypatch) -> None:
        """The entity's own LinkedIn page or App Store listing is no collision."""
        async def fake_search(client, query, max_results=8):
            return [
                {"url": "https://www.linkedin.com/company/earthly-insight", "title": "LinkedIn", "snippet": ""},
                {"url": "https://apps.apple.com/us/app/earthly-insight/id1", "title": "App", "snippet": ""},
                {"url": "https://earthlyinsight.ai/privacy", "title": "Privacy", "snippet": ""},
                {"url": "https://play.google.com/store/apps/details?id=x", "title": "Play", "snippet": ""},
                {"url": "https://github.com/earthly-insight", "title": "GitHub", "snippet": ""},
            ]
        from researcher import agent as researcher_agent_mod
        monkeypatch.setattr(researcher_agent_mod, "search_brave", fake_search)

        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="Earthly Insight",
            entity_website="https://earthlyinsight.com",
        )
        assert suggestions == ["earthlyinsight.ai"]

    @pytest.mark.asyncio
    async def test_skipped_when_no_canonical(self) -> None:
        suggestions = await _probe_collision_suggestions(
            client=None, entity_name="Anything", entity_website=None,
        )
        assert suggestions == []


def _verifier_model(status: str, candidates: list[str] | None = None) -> TestModel:
    """TestModel returning a canned VerificationOutcome."""
    return TestModel(
        custom_output_args={
            "status": status,
            "candidates": list(candidates or []),
            "reasoning": f"canned {status} outcome for tests",
        },
    )


def _enricher_model(
    *,
    founded: int | None = 2021,
    description: str = "TestCorp is a test company.",
    history_markdown: str = "Para 1.\n\nPara 2.",
) -> TestModel:
    """TestModel returning a canned EnrichmentDraft."""
    return TestModel(
        custom_output_args={
            "founded": founded,
            "description": description,
            "history_markdown": history_markdown,
        },
    )


class TestOnboardPhaseBVerifier:
    """Phase B verifier wiring: needs-disambiguation, unverified, verified."""

    @pytest.mark.asyncio
    async def test_needs_disambiguation_with_auto_approve_rejects(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """Auto-approve handler returns 'reject' on disambiguation; run halts rejected."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        with (
            ingestor_agent.override(model=_ingestor_model()),
            entity_verifier_agent.override(
                model=_verifier_model(
                    "needs-disambiguation",
                    candidates=["Apple Inc.", "Apple Records"],
                ),
            ),
            entity_enricher_agent.override(model=_enricher_model()),
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
            result = await onboard_entity("Apple", "company", config=config)

        assert result.status == "rejected"
        assert any("needs-disambiguation" in e for e in result.errors)
        assert any("Apple Inc." in e for e in result.errors)
        assert any("Apple Records" in e for e in result.errors)
        # No entity file should have been written.
        entity_path = tmp_path / "research" / "entities" / "companies" / "apple.md"
        assert not entity_path.exists()

    @pytest.mark.asyncio
    async def test_unverified_with_auto_approve_rejects(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """Auto-approve handler returns 'reject' on unverified; run halts rejected."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        with (
            ingestor_agent.override(model=_ingestor_model()),
            entity_verifier_agent.override(model=_verifier_model("unverified")),
            entity_enricher_agent.override(model=_enricher_model()),
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
                "Obscure Startup", "company", config=config,
            )

        assert result.status == "rejected"
        assert any("unverified" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_unverified_with_operator_pick_persists_status(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """Operator returns 'unverified-startup'; that becomes verification_status."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        class PickStartupHandler(AutoApproveCheckpointHandler):
            async def review_verification_status(
                self, entity_name, website, reasoning, statuses,
            ):
                self.calls.append("review_verification_status")
                assert statuses == ["unverified-startup", "unverified-other"]
                return "unverified-startup"

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            entity_verifier_agent.override(model=_verifier_model("unverified")),
            entity_enricher_agent.override(model=_enricher_model()),
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
            handler = PickStartupHandler()
            result = await onboard_entity(
                "Obscure Startup", "company", config=config, checkpoint=handler,
            )

        assert result.status == "accepted"
        assert "review_verification_status" in handler.calls
        assert "review_entity_disambiguation" not in handler.calls
        # Entity file should record the operator-picked verification_status.
        entity_path = (
            tmp_path / "research" / "entities" / "companies" / "obscure-startup.md"
        )
        assert entity_path.exists()
        fm, _ = parse_frontmatter(entity_path.read_text())
        assert fm.get("verification_status") == "unverified-startup"

    @pytest.mark.asyncio
    async def test_verified_proceeds_to_enricher(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """verified outcome proceeds to enricher; entity file lands with Facts and History."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)
        monkeypatch.setattr(
            "orchestrator.pipeline.gather_light_research",
            _fake_gather("Anthropic builds AI systems."),
        )

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            entity_verifier_agent.override(model=_verifier_model("verified")),
            entity_enricher_agent.override(
                model=_enricher_model(
                    founded=2021,
                    description="Anthropic is an AI safety lab.",
                    history_markdown="Founded in 2021.\n\nBuilds Claude.",
                ),
            ),
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
            result = await onboard_entity("Anthropic", "company", config=config)

        assert result.status == "accepted"
        entity_path = (
            tmp_path / "research" / "entities" / "companies" / "anthropic.md"
        )
        assert entity_path.exists()
        text = entity_path.read_text()
        fm, body = parse_frontmatter(text)
        # Facts: founded persisted, description tightened.
        assert fm.get("founded") == 2021
        assert "AI safety lab" in fm.get("description", "")
        # History: body populated by the enricher.
        assert "Founded in 2021" in body
        # No verification_status written when verifier returned 'verified'.
        assert fm.get("verification_status") in (None, "verified")

    @pytest.mark.asyncio
    async def test_force_re_enriches_existing_entity(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """dr onboard --force re-runs the enricher and splices into existing file."""
        _setup_tmp_repo(tmp_path)
        # Pre-create the entity file so onboard takes the existing-entity path.
        entity_dir = tmp_path / "research" / "entities" / "companies"
        entity_dir.mkdir(parents=True, exist_ok=True)
        existing = entity_dir / "openai.md"
        existing.write_text(
            "---\nname: OpenAI\ntype: company\ndescription: An AI lab.\n---\n",
            encoding="utf-8",
        )

        claim_research([_URL])
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)
        monkeypatch.setattr(
            "orchestrator.pipeline.gather_light_research",
            _fake_gather("OpenAI builds AI systems."),
        )

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            entity_verifier_agent.override(model=_verifier_model("verified")),
            entity_enricher_agent.override(
                model=_enricher_model(
                    founded=2015,
                    description="OpenAI is an AI research and deployment company.",
                    history_markdown="Founded in 2015.\n\nReleased ChatGPT in 2022.",
                ),
            ),
            patch.object(
                Agent, "override", side_effect=lambda **kw: _noop(**kw)
            ),
        ):
            config = VerifyConfig(
                model="test",
                max_sources=2,
                skip_wayback=True,
                repo_root=str(tmp_path),
                force_overwrite=True,
            )
            result = await onboard_entity("OpenAI", "company", config=config)

        assert result.status == "accepted"
        text = existing.read_text()
        fm, body = parse_frontmatter(text)
        assert fm.get("founded") == 2015
        assert "research and deployment" in fm.get("description", "")
        assert "Founded in 2015" in body

    @pytest.mark.asyncio
    async def test_onboard_skips_enricher_when_no_page_fetched(
        self, tmp_path: Path, monkeypatch, claim_research, capsys
    ) -> None:
        """--force on an existing entity leaves the file alone when no page summary was collected."""
        _setup_tmp_repo(tmp_path)
        entity_dir = tmp_path / "research" / "entities" / "companies"
        entity_dir.mkdir(parents=True, exist_ok=True)
        existing = entity_dir / "openai.md"
        original = "---\nname: OpenAI\ntype: company\ndescription: An AI lab.\n---\n"
        existing.write_text(original, encoding="utf-8")

        claim_research([_URL])
        monkeypatch.setattr(
            "orchestrator.pipeline.gather_light_research",
            _fake_gather("", ["https://example.com/report: http_403: Forbidden"]),
        )

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            entity_verifier_agent.override(model=_verifier_model("verified")),
            entity_enricher_agent.override(
                model=_enricher_model(
                    founded=2015,
                    description="Guessed description.",
                    history_markdown="Guessed history.",
                ),
            ),
            patch.object(
                Agent, "override", side_effect=lambda **kw: _noop(**kw)
            ),
            patch.object(
                entity_enricher_agent, "run", wraps=entity_enricher_agent.run
            ) as spy,
        ):
            config = VerifyConfig(
                model="test",
                max_sources=2,
                skip_wayback=True,
                repo_root=str(tmp_path),
                force_overwrite=True,
            )
            await onboard_entity("OpenAI", "company", config=config)

        spy.assert_not_called()
        text = existing.read_text(encoding="utf-8")
        assert text == original
        assert "Guessed" not in text
        err = capsys.readouterr().err
        assert "Enricher skipped: light research collected no page summary" in err
        assert "  ! https://example.com/report: http_403: Forbidden" in err

    @pytest.mark.asyncio
    async def test_name_based_force_keeps_on_disk_description(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """With no page summary, a name-based run reads the description from the entity file on disk."""
        _setup_tmp_repo(tmp_path)
        entity_dir = tmp_path / "research" / "entities" / "companies"
        entity_dir.mkdir(parents=True, exist_ok=True)
        existing = entity_dir / "openai.md"
        original = "---\nname: OpenAI\ntype: company\ndescription: An AI lab.\n---\n"
        existing.write_text(original, encoding="utf-8")

        monkeypatch.setattr(
            "orchestrator.pipeline.gather_light_research",
            _fake_gather("", ["https://example.com/report: http_403: Forbidden"]),
        )

        seen: list[str] = []

        class RecordingHandler(AutoApproveCheckpointHandler):
            async def review_onboard(self, *args, entity_description: str = "", **kwargs):
                seen.append(entity_description)
                return []

        from researcher.entity_verifier import entity_verifier_agent

        with entity_verifier_agent.override(model=_verifier_model("verified")):
            config = VerifyConfig(
                model="test",
                max_sources=2,
                skip_wayback=True,
                repo_root=str(tmp_path),
                force_overwrite=True,
            )
            result = await onboard_entity(
                "OpenAI", "company", config=config, checkpoint=RecordingHandler(),
            )

        assert result.entity_ref == "companies/openai"
        assert seen == ["An AI lab."]
        assert existing.read_text(encoding="utf-8") == original

    @pytest.mark.asyncio
    async def test_onboard_new_entity_skips_enricher_when_no_page_fetched(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """A new entity gets the placeholder description, not a model-memory guess."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])
        monkeypatch.setattr(
            "orchestrator.pipeline.gather_light_research", _fake_gather(""),
        )

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            entity_verifier_agent.override(model=_verifier_model("verified")),
            entity_enricher_agent.override(
                model=_enricher_model(
                    founded=2015,
                    description="Guessed description.",
                    history_markdown="Guessed history.",
                ),
            ),
            patch.object(
                Agent, "override", side_effect=lambda **kw: _noop(**kw)
            ),
            patch.object(
                entity_enricher_agent, "run", wraps=entity_enricher_agent.run
            ) as spy,
        ):
            config = VerifyConfig(
                model="test",
                max_sources=2,
                skip_wayback=True,
                repo_root=str(tmp_path),
            )
            await onboard_entity("Ecosia", "company", config=config)

        spy.assert_not_called()
        entity_path = tmp_path / "research" / "entities" / "companies" / "ecosia.md"
        assert entity_path.exists()
        text = entity_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        assert fm.get("description") == "Ecosia (company)."
        assert fm.get("founded") is None
        assert "Guessed" not in text

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
        """Per-template loop runs must hand the researcher a resolved_entity that
        carries the merged search_hints. Without this wiring, the post-scorer
        filter and scorer disambiguation never fire on the onboard run that wrote
        them — they would only kick in on a re-run from disk."""
        _setup_tmp_repo(tmp_path)

        async def fake_probe(client, entity_name, entity_website):
            return ["evil.example"]
        monkeypatch.setattr(
            "orchestrator.pipeline._probe_collision_suggestions", fake_probe
        )

        seen_resolved_entities: list = []

        async def spy_research(claim, entity, cfg, sem, client, **kwargs):
            seen_resolved_entities.append(kwargs.get("resolved_entity"))
            return _ro(urls=[_URL])

        monkeypatch.setattr("researcher.decomposed.decomposed_research", spy_research)
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
                search_hints_exclude=["operator-bad.example"],
                only=["publishes-sustainability-report"],
            )

        assert result.status == "accepted"
        # First call is light research (no resolved_entity); subsequent calls are
        # per-template and MUST carry the resolved entity with search_hints.
        per_template_calls = [r for r in seen_resolved_entities if r is not None]
        assert per_template_calls, (
            "the loop ran without a resolved_entity; search_hints "
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
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """CLI-provided hints + probe suggestions persist to entity YAML frontmatter
        and round-trip through parse_entity_ref."""
        _setup_tmp_repo(tmp_path)

        claim_research([_URL])

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


class TestOnboardUsesEntityFileOnDisk:
    """A ref to a hand-written entity file makes that file the authoritative
    entity for the analyst and auditor, not the enricher's draft."""

    FILE_DESCRIPTION = "GreenTest is a chatbot that says it runs on hydropower."
    ENRICHER_DESCRIPTION = "GreenTest plants verified trees monthly (enricher guess)."

    def _write_product(self, tmp_path: Path) -> str:
        path = tmp_path / "research" / "entities" / "products" / "greentest.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            "name: GreenTest\n"
            "type: product\n"
            f"description: {self.FILE_DESCRIPTION}\n"
            "website: https://greentest.example\n"
            "parent_company: companies/greentest-bv\n"
            "search_hints:\n"
            "  exclude:\n"
            "  - file-excluded.example\n"
            "---\n",
            encoding="utf-8",
        )
        return "products/greentest"

    @pytest.mark.asyncio
    async def test_entity_file_reaches_analyst_and_auditor(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        from tests.loop_harness import capturing_model

        _setup_tmp_repo(tmp_path)
        ref = self._write_product(tmp_path)
        before = (tmp_path / "research" / "entities" / f"{ref}.md").read_text()

        seed_urls: list = []
        real_gather = __import__(
            "orchestrator.pipeline", fromlist=["gather_light_research"]
        ).gather_light_research

        async def spy_gather(*args, **kwargs):
            seed_urls.append(kwargs.get("seed_url"))
            return await real_gather(*args, **kwargs)

        monkeypatch.setattr("orchestrator.pipeline.gather_light_research", spy_gather)
        claim_research(_URLS)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        from researcher.entity_verifier import entity_verifier_agent
        from researcher.entity_enricher import entity_enricher_agent

        analyst_prompts: list[str] = []
        auditor_prompts: list[str] = []
        verdict_model = capturing_model(analyst_prompts, {
            # The title must pass the template, or the claim is blocked and the
            # auditor is skipped.
            "title": "GreenTest is hosted on renewable energy",
            "topics": ["environmental-impact"],
            "verdict": "mixed",
            "confidence": "medium",
            "narrative": "The evidence is mixed.",
            "verification_level": "independently-verified",
            "seo_title": "GreenTest runs on renewable energy",
        })
        auditor_model = capturing_model(auditor_prompts, {
            "verdict": "mixed", "confidence": "medium",
            "reasoning": "Independent assessment agrees.", "evidence_gaps": [],
        })
        with (
            ingestor_agent.override(model=_fetching_ingest_model()),
            verdict_only_agent.override(model=verdict_model),
            auditor_agent.override(model=auditor_model),
            entity_verifier_agent.override(model=_verifier_model("verified")),
            entity_enricher_agent.override(
                model=_enricher_model(description=self.ENRICHER_DESCRIPTION),
            ),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            config = VerifyConfig(
                model="test", max_sources=4, skip_wayback=True, repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "GreenTest", "product", config=config, entity_ref=ref,
                only=["renewable-energy-hosting"],
            )

        assert result.status == "accepted", result.errors
        assert analyst_prompts, "analyst never ran"
        assert auditor_prompts, "auditor never ran"
        analyst_prompt = analyst_prompts[0]
        assert f"Description: {self.FILE_DESCRIPTION}" in analyst_prompt
        assert "Parent company: companies/greentest-bv" in analyst_prompt
        assert self.ENRICHER_DESCRIPTION not in analyst_prompt
        assert f"Description: {self.FILE_DESCRIPTION}" in auditor_prompts[0]
        assert self.ENRICHER_DESCRIPTION not in auditor_prompts[0]
        # Light research starts from the file's website, not a search.
        assert seed_urls and seed_urls[0] == "https://greentest.example"
        # The file is read, never rewritten, without --force.
        assert (tmp_path / "research" / "entities" / f"{ref}.md").read_text() == before

    @pytest.mark.asyncio
    async def test_entity_file_search_hints_reach_research(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _setup_tmp_repo(tmp_path)
        ref = self._write_product(tmp_path)

        seen: list = []

        async def spy_research(claim, entity, cfg, sem, client, **kwargs):
            seen.append(kwargs.get("resolved_entity"))
            return _ro(urls=[_URL])

        monkeypatch.setattr("researcher.decomposed.decomposed_research", spy_research)

        async def fake_probe(client, entity_name, entity_website):
            return ["probe-excluded.example"]

        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", fake_probe)

        from researcher.entity_verifier import entity_verifier_agent

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            entity_verifier_agent.override(model=_verifier_model("verified")),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            config = VerifyConfig(
                model="test", max_sources=2, skip_wayback=True, repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "GreenTest", "product", config=config, entity_ref=ref,
                only=["renewable-energy-hosting"],
                search_hints_exclude=["cli-excluded.example"],
            )

        assert result.status == "accepted", result.errors
        per_template = [r for r in seen if r is not None]
        assert per_template, "per-template research never ran with a resolved entity"
        resolved = per_template[0]
        assert resolved.website == "https://greentest.example"
        assert resolved.parent_company == "companies/greentest-bv"
        assert resolved.search_hints is not None
        assert resolved.search_hints.exclude == [
            "file-excluded.example", "cli-excluded.example", "probe-excluded.example",
        ]

class TestOnboardSubjectFanOut:
    """Subject onboarding queues only templates whose subjects: list names the subject."""

    def _write_subject_entity(self, tmp_path: Path, slug: str, name: str) -> str:
        """Pre-create a subject entity file so onboard_entity skips light research and template-fan-out is exercised in isolation."""
        path = tmp_path / "research" / "entities" / "subjects" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {name}\ntype: subject\ndescription: A test subject.\n---\n"
        )
        return f"subjects/{slug}"

    @pytest.mark.asyncio
    async def test_referenced_subject_queues_only_matching_templates(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        _setup_tmp_repo(tmp_path)
        ref = self._write_subject_entity(tmp_path, "ai-model-producers", "AI Model Producers")

        claim_research([])
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            config = VerifyConfig(
                model="test", max_sources=1, skip_wayback=True, repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "AI Model Producers", "subject", config=config, entity_ref=ref,
            )

        assert result.status == "accepted"
        # templates.yaml lists exactly two subject templates pairing with subjects/ai-model-producers
        applied = set(result.templates_applied)
        assert applied == {
            "ai-producers-signed-safety-commitments",
            "ai-producers-existential-score",
        }

    @pytest.mark.asyncio
    async def test_unreferenced_subject_warns_and_proceeds(
        self, tmp_path: Path, monkeypatch, claim_research
    ) -> None:
        """Subject onboard with no matching ``subjects:`` template warns; does not halt.

        The entity is first-class — the file should still land. Per the
        plan's Step 10: surface a warning row in the report rather
        than aborting the run.
        """
        _setup_tmp_repo(tmp_path)
        ref = self._write_subject_entity(tmp_path, "unreferenced-test-subject", "Unreferenced Test Subject")

        claim_research([])
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        with (
            ingestor_agent.override(model=_ingestor_model()),
            analyst_agent.override(model=_analyst_model()),
            auditor_agent.override(model=_auditor_model()),
            patch.object(Agent, "override", side_effect=lambda **kw: _noop(**kw)),
        ):
            config = VerifyConfig(
                model="test", max_sources=1, skip_wayback=True, repo_root=str(tmp_path),
            )
            result = await onboard_entity(
                "Unreferenced Test Subject", "subject", config=config, entity_ref=ref,
            )

        assert result.status == "accepted"
        assert result.templates_applied == []
        assert any(
            "subjects/unreferenced-test-subject" in w for w in result.warnings
        ), f"expected subject-warning in result.warnings, got {result.warnings!r}"
        # The "No core templates" rejection is reserved for company /
        # product paths now; subjects warn rather than halt.
        assert not any("No core templates" in e for e in result.errors)


class TestGatherLightResearchErrors:
    """Light research returns why no page summary was collected."""

    @pytest.mark.asyncio
    async def test_gather_light_research_keeps_fetch_errors(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import asyncio

        from common.models import EntityType
        from loop.errors import StepError
        from orchestrator.pipeline import gather_light_research

        async def fake_ingest(*args, **kwargs):
            return [], [StepError(
                step="ingest", url="https://ecosia.example",
                error_type="http_403", message="Forbidden", retryable=False,
            )]

        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        bundle = await gather_light_research(
            "Ecosia AI", EntityType.PRODUCT, VerifyConfig(repo_root=str(tmp_path)),
            asyncio.Semaphore(1), None, seed_url="ecosia.example",
        )
        assert bundle.raw_description == ""
        assert any("http_403" in e for e in bundle.fetch_errors)

    @pytest.mark.asyncio
    async def test_gather_light_research_reports_search_errors(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import asyncio

        from common.models import EntityType
        from loop.errors import StepError
        from orchestrator.pipeline import gather_light_research

        async def fake_research(*args, **kwargs):
            return _ro(errors=[StepError(
                step="research", error_type="no_results",
                message="search returned nothing", retryable=False,
            )])

        monkeypatch.setattr("orchestrator.pipeline._research", fake_research)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        bundle = await gather_light_research(
            "Ecosia AI", EntityType.PRODUCT, VerifyConfig(repo_root=str(tmp_path)),
            asyncio.Semaphore(1), None,
        )
        assert bundle.entity_website is None
        assert bundle.raw_description == ""
        assert any("no_results" in e for e in bundle.fetch_errors)

    @pytest.mark.asyncio
    async def test_gather_light_research_reports_no_website(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import asyncio

        from common.models import EntityType
        from orchestrator.pipeline import gather_light_research

        async def fake_research(*args, **kwargs):
            return _ro()

        monkeypatch.setattr("orchestrator.pipeline._research", fake_research)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        bundle = await gather_light_research(
            "Ecosia AI", EntityType.PRODUCT, VerifyConfig(repo_root=str(tmp_path)),
            asyncio.Semaphore(1), None,
        )
        assert bundle.fetch_errors == ["search found no website"]

    @pytest.mark.asyncio
    async def test_gather_light_research_reports_exception(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import asyncio

        from common.models import EntityType
        from orchestrator.pipeline import gather_light_research

        async def fake_research(*args, **kwargs):
            raise RuntimeError("Brave 500")

        monkeypatch.setattr("orchestrator.pipeline._research", fake_research)

        bundle = await gather_light_research(
            "Ecosia AI", EntityType.PRODUCT, VerifyConfig(repo_root=str(tmp_path)),
            asyncio.Semaphore(1), None,
        )
        assert not bundle.has_page_summary
        assert bundle.fetch_errors == ["light research failed: Brave 500"]

    @pytest.mark.asyncio
    async def test_gather_light_research_reports_empty_summary(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import asyncio

        from common.models import EntityType
        from orchestrator.pipeline import gather_light_research

        sf = _make_source_file("https://ecosia.example", "ecosia")
        sf.frontmatter.summary = ""

        async def fake_ingest(*args, **kwargs):
            return [("https://ecosia.example", sf)], []

        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        bundle = await gather_light_research(
            "Ecosia AI", EntityType.PRODUCT, VerifyConfig(repo_root=str(tmp_path)),
            asyncio.Semaphore(1), None, seed_url="ecosia.example",
        )
        assert not bundle.has_page_summary
        assert bundle.fetch_errors == [
            "https://ecosia.example: empty_summary: page fetched but summary empty"
        ]

    @pytest.mark.asyncio
    async def test_gather_light_research_reports_silent_ingest_failure(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A worker that raised leaves no source and no error; the bundle still says why."""
        import asyncio

        from common.models import EntityType
        from orchestrator.pipeline import gather_light_research

        async def fake_ingest(*args, **kwargs):
            return [], []

        monkeypatch.setattr("orchestrator.pipeline._ingest_urls", fake_ingest)
        monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)

        bundle = await gather_light_research(
            "Ecosia AI", EntityType.PRODUCT, VerifyConfig(repo_root=str(tmp_path)),
            asyncio.Semaphore(1), None, seed_url="ecosia.example",
        )
        assert bundle.fetch_errors == [
            "https://ecosia.example: empty_summary: page not ingested and no error recorded"
        ]



