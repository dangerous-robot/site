"""Tests for the dr ingest subcommand CLI."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

import click

from orchestrator.cli import (
    _check_provider_api_keys,
    _required_env_for_model,
    main,
)


class TestIngestCli:
    def test_invalid_url(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ingest", "not-a-url"])
        assert result.exit_code != 0
        assert "invalid url" in (result.output + (result.stderr if hasattr(result, "stderr") else "")).lower()

    def test_missing_url_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ingest"])
        assert result.exit_code != 0
        assert "url" in result.output.lower() or "missing" in result.output.lower()

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["step-ingest", "--help"])
        assert result.exit_code == 0
        assert "Fetch a URL" in result.output
        assert "--write" in result.output
        assert "--skip-wayback" in result.output
        assert "--force" in result.output


class TestRequiredEnvForModel:
    def test_test_model_skipped(self) -> None:
        assert _required_env_for_model("test") == ()

    def test_anthropic_prefix(self) -> None:
        assert _required_env_for_model("anthropic:claude-haiku-4-5-20251001") == ("ANTHROPIC_API_KEY",)

    def test_openai_prefix(self) -> None:
        assert _required_env_for_model("openai:gpt-4o-mini") == ("OPENAI_API_KEY",)

    def test_infomaniak_requires_both_keys(self) -> None:
        assert _required_env_for_model("infomaniak:swiss-ai/Apertus-70B-Instruct-2509") == (
            "INFOMANIAK_API_KEY",
            "INFOMANIAK_PRODUCT_ID",
        )

    def test_greenpt_requires_api_key(self) -> None:
        assert _required_env_for_model("greenpt:gpt-oss-120b") == ("GREENPT_API_KEY",)

    def test_chained_spec_returns_union(self) -> None:
        """``a||b`` returns the stable-ordered union of both legs' required env vars."""
        result = _required_env_for_model(
            "anthropic:claude-haiku-4-5-20251001||greenpt:gpt-oss-120b"
        )
        assert result == ("ANTHROPIC_API_KEY", "GREENPT_API_KEY")

    def test_chained_spec_dedupes_repeated_vars(self) -> None:
        """Two Infomaniak legs union to a single pair of Infomaniak vars."""
        result = _required_env_for_model(
            "infomaniak:openai/gpt-oss-120b||infomaniak:mistral24b"
        )
        assert result == ("INFOMANIAK_API_KEY", "INFOMANIAK_PRODUCT_ID")

    def test_chained_spec_does_not_short_circuit_on_test_leg(self) -> None:
        result = _required_env_for_model("anthropic:claude-haiku-4-5-20251001||test")
        assert result == ("ANTHROPIC_API_KEY",)

    def test_single_test_spec_still_short_circuits(self) -> None:
        """The ``"test" in model`` branch still applies to non-chained specs."""
        assert _required_env_for_model("test") == ()

    def test_bare_string_rejected_with_usage_error(self) -> None:
        with pytest.raises(click.UsageError) as exc:
            _required_env_for_model("gpt-oss-120b")
        assert "no recognized provider prefix" in str(exc.value)
        assert "infomaniak" in str(exc.value)

    def test_unknown_prefix_rejected(self) -> None:
        with pytest.raises(click.UsageError):
            _required_env_for_model("acme:something")


class TestCheckProviderApiKeys:
    def test_single_anthropic_passes_with_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        _check_provider_api_keys("anthropic:claude")

    def test_mixed_providers_require_union_of_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A run with anthropic baseline + infomaniak override must require BOTH providers' keys."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.delenv("INFOMANIAK_API_KEY", raising=False)
        monkeypatch.delenv("INFOMANIAK_PRODUCT_ID", raising=False)
        with pytest.raises(SystemExit) as exc:
            _check_provider_api_keys(["anthropic:claude", "infomaniak:swiss-ai/Apertus-70B-Instruct-2509"])
        assert exc.value.code == 2

    def test_mixed_providers_pass_when_all_keys_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("INFOMANIAK_API_KEY", "y")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "z")
        _check_provider_api_keys(["anthropic:claude", "infomaniak:swiss-ai/Apertus-70B-Instruct-2509"])

    def test_test_model_skips_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        _check_provider_api_keys("test")


class TestDraftBraveKeyCheck:
    """``dr draft`` refuses a Brave backend with no Brave key before any model call."""

    class _Reached(Exception):
        pass

    def _invoke(self, monkeypatch, tmp_path, backend: str):
        path = tmp_path / "research" / "entities" / "products" / "acme.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\nname: Acme\ntype: product\ndescription: A test entity.\n---\n",
            encoding="utf-8",
        )
        reached = self._Reached

        async def _fake_run(*_args, **_kwargs):
            raise reached("loop.run was called")

        monkeypatch.setattr("loop.run", _fake_run)
        monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", backend)
        monkeypatch.delenv("BRAVE_WEB_SEARCH_API_KEY", raising=False)
        return CliRunner().invoke(main, [
            "--model", "test", "draft", "--entity", "products/acme", "x",
            "--repo-root", str(tmp_path),
        ])

    def test_brave_backend_without_key_is_a_usage_error(self, monkeypatch, tmp_path) -> None:
        result = self._invoke(monkeypatch, tmp_path, "brave")
        assert result.exit_code == 2, result.output
        assert "BRAVE_WEB_SEARCH_API_KEY" in result.output
        assert not isinstance(result.exception, self._Reached)

    def test_tavily_backend_without_brave_key_reaches_the_loop(self, monkeypatch, tmp_path) -> None:
        result = self._invoke(monkeypatch, tmp_path, "tavily")
        assert isinstance(result.exception, self._Reached), result.output


