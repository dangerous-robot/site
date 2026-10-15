"""Acceptance tests for RE-AY (Companies out): companies are not a claim target.

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ SP8 (Companies out), "Tests that prove it"; Q-B3 (companies) default).
Behaviour is driven only through public entries: the ``dr`` CLI under
``CliRunner`` and the public ``common.templates`` functions. The only patch
is a tripwire on the public ``loop.run``, which no refused mode may reach.

Covered:

- every ``dr draft`` mode whose entity is a company (``--entity``, its
  ``--dry-run``, ``--criterion ... --entity`` with a moved slug and with
  ``corporate-structure``, ``--claim`` with ``--force`` and ``--dry-run``,
  ``--claim --criterion`` attach, ``--restates --pick``, including a
  company claim with no restatement block or no such candidate, and an
  attach on a published claim or one that has ``criteria_slug``) exits 2 with one
  identical error line naming products and subjects, calls no loop and
  writes nothing (the whole tmp tree byte for byte, no findings);
- the refusal runs before entity resolution, so a company ref with no
  entity file gets the same error, and a ref spelled with ``..`` or ``./``,
  in other casing (``Companies``), or through the repo's own directory name
  is refused too, in ``--entity``, ``--criterion`` and a stored claim's
  ``entity:`` (``companies/../products/<slug>`` included: its type comes
  from the raw first segment);
- an inactive criterion is refused by ``--criterion`` for any entity type;
- a product ``--entity`` run still reaches the loop (a control proving
  the tripwire fires);
- ``inactive: true`` on a criterion: ``load_templates`` reads it and
  ``templates_for_entity_type("company")`` returns nothing on a fixture
  copy in the post-RE-AY shape;
- the real ``research/templates.yaml``: ``corporate-structure`` stays under
  ``templates:`` with ``inactive: true`` and its ``STRUCTURE`` vocabulary
  (the Responsible AI matrix's ownership row is validated against it),
  the four other company criteria sit under ``inactive_templates:``, and
  no other company criterion is active;
- the site's criteria schema declares the optional ``inactive`` key.

The site build and the matrix check against the real file are covered by
``npm run build`` (pre-commit hook) and ``src/lib/matrixCheck.test.ts``
(``npm run test:site``, which reads the real ``research/templates.yaml``
through ``activeCriteria()``).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from orchestrator.cli import _COMPANY_REFUSAL
from tests.loop_harness import write_entity

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_FIXTURE = Path(__file__).parent / "fixtures" / "templates" / "templates.yaml"

COMPANY_REF = "companies/probe-co"
COMPANY_NAME = "Probe Co"
COMPANY_SENTENCE = "Probe Co publishes an annual energy report"
COMPANY_CLAIM_STEM = "publishes-an-annual-energy-report"
PRODUCT_REF = "products/probe-product"
PRODUCT_NAME = "Probe Product"

MOVED_COMPANY_SLUGS = (
    "publishes-sustainability-report",
    "contributes-to-ai-safety",
    "contributes-to-environmental-causes",
    "financial-transparency",
)
KEPT_COMPANY_SLUG = "corporate-structure"
STRUCTURE_WORDS = [
    "publicly-traded", "privately-held", "non-profit", "B-corp",
    "employee-owned", "steward-ownership", "cooperative",
]


# --------------------------------------------------------------------------- #
# Helpers                                                                        #
# --------------------------------------------------------------------------- #


def _dr(repo_root: Path, *args: str):
    from orchestrator.cli import main

    return CliRunner().invoke(main, ["--model", "test", *args, "--repo-root", str(repo_root)])


def _tripwire(monkeypatch) -> list[str]:
    """Make the public loop entry record and fail if a command reaches it."""
    import loop

    called: list[str] = []

    async def _run(*args, **kwargs):
        called.append("run")
        raise AssertionError("loop.run must not be called for a company entity")

    monkeypatch.setattr(loop, "run", _run)
    return called


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` with its bytes, so "nothing written" is checked whole."""
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _error_line(output: str) -> str:
    """The one ``Error:`` line a refusal prints (click puts it last for a usage error)."""
    lines = [line for line in output.splitlines() if line.startswith("Error:")]
    assert len(lines) == 1, output
    return lines[0]


