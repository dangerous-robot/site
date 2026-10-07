"""Canonical URL form for dedup-as-equivalence.

Two URLs that should be treated as the same resource produce the same
canonical string. The result is itself a valid URL and ``canonicalize``
is idempotent.

Non-obvious choices: ``http`` and ``https`` stay distinct (security
origins differ); ``www.`` is stripped from the host but punycode/IDN
hosts are left alone; default ports are stripped; paths are NOT
lowercased (many servers are case-sensitive); fragments are dropped;
percent-encoding is preserved as-is to avoid double-encoding.

Malformed input raises ``ValueError`` -- silent fallthrough would make
dedup unreliable.

``canonical_key`` adds one rule on top for lookup keys: every form of
one arXiv paper (abs, html or pdf page, any version, ``http`` or
``https``, ``export.arxiv.org``) keys as ``https://arxiv.org/abs/{id}``.
This is the one exception to keeping ``http`` and ``https`` apart.
``canonicalize`` and ``same_resource`` stay page-exact, because the abs
page carries only the abstract and is not the same text as the paper.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Tracking params to drop (matched case-insensitively on the key).
TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "ref",
    "ref_src",
})

_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


def canonicalize(url: str) -> str:
    """Return a deterministic canonical form of ``url`` for dedup.

    Two URLs that should be treated as the same resource produce the
    same string. The result is itself a valid URL; ``canonicalize`` is
    idempotent.

    Raises:
        ValueError: when ``url`` is empty, not a string, missing a
            scheme, missing a host, or otherwise unparseable.
    """
    if not isinstance(url, str):
        raise ValueError(f"canonicalize expects a str, got {type(url).__name__}")
    stripped = url.strip()
    if not stripped:
        raise ValueError("canonicalize received an empty URL")

    try:
        parts = urlsplit(stripped)
    except ValueError as exc:
        raise ValueError(f"unparseable URL: {url!r} ({exc})") from exc

    scheme = parts.scheme.lower()
    if not scheme:
        raise ValueError(f"URL missing scheme: {url!r}")

    # urlsplit's hostname accessor lowercases for us; netloc does not.
    host = parts.hostname
    if not host:
        raise ValueError(f"URL missing host: {url!r}")
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
        if not host:
            raise ValueError(f"URL host is only 'www.': {url!r}")

    # Port: strip defaults; preserve non-defaults.
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"invalid port in URL {url!r}: {exc}") from exc
    if port is not None and _DEFAULT_PORTS.get(scheme) == port:
        port = None

    # Userinfo (user[:password]) -- preserve if present.
    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo = f"{userinfo}:{parts.password}"
        userinfo = f"{userinfo}@"

    netloc = f"{userinfo}{host}"
    if port is not None:
        netloc = f"{netloc}:{port}"

    path = _normalize_path(parts.path)
    query = _normalize_query(parts.query)
    fragment = ""  # always dropped

    return urlunsplit((scheme, netloc, path, query, fragment))


def _normalize_path(path: str) -> str:
    """Resolve ``.`` and ``..`` segments; strip trailing slash unless root.

    The empty path (``""``) is normalised to ``"/"`` so that
    ``https://a.com`` and ``https://a.com/`` canonicalise to the same
    string. This is the practical equivalence most callers want.
    """
    if not path:
        return "/"

    # Resolve "." and ".." path segments while preserving leading "/".
    leading_slash = path.startswith("/")
    trailing_slash = path.endswith("/") and len(path) > 1
    segments = [s for s in path.split("/") if s not in ("", ".")]
    resolved: list[str] = []
    for seg in segments:
        if seg == "..":
            if resolved:
                resolved.pop()
            # If we go above root, silently clamp (don't escape origin).
            continue
        resolved.append(seg)

    rebuilt = "/".join(resolved)
    if leading_slash:
        rebuilt = "/" + rebuilt
    if trailing_slash and rebuilt and not rebuilt.endswith("/"):
        rebuilt += "/"

    if rebuilt == "":
        return "/"
    # Strip trailing slash unless path is exactly "/".
    if len(rebuilt) > 1 and rebuilt.endswith("/"):
        rebuilt = rebuilt[:-1]
    return rebuilt


def _normalize_query(query: str) -> str:
    """Drop tracking params (case-insensitive on key); sort remaining keys.

    Uses ``keep_blank_values=True`` so ``?a=`` is preserved. Duplicate
    keys retain their original relative order via stable sort on key.
    """
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if k.lower() not in TRACKING_PARAMS]
    if not kept:
        return ""
    # Stable sort by key; duplicate-key value order is preserved.
    kept.sort(key=lambda kv: kv[0])
    return urlencode(kept, doseq=False)


_ARXIV_HOSTS = frozenset({"arxiv.org", "export.arxiv.org"})
# New-style ids (2502.12447) or old-style archive/number ids (hep-th/9901001,
# math.AG/0601001), then an optional version, ".pdf" or trailing path.
_ARXIV_PAPER_PATH = re.compile(
    r"/(?:abs|html|pdf)/"
    r"(?P<id>\d{4}\.\d{4,5}|[a-z][a-z-]*(?:\.[A-Za-z]{2})?/\d{7})"
    r"(?:v\d+)?(?:\.pdf)?(?:/.*)?"
)


def canonical_key(url: str) -> str:
    """Canonical form for use as a lookup key; malformed URLs key as themselves.

    Every form of one arXiv paper keys as ``https://arxiv.org/abs/{id}``
    (no version, query or fragment), so the dedup indexes treat them as one
    source while the stored file keeps the URL it was ingested from.
    """
    try:
        canonical = canonicalize(url)
    except ValueError:
        return url.strip()
    parts = urlsplit(canonical)
    if parts.hostname in _ARXIV_HOSTS and parts.port is None:
        paper = _ARXIV_PAPER_PATH.fullmatch(parts.path)
        if paper:
            return f"https://arxiv.org/abs/{paper.group('id')}"
    return canonical


def same_resource(a: str | None, b: str | None) -> bool:
    """True when two URLs canonicalize equal; missing or malformed URLs never match."""
    if not a or not b:
        return False
    try:
        return canonicalize(a) == canonicalize(b)
    except ValueError:
        return False
