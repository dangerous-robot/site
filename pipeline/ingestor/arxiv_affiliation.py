"""Find a corporate AI lab in an arXiv paper's author block.

The abstract page arXiv serves carries no affiliations, so an ingest of
``arxiv.org/abs/<id>`` labels a lab's own paper as independent work
published by "arXiv". The HTML render lists each author's affiliation and
email; this module reads them in code, outside the ingest model.
"""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from common.canonical_url import canonical_key
from common.source_classification import corporate_lab_publisher
from common.throttle import acquire as throttle_acquire
from common.throttle import register as throttle_register
from common.timeouts import HTTP_READ_S
# Same bucket as the arXiv search tool; register() raises on mismatched params.
from researcher.tools.arxiv import _ARXIV_BURST, _ARXIV_RATE_PER_SEC

logger = logging.getLogger(__name__)

_ABS_PREFIX = "https://arxiv.org/abs/"
# Footnotes and thanks ("Work done during an internship at Google") are not
# affiliations.
_NOT_AFFILIATION = ".ltx_note, .ltx_role_footnote, .ltx_role_thanks"


def _html_url(requested_url: str) -> str | None:
    """The HTML render for an arXiv paper URL, keeping its version; else None."""
    key = canonical_key(requested_url)
    if not key.startswith(_ABS_PREFIX):
        return None
    paper_id = key.removeprefix(_ABS_PREFIX)
    version = re.search(rf"/{re.escape(paper_id)}(v\d+)", requested_url)
    return f"https://arxiv.org/html/{paper_id}{version.group(1) if version else ''}"


def author_block_lab(html: str) -> str | None:
    """The corporate lab named in a LaTeXML render's ``.ltx_authors`` block, or None."""
    soup = BeautifulSoup(html, "html.parser")
    texts: list[str] = []
    for block in soup.select(".ltx_authors"):
        for note in block.select(_NOT_AFFILIATION):
            note.decompose()
        texts.append(block.get_text(" "))
    return corporate_lab_publisher(" ".join(texts)) if texts else None


async def arxiv_corporate_lab(client: httpx.AsyncClient, requested_url: str) -> str | None:
    """The corporate lab among an arXiv paper's authors, or None.

    None for a URL that is not an arXiv paper, a paper with no HTML render
    (older papers), or any fetch failure: the lookup never fails an ingest.
    """
    html_url = _html_url(requested_url)
    if html_url is None:
        return None
    try:
        throttle_register("arxiv", rate_per_sec=_ARXIV_RATE_PER_SEC, burst=_ARXIV_BURST)
        await throttle_acquire("arxiv")
        resp = await client.get(html_url, follow_redirects=True, timeout=HTTP_READ_S)
        if resp.status_code != 200:
            logger.info("arXiv author lookup: %s returned HTTP %d", html_url, resp.status_code)
            return None
        lab = author_block_lab(resp.text)
    except Exception as exc:
        logger.info("arXiv author lookup failed for %s: %s", html_url, exc)
        return None
    if lab:
        logger.info("arXiv author lookup: %s lists a %s author", html_url, lab)
    return lab
