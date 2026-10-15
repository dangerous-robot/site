"""Acceptance tests for RE-AW (Recheck): `dr recheck`, pending drafts and their promotion.

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ SP5 (Recheck), "Tests that prove it"; design
``handoff/2026-10-14-re-aw-design.md``). Every case drives behaviour through a
public entry: the ``dr`` CLI under ``CliRunner`` with the agents on scripted
models (``tests/loop_harness.py``), ``loop.run`` wrapped by a spy that
delegates to it, the lint runner, or a public writer function in
``orchestrator.persistence``. Nothing here patches a private name under
``pipeline/loop/``.

Shapes pinned here (the design's § 1 and § 2):

- a pending draft of ``research/claims/<ref>.md`` is
  ``research/pending/<ref>.md`` plus its ``.audit.yaml``;
- ``dr recheck --due --dry-run`` prints one line per due claim,
  ``<ref>  due <YYYY-MM-DD>``, and nothing else that names a ref with ``due``;
- the batch prints one summary line per claim, starting with its ref;
- a re-fetched cached source carries ``sources_consulted[].recheck`` with
  ``refetched: true`` and fresh ``quotes`` checks;
- the packet record of a pending draft carries ``recheck`` with
  ``live_verdict``, ``pending_verdict``, ``verdict_changed``,
  ``quotes_found``, ``quotes_checked`` and ``refetched``, and its header
  says ``verdict unchanged, N of M quotes still found, K sources re-fetched``
  or ``verdict changed: <old> to <new>``.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from common.frontmatter import parse_frontmatter, serialize_frontmatter
from tests.loop_harness import (
    ENTITY_REF,
    PAGE_TEXT,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    scripted_agents,
    write_entity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
TODAY = datetime.date.today()
REVIEWER = "reviewer@example.org"
DUE_LINE = re.compile(r"^(\S+)\s+due (\d{4}-\d{2}-\d{2})\b")


def _days(n: int) -> str:
    return (TODAY + datetime.timedelta(days=n)).isoformat()


# --------------------------------------------------------------------------- #
# Fixtures                                                                         #
# --------------------------------------------------------------------------- #


def _ref(stem: str) -> str:
    return f"{ENTITY_REF}/{stem}"


def _claim_path(root: Path, stem: str, base: str = "claims") -> Path:
    return root / "research" / base / ENTITY_REF / f"{stem}.md"


def _sidecar_path(claim_path: Path) -> Path:
    return claim_path.with_suffix(".audit.yaml")


def _write_claim(
    root: Path,
    stem: str,
    *,
    base: str = "claims",
    statement: str = SENTENCE,
    status: str = "published",
    verdict: str = "mixed",
    as_of: str | datetime.date | None = None,
    next_due: str | datetime.date | None = None,
    cadence: int | None = None,
    sources: tuple[str, ...] = ("2026/old",),
    extra_fm: dict | None = None,
    sidecar_extra: dict | None = None,
    reviewed: bool = True,
) -> Path:
    """A claim file and a valid sidecar under ``research/<base>/``; return the claim path.

    ``as_of`` as a ``str`` is written quoted (the on-disk form); as a ``date``
    it is written as a YAML date.
    """
    write_entity(root)
    fm: dict = {
        "title": statement, "statement": statement, "entity": ENTITY_REF,
        "topics": ["environmental-impact"], "verdict": verdict, "confidence": "medium",
        "criteria_slug": "probe-criterion", "status": status,
        "as_of": as_of if as_of is not None else _days(-10),
        "sources": list(sources),
    }
    if next_due is not None:
        fm["next_recheck_due"] = next_due
    if cadence is not None:
        fm["recheck_cadence_days"] = cadence
    fm.update(extra_fm or {})
    path = _claim_path(root, stem, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)}---\n\nBody.\n", encoding="utf-8")
    sidecar = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst", "auditor"]},
        "sources_consulted": [],
        "audit": {
            "analyst_verdict": verdict, "auditor_verdict": verdict, "analyst_confidence": "medium",
            "auditor_confidence": "medium", "verdict_agrees": True, "confidence_agrees": True,
            "needs_review": False, "auditor_reasoning": "Agreed.", "evidence_gaps": [],
            "needs_review_reasons": [], "pipeline_verdict": verdict, "pipeline_confidence": "medium",
            "rule_applied": "agreed",
        },
        "human_review": {
            "reviewed_at": "2026-10-02" if reviewed else None,
            "reviewer": REVIEWER if reviewed else None,
            "notes": None, "pr_url": None,
        },
    }
    sidecar.update(sidecar_extra or {})
    _sidecar_path(path).write_text(yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _write_source(root: Path, sid: str, url: str, *, accessed: str, key_quotes: list[str] | None = None) -> Path:
    fm = {
        "url": url, "title": f"Stored {sid}", "publisher": "Stored Publisher", "accessed_date": accessed,
        "kind": "report", "independence": "independent", "summary": "A stored summary.",
    }
    if key_quotes:
        fm["key_quotes"] = list(key_quotes)
    path = root / "research" / "sources" / f"{sid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nBody.\n", encoding="utf-8")
    return path


def _dr(root: Path, *args: str, input: str | None = None):
    from orchestrator.cli import main

    return CliRunner().invoke(main, ["--model", "test", *args, "--repo-root", str(root)], input=input)


def _recheck(root: Path, *args: str):
    return _dr(root, "recheck", *args, "--skip-wayback")


def _fm(path: Path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8"))[0]


def _sidecar(claim_path: Path) -> dict:
    return yaml.safe_load(_sidecar_path(claim_path).read_text(encoding="utf-8"))


def _bytes(*paths: Path) -> tuple[bytes, ...]:
    return tuple(p.read_bytes() for p in paths)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _tripwire(monkeypatch) -> list[str]:
    """Make the public loop entry fail if a command reaches it."""
    import loop

    called: list[str] = []

    async def _run(*args, **kwargs):
        called.append("run")
        raise AssertionError("loop.run must not be called here")

    monkeypatch.setattr(loop, "run", _run)
    return called


def _date(value) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def _findings(root: Path) -> list[dict]:
    d = root / "research" / "findings"
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(d.rglob("*.yaml"))] if d.exists() else []


# --------------------------------------------------------------------------- #
# --due selection                                                                  #
# --------------------------------------------------------------------------- #


def test_due_dry_run_lists_the_due_claims_with_their_dates_and_calls_no_model(tmp_path, monkeypatch) -> None:
    # Selected: no next_recheck_due and as_of older than the 60-day default (quoted on disk).
    _write_claim(tmp_path, "old-as-of", as_of=_days(-90))
    # Skipped: as_of inside the cadence.
    _write_claim(tmp_path, "recent-as-of", as_of=_days(-10))
    # Skipped: a future next_recheck_due, whatever its as_of.
    _write_claim(tmp_path, "future-due", as_of=_days(-200), next_due=_days(30))
    # Selected: a past next_recheck_due, whatever its as_of (written as a YAML date).
    _write_claim(tmp_path, "past-due", as_of=TODAY - datetime.timedelta(days=1), next_due=_days(-5))
    # Selected by its own cadence: 30 days, as_of 40 days ago.
    _write_claim(tmp_path, "short-cadence", as_of=_days(-40), cadence=30)
    # Skipped: drafts and archived claims are not rechecked by --due.
    _write_claim(tmp_path, "old-draft", status="draft", as_of=_days(-200), reviewed=False)
    _write_claim(tmp_path, "old-archived", status="archived", as_of=_days(-200))
    # Skipped: a pending recheck already awaits review.
    _write_claim(tmp_path, "already-pending", as_of=_days(-200))
    _write_claim(tmp_path, "already-pending", base="pending", status="draft", reviewed=False)
    called = _tripwire(monkeypatch)
    before = _snapshot(tmp_path)

    result = _dr(tmp_path, "recheck", "--due", "--dry-run")

    assert result.exit_code == 0, result.output
    assert called == []
    listed = {m.group(1): m.group(2) for line in result.output.splitlines() if (m := DUE_LINE.match(line.strip()))}
    assert listed == {
        _ref("old-as-of"): _days(-30),
        _ref("past-due"): _days(-5),
        _ref("short-cadence"): _days(-10),
    }, result.output
    assert _snapshot(tmp_path) == before


def test_due_dry_run_skips_a_claim_whose_frontmatter_does_not_parse(tmp_path, monkeypatch) -> None:
    _write_claim(tmp_path, "old-as-of", as_of=_days(-90))
    bad = _claim_path(tmp_path, "malformed")
    bad.write_text("---\ntitle: [unclosed\nstatus: published\n---\nBody.\n", encoding="utf-8")
    _tripwire(monkeypatch)

    result = _dr(tmp_path, "recheck", "--due", "--dry-run")

    assert result.exit_code == 0, result.output
    listed = [m.group(1) for line in result.output.splitlines() if (m := DUE_LINE.match(line.strip()))]
    assert listed == [_ref("old-as-of")]


def test_due_dry_run_lists_nothing_when_no_claim_is_due(tmp_path, monkeypatch) -> None:
    _write_claim(tmp_path, "recent-as-of", as_of=_days(-10))
    _tripwire(monkeypatch)

    result = _dr(tmp_path, "recheck", "--due", "--dry-run")

    assert result.exit_code == 0, result.output
    assert not [line for line in result.output.splitlines() if DUE_LINE.match(line.strip())], result.output


# --------------------------------------------------------------------------- #
# The batch                                                                        #
# --------------------------------------------------------------------------- #

BATCH = {
    "claim-a": "Probe Subject data centers used more than 4% of US electricity in 2024",
    "claim-b": "Probe Subject data centers used more than 5% of US electricity in 2024",
    "claim-c": "Probe Subject data centers used more than 6% of US electricity in 2024",
}


def _analyst_failing_on(statement: str) -> FunctionModel:
    """An analyst that answers every claim but raises on the one whose prompt carries ``statement``."""
    args = analyst_args()

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        prompt = "\n".join(
            str(p.content) for m in messages for p in getattr(m, "parts", []) if isinstance(p, UserPromptPart)
        )
        if statement in prompt:
            raise RuntimeError("scripted analyst failure for one claim")
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(_fn)


def test_a_batch_with_one_abandoned_claim_writes_two_pending_drafts_one_finding_and_three_lines(
    tmp_path, monkeypatch,
) -> None:
    import loop

    live = {stem: _write_claim(tmp_path, stem, statement=s, as_of=_days(-90)) for stem, s in BATCH.items()}
    live_before = {stem: _bytes(p, _sidecar_path(p)) for stem, p in live.items()}
    sems: list[object] = []
    real_run = loop.run

    async def _spy(spec, config, *args, **kwargs):
        sems.append(kwargs.get("sem"))
        return await real_run(spec, config, *args, **kwargs)

    monkeypatch.setattr(loop, "run", _spy)

    with scripted_agents(analyst_model=_analyst_failing_on(BATCH["claim-b"])):
        result = _recheck(tmp_path, "--due")

    assert result.exit_code == 0, result.output
    pending = {stem: _claim_path(tmp_path, stem, "pending") for stem in BATCH}
    assert pending["claim-a"].exists() and _sidecar_path(pending["claim-a"]).exists()
    assert pending["claim-c"].exists() and _sidecar_path(pending["claim-c"]).exists()
    assert not pending["claim-b"].exists()
    for stem, p in live.items():
        assert _bytes(p, _sidecar_path(p)) == live_before[stem], stem
    (abandoned,) = _findings(tmp_path)
    assert abandoned["outcome"] == "abandoned"
    assert abandoned["claim_spec"]["statement"] == BATCH["claim-b"]
    summary = _summary_lines(result.output)
    assert all(len(summary[stem]) == 1 for stem in BATCH), result.output
    assert "abandoned" in summary["claim-b"][0].lower(), result.output
    # One line per claim: a batch does not add the pending draft's path.
    assert "Pending draft:" not in result.output
    # One LLM semaphore for the whole batch.
    assert len(sems) == 3
    assert sems[0] is not None and all(s is sems[0] for s in sems), sems


def _summary_lines(output: str) -> dict[str, list[str]]:
    """Each batch claim's summary lines: the lines that start with ``<ref>:``."""
    return {stem: [line for line in output.splitlines() if line.startswith(f"{_ref(stem)}:")] for stem in BATCH}


