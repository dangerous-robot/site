"""CLI entry: uv run python -m linter [--detail] [--output FILE] [--json] [--min-severity ...]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import format_json_report, format_summary_report, format_text_report
from .runner import run_all_checks


def main() -> None:
    ap = argparse.ArgumentParser(description="dangerousrobot.org content linter")
    ap.add_argument("--detail", action="store_true", help="show full per-file detail on stdout")
    ap.add_argument("--output", type=Path, metavar="FILE", help="write full detail to FILE")
    ap.add_argument("--json", action="store_true", help="emit JSON (implies --detail)")
    ap.add_argument(
        "--min-severity",
        default="info",
        choices=["error", "warning", "info"],
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=Path.cwd().parent,
        help="repo root (default: parent of cwd, works when invoked from pipeline/)",
    )
    args = ap.parse_args()

    issues, files_checked = run_all_checks(args.root)
    has_errors = any(i.severity == "error" for i in issues)

    if args.json:
        print(format_json_report(issues, args.min_severity))
    elif args.detail:
        print(format_text_report(issues, files_checked, args.min_severity))
    else:
        print(format_summary_report(issues, files_checked, args.min_severity))

    if args.output:
        args.output.write_text(
            format_text_report(issues, files_checked, args.min_severity), encoding="utf-8"
        )
        print(f"  detail written to {args.output}")

    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
