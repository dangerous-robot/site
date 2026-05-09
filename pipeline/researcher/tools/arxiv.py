"""arXiv academic-API search wrapper used by the decomposed researcher.

Unauthenticated GET against ``https://export.arxiv.org/api/query``,
Atom XML parsed via stdlib ``xml.etree.ElementTree``. Throttle: one
request per three seconds per arXiv API guidelines. Failures propagate
to the caller; ``researcher/decomposed.py`` classifies them.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import httpx

from common.throttle import acquire as throttle_acquire
from common.throttle import register as throttle_register
from common.timeouts import HTTP_READ_S

logger = logging.getLogger(__name__)

_ARXIV_QUERY_URL = "https://export.arxiv.org/api/query"

# arXiv API guideline: no more than one request every three seconds.
# burst=1 keeps a single immediate acquire after an idle window.
_ARXIV_RATE_PER_SEC = 1 / 3.0
_ARXIV_BURST = 1.0

# Atom 1.0 + arXiv-specific namespaces. Element lookups use the
# Clark-notation key ({ns}localname).
_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# arXiv ``<id>`` URLs end in ``vN``; strip to the stable paper id.
_VERSION_SUFFIX_RE = re.compile(r"v\d+$")


# ``register`` is idempotent for matching params (see throttle.py); calling
# it at import covers the first concurrent acquire before any test reset.
throttle_register("arxiv", rate_per_sec=_ARXIV_RATE_PER_SEC, burst=_ARXIV_BURST)


def _strip_version(arxiv_id: str) -> str:
    return _VERSION_SUFFIX_RE.sub("", arxiv_id)


def _parse_atom_entries(body: str) -> list[dict]:
    """Parse arXiv's Atom response into ``{url, title, snippet, paper_id}`` dicts.

    Whitespace-collapses title/summary (arXiv abstracts include
    significant newline runs). Returns ``[]`` for an empty feed;
    malformed XML raises ``ET.ParseError`` for the dispatcher to
    classify as a transport-class failure.
    """
    root = ET.fromstring(body)
    entries: list[dict] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        id_el = entry.find("atom:id", _ATOM_NS)
        if id_el is None or not (id_el.text or "").strip():
            continue
        raw_id = id_el.text.strip()
        url = raw_id
        slug = raw_id.rsplit("/", 1)[-1]
        paper_id = _strip_version(slug)

        title_el = entry.find("atom:title", _ATOM_NS)
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""

        summary_el = entry.find("atom:summary", _ATOM_NS)
        snippet = " ".join((summary_el.text or "").split()) if summary_el is not None else ""

        entries.append(
            {
                "url": url,
                "title": title,
                "snippet": snippet,
                "paper_id": paper_id,
                "raw_content": None,
            }
        )
    return entries


async def search_arxiv(
    client: httpx.AsyncClient, query: str, max_results: int = 10
) -> list[dict]:
    """Search arXiv; return ``{url, title, snippet, paper_id, raw_content}`` dicts.

    Transport failures propagate; the dispatcher in ``decomposed.py``
    classifies them. No fallback to another origin.
    """
    logger.info("arXiv search: %s", query)

    # Re-register defensively: tests that ``reset()`` the throttle between
    # cases need the bucket back before ``acquire`` raises KeyError.
    throttle_register("arxiv", rate_per_sec=_ARXIV_RATE_PER_SEC, burst=_ARXIV_BURST)

    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
    }
    headers = {"Accept": "application/atom+xml"}

    await throttle_acquire("arxiv")
    resp = await client.get(
        _ARXIV_QUERY_URL,
        params=params,
        headers=headers,
        timeout=HTTP_READ_S,
    )
    resp.raise_for_status()

    return _parse_atom_entries(resp.text)
