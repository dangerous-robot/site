"""Classify a source as primary, secondary, or tertiary based on publisher and kind.

Shared utility used by both `_write_source_files()` (called from `research_claim`
and `onboard_entity`) and the standalone `dr ingest` write path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from common.utils import host_matches, url_host

# Publisher substrings (lowercase) that identify primary sources.
# Matched against publisher.lower(), order doesn't matter here.
_PRIMARY_PUBLISHERS: frozenset[str] = frozenset(
    {
        "anthropic",
        "openai",
        "google",
        "microsoft",
        "meta",
        "ecosia",
        "greenpt",
        "chattree",
        "infomaniak",
        "tracklight",
        "transparently",
        "edgar",
    }
)

# Publisher substrings (lowercase) that strongly imply secondary sources.
_SECONDARY_PUBLISHERS: frozenset[str] = frozenset(
    {
        "arxiv",
        "ieee",
        "university",
        "journal",
        "b lab",
        "b corp",
        "ditchcarbon",
        "sacra",
        "crunchbase",
        "unesco",
        "ntia",
        "unfccc",
        "oecd",
    }
)

# Publisher substrings (lowercase) that imply tertiary sources.
_TERTIARY_PUBLISHERS: frozenset[str] = frozenset(
    {
        "future of life",
        "earth day",
        "center for ai safety",
        "nerdwallet",
        "zenbusiness",
        "substack",
    }
)

# SourceKind values that are intrinsically tertiary when publisher is unknown.
_TERTIARY_KINDS: frozenset[str] = frozenset({"blog"})


def classify_source_type(publisher: str, kind: str) -> str:
    """Return 'primary', 'secondary', or 'tertiary' for a source.

    Rules (evaluated in order, first match wins):
    1. publisher matches a known AI-company or regulatory-filing term -> primary
    2. kind is 'documentation' -> primary (company docs are first-party)
    3. publisher matches a known secondary-source term -> secondary
    4. publisher matches a known tertiary-source term -> tertiary
    5. kind is 'blog' -> tertiary
    6. everything else -> secondary (safer default)
    """
    pub_lower = publisher.lower()
    kind_lower = kind.lower()

    # sec.gov as a substring avoids matching "section", "secretary", etc.
    if "sec.gov" in pub_lower or any(term in pub_lower for term in _PRIMARY_PUBLISHERS):
        return "primary"

    if kind_lower == "documentation":
        return "primary"

    if any(term in pub_lower for term in _SECONDARY_PUBLISHERS):
        return "secondary"

    if any(term in pub_lower for term in _TERTIARY_PUBLISHERS):
        return "tertiary"

    if kind_lower in _TERTIARY_KINDS:
        return "tertiary"

    return "secondary"


_INDEPENDENCE_BY_SOURCE_TYPE: dict[str, str] = {
    "primary": "first-party",
    "secondary": "independent",
    "tertiary": "unknown",
}


def independence_for_source_type(source_type: str) -> str:
    """Map `source_type` to `independence` per the v1 proxy.

    See docs/architecture/source-quality.md § The `independence` field.
    """
    return _INDEPENDENCE_BY_SOURCE_TYPE.get(source_type, "unknown")


# --- Entity match: the claim entity's own pages are first-party -------------

_COMPANY_SUFFIXES: frozenset[str] = frozenset({"inc", "llc", "ltd"})


def _normalize_name(name: str) -> str:
    """Lowercase, drop punctuation, and strip trailing inc/llc/ltd tokens."""
    words = re.sub(r"[^\w\s]", " ", name.lower()).split()
    while words and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


@dataclass(frozen=True)
class EntityIdentity:
    """Normalized names and website hosts of a claim's entity and its parent."""

    names: frozenset[str]
    hosts: frozenset[str]

    @classmethod
    def from_parts(
        cls, names: Iterable[str | None], websites: Iterable[str | None]
    ) -> "EntityIdentity":
        return cls(
            names=frozenset(n for n in (_normalize_name(x or "") for x in names) if n),
            hosts=frozenset(h for h in (url_host(w) for w in websites) if h),
        )


def entity_first_party_reason(
    publisher: str, url: str, identity: EntityIdentity
) -> str | None:
    """Return why a source is first-party for the entity, or None.

    Host: the URL host equals or is a subdomain of an entity website host.
    Publisher: the normalized publisher equals an entity name, legal name or
    alias. Equality, not substring: "meta" must not match "Metacritic".
    """
    host = url_host(url)
    for entity_host in sorted(identity.hosts):
        if host_matches(host, entity_host):
            return f"URL host {host} is the entity's website ({entity_host})"
    if _normalize_name(publisher) in identity.names:
        return f"Publisher {publisher!r} is the entity or its parent company"
    return None
