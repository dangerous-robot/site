"""Structured logging for the dangerous-robot pipeline.

Two persistent JSON streams (``logs/info.log``, ``logs/debug.log``) plus a
human-readable console handler. Every record is stamped with a ``run_id``
pulled from a :class:`contextvars.ContextVar`, so a single pipeline
invocation can be reconstructed by grepping by id across both files.

The ``run_id`` field is shared with the planned token-usage log
(``docs/plans/token-usage-log.md``); call sites that build a
``VerifyConfig`` use ``cfg.run_id`` and call sites that don't (e.g.
``dr ingest``) use ``bind_run_id(new_run_id())``.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator

run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)


# Stdlib LogRecord attribute names, derived from a probe instance so the
# set stays correct across Python versions (e.g. taskName landed in 3.12).
# `message` and `asctime` are populated lazily by getMessage()/formatTime(),
# and `run_id` is added by RunIdFilter — none appear on a fresh record, so
# we add them by hand.
_RESERVED = frozenset(
    set(logging.LogRecord("probe", 0, "", 0, "", None, None).__dict__)
    | {"message", "asctime", "run_id"}
)


def _iter_extras(record: logging.LogRecord):
    """Yield (key, value) pairs for caller-supplied extras only."""
    for k, v in record.__dict__.items():
        if k in _RESERVED or k.startswith("_"):
            continue
        yield k, v


def new_run_id() -> str:
    """Return a fresh run id (UUID4 hex, 32 chars, no dashes)."""
    return uuid.uuid4().hex


@contextmanager
def bind_run_id(run_id: str) -> Iterator[str]:
    """Bind ``run_id`` to the current async context for the duration of the block.

    Yields the bound id so callers can capture it without re-threading::

        with bind_run_id(new_run_id()) as run_id:
            ...
    """
    token = run_id_var.set(run_id)
    try:
        yield run_id
    finally:
        run_id_var.reset(token)


class RunIdFilter(logging.Filter):
    """Stamp every record with the current ``run_id`` contextvar value."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
            timespec="microseconds"
        )
        payload: dict = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": getattr(record, "run_id", None),
        }
        for k, v in _iter_extras(record):
            if k in payload:
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except TypeError:
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """Human-readable single-line records with UTC timestamp and run_id.

    Format: ``<ts>  <LEVEL>  <logger>  [run_id=<id>]  <msg>  [k=v ...]``
    Extras supplied via ``logger.info("...", extra={"k": v})`` append as
    space-separated ``key=value`` pairs after the message.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        run_id = getattr(record, "run_id", None) or "-"
        line = (
            f"{ts}  {record.levelname:<7}  {record.name}  "
            f"[run_id={run_id}]  {record.getMessage()}"
        )
        extras = [f"{k}={v}" for k, v in _iter_extras(record)]
        if extras:
            line += "  " + " ".join(extras)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


_progress_logger = logging.getLogger(__name__)


def progress(msg: str, *args: object) -> None:
    """Mirror an INFO record to both stderr (real-time) and info.log.

    Use for operator-facing progress prints (``[1/N] Done: ...``) where
    you want the message visible without ``--verbose`` AND persisted in
    ``logs/info.log``. Equivalent to ``click.echo(msg, err=True)`` plus a
    ``logger.info(msg)`` call.

    With ``--verbose``, the same message reaches stderr twice (once from
    this direct write, once from the logger's console handler). That is
    the accepted tradeoff of mirroring.
    """
    formatted = (msg % args) if args else msg
    sys.stderr.write(formatted + "\n")
    sys.stderr.flush()
    _progress_logger.info(msg, *args)


def configure_logging(verbose: bool, repo_root: Path | None) -> None:
    """Install handlers on the root logger.

    Idempotent: calling twice does not stack handlers. When ``repo_root``
    is ``None`` only the console handler is installed (file logging is
    skipped). When ``repo_root`` is provided, ``logs/info.log`` and
    ``logs/debug.log`` are created under it with rotation enabled.
    """
    root = logging.getLogger()
    # Drop any prior handlers (filters/handlers from earlier configure calls
    # or stdlib basicConfig). Keep this idempotent so repeated CLI invocations
    # in tests don't double-write.
    for h in list(root.handlers):
        root.removeHandler(h)
    for f in list(root.filters):
        root.removeFilter(f)

    root.setLevel(logging.DEBUG)

    # Attach RunIdFilter on each handler (not the root logger). A filter on
    # a logger only fires for records emitted by that logger directly;
    # records propagated up from child loggers reach the root's handlers
    # without consulting the root's filters. Per-handler filters work for
    # both paths.
    run_id_filter = RunIdFilter()

    if repo_root is not None:
        logs_dir = repo_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # delay=True defers actually opening the file until the first
        # record is emitted. Keeps "dr <subcommand> --help" from creating
        # empty info.log/debug.log just because the group callback ran.
        info_handler = RotatingFileHandler(
            logs_dir / "info.log",
            maxBytes=50_000_000,
            backupCount=5,
            encoding="utf-8",
            delay=True,
        )
        info_handler.setLevel(logging.INFO)
        # info.log is meant to be skimmed by humans ("what happened today?").
        # debug.log keeps the JSON format so it can be queried with jq.
        info_handler.setFormatter(HumanFormatter())
        info_handler.addFilter(run_id_filter)
        root.addHandler(info_handler)

        debug_handler = RotatingFileHandler(
            logs_dir / "debug.log",
            maxBytes=100_000_000,
            backupCount=3,
            encoding="utf-8",
            delay=True,
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(JsonFormatter())
        debug_handler.addFilter(run_id_filter)
        root.addHandler(debug_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO if verbose else logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    console.addFilter(run_id_filter)
    root.addHandler(console)
