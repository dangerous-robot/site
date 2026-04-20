"""General-purpose utilities shared across pipeline packages."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Convert text to a kebab-case slug (deterministic, no LLM)."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")
