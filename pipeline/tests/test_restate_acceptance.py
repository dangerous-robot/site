"""Acceptance fixture for RE-AU (Restate inside the loop): the us-data-centers claim.

The absorbed plan (``docs/plans/completed/claim-restate_superseded.md`` § Tests,
``test_restater_acceptance.py``) snapshots the us-data-centers claim, its
sidecar, its entity, its eight cited sources and the uncited Pew source that
carries the sweep's top candidate A1 into
``tests/fixtures/restate/us-data-centers/``. Adapted to the loop: the claim
is re-run with ``dr draft --claim <ref> --force`` on a copy of the fixture,
the scripted search returns the eight cited URLs so every source is a dedup
hit, the scripted analyst and Evaluator agree on ``unverified`` (the
restater's trigger), and the restater is scripted (1) or live (2).

1. Scripted: a three-candidate proposal whose quotes are real passages from
   the fixture sources. The sidecar block ranks A1 first with
   ``quote_verified: true`` and ``decisiveness: 4``, lists the Google
   disclosure next, and a candidate quoting invented text comes out capped at
   2; the uncited Pew source reached the restater from the disk pool.
2. Live (``acceptance`` marker, skipped by default): the same run on the
   real models from ``DR_*`` env, asserting shape and that at least one
   candidate carries a quote.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from common.frontmatter import parse_frontmatter
from tests.loop_harness import (
    analyst_args,
    auditor_args,
    candidate,
    fake_execute_searches,
    restater_args,
    scorer_args,
    scripted_agents,
)

FIXTURE = Path(__file__).parent / "fixtures" / "restate" / "us-data-centers"
ENTITY_REF = "subjects/us-data-centers"
ENTITY_NAME = "US Data Centers"
STEM = (
    "there-are-fewer-than-10-us-data-centers-that-are-certified-to-run-on-50-or-greater-"
    "renewable-energy-power-sources"
)
CLAIM_REF = f"{ENTITY_REF}/{STEM}"
PEW = "2025/what-we-know-about-energy-use-at-us-data-centers-amid-the-ai-boom"
GOOGLE = "2026/energy"
GBI = "2026/datacenters"

A1 = (
    "Renewable sources supplied about a quarter of the electricity used by US data centers in 2024; "
    "natural gas supplied more than 40%."
)
A3 = "US data centers run by Google match their electricity with renewable certificates rather than hourly supply."
INVENTED = "US data centers are certified by a federal registry of their renewable share."

PROPOSAL = restater_args(
    why_unverified="quantifier-unsupported",
    note="No source counts facilities by renewable share; the sources give the national grid mix and operators' matching claims.",
    candidates=[
        candidate(
            INVENTED, frame="disclosure", decisiveness=4,
            supporting=[{"source": GBI, "quote": "a federal registry lists every certified data center", "note": "invented"}],
            rationale="Green Globes Certification for Data Centers would list the registry.",
        ),
        candidate(
            A3, frame="disclosure", expected_confidence="medium", level="self-reported", decisiveness=3,
            supporting=[{"source": GOOGLE, "quote": "maintained a 100% renewable energy match globally every year since 2017",
                         "note": "a match, not hourly supply"}],
            rationale="Google's Energy Innovations and Initiatives describes a 100% renewable energy match.",
        ),
        candidate(
            A1, frame="measurement", expected_verdict="true", expected_confidence="medium",
            level="independently-verified", decisiveness=4,
            supporting=[{"source": PEW, "quote": "Natural gas supplied over 40% of electricity for U.S. data centers in 2024, while renewables accounted for about 24%.",
                         "note": "the grid mix for 2024"}],
            rationale="What We Know About Energy Use at U.S. Data Centers Amid the AI Boom gives the 2024 mix.",
        ),
    ],
)


def _copy_fixture(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE / "research", tmp_path / "research")
    return tmp_path


def _cited_urls(repo_root: Path) -> list[str]:
    fm, _ = parse_frontmatter((repo_root / "research" / "claims" / f"{CLAIM_REF}.md").read_text(encoding="utf-8"))
    urls = []
    for sid in fm["sources"]:
        sfm, _ = parse_frontmatter((repo_root / "research" / "sources" / f"{sid}.md").read_text(encoding="utf-8"))
        urls.append(sfm["url"])
    return urls


def _sidecar(repo_root: Path) -> dict:
    return yaml.safe_load((repo_root / "research" / "claims" / f"{CLAIM_REF}.audit.yaml").read_text(encoding="utf-8"))


def test_scripted_restater_over_the_fixture_ranks_the_sweeps_candidate_first(tmp_path) -> None:
    from orchestrator.cli import main

    repo = _copy_fixture(tmp_path)
    urls = _cited_urls(repo)
    assert len(urls) == 8
    models = [x for a in ("researcher", "analyst", "auditor", "ingestor", "tiebreaker", "restater")
              for x in (f"--{a}-model", "test")]
    with scripted_agents(
        scorer=scorer_args(urls),
        search=fake_execute_searches(urls, page_text={}),
        analyst=analyst_args(verdict="unverified", title="Fewer than 10 US data centers certified"),
        auditor=auditor_args(verdict="unverified"),
        restater=PROPOSAL,
    ):
        result = CliRunner().invoke(main, [
            "--model", "test", *models, "draft", "--claim", CLAIM_REF, "--force", "--skip-wayback",
            "--repo-root", str(repo),
        ])
    assert result.exit_code == 0, result.output

    sidecar = _sidecar(repo)
    block = sidecar["restatement"]
    assert block["original"]["verdict"] == "unverified"
    assert block["pool"]["consulted"] == 8
    assert block["pool"]["on_disk"] == 1, "the uncited Pew source reached the restater from the disk pool"
    assert block["pool"]["sent"] == 9
    ranked = block["candidates"]
    assert [c["text"] for c in ranked] == [A1, A3, INVENTED]
    assert [c["rank"] for c in ranked] == [1, 2, 3]
    assert ranked[0]["decisiveness"] == 4
    assert ranked[0]["supporting"][0] == {
        "source": PEW,
        "quote": "Natural gas supplied over 40% of electricity for U.S. data centers in 2024, while renewables accounted for about 24%.",
        "quote_verified": True,
        "note": "the grid mix for 2024",
    }
    assert ranked[1]["decisiveness"] == 3 and ranked[1]["supporting"][0]["quote_verified"] is True
    assert ranked[2]["decisiveness"] == 2, "an invented quote is kept, marked unverified, and caps decisiveness"
    assert ranked[2]["supporting"][0]["quote_verified"] is False
    assert block["dropped"] == []
    assert sidecar["pipeline_run"]["run_id"]
    # The claim stays the original: the restater never rewrites it.
    fm, _ = parse_frontmatter((repo / "research" / "claims" / f"{CLAIM_REF}.md").read_text(encoding="utf-8"))
    assert fm["statement"].startswith("There are fewer than 10 US data centers")
    assert fm["verdict"] == "unverified"


@pytest.mark.acceptance
@pytest.mark.asyncio
async def test_live_restater_over_the_fixture_returns_a_proposal_of_the_right_shape(tmp_path) -> None:
    """Runs the real models from ``DR_*`` env (``uv run pytest -m acceptance -k restate``); paid."""
    from dotenv import load_dotenv

    from common.models import DEFAULT_MODEL
    from loop import ClaimSpec, VerifyConfig, run
    from loop.restater.models import Frame, WhyUnverified
    from orchestrator.entity_resolution import parse_entity_ref

    load_dotenv()
    if not (os.environ.get("TAVILY_API_KEY") or os.environ.get("BRAVE_WEB_SEARCH_API_KEY")):
        pytest.skip("no search key in the environment")
    repo = _copy_fixture(tmp_path)
    fm, _ = parse_frontmatter((repo / "research" / "claims" / f"{CLAIM_REF}.md").read_text(encoding="utf-8"))
    spec = ClaimSpec(statement=fm["statement"] if fm.get("statement") else fm["title"], entity=parse_entity_ref(ENTITY_REF, repo))
    config = VerifyConfig(
        model=os.environ.get("DR_MODEL", DEFAULT_MODEL),
        researcher_model=os.environ.get("DR_RESEARCHER_MODEL"),
        analyst_model=os.environ.get("DR_ANALYST_MODEL"),
        auditor_model=os.environ.get("DR_AUDITOR_MODEL"),
        ingestor_model=os.environ.get("DR_INGESTOR_MODEL"),
        tiebreaker_model=os.environ.get("DR_TIEBREAKER_MODEL"),
        restater_model=os.environ.get("DR_RESTATER_MODEL"),
        repo_root=str(repo), skip_wayback=True, allow_save=False,
    )
    result = await run(spec, config)

    assert result.analyst_output is not None, result.errors
    block = result.restatement
    if result.consistency.pipeline_verdict.value not in ("unverified", "mixed", "not-applicable") and \
            result.consistency.tiebreaker_verdict is None:
        pytest.skip(f"the live run graded the claim {result.consistency.pipeline_verdict.value} with agreement; nothing to restate")
    assert block is not None, result.finding
    assert len(block["candidates"]) >= 2
    assert len({c["frame"] for c in block["candidates"]}) >= 2
    assert all(c["frame"] in {f.value for f in Frame} for c in block["candidates"])
    assert block["why_unverified"] in {w.value for w in WhyUnverified}
    pool_ids = {p.relative_to(repo / "research" / "sources").with_suffix("").as_posix()
                for p in (repo / "research" / "sources").rglob("*.md")}
    consulted = {sd.get("source_id") for sd in result.sources}
    for c in block["candidates"]:
        for ref in c["supporting"] + c["contradicting"]:
            assert ref["source"] in pool_ids | consulted, ref
    assert any(c["supporting"] or c["contradicting"] for c in block["candidates"]), (
        "no candidate carries a quote, so the ranking is by text, not by how decisively the evidence settles it"
    )
