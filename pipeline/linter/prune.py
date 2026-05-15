"""Prune source files not cited by any claim.

Usage (from repo root or pipeline/):
  uv run python -m linter.prune           # dry-run — list orphans
  uv run python -m linter.prune --apply   # delete orphans + empty year dirs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .runner import run_all_checks


def main() -> None:
    ap = argparse.ArgumentParser(description="Remove source files not cited by any claim.")
    ap.add_argument("--apply", action="store_true", help="delete files (default: dry-run)")
    ap.add_argument(
        "--root",
        type=Path,
        default=Path.cwd().parent,
        help="repo root (default: parent of cwd, works when invoked from pipeline/)",
    )
    args = ap.parse_args()

    issues, _ = run_all_checks(args.root)
    orphans = sorted(Path(i.path) for i in issues if i.check_id == "unreferenced-source")

    if not orphans:
        print("No orphaned sources found.")
        return

    mode = "DRY RUN — Would delete" if not args.apply else "Deleting"
    print(f"{mode} {len(orphans)} orphaned source(s):")
    for p in orphans:
        print(f"  {p}")

    if not args.apply:
        print("\nPass --apply to delete.")
        return

    for p in orphans:
        p.unlink(missing_ok=True)

    # Remove year directories that are now empty
    year_dirs = {p.parent for p in orphans}
    for d in sorted(year_dirs):
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
            print(f"  removed empty dir: {d}")

    print(f"\nDeleted {len(orphans)} file(s).")


if __name__ == "__main__":
    main()
