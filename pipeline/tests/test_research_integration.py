"""Acceptance test for the one loop and the one writer (RE-AR, One loop, one writer).

All four agents on scripted models, driven through ``dr draft`` and
``loop.run``:

- ``dr draft --entity`` writes the cited sources, the claim and the sidecar
  in the one write order, with the claim's ``sources:`` in the researcher's
  URL order and the sidecar carrying ``pipeline_run.run_id``;
- ``dr draft --force`` on a published fixture resets the sign-off and writes
  the refresh block (cases from ``test_entity_independence.py`` and
  ``test_onboard.py`` ``TestOnboardForceRewritesKeepTheRefreshTrail``);
- a criterion's grading text reaches both the Analyst and the Evaluator;
- a write that fails between the claim and the sidecar leaves the live claim
  readable and the published snapshot intact;
- a blocked or failed run writes nothing, so no orphan source files are left;
- the command's grammar: SENTENCE with ``--entity``, an entity file that
  exists, before any model call.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from common.frontmatter import parse_frontmatter
from common.utils import slugify
from tests.loop_harness import (
    ENTITY_REF,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    capturing_model,
    claim_dir,
    claim_spec,
    failing_model,
    loop_config,
    scorer_args,
    scripted_agents,
    write_entity,
    written_claims,
    written_sources,
)

# An ad hoc claim's stem is its statement, slugified (RE-AS, One claim path).
CLAIM_STEM = slugify(SENTENCE)
EXPECTED_SOURCE_IDS = ["2026/report", "2026/second-report", "2026/third-report", "2026/fourth-report"]


def _draft(tmp_path, *extra: str, dry_run: bool = False):
    from orchestrator.cli import main

    # --skip-wayback keeps the run offline: no archive.org lookup or capture.
    args = [
        "--model", "test", "draft", "--entity", ENTITY_REF, SENTENCE, "--skip-wayback",
        "--repo-root", str(tmp_path),
    ]
    if dry_run:
        args.insert(3, "--dry-run")
    return CliRunner().invoke(main, [*args, *extra])


def _claim_and_sidecar(tmp_path) -> tuple[Path, Path]:
    path = claim_dir(tmp_path) / f"{CLAIM_STEM}.md"
    return path, path.with_name(f"{CLAIM_STEM}.audit.yaml")


def _record_write_order(monkeypatch) -> list[str]:
    """Wrap the writer's steps so the order they run in is observable."""
    import orchestrator.persistence as persistence

    order: list[str] = []
    for name in ("mark_forced_rewrite", "_write_source_files", "_write_claim_file", "_write_audit_sidecar"):
        real = getattr(persistence, name)

        def _wrapped(*args, _name=name, _real=real, **kwargs):
            order.append(_name)
            return _real(*args, **kwargs)

        monkeypatch.setattr(persistence, name, _wrapped)
    return order


# --------------------------------------------------------------------------- #
# dr draft writes claim, cited sources and sidecar in one order                  #
# --------------------------------------------------------------------------- #


def test_draft_writes_sources_claim_and_sidecar_in_order(tmp_path, monkeypatch) -> None:
    write_entity(tmp_path)
    order = _record_write_order(monkeypatch)

    with scripted_agents():
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    assert order == ["_write_source_files", "_write_claim_file", "_write_audit_sidecar"]

    claim_path, sidecar_path = _claim_and_sidecar(tmp_path)
    assert written_claims(tmp_path) == [claim_path]
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm["entity"] == ENTITY_REF
    assert fm["status"] == "draft"
    assert fm["verdict"] == "mixed"
    assert fm["confidence"] == "medium"
    assert "criteria_slug" not in fm
    # The researcher's URL order, not cached-then-fresh.
    assert fm["sources"] == EXPECTED_SOURCE_IDS
    assert [p.stem for p in written_sources(tmp_path)] == sorted(s.split("/")[1] for s in EXPECTED_SOURCE_IDS)
    for sid in EXPECTED_SOURCE_IDS:
        source_fm, _ = parse_frontmatter((tmp_path / "research" / "sources" / f"{sid}.md").read_text())
        assert source_fm["url"] in URLS

    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    keys = list(sidecar)
    assert keys.index("sub_questions") == keys.index("research") + 1
    assert keys.index("sub_questions") == keys.index("sources_consulted") - 1
    assert sidecar["pipeline_run"]["agents"] == ["researcher", "ingestor", "analyst", "auditor"]
    assert isinstance(sidecar["pipeline_run"]["run_id"], str) and len(sidecar["pipeline_run"]["run_id"]) == 32
    assert sidecar["audit"]["auditor_verdict"] == "mixed"
    assert sidecar["human_review"]["reviewed_at"] is None
    assert {e["id"] for e in sidecar["sub_questions"]} == {"sq1", "sq2"}
    assert result.output.count(str(claim_path.relative_to(tmp_path))) >= 1


