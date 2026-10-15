"""Acceptance tests for RE-AW (Recheck): `dr recheck`, pending drafts and their promotion.

Written before the implementation (plan ``docs/plans/completed/pipeline-rebuild.md``
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



def test_the_seeded_live_sidecar_key_is_declared_in_the_site_schema() -> None:
    from orchestrator.persistence import SEEDED_LIVE_KEY

    config = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    assert re.search(rf"^\s*{SEEDED_LIVE_KEY}\s*:", config, re.MULTILINE), f"{SEEDED_LIVE_KEY} is not declared"

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


# --------------------------------------------------------------------------- #
# Carried from RE-AW (Recheck) review into RE-AX (Fold side tools)                 #
# (numbers are the SP5 open-majors list in handoff/2026-10-14-pipeline-rebuild.md) #
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("human_at_terminal")
def test_promotion_keeps_corrections_and_tags_edited_on_the_live_claim_after_the_recheck(tmp_path) -> None:
    """Items 6 and 14, RE-AK (Published fields survive the pipeline): `corrections` and `tags`
    edited on the live claim after the recheck seeded its pending pair survive promotion, and
    the approval's own correction is added on top, newest first."""
    first = {"date": "2026-09-01", "summary": "An older correction.", "previous_verdict": "mostly-true"}
    later = {"date": "2026-10-10", "summary": "Edited on the live claim after the recheck.",
             "previous_verdict": "mixed"}
    live = _write_claim(tmp_path, "live-claim", verdict="true", as_of=_days(-90),
                        extra_fm={"corrections": [first], "tags": ["energy"]})

    with scripted_agents(analyst=analyst_args(verdict="false"), auditor=auditor_args(verdict="false")):
        ran = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert ran.exit_code == 0, ran.output
    fm, body = parse_frontmatter(live.read_text(encoding="utf-8"))
    live.write_text(serialize_frontmatter({**fm, "corrections": [later, first], "tags": ["energy", "water"]}, body),
                    encoding="utf-8")

    done = _approve(tmp_path, "--correction", "Re-checked against new sources.")

    assert done.exit_code == 0, done.output
    promoted = _fm(live)
    assert promoted["tags"] == ["energy", "water"]
    summaries = [c["summary"] for c in promoted["corrections"]]
    assert summaries == ["Re-checked against new sources.", later["summary"], first["summary"]]


def test_promotion_lists_two_dropped_sources_in_the_live_order(tmp_path) -> None:
    """Items 3, 12 and 21: mined from the deleted TestRefreshSnapshot cases."""
    from orchestrator.persistence import promote_pending

    live, _pending = _pending_pair(tmp_path, live_sources=("2026/a", "2026/b", "2026/c"),
                                   pending_sources=("2026/b",))

    promote_pending(live, tmp_path)

    assert _sidecar(live)["refresh"]["dropped_sources"] == ["2026/a", "2026/c"]


def test_a_refresh_block_carried_forward_at_promotion_gets_its_dropped_sources_recomputed(tmp_path) -> None:
    """Items 3, 12 and 21: a block already on the live sidecar keeps its `previous` and
    recomputes `dropped_sources` against the promoted claim's sources."""
    from orchestrator.persistence import promote_pending

    live, _pending = _pending_pair(tmp_path, live_sources=("2026/a", "2026/b"), pending_sources=("2026/c",))
    previous = {"status": "published", "verdict": "true", "sources": ["2026/x", "2026/c", "2026/y"],
                "reviewer": REVIEWER}
    data = _sidecar(live)
    data["refresh"] = {"refreshed_at": "2026-10-01T00:00:00+00:00", "previous": previous,
                       "dropped_sources": ["stale"]}
    _sidecar_path(live).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    promote_pending(live, tmp_path)

    refresh = _sidecar(live)["refresh"]
    assert refresh["previous"] == previous
    assert refresh["dropped_sources"] == ["2026/x", "2026/y"]


def test_a_cached_capture_that_redirects_where_the_live_page_ends_is_recorded_ok(tmp_path) -> None:
    """Item 13: the loop's re-check of a cached archive link passes the live page's final URL
    (`also_same_as`), as `dr recheck --sources` does, so a capture that redirects there is `ok`."""
    import httpx
    import respx

    from tests.loop_harness import fake_execute_searches

    moved = f"{URLS[0]}-moved"
    ts = "20261010000000"
    link = f"https://web.archive.org/web/{ts}/{URLS[0]}"
    memento = {"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT"}
    on_page = "Probe Subject data centers used more than 4% of US electricity in 2024."
    old = _write_source(tmp_path, "2026/stored-old", URLS[0], accessed=_days(-200), key_quotes=[on_page])
    old.write_text(old.read_text(encoding="utf-8").replace(f"url: {URLS[0]}\n", f"url: {URLS[0]}\narchived_url: {link}\n"),
                   encoding="utf-8")
    sids = ["2026/stored-old"]
    for i in (1, 2, 3):
        _write_source(tmp_path, f"2026/stored-{i}", URLS[i], accessed=_days(-1))
        sids.append(f"2026/stored-{i}")
    _write_claim(tmp_path, "live-claim", as_of=_days(-90), sources=tuple(sids))
    # No search raw_content for the stored URL, so the recheck fetches it (and follows the redirect).
    page_text = {u: t for u, t in PAGE_TEXT.items() if u != URLS[0]}

    with respx.mock(assert_all_called=False) as mock, scripted_agents(search=fake_execute_searches(page_text=page_text)):
        mock.get(URLS[0]).mock(return_value=httpx.Response(301, headers={"location": moved}))
        mock.get(moved).mock(return_value=httpx.Response(200, html=f"<html><body><p>{on_page}</p></body></html>"))
        replay = f"https://web.archive.org/web/{ts}id_/{URLS[0]}"
        moved_replay = f"https://web.archive.org/web/{ts}id_/{moved}"
        mock.head(replay).mock(return_value=httpx.Response(301, headers={**memento, "location": moved_replay}))
        mock.head(moved_replay).mock(return_value=httpx.Response(200, headers=memento))
        result = _dr(tmp_path, "recheck", "--claim", _ref("live-claim"), "--wayback")

    assert result.exit_code == 0, result.output
    entries = {e["id"]: e for e in _sidecar(_claim_path(tmp_path, "live-claim", "pending"))["sources_consulted"]}
    record = entries["2026/stored-old"]["recheck"]
    assert record["refetched"] is True
    assert record["archive"] == "ok", record


