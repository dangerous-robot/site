"""Re-run v1 launch claims via dr claim-refresh and log what changed.

Written for the v1 source-quality backfill (2026-05-05), which landed
verification_level + cap_rationale onto the v1 launch claims. Per-claim deltas
are written to docs/plans/source-quality-rerun-log.jsonl.

- Re-run only claims with status=published and a criteria_slug.
- Skip status=draft and status=blocked (out of v1 scope, would risk
  unblocking or producing speculative verdicts).
- claim-refresh writes status: draft, resets the sidecar's human_review and
  keeps the prior published state in the sidecar's refresh block. This script
  leaves all of that as written: every refreshed claim leaves the published
  list until a person approves it in `dr review-queue`, even when the verdict
  and confidence are unchanged, because the sources and narrative may not be.
- Log per-claim status (with source-id deltas) to a JSONL file so the user
  can triage on return.

Usage:
  uv run python scripts/rerun_v1_claims.py --dry-run
  uv run python scripts/rerun_v1_claims.py --only microsoft/corporate-structure
  uv run python scripts/rerun_v1_claims.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CLAIMS_ROOT = ROOT / "research" / "claims"
LOG_PATH = ROOT / "docs" / "plans" / "source-quality-rerun-log.jsonl"
V1_ENTITIES = ["anthropic", "brave-leo", "brave-software", "chatgpt", "microsoft", "openai"]


def parse_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def sidecar_path_for(claim_path: Path) -> Path:
    return claim_path.with_name(claim_path.stem + ".audit.yaml")


def collect_v1_claims() -> list[Path]:
    paths: list[Path] = []
    for entity in V1_ENTITIES:
        d = CLAIMS_ROOT / entity
        if not d.is_dir():
            continue
        paths.extend(sorted(d.glob("*.md")))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Process a single claim (entity/slug)", default=None)
    ap.add_argument("--dry-run", action="store_true", help="List candidates and skips; do not run claim-refresh")
    ap.add_argument("--force", action="store_true", help="Re-run even if verification_level is already populated")
    args = ap.parse_args()

    candidates = collect_v1_claims()

    runnable: list[tuple[Path, dict]] = []
    skipped: list[tuple[Path, str]] = []

    for path in candidates:
        fm = parse_fm(path)
        rel = path.relative_to(CLAIMS_ROOT)
        ref = str(rel.with_suffix(""))
        if args.only and ref != args.only:
            continue
        status = fm.get("status")
        if status != "published":
            skipped.append((path, f"status={status!r}"))
            continue
        if not fm.get("criteria_slug"):
            skipped.append((path, "missing criteria_slug"))
            continue
        if fm.get("verification_level") and not args.force:
            skipped.append((path, "already has verification_level (use --force to re-run)"))
            continue
        runnable.append((path, fm))

    if not args.only:
        print(f"v1 launch claims found: {len(candidates)}")
        print(f"  runnable: {len(runnable)}")
        print(f"  skipped:  {len(skipped)}")
    for path, reason in skipped:
        print(f"  SKIP {path.relative_to(CLAIMS_ROOT)} -- {reason}", file=sys.stderr)

    if args.dry_run:
        return 0

    if not runnable:
        print("nothing to run", file=sys.stderr)
        return 1

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    summary: dict[str, int] = {"awaits_review": 0, "errors": 0}

    for i, (path, pre_fm) in enumerate(runnable, 1):
        rel = path.relative_to(CLAIMS_ROOT).with_suffix("")
        ref = str(rel)
        sidecar = sidecar_path_for(path)
        pre_review: dict | None = None
        if sidecar.exists():
            try:
                pre_data = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
                pre_review = pre_data.get("human_review")
            except yaml.YAMLError:
                pre_review = None
        pre_sources = list(pre_fm.get("sources") or [])
        pre_verdict = pre_fm.get("verdict")
        pre_confidence = pre_fm.get("confidence")
        started = time.time()
        print(f"\n[{i}/{len(runnable)}] {ref} -- pre: verdict={pre_verdict} confidence={pre_confidence}")

        cmd = ["uv", "run", "dr", "claim-refresh", ref]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        duration = time.time() - started

        log_entry: dict = {
            "ref": ref,
            "started": datetime.datetime.now().isoformat(),
            "duration_s": round(duration, 1),
            "pre": {"verdict": pre_verdict, "confidence": pre_confidence,
                    "sources": pre_sources,
                    "had_signoff": bool(pre_review and pre_review.get("reviewed_at")),
                    "reviewer": (pre_review or {}).get("reviewer")},
            "stdout_tail": (proc.stdout or "").splitlines()[-3:],
            "stderr_tail": (proc.stderr or "").splitlines()[-3:],
            "returncode": proc.returncode,
        }

        if proc.returncode != 0:
            print(f"  FAILED rc={proc.returncode}", file=sys.stderr)
            print(f"  stderr tail: {log_entry['stderr_tail']}", file=sys.stderr)
            summary["errors"] += 1
            log_entry["outcome"] = "error"
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
            continue

        post_fm = parse_fm(path)
        post_verdict = post_fm.get("verdict")
        post_confidence = post_fm.get("confidence")
        post_sources = list(post_fm.get("sources") or [])
        post_level = post_fm.get("verification_level")
        added = sorted(set(post_sources) - set(pre_sources))
        removed = sorted(set(pre_sources) - set(post_sources))

        unchanged = (pre_verdict == post_verdict) and (pre_confidence == post_confidence)
        log_entry["post"] = {
            "verdict": post_verdict,
            "confidence": post_confidence,
            "verification_level": post_level,
            "sources": post_sources,
            "sources_added": added,
            "sources_removed": removed,
        }
        log_entry["outcome"] = "awaits_review"
        log_entry["next_step"] = "draft until a person approves it in dr review-queue"
        summary["awaits_review"] += 1
        change = "unchanged" if unchanged else f"now verdict={post_verdict} confidence={post_confidence}"
        print(f"  refreshed ({change}) -- draft, awaits review in dr review-queue")

        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

    print("\n=== Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  log: {LOG_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
