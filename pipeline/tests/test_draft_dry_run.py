"""``dr draft --dry-run`` is a free preflight.

Covered:

- every ``dr draft`` mode that runs a model (``--entity``, ``--subject``,
  ``--criterion ... --entity``, ``--claim``, ``--restates --pick``,
  ``--claim --rerun analyst|evaluator``, ``--source``) exits 0 with
  ``--dry-run``, reaches no loop entry, no agent, no HTTP request, and
  writes nothing (the whole tmp tree byte for byte);
- it prints what a real run would do: the statement, the target path and
  whether it overwrites, the model per agent, the search backend;
- it runs the checks that refuse a real run or its write and exits nonzero
  when one would: ``--claim`` on a published claim, a missing claim ref, an
  existing claim without ``--force``, a claim whose status is unknown, a
  claim whose entity writes elsewhere, a missing provider key, Brave with no
  key; still with no call and no write;
- ``--dry-run`` and ``--paid-dry-run`` together are a usage error.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest
import yaml
from click.testing import CliRunner

from tests.loop_harness import write_entity

TEMPLATES_FIXTURE = Path(__file__).parent / "fixtures" / "templates" / "templates.yaml"

PRODUCT_REF = "products/probe-product"
PRODUCT_NAME = "Probe Product"
SUBJECT_REF = "subjects/probe-subject"
SENTENCE = "Probe Product runs on wind power"
CLAIM_STEM = "runs-on-wind-power"
CLAIM_REF = f"probe-product/{CLAIM_STEM}"
CLAIM_PATH = Path("research/claims/probe-product") / f"{CLAIM_STEM}.md"


# --------------------------------------------------------------------------- #
# Helpers                                                                        #
# --------------------------------------------------------------------------- #


def _dr(repo_root: Path, *args: str, model_args: tuple[str, ...] = ("--model", "test")):
    from orchestrator.cli import main

    return CliRunner().invoke(main, [*model_args, *args, "--repo-root", str(repo_root)])


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _write_claim(root: Path, rel: Path = CLAIM_PATH, *, entity: str = PRODUCT_REF, **fm_extra) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": SENTENCE, "statement": SENTENCE, "entity": entity,
        "topics": ["environmental-impact"], "verdict": "unverified", "confidence": "low",
        "status": "draft", "as_of": "2026-10-01", "sources": [],
    }
    fm.update(fm_extra)
    path.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nThe stored narrative.\n", encoding="utf-8")
    sidecar = {
        "schema_version": 1,
        "pipeline_run": {"ran_at": "2026-10-01T00:00:00+00:00", "model": "m", "agents": ["analyst"]},
        "sources_consulted": [],
        "audit": None,
        "human_review": {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None},
        "restatement": {
            "candidates": [
                {"rank": 1, "text": "Probe Product buys renewable energy credits", "expected_verdict": "true"},
            ],
        },
    }
    path.with_suffix(".audit.yaml").write_text(yaml.safe_dump(sidecar, sort_keys=False), encoding="utf-8")
    return path


def _repo(root: Path) -> Path:
    write_entity(root, PRODUCT_REF, PRODUCT_NAME)
    write_entity(root, SUBJECT_REF, "Probe Subject")
    (root / "research").mkdir(exist_ok=True)
    shutil.copy(TEMPLATES_FIXTURE, root / "research" / "templates.yaml")
    _write_claim(root)
    return root


@pytest.fixture
def tripwire(monkeypatch) -> list[str]:
    """Record and fail any loop entry, agent run or HTTP request a dry run reaches."""
    import loop
    from pydantic_ai import Agent

    called: list[str] = []

    def _trip(name):
        def _fn(*args, **kwargs):
            called.append(name)
            raise AssertionError(f"{name} reached on a free dry run")

        async def _afn(*args, **kwargs):
            _fn()

        return _fn, _afn

    for target, attr, is_async in (
        (loop, "run", True), (loop, "rerun", True), (Agent, "run", True), (Agent, "run_sync", False),
        (Agent, "iter", False),
        (httpx.AsyncClient, "send", True), (httpx.Client, "send", False),
    ):
        sync_fn, async_fn = _trip(f"{getattr(target, '__name__', target)}.{attr}")
        monkeypatch.setattr(target, attr, async_fn if is_async else sync_fn)
    monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", "tavily")
    return called


MODES = {
    "entity": ["draft", "--entity", PRODUCT_REF, "Probe Product publishes its energy use"],
    "subject-existing": ["draft", "--subject", "probe-subject", "Probe subjects use energy"],
    "subject-new": ["draft", "--subject", "brand-new-subject", "Brand new subjects use energy"],
    "criterion": ["draft", "--criterion", "renewable-energy-hosting", "--entity", PRODUCT_REF],
    "claim": ["draft", "--claim", CLAIM_REF, "--force"],
    "restates": ["draft", "--restates", CLAIM_REF, "--pick", "1"],
    "rerun-analyst": ["draft", "--claim", CLAIM_REF, "--rerun", "analyst"],
    "rerun-evaluator": ["draft", "--claim", CLAIM_REF, "--rerun", "evaluator"],
    "source": ["draft", "--source", "https://example.com/page"],
}


# --------------------------------------------------------------------------- #
# No call, no write, in every mode                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", list(MODES))
def test_dry_run_calls_nothing_and_writes_nothing(tmp_path, tripwire, mode) -> None:
    root = _repo(tmp_path)
    before = _snapshot(root)

    result = _dr(root, *MODES[mode], "--dry-run")

    assert result.exit_code == 0, result.output
    assert tripwire == []
    assert _snapshot(root) == before
    assert "no model call, no search call, nothing written" in result.output


def test_dry_run_on_a_published_claim_rerun_reports_the_pending_draft(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)
    _write_claim(root, status="published")
    before = _snapshot(root)

    result = _dr(root, *MODES["rerun-evaluator"], "--dry-run")

    assert result.exit_code == 0, result.output
    assert tripwire == []
    assert _snapshot(root) == before
    assert "research/pending/probe-product/runs-on-wind-power.md" in result.output


def test_dry_run_prints_what_a_real_run_would_do(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)

    result = _dr(
        root, "draft", "--entity", PRODUCT_REF, "Probe Product publishes its energy use", "--dry-run",
        model_args=("--model", "test", "--analyst-model", "test-analyst"),
    )

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Probe Product publishes its energy use" in out
    assert (
        "probe-product/probe-product-publishes-its-energy-use at "
        "research/claims/probe-product/probe-product-publishes-its-energy-use.md (new file)"
    ) in out
    assert "analyst test-analyst" in out
    assert "researcher test" in out
    assert "tavily" in out


def test_dry_run_reports_an_overwrite(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)

    result = _dr(root, *MODES["claim"], "--dry-run")

    assert result.exit_code == 0, result.output
    assert f"{CLAIM_PATH.as_posix()} (overwrites the draft there)" in result.output


# --------------------------------------------------------------------------- #
# Refused like the real run                                                      #
# --------------------------------------------------------------------------- #


def _assert_refused(root: Path, called: list[str], args: list[str], code: int, text: str, **kw) -> None:
    before = _snapshot(root)
    result = _dr(root, *args, **kw)
    assert result.exit_code == code, result.output
    assert text in result.output
    assert called == []
    assert _snapshot(root) == before


def test_dry_run_refuses_a_published_claim_like_force_does(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)
    _write_claim(root, status="published")
    _assert_refused(root, tripwire, [*MODES["claim"], "--dry-run"], 2, "dr recheck --claim")


def test_dry_run_refuses_a_missing_claim(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)
    _assert_refused(root, tripwire, ["draft", "--claim", "probe-product/no-such-claim", "--force", "--dry-run"], 1, "not found")


def test_dry_run_refuses_an_existing_claim_without_force(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)
    _assert_refused(root, tripwire, ["draft", "--entity", PRODUCT_REF, CLAIM_STEM.replace("-", " "), "--dry-run"],
                    1, "already exists")


def test_dry_run_refuses_a_claim_with_an_unknown_status(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)
    _write_claim(root, status="retired")
    _assert_refused(root, tripwire, [*MODES["claim"], "--dry-run"], 1, "is not draft, published or archived")


@pytest.mark.parametrize("mode", ["claim", "rerun-analyst"])
def test_dry_run_refuses_a_claim_whose_entity_writes_elsewhere(tmp_path, tripwire, mode) -> None:
    root = _repo(tmp_path)
    _write_claim(root, entity=SUBJECT_REF)
    _assert_refused(root, tripwire, [*MODES[mode], "--dry-run"], 1, "Nothing was run")


def test_dry_run_refuses_a_missing_provider_key(tmp_path, tripwire, monkeypatch) -> None:
    root = _repo(tmp_path)
    monkeypatch.delenv("GREENPT_API_KEY", raising=False)
    _assert_refused(root, tripwire, [*MODES["entity"], "--dry-run"], 2, "GREENPT_API_KEY not set",
                    model_args=("--model", "greenpt:some-model"))


def test_dry_run_refuses_brave_without_its_key(tmp_path, tripwire, monkeypatch) -> None:
    root = _repo(tmp_path)
    monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", "brave")
    monkeypatch.delenv("BRAVE_WEB_SEARCH_API_KEY", raising=False)
    _assert_refused(root, tripwire, [*MODES["entity"], "--dry-run"], 2, "BRAVE_WEB_SEARCH_API_KEY")


def test_dry_run_refuses_tavily_when_no_search_key_is_set(tmp_path, tripwire, monkeypatch) -> None:
    """Tavily falls back to Brave per query; with neither key the real run would pay for the planner, then fail."""
    root = _repo(tmp_path)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_WEB_SEARCH_API_KEY", raising=False)
    for flags in (("--dry-run",), ("--paid-dry-run",), ()):
        _assert_refused(root, tripwire, [*MODES["entity"], *flags], 2, "TAVILY_API_KEY")


def test_dry_run_takes_tavily_with_only_the_brave_key(tmp_path, tripwire, monkeypatch) -> None:
    root = _repo(tmp_path)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("BRAVE_WEB_SEARCH_API_KEY", "dummy")
    result = _dr(root, *MODES["entity"], "--dry-run")
    assert result.exit_code == 0, result.output
    assert "falls back to Brave" in result.output


def test_claim_dry_run_without_force_is_the_real_runs_usage_error(tmp_path, tripwire) -> None:
    """The real ``--claim REF`` without ``--force`` is a usage error, so the free check is too."""
    root = _repo(tmp_path)
    real = _dr(root, "draft", "--claim", CLAIM_REF)
    assert real.exit_code == 2, real.output
    _assert_refused(root, tripwire, ["draft", "--claim", CLAIM_REF, "--dry-run"], 2, "--force")


def test_dry_run_and_paid_dry_run_together_are_a_usage_error(tmp_path, tripwire) -> None:
    root = _repo(tmp_path)
    _assert_refused(root, tripwire, [*MODES["entity"], "--dry-run", "--paid-dry-run"], 2, "--paid-dry-run")