def test_a_batch_claim_whose_entity_file_is_missing_is_abandoned_with_a_finding_and_the_rest_run(
    tmp_path,
) -> None:
    """A claim the batch cannot start is a finding (rule config-fatal), not only a printed line."""
    live = {stem: _write_claim(tmp_path, stem, statement=s, as_of=_days(-90)) for stem, s in BATCH.items()}
    broken = live["claim-b"]
    broken.write_text(
        broken.read_text(encoding="utf-8").replace(f"entity: {ENTITY_REF}", "entity: subjects/missing-subject"),
        encoding="utf-8",
    )

    with scripted_agents():
        result = _recheck(tmp_path, "--due")

    assert result.exit_code == 0, result.output
    for stem in ("claim-a", "claim-c"):
        pending = _claim_path(tmp_path, stem, "pending")
        assert pending.exists() and _sidecar_path(pending).exists(), stem
    assert not _claim_path(tmp_path, "claim-b", "pending").exists()
    (finding,) = _findings(tmp_path)
    assert finding["claim_ref"] == _ref("claim-b")
    assert (finding["outcome"], finding["rule"], finding["step"]) == ("abandoned", "config-fatal", "research")
    assert finding["claim_spec"]["statement"] == BATCH["claim-b"]
    summary = _summary_lines(result.output)
    assert all(len(summary[stem]) == 1 for stem in BATCH), result.output
    assert summary["claim-b"][0] == f"{_ref('claim-b')}: abandoned (finding {finding['run_id']})"
    assert "--claim" not in result.output


def test_a_batch_claim_whose_run_raises_is_abandoned_with_a_finding_and_the_rest_run(tmp_path, monkeypatch) -> None:
    import loop

    for stem, s in BATCH.items():
        _write_claim(tmp_path, stem, statement=s, as_of=_days(-90))
    real_run = loop.run

    async def _spy(spec, config, *args, **kwargs):
        if spec.statement == BATCH["claim-b"]:
            raise RuntimeError("scripted failure outside the loop's steps")
        return await real_run(spec, config, *args, **kwargs)

    monkeypatch.setattr(loop, "run", _spy)

    with scripted_agents():
        result = _recheck(tmp_path, "--due")

    assert result.exit_code == 0, result.output
    assert _claim_path(tmp_path, "claim-a", "pending").exists()
    assert _claim_path(tmp_path, "claim-c", "pending").exists()
    (finding,) = _findings(tmp_path)
    assert finding["claim_ref"] == _ref("claim-b")
    assert (finding["outcome"], finding["rule"]) == ("abandoned", "config-fatal")
    assert finding["error"]["error_class"] == "RuntimeError"
    summary = _summary_lines(result.output)
    assert all(len(summary[stem]) == 1 for stem in BATCH), result.output
    assert summary["claim-b"][0] == f"{_ref('claim-b')}: abandoned (finding {finding['run_id']})"


