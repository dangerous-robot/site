"""Acceptance tests for RE-AS (One claim path): every claim reaches the loop through ``dr draft``.

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ SP6a (One claim path), "Tests that prove it"). Every case drives behaviour
through a public entry: the ``dr`` CLI under ``CliRunner`` with the four
agents on scripted models (``tests/loop_harness.py``), ``loop.run``, or a
public writer or template function. Nothing here patches a private name
under ``pipeline/loop/``; the only patch is a tripwire on the public
``loop.run`` for cases that must call no model.

Covered:

- ``dr draft --criterion <slug> --entity <ref>``: ``statement`` rendered once,
  ``criteria_slug`` and the criterion's topics stored, the file at
  ``<entity-dir>/<criteria_slug>.md``; the criterion's ``grading_rule``
  reaches both agents and ``notes`` neither; the Evaluator grades
  ``statement`` whatever the analyst titles; ``vocabulary`` is ignored;
  a criterion for another entity type, another subject, an unknown or an
  inactive slug is a usage error before any model call.
- ``dr draft --subject <slug> "<sentence>"``: the subject record is written
  once with the claim and never overwritten; an abandoned run leaves no
  record and no claim.
- ``dr draft --claim <ref> --force``: re-runs ``statement`` (``title`` when
  absent), keeps ``criteria_slug``, writes to the existing path; a non-draft
  returns to draft with the refresh trail (until SP5 (Recheck)); a failed
  run leaves the claim untouched; operator fields survive.
- the claim-path test: fixture copies of the eleven on-disk claims, set to
  draft and re-run, keep their paths.
- the grammar of ``dr draft``.
- ``dr draft --claim <ref> --criterion <new-slug>`` (attach): the entry
  appended from the stored claim, ``criteria_slug`` written, nothing else
  changed, no model call, the four refusals; ``dr review --approve`` then
  accepts the claim and lint reports no ``published-without-criterion``.
- ``dr step-analyze`` and ``dr step-audit`` read the stored ``statement``
  (one statement rule; closes the "Claim-text reconstruction duplicated"
  backlog row).
- the record and the code: ``statement`` declared; ``grading_rule`` declared
  and seeded; no template adapter on ``ClaimSpec``; ``analyse_claim`` needs a
  resolved entity; the old commands, modules, checkpoints, writers and
  wrapper scripts are gone; no underscore loop name imported outside the
  loop; the entity key set derived from the writer.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from common.frontmatter import parse_frontmatter
from common.utils import slugify
from tests.loop_harness import (
    ENTITY_NAME,
    ENTITY_REF,
    SENTENCE,
    URLS,
    analyst_args,
    auditor_args,
    capturing_model,
    claim_dir,
    failing_model,
    scripted_agents,
    write_entity,
    written_claims,
    written_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
TEMPLATES_FIXTURE = Path(__file__).parent / "fixtures" / "templates" / "templates.yaml"

SUBJECT_CRITERION = "uses-renewable-energy"
SUBJECT_STATEMENT = f"{ENTITY_NAME} uses renewable energy"
PRODUCT_REF = "products/probe-product"
PRODUCT_NAME = "Probe Product"
PRODUCT_CRITERION = "has-corporate-structure"
NOTES_SENTINEL = "NOTES-SENTINEL: reader-facing rationale"
RULE_SENTINEL = "RULE-SENTINEL: mixed = offsets only"

TEMPLATES_YAML = f"""templates:
  # Active criteria; the comment lines are part of the file and must survive an append.

  # --- Subject ---

  - slug: {SUBJECT_CRITERION}
    text: "ENTITY uses renewable energy"
    entity_type: subject
    subjects: [{ENTITY_REF}]
    topics: [ai-safety]
    core: true
    notes: "{NOTES_SENTINEL}"
    grading_rule: "{RULE_SENTINEL}"

  # --- Product ---

  - slug: {PRODUCT_CRITERION}
    text: "PRODUCT has STRUCTURE corporate structure"
    entity_type: product
    topics: [industry-analysis]
    core: true
    vocabulary:
      STRUCTURE:
        - publicly-traded
        - privately-held


# Deferred: the pipeline and the site read `templates:` only.

inactive_templates:

  - slug: data-jurisdiction
    text: "PRODUCT stores user data in JURISDICTION"
    entity_type: product
    topics: [data-privacy]
    core: true
