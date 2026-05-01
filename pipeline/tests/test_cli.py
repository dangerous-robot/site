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


class TestVerifyOptions:
    def test_verify_help_lists_candidate_pool_size(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["verify", "--help"])
        assert result.exit_code == 0
        assert "--candidate-pool-size" in result.output


class TestVerifyClaimCLI:
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
        monkeypatch.setattr("asyncio.run", lambda coro: asyncio.get_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro)

        from orchestrator.cli import main
        runner = CliRunner()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")
        result = runner.invoke(main, ["verify-claim", "-", "some claim"], catch_exceptions=False)
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
        monkeypatch.setattr("asyncio.run", lambda coro: asyncio.get_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro)
        monkeypatch.setattr("common.content_loader.resolve_repo_root", lambda: tmp_path)

        from orchestrator.cli import main
        runner = CliRunner()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "x")
        result = runner.invoke(main, ["verify-claim", "products/widget", "some claim"], catch_exceptions=False)

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
        result = runner.invoke(main, ["verify-claim", "invalid-no-slash", "test claim"])
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
        result = runner.invoke(main, ["verify-claim", "badtype/foo", "test claim"])
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
        result = runner.invoke(main, ["verify-claim", "products/nonexistent", "test claim"])
        assert result.exit_code != 0
        output = result.output + (result.exception and str(result.exception) or "")
        assert "nonexistent" in output.lower() or "not found" in output.lower()
