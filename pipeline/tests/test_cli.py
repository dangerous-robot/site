"""Tests for the dr ingest subcommand CLI."""

from __future__ import annotations

from click.testing import CliRunner

from orchestrator.cli import main


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
        assert "Ingest a URL" in result.output
        assert "--dry-run" in result.output
        assert "--skip-wayback" in result.output