def test_restates_on_a_published_claim_leaves_the_live_sidecar_alone(tmp_path) -> None:
    """Item 18: `dr draft --restates` never writes `restatement.picked` into a published
    claim's live sidecar; the new claim is still written."""
    live = _write_claim(tmp_path, "live-claim", verdict="mixed",
                        sidecar_extra={"restatement": _restatement(LIVE_CANDIDATES, picked=1)})
    before = _bytes(live, _sidecar_path(live))

    with scripted_agents():
        result = _dr(tmp_path, "draft", "--restates", _ref("live-claim"), "--pick", "2", "--skip-wayback")

    assert result.exit_code == 0, result.output
    assert _bytes(live, _sidecar_path(live)) == before
    restated = [p for p in (tmp_path / "research" / "claims" / ENTITY_REF).glob("*.audit.yaml")
                if p.name != "live-claim.audit.yaml"]
    assert [yaml.safe_load(p.read_text(encoding="utf-8")).get("restates") for p in restated] == [_ref("live-claim")]


@pytest.mark.parametrize(
    "status,advice,not_advice",
    [
        ("published", "dr recheck --claim", "--force"),
        ("archived", "dr recheck --claim", "--force"),
        ("draft", "dr draft --claim", "dr recheck"),
    ],
)
def test_findings_advice_for_a_claim_without_a_sidecar_names_a_command_that_runs(
    tmp_path, status, advice, not_advice,
) -> None:
    """Item 24: `dr draft --claim <ref> --force` is a usage error on a published or archived claim."""
    claim = _write_claim(tmp_path, "lost-sidecar", status=status, reviewed=status != "draft")
    _sidecar_path(claim).unlink()

    result = _dr(tmp_path, "findings")

    assert result.exit_code == 0, result.output
    [row] = [ln for ln in result.output.splitlines() if _ref("lost-sidecar") in ln and "no sidecar" in ln]
    assert f"{advice} {_ref('lost-sidecar')}" in row
    assert not_advice not in row


def test_the_archive_capture_paragraph_lists_only_commands_that_look_up_a_snapshot() -> None:
    """Items 5 and 22: `dr recheck --due --dry-run` makes no archive.org call. The paragraph
    lives in AGENTS.md today and may move with the command list to
    docs/architecture/pipeline-commands.md; every copy is checked and at least one must exist."""
    paragraphs = []
    for rel in ("AGENTS.md", "docs/architecture/pipeline-commands.md"):
        path = REPO_ROOT / rel
        if path.exists():
            text = path.read_text(encoding="utf-8")
            paragraphs += [p for p in text.split("\n\n") if "Save Page Now" in p and "existing snapshot" in p]
    assert paragraphs, "no archive-capture paragraph found (positive control)"
    for paragraph in paragraphs:
        assert "dr draft --dry-run" in paragraph
        assert "--due --dry-run" not in paragraph


# --------------------------------------------------------------------------- #
# RE-AX (Fold side tools) fix pass: operator fields edited on the live claim     #
# after seeding survive promotion (RE-AK (Published fields survive the           #
# pipeline) and RE-AH (Claim refresh keeps operator fields and verifies quotes)) #
# --------------------------------------------------------------------------- #

_ANALYST_TAKEAWAY = "The analyst wrote this takeaway."
# The loop writes the claim's statement as its title, so a recheck's analyst title is SENTENCE.
_LIVE_RECORD = {
    "title": SENTENCE,
    "seo_title": "Probe Subject electricity share",
    "verdict": "mixed",
    "cap_rationale": None,
}


def _seed_then_edit_live(root: Path, live_fm: dict, live_edit: dict, *, analyst: dict | None = None,
                         auditor_verdict: str = "mixed", live_record: dict | None = None) -> Path:
    """Recheck a published `mixed` claim (live analyst_record `_LIVE_RECORD`), then edit the live claim."""
    live = _write_claim(root, "live-claim", verdict="mixed", as_of=_days(-90), extra_fm=live_fm,
                        sidecar_extra={"analyst_record": {**_LIVE_RECORD, **(live_record or {})}})
    args = analyst or {**analyst_args(), "takeaway": _ANALYST_TAKEAWAY}
    with scripted_agents(analyst=args, auditor=auditor_args(verdict=auditor_verdict)):
        ran = _recheck(root, "--claim", _ref("live-claim"))
    assert ran.exit_code == 0, ran.output
    pending = _claim_path(root, "live-claim", "pending")
    seeded = _sidecar(pending)["seeded_live"]
    assert {key: seeded[key] for key in ("takeaway", "seo_title", "cap_rationale", "corrections", "tags")} == {
        "takeaway": live_fm.get("takeaway"), "seo_title": live_fm.get("seo_title"),
        "cap_rationale": live_fm.get("cap_rationale"),
        "corrections": live_fm.get("corrections"), "tags": live_fm.get("tags"),
    }
    assert seeded["analyst_title"] == {**_LIVE_RECORD, **(live_record or {})}["title"]
    pending_fm = _fm(pending)
    assert seeded["pending"] == {key: pending_fm.get(key) for key in ("takeaway", "seo_title", "cap_rationale")}
    if live_edit:
        fm, body = parse_frontmatter(live.read_text(encoding="utf-8"))
        live.write_text(serialize_frontmatter({**fm, **live_edit}, body), encoding="utf-8")
    return live


