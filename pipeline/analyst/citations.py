"""Turn model citation habits into reader-facing source titles.

Some models cite with bracket tokens (【2025/some-id】, native to gpt-oss) or
with numbered references ("Source 3", "Sources 2, 4"). Neither means anything
on the published site, so both are rewritten to italic source titles.
"""

from __future__ import annotations

import re

# A run of one or more adjacent bracket tokens, with any same-line whitespace
# before each, so "text【a】 【b】." becomes "text (*A* and *B*)." with one
# space. Newlines are not consumed so a token never joins two lines.
_BRACKET_RUN = re.compile(r"(?:[^\S\n]*【[^】]*】)+")
_BRACKET_TOKEN = re.compile(r"【([^】]*)】")

# `\s` is Unicode-aware for str patterns, so U+00A0 between "Source" and the
# number is matched. The `\b` after the digits keeps "Source 3D" untouched.
# An optional ": *Title*" after the reference is swallowed so the title is
# not written twice.
_SOURCE_N = re.compile(
    r"\bSources?\s+(\d+(?:\s*(?:,\s*and|,|and|&)\s*\d+)*)\b(?::\s*\*[^*\n]*\*)?"
)


def _join_titles(titles: list[str]) -> str:
    italic = [f"*{t}*" for t in titles]
    if len(italic) <= 2:
        return " and ".join(italic)
    return ", ".join(italic[:-1]) + " and " + italic[-1]


def _title_lookup(sources: list[dict]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for src in sources:
        title = src.get("title")
        if not title:
            continue
        for key in (src.get("source_id"), src.get("slug")):
            if key:
                lookup.setdefault(key, title)
    return lookup


def clean_citations(text: str, sources: list[dict]) -> tuple[str, list[str]]:
    """Replace citation tokens and "Source N" references with source titles.

    `sources` must be the list given to `build_analyst_prompt`, in the same
    order: "Source N" maps to `sources[N - 1]`. Bracket ids are matched on
    each source's `source_id` (or `slug`); an id is the text before any
    `†` suffix inside the brackets.

    Unknown bracket ids are removed. A numbered reference with any number
    out of range is left as written, so the lint check can catch it.
    Returns the cleaned text and the tokens that could not be resolved.
    """
    if not text:
        return text, []

    lookup = _title_lookup(sources)
    unresolved: list[str] = []

    def bracket_run(match: re.Match[str]) -> str:
        titles: list[str] = []
        for token in _BRACKET_TOKEN.finditer(match.group(0)):
            key = token.group(1).split("†", 1)[0].strip()
            title = lookup.get(key)
            if title is None:
                unresolved.append(token.group(0))
            elif title not in titles:
                titles.append(title)
        if not titles:
            return ""
        return f" ({_join_titles(titles)})"

    def source_n(match: re.Match[str]) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        if any(n < 1 or n > len(sources) for n in numbers):
            unresolved.append(match.group(0))
            return match.group(0)
        titles: list[str] = []
        for n in numbers:
            title = sources[n - 1].get("title")
            if not title:
                unresolved.append(match.group(0))
                return match.group(0)
            if title not in titles:
                titles.append(title)
        return _join_titles(titles)

    text = _BRACKET_RUN.sub(bracket_run, text)
    text = _SOURCE_N.sub(source_n, text)
    return text, unresolved
