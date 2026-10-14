"""scripts/rerun_v1_claims.py must not carry a sign-off onto refreshed content.

An unchanged verdict does not mean unchanged sources or narrative. Writing the
pre-refresh ``human_review`` back and flipping the claim to published would put
regenerated content live under a person's name with nobody at a terminal.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rerun_v1_claims.py"

CLAIM = """---
title: Example claim
status: {status}
criteria_slug: example-criterion
verdict: true
confidence: high
sources:
  - 2026/example-source
---
Body.
"""

SIGNED_OFF = {
    "reviewed_at": "2026-05-01",
    "reviewer": "reviewer@example.org",
    "notes": "checked",
    "pr_url": None,
}
RESET = {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None}


def _load_script():
    spec = importlib.util.spec_from_file_location("rerun_v1_claims", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_with_unchanged_verdict_stays_draft_and_unsigned(tmp_path, monkeypatch):
    script = _load_script()
    claims_root = tmp_path / "research" / "claims"
    claim = claims_root / "anthropic" / "example.md"
    sidecar = claim.with_name("example.audit.yaml")
    claim.parent.mkdir(parents=True)
    claim.write_text(CLAIM.format(status="published"), encoding="utf-8")
    sidecar.write_text(yaml.safe_dump({"human_review": SIGNED_OFF}), encoding="utf-8")
    log_path = tmp_path / "rerun-log.jsonl"

    def fake_claim_refresh(cmd, **kwargs):
        # What dr draft --claim --force does to these files: same verdict, status
        # draft, sign-off reset. No model or network call.
        claim.write_text(CLAIM.format(status="draft"), encoding="utf-8")
        sidecar.write_text(yaml.safe_dump({"human_review": dict(RESET)}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(script, "CLAIMS_ROOT", claims_root)
    monkeypatch.setattr(script, "LOG_PATH", log_path)
    monkeypatch.setattr(script.subprocess, "run", fake_claim_refresh)
    monkeypatch.setattr(sys, "argv", ["rerun_v1_claims.py", "--only", "anthropic/example"])

    assert script.main() == 0

    assert script.parse_fm(claim)["status"] == "draft"
    review = yaml.safe_load(sidecar.read_text(encoding="utf-8"))["human_review"]
    assert review["reviewed_at"] is None
    assert review["reviewer"] is None
    entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["outcome"] == "awaits_review"
    assert "dr review-queue" in entry["next_step"]
