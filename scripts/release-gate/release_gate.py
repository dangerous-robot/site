#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit): the release gate.

Denies code edits unless an active work item is registered and valid.
Everything else (docs, research, editorial content, .claude/) passes
through untouched. See release_common.py for the lists.

Why a command hook and not a prompt hook: a prompt hook only sees the
tool call's input (file path and edit text), not VERSION.md, the roadmap,
or the plan, so it cannot know whether the work was scheduled. The
judgment happens in the release-triage skill, with full context; this
hook only enforces that the judgment was recorded.

A `deny` from PreToolUse holds in every permission mode, including
--dangerously-skip-permissions (Claude Code docs, hooks guide).
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from release_common import (  # noqa: E402
    BYPASS_ENV_VAR,
    BYPASS_ENV_VALUE,
    HOTFIX_TTL_HOURS,
    WORK_ITEM_FILE,
    is_gated,
    load_work_item,
    read_hook_input,
    relative_to_root,
    repo_root,
    validate_work_item,
)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def main() -> None:
    if os.environ.get(BYPASS_ENV_VAR, "").lower() == BYPASS_ENV_VALUE:
        return  # exit 0, no output: normal permission flow

    data = read_hook_input()
    tool_input = data.get("tool_input") or {}
    path_str = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    root = repo_root()
    rel = relative_to_root(path_str, root)
    if rel is None or not is_gated(rel):
        return

    item = load_work_item(root)
    ok, why = validate_work_item(item, root)
    if ok:
        return

    deny(
        f"Release gate: edit to `{rel}` blocked ({why}). "
        "Code changes must belong to Scheduled work (AGENTS.md § Release planning). "
        "Do not retry the edit. Instead: (1) invoke the `release-triage` skill to classify this "
        "change against VERSION.md and assign it to a release, then (2) register it with "
        "`python3 scripts/release-gate/work_item.py start --title \"...\" --kind patch|minor|major "
        "--release vX.Y.Z --plan docs/plans/drafts/<name>.md` (or `--section \"§N\"` for an item "
        "listed directly in the roadmap). For an urgent fix only: "
        f"`python3 scripts/release-gate/work_item.py hotfix --title \"...\" --reason \"...\"` "
        f"(expires in {HOTFIX_TTL_HOURS}h). State: `python3 scripts/release-gate/work_item.py status`. "
        f"Record lives at {WORK_ITEM_FILE}."
    )


if __name__ == "__main__":
    main()
