"""Tests for the ingestor CLI."""

from __future__ import annotations

from click.testing import CliRunner

from ingestor.cli import main


class TestCli:
    def test_invalid_url(self):
        runner = CliRunner()
        result = runner.invoke(main, ["not-a-url"])
        assert result.exit_code != 0
        assert "invalid URL" in result.output.lower() or "invalid url" in (
            result.output + (result.stderr if hasattr(result, "stderr") else "")
        ).lower()

    def test_missing_url_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code != 0
        # Click shows "Missing argument" for required args
        assert "url" in result.output.lower() or "missing" in result.output.lower()

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Ingest a URL" in result.output
        assert "--dry-run" in result.output
        assert "--model" in result.output
        assert "--skip-wayback" in result.output
