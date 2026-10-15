"""RE-AS (One claim path) parity with RE-AR (One loop, one writer): same files, plus ``statement``.

The goldens under ``tests/fixtures/sp1_parity/`` were recorded at commit
``841df4b`` (the RE-AR end state) by running the RE-AR acceptance fixtures
through today's commands: ``dr draft --entity`` for the ad hoc case and
``dr claim-refresh`` for the criterion-backed case. After RE-AS the same
fixtures run through ``dr draft --entity`` and ``dr draft --claim --force``
and must produce the same claim, sidecar and source files, with these
differences and no others:

- every claim gains ``statement``;
- the ad hoc claim's ``title`` (and the sidecar's ``analyst_record.title``)
  becomes the operator's sentence instead of the analyst's title, and its
  file stem is ``slugify(statement)`` (plan § SP6a, "the one intended
  difference");
- the sidecar's ``audit`` block gains ``pipeline_verdict``,
  ``pipeline_confidence`` and ``rule_applied`` (RE-AT, Rules, findings file,
  tie-breaker); the scripted analyst and Evaluator agree, so they are the
  analyst's verdict and confidence and ``agreed``;
- the sidecar's ``sub_questions`` block gains the harness plan's
  counter-evidence sub-question and, per entry, ``kind`` and ``snippet_only``;
  ``research.queries`` gains its query; ``analyst_record`` gains
  ``uncited_by_title`` (RE-BA, Source pool rules; ``_apply_re_ba_differences``).

Volatile values (``as_of``, ``ran_at``, ``run_id``, the per-agent
``models_used`` read from the operator's ``.env``) are replaced before the
comparison. ``sources_consulted`` is compared in URL order because ingest
runs two URLs at a time.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from common.frontmatter import parse_frontmatter
from common.utils import slugify
from tests.loop_harness import (
    ENTITY_NAME,
    ENTITY_REF,
    SENTENCE,
    analyst_args,
    claim_dir,
    scripted_agents,
    write_entity,
)

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "sp1_parity"
CRITERION_SLUG = "uses-renewable-energy"
CRITERION_STATEMENT = f"{ENTITY_NAME} uses renewable energy"
CRITERION_CLAIM_REF = f"{ENTITY_REF}/{CRITERION_SLUG}"
_VOLATILE = {"as_of": "DATE", "ran_at": "TS", "run_id": "RUNID"}


def _normalize(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in _VOLATILE:
                out[key] = _VOLATILE[key]
            elif key == "models_used" and isinstance(value, dict):
                # Per-agent models come from the operator's .env, not the fixture.
                out[key] = {agent: "MODEL" for agent in value}
            elif key == "sources_consulted" and isinstance(value, list):
                out[key] = sorted((_normalize(v) for v in value), key=lambda e: str(e.get("url", "")))
            else:
                out[key] = _normalize(value)
        return out
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    return obj


def _plain(obj):
    """JSON round trip so dates and enums compare as strings on both sides."""
    return json.loads(json.dumps(_normalize(obj), default=str, sort_keys=True))


def collect(repo_root: Path, ref: str = ENTITY_REF) -> dict:
    """The one claim, its sidecar and every source file under ``repo_root``, normalized."""
    claims = sorted(claim_dir(repo_root, ref).glob("*.md"))
    assert len(claims) == 1, claims
    claim_path = claims[0]
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    sidecar = yaml.safe_load(claim_path.with_suffix(".audit.yaml").read_text(encoding="utf-8"))
    sources_dir = repo_root / "research" / "sources"
    sources = {
        str(p.relative_to(sources_dir)): p.read_text(encoding="utf-8")
        for p in sorted(sources_dir.rglob("*.md"))
    }
    return {
        "stem": claim_path.stem,
        "claim_fm": _plain(fm),
        "claim_body": body,
        "sidecar": _plain(sidecar),
        "sources": sources,
    }


def write_criterion_fixture(repo_root: Path) -> None:
    """A subject criterion and a draft claim written from it, at the criterion stem."""
    write_entity(repo_root)
    (repo_root / "research" / "templates.yaml").write_text(
        "templates:\n"
        f"  - slug: {CRITERION_SLUG}\n"
        '    text: "ENTITY uses renewable energy"\n'
        "    entity_type: subject\n"
        f"    subjects: [{ENTITY_REF}]\n"
        "    topics: [ai-safety, environmental-impact]\n"
        "    core: true\n"
        '    notes: "mixed = offsets only"\n'
        '    grading_rule: "mixed = offsets only"\n',
        encoding="utf-8",
    )
    path = claim_dir(repo_root) / f"{CRITERION_SLUG}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {CRITERION_STATEMENT}\nentity: {ENTITY_REF}\n"
        "topics: [ai-safety, environmental-impact]\nverdict: 'true'\nconfidence: high\n"
        f"criteria_slug: {CRITERION_SLUG}\nstatus: draft\nas_of: '2026-10-01'\nsources: []\n---\n"
        "Old narrative.\n",
        encoding="utf-8",
    )


def run_adhoc(repo_root: Path):
    from orchestrator.cli import main

    write_entity(repo_root)
    with scripted_agents():
        return CliRunner().invoke(main, [
            "--model", "test", "draft", "--entity", ENTITY_REF, SENTENCE,
            "--skip-wayback", "--repo-root", str(repo_root),
        ])


def run_criterion(repo_root: Path, command: list[str] | None = None):
    """Re-run the criterion fixture; ``command`` is the post-RE-AS form unless given."""
    from orchestrator.cli import main

    write_criterion_fixture(repo_root)
    args = command or ["draft", "--claim", CRITERION_CLAIM_REF, "--force"]
    with scripted_agents(analyst=analyst_args(title=CRITERION_STATEMENT)):
        return CliRunner().invoke(main, [
            "--model", "test", *args, "--skip-wayback", "--repo-root", str(repo_root),
        ])


def _golden(case: str) -> dict:
    """The RE-AR (One loop, one writer) golden plus the audit keys RE-AT adds.

    The file stays as recorded at ``841df4b`` rather than being regenerated:
    it is the pre-rebuild artifact the parity is measured against, and a
    regenerated file would absorb any later drift instead of catching it.
    The keys RE-AT (Rules, findings file, tie-breaker) adds are listed in the
    module docstring and patched in here, so they are the only difference.
    """
    golden = json.loads((GOLDEN_DIR / case / "golden.json").read_text(encoding="utf-8"))
    audit = golden["sidecar"]["audit"]
    audit.update(
        pipeline_verdict=audit["analyst_verdict"],
        pipeline_confidence=audit["analyst_confidence"],
        rule_applied="agreed",
    )
    _apply_re_ba_differences(golden["sidecar"])
    return golden


def _apply_re_ba_differences(sidecar: dict) -> None:
    """The sidecar differences RE-BA (Source pool rules) adds, and no others.

    The harness plan carries a counter-evidence sub-question with its own
    query (the planner must emit one); every ``sub_questions`` entry records
    its ``kind`` and the tags the text check dropped (``snippet_only``, none
    here: every harness page names every sub-question's terms); and the
    ``analyst_record`` lists the cited sources the narrative never names by
    title (none: the scripted analyst cites nothing by id).
    """
    from tests.loop_harness import COUNTER_SUB_QUESTION, planner_args

    plan = planner_args()
    sidecar["research"]["planner_rationale"] = plan["rationale"]
    sidecar["research"]["queries"] = [q["text"] for q in plan["queries"]]
    for entry in sidecar["sub_questions"]:
        entry.setdefault("kind", "coverage")
        entry.setdefault("snippet_only", [])
    counter = COUNTER_SUB_QUESTION
    sidecar["sub_questions"].append({
        "id": counter["id"], "question": counter["question"], "rationale": counter["rationale"],
        "kind": "counter-evidence",
        "queries": [q["text"] for q in plan["queries"] if q["sub_question_id"] == counter["id"]],
        "citations": [], "snippet_only": [],
    })
    sidecar["analyst_record"]["uncited_by_title"] = []


def test_criterion_backed_claim_matches_the_re_ar_golden_except_statement(tmp_path) -> None:
    result = run_criterion(tmp_path)
    assert result.exit_code == 0, result.output

    golden = _golden("criterion")
    actual = collect(tmp_path)
    assert actual["stem"] == golden["stem"] == CRITERION_SLUG
    expected_fm = {**golden["claim_fm"], "statement": CRITERION_STATEMENT}
    assert actual["claim_fm"] == expected_fm
    assert actual["claim_body"] == golden["claim_body"]
    assert actual["sidecar"] == golden["sidecar"]
    assert actual["sources"] == golden["sources"]


def test_ad_hoc_claim_matches_the_re_ar_golden_except_statement_and_title(tmp_path) -> None:
    result = run_adhoc(tmp_path)
    assert result.exit_code == 0, result.output

    golden = _golden("adhoc")
    actual = collect(tmp_path)
    assert actual["stem"] == slugify(SENTENCE)
    expected_fm = {**golden["claim_fm"], "title": SENTENCE, "statement": SENTENCE}
    assert actual["claim_fm"] == expected_fm
    assert actual["claim_body"] == golden["claim_body"]
    expected_sidecar = json.loads(json.dumps(golden["sidecar"]))
    expected_sidecar["analyst_record"]["title"] = SENTENCE
    assert actual["sidecar"] == expected_sidecar
    assert actual["sources"] == golden["sources"]
