"""The review packet at `dr review` (RE-AV, Review packet; plan § SP4 (Review packet) and § End state, The review packet).

Every case drives the `dr` CLI through CliRunner on hand-written claims and
sidecars (the keys the writer adds are recorded by a real run in
``test_packet_records.py``). The packet's text is pinned by its part
headings, which start ``── <n>. `` (1 Verdict chain, 2 Quotes, 3 Source
independence, 4 Search and rejected candidates), and by the line prefixes of
the verdict chain. The walkthrough prints parts 2 to 4, then the item line
``── [i/n] <slug>``, part 1 and the header facts, then the key prompt.
"""

from __future__ import annotations

import json
import re
import shutil
import stat
from pathlib import Path

import click
import pytest
import yaml
from click.testing import CliRunner

from tests.loop_harness import ENTITY_REF, write_entity

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
FIXTURES = PIPELINE_DIR / "tests" / "fixtures"

STEM = "probe-claim"
SLUG = f"{ENTITY_REF}/{STEM}"
STATEMENT = "Probe Subject data centers used more than 4% of US electricity in 2024"
RUN_ID = "1" * 32
ANALYST_FIRST_SENTENCE = "The analyst narrative opens here."
EVALUATOR_REASON = "The Evaluator found the share unproven."
TIEBREAKER_REASON = "The tie-breaker weighed both sides."
OFF_ENTITY = "Off-entity: the source does not mention Probe Subject, and the claim does not name its publisher."
ENTITY_MATCH = "Entity match: probe-subject.example is the entity's own site."
SCORER_REASON = "scored below 3 on every sub-question"
ARCHIVED = "https://web.archive.org/web/20260101000000/https://news.example.org/a0"
PACKET_WIDTH = 100
HEADING = re.compile(r"^── ([1-4])\. ")
ITEM_LINE = re.compile(r"^── \[\d+/\d+\] ")
HEADER_LABELS = ("Title", "Takeaway", "SEO title", "Tags", "Sources")
CANDIDATE_TEXTS = [
    "Probe Subject data centers used about 4% of US electricity in 2023.",
    "Probe Subject data centers used more than 3% of US electricity in 2024.",
    "Probe Subject reports its data centers' electricity use every year.",
    "Probe Subject data centers used less than 5% of US electricity in 2024.",
    "Probe Subject's electricity share rose between 2020 and 2024.",
]


# --------------------------------------------------------------------------- #
# Fixture                                                                          #
# --------------------------------------------------------------------------- #


def _source_id(i: int) -> str:
    return f"2026/src-{i}"


def _url(i: int) -> str:
    # Sources 0 to 3 share one canonical host; 4 to 7 each have their own.
    return f"https://news.example.org/a{i}" if i < 4 else f"https://site{i}.example.net/a{i}"


def _quote(i: int, j: int) -> str:
    return f"quote {i}-{j}"


def _passage(i: int, j: int) -> str:
    return f"Before the match. Here {_quote(i, j)} sits in this sentence. After the match."


def _restatement_block(*, picked=None) -> dict:
    return {
        "schema_version": 1,
        "model": "test",
        "trigger": "tie-broken",
        "original": {"statement": STATEMENT, "verdict": "mixed", "confidence": "medium"},
        "pool": {"consulted": 8, "on_disk": 0, "sent": 8},
        "why_unverified": "quantifier-unsupported",
        "why_unverified_note": "The sources give a range, not a floor.",
        "candidates": [
            {
                "rank": i + 1, "text": t, "frame": "narrowed", "expected_verdict": "true",
                "expected_confidence": "medium", "verification_level_estimate": "independently-verified",
                "decisiveness": 4 - min(i, 3), "needs_new_research": False,
                "supporting": [], "contradicting": [], "rationale": "Report 1 says so.",
            }
            for i, t in enumerate(CANDIDATE_TEXTS)
        ],
        "dropped": [],
        "picked": picked,
    }


def _write_source_file(repo_root: Path, i: int) -> None:
    fm = {
        "url": _url(i), "title": f"Source {i}", "publisher": f"Publisher {i}", "accessed_date": "2026-10-01",
        "kind": "report" if i % 2 else "article", "independence": "independent",
        "summary": f"Summary of source {i}.", "key_quotes": [_quote(i, j) for j in range(3)],
    }
    if i == 0:
        fm["archived_url"] = ARCHIVED
    path = repo_root / "research" / "sources" / f"{_source_id(i)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nBody of source {i}.\n", encoding="utf-8")


def _sources_consulted() -> list[dict]:
    entries = []
    for i in range(8):
        if i == 7:  # a cached source: reused from disk, quotes not checked this run
            quotes = [{"text": _quote(i, j), "found": None, "checked_against": "not-rechecked", "passage": None}
                      for j in range(3)]
        else:
            quotes = [
                {"text": _quote(i, j), "found": True, "checked_against": "page", "passage": _passage(i, j)}
                for j in range(3)
            ]
            if i == 1:
                quotes[2] = {"text": "a quote the page never had", "found": False, "checked_against": "page",
                             "passage": None, "reason": "not found in the text of page"}
        entry = {"id": _source_id(i), "url": _url(i), "title": f"Source {i}", "ingested": True, "quotes": quotes}
        if i < 4:
            entry["shared_with"] = [_source_id(k) for k in range(4) if k != i]
        entries.append(entry)
    return entries


def _audit(*, tiebreak: bool = True) -> dict:
    audit = {
        "analyst_verdict": "mixed", "auditor_verdict": "false" if tiebreak else "mixed",
        "analyst_confidence": "medium", "auditor_confidence": "high",
        "verdict_agrees": not tiebreak, "confidence_agrees": False, "needs_review": tiebreak,
        "auditor_reasoning": EVALUATOR_REASON, "evidence_gaps": ["gap one", "gap two"],
        "needs_review_reasons": ["verdicts differ"] if tiebreak else [],
        "pipeline_verdict": "mixed", "pipeline_confidence": "medium",
        "rule_applied": "tiebreaker-matched-analyst" if tiebreak else "agreed",
    }
    if tiebreak:
        audit.update({"tiebreaker_verdict": "mixed", "tiebreaker_confidence": "medium",
                      "tiebreaker_reasoning": TIEBREAKER_REASON})
    return audit


