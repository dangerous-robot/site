"""Wrap bare email addresses and URLs in Markdown text in angle brackets.

markdownlint MD034 (on for ``research/``) rejects a bare address; the
CommonMark autolink form ``<mail@example.org>`` passes and renders as a link.
Extents follow GitHub's autolink-literal rules, which markdownlint uses to
find bare addresses. Bare ``www.`` hosts are left alone: ``<www.example.org>``
is not an autolink and would render with its brackets.
"""

from __future__ import annotations

import re

# Spans whose text is not prose: code, existing autolinks and HTML, links
# and images (text and destination), and reference definitions.
_PROTECTED = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[^\n]*\n.*?(?:^(?P=fence)[ \t]*$|\Z)"
    r"|(?P<ticks>`+).+?(?P=ticks)"
    r"|<!--.*?-->"
    r"|<[^<>\s]+>"
    r"|</?[A-Za-z][^<>]*>"
    r"|!?\[[^\]\n]*\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+\"[^\"\n]*\")?\)"
    r"|^[ ]{0,3}\[[^\]\n]+\]:[^\n]*$",
    re.MULTILINE | re.DOTALL,
)

_BARE = re.compile(
    r"(?P<url>(?<![A-Za-z0-9])https?://[^\s<]+)"
    r"|(?P<email>(?<![\w.+:/-])[A-Za-z0-9._+-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+)"
)

_TRAILING_PUNCT = "?!.,:*_~'\""
_ENTITY_AT_END = re.compile(r"&[A-Za-z0-9]+;$")


def _trim_url(url: str) -> str:
    while url:
        last = url[-1]
        if last in _TRAILING_PUNCT:
            url = url[:-1]
        elif last == ")" and url.count("(") < url.count(")"):
            url = url[:-1]
        elif last == ";" and (m := _ENTITY_AT_END.search(url)):
            url = url[: m.start()]
        else:
            break
    return url


def _wrap(match: re.Match[str]) -> str:
    text = match.group(0)
    if match.group("email"):
        return f"<{text}>"
    url = _trim_url(text)
    return f"<{url}>{text[len(url):]}"


def wrap_bare_links(markdown: str) -> str:
    """Return ``markdown`` with each bare email address and http(s) URL in
    angle brackets. Code, links, autolinks and HTML are unchanged, so the
    result is stable when run again."""
    out: list[str] = []
    pos = 0
    for protected in _PROTECTED.finditer(markdown):
        out.append(_BARE.sub(_wrap, markdown[pos : protected.start()]))
        out.append(protected.group(0))
        pos = protected.end()
    out.append(_BARE.sub(_wrap, markdown[pos:]))
    return "".join(out)
