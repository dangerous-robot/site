"""Live acceptance tests that hit real APIs.

Run with: uv run pytest -m acceptance
Skipped by default in plain `uv run pytest`.

Requires BRAVE_WEB_SEARCH_API_KEY and ANTHROPIC_API_KEY in .env or environment.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from common.models import Verdict
from orchestrator.pipeline import VerifyConfig, verify_claim

load_dotenv()

_has_keys = bool(
    os.environ.get("BRAVE_WEB_SEARCH_API_KEY")
    and os.environ.get("ANTHROPIC_API_KEY")
)


@pytest.mark.acceptance
@pytest.mark.skipif(not _has_keys, reason="API keys not available")
class TestLiveVerification:

    @pytest.mark.asyncio
    async def test_false_claim_gets_false_verdict(self) -> None:
        """A knowingly false claim should produce a false or mostly-false verdict.

        TreadLightly AI does not exclusively use models trained on 100%
        renewable energy -- no major LLM provider makes that guarantee.
        The pipeline should research this and reach that conclusion.
        """
        from orchestrator.checkpoints import AutoApproveCheckpointHandler

        result = await verify_claim(
            entity_name="TreadLightly AI",
            claim_text=(
                "TreadLightly AI only uses models that were trained "
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