def test_sidecar_records_an_uncovered_sub_question_with_no_citations(tmp_path) -> None:
    """From the base ``test_research_integration.py`` sidecar block check: every
    planned sub-question gets a sidecar entry, and one no ingested source
    addressed has ``citations: []`` (research-flow.md)."""
    write_entity(tmp_path)
    only_sq1 = {
        "kept": [{"url": u, "addresses": ["sq1"], "score": 4.0} for u in URLS],
        "dropped": [], "rationale": "sq1 only",
    }
    with scripted_agents(scorer=only_sq1):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    _claim_path, sidecar_path = _claim_and_sidecar(tmp_path)
    block = {e["id"]: e for e in yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))["sub_questions"]}
    assert set(block) == {"sq1", "sq2"}
    for entry in block.values():
        assert {"id", "question", "rationale", "queries", "citations"} <= set(entry)
    assert block["sq2"]["citations"] == []
    assert sorted(block["sq1"]["citations"]) == sorted(EXPECTED_SOURCE_IDS)


def test_draft_help_lists_the_research_flags() -> None:
    """From test_cli.py ``TestClaimProbeOptions.test_verify_help_lists_candidate_pool_size``."""
    from orchestrator.cli import main

    result = CliRunner().invoke(main, ["draft", "--help"])
    assert result.exit_code == 0, result.output
    for flag in ("--candidate-pool-size", "--max-sources", "--max-initial-queries"):
        assert flag in result.output


def test_draft_lists_only_the_sources_the_analyst_cited(tmp_path) -> None:
    write_entity(tmp_path)
    cited = ["2026/report", "2026/third-report"]

    with scripted_agents(analyst=analyst_args(cited_sources=cited, level="partially-verified")):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    claim_path, _ = _claim_and_sidecar(tmp_path)
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm["sources"] == cited
    assert [f"2026/{p.stem}" for p in written_sources(tmp_path)] == cited


