"""Pre-ingest publisher quality classification based on URL hostname."""
from __future__ import annotations

from urllib.parse import urlparse

from common.source_classification import (
    _PRIMARY_PUBLISHERS,
    _SECONDARY_PUBLISHERS,
    _TERTIARY_PUBLISHERS,
)

_FORUM_DOMAINS: frozenset[str] = frozenset({
    "reddit.com",
    "quora.com",
    "news.ycombinator.com",
    "stackexchange.com",
    "stackoverflow.com",
})


def classify_url_publisher_quality(url: str) -> str:
    """Return 'primary', 'secondary', 'tertiary', or 'forum' for a URL's hostname.

    Less accurate than post-ingest classify_source_type (no kind signal),
    but sufficient as a scoring hint.
    """
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return "secondary"
    hostname = hostname.lower().removeprefix("www.")

    # Forum check first (exact match or subdomain)
    for domain in _FORUM_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return "forum"

    if any(term in hostname for term in _PRIMARY_PUBLISHERS):
        return "primary"
    if any(term in hostname for term in _SECONDARY_PUBLISHERS):
        return "secondary"
    if any(term in hostname for term in _TERTIARY_PUBLISHERS):
        return "tertiary"
    return "secondary"
