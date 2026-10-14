"""Backfill each claim sidecar's analyst record from git, once.

A forced rewrite (dr draft --claim <ref> --force) tells the operator's
seo_title, takeaway and cap_rationale from the analyst's by comparing them with
the sidecar's `analyst_record`. Sidecars written before that record
existed have none, so every value on disk counts as the operator's. This script
writes the record from each claim's last pipeline-written version in git.

Which commit counts as pipeline-written: the newest commit that has the claim
file at its current path where
  - the sidecar's `pipeline_run.ran_at` differs from the parent commit's (or
    the sidecar is new), so a pipeline run rewrote the sidecar in that commit;
  - `pipeline_run.agents` includes `analyst`, so the run wrote the claim text
    (a `dr step-audit --write` or a blocked run rewrites only the sidecar);
  - the claim's status is not `blocked` (a blocked write holds placeholders).
`dr review` approvals and hand edits leave `ran_at` unchanged, so they are
never chosen. Commit messages are not used: they are written by hand.

Limits: `dr step-analyze --write` rewrites the claim without the sidecar, so
its writes are invisible here, and a hand edit made before the run's commit is
indistinguishable from the analyst's text.

Usage (from the repo root):
  uv run --directory pipeline python ../scripts/backfill_analyst_record.py           # dry run
  uv run --directory pipeline python ../scripts/backfill_analyst_record.py --write
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_COMPARED = ("title", "seo_title", "verdict", "takeaway", "cap_rationale")


@dataclasses.dataclass
class Row:
    claim: str
    commit: str | None = None
    commit_date: str | None = None
    record: dict | None = None
    differs: list[str] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)
    skip: str | None = None


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _show(repo: Path, commit: str, rel: str) -> str | None:
    result = _git(repo, "show", f"{commit}:{rel}")
    return result.stdout if result.returncode == 0 else None


def _frontmatter(text: str | None) -> dict | None:
    match = _FRONTMATTER.match(text or "")
    if not match:
        return None
    loaded = yaml.safe_load(match.group(1))
    return loaded if isinstance(loaded, dict) else None


def _yaml(text: str | None) -> dict:
    if not text:
        return {}
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _run(sidecar: dict) -> dict:
    run = sidecar.get("pipeline_run")
    return run if isinstance(run, dict) else {}


def _text(value: object) -> str:
    # The claim writer reads a missing takeaway or cap_rationale as "".
    return "" if value is None else str(value)


def record_from(fm: dict) -> dict:
    """The record `updated_analyst_record` would have written for this version."""
    record: dict = {}
    if fm.get("seo_title") is not None:
        record["title"] = fm.get("title")
        record["seo_title"] = fm["seo_title"]
    if fm.get("verdict") is not None:
        record["verdict"] = str(fm["verdict"])
    if fm.get("takeaway") is not None:
        record["takeaway"] = fm["takeaway"]
    record["cap_rationale"] = fm.get("cap_rationale")
    return record


def _pipeline_written(repo: Path, claim_rel: str, sidecar_rel: str) -> tuple[str, str, str, dict] | None:
    log = _git(repo, "log", "--format=%H %h %ad", "--date=short", "--", claim_rel).stdout.split("\n")
    for line in filter(None, log):
        full, short, date = line.split(" ")
        fm = _frontmatter(_show(repo, full, claim_rel))
        if fm is None or fm.get("status") == "blocked":
            continue
        run = _run(_yaml(_show(repo, full, sidecar_rel)))
        if "analyst" not in (run.get("agents") or []):
            continue
        if run.get("ran_at") == _run(_yaml(_show(repo, f"{full}^", sidecar_rel))).get("ran_at"):
            continue
        return full, short, date, fm
    return None


def plan(repo_root: Path) -> list[Row]:
    rows = []
    for path in sorted((repo_root / "research" / "claims").rglob("*.md")):
        claim_rel = path.relative_to(repo_root).as_posix()
        sidecar_path = path.with_name(path.stem + ".audit.yaml")
        sidecar_rel = sidecar_path.relative_to(repo_root).as_posix()
        row = Row(claim=claim_rel)
        rows.append(row)
        if not sidecar_path.exists():
            row.skip = "no sidecar on disk"
            continue
        if "analyst_record" in _yaml(sidecar_path.read_text(encoding="utf-8")):
            row.skip = "sidecar already has an analyst_record"
            continue
        found = _pipeline_written(repo_root, claim_rel, sidecar_rel)
        if found is None:
            row.skip = "no pipeline-written version in git"
            continue
        full, row.commit, row.commit_date, fm = found
        row.record = record_from(fm)
        current = _frontmatter(path.read_text(encoding="utf-8")) or {}
        row.differs = [
            field for field in _COMPARED
            if field in row.record and _text(current.get(field)) != _text(row.record[field])
        ]
        if _show(repo_root, f"{full}^", claim_rel) is not None:
            row.notes.append("run overwrote an earlier version, so a kept value may predate it")
    return rows


def write(repo_root: Path, rows: list[Row]) -> int:
    written = 0
    for row in rows:
        if row.skip or row.record is None:
            continue
        sidecar_path = (repo_root / row.claim).with_name(Path(row.claim).stem + ".audit.yaml")
        text = sidecar_path.read_text(encoding="utf-8")
        # Appended rather than re-dumped, so the rest of the file keeps its
        # YAML style and the diff shows only the record. plan() skipped any
        # sidecar that already has the key.
        if text and not text.endswith("\n"):
            text += "\n"
        sidecar_path.write_text(
            text + yaml.safe_dump({"analyst_record": row.record}, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        written += 1
    return written


def _print(rows: list[Row]) -> None:
    print("claim\tcommit\trecord\tdiffers_from_current\tnotes")
    for row in rows:
        if row.skip:
            print(f"{row.claim}\t-\tskip: {row.skip}\t-\t-")
            continue
        print("\t".join([
            row.claim,
            f"{row.commit} ({row.commit_date})",
            json.dumps(row.record, ensure_ascii=False),
            ",".join(row.differs) or "none",
            "; ".join(row.notes) or "-",
        ]))
    with_record = [r for r in rows if r.record is not None]
    print(
        f"\n{len(rows)} claims: {len(with_record)} would get a record, "
        f"{sum(1 for r in with_record if r.differs)} of them with a current value that "
        f"differs from it (kept as the operator's on the next refresh), "
        f"{len(rows) - len(with_record)} skipped."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true", help="Write the records (default: dry run).")
    args = parser.parse_args()

    rows = plan(args.repo_root)
    _print(rows)
    if args.write:
        print(f"Wrote {write(args.repo_root, rows)} sidecar(s).")
    else:
        print("Dry run: nothing written. Pass --write to write the records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
