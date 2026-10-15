"""Sub-question coverage, confirmed against each source's text after ingest.

The scorer tags each candidate URL with the sub-questions it looks like it
addresses, judging from a search snippet. After ingest, a tag stands only
when the source's text mentions at least one of the sub-question's terms;
otherwise it is dropped from coverage and reported as snippet-only.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping

from common.models import SubQuestion
from common.source_classification import EntityIdentity

_STOP_WORDS: frozenset[str] = frozenset({
    "the", "and", "does", "what", "which", "with", "from", "that", "this", "its",
    "are", "was", "were", "has", "have", "not", "for", "how", "why", "who", "when",
    "where", "any", "than", "more", "less", "into", "over", "about", "their",
    "there", "these", "those", "they", "them", "will", "would", "can", "could",
    "should", "did", "been", "being", "also",
})
_MIN_TERM_LENGTH = 3


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def _padded_words(text: str) -> str:
    # Space-padded so a term test with surrounding spaces is a whole-word match.
    return " " + " ".join(_words(text)) + " "


def sub_question_terms(
    sq: SubQuestion, queries: Iterable[str], identity: EntityIdentity
) -> frozenset[str]:
    """The words of ``sq``'s question and queries that can confirm a tag.

    Lowercased, three letters or longer, minus stop words and minus every
    word of the entity's names, since every page about the entity names it.
    """
    name_words = {w for name in identity.names for w in name.split()}
    return frozenset(
        w
        for text in (sq.question, *queries)
        for w in _words(text)
        if len(w) >= _MIN_TERM_LENGTH and w not in _STOP_WORDS and w not in name_words
    )


def _source_text(sd: Mapping, page_text: Mapping[str, str]) -> str:
    """The fetched page for a fresh source; the stored fields for a cached one."""
    fetched = page_text.get(sd.get("url") or "")
    if fetched is not None:
        return fetched
    parts = [sd.get("title"), sd.get("summary"), *(sd.get("key_quotes") or []), sd.get("body")]
    return " ".join(p for p in parts if isinstance(p, str))


def confirm_coverage(
    sub_questions: list[SubQuestion],
    queries_by_sub_question: Mapping[str, list[str]],
    sources: list[dict],
    page_text: Mapping[str, str],
    identity: EntityIdentity,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Confirm the scorer's tags against each source's text; return (coverage, snippet_only).

    ``coverage`` maps each sub-question id to the source ids whose text
    mentions one of its terms; ``snippet_only`` maps it to the ids whose tag
    was dropped. Every sub-question id is in both, with an empty list for
    none. Each source's ``addresses`` is rewritten in place to the confirmed
    tags, so the analyst prompt shows the confirmed set.

    A word in more than one sub-question's terms is left out of all of them:
    it is the claim's topic ("energy" on an energy claim), which every page
    mentions, so it cannot tell one sub-question's evidence from another's.
    A sub-question left with no terms keeps every tag.
    """
    raw_terms = {
        sq.id: sub_question_terms(sq, queries_by_sub_question.get(sq.id, []), identity)
        for sq in sub_questions
    }
    seen_in = Counter(w for terms in raw_terms.values() for w in terms)
    terms = {
        sq_id: frozenset(w for w in words if seen_in[w] == 1)
        for sq_id, words in raw_terms.items()
    }
    coverage: dict[str, list[str]] = {sq.id: [] for sq in sub_questions}
    snippet_only: dict[str, list[str]] = {sq.id: [] for sq in sub_questions}
    for sd in sources:
        sid = sd.get("source_id")
        if not sid:
            continue
        padded = _padded_words(_source_text(sd, page_text))
        confirmed: list[str] = []
        for sq_id in sd.get("addresses", []):
            if sq_id not in coverage:
                confirmed.append(sq_id)
                continue
            sq_terms = terms[sq_id]
            if not sq_terms or any(f" {w} " in padded for w in sq_terms):
                confirmed.append(sq_id)
                if sid not in coverage[sq_id]:
                    coverage[sq_id].append(sid)
            elif sid not in snippet_only[sq_id]:
                snippet_only[sq_id].append(sid)
        sd["addresses"] = confirmed
    return coverage, snippet_only
