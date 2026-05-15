"""CLI entry: uv run python -m linter [--json] [--min-severity {error,warning,info}] [--root PATH]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import format_json_report, format_text_report
from .runner import run_all_checks


def main() -> None:
    ap = argparse.ArgumentParser(description="dangerousrobot.org content linter")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument(
        "--min-severity",
        default="info",
        choices=["error", "warning", "info"],
        help="lowest severity to include in output (default: info)",
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=Path.cwd().parent,
        help="repo root (default: parent of cwd, works when invoked from pipeline/)",
    )
    args = ap.parse_args()

    issues, files_checked = run_all_checks(args.root)

    if args.json:
        print(format_json_report(issues, args.min_severity))
    else:
        print(format_text_report(issues, files_checked, args.min_severity))

    sys.exit(1 if any(i.severity == "error" for i in issues) else 0)


if __name__ == "__main__":
    main()
