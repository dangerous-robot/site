"""``loop.rerun``: one agent over stored sources (RE-AR, One loop, one writer).

``rerun(spec, config, sources, agent, analyst_output=None)`` runs the Analyst
or the Evaluator alone, through the same null retry as ``run``, with no
researcher or ingest call. ``dr draft --claim <ref> --rerun analyst|evaluator``
calls it and then the writer; the writer's sidecar carries the other agents'
record forward by default (``tests/test_draft_rerun.py``).
"""

from __future__ import annotations

import pytest

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