def _promote(live: Path, root: Path) -> dict:
    from orchestrator.persistence import promote_pending

    promote_pending(live, root)
    assert "seeded_live" not in _sidecar(live)
    return _fm(live)


def test_promotion_keeps_a_takeaway_edited_on_the_live_claim_while_the_verdict_is_unchanged(tmp_path) -> None:
    from linter.runner import run_all_checks

    live = _seed_then_edit_live(tmp_path, {"takeaway": "First operator takeaway."},
                                {"takeaway": "Later operator takeaway."})
    pending = _claim_path(tmp_path, "live-claim", "pending")
    assert _fm(pending)["takeaway"] == "First operator takeaway."
    issues, _checked = run_all_checks(tmp_path)
    assert issues, "control: the lint run reports something on this fixture"
    named = [i for i in issues if "seeded_live" in i.message or str(_sidecar_path(pending)) in str(i.path)]
    assert named == [], "a pending sidecar's seeded_live block raises no lint issue"

    assert _promote(live, tmp_path)["takeaway"] == "Later operator takeaway."


def test_promotion_drops_a_live_takeaway_edit_when_the_verdict_changed(tmp_path) -> None:
    """Control for the takeaway carry: the keep rule holds it only while the verdict is unchanged."""
    live = _seed_then_edit_live(tmp_path, {"takeaway": "First operator takeaway."},
                                {"takeaway": "Later operator takeaway."},
                                analyst={**analyst_args(verdict="false"), "takeaway": _ANALYST_TAKEAWAY},
                                auditor_verdict="false")

    assert _promote(live, tmp_path)["takeaway"] == _ANALYST_TAKEAWAY


def test_promotion_keeps_an_seo_title_edited_on_the_live_claim_while_the_analyst_title_is_unchanged(tmp_path) -> None:
    live = _seed_then_edit_live(tmp_path, {"seo_title": "First operator SEO title"},
                                {"seo_title": "Later operator SEO title"})
    assert _fm(_claim_path(tmp_path, "live-claim", "pending"))["seo_title"] == "First operator SEO title"

    assert _promote(live, tmp_path)["seo_title"] == "Later operator SEO title"


def test_promotion_drops_a_live_seo_title_edit_when_the_analyst_title_changed(tmp_path) -> None:
    """Control for the seo_title carry."""
    live = _seed_then_edit_live(tmp_path, {"seo_title": "First operator SEO title"},
                                {"seo_title": "Later operator SEO title"},
                                live_record={"title": "An older analyst title for the claim"})

    assert _promote(live, tmp_path)["seo_title"] == _LIVE_RECORD["seo_title"]


def test_promotion_keeps_a_cap_rationale_edited_on_the_live_claim(tmp_path) -> None:
    live = _seed_then_edit_live(tmp_path, {"cap_rationale": "First operator rationale."},
                                {"cap_rationale": "Later operator rationale."})
    assert _fm(_claim_path(tmp_path, "live-claim", "pending"))["cap_rationale"] == "First operator rationale."

    assert _promote(live, tmp_path)["cap_rationale"] == "Later operator rationale."


def test_promotion_keeps_a_review_edit_on_the_pending_claim_when_the_live_claim_is_unchanged(tmp_path) -> None:
    """Control: with no live edit after seeding, the pending value (here a review edit) stands."""
    from orchestrator.persistence import set_claim_fields

    live = _seed_then_edit_live(tmp_path, {"takeaway": "First operator takeaway.", "seo_title": "Operator SEO title"},
                                {})
    pending = _claim_path(tmp_path, "live-claim", "pending")
    set_claim_fields(pending, {"takeaway": "Reviewer edit on the pending draft.", "seo_title": "Reviewer SEO title"})

    promoted = _promote(live, tmp_path)
    assert promoted["takeaway"] == "Reviewer edit on the pending draft."
    assert promoted["seo_title"] == "Reviewer SEO title"


def test_promotion_with_an_unparseable_live_claim_refuses_before_anything_moves(tmp_path) -> None:
    from orchestrator.persistence import promote_pending

    live = _seed_then_edit_live(tmp_path, {"takeaway": "First operator takeaway."}, {})
    pending = _claim_path(tmp_path, "live-claim", "pending")
    # No frontmatter at all: the published-snapshot read treats it as unpublished, so only the
    # operator-field merge sees the failure, and it must refuse before the first move.
    live.write_text("Body with no frontmatter.\n", encoding="utf-8")
    before = _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending))

    with pytest.raises(ValueError, match="frontmatter"):
        promote_pending(live, tmp_path)

    assert _bytes(live, _sidecar_path(live), pending, _sidecar_path(pending)) == before


