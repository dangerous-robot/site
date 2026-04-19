"""Report generation for consistency check results."""

from __future__ import annotations

import json

from .models import ComparisonResult


def format_text_report(results: list[ComparisonResult]) -> str:
    """Format results as a human-readable text report."""
    if not results:
        return "No claims checked."

    total = len(results)
    agreements = sum(1 for r in results if r.verdict_agrees)
    reviews = sum(1 for r in results if r.needs_review)

    lines: list[str] = []

    # Header
    lines.append("=" * 60)
    lines.append("Consistency Check Report")
    lines.append("=" * 60)
    lines.append(f"Claims checked: {total}")
    lines.append(f"Verdict agreements: {agreements}/{total}")
    lines.append(f"Needs review: {reviews}")
    lines.append("")

    # Table
    lines.append(f"{'Claim':<40} {'Actual':<14} {'Assessed':<14} {'Severity':<10} {'Review'}")
    lines.append("-" * 90)
    for r in results:
        review_flag = "***" if r.needs_review else ""
        lines.append(
            f"{r.claim_id:<40} {r.actual_verdict.value:<14} "
            f"{r.assessed_verdict.value:<14} {r.verdict_severity.value:<10} {review_flag}"
        )
    lines.append("")

    # Details for disagreements
    disagreements = [r for r in results if r.needs_review]
    if disagreements:
        lines.append("=" * 60)
        lines.append("Details (needs review)")
        lines.append("=" * 60)
        for r in disagreements:
            lines.append("")
            lines.append(f"--- {r.claim_id} ---")
            lines.append(f"File: {r.claim_file}")
            lines.append(f"Actual:   verdict={r.actual_verdict.value}, confidence={r.actual_confidence.value}")
            lines.append(f"Assessed: verdict={r.assessed_verdict.value}, confidence={r.assessed_confidence.value}")
            lines.append(f"Severity: {r.verdict_severity.value}")
            lines.append(f"Reasoning: {r.reasoning}")
            if r.evidence_gaps:
                lines.append("Evidence gaps:")
                for gap in r.evidence_gaps:
                    lines.append(f"  - {gap}")

    return "\n".join(lines)


def format_json_report(results: list[ComparisonResult]) -> str:
    """Format results as a JSON report."""
    total = len(results)
    agreements = sum(1 for r in results if r.verdict_agrees)
    reviews = sum(1 for r in results if r.needs_review)

    report = {
        "summary": {
            "total": total,
            "verdict_agreements": agreements,
            "needs_review": reviews,
        },
        "results": [r.model_dump(mode="json") for r in results],
    }

    return json.dumps(report, indent=2)