class TestPerAgentModelOptions:
    def test_top_level_help_lists_per_agent_options(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for opt in ("--researcher-model", "--analyst-model", "--auditor-model", "--ingestor-model"):
            assert opt in result.output


class TestRemovedCommands:
    """Explicit coverage asserting that hard-removed commands no longer exist in the CLI."""

    def test_verify_removed(self) -> None:
        """dr verify should no longer be registered."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["verify", "--help"])
        assert result.exit_code != 0

    def test_verify_claim_removed(self) -> None:
        """dr verify-claim should no longer be registered."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["verify-claim", "--help"])
        assert result.exit_code != 0


def test_step_analyze_gives_analyst_source_ids_so_year_slug_citations_resolve(tmp_path) -> None:
    research = tmp_path / "research"
    (research / "entities" / "companies").mkdir(parents=True)
    (research / "entities" / "companies" / "acme.md").write_text(
        "---\nname: Acme\ntype: company\n---\n", encoding="utf-8"
    )
    (research / "claims" / "acme").mkdir(parents=True)
    (research / "claims" / "acme" / "green.md").write_text(
        "---\ntitle: Acme is green\nentity: companies/acme\nsources:\n- 2026/foo\n---\nBody.\n",
        encoding="utf-8",
    )
    (research / "sources" / "2026").mkdir(parents=True)
    (research / "sources" / "2026" / "foo.md").write_text(
        "---\nurl: https://acme.com/foo\ntitle: Foo Report\npublisher: Acme\n"
        "kind: report\nsummary: About foo.\n---\nFoo body.\n",
        encoding="utf-8",
    )

    from contextlib import nullcontext

    from analyst.agent import verdict_only_agent
    from tests.loop_harness import capturing_model

    captured: list[str] = []
    model = capturing_model(captured, {
        "title": "Acme is green", "verdict": "unverified", "confidence": "low",
        "narrative": "Acme says so 【2026/foo】.", "topics": ["environmental-impact"],
        "verification_level": "claimed", "cap_rationale": "Only Acme's own report addresses the claim.",
        "seo_title": "Acme green claim",
    })
    with verdict_only_agent.override(model=model), patch.object(
        verdict_only_agent, "override", side_effect=lambda **kw: nullcontext(),
    ):
        result = CliRunner().invoke(
            main,
            ["--model", "test", "step-analyze", "--claim", "acme/green", "--repo-root", str(tmp_path)],
        )

    assert result.exit_code == 0, result.output
    assert "Level:      claimed" in result.output
    # The analyst sees the year/slug id, so a citation token by id resolves to the title.
    assert any("2026/foo" in p for p in captured)
    assert "*Foo Report*" in result.output
    assert "【" not in result.output


def test_step_analyze_write_keeps_the_entity_match_override(tmp_path) -> None:
    """--write records the Off-entity relabel and fits the level to it, as dr draft does."""
    from contextlib import nullcontext

    from pydantic_ai.models.test import TestModel

    from analyst.agent import verdict_only_agent
    from common.frontmatter import parse_frontmatter

    research = tmp_path / "research"
    (research / "entities" / "companies").mkdir(parents=True)
    (research / "entities" / "companies" / "acme.md").write_text(
        "---\nname: Acme\ntype: company\nwebsite: https://acme.com\n---\n", encoding="utf-8"
    )
    (research / "claims" / "acme").mkdir(parents=True)
    claim_path = research / "claims" / "acme" / "green.md"
    claim_path.write_text(
        "---\ntitle: Acme is green\nentity: companies/acme\nsources:\n- 2026/grid-news\n---\nBody.\n",
        encoding="utf-8",
    )
    (research / "sources" / "2026").mkdir(parents=True)
    (research / "sources" / "2026" / "grid-news.md").write_text(
        "---\nurl: https://news.example.com/grid\ntitle: Grid News\npublisher: Daily News\n"
        "kind: article\nindependence: independent\nsummary: Data centers use more power.\n---\n"
        "Data centers use more power.\n",
        encoding="utf-8",
    )
    model = TestModel(custom_output_args={
        "title": "Acme is green",
        "verdict": "true",
        "confidence": "high",
        "narrative": "Grid News says so.",
        "topics": ["environmental-impact"],
        "verification_level": "independently-verified",
        "seo_title": "Acme green claim",
    })

    with verdict_only_agent.override(model=model), patch.object(
        verdict_only_agent, "override",
        side_effect=lambda **kw: nullcontext(),
    ):
        result = CliRunner().invoke(
            main,
            [
                "--model", "test", "step-analyze", "--claim", "acme/green",
                "--write", "--force", "--repo-root", str(tmp_path),
            ],
        )

    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    [override] = fm["source_overrides"]
    assert override["source"] == "2026/grid-news"
    assert override["independence"] == "unknown"
    assert override["reason"].startswith("Off-entity:")
    assert fm["verification_level"] == "claimed"


def _published_claim_repo(tmp_path):
    """A published, signed-off claim (verdict true) with its sidecar."""
    import yaml

    research = tmp_path / "research"
    (research / "entities" / "companies").mkdir(parents=True)
    (research / "entities" / "companies" / "acme.md").write_text(
        "---\nname: Acme\ntype: company\nwebsite: https://acme.com\n---\n", encoding="utf-8"
    )
    (research / "claims" / "acme").mkdir(parents=True)
    claim_path = research / "claims" / "acme" / "green.md"
    claim_path.write_text(
        "---\ntitle: Acme is green\nentity: companies/acme\nverdict: 'true'\nconfidence: high\n"
        "status: published\nas_of: '2026-10-01'\nsources:\n- 2026/report\n---\nBody.\n",
        encoding="utf-8",
    )
    (research / "sources" / "2026").mkdir(parents=True)
    (research / "sources" / "2026" / "report.md").write_text(
        "---\nurl: https://acme.com/report\ntitle: Acme Report\npublisher: Acme\n"
        "kind: report\nsummary: Acme says it is green.\n---\nAcme says it is green.\n",
        encoding="utf-8",
    )
    sidecar_path = claim_path.with_name("green.audit.yaml")
    sidecar_path.write_text(yaml.safe_dump({
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst"]},
        "sources_consulted": [],
        "audit": None,
        "human_review": {
            "reviewed_at": "2026-10-02", "reviewer": "reviewer@example.org",
            "notes": None, "pr_url": None,
        },
    }), encoding="utf-8")
    return claim_path, sidecar_path


def _step_analyze_write(tmp_path, verdict: str, **output):
    from contextlib import nullcontext

    from pydantic_ai.models.test import TestModel

    from analyst.agent import verdict_only_agent

    model = TestModel(custom_output_args={
        "title": "Acme is green",
        "verdict": verdict,
        "confidence": "low",
        "narrative": "Acme Report says so.",
        "topics": ["environmental-impact"],
        "verification_level": "self-reported",
        "cap_rationale": "Only Acme says so.",
        "seo_title": "Acme green claim",
        **output,
    })
    with verdict_only_agent.override(model=model), patch.object(
        verdict_only_agent, "override",
        side_effect=lambda **kw: nullcontext(),
    ):
        return CliRunner().invoke(
            main,
            [
                "--model", "test", "--analyst-model", "test", "step-analyze", "--claim", "acme/green",
                "--write", "--force", "--repo-root", str(tmp_path),
            ],
        )


@pytest.mark.parametrize("status", ["published", "archived"])
def test_step_analyze_write_refuses_a_live_claim(tmp_path, status) -> None:
    """From RE-AW (Recheck) on, no write lands on a published or archived claim
    in place: the refusal names `dr recheck --claim`, which writes a pending
    draft. Nothing is written."""
    from common.frontmatter import parse_frontmatter, serialize_frontmatter

    claim_path, sidecar_path = _published_claim_repo(tmp_path)
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    claim_path.write_text(serialize_frontmatter({**fm, "status": status}, body), encoding="utf-8")
    before = (claim_path.read_bytes(), sidecar_path.read_bytes())

    result = _step_analyze_write(tmp_path, "false")

    assert result.exit_code == 2, result.output
    assert "dr recheck --claim acme/green" in result.output
    assert (claim_path.read_bytes(), sidecar_path.read_bytes()) == before


def test_step_analyze_write_leaves_a_draft_claims_sidecar_alone(tmp_path) -> None:
    import yaml

    from common.frontmatter import parse_frontmatter, serialize_frontmatter

    claim_path, sidecar_path = _published_claim_repo(tmp_path)
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    claim_path.write_text(serialize_frontmatter({**fm, "status": "draft"}, body), encoding="utf-8")
    before = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))

    result = _step_analyze_write(tmp_path, "false")

    assert result.exit_code == 0, result.output
    assert parse_frontmatter(claim_path.read_text(encoding="utf-8"))[0]["status"] == "draft"
    after = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    after.pop("analyst_record")  # the claim write's own record
    assert after == before


