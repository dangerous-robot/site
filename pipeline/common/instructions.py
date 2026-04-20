"""Load agent system prompts from instruction files."""

from __future__ import annotations

from pathlib import Path


def load_instructions(agent_dir: Path) -> str:
    """Load the system prompt from instructions.md in the given agent directory.

    Raises:
        FileNotFoundError: If instructions.md does not exist.
        ValueError: If the file is empty or whitespace-only.
    """
    path = agent_dir / "instructions.md"
    if not path.exists():
        raise FileNotFoundError(f"Instructions file not found: {path}")

    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"Instructions file is empty: {path}")

    return content
