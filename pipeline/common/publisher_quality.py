"""Pre-ingest publisher quality classification based on URL hostname."""
from __future__ import annotations

from common.blocklist import _host_matches, _normalised_host
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
    hostname = _normalised_host(url)
    if not hostname:
        return "secondary"

    if any(_host_matches(hostname, domain) for domain in _FORUM_DOMAINS):
        return "forum"

    if any(term in hostname for term in _PRIMARY_PUBLISHERS):
        return "primary"
    if any(term in hostname for term in _SECONDARY_PUBLISHERS):
        return "secondary"
    if any(term in hostname for term in _TERTIARY_PUBLISHERS):
        return "tertiary"
    return "secondary"
