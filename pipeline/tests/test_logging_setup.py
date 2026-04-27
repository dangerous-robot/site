"""Tests for pipeline.common.logging_setup."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import pytest

from common.logging_setup import (
    JsonFormatter,
    RunIdFilter,
    bind_run_id,
    configure_logging,
    new_run_id,
    run_id_var,
)
from orchestrator.pipeline import VerifyConfig


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Snapshot/restore root logger state between tests."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_filters = list(root.filters)
    saved_level = root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for f in list(root.filters):
        root.removeFilter(f)
    for h in saved_handlers:
        root.addHandler(h)
    for f in saved_filters:
        root.addFilter(f)
    root.setLevel(saved_level)


def test_configure_logging_creates_handlers(tmp_path: Path) -> None:
    configure_logging(verbose=False, repo_root=tmp_path)

    root = logging.getLogger()
    assert len(root.handlers) == 3, f"expected 3 handlers, got {len(root.handlers)}"
    # logs/ is created up front; files are not (delay=True defers file open
    # until first emit, so --help paths don't materialize empty files).
    assert (tmp_path / "logs").exists()
    assert not (tmp_path / "logs" / "info.log").exists()
    assert not (tmp_path / "logs" / "debug.log").exists()

    # Verify formatter assignment: info.log gets HumanFormatter, debug.log JSON.
    from common.logging_setup import HumanFormatter, JsonFormatter
    formatters_by_filename = {}
    for h in root.handlers:
        if hasattr(h, "baseFilename"):
            formatters_by_filename[Path(h.baseFilename).name] = type(h.formatter)
    assert formatters_by_filename["info.log"] is HumanFormatter
    assert formatters_by_filename["debug.log"] is JsonFormatter


def test_json_formatter_emits_run_id(tmp_path: Path) -> None:
    configure_logging(verbose=False, repo_root=tmp_path)
    log = logging.getLogger("test.run_id")

    with bind_run_id("abc123"):
        log.info("hello")

    records = _read_jsonl(tmp_path / "logs" / "debug.log")
    assert len(records) == 1
    assert records[0]["run_id"] == "abc123"
    assert records[0]["msg"] == "hello"
    assert records[0]["level"] == "INFO"
    assert records[0]["logger"] == "test.run_id"


def test_info_log_is_human_readable(tmp_path: Path) -> None:
    configure_logging(verbose=False, repo_root=tmp_path)
    log = logging.getLogger("test.human")

    with bind_run_id("abc123"):
        log.info("hello world")

    text = (tmp_path / "logs" / "info.log").read_text(encoding="utf-8").strip()
    assert text.startswith("20"), f"expected ISO-8601 timestamp prefix, got: {text!r}"
    assert "INFO" in text
    assert "test.human" in text
    assert "[run_id=abc123]" in text
    assert "hello world" in text
    # Should not be JSON.
    assert not text.startswith("{"), f"info.log should not be JSON: {text!r}"


def test_run_id_isolated_per_async_task(tmp_path: Path) -> None:
    configure_logging(verbose=False, repo_root=tmp_path)
    log = logging.getLogger("test.async")

    async def task(run_id: str, msg: str) -> None:
        with bind_run_id(run_id):
            await asyncio.sleep(0)  # let scheduler interleave
            log.info(msg)

    async def runner() -> None:
        await asyncio.gather(task("aaaa", "first"), task("bbbb", "second"))

    asyncio.run(runner())

    records = _read_jsonl(tmp_path / "logs" / "debug.log")
    by_msg = {
        r["msg"]: r["run_id"] for r in records if r["logger"] == "test.async"
    }
    assert by_msg == {"first": "aaaa", "second": "bbbb"}


def test_console_level_respects_verbose(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    # verbose=False: INFO must NOT reach stderr; WARNING must.
    configure_logging(verbose=False, repo_root=tmp_path)
    log = logging.getLogger("test.console")
    log.info("info-quiet")
    log.warning("warn-quiet")
    captured = capsys.readouterr()
    assert "info-quiet" not in captured.err
    assert "warn-quiet" in captured.err

    # verbose=True: INFO reaches stderr; DEBUG still does NOT.
    configure_logging(verbose=True, repo_root=tmp_path)
    log = logging.getLogger("test.console")
    log.info("info-loud")
    log.debug("debug-loud")
    captured = capsys.readouterr()
    assert "info-loud" in captured.err
    assert "debug-loud" not in captured.err


def test_extra_fields_serialized(tmp_path: Path) -> None:
    configure_logging(verbose=False, repo_root=tmp_path)
    log = logging.getLogger("test.extra")

    log.info("hi", extra={"claim_id": "ecosia/x", "n": 5})

    records = _read_jsonl(tmp_path / "logs" / "debug.log")
    assert records[0]["claim_id"] == "ecosia/x"
    assert records[0]["n"] == 5

    info_text = (tmp_path / "logs" / "info.log").read_text(encoding="utf-8")
    assert "claim_id=ecosia/x" in info_text
    assert "n=5" in info_text


def test_extra_field_with_unserializable_value(tmp_path: Path) -> None:
    """Non-JSON-serializable extras fall back to repr() rather than crashing."""
    configure_logging(verbose=False, repo_root=tmp_path)
    log = logging.getLogger("test.extra.unsafe")

    class Opaque:
        def __repr__(self) -> str:
            return "<Opaque>"

    log.info("hi", extra={"obj": Opaque()})

    records = _read_jsonl(tmp_path / "logs" / "debug.log")
    assert records[0]["obj"] == "<Opaque>"


def test_idempotent_reconfigure(tmp_path: Path) -> None:
    configure_logging(verbose=False, repo_root=tmp_path)
    configure_logging(verbose=False, repo_root=tmp_path)

    log = logging.getLogger("test.idempotent")
    log.info("once")

    records = _read_jsonl(tmp_path / "logs" / "debug.log")
    assert len(records) == 1, f"expected 1 record, got {len(records)}"


def test_repo_root_none_fallback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(verbose=True, repo_root=None)
    root = logging.getLogger()
    assert len(root.handlers) == 1, "console-only when repo_root is None"

    log = logging.getLogger("test.fallback")
    log.info("works")  # must not raise

    captured = capsys.readouterr()
    assert "works" in captured.err
    # No logs/ directory should have been created anywhere we can check; the
    # function should not have called mkdir at all.
    assert not (tmp_path / "logs").exists()


def test_verify_config_run_id_inherits_bound_contextvar() -> None:
    with bind_run_id("inherit-me"):
        assert VerifyConfig().run_id == "inherit-me"


def test_verify_config_run_id_generates_when_unbound() -> None:
    assert run_id_var.get() is None
    assert VerifyConfig().run_id is not None


def test_cli_invocation_emits_non_null_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: subcommand banner logs (and lint/review/publish in full) used to log run_id=null."""
    from click.testing import CliRunner
    from orchestrator.cli import main

    # Override the session-scoped fixture that pins _safe_repo_root to None,
    # so file handlers attach to tmp_path/logs and we can read the result.
    monkeypatch.setattr("orchestrator.cli._safe_repo_root", lambda: tmp_path)

    result = CliRunner().invoke(main, ["lint", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, f"dr lint failed: {result.output!r}"
    records = _read_jsonl(tmp_path / "logs" / "debug.log")
    banner = next((r for r in records if r["msg"].startswith("dr lint:")), None)
    assert banner is not None, f"no banner record; output={result.output!r}"
    assert banner["run_id"] is not None, f"banner run_id is null: {banner!r}"


def test_timestamp_is_utc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    if hasattr(time, "tzset"):
        time.tzset()

    configure_logging(verbose=False, repo_root=tmp_path)
    log = logging.getLogger("test.utc")
    log.info("ts")

    records = _read_jsonl(tmp_path / "logs" / "debug.log")
    assert records[0]["ts"].endswith("+00:00"), f"timestamp not UTC: {records[0]['ts']!r}"
    info_text = (tmp_path / "logs" / "info.log").read_text(encoding="utf-8")
    assert "Z" in info_text, "info.log timestamp should end with 'Z' (UTC)"
