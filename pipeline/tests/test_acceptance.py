"""Live acceptance tests that hit real APIs.

Run with: uv run pytest -m acceptance
Skipped by default in plain `uv run pytest`.

Requires BRAVE_WEB_SEARCH_API_KEY and ANTHROPIC_API_KEY in .env or environment.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

from common.content_loader import resolve_repo_root
from common.models import Verdict
from orchestrator.pipeline import VerifyConfig, verify_claim

load_dotenv()

_has_keys = bool(
    os.environ.get("BRAVE_WEB_SEARCH_API_KEY")
    and os.environ.get("ANTHROPIC_API_KEY")
)


@pytest.mark.acceptance
@pytest.mark.skipif(not _has_keys, reason="API keys not available")
@pytest.mark.skip(reason="multi-topic rename: baseline tuples need rebuild, see docs/plans/multi-topic.md")
class TestLiveVerification:

    @pytest.mark.asyncio
    async def test_false_claim_gets_false_verdict(self) -> None:
        """A knowingly false claim should produce a false or mostly-false verdict.

        Anthropic does not exclusively use models trained on 100%
        renewable energy -- no major LLM provider makes that guarantee.
        The pipeline should research this and reach that conclusion.
        """
        from orchestrator.checkpoints import AutoApproveCheckpointHandler

        result = await verify_claim(
            entity_name="Anthropic",
            claim_text=(
                "Anthropic only uses models that were trained "
                "on 100% renewable energy"
            ),
            config=VerifyConfig(max_sources=3),
            checkpoint=AutoApproveCheckpointHandler(),
        )

        # Pipeline should complete without fatal errors
        assert not result.errors, f"Pipeline errors: {result.errors}"

        # Research should find at least one source
        assert len(result.urls_found) > 0, "Research found no URLs"

        # At least one source should ingest successfully
        assert len(result.urls_ingested) > 0, "No sources ingested"

        # Analyst should produce a verdict
        assert result.analyst_output is not None, "No analyst output produced"

        assert result.analyst_output.verdict.verdict in (
            Verdict.FALSE,
            Verdict.MOSTLY_FALSE,
            Verdict.MIXED,
            Verdict.UNVERIFIED,
        ), f"Expected false-ish or unverified verdict, got: {result.analyst_output.verdict.verdict}"

        # The claim should NOT be rated as true
        assert result.analyst_output.verdict.verdict not in (
            Verdict.TRUE,
            Verdict.MOSTLY_TRUE,
        ), f"False claim rated as true: {result.analyst_output.verdict.verdict}"


# Baseline captured 2026-04-24 from the post-cleanup run. After re-running
# `dr onboard` the test compares the resulting research/ state to these values.
# LLM non-determinism: pin the deterministic fields (slug, topics) and lock
# verdict/confidence to current values so drift is visible (test fails -> review
# the change and either accept the new baseline or treat it as a regression).
#
# After the multi-topic rename (docs/plans/multi-topic.md) `topics` is a list;
# the assertion compares list-equality. The single-topic baselines below are
# the strawman shape (mirroring research/templates.yaml at the time of the
# rename) and will need a follow-up curation pass once the operator expands
# templates to multi-topic.

ANTHROPIC_ENTITY_BASELINE = {
    "name": "Anthropic",
    "type": "company",
    "website": "https://anthropic.com",
}

CLAUDE_ENTITY_BASELINE = {
    "name": "Claude",
    "type": "product",
    "website": "https://claude.ai",
}

# slug -> expected (verdict, confidence, topics, min_sources)
ANTHROPIC_CLAIM_BASELINE = {
    "corporate-structure": ("true", "high", ["industry-analysis"], 2),
    "donates-to-ai-safety": ("true", "high", ["ai-safety"], 2),
    "donates-to-environmental-causes": (
        "unverified",
        "low",
        ["environmental-impact"],
        2,
    ),
    "publishes-sustainability-report": (
        "unverified",
        "high",
        ["industry-analysis"],
        2,
    ),
}

CLAUDE_CLAIM_BASELINE = {
    "discloses-energy-sourcing": (
        "unverified",
        "medium",
        ["environmental-impact"],
        3,
    ),
    "discloses-models-used": (("true", "mostly-true"), "high", ["ai-literacy"], 3),
    "excludes-frontier-models": ("mostly-true", "high", ["ai-literacy"], 4),
    "excludes-image-generation": (
        "mostly-false",
        "high",
        ["product-comparison"],
        4,
    ),
    "no-training-on-user-data": ("mostly-true", "high", ["data-privacy"], 4),
    "realtime-energy-display": ("false", "high", ["product-comparison"], 4),
    "renewable-energy-hosting": (
        "unverified",
        "low",
        ["environmental-impact"],
        4,
    ),
}

REQUIRED_SIDECAR_KEYS = {
    "schema_version",
    "pipeline_run",
    "sources_consulted",
    "audit",
    "human_review",
}


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    assert m, f"No frontmatter in {path}"
    return yaml.safe_load(m.group(1)) or {}


@pytest.mark.acceptance
@pytest.mark.skipif(not _has_keys, reason="API keys not available")
@pytest.mark.skip(reason="multi-topic rename: baseline tuples need rebuild, see docs/plans/multi-topic.md")
class TestLiveCliCommands:
    """End-to-end CLI walkthrough for the Anthropic / Claude fixture.

    Runs the operator-facing commands against the real repo so resulting
    research/ files can be inspected by hand. ``--force`` is passed on
    onboard so the test is rerunnable without manual cleanup.

    After the commands complete, the resulting research/ state is asserted
    against the 2026-04-24 baseline captured at module top. A failing
    assertion means either (a) the LLM produced a different verdict and
    the baseline should be updated, or (b) the pipeline regressed.
    """

    def test_anthropic_claude_walkthrough(self) -> None:
        repo_root = resolve_repo_root()

        commands = [
            ["dr", "onboard", "Anthropic", "anthropic.com", "--type", "company", "--force"],
            ["dr", "review", "--claim", "anthropic/publishes-sustainability-report"],
            ["dr", "onboard", "Claude", "claude.ai", "--type", "product", "--force"],
        ]

        for cmd in commands:
            result = subprocess.run(
                cmd,
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            assert result.returncode == 0, (
                f"Command failed ({result.returncode}): {' '.join(cmd)}"
            )

        self._assert_entity(repo_root, "companies/anthropic", ANTHROPIC_ENTITY_BASELINE)
        self._assert_entity(repo_root, "products/claude", CLAUDE_ENTITY_BASELINE)

        self._assert_claims(repo_root, "anthropic", ANTHROPIC_CLAIM_BASELINE)
        self._assert_claims(repo_root, "claude", CLAUDE_CLAIM_BASELINE)

    @staticmethod
    def _assert_entity(repo_root: Path, ref: str, baseline: dict) -> None:
        path = repo_root / "research" / "entities" / f"{ref}.md"
        assert path.exists(), f"Missing entity file: {path}"
        fm = _parse_frontmatter(path)
        for field, expected in baseline.items():
            assert fm.get(field) == expected, (
                f"{ref}: expected {field}={expected!r}, got {fm.get(field)!r}"
            )

    @staticmethod
    def _assert_claims(
        repo_root: Path,
        entity_dir: str,
        baseline: dict[
            str,
            tuple[str | tuple[str, ...], str | tuple[str, ...], list[str], int],
        ],
    ) -> None:
        claim_dir = repo_root / "research" / "claims" / entity_dir
        assert claim_dir.is_dir(), f"Missing claim directory: {claim_dir}"

        actual_slugs = {p.stem for p in claim_dir.glob("*.md")}
        expected_slugs = set(baseline)
        assert actual_slugs == expected_slugs, (
            f"{entity_dir} claim set differs.\n"
            f"  missing:  {expected_slugs - actual_slugs}\n"
            f"  extra:    {actual_slugs - expected_slugs}"
        )

        def _matches(actual, expected) -> bool:
            # Accept a single value or a tuple/list of acceptable values
            # so baselines can tolerate LLM nondeterminism on a per-field basis.
            if isinstance(expected, (tuple, list)):
                return actual in expected
            return actual == expected

        for slug, (verdict, confidence, topics, min_sources) in baseline.items():
            claim_path = claim_dir / f"{slug}.md"
            fm = _parse_frontmatter(claim_path)
            assert _matches(fm.get("verdict"), verdict), (
                f"{entity_dir}/{slug}: verdict drift "
                f"(expected {verdict!r}, got {fm.get('verdict')!r})"
            )
            assert _matches(fm.get("confidence"), confidence), (
                f"{entity_dir}/{slug}: confidence drift "
                f"(expected {confidence!r}, got {fm.get('confidence')!r})"
            )
            assert fm.get("topics") == topics, (
                f"{entity_dir}/{slug}: topics mismatch "
                f"(expected {topics!r}, got {fm.get('topics')!r})"
            )
            sources = fm.get("sources") or []
            assert len(sources) >= min_sources, (
                f"{entity_dir}/{slug}: expected >= {min_sources} sources, "
                f"got {len(sources)}"
            )

            sidecar = claim_path.with_suffix(".audit.yaml")
            assert sidecar.exists(), f"Missing audit sidecar: {sidecar}"
            sidecar_data = yaml.safe_load(sidecar.read_text()) or {}
            missing_keys = REQUIRED_SIDECAR_KEYS - set(sidecar_data)
            assert not missing_keys, (
                f"{entity_dir}/{slug} sidecar missing keys: {missing_keys}"
            )
