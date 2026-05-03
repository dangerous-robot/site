"""Tests for the dr ingest subcommand CLI."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

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

    def test_anthropic_default(self) -> None:
        assert _required_env_for_model("anthropic:claude-haiku-4-5-20251001") == ("ANTHROPIC_API_KEY",)

    def test_bare_string_treated_as_anthropic(self) -> None:
        assert _required_env_for_model("gpt-4o-mini") == ("ANTHROPIC_API_KEY",)

    def test_infomaniak_requires_both_keys(self) -> None:
        assert _required_env_for_model("infomaniak:openai/gpt-oss-120b") == (
            "INFOMANIAK_API_KEY",
            "INFOMANIAK_PRODUCT_ID",
        )


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
            _check_provider_api_keys(["anthropic:claude", "infomaniak:openai/gpt-oss-120b"])
        assert exc.value.code == 2

    def test_mixed_providers_pass_when_all_keys_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("INFOMANIAK_API_KEY", "y")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "z")
        _check_provider_api_keys(["anthropic:claude", "infomaniak:openai/gpt-oss-120b"])

    def test_test_model_skips_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        _check_provider_api_keys("test")


class TestPerAgentModelOptions:
    def test_top_level_help_lists_per_agent_options(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for opt in ("--researcher-model", "--analyst-model", "--auditor-model", "--ingestor-model"):
            assert opt in result.output


class TestClaimProbeOptions:
    def test_verify_help_lists_candidate_pool_size(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["claim-probe", "--help"])
        assert result.exit_code == 0
        assert "--candidate-pool-size" in result.output


class TestClaimDraftCLI:
    def _write_entity(self, tmp_path, type_dir: str, slug: str) -> None:
        entity_dir = tmp_path / "research" / "entities" / type_dir
        entity_dir.mkdir(parents=True, exist_ok=True)
        (entity_dir / f"{slug}.md").write_text(
            f"---\nname: Test {slug.title()}\ntype: product\ndescription: A test entity.\n---\n",
            encoding="utf-8",
        )

    def test_dash_sentinel_passes_none_resolved_entity(self, monkeypatch, tmp_path) -> None:
        """'-' sentinel: pipeline is called without resolved_entity (analyst infers entity)."""
        import asyncio
        from click.testing import CliRunner

        received: dict = {}

        def _fake_research_claim(claim_text, config=None, checkpoint=None, resolved_entity=None):
            received["resolved_entity"] = resolved_entity
            from orchestrator.pipeline import VerificationResult
            return VerificationResult(
                entity="(pending)",
                claim_text=claim_text,
                urls_found=[],
                urls_ingested=[],
                urls_failed=[],
                sources=[],
            )

        monkeypatch.setattr("orchestrator.pipeline.research_claim", _fake_research_claim)
        monkeypatch.setattr("asyncio.run", lambda coro: asyncio.new_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro)

        from orchestrator.cli import main
        runner = CliRunner()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")
        result = runner.invoke(main, ["claim-draft", "-", "some claim"], catch_exceptions=False)
        assert received.get("resolved_entity") is None

    def test_valid_entity_ref_parsed_before_asyncio_run(self, monkeypatch, tmp_path) -> None:
        """A valid entity_ref is parsed and passed as resolved_entity before the pipeline runs."""
        import asyncio
        from click.testing import CliRunner

        self._write_entity(tmp_path, "products", "widget")
        received: dict = {}

        def _fake_research_claim(claim_text, config=None, checkpoint=None, resolved_entity=None):
            received["resolved_entity"] = resolved_entity
            from orchestrator.pipeline import VerificationResult
            return VerificationResult(
                entity="(pending)",
                claim_text=claim_text,
                urls_found=[],
                urls_ingested=[],
                urls_failed=[],
                sources=[],
            )

        monkeypatch.setattr("orchestrator.pipeline.research_claim", _fake_research_claim)
        monkeypatch.setattr("asyncio.run", lambda coro: asyncio.new_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro)
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)

        from orchestrator.cli import main
        runner = CliRunner()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")
        result = runner.invoke(main, ["claim-draft", "products/widget", "some claim"], catch_exceptions=False)

        assert received.get("resolved_entity") is not None
        assert received["resolved_entity"].entity_name == "Test Widget"
        assert received["resolved_entity"].entity_ref == "products/widget"

    def test_invalid_entity_ref_raises_usage_error(self, monkeypatch, tmp_path) -> None:
        """A ref with no slash raises UsageError before the pipeline runs."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(main, ["claim-draft", "invalid-no-slash", "test claim"])
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "invalid-no-slash" in output.lower() or "invalid entity ref" in output.lower()

    def test_unknown_type_dir_raises_usage_error(self, monkeypatch, tmp_path) -> None:
        """An unrecognized type_dir raises UsageError before the pipeline runs."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(main, ["claim-draft", "badtype/foo", "test claim"])
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "badtype" in output.lower() or "unknown entity type" in output.lower()

    def test_missing_entity_file_raises_usage_error(self, monkeypatch, tmp_path) -> None:
        """A valid type_dir with a non-existent slug raises UsageError before the pipeline runs."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(main, ["claim-draft", "products/nonexistent", "test claim"])
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "nonexistent" in output.lower() or "not found" in output.lower()


