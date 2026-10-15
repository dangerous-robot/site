"""Classify a source as primary, secondary, or tertiary based on publisher and kind.

Shared utility used by both `_write_source_files()` (called from the writer's
`persist_sources`) and the standalone `dr ingest` write path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

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

# Press-wire services: (lowercase publisher word or phrase, origin key). A release
# syndicated through one ("Yahoo Finance (via ACCESS Newswire)") is the
# issuing organization's own statement. First row that matches wins, so the
# bare "newswire" comes last.
NEWSWIRE_ORIGINS: tuple[tuple[str, str], ...] = (
    ("pr newswire", "prnewswire"),
    ("prnewswire", "prnewswire"),
    ("business wire", "businesswire"),
    ("businesswire", "businesswire"),
    ("globenewswire", "globenewswire"),
    ("globe newswire", "globenewswire"),
    ("access newswire", "accesswire"),
    ("accesswire", "accesswire"),
    ("ein presswire", "einpresswire"),
    ("einpresswire", "einpresswire"),
    ("prweb", "prweb"),
    ("marketwired", "marketwired"),
    ("newsfile", "newsfile"),
    ("cision", "cision"),
    ("newswire", "newswire"),
)


# Whole words only: a bare substring test made "Decision Lab" and "Precision
# Medicine Weekly" press wires (by "cision") and so first-party. The bare
# "newswire" keeps substring matching: no ordinary word contains it, and a
# run-together name ("AsiaNewswire") is still a press wire.
_NEWSWIRE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(re.escape(term) if term == "newswire" else rf"\b{re.escape(term)}\b"), origin)
    for term, origin in NEWSWIRE_ORIGINS
)


def newswire_origin(publisher: str) -> str | None:
    """The press-wire service a publisher names (``NEWSWIRE_ORIGINS``, whole words), or None."""
    pub_lower = (publisher or "").lower()
    return next((origin for pattern, origin in _NEWSWIRE_PATTERNS if pattern.search(pub_lower)), None)


def is_newswire(publisher: str) -> bool:
    """True when the publisher names a press-wire service."""
    return newswire_origin(publisher) is not None


def classify_source_type(publisher: str, kind: str) -> str:
    """Return 'primary', 'secondary', or 'tertiary' for a source.

    Rules (evaluated in order, first match wins):
    1. publisher matches a known AI-company or regulatory-filing term -> primary
    1b. publisher names a press-wire service (``is_newswire``) -> primary
       (a syndicated release is its issuer's own statement)
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

    if is_newswire(publisher):
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


# Platforms where one host serves many organizations' own accounts, so the
# account handle in the path, not the host, says whose statement a page is.
PROFILE_PLATFORMS: frozenset[str] = frozenset(
    {"linkedin.com", "x.com", "twitter.com", "facebook.com", "instagram.com", "youtube.com"}
)
# Hosts that serve the entity and any same-name organization alike, so a
# whole-host exclude would drop the entity's own pages too.
SHARED_PLATFORM_HOSTS: frozenset[str] = PROFILE_PLATFORMS | {
    "apps.apple.com", "play.google.com", "github.com",
}
_LINKEDIN_ACCOUNT_KINDS = frozenset({"company", "in", "showcase"})
_YOUTUBE_ACCOUNT_KINDS = frozenset({"c", "user"})


def _profile_platform(host: str) -> str | None:
    return next((p for p in sorted(PROFILE_PLATFORMS) if host_matches(host, p)), None)


def _profile_handle(platform: str, path: str) -> str | None:
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    if platform == "linkedin.com":
        if len(parts) >= 2 and parts[0] in _LINKEDIN_ACCOUNT_KINDS:
            return parts[1]
        if len(parts) >= 2 and parts[0] == "posts":
            # /posts/<handle>_<post slug>
            return parts[1].split("_", 1)[0]
        return None
    if platform == "youtube.com":
        if parts[0].startswith("@"):
            return parts[0]
        if len(parts) >= 2 and parts[0] in _YOUTUBE_ACCOUNT_KINDS:
            return parts[1]
        return None
    return parts[0]


def _handle_variants(name: str) -> set[str]:
    words = name.split()
    return {"-".join(words), "_".join(words), "".join(words)}


def profile_url_names_entity(url: str, identity: EntityIdentity) -> bool:
    """True when ``url`` is on a profile platform and its account handle is the entity's.

    The handle must equal an entity name with its words joined by ``-``, ``_``
    or nothing. Never true off ``PROFILE_PLATFORMS``.
    """
    host = url_host(url)
    platform = _profile_platform(host)
    if platform is None:
        return False
    try:
        path = urlparse(url).path
    except ValueError:
        return False
    handle = _profile_handle(platform, path)
    if not handle:
        return False
    handle = handle.lower().removeprefix("@")
    return any(handle in _handle_variants(name) for name in identity.names)


def entity_first_party_reason(
    publisher: str, url: str, identity: EntityIdentity
) -> str | None:
    """Return why a source is first-party for the entity, or None.

    Host: the URL host equals or is a subdomain of an entity website host.
    Profile: the URL is the entity's own account on a profile platform
    (``profile_url_names_entity``), whose publisher is usually the platform.
    Publisher: the normalized publisher equals an entity name, legal name or
    alias. Equality, not substring: "meta" must not match "Metacritic".
    """
    host = url_host(url)
    for entity_host in sorted(identity.hosts):
        if host_matches(host, entity_host):
            return f"URL host {host} is the entity's website ({entity_host})"
    if profile_url_names_entity(url, identity):
        return f"URL is the entity's own {_profile_platform(host)} account"
    if _normalize_name(publisher) in identity.names:
        return f"Publisher {publisher!r} is the entity or its parent company"
    return None


# --- Off-entity sources ------------------------------------------------------


def _padded_words(text: str) -> str:
    # Space-padded so a phrase test with surrounding spaces is a whole-word match.
    return " " + " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split()) + " "


def _names_entity(padded_words: str, identity: EntityIdentity) -> bool:
    return any(f" {name} " in padded_words for name in identity.names)


def publisher_named_in_claim(publisher: str, claim_text: str) -> bool:
    """True when the normalized publisher appears as whole words in the claim text.

    The claim may name a provider the entity relies on ("Euria is hosted on
    renewable energy by Infomaniak"); that provider's own pages are evidence.
    """
    name = _normalize_name(publisher)
    return bool(name) and f" {name} " in _padded_words(claim_text)


def source_engages_entity(sd: Mapping, identity: EntityIdentity) -> bool:
    """True when a source's text names the entity or one of its website hosts.

    Reads the ingested title, summary, key quotes and body. Names match as
    whole words ("ChatGPT" does not name "ChatGPTree"); hosts match on the
    raw text, where normalizing would split "brave.com" in two.
    """
    parts = [sd.get("title"), sd.get("summary"), *(sd.get("key_quotes") or []), sd.get("body")]
    raw = " ".join(p for p in parts if isinstance(p, str)).lower()
    if _names_entity(_padded_words(raw), identity):
        return True
    # A "." may precede the host, so "www.brave.com" and "search.brave.com"
    # count; a letter or "-" may not, so "notbrave.com" does not.
    return any(
        re.search(rf"(?<![\w-]){re.escape(host)}(?![\w-])", raw) for host in identity.hosts
    )


# Second-level labels under a two-letter country code ("bbc.co.uk").
_COUNTRY_SECOND_LEVEL: frozenset[str] = frozenset({"ac", "co", "com", "edu", "gov", "net", "org"})
# Hosts where many organizations' sites share one registrable label, so an
# entity website there says nothing about the platform's other pages.
_SHARED_SITE_HOSTS: frozenset[str] = SHARED_PLATFORM_HOSTS | {
    "github.io", "medium.com", "netlify.app", "notion.site", "pages.dev",
    "sites.google.com", "substack.com", "vercel.app", "wixsite.com",
}


def _brand_label(host: str) -> str:
    """The registrable label of a host: ``claude`` for platform.claude.com and claude.ai."""
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return ""
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _COUNTRY_SECOND_LEVEL:
        return labels[-3]
    return labels[-2]


def entity_affiliated(publisher: str, url: str, identity: EntityIdentity) -> bool:
    """True when a source looks published by the entity or its parent under another name or host.

    The publisher names the entity or parent as whole words ("Anthropic
    (Claude Platform)" for Claude), or the URL's registrable label equals
    that of an entity website host (platform.claude.com for claude.ai,
    ai.google.dev for gemini.google.com). Looser than
    ``entity_first_party_reason``, so it only keeps a label, never sets one.
    """
    if _names_entity(_padded_words(publisher), identity):
        return True
    label = _brand_label(url_host(url))
    return bool(label) and any(
        label == _brand_label(h)
        for h in identity.hosts
        if not any(host_matches(h, shared) for shared in _SHARED_SITE_HOSTS)
    )


def effective_independence(
    source_ids: Iterable[str],
    file_labels: Mapping[str, str | None],
    overrides: Mapping[str, str | None],
) -> list[tuple[str, str | None]]:
    """Each source ref's independence on one claim: its override when set, else its own label.

    The one counting rule for the lint check and the write-time level fit,
    matching ``countSourcesByIndependence`` in ``src/lib/sourceQuality.ts``:
    one entry per ref, so a repeated ref counts each time, as on the site.
    """
    return [
        (sid, overrides.get(sid) or file_labels.get(sid))
        for sid in source_ids
    ]


# --- Corporate labs named in a paper's author block --------------------------

# (pattern, publisher, case-sensitive). Every publisher here is also in
# _PRIMARY_PUBLISHERS, so a relabelled paper classifies as primary.
_CORPORATE_LAB_PATTERNS: tuple[tuple[str, str, bool], ...] = (
    (r"\bGoogle Research\b", "Google", False),
    (r"\bGoogle DeepMind\b", "Google", False),
    (r"\bDeepMind\b", "Google", False),
    (r"\bGoogle\b", "Google", False),
    (r"@google\.com\b", "Google", False),
    (r"@deepmind\.com\b", "Google", False),
    (r"\bAnthropic\b", "Anthropic", False),
    (r"@anthropic\.com\b", "Anthropic", False),
    (r"\bOpenAI\b", "OpenAI", False),
    (r"@openai\.com\b", "OpenAI", False),
    (r"\bMeta AI\b", "Meta", False),
    # Uppercase only: "fair" is an ordinary word.
    (r"\bFAIR\b", "Meta", True),
    (r"\bMeta Platforms\b", "Meta", False),
    (r"@meta\.com\b", "Meta", False),
    (r"@fb\.com\b", "Meta", False),
    (r"\bMicrosoft Research\b", "Microsoft", False),
    (r"@microsoft\.com\b", "Microsoft", False),
)


# (pattern, case-sensitive). An academic affiliation named before any lab
# makes the paper academic work with industry co-authors, not a lab's own.
_ACADEMIC_AFFILIATION_PATTERNS: tuple[tuple[str, bool], ...] = (
    (r"\bUniv\w*", False),
    (r"\bInstitut\w*", False),
    (r"\bCollege\b", False),
    (r"\bSchool of\b", False),
    (r"\bAcademy of\b", False),
    (r"\bPolytechnic\b", False),
    (r"\bPolitecnico\b", False),
    (r"\b(?:MIT|ETH|EPFL|CNRS|Inria|INRIA|KAIST)\b", True),
    (r"@[\w.-]+\.edu\b", False),
    (r"@[\w.-]+\.ac\.[a-z]{2}\b", False),
)


def _earliest(patterns: Iterable[tuple[str, bool]], text: str) -> int | None:
    starts = [
        m.start()
        for pattern, case_sensitive in patterns
        if (m := re.search(pattern, text, 0 if case_sensitive else re.IGNORECASE))
    ]
    return min(starts, default=None)


def corporate_lab_publisher(author_text: str) -> str | None:
    """The corporate AI lab that is the first affiliation in ``author_text``, or None.

    ``author_text`` is a paper's author block (names, affiliations, emails)
    in author order. A paper whose first affiliation is academic is that
    group's work even with a lab co-author, so it gets None: as a lab's
    paper it would be first-party for the lab, and off-entity on every
    other entity's claim.
    """
    best: tuple[int, str] | None = None
    for pattern, publisher, case_sensitive in _CORPORATE_LAB_PATTERNS:
        match = re.search(pattern, author_text, 0 if case_sensitive else re.IGNORECASE)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), publisher)
    if best is None:
        return None
    academic = _earliest(_ACADEMIC_AFFILIATION_PATTERNS, author_text)
    return None if academic is not None and academic < best[0] else best[1]