def _write_packet_claim(
    repo_root: Path,
    *,
    stem: str = STEM,
    verdict: str = "mixed",
    criteria_slug: str | None = "probe-criterion",
    restatement: dict | None | bool = True,
    tiebreak: bool = True,
    rejected: int = 32,
    refresh_previous: str | None = None,
    status: str = "draft",
    verdict_override: dict | None = None,
) -> Path:
    """A draft with 8 consulted sources, 3 quotes each, ``rejected`` rejected candidates and a full verdict chain."""
    write_entity(repo_root)
    for i in range(8):
        if i != 6:  # source 6 was consulted, not cited, and never written
            _write_source_file(repo_root, i)
    fm = {
        "title": STATEMENT, "statement": STATEMENT, "entity": ENTITY_REF, "topics": ["environmental-impact"],
        "verdict": verdict, "confidence": "medium", "verification_level": "partially-verified",
        "takeaway": "A takeaway line.", "seo_title": "Probe share",
    }
    if criteria_slug:
        fm["criteria_slug"] = criteria_slug
    fm.update({
        "status": status, "as_of": "2026-10-01",
        "sources": [_source_id(i) for i in range(8) if i != 6],
        "source_overrides": [
            {"source": _source_id(2), "independence": "unknown", "reason": OFF_ENTITY},
            {"source": _source_id(3), "independence": "first-party", "reason": ENTITY_MATCH},
        ],
        "tags": ["highlight"],
    })
    claim_path = repo_root / "research" / "claims" / ENTITY_REF / f"{stem}.md"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text(
        f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)}---\n\n"
        f"{ANALYST_FIRST_SENTENCE} A second sentence follows.\n",
        encoding="utf-8",
    )
    sidecar: dict = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m",
                         "agents": ["researcher", "ingestor", "analyst", "auditor", "tiebreaker", "restater"],
                         "run_id": RUN_ID},
        "models_used": {"analyst": "m", "auditor": "m"},
        "research": {
            "queries": ["probe energy report", "probe electricity share disputed"],
            "scorer_rationale": "Kept the energy reports; dropped off-topic pages.",
            "rejected": [
                {"url": f"https://rejected.example.com/r{k}", "title": f"Rejected {k}", "score": None,
                 "reason": SCORER_REASON}
                for k in range(rejected)
            ],
        },
        "sub_questions": [
            {"id": "sq1", "question": "Does the subject publish energy data?", "rationale": "first-party axis",
             "kind": "coverage", "queries": ["probe energy report"], "citations": [_source_id(0)]},
            {"id": "sq2", "question": "What shows the share was below 4%?", "rationale": "falsifier",
             "kind": "counter-evidence", "queries": ["probe electricity share disputed"], "citations": []},
        ],
        "sources_consulted": _sources_consulted(),
        "audit": _audit(tiebreak=tiebreak),
        "human_review": {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None},
    }
    if verdict_override is not None:
        sidecar["human_review"]["verdict_override"] = verdict_override
    if refresh_previous is not None:
        sidecar["refresh"] = {
            "refreshed_at": "2026-10-04T18:22:00+00:00",
            "previous": {"status": "published", "verdict": refresh_previous, "reviewed_at": "2026-05-11",
                         "reviewer": "reviewer@example.com", "sources": []},
            "dropped_sources": [],
        }
    if restatement is True:
        sidecar["restatement"] = _restatement_block()
    elif isinstance(restatement, dict):
        sidecar["restatement"] = restatement
    claim_path.with_suffix(".audit.yaml").write_text(
        yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )
    return claim_path


def _dr(repo_root: Path, *args: str, input: str | None = None):
    from orchestrator.cli import main

    return CliRunner().invoke(main, [*args, "--repo-root", str(repo_root)], input=input)


def _lines(output: str) -> list[str]:
    return click.unstyle(output).splitlines()


def _headings(lines: list[str]) -> list[tuple[int, int]]:
    """(line index, part number) of every part heading, in output order."""
    return [(i, int(m.group(1))) for i, line in enumerate(lines) if (m := HEADING.match(line))]


def _part(lines: list[str], n: int) -> list[str]:
    """The lines of part ``n``: from its heading to the next heading, item line or prompt."""
    start = next(i for i, p in _headings(lines) if p == n)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if HEADING.match(lines[i]) or ITEM_LINE.match(lines[i]) or "[a]pprove" in lines[i]:
            end = i
            break
    return lines[start:end]


def _prompt_index(lines: list[str]) -> int:
    return next(i for i, line in enumerate(lines) if "[a]pprove" in line)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _sidecar(claim_path: Path) -> dict:
    return yaml.safe_load(claim_path.with_suffix(".audit.yaml").read_text(encoding="utf-8"))


def _text_packet(repo_root: Path, ref: str = SLUG) -> str:
    result = _dr(repo_root, "review", "--format", "text", "--claim", ref)
    assert result.exit_code == 0, result.output
    return result.output


# --------------------------------------------------------------------------- #
# Part 1: the verdict chain                                                        #
# --------------------------------------------------------------------------- #

CHAIN_PREFIXES = ("Statement:", "Restated", "Analyst:", "Evaluator:", "Tie-breaker:", "Pipeline:")


def test_the_verdict_chain_prints_each_side_on_one_line_in_order(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    part1 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 1)]

    firsts = [next(i for i, line in enumerate(part1) if line.startswith(p)) for p in CHAIN_PREFIXES]
    assert firsts == sorted(firsts), part1
    for prefix in ("Statement:", "Analyst:", "Evaluator:", "Tie-breaker:", "Pipeline:"):
        assert sum(1 for line in part1 if line.startswith(prefix)) == 1, (prefix, part1)
    restated = [line for line in part1 if line.startswith("Restated #")]
    assert [int(re.match(r"Restated #(\d)", line).group(1)) for line in restated] == [1, 2, 3, 4, 5]

    by_prefix = {p: next(line for line in part1 if line.startswith(p)) for p in CHAIN_PREFIXES}
    assert STATEMENT[:40] in by_prefix["Statement:"]
    assert "mixed (medium)" in by_prefix["Analyst:"] and ANALYST_FIRST_SENTENCE in by_prefix["Analyst:"]
    assert "false (high)" in by_prefix["Evaluator:"] and EVALUATOR_REASON in by_prefix["Evaluator:"]
    assert "mixed (medium)" in by_prefix["Tie-breaker:"] and TIEBREAKER_REASON in by_prefix["Tie-breaker:"]
    assert "mixed (medium)" in by_prefix["Pipeline:"] and "tiebreaker-matched-analyst" in by_prefix["Pipeline:"]