@pytest.mark.parametrize(
    "previous",
    [{"status": "blocked", "blocked_reason": "insufficient_sources"}],
    ids=["blocked"],
)
def test_step_analyze_write_returns_a_non_draft_claim_to_draft(tmp_path, previous) -> None:
    """A blocked claim with a verdict is no longer blocked (published and
    archived claims are refused above)."""
    import yaml

    from common.frontmatter import parse_frontmatter, serialize_frontmatter

    claim_path, sidecar_path = _published_claim_repo(tmp_path)
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    claim_path.write_text(serialize_frontmatter({**fm, **previous}, body), encoding="utf-8")

    result = _step_analyze_write(tmp_path, "false")

    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm["status"] == "draft"
    assert "blocked_reason" not in fm
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["human_review"]["reviewed_at"] is None
    assert "refresh" not in sidecar


def _add_audit_block(sidecar_path, analyst_verdict: str = "true") -> None:
    """Give the sidecar the Evaluator's comparison of the claim on disk."""
    import yaml

    data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    data["audit"] = {
        "analyst_verdict": analyst_verdict, "auditor_verdict": "false",
        "analyst_confidence": "high", "auditor_confidence": "medium",
        "verdict_agrees": False, "confidence_agrees": False, "needs_review": True,
        "auditor_reasoning": "The report is self-published.",
        "evidence_gaps": [], "needs_review_reasons": ["verdict_disagreement"],
    }
    sidecar_path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.mark.parametrize("status", ["draft"])
def test_step_analyze_write_clears_the_evaluators_comparison(tmp_path, status) -> None:
    """The Evaluator graded the old analysis, so the claim page must not show
    it agreeing or disagreeing with the new verdict until dr step-audit
    --write grades the new one."""
    import yaml

    from common.frontmatter import parse_frontmatter, serialize_frontmatter

    claim_path, sidecar_path = _published_claim_repo(tmp_path)
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    claim_path.write_text(serialize_frontmatter({**fm, "status": status}, body), encoding="utf-8")
    _add_audit_block(sidecar_path)

    result = _step_analyze_write(tmp_path, "false")

    assert result.exit_code == 0, result.output
    assert yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))["audit"] is None


def test_approval_after_step_analyze_records_no_override(tmp_path, human_at_terminal) -> None:
    """A verdict the analyst changed is not a reviewer's override."""
    import yaml

    from common.frontmatter import parse_frontmatter, serialize_frontmatter
    from orchestrator.review import approve_claim

    claim_path, sidecar_path = _published_claim_repo(tmp_path)
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    # A draft: from RE-AW (Recheck) on, step-analyze refuses a published claim.
    claim_path.write_text(
        serialize_frontmatter({**fm, "status": "draft", "criteria_slug": "green-claim"}, body), encoding="utf-8"
    )
    _add_audit_block(sidecar_path)

    result = _step_analyze_write(tmp_path, "false")
    assert result.exit_code == 0, result.output
    approve_claim(claim_path, reviewer="reviewer@example.org", mode="approve")

    review = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))["human_review"]
    assert review["verdict_override"] is None


def test_step_analyze_write_takes_the_analysts_seo_title_and_takeaway(tmp_path) -> None:
    """The keep rules decide, as on the other write paths: values the analyst
    last wrote are replaced, and the record follows the new run."""
    import yaml

    from common.frontmatter import parse_frontmatter, serialize_frontmatter

    claim_path, sidecar_path = _published_claim_repo(tmp_path)
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    claim_path.write_text(serialize_frontmatter({
        **fm, "status": "draft", "title": "Acme was green",
        "seo_title": "Acme was green", "takeaway": "Acme was green last year.",
    }, body), encoding="utf-8")
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    sidecar["analyst_record"] = {
        "title": "Acme was green", "seo_title": "Acme was green", "verdict": "true",
        "takeaway": "Acme was green last year.", "cap_rationale": None,
    }
    sidecar_path.write_text(yaml.safe_dump(sidecar), encoding="utf-8")

    result = _step_analyze_write(tmp_path, "false", takeaway="Acme is no longer green.")

    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    # The stored sentence (here the title, no statement yet) is written as both.
    assert fm["title"] == fm["statement"] == "Acme was green"
    assert fm["seo_title"] == "Acme green claim"
    assert fm["takeaway"] == "Acme is no longer green."
    record = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))["analyst_record"]
    assert record["title"] == "Acme was green"
    assert record["seo_title"] == "Acme green claim"
    assert record["takeaway"] == "Acme is no longer green."