def _post_ay_templates() -> dict:
    """The fixture copy of research/templates.yaml in the post-RE-AY shape.

    The four company criteria no matrix row names move to
    ``inactive_templates:``; ``corporate-structure`` stays under
    ``templates:`` with ``inactive: true``.
    """
    data = yaml.safe_load(TEMPLATES_FIXTURE.read_text(encoding="utf-8"))
    moved = [t for t in data["templates"] if t["slug"] in MOVED_COMPANY_SLUGS]
    assert len(moved) == len(MOVED_COMPANY_SLUGS), "the fixture copy lost a company criterion"
    data["templates"] = [t for t in data["templates"] if t["slug"] not in MOVED_COMPANY_SLUGS]
    for t in data["templates"]:
        if t["slug"] == KEPT_COMPANY_SLUG:
            t["inactive"] = True
    data["inactive_templates"] = moved + list(data.get("inactive_templates") or [])
    return data


def _write_templates(repo_root: Path) -> Path:
    path = repo_root / "research" / "templates.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(_post_ay_templates(), sort_keys=False), encoding="utf-8")
    return path


def _write_company_claim(
    repo_root: Path, *, restatement: bool = False, ref: str = COMPANY_REF, **fm_extra,
) -> str:
    """A draft company claim plus a valid sidecar at the flat company path; return its ref.

    Company and product claims share ``research/claims/<slug>/``
    (``_claim_dir_for``), so only the claim's ``entity:`` says it is a
    company's. With ``restatement`` the sidecar carries a pickable
    candidate, so the only reason ``--restates`` can refuse is the company.
    """
    slug = ref.split("/", 1)[1]
    claim_path = repo_root / "research" / "claims" / slug / f"{COMPANY_CLAIM_STEM}.md"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": COMPANY_SENTENCE, "statement": COMPANY_SENTENCE, "entity": ref,
        "topics": ["environmental-impact"], "verdict": "unverified", "confidence": "low",
        "status": "draft", "as_of": "2026-10-01", "sources": [],
    }
    fm.update(fm_extra)
    claim_path.write_text(
        f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nThe stored narrative.\n", encoding="utf-8",
    )
    sidecar: dict = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst"]},
        "sources_consulted": [],
        "audit": None,
        "human_review": {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None},
    }
    if restatement:
        sidecar["restatement"] = {
            "candidates": [
                {"rank": 1, "text": "Probe Co published an energy report for 2025", "expected_verdict": "true"},
            ],
        }
    claim_path.with_suffix(".audit.yaml").write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")
    return f"{slug}/{COMPANY_CLAIM_STEM}"


def _company_repo(tmp_path: Path, *, entity_file: bool = True, restatement: bool = False) -> str:
    if entity_file:
        write_entity(tmp_path, COMPANY_REF, COMPANY_NAME)
    write_entity(tmp_path, PRODUCT_REF, PRODUCT_NAME)
    _write_templates(tmp_path)
    return _write_company_claim(tmp_path, restatement=restatement)


def _mode_args(mode: str, claim_ref: str) -> list[str]:
    return {
        "entity": ["draft", "--entity", COMPANY_REF, COMPANY_SENTENCE],
        "entity-dry-run": ["draft", "--dry-run", "--entity", COMPANY_REF, COMPANY_SENTENCE],
        "criterion-moved": ["draft", "--criterion", MOVED_COMPANY_SLUGS[0], "--entity", COMPANY_REF],
        "criterion-kept": ["draft", "--criterion", KEPT_COMPANY_SLUG, "--entity", COMPANY_REF],
        "claim-force": ["draft", "--claim", claim_ref, "--force"],
        "claim-dry-run": ["draft", "--claim", claim_ref, "--dry-run"],
        "claim-attach": ["draft", "--claim", claim_ref, "--criterion", "probe-co-energy-report"],
        "restates": ["draft", "--restates", claim_ref, "--pick", "1"],
    }[mode] + ["--skip-wayback"] * (mode != "claim-attach")