def test_an_agreed_run_says_the_tiebreaker_did_not_run_and_no_restatement(tmp_path) -> None:
    _write_packet_claim(tmp_path, tiebreak=False, restatement=None)
    part1 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 1)]
    tie = next(line for line in part1 if line.startswith("Tie-breaker:"))
    assert "not run" in tie
    restated = [line for line in part1 if line.startswith("Restated")]
    assert len(restated) == 1 and "none" in restated[0], part1


def test_a_failed_restater_shows_restatement_unavailable_with_the_finding(tmp_path) -> None:
    _write_packet_claim(tmp_path, restatement=None)
    findings = tmp_path / "research" / "findings" / "2026"
    findings.mkdir(parents=True)
    (findings / f"{RUN_ID}.yaml").write_text(yaml.safe_dump({
        "run_id": RUN_ID, "date": "2026-10-01", "command": "dr draft",
        "claim_spec": {"statement": STATEMENT, "entity": ENTITY_REF},
        "claim_ref": SLUG, "config": {}, "models_used": {}, "step": "restate", "rule": "flaw-retry",
        "error": {"error_type": "invalid_output", "message": "bad"}, "attempts": 2, "outcome": "partial",
        "closed": None,
    }, sort_keys=False), encoding="utf-8")
    part1 = "\n".join(_part(_lines(_text_packet(tmp_path)), 1))
    assert f"restatement unavailable (finding {RUN_ID})" in part1.lower()


def test_a_pre_tiebreaker_sidecar_reads_the_analyst_verdict_as_the_pipelines(tmp_path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "pre_sp2", root)
    result = _dr(root, "review", "--format", "text", "--claim", "ecosia-ai/renewable-energy-hosting")
    assert result.exit_code == 0, result.output
    pipeline = next(line.strip() for line in _lines(result.output) if line.strip().startswith("Pipeline:"))
    audit = yaml.safe_load(
        (root / "research" / "claims" / "ecosia-ai" / "renewable-energy-hosting.audit.yaml").read_text()
    )["audit"]
    assert audit["analyst_verdict"] in pipeline
    assert "rule not recorded (pre-tie-breaker sidecar)" in pipeline


# --------------------------------------------------------------------------- #
# The walkthrough layout: parts 2 to 4, then part 1 and the header facts           #
# --------------------------------------------------------------------------- #


def test_the_walkthrough_ends_with_the_verdict_chain_and_header_facts_within_40_lines(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    result = _dr(tmp_path, "review", input="q\n")
    assert result.exit_code == 0, result.output
    lines = _lines(result.output)

    order = [p for _i, p in _headings(lines)]
    assert order == [2, 3, 4, 1], order
    prompt = _prompt_index(lines)
    item = next(i for i, line in enumerate(lines) if ITEM_LINE.match(line))
    part4_start = next(i for i, p in _headings(lines) if p == 4)
    part1_start = next(i for i, p in _headings(lines) if p == 1)
    assert part4_start < item < part1_start < prompt
    assert item == part1_start - 1, "the item line opens the bottom block"

    bottom = lines[item:prompt]
    assert len(bottom) <= 40, f"{len(bottom)} lines between the end of part 4 and the prompt"
    assert not any(HEADING.match(line) and not line.startswith("── 1.") for line in bottom)
    for label in HEADER_LABELS:
        assert any(re.match(rf"\s+{label}\s", line) for line in bottom), (label, bottom)
    assert all(len(line) <= PACKET_WIDTH for line in bottom), [line for line in bottom if len(line) > PACKET_WIDTH]

    # Everything from parts 2 to 4 is above the bottom block, for scroll-back.
    above = "\n".join(lines[:item])
    assert "https://rejected.example.com/r31" in above
    assert _passage(5, 2) in above
    assert "[r]estate" in lines[prompt] and "[v]iew" in lines[prompt]


def test_the_full_packet_keeps_a_long_statement_whole_while_the_bottom_block_cuts_it(tmp_path) -> None:
    from orchestrator.packet import build_packet, render_bottom, render_full

    claim_path = _write_packet_claim(tmp_path)
    packet = build_packet(claim_path, tmp_path)
    long_statement = "A long statement " + "that keeps going " * 12 + "and ends here."
    packet["verdict_chain"]["statement"] = long_statement
    assert long_statement in render_full(packet)
    bottom = click.unstyle(render_bottom(packet, 1, 1)).splitlines()
    assert long_statement not in "\n".join(bottom), "control: the bottom block cuts it"
    assert all(len(line) <= PACKET_WIDTH for line in bottom)


def test_the_v_key_pages_the_whole_packet_in_ranked_order(tmp_path, monkeypatch) -> None:
    import orchestrator.review_queue as review_queue_mod

    _write_packet_claim(tmp_path)
    capture = tmp_path / "paged.txt"
    script = tmp_path / "capture-pager.sh"
    script.write_text(f'#!/bin/sh\ncat > "{capture}"\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PAGER", str(script))
    monkeypatch.setattr(review_queue_mod, "_stdout_is_tty", lambda: True)

    result = _dr(tmp_path, "review", input="v\nq\n")
    assert result.exit_code == 0, result.output
    paged = capture.read_text(encoding="utf-8")
    assert [p for _i, p in _headings(paged.splitlines())] == [1, 2, 3, 4]

    text = _text_packet(tmp_path)
    assert paged.rstrip("\n") == text.rstrip("\n"), "v pages exactly what --format text prints"
    assert "\x1b[" not in paged, "the paged packet is plain text"


def test_format_text_with_a_claim_prints_the_whole_packet_in_ranked_order(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    lines = _lines(_text_packet(tmp_path))
    assert [p for _i, p in _headings(lines)] == [1, 2, 3, 4]
    part1 = "\n".join(_part(lines, 1))
    for label in HEADER_LABELS:
        assert label in part1


# --------------------------------------------------------------------------- #
# Part 2: quotes beside their passages                                             #
# --------------------------------------------------------------------------- #


def test_a_found_quote_prints_its_passage_and_the_archive_fragment_link(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    part2 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 2)]
    i = part2.index(f'[found] "{_quote(0, 0)}"')
    assert part2[i + 1] == f"passage: {_passage(0, 0)}"
    assert part2[i + 2] == f"open: {ARCHIVED}#:~:text=quote%200%2D0"
    # A source with no archived_url gets no link.
    j = part2.index(f'[found] "{_quote(2, 0)}"')
    assert part2[j + 1] == f"passage: {_passage(2, 0)}"
    assert not part2[j + 2].startswith("open:")


def test_a_quote_that_was_not_found_prints_its_reason(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    part2 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 2)]
    assert '[not found] "a quote the page never had": not found in the text of page' in part2


def test_a_cached_sources_quotes_show_not_rechecked(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    part2 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 2)]
    assert f'[not-rechecked] "{_quote(7, 0)}"' in part2