class TestStepAnalyzeCriterion:
    SENTINEL = "SENTINEL-NOTES: mixed = offsets only"

    def _write_repo(self, tmp_path, criteria_slug: str, templates: list | None) -> None:
        import yaml

        research = tmp_path / "research"
        (research / "entities" / "companies").mkdir(parents=True)
        (research / "entities" / "companies" / "acme.md").write_text(
            "---\nname: Acme\ntype: company\n---\n", encoding="utf-8"
        )
        (research / "claims" / "acme").mkdir(parents=True)
        (research / "claims" / "acme" / "green.md").write_text(
            "---\ntitle: Acme title fallback\nentity: companies/acme\n"
            f"criteria_slug: {criteria_slug}\nsources: []\n---\nBody.\n",
            encoding="utf-8",
        )
        if templates is not None:
            (research / "templates.yaml").write_text(
                yaml.safe_dump({"templates": templates}), encoding="utf-8"
            )

    def _run(self, tmp_path) -> tuple:
        from contextlib import nullcontext

        from analyst.agent import verdict_only_agent
        from tests.loop_harness import capturing_model

        captured: list[str] = []
        model = capturing_model(captured, {
            "title": "Acme is green", "verdict": "unverified", "confidence": "low",
            "narrative": "N.", "topics": ["environmental-impact"], "verification_level": "claimed",
            "cap_rationale": "Only Acme says so.", "seo_title": "Acme green claim",
        })
        with verdict_only_agent.override(model=model), patch.object(
            verdict_only_agent, "override", side_effect=lambda **kw: nullcontext(),
        ):
            result = CliRunner().invoke(
                main,
                ["--model", "test", "step-analyze", "--claim", "acme/green", "--repo-root", str(tmp_path)],
            )
        return result, captured

    def test_grading_rule_reaches_analyst_and_notes_do_not(self, tmp_path) -> None:
        """The criterion's ``grading_rule`` is the text the analyst gets; ``notes`` is
        reader-facing. The claim is assessed as stored (``title`` here, no ``statement``)."""
        self._write_repo(tmp_path, "green-hosting", [
            {"slug": "green-hosting", "text": "COMPANY is hosted on renewable energy", "entity_type": "company", "topics": ["environmental-impact"], "core": True, "notes": "NOTES-ONLY reader text", "grading_rule": self.SENTINEL},
        ])
        result, captured = self._run(tmp_path)
        assert result.exit_code == 0, result.output
        prompt = "\n".join(captured)
        assert "Acme title fallback" in prompt
        assert "Acme is hosted on renewable energy" not in prompt
        assert f"## Criterion notes\n{self.SENTINEL}" in prompt
        assert "NOTES-ONLY" not in prompt

    def test_unknown_criteria_slug_falls_back_to_title(self, tmp_path) -> None:
        self._write_repo(tmp_path, "not-a-template", [
            {"slug": "green-hosting", "text": "COMPANY is hosted on renewable energy", "entity_type": "company", "topics": ["environmental-impact"], "core": True},
        ])
        result, captured = self._run(tmp_path)
        assert result.exit_code == 0, result.output
        prompt = "\n".join(captured)
        assert "Acme title fallback" in prompt
        assert "## Criterion notes" not in prompt

    def test_missing_templates_file_falls_back_to_title(self, tmp_path) -> None:
        self._write_repo(tmp_path, "green-hosting", None)
        result, captured = self._run(tmp_path)
        assert result.exit_code == 0, result.output
        prompt = "\n".join(captured)
        assert "Acme title fallback" in prompt
        assert "## Criterion notes" not in prompt


# --------------------------------------------------------------------------- #
# Archive links in code: dr step-ingest and dr recheck --sources              #
# --------------------------------------------------------------------------- #

_ARCHIVE_PAGE_URL = "https://example.org/page"
_ARCHIVE_PAGE = "<html><head><title>Page</title></head><body><p>The stored page.</p></body></html>"


def _archive_ts(days_ago: float) -> str:
    import datetime

    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return when.strftime("%Y%m%d%H%M%S")


# A recent capture, so the freshness refresh after a live fetch leaves it alone.
_ARCHIVE_SNAPSHOT = f"https://web.archive.org/web/{_archive_ts(1)}/https://example.org/page"
_DONE_SNAPSHOT = f"https://web.archive.org/web/{_archive_ts(1)}/https://example.org/done"


def _timegate_re():
    import re

    return re.compile(r"https://web\.archive\.org/web/\d{14}/.+")


def _save_re():
    import re

    return re.compile(r"https://web\.archive\.org/save/.+")


def _live_page(mock, url: str = _ARCHIVE_PAGE_URL):
    """Mock the live fetch `dr recheck --sources` makes before each lookup."""
    import httpx

    return mock.get(url).mock(return_value=httpx.Response(200, text=_ARCHIVE_PAGE))


@pytest.fixture
def no_archive_wait(monkeypatch):
    async def _no_wait(seconds: float) -> None:
        return None

    monkeypatch.setattr("ingestor.tools.wayback._wait", _no_wait)


