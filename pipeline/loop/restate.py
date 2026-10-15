"""The restate step: ranked restatements of a claim whose verdict is weak or was tie-broken.

The step runs after the Evaluator (and the tie-breaker, when it ran) has
settled the pipeline verdict. It sends the restater the run's consulted
sources plus the best-matching sources already in ``research/sources/``,
then checks what comes back in code: evidence refs must name a sent source,
quotes are searched in the source text, decisiveness and confidence are
capped by what was verified, a candidate about another entity is dropped,
and the candidates are ranked by decisiveness whatever order the model gave.
The result is the sidecar's ``restatement`` block; the step writes nothing.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from common.frontmatter import parse_frontmatter
from common.models import Confidence, FailureInfo, Verdict, VerificationLevel, resolve_model
from common.utils import host_matches, url_host
from ingestor.validation import quote_in_text
from loop.analyse import _failure_from_exc, _run_agent_once
from loop.coverage import _STOP_WORDS, _words
from loop.restater.models import RestateBundle, RestatementProposal, RestateSource, RestaterDeps
from loop.spec import ClaimSpec, VerificationResult, VerifyConfig, _cfg_repo_root
from orchestrator.entity_resolution import ResolvedEntity
from orchestrator.persistence import load_source_dict

WEAK_VERDICTS = frozenset({Verdict.UNVERIFIED, Verdict.MIXED, Verdict.NOT_APPLICABLE})
SCHEMA_VERSION = 1

# Pool ranking weights: a source that names the entity counts most, then one
# that uses the statement's words, then one that uses the sub-questions'.
_ENTITY_WEIGHT = 3
_STATEMENT_WEIGHT = 2
_SUB_QUESTION_WEIGHT = 1
_MAX_HITS = 3
_MIN_TERM_LENGTH = 3

_SELF_REPORTED_LEVELS = frozenset({VerificationLevel.CLAIMED, VerificationLevel.SELF_REPORTED})


def needs_restatement(comparison) -> str | None:
    """The trigger for a settled comparison: ``"weak-verdict"``, ``"tie-broken"`` or None.

    A weak pipeline verdict wins even when the tie-breaker ran; evidence
    gaps alone never trigger a restatement.
    """
    if comparison is None:
        return None
    verdict = comparison.pipeline_verdict
    if verdict is not None and Verdict(verdict) in WEAK_VERDICTS:
        return "weak-verdict"
    if comparison.tiebreaker_verdict is not None:
        return "tie-broken"
    return None


# --------------------------------------------------------------------------- #
# The same-entity rule                                                          #
# --------------------------------------------------------------------------- #


def _name_words(text: str) -> list[str]:
    # A trailing "s" is ignored on both sides, so "US data center operators"
    # names "US Data Centers".
    return [w[:-1] if len(w) > 1 and w.endswith("s") else w for w in _words(text)]


def names_entity(text: str, names: Iterable[str]) -> bool:
    """True when ``text`` names one of ``names``: whole words, case-insensitive."""
    words = _name_words(text)
    for name in names:
        target = _name_words(name)
        n = len(target)
        if n and any(words[i:i + n] == target for i in range(len(words) - n + 1)):
            return True
    return False


def _own_names(entity: ResolvedEntity) -> list[str]:
    return [entity.entity_name, entity.legal_name or "", *(entity.aliases or [])]


def _dedupe(names: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, str] = {}
    for name in names:
        name = (name or "").strip()
        if name and name.lower() not in seen:
            seen[name.lower()] = name
    return tuple(seen.values())


def allowed_names(resolved: ResolvedEntity, statement: str, repo_root: Path) -> tuple[str, ...]:
    """The names a candidate may use: the entity's own, plus any entity file's the statement names.

    A subject claim often names products ("a prompt to Gemini or ChatGPT");
    a candidate narrowed to one of them is still about the claim, while a
    switch to an entity the original never named is not.
    """
    names = list(_own_names(resolved))
    entities_dir = repo_root / "research" / "entities"
    for path in sorted(entities_dir.rglob("*.md")) if entities_dir.is_dir() else []:
        try:
            fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        file_names = [fm.get("name") or "", *(a for a in fm.get("aliases") or [] if isinstance(a, str))]
        if names_entity(statement, [n for n in file_names if n]):
            names.extend(file_names)
    return _dedupe(names)


# --------------------------------------------------------------------------- #
# The pool                                                                      #
# --------------------------------------------------------------------------- #


def _terms(text: str) -> set[str]:
    return {w for w in _words(text) if len(w) >= _MIN_TERM_LENGTH and w not in _STOP_WORDS}


def _query_terms(entity: ResolvedEntity, statement: str, sub_question_texts: Iterable[str]) -> dict[str, int]:
    weights: dict[str, int] = {}
    for text, weight in (
        *((t, _SUB_QUESTION_WEIGHT) for t in sub_question_texts),
        (statement, _STATEMENT_WEIGHT),
        *((n, _ENTITY_WEIGHT) for n in _own_names(entity) if n),
    ):
        for term in _terms(text):
            weights[term] = max(weights.get(term, 0), weight)
    return weights


def _source_tokens(sd: dict) -> list[str]:
    parts = [sd.get("title"), sd.get("publisher"), sd.get("summary"), *(sd.get("key_quotes") or []), sd.get("body")]
    return _words(" ".join(p for p in parts if isinstance(p, str)))


def _score(sd: dict, weights: dict[str, int]) -> float:
    tokens = _source_tokens(sd)
    counts = Counter(tokens)
    raw = sum(w * min(counts[t], _MAX_HITS) for t, w in weights.items() if counts[t])
    return raw / math.log(2 + len(tokens)) if raw else 0.0


def _excluded_domains(entity: ResolvedEntity) -> list[str]:
    hints = entity.search_hints
    entries = hints.exclude if hints is not None else []
    return [e.strip().lower().removeprefix("www.") for e in entries if "." in e and " " not in e.strip()]


def rank_disk_pool(
    repo_root: Path,
    *,
    entity: ResolvedEntity,
    statement: str,
    sub_question_texts: Iterable[str] = (),
    skip_ids: Iterable[str] = (),
) -> list[dict]:
    """Every stored source not in ``skip_ids`` that scores above zero, best first.

    The score sums each query term's weight times its hits (at most three),
    divided by the log of the source's length so a long page does not win
    by length; ties go by source id. A source whose host matches a
    domain-shaped ``search_hints.exclude`` entry is left out.
    """
    sources_dir = repo_root / "research" / "sources"
    if not sources_dir.is_dir():
        return []
    weights = _query_terms(entity, statement, sub_question_texts)
    excluded = _excluded_domains(entity)
    skip = set(skip_ids)
    scored: list[tuple[float, str, dict]] = []
    for path in sources_dir.rglob("*.md"):
        sid = path.relative_to(sources_dir).with_suffix("").as_posix()
        if sid in skip:
            continue
        sd = load_source_dict(sid, repo_root)
        if sd is None:
            continue
        host = url_host(sd.get("url"))
        if host and any(host_matches(host, d) for d in excluded):
            continue
        score = _score(sd, weights)
        if score > 0:
            scored.append((score, sid, sd))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [sd for _score_, _sid, sd in scored]


def _restate_source(sd: dict, marker: str) -> RestateSource:
    return RestateSource(
        id=sd.get("source_id") or "",
        marker=marker,
        title=sd.get("title") or "",
        publisher=sd.get("publisher") or "",
        kind=sd.get("kind") or "",
        independence=sd.get("independence") or "",
        summary=sd.get("summary") or "",
        key_quotes=[q for q in sd.get("key_quotes") or [] if isinstance(q, str)],
        body=sd.get("body") or "",
    )


# --------------------------------------------------------------------------- #
# The code-side checks                                                          #
# --------------------------------------------------------------------------- #


def _source_fields(sd: dict) -> list[str]:
    fields = [sd.get("title"), sd.get("summary"), *(sd.get("key_quotes") or []), sd.get("body")]
    return [f for f in fields if isinstance(f, str)]


def _refs(refs, sources_by_id: dict[str, dict]) -> list[dict]:
    # One quote rule for the ingest check and the restater (``quote_in_text``).
    return [
        {"source": r.source, "quote": r.quote,
         "quote_verified": any(quote_in_text(r.quote, f) for f in _source_fields(sources_by_id[r.source])),
         "note": r.note}
        for r in refs
        if r.source in sources_by_id
    ]


def evaluate_proposal(
    proposal: RestatementProposal,
    sources_by_id: dict[str, dict],
    names: tuple[str, ...],
    max_candidates: int,
) -> tuple[list[dict], list[dict]]:
    """The ranked candidates and the dropped ones, after the code-side checks.

    A ref to a source that was not sent is dropped; a quote not found in its
    source is kept and marked unverified. Without a verified supporting
    quote decisiveness is at most 2, and an ``unverified`` candidate is at
    most 1; at 1 or less the candidate needs new research. A ``claimed`` or
    ``self-reported`` level caps confidence at low. A candidate that names
    none of ``names`` is dropped. The rest are ranked by decisiveness, then
    those needing no new research, then text.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for c in proposal.candidates:
        if not names_entity(c.text, names):
            dropped.append({"text": c.text, "reason": f"names none of the claim's entity names: {', '.join(names)}"})
            continue
        supporting = _refs(c.supporting, sources_by_id)
        contradicting = _refs(c.contradicting, sources_by_id)
        decisiveness = c.decisiveness
        if not any(r["quote_verified"] for r in supporting):
            decisiveness = min(decisiveness, 2)
        if c.expected_verdict == Verdict.UNVERIFIED:
            decisiveness = min(decisiveness, 1)
        confidence = c.expected_confidence
        if c.verification_level_estimate in _SELF_REPORTED_LEVELS and confidence != Confidence.LOW:
            confidence = Confidence.LOW
        kept.append({
            "rank": 0,
            "text": c.text,
            "frame": c.frame.value,
            "expected_verdict": c.expected_verdict.value,
            "expected_confidence": confidence.value,
            "verification_level_estimate": c.verification_level_estimate.value,
            "decisiveness": decisiveness,
            "needs_new_research": c.needs_new_research or decisiveness <= 1,
            "supporting": supporting,
            "contradicting": contradicting,
            "rationale": c.rationale,
        })
    kept.sort(key=lambda c: (-c["decisiveness"], c["needs_new_research"], c["text"]))
    kept = kept[:max_candidates]
    for i, c in enumerate(kept, 1):
        c["rank"] = i
    return kept, dropped


