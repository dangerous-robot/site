"""General-purpose utilities shared across pipeline packages."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def slugify(text: str) -> str:
    """Convert text to a kebab-case slug (deterministic, no LLM)."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")


def slug_from_url(url: str) -> str | None:
    """Derive a slug from the last non-empty path segment of a URL.

    Returns None for root-only URLs so callers can fall back to an
    LLM-generated slug.
    """
    path = urlparse(url).path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if "/" in path else path
    if not segment:
        return None
    return slugify(segment)


def url_host(url: str | None) -> str:
    """Lowercase URL host without a leading ``www.``.

    Returns "" when the URL is empty, has no host, or does not parse.
    """
    if not url:
        return ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host.removeprefix("www.")


def host_matches(host: str, domain: str) -> bool:
    """True when ``host`` is ``domain`` or a subdomain of it (dot boundary)."""
    return host == domain or host.endswith("." + domain)


def host_token(url: str) -> str:
    """Slug-safe host prefix used to disambiguate colliding source slugs.

    Drops ``www.`` and the last label: ``aws.amazon.com`` gives
    ``aws-amazon``, ``brave.com`` gives ``brave``. Returns "" when the URL
    has no host.
    """
    labels = [label for label in url_host(url).split(".") if label]
    if len(labels) > 1:
        labels = labels[:-1]
    return slugify("-".join(labels))