class TestStepIngestArchive:
    def _invoke(self, tmp_path, *flags: str):
        (tmp_path / "research" / "sources").mkdir(parents=True, exist_ok=True)
        return CliRunner().invoke(
            main,
            [
                "--model", "test", "--ingestor-model", "test",
                "step-ingest", _ARCHIVE_PAGE_URL, *flags, "--repo-root", str(tmp_path),
            ],
        )

    def test_read_only_prints_the_snapshot_and_never_saves(
        self, tmp_path, stub_ingest_model, mock_capture_replay
    ) -> None:
        import httpx
        import respx

        with respx.mock as mock:
            mock_capture_replay()
            mock.get(_ARCHIVE_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCHIVE_PAGE))
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": _ARCHIVE_SNAPSHOT})
            )
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert f"archived_url: {_ARCHIVE_SNAPSHOT}" in result.output
        assert save.called is False

    def test_read_only_model_wayback_check_makes_no_capture(
        self, tmp_path, stub_ingest_model_calling_wayback
    ) -> None:
        import httpx
        import respx

        with respx.mock as mock:
            mock.get(_ARCHIVE_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCHIVE_PAGE))
            timegate = mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
            save = mock.get(_save_re()).mock(
                return_value=httpx.Response(302, headers={"location": _ARCHIVE_SNAPSHOT})
            )
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        # The model's tool call and the lookup in code each checked TimeGate.
        assert timegate.call_count == 2
        assert save.called is False

    def test_deprecated_ingest_dry_run_makes_no_capture(
        self, tmp_path, stub_ingest_model_calling_wayback
    ) -> None:
        import httpx
        import respx

        (tmp_path / "research" / "sources").mkdir(parents=True, exist_ok=True)
        with respx.mock as mock:
            mock.get(_ARCHIVE_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCHIVE_PAGE))
            timegate = mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
            save = mock.get(_save_re()).mock(
                return_value=httpx.Response(302, headers={"location": _ARCHIVE_SNAPSHOT})
            )
            result = CliRunner().invoke(
                main,
                [
                    "--model", "test", "--ingestor-model", "test",
                    "ingest", _ARCHIVE_PAGE_URL, "--dry-run", "--repo-root", str(tmp_path),
                ],
            )

        assert result.exit_code == 0, result.output
        assert timegate.call_count == 2
        assert save.called is False

    def test_read_only_miss_reports_it_without_a_capture(self, tmp_path, stub_ingest_model) -> None:
        import httpx
        import respx

        with respx.mock as mock:
            mock.get(_ARCHIVE_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCHIVE_PAGE))
            mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert "archived_url" not in result.output
        assert "Archive lookup failed" in result.output
        assert save.called is False

    def test_write_records_a_rate_limit_as_an_error_line(
        self, tmp_path, stub_ingest_model, no_archive_wait
    ) -> None:
        import httpx
        import respx

        with respx.mock as mock:
            mock.get(_ARCHIVE_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCHIVE_PAGE))
            mock.get(_timegate_re()).mock(return_value=httpx.Response(429))
            result = self._invoke(tmp_path, "--write")

        assert result.exit_code == 0, result.output
        error_lines = [ln for ln in result.output.splitlines() if "Archive lookup failed" in ln]
        assert len(error_lines) == 1 and "429" in error_lines[0]
        written = (tmp_path / "research" / "sources" / "2026" / "page.md").read_text()
        assert "archived_url" not in written

    def test_write_saves_on_a_miss(self, tmp_path, stub_ingest_model, mock_capture_replay) -> None:
        import httpx
        import respx

        with respx.mock as mock:
            mock_capture_replay()
            mock.get(_ARCHIVE_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCHIVE_PAGE))
            mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
            mock.get(_save_re()).mock(
                return_value=httpx.Response(200, headers={"content-location": _ARCHIVE_SNAPSHOT})
            )
            result = self._invoke(tmp_path, "--write")

        assert result.exit_code == 0, result.output
        written = (tmp_path / "research" / "sources" / "2026" / "page.md").read_text()
        assert f"archived_url: {_ARCHIVE_SNAPSHOT}" in written

    def test_skip_wayback_makes_no_archive_request(self, tmp_path, stub_ingest_model) -> None:
        import httpx
        import respx

        with respx.mock as mock:
            mock.get(_ARCHIVE_PAGE_URL).mock(return_value=httpx.Response(200, html=_ARCHIVE_PAGE))
            timegate = mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
            result = self._invoke(tmp_path, "--skip-wayback")

        assert result.exit_code == 0, result.output
        assert timegate.called is False


