"""``loop.rerun``: one agent over stored sources (RE-AR, One loop, one writer).

``rerun(spec, config, sources, agent, analyst_output=None)`` runs the Analyst
or the Evaluator alone, through the same null retry as ``run``, with no
researcher or ingest call. ``dr step-analyze --write`` and ``dr step-audit
--write`` call it and then the writer; the writer's sidecar carries the
other agents' record forward by default.
"""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from tests.loop_harness import (
    SENTENCE,
    analyst_args,
    auditor_args,
    capturing_model,
    claim_spec,
    loop_config,
    scripted_agents,
    write_entity,
)

NARRATIVE = "A narrative only the stored analysis carries."


def _analyst_output():
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment

    return AnalystOutput(
        entity=EntityResolution(
            entity_name="Probe Subject", entity_type="subject", entity_description="A subject.",
        ),
        verdict=VerdictAssessment(**analyst_args(narrative=NARRATIVE)),
    )


def _stored_sources() -> list[dict]:
    return [
        {
            "title": f"Report {i}", "publisher": "Example Publisher", "summary": "A summary.",
            "key_quotes": [], "body": "Body.", "slug": f"report-{i}", "url": f"https://example.org/{i}",
            "source_id": f"2026/report-{i}", "kind": "article", "independence": "independent",
        }
        for i in range(1, 5)
    ]


def _refusing_model(calls: list[str], name: str):
    """A model that records the call it must never get, then fails it."""
    from pydantic_ai.models.function import FunctionModel

    async def _fn(messages, info):
        calls.append(name)
        raise AssertionError(f"{name} must not run on a rerun")

    return FunctionModel(_fn)


@pytest.mark.asyncio
async def test_rerun_evaluator_grades_the_given_analysis_once(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    spec = claim_spec(tmp_path)
    cfg = loop_config(tmp_path)
    captured: list[str] = []
    calls: list[str] = []
    ao = _analyst_output()
    sources = _stored_sources()

    with scripted_agents(
        auditor_model=capturing_model(captured, auditor_args(), calls=calls, name="auditor"),
        analyst_model=_refusing_model(calls, "analyst"),
        search=_never_search,
        ingestor=_refusing_model(calls, "ingestor"),
    ):
        result = await loop.rerun(spec, cfg, sources, agent="evaluator", analyst_output=ao)

    assert calls == ["auditor"]
    assert len(captured) == 1
    assert NARRATIVE in captured[0]
    assert SENTENCE in captured[0]
    assert result.analyst_output is ao
    assert result.consistency is not None
    assert result.consistency.verdict_agrees is True
    assert result.sources == sources
    assert result.errors == []


@pytest.mark.asyncio
async def test_rerun_analyst_runs_the_analyst_once_and_returns_no_audit(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    spec = claim_spec(tmp_path)
    cfg = loop_config(tmp_path)
    captured: list[str] = []
    calls: list[str] = []
    sources = _stored_sources()

    with scripted_agents(
        analyst_model=capturing_model(captured, analyst_args(), calls=calls, name="analyst"),
        auditor_model=_refusing_model(calls, "auditor"),
        search=_never_search,
        ingestor=_refusing_model(calls, "ingestor"),
    ):
        result = await loop.rerun(spec, cfg, sources, agent="analyst")

    assert calls == ["analyst"]
    assert SENTENCE in captured[0]
    assert result.analyst_output is not None
    assert result.analyst_output.verdict.verdict.value == "mixed"
    assert result.consistency is None
    assert result.sources == sources


@pytest.mark.asyncio
async def test_rerun_evaluator_needs_an_analysis(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    with pytest.raises(ValueError):
        await loop.rerun(claim_spec(tmp_path), loop_config(tmp_path), _stored_sources(), agent="evaluator")


@pytest.mark.asyncio
async def test_rerun_refuses_an_unknown_agent(tmp_path) -> None:
    import loop

    write_entity(tmp_path)
    with pytest.raises(ValueError):
        await loop.rerun(claim_spec(tmp_path), loop_config(tmp_path), _stored_sources(), agent="researcher")


async def _never_search(queries, client, **_kwargs):
    raise AssertionError("execute_searches must not run on a rerun")


# --------------------------------------------------------------------------- #
# dr step-audit --write: the writer carries the rest of the sidecar forward      #
# --------------------------------------------------------------------------- #


def _write_claim_repo(tmp_path, sidecar: dict) -> tuple:
    from common.frontmatter import serialize_frontmatter

    (tmp_path / "research" / "entities" / "companies").mkdir(parents=True)
    (tmp_path / "research" / "entities" / "companies" / "example.md").write_text(
        serialize_frontmatter({"name": "Example", "type": "company", "description": "A company."}, "Body.\n"),
        encoding="utf-8",
    )
    claim_dir = tmp_path / "research" / "claims" / "example"
    claim_dir.mkdir(parents=True)
    claim_path = claim_dir / "claim.md"
    claim_path.write_text(
        serialize_frontmatter(
            {"title": "Example claim", "entity": "companies/example", "verdict": "unverified",
             "confidence": "low", "topics": ["environmental-impact"], "sources": []},
            "Body.\n",
        ),
        encoding="utf-8",
    )
    sidecar_path = claim_dir / "claim.audit.yaml"
    sidecar_path.write_text(
        yaml.safe_dump({"schema_version": 1, "sources_consulted": [], **sidecar}), encoding="utf-8"
    )
    return claim_path, sidecar_path


def test_step_audit_write_carries_the_rest_of_the_sidecar_forward(tmp_path) -> None:
    """Research trace, sub-questions, other agents' models, the fit note and an
    unknown key all survive an Evaluator-only rewrite."""
    from orchestrator.cli import main

    note = "verification_level independently-verified lowered to claimed: the written sources include 0"
    _claim_path, sidecar_path = _write_claim_repo(tmp_path, {
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m",
                         "agents": ["researcher", "ingestor", "analyst"], "level_clamp": note},
        "models_used": {"researcher": "r-model", "ingestor": "i-model", "analyst": "a-model",
                        "auditor": "old-auditor"},
        "research": {"mode": "decomposed", "queries": ["q1"]},
        "sub_questions": [{"id": "sq1", "question": "Q?", "rationale": "r", "queries": ["q1"], "citations": []}],
        "custom_note": {"kept": True},
    })

    result = CliRunner().invoke(main, [
        "--model", "test", "--auditor-model", "test",
        "step-audit", "--claim", "example/claim", "--write", "--repo-root", str(tmp_path),
    ])

    assert result.exit_code == 0, result.output
    data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert data["pipeline_run"]["agents"] == ["auditor"]
    assert data["pipeline_run"]["level_clamp"] == note
    assert data["models_used"] == {
        "researcher": "r-model", "ingestor": "i-model", "analyst": "a-model", "auditor": "test",
    }
    assert data["research"] == {"mode": "decomposed", "queries": ["q1"]}
    assert data["sub_questions"][0]["id"] == "sq1"
    assert data["custom_note"] == {"kept": True}
    assert data["audit"]["auditor_verdict"]