# --------------------------------------------------------------------------- #
# dr recheck --claim: the pending draft                                            #
# --------------------------------------------------------------------------- #


def test_recheck_claim_writes_a_pending_draft_and_leaves_the_live_claim_alone(tmp_path) -> None:
    older = {"date": "2026-01-02", "summary": "Older fix.", "previous_verdict": "true"}
    live = _write_claim(
        tmp_path, "live-claim", as_of=_days(-90), cadence=45,
        extra_fm={"corrections": [older], "tags": ["highlight"], "seo_title": "Operator seo title"},
        sidecar_extra={"analyst_record": {
            "title": SENTENCE, "seo_title": "Analyst seo title", "verdict": "mixed",
            "takeaway": None, "cap_rationale": None,
        }},
    )
    before = _bytes(live, _sidecar_path(live))

    with scripted_agents():
        result = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    assert _bytes(live, _sidecar_path(live)) == before
    pending = _claim_path(tmp_path, "live-claim", "pending")
    assert pending.exists() and _sidecar_path(pending).exists()
    fm = _fm(pending)
    assert fm["status"] == "draft"
    assert fm["statement"] == SENTENCE
    # Operator fields come over from the live claim (RE-AK, Published fields survive the pipeline).
    assert [c["summary"] for c in fm["corrections"]] == ["Older fix."]
    assert fm["tags"] == ["highlight"]
    assert fm["seo_title"] == "Operator seo title"
    # The writer sets next_recheck_due from the claim's own cadence, which it keeps.
    assert fm["recheck_cadence_days"] == 45
    assert _date(fm["as_of"]) == TODAY
    assert _date(fm["next_recheck_due"]) == TODAY + datetime.timedelta(days=45)
    sidecar = _sidecar(pending)
    assert sidecar["human_review"]["reviewed_at"] is None
    assert sidecar["human_review"]["reviewer"] is None
    # The snapshot is written at promotion, not before the run.
    assert "refresh" not in sidecar


def test_recheck_claim_on_a_draft_is_a_usage_error_pointing_at_draft_force(tmp_path, monkeypatch) -> None:
    _write_claim(tmp_path, "a-draft", status="draft", reviewed=False)
    called = _tripwire(monkeypatch)
    before = _snapshot(tmp_path)

    result = _dr(tmp_path, "recheck", "--claim", _ref("a-draft"))

    assert result.exit_code == 2, result.output
    assert "dr draft --claim" in result.output
    assert called == []
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "args",
    [(), ("--dry-run",), ("--due", "--claim", "x/y"), ("--claim", "x/y", "--dry-run")],
    ids=["no-mode", "dry-run-alone", "two-modes", "dry-run-with-claim"],
)
def test_recheck_grammar_is_checked_before_any_model_call(tmp_path, monkeypatch, args) -> None:
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, "recheck", *args)
    assert result.exit_code == 2, result.output
    assert "No such command" not in result.output, result.output
    assert called == []


def test_a_cached_source_older_than_the_cadence_is_refetched_and_its_file_is_not_rewritten(tmp_path) -> None:
    """The page text comes from the search's raw_content (``ResearchOutput.prefetched_bodies``,
    kept for every research URL, cached or not); the test runs under ``respx.mock`` so a
    live GET fails loudly instead of reaching the network."""
    import respx

    on_page = "Probe Subject data centers used more than 4% of US electricity in 2024."
    assert on_page in PAGE_TEXT[URLS[0]]
    old = _write_source(tmp_path, "2026/stored-old", URLS[0], accessed=_days(-200),
                        key_quotes=[on_page, "A sentence the page never carried."])
    fresh = _write_source(tmp_path, "2026/stored-fresh", URLS[1], accessed=_days(-1),
                          key_quotes=["Third parties confirm the energy data it publishes"])
    files_before = _bytes(old, fresh)
    _write_claim(tmp_path, "live-claim", as_of=_days(-90), sources=("2026/stored-old", "2026/stored-fresh"))

    with respx.mock(assert_all_called=False), scripted_agents():
        result = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    assert _bytes(old, fresh) == files_before
    entries = {e["id"]: e for e in _sidecar(_claim_path(tmp_path, "live-claim", "pending"))["sources_consulted"]}
    refetched = entries["2026/stored-old"]
    assert refetched["recheck"]["refetched"] is True
    found = {q["text"]: q["found"] for q in refetched["quotes"]}
    assert found == {on_page: True, "A sentence the page never carried.": False}
    assert all(q["checked_against"] != "not-rechecked" for q in refetched["quotes"])
    kept = entries["2026/stored-fresh"]
    assert (kept.get("recheck") or {}).get("refetched") in (None, False)
    assert {q["checked_against"] for q in kept["quotes"]} == {"not-rechecked"}


def test_a_cached_source_that_refetches_as_a_pdf_keeps_its_quotes_unchecked(tmp_path) -> None:
    """A non-HTML page would read as text with none of the quotes in it; the quotes stay not-rechecked."""
    import httpx
    import respx

    from tests.loop_harness import fake_execute_searches

    old = _write_source(tmp_path, "2026/stored-pdf", URLS[0], accessed=_days(-200),
                        key_quotes=["Probe Subject data centers used more than 4% of US electricity in 2024."])
    _write_claim(tmp_path, "live-claim", as_of=_days(-90), sources=("2026/stored-pdf",))
    # No search raw_content for the stored URL, so the recheck fetches it.
    page_text = {u: t for u, t in PAGE_TEXT.items() if u != URLS[0]}

    with respx.mock(assert_all_called=False) as mock, scripted_agents(search=fake_execute_searches(page_text=page_text)):
        mock.get(URLS[0]).mock(return_value=httpx.Response(
            200, content=b"%PDF-1.7 binary", headers={"content-type": "application/pdf"},
        ))
        result = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    entries = {e["id"]: e for e in _sidecar(_claim_path(tmp_path, "live-claim", "pending"))["sources_consulted"]}
    entry = entries["2026/stored-pdf"]
    assert entry["recheck"]["refetched"] is False
    assert "not an HTML page" in entry["recheck"]["reason"]
    assert {q["checked_against"] for q in entry["quotes"]} == {"not-rechecked"}
    assert old.exists()