# --------------------------------------------------------------------------- #
# P2 (pending tag edit lost): promotion takes `tags` and `corrections` from the  #
# live claim only when they changed there after the recheck seeded the pending   #
# pair; a review edit on the pending draft survives. Items 6 and 14 of SP5        #
# (RE-AW, Recheck), both directions.                                              #
# --------------------------------------------------------------------------- #

_OLDER_CORRECTION = {"date": "2026-09-01", "summary": "An older correction.", "previous_verdict": "mostly-true"}


def _recheck_unchanged(root: Path, live_fm: dict) -> tuple[Path, Path]:
    """Recheck a published `mixed` claim into a pending draft with the same verdict; return (live, pending)."""
    live = _write_claim(root, "live-claim", verdict="mixed", as_of=_days(-90), extra_fm=live_fm)
    with scripted_agents(analyst=analyst_args(), auditor=auditor_args(verdict="mixed")):
        ran = _recheck(root, "--claim", _ref("live-claim"))
    assert ran.exit_code == 0, ran.output
    pending = _claim_path(root, "live-claim", "pending")
    assert _fm(pending)["verdict"] == "mixed"
    return live, pending


def _edit_live(live: Path, edit: dict) -> None:
    fm, body = parse_frontmatter(live.read_text(encoding="utf-8"))
    live.write_text(serialize_frontmatter({**fm, **edit}, body), encoding="utf-8")


def _queue_tag_editor(tags: list[str]):
    """A stand-in for the `e` key's editor: rewrite only `tags` in the edit buffer."""
    def edit(path: Path) -> int:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["tags"] = tags
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return 0

    return edit


@pytest.mark.usefixtures("human_at_terminal")
def test_a_tag_edit_made_in_the_review_queue_on_a_pending_recheck_survives_approval(tmp_path, monkeypatch) -> None:
    """The review queue lists the pending draft; `e` edits its tags, `a` promotes it. The live
    claim's tags did not change after seeding, so the reviewer's edit is what goes live."""
    import orchestrator.review_queue as review_queue_mod

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    monkeypatch.setattr(review_queue_mod, "_run_editor_blocking", _queue_tag_editor(["energy", "highlight"]))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    walk = _dr(tmp_path, "review", input="e\ns\na\n")

    assert walk.exit_code == 0, walk.output
    assert "Saved edits" in walk.output
    assert not pending.exists(), walk.output
    promoted = _fm(live)
    assert promoted["status"] == "published"
    assert promoted["tags"] == ["energy", "highlight"]
    assert "seeded_live" not in _sidecar(live)


def test_promotion_takes_live_tags_edited_after_seeding_over_unchanged_pending_tags(tmp_path) -> None:
    """The other direction: a live edit after seeding wins when the pending value is unchanged."""
    from orchestrator.persistence import promote_pending

    live, _pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    _edit_live(live, {"tags": ["energy", "water"]})

    promote_pending(live, tmp_path)

    assert _fm(live)["tags"] == ["energy", "water"]


def test_promotion_unions_corrections_added_on_both_the_live_and_the_pending_claim(tmp_path) -> None:
    from orchestrator.persistence import promote_pending, set_claim_corrections

    live_added = {"date": "2026-10-12", "summary": "Added on the live claim.", "previous_verdict": "mixed"}
    pending_added = {"date": "2026-10-10", "summary": "Added on the pending draft.", "previous_verdict": "mixed"}
    live, pending = _recheck_unchanged(tmp_path, {"corrections": [_OLDER_CORRECTION]})
    _edit_live(live, {"corrections": [live_added, _OLDER_CORRECTION]})
    set_claim_corrections(pending, [pending_added, _OLDER_CORRECTION])

    promote_pending(live, tmp_path)

    summaries = [c["summary"] for c in _fm(live)["corrections"]]
    assert summaries == [live_added["summary"], pending_added["summary"], _OLDER_CORRECTION["summary"]]


def test_promotion_keeps_a_correction_removed_on_the_live_claim_removed(tmp_path) -> None:
    """A correction deleted on the live claim after seeding stays deleted when the pending draft
    did not change its list (no union in that case)."""
    from orchestrator.persistence import promote_pending

    live, _pending = _recheck_unchanged(tmp_path, {"corrections": [_OLDER_CORRECTION]})
    _edit_live(live, {"corrections": None})

    promote_pending(live, tmp_path)

    assert not _fm(live).get("corrections")


@pytest.mark.usefixtures("human_at_terminal")
def test_a_pending_tag_edit_survives_a_promotion_that_stopped_before_the_claim_move(tmp_path, monkeypatch) -> None:
    """The half-done promotion path: the merge ran before the sidecar move, so finishing the
    promotion must not take the live tags over the reviewer's edit."""
    from orchestrator.persistence import set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    set_claim_fields(pending, {"tags": ["energy", "highlight"]})

    with monkeypatch.context() as m:
        _fail_replace_onto(m, live)
        failed = _approve(tmp_path)
    assert failed.exit_code != 0
    assert pending.exists() and not _sidecar_path(pending).exists()

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert not pending.exists()
    assert _fm(live)["tags"] == ["energy", "highlight"]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_pending_tag_edit_survives_a_promotion_whose_sidecar_move_failed(tmp_path, monkeypatch) -> None:
    """The sidecar move fails, so the retry is a fresh promotion, not a half-done one: the
    pending sidecar must still carry its seed record, or the retry takes the live tags."""
    from orchestrator.persistence import set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    set_claim_fields(pending, {"tags": ["energy", "highlight"]})

    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(live))
        failed = _approve(tmp_path)
    assert failed.exit_code != 0
    assert pending.exists() and _sidecar_path(pending).exists()
    assert "seeded_live" in _sidecar(pending)

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert _fm(live)["tags"] == ["energy", "highlight"]
    assert "seeded_live" not in _sidecar(live)


