"""Probe safety for the one loop (RE-AR, One loop, one writer).

Two import-level checks and one zero-write run:

- no module under ``pipeline/loop/`` imports a writer name from
  ``orchestrator.persistence`` (readers and pure helpers such as
  ``fit_verdict_to_written_pool`` are allowed);
- ``orchestrator/cli.py`` reaches the loop only through its public names,
  so no command calls a loop step by a private name;
- ``dr draft --dry-run`` on scripted inputs reaches no writer and no archive
  save, and runs the loop with ``allow_save`` False.
"""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner

from tests.loop_harness import SENTENCE, scripted_agents, write_entity, written_claims, written_sources

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
LOOP_DIR = PIPELINE_ROOT / "loop"
CLI_PATH = PIPELINE_ROOT / "orchestrator" / "cli.py"

# Writer names the loop package may never import or reach as an attribute:
# every function in ``orchestrator/persistence.py`` that writes a file. A
# writer added to persistence.py is added here in the same commit
# (``test_every_persistence_writer_is_listed`` checks it).
WRITER_NAMES = frozenset({
    "_write_source_files",
    "_write_claim_file",
    "_write_audit_sidecar",
    "_write_entity_file",
    "_store_analyst_record",
    "_edit_sidecar",
    "persist_sources",
    "mark_forced_rewrite",
    "set_claim_status",
    "set_claim_corrections",
    "set_claim_criterion",
    "set_claim_fields",
    "append_template_entry",
    "write_subject_record",
    "write_claim_run",
    "write_evaluator_rerun",
    "record_restatement_pick",
    "write_finding",
    "close_finding",
    # RE-AW (Recheck): the pending-draft write and its promotion over the live claim.
    "write_pending_recheck",
    "promote_pending",
    "_finish_promotion",
    # RE-AX (Fold side tools): `dr draft --claim <ref> --rerun`, its pending-draft
    # form, the staging both pending writes share and the promotion's carry of
    # the live claim's operator fields.
    "write_analyst_rerun",
    "write_pending_rerun",
    "_stage_pending",
    "_merge_live_operator_fields",
})

# The only names cli.py may import from the loop package (plan § SP1, Tests that prove it).
PUBLIC_LOOP_NAMES = frozenset({
    "run",
    "rerun",
    "ClaimSpec",
    "VerifyConfig",
    "VerificationResult",
    "StepError",
    "check_ingested_source",
    "blocked_reason_label",
})


def _loop_modules() -> list[Path]:
    assert LOOP_DIR.is_dir(), f"{LOOP_DIR} does not exist: pipeline/loop/ is not built yet"
    modules = sorted(LOOP_DIR.rglob("*.py"))
    assert modules, "pipeline/loop/ holds no modules"
    return modules


def _imported_names(tree: ast.AST, module_filter) -> list[tuple[str, str]]:
    """(module, name) pairs from ``from <module> import <name>`` statements that pass the filter."""
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and module_filter(node.module):
            out.extend((node.module, alias.name) for alias in node.names)
    return out