def _fail_once(monkeypatch, name: str) -> None:
    """Make the writer step ``name`` in ``orchestrator.persistence`` raise on its first call only."""
    import orchestrator.persistence as persistence

    real = getattr(persistence, name)
    calls = {"n": 0}

    def _wrapped(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(f"simulated {name} failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(persistence, name, _wrapped)


def _queue_paths(root: Path) -> list[str]:
    listed = _dr(root, "review", "--format", "json")
    assert listed.exit_code == 0 and listed.exception is None, listed.output
    return [r["path"] for r in json.loads(listed.output or "[]")]


def _due_refs(root: Path) -> list[str]:
    due = _dr(root, "recheck", "--due", "--dry-run")
    assert due.exit_code == 0, due.output
    return [m.group(1) for m in (DUE_LINE.match(line) for line in due.output.splitlines()) if m]


def _staging_dirs(root: Path) -> list[Path]:
    return [p for p in root.iterdir() if p.name.startswith(".dr-recheck-")]


WRITER_STEPS = ["persist_sources", "_write_claim_file", "_write_audit_sidecar"]


@pytest.mark.parametrize("failing_write", WRITER_STEPS)
def test_a_writer_failure_during_a_recheck_writes_no_pending_pair_and_the_claim_stays_due(
    tmp_path, monkeypatch, failing_write,
) -> None:
    """The plan's "Failed rerun of a claim that has been published or archived"
    row: nothing is written and a finding is recorded. The live pair keeps
    its bytes, no pending pair appears (so the queue does not list one and
    ``--approve`` has nothing to promote), the claim stays due, and
    ``dr findings`` lists the half-claim finding. A second run completes."""
    from orchestrator.persistence import promote_pending

    live = _write_claim(tmp_path, "live-claim", as_of=_days(-90))
    pending = _claim_path(tmp_path, "live-claim", "pending")
    before = _bytes(live, _sidecar_path(live))
    _fail_once(monkeypatch, failing_write)

    with scripted_agents():
        failed = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert failed.exit_code == 1
    assert f"{_ref('live-claim')}: failed (half-claim)" in failed.output
    assert _bytes(live, _sidecar_path(live)) == before
    assert not pending.exists() and not _sidecar_path(pending).exists()
    assert _staging_dirs(tmp_path) == []
    assert not any(p.startswith("research/pending/") for p in _queue_paths(tmp_path))
    assert _ref("live-claim") in _due_refs(tmp_path)
    listed = _dr(tmp_path, "findings")
    assert listed.exit_code == 0, listed.output
    assert "half-claim" in listed.output
    assert f"claim: {_ref('live-claim')}" in listed.output
    assert "Half-claims:" not in listed.output
    with pytest.raises(FileNotFoundError):
        promote_pending(live, tmp_path)

    with scripted_agents():
        again = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert again.exit_code == 0, again.output
    assert _bytes(live, _sidecar_path(live)) == before
    assert _fm(pending)["status"] == "draft"
    assert _date(_fm(pending)["as_of"]) == TODAY
    assert _sidecar(pending)["pipeline_run"]["ran_at"] != "2026-10-01T00:00:00+00:00"
    assert f"Pending draft: {pending.relative_to(tmp_path).as_posix()}" in again.output
    assert _ref("live-claim") not in _due_refs(tmp_path)


@pytest.mark.parametrize("failing_write", WRITER_STEPS)
def test_a_writer_failure_on_a_second_recheck_keeps_the_earlier_pending_pair(
    tmp_path, monkeypatch, failing_write,
) -> None:
    live = _write_claim(tmp_path, "live-claim", as_of=_days(-90))
    pending = _claim_path(tmp_path, "live-claim", "pending")
    with scripted_agents():
        first = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert first.exit_code == 0, first.output
    live_before = _bytes(live, _sidecar_path(live))
    pending_before = _bytes(pending, _sidecar_path(pending))
    _fail_once(monkeypatch, failing_write)

    # A different verdict, so a claim written over the earlier one would not match its bytes.
    with scripted_agents(
        analyst=analyst_args(verdict="false", confidence="medium"),
        auditor=auditor_args(verdict="false", confidence="medium"),
    ):
        failed = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert failed.exit_code == 1
    assert _bytes(live, _sidecar_path(live)) == live_before
    assert _bytes(pending, _sidecar_path(pending)) == pending_before
    assert _staging_dirs(tmp_path) == []


def test_a_recheck_stopped_between_its_moves_is_a_half_claim_dr_findings_lists(tmp_path, monkeypatch) -> None:
    """The one window left: the pending claim moved into place and its sidecar did not.
    It is not a half-done promotion, ``dr findings`` names the way back, and a
    second recheck completes the pair."""
    from orchestrator.persistence import half_claims, promotion_half_done

    live = _write_claim(tmp_path, "live-claim", as_of=_days(-90))
    pending = _claim_path(tmp_path, "live-claim", "pending")
    before = _bytes(live, _sidecar_path(live))
    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(pending))
        with scripted_agents():
            failed = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert failed.exit_code == 1
    assert _bytes(live, _sidecar_path(live)) == before
    assert pending.exists() and not _sidecar_path(pending).exists()
    assert _staging_dirs(tmp_path) == []
    assert promotion_half_done(live, tmp_path) is False
    assert half_claims(tmp_path)["pending_without_sidecar"] == [_ref("live-claim")]
    listed = _dr(tmp_path, "findings")
    assert "Half-claims:" in listed.output
    assert f"{_ref('live-claim')}: pending recheck with no sidecar; rerun dr recheck --claim {_ref('live-claim')}" in listed.output

    with scripted_agents():
        again = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert again.exit_code == 0, again.output
    assert _sidecar_path(pending).exists()
    assert half_claims(tmp_path)["pending_without_sidecar"] == []


def test_dr_findings_lists_a_staging_directory_a_killed_recheck_left(tmp_path) -> None:
    from orchestrator.persistence import half_claims

    write_entity(tmp_path)
    left = tmp_path / ".dr-recheck-abc123"
    (left / ENTITY_REF).mkdir(parents=True)

    assert half_claims(tmp_path)["staging_left"] == [".dr-recheck-abc123"]
    listed = _dr(tmp_path, "findings")
    assert ".dr-recheck-abc123: a recheck stopped while writing" in listed.output


def test_a_recheck_writes_in_the_one_order_then_moves_the_pair_into_place(tmp_path, monkeypatch) -> None:
    """The write order of ``dr recheck --claim``: the forced-rewrite check,
    sources, claim, sidecar, all outside ``research/``, then the claim and
    the sidecar moved into ``research/pending/``, the claim first."""
    import os

    import orchestrator.persistence as persistence

    _write_claim(tmp_path, "live-claim", as_of=_days(-90))
    pending = _claim_path(tmp_path, "live-claim", "pending")
    order: list[str] = []
    written_at: list[Path] = []
    for name in ("mark_forced_rewrite", "_write_source_files", "_write_claim_file", "_write_audit_sidecar"):
        real = getattr(persistence, name)

        def _wrapped(*args, _name=name, _real=real, **kwargs):
            order.append(_name)
            out = _real(*args, **kwargs)
            if _name == "_write_claim_file":
                written_at.append(Path(out))
            return out

        monkeypatch.setattr(persistence, name, _wrapped)
    real_replace = os.replace

    def _replace(src, dst, *args, **kwargs):
        order.append(f"move:{Path(dst).relative_to(tmp_path).as_posix()}")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", _replace)

    with scripted_agents():
        result = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    assert order == [
        "mark_forced_rewrite", "_write_source_files", "_write_claim_file", "_write_audit_sidecar",
        f"move:{pending.relative_to(tmp_path).as_posix()}",
        f"move:{_sidecar_path(pending).relative_to(tmp_path).as_posix()}",
    ]
    (staged,) = written_at
    assert (tmp_path / "research") not in staged.parents
    assert staged.name == pending.name
    assert ".dr-recheck-" not in pending.read_text(encoding="utf-8")
    assert ".dr-recheck-" not in _sidecar_path(pending).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# next_recheck_due on every claim write                                           #
# --------------------------------------------------------------------------- #


def test_dr_draft_writes_next_recheck_due_from_the_default_cadence(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents():
        result = _dr(tmp_path, "draft", "--entity", ENTITY_REF, SENTENCE, "--skip-wayback")

    assert result.exit_code == 0, result.output
    (path,) = sorted((tmp_path / "research" / "claims" / ENTITY_REF).glob("*.md"))
    fm = _fm(path)
    assert _date(fm["next_recheck_due"]) == _date(fm["as_of"]) + datetime.timedelta(days=60)


def test_a_forced_rewrite_of_a_draft_keeps_its_cadence_and_moves_next_recheck_due(tmp_path) -> None:
    path = _write_claim(tmp_path, "a-draft", status="draft", reviewed=False, cadence=30,
                        as_of=_days(-90), next_due=_days(-60))

    with scripted_agents():
        result = _dr(tmp_path, "draft", "--claim", _ref("a-draft"), "--force", "--skip-wayback")

    assert result.exit_code == 0, result.output
    fm = _fm(path)
    assert fm["recheck_cadence_days"] == 30
    assert _date(fm["next_recheck_due"]) == TODAY + datetime.timedelta(days=30)


# --------------------------------------------------------------------------- #
# Every write aimed at a published or archived claim lands at the pending location #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["published", "archived"])
def test_draft_claim_force_on_a_live_claim_is_a_usage_error_naming_recheck(tmp_path, monkeypatch, status) -> None:
    _write_claim(tmp_path, "live-claim", status=status)
    called = _tripwire(monkeypatch)
    before = _snapshot(tmp_path)

    result = _dr(tmp_path, "draft", "--claim", _ref("live-claim"), "--force", "--skip-wayback")

    assert result.exit_code == 2, result.output
    assert f"dr recheck --claim {_ref('live-claim')}" in result.output
    assert called == []
    assert _snapshot(tmp_path) == before


def test_draft_entity_force_onto_a_published_path_is_a_usage_error(tmp_path, monkeypatch) -> None:
    from common.utils import slugify

    stem = slugify(SENTENCE)
    _write_claim(tmp_path, stem)
    called = _tripwire(monkeypatch)
    before = _snapshot(tmp_path)

    result = _dr(tmp_path, "draft", "--entity", ENTITY_REF, SENTENCE, "--force", "--skip-wayback")

    assert result.exit_code == 2, result.output
    assert "dr recheck --claim" in result.output
    assert called == []
    assert _snapshot(tmp_path) == before


def test_draft_claim_force_on_a_blocked_claim_still_rewrites_it_as_a_draft(tmp_path) -> None:
    """Blocked claims are not live; only published and archived ones go to the pending location."""
    path = _write_claim(tmp_path, "blocked-claim", status="blocked",
                        extra_fm={"blocked_reason": "insufficient_sources"})

    with scripted_agents():
        result = _dr(tmp_path, "draft", "--claim", _ref("blocked-claim"), "--force", "--skip-wayback")

    assert result.exit_code == 0, result.output
    assert _fm(path)["status"] == "draft"
    assert not _claim_path(tmp_path, "blocked-claim", "pending").exists()


# --------------------------------------------------------------------------- #
# Promotion at dr review                                                           #
# --------------------------------------------------------------------------- #


def _pending_pair(
    root: Path,
    *,
    live_verdict: str = "true",
    pending_verdict: str = "false",
    live_sources: tuple[str, ...] = ("2026/a", "2026/b"),
    pending_sources: tuple[str, ...] = ("2026/b", "2026/c"),
    consulted: list[dict] | None = None,
    live_extra: dict | None = None,
) -> tuple[Path, Path]:
    live = _write_claim(root, "live-claim", verdict=live_verdict, as_of=_days(-90),
                        sources=live_sources, extra_fm=live_extra)
    pending = _write_claim(
        root, "live-claim", base="pending", status="draft", verdict=pending_verdict, as_of=_days(0),
        sources=pending_sources, reviewed=False, extra_fm=live_extra,
        sidecar_extra={"sources_consulted": consulted or []},
    )
    return live, pending


def test_promote_pending_moves_the_pair_over_the_live_claim_with_the_refresh_snapshot(tmp_path) -> None:
    from orchestrator.persistence import promote_pending

    live, pending = _pending_pair(tmp_path)
    pending_bytes = pending.read_bytes()

    promote_pending(live, tmp_path)

    assert not pending.exists() and not _sidecar_path(pending).exists()
    assert live.read_bytes() == pending_bytes
    sidecar = _sidecar(live)
    previous = sidecar["refresh"]["previous"]
    assert previous["status"] == "published"
    assert previous["verdict"] == "true"
    assert previous["reviewer"] == REVIEWER
    assert sidecar["refresh"]["dropped_sources"] == ["2026/a"]


def _approve(root: Path, *extra: str):
    return _dr(root, "review", "--claim", _ref("live-claim"), "--approve", "--reviewer", REVIEWER, *extra)


@pytest.mark.usefixtures("human_at_terminal")
def test_approve_promotes_a_changed_pending_recheck_with_a_correction(tmp_path) -> None:
    older = {"date": "2026-01-02", "summary": "Older fix.", "previous_verdict": "mixed"}
    live, pending = _pending_pair(tmp_path, live_extra={"corrections": [older], "tags": ["highlight"]})

    result = _approve(tmp_path, "--correction", "Re-checked: the share is now disputed.")

    assert result.exit_code == 0, result.output
    assert not pending.exists() and not _sidecar_path(pending).exists()
    fm = _fm(live)
    assert fm["status"] == "published"
    assert fm["verdict"] == "false"
    assert fm["tags"] == ["highlight"]
    assert [c["summary"] for c in fm["corrections"]] == [
        "Re-checked: the share is now disputed.", "Older fix.",
    ]
    assert fm["corrections"][0]["previous_verdict"] == "true"
    sidecar = _sidecar(live)
    assert sidecar["human_review"]["reviewer"] == REVIEWER
    assert sidecar["human_review"]["reviewed_at"] == TODAY.isoformat()
    # The new verdict is the pipeline's, so the sign-off records no override.
    assert sidecar["human_review"].get("verdict_override") is None
    assert "refresh" not in sidecar


@pytest.mark.usefixtures("human_at_terminal")
def test_approve_refuses_a_changed_pending_recheck_without_a_correction_and_moves_nothing(tmp_path) -> None:
    live, pending = _pending_pair(tmp_path)
    before = _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending))

    result = _approve(tmp_path)

    assert result.exit_code != 0
    assert "--correction" in result.output
    assert _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending)) == before