def test_draft_refuses_an_existing_claim_without_force(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents():
        first = _draft(tmp_path)
        assert first.exit_code == 0, first.output
        claim_path, _ = _claim_and_sidecar(tmp_path)
        before = claim_path.read_text(encoding="utf-8")
        second = _draft(tmp_path)

    assert second.exit_code != 0
    assert "--force" in second.output
    assert claim_path.read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------- #
# dr draft --force on a claim that is not a draft                                #
# --------------------------------------------------------------------------- #


def _publish(tmp_path, status: str = "published", verdict: str = "true") -> tuple[Path, Path]:
    """A claim at the stem its statement yields, signed off by a reviewer."""
    claim_path, sidecar_path = _claim_and_sidecar(tmp_path)
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text(
        f"---\ntitle: {SENTENCE}\n"
        f"entity: {ENTITY_REF}\ntopics: [environmental-impact]\n"
        f"verdict: '{verdict}'\nconfidence: high\n"
        f"status: {status}\nas_of: '2026-10-01'\nsources:\n- 2026/old\n---\nBody.\n",
        encoding="utf-8",
    )
    sidecar_path.write_text(yaml.safe_dump({
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst"]},
        "sources_consulted": [],
        "audit": None,
        "human_review": {
            "reviewed_at": "2026-10-02", "reviewer": "reviewer@example.org", "notes": None, "pr_url": None,
        },
    }), encoding="utf-8")
    return claim_path, sidecar_path


def test_forced_rewrite_of_a_published_claim_keeps_the_refresh_trail(tmp_path, monkeypatch) -> None:
    from orchestrator.review import refresh_verdict_change

    write_entity(tmp_path)
    claim_path, sidecar_path = _publish(tmp_path)
    order = _record_write_order(monkeypatch)

    # The Evaluator agrees, so the analyst's verdict is the pipeline's and no tie-breaker runs.
    with scripted_agents(
        analyst=analyst_args(verdict="false", confidence="medium"),
        auditor=auditor_args(verdict="false", confidence="medium"),
    ):
        result = _draft(tmp_path, "--force")

    assert result.exit_code == 0, result.output
    assert order == ["mark_forced_rewrite", "_write_source_files", "_write_claim_file", "_write_audit_sidecar"]
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm["status"] == "draft"
    assert fm["verdict"] == "false"
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["human_review"]["reviewed_at"] is None
    assert sidecar["human_review"]["reviewer"] is None
    previous = sidecar["refresh"]["previous"]
    assert previous["status"] == "published"
    assert previous["verdict"] == "true"
    assert previous["reviewer"] == "reviewer@example.org"
    assert sidecar["refresh"]["dropped_sources"] == ["2026/old"]
    # dr review --approve then asks for a public correction.
    assert refresh_verdict_change(fm, sidecar) == ("true", "false")


def test_forced_rewrite_of_an_archived_claim_loses_its_sign_off(tmp_path) -> None:
    write_entity(tmp_path)
    claim_path, sidecar_path = _publish(tmp_path, status="archived")

    with scripted_agents():
        result = _draft(tmp_path, "--force")

    assert result.exit_code == 0, result.output
    assert parse_frontmatter(claim_path.read_text(encoding="utf-8"))[0]["status"] == "draft"
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["human_review"]["reviewed_at"] is None
    assert "refresh" not in sidecar


def test_forced_rewrite_of_a_draft_keeps_its_review(tmp_path) -> None:
    write_entity(tmp_path)
    _claim_path, sidecar_path = _publish(tmp_path, status="draft")

    with scripted_agents():
        result = _draft(tmp_path, "--force")

    assert result.exit_code == 0, result.output
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["human_review"]["reviewer"] == "reviewer@example.org"
    assert "refresh" not in sidecar


def test_forced_rewrite_refuses_an_unparseable_claim(tmp_path) -> None:
    write_entity(tmp_path)
    claim_path, _sidecar_path = _publish(tmp_path)
    claim_path.write_text("---\ntitle: [unclosed\n---\nBody.\n", encoding="utf-8")

    with scripted_agents():
        result = _draft(tmp_path, "--force")

    assert result.exit_code != 0
    text = result.output + (str(result.exception) if result.exception else "")
    assert "cannot parse existing claim" in text
    assert claim_path.read_text(encoding="utf-8") == "---\ntitle: [unclosed\n---\nBody.\n"


def test_forced_rewrite_keeps_the_operators_seo_title_and_cap_rationale(tmp_path) -> None:
    """RE-AH, RE-AK: operator fields survive while the analyst's title is unchanged."""
    write_entity(tmp_path)
    claim_path, sidecar_path = _publish(tmp_path, status="draft")
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    fm["seo_title"] = "Operator seo title"
    fm["cap_rationale"] = "Operator rationale for the low cap."
    fm["verification_level"] = "claimed"
    from common.frontmatter import serialize_frontmatter

    claim_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    sidecar["analyst_record"] = {
        "title": fm["title"], "seo_title": "Probe Subject electricity share",
        "cap_rationale": "Analyst rationale.", "takeaway": None,
    }
    sidecar_path.write_text(yaml.safe_dump(sidecar), encoding="utf-8")

    with scripted_agents(analyst=analyst_args(level="claimed", cap_rationale="New analyst rationale.")):
        result = _draft(tmp_path, "--force")

    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm["seo_title"] == "Operator seo title"
    assert fm["cap_rationale"] == "Operator rationale for the low cap."


# --------------------------------------------------------------------------- #
# Criterion grading text reaches both agents                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_grading_rule_reaches_analyst_and_evaluator(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    sentinel = "SENTINEL-NOTES: mixed = offsets only"
    analyst_prompts: list[str] = []
    auditor_prompts: list[str] = []

    with scripted_agents(
        analyst_model=capturing_model(analyst_prompts, analyst_args()),
        auditor_model=capturing_model(auditor_prompts, auditor_args()),
    ):
        result = await loop.run(claim_spec(tmp_path, grading_rule=sentinel), loop_config(tmp_path))

    assert result.analyst_output is not None, result.errors
    assert result.consistency is not None
    assert any(sentinel in p for p in analyst_prompts)
    assert any(sentinel in p for p in auditor_prompts)


# --------------------------------------------------------------------------- #
# A write that fails between the claim and the sidecar                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("failing_write", ["_write_claim_file", "_write_audit_sidecar"])
def test_failed_write_keeps_the_live_claim_readable_and_the_snapshot(tmp_path, monkeypatch, failing_write) -> None:
    import orchestrator.persistence as persistence

    write_entity(tmp_path)
    claim_path, sidecar_path = _publish(tmp_path)
    real = getattr(persistence, failing_write)
    calls = {"n": 0}

    def _fail_once(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(f"simulated {failing_write} failure")
        return real(*args, **kwargs)

    monkeypatch.setattr(persistence, failing_write, _fail_once)

    with scripted_agents(analyst=analyst_args(verdict="false")):
        failed = _draft(tmp_path, "--force")
    assert failed.exit_code != 0

    fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    if failing_write == "_write_claim_file":
        assert fm["status"] == "published"
        assert fm["verdict"] == "true"
    else:
        assert fm["status"] == "draft"
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["refresh"]["previous"]["verdict"] == "true"
    assert sidecar["refresh"]["previous"]["reviewer"] == "reviewer@example.org"
    assert sidecar["human_review"]["reviewed_at"] is None

    with scripted_agents(analyst=analyst_args(verdict="false")):
        again = _draft(tmp_path, "--force")
    assert again.exit_code == 0, again.output
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["refresh"]["previous"]["verdict"] == "true"
    assert sidecar["refresh"]["previous"]["reviewer"] == "reviewer@example.org"
    assert parse_frontmatter(claim_path.read_text(encoding="utf-8"))[0]["status"] == "draft"


# --------------------------------------------------------------------------- #
# Blocked and failed runs write nothing                                          #
# --------------------------------------------------------------------------- #


def test_analyst_failure_writes_nothing(tmp_path) -> None:
    """No orphan source files when the analyst fails (closes the backlog finding)."""
    write_entity(tmp_path)

    with scripted_agents(analyst_model=failing_model()):
        result = _draft(tmp_path)

    assert result.exit_code != 0
    assert "analyst" in result.output.lower()
    assert written_claims(tmp_path) == []
    assert written_sources(tmp_path) == []


def test_threshold_block_writes_nothing(tmp_path) -> None:
    write_entity(tmp_path)
    two = URLS[:2]

    with scripted_agents(scorer=scorer_args(two), search=_search_for(two)):
        result = _draft(tmp_path)

    assert result.exit_code != 0
    assert "insufficient_sources" in result.output
    assert written_claims(tmp_path) == []
    assert written_sources(tmp_path) == []


def _search_for(urls):
    from tests.loop_harness import fake_execute_searches

    return fake_execute_searches(urls)


# --------------------------------------------------------------------------- #
# Grammar                                                                        #
# --------------------------------------------------------------------------- #


def _tripwire_loop(monkeypatch) -> list[str]:
    import loop

    called: list[str] = []

    async def _run(*args, **kwargs):
        called.append("run")
        raise AssertionError("the loop must not run before the usage check")

    monkeypatch.setattr(loop, "run", _run)
    return called


def test_draft_requires_a_sentence_with_entity(tmp_path, monkeypatch) -> None:
    from orchestrator.cli import main

    write_entity(tmp_path)
    called = _tripwire_loop(monkeypatch)
    result = CliRunner().invoke(main, ["--model", "test", "draft", "--entity", ENTITY_REF, "--repo-root", str(tmp_path)])
    assert result.exit_code == 2, result.output
    assert called == []


def test_draft_requires_a_mode_flag(tmp_path, monkeypatch) -> None:
    from orchestrator.cli import main

    called = _tripwire_loop(monkeypatch)
    result = CliRunner().invoke(main, ["--model", "test", "draft", SENTENCE, "--repo-root", str(tmp_path)])
    assert result.exit_code == 2, result.output
    assert "--entity" in result.output
    assert called == []


@pytest.mark.parametrize("ref", ["no-slash", "badtype/foo", "subjects/nonexistent"])
def test_draft_refuses_an_entity_ref_that_names_no_file(tmp_path, monkeypatch, ref) -> None:
    from orchestrator.cli import main

    called = _tripwire_loop(monkeypatch)
    result = CliRunner().invoke(main, ["--model", "test", "draft", "--entity", ref, SENTENCE, "--repo-root", str(tmp_path)])
    assert result.exit_code == 2, result.output
    # parse_entity_ref names the ref, the type dir or the missing file.
    assert any(part in result.output for part in ref.split("/"))
    assert called == []