ALL_MODES = (
    "entity", "entity-dry-run", "criterion-moved", "criterion-kept",
    "claim-force", "claim-dry-run", "claim-attach", "restates",
)


# --------------------------------------------------------------------------- #
# dr draft refuses every mode on a company entity                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", ALL_MODES)
def test_every_draft_mode_on_a_company_is_one_usage_error_and_writes_nothing(tmp_path, monkeypatch, mode) -> None:
    claim_ref = _company_repo(tmp_path, restatement=(mode == "restates"))
    before = _snapshot(tmp_path)
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, *_mode_args(mode, claim_ref))

    assert result.exit_code == 2, result.output
    line = _error_line(result.output)
    assert "products and subjects" in line, line
    assert called == []
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "research" / "findings").exists()


def test_the_refusal_text_is_the_same_for_every_mode(tmp_path, monkeypatch) -> None:
    """One error, byte for byte: the message names no ref, so the lines compare equal."""
    lines: dict[str, str] = {}
    for mode in ALL_MODES:
        root = tmp_path / mode
        root.mkdir()
        claim_ref = _company_repo(root, restatement=(mode == "restates"))
        _tripwire(monkeypatch)
        result = _dr(root, *_mode_args(mode, claim_ref))
        assert result.exit_code == 2, f"{mode}: {result.output}"
        lines[mode] = _error_line(result.output)

    assert len(set(lines.values())) == 1, lines


def _assert_refused_and_unchanged(root: Path, monkeypatch, *args: str) -> None:
    before = _snapshot(root)
    called = _tripwire(monkeypatch)
    result = _dr(root, *args)
    assert result.exit_code == 2, result.output
    assert _error_line(result.output) == f"Error: {_COMPANY_REFUSAL}"
    assert called == []
    assert _snapshot(root) == before


def test_restates_on_a_company_claim_with_no_restatement_block_is_refused(tmp_path, monkeypatch) -> None:
    """The usual state of a claim: the company refusal comes before the block lookup."""
    claim_ref = _company_repo(tmp_path, restatement=False)
    _assert_refused_and_unchanged(tmp_path, monkeypatch, *_mode_args("restates", claim_ref))


def test_restates_on_a_company_claim_with_a_missing_candidate_is_refused(tmp_path, monkeypatch) -> None:
    claim_ref = _company_repo(tmp_path, restatement=True)
    _assert_refused_and_unchanged(
        tmp_path, monkeypatch, "draft", "--restates", claim_ref, "--pick", "3", "--skip-wayback",
    )


@pytest.mark.parametrize("fm_extra", [{"status": "published"}, {"criteria_slug": "already-there"}])
def test_attach_on_a_company_claim_is_refused_before_the_status_and_criterion_checks(
    tmp_path, monkeypatch, fm_extra,
) -> None:
    write_entity(tmp_path, COMPANY_REF, COMPANY_NAME)
    _write_templates(tmp_path)
    claim_ref = _write_company_claim(tmp_path, **fm_extra)
    _assert_refused_and_unchanged(tmp_path, monkeypatch, *_mode_args("claim-attach", claim_ref))


# ``companies/../products/<slug>`` loads a product file, but ``parse_entity_ref``
# types the run from the raw first segment, so it would be a company-typed claim.
COMPANY_TYPED_PRODUCT_REF = f"companies/../{PRODUCT_REF}"
# The last two load the company file but start with ``..`` or ``Companies`` once
# normalised; the second loads it only on a case-insensitive file system (macOS).
OTHER_SPELLINGS = [
    "products/../companies/probe-co",
    "./companies/probe-co",
    COMPANY_TYPED_PRODUCT_REF,
    "products/../../entities/companies/probe-co",
    "products/../Companies/probe-co",
]


@pytest.mark.parametrize("ref", OTHER_SPELLINGS)
def test_a_company_ref_spelled_another_way_is_refused(tmp_path, monkeypatch, ref) -> None:
    _company_repo(tmp_path)
    _assert_refused_and_unchanged(
        tmp_path, monkeypatch, "draft", "--dry-run", "--entity", ref, COMPANY_SENTENCE, "--skip-wayback",
    )