def test_each_consulted_source_is_marked_cited_or_not_and_written_or_not(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    part2 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 2)]
    assert any(line.startswith(f"[cited] {_source_id(0)}") for line in part2), part2
    six = next(line for line in part2 if _source_id(6) in line)
    assert six.startswith(f"[not cited] {_source_id(6)}") and "(no source file)" in six


def test_a_legacy_sidecar_renders_the_four_parts_from_the_source_files(tmp_path) -> None:
    """The SP3 card sidecars predate the packet keys: quotes come from the source files, marked not recorded."""
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "pre_sp2", root)
    result = _dr(root, "review", "--format", "json", "--claim", "ecosia-ai/renewable-energy-hosting")
    assert result.exit_code == 0, result.output
    (record,) = json.loads(result.output)
    for part in ("verdict_chain", "quotes", "independence", "search"):
        assert part in record, part
    checks = {q["checked_against"] for s in record["quotes"] for q in s["quotes"]}
    assert checks == {"not-recorded"}, checks
    assert any(s["quotes"] for s in record["quotes"])
    text = _dr(root, "review", "--format", "text", "--claim", "ecosia-ai/renewable-energy-hosting")
    assert [p for _i, p in _headings(_lines(text.output))] == [1, 2, 3, 4]
    assert "[not recorded]" in text.output


# --------------------------------------------------------------------------- #
# Part 3: source independence                                                      #
# --------------------------------------------------------------------------- #


def test_independence_shows_labels_override_reasons_and_shared_hosts(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    part3 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 3)]
    two = next(i for i, line in enumerate(part3) if line.startswith(_source_id(2)))
    assert "Publisher 2" in part3[two] and "article" in part3[two] and "unknown" in part3[two]
    block = []
    for line in part3[two + 1:]:
        if line.startswith("2026/src-"):
            break
        block.append(line)
    assert OFF_ENTITY in block
    shared = next(line for line in block if line.startswith("shared with:"))
    assert all(_source_id(k) in shared for k in (0, 1, 3)) and _source_id(4) not in shared
    assert any(ENTITY_MATCH in line for line in part3)
    five = next(i for i, line in enumerate(part3) if line.startswith(_source_id(5)))
    assert not any(line.startswith("shared with:") for line in part3[five + 1:five + 3])


# --------------------------------------------------------------------------- #
# Part 4: what the run searched for and rejected                                   #
# --------------------------------------------------------------------------- #


