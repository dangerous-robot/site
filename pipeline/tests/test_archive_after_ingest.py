"""Light research keeps only a page summary, so it makes no archive request.

The archive-after-ingest cases of the claim run live in ``test_beta7_pins.py``,
driven through ``loop.run``. This light-research case goes with light research
(``gather_light_research`` in ``orchestrator/pipeline.py``).
"""

from __future__ import annotations

import re

import httpx
import pytest
import respx

from loop import VerifyConfig

_PAGE_URL = "https://example.org/page"
_PAGE = "<html><head><title>Page</title></head><body><p>The stored page.</p></body></html>"
_TIMEGATE = re.compile(r"https://web\.archive\.org/web/\d{14}/.+")
_SAVE = re.compile(r"https://web\.archive\.org/save/.+")


@pytest.mark.asyncio
async def test_light_research_does_not_archive_the_page_it_discards(
    stub_ingest_model, monkeypatch
) -> None:
    """Onboard light research keeps only the summary, so it makes no archive request."""
    import asyncio

    from common.models import EntityType
    from orchestrator.pipeline import gather_light_research

    async def _no_probe(*args, **kwargs):
        return []

    monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)
    cfg = VerifyConfig(model="test", skip_wayback=False, repo_root="/tmp")
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(404))
        save = mock.get(_SAVE).mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient() as client:
            bundle = await gather_light_research(
                "Example", EntityType.COMPANY, cfg, asyncio.Semaphore(2), client,
                seed_url=_PAGE_URL,
            )

    assert bundle.raw_description == "The stored page."
    assert timegate.called is False
    assert save.called is False
