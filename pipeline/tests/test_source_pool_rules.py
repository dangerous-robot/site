"""Acceptance tests for RE-BA (Source pool rules).

Written before the implementation (plan ``docs/plans/completed/pipeline-rebuild.md``
§ SP6b (Source pool rules), "Tests that prove it"). Every case drives
behaviour through a public entry: ``loop.run``, ``loop.rerun`` or
``loop.ingest_one`` with the agents on scripted models
(``tests/loop_harness.py``), the ``dr`` CLI under ``CliRunner``, or a public
classifier, planner or citation function. Nothing here patches a private name
under ``pipeline/loop/``.

Covered, one section per RE-AL (Source pool and coverage quality) row:

- newswire: a publisher naming a newswire is ``first-party`` for the entity
  the release names, on a product claim (fresh or cached) and on a subject
  claim; a release about another organization stays off-entity;
- the level fit runs inside the loop, after the cited filter and before the
  Evaluator, so ``audit.analyst_confidence`` is post-fit while
  ``pipeline_run.level_clamp`` still carries the note; the fit lowers
  confidence only when it lowers the level, so an analyst-chosen capped level
  keeps its confidence and lint's ``confidence-cap-violation`` is reachable
  again (carried finding SP2-6); ``rerun(agent="analyst")`` fits too;
- coverage is re-derived after ingest from the fetched text: a scorer tag
  whose page never mentions the sub-question's terms is dropped, listed under
  ``sub_questions[].snippet_only``, and the analyst's uncovered marker uses
  the re-derived set; a cached source is checked against its stored text;
- a ``cited_sources`` id whose title the narrative never names is listed in
  ``analyst_record.uncited_by_title`` and survives a forced rerun;
- cached sources do not shrink the fresh-ingest target;
- the planner emits one counter-evidence sub-question with at least one
  query, recorded in the sidecar with ``kind``;
- carried: a per-URL null body is retried once inside ``ingest_one`` (SP2-2);
  a recovered ingest retry records each error once (SP2-9); the runbook names
  ``DR_TIEBREAKER_MODEL`` (SP2-5); the old path is gone.
"""

from __future__ import annotations

import inspect
import re
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml
from click.testing import CliRunner
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from common.frontmatter import parse_frontmatter
from common.models import Confidence, Independence, VerificationLevel
from common.utils import slugify
from tests.loop_harness import (
    COUNTER_SUB_QUESTION,
    ENTITY_REF,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    capturing_model,
    counting_ingest_model,
    claim_dir,
    claim_spec,
    fake_execute_searches,
    ingest_model,
    loop_config,
    planner_args,
    scorer_args,
    scripted_agents,
    write_entity,
    written_claims,
    written_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
CLAIM_STEM = slugify(SENTENCE)
NEWSWIRE_PUBLISHER = "Yahoo Finance (via ACCESS Newswire)"
PRODUCT_REF = "products/earthly-insight"
PRODUCT_NAME = "Earthly Insight"
PRODUCT_SENTENCE = "Earthly Insight is hosted on renewable energy"
RELEASE_QUOTE = "Earthly Insight announced a more conscious approach to data hosting."
NULL_BODY = UnexpectedModelBehavior(
    "Invalid response from openai chat completions endpoint: 4 validation errors for ChatCompletion"
)


# --------------------------------------------------------------------------- #
# Helpers                                                                        #
# --------------------------------------------------------------------------- #


def _draft(tmp_path, *extra: str, dry_run: bool = False, sentence: str = SENTENCE, mode=("--entity", ENTITY_REF)):
    from orchestrator.cli import main

    agents = [f"--{a}-model" for a in ("researcher", "analyst", "auditor", "ingestor", "tiebreaker")]
    models = [x for flag in agents for x in (flag, "test")]
    args = ["--model", "test", *models, "draft", *mode, *([sentence] if sentence else []),
            "--skip-wayback", "--repo-root", str(tmp_path)]
    if dry_run:
        args.insert(args.index("draft") + 1, "--dry-run")
    return CliRunner().invoke(main, [*args, *extra])


def _claim_and_sidecar(tmp_path, stem: str = CLAIM_STEM, ref: str = ENTITY_REF) -> tuple[Path, Path]:
    path = claim_dir(tmp_path, ref) / f"{stem}.md"
    return path, path.with_name(f"{stem}.audit.yaml")


def _sidecar(tmp_path, stem: str = CLAIM_STEM, ref: str = ENTITY_REF) -> dict:
    _claim, sidecar = _claim_and_sidecar(tmp_path, stem, ref)
    return yaml.safe_load(sidecar.read_text(encoding="utf-8"))


def _claim_fm(tmp_path, stem: str = CLAIM_STEM, ref: str = ENTITY_REF) -> dict:
    claim, _sidecar = _claim_and_sidecar(tmp_path, stem, ref)
    fm, _body = parse_frontmatter(claim.read_text(encoding="utf-8"))
    return fm


def _store_source(
    repo_root: Path, url: str, slug: str, *, publisher: str = "Example Publisher",
    independence: str = "independent", body: str = "Body. Third parties confirm the energy data it publishes.",
) -> str:
    path = repo_root / "research" / "sources" / "2026" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nurl: {url}\ntitle: Stored {slug}\npublisher: {publisher}\n"
        f"accessed_date: 2026-01-01\nkind: article\nindependence: {independence}\n"
        f"summary: Stored.\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return f"2026/{slug}"


def write_product(repo_root: Path, ref: str = PRODUCT_REF, name: str = PRODUCT_NAME) -> str:
    """A product entity with a website, so the entity match has a host to compare."""
    type_dir, slug = ref.split("/", 1)
    path = repo_root / "research" / "entities" / type_dir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ntype: product\nwebsite: https://{slug.replace('-', '')}.com\n"
        "description: A hosted analytics product.\n---\n",
        encoding="utf-8",
    )
    return ref