def test_search_lists_queries_with_the_counter_evidence_mark_and_rejected_candidates_with_reasons(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    part4 = [line.strip() for line in _part(_lines(_text_packet(tmp_path)), 4)]
    assert any("probe electricity share disputed" in line and "counter-evidence" in line for line in part4)
    rejected = [line for line in part4 if line.startswith("https://rejected.example.com/")]
    assert len(rejected) == 32
    assert all(SCORER_REASON in line for line in rejected)
    assert any(line.startswith("Scorer:") and "dropped off-topic pages" in line for line in part4)


# --------------------------------------------------------------------------- #
# --format json                                                                    #
# --------------------------------------------------------------------------- #


def test_format_json_prints_the_four_parts_and_the_queue_fields(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    result = _dr(tmp_path, "review", "--format", "json")
    assert result.exit_code == 0, result.output
    (record,) = json.loads(result.output)
    assert record["claim_slug"] == SLUG
    for key in ("restatement", "restatement_unavailable", "pipeline_verdict", "unreviewed_override"):
        assert key in record, key
    chain = record["verdict_chain"]
    assert chain["statement"] == STATEMENT
    assert chain["tiebreaker"]["reason"] == TIEBREAKER_REASON
    assert chain["pipeline_verdict"] == "mixed" and chain["rule_applied"] == "tiebreaker-matched-analyst"
    src0 = next(s for s in record["quotes"] if s["source"] == _source_id(0))
    assert src0["cited"] is True and src0["written"] is True
    q = src0["quotes"][0]
    assert q["passage"] == _passage(0, 0) and q["fragment_link"] == f"{ARCHIVED}#:~:text=quote%200%2D0"
    ind2 = next(s for s in record["independence"] if s["source"] == _source_id(2))
    assert OFF_ENTITY in ind2["override_reasons"]
    assert ind2["shared_with"] == [_source_id(k) for k in (0, 1, 3)]
    assert len(record["search"]["rejected"]) == 32


def test_format_json_with_a_claim_prints_one_record_for_a_claim_outside_the_queue(tmp_path) -> None:
    _write_packet_claim(tmp_path, status="published", criteria_slug="probe-criterion")
    queue = _dr(tmp_path, "review", "--format", "json")
    assert json.loads(queue.output) == []
    one = _dr(tmp_path, "review", "--format", "json", "--claim", SLUG)
    assert one.exit_code == 0, one.output
    (record,) = json.loads(one.output)
    assert record["claim_slug"] == SLUG


@pytest.mark.parametrize("args", [
    ("review", "--format", "json"),
    ("review", "--format", "text"),
    ("review", "--format", "json", "--claim", SLUG),
    ("review", "--format", "text", "--claim", SLUG),
], ids=["json-queue", "text-queue", "json-claim", "text-claim"])
def test_the_formats_write_nothing(tmp_path, args) -> None:
    _write_packet_claim(tmp_path)
    before = _snapshot(tmp_path)
    result = _dr(tmp_path, *args)
    assert result.exit_code == 0, result.output
    assert _snapshot(tmp_path) == before


# --------------------------------------------------------------------------- #
# The r key: pick a restatement, run nothing                                       #
# --------------------------------------------------------------------------- #


def _tripwire(monkeypatch) -> list[str]:
    import loop

    called: list[str] = []

    async def _fail(*_a, **_kw):
        called.append("loop")
        raise AssertionError("no run starts inside dr review")

    monkeypatch.setattr(loop, "run", _fail)
    monkeypatch.setattr(loop, "rerun", _fail)
    return called


def test_r_lists_the_candidates_records_the_pick_and_prints_the_command(tmp_path, monkeypatch) -> None:
    claim_path = _write_packet_claim(tmp_path)
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, "review", input="r\n2\nq\n")
    assert result.exit_code == 0, result.output
    assert called == []
    out = click.unstyle(result.output)
    # The listing the r key prints sits between the last key prompt and the number prompt,
    # so part 1's "Restated #n:" lines cannot satisfy it.
    asked = out.index("Candidate number")
    listing = out[out.rindex("[a]pprove", 0, asked):asked]
    for rank, text in enumerate(CANDIDATE_TEXTS, 1):
        assert re.search(rf"^\s*#{rank}\s.*{re.escape(text[:30])}", listing, re.M), (rank, listing)
    assert f"dr draft --restates {SLUG} --pick 2" in out
    assert _sidecar(claim_path)["restatement"]["picked"] == 2
    assert "status: draft" in claim_path.read_text(encoding="utf-8")


def test_r_with_a_blank_answer_records_nothing(tmp_path, monkeypatch) -> None:
    claim_path = _write_packet_claim(tmp_path)
    _tripwire(monkeypatch)
    before = claim_path.with_suffix(".audit.yaml").read_bytes()
    result = _dr(tmp_path, "review", input="r\n\nq\n")
    assert result.exit_code == 0, result.output
    assert claim_path.with_suffix(".audit.yaml").read_bytes() == before
    assert "--pick" not in result.output


def test_r_with_a_rank_that_is_not_listed_records_nothing(tmp_path, monkeypatch) -> None:
    claim_path = _write_packet_claim(tmp_path)
    _tripwire(monkeypatch)
    before = claim_path.with_suffix(".audit.yaml").read_bytes()
    result = _dr(tmp_path, "review", input="r\n9\nq\n")
    assert result.exit_code == 0, result.output
    assert claim_path.with_suffix(".audit.yaml").read_bytes() == before
    assert "--pick 9" not in result.output


def test_r_is_refused_on_a_sidecar_with_no_block(tmp_path, monkeypatch) -> None:
    claim_path = _write_packet_claim(tmp_path, restatement=None, tiebreak=False)
    _tripwire(monkeypatch)
    before = claim_path.with_suffix(".audit.yaml").read_bytes()
    result = _dr(tmp_path, "review", input="r\nq\n")
    assert result.exit_code == 0, result.output
    assert "no restatement candidates" in result.output.lower()
    assert claim_path.with_suffix(".audit.yaml").read_bytes() == before


def test_r_is_refused_when_the_restater_failed(tmp_path, monkeypatch) -> None:
    claim_path = _write_packet_claim(tmp_path, restatement=None)
    findings = tmp_path / "research" / "findings" / "2026"
    findings.mkdir(parents=True)
    (findings / f"{RUN_ID}.yaml").write_text(yaml.safe_dump({
        "run_id": RUN_ID, "date": "2026-10-01", "command": "dr draft",
        "claim_spec": {"statement": STATEMENT, "entity": ENTITY_REF}, "claim_ref": SLUG, "config": {},
        "models_used": {}, "step": "restate", "rule": "flaw-retry",
        "error": {"error_type": "invalid_output", "message": "bad"}, "attempts": 2, "outcome": "partial",
        "closed": None,
    }, sort_keys=False), encoding="utf-8")
    _tripwire(monkeypatch)
    before = claim_path.with_suffix(".audit.yaml").read_bytes()
    result = _dr(tmp_path, "review", input="r\nq\n")
    assert result.exit_code == 0, result.output
    assert f"restatement unavailable (finding {RUN_ID})" in result.output.lower()
    assert claim_path.with_suffix(".audit.yaml").read_bytes() == before


@pytest.mark.usefixtures("human_at_terminal")
def test_r_then_a_keeps_the_pick_so_the_printed_command_runs(tmp_path, monkeypatch) -> None:
    import orchestrator.review as review_mod
    from tests.loop_harness import analyst_args, auditor_args, scripted_agents

    class _GitEmail:
        stdout = "queue-test@example.com\n"

    monkeypatch.setattr(review_mod.subprocess, "run", lambda *a, **kw: _GitEmail())
    claim_path = _write_packet_claim(tmp_path)
    result = _dr(tmp_path, "review", input="r\n2\na\nq\n")
    assert result.exit_code == 0, result.output
    assert f"Approved {SLUG}" in result.output
    assert "status: published" in claim_path.read_text(encoding="utf-8")
    assert _sidecar(claim_path)["restatement"]["picked"] == 2

    with scripted_agents(analyst=analyst_args(verdict="true"), auditor=auditor_args(verdict="true")):
        draft = _dr(tmp_path, "draft", "--restates", SLUG, "--pick", "2", "--paid-dry-run", "--skip-wayback")
    assert draft.exit_code == 0, draft.output
    assert CANDIDATE_TEXTS[1] in draft.output


@pytest.mark.usefixtures("human_at_terminal")
@pytest.mark.parametrize("restated", [False, True])
def test_approve_keeps_a_picked_block_only_until_a_claim_restates_the_original(tmp_path, restated) -> None:
    claim_path = _write_packet_claim(tmp_path, restatement=_restatement_block(picked=2))
    if restated:
        other = claim_path.with_name("restated-claim.audit.yaml")
        other.write_text(yaml.safe_dump({"schema_version": 1, "restates": SLUG}), encoding="utf-8")
    result = _approve(tmp_path)
    assert result.exit_code == 0, result.output
    assert ("restatement" in _sidecar(claim_path)) is not restated


# --------------------------------------------------------------------------- #
# --approve's sign-off gate in place of dr publish's two refusals (test_publish.py:555, 624) #
# --------------------------------------------------------------------------- #


def _approve(repo_root: Path, *extra: str, ref: str = SLUG):
    return _dr(repo_root, "review", "--claim", ref, "--approve", "--reviewer", "r@example.org", *extra)


@pytest.mark.usefixtures("human_at_terminal")
def test_approve_refuses_a_refresh_whose_verdict_changed_without_a_correction(tmp_path) -> None:
    claim_path = _write_packet_claim(tmp_path, refresh_previous="false", restatement=None, tiebreak=False)
    before = (claim_path.read_bytes(), claim_path.with_suffix(".audit.yaml").read_bytes())
    result = _approve(tmp_path)
    assert result.exit_code != 0
    assert "--correction" in result.output
    assert (claim_path.read_bytes(), claim_path.with_suffix(".audit.yaml").read_bytes()) == before


@pytest.mark.usefixtures("human_at_terminal")
def test_approve_with_a_correction_publishes_and_records_it(tmp_path) -> None:
    from common.frontmatter import parse_frontmatter

    claim_path = _write_packet_claim(tmp_path, refresh_previous="false", restatement=None, tiebreak=False)
    result = _approve(tmp_path, "--correction", "Re-checked against the 2024 report.")
    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm["status"] == "published"
    assert fm["corrections"][0]["previous_verdict"] == "false"
    assert "refresh" not in _sidecar(claim_path)


@pytest.mark.usefixtures("human_at_terminal")
def test_approve_of_an_unchanged_refresh_publishes_and_closes_the_refresh(tmp_path) -> None:
    claim_path = _write_packet_claim(tmp_path, refresh_previous="mixed", restatement=None, tiebreak=False)
    result = _approve(tmp_path)
    assert result.exit_code == 0, result.output
    assert "status: published" in claim_path.read_text(encoding="utf-8")
    assert "refresh" not in _sidecar(claim_path)


@pytest.mark.usefixtures("human_at_terminal")
def test_approve_records_an_edited_verdict_as_the_reviewers_override(tmp_path) -> None:
    claim_path = _write_packet_claim(tmp_path, verdict="false", restatement=None, tiebreak=False)
    result = _approve(tmp_path)
    assert result.exit_code == 0, result.output
    review = _sidecar(claim_path)["human_review"]
    assert review["verdict_override"] == {"from": "mixed", "to": "false"}
    assert review["reviewer"] == "r@example.org"


def test_a_piped_approve_of_an_edited_verdict_writes_nothing(tmp_path) -> None:
    claim_path = _write_packet_claim(tmp_path, verdict="false", restatement=None, tiebreak=False)
    before = (claim_path.read_bytes(), claim_path.with_suffix(".audit.yaml").read_bytes())
    result = _approve(tmp_path)
    assert result.exit_code != 0
    # The refusal is the terminal gate's, not some other error (RE-AV review item 9).
    assert "needs a person at a terminal" in result.output, result.output
    assert (claim_path.read_bytes(), claim_path.with_suffix(".audit.yaml").read_bytes()) == before


def test_the_packet_names_an_unreviewed_override_before_approval(tmp_path) -> None:
    _write_packet_claim(tmp_path, verdict="false", restatement=None, tiebreak=False)
    part1 = "\n".join(_part(_lines(_text_packet(tmp_path)), 1))
    assert re.search(r"Override\s+pipeline mixed, claim false", part1), part1
    (record,) = json.loads(_dr(tmp_path, "review", "--format", "json", "--claim", SLUG).output)
    assert record["unreviewed_override"] == {"from": "mixed", "to": "false"}


def test_a_matching_recorded_override_shows_no_override_row(tmp_path) -> None:
    _write_packet_claim(tmp_path, verdict="false", restatement=None, tiebreak=False,
                        verdict_override={"from": "mixed", "to": "false"})
    part1 = "\n".join(_part(_lines(_text_packet(tmp_path)), 1))
    assert "Override" not in part1, part1
    (record,) = json.loads(_dr(tmp_path, "review", "--format", "json", "--claim", SLUG).output)
    assert record["unreviewed_override"] is None


def test_a_stale_recorded_override_still_shows_the_override_row(tmp_path) -> None:
    # The reviewer approved mixed -> true; the claim now says false, so that override no longer covers it.
    _write_packet_claim(tmp_path, verdict="false", restatement=None, tiebreak=False,
                        verdict_override={"from": "mixed", "to": "true"})
    part1 = "\n".join(_part(_lines(_text_packet(tmp_path)), 1))
    assert re.search(r"Override\s+pipeline mixed, claim false", part1), part1
    (record,) = json.loads(_dr(tmp_path, "review", "--format", "json", "--claim", SLUG).output)
    assert record["unreviewed_override"] == {"from": "mixed", "to": "false"}


@pytest.mark.usefixtures("human_at_terminal")
def test_the_a_key_on_a_refresh_with_a_changed_verdict_asks_for_the_correction(tmp_path, monkeypatch) -> None:
    import orchestrator.review as review_mod
    from common.frontmatter import parse_frontmatter

    class _GitEmail:
        stdout = "queue-test@example.com\n"

    # The walkthrough has no --reviewer; pin the git email fallback so CI runners without one pass.
    monkeypatch.setattr(review_mod.subprocess, "run", lambda *a, **kw: _GitEmail())
    claim_path = _write_packet_claim(tmp_path, refresh_previous="false", restatement=None, tiebreak=False)
    result = _dr(tmp_path, "review", input="a\nRe-checked.\nq\n")
    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm["status"] == "published" and fm["corrections"][0]["summary"] == "Re-checked."


# --------------------------------------------------------------------------- #
# Claim refs, grammar and the removed commands                                     #
# --------------------------------------------------------------------------- #


def test_a_bare_subject_claim_slug_resolves(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    result = _dr(tmp_path, "review", "--format", "json", "--claim", STEM)
    assert result.exit_code == 0, result.output
    (record,) = json.loads(result.output)
    assert record["claim_slug"] == SLUG


def test_an_ambiguous_bare_slug_is_refused(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    other = tmp_path / "research" / "claims" / "subjects" / "other-subject" / f"{STEM}.md"
    other.parent.mkdir(parents=True)
    shutil.copy(tmp_path / "research" / "claims" / f"{SLUG}.md", other)
    shutil.copy(tmp_path / "research" / "claims" / f"{SLUG}.audit.yaml", other.with_suffix(".audit.yaml"))
    result = _dr(tmp_path, "review", "--format", "json", "--claim", STEM)
    assert result.exit_code == 1
    assert "Ambiguous" in result.output and "subjects/other-subject" in result.output


@pytest.mark.usefixtures("human_at_terminal")
def test_a_sign_off_by_bare_slug_reports_the_resolved_path(tmp_path) -> None:
    _write_packet_claim(tmp_path)
    result = _dr(tmp_path, "review", "--claim", STEM, "--reviewer", "r@example.org")
    assert result.exit_code == 0, result.output
    assert f"research/claims/{SLUG}.audit.yaml" in result.output


@pytest.mark.parametrize("args", [
    ("review", "--approve"),
    ("review", "--archive"),
    ("review", "--correction", "x"),
    ("review", "--reviewer", "r@example.org"),
    ("review", "--notes", "x"),
    ("review", "--pr-url", "https://example.org/pr/1"),
    ("review", "--format", "json", "--claim", SLUG, "--approve"),
    ("review", "--format", "text", "--claim", SLUG, "--archive"),
    ("review", "--claim", SLUG, "--filter-entity", "subjects"),
], ids=["approve", "archive", "correction", "reviewer", "notes", "pr-url", "json-approve", "text-archive",
        "claim-filter"])
def test_review_grammar_refusals_are_usage_errors_that_write_nothing(tmp_path, args) -> None:
    _write_packet_claim(tmp_path)
    before = _snapshot(tmp_path)
    result = _dr(tmp_path, *args)
    assert result.exit_code == 2, result.output
    assert _snapshot(tmp_path) == before


def test_dr_help_lists_review_and_neither_publish_nor_review_queue() -> None:
    from orchestrator.cli import main

    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    names = set(re.findall(r"^ {2}([a-z][a-z-]+)\s", result.output, re.M))
    assert "review" in names
    assert "publish" not in names and "review-queue" not in names
    for gone in ("publish", "review-queue"):
        assert CliRunner().invoke(main, [gone, "--help"]).exit_code == 2


def test_review_help_names_the_walkthrough_keys_and_formats() -> None:
    from orchestrator.cli import main

    result = CliRunner().invoke(main, ["review", "--help"])
    assert result.exit_code == 0
    for word in ("--format", "--filter-entity", "--claim", "--approve", "--archive", "--correction"):
        assert word in result.output


# --------------------------------------------------------------------------- #
# The direct frontmatter write leaves review_queue                                 #
# --------------------------------------------------------------------------- #


def test_review_queue_has_no_direct_frontmatter_write() -> None:
    source = (PIPELINE_DIR / "orchestrator" / "review_queue.py").read_text(encoding="utf-8")
    assert "write_text(" not in source and "serialize_frontmatter" not in source
    assert "_apply_edits" not in source and "_format_header" not in source


def test_set_claim_fields_writes_the_five_editable_fields_and_refuses_others(tmp_path) -> None:
    from common.frontmatter import parse_frontmatter
    from orchestrator.persistence import set_claim_fields

    claim_path = _write_packet_claim(tmp_path)
    set_claim_fields(claim_path, {"takeaway": "New takeaway.", "tags": ["highlight", "energy"], "verdict": "false"})
    text = claim_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    assert fm["takeaway"] == "New takeaway." and fm["verdict"] == "false"
    assert "tags: [highlight, energy]" in text, "tags stay a flow list"
    assert body.strip().startswith(ANALYST_FIRST_SENTENCE)
    assert fm["statement"] == STATEMENT

    before = claim_path.read_bytes()
    with pytest.raises(ValueError):
        set_claim_fields(claim_path, {"statement": "rewritten"})
    assert claim_path.read_bytes() == before


# --------------------------------------------------------------------------- #
# Docs and schema                                                                  #
# --------------------------------------------------------------------------- #


def _operator_set() -> list[Path]:
    files = [REPO_ROOT / "AGENTS.md", REPO_ROOT / "CONTRIBUTING.md", REPO_ROOT / "docs" / "runbook.md",
             REPO_ROOT / "pipeline" / "README.md", REPO_ROOT / "tasks.py"]
    files += sorted((REPO_ROOT / "docs" / "architecture").glob("*.md"))
    files += sorted((REPO_ROOT / ".claude" / "skills").rglob("*.md"))
    files += sorted((REPO_ROOT / "scripts").glob("*.sh"))
    files += sorted((REPO_ROOT / "docs" / "plans").glob("*.md"))
    return [p for p in files if p.exists()]


def _shared_grep(paths: list[Path]) -> list[str]:
    pattern = re.compile(r"review-queue|dr publish")
    hits = []
    for path in paths:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # A completed or deferred plan's path inside a link names a file, not a command (plan § Spikes).
            if pattern.search(line) and "plans/completed/" not in line and "plans/deferred/" not in line:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{n}: {line.strip()[:80]}")
    return hits


def test_the_operator_docs_name_neither_removed_command() -> None:
    """The spike's shared grep: ``review-queue\\|dr publish`` over the operator set returns nothing."""
    assert _shared_grep([REPO_ROOT / "docs" / "plans" / "completed" / "pipeline-rebuild.md"]), "control: the plan names both"
    assert _shared_grep(_operator_set()) == []


_STALE_SIGN_OFF = re.compile(r"bare `dr review` records|research/claims/`? should go through PRs|\*\*Open a PR\.\*\*")


def test_no_operator_doc_describes_the_old_sign_off() -> None:
    """Bare ``dr review`` is the walkthrough, and research content is signed off there, not in a PR."""
    control = "- **Research content**: changes to `research/claims/` should go through PRs"
    assert _STALE_SIGN_OFF.search(control), "control: the pattern catches the old CONTRIBUTING line"
    hits = [f"{p.relative_to(REPO_ROOT)}:{n}" for p in _operator_set()
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if _STALE_SIGN_OFF.search(line)]
    assert hits == []
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Sign off at `dr review`" in contributing
    workflow = (REPO_ROOT / "docs" / "architecture" / "research-workflow.md").read_text(encoding="utf-8")
    assert "`dr review --claim <ref>` without `--approve` or `--archive` records a sign-off" in workflow


def test_research_flow_sign_off_section_has_no_pull_request_step() -> None:
    text = (REPO_ROOT / "docs" / "architecture" / "research-flow.md").read_text(encoding="utf-8")
    assert "## 5. Sign-off without a PR" in text
    assert "before and after PR" not in text
    lifecycle = text[text.index("## 1. Claim lifecycle"):text.index("## 2.")]
    assert "PR opened" not in lifecycle and "PR merged" not in lifecycle
    section5 = text[text.index("## 5. Sign-off without a PR"):text.index("## 6.")]
    assert "dr review" in section5 and "Open PR" not in section5


def test_the_runbook_restatement_section_uses_the_r_key() -> None:
    text = (REPO_ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    section = text[text.index("## Picking a restatement"):]
    section = section[:section.index("\n## ", 1)]
    assert "`r`" in section and "dr review" in section
    assert "audit.yaml" not in section, "the operator reads the candidates in the packet, not the sidecar"


def _audit_schema_block() -> str:
    source = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    start = source.index("const auditSchema = z.object({")
    return source[start:source.index("\n});", start)]


def _declaration(block: str, key: str) -> str:
    lines = block.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"  {key}:"))
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"  \w+:", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def test_the_site_schema_declares_the_packet_keys() -> None:
    block = _audit_schema_block()
    consulted = _declaration(block, "sources_consulted")
    for field in ("quotes:", "passage:", "found:", "checked_against:", "shared_with:"):
        assert field in consulted, f"sources_consulted lacks {field}"
    research = _declaration(block, "research")
    assert "rejected:" in research and "reason:" in research
    assert ".optional()" in research
    refresh = _declaration(block, "refresh")
    assert ".optional()" in refresh
    assert "level_clamp:" in _declaration(block, "pipeline_run")
    for key in ("analyst_record", "restatement"):
        assert ".optional()" in _declaration(block, key)
    assert "picked:" in _declaration(block, "restatement")
    audit = _declaration(block, "audit")
    for field in ("pipeline_verdict", "rule_applied", "tiebreaker_verdict", "tiebreaker_reasoning"):
        assert field in audit


def test_the_walkthrough_survives_a_claim_that_stops_parsing(tmp_path, monkeypatch) -> None:
    """A claim broken mid-walkthrough (the `o` editor returns at once) gives a notice, not a traceback."""
    import orchestrator.review_queue as review_queue_mod

    claim_path = _write_packet_claim(tmp_path)
    monkeypatch.setattr(
        review_queue_mod, "_preview", lambda path: path.write_text("---\ntitle: [unclosed\n---\n", encoding="utf-8"),
    )
    result = _dr(tmp_path, "review", input="p\nv\nq\n")
    assert result.exit_code == 0, result.output
    assert "Could not read the packet" in result.output
    assert claim_path.read_text(encoding="utf-8").startswith("---\ntitle: [unclosed")


# --------------------------------------------------------------------------- #
# Carried into RE-AW (Recheck) from the RE-AV (Review packet) review             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fmt", ["json", "text"])
def test_queue_format_reports_one_unreadable_packet_and_prints_the_rest(tmp_path, fmt) -> None:
    """Item 8: one bad sidecar must not abort the whole queue listing."""
    _write_packet_claim(tmp_path, stem="good-claim")
    bad = _write_packet_claim(tmp_path, stem="bad-claim")
    sidecar = _sidecar(bad)
    sidecar["sub_questions"] = 7  # item_for reads the claim; build_packet cannot
    bad.with_suffix(".audit.yaml").write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")

    result = _dr(tmp_path, "review", "--format", fmt)

    assert result.exit_code == 1, result.output
    assert f"{ENTITY_REF}/bad-claim" in result.stderr
    if fmt == "json":
        records = json.loads(result.stdout)
        assert [r["claim_slug"] for r in records] == [f"{ENTITY_REF}/good-claim"]
    else:
        assert f"{ENTITY_REF}/good-claim" in result.stdout


def test_part4_says_rejected_not_recorded_for_a_sidecar_without_the_key(tmp_path) -> None:
    """Item 10: an old sidecar has no research.rejected; the packet must not claim zero rejections."""
    claim_path = _write_packet_claim(tmp_path)
    sidecar = _sidecar(claim_path)
    del sidecar["research"]["rejected"]
    sidecar["research"]["urls_dropped"] = 30
    claim_path.with_suffix(".audit.yaml").write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")

    part4 = "\n".join(_part(_lines(_text_packet(tmp_path)), 4))

    assert "Rejected (0)" not in part4, part4
    assert "Rejected: not recorded (30 dropped)" in part4, part4


def test_part4_still_counts_an_empty_rejected_list(tmp_path) -> None:
    """Positive control for item 10: a recorded empty list is zero rejections."""
    _write_packet_claim(tmp_path, rejected=0)
    part4 = "\n".join(_part(_lines(_text_packet(tmp_path)), 4))
    assert "Rejected (0)" in part4, part4


def test_restatement_unavailable_is_null_in_json_when_no_restater_failed(tmp_path) -> None:
    """Item 12, first half: null, not an empty string."""
    _write_packet_claim(tmp_path, restatement=None)
    (record,) = json.loads(_dr(tmp_path, "review", "--format", "json", "--claim", SLUG).output)
    assert record["restatement_unavailable"] is None
    assert record["verdict_chain"]["restatement_unavailable"] is None


def test_a_stored_quote_wrapped_in_quote_marks_prints_with_one_pair(tmp_path) -> None:
    """Item 12, second half: on-disk key_quotes can carry their own wrapping marks (the Ecosia source)."""
    claim_path = _write_packet_claim(tmp_path)
    sidecar = _sidecar(claim_path)
    for entry in sidecar["sources_consulted"]:
        entry.pop("quotes", None)  # an old sidecar: the packet reads the source file's key_quotes
    claim_path.with_suffix(".audit.yaml").write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")
    source = tmp_path / "research" / "sources" / f"{_source_id(0)}.md"
    fm, body = source.read_text(encoding="utf-8").split("---\n", 2)[1:]
    data = yaml.safe_load(fm)
    data["key_quotes"] = ['"Renewable sources provide around 26% of global electricity."']
    source.write_text(f"---\n{yaml.safe_dump(data, sort_keys=False)}---\n{body}", encoding="utf-8")

    part2 = "\n".join(_part(_lines(_text_packet(tmp_path)), 2))

    assert "Renewable sources provide around 26% of global electricity." in part2, part2
    assert '""' not in part2, part2
