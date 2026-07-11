#!/usr/bin/env python3
"""Deterministic per-file metrics for the codebase analysis report.

Produces data/metrics.json: LOC, lizard complexity, git churn, import
fan-in/out, graphify centrality, and a composite hotspot rank. All numbers
cited in ANALYSIS.md and the interactive artifacts trace back to this file.

Run from repo root: .venv/bin/python docs/reports/codebase-analysis-2026-07/scripts/compute_metrics.py
"""

import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import lizard
import networkx as nx

ROOT = Path.cwd()
OUT = ROOT / "docs/reports/codebase-analysis-2026-07/data/metrics.json"

SRC_GLOBS = [
    ("src", ["*.astro", "*.ts", "*.css"]),
    ("pipeline", ["*.py"]),
    ("scripts", ["*.py", "*.ts", "*.mjs", "*.sh"]),
]
ROOT_FILES = ["tasks.py", "astro.config.ts"]
EXCLUDE_PARTS = {".venv", "node_modules", "__pycache__", ".astro", "dist", "archive"}

PIPELINE_PKGS = {"common", "orchestrator", "researcher", "ingestor", "analyst", "auditor", "linter", "tests"}


def collect_files():
    files = []
    for base, patterns in SRC_GLOBS:
        for pattern in patterns:
            for p in (ROOT / base).rglob(pattern):
                if EXCLUDE_PARTS & set(p.parts):
                    continue
                files.append(p.relative_to(ROOT))
    for f in ROOT_FILES:
        if (ROOT / f).exists():
            files.append(Path(f))
    return sorted(set(files))


def git_tracked():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=ROOT)
    return set(out.stdout.splitlines())


def git_churn():
    """Commits + line churn per path over full history (no rename following)."""
    out = subprocess.run(
        ["git", "log", "--numstat", "--format=@%H"],
        capture_output=True, text=True, cwd=ROOT,
    )
    churn = defaultdict(lambda: {"commits": 0, "added": 0, "deleted": 0})
    seen_in_commit = set()
    for line in out.stdout.splitlines():
        if line.startswith("@"):
            seen_in_commit = set()
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if path not in seen_in_commit:
            churn[path]["commits"] += 1
            seen_in_commit.add(path)
        if added.isdigit():
            churn[path]["added"] += int(added)
        if deleted.isdigit():
            churn[path]["deleted"] += int(deleted)
    return churn


def astro_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    return m.group(1) if m else ""


def complexity(path, text):
    """lizard analysis; .astro analyzed as its TS frontmatter only."""
    suffix = path.suffix
    if suffix == ".astro":
        code = astro_frontmatter(text)
        if not code.strip():
            return None
        info = lizard.analyze_file.analyze_source_code(str(path.with_suffix(".ts")), code)
    elif suffix in (".py", ".ts", ".mjs"):
        info = lizard.analyze_file.analyze_source_code(str(path), text)
    else:
        return None
    fns = info.function_list
    return {
        "nloc": info.nloc,
        "functions": len(fns),
        "ccn_max": max((f.cyclomatic_complexity for f in fns), default=0),
        "ccn_total": sum(f.cyclomatic_complexity for f in fns),
        "longest_fn_nloc": max((f.nloc for f in fns), default=0),
        "worst_fn": max(fns, key=lambda f: f.cyclomatic_complexity).name if fns else None,
    }


def python_imports(files, texts):
    """Import edges within pipeline/ resolved via ast (deterministic)."""
    module_to_path = {}
    for f in files:
        if f.suffix == ".py" and f.parts[0] == "pipeline":
            mod = ".".join(f.with_suffix("").parts[1:])
            module_to_path[mod] = str(f)
            if f.name == "__init__.py":
                module_to_path[".".join(f.parts[1:-1])] = str(f)

    def resolve(mod):
        for candidate in (mod, mod + ".__init__"):
            if candidate in module_to_path:
                return module_to_path[candidate]
        # from common.models import X -> common.models
        parts = mod.split(".")
        while parts:
            joined = ".".join(parts)
            if joined in module_to_path:
                return module_to_path[joined]
            parts = parts[:-1]
        return None

    edges = []
    for f in files:
        if f.suffix != ".py" or f.parts[0] != "pipeline":
            continue
        try:
            tree = ast.parse(texts[f])
        except SyntaxError:
            continue
        pkg_parts = f.with_suffix("").parts[1:-1] if f.name != "__init__.py" else f.parts[1:-1]
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = list(pkg_parts)[: len(pkg_parts) - node.level + 1]
                    mod = ".".join(base + ([node.module] if node.module else []))
                else:
                    mod = node.module or ""
                mods = [mod]
            for mod in mods:
                if mod.split(".")[0] in PIPELINE_PKGS:
                    target = resolve(mod)
                    if target and target != str(f):
                        edges.append({"source": str(f), "target": target, "source_type": "deterministic"})
    return edges


def ts_imports(files, texts):
    """Import edges in src/ + scripts/ via regex (approximate: no re-exports)."""
    existing = {str(f) for f in files}
    pattern = re.compile(r"""(?:^|\n)\s*import\s+(?:[^'"]*?\sfrom\s+)?['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]""")
    edges = []
    for f in files:
        if f.suffix not in (".ts", ".astro", ".mjs"):
            continue
        text = texts[f] if f.suffix != ".astro" else astro_frontmatter(texts[f])
        for m in pattern.finditer(text):
            spec = m.group(1) or m.group(2)
            if not spec or not spec.startswith("."):
                continue
            base = (f.parent / spec).resolve()
            try:
                base = base.relative_to(ROOT)
            except ValueError:
                continue
            for cand in (str(base), f"{base}.ts", f"{base}.astro", f"{base}.mjs", f"{base}/index.ts"):
                if cand in existing:
                    edges.append({"source": str(f), "target": cand, "source_type": "grep-approx"})
                    break
    return edges