def _release_pages(urls: list[str] | None = None) -> dict[str, str]:
    return {u: f"{RELEASE_QUOTE} Third parties confirm the energy data it publishes." for u in (urls or URLS)}


def _release_quotes(urls: list[str] | None = None) -> dict[str, list[str]]:
    return {u: [RELEASE_QUOTE] for u in (urls or URLS)}


def _labels(result) -> dict[str, str]:
    return {sd["source_id"]: sd["independence"] for sd in result.sources}


def _overrides(result) -> dict:
    return {o.source: o for o in (result.analyst_output.verdict.source_overrides or [])}


async def _run(tmp_path, *, ref: str = ENTITY_REF, sentence: str = SENTENCE, **config_overrides):
    import loop

    return await loop.run(claim_spec(tmp_path, sentence=sentence, ref=ref), loop_config(tmp_path, **config_overrides))


# --------------------------------------------------------------------------- #
# RE-AL row 1: a syndicated press-wire release is first-party                    #
# --------------------------------------------------------------------------- #


def test_newswire_publishers_are_recognised_and_named_by_origin() -> None:
    from common.source_classification import is_newswire, newswire_origin

    assert is_newswire(NEWSWIRE_PUBLISHER)
    assert newswire_origin(NEWSWIRE_PUBLISHER) == "accesswire"
    assert newswire_origin("PR Newswire") == "prnewswire"
    assert newswire_origin("Business Wire") == "businesswire"
    assert newswire_origin("GlobeNewswire") == "globenewswire"
    assert not is_newswire("The Guardian")
    assert newswire_origin("The Guardian") is None
    # A publisher that merely contains "wire" is not a newswire.
    assert not is_newswire("Wired")
    # Whole words only: "cision" inside another word names no press wire.
    assert newswire_origin("Cision PR Newswire") == "prnewswire"
    assert newswire_origin("Cision") == "cision"
    assert newswire_origin("Decision Lab") is None
    assert newswire_origin("Precision Medicine Weekly") is None
    assert newswire_origin("AsiaNewswire") == "newswire"


def test_a_publisher_containing_a_newswire_term_inside_a_word_stays_secondary() -> None:
    from common.source_classification import classify_source_type, independence_for_source_type

    for publisher in ("Decision Lab", "Precision Medicine Weekly"):
        source_type = classify_source_type(publisher, "article")
        assert source_type == "secondary", publisher
        assert independence_for_source_type(source_type) == "independent"


def test_a_newswire_publisher_classifies_as_primary_and_first_party() -> None:
    from common.source_classification import classify_source_type, independence_for_source_type

    source_type = classify_source_type(NEWSWIRE_PUBLISHER, "article")
    assert source_type == "primary"
    assert independence_for_source_type(source_type) == "first-party"


