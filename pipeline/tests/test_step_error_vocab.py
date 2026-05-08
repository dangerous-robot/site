"""Drift smoke test for StepError.error_type vocabulary.

The ``error_type`` field on ``StepError`` is intentionally a free-form
``str`` (see the class docstring in ``orchestrator/checkpoints.py``).
That flexibility is convenient but easy to abuse: a contributor can add
``error_type="foo"`` in production code without telling anyone, and the
docstring slowly goes stale.

This test scans every production ``.py`` file under ``pipeline/`` for
literal ``error_type=...`` assignments and asserts that each literal is
documented in the ``StepError`` docstring. The reverse direction
(documented-but-unused) is intentionally allowed: the docstring lists
several values reserved for tier1 source-pool expansion paths that
haven't shipped yet.

If this test fails with "undocumented error_type literal", you have two
options:
    1. Add the new literal to the ``StepError`` docstring under the
       appropriate group, then re-run.
    2. Reconsider whether the new literal really belongs on the error
       channel rather than ``research_trace["tool_outcomes"]`` or
       ``sources_consulted[].acquisition.outcome``.
"""

from __future__ import annotations

import re
from pathlib import Path

from orchestrator.checkpoints import StepError


# Mirror of the in-use + reserved vocabulary from the StepError docstring.
# Keep this in sync with orchestrator/checkpoints.py::StepError.__doc__.
# The smoke test below also asserts the docstring itself contains each
# of these literals, so drift between this list and the docstring fails
# loudly before drift between either and production code can hide.
DOCUMENTED_LITERALS: frozenset[str] = frozenset(
    {
        # Fetch / network
        "timeout",
        "blocked_host",
        "all_blocked",
        "http_error",
        # Model
        "model_error",
        "api_key_missing",
        # Researcher
        "no_queries",
        "no_results",
        "scorer_dropped_all",
        # Reserved (tier1 source-pool expansion)
        "wayback_unavailable",
        "memento_unavailable",
        "edgar_ua_missing",
        "edgar_rate_limited",
        "tavily_rate_limited",
    }
)

# Format-pattern prefixes: production code may build error_type values via
# f-strings (e.g. f"http_{status}"). The docstring documents these as
# ``http_{status}``. We strip the trailing brace expression and match the
# prefix against the documented patterns below.
DOCUMENTED_PATTERNS: frozenset[str] = frozenset({"http_"})


# Match `error_type = "literal"` or `error_type="literal"` (single or double
# quotes). The literal is captured in group 1.
_PLAIN_RE = re.compile(r"error_type\s*=\s*['\"]([^'\"]+)['\"]")
# Match `error_type = f"prefix{...}..."`. We capture only the substring
# before the first `{` -- that's the stable prefix the docstring should
# document as a pattern. If there is no `{`, we treat it as a plain literal.
_FSTRING_RE = re.compile(r"error_type\s*=\s*f['\"]([^'\"]*)")

# Match `_research_err("literal", ...)` -- the helper in
# pipeline/researcher/decomposed.py forwards its first positional argument
# to ``StepError(error_type=...)``. Without this rule the scanner would
# miss every researcher error_type and silently allow drift there.
_RESEARCH_ERR_RE = re.compile(r"_research_err\(\s*['\"]([^'\"]+)['\"]")


def _pipeline_root() -> Path:
    # tests/ live inside pipeline/, so the parent of this file's parent is
    # the package root. Tests are invoked with cwd=pipeline/ via `inv test`.
    return Path(__file__).resolve().parent.parent


def _iter_production_py_files() -> list[Path]:
    root = _pipeline_root()
    skip_dirs = {"tests", "__pycache__", ".venv", "venv"}
    out: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in skip_dirs for part in path.relative_to(root).parts):
            continue
        out.append(path)
    return out


def _scan_for_error_type_literals() -> dict[str, list[str]]:
    """Return {literal: [file paths where it appears]} for production code."""
    findings: dict[str, list[str]] = {}
    root = _pipeline_root()
    for path in _iter_production_py_files():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root))

        for match in _PLAIN_RE.finditer(text):
            findings.setdefault(match.group(1), []).append(rel)

        for match in _FSTRING_RE.finditer(text):
            raw = match.group(1)
            # Capture the stable prefix before any interpolation.
            prefix = raw.split("{", 1)[0]
            if "{" in raw:
                # Tag with the trailing brace so the matcher knows this is
                # a format pattern, not a plain literal.
                findings.setdefault(prefix + "{", []).append(rel)
            elif prefix:
                findings.setdefault(prefix, []).append(rel)

        for match in _RESEARCH_ERR_RE.finditer(text):
            findings.setdefault(match.group(1), []).append(rel)
    return findings


def _is_documented(literal: str) -> bool:
    if literal.endswith("{"):
        # Format pattern; check the prefix is documented.
        return literal[:-1] in {p.rstrip("{") for p in DOCUMENTED_PATTERNS} or any(
            literal[:-1] == p.rstrip("_") + "_" for p in DOCUMENTED_PATTERNS
        ) or literal[:-1] in DOCUMENTED_PATTERNS
    return literal in DOCUMENTED_LITERALS


def test_documented_vocabulary_appears_in_docstring() -> None:
    """The docstring must mention each literal we claim is documented.

    This catches the case where the test's ``DOCUMENTED_LITERALS`` set
    drifts ahead of the actual class docstring.
    """
    doc = StepError.__doc__ or ""
    missing = sorted(lit for lit in DOCUMENTED_LITERALS if lit not in doc)
    assert not missing, (
        "DOCUMENTED_LITERALS contains values absent from StepError.__doc__: "
        f"{missing}. Either add them to the docstring or remove them from "
        "the test's DOCUMENTED_LITERALS set."
    )
    # And the format pattern note.
    assert "http_{status}" in doc, (
        "StepError docstring should document the http_{status} format pattern."
    )


def test_no_undocumented_error_type_literals_in_production() -> None:
    """Every literal ``error_type=`` value in production code is documented.

    Skips ``pipeline/tests/`` and ``__pycache__``. Plain string literals
    must appear in ``DOCUMENTED_LITERALS``; f-string prefixes (e.g.
    ``http_`` from ``f"http_{status}"``) must appear in
    ``DOCUMENTED_PATTERNS``.
    """
    findings = _scan_for_error_type_literals()
    undocumented: dict[str, list[str]] = {
        literal: paths
        for literal, paths in findings.items()
        if not _is_documented(literal)
    }
    assert not undocumented, (
        "Found undocumented error_type literal(s) in production code. "
        "Either add them to the StepError docstring (and to "
        "DOCUMENTED_LITERALS / DOCUMENTED_PATTERNS in this test) or "
        "reconsider whether the value belongs on the error channel "
        "rather than research_trace['tool_outcomes'] or "
        "sources_consulted[].acquisition.outcome.\n\n"
        f"Undocumented: {undocumented}"
    )


def test_scanner_finds_known_literals() -> None:
    """Sanity: the scanner picks up the literals we know exist today.

    Without this, a regex bug could mask drift by silently finding
    nothing. We assert at least the canonical set is present so a
    broken scanner fails loudly instead of passing trivially.
    """
    findings = _scan_for_error_type_literals()
    must_be_present = {
        "timeout",
        "blocked_host",
        "all_blocked",
        "model_error",
        "no_queries",
        "no_results",
        "scorer_dropped_all",
        "http_{",  # format pattern from f"http_{exc.status_code}"
    }
    missing = sorted(must_be_present - set(findings))
    assert not missing, (
        f"Scanner failed to find expected literals: {missing}. "
        "The error_type regex may be broken."
    )
