#!/usr/bin/env python3
"""Mechanical conformance sweep of the research/ content corpus.

Purely descriptive (no schema assumptions encoded here beyond enum values
parsed from content.config.ts): per-collection counts, per-field coverage,
enum-value violations, and claim/.audit.yaml sidecar pairing.

Run from repo root: .venv/bin/python docs/reports/codebase-analysis-2026-07/scripts/data_conformance.py
"""

import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path.cwd()
OUT = ROOT / "docs/reports/codebase-analysis-2026-07/data/data-conformance.json"


def frontmatter(path):
    text = path.read_text(errors="replace")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return "PARSE_ERROR"


def ts_enum_values():
    """Pull the enum vocab for claim fields straight from the Zod source."""
    text = (ROOT / "src/content.config.ts").read_text()
    vocab = {}
    for m in re.finditer(r"(\w+)\s*:\s*z\.enum\(\s*\[([^\]]*)\]", text):
        vocab.setdefault(m.group(1), set()).update(re.findall(r"['\"]([^'\"]+)['\"]", m.group(2)))
    return vocab


def sweep_collection(paths):
    field_coverage = Counter()
    parse_errors, missing_fm = [], []
    docs = {}
    for p in paths:
        fm = frontmatter(p)
        rel = str(p.relative_to(ROOT))
        if fm is None:
            missing_fm.append(rel)
        elif fm == "PARSE_ERROR":
            parse_errors.append(rel)
        elif isinstance(fm, dict):
            docs[rel] = fm
            field_coverage.update(fm.keys())
    return docs, field_coverage, parse_errors, missing_fm


def main():
    vocab = ts_enum_values()

    claims = sorted((ROOT / "research/claims").rglob("*.md"))
    sidecars = sorted((ROOT / "research/claims").rglob("*.audit.yaml"))
    sources = sorted((ROOT / "research/sources").rglob("*.md"))
    entities = sorted((ROOT / "research/entities").rglob("*.md"))

    claim_docs, claim_fields, claim_errs, claim_nofm = sweep_collection(claims)
    source_docs, source_fields, source_errs, source_nofm = sweep_collection(sources)
    entity_docs, entity_fields, entity_errs, entity_nofm = sweep_collection(entities)

    # sidecar pairing: claim foo.md <-> foo.audit.yaml
    claim_stems = {str(p.relative_to(ROOT)).removesuffix(".md") for p in claims}
    sidecar_stems = {str(p.relative_to(ROOT)).removesuffix(".audit.yaml") for p in sidecars}
    claims_without_sidecar = sorted(claim_stems - sidecar_stems)
    orphan_sidecars = sorted(sidecar_stems - claim_stems)

    # enum violations against the Zod vocab
    violations = defaultdict(list)
    checked_fields = [f for f in ("verdict", "confidence", "status", "kind",
                                  "source_type", "independence", "verification_level", "type")
                      if f in vocab]
    for rel, fm in {**claim_docs, **source_docs, **entity_docs}.items():
        for field in checked_fields:
            if field in fm and isinstance(fm[field], str) and fm[field] not in vocab[field]:
                violations[field].append({"file": rel, "value": fm[field]})

    distributions = {}
    for field in ("verdict", "confidence", "status"):
        distributions[field] = dict(Counter(
            fm.get(field) for fm in claim_docs.values() if fm.get(field)))
    distributions["source_kind"] = dict(Counter(
        fm.get("kind") for fm in source_docs.values() if fm.get("kind")))
    distributions["entity_type"] = dict(Counter(
        fm.get("type") for fm in entity_docs.values() if fm.get("type")))

    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    out = {
        "provenance": {"commit": head, "generated_by": "data_conformance.py",
                       "enum_vocab_source": "src/content.config.ts z.enum sites",
                       "note": "descriptive sweep; field coverage counts, not required-field validation"},
        "counts": {"claims": len(claims), "audit_sidecars": len(sidecars),
                   "sources": len(sources), "entities": len(entities)},
        "sidecar_pairing": {"claims_without_sidecar": claims_without_sidecar,
                            "orphan_sidecars": orphan_sidecars},
        "field_coverage": {"claims": dict(claim_fields.most_common()),
                           "sources": dict(source_fields.most_common()),
                           "entities": dict(entity_fields.most_common())},
        "frontmatter_problems": {
            "parse_errors": claim_errs + source_errs + entity_errs,
            "missing_frontmatter": claim_nofm + source_nofm + entity_nofm},
        "enum_violations": {k: v for k, v in violations.items()},
        "distributions": distributions,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"data-conformance: {len(claims)} claims ({len(claims_without_sidecar)} missing sidecar, "
          f"{len(orphan_sidecars)} orphan sidecars), {len(sources)} sources, {len(entities)} entities, "
          f"{sum(len(v) for v in violations.values())} enum violations")


if __name__ == "__main__":
    main()
