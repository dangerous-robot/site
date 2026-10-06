"""Shared helpers for the release gate hooks and the work-item helper.

Stdlib only. Python 3.9+. No jq dependency.

Everything configurable lives in the CONFIG block below. The intent is
"hard to break, easy to bend": change a list here rather than editing
the hook logic.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# CONFIG (edit freely)
# --------------------------------------------------------------------------

# Paths (relative to the repo root) whose edits require an active work item.
GATED_PREFIXES = (
    "src/",
    "pipeline/",
    "workers/",
    "scripts/",
    "public/",
    ".github/",
)

# Root-level files that are also gated (build and dependency config).
GATED_ROOT_FILES = (
    "astro.config.ts",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "tasks.py",
    "tsconfig.json",
    "wrangler.toml",
)

# Paths that are never gated, even if they fall under a gated prefix.
# Editorial content, research content, docs, plans, and the gate's own files.
EXEMPT_PREFIXES = (
    "src/content/",
    "docs/",
    "research/",
    ".claude/",
)

# File suffixes that are never gated (prose, not code).
EXEMPT_SUFFIXES = (".md", ".mdx", ".txt")

# Where the active work item is recorded. Gitignored (see .gitignore).
WORK_ITEM_FILE = ".claude/active-work.json"

# Hotfix registrations expire after this long; re-register to extend.
HOTFIX_TTL_HOURS = 4

# Setting this environment variable (in the shell that launches `claude`)
# turns the gate off for that session. It is deliberately not something an
# agent can flip from inside a session: hooks inherit the launcher's env,
# not the env of commands the agent runs.
BYPASS_ENV_VAR = "RELEASE_GATE"
BYPASS_ENV_VALUE = "off"

VALID_KINDS = ("patch", "minor", "major", "hotfix")

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def repo_root() -> Path:
    """Claude Code sets CLAUDE_PROJECT_DIR for hooks; fall back to cwd."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(root).resolve()


def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def relative_to_root(path_str: str, root: Path) -> str | None:
    """Return a forward-slash path relative to root, or None if outside it."""
    if not path_str:
        return None
    p = Path(path_str)
    if not p.is_absolute():
        p = root / p
    try:
        rel = p.resolve().relative_to(root)
    except ValueError:
        return None
    return rel.as_posix()


def is_gated(rel: str) -> bool:
    if rel.startswith(EXEMPT_PREFIXES) or rel.endswith(EXEMPT_SUFFIXES):
        return False
    if rel in GATED_ROOT_FILES:
        return True
    return rel.startswith(GATED_PREFIXES)


def read_version(root: Path) -> dict:
    """Parse VERSION.md: first non-empty line is the version; 'Active release:' names the roadmap."""
    info = {"version": None, "active_release_path": None}
    vf = root / "VERSION.md"
    if not vf.exists():
        return info
    for line in vf.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if info["version"] is None:
            info["version"] = s
            continue
        m = re.match(r"Active release:\s*(\S+)", s)
        if m:
            info["active_release_path"] = m.group(1)
    return info


def roadmap_files(root: Path) -> list[str]:
    """Release roadmaps per AGENTS.md: docs/v{semver}-roadmap.md or docs/v{semver}.md."""
    docs = root / "docs"
    if not docs.is_dir():
        return []
    out = []
    for p in sorted(docs.glob("v*.md")):
        if re.match(r"v\d+\.\d+\.\d+(-roadmap)?\.md$", p.name):
            out.append(p.relative_to(root).as_posix())
    return out


def roadmap_for_release(root: Path, release: str) -> str | None:
    """Map 'v1.0.0' (or '1.0.0') to an existing roadmap file path."""
    if not release:
        return None
    tag = release if release.startswith("v") else f"v{release}"
    for name in (f"docs/{tag}-roadmap.md", f"docs/{tag}.md"):
        if (root / name).exists():
            return name
    return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_work_item(root: Path) -> dict | None:
    f = root / WORK_ITEM_FILE
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"_corrupt": True}


def validate_work_item(item: dict | None, root: Path) -> tuple[bool, str]:
    """Return (ok, reason). Mirrors the rules in AGENTS.md § Release planning:
    only Scheduled work (in a release roadmap) may be coded, except a hotfix."""
    if item is None:
        return False, "no active work item"
    if item.get("_corrupt"):
        return False, f"{WORK_ITEM_FILE} is not valid JSON"
    kind = item.get("kind")
    if kind not in VALID_KINDS:
        return False, f"kind must be one of {', '.join(VALID_KINDS)} (got {kind!r})"
    title = (item.get("title") or "").strip()
    if not title:
        return False, "title is required"

    if kind == "hotfix":
        if not (item.get("reason") or "").strip():
            return False, "hotfix needs a reason"
        exp = parse_ts(item.get("expires"))
        if exp is None:
            return False, "hotfix needs an 'expires' timestamp"
        if exp < now_utc():
            return False, f"hotfix registration expired at {exp.isoformat(timespec='minutes')}"
        return True, "hotfix"

    release = item.get("release") or ""
    roadmap = roadmap_for_release(root, release)
    if roadmap is None:
        return False, (
            f"release {release!r} has no roadmap file (expected docs/{release}-roadmap.md); "
            "only Scheduled work may be coded"
        )
    plan = item.get("plan") or ""
    section = (item.get("section") or "").strip()
    if plan:
        if not (root / plan).exists():
            return False, f"plan file not found: {plan}"
    elif not section:
        return False, "either a plan path or a roadmap section reference is required"
    return True, roadmap


def describe_work_item(item: dict | None, root: Path) -> str:
    if item is None:
        return "none"
    ok, why = validate_work_item(item, root)
    kind = item.get("kind", "?")
    title = item.get("title", "?")
    bits = [f"\"{title}\" ({kind}"]
    if item.get("release"):
        bits.append(f", {item['release']}")
    bits.append(")")
    if item.get("plan"):
        bits.append(f", plan {item['plan']}")
    elif item.get("section"):
        bits.append(f", roadmap {item['section']}")
    started = parse_ts(item.get("started"))
    if started:
        hours = (now_utc() - started).total_seconds() / 3600
        bits.append(f", started {hours:.1f}h ago")
    if not ok:
        bits.append(f" [INVALID: {why}]")
    return "".join(bits)


def hotfix_expiry() -> str:
    return (now_utc() + timedelta(hours=HOTFIX_TTL_HOURS)).isoformat(timespec="minutes")