@pytest.mark.asyncio
async def test_a_newswire_release_naming_a_product_entity_is_first_party_on_its_claim(tmp_path) -> None:
    """The Earthly Insight case: an ACCESS Newswire release on finance.yahoo.com naming the
    entity is the entity's own statement, so it counts as first-party, not independent, and
    the level fit sees no independent source."""
    write_product(tmp_path)
    analyst = analyst_args(level="independently-verified", confidence="medium")
    with scripted_agents(
        analyst=analyst,
        search=fake_execute_searches(URLS, _release_pages()),
        ingestor=ingest_model(key_quotes=_release_quotes(), publisher=NEWSWIRE_PUBLISHER),
    ):
        result = await _run(tmp_path, ref=PRODUCT_REF, sentence=PRODUCT_SENTENCE)

    assert result.analyst_output is not None, result.errors
    assert set(_labels(result).values()) == {"first-party"}, _labels(result)
    assert not any(o.reason.startswith("Off-entity") for o in _overrides(result).values())
    # No independent source is written, so the fit lowers the level inside the loop.
    assert result.analyst_output.verdict.verification_level == VerificationLevel.CLAIMED
    assert result.level_clamp and "independently-verified lowered to claimed" in result.level_clamp


@pytest.mark.asyncio
async def test_a_cached_independent_newswire_release_naming_the_entity_is_relabelled(tmp_path) -> None:
    """A release already on disk as ``independent`` (the file label never changes) is
    relabelled for this claim with an override that names the rule."""
    write_product(tmp_path)
    release = _store_source(
        tmp_path, URLS[0], "release", publisher=NEWSWIRE_PUBLISHER, independence="independent",
        body=f"{RELEASE_QUOTE} The release names the product throughout.",
    )
    with scripted_agents(search=fake_execute_searches(URLS, _release_pages())):
        result = await _run(tmp_path, ref=PRODUCT_REF, sentence=PRODUCT_SENTENCE)

    assert result.analyst_output is not None, result.errors
    assert result.cached_source_ids == [release]
    assert _labels(result)[release] == "first-party"
    override = _overrides(result)[release]
    assert override.independence == Independence.FIRST_PARTY
    assert override.code_relabel is True
    assert "newswire" in override.reason.lower()


@pytest.mark.asyncio
async def test_a_newswire_release_about_another_organization_stays_off_entity(tmp_path) -> None:
    """Control: a release that never names the entity is another organization's
    self-report, so the off-entity rule still makes it ``unknown``."""
    write_product(tmp_path)
    pages = {u: "Another Company announced a product. Third parties confirm the energy data." for u in URLS}
    with scripted_agents(
        search=fake_execute_searches(URLS, pages),
        ingestor=ingest_model(publisher=NEWSWIRE_PUBLISHER),
    ):
        result = await _run(tmp_path, ref=PRODUCT_REF, sentence=PRODUCT_SENTENCE)

    assert result.analyst_output is not None, result.errors
    assert set(_labels(result).values()) == {"unknown"}
    assert all(o.reason.startswith("Off-entity") for o in _overrides(result).values())


@pytest.mark.asyncio
async def test_a_newswire_release_on_a_subject_claim_is_first_party(tmp_path) -> None:
    """A subject is a topic, not an organization: the classifier's label stands."""
    write_entity(tmp_path)
    with scripted_agents(ingestor=ingest_model(publisher="PR Newswire")):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert set(_labels(result).values()) == {"first-party"}, _labels(result)


# --------------------------------------------------------------------------- #
# RE-AL row 2: the level fit runs in the loop, before the Evaluator              #
# --------------------------------------------------------------------------- #


def test_the_level_fit_lives_in_the_loop_and_the_writer_only_records_its_note() -> None:
    import orchestrator.cli as cli
    import orchestrator.persistence as persistence
    from loop.fit import fit_verdict_to_written_pool

    assert callable(fit_verdict_to_written_pool)
    assert not hasattr(persistence, "fit_verdict_to_written_pool")
    assert "fit_verdict_to_written_pool" not in inspect.getsource(persistence)
    assert "fit_verdict_to_written_pool" not in inspect.getsource(cli)


@pytest.mark.asyncio
async def test_the_fit_runs_before_the_evaluator_so_the_comparison_sees_the_fitted_confidence(tmp_path) -> None:
    """Every source is the subject's own (publisher equals the entity name), so the fit
    lowers ``independently-verified`` and caps confidence before the Evaluator compares."""
    write_entity(tmp_path)
    analyst = analyst_args(level="independently-verified", confidence="medium")
    with scripted_agents(
        analyst=analyst, auditor=auditor_args(verdict="mixed", confidence="medium"),
        ingestor=ingest_model(publisher="Probe Subject"),
    ):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert result.level_clamp and "independently-verified lowered to" in result.level_clamp
    assert result.analyst_output.verdict.verification_level in (VerificationLevel.SELF_REPORTED, VerificationLevel.CLAIMED)
    assert result.analyst_output.verdict.confidence == Confidence.LOW
    assert result.consistency is not None
    assert result.consistency.primary_confidence == Confidence.LOW
    assert result.consistency.assessed_confidence == Confidence.MEDIUM
    assert result.consistency.confidence_agrees is False


