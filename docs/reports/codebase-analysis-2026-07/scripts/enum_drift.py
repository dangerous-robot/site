#!/usr/bin/env python3
"""Mechanical diff of the hand-duplicated enum values across the Python/Zod boundary.

Compares Enum classes in pipeline/common/models.py against z.enum([...]) value
sets in src/content.config.ts (const arrays resolved). Pairs are matched by
value-set overlap (Jaccard), so renamed containers still pair up.

Run from repo root: .venv/bin/python docs/reports/codebase-analysis-2026-07/scripts/enum_drift.py
"""

import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
PY_FILE = ROOT / "pipeline/common/models.py"
TS_FILE = ROOT / "src/content.config.ts"
OUT = ROOT / "docs/reports/codebase-analysis-2026-07/data/enum-drift.json"


def python_enums():
    tree = ast.parse(PY_FILE.read_text())
    enums = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
        if not base_names & {"Enum", "StrEnum", "IntEnum"}:
            continue
        values = []
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant):
                values.append(str(stmt.value.value))
        if values:
            enums[node.name] = {"values": values, "line": node.lineno}
    return enums


def ts_enums():
    text = TS_FILE.read_text()
    lines = text.split("\n")

    # const NAME = ["a", "b"] as const  (arrays that may feed z.enum)
    const_arrays = {}
    for m in re.finditer(r"const\s+(\w+)\s*=\s*\[([^\]]*)\]\s*as\s+const", text):
        const_arrays[m.group(1)] = re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))

    found = {}

    def line_of(pos):
        return text.count("\n", 0, pos) + 1

    def context_key(pos):
        """Nearest preceding `key:` or `const name` for a readable label."""
        prefix = text[:pos]
        m = re.search(r"(\w+)\s*:\s*z\.enum\($", prefix)
        if m:
            return m.group(1)
        for lm in reversed(list(re.finditer(r"(\w+)\s*:", prefix[-300:]))):
            return lm.group(1)
        return f"enum@{line_of(pos)}"

    for m in re.finditer(r"z\.enum\(\s*\[([^\]]*)\]", text):
        values = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
        if values:
            found[f"{context_key(m.start())}:{line_of(m.start())}"] = {
                "values": values, "line": line_of(m.start())}
    for m in re.finditer(r"z\.enum\(\s*(\w+)\s*\)", text):
        name = m.group(1)
        if name in const_arrays:
            found[f"{name}:{line_of(m.start())}"] = {
                "values": const_arrays[name], "line": line_of(m.start())}
    return found


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def main():
    py = python_enums()
    ts = ts_enums()

    pairs, drift = [], []
    used_ts = set()
    for py_name, py_rec in py.items():
        best, best_score = None, 0.0
        for ts_name, ts_rec in ts.items():
            score = jaccard(py_rec["values"], ts_rec["values"])
            if score > best_score:
                best, best_score = ts_name, score
        if best and best_score >= 0.5:
            used_ts.add(best)
            ts_rec = ts[best]
            only_py = sorted(set(py_rec["values"]) - set(ts_rec["values"]))
            only_ts = sorted(set(ts_rec["values"]) - set(py_rec["values"]))
            rec = {
                "python_enum": py_name, "python_line": py_rec["line"],
                "ts_enum": best, "ts_line": ts_rec["line"],
                "jaccard": round(best_score, 3),
                "only_in_python": only_py, "only_in_ts": only_ts,
                "in_sync": not only_py and not only_ts,
            }
            (pairs if rec["in_sync"] else drift).append(rec)

    unmatched_py = [{"python_enum": k, "line": v["line"], "values": v["values"]}
                    for k, v in py.items()
                    if not any(p["python_enum"] == k for p in pairs + drift)]
    unmatched_ts = [{"ts_enum": k, "line": v["line"], "values": v["values"]}
                    for k, v in ts.items() if k not in used_ts]

    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    out = {
        "provenance": {"commit": head, "generated_by": "enum_drift.py",
                       "python_source": str(PY_FILE.relative_to(ROOT)),
                       "ts_source": str(TS_FILE.relative_to(ROOT)),
                       "pairing": "value-set Jaccard >= 0.5"},
        "in_sync": pairs,
        "drifted": drift,
        "python_only": unmatched_py,
        "ts_only": unmatched_ts,
        "summary": {"python_enums": len(py), "ts_enum_sites": len(ts),
                    "in_sync": len(pairs), "drifted": len(drift)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"enum-drift: {len(py)} py enums, {len(ts)} ts enum sites, "
          f"{len(pairs)} in sync, {len(drift)} drifted, "
          f"{len(unmatched_py)} py-only, {len(unmatched_ts)} ts-only")


if __name__ == "__main__":
    main()