@pytest.mark.usefixtures("human_at_terminal")
def test_approve_promotes_an_unchanged_pending_recheck_without_a_correction(tmp_path) -> None:
    live, pending = _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed")

    result = _approve(tmp_path)

    assert result.exit_code == 0, result.output
    assert not pending.exists()
    fm = _fm(live)
    assert fm["status"] == "published"
    assert not fm.get("corrections")


def test_a_piped_approve_of_a_pending_recheck_moves_nothing(tmp_path) -> None:
    live, pending = _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed")
    before = _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending))

    result = _approve(tmp_path)

    assert result.exit_code != 0
    assert "needs a person at a terminal" in result.output
    assert _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending)) == before


@pytest.mark.usefixtures("human_at_terminal")
def test_a_plain_sign_off_of_a_pending_recheck_is_refused_pointing_at_approve(tmp_path) -> None:
    """A signed-off pending draft would leave the queue, and --due skips a claim
    with a pending draft, so nothing would list it again: only --approve takes it."""
    live, pending = _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed")
    before = _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending))

    result = _dr(tmp_path, "review", "--claim", _ref("live-claim"), "--reviewer", REVIEWER)

    assert result.exit_code != 0
    assert "--approve" in result.output
    assert _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending)) == before


def test_draft_claim_force_with_a_pending_pair_present_still_refuses_and_touches_neither(
    tmp_path, monkeypatch,
) -> None:
    """``dr draft --claim`` resolves the live claim only; the pending lookup belongs to ``dr review``."""
    live, pending = _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed")
    before = _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending))
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, "draft", "--claim", _ref("live-claim"), "--force", "--skip-wayback")

    assert result.exit_code == 2, result.output
    assert "dr recheck --claim" in result.output
    assert called == []
    assert _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending)) == before