@pytest.mark.usefixtures("human_at_terminal")
def test_a_live_tag_edit_made_after_a_failed_sidecar_move_survives_the_retry(tmp_path, monkeypatch) -> None:
    """The other direction of the failed sidecar move: with the seed record kept, a live edit
    made between the failure and the retry is still told apart from the unchanged pending tags."""
    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})

    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(live))
        failed = _approve(tmp_path)
    assert failed.exit_code != 0
    _edit_live(live, {"tags": ["energy", "water"]})

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert _fm(live)["tags"] == ["energy", "water"]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_review_tag_edit_made_after_a_failed_sidecar_move_survives_the_retry(tmp_path, monkeypatch) -> None:
    """The first --approve took the live tag into the pending draft, then the sidecar move
    failed. The reviewer then removes that tag on the pending draft; the retry must not take
    it back from the live claim, which it already consumed."""
    from orchestrator.persistence import set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    _edit_live(live, {"tags": ["energy", "pick"]})

    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(live))
        failed = _approve(tmp_path)
    assert failed.exit_code != 0
    assert _fm(pending)["tags"] == ["energy", "pick"]
    set_claim_fields(pending, {"tags": ["energy"]})

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert _fm(live)["tags"] == ["energy"]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_live_tag_removed_after_a_failed_sidecar_move_stays_removed(tmp_path, monkeypatch) -> None:
    """A tag added on the live claim, taken by the first --approve, then removed on the live
    claim before the retry: the retry takes the removal as a fresh live edit."""
    live, _pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    _edit_live(live, {"tags": ["energy", "water"]})

    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(live))
        failed = _approve(tmp_path)
    assert failed.exit_code != 0
    _edit_live(live, {"tags": ["energy"]})

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert _fm(live)["tags"] == ["energy"]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_review_correction_edit_made_after_a_failed_sidecar_move_survives_the_retry(
    tmp_path, monkeypatch,
) -> None:
    from orchestrator.persistence import set_claim_corrections

    live_added = {"date": "2026-10-12", "summary": "Added on the live claim.", "previous_verdict": "mixed"}
    live, pending = _recheck_unchanged(tmp_path, {"corrections": [_OLDER_CORRECTION]})
    _edit_live(live, {"corrections": [live_added, _OLDER_CORRECTION]})

    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(live))
        failed = _approve(tmp_path)
    assert failed.exit_code != 0
    set_claim_corrections(pending, [_OLDER_CORRECTION])

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert [c["summary"] for c in _fm(live)["corrections"]] == [_OLDER_CORRECTION["summary"]]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_review_takeaway_edit_made_after_a_failed_sidecar_move_survives_the_retry(
    tmp_path, monkeypatch,
) -> None:
    from orchestrator.persistence import set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"takeaway": "Operator takeaway."})
    _edit_live(live, {"takeaway": "Live edit after seeding."})

    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(live))
        failed = _approve(tmp_path)
    assert failed.exit_code != 0
    assert _fm(pending)["takeaway"] == "Live edit after seeding."
    set_claim_fields(pending, {"takeaway": "Reviewer edit after the failed move."})

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert _fm(live)["takeaway"] == "Reviewer edit after the failed move."


@pytest.mark.usefixtures("human_at_terminal")
def test_a_pending_tag_edit_survives_promotion_of_a_pair_with_no_seed_record(tmp_path) -> None:
    """A pending pair written before the seed record existed cannot tell a live edit from a
    review edit; the pending value stands (as before the record), so the review edit is kept."""
    from orchestrator.persistence import set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    data = _sidecar(pending)
    data.pop("seeded_live")
    _sidecar_path(pending).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    set_claim_fields(pending, {"tags": ["energy", "highlight"]})

    approved = _approve(tmp_path)

    assert approved.exit_code == 0, approved.output
    assert _fm(live)["tags"] == ["energy", "highlight"]


def test_promotion_keeps_tags_added_on_both_the_live_and_the_pending_claim(tmp_path) -> None:
    from orchestrator.persistence import promote_pending, set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy", "water-use"]})
    _edit_live(live, {"tags": ["energy", "water-use", "water"]})
    set_claim_fields(pending, {"tags": ["energy", "highlight"]})

    promote_pending(live, tmp_path)

    # Both additions kept; the pending draft's removal of water-use applied.
    assert _fm(live)["tags"] == ["energy", "water", "highlight"]


# --------------------------------------------------------------------------- #
# Promotion stopped after each of its writes: the retry keeps a review edit on  #
# the pending draft and an operator edit on the live claim made in between      #
# (RE-AK (Published fields survive the pipeline): corrections and tags always   #
# kept, an operator's takeaway kept while the verdict is unchanged).            #
# --------------------------------------------------------------------------- #

