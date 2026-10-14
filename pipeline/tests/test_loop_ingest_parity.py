"""The moved ingest path keeps its three checks (RE-AR, One loop, one writer).

Through the public ``loop.ingest_one``: an arXiv paper with a corporate-lab
author is first-party (``arxiv_corporate_lab``), a key quote not on the
requested page is dropped (``drop_unfound_quotes`` over
``requested_page_text``, so text from another page cannot vouch for it),
and a model that never fetched the page is rejected (``fetch_failed``).
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from common.models import Independence
from ingestor.agent import ingestor_agent

_TODAY = datetime.date(2026, 10, 14)
_FIXTURES = Path(__file__).parent / "fixtures"
_CORPORATE_HTML = (_FIXTURES / "arxiv_html_corporate.html").read_text(encoding="utf-8")
_PAGE_URL = "https://example.org/report"
_OTHER_URL = "https://example.org/other"
_ON_PAGE = "data centers used more than 4% of US electricity"
_ELSEWHERE = "a sentence that only the other page carries"
_PAGE_TEXT = f"Report. The {_ON_PAGE} in 2024."
_OTHER_HTML = f"<html><body><p>{_ELSEWHERE}.</p></body></html>"


def _source_args(url: str, **frontmatter) -> dict:
    fm = {
        "url": url,
        "title": "Report",
        "publisher": "Example Publisher",
        "accessed_date": _TODAY.isoformat(),
        "kind": "article",
        "summary": "A factual summary.",
    }
    fm.update(frontmatter)
    return {"frontmatter": fm, "body": "Body.", "slug": "report", "year": 2026}


def _scripted_model(fetch_urls: list[str], source: dict) -> FunctionModel:
    """Call ``web_fetch`` once per URL in order, then return ``source``."""
    step = 0

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        nonlocal step
        if step < len(fetch_urls):
            url = fetch_urls[step]
            step += 1
            return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})])
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])

    return FunctionModel(_fn)


async def _ingest(url: str, model: FunctionModel, tmp_path, *, prefetched: str | None = None):
    from contextlib import nullcontext
    from unittest.mock import patch

    import loop

    cfg = loop.VerifyConfig(model="test", repo_root=str(tmp_path), skip_wayback=True)
    async with httpx.AsyncClient() as client:
        with ingestor_agent.override(model=model):
            with patch.object(ingestor_agent, "override", side_effect=lambda **kw: nullcontext()):
                return await loop.ingest_one(
                    client, url, cfg, _TODAY, asyncio.Semaphore(8), prefetched_body=prefetched,
                )


@pytest.fixture
def _no_arxiv_wait(monkeypatch):
    monkeypatch.setattr("ingestor.arxiv_affiliation.throttle_acquire", AsyncMock())


@pytest.mark.asyncio
async def test_arxiv_corporate_lab_paper_is_first_party(tmp_path, _no_arxiv_wait) -> None:
    url = "https://arxiv.org/html/2508.15734v1"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, html=_CORPORATE_HTML))
        outcome = await _ingest(
            url, _scripted_model([url], _source_args(url, publisher="arXiv", independence="independent")),
            tmp_path,
        )
    assert isinstance(outcome, tuple), outcome
    sf = outcome[1]
    assert sf.frontmatter.publisher == "Google"
    assert sf.frontmatter.independence == Independence.FIRST_PARTY


@pytest.mark.asyncio
async def test_key_quote_not_on_the_requested_page_is_dropped(tmp_path) -> None:
    """The quote lives on another page the model also fetched; only the requested page vouches."""
    with respx.mock:
        respx.get(_OTHER_URL).mock(return_value=httpx.Response(200, html=_OTHER_HTML))
        outcome = await _ingest(
            _PAGE_URL,
            _scripted_model(
                [_PAGE_URL, _OTHER_URL], _source_args(_PAGE_URL, key_quotes=[_ON_PAGE, _ELSEWHERE]),
            ),
            tmp_path,
            prefetched=_PAGE_TEXT,
        )
    assert isinstance(outcome, tuple), outcome
    assert outcome[1].frontmatter.key_quotes == [_ON_PAGE]


@pytest.mark.asyncio
async def test_source_without_a_fetched_page_is_rejected(tmp_path) -> None:
    import loop

    outcome = await _ingest(_PAGE_URL, _scripted_model([], _source_args(_PAGE_URL)), tmp_path)
    assert isinstance(outcome, loop.StepError)
    assert outcome.error_type == "fetch_failed"