def graph_centrality():
    """Per-file degree + betweenness from the graphify graph, EXTRACTED edges only."""
    g = json.loads((ROOT / "graphify-out/graph.json").read_text())
    G = nx.Graph()
    node_file = {}
    for n in g["nodes"]:
        G.add_node(n["id"])
        if n.get("source_file"):
            node_file[n["id"]] = n["source_file"]
    kept = 0
    for l in g["links"]:
        if l.get("confidence") == "EXTRACTED":
            G.add_edge(l["source"], l["target"])
            kept += 1
    deg = nx.degree_centrality(G)
    btw = nx.betweenness_centrality(G, k=400, seed=42)
    per_file = defaultdict(lambda: {"degree_sum": 0.0, "betweenness_sum": 0.0, "betweenness_max": 0.0, "nodes": 0})
    for nid, f in node_file.items():
        rec = per_file[f]
        rec["nodes"] += 1
        rec["degree_sum"] += deg.get(nid, 0)
        b = btw.get(nid, 0)
        rec["betweenness_sum"] += b
        rec["betweenness_max"] = max(rec["betweenness_max"], b)
    meta = {
        "built_at_commit": g.get("built_at_commit"),
        "edges_total": len(g["links"]),
        "edges_extracted_used": kept,
        "betweenness_sample_k": 400,
        "betweenness_seed": 42,
    }
    return {k: {m: round(v, 6) if isinstance(v, float) else v for m, v in rec.items()} for k, rec in per_file.items()}, meta


def main():
    files = collect_files()
    texts = {}
    for f in files:
        try:
            texts[f] = (ROOT / f).read_text(errors="replace")
        except OSError:
            texts[f] = ""

    tracked = git_tracked()
    churn = git_churn()
    centrality, graph_meta = graph_centrality()

    py_edges = python_imports(files, texts)
    ts_edges = ts_imports(files, texts)
    all_edges = py_edges + ts_edges
    fan_in, fan_out = defaultdict(int), defaultdict(int)
    for e in all_edges:
        fan_out[e["source"]] += 1
        fan_in[e["target"]] += 1

    records = {}
    for f in files:
        s = str(f)
        text = texts[f]
        comp = complexity(f, text)
        records[s] = {
            "loc": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
            "lang": f.suffix.lstrip("."),
            "tracked": s in tracked,
            "churn_commits": churn.get(s, {}).get("commits", 0),
            "churn_added": churn.get(s, {}).get("added", 0),
            "churn_deleted": churn.get(s, {}).get("deleted", 0),
            "fan_in": fan_in.get(s, 0),
            "fan_out": fan_out.get(s, 0),
            "complexity": comp,
            "centrality": centrality.get(s),
        }

    # Composite hotspot: weighted mean of normalized churn, complexity, centrality.
    scored = []
    candidates = {s: r for s, r in records.items() if r["complexity"] and r["tracked"]}
    if candidates:
        max_churn = max(r["churn_commits"] for r in candidates.values()) or 1
        max_ccn = max(r["complexity"]["ccn_total"] for r in candidates.values()) or 1
        max_btw = max((r["centrality"] or {}).get("betweenness_sum", 0) for r in candidates.values()) or 1
        for s, r in candidates.items():
            score = round(
                0.4 * (r["churn_commits"] / max_churn)
                + 0.4 * (r["complexity"]["ccn_total"] / max_ccn)
                + 0.2 * ((r["centrality"] or {}).get("betweenness_sum", 0) / max_btw),
                4,
            )
            scored.append({"path": s, "score": score,
                           "churn_commits": r["churn_commits"],
                           "ccn_total": r["complexity"]["ccn_total"],
                           "betweenness_sum": (r["centrality"] or {}).get("betweenness_sum", 0)})
        scored.sort(key=lambda x: (-x["score"], x["path"]))
        for i, rec in enumerate(scored):
            rec["rank"] = i + 1
            if rec["path"] in records:
                records[rec["path"]]["hotspot_rank"] = i + 1
                records[rec["path"]]["hotspot_score"] = rec["score"]

    by_dir = defaultdict(lambda: {"files": 0, "loc": 0})
    for s, r in records.items():
        d = str(Path(s).parent)
        by_dir[d]["files"] += 1
        by_dir[d]["loc"] += r["loc"]

    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    out = {
        "provenance": {
            "commit": head,
            "generated_by": "compute_metrics.py",
            "tools": {"lizard": lizard.version, "networkx": nx.__version__,
                      "python": sys.version.split()[0]},
            "graphify_graph": graph_meta,
            "hotspot_formula": "0.4*norm(churn_commits) + 0.4*norm(ccn_total) + 0.2*norm(betweenness_sum)",
            "notes": [
                "churn covers full git history, no rename following",
                ".astro complexity covers frontmatter TS only (template logic excluded)",
                "ts import edges are regex-derived (grep-approx): re-exports/dynamic aliases missed",
                "centrality from graphify graph EXTRACTED edges only; betweenness sampled k=400 seed=42",
            ],
        },
        "files": records,
        "hotspots_top30": scored[:30],
        "import_edges": all_edges,
        "by_dir": {k: dict(v) for k, v in sorted(by_dir.items())},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, sort_keys=False))
    print(f"metrics.json: {len(records)} files, {len(all_edges)} import edges, top hotspot: "
          f"{scored[0]['path'] if scored else 'n/a'}")


if __name__ == "__main__":
    main()