def test_step_audit_write_keeps_the_archive_record(tmp_path) -> None:
    """A re-audit rebuilds sources_consulted; the archive outcome must survive it."""
    import yaml

    from common.frontmatter import serialize_frontmatter

    (tmp_path / "research" / "entities" / "companies").mkdir(parents=True)
    (tmp_path / "research" / "entities" / "companies" / "example.md").write_text(
        serialize_frontmatter(
            {"name": "Example", "type": "company", "description": "A company."}, "Body.\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "research" / "sources" / "2026").mkdir(parents=True)
    (tmp_path / "research" / "sources" / "2026" / "page.md").write_text(
        serialize_frontmatter(
            {"url": _ARCHIVE_PAGE_URL, "title": "Page", "publisher": "Example",
             "accessed_date": "2026-10-07", "kind": "article", "summary": "The page."},
            "The page.\n",
        ),
        encoding="utf-8",
    )
    claim_dir = tmp_path / "research" / "claims" / "example"
    claim_dir.mkdir(parents=True)
    # The verdict is the TestModel Evaluator's (true, high): the pair agrees, so no tie-breaker runs.
    (claim_dir / "claim.md").write_text(
        serialize_frontmatter(
            {"title": "Example claim", "entity": "companies/example", "verdict": "true",
             "confidence": "high", "topics": ["environmental-impact"], "sources": ["2026/page"]},
            "Body.\n",
        ),
        encoding="utf-8",
    )
    archive = {"status": "failed", "error": "archive.org TimeGate check failed (HTTP 429)"}
    (claim_dir / "claim.audit.yaml").write_text(
        yaml.safe_dump({
            "schema_version": 1,
            "sources_consulted": [{
                "id": "2026/page", "url": _ARCHIVE_PAGE_URL, "title": "Page",
                "ingested": True, "archive": archive,
            }],
        }),
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, [
        "--model", "test", "--auditor-model", "test", "step-audit", "--claim", "example/claim", "--write",
        "--repo-root", str(tmp_path),
    ])

    assert result.exit_code == 0, result.output
    data = yaml.safe_load((claim_dir / "claim.audit.yaml").read_text(encoding="utf-8"))
    assert data["pipeline_run"]["agents"] == ["auditor"]
    assert data["sources_consulted"][0]["archive"] == archive


def _step_audit_write(tmp_path, sidecar: dict) -> dict:
    """Run dr step-audit --write on a one-claim repo with this sidecar; return the new sidecar."""
    import yaml

    from common.frontmatter import serialize_frontmatter

    (tmp_path / "research" / "entities" / "companies").mkdir(parents=True)
    (tmp_path / "research" / "entities" / "companies" / "example.md").write_text(
        serialize_frontmatter(
            {"name": "Example", "type": "company", "description": "A company."}, "Body.\n"
        ),
        encoding="utf-8",
    )
    claim_dir = tmp_path / "research" / "claims" / "example"
    claim_dir.mkdir(parents=True)
    # The verdict is the TestModel Evaluator's (true, high): the pair agrees, so no tie-breaker runs.
    (claim_dir / "claim.md").write_text(
        serialize_frontmatter(
            {"title": "Example claim", "entity": "companies/example", "verdict": "true",
             "confidence": "high", "topics": ["environmental-impact"], "sources": []},
            "Body.\n",
        ),
        encoding="utf-8",
    )
    (claim_dir / "claim.audit.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "sources_consulted": [], **sidecar}),
        encoding="utf-8",
    )

    # --auditor-model is explicit so a DR_AUDITOR_MODEL in the developer's
    # .env cannot send this test to a live model.
    result = CliRunner().invoke(main, [
        "--model", "test", "--auditor-model", "test",
        "step-audit", "--claim", "example/claim", "--write",
        "--repo-root", str(tmp_path),
    ])

    assert result.exit_code == 0, result.output
    data = yaml.safe_load((claim_dir / "claim.audit.yaml").read_text(encoding="utf-8"))
    assert data["pipeline_run"]["agents"] == ["auditor"]
    return data


def test_step_audit_write_keeps_the_models_of_agents_it_did_not_run(tmp_path) -> None:
    """A re-audit replaces only the Evaluator's model; the record of who wrote the claim stays."""
    data = _step_audit_write(tmp_path, {
        "models_used": {
            "researcher": "infomaniak:researcher-model",
            "ingestor": "infomaniak:ingestor-model",
            "analyst": "infomaniak:analyst-model",
            "auditor": "infomaniak:old-auditor-model",
        },
    })

    assert data["models_used"] == {
        "researcher": "infomaniak:researcher-model",
        "ingestor": "infomaniak:ingestor-model",
        "analyst": "infomaniak:analyst-model",
        "auditor": "test",
    }


def test_step_audit_write_keeps_the_level_fit_note(tmp_path) -> None:
    """The claim is not rewritten, so the note on why its level differs from the analyst's still holds."""
    note = "verification_level independently-verified lowered to claimed: the written sources include 0"
    data = _step_audit_write(tmp_path, {
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m",
                         "agents": ["analyst"], "level_clamp": note},
    })

    assert data["pipeline_run"]["level_clamp"] == note


class TestRecheckSourcesBackfill:
    _SOURCE = (
        "---\n"
        "url: https://example.org/page\n"
        "title: Page\n"
        "publisher: Example\n"
        "accessed_date: '2026-05-04'\n"
        "kind: article\n"
        "summary: A long summary that a YAML round trip could re-wrap differently from how\n"
        "  it is stored now.\n"
        "---\n"
        "Body.\n"
    )

    def _repo(self, tmp_path):
        sources = tmp_path / "research" / "sources" / "2026"
        sources.mkdir(parents=True)
        (sources / "page.md").write_text(self._SOURCE, encoding="utf-8")
        (sources / "done.md").write_text(
            self._SOURCE.replace(
                "url: https://example.org/page\n",
                f"url: https://example.org/done\narchived_url: {_DONE_SNAPSHOT}\n",
            ),
            encoding="utf-8",
        )
        return sources

    def _invoke(self, tmp_path, *ids: str):
        return CliRunner().invoke(
            main, ["recheck", "--sources", *ids, "--repo-root", str(tmp_path)]
        )

    def test_adds_only_the_archived_url_line(self, tmp_path, mock_capture_replay) -> None:
        import httpx
        import respx

        sources = self._repo(tmp_path)
        with respx.mock as mock:
            mock_capture_replay()
            _live_page(mock)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": _ARCHIVE_SNAPSHOT})
            )
            _live_page(mock, "https://example.org/done")
            done_before = (sources / "done.md").read_bytes()
            result = self._invoke(tmp_path, "2026/page", "2026/done")

        assert result.exit_code == 0, result.output
        expected = self._SOURCE.replace(
            "url: https://example.org/page\n",
            f"url: https://example.org/page\narchived_url: {_ARCHIVE_SNAPSHOT}\n",
        )
        assert (sources / "page.md").read_text() == expected
        # A source that already has a good link is rechecked and left byte for byte.
        assert any(line.startswith("2026/done:") for line in result.output.splitlines()), result.output
        assert (sources / "done.md").read_bytes() == done_before

    def test_failure_prints_the_reason_and_exits_nonzero(self, tmp_path, no_archive_wait) -> None:
        import httpx
        import respx

        sources = self._repo(tmp_path)
        with respx.mock as mock:
            _live_page(mock)
            mock.get(_timegate_re()).mock(return_value=httpx.Response(429))
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path, "2026/page")

        assert result.exit_code == 1
        assert "2026/page: archive lookup failed" in result.output
        assert "429" in result.output
        assert (sources / "page.md").read_text() == self._SOURCE
        assert save.called is False

    def test_unknown_source_id_fails(self, tmp_path) -> None:
        self._repo(tmp_path)
        result = self._invoke(tmp_path, "2026/missing")
        assert result.exit_code == 1
        assert "2026/missing: not found" in result.output

    def test_backfill_passes_no_freshness(self, tmp_path, mock_capture_replay) -> None:
        """Only the ingest refreshes, so an old good capture is recorded without a save."""
        import httpx
        import respx

        old = f"https://web.archive.org/web/{_archive_ts(300)}/https://example.org/page"
        sources = self._repo(tmp_path)
        with respx.mock as mock:
            mock_capture_replay()
            _live_page(mock)
            mock.get(_timegate_re()).mock(return_value=httpx.Response(302, headers={"location": old}))
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path, "2026/page")

        assert result.exit_code == 0, result.output
        assert f"archived_url: {old}\n" in (sources / "page.md").read_text()
        assert save.called is False


