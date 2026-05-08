"""Tests for ``dr stats`` and the underlying ``orchestrator.stats`` aggregations.

Mirrors ``test_publish.py``'s ``tmp_path`` + CliRunner fixture style so
every test runs against a synthetic repo root with no leakage to the
real ``research/`` tree.

Coverage targets the four aggregate dimensions the plan calls out:
empty corpus, legacy (no acquisition) sidecars, full-acquisition
sidecars across multiple origins, and the verification_level histogram
across claim frontmatter. Both ``--format text`` and ``--format json``
paths are exercised; JSON is parsed back via ``json.loads`` to confirm
shape stability.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from orchestrator.cli import main
from orchestrator.stats import compute_stats


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_claim(
    tmp_path: Path,
    *,
    entity: str,
    slug: str,
    verification_level: str | None = None,
    sidecar_data: dict | None = None,
) -> tuple[Path, Path]:
    """Write a minimal claim + optional sidecar under ``tmp_path``.

    The claim frontmatter is intentionally bare (only ``title`` and an
    optional ``verification_level``); the stats aggregator only reads
    ``verification_level`` so we don't need a schema-complete file.
    """
    entity_dir = tmp_path / "research" / "claims" / entity
    entity_dir.mkdir(parents=True, exist_ok=True)

    claim_path = entity_dir / f"{slug}.md"
    fm_lines = ["---", "title: Test Claim"]
    if verification_level is not None:
        fm_lines.append(f"verification_level: {verification_level}")
    fm_lines.extend(["---", "Body.", ""])
    claim_path.write_text("\n".join(fm_lines), encoding="utf-8")

    sidecar_path = entity_dir / f"{slug}.audit.yaml"
    if sidecar_data is not None:
        sidecar_path.write_text(
            yaml.safe_dump(sidecar_data, sort_keys=False), encoding="utf-8"
        )
    return claim_path, sidecar_path


def _sidecar_with_sources(sources: list[dict]) -> dict:
    """Minimal sidecar payload around a ``sources_consulted`` list."""
    return {
        "schema_version": 1,
        "pipeline_run": {
            "ran_at": "2026-05-08T12:00:00+00:00",
            "model": "test-model",
            "agents": ["researcher"],
        },
        "sources_consulted": sources,
        "audit": None,
        "human_review": {
            "reviewed_at": None,
            "reviewer": None,
            "notes": None,
            "pr_url": None,
        },
    }


# ---------------------------------------------------------------------------
# Pure aggregation: compute_stats
# ---------------------------------------------------------------------------


class TestComputeStats:
    def test_empty_corpus_returns_zero_counts_and_null_rate(self, tmp_path: Path) -> None:
        # No research/ tree at all — list_claims should return [].
        result = compute_stats(tmp_path)

        assert result["wayback_recovery"] == {"recovered": 0, "total": 0, "rate": None}
        assert result["acquisition_origins"]["total"] == 0
        # All known origins still appear with zero counts (shape stability).
        for origin in ("brave", "tavily", "arxiv", "s2", "openalex", "edgar", "unknown"):
            assert result["acquisition_origins"][origin] == 0
        assert result["verification_levels"]["total"] == 0
        assert result["verification_levels"]["unset"] == 0

    def test_legacy_sidecars_no_acquisition_field(self, tmp_path: Path) -> None:
        """Sidecars without `acquisition` count toward total but never recover."""
        _write_claim(
            tmp_path,
            entity="ecosia",
            slug="claim-a",
            sidecar_data=_sidecar_with_sources([
                {"id": "2025/x", "url": "https://example.com/a", "title": "A", "ingested": True},
                {"id": "2025/y", "url": "https://example.com/b", "title": "B", "ingested": True},
            ]),
        )

        result = compute_stats(tmp_path)

        # Two ingest-bucket entries, zero recoveries, rate 0.0 (not None — total>0).
        assert result["wayback_recovery"] == {"recovered": 0, "total": 2, "rate": 0.0}
        # Both bucket as `unknown` in the origins histogram.
        assert result["acquisition_origins"]["unknown"] == 2
        assert result["acquisition_origins"]["total"] == 2
        # No origins have non-zero counts.
        for origin in ("brave", "tavily", "arxiv", "s2", "openalex", "edgar"):
            assert result["acquisition_origins"][origin] == 0

    def test_acquisition_origins_histogram(self, tmp_path: Path) -> None:
        """Origins span multiple values; histogram totals match input."""
        sources = [
            {
                "id": f"2026/s{i}", "url": f"https://e.org/{i}", "title": f"S{i}",
                "ingested": True,
                "acquisition": {"stage": "research", "origin": origin},
            }
            for i, origin in enumerate(["brave", "brave", "tavily", "arxiv", "edgar"])
        ]
        _write_claim(
            tmp_path,
            entity="anthropic",
            slug="claim-multi",
            sidecar_data=_sidecar_with_sources(sources),
        )

        result = compute_stats(tmp_path)

        ao = result["acquisition_origins"]
        assert ao["brave"] == 2
        assert ao["tavily"] == 1
        assert ao["arxiv"] == 1
        assert ao["edgar"] == 1
        assert ao["s2"] == 0
        assert ao["openalex"] == 0
        assert ao["unknown"] == 0
        assert ao["total"] == 5

    def test_wayback_recovery_rate_computes_correctly(self, tmp_path: Path) -> None:
        """Mix of recovered_via values; only ingest stage counts toward total."""
        sources = [
            # Recovered via archive.org (counts toward both numerator and denominator).
            {
                "id": "2026/a", "url": "https://e.org/a", "title": "A", "ingested": True,
                "acquisition": {
                    "stage": "ingest", "origin": "brave",
                    "recovered_via": "archive_org", "outcome": "recovered",
                },
            },
            # Recovered via memento.
            {
                "id": "2026/b", "url": "https://e.org/b", "title": "B", "ingested": True,
                "acquisition": {
                    "stage": "ingest", "origin": "tavily",
                    "recovered_via": "memento", "outcome": "recovered",
                },
            },
            # Ingest-stage but matched directly (no recovery).
            {
                "id": "2026/c", "url": "https://e.org/c", "title": "C", "ingested": True,
                "acquisition": {"stage": "ingest", "origin": "brave", "outcome": "matched"},
            },
            # Research-stage entry: NOT in the ingest denominator.
            {
                "id": "2026/d", "url": "https://e.org/d", "title": "D", "ingested": True,
                "acquisition": {"stage": "research", "origin": "openalex"},
            },
        ]
        _write_claim(
            tmp_path,
            entity="openai",
            slug="claim-recovered",
            sidecar_data=_sidecar_with_sources(sources),
        )

        wr = compute_stats(tmp_path)["wayback_recovery"]
        # 3 ingest entries, 2 recovered.
        assert wr == {"recovered": 2, "total": 3, "rate": 2 / 3}

    def test_verification_level_distribution(self, tmp_path: Path) -> None:
        """Histogram counts each known level + the `unset` sentinel."""
        _write_claim(tmp_path, entity="e1", slug="c1", verification_level="claimed")
        _write_claim(tmp_path, entity="e1", slug="c2", verification_level="claimed")
        _write_claim(tmp_path, entity="e1", slug="c3", verification_level="independently-verified")
        _write_claim(tmp_path, entity="e1", slug="c4", verification_level="multiply-verified")
        # No verification_level in frontmatter -> `unset`.
        _write_claim(tmp_path, entity="e1", slug="c5")

        vl = compute_stats(tmp_path)["verification_levels"]
        assert vl["claimed"] == 2
        assert vl["self-reported"] == 0
        assert vl["partially-verified"] == 0
        assert vl["independently-verified"] == 1
        assert vl["multiply-verified"] == 1
        assert vl["unset"] == 1
        assert vl["total"] == 5


# ---------------------------------------------------------------------------
# CLI: dr stats --format text|json
# ---------------------------------------------------------------------------


class TestDrStatsCli:
    def test_text_format_on_empty_corpus(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["stats", "--repo-root", str(tmp_path)])

        assert result.exit_code == 0, result.output
        # Empty-state hint, not a divide-by-zero.
        assert "no acquisition data yet" in result.output
        assert "0 sources scanned" in result.output

    def test_text_format_default_when_flag_omitted(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["stats", "--repo-root", str(tmp_path)])

        assert result.exit_code == 0, result.output
        # Header line is the text formatter's signature.
        assert "dr stats" in result.output
        assert "Wayback recovery" in result.output

    def test_json_format_parses_and_has_three_top_level_keys(self, tmp_path: Path) -> None:
        _write_claim(
            tmp_path,
            entity="ecosia",
            slug="c1",
            verification_level="self-reported",
            sidecar_data=_sidecar_with_sources([
                {
                    "id": "2026/a", "url": "https://e.org/a", "title": "A", "ingested": True,
                    "acquisition": {
                        "stage": "ingest", "origin": "brave",
                        "recovered_via": "archive_org", "outcome": "recovered",
                    },
                },
            ]),
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["stats", "--format", "json", "--repo-root", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)  # parses cleanly
        assert set(data.keys()) == {
            "wayback_recovery", "acquisition_origins", "verification_levels"
        }
        assert data["wayback_recovery"] == {"recovered": 1, "total": 1, "rate": 1.0}
        assert data["acquisition_origins"]["brave"] == 1
        assert data["acquisition_origins"]["total"] == 1
        assert data["verification_levels"]["self-reported"] == 1
        assert data["verification_levels"]["total"] == 1

    def test_json_format_empty_corpus_has_null_rate(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main, ["stats", "--format", "json", "--repo-root", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        # Null rate (not 0.0, not NaN) so downstream metrics can distinguish
        # "no data" from "data and zero recovery".
        assert data["wayback_recovery"]["rate"] is None
        assert data["wayback_recovery"]["recovered"] == 0
        assert data["wayback_recovery"]["total"] == 0

    def test_text_format_renders_origins_and_levels(self, tmp_path: Path) -> None:
        _write_claim(
            tmp_path,
            entity="anthropic",
            slug="c1",
            verification_level="independently-verified",
            sidecar_data=_sidecar_with_sources([
                {
                    "id": "2026/a", "url": "https://e.org/a", "title": "A", "ingested": True,
                    "acquisition": {"stage": "research", "origin": "tavily"},
                },
            ]),
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["stats", "--format", "text", "--repo-root", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        # Origin row and level row both appear with their counts.
        assert "tavily" in result.output
        assert "independently-verified" in result.output