def test_the_typed_back_slug_of_a_pending_recheck_is_the_live_ref(tmp_path, monkeypatch) -> None:
    import orchestrator.review as review_mod

    typed: list[str] = []
    monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(review_mod, "_prompt_slug", lambda verb, slug: typed.append(slug) or slug)
    _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed")

    result = _approve(tmp_path)

    assert result.exit_code == 0, result.output
    assert typed == [_ref("live-claim")]


def test_a_recheck_lists_only_cited_sources_and_promotion_reports_the_dropped_one(tmp_path) -> None:
    """RE-AF (Sub-question coverage and the cited source list), mined from the old
    ``test_cli.py`` refresh case (``TestClaimRefreshListsCitedSources``): the
    pending draft lists only the sources the analyst cites, and promotion's
    snapshot names the live source the recheck no longer cites."""
    from orchestrator.persistence import promote_pending

    # Both stored sources are found again by the research (URLS[0], URLS[1]), so both are consulted.
    _write_source(tmp_path, "2026/old", URLS[0], accessed=_days(-1))
    _write_source(tmp_path, "2026/d", URLS[1], accessed=_days(-1))
    live = _write_claim(tmp_path, "live-claim", as_of=_days(-90), sources=("2026/old", "2026/d"))

    with scripted_agents(analyst=analyst_args(cited_sources=["2026/d"])):
        result = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    pending = _claim_path(tmp_path, "live-claim", "pending")
    assert _fm(pending)["sources"] == ["2026/d"]
    consulted = {e["id"] for e in _sidecar(pending)["sources_consulted"]}
    assert "2026/old" in consulted

    promote_pending(live, tmp_path)

    assert _sidecar(live)["refresh"]["dropped_sources"] == ["2026/old"]


@pytest.mark.usefixtures("human_at_terminal")
def test_an_archived_claim_rechecks_into_a_pending_draft_and_promotes_without_a_correction(tmp_path) -> None:
    """An archived claim has no published verdict: promotion writes no snapshot and asks no correction."""
    live = _write_claim(tmp_path, "live-claim", status="archived", verdict="true", as_of=_days(-90))
    before = _bytes(live, _sidecar_path(live))

    with scripted_agents():
        result = _recheck(tmp_path, "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    assert _bytes(live, _sidecar_path(live)) == before
    pending = _claim_path(tmp_path, "live-claim", "pending")
    assert _fm(pending)["status"] == "draft"
    assert _fm(pending)["verdict"] != "true"
    review = _sidecar(pending)["human_review"]
    assert (review["reviewed_at"], review["reviewer"]) == (None, None)

    approved = _approve(tmp_path)

    assert approved.exit_code == 0, approved.output
    fm = _fm(live)
    assert fm["status"] == "published"
    assert not fm.get("corrections")
    sidecar = _sidecar(live)
    assert "refresh" not in sidecar
    assert sidecar["human_review"]["reviewer"] == REVIEWER


def _fail_replace_onto(monkeypatch, target: Path) -> None:
    """Make ``os.replace`` fail when it would land on ``target``; every other replace runs."""
    import os

    real = os.replace

    def _replace(src, dst, *args, **kwargs):
        if Path(dst) == target:
            raise OSError(f"simulated failure moving onto {target}")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", _replace)


@pytest.mark.usefixtures("human_at_terminal")
def test_a_promotion_that_fails_on_the_sidecar_move_leaves_the_live_pair_and_a_second_approve_completes(
    tmp_path, monkeypatch,
) -> None:
    live, pending = _pending_pair(tmp_path)
    live_before = _bytes(live, _sidecar_path(live))

    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(live))
        failed = _approve(tmp_path, "--correction", "Re-checked.")
    assert failed.exit_code != 0
    assert _bytes(live, _sidecar_path(live)) == live_before
    assert pending.exists() and _sidecar_path(pending).exists()

    again = _approve(tmp_path, "--correction", "Re-checked.")

    assert again.exit_code == 0, again.output
    assert not pending.exists() and not _sidecar_path(pending).exists()
    fm = _fm(live)
    assert (fm["status"], fm["verdict"]) == ("published", "false")
    assert fm["corrections"][0]["previous_verdict"] == "true"
    assert _sidecar(live)["human_review"]["reviewer"] == REVIEWER


@pytest.mark.usefixtures("human_at_terminal")
def test_a_promotion_that_fails_on_the_claim_move_keeps_the_snapshot_and_a_second_approve_completes(
    tmp_path, monkeypatch,
) -> None:
    """The RE-AK (Published fields survive the pipeline) crash case for promotion:
    the live claim keeps its bytes, the moved sidecar keeps the sign-off in its
    snapshot, and a second ``--approve`` finishes the move and the approval."""
    live, pending = _pending_pair(tmp_path)
    live_claim_before = live.read_bytes()

    with monkeypatch.context() as m:
        _fail_replace_onto(m, live)
        failed = _approve(tmp_path, "--correction", "Re-checked.")
    assert failed.exit_code != 0
    assert live.read_bytes() == live_claim_before
    assert _fm(live)["status"] == "published"
    assert _sidecar(live)["refresh"]["previous"]["reviewer"] == REVIEWER
    assert pending.exists() and not _sidecar_path(pending).exists()

    again = _approve(tmp_path, "--correction", "Re-checked.")

    assert again.exit_code == 0, again.output
    assert not pending.exists()
    fm = _fm(live)
    assert (fm["status"], fm["verdict"]) == ("published", "false")
    assert fm["corrections"][0]["previous_verdict"] == "true"
    sidecar = _sidecar(live)
    assert sidecar["human_review"]["reviewer"] == REVIEWER
    assert "refresh" not in sidecar


