"""Smoke tests: dr CLI entry point and all subcommands respond to --help."""

from __future__ import annotations

import subprocess

import pytest


@pytest.mark.parametrize("subcommand", ["", "verify", "research", "reassess", "ingest"])
def test_dr_cli_help(subcommand):
    cmd = ["uv", "run", "dr"]
    if subcommand:
        cmd.append(subcommand)
    cmd.append("--help")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd="/Users/brandon/dev/ai/dangerous-robot/site",
    )
    assert result.returncode == 0, f"dr {subcommand} --help failed: {result.stderr}"
    assert "Usage" in result.stdout
