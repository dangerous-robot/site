"""Tests for the instructions loader utility."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.instructions import load_instructions


class TestLoadInstructions:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="instructions.md"):
            load_instructions(tmp_path)

    def test_empty_file_raises(self, tmp_path):
        (tmp_path / "instructions.md").write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            load_instructions(tmp_path)

    def test_whitespace_only_raises(self, tmp_path):
        (tmp_path / "instructions.md").write_text("   \n\t\n  ", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            load_instructions(tmp_path)

    def test_non_ascii_preserved(self, tmp_path):
        content = "You are an agent. Handle umlauts: Uberpr\u00fcfung, accents: r\u00e9sum\u00e9."
        (tmp_path / "instructions.md").write_text(content, encoding="utf-8")
        assert load_instructions(tmp_path) == content

    def test_literal_curly_braces_preserved(self, tmp_path):
        content = "Use {entity_name} as a literal string, not a template variable."
        (tmp_path / "instructions.md").write_text(content, encoding="utf-8")
        assert load_instructions(tmp_path) == content


class TestAgentInstructionsWiring:
    """Each agent's system prompt should match its instructions.md content."""

    def test_researcher_loads_instructions(self):
        from researcher.agent import research_agent
        agent_dir = Path(__file__).resolve().parent.parent / "researcher"
        expected = load_instructions(agent_dir)
        assert research_agent._system_prompts[0] == expected

    def test_analyst_loads_instructions(self):
        from analyst.agent import analyst_agent
        agent_dir = Path(__file__).resolve().parent.parent / "analyst"
        expected = load_instructions(agent_dir)
        assert analyst_agent._system_prompts[0] == expected

    def test_auditor_loads_instructions(self):
        from auditor.agent import auditor_agent
        agent_dir = Path(__file__).resolve().parent.parent / "auditor"
        expected = load_instructions(agent_dir)
        assert auditor_agent._system_prompts[0] == expected

    def test_ingestor_loads_instructions(self):
        from ingestor.agent import ingestor_agent
        agent_dir = Path(__file__).resolve().parent.parent / "ingestor"
        expected = load_instructions(agent_dir)
        assert ingestor_agent._system_prompts[0] == expected
