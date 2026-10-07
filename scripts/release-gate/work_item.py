#!/usr/bin/env python3
"""Register, inspect, and clear the active work item the release gate checks.

Usage:
  python3 scripts/release-gate/work_item.py status
  python3 scripts/release-gate/work_item.py start --title "..." --kind patch|minor|major \
      --release v1.0.0 [--plan docs/plans/drafts/x.md | --section "SITE-J (Responsible AI chatbots)"]
  python3 scripts/release-gate/work_item.py hotfix --title "..." --reason "..."
  python3 scripts/release-gate/work_item.py finish

`start` validates against the same rules the gate uses, so a bad
registration fails here rather than at the first edit. The record is a
small JSON file at .claude/active-work.json (gitignored).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from release_common import (  # noqa: E402
    HOTFIX_TTL_HOURS,
    VALID_KINDS,
    WORK_ITEM_FILE,
    describe_work_item,
    hotfix_expiry,
    load_work_item,
    now_utc,
    read_version,
    repo_root,
    roadmap_files,
    validate_work_item,
)


def write_item(item: dict, root) -> None:
    f = root / WORK_ITEM_FILE
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")


def cmd_status(args, root) -> int:
    v = read_version(root)
    item = load_work_item(root)
    ok, why = validate_work_item(item, root)
    print(f"Working version: {v['version'] or '?'}")
    print(f"Active release:  {v['active_release_path'] or '?'}")
    print(f"Roadmaps:        {', '.join(roadmap_files(root)) or 'none'}")
    print(f"Work item:       {describe_work_item(item, root)}")
    print(f"Gate verdict:    {'ALLOW' if ok else 'DENY'} ({why})")
    return 0


def cmd_start(args, root) -> int:
    existing = load_work_item(root)
    if existing and not args.force:
        print(
            f"An item is already active: {describe_work_item(existing, root)}\n"
            "Run `finish` first, or pass --force to replace it.",
            file=sys.stderr,
        )
        return 1
    item = {
        "title": args.title.strip(),
        "kind": args.kind,
        "release": args.release if args.release.startswith("v") else f"v{args.release}",
        "plan": args.plan or "",
        "section": args.section or "",
        "started": now_utc().isoformat(timespec="minutes"),
    }
    ok, why = validate_work_item(item, root)
    if not ok:
        print(f"Refused: {why}", file=sys.stderr)
        return 1
    write_item(item, root)
    print(f"Registered: {describe_work_item(item, root)}")
    print(f"Scheduled in {why}. Remember AGENTS.md Plans & Backlog rules 4 and 6 as work lands.")
    return 0


def cmd_hotfix(args, root) -> int:
    existing = load_work_item(root)
    if existing and not args.force:
        print(
            f"An item is already active: {describe_work_item(existing, root)}\n"
            "Run `finish` first, or pass --force to replace it.",
            file=sys.stderr,
        )
        return 1
    item = {
        "title": args.title.strip(),
        "kind": "hotfix",
        "reason": args.reason.strip(),
        "started": now_utc().isoformat(timespec="minutes"),
        "expires": hotfix_expiry(),
    }
    ok, why = validate_work_item(item, root)
    if not ok:
        print(f"Refused: {why}", file=sys.stderr)
        return 1
    write_item(item, root)
    print(f"Hotfix registered for {HOTFIX_TTL_HOURS}h: {describe_work_item(item, root)}")
    print("A hotfix is a patch by definition: record it in the active roadmap or UNSCHEDULED.md before you finish.")
    return 0


def cmd_finish(args, root) -> int:
    f = root / WORK_ITEM_FILE
    if not f.exists():
        print("No active work item.")
        return 0
    item = load_work_item(root)
    f.unlink()
    print(f"Cleared: {describe_work_item(item, root)}")
    print("Before committing: tick the plan, update the roadmap status, and sync UNSCHEDULED.md (AGENTS.md rules 4 to 6).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    s = sub.add_parser("start")
    s.add_argument("--title", required=True)
    s.add_argument("--kind", required=True, choices=[k for k in VALID_KINDS if k != "hotfix"])
    s.add_argument("--release", required=True, help="e.g. v1.0.0; must have docs/v1.0.0-roadmap.md")
    s.add_argument("--plan", help="plan file path, e.g. docs/plans/drafts/foo.md")
    s.add_argument("--section", help="roadmap work item ID and name when no plan file exists, e.g. \"SITE-J (Responsible AI chatbots)\"")
    s.add_argument("--force", action="store_true")

    h = sub.add_parser("hotfix")
    h.add_argument("--title", required=True)
    h.add_argument("--reason", required=True)
    h.add_argument("--force", action="store_true")

    sub.add_parser("finish")

    args = p.parse_args()
    root = repo_root()
    return {"status": cmd_status, "start": cmd_start, "hotfix": cmd_hotfix, "finish": cmd_finish}[args.cmd](args, root)


if __name__ == "__main__":
    sys.exit(main())