class TestRecheckSources:
    _URL = "https://example.org/page"
    _BAD = f"https://web.archive.org/web/{_archive_ts(2)}/https://example.org/page"

    def _source(self, archived_url: str | None) -> str:
        link = f"archived_url: {archived_url}\n" if archived_url else ""
        return (
            "---\n"
            f"url: {self._URL}\n"
            f"{link}"
            "title: Page\n"
            "publisher: Example\n"
            "published_date: '2025-12-09'\n"
            "accessed_date: '2026-05-04'\n"
            "kind: article\n"
            "summary: A long summary that a YAML round trip could re-wrap differently from how\n"
            "  it is stored now.\n"
            "---\n"
            "Body.\n"
        )

    def _write(self, tmp_path, archived_url: str | None):
        path = tmp_path / "research" / "sources" / "2026" / "page.md"
        path.parent.mkdir(parents=True)
        path.write_text(self._source(archived_url), encoding="utf-8")
        return path

    def _invoke(self, tmp_path):
        return CliRunner().invoke(
            main, ["recheck", "--sources", "2026/page", "--repo-root", str(tmp_path)]
        )

    @staticmethod
    def _replay(link: str) -> str:
        return link.replace("/https://", "id_/https://", 1)

    @staticmethod
    def _replayed(status: int):
        import httpx

        return httpx.Response(status, headers={"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT"})

    def test_recheck_sources_replaces_error_capture(self, tmp_path) -> None:
        import re

        import httpx
        import respx

        good_ts = _archive_ts(30)
        good = f"https://web.archive.org/web/{good_ts}/{self._URL}"
        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(404))
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            mock.get(re.compile(r"https://web\.archive\.org/cdx/search/cdx.*")).mock(
                return_value=httpx.Response(
                    200, json=[["timestamp", "original", "statuscode"], [good_ts, self._URL, "200"]]
                )
            )
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert path.read_text() == self._source(good)
        assert f"2026/page: {self._BAD} -> {good}" in result.output
        assert save.called is False

    def test_recheck_unchanged(self, tmp_path) -> None:
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(200))
            timegate = mock.get(_timegate_re())
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert "2026/page: unchanged" in result.output
        assert path.read_text() == self._source(self._BAD)
        assert timegate.called is False

    def test_recheck_keeps_the_link_when_no_good_capture(self, tmp_path) -> None:
        """Closes the backlog row "`--recheck` removes a bad link before another
        capture is found": the old link stays until a replacement passes its check."""
        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(404))
            mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert "removed" not in result.output
        assert "archive.org capture is an error page (HTTP 404)" in result.output
        assert "no other 200 capture found" in result.output
        assert save.called is False

    def test_recheck_unverified_leaves_file(self, tmp_path) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(side_effect=httpx.ConnectError("down"))
            timegate = mock.get(_timegate_re())
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert "ConnectError" in result.output
        assert timegate.called is False

    def test_recheck_after_timegate_429_keeps_the_link_and_says_the_search_did_not_finish(
        self, tmp_path, no_archive_wait
    ) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(404))
            mock.get(_timegate_re()).mock(return_value=httpx.Response(429))
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert "archive.org TimeGate check failed (HTTP 429)" in result.output
        assert "no other 200 capture found" not in result.output
        assert "rerun `dr recheck --sources 2026/page` later" in result.output

    _MOVED = "https://example.org/moved"

    def _captured_redirect(self, mock, link: str) -> None:
        """The capture ``link`` of the page replays a 301 to a 200 capture of ``_MOVED``."""
        import httpx

        ts = link.split("/web/", 1)[1].split("/", 1)[0]
        moved = f"https://web.archive.org/web/{ts}id_/{self._MOVED}"
        mock.head(self._replay(link)).mock(
            return_value=httpx.Response(
                301,
                headers={"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT", "location": moved},
            )
        )
        mock.head(moved).mock(return_value=self._replayed(200))

    def _live_redirect(self, mock) -> None:
        import httpx

        mock.get(self._URL).mock(
            return_value=httpx.Response(301, headers={"location": self._MOVED})
        )
        _live_page(mock, self._MOVED)

    def test_recheck_keeps_capture_that_redirects_where_the_live_page_ends(
        self, tmp_path
    ) -> None:
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            self._live_redirect(mock)
            self._captured_redirect(mock, self._BAD)
            timegate = mock.get(_timegate_re())
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert "2026/page: unchanged" in result.output
        assert path.read_text() == self._source(self._BAD)
        assert timegate.called is False

    def test_recheck_rejects_captured_redirect_when_live_page_does_not_load(
        self, tmp_path
    ) -> None:
        import re

        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            mock.get(self._URL).mock(side_effect=httpx.ConnectError("down"))
            self._captured_redirect(mock, self._BAD)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            mock.get(re.compile(r"https://web\.archive\.org/cdx/search/cdx.*")).mock(
                return_value=httpx.Response(200, json=[["timestamp", "original", "statuscode"]])
            )
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert f"archive.org capture redirects to {self._MOVED}" in result.output
        assert "no other 200 capture found" in result.output

    def test_backfill_records_capture_that_redirects_where_the_live_page_ends(
        self, tmp_path
    ) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, None)
        with respx.mock as mock:
            self._live_redirect(mock)
            self._captured_redirect(mock, self._BAD)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert path.read_text() == self._source(self._BAD)
        assert save.called is False

    def test_recheck_without_a_link_backfills(self, tmp_path, mock_capture_replay) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, None)
        with respx.mock as mock:
            mock_capture_replay()
            _live_page(mock)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert path.read_text() == self._source(self._BAD)


def test_step_audit_sends_claim_title(tmp_path) -> None:
    """step-audit grades the claim statement in the frontmatter title, not only the body."""
    from contextlib import nullcontext

    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    from auditor.agent import auditor_agent
    from common.frontmatter import serialize_frontmatter

    (tmp_path / "research" / "entities" / "companies").mkdir(parents=True)
    (tmp_path / "research" / "entities" / "companies" / "example.md").write_text(
        serialize_frontmatter(
            {"name": "Example", "type": "company", "description": "A company."}, "Body.\n"
        ),
        encoding="utf-8",
    )
    claim_title = "Example hosts its chatbot on renewable energy"
    claim_dir = tmp_path / "research" / "claims" / "example"
    claim_dir.mkdir(parents=True)
    (claim_dir / "claim.md").write_text(
        serialize_frontmatter(
            {"title": claim_title, "entity": "companies/example", "verdict": "unverified",
             "confidence": "low", "topics": ["environmental-impact"], "sources": []},
            "No source names the data centers or their energy mix.\n",
        ),
        encoding="utf-8",
    )

    captured: list[str] = []

    def _fn(messages, info):
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, UserPromptPart):
                    captured.append(str(part.content))
        args = {"verdict": "unverified", "confidence": "low", "reasoning": "Scripted.",
                "evidence_gaps": []}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    with auditor_agent.override(model=FunctionModel(_fn)):
        with patch.object(auditor_agent, "override", side_effect=lambda **kw: nullcontext()):
            result = CliRunner().invoke(main, [
                "--model", "test", "step-audit", "--claim", "example/claim",
                "--repo-root", str(tmp_path),
            ])

    assert result.exit_code == 0, result.output
    assert any(claim_title in p for p in captured)