def test_the_sidecar_confidence_is_post_fit_while_level_clamp_carries_the_note(tmp_path) -> None:
    write_entity(tmp_path)
    analyst = analyst_args(level="independently-verified", confidence="medium")
    with scripted_agents(
        analyst=analyst, auditor=auditor_args(verdict="mixed", confidence="medium"),
        ingestor=ingest_model(publisher="Probe Subject"),
    ):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    sidecar = _sidecar(tmp_path)
    assert sidecar["audit"]["analyst_confidence"] == "low"
    assert sidecar["audit"]["auditor_confidence"] == "medium"
    assert sidecar["audit"]["confidence_agrees"] is False
    assert "independently-verified lowered to" in sidecar["pipeline_run"]["level_clamp"]
    fm = _claim_fm(tmp_path)
    assert fm["confidence"] == "low"
    assert fm["verification_level"] in ("self-reported", "claimed")


def test_an_analyst_chosen_capped_level_keeps_its_confidence_and_lint_flags_it(tmp_path) -> None:
    """Carried SP2-6: the fit lowers confidence only when it lowers the level. An analyst
    that picks ``claimed`` at medium confidence is written as it answered, with no
    ``level_clamp``, and ``dr lint``'s ``confidence-cap-violation`` is reachable again."""
    from linter.checks import check_confidence_cap_violation

    write_entity(tmp_path)
    with scripted_agents(analyst=analyst_args(level="claimed", confidence="medium")):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    fm = _claim_fm(tmp_path)
    assert fm["verification_level"] == "claimed"
    assert fm["confidence"] == "medium"
    sidecar = _sidecar(tmp_path)
    assert "level_clamp" not in sidecar["pipeline_run"]
    assert sidecar["audit"]["analyst_confidence"] == "medium"
    claim, _sidecar_path = _claim_and_sidecar(tmp_path)
    issues = check_confidence_cap_violation([claim], {str(claim): fm})
    assert [i.check_id for i in issues] == ["confidence-cap-violation"]


@pytest.mark.asyncio
async def test_rerun_analyst_fits_the_level_against_the_stored_sources(tmp_path) -> None:
    """``dr draft --rerun analyst`` reads the fit from the loop's result, not from the writer."""
    import loop

    write_entity(tmp_path)
    sources = [
        {"source_id": f"2026/own-{i}", "url": u, "title": f"Own page {i}", "publisher": "Probe Subject",
         "summary": "The subject's own page.", "key_quotes": [], "body": "Own body.", "slug": f"own-{i}",
         "kind": "article", "independence": "first-party"}
        for i, u in enumerate(URLS)
    ]
    with scripted_agents(analyst=analyst_args(level="independently-verified", confidence="medium")):
        result = await loop.rerun(claim_spec(tmp_path), loop_config(tmp_path), sources, agent="analyst")

    assert result.analyst_output is not None, result.errors
    assert result.level_clamp and "independently-verified lowered to claimed" in result.level_clamp
    assert result.analyst_output.verdict.verification_level == VerificationLevel.CLAIMED
    assert result.analyst_output.verdict.confidence == Confidence.LOW


# --------------------------------------------------------------------------- #
# RE-AL row 3: coverage re-derived from the fetched text after ingest            #
# --------------------------------------------------------------------------- #

# Every URL is tagged with both coverage sub-questions; the pages name sq1's
# terms ("publish", "energy", "data") and none of sq2's ("third", "parties",
# "confirm", "independent").
_SQ1_ONLY_PAGES = {u: f"Page {i + 1}. Probe Subject publishes its energy data in a yearly report." for i, u in enumerate(URLS)}
_BOTH_TAGS = {
    "kept": [{"url": u, "addresses": ["sq1", "sq2"], "score": 4.0} for u in URLS],
    "dropped": [], "rationale": "both",
}
_HARNESS_IDS = ["2026/report", "2026/second-report", "2026/third-report", "2026/fourth-report"]