@pytest.mark.parametrize("slug", [MOVED_COMPANY_SLUGS[0], KEPT_COMPANY_SLUG])
@pytest.mark.parametrize("ref", OTHER_SPELLINGS)
def test_criterion_on_a_company_ref_spelled_another_way_is_refused(tmp_path, monkeypatch, ref, slug) -> None:
    _company_repo(tmp_path)
    _assert_refused_and_unchanged(
        tmp_path, monkeypatch, "draft", "--criterion", slug, "--entity", ref, "--skip-wayback",
    )


@pytest.mark.parametrize("mode", ["claim-force", "claim-dry-run", "claim-attach", "restates"])
@pytest.mark.parametrize("ref", OTHER_SPELLINGS)
def test_a_stored_claim_whose_entity_is_a_company_spelled_another_way_is_refused(
    tmp_path, monkeypatch, mode, ref,
) -> None:
    """The claim sits in the product's folder, so only its ``entity:`` value makes it a company's."""
    _company_repo(tmp_path)
    claim_ref = _write_company_claim(tmp_path, restatement=(mode == "restates"), ref=PRODUCT_REF, entity=ref)
    _assert_refused_and_unchanged(tmp_path, monkeypatch, *_mode_args(mode, claim_ref))


def _through_the_repo_dir(root: Path) -> str:
    """A company ref that climbs out of the repo and back in through its own directory name."""
    return f"products/../../../../{root.name}/research/entities/{COMPANY_REF}"


@pytest.mark.parametrize("mode", ["entity", "criterion-kept", "claim-force", "claim-attach"])
def test_a_company_ref_through_the_repo_directory_name_is_refused(tmp_path, monkeypatch, mode) -> None:
    """The check compares the entity file's place on disk, not only the ref's text."""
    _company_repo(tmp_path)
    ref = _through_the_repo_dir(tmp_path)
    assert (tmp_path / "research" / "entities" / f"{ref}.md").exists()
    if mode.startswith("claim"):
        claim_ref = _write_company_claim(tmp_path, ref=PRODUCT_REF, entity=ref)
        args = _mode_args(mode, claim_ref)
    else:
        args = [a if a != COMPANY_REF else ref for a in _mode_args(mode, "")]
        if mode == "entity":
            args.insert(1, "--dry-run")
    _assert_refused_and_unchanged(tmp_path, monkeypatch, *args)


def test_an_inactive_criterion_is_not_drafted_for_any_entity_type(tmp_path, monkeypatch) -> None:
    """``inactive: true`` keeps a criterion loadable by slug, but ``dr draft --criterion`` takes active ones only."""
    _company_repo(tmp_path)
    path = tmp_path / "research" / "templates.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for t in data["templates"]:
        if t["slug"] == "renewable-energy-hosting":
            t["inactive"] = True
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    before = _snapshot(tmp_path)
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, "draft", "--criterion", "renewable-energy-hosting", "--entity", PRODUCT_REF, "--skip-wayback")

    assert result.exit_code == 2, result.output
    assert "no active criterion" in _error_line(result.output)
    assert called == []
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("mode", ["entity", "criterion-moved", "criterion-kept"])
def test_a_company_ref_with_no_entity_file_gets_the_same_refusal(tmp_path, monkeypatch, mode) -> None:
    """The refusal reads the ref, before entity resolution and the criterion lookup."""
    with_file = tmp_path / "with-file"
    with_file.mkdir()
    claim_ref = _company_repo(with_file)
    _tripwire(monkeypatch)
    expected = _error_line(_dr(with_file, *_mode_args(mode, claim_ref)).output)

    no_file = tmp_path / "no-file"
    no_file.mkdir()
    claim_ref = _company_repo(no_file, entity_file=False)
    before = _snapshot(no_file)
    called = _tripwire(monkeypatch)

    result = _dr(no_file, *_mode_args(mode, claim_ref))

    assert result.exit_code == 2, result.output
    assert _error_line(result.output) == expected
    assert called == []
    assert _snapshot(no_file) == before


