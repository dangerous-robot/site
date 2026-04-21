"""Host blocklist: drop known-403/paywall URLs before the ingestor spends time on them.

Matching is lowercase, strips a leading ``www.`` from the URL host, and then
performs a suffix match on a dot boundary. This means ``linkedin.com`` matches
``www.linkedin.com`` and ``uk.linkedin.com``, but NOT ``notlinkedin.com``.

Blocklist data lives in ``research/blocklist.yaml`` so operators can edit it
without touching code. A missing file is treated as an empty list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlocklistEntry:
    """One entry from ``research/blocklist.yaml``."""

    host: str
    reason: str


@dataclass(frozen=True)
class FilterDecision:
    """Record of a URL dropped by the blocklist."""

    url: str
    host: str
    reason: str


@lru_cache(maxsize=8)
def _load_blocklist_cached(repo_root_str: str) -> tuple[BlocklistEntry, ...]:
    path = Path(repo_root_str) / "research" / "blocklist.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return ()
    entries: list[BlocklistEntry] = []
    for e in data.get("hosts", []) or []:
        host = e.get("host")
        if not host:
            continue
        entries.append(BlocklistEntry(host=str(host).lower(), reason=e.get("reason", "")))
    return tuple(entries)


def load_blocklist(repo_root: Path) -> list[BlocklistEntry]:
    """Load blocklist entries from ``<repo_root>/research/blocklist.yaml``.

    Returns an empty list if the file does not exist (fresh clones should not crash).
    Cached per repo root so onboarding does not re-parse the YAML for every template.
    """
    return list(_load_blocklist_cached(str(repo_root)))


def _normalised_host(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def _host_matches(url_host: str, blocked_host: str) -> bool:
    return url_host == blocked_host or url_host.endswith("." + blocked_host)


def filter_urls(
    urls: list[str], entries: list[BlocklistEntry]
) -> tuple[list[str], list[FilterDecision]]:
    """Split ``urls`` into (kept, dropped) based on ``entries``.

    Unparseable or hostless URLs pass through untouched (``kept``).
    """
    kept: list[str] = []
    dropped: list[FilterDecision] = []
    for url in urls:
        host = _normalised_host(url)
        if not host:
            kept.append(url)
            continue
        match = next((e for e in entries if _host_matches(host, e.host)), None)
        if match:
            dropped.append(FilterDecision(url=url, host=match.host, reason=match.reason))
            logger.info(
                "Blocklist drop: %s (host=%s, reason=%s)", url, match.host, match.reason
            )
        else:
            kept.append(url)
    return kept, dropped