# Every write `dr review --approve` makes to the claim files when it promotes a
# pending recheck that has a live tag and takeaway edit to take. The stop cases
# below run once per entry; a new write fails the inventory test until its stop
# case is counted here. `<copy>` is the merged pending claim's sibling copy.
_PENDING_DIR = "research/pending/subjects/probe-subject"
_LIVE_DIR = "research/claims/subjects/probe-subject"
PROMOTION_WRITES = [
    ("write", f"{_PENDING_DIR}/live-claim.md.<copy>"),
    ("write", f"{_PENDING_DIR}/live-claim.audit.yaml"),
    ("replace", f"{_PENDING_DIR}/live-claim.md.<copy> -> {_PENDING_DIR}/live-claim.md"),
    ("write", f"{_PENDING_DIR}/live-claim.audit.yaml"),
    ("replace", f"{_PENDING_DIR}/live-claim.audit.yaml -> {_LIVE_DIR}/live-claim.audit.yaml"),
    ("replace", f"{_PENDING_DIR}/live-claim.md -> {_LIVE_DIR}/live-claim.md"),
    ("write", f"{_LIVE_DIR}/live-claim.audit.yaml"),
    ("rmdir", _PENDING_DIR),
    ("rmdir", "research/pending/subjects"),
    ("write", f"{_LIVE_DIR}/live-claim.audit.yaml"),
    ("write", f"{_LIVE_DIR}/live-claim.md"),
]


def _normalized(writes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(kind, re.sub(r"live-claim\.md\.[0-9a-f]+\.merge", "live-claim.md.<copy>", path))
            for kind, path in writes]


def _pending_promotion_with_live_edits(root: Path) -> tuple[Path, Path]:
    """A pending recheck seeded from a live claim whose tags and takeaway an operator then edited."""
    live, pending = _recheck_unchanged(root, {"tags": ["energy"], "takeaway": "Seed operator takeaway."})
    assert _fm(pending)["takeaway"] == "Seed operator takeaway."
    _edit_live(live, {"tags": ["energy", "pick"], "takeaway": "Live takeaway edit."})
    return live, pending


@pytest.mark.usefixtures("human_at_terminal")
def test_the_promotion_write_inventory_has_a_stop_case_per_write(tmp_path) -> None:
    from tests.write_faults import WriteFaults

    live, pending = _pending_promotion_with_live_edits(tmp_path)
    faults = WriteFaults(tmp_path)

    with faults.record():
        approved = _approve(tmp_path)

    assert approved.exit_code == 0, approved.output
    assert _normalized(faults.writes) == PROMOTION_WRITES
    fm = _fm(live)
    assert (fm["status"], sorted(fm["tags"]), fm["takeaway"]) == ("published", ["energy", "pick"], "Live takeaway edit.")


@pytest.mark.usefixtures("human_at_terminal")
@pytest.mark.parametrize("edit", ["none", "review", "live"])
@pytest.mark.parametrize("stop", range(len(PROMOTION_WRITES)), ids=lambda n: f"stop{n}")
def test_a_promotion_stopped_at_any_write_keeps_edits_made_before_the_retry(tmp_path, stop, edit) -> None:
    """Stop `--approve` at one write, edit (or not), run `--approve` again. A review edit is made
    on the pending draft while it exists (else on the claim being approved) and removes the
    tag the reviewer can see the merge took; a live edit adds a tag and rewrites the takeaway."""
    from tests.write_faults import WriteFaults

    live, pending = _pending_promotion_with_live_edits(tmp_path)
    faults = WriteFaults(tmp_path)

    with faults.fail_at(stop):
        first = _approve(tmp_path)
    assert faults.fired, faults.writes

    expected_tags = {"energy", "pick"}
    expected_takeaway = "Live takeaway edit."
    if edit == "review":
        target = pending if pending.exists() else live
        seen = set(_fm(target).get("tags") or [])
        reviewed = (seen - {"pick"}) | {"highlight"}
        _edit_live(target, {"tags": sorted(reviewed), "takeaway": "Reviewer takeaway."})
        assert reviewed != seen
        # A tag the merge had not yet taken when the reviewer looked is still the live claim's edit.
        expected_tags = reviewed | ({"pick"} if "pick" not in seen else set())
        expected_takeaway = "Reviewer takeaway."
    elif edit == "live":
        seen = set(_fm(live).get("tags") or [])
        _edit_live(live, {"tags": sorted(seen | {"water"}), "takeaway": "Second live takeaway edit."})
        expected_tags = {"energy", "pick", "water"}
        expected_takeaway = "Second live takeaway edit."

    if first.exit_code != 0:
        again = _approve(tmp_path)
        assert again.exit_code == 0, again.output

    fm = _fm(live)
    assert fm["status"] == "published"
    assert set(fm["tags"]) == expected_tags
    assert fm["takeaway"] == expected_takeaway
    assert not pending.exists() and not _sidecar_path(pending).exists()
    assert list((tmp_path / "research").rglob("*.merge")) == []
    sidecar = _sidecar(live)
    assert "seeded_live" not in sidecar
    assert "refresh" not in sidecar
    assert sidecar["human_review"]["reviewer"] == REVIEWER


@pytest.mark.parametrize("field", ["takeaway", "seo_title", "cap_rationale"])
def test_a_review_edit_on_the_pending_draft_wins_over_a_live_edit_of_the_same_field(tmp_path, field) -> None:
    """Both sides edited one scalar field after seeding: the reviewer's pending value goes live
    (a live value is taken only when the pending draft left the field as seeded)."""
    from orchestrator.persistence import promote_pending

    live, pending = _recheck_unchanged(tmp_path, {field: "Seed operator value."})
    _edit_live(pending, {field: "Reviewer edit on pending."})
    _edit_live(live, {field: "Live edit after seeding."})

    promote_pending(live, tmp_path)

    assert _fm(live)[field] == "Reviewer edit on pending."