def test_control_a_product_entity_still_reaches_the_loop(tmp_path, monkeypatch) -> None:
    """Control for the refusal tests: the tripwire fires when a mode is allowed."""
    _company_repo(tmp_path)
    monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", "tavily")  # a developer .env naming brave would stop at the key check
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, "draft", "--dry-run", "--entity", PRODUCT_REF, "Probe Product runs on wind", "--skip-wayback")

    assert called == ["run"], result.output


def test_control_a_product_claim_in_the_same_flat_layout_still_reaches_the_loop(tmp_path, monkeypatch) -> None:
    """Control: company and product claims share research/claims/<slug>/, so the
    refusal must read the claim's ``entity:``; a product claim there is re-run."""
    _company_repo(tmp_path)
    product_claim = _write_company_claim(tmp_path, ref=PRODUCT_REF)
    monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", "tavily")
    called = _tripwire(monkeypatch)

    result = _dr(tmp_path, "draft", "--claim", product_claim, "--dry-run", "--skip-wayback")

    assert called == ["run"], result.output


# --------------------------------------------------------------------------- #
# The inactive key                                                               #
# --------------------------------------------------------------------------- #


def test_templates_for_entity_type_skips_inactive_criteria(tmp_path) -> None:
    from common.templates import get_template, load_templates, templates_for_entity_type

    _write_templates(tmp_path)
    templates = load_templates(tmp_path)

    kept = get_template(templates, KEPT_COMPANY_SLUG)
    assert kept is not None, "corporate-structure must still load: the site and lint read it by slug"
    assert kept.inactive is True
    assert templates_for_entity_type(templates, "company") == []
    # Active criteria of the other types are untouched.
    product = templates_for_entity_type(templates, "product")
    assert len(product) == 8
    assert all(t.inactive is False for t in product)


def test_inactive_defaults_to_false(tmp_path) -> None:
    from common.templates import TemplateRecord

    record = TemplateRecord(slug="x", text="PRODUCT does Y", entity_type="product", topics=["ai-safety"], core=True)
    assert record.inactive is False


# --------------------------------------------------------------------------- #
# The real research/templates.yaml                                               #
# --------------------------------------------------------------------------- #


def _real_templates() -> dict:
    return yaml.safe_load((REPO_ROOT / "research" / "templates.yaml").read_text(encoding="utf-8"))


def test_the_real_registry_has_no_active_company_criterion_but_corporate_structure() -> None:
    data = _real_templates()
    active_company = [t["slug"] for t in data["templates"] if t["entity_type"] == "company"]
    assert active_company == [KEPT_COMPANY_SLUG]
    inactive_slugs = {t["slug"] for t in data["inactive_templates"]}
    assert set(MOVED_COMPANY_SLUGS) <= inactive_slugs


def test_corporate_structure_stays_for_the_matrix_with_inactive_true() -> None:
    """The Responsible AI matrix's ownership row is keyed on corporate-structure and
    validated against its vocabulary at build time (src/lib/matrixCheck.ts), and the
    site's criteria loader reads ``templates:`` only."""
    entry = next(t for t in _real_templates()["templates"] if t["slug"] == KEPT_COMPANY_SLUG)
    assert entry["inactive"] is True
    assert entry["vocabulary"] == {"STRUCTURE": STRUCTURE_WORDS}


def test_the_real_registry_gives_the_pipeline_no_company_criterion() -> None:
    from common.templates import load_templates, templates_for_entity_type

    assert templates_for_entity_type(load_templates(REPO_ROOT), "company") == []


# --------------------------------------------------------------------------- #
# The site schema declares the key                                               #
# --------------------------------------------------------------------------- #


def test_the_criteria_schema_declares_inactive_as_optional() -> None:
    source = (REPO_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    marker = "const criteria = defineCollection("
    start = source.index(marker)
    end = source.index("defineCollection(", start + len(marker))
    block = source[start:end]
    assert re.search(r"\binactive:\s*z\.boolean\(\)\.optional\(\)", block), (
        "the criteria schema in src/content.config.ts must declare `inactive: z.boolean().optional()`"
    )