# --------------------------------------------------------------------------- #
# The step                                                                      #
# --------------------------------------------------------------------------- #


async def restate_step(
    result: VerificationResult,
    spec: ClaimSpec,
    cfg: VerifyConfig,
    *,
    cited_ids: Iterable[str],
    trigger: str,
) -> tuple[dict | None, FailureInfo | None]:
    """One restater attempt; ``(block, None)`` or ``(None, failure)``.

    The pool is the run's consulted sources, all sent and first (``[cited]``
    when the claim lists them, ``[consulted]`` otherwise), then the ranked
    disk pool (``[archive]``) up to ``cfg.restate_pool_size`` in all.
    """
    from loop.restater.agent import build_restater_prompt, restater_agent

    repo_root = _cfg_repo_root(cfg)
    comparison = result.consistency
    cited = set(cited_ids)
    consulted = [sd for sd in result.sources if sd.get("source_id")]
    sub_question_texts = [sq.question for sq in result.sub_questions]
    sub_question_texts += [q for qs in result.queries_by_sub_question.values() for q in qs]
    disk = rank_disk_pool(
        repo_root, entity=spec.entity, statement=spec.statement,
        sub_question_texts=sub_question_texts, skip_ids=[sd["source_id"] for sd in consulted],
    )
    room = max(0, cfg.restate_pool_size - len(consulted))
    sent_disk = disk[:room]
    sources = [
        _restate_source(sd, "cited" if sd["source_id"] in cited else "consulted") for sd in consulted
    ] + [_restate_source(sd, "archive") for sd in sent_disk]
    sources_by_id = {sd["source_id"]: sd for sd in [*consulted, *sent_disk]}

    verdict = comparison.pipeline_verdict or comparison.primary_verdict
    confidence = comparison.pipeline_confidence or comparison.primary_confidence
    bundle = RestateBundle(
        statement=spec.statement,
        pipeline_verdict=Verdict(verdict).value,
        pipeline_confidence=Confidence(confidence).value,
        tiebreak_rule=comparison.rule_applied if comparison.tiebreaker_verdict is not None else None,
        narrative=result.analyst_output.verdict.narrative if result.analyst_output else "",
        evidence_gaps=list(comparison.evidence_gaps),
        entity_name=spec.entity.entity_name,
        entity_aliases=list(spec.entity.aliases or []),
        entity_type=getattr(spec.entity.entity_type, "value", str(spec.entity.entity_type)),
        entity_description=spec.entity.entity_description or "",
        max_candidates=cfg.restate_max_candidates,
        sources=sources,
    )
    names = allowed_names(spec.entity, spec.statement, repo_root)
    model_spec = cfg.model_for("restater")

    with restater_agent.override(model=resolve_model(model_spec)):
        proposal, _, exc = await _run_agent_once(
            restater_agent, build_restater_prompt(bundle), cfg.restater_timeout_s,
            deps=RestaterDeps(allowed_names=names),
        )
    if proposal is None:
        return None, _failure_from_exc(
            exc or RuntimeError("the restater returned no output"), step="restater", agent="restater",
            model=model_spec, timeout_s=cfg.restater_timeout_s,
        )

    candidates, dropped = evaluate_proposal(proposal, sources_by_id, names, cfg.restate_max_candidates)
    block = {
        "schema_version": SCHEMA_VERSION,
        "model": model_spec,
        "trigger": trigger,
        "original": {"statement": spec.statement, "verdict": bundle.pipeline_verdict,
                     "confidence": bundle.pipeline_confidence},
        "pool": {"consulted": len(consulted), "on_disk": len(disk), "sent": len(sources)},
        "why_unverified": proposal.why_unverified.value,
        "why_unverified_note": proposal.why_unverified_note,
        "candidates": candidates,
        "dropped": dropped,
        "picked": None,
    }
    return block, None
