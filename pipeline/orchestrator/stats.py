"""Aggregate read-only statistics from claims and audit sidecars.

Backs the ``dr stats`` CLI subcommand. Pure data: no I/O beyond reading
the existing claim files and their paired ``.audit.yaml`` sidecars via
``content_loader`` and ``sidecar`` helpers.

Three aggregates land here so Tier 1 source-pool expansion can measure
its target metrics as Paths 1-3 ship (see
``docs/plans/source-pool-expansion-tier1.md``):

* ``wayback_recovery`` — Path 1 recovery rate (Wayback / Memento).
* ``acquisition_origins`` — Path 2/3 per-origin distribution.
* ``verification_levels`` — analyst-derived level distribution across all claims.

Empty-state behavior is deliberate: a corpus with no ``acquisition``
entries (the current state) yields zero counts and a ``None`` rate
rather than a ZeroDivisionError. The text formatter prints a
"no acquisition data yet" hint; the JSON formatter exposes ``null``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.content_loader import list_claims, load_claim
from common.frontmatter import parse_frontmatter
from common.sidecar import read_sidecar

# Per-URL acquisition origins emitted by the source-pool-expansion-tier1 paths.
# Keep this list in sync with the Zod enum in ``src/content.config.ts``.
ACQUISITION_ORIGINS: tuple[str, ...] = (
    "brave",
    "tavily",
    "arxiv",
    "s2",
    "openalex",
    "edgar",
)

# Analyst-set source-pool diversity tiers from the claim frontmatter.
# Mirror of the Zod enum at ``src/content.config.ts``; ``unset`` is the
# sentinel bucket for claims that have no ``verification_level`` field.
VERIFICATION_LEVELS: tuple[str, ...] = (
    "claimed",
    "self-reported",
    "partially-verified",
    "independently-verified",
    "multiply-verified",
)

# Wayback / Memento outcomes that count as a "recovered" ingest.
RECOVERY_VALUES: frozenset[str] = frozenset({"archive_org", "memento"})


def _iter_sources_consulted(repo_root: Path):
    """Yield every ``sources_consulted`` entry across every sidecar.

    Skips claims with no sidecar and sidecars whose payload is not a dict
    (e.g. an unparseable file: ``read_sidecar`` returns ``{}`` on parse
    error, which is harmless here).
    """
    for claim_path in list_claims(repo_root):
        sidecar = read_sidecar(claim_path)
        if not sidecar:
            continue
        entries = sidecar.get("sources_consulted") or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                yield entry


def _compute_wayback_recovery(entries: list[dict]) -> dict[str, Any]:
    """Recovery rate over the ingest-stage subset.

    Denominator: entries whose ``acquisition.stage == 'ingest'`` OR
    entries with no ``acquisition`` at all (legacy / current sidecars).
    The lenient legacy bucket is intentional — until Path 1 starts
    writing ``acquisition`` blocks, all current entries land here so
    the rate is measurable from day one.

    Numerator: entries whose ``acquisition.recovered_via`` is one of
    ``RECOVERY_VALUES``. By construction the numerator is a subset of
    the denominator (a recovered_via implies acquisition is present).

    Returns ``{"recovered": int, "total": int, "rate": float | None}``.
    Rate is ``None`` when ``total == 0`` to avoid a synthetic 0.0 that
    looks like real data.
    """
    recovered = 0
    total = 0
    for entry in entries:
        acq = entry.get("acquisition")
        if not isinstance(acq, dict):
            # Legacy / pre-acquisition sidecars: count as ingest by default.
            total += 1
            continue
        stage = acq.get("stage")
        if stage is None or stage == "ingest":
            total += 1
            if acq.get("recovered_via") in RECOVERY_VALUES:
                recovered += 1
    rate = (recovered / total) if total else None
    return {"recovered": recovered, "total": total, "rate": rate}


def _compute_acquisition_origins(entries: list[dict]) -> dict[str, Any]:
    """Histogram of ``acquisition.origin`` across all sources_consulted.

    Entries missing ``acquisition`` (or ``acquisition.origin``) bucket as
    ``unknown``. Recognised origins always appear with at least a zero so
    text/JSON output is shape-stable across runs.
    """
    counts: dict[str, int] = {origin: 0 for origin in ACQUISITION_ORIGINS}
    counts["unknown"] = 0
    total = 0
    for entry in entries:
        total += 1
        acq = entry.get("acquisition")
        origin = acq.get("origin") if isinstance(acq, dict) else None
        if origin in counts:
            counts[origin] += 1
        else:
            counts["unknown"] += 1
    return {**counts, "total": total}


def _compute_verification_levels(repo_root: Path) -> dict[str, Any]:
    """Histogram of ``verification_level`` across all claim frontmatter.

    ``verification_level`` is optional in the schema; claims that omit
    it bucket as ``unset``. Recognised levels always appear with at
    least a zero, again for stable output shape.
    """
    counts: dict[str, int] = {level: 0 for level in VERIFICATION_LEVELS}
    counts["unset"] = 0
    total = 0
    for claim_path in list_claims(repo_root):
        text = claim_path.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        total += 1
        level = fm.get("verification_level")
        if isinstance(level, str) and level in counts:
            counts[level] += 1
        else:
            counts["unset"] += 1
    return {**counts, "total": total}


def compute_stats(repo_root: Path) -> dict[str, Any]:
    """Walk ``repo_root`` and produce the three aggregates.

    Pure: takes only a repo root, reads the filesystem, returns a dict.
    No CLI / printing concerns leak in.
    """
    source_entries = list(_iter_sources_consulted(repo_root))
    return {
        "wayback_recovery": _compute_wayback_recovery(source_entries),
        "acquisition_origins": _compute_acquisition_origins(source_entries),
        "verification_levels": _compute_verification_levels(repo_root),
    }


def format_text_report(stats: dict[str, Any]) -> str:
    """Human-readable report mirroring ``dr lint``'s text style."""
    wr = stats["wayback_recovery"]
    ao = stats["acquisition_origins"]
    vl = stats["verification_levels"]

    lines = [
        "dr stats — dangerousrobot.org content aggregates",
        "=" * 60,
    ]

    # --- Wayback recovery ---
    lines.append("")
    lines.append("Wayback recovery (ingest stage)")
    if wr["total"] == 0:
        lines.append("  no acquisition data yet (0 sources scanned)")
    elif wr["rate"] is None:
        # Defensive: total > 0 with rate None shouldn't happen, but render safely.
        lines.append(f"  {wr['recovered']}/{wr['total']} (rate unavailable)")
    else:
        pct = f"{wr['rate'] * 100:.1f}%"
        lines.append(f"  {wr['recovered']}/{wr['total']} recovered ({pct})")

    # --- Acquisition origins ---
    lines.append("")
    lines.append(f"Acquisition origins ({ao['total']} sources)")
    if ao["total"] == 0:
        lines.append("  no sources scanned")
    else:
        for origin in [*ACQUISITION_ORIGINS, "unknown"]:
            lines.append(f"  {origin:<12} {ao[origin]}")

    # --- Verification levels ---
    lines.append("")
    lines.append(f"Verification levels ({vl['total']} claims)")
    if vl["total"] == 0:
        lines.append("  no claims found")
    else:
        for level in [*VERIFICATION_LEVELS, "unset"]:
            lines.append(f"  {level:<24} {vl[level]}")

    lines.append("=" * 60)
    return "\n".join(lines)


def format_json_report(stats: dict[str, Any]) -> str:
    """Stable JSON shape for downstream metric computation."""
    return json.dumps(stats, indent=2)
