"""What a run records for the review packet (RE-AV, Review packet; plan § SP4 (Review packet)), and the carried RE-AU (Restate inside the loop) items.

The loop records, the writer stores:

- ``sources_consulted[].quotes[] {text, found, checked_against, passage | reason}``
  from the ingest quote check (``ingestor.validation.apply_quote_checks``), with
  ``found: null`` and ``checked_against: not-rechecked`` for a cached source;
- ``sources_consulted[].shared_with`` naming the other consulted sources on the
  same canonical host or from the same newswire origin (omitted when empty);
- ``research.rejected[] {url, title, score, reason}`` from the scorer's dropped list.

Carried from the RE-AU (Restate inside the loop) review: one quote rule shared
by the ingest check and the restater (item 5), the ``--restates --pick`` stem
refusal (item 8) and the ``partial`` outcome in the operator docs (item 9).
Runs go through ``dr draft`` with scripted agents (``tests/loop_harness.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from common.utils import slugify
from tests.loop_harness import (
    ENTITY_NAME,
    ENTITY_REF,
    PAGE_TEXT,
    SENTENCE,
    URLS,
    fake_execute_searches,
    ingest_model,
    scorer_args,
    scripted_agents,
    write_entity,
    written_claims,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_FLAGS = ("researcher", "analyst", "auditor", "ingestor", "tiebreaker", "restater")
FOUND = "used more than 4% of US electricity"
NOT_ON_PAGE = "Probe Subject runs entirely on wind power"


def _dr(repo_root: Path, *args: str):
    from orchestrator.cli import main

    models = ["--model", "test", *[x for a in AGENT_FLAGS for x in (f"--{a}-model", "test")]]
    return CliRunner().invoke(main, [*models, *args, "--repo-root", str(repo_root)])


def _draft(repo_root: Path, **agents):
    write_entity(repo_root)
    with scripted_agents(**agents):
        result = _dr(repo_root, "draft", "--entity", ENTITY_REF, SENTENCE, "--skip-wayback")
    assert result.exit_code == 0, result.output
    (claim,) = written_claims(repo_root)
    return yaml.safe_load(claim.with_suffix(".audit.yaml").read_text(encoding="utf-8"))


def _entry(sidecar: dict, url: str) -> dict:
    return next(e for e in sidecar["sources_consulted"] if e["url"] == url)


# --------------------------------------------------------------------------- #
# Quotes and passages                                                              #
# --------------------------------------------------------------------------- #


def test_a_draft_records_each_quote_check_with_its_passage_or_reason(tmp_path) -> None:
    sidecar = _draft(tmp_path, ingestor=ingest_model(key_quotes={URLS[0]: [FOUND, NOT_ON_PAGE]}))
    quotes = _entry(sidecar, URLS[0])["quotes"]
    assert [q["text"] for q in quotes] == [FOUND, NOT_ON_PAGE]

    found, missing = quotes
    assert found["found"] is True and found["checked_against"] == "page"
    assert "reason" not in found
    # The passage is the page's own text (case kept), the matched sentence and some context.
    assert "Probe Subject data centers used more than 4% of US electricity in 2024." in found["passage"]

    assert missing["found"] is False and missing["checked_against"] == "page"
    assert missing["passage"] is None and missing["reason"]

    # A source whose ingest kept no quote records an empty list, not a missing key.
    assert _entry(sidecar, URLS[1])["quotes"] == []


def test_a_cached_source_records_its_quotes_as_not_rechecked(tmp_path) -> None:
    cached = tmp_path / "research" / "sources" / "2026" / "cached-report.md"
    cached.parent.mkdir(parents=True)
    fm = {
        "url": URLS[3], "title": "Cached report", "publisher": "Example Publisher", "accessed_date": "2026-01-01",
        "kind": "article", "independence": "independent", "summary": "A stored page.",
        "key_quotes": ["a stored quote"],
    }
    cached.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\n{PAGE_TEXT[URLS[3]]}\n", encoding="utf-8")

    sidecar = _draft(tmp_path)
    entry = next(e for e in sidecar["sources_consulted"] if e["id"] == "2026/cached-report")
    assert entry["quotes"] == [
        {"text": "a stored quote", "found": None, "checked_against": "not-rechecked", "passage": None},
    ]


# --------------------------------------------------------------------------- #
# shared_with                                                                       #
# --------------------------------------------------------------------------- #


def _page(i: int) -> str:
    return PAGE_TEXT[URLS[0]].replace("Page 1.", f"Page {i + 1}.")


def test_shared_with_names_the_other_sources_on_the_same_canonical_host(tmp_path) -> None:
    urls = [
        "https://example.org/a",
        "https://www.example.org/b",  # the canonical host drops www.
        "https://example.org/c",
        "https://other.example.net/d",
    ]
    pages = {u: _page(i) for i, u in enumerate(urls)}
    sidecar = _draft(tmp_path, search=fake_execute_searches(urls, pages), scorer=scorer_args(urls))
    ids = {e["url"]: e["id"] for e in sidecar["sources_consulted"]}
    assert _entry(sidecar, urls[0])["shared_with"] == [ids[urls[1]], ids[urls[2]]]
    assert _entry(sidecar, urls[1])["shared_with"] == [ids[urls[0]], ids[urls[2]]]
    assert "shared_with" not in _entry(sidecar, urls[3])


def test_shared_with_names_the_other_releases_from_the_same_newswire_origin(tmp_path) -> None:
    urls = [f"https://site{i}.example.net/release" for i in range(4)]
    pages = {u: _page(i) for i, u in enumerate(urls)}
    sidecar = _draft(
        tmp_path, search=fake_execute_searches(urls, pages), scorer=scorer_args(urls),
        ingestor=ingest_model(publisher="PR Newswire"),
    )
    ids = [_entry(sidecar, u)["id"] for u in urls]
    for i, u in enumerate(urls):
        assert _entry(sidecar, u)["shared_with"] == [x for k, x in enumerate(ids) if k != i]


# --------------------------------------------------------------------------- #
# research.rejected                                                                 #
# --------------------------------------------------------------------------- #


def test_research_rejected_lists_the_scorer_drops_with_a_reason(tmp_path) -> None:
    extra = ["https://example.org/off-topic-1", "https://example.org/off-topic-2"]
    scorer = scorer_args(URLS)
    scorer["dropped"] = list(extra)
    scorer["rationale"] = "two pages are off topic"
    sidecar = _draft(tmp_path, search=fake_execute_searches(URLS + extra), scorer=scorer)
    rejected = sidecar["research"]["rejected"]
    assert [r["url"] for r in rejected] == extra
    assert [r["title"] for r in rejected] == ["Report 5", "Report 6"]
    for r in rejected:
        assert set(r) == {"url", "title", "score", "reason"}
        assert r["score"] is None
        assert "below 3" in r["reason"]


def test_a_run_whose_scorer_dropped_nothing_records_an_empty_rejected_list(tmp_path) -> None:
    sidecar = _draft(tmp_path)
    assert sidecar["research"]["rejected"] == []


# --------------------------------------------------------------------------- #
# The one quote rule (ingestor/validation.py)                                      #
# --------------------------------------------------------------------------- #


def test_check_quote_returns_the_passage_in_the_pages_own_case() -> None:
    from ingestor.validation import PASSAGE_MAX_CHARS, check_quote

    filler = "Unrelated words fill the page here. " * 80
    page = f"{filler}The Report Says Data Centers Used 4.4% Of US Electricity In 2023. {filler}"
    check = check_quote("data centers used 4.4% of US electricity", page)
    assert check.found is True and check.reason is None
    assert "The Report Says Data Centers Used 4.4% Of US Electricity In 2023." in check.passage
    assert len(check.passage) <= PASSAGE_MAX_CHARS


def test_check_quote_gives_a_reason_and_no_passage_when_the_quote_is_absent() -> None:
    from ingestor.validation import check_quote

    check = check_quote("a sentence that is not there", "The page says something else entirely.")
    assert check.found is False and check.passage is None
    assert check.reason


def test_apply_quote_checks_agrees_with_check_quote() -> None:
    """Control: the ingest drop and the shared check are one rule."""
    from ingestor.models import SourceFile
    from ingestor.validation import apply_quote_checks, check_quote

    page = "The therapist said energy use rose. Google's figure is 0.24 Wh."
    quotes = ["rapist said energy", "therapist said energy", "Google’s figure", "not there"]
    sf = SourceFile.model_validate({
        "frontmatter": {"url": "https://example.org/p", "title": "T", "publisher": "P", "accessed_date": "2026-10-14",
                        "kind": "article", "summary": "S", "key_quotes": list(quotes)},
        "body": "B", "slug": "p", "year": 2026,
    })
    dropped = [c.text for c in apply_quote_checks(sf, page) if not c.found]
    assert dropped == [q for q in quotes if not check_quote(q, page).found]
    assert dropped == ["rapist said energy", "not there"]


def test_ingest_and_the_drop_share_apply_quote_checks_which_leaves_no_quotes_alone() -> None:
    from ingestor.models import SourceFile
    from ingestor.validation import apply_quote_checks

    sf = SourceFile.model_validate({
        "frontmatter": {"url": "https://example.org/p", "title": "T", "publisher": "P", "accessed_date": "2026-10-14",
                        "kind": "article", "summary": "S", "key_quotes": []},
        "body": "B", "slug": "p", "year": 2026,
    })
    assert apply_quote_checks(sf, "Any page.", with_passage=True) == []
    assert sf.frontmatter.key_quotes == [], "an empty list stays an empty list"
    sf.frontmatter.key_quotes = ["not there"]
    (check,) = apply_quote_checks(sf, "Any page.", with_passage=True)
    assert check.found is False and sf.frontmatter.key_quotes is None, "control: a quote list is rewritten"
    ingest = (REPO_ROOT / "pipeline" / "loop" / "ingest.py").read_text(encoding="utf-8")
    assert "apply_quote_checks(sf," in ingest and "check_quotes(" not in ingest


def _proposal(quote: str):
    from loop.restater.models import EvidenceRef, RestatementCandidate, RestatementProposal

    return RestatementProposal(
        why_unverified="term-mismatch",
        why_unverified_note="note",
        candidates=[RestatementCandidate(
            text=f"{ENTITY_NAME} energy use rose in 2024.", frame="narrowed", expected_verdict="true",
            expected_confidence="medium", verification_level_estimate="independently-verified", decisiveness=3,
            supporting=[EvidenceRef(source="2026/a", quote=quote, note="says so")], contradicting=[],
            needs_new_research=False, rationale="The report says so.",
        )],
    )


@pytest.mark.parametrize(("quote", "verified"), [
    ("rapist said energy", False),       # inside a word: the old substring rule accepted it
    ("therapist said energy", True),     # control
    ("Google’s figure", True),      # a curly apostrophe: the old rule rejected it
    ("not in the source", False),        # control
])
def test_the_restater_marks_quotes_with_the_shared_rule(quote, verified) -> None:
    """Carried RE-AU (Restate inside the loop) item 5: the restater's quote check is the ingest check, not a second rule."""
    from loop.restate import evaluate_proposal

    sources = {"2026/a": {"title": "A report", "summary": "", "key_quotes": [],
                          "body": "The therapist said energy use rose. Google's figure is 0.24 Wh."}}
    kept, _dropped = evaluate_proposal(_proposal(quote), sources, (ENTITY_NAME,), 5)
    assert kept[0]["supporting"][0]["quote_verified"] is verified