@pytest.mark.asyncio
async def test_a_tag_whose_page_never_mentions_the_sub_question_terms_is_dropped_after_ingest(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(scorer=_BOTH_TAGS, search=fake_execute_searches(URLS, _SQ1_ONLY_PAGES)):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert sorted(result.sub_question_coverage["sq1"]) == sorted(_HARNESS_IDS)
    assert result.sub_question_coverage["sq2"] == []
    assert sorted(result.snippet_only["sq2"]) == sorted(_HARNESS_IDS)
    assert result.snippet_only.get("sq1", []) == []
    # The analyst sees the re-derived set on each source.
    for sd in result.sources:
        assert sd["addresses"] == ["sq1"]


def test_the_sidecar_marks_snippet_derived_tags_and_the_analyst_is_told_the_gap(tmp_path) -> None:
    captured: list[str] = []
    write_entity(tmp_path)
    with scripted_agents(
        scorer=_BOTH_TAGS, search=fake_execute_searches(URLS, _SQ1_ONLY_PAGES),
        analyst_model=capturing_model(captured, analyst_args()),
    ):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    block = {e["id"]: e for e in _sidecar(tmp_path)["sub_questions"]}
    assert block["sq2"]["citations"] == []
    assert sorted(block["sq2"]["snippet_only"]) == sorted(_HARNESS_IDS)
    assert sorted(block["sq1"]["citations"]) == sorted(_HARNESS_IDS)
    assert block["sq1"]["snippet_only"] == []
    prompt = captured[0]
    sq2_line = next(line for line in prompt.splitlines() if line.startswith("- sq2:"))
    assert "no source addresses this sub-question" in sq2_line
    sq1_line = next(line for line in prompt.splitlines() if line.startswith("- sq1:"))
    assert "no source addresses" not in sq1_line


@pytest.mark.asyncio
async def test_a_cached_source_is_checked_against_its_stored_text(tmp_path) -> None:
    """Dedup hits carry no fetched page: their title, summary, quotes and body stand in."""
    write_entity(tmp_path)
    confirming = _store_source(tmp_path, URLS[0], "confirming", body="Third parties confirm the figure.")
    silent = _store_source(tmp_path, URLS[1], "silent", body="Body.")
    scorer = {
        "kept": [{"url": u, "addresses": ["sq2"], "score": 4.0} for u in URLS],
        "dropped": [], "rationale": "sq2",
    }
    pages = {u: "Third parties confirm the energy data it publishes." for u in URLS}
    with scripted_agents(scorer=scorer, search=fake_execute_searches(URLS, pages)):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert sorted(result.cached_source_ids) == sorted([confirming, silent])
    assert confirming in result.sub_question_coverage["sq2"]
    assert silent not in result.sub_question_coverage["sq2"]
    assert result.snippet_only["sq2"] == [silent]


@pytest.mark.asyncio
async def test_entity_name_words_do_not_count_as_sub_question_terms(tmp_path) -> None:
    """Every page names the entity, so its name cannot be what confirms a tag."""
    write_entity(tmp_path)
    plan = planner_args()
    plan["sub_questions"] = [
        {"id": "sq1", "question": "Is Probe Subject large?", "rationale": "size"},
        {"id": "sq2", "question": "Do third parties confirm it?", "rationale": "independent axis"},
        COUNTER_SUB_QUESTION,
    ]
    plan["queries"] = [
        {"text": "probe subject", "sub_question_id": "sq1"},
        {"text": "probe subject energy independent", "sub_question_id": "sq2"},
        {"text": "probe subject electricity share disputed", "sub_question_id": "sq3"},
    ]
    scorer = {"kept": [{"url": u, "addresses": ["sq1"], "score": 4.0} for u in URLS], "dropped": [], "rationale": "sq1"}
    pages = {u: "Probe Subject data centers used more than 4% of US electricity in 2024." for u in URLS}
    with scripted_agents(planner=plan, scorer=scorer, search=fake_execute_searches(URLS, pages)):
        result = await _run(tmp_path)

    assert result.analyst_output is not None, result.errors
    assert result.sub_question_coverage["sq1"] == []
    assert sorted(result.snippet_only["sq1"]) == sorted(_HARNESS_IDS)


# --------------------------------------------------------------------------- #
# RE-AL row 4: cited sources the narrative never names by title                  #
# --------------------------------------------------------------------------- #


def test_uncited_by_title_lists_cited_ids_the_narrative_never_names() -> None:
    from analyst.agent import VerdictAssessment
    from analyst.citations import uncited_by_title

    sources = [
        {"source_id": "2026/a", "title": "AWS Cloud Sustainability"},
        {"source_id": "2026/b", "title": "Brave Transparency Report"},
        {"source_id": "2026/c", "title": "Unrelated"},
    ]
    verdict = VerdictAssessment(
        title="T", topics=["environmental-impact"], verdict="mixed", confidence="medium",
        narrative="Per *AWS Cloud Sustainability*, the picture is mixed.",
        verification_level="partially-verified", seo_title="T",
        cited_sources=["2026/a", "2026/b", "2026/missing"],
    )
    # Only cited ids that exist in ``sources`` and are not named by title, in sources order.
    assert uncited_by_title(verdict, sources) == ["2026/b"]


def test_a_cited_source_the_narrative_never_names_is_listed_in_the_sidecar_and_survives_a_rerun(tmp_path) -> None:
    write_entity(tmp_path)
    analyst = analyst_args(
        cited_sources=["2026/report", "2026/second-report"],
        narrative="Per *Report at report*, the evidence is mixed.",
    )
    with scripted_agents(analyst=analyst):
        result = _draft(tmp_path)
    assert result.exit_code == 0, result.output
    assert _claim_fm(tmp_path)["sources"] == ["2026/report", "2026/second-report"]
    assert _sidecar(tmp_path)["analyst_record"]["uncited_by_title"] == ["2026/second-report"]

    # A forced rerun rewrites the record through the claim writer's keep rules.
    with scripted_agents(analyst=analyst):
        rerun = _draft(tmp_path, "--force", sentence=None, mode=("--claim", f"{ENTITY_REF}/{CLAIM_STEM}"))
    assert rerun.exit_code == 0, rerun.output
    assert _sidecar(tmp_path)["analyst_record"]["uncited_by_title"] == ["2026/second-report"]


def test_every_cited_source_named_by_title_lists_nothing(tmp_path) -> None:
    write_entity(tmp_path)
    analyst = analyst_args(
        cited_sources=["2026/report", "2026/second-report"],
        narrative="Per *Report at report* and *Report at second-report*, the evidence is mixed.",
    )
    with scripted_agents(analyst=analyst):
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    assert _sidecar(tmp_path)["analyst_record"]["uncited_by_title"] == []


# --------------------------------------------------------------------------- #
# RE-AL row 5: cached sources do not shrink the fresh-ingest target              #
# --------------------------------------------------------------------------- #

_SIX_URLS = [*URLS, "https://example.org/fifth-report", "https://example.org/sixth-report"]


@pytest.mark.asyncio
async def test_two_cached_sources_still_ingest_max_sources_fresh_candidates(tmp_path) -> None:
    write_entity(tmp_path)
    cached = [_store_source(tmp_path, _SIX_URLS[0], "cached-a"), _store_source(tmp_path, _SIX_URLS[1], "cached-b")]
    pages = {u: "Probe Subject publishes energy data; third parties confirm it." for u in _SIX_URLS}
    with scripted_agents(scorer=scorer_args(_SIX_URLS), search=fake_execute_searches(_SIX_URLS, pages)):
        result = await _run(tmp_path, max_sources=4)

    assert result.analyst_output is not None, result.errors
    assert sorted(result.cached_source_ids) == sorted(cached)
    assert len(result.source_files) == 4, [u for u, _sf in result.source_files]
    assert len(result.sources) == 6


# --------------------------------------------------------------------------- #
# The counter-evidence sub-question                                              #
# --------------------------------------------------------------------------- #


def test_a_research_plan_needs_one_counter_evidence_sub_question_with_a_query() -> None:
    from researcher.planner import ResearchPlan

    coverage = [
        {"id": "sq1", "question": "Q1?", "rationale": "axis 1"},
        {"id": "sq2", "question": "Q2?", "rationale": "axis 2"},
    ]
    counter = {"id": "sq3", "question": "What would falsify it?", "rationale": "counter", "kind": "counter-evidence"}
    queries = [{"text": "q1", "sub_question_id": "sq1"}, {"text": "q2", "sub_question_id": "sq2"}]

    plan = ResearchPlan(sub_questions=[*coverage, counter], queries=[*queries, {"text": "q3", "sub_question_id": "sq3"}], rationale="r")
    assert [sq.kind for sq in plan.sub_questions] == ["coverage", "coverage", "counter-evidence"]

    with pytest.raises(ValidationError):
        ResearchPlan(sub_questions=coverage, queries=queries, rationale="no counter-evidence sub-question")
    with pytest.raises(ValidationError):
        ResearchPlan(sub_questions=[*coverage, counter], queries=queries, rationale="counter-evidence without a query")
    with pytest.raises(ValidationError):
        ResearchPlan(
            sub_questions=[*coverage, counter, {**counter, "id": "sq4"}],
            queries=[*queries, {"text": "q3", "sub_question_id": "sq3"}, {"text": "q4", "sub_question_id": "sq4"}],
            rationale="two counter-evidence sub-questions",
        )


def test_the_planner_instructions_ask_for_one_counter_evidence_sub_question() -> None:
    text = (PIPELINE_DIR / "researcher" / "planner.py").read_text(encoding="utf-8")
    assert "counter-evidence" in text
    assert re.search(r"falsif", text), "the instructions say the sub-question is the one that would falsify the claim"


def test_the_sidecar_records_the_counter_evidence_sub_question_with_its_query(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents():
        result = _draft(tmp_path)

    assert result.exit_code == 0, result.output
    sidecar = _sidecar(tmp_path)
    block = sidecar["sub_questions"]
    kinds = {e["id"]: e.get("kind") for e in block}
    assert kinds == {"sq1": "coverage", "sq2": "coverage", "sq3": "counter-evidence"}
    counter = next(e for e in block if e["id"] == "sq3")
    assert counter["queries"] == ["probe subject electricity share disputed"]
    assert "probe subject electricity share disputed" in sidecar["research"]["queries"]


def test_the_site_schema_declares_the_sub_questions_block() -> None:
    source = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    start = source.index("const auditSchema")
    block = source[start:source.index("human_review:", start)]
    assert "sub_questions:" in block
    for key in ("kind", "snippet_only", "citations", "queries"):
        assert key in block, f"sub_questions declares {key}"
    assert "counter-evidence" in block


# --------------------------------------------------------------------------- #
# Carried from the RE-AT review: per-URL null-body retry (SP2-2)                 #
# --------------------------------------------------------------------------- #


def _ingest_model_raising(exc: Exception, *, times: int, runs: list[str]) -> FunctionModel:
    """An ingest model whose first ``times`` runs raise ``exc``, then behaves like the harness model."""
    inner = ingest_model()

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        if not any(isinstance(p, ToolCallPart) for p in parts):
            runs.append("run")
            if len(runs) <= times:
                raise exc
        return await inner.function(messages, info)

    return FunctionModel(_fn)


async def _ingest_one(tmp_path, model: FunctionModel, url: str = URLS[0]):
    import datetime

    from ingestor.agent import ingestor_agent
    from loop import ingest_one

    cfg = loop_config(tmp_path, url_retry_delay_s=0.0)
    import asyncio
    async with httpx.AsyncClient() as client:
        with ingestor_agent.override(model=model), patch.object(
            ingestor_agent, "override", side_effect=lambda **kw: nullcontext(),
        ):
            return await ingest_one(
                client, url, cfg, datetime.date(2026, 10, 14), asyncio.Semaphore(2),
                prefetched_body="Probe Subject publishes energy data.",
            )


@pytest.mark.asyncio
async def test_a_null_body_on_one_url_is_retried_and_the_url_is_kept(tmp_path) -> None:
    runs: list[str] = []
    outcome = await _ingest_one(tmp_path, _ingest_model_raising(NULL_BODY, times=1, runs=runs))

    assert isinstance(outcome, tuple), outcome
    assert outcome[0] == URLS[0]
    assert len(runs) == 2


@pytest.mark.asyncio
async def test_an_exhausted_null_body_is_a_null_body_step_error(tmp_path) -> None:
    runs: list[str] = []
    outcome = await _ingest_one(tmp_path, _ingest_model_raising(NULL_BODY, times=5, runs=runs))

    assert not isinstance(outcome, tuple)
    assert outcome.error_type == "null_body"
    assert outcome.step == "ingest" and outcome.url == URLS[0]
    # One retry (``VerifyConfig.url_retries``), then the URL is given up.
    assert len(runs) == 2


@pytest.mark.asyncio
async def test_a_model_error_on_one_url_is_not_retried(tmp_path) -> None:
    runs: list[str] = []
    outcome = await _ingest_one(tmp_path, _ingest_model_raising(RuntimeError("scripted model failure"), times=5, runs=runs))

    assert not isinstance(outcome, tuple)
    assert outcome.error_type == "model_error"
    assert len(runs) == 1


def _http_error(status: int):
    from pydantic_ai.exceptions import ModelHTTPError

    return ModelHTTPError(status_code=status, model_name="scripted", body=None)


@pytest.mark.parametrize(("status", "error_type"), [(503, "http_error"), (429, "rate_limited")])
@pytest.mark.asyncio
async def test_a_provider_5xx_or_429_on_one_url_is_retried_as_transport(tmp_path, status, error_type) -> None:
    from loop import Rule, rule_for

    runs: list[str] = []
    outcome = await _ingest_one(tmp_path, _ingest_model_raising(_http_error(status), times=5, runs=runs))

    assert not isinstance(outcome, tuple)
    assert outcome.error_type == error_type
    assert rule_for(outcome.error_type) is Rule.TRANSPORT_RETRY
    # One retry (``VerifyConfig.url_retries``), then the URL is given up.
    assert len(runs) == 2

    runs.clear()
    recovered = await _ingest_one(tmp_path, _ingest_model_raising(_http_error(status), times=1, runs=runs))
    assert isinstance(recovered, tuple), recovered
    assert len(runs) == 2


def test_provider_http_errors_are_classified_by_status() -> None:
    from pydantic_ai.exceptions import ModelAPIError

    from loop import Rule, classify_exception

    assert classify_exception(_http_error(429)) == ("rate_limited", Rule.TRANSPORT_RETRY)
    assert classify_exception(_http_error(503)) == ("http_error", Rule.TRANSPORT_RETRY)
    assert classify_exception(_http_error(401)) == ("api_key_missing", Rule.CONFIG_FATAL)
    assert classify_exception(_http_error(400)) == ("model_error", Rule.FLAW_RETRY)
    assert classify_exception(ModelAPIError(model_name="scripted", message="Connection error.")) == (
        "http_error", Rule.TRANSPORT_RETRY,
    )


@pytest.mark.asyncio
async def test_a_provider_outage_on_every_page_is_a_transport_failure_of_the_ingest_step(tmp_path) -> None:
    from common.models import BlockedReason

    write_entity(tmp_path)
    ingests: list[str] = []
    with scripted_agents(ingestor=counting_ingest_model(ingests, fail=_http_error(503))):
        result = await _run(
            tmp_path, transport_retries=1, transport_backoff_s=(0.0,), url_retry_delay_s=0.0,
        )

    # Each URL is tried twice inside one step (``url_retries``), and the step twice.
    assert len(ingests) == 2 * 2 * len(URLS)
    finding = result.finding
    assert finding.step == "ingest"
    assert finding.error["error_type"] == "sources_unreachable"
    assert finding.rule == "transport-retry"
    assert finding.attempts == 2
    assert result.blocked_reason == BlockedReason.INSUFFICIENT_SOURCES


# --------------------------------------------------------------------------- #
# Carried: a recovered ingest retry records each error once (SP2-9)              #
# --------------------------------------------------------------------------- #


def _ingest_model_failing_once(url: str) -> FunctionModel:
    """Returns an unfetched source for ``url`` on its first request (ingest rejects it), then fetches."""
    inner = ingest_model()
    seen: list[str] = []

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        prompt = next(p.content for p in parts if isinstance(p, UserPromptPart))
        requested = prompt.split("URL: ", 1)[1].split("\n", 1)[0]
        if requested == url and not any(isinstance(p, ToolCallPart) for p in parts) and not seen:
            seen.append(requested)
            source = {"frontmatter": {
                "url": url, "title": "Unfetched", "publisher": "Example Publisher",
                "accessed_date": "2026-10-14", "kind": "article", "summary": "Invented.",
            }, "body": "Body.", "slug": "page", "year": 2026}
            return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])
        return await inner.function(messages, info)

    return FunctionModel(_fn)