_STEP_AUDIT_NOTES = "SENTINEL-NOTES: mixed = offsets only"


def _step_audit_prompts(tmp_path, criteria_slug: str | None, templates: list | None) -> list[str]:
    """Run step-audit on one claim with a scripted Evaluator; return the user prompts it got."""
    from contextlib import nullcontext

    import yaml
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    from auditor.agent import auditor_agent
    from common.frontmatter import serialize_frontmatter

    (tmp_path / "research" / "entities" / "companies").mkdir(parents=True)
    (tmp_path / "research" / "entities" / "companies" / "example.md").write_text(
        serialize_frontmatter(
            {"name": "Example", "type": "company", "description": "A company."}, "Body.\n"
        ),
        encoding="utf-8",
    )
    fm = {"title": "Example is hosted on renewable energy", "entity": "companies/example",
          "verdict": "mixed", "confidence": "low", "topics": ["environmental-impact"],
          "sources": []}
    if criteria_slug:
        fm["criteria_slug"] = criteria_slug
    claim_dir = tmp_path / "research" / "claims" / "example"
    claim_dir.mkdir(parents=True)
    (claim_dir / "claim.md").write_text(
        serialize_frontmatter(fm, "Only offsets are documented.\n"), encoding="utf-8"
    )
    if templates is not None:
        (tmp_path / "research" / "templates.yaml").write_text(
            yaml.safe_dump({"templates": templates}), encoding="utf-8"
        )

    captured: list[str] = []

    def _fn(messages, info):
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, UserPromptPart):
                    captured.append(str(part.content))
        args = {"verdict": "mixed", "confidence": "low", "reasoning": "Scripted.",
                "evidence_gaps": []}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    with auditor_agent.override(model=FunctionModel(_fn)):
        with patch.object(auditor_agent, "override", side_effect=lambda **kw: nullcontext()):
            result = CliRunner().invoke(main, [
                "--model", "test", "step-audit", "--claim", "example/claim",
                "--repo-root", str(tmp_path),
            ])
    assert result.exit_code == 0, result.output
    assert captured, "the Evaluator never ran"
    return captured


def _green_template(**extra) -> dict:
    return {"slug": "green-hosting", "text": "COMPANY is hosted on renewable energy",
            "entity_type": "company", "topics": ["environmental-impact"], "core": True, **extra}


def test_step_audit_sends_the_grading_rule_and_not_notes(tmp_path) -> None:
    prompts = _step_audit_prompts(
        tmp_path, "green-hosting",
        [_green_template(notes="NOTES-ONLY reader text", grading_rule=_STEP_AUDIT_NOTES)],
    )
    assert f"## Criterion notes\n{_STEP_AUDIT_NOTES}" in "\n".join(prompts)
    assert "NOTES-ONLY" not in "\n".join(prompts)


@pytest.mark.parametrize(
    "criteria_slug,templates",
    [
        ("green-hosting", [_green_template(notes=_STEP_AUDIT_NOTES)]),
        (None, [_green_template(grading_rule=_STEP_AUDIT_NOTES)]),
        ("not-a-template", [_green_template(grading_rule=_STEP_AUDIT_NOTES)]),
        ("green-hosting", None),
    ],
    ids=["notes-without-grading-rule", "no-criteria-slug", "unknown-slug", "no-templates-file"],
)
def test_step_audit_without_a_grading_rule_sends_none(tmp_path, criteria_slug, templates) -> None:
    prompts = _step_audit_prompts(tmp_path, criteria_slug, templates)
    assert "## Criterion notes" not in "\n".join(prompts)


def test_step_audit_skips_blocked_claims(tmp_path) -> None:
    """A blocked claim's title keeps the raw placeholder; step-audit neither grades it nor
    rewrites its sidecar under --write."""
    from pydantic_ai.models.function import FunctionModel

    from auditor.agent import auditor_agent
    from common.frontmatter import serialize_frontmatter

    (tmp_path / "research" / "entities" / "companies").mkdir(parents=True)
    (tmp_path / "research" / "entities" / "companies" / "example.md").write_text(
        serialize_frontmatter(
            {"name": "Example", "type": "company", "description": "A company."}, "Body.\n"
        ),
        encoding="utf-8",
    )
    claim_dir = tmp_path / "research" / "claims" / "example"
    claim_dir.mkdir(parents=True)
    (claim_dir / "corporate-structure.md").write_text(
        serialize_frontmatter(
            {"title": "Example has STRUCTURE corporate structure", "entity": "companies/example",
             "verdict": "unverified", "confidence": "low", "topics": ["industry-analysis"],
             "sources": [], "status": "blocked", "blocked_reason": "analyst_error"},
            "This claim is blocked: `analyst_error`.\n",
        ),
        encoding="utf-8",
    )
    sidecar = claim_dir / "corporate-structure.audit.yaml"
    sidecar.write_text("schema_version: 1\n", encoding="utf-8")

    calls: list = []

    def _fn(messages, info):
        calls.append(messages)
        raise AssertionError("the auditor must not run on a blocked claim")

    with auditor_agent.override(model=FunctionModel(_fn)):
        result = CliRunner().invoke(main, [
            "--model", "test", "step-audit", "--entity", "example", "--write",
            "--repo-root", str(tmp_path),
        ])

    assert result.exit_code == 0, result.output
    assert calls == []
    assert "Skipped (blocked): example/corporate-structure" in result.output
    assert sidecar.read_text(encoding="utf-8") == "schema_version: 1\n"
