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


def host_token(url: str) -> str:
    """Slug-safe host prefix used to disambiguate colliding source slugs.

    Drops ``www.`` and the last label: ``aws.amazon.com`` gives
    ``aws-amazon``, ``brave.com`` gives ``brave``. Returns "" when the URL
    has no host.
    """
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    labels = [label for label in host.split(".") if label]
    if len(labels) > 1:
        labels = labels[:-1]
    return slugify("-".join(labels))
