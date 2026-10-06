#!/usr/bin/env python3
"""UserPromptSubmit hook: inject release state into every turn.

Two short lines so the agent always knows the working version, the active
release roadmap, and whether a work item is registered. This is the
"trigger" half: when the user starts describing new work and no item is
active, the agent is told to run release-triage before touching code.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from release_common import (  # noqa: E402
    BYPASS_ENV_VAR,
    BYPASS_ENV_VALUE,
    GATED_PREFIXES,
    describe_work_item,
    load_work_item,
    read_hook_input,
    read_version,
    repo_root,
    roadmap_files,
    validate_work_item,
)


def main() -> None:
    read_hook_input()  # consume stdin; prompt text is not needed here
    root = repo_root()
    v = read_version(root)
    item = load_work_item(root)
    ok, _ = validate_work_item(item, root)
    gate_state = (
        "OFF for this session"
        if os.environ.get(BYPASS_ENV_VAR, "").lower() == BYPASS_ENV_VALUE
        else "on"
    )
    roadmaps = ", ".join(roadmap_files(root)) or "none"
    gated = ", ".join(p.rstrip("/") for p in GATED_PREFIXES)

    line1 = (
        f"[release-context] Working version {v['version'] or '?'} (VERSION.md). "
        f"Active release: {v['active_release_path'] or '?'}. Roadmaps on disk: {roadmaps}. "
        f"Active work item: {describe_work_item(item, root)}. Gate: {gate_state}."
    )
    if ok:
        line2 = (
            "Code edits are allowed for the active work item only. If this prompt starts "
            "different work, finish or re-triage first (`python3 scripts/release-gate/work_item.py finish`)."
        )
    else:
        line2 = (
            f"No valid work item: edits under {gated} will be denied. If this prompt asks for a "
            "code change, invoke the `release-triage` skill first (classify by VERSION.md semver "
            "rules, assign a release, register the item), then plan with Superpowers "
            "(brainstorming -> writing-plans into docs/plans/drafts/), then implement."
        )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": line1 + "\n" + line2,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