def test_a_half_done_promotion_names_the_way_back_and_the_queue_does_not_crash(tmp_path, monkeypatch) -> None:
    """The queue does not list a pending claim whose sidecar moved, so the failed approval says to rerun it."""
    import orchestrator.review as review_mod

    monkeypatch.setattr(review_mod, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(review_mod, "_prompt_slug", lambda verb, slug: slug)
    live, pending = _pending_pair(tmp_path)
    with monkeypatch.context() as m:
        _fail_replace_onto(m, live)
        failed = _approve(tmp_path, "--correction", "Re-checked.")
    assert failed.exit_code != 0
    assert "run the same --approve again" in failed.output
    assert pending.exists() and not _sidecar_path(pending).exists()

    listed = _dr(tmp_path, "review", "--format", "json")
    walk = _dr(tmp_path, "review", input="q\n")

    assert listed.exit_code == 0 and listed.exception is None, listed.output
    assert walk.exit_code == 0 and walk.exception is None, walk.output


@pytest.mark.usefixtures("human_at_terminal")
def test_a_recheck_after_a_half_done_promotion_keeps_the_prior_sign_off_in_the_snapshot(
    tmp_path, monkeypatch,
) -> None:
    from orchestrator.persistence import promote_pending

    live, pending = _pending_pair(tmp_path)
    live_claim_before = live.read_bytes()
    with monkeypatch.context() as m:
        _fail_replace_onto(m, live)
        assert _approve(tmp_path, "--correction", "Re-checked.").exit_code != 0

    with scripted_agents():
        rerun = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert rerun.exit_code == 0, rerun.output
    assert live.read_bytes() == live_claim_before
    assert _sidecar_path(pending).exists()

    promote_pending(live, tmp_path)

    refresh = _sidecar(live)["refresh"]
    assert refresh["previous"]["reviewer"] == REVIEWER
    assert refresh["previous"]["verdict"] == "true"
    assert not pending.exists() and not _sidecar_path(pending).exists()

    done = _approve(tmp_path, "--correction", "Re-checked.")
    assert done.exit_code == 0, done.output
    assert _fm(live)["status"] == "published"
    assert _sidecar(live)["human_review"]["reviewer"] == REVIEWER


# --------------------------------------------------------------------------- #
# The r key on a pending recheck                                                   #
# --------------------------------------------------------------------------- #

PENDING_CANDIDATES = [
    "Probe Subject data centers used about 4% of US electricity in 2023.",
    "Probe Subject data centers used more than 3% of US electricity in 2024.",
]
LIVE_CANDIDATES = [
    "Probe Subject publishes its data center electricity use every year.",
    "Probe Subject's electricity share rose between 2020 and 2024.",
]


def _restatement(texts: list[str], picked: int | None = None) -> dict:
    return {
        "schema_version": 1, "model": "test", "trigger": "tie-broken",
        "original": {"statement": SENTENCE, "verdict": "mixed", "confidence": "medium"},
        "pool": {"consulted": 4, "on_disk": 0, "sent": 4},
        "why_unverified": "quantifier-unsupported", "why_unverified_note": "A range, not a floor.",
        "candidates": [
            {"rank": i + 1, "text": t, "frame": "narrowed", "expected_verdict": "true",
             "expected_confidence": "medium", "verification_level_estimate": "independently-verified",
             "decisiveness": 4 - i, "needs_new_research": False, "supporting": [], "contradicting": [],
             "rationale": "Report 1 says so."}
            for i, t in enumerate(texts)
        ],
        "dropped": [],
        "picked": picked,
    }


def test_r_on_a_pending_recheck_records_the_pick_there_and_the_printed_command_reads_it(
    tmp_path, monkeypatch,
) -> None:
    """``dr draft --restates <ref> --pick <n>`` reads candidate n from the sidecar the
    pick was recorded on: the pending one, not an older kept pick on the live one."""
    live, pending = _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed")
    for path, block in ((live, _restatement(LIVE_CANDIDATES, picked=2)), (pending, _restatement(PENDING_CANDIDATES))):
        data = _sidecar(path)
        data["restatement"] = block
        _sidecar_path(path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    live_before = _bytes(live, _sidecar_path(live))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    walk = _dr(tmp_path, "review", input="r\n2\nq\n")

    assert walk.exit_code == 0, walk.output
    assert f"dr draft --restates {_ref('live-claim')} --pick 2" in walk.output
    assert _sidecar(pending)["restatement"]["picked"] == 2
    assert _bytes(live, _sidecar_path(live)) == live_before

    with scripted_agents():
        dry = _dr(tmp_path, "draft", "--restates", _ref("live-claim"), "--pick", "2", "--dry-run", "--skip-wayback")
    assert dry.exit_code == 0, dry.output
    assert PENDING_CANDIDATES[1] in dry.output
    assert LIVE_CANDIDATES[1] not in dry.output

    with scripted_agents():
        real = _dr(tmp_path, "draft", "--restates", _ref("live-claim"), "--pick", "2", "--skip-wayback")
    assert real.exit_code == 0, real.output
    restated = [p for p in (tmp_path / "research" / "claims" / ENTITY_REF).glob("*.audit.yaml")
                if p.name != "live-claim.audit.yaml"]
    assert [yaml.safe_load(p.read_text(encoding="utf-8")).get("restates") for p in restated] == [_ref("live-claim")]
    assert _bytes(live, _sidecar_path(live)) == live_before
    assert _sidecar(pending)["restatement"]["picked"] == 2


# --------------------------------------------------------------------------- #
# dr step-audit --write never writes a live claim's sidecar                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["published", "archived"])
def test_step_audit_write_on_a_live_claim_is_a_usage_error_naming_recheck(tmp_path, monkeypatch, status) -> None:
    import loop

    _write_claim(tmp_path, "live-claim", status=status)
    called: list[str] = []

    async def _rerun(*_a, **_kw):
        called.append("rerun")
        raise AssertionError("loop.rerun must not be called here")

    monkeypatch.setattr(loop, "rerun", _rerun)
    before = _snapshot(tmp_path)

    result = _dr(tmp_path, "step-audit", "--claim", _ref("live-claim"), "--write")

    assert result.exit_code == 2, result.output
    assert f"dr recheck --claim {_ref('live-claim')}" in result.output
    assert called == []
    assert _snapshot(tmp_path) == before


def test_step_audit_write_over_an_entity_writes_drafts_and_leaves_live_sidecars_alone(tmp_path) -> None:
    live = _write_claim(tmp_path, "live-claim", status="published")
    draft = _write_claim(tmp_path, "a-draft", status="draft", reviewed=False)
    live_before = _bytes(live, _sidecar_path(live))
    draft_before = _sidecar_path(draft).read_bytes()

    with scripted_agents():
        # --entity matches the claim directory name.
        result = _dr(tmp_path, "step-audit", "--entity", ENTITY_REF.split("/")[-1], "--write")

    assert result.exit_code == 0, result.output
    assert _bytes(live, _sidecar_path(live)) == live_before
    assert f"dr recheck --claim {_ref('live-claim')}" in result.output
    assert _sidecar_path(draft).read_bytes() != draft_before


# --------------------------------------------------------------------------- #
# The pending draft in the review queue                                            #
# --------------------------------------------------------------------------- #

RECHECK_UNCHANGED = re.compile(r"verdict unchanged, (\d+) of (\d+) quotes still found, (\d+) sources? re-fetched")


def _consulted() -> list[dict]:
    """Two cited sources: one re-fetched (2 of 3 quotes found), one fresh (1 of 1 found)."""
    return [
        {"id": "2026/b", "url": "https://example.org/b", "title": "B", "ingested": True,
         "quotes": [
             {"text": "b one", "found": True, "checked_against": "page", "passage": "b one."},
             {"text": "b two", "found": True, "checked_against": "page", "passage": "b two."},
             {"text": "b three", "found": False, "checked_against": "page", "passage": None,
              "reason": "not found in the fetched page text"},
         ],
         "recheck": {"refetched": True, "checked_at": TODAY.isoformat(), "archive": "skipped", "reason": None}},
        {"id": "2026/c", "url": "https://example.org/c", "title": "C", "ingested": True,
         "quotes": [{"text": "c one", "found": True, "checked_against": "page", "passage": "c one."}]},
    ]


def test_the_queue_lists_a_pending_recheck_under_its_live_ref(tmp_path) -> None:
    _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed", consulted=_consulted())

    result = _dr(tmp_path, "review", "--format", "json")

    assert result.exit_code == 0, result.output
    records = json.loads(result.output)
    (record,) = [r for r in records if r["claim_slug"] == _ref("live-claim")]
    assert record["path"].startswith("research/pending/")
    assert record["recheck"] == {
        "live_verdict": "mixed", "pending_verdict": "mixed", "verdict_changed": False,
        "quotes_found": 3, "quotes_checked": 4, "quotes_not_rechecked": 0, "refetched": 1,
    }


def test_the_pending_header_says_verdict_unchanged_with_the_counts(tmp_path) -> None:
    _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed", consulted=_consulted())

    result = _dr(tmp_path, "review", "--format", "text", "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    m = RECHECK_UNCHANGED.search(result.output)
    assert m is not None, result.output
    assert m.groups() == ("3", "4", "1")


def test_the_pending_header_names_the_quotes_it_did_not_recheck(tmp_path) -> None:
    """A cited source inside its cadence keeps its quotes unchecked; the header says how many."""
    consulted = _consulted()
    consulted[1]["quotes"].append({"text": "c two", "found": None, "checked_against": "not-rechecked", "passage": None})
    _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed", consulted=consulted)

    result = _dr(tmp_path, "review", "--format", "text", "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    m = RECHECK_UNCHANGED.search(result.output)
    assert m is not None and m.groups() == ("3", "4", "1"), result.output
    assert "1 quotes not rechecked" in result.output


def test_the_pending_header_says_verdict_changed(tmp_path) -> None:
    _pending_pair(tmp_path, live_verdict="true", pending_verdict="false", consulted=_consulted())

    result = _dr(tmp_path, "review", "--format", "text", "--claim", _ref("live-claim"))

    assert result.exit_code == 0, result.output
    assert "verdict changed: true to false" in result.output


def test_delete_in_the_walkthrough_removes_only_the_pending_pair(tmp_path, monkeypatch) -> None:
    # On macOS `d` moves files to ~/.Trash: keep them out of the real one.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    live, pending = _pending_pair(tmp_path, live_verdict="mixed", pending_verdict="mixed")
    before = _bytes(live, _sidecar_path(live))

    result = _dr(tmp_path, "review", input="d\ny\n")

    assert result.exit_code == 0, result.output
    assert not pending.exists() and not _sidecar_path(pending).exists()
    assert _bytes(live, _sidecar_path(live)) == before


# --------------------------------------------------------------------------- #
# Lint reads the pending location; the site does not                              #
# --------------------------------------------------------------------------- #


def test_lint_counts_a_source_cited_only_by_a_pending_draft_as_referenced(tmp_path) -> None:
    from linter.runner import run_all_checks

    _write_source(tmp_path, "2026/only-pending", "https://example.org/only-pending", accessed=_days(-1))
    _write_source(tmp_path, "2026/live-source", "https://example.org/live-source", accessed=_days(-1))
    _write_claim(tmp_path, "live-claim", sources=("2026/live-source",))
    _write_claim(tmp_path, "live-claim", base="pending", status="draft", reviewed=False,
                 sources=("2026/only-pending", "2026/missing-id"))

    issues, _checked = run_all_checks(tmp_path)

    unreferenced = [i for i in issues if i.check_id == "unreferenced-source"]
    assert not [i for i in unreferenced if "only-pending" in i.path], unreferenced
    broken = [i for i in issues if i.check_id == "broken-source-ref"]
    assert any("research/pending" in i.path and "missing-id" in i.message for i in broken), broken


def test_lint_positive_control_a_source_nobody_cites_is_unreferenced(tmp_path) -> None:
    from linter.runner import run_all_checks

    _write_source(tmp_path, "2026/nobody", "https://example.org/nobody", accessed=_days(-1))
    _write_claim(tmp_path, "live-claim", sources=())

    issues, _checked = run_all_checks(tmp_path)

    assert any(i.check_id == "unreferenced-source" and "nobody" in i.path for i in issues)


def test_the_site_claims_loader_reads_research_claims_only() -> None:
    """The site build ignores the pending location: its claims loader walks research/claims alone.

    The verify step also runs ``npm run build`` with a deliberately invalid
    pending draft present (design § 7).
    """
    config = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    assert "nodePath.resolve('research/claims')" in config
    assert "research/pending" not in config
    assert not list((REPO_ROOT / "src").rglob("*pending*.astro"))


def test_the_recheck_sidecar_key_is_declared_in_the_site_schema() -> None:
    config = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    sources_block = config[config.index("sources_consulted"):]
    assert re.search(r"\brecheck\s*:", sources_block), "sources_consulted[].recheck is not declared"


# --------------------------------------------------------------------------- #
# dr recheck --sources (the folded wayback-backfill)                              #
# --------------------------------------------------------------------------- #


def test_dr_help_lists_recheck_and_no_wayback_backfill() -> None:
    from orchestrator.cli import main

    top = CliRunner().invoke(main, ["--help"])
    assert top.exit_code == 0
    assert "recheck" in top.output
    assert "wayback-backfill" not in top.output
    gone = CliRunner().invoke(main, ["wayback-backfill", "--help"])
    assert gone.exit_code != 0


def test_recheck_sources_reports_key_quotes_missing_from_the_live_page(tmp_path) -> None:
    import httpx
    import respx

    url = "https://example.org/quoted"
    page = "<html><body><p>The stored page says the share was four percent.</p></body></html>"
    archived = "https://web.archive.org/web/20260101000000/https://example.org/quoted"
    path = _write_source(tmp_path, "2026/quoted", url, accessed=_days(-200),
                         key_quotes=["the share was four percent", "a line that was removed"])
    text = path.read_text(encoding="utf-8").replace(f"url: {url}\n", f"url: {url}\narchived_url: {archived}\n")
    path.write_text(text, encoding="utf-8")
    before = path.read_bytes()

    with respx.mock as mock:
        mock.get(url).mock(return_value=httpx.Response(200, text=page))
        mock.head(archived.replace("/https://", "id_/https://", 1)).mock(
            return_value=httpx.Response(200, headers={"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT"})
        )
        result = _dr(tmp_path, "recheck", "--sources", "2026/quoted")

    assert result.exit_code == 0, result.output
    assert "1 of 2 key quotes found" in result.output
    assert "a line that was removed" in result.output
    # Only archived_url may change on --sources; here the link held, so nothing changes.
    assert path.read_bytes() == before


# --------------------------------------------------------------------------- #
# Carried from RE-AV (Review packet): CI job count in the docs (item 4)           #
# --------------------------------------------------------------------------- #


def test_research_workflow_names_the_ci_job_count_ci_yml_has() -> None:
    ci = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    jobs = list(ci["jobs"])
    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    doc = (REPO_ROOT / "docs" / "architecture" / "research-workflow.md").read_text(encoding="utf-8")
    m = re.search(r"whose (\w+) jobs \(([^)]*)\)", doc)
    if m is None:
        # The count was dropped: the doc must not name a job count at all.
        assert not re.search(r"\b(two|three|four|five|six) jobs\b", doc)
        return
    assert m.group(1) == words[len(jobs)], (m.group(0), jobs)
    named = re.findall(r"`([a-z0-9-]+)`", m.group(2))
    assert sorted(named) == sorted(jobs)
