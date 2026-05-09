"""Tests for the arXiv academic-API search wrapper.

Mirrors the Tavily/Brave test layout. Coverage targets the contract laid
out in ``docs/plans/source-pool-expansion-tier1.md`` § Path 2:

* Atom XML success path with version-stripped ``paper_id``.
* Empty Atom feed yields an empty list (``no_results`` clean miss is
  the dispatcher's responsibility, not the tool's).
* ``httpx.ReadTimeout`` propagates so the dispatcher can map it to
  ``StepError(error_type='timeout')``.
* ``5xx`` raises ``HTTPStatusError`` so the dispatcher can map it to
  ``StepError(error_type='http_error')``.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from common import throttle as throttle_mod
from researcher.tools.arxiv import search_arxiv

_ARXIV_URL = "https://export.arxiv.org/api/query"


# Two-entry Atom payload modeled on the actual arXiv response shape.
# - First entry has a ``v2`` version suffix to exercise the strip.
# - Second entry has no version suffix to exercise the no-op branch.
_ATOM_TWO_ENTRIES = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>arXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/2106.04560v2</id>
    <updated>2022-01-15T00:00:00Z</updated>
    <title>Carbon Footprint of Large Language Models</title>
    <summary>
      We study the lifecycle emissions of training and serving
      large language models across cloud providers.
    </summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2410.12345</id>
    <updated>2024-10-01T00:00:00Z</updated>
    <title>Scaling Laws for AI Safety Evaluations</title>
    <summary>This paper proposes a scaling-law framework for evaluation harnesses.</summary>
  </entry>
</feed>
"""


_ATOM_EMPTY = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title>arXiv Query</title>
</feed>
"""


@pytest.fixture(autouse=True)
def _reset_throttle():
    """Drop the module-level arxiv bucket between tests so timing-sensitive
    asserts don't depend on previous-test token state."""
    yield
    throttle_mod.reset("arxiv")


class TestArxivSuccess:
    @pytest.mark.asyncio
    async def test_returns_two_candidates_with_paper_id(self) -> None:
        """The wrapper returns one dict per ``<entry>`` with ``paper_id``
        derived from the canonical arXiv id (version suffix stripped)."""
        with respx.mock:
            respx.get(_ARXIV_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=_ATOM_TWO_ENTRIES,
                    headers={"content-type": "application/atom+xml"},
                ),
            )
            async with httpx.AsyncClient() as client:
                results = await search_arxiv(client, "carbon footprint LLM")

        assert len(results) == 2

        first = results[0]
        assert first["url"] == "http://arxiv.org/abs/2106.04560v2"
        assert first["paper_id"] == "2106.04560"  # vN suffix stripped
        assert first["title"] == "Carbon Footprint of Large Language Models"
        # Whitespace-collapsed summary so YAML serialization downstream
        # doesn't carry significant indentation from the Atom payload.
        assert "lifecycle emissions" in first["snippet"]
        assert first["raw_content"] is None

        second = results[1]
        assert second["paper_id"] == "2410.12345"  # no suffix to strip
        assert second["title"] == "Scaling Laws for AI Safety Evaluations"

    @pytest.mark.asyncio
    async def test_query_sent_in_search_query_param(self) -> None:
        """The query rides in the ``search_query`` URL param, not the body."""
        with respx.mock:
            route = respx.get(_ARXIV_URL).mock(
                return_value=httpx.Response(200, text=_ATOM_EMPTY),
            )
            async with httpx.AsyncClient() as client:
                await search_arxiv(client, "ai safety scaling")
        sent = route.calls.last.request
        # respx matches by base URL; query string is on the request URL.
        assert sent.url.params["search_query"] == "ai safety scaling"
        assert sent.url.params["max_results"] == "10"

    @pytest.mark.asyncio
    async def test_empty_feed_returns_empty_list(self) -> None:
        """Zero ``<entry>`` elements yields ``[]`` (the dispatcher records
        the per-tool ``no_results`` outcome, not the tool itself)."""
        with respx.mock:
            respx.get(_ARXIV_URL).mock(
                return_value=httpx.Response(200, text=_ATOM_EMPTY),
            )
            async with httpx.AsyncClient() as client:
                results = await search_arxiv(client, "obscure query")
        assert results == []


class TestArxivFailures:
    @pytest.mark.asyncio
    async def test_timeout_propagates(self) -> None:
        """``httpx.ReadTimeout`` is not swallowed; the dispatcher maps it
        to ``StepError(error_type='timeout')``."""
        with respx.mock:
            respx.get(_ARXIV_URL).mock(
                side_effect=httpx.ReadTimeout("simulated timeout"),
            )
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.ReadTimeout):
                    await search_arxiv(client, "q")

    @pytest.mark.asyncio
    async def test_503_raises_http_status_error(self) -> None:
        """5xx response raises ``HTTPStatusError`` (via
        ``raise_for_status``) so the dispatcher maps it to
        ``StepError(error_type='http_error')``."""
        with respx.mock:
            respx.get(_ARXIV_URL).mock(
                return_value=httpx.Response(503, text="service unavailable"),
            )
            async with httpx.AsyncClient() as client:
                with pytest.raises(httpx.HTTPStatusError):
                    await search_arxiv(client, "q")