def test_the_restater_defines_no_quote_matcher_of_its_own() -> None:
    source = (REPO_ROOT / "pipeline" / "loop" / "restate.py").read_text(encoding="utf-8")
    assert "_quote_found" not in source and "def _collapse" not in source
    assert "from ingestor.validation import" in source


# --------------------------------------------------------------------------- #
# Carried RE-AU (Restate inside the loop) item 8: a pick whose stem is the original's                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("extra", [("--force",), ()], ids=["force", "plain"])
def test_restates_pick_refuses_a_candidate_that_would_overwrite_the_original(tmp_path, monkeypatch, extra) -> None:
    import loop

    write_entity(tmp_path)
    text = f"{ENTITY_NAME} data centers used more than 4% of US electricity in 2024."
    original = tmp_path / "research" / "claims" / ENTITY_REF / f"{slugify(text)}.md"
    original.parent.mkdir(parents=True)
    fm = {"title": text, "statement": text, "entity": ENTITY_REF, "topics": ["environmental-impact"],
          "verdict": "mixed", "confidence": "medium", "verification_level": "partially-verified",
          "status": "draft", "as_of": "2026-10-01", "sources": []}
    original.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nNarrative.\n", encoding="utf-8")
    sidecar = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst"]},
        "sources_consulted": [], "audit": None,
        "human_review": {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None},
        "restatement": {"schema_version": 1, "trigger": "weak-verdict", "picked": None,
                        "candidates": [{"rank": 1, "text": text}]},
    }
    original.with_suffix(".audit.yaml").write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")
    before = (original.read_bytes(), original.with_suffix(".audit.yaml").read_bytes())

    async def _fail(*_a, **_kw):
        raise AssertionError("the loop must not run")

    monkeypatch.setattr(loop, "run", _fail)
    ref = f"{ENTITY_REF}/{original.stem}"
    result = _dr(tmp_path, "draft", "--restates", ref, "--pick", "1", *extra)
    assert result.exit_code == 2, result.output
    assert "original" in result.output.lower()
    assert (original.read_bytes(), original.with_suffix(".audit.yaml").read_bytes()) == before


# --------------------------------------------------------------------------- #
# Carried RE-AU (Restate inside the loop) item 9: the partial outcome in the operator docs                    #
# --------------------------------------------------------------------------- #


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    level = heading.split(" ", 1)[0]
    rest = text[start + len(heading):]
    ends = [i for i in (rest.find(f"\n{level} "), rest.find("\n## ")) if i >= 0]
    return text[start:start + len(heading) + (min(ends) if ends else len(rest))]


def test_the_operator_docs_name_the_partial_outcome_of_a_failed_restater() -> None:
    agents = _section((REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"), "### Run rules")
    runbook = _section((REPO_ROOT / "docs" / "runbook.md").read_text(encoding="utf-8"), "## Triaging findings")
    readme = next(
        line for line in (REPO_ROOT / "pipeline" / "README.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("- `loop/`")
    )
    for name, text in (("AGENTS.md § Run rules", agents), ("runbook § Triaging findings", runbook),
                       ("pipeline/README.md loop bullet", readme)):
        assert "partial" in text, f"{name} omits the partial outcome"
    assert "restate" in agents.lower() and "partial" in runbook