@pytest.mark.asyncio
async def test_a_recovered_ingest_retry_records_each_error_once(tmp_path) -> None:
    write_entity(tmp_path)
    with scripted_agents(ingestor=_ingest_model_failing_once(URLS[3])):
        result = await _run(tmp_path, flaw_retries=1, llm_concurrency=1)

    assert result.analyst_output is not None, result.errors
    assert result.finding is not None and result.finding.outcome == "recovered"
    assert result.finding.step == "ingest"
    assert len(result.errors) == len(set(result.errors)), result.errors
    assert result.urls_failed == []
    assert sorted(sd["source_id"] for sd in result.sources) == sorted(_HARNESS_IDS)


# --------------------------------------------------------------------------- #
# Carried: the runbook names the tie-breaker's model variable (SP2-5)            #
# --------------------------------------------------------------------------- #


def test_the_runbook_names_the_tiebreaker_model_variable() -> None:
    runbook = (REPO_ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    assert "DR_TIEBREAKER_MODEL" in runbook


# --------------------------------------------------------------------------- #
# The old path is gone                                                           #
# --------------------------------------------------------------------------- #


def test_the_old_path_is_gone() -> None:
    loop_dir = PIPELINE_DIR / "loop"
    research = (loop_dir / "research.py").read_text(encoding="utf-8")
    ingest = (loop_dir / "ingest.py").read_text(encoding="utf-8")
    persistence = (PIPELINE_DIR / "orchestrator" / "persistence.py").read_text(encoding="utf-8")
    assert "def _invert_addresses" not in research, "coverage built from scorer tags alone"
    assert "max_sources - len(" not in ingest, "cached sources shrank the ingest target"
    assert "def fit_verdict_to_written_pool" not in persistence, "the fit moved to loop/fit.py"
    assert "fit_verdict_to_written_pool(" not in persistence, "the writer-time fit call"
