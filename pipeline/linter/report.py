"""Text and JSON report formatters."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict

from .models import LintIssue

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _filter_by_severity(issues: list[LintIssue], min_severity: str) -> list[LintIssue]:
    threshold = SEVERITY_ORDER.get(min_severity, 2)
    return [i for i in issues if SEVERITY_ORDER.get(i.severity, 2) <= threshold]


def format_text_report(issues: list[LintIssue], min_severity: str = "info") -> str:
    filtered = _filter_by_severity(issues, min_severity)
    errors = [i for i in filtered if i.severity == "error"]
    warnings = [i for i in filtered if i.severity == "warning"]
    infos = [i for i in filtered if i.severity == "info"]

    all_paths: set[str] = {i.path for i in filtered}
    lines = [
        "dr lint — dangerousrobot.org content linter",
        "=" * 60,
        f"  {len(all_paths)} files checked  |  "
        f"{len(errors)} errors  |  {len(warnings)} warnings  |  {len(infos)} info",
    ]

    for severity_label, severity_issues in [("ERRORS", errors), ("WARNINGS", warnings), ("INFO", infos)]:
        if not severity_issues:
            continue
        by_path: dict[str, list[LintIssue]] = defaultdict(list)
        for issue in severity_issues:
            by_path[issue.path].append(issue)
        lines.append("")
        lines.append(severity_label)
        for path in sorted(by_path):
            lines.append(f"  {path}")
            for issue in by_path[path]:
                lines.append(f"    [{issue.check_id}] {issue.message}")
                if issue.hint:
                    lines.append(f"    hint: {issue.hint}")

    lines.append("=" * 60)
    lines.append(f"Exit code: {'1' if errors else '0'}")
    return "\n".join(lines)


def format_json_report(issues: list[LintIssue], min_severity: str = "info") -> str:
    filtered = _filter_by_severity(issues, min_severity)
    return json.dumps([asdict(i) for i in filtered], indent=2)