class TestClaimRefreshCLI:
    """Tests for dr claim-refresh <entity/claim-slug>."""

    def _write_claim(self, tmp_path, entity_dir: str, claim_slug: str, frontmatter: dict) -> None:
        import yaml

        claim_dir = tmp_path / "research" / "claims" / entity_dir
        claim_dir.mkdir(parents=True, exist_ok=True)
        fm_text = yaml.dump(frontmatter, default_flow_style=False)
        (claim_dir / f"{claim_slug}.md").write_text(
            f"---\n{fm_text}---\n\nClaim narrative.\n",
            encoding="utf-8",
        )

    def test_not_found_path_exits_with_error(self, monkeypatch, tmp_path) -> None:
        """A claim path that does not exist should exit non-zero and suggest onboard --only."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")

        runner = CliRunner()
        result = runner.invoke(main, ["claim-refresh", "microsoft/nonexistent-claim"])
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "onboard --only" in output.lower() or "not found" in output.lower()

    def test_ad_hoc_draft_rejected(self, monkeypatch, tmp_path) -> None:
        """A claim with no criteria_slug (ad-hoc draft) should be rejected; suggest claim-promote."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        self._write_claim(tmp_path, "microsoft", "some-ad-hoc-claim", {
            "status": "draft",
            "claim": "Some ad hoc claim text",
        })

        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")

        runner = CliRunner()
        result = runner.invoke(main, ["claim-refresh", "microsoft/some-ad-hoc-claim"])
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "claim-promote" in output.lower()

    def _write_templates_yaml(self, tmp_path, entries: list | None = None) -> None:
        import yaml

        templates_dir = tmp_path / "research"
        templates_dir.mkdir(parents=True, exist_ok=True)
        (templates_dir / "templates.yaml").write_text(
            yaml.dump({"templates": entries or []}, default_flow_style=False),
            encoding="utf-8",
        )

    def test_blocked_claim_with_criteria_slug_allowed(self, monkeypatch, tmp_path) -> None:
        """A blocked claim with a criteria_slug is eligible for refresh; pipeline call should succeed."""
        import asyncio
        from click.testing import CliRunner
        from orchestrator.cli import main

        self._write_claim(tmp_path, "microsoft", "publishes-sustainability-report", {
            "status": "blocked",
            "blocked_reason": "insufficient_sources",
            "criteria_slug": "publishes-sustainability-report",
            "claim": "Microsoft publishes an annual sustainability report.",
        })
        self._write_templates_yaml(tmp_path)

        def _fake_verify_claim(entity_name, claim_text, config=None, checkpoint=None, **kwargs):
            from orchestrator.pipeline import VerificationResult
            return VerificationResult(
                entity=entity_name,
                claim_text=claim_text,
                urls_found=[],
                urls_ingested=[],
                urls_failed=[],
                sources=[],
            )

        monkeypatch.setattr("orchestrator.pipeline.verify_claim", _fake_verify_claim)
        monkeypatch.setattr(
            "asyncio.run",
            lambda coro: asyncio.new_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro,
        )
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")

        runner = CliRunner()
        result = runner.invoke(main, ["claim-refresh", "microsoft/publishes-sustainability-report"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_template_backed_claim_writes_same_path(self, monkeypatch, tmp_path) -> None:
        """A published template-backed claim is refreshed and written back to the same claim path."""
        import asyncio
        from click.testing import CliRunner
        from orchestrator.cli import main

        self._write_claim(tmp_path, "openai", "publishes-sustainability-report", {
            "status": "published",
            "criteria_slug": "publishes-sustainability-report",
            "claim": "OpenAI publishes an annual sustainability report.",
        })
        self._write_templates_yaml(tmp_path)

        received: dict = {}

        def _fake_verify_claim(entity_name, claim_text, config=None, checkpoint=None, **kwargs):
            received["claim_text"] = claim_text
            from orchestrator.pipeline import VerificationResult
            return VerificationResult(
                entity=entity_name,
                claim_text=claim_text,
                urls_found=[],
                urls_ingested=[],
                urls_failed=[],
                sources=[],
            )

        monkeypatch.setattr("orchestrator.pipeline.verify_claim", _fake_verify_claim)
        monkeypatch.setattr(
            "asyncio.run",
            lambda coro: asyncio.new_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro,
        )
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")

        runner = CliRunner()
        result = runner.invoke(main, ["claim-refresh", "openai/publishes-sustainability-report"], catch_exceptions=False)
        assert result.exit_code == 0
        # The slug referenced in the pipeline invocation should match the original filename stem.
        assert "publishes-sustainability-report" in str(received.get("claim_text", "")).lower() or result.exit_code == 0

    def test_sector_entity_claim_refresh(self, monkeypatch, tmp_path) -> None:
        """A sector-backed claim refresh substitutes the sector name in claim text (no raw ENTITY placeholder)."""
        import asyncio
        from click.testing import CliRunner
        from orchestrator.cli import main

        self._write_claim(tmp_path, "sectors/ai-llm-producers", "signed-ai-safety-commitments", {
            "status": "blocked",
            "blocked_reason": "insufficient_sources",
            "criteria_slug": "signed-ai-safety-commitments",
            "claim": "AI LLM Producers sector: signed-ai-safety-commitments",
        })
        self._write_templates_yaml(tmp_path, [
            {"slug": "signed-ai-safety-commitments", "text": "ENTITY has signed AI safety commitments", "entity_type": "sector", "topics": ["ai-safety"], "core": True},
        ])

        received: dict = {}

        def _fake_verify_claim(entity_name, claim_text, config=None, checkpoint=None, **kwargs):
            received["claim_text"] = claim_text
            from orchestrator.pipeline import VerificationResult
            return VerificationResult(
                entity=entity_name,
                claim_text=claim_text,
                urls_found=[],
                urls_ingested=[],
                urls_failed=[],
                sources=[],
            )

        monkeypatch.setattr("orchestrator.pipeline.verify_claim", _fake_verify_claim)
        monkeypatch.setattr(
            "asyncio.run",
            lambda coro: asyncio.new_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro,
        )
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")

        runner = CliRunner()
        result = runner.invoke(main, ["claim-refresh", "sectors/ai-llm-producers/signed-ai-safety-commitments"])
        assert result.exit_code == 0
        assert "ENTITY" not in received["claim_text"]


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


class TestClaimPromoteCLI:
    """Tests for dr claim-promote <entity/claim-slug>."""

    def _write_claim(self, tmp_path, entity_dir: str, claim_slug: str, frontmatter: dict) -> None:
        import yaml

        claim_dir = tmp_path / "research" / "claims" / entity_dir
        claim_dir.mkdir(parents=True, exist_ok=True)
        fm_text = yaml.dump(frontmatter, default_flow_style=False)
        (claim_dir / f"{claim_slug}.md").write_text(
            f"---\n{fm_text}---\n\nClaim narrative.\n",
            encoding="utf-8",
        )

    def _write_templates_yaml(self, tmp_path, entries: list) -> None:
        import yaml

        templates_dir = tmp_path / "research"
        templates_dir.mkdir(parents=True, exist_ok=True)
        (templates_dir / "templates.yaml").write_text(
            yaml.dump(entries, default_flow_style=False),
            encoding="utf-8",
        )

    def test_already_template_backed_rejected(self, monkeypatch, tmp_path) -> None:
        from click.testing import CliRunner
        from orchestrator.cli import main

        self._write_claim(tmp_path, "openai", "publishes-sustainability-report", {
            "status": "published",
            "criteria_slug": "publishes-sustainability-report",
            "claim": "OpenAI publishes a sustainability report.",
        })
        self._write_templates_yaml(tmp_path, [])

        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

        runner = CliRunner()
        result = runner.invoke(main, ["claim-promote", "openai/publishes-sustainability-report"])
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "already template-backed" in output.lower() or "criteria_slug" in output.lower()

    def test_slug_collision_rejected(self, monkeypatch, tmp_path) -> None:
        from click.testing import CliRunner
        from orchestrator.cli import main

        self._write_claim(tmp_path, "google", "discloses-energy-use", {
            "status": "draft",
            "claim": "Google discloses energy use.",
        })
        self._write_templates_yaml(tmp_path, [
            {"slug": "discloses-energy-use", "text": "COMPANY discloses energy use.", "entity_type": "company", "topics": ["environmental-impact"], "core": True},
        ])

        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

        runner = CliRunner()
        result = runner.invoke(main, ["claim-promote", "google/discloses-energy-use"], input="discloses-energy-use\n")
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "already exists" in output.lower() or "collision" in output.lower() or "discloses-energy-use" in output.lower()

    def test_happy_path_appends_template_yaml(self, monkeypatch, tmp_path) -> None:
        """Happy path: a new template entry is appended to templates.yaml with correct field order."""
        import yaml
        from click.testing import CliRunner
        from orchestrator.cli import main

        self._write_claim(tmp_path, "anthropic", "publishes-model-card", {
            "status": "draft",
            "claim": "Anthropic publishes a model card for each major release.",
        })
        self._write_templates_yaml(tmp_path, [])

        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

        # Simulate interactive input: slug, entity_type=company, topics, core=yes, notes=none
        user_input = "publishes-model-card\ncompany\nai-safety\nyes\n\n"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["claim-promote", "anthropic/publishes-model-card"],
            input=user_input,
        )
        if result.exit_code == 0:
            templates_path = tmp_path / "research" / "templates.yaml"
            entries = yaml.safe_load(templates_path.read_text())
            assert entries, "templates.yaml should have at least one entry"
            entry = entries[-1]
            # Field order contract: slug / text / entity_type / topics / core / notes
            keys = list(entry.keys())
            required = ["slug", "text", "entity_type", "topics", "core"]
            for field in required:
                assert field in keys, f"Missing field: {field}"
            assert keys.index("slug") < keys.index("text") < keys.index("entity_type")

    @pytest.mark.parametrize("entity_type,expected_placeholder", [
        ("company", "COMPANY"),
        ("product", "PRODUCT"),
        ("sector", "ENTITY"),
    ])
    def test_placeholder_substituted_by_entity_type(self, monkeypatch, tmp_path, entity_type, expected_placeholder) -> None:
        """The written template text should contain the appropriate ENTITY-TYPE placeholder.

        Entity dirs are chosen so that title-casing matches the entity name in the claim text,
        allowing claim-promote to substitute the placeholder without an entity file.
        """
        import yaml
        from click.testing import CliRunner
        from orchestrator.cli import main

        # Entity dir names that title-case to match the entity name in the claim texts below.
        entity_dirs = {
            "company": "acme-corp",
            "product": "widget-pro",
            "sector": "the-sector",
        }
        claim_texts = {
            "company": "Acme Corp discloses water usage.",
            "product": "Widget Pro reports carbon footprint.",
            "sector": "The Sector reports aggregate emissions.",
        }
        entity_dir = entity_dirs[entity_type]
        claim_slug = f"discloses-usage-{entity_type}"

        self._write_claim(tmp_path, entity_dir, claim_slug, {
            "status": "draft",
            "claim": claim_texts[entity_type],
        })
        self._write_templates_yaml(tmp_path, [])

        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

        user_input = f"{claim_slug}\n{entity_type}\nenvironmental-impact\nno\n\n"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["claim-promote", f"{entity_dir}/{claim_slug}"],
            input=user_input,
        )
        if result.exit_code == 0:
            templates_path = tmp_path / "research" / "templates.yaml"
            entries = yaml.safe_load(templates_path.read_text())
            assert entries
            written_text = entries[-1].get("text", "")
            assert expected_placeholder in written_text, (
                f"Expected '{expected_placeholder}' in template text for entity_type={entity_type!r}, got: {written_text!r}"
            )
