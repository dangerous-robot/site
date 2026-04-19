"""Load research content files (sources, claims, entities) by slug."""

from __future__ import annotations

import subprocess
from pathlib import Path

from common.frontmatter import parse_frontmatter


def resolve_repo_root() -> Path:
    """Find the repository root via git."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _load_file(path: Path) -> tuple[dict, str]:
    """Load a markdown file and return (frontmatter, body)."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    text = path.read_text(encoding="utf-8")
    return parse_frontmatter(text)


def load_source(source_id: str, repo_root: Path) -> tuple[dict, str]:
    """Load a source file by ID (e.g. '2025/fli-safety-index')."""
    path = repo_root / "research" / "sources" / f"{source_id}.md"
    return _load_file(path)


def load_claim(claim_path: str, repo_root: Path) -> tuple[dict, str]:
    """Load a claim file (e.g. 'ecosia/renewable-energy-hosting')."""
    path = repo_root / "research" / "claims" / f"{claim_path}.md"
    return _load_file(path)


def load_entity(entity_path: str, repo_root: Path) -> tuple[dict, str]:
    """Load an entity file (e.g. 'companies/ecosia')."""
    path = repo_root / "research" / "entities" / f"{entity_path}.md"
    return _load_file(path)


def list_claims(
    repo_root: Path,
    entity: str | None = None,
    category: str | None = None,
) -> list[Path]:
    """List claim files, optionally filtered by entity or category.

    Filtering by entity matches on the directory name (e.g. 'ecosia').
    Filtering by category requires parsing frontmatter to check the value.
    """
    claims_dir = repo_root / "research" / "claims"
    if not claims_dir.exists():
        return []

    paths = sorted(claims_dir.rglob("*.md"))

    if entity is not None:
        paths = [p for p in paths if p.parent.name == entity]

    if category is not None:
        filtered = []
        for p in paths:
            fm, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
            if fm.get("category") == category:
                filtered.append(p)
        paths = filtered

    return paths
