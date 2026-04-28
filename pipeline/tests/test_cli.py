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
        result = runner.invoke(main, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "Fetch a URL" in result.output
        assert "--dry-run" in result.output
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
