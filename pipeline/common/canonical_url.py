"""Canonical URL form for dedup-as-equivalence.

Shared infrastructure for the source-pool-expansion-tier1 plan: the
researcher will gain new candidate-source paths (Brave, OpenAlex,
arXiv, SEC, ...) that all need to feed into a single deduplication
key. ``canonicalize`` produces that key.

Design choices (deliberate; see docstring on each rule):

* ``http`` and ``https`` are treated as distinct schemes. They are
  distinct origins for security; many sites differ between them.
* ``www.`` is stripped from the host. The dedup goal is equivalence,
  not fetching, and ``www`` vs apex is the most common avoidable
  duplicate. Punycode/IDN hosts are left alone.
* Default ports (``:80`` for http, ``:443`` for https) are stripped.
  Non-default ports are preserved.
* Paths are NOT lowercased -- many servers are case-sensitive.
  Trailing slashes are stripped except on the root path.
* A small set of tracking query parameters is dropped (case-insensitive
  on keys). Remaining query keys are sorted alphabetically; duplicate
  keys preserve their value order.
* Fragments are dropped entirely (client-side only).
* Percent-encoding is left as-is. Re-encoding can double-encode
  already-encoded URLs and is more dangerous than helpful here.

Malformed input raises ``ValueError`` -- silent fallthrough to the
original string would make dedup unreliable.
"""

from __future__ import annotations

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
