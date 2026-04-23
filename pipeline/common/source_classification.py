"""Classify a source as primary, secondary, or tertiary based on publisher and kind.

Shared utility used by both `_write_source_files()` (called from `research_claim`
and `onboard_entity`) and the standalone `dr ingest` write path.
"""

from __future__ import annotations

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
