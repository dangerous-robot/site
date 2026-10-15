"""The review packet: what a reviewer reads before signing off on one claim.

Four parts, in the order the reviewer ranked them:

1. The verdict chain: the statement, the restated candidates, the analyst,
   the Evaluator, the tie-breaker and the pipeline's settled verdict, one
   line each, followed by the header facts (verdict, title, takeaway, tags,
   source counts, a pending refresh or override).
2. Every key quote with the automated check's result and the page passage.
3. Source independence: publisher, kind, label, override reasons and the
   other consulted sources on the same host or newswire origin.
4. What the run searched for and what the scorer rejected.

``build_packet`` reads the claim, its sidecar, its source files and the
findings file, and writes nothing. ``render_full`` is the plain text of all
four parts (``dr review --format text`` and the ``v`` key);
``render_upper`` and ``render_bottom`` split it for the walkthrough, which
prints parts 2 to 4 first so part 1 sits directly above the key prompt.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import asdict
from pathlib import Path

import click

from common.frontmatter import claim_statement, parse_frontmatter
from common.sidecar import pipeline_verdict_of, read_sidecar
from common.source_classification import classify_source_type, independence_for_source_type
from orchestrator.review_queue import QueueItem, _partial_restate_runs, item_for

PACKET_WIDTH = 100
PART_TITLES = {
    1: "Verdict chain",
    2: "Quotes",
    3: "Source independence",
    4: "Search and rejected candidates",
}
_RULE_WIDTH = 72
_SCORER_CHARS = 300
_EMPTY = "—"
_EMPHASIS = re.compile(r"[*_`]")
_FIRST_SENTENCE = re.compile(r"^(.+?[.!?])(?=\s|$)", re.S)
_QUOTE_KEYS = ("text", "found", "checked_against", "passage", "reason", "fragment_link")


# --------------------------------------------------------------------------- #
# Building the record                                                          #
# --------------------------------------------------------------------------- #


def fragment_link(archived_url: str, quote: str) -> str:
    """A text-fragment link that opens the archive copy at ``quote``."""
    return f"{archived_url}#:~:text={urllib.parse.quote(quote, safe='').replace('-', '%2D')}"


def build_packet(claim_path: Path, repo_root: Path, *, partial_restate_runs: set[str] | None = None) -> dict:
    """The review packet of one claim, as a JSON-ready record.

    The record is the claim's ``QueueItem`` fields plus ``verdict_chain``,
    ``quotes``, ``independence`` and ``search``. Raises ``ValueError`` when
    the claim does not parse or has no sidecar. ``partial_restate_runs`` (the
    run ids of failed restaters) is read from the findings file when not given.
    """
    claims_root = repo_root / "research" / "claims"
    if partial_restate_runs is None:
        partial_restate_runs = _partial_restate_runs(repo_root)
    item = item_for(claim_path, claims_root, repo_root, partial_restate_runs)
    if item is None:
        raise ValueError(f"no readable claim with a sidecar at {claim_path}")
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    sidecar = read_sidecar(claim_path) or {}

    cited = [str(s) for s in fm.get("sources") or []]
    consulted = [e for e in sidecar.get("sources_consulted") or [] if isinstance(e, dict) and e.get("id")]
    consulted_ids = {str(e["id"]) for e in consulted}
    entries = consulted + [{"id": sid} for sid in cited if sid not in consulted_ids]
    files = {str(e["id"]): _source_file(str(e["id"]), repo_root) for e in entries}
    overrides = [o for o in fm.get("source_overrides") or [] if isinstance(o, dict)]

    record = asdict(item)
    record["verdict_chain"] = _verdict_chain(item, fm, body, sidecar)
    record["quotes"] = [_quotes_of(e, files[str(e["id"])], cited) for e in entries]
    record["independence"] = [_independence_of(e, files[str(e["id"])], overrides) for e in entries]
    record["search"] = _search_of(sidecar)
    return record


def _source_file(source_id: str, repo_root: Path) -> dict | None:
    """The source file's frontmatter, or None when it was never written or does not parse."""
    path = repo_root / "research" / "sources" / f"{source_id}.md"
    try:
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return fm