@pytest.mark.usefixtures("human_at_terminal")
def test_a_live_tag_edit_survives_a_rerun_from_the_existing_pending_pair(tmp_path) -> None:
    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    _edit_live(live, {"tags": ["energy", "water"]})
    with scripted_agents(analyst=analyst_args()):
        r = _dr(tmp_path, "draft", "--claim", _ref("live-claim"), "--rerun", "analyst")
    assert r.exit_code == 0, r.output
    assert "seeded_live" in _sidecar(pending)

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert _fm(live)["tags"] == ["energy", "water"]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_review_tag_edit_survives_a_second_recheck_from_the_existing_pending_pair(tmp_path) -> None:
    from orchestrator.persistence import set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    set_claim_fields(pending, {"tags": ["energy", "highlight"]})
    with scripted_agents(analyst=analyst_args(), auditor=auditor_args(verdict="mixed")):
        ran = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert ran.exit_code == 0, ran.output
    assert _fm(pending)["tags"] == ["energy", "highlight"]

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert _fm(live)["tags"] == ["energy", "highlight"]


@pytest.mark.usefixtures("human_at_terminal")
def test_review_and_live_tag_edits_both_survive_a_second_recheck_from_the_existing_pending_pair(tmp_path) -> None:
    from orchestrator.persistence import set_claim_fields

    live, pending = _recheck_unchanged(tmp_path, {"tags": ["energy"]})
    set_claim_fields(pending, {"tags": ["energy", "highlight"]})
    _edit_live(live, {"tags": ["energy", "water"]})
    with scripted_agents(analyst=analyst_args(), auditor=auditor_args(verdict="mixed")):
        ran = _recheck(tmp_path, "--claim", _ref("live-claim"))
    assert ran.exit_code == 0, ran.output

    again = _approve(tmp_path)

    assert again.exit_code == 0, again.output
    assert sorted(_fm(live)["tags"]) == ["energy", "highlight", "water"]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_review_tag_edit_on_a_pending_draft_from_an_analyst_rerun_survives_a_second_rerun_and_promotion(
    tmp_path,
) -> None:
    from orchestrator.persistence import promote_pending, set_claim_fields
    import tests.test_draft_rerun as D

    live = D._repo(tmp_path, status="published", verdict="true", confidence="high", fm_extra={"tags": ["energy"]})
    with scripted_agents(analyst=analyst_args(verdict="true")):
        assert D._rerun(tmp_path, "analyst").exit_code == 0
    pending = D._claim_path(tmp_path, "pending")
    assert D._sidecar(pending)["seeded_live"]["tags"] == ["energy"]
    set_claim_fields(pending, {"tags": ["energy", "highlight"]})
    with scripted_agents(analyst=analyst_args(verdict="true")):
        assert D._rerun(tmp_path, "analyst").exit_code == 0
    assert D._fm(pending)["tags"] == ["energy", "highlight"]

    promote_pending(live, tmp_path)

    assert D._fm(live)["tags"] == ["energy", "highlight"]


@pytest.mark.usefixtures("human_at_terminal")
def test_a_review_queue_tag_edit_on_a_pending_draft_from_an_evaluator_rerun_survives_approval(
    tmp_path, monkeypatch,
) -> None:
    import orchestrator.review_queue as review_queue_mod
    import tests.test_draft_rerun as D

    live = D._repo(tmp_path, status="published", verdict="mixed", fm_extra={"tags": ["energy"]})
    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="mixed")):
        assert D._rerun(tmp_path, "evaluator").exit_code == 0
    pending = D._claim_path(tmp_path, "pending")
    assert pending.exists()
    monkeypatch.setattr(review_queue_mod, "_run_editor_blocking", _queue_tag_editor(["energy", "highlight"]))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    walk = _dr(tmp_path, "review", input="e\ns\na\n")

    assert walk.exit_code == 0, walk.output
    assert not pending.exists(), walk.output
    assert D._fm(live)["tags"] == ["energy", "highlight"]


@pytest.mark.usefixtures("human_at_terminal")
def test_approving_an_evaluator_rerun_that_changed_a_published_verdict_needs_a_correction(tmp_path) -> None:
    import tests.test_draft_rerun as D

    live = D._repo(tmp_path, status="published", verdict="true", confidence="high",
                   fm_extra={"takeaway": D.OPERATOR_TAKEAWAY},
                   sidecar_extra={"analyst_record": dict(D.ANALYST_RECORD_TRUE)})
    before = live.read_bytes()
    with scripted_agents(auditor=auditor_args(verdict="false"), tiebreaker=auditor_args(verdict="false")):
        assert D._rerun(tmp_path, "evaluator").exit_code == 0
    assert D._fm(D._claim_path(tmp_path, "pending"))["verdict"] == "false"
    assert live.read_bytes() == before

    r = D._dr(tmp_path, "review", "--claim", D.REF, "--approve", "--reviewer", REVIEWER)

    assert r.exit_code != 0, r.output
    assert "--correction" in r.output
    assert live.read_bytes() == before


