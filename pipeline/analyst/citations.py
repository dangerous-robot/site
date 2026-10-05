"""Turn model citation habits into reader-facing source titles.

Some models cite with bracket tokens (【2025/some-id】, native to gpt-oss) or
with numbered references ("Source 3", "Sources 2, 4"). Neither means anything
on the published site, so both are rewritten to italic source titles, or
removed from fields too short to hold a title.
"""

from __future__ import annotations

import re

# Bracket runs and numbered references are matched by one alternation in a
# single substitution pass, so a title inserted for one (say "Open Source 1
# Report") is never scanned again as a reference.
#
# Bracket run: one or more adjacent tokens, with any same-line whitespace
# before each, so "text【a】 【b】." becomes "text (*A* and *B*)." with one
# space. Newlines are not consumed so a token never joins two lines.
#
# Numbered reference: singular "Source" takes exactly one number, so the "3"
# in "Per Source 1, 3 data centers" stays prose; only plural "Sources" takes a
# list. Case-insensitive; `\b` before "source" excludes "resources 2". `\s`
# is Unicode-aware, so U+00A0 after "Source" matches. The `\b` after the
# digits keeps "Source 3D" untouched. An optional ": *Title*" after the
# reference is swallowed so the title is not written twice.
_CITATION = re.compile(
    r"(?P<bracket>(?:[^\S\n]*【[^】]*】)+)"
    r"|\b(?:source\s+(?P<one>\d+)|sources\s+(?P<many>\d+(?:\s*(?:,\s*and|,|and|&)\s*\d+)*))\b"
    r"(?::\s*\*[^*\n]*\*)?",
    re.IGNORECASE,
)
_BRACKET_TOKEN = re.compile(r"【([^】]*)】")

# Strip-mode tidying of what a removal leaves behind.
_EMPTY_PARENS = re.compile(r"[^\S\n]*\(\s*\)")
_SPACE_BEFORE_PUNCT = re.compile(r"[^\S\n]+([.,;:!?)])")
_SPACE_RUN = re.compile(r"[^\S\n]{2,}")


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


def clean_citations(
    text: str, sources: list[dict], *, strip: bool = False
) -> tuple[str, list[str]]:
    """Replace citation tokens and "Source N" references with source titles.

    `sources` must be the list given to `build_analyst_prompt`, in the same
    order: "Source N" maps to `sources[N - 1]`. Bracket ids are matched on
    each source's `source_id` (or `slug`); an id is the text before any
    `†` suffix inside the brackets.

    With `strip=True` resolved references are removed instead of replaced,
    for length-capped fields where an inserted title could break the limit.

    Unknown bracket ids are removed. A numbered reference with any number
    out of range is left as written, so the lint check can catch it.
    Returns the cleaned text and the tokens that could not be resolved.
    """
    if not text:
        return text, []

    lookup = _title_lookup(sources)
    unresolved: list[str] = []
    removed = False

    def bracket_run(run: str) -> str:
        titles: list[str] = []
        for token in _BRACKET_TOKEN.finditer(run):
            key = token.group(1).split("†", 1)[0].strip()
            title = lookup.get(key)
            if title is None:
                unresolved.append(token.group(0))
            elif title not in titles:
                titles.append(title)
        if strip or not titles:
            return ""
        return f" ({_join_titles(titles)})"

    def source_n(match: re.Match[str]) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group("one") or match.group("many"))]
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
        return "" if strip else _join_titles(titles)

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        if match.group("bracket") is not None:
            out = bracket_run(match.group("bracket"))
        else:
            out = source_n(match)
        removed = removed or out == ""
        return out

    text = _CITATION.sub(replace, text)
    if strip and removed:
        text = _EMPTY_PARENS.sub("", text)
        text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
        text = _SPACE_RUN.sub(" ", text).strip()
    return text, unresolved