def _attribute_names(tree: ast.AST) -> set[str]:
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def _writer_reaches(module: Path, label: str) -> list[str]:
    """Each writer name ``module`` imports from a persistence module or reaches as an attribute."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offending = [
        f"{label}: from {mod} import {name}"
        for mod, name in _imported_names(tree, lambda m: "persistence" in m)
        if name in WRITER_NAMES
    ]
    offending += [f"{label}: attribute .{attr}" for attr in sorted(_attribute_names(tree) & WRITER_NAMES)]
    return offending


def test_loop_package_imports_no_writer() -> None:
    offending: list[str] = []
    for module in _loop_modules():
        offending += _writer_reaches(module, str(module.relative_to(PIPELINE_ROOT)))
    assert not offending, "the loop reaches a writer:\n" + "\n".join(offending)


@pytest.mark.parametrize("name", ["write_claim_run", "record_restatement_pick", "_edit_sidecar", "set_claim_fields"])
def test_the_writer_check_flags_a_loop_module_that_imports_a_writer(tmp_path, name: str) -> None:
    """Positive control for the check above: a module importing a writer is caught."""
    module = tmp_path / "fake_step.py"
    module.write_text(
        f"from orchestrator.persistence import load_source_dict, {name}\n"
        f"import orchestrator.persistence as p\n_ = p.{name}\n",
        encoding="utf-8",
    )
    found = _writer_reaches(module, "fake_step.py")
    assert f"fake_step.py: from orchestrator.persistence import {name}" in found
    assert f"fake_step.py: attribute .{name}" in found
    assert not any("load_source_dict" in f for f in found), "a reader is not a writer"


def test_every_persistence_writer_is_listed() -> None:
    """Every name in WRITER_NAMES exists in persistence.py, and every function there that writes a file is listed.

    "Writes a file" is read from the source: a top-level function whose body
    calls ``write_text`` or ``write_bytes``, ``open`` with a write mode,
    ``os.replace`` or ``os.rename``, or calls a listed writer.
    """
    import orchestrator.persistence as persistence

    missing = sorted(n for n in WRITER_NAMES if not hasattr(persistence, n))
    assert not missing, f"WRITER_NAMES names functions persistence.py does not define: {missing}"

    tree = ast.parse((PIPELINE_ROOT / "orchestrator" / "persistence.py").read_text(encoding="utf-8"))
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    def write_mode(call: ast.Call) -> bool:
        modes = [a for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        modes += [k.value for k in call.keywords
                  if k.arg == "mode" and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)]
        return any(set(m.value) & set("wax") for m in modes)

    def writes(fn: ast.FunctionDef) -> bool:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                target = node.func
                called = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                owner = getattr(target.value, "id", "") if isinstance(target, ast.Attribute) else ""
                if called in ("write_text", "write_bytes") or called in WRITER_NAMES:
                    return True
                if called == "open" and write_mode(node):
                    return True
                if owner == "os" and called in ("replace", "rename"):
                    return True
        return False

    control = ast.parse("def f(p):\n    with p.open('w') as fh:\n        fh.write('x')\n    os.replace(p, p)\n").body[0]
    assert writes(control), "control: open with a write mode counts as a write"

    unlisted = sorted(name for name, fn in functions.items() if writes(fn) and name not in WRITER_NAMES)
    assert not unlisted, f"persistence.py functions that write a file but are not in WRITER_NAMES: {unlisted}"


def test_loop_package_exports_its_public_names() -> None:
    import loop

    for name in PUBLIC_LOOP_NAMES | {
        "ingest_one", "ingest_urls", "merge_acquisition_writes", "analyse_claim",
        "audit_claim", "apply_entity_match",
    }:
        assert hasattr(loop, name), f"loop.{name} is not exported"
    from loop.errors import StepError

    assert loop.StepError is StepError


def test_cli_imports_only_public_loop_names() -> None:
    tree = ast.parse(CLI_PATH.read_text(encoding="utf-8"), filename=str(CLI_PATH))
    loop_imports = _imported_names(tree, lambda m: m == "loop" or m.startswith("loop."))
    assert loop_imports, "cli.py does not import from the loop package yet"
    bad = [f"from {m} import {n}" for m, n in loop_imports if n not in PUBLIC_LOOP_NAMES]
    assert not bad, "cli.py reaches a loop step by a non-public name:\n" + "\n".join(bad)

    private_from_pipeline = [
        f"from {m} import {n}"
        for m, n in _imported_names(tree, lambda m: m == "orchestrator.pipeline")
        if n.startswith("_")
    ]
    assert not private_from_pipeline, (
        "cli.py still imports a private loop helper from orchestrator.pipeline:\n"
        + "\n".join(private_from_pipeline)
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name == "loop" or a.name.startswith("loop.") for a in node.names), (
                "cli.py imports the loop package as a module; import its public names instead"
            )


def test_cli_builds_the_sub_questions_block_through_the_writer() -> None:
    text = CLI_PATH.read_text(encoding="utf-8")
    assert "_build_sub_questions_block" not in text, (
        "cli.py still imports the loop-side _build_sub_questions_block; the writer builds that block"
    )


# --------------------------------------------------------------------------- #
# Zero-write probe                                                               #
# --------------------------------------------------------------------------- #

_WATCHED_WRITERS = (
    "_write_source_files",
    "_write_claim_file",
    "_write_audit_sidecar",
    "_write_entity_file",
    "persist_sources",
    "mark_forced_rewrite",
    "set_claim_status",
)


def _watch_writers(monkeypatch) -> list[str]:
    """Replace every writer with a recorder; the list stays empty on a clean dry run."""
    import orchestrator.persistence as persistence
    from ingestor.tools import wayback

    reached: list[str] = []

    def _recorder(name):
        def _hit(*args, **kwargs):
            reached.append(name)
            raise AssertionError(f"{name} reached on a dry run")

        return _hit

    for name in _WATCHED_WRITERS:
        assert hasattr(persistence, name), f"orchestrator.persistence.{name} is missing"
        monkeypatch.setattr(persistence, name, _recorder(name))

    async def _save(*args, **kwargs):
        reached.append("_save_and_check")
        raise AssertionError("_save_and_check reached on a dry run")

    monkeypatch.setattr(wayback, "_save_and_check", _save)
    return reached


_SAVE_PATH = r"^/save(/|$)"


def _offline_archive():
    """Answer every archive.org lookup with 404 so the dry run keeps its lookup but stays offline.

    A Save Page Now request (``/save/`` path) gets its own route, ``"save"``,
    so a test can assert it was never sent, whichever code path sent it.
    """
    router = respx.mock(assert_all_called=False)
    router.route(host__regex=r"(^|\.)archive\.org$", path__regex=_SAVE_PATH, name="save").mock(
        return_value=httpx.Response(200)
    )
    router.route(host__regex=r"(^|\.)archive\.org$").mock(return_value=httpx.Response(404))
    return router


def _save_asking_ingest_model():
    """An Ingestor model that first asks ``web_fetch`` for the page's Save Page Now URL.

    The live dry-run probe saw the Ingestor model do exactly this; afterwards it
    behaves like the harness's ``ingest_model``.
    """
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
    from pydantic_ai.models.function import FunctionModel

    from tests.loop_harness import ingest_model

    plain = ingest_model().function

    async def _fn(messages, info):
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        calls = sum(isinstance(p, ToolCallPart) for p in parts)
        if calls >= 2:
            return await plain(messages, info)
        prompt = next(p.content for p in parts if isinstance(p, UserPromptPart))
        url = prompt.split("URL: ", 1)[1].split("\n", 1)[0]
        target = f"https://web.archive.org/save/{url}" if calls == 0 else url
        return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": target})])

    return FunctionModel(_fn)


def test_dry_run_reaches_no_writer_and_no_archive_save(tmp_path, monkeypatch) -> None:
    from orchestrator.cli import main
    import loop

    write_entity(tmp_path)
    reached = _watch_writers(monkeypatch)

    seen: dict = {}
    real_run = loop.run

    async def _spy(spec, config, **kwargs):
        seen["config"] = config
        seen["spec"] = spec
        return await real_run(spec, config, **kwargs)

    monkeypatch.setattr(loop, "run", _spy)

    with scripted_agents(), _offline_archive():
        result = CliRunner().invoke(main, [
            "--model", "test", "draft", "--dry-run", "--entity", "subjects/probe-subject", SENTENCE,
            "--repo-root", str(tmp_path),
        ])

    assert result.exit_code == 0, result.output
    assert reached == []
    assert seen["config"].allow_save is False
    assert seen["config"].skip_wayback is False
    assert seen["spec"].statement == SENTENCE
    assert written_claims(tmp_path) == []
    assert written_sources(tmp_path) == []
    # The result is printed, so an operator sees the verdict of a dry run.
    assert "mixed" in result.output.lower()


def test_dry_run_with_wayback_on_never_asks_for_a_capture(tmp_path, monkeypatch) -> None:
    """``--dry-run`` keeps the archive lookup but never Save Page Now, even with ``--wayback``."""
    from orchestrator.cli import main

    write_entity(tmp_path)
    reached = _watch_writers(monkeypatch)

    with scripted_agents(ingestor=_save_asking_ingest_model()), _offline_archive() as router:
        result = CliRunner().invoke(main, [
            "--model", "test", "draft", "--dry-run", "--wayback", "--entity", "subjects/probe-subject",
            SENTENCE, "--repo-root", str(tmp_path),
        ])
        # respx clears call counts when the router exits, so read them here.
        # The scripted Ingestor asked web_fetch for a /save/ URL for every
        # page; no such request may leave the process.
        save_calls = router.routes["save"].call_count

    assert result.exit_code == 0, result.output
    assert reached == []
    assert save_calls == 0


@pytest.mark.parametrize("name", ["claim-probe", "claim-draft", "wayback-backfill"])
def test_old_commands_are_gone(name: str) -> None:
    from orchestrator.cli import main

    result = CliRunner().invoke(main, [name, "--help"])
    assert result.exit_code != 0, f"dr {name} still exists"
    top = CliRunner().invoke(main, ["--help"])
    assert name not in top.output
    assert "draft" in top.output