# The writes of a retry that finishes a promotion stopped at its claim move
# (`promotion_half_done`), when the live claim was edited before the retry:
# the merge against the seed record on the live sidecar, then the rest.
HALF_DONE_WRITES = [
    ("write", f"{_PENDING_DIR}/live-claim.md.<copy>"),
    ("write", f"{_LIVE_DIR}/live-claim.audit.yaml"),
    ("replace", f"{_PENDING_DIR}/live-claim.md.<copy> -> {_PENDING_DIR}/live-claim.md"),
    ("replace", f"{_PENDING_DIR}/live-claim.md -> {_LIVE_DIR}/live-claim.md"),
    ("write", f"{_LIVE_DIR}/live-claim.audit.yaml"),
    ("rmdir", _PENDING_DIR),
    ("rmdir", "research/pending/subjects"),
    ("write", f"{_LIVE_DIR}/live-claim.audit.yaml"),
    ("write", f"{_LIVE_DIR}/live-claim.md"),
]
_CLAIM_MOVE = PROMOTION_WRITES.index(("replace", f"{_PENDING_DIR}/live-claim.md -> {_LIVE_DIR}/live-claim.md"))


def _half_done_with_a_live_edit(root: Path) -> tuple[Path, Path]:
    """A promotion stopped at its claim move, then a live tag and takeaway edit; return (live, pending)."""
    from orchestrator.persistence import promotion_half_done
    from tests.write_faults import WriteFaults

    live, pending = _pending_promotion_with_live_edits(root)
    faults = WriteFaults(root)
    with faults.fail_at(_CLAIM_MOVE):
        assert _approve(root).exit_code != 0
    assert promotion_half_done(live, root)
    _edit_live(live, {"tags": sorted(set(_fm(live)["tags"]) | {"water"}), "takeaway": "Second live takeaway edit."})
    return live, pending


@pytest.mark.usefixtures("human_at_terminal")
def test_the_half_done_promotion_write_inventory_has_a_stop_case_per_write(tmp_path) -> None:
    from tests.write_faults import WriteFaults

    live, _pending = _half_done_with_a_live_edit(tmp_path)
    faults = WriteFaults(tmp_path)

    with faults.record():
        approved = _approve(tmp_path)

    assert approved.exit_code == 0, approved.output
    assert _normalized(faults.writes) == HALF_DONE_WRITES
    fm = _fm(live)
    assert (sorted(fm["tags"]), fm["takeaway"]) == (["energy", "pick", "water"], "Second live takeaway edit.")


@pytest.mark.usefixtures("human_at_terminal")
@pytest.mark.parametrize("edit", ["none", "review", "live"])
@pytest.mark.parametrize("stop", range(len(HALF_DONE_WRITES)), ids=lambda n: f"stop{n}")
def test_a_half_done_promotion_retry_stopped_at_any_write_keeps_edits_made_before_the_next_retry(
    tmp_path, stop, edit,
) -> None:
    from tests.write_faults import WriteFaults

    live, pending = _half_done_with_a_live_edit(tmp_path)
    faults = WriteFaults(tmp_path)

    with faults.fail_at(stop):
        second = _approve(tmp_path)
    assert faults.fired, faults.writes

    expected_tags = {"energy", "pick", "water"}
    expected_takeaway = "Second live takeaway edit."
    if edit == "review":
        target = pending if pending.exists() else live
        seen = set(_fm(target).get("tags") or [])
        reviewed = (seen - {"water"}) | {"highlight"}
        _edit_live(target, {"tags": sorted(reviewed), "takeaway": "Reviewer takeaway."})
        expected_tags = reviewed | ({"water"} if "water" not in seen else set())
        expected_takeaway = "Reviewer takeaway."
    elif edit == "live":
        _edit_live(live, {"tags": sorted(set(_fm(live)["tags"]) | {"solar"}), "takeaway": "Third live takeaway edit."})
        expected_tags = {"energy", "pick", "water", "solar"}
        expected_takeaway = "Third live takeaway edit."

    if second.exit_code != 0:
        third = _approve(tmp_path)
        assert third.exit_code == 0, third.output

    fm = _fm(live)
    assert fm["status"] == "published"
    assert set(fm["tags"]) == expected_tags
    assert fm["takeaway"] == expected_takeaway
    assert not pending.exists()
    assert list((tmp_path / "research").rglob("*.merge")) == []
    assert "seeded_live" not in _sidecar(live)


@pytest.mark.usefixtures("human_at_terminal")
def test_a_live_edit_is_lost_when_a_recheck_stopped_between_its_moves_is_rerun_before_promotion(
    tmp_path, monkeypatch,
) -> None:
    """Pins a loss the seed record does not cover. The first recheck moved its pending claim and
    stopped before its sidecar; the rerun (`dr recheck --claim`, the advice `dr findings` gives)
    starts from that pending claim with no sidecar, so its pair has no `seeded_live`, and
    promotion keeps the pending tags over a live edit made in between."""
    live = _write_claim(tmp_path, "live-claim", verdict="mixed", as_of=_days(-90), extra_fm={"tags": ["energy"]})
    pending = _claim_path(tmp_path, "live-claim", "pending")
    with monkeypatch.context() as m:
        _fail_replace_onto(m, _sidecar_path(pending))
        with scripted_agents(analyst=analyst_args(), auditor=auditor_args(verdict="mixed")):
            assert _recheck(tmp_path, "--claim", _ref("live-claim")).exit_code == 1
    assert pending.exists() and not _sidecar_path(pending).exists()
    _edit_live(live, {"tags": ["energy", "water"]})
    with scripted_agents(analyst=analyst_args(), auditor=auditor_args(verdict="mixed")):
        assert _recheck(tmp_path, "--claim", _ref("live-claim")).exit_code == 0
    assert "seeded_live" not in _sidecar(pending)

    approved = _approve(tmp_path)

    assert approved.exit_code == 0, approved.output
    assert _fm(live)["tags"] == ["energy"]
