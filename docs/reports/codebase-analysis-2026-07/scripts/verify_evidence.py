#!/usr/bin/env python3
"""Mechanical evidence check for analysis findings.

Every finding must carry evidence entries {file, line, quote}. A quote that
cannot be found (whitespace-normalized) in the named file auto-rejects the
evidence; line numbers are informational and tolerated to drift.

Usage (repo root):
  .venv/bin/python .../verify_evidence.py findings1.json [findings2.json ...]

Accepts either {"findings": [...]} or a bare list. Writes a verification
report next to each input as <name>.evidence-check.json and prints a summary.
Exit code 1 if any evidence failed.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path.cwd()


def normalize(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def check_evidence(ev):
    f = ev.get("file", "")
    quote = ev.get("quote", "")
    path = ROOT / f
    if not quote or len(normalize(quote)) < 8:
        return {"ok": False, "reason": "quote missing or too short (<8 chars normalized)"}
    if not path.is_file():
        return {"ok": False, "reason": f"file not found: {f}"}
    try:
        text = path.read_text(errors="replace")
    except OSError as e:
        return {"ok": False, "reason": f"unreadable: {e}"}
    nq, nt = normalize(quote), normalize(text)
    if nq not in nt:
        return {"ok": False, "reason": "quote not found in file"}
    # locate actual line for drift reporting
    lines = text.split("\n")
    first_words = normalize(quote).split(" ")[:4]
    needle = " ".join(first_words)
    actual = next((i + 1 for i, l in enumerate(lines) if needle in normalize(l)), None)
    claimed = ev.get("line")
    return {"ok": True, "actual_line": actual, "claimed_line": claimed,
            "line_drift": (actual is not None and claimed is not None and abs(actual - claimed) > 5)}


def main():
    any_fail = False
    for arg in sys.argv[1:]:
        p = Path(arg)
        data = json.loads(p.read_text())
        findings = data["findings"] if isinstance(data, dict) and "findings" in data else data
        report = []
        for fd in findings:
            fid = fd.get("id", "?")
            evs = fd.get("evidence", [])
            if not evs:
                report.append({"finding": fid, "ok": False, "reason": "no evidence entries"})
                any_fail = True
                continue
            for ev in evs:
                res = check_evidence(ev)
                report.append({"finding": fid, "file": ev.get("file"), **res})
                if not res["ok"]:
                    any_fail = True
        outp = p.with_suffix(".evidence-check.json")
        ok = sum(1 for r in report if r.get("ok"))
        outp.write_text(json.dumps({"input": str(p), "checked": len(report), "passed": ok,
                                    "failed": len(report) - ok, "results": report}, indent=1))
        print(f"{p.name}: {ok}/{len(report)} evidence entries verified")
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
