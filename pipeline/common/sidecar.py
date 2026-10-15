"""Read/write helpers for the `.audit.yaml` sidecar that lives next to each claim."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def sidecar_path_for(claim_path: Path) -> Path:
    return claim_path.with_name(claim_path.stem + ".audit.yaml")


def read_sidecar(claim_path: Path) -> dict[str, Any] | None:
    sidecar_path = sidecar_path_for(claim_path)
    if not sidecar_path.exists():
        return None
    try:
        return yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def pipeline_verdict_of(audit: dict[str, Any] | None) -> str | None:
    """The verdict the pipeline settled on, from a sidecar's ``audit`` block.

    A sidecar written before the tie-breaker existed carries no
    ``pipeline_verdict``; there the analyst's verdict was the pipeline's.
    """
    if not isinstance(audit, dict):
        return None
    return audit.get("pipeline_verdict") or audit.get("analyst_verdict")