def _analyst_reason(body: str) -> str:
    """The first sentence of the claim's narrative (the analyst wrote it), emphasis removed."""
    lines = [ln for ln in body.strip().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    text = " ".join(_EMPHASIS.sub("", " ".join(lines)).split())
    m = _FIRST_SENTENCE.match(text)
    return m.group(1) if m else text


def _side(verdict: object, confidence: object, reason: object) -> dict:
    return {"verdict": str(verdict or ""), "confidence": str(confidence or ""), "reason": str(reason or "")}


def _verdict_chain(item: QueueItem, fm: dict, body: str, sidecar: dict) -> dict:
    audit = sidecar.get("audit") if isinstance(sidecar.get("audit"), dict) else {}
    restatement = None
    if item.restatement:
        restatement = {
            "candidates": [
                {k: c.get(k) for k in ("rank", "text", "expected_verdict", "expected_confidence", "decisiveness")}
                for c in item.restatement.get("candidates") or [] if isinstance(c, dict)
            ],
            "picked": item.restatement.get("picked"),
        }
    tiebreaker = None
    if audit.get("tiebreaker_verdict"):
        tiebreaker = _side(audit.get("tiebreaker_verdict"), audit.get("tiebreaker_confidence"),
                           audit.get("tiebreaker_reasoning"))
    return {
        "statement": claim_statement(fm),
        "restatement": restatement,
        "restatement_unavailable": item.restatement_unavailable,
        "analyst": _side(audit.get("analyst_verdict") or fm.get("verdict"),
                         audit.get("analyst_confidence") or fm.get("confidence"), _analyst_reason(body)),
        "evaluator": _side(audit.get("auditor_verdict"), audit.get("auditor_confidence"),
                           audit.get("auditor_reasoning")) if audit else None,
        "tiebreaker": tiebreaker,
        "pipeline_verdict": pipeline_verdict_of(audit),
        "pipeline_confidence": audit.get("pipeline_confidence") or audit.get("analyst_confidence"),
        "rule_applied": audit.get("rule_applied"),
        "evidence_gaps": [str(g) for g in audit.get("evidence_gaps") or []],
        # A sidecar from before the tie-breaker records no pipeline verdict of its own.
        "pre_tiebreaker": bool(audit) and "pipeline_verdict" not in audit,
    }


def _quotes_of(entry: dict, source: dict | None, cited: list[str]) -> dict:
    source_id = str(entry["id"])
    archived = (source or {}).get("archived_url") or None
    if "quotes" in entry:
        raw = [q for q in entry.get("quotes") or [] if isinstance(q, dict)]
    else:
        # A sidecar written before the checks were recorded: the source file's
        # kept quotes, with no check result to show.
        raw = [
            {"text": q, "found": None, "checked_against": "not-recorded", "passage": None}
            for q in (source or {}).get("key_quotes") or [] if isinstance(q, str)
        ]
    quotes = []
    for q in raw:
        out = {k: q.get(k) for k in _QUOTE_KEYS}
        if out["found"] is True and archived:
            out["fragment_link"] = fragment_link(str(archived), str(out["text"]))
        quotes.append(out)
    return {
        "source": source_id,
        "title": str(entry.get("title") or (source or {}).get("title") or ""),
        "cited": source_id in cited,
        "written": source is not None,
        "archived_url": archived,
        "quotes": quotes,
    }


def _independence_of(entry: dict, source: dict | None, overrides: list[dict]) -> dict:
    source_id = str(entry["id"])
    mine = [o for o in overrides if str(o.get("source")) == source_id]
    publisher = str((source or {}).get("publisher") or "")
    kind = str((source or {}).get("kind") or "")
    label = (source or {}).get("independence")
    if source is not None and not label:
        label = independence_for_source_type(source.get("source_type") or classify_source_type(publisher, kind))
    for o in mine:
        if o.get("independence"):
            label = o["independence"]
    return {
        "source": source_id,
        "written": source is not None,
        "publisher": publisher,
        "kind": kind,
        "independence": str(getattr(label, "value", label) or ""),
        "override_reasons": [str(o["reason"]) for o in mine if o.get("reason")],
        "shared_with": [str(s) for s in entry.get("shared_with") or []],
    }


def _search_of(sidecar: dict) -> dict:
    research = sidecar.get("research") if isinstance(sidecar.get("research"), dict) else {}
    sub_questions = [
        {
            "id": str(sq.get("id") or ""),
            "kind": str(sq.get("kind") or "coverage"),
            "question": str(sq.get("question") or ""),
            "queries": [str(q) for q in sq.get("queries") or []],
        }
        for sq in sidecar.get("sub_questions") or [] if isinstance(sq, dict)
    ]
    dropped = research.get("urls_dropped")
    return {
        "sub_questions": sub_questions,
        "queries": [str(q) for q in research.get("queries") or []],
        "scorer_rationale": str(research.get("scorer_rationale") or ""),
        "rejected": [r for r in research.get("rejected") or [] if isinstance(r, dict)],
        # A sidecar written before the scorer's rejections were recorded has
        # no ``rejected`` key: its empty list is not "nothing rejected".
        "rejected_recorded": "rejected" in research,
        "urls_dropped": dropped if isinstance(dropped, int) and not isinstance(dropped, bool) else None,
    }


# --------------------------------------------------------------------------- #
# Text                                                                          #
# --------------------------------------------------------------------------- #


def _rule(prefix: str) -> str:
    return prefix + "─" * max(4, _RULE_WIDTH - len(prefix))


def _heading(n: int) -> str:
    return _rule(f"── {n}. {PART_TITLES[n]} ")


def item_line(slug: str, index: int, total: int) -> str:
    """``── [i/n] <slug> ───``: the line that opens one queued draft, cut to the packet width.

    A long slug is cut with ``…``; the sign-off prompt and the ``r`` key's
    command print it whole.
    """
    return _cut(_rule(f"── [{index}/{total}] {slug} "))


def _cut(line: str) -> str:
    return line if len(line) <= PACKET_WIDTH else line[: PACKET_WIDTH - 1] + "…"


def _chain_lines(chain: dict, *, cut: bool = True) -> list[str]:
    def side(label: str, s: dict) -> str:
        reason = " ".join(s["reason"].split())
        return f"  {label:<12} {s['verdict']} ({s['confidence']})" + (f": {reason}" if reason else "")

    lines = [f"  {'Statement:':<12} {chain['statement']}"]
    restatement = chain["restatement"]
    if chain["restatement_unavailable"]:
        lines.append(f"  Restatement unavailable (finding {chain['restatement_unavailable']})")
    elif restatement and restatement["candidates"]:
        for c in restatement["candidates"]:
            picked = " [picked]" if restatement.get("picked") is not None and restatement["picked"] == c["rank"] else ""
            lines.append(
                f"  Restated #{c['rank']}: {c['expected_verdict']} ({c['expected_confidence']}), "
                f"decisiveness {c['decisiveness']}/4: {c['text']}{picked}"
            )
    else:
        lines.append(f"  {'Restated:':<12} none")
    lines.append(side("Analyst:", chain["analyst"]))
    if chain["evaluator"] is None:
        lines.append(f"  {'Evaluator:':<12} not run")
    else:
        lines.append(side("Evaluator:", chain["evaluator"]))
    if chain["tiebreaker"] is not None:
        lines.append(side("Tie-breaker:", chain["tiebreaker"]))
    elif chain["evaluator"] is None:
        lines.append(f"  {'Tie-breaker:':<12} not run")
    else:
        lines.append(f"  {'Tie-breaker:':<12} not run (analyst and Evaluator agreed)")
    pipeline = f"  {'Pipeline:':<12} {chain['pipeline_verdict'] or _EMPTY} ({chain['pipeline_confidence'] or _EMPTY})"
    if chain["rule_applied"]:
        pipeline += f", rule {chain['rule_applied']}"
    elif chain["pre_tiebreaker"]:
        pipeline += ", rule not recorded (pre-tie-breaker sidecar)"
    else:
        pipeline += ", rule not recorded"
    lines.append(pipeline)
    return [_cut(line) for line in lines] if cut else lines


def render_header_facts(item: QueueItem, *, styled: bool = False, gaps: list[str] | None = None) -> list[str]:
    """The header facts printed with part 1: verdict, a pending recheck, refresh or override, the fields a reviewer edits."""
    def style(text: str, **kw) -> str:
        return click.style(text, **kw) if styled else text

    empty = style(_EMPTY, dim=True)

    def row(label: str, value: str) -> str:
        return f"  {label:<9} {value}"

    def cut(label: str, value: str) -> str:
        # Cut the plain text, so styling never counts toward the width.
        return _cut(row(label, value))

    flag = "  ⚠ needs review" if item.needs_review else ""
    verdict_row = cut("Verdict", item.verdict.upper() + flag)
    if styled:
        verdict_row = verdict_row.replace(item.verdict.upper(), click.style(item.verdict.upper(), bold=True), 1)
        if flag:
            verdict_row = verdict_row.replace(flag, click.style(flag, fg="yellow"), 1)

    recheck_rows = []
    if item.recheck:
        r = item.recheck
        if r.get("verdict_changed"):
            text = f"verdict changed: {r.get('live_verdict')} to {r.get('pending_verdict')}"
            recheck_rows.append(cut("Recheck", text) if not styled else row("Recheck", style(text, fg="yellow")))
        else:
            recheck_rows.append(cut("Recheck", (
                f"verdict unchanged, {r.get('quotes_found', 0)} of {r.get('quotes_checked', 0)} quotes still found, "
                f"{r.get('refetched', 0)} sources re-fetched"
            )))
            if r.get("quotes_not_rechecked"):
                recheck_rows.append(cut("", f"{r['quotes_not_rechecked']} quotes not rechecked (source inside its cadence)"))

    refresh_rows = []
    if item.previous_verdict:
        was = f"Was published: {item.previous_verdict} (reviewed {item.previous_reviewed_at or 'unknown'})"
        if item.verdict != item.previous_verdict:
            was += style("  verdict changed; approval will ask for a correction", fg="yellow")
        refresh_rows.append(row("", was))

    override_rows = []
    if item.unreviewed_override:
        override = item.unreviewed_override
        override_rows.append(cut(
            "Override", f"pipeline {override['from']}, claim {override['to']}; approving records it as yours",
        ))

    gap_rows = []
    if gaps:
        gap_rows.append(cut("Gaps", f"{len(gaps)}: {' '.join(str(gaps[0]).split())}"))

    return [
        verdict_row,
        *recheck_rows,
        *refresh_rows,
        *override_rows,
        cut("Title", item.title) if item.title else row("Title", empty),
        cut("Takeaway", item.takeaway) if item.takeaway else row("Takeaway", empty),
        cut("SEO title", item.seo_title) if item.seo_title else row("SEO title", empty),
        cut("Tags", ", ".join(item.tags)) if item.tags else row("Tags", empty),
        row("Sources", f"{item.sources_count} cited · {item.sources_ingested} ingested"),
        *gap_rows,
    ]


def _item_of(packet: dict) -> QueueItem:
    fields = QueueItem.__dataclass_fields__
    return QueueItem(**{k: v for k, v in packet.items() if k in fields})


def _part1(packet: dict, *, styled: bool, cut: bool = True) -> list[str]:
    # Only the walkthrough's bottom block has a width budget; the full packet keeps the whole statement.
    return [
        _heading(1),
        *_chain_lines(packet["verdict_chain"], cut=cut),
        *render_header_facts(_item_of(packet), styled=styled, gaps=packet["verdict_chain"]["evidence_gaps"]),
    ]


_QUOTE_MARKS = ('"', "\u201c", "\u201d")


def _quoted(text: object) -> str:
    """``text`` in double quote marks, unless the stored text already opens and closes with one."""
    text = str(text)
    stripped = text.strip()
    if len(stripped) > 1 and stripped[0] in _QUOTE_MARKS and stripped[-1] in _QUOTE_MARKS:
        return stripped
    return f'"{text}"'


def _part2(packet: dict) -> list[str]:
    lines = [_heading(2)]
    for s in packet["quotes"]:
        mark = "[cited]" if s["cited"] else "[not cited]"
        missing = "" if s["written"] else " (no source file)"
        lines.append(f"{mark} {s['source']}: {s['title']}{missing}")
        for q in s["quotes"]:
            text = _quoted(q["text"])
            if q["found"] is True:
                lines.append(f"  [found] {text}")
                if q["passage"]:
                    lines.append(f"    passage: {q['passage']}")
                if q["fragment_link"]:
                    lines.append(f"    open: {q['fragment_link']}")
            elif q["found"] is False:
                lines.append(f'  [not found] {text}: {q["reason"] or "no reason recorded"}')
            elif q["checked_against"] == "not-recorded":
                lines.append(f"  [not recorded] {text}")
            else:
                lines.append(f'  [{q["checked_against"] or "not checked"}] {text}')
    if not packet["quotes"]:
        lines.append("No sources consulted.")
    return lines


def _part3(packet: dict) -> list[str]:
    lines = [_heading(3)]
    for s in packet["independence"]:
        if s["written"]:
            lines.append(f"{s['source']}: {s['publisher'] or _EMPTY} · {s['kind'] or _EMPTY} · {s['independence'] or _EMPTY}")
        else:
            lines.append(f"{s['source']}: (no source file)")
        lines.extend(f"  {reason}" for reason in s["override_reasons"])
        if s["shared_with"]:
            lines.append(f"  shared with: {', '.join(s['shared_with'])}")
    if not packet["independence"]:
        lines.append("No sources consulted.")
    return lines


def _part4(packet: dict) -> list[str]:
    search = packet["search"]
    lines = [_heading(4), "Queries:"]
    listed: set[str] = set()
    for sq in search["sub_questions"]:
        for q in sq["queries"]:
            lines.append(f"  {q} ({sq['id']}, {sq['kind']})")
            listed.add(q)
    lines.extend(f"  {q}" for q in search["queries"] if q not in listed)
    rationale = " ".join(search["scorer_rationale"].split())
    lines.append(f"Scorer: {rationale[:_SCORER_CHARS] or _EMPTY}")
    if not search.get("rejected_recorded", True):
        dropped = search.get("urls_dropped")
        lines.append("Rejected: not recorded" + (f" ({dropped} dropped)" if dropped is not None else ""))
        return lines
    lines.append(f"Rejected ({len(search['rejected'])}):")
    lines.extend(f"  {r.get('url', '')}: {r.get('reason', '')}" for r in search["rejected"])
    return lines


def render_upper(packet: dict) -> str:
    """Parts 2 to 4, plain text: what the walkthrough prints above the verdict chain."""
    return "\n".join([*_part2(packet), "", *_part3(packet), "", *_part4(packet)])


def render_bottom(packet: dict, index: int, total: int) -> str:
    """The item line, part 1 and the header facts, styled: what sits directly above the key prompt."""
    return "\n".join(["", item_line(packet["claim_slug"], index, total), *_part1(packet, styled=True), ""])


def render_full(packet: dict) -> str:
    """The whole packet, parts 1 to 4 in order, as plain text."""
    return "\n".join([*_part1(packet, styled=False, cut=False), "", render_upper(packet)])
