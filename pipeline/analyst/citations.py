"""Turn model citation habits into reader-facing source titles.

Some models cite with bracket tokens (【2025/some-id】, native to gpt-oss) or
with numbered references ("Source 3", "Sources 2, 4"). Neither means anything
on the published site, so in the narrative both are rewritten to italic
source titles. Fields too short to hold a title reject them instead (see
`has_citation_reference`), so the model rewrites the sentence.
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
# list. Lowercase forms are ordinary prose ("the source 2 weeks ago", "open
# source 2.0") unless they are a plural list of two or more numbers ("as
# sources 2 and 4 show"); rewriting prose into a title changes its meaning,
# and a missed reference is still caught by the lint check. `\b` before
# "source" excludes "resources 2". `\s` is Unicode-aware, so U+00A0 after
# "Source" matches. The `\b` after the digits keeps "Source 3D" untouched. An
# optional ": *Title*" after the reference is swallowed so the title is not
# written twice.
_LIST_SEP = r"\s*(?:,\s*and|,|and|&)\s*"
_CITATION = re.compile(
    r"(?P<bracket>(?:[^\S\n]*【[^】]*】)+)"
    r"|\b(?:Source\s+(?P<one>\d+)"
    rf"|Sources\s+(?P<many>\d+(?:{_LIST_SEP}\d+)*)"
    rf"|sources\s+(?P<list>\d+(?:{_LIST_SEP}\d+)+))\b"
    r"(?::\s*\*[^*\n]*\*)?"
)
_BRACKET_TOKEN = re.compile(r"【([^】]*)】")


def has_citation_reference(text: str) -> bool:
    """True when ``text`` holds a bracket token or a numbered source reference."""
    return bool(_CITATION.search(text))


def find_citation_references(text: str) -> list[tuple[str, str]]:
    """Every citation reference in ``text`` as ``(kind, matched text)``.

    ``kind`` is ``"bracket"`` for 【id】 runs and ``"numbered"`` for "Source N"
    forms. Shares the cleaner's pattern so `dr lint` flags exactly what the
    cleaner would rewrite.
    """
    return [
        ("bracket" if m.lastgroup == "bracket" else "numbered", m[0].strip())
        for m in _CITATION.finditer(text or "")
    ]


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

    def replace(m: re.Match[str]) -> str:
        # Only the alternation's named groups capture, so `lastgroup` names
        # the branch: "bracket", or "one"/"many"/"list" for a numbered one.
        kind = m.lastgroup
        titles: list[str] = []
        if kind == "bracket":
            for token in _BRACKET_TOKEN.finditer(m[kind]):
                title = lookup.get(token[1].split("†", 1)[0].strip())
                if title is None:
                    unresolved.append(token[0])
                elif title not in titles:
                    titles.append(title)
            return f" ({_join_titles(titles)})" if titles else ""
        for n in map(int, re.findall(r"\d+", m[kind])):
            title = sources[n - 1].get("title") if 1 <= n <= len(sources) else None
            if not title:
                unresolved.append(m[0])
                return m[0]
            if title not in titles:
                titles.append(title)
        return _join_titles(titles)

    return _CITATION.sub(replace, text), unresolved
