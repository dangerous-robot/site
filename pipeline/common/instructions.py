"""Load agent system prompts from instruction files."""

from __future__ import annotations

from pathlib import Path

_COMMON_DIR = Path(__file__).resolve().parent


def load_instructions(agent_dir: Path, *fragments: Path) -> str:
    """Load the system prompt from instructions.md, optionally appending shared fragments.

    Each fragment is appended after the main instructions, separated by a blank line.
    Pass paths from _COMMON_DIR for shared content (e.g. verdict-scale.md).

    Raises:
        FileNotFoundError: If instructions.md or any fragment does not exist.
        ValueError: If the main instructions file is empty or whitespace-only.
    """
    path = agent_dir / "instructions.md"
    if not path.exists():
        raise FileNotFoundError(f"Instructions file not found: {path}")

    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"Instructions file is empty: {path}")

    for fragment in fragments:
        if not fragment.exists():
            raise FileNotFoundError(f"Fragment file not found: {fragment}")
        content = content.rstrip() + "\n\n" + fragment.read_text(encoding="utf-8")

    return content


def common(filename: str) -> Path:
    """Return the path to a file in the common instructions directory."""
    return _COMMON_DIR / filename