"""


# --------------------------------------------------------------------------- #
# Helpers                                                                        #
# --------------------------------------------------------------------------- #


def _dr(repo_root: Path, *args: str):
    from orchestrator.cli import main

    return CliRunner().invoke(main, ["--model", "test", *args, "--repo-root", str(repo_root)])


def _draft_args(*args: str) -> list[str]:
    return ["draft", *args, "--skip-wayback"]


def _templates(repo_root: Path, text: str = TEMPLATES_YAML) -> Path:
    path = repo_root / "research" / "templates.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _capturing():
    """Scripted agents whose Analyst and Evaluator record their prompts."""
    analyst_prompts: list[str] = []
    auditor_prompts: list[str] = []
    ctx = scripted_agents(
        analyst_model=capturing_model(analyst_prompts, analyst_args()),
        auditor_model=capturing_model(auditor_prompts, auditor_args()),
    )
    return ctx, analyst_prompts, auditor_prompts


def _tripwire(monkeypatch) -> list[str]:
    """Make the public loop entry fail if a command reaches it."""
    import loop

    called: list[str] = []

    async def _run(*args, **kwargs):
        called.append("run")
        raise AssertionError("loop.run must not be called here")

    monkeypatch.setattr(loop, "run", _run)
    return called


def _write_claim(
    repo_root: Path,
    *,
    ref: str = ENTITY_REF,
    stem: str,
    statement: str | None,
    title: str | None = None,
    criteria_slug: str | None = None,
    status: str = "draft",
    verdict: str = "true",
    topics: tuple[str, ...] = ("environmental-impact",),
    reviewer: str | None = None,
    extra_fm: dict | None = None,
    analyst_record: dict | None = None,
) -> tuple[Path, Path]:
    """A claim file plus a valid sidecar at ``<entity-dir>/<stem>.md``; return both paths."""
    fm: dict = {"title": title or statement or stem}
    if statement is not None:
        fm["statement"] = statement
    fm.update({
        "entity": ref, "topics": list(topics), "verdict": verdict, "confidence": "high",
    })
    if criteria_slug:
        fm["criteria_slug"] = criteria_slug
    fm.update({"status": status, "as_of": "2026-10-01", "sources": ["2026/old"]})
    fm.update(extra_fm or {})
    claim_path = claim_dir(repo_root, ref) / f"{stem}.md"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim_path.write_text(
        f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nThe stored narrative.\n", encoding="utf-8",
    )
    sidecar = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst"]},
        "sources_consulted": [],
        "audit": None,
        "human_review": {
            "reviewed_at": "2026-10-02" if reviewer else None, "reviewer": reviewer,
            "notes": None, "pr_url": None,
        },
    }
    if analyst_record is not None:
        sidecar["analyst_record"] = analyst_record
    sidecar_path = claim_path.with_suffix(".audit.yaml")
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")
    return claim_path, sidecar_path


def _write_source(repo_root: Path, source_id: str = "2026/old", url: str = URLS[0]) -> Path:
    path = repo_root / "research" / "sources" / f"{source_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nurl: {url}\ntitle: Stored report\npublisher: Example Publisher\n"
        "accessed_date: 2026-01-01\nkind: article\nindependence: independent\n"
        "summary: Stored.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    return path


def _claim_ref(path: Path, repo_root: Path) -> str:
    return str(path.relative_to(repo_root / "research" / "claims").with_suffix(""))


def _fm(path: Path) -> dict:
    return parse_frontmatter(path.read_text(encoding="utf-8"))[0]


# --------------------------------------------------------------------------- #
# dr draft --criterion <slug> --entity <ref>                                     #
# --------------------------------------------------------------------------- #


def test_criterion_draft_stores_statement_and_criteria_slug_at_the_criterion_stem(tmp_path) -> None:
    write_entity(tmp_path)
    _templates(tmp_path)
    with scripted_agents():
        result = _dr(tmp_path, *_draft_args("--criterion", SUBJECT_CRITERION, "--entity", ENTITY_REF))

    assert result.exit_code == 0, result.output
    claim_path = claim_dir(tmp_path) / f"{SUBJECT_CRITERION}.md"
    assert written_claims(tmp_path) == [claim_path]
    fm = _fm(claim_path)
    assert fm["statement"] == SUBJECT_STATEMENT
    assert fm["title"] == SUBJECT_STATEMENT
    assert fm["criteria_slug"] == SUBJECT_CRITERION
    # The criterion's topics, not the scripted analyst's (environmental-impact).
    assert fm["topics"] == ["ai-safety"]
    assert fm["status"] == "draft"


def test_grading_rule_reaches_both_agents_and_notes_neither(tmp_path) -> None:
    """RE-AG (Analyst prompt: criterion notes and absence claims) end to end: the
    per-criterion ``grading_rule`` is the one text both agents get."""
    write_entity(tmp_path)
    _templates(tmp_path)
    ctx, analyst_prompts, auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, *_draft_args("--criterion", SUBJECT_CRITERION, "--entity", ENTITY_REF))

    assert result.exit_code == 0, result.output
    assert analyst_prompts and auditor_prompts
    assert all(RULE_SENTINEL in p for p in analyst_prompts)
    assert all(RULE_SENTINEL in p for p in auditor_prompts)
    assert not any(NOTES_SENTINEL in p for p in analyst_prompts + auditor_prompts)


def test_the_evaluator_grades_the_statement_whatever_the_analyst_titles(tmp_path) -> None:
    """RE-AD (Evaluator grades the claim), the one rule: ``statement`` is graded and
    written as ``title``; there is no title-failed outcome any more."""
    write_entity(tmp_path)
    _templates(tmp_path)
    auditor_prompts: list[str] = []
    with scripted_agents(
        analyst=analyst_args(title="A title the analyst rewrote freely"),
        auditor_model=capturing_model(auditor_prompts, auditor_args()),
    ):
        result = _dr(tmp_path, *_draft_args("--criterion", SUBJECT_CRITERION, "--entity", ENTITY_REF))

    assert result.exit_code == 0, result.output
    assert any(f"## Claim\n{SUBJECT_STATEMENT}\n" in p for p in auditor_prompts)
    assert not any("rewrote freely" in p.split("## Claim\n", 1)[1].split("\n", 1)[0] for p in auditor_prompts)
    fm = _fm(claim_dir(tmp_path) / f"{SUBJECT_CRITERION}.md")
    assert fm["title"] == SUBJECT_STATEMENT
    sidecar = yaml.safe_load((claim_dir(tmp_path) / f"{SUBJECT_CRITERION}.audit.yaml").read_text())
    assert sidecar["audit"]["auditor_verdict"] == "mixed"


def test_the_pipeline_ignores_vocabulary(tmp_path) -> None:
    """A criterion with a ``vocabulary`` map (a site-only key) renders with the
    placeholder as written and no "one of (...)" hint."""
    from common.templates import TemplateRecord, get_template, load_templates

    write_entity(tmp_path, PRODUCT_REF, PRODUCT_NAME)
    _templates(tmp_path)
    templates = load_templates(tmp_path)
    assert "vocabulary" not in {f.name for f in dataclasses.fields(TemplateRecord)}
    assert get_template(templates, SUBJECT_CRITERION).grading_rule == RULE_SENTINEL

    with scripted_agents():
        result = _dr(tmp_path, *_draft_args("--criterion", PRODUCT_CRITERION, "--entity", PRODUCT_REF))

    assert result.exit_code == 0, result.output
    fm = _fm(tmp_path / "research" / "claims" / "probe-product" / f"{PRODUCT_CRITERION}.md")
    assert fm["statement"] == f"{PRODUCT_NAME} has STRUCTURE corporate structure"
    assert "one of" not in fm["statement"]


def test_the_vocabulary_slot_code_is_gone() -> None:
    import common.templates as templates

    for name in (
        "render_claim_text", "validate_analyst_title", "render_blocked_title",
        "blocked_title_message", "VOCABULARY_HINT_PREFIX",
    ):
        assert not hasattr(templates, name), f"common.templates.{name} still exists"


@pytest.mark.parametrize(
    "criterion, entity_ref, entity_name",
    [
        (SUBJECT_CRITERION, PRODUCT_REF, PRODUCT_NAME),            # subject criterion, product entity
        (PRODUCT_CRITERION, ENTITY_REF, ENTITY_NAME),              # product criterion, subject entity
        (SUBJECT_CRITERION, "subjects/other-subject", "Other"),    # subject not in the criterion's list
        ("no-such-criterion", ENTITY_REF, ENTITY_NAME),            # unknown slug
        ("data-jurisdiction", PRODUCT_REF, PRODUCT_NAME),          # inactive slug
    ],
)
def test_a_criterion_that_does_not_apply_to_the_entity_is_a_usage_error(
    tmp_path, monkeypatch, criterion, entity_ref, entity_name,
) -> None:
    """From ``TestOnboardSubjectFanOut``: a criterion applies only to its entity
    type and, for a subject criterion, to the subjects it names."""
    write_entity(tmp_path, entity_ref, entity_name)
    _templates(tmp_path)
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args("--criterion", criterion, "--entity", entity_ref))

    assert result.exit_code == 2, result.output
    assert criterion in result.output
    assert called == []
    assert written_claims(tmp_path, entity_ref) == []


# --------------------------------------------------------------------------- #
# dr draft --subject <slug> "<sentence>"                                         #
# --------------------------------------------------------------------------- #

SP6_SLUG = "probe-sp6"
SP6_SENTENCE = "Probe Sp6 operators published their 2024 electricity use"


def _subject_file(repo_root: Path) -> Path:
    return repo_root / "research" / "entities" / "subjects" / f"{SP6_SLUG}.md"


def test_subject_draft_writes_the_subject_record_once_with_the_claim(tmp_path) -> None:
    with scripted_agents():
        result = _dr(tmp_path, *_draft_args("--subject", SP6_SLUG, SP6_SENTENCE))

    assert result.exit_code == 0, result.output
    entity_path = _subject_file(tmp_path)
    assert entity_path.exists()
    entity_fm = _fm(entity_path)
    assert entity_fm["type"] == "subject"
    assert slugify(entity_fm["name"]) == SP6_SLUG
    assert entity_fm["description"] == SP6_SENTENCE
    claim_path = tmp_path / "research" / "claims" / "subjects" / SP6_SLUG / f"{slugify(SP6_SENTENCE)}.md"
    assert claim_path.exists(), sorted((tmp_path / "research" / "claims").rglob("*.md"))
    fm = _fm(claim_path)
    assert fm["entity"] == f"subjects/{SP6_SLUG}"
    assert fm["statement"] == SP6_SENTENCE
    assert fm["title"] == SP6_SENTENCE
    assert "criteria_slug" not in fm

    # A second draft for the same subject reuses the record and never rewrites it.
    edited = entity_path.read_text(encoding="utf-8").replace(SP6_SENTENCE, "An operator-edited description")
    entity_path.write_text(edited, encoding="utf-8")
    second_sentence = "Probe Sp6 operators cut their water use in 2025"
    with scripted_agents():
        again = _dr(tmp_path, *_draft_args("--subject", SP6_SLUG, second_sentence))

    assert again.exit_code == 0, again.output
    assert entity_path.read_text(encoding="utf-8") == edited
    assert (claim_path.parent / f"{slugify(second_sentence)}.md").exists()


def test_subject_draft_uses_an_existing_record(tmp_path) -> None:
    write_entity(tmp_path, f"subjects/{SP6_SLUG}", "Custom Subject Name")
    before = _subject_file(tmp_path).read_text(encoding="utf-8")
    ctx, analyst_prompts, _auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, *_draft_args("--subject", SP6_SLUG, SP6_SENTENCE))

    assert result.exit_code == 0, result.output
    assert _subject_file(tmp_path).read_text(encoding="utf-8") == before
    assert any("Custom Subject Name" in p for p in analyst_prompts)


def test_an_abandoned_subject_run_leaves_no_record_and_no_claim(tmp_path) -> None:
    with scripted_agents(analyst_model=failing_model()):
        result = _dr(tmp_path, *_draft_args("--subject", SP6_SLUG, SP6_SENTENCE))

    assert result.exit_code != 0
    assert "analyst" in result.output.lower(), result.output
    assert not _subject_file(tmp_path).exists()
    assert not (tmp_path / "research" / "claims").exists()
    assert written_sources(tmp_path) == []


# --------------------------------------------------------------------------- #
# dr draft --claim <ref> --force                                                 #
# --------------------------------------------------------------------------- #


def test_claim_force_reruns_the_stored_statement_and_keeps_criteria_slug_and_path(tmp_path) -> None:
    """Closes the backlog row "`dr claim-draft --force` drops `criteria_slug`"."""
    write_entity(tmp_path)
    _templates(tmp_path)
    stored = "Probe Subject sourced half its power from wind in 2024"
    claim_path, _ = _write_claim(
        tmp_path, stem="a-stem-that-is-not-the-statement", statement=stored,
        title="An older title", criteria_slug=SUBJECT_CRITERION,
    )
    ctx, analyst_prompts, auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 0, result.output
    assert any(stored in p for p in analyst_prompts)
    assert any(f"## Claim\n{stored}\n" in p for p in auditor_prompts)
    assert written_claims(tmp_path) == [claim_path]
    fm = _fm(claim_path)
    assert fm["statement"] == stored
    assert fm["title"] == stored
    assert fm["criteria_slug"] == SUBJECT_CRITERION
    assert fm["verdict"] == "mixed"


def test_claim_force_sends_the_criterions_grading_rule_and_not_its_notes(tmp_path) -> None:
    """From ``test_cli.py`` ``test_criterion_notes_reach_the_loop_as_the_grading_rule``
    (claim-refresh): the rerun of a criterion-backed claim carries ``grading_rule``."""
    write_entity(tmp_path)
    _templates(tmp_path)
    claim_path, _ = _write_claim(
        tmp_path, stem=SUBJECT_CRITERION, statement=SUBJECT_STATEMENT, criteria_slug=SUBJECT_CRITERION,
    )
    ctx, analyst_prompts, auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 0, result.output
    assert analyst_prompts and auditor_prompts
    assert all(RULE_SENTINEL in p for p in analyst_prompts + auditor_prompts)
    assert not any(NOTES_SENTINEL in p for p in analyst_prompts + auditor_prompts)


def test_claim_force_note_names_the_real_flag_reason(tmp_path) -> None:
    """From ``test_cli.py`` ``TestClaimRefreshFlagReason``: agreeing verdicts with two
    evidence gaps are flagged for the gaps, not for a disagreement."""
    from tests.loop_harness import auditor_args

    write_entity(tmp_path)
    claim_path, _ = _write_claim(tmp_path, stem="gaps", statement="Probe Subject reports its water use")
    with scripted_agents(auditor=auditor_args(evidence_gaps=["no inventory", "no audit"])):
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 0, result.output
    assert f"Refreshed: {claim_path}" in result.output
    assert "Note: flagged for human review (2+ evidence gaps)." in result.output
    assert "verdict disagreement" not in result.output


def test_claim_force_falls_back_to_the_title_when_statement_is_absent(tmp_path) -> None:
    """The claims written before RE-AS carry no ``statement``; they re-run from ``title``."""
    write_entity(tmp_path)
    title = "Probe Subject reports its electricity use yearly"
    claim_path, _ = _write_claim(tmp_path, stem="reports-electricity-use", statement=None, title=title)
    ctx, analyst_prompts, _auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 0, result.output
    assert any(title in p for p in analyst_prompts)
    assert written_claims(tmp_path) == [claim_path]
    fm = _fm(claim_path)
    assert fm["statement"] == title
    assert fm["title"] == title


def test_claim_force_on_a_published_claim_returns_it_to_draft_with_the_refresh_trail(tmp_path) -> None:
    """From ``TestClaimRefreshKeepsPublishedState.test_snapshot_survives_refresh``; today's
    behaviour until SP5 (Recheck) refuses non-drafts."""
    write_entity(tmp_path)
    claim_path, sidecar_path = _write_claim(
        tmp_path, stem="published-claim", statement="Probe Subject runs on hydro power",
        status="published", reviewer="reviewer@example.org",
    )
    # The Evaluator agrees, so the analyst's verdict is the pipeline's and no tie-breaker runs.
    with scripted_agents(analyst=analyst_args(verdict="false"), auditor=auditor_args(verdict="false")):
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 0, result.output
    fm = _fm(claim_path)
    assert fm["status"] == "draft"
    assert fm["verdict"] == "false"
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["human_review"]["reviewed_at"] is None
    assert sidecar["refresh"]["previous"]["verdict"] == "true"
    assert sidecar["refresh"]["previous"]["reviewer"] == "reviewer@example.org"
    assert sidecar["refresh"]["dropped_sources"] == ["2026/old"]


def test_a_failed_claim_force_leaves_the_claim_untouched(tmp_path) -> None:
    """From ``test_failed_refresh_leaves_the_published_claim_untouched``."""
    write_entity(tmp_path)
    claim_path, sidecar_path = _write_claim(
        tmp_path, stem="published-claim", statement="Probe Subject runs on hydro power",
        status="published", reviewer="reviewer@example.org",
    )
    claim_before = claim_path.read_bytes()
    sidecar_before = sidecar_path.read_bytes()
    with scripted_agents(analyst_model=failing_model()):
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code != 0
    assert "analyst" in result.output.lower(), result.output
    assert claim_path.read_bytes() == claim_before
    assert sidecar_path.read_bytes() == sidecar_before
    assert written_sources(tmp_path) == []


def test_claim_force_keeps_the_operators_seo_title_and_cap_rationale(tmp_path) -> None:
    """From ``test_cli.py`` ``test_refresh_keeps_operator_seo_title_and_cap_rationale``
    (RE-AH, RE-AK): told apart through ``analyst_record``; the title is the statement."""
    write_entity(tmp_path)
    statement = "Probe Subject runs on hydro power"
    claim_path, _ = _write_claim(
        tmp_path, stem="hydro", statement=statement, status="draft",
        extra_fm={
            "confidence": "low", "verification_level": "claimed",
            "cap_rationale": "Operator rationale for the low cap.", "seo_title": "Operator seo title",
        },
        analyst_record={
            "title": statement, "seo_title": "Analyst seo title",
            "cap_rationale": "Analyst rationale.", "takeaway": None, "verdict": "true",
        },
    )
    with scripted_agents(analyst=analyst_args(level="claimed", cap_rationale="New analyst rationale.")):
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 0, result.output
    fm = _fm(claim_path)
    assert fm["seo_title"] == "Operator seo title"
    assert fm["cap_rationale"] == "Operator rationale for the low cap."


def test_claim_force_writes_the_fitted_level_and_its_note(tmp_path) -> None:
    """From ``test_cli.py`` ``test_refresh_lowers_a_level_the_written_sources_do_not_support``
    (RE-AE (Source pool independence)): the level fit only lowers, on the ``--claim --force`` form."""
    write_entity(tmp_path)
    claim_path, sidecar_path = _write_claim(
        tmp_path, stem="fitted-level", statement="Probe Subject reports its grid mix",
    )
    from tests.loop_harness import ingest_model

    # Every fetched page is published by the entity itself: no independent source is written.
    with scripted_agents(
        analyst=analyst_args(level="multiply-verified", confidence="medium"),
        ingestor=ingest_model(publisher=ENTITY_NAME),
    ):
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 0, result.output
    fm = _fm(claim_path)
    assert fm["confidence"] == "low"
    assert fm["verification_level"] == "claimed"
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    assert "multiply-verified lowered to claimed" in sidecar["pipeline_run"]["level_clamp"]


def test_claim_force_whose_directory_does_not_match_its_entity_is_refused_before_the_loop(
    tmp_path, monkeypatch,
) -> None:
    """The writer would refuse this after the paid loop; ``dr draft`` refuses it first."""
    write_entity(tmp_path)
    written, sidecar = _write_claim(tmp_path, stem="misplaced", statement="Probe Subject runs on wind")
    claim_path = tmp_path / "research" / "claims" / "subjects" / "another-subject" / "misplaced.md"
    claim_path.parent.mkdir(parents=True)
    written.rename(claim_path)
    sidecar.rename(claim_path.with_suffix(".audit.yaml"))
    before = claim_path.read_bytes()
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))

    assert result.exit_code == 1, result.output
    assert "Nothing was run" in result.output
    assert called == []
    assert claim_path.read_bytes() == before


def test_an_existing_claim_without_force_is_refused_before_the_loop(tmp_path, monkeypatch) -> None:
    """``--entity`` (and ``--criterion``, ``--subject``) over an existing file without ``--force``
    exits 1 before any model call and leaves the file alone."""
    write_entity(tmp_path)
    claim_path, _ = _write_claim(tmp_path, stem=slugify(SENTENCE), statement=SENTENCE)
    before = claim_path.read_bytes()
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args("--entity", ENTITY_REF, SENTENCE))

    assert result.exit_code == 1, result.output
    assert "already exists" in result.output
    assert called == []
    assert claim_path.read_bytes() == before


def test_claim_that_names_no_file_is_refused_before_the_loop(tmp_path, monkeypatch) -> None:
    """From ``TestClaimRefreshCLI.test_not_found_path_exits_with_error``."""
    write_entity(tmp_path)
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args("--claim", f"{ENTITY_REF}/no-such-claim", "--force"))
    assert result.exit_code != 0
    assert "no-such-claim" in result.output
    assert called == []


def test_claim_whose_entity_file_is_missing_is_a_usage_error(tmp_path, monkeypatch) -> None:
    """From ``TestClaimRefreshCLI.test_missing_entity_file_is_a_usage_error``."""
    claim_path, _ = _write_claim(tmp_path, stem="orphan", statement="Orphan statement")
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--force"))
    assert result.exit_code == 2, result.output
    assert ENTITY_REF in result.output
    assert called == []


# --------------------------------------------------------------------------- #
# The claim-path test: the eleven on-disk claims keep their paths               #
# --------------------------------------------------------------------------- #


# The eleven claims on disk when RE-AS (One claim path) landed, pinned so that later
# drafts (the SP3 (Restate inside the loop) cards, the Phase 4 attach runs) do not move
# this test. Paths relative to research/claims/.
ON_DISK_CLAIMS = (
    "chatgptree/renewable-energy-hosting.md",
    "earthly-insight/renewable-energy-hosting.md",
    "ecosia-ai/renewable-energy-hosting.md",
    "euria/renewable-energy-hosting.md",
    "greenpt/renewable-energy-hosting.md",
    "subjects/ai-model-producers/ai-producers-existential-score.md",
    "subjects/generative-ai/answering-a-generative-ai-prompt-uses-roughly-ten-times-the-electricity-of-a-web-search.md",
    "subjects/generative-ai/serving-generative-ai-answers-inference-now-uses-more-electricity-than-training-the-models.md",
    "subjects/generative-ai/using-generative-ai-harms-cognitive-ability.md",
    "subjects/us-data-centers/there-are-fewer-than-10-us-data-centers-that-are-certified-to-run-on-50-or-greater-renewable-energy-power-sources.md",
    "viro-ai/renewable-energy-hosting.md",
)


def _copy_research(tmp_path: Path) -> list[Path]:
    """Fixture copies of the eleven pinned claims (with sidecars), the entities and the
    criteria fixture; every claim set to draft."""
    from common.sidecar import sidecar_path_for

    research = REPO_ROOT / "research"
    shutil.copytree(research / "entities", tmp_path / "research" / "entities")
    shutil.copy(TEMPLATES_FIXTURE, tmp_path / "research" / "templates.yaml")
    if (research / "blocklist.yaml").exists():
        shutil.copy(research / "blocklist.yaml", tmp_path / "research" / "blocklist.yaml")
    claims: list[Path] = []
    for rel in ON_DISK_CLAIMS:
        src = research / "claims" / rel
        dest = tmp_path / "research" / "claims" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
        if sidecar_path_for(src).exists():
            shutil.copy(sidecar_path_for(src), sidecar_path_for(dest))
        text = dest.read_text(encoding="utf-8")
        dest.write_text(re.sub(r"^status: .*$", "status: draft", text, count=1, flags=re.M), encoding="utf-8")
        assert _fm(dest)["status"] == "draft"
        claims.append(dest)
    return sorted(claims)


def test_the_on_disk_claims_keep_their_paths_when_rerun_as_drafts(tmp_path) -> None:
    """The claim id and the site URL are the file path (interview Q10): ``--claim --force``
    writes back to the existing path even when ``statement`` differs from the stem."""
    claims = _copy_research(tmp_path)
    assert len(claims) == len(ON_DISK_CLAIMS) == 11
    before = {str(p.relative_to(tmp_path)): _fm(p) for p in claims}

    for path in claims:
        with scripted_agents():
            result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(path, tmp_path), "--force"))
        assert result.exit_code == 0, (path.name, result.output)

    after = sorted(p for p in (tmp_path / "research" / "claims").rglob("*.md"))
    assert [str(p.relative_to(tmp_path)) for p in after] == list(before)
    for rel, old in before.items():
        new = _fm(tmp_path / rel)
        assert new["statement"] == (old.get("statement") or old["title"]), rel
        assert new["title"] == new["statement"], rel
        assert new.get("criteria_slug") == old.get("criteria_slug"), rel
        assert new["entity"] == old["entity"], rel


# --------------------------------------------------------------------------- #
# Grammar                                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "args",
    [
        ["--claim", f"{ENTITY_REF}/some-claim", SENTENCE, "--force"],        # SENTENCE with --claim
        ["--criterion", SUBJECT_CRITERION, "--entity", ENTITY_REF, SENTENCE],  # SENTENCE with --criterion
        ["--entity", ENTITY_REF],                                            # --entity without SENTENCE
        ["--subject", SP6_SLUG],                                             # --subject without SENTENCE
        ["--entity", ENTITY_REF, "--subject", SP6_SLUG, SENTENCE],           # two mode flags
        ["--claim", f"{ENTITY_REF}/some-claim", "--subject", SP6_SLUG],      # two mode flags
        ["--claim", f"{ENTITY_REF}/some-claim", "--entity", ENTITY_REF, "--force"],  # two mode flags
        ["--criterion", SUBJECT_CRITERION],                                  # --criterion needs --entity
        [SENTENCE],                                                          # no mode flag
    ],
    ids=[
        "sentence-with-claim", "sentence-with-criterion", "entity-without-sentence",
        "subject-without-sentence", "entity-and-subject", "claim-and-subject", "claim-and-entity",
        "criterion-without-entity", "no-mode-flag",
    ],
)
def test_draft_grammar_errors_are_usage_errors_before_any_model_call(tmp_path, monkeypatch, args) -> None:
    write_entity(tmp_path)
    _templates(tmp_path)
    _write_claim(tmp_path, stem="some-claim", statement="Some statement")
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args(*args))
    assert result.exit_code == 2, result.output
    # The command's own grammar check, not click rejecting an unknown option.
    assert "No such option" not in result.output, result.output
    assert called == []


def test_claim_without_force_dry_run_or_criterion_is_a_usage_error(tmp_path, monkeypatch) -> None:
    """A ``--claim`` run always writes over an existing file, so the ``--force`` it
    would need is checked before the paid run, not after it (§ Run rules, Startup)."""
    write_entity(tmp_path)
    claim_path, _ = _write_claim(tmp_path, stem="some-claim", statement="Some statement")
    called = _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path)))
    assert result.exit_code == 2, result.output
    assert "--force" in result.output
    assert called == []


def test_claim_dry_run_reruns_the_statement_and_writes_nothing(tmp_path) -> None:
    write_entity(tmp_path)
    claim_path, sidecar_path = _write_claim(tmp_path, stem="some-claim", statement="Some statement")
    claim_before, sidecar_before = claim_path.read_bytes(), sidecar_path.read_bytes()
    ctx, analyst_prompts, _auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--dry-run"))

    assert result.exit_code == 0, result.output
    assert any("Some statement" in p for p in analyst_prompts)
    assert claim_path.read_bytes() == claim_before
    assert sidecar_path.read_bytes() == sidecar_before
    assert written_sources(tmp_path) == []


# --------------------------------------------------------------------------- #
# dr draft --claim <ref> --criterion <new-slug>: attach                           #
# --------------------------------------------------------------------------- #

NEW_SLUG = "probe-sp6-criterion"


def _attach_fixture(tmp_path: Path, *, ref: str = ENTITY_REF, name: str = ENTITY_NAME, **claim_kwargs):
    write_entity(tmp_path, ref, name)
    templates_path = _templates(tmp_path)
    kwargs = {"stem": slugify(SENTENCE), "statement": SENTENCE, "topics": ("environmental-impact", "ai-safety")}
    kwargs.update(claim_kwargs)
    claim_path, sidecar_path = _write_claim(tmp_path, ref=ref, **kwargs)
    return templates_path, claim_path, sidecar_path


def test_attach_appends_the_entry_from_the_stored_claim_and_calls_no_model(tmp_path, monkeypatch) -> None:
    from common.templates import get_template, load_templates

    templates_path, claim_path, sidecar_path = _attach_fixture(tmp_path)
    templates_before = templates_path.read_text(encoding="utf-8")
    old = yaml.safe_load(templates_before)
    claim_text_before = claim_path.read_text(encoding="utf-8")
    fm_before, body_before = parse_frontmatter(claim_text_before)
    sidecar_before = sidecar_path.read_bytes()
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--criterion", NEW_SLUG))

    assert result.exit_code == 0, result.output
    assert called == []
    entry = get_template(load_templates(tmp_path), NEW_SLUG)
    assert entry is not None
    assert entry.text == "ENTITY data centers used more than 4% of US electricity in 2024"
    assert entry.entity_type == "subject"
    assert entry.subjects == [ENTITY_REF]
    assert entry.topics == ["environmental-impact", "ai-safety"]
    assert entry.core is False
    # The file keeps its shape: the entry lands in `templates:`, the inactive list
    # and every comment line are untouched, and the earlier entries are unchanged.
    new = yaml.safe_load(templates_path.read_text(encoding="utf-8"))
    assert new["templates"][:-1] == old["templates"]
    assert new["templates"][-1]["slug"] == NEW_SLUG
    assert new["inactive_templates"] == old["inactive_templates"]
    new_text = templates_path.read_text(encoding="utf-8")
    for line in templates_before.splitlines():
        if line.lstrip().startswith("#"):
            assert line in new_text, line
    # The claim: only `criteria_slug` changes; the body, the path and the sidecar do not.
    assert written_claims(tmp_path) == [claim_path]
    fm_after, body_after = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    assert fm_after.pop("criteria_slug") == NEW_SLUG
    assert fm_after == fm_before
    assert body_after == body_before
    # One line is added and no other byte of the claim changes.
    assert claim_path.read_text(encoding="utf-8").replace(f"criteria_slug: {NEW_SLUG}\n", "", 1) == claim_text_before
    assert sidecar_path.read_bytes() == sidecar_before


def test_a_failed_registry_write_leaves_the_claim_and_the_registry_unchanged(tmp_path, monkeypatch) -> None:
    """The claim is written first and restored when the registry write fails, so no failure
    leaves a criterion in ``research/templates.yaml`` that no claim carries."""
    import orchestrator.persistence as persistence

    templates_path, claim_path, sidecar_path = _attach_fixture(tmp_path)
    before = {p: p.read_bytes() for p in (templates_path, claim_path, sidecar_path)}
    _tripwire(monkeypatch)

    def _fail(*args, **kwargs):
        raise OSError("simulated registry write failure")

    monkeypatch.setattr(persistence, "append_template_entry", _fail)
    result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--criterion", NEW_SLUG))

    assert result.exit_code == 1, result.output
    assert "simulated registry write failure" in result.output
    for path, data in before.items():
        assert path.read_bytes() == data, path.name


def test_attach_on_a_product_claim_uses_the_product_placeholder_and_no_subjects(tmp_path, monkeypatch) -> None:
    from common.templates import get_template, load_templates

    statement = "Probe Product discloses its training data sources"
    _templates_path, claim_path, _ = _attach_fixture(
        tmp_path, ref=PRODUCT_REF, name=PRODUCT_NAME, stem=slugify(statement), statement=statement,
        topics=("data-privacy",),
    )
    _tripwire(monkeypatch)
    result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--criterion", NEW_SLUG))

    assert result.exit_code == 0, result.output
    entry = get_template(load_templates(tmp_path), NEW_SLUG)
    assert entry.text == "PRODUCT discloses its training data sources"
    assert entry.entity_type == "product"
    assert entry.subjects == []
    assert entry.topics == ["data-privacy"]


@pytest.mark.parametrize(
    "case",
    ["existing-slug", "claim-has-criterion", "not-a-draft", "company-entity"],
)
def test_attach_refusals_change_nothing(tmp_path, monkeypatch, case) -> None:
    slug = NEW_SLUG
    kwargs: dict = {}
    if case == "existing-slug":
        slug = SUBJECT_CRITERION
    elif case == "claim-has-criterion":
        kwargs["criteria_slug"] = SUBJECT_CRITERION
    elif case == "not-a-draft":
        kwargs.update(status="published", reviewer="reviewer@example.org")
    if case == "company-entity":
        templates_path, claim_path, sidecar_path = _attach_fixture(
            tmp_path, ref="companies/probe-co", name="Probe Co",
            statement="Probe Co publishes an energy report", stem="publishes-an-energy-report",
        )
    else:
        templates_path, claim_path, sidecar_path = _attach_fixture(tmp_path, **kwargs)
    before = {p: p.read_bytes() for p in (templates_path, claim_path, sidecar_path)}
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, *_draft_args("--claim", _claim_ref(claim_path, tmp_path), "--criterion", slug))

    assert result.exit_code != 0, result.output
    assert "No such option" not in result.output, result.output
    assert called == []
    for path, data in before.items():
        assert path.read_bytes() == data, path.name


def test_after_attach_review_approve_accepts_the_claim_and_lint_is_clean(
    tmp_path, monkeypatch, human_at_terminal,
) -> None:
    from linter.checks import check_broken_criteria_slug, check_published_criterion
    from linter.runner import load_templates as load_template_slugs

    _templates_path, claim_path, _sidecar_path = _attach_fixture(tmp_path)
    ref = _claim_ref(claim_path, tmp_path)
    _tripwire(monkeypatch)
    attached = _dr(tmp_path, *_draft_args("--claim", ref, "--criterion", NEW_SLUG))
    assert attached.exit_code == 0, attached.output

    approved = _dr(tmp_path, "review", "--claim", ref, "--approve", "--reviewer", "reviewer@example.org")
    assert approved.exit_code == 0, approved.output
    fm = _fm(claim_path)
    assert fm["status"] == "published"
    assert fm["criteria_slug"] == NEW_SLUG
    fms = {str(claim_path): fm}
    assert check_published_criterion([claim_path], fms) == []
    assert check_broken_criteria_slug([claim_path], fms, load_template_slugs(tmp_path)) == []


# --------------------------------------------------------------------------- #
# One statement rule for the side tools (until SP7 (Fold side tools) folds them) #
# --------------------------------------------------------------------------- #


def test_step_analyze_reads_the_stored_statement(tmp_path) -> None:
    write_entity(tmp_path)
    _write_source(tmp_path)
    stored = "Probe Subject reports its water use yearly"
    claim_path, _ = _write_claim(tmp_path, stem="water-use", statement=stored, title="An older title")
    ctx, analyst_prompts, _auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, "step-analyze", "--claim", _claim_ref(claim_path, tmp_path))

    assert result.exit_code == 0, result.output
    assert any(stored in p for p in analyst_prompts)
    assert not any("An older title" in p for p in analyst_prompts)


def test_step_audit_grades_the_stored_statement(tmp_path) -> None:
    write_entity(tmp_path)
    _write_source(tmp_path)
    stored = "Probe Subject reports its water use yearly"
    claim_path, _ = _write_claim(tmp_path, stem="water-use", statement=stored, title="An older title")
    ctx, _analyst_prompts, auditor_prompts = _capturing()
    with ctx:
        result = _dr(tmp_path, "step-audit", "--claim", _claim_ref(claim_path, tmp_path))

    assert result.exit_code == 0, result.output
    assert any(f"## Claim\n{stored}\n" in p for p in auditor_prompts)


# --------------------------------------------------------------------------- #
# The record and the code                                                        #
# --------------------------------------------------------------------------- #


def _zod_block(start: str, end: str) -> str:
    source = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    return source[source.index(start):source.index(end)]


def test_statement_is_a_declared_claim_key() -> None:
    from linter.checks import CANONICAL_CLAIM_KEYS
    from orchestrator.persistence import CLAIM_FRONTMATTER_KEYS

    assert "statement" in CLAIM_FRONTMATTER_KEYS
    assert "statement" in CANONICAL_CLAIM_KEYS
    claims_schema = _zod_block("const claims = defineCollection", "const entities = defineCollection")
    assert re.search(r"^\s*statement: z\.string\(\)", claims_schema, re.M), "statement is not in the claims schema"


def test_grading_rule_is_declared_and_seeded_for_every_active_criterion_with_notes() -> None:
    """The migration check: no active criterion with ``notes`` set has an empty
    ``grading_rule`` (seeded from ``notes``, marked for Brandon's rewrite)."""
    from common.templates import TemplateRecord

    assert "grading_rule" in {f.name for f in dataclasses.fields(TemplateRecord)}
    criteria_schema = _zod_block("const criteria = defineCollection", "export const collections")
    assert re.search(r"^\s*grading_rule: z\.string\(\)", criteria_schema, re.M)
    data = yaml.safe_load((REPO_ROOT / "research" / "templates.yaml").read_text(encoding="utf-8"))
    missing = [
        entry["slug"] for entry in data["templates"]
        if (entry.get("notes") or "").strip() and not (entry.get("grading_rule") or "").strip()
    ]
    assert missing == [], f"active criteria with notes but no grading_rule: {missing}"


def test_claim_spec_carries_no_template_adapter() -> None:
    from loop import ClaimSpec

    names = {f.name for f in dataclasses.fields(ClaimSpec)}
    assert "template" not in names
    assert {"statement", "entity", "criteria_slug", "topics", "grading_rule"} <= names


def test_analyse_claim_requires_a_resolved_entity() -> None:
    """The ``claim-draft -`` entity inference branch is gone: no caller passes None."""
    import loop

    params = inspect.signature(loop.analyse_claim).parameters
    assert params["resolved_entity"].default is inspect.Parameter.empty


def test_old_commands_are_gone() -> None:
    from orchestrator.cli import main

    top = CliRunner().invoke(main, ["--help"])
    assert top.exit_code == 0
    for name in ("onboard", "claim-refresh", "claim-promote", "entity-enrich"):
        assert name not in top.output, f"dr --help still lists {name}"
        gone = CliRunner().invoke(main, [name, "--help"])
        assert gone.exit_code != 0, f"dr {name} still exists"
    draft_help = CliRunner().invoke(main, ["draft", "--help"]).output
    for flag in ("--criterion", "--subject", "--claim", "--entity", "--dry-run", "--force"):
        assert flag in draft_help


def test_old_path_modules_writers_checkpoints_and_scripts_are_gone() -> None:
    import orchestrator.persistence as persistence

    for rel in (
        "pipeline/orchestrator/pipeline.py",
        "pipeline/researcher/entity_verifier.py",
        "pipeline/researcher/entity_enricher.py",
        "scripts/onboard-chatgpt.sh",
        "scripts/onboard-openai.sh",
    ):
        assert not (REPO_ROOT / rel).exists(), f"{rel} still exists"
    for name in ("_write_draft_entity_file", "update_entity_enrichment"):
        assert not hasattr(persistence, name), f"persistence.{name} still exists"
    # The checkpoint handlers, the onboard entity gates among them, went with RE-AT
    # (Rules, findings file, tie-breaker): no run asks a person anything.
    assert not (REPO_ROOT / "pipeline/orchestrator/checkpoints.py").exists()


def test_no_module_outside_the_loop_imports_an_underscore_loop_name() -> None:
    offenders: list[str] = []
    for path in sorted(PIPELINE_DIR.rglob("*.py")):
        rel = path.relative_to(PIPELINE_DIR)
        if rel.parts[0] in ("loop", "tests", ".venv") or "__pycache__" in rel.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module == "loop" or node.module.startswith("loop."):
                for alias in node.names:
                    if alias.name.startswith("_"):
                        offenders.append(f"{rel}: from {node.module} import {alias.name}")
    assert offenders == []


def test_entity_keys_come_from_the_writer_and_the_schema_declares_them() -> None:
    """``CANONICAL_ENTITY_KEYS`` is derived like ``CANONICAL_CLAIM_KEYS``; the drafts
    writer's ``status`` key leaves with it."""
    from linter.checks import CANONICAL_ENTITY_KEYS
    from orchestrator.persistence import ENTITY_FRONTMATTER_KEYS

    assert CANONICAL_ENTITY_KEYS == set(ENTITY_FRONTMATTER_KEYS)
    entities_schema = _zod_block("const entities = defineCollection", "const criteria = defineCollection")
    for key in ENTITY_FRONTMATTER_KEYS:
        # `website` is declared through the shared `httpUrl` schema, not `z.` directly.
        assert re.search(rf"^\s*{key}: (z|httpUrl)\.", entities_schema, re.M), f"{key} is not in the entities schema"
