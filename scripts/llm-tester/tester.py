"""Thin CLI dispatcher for the LLM tester harnesses.

Usage:
    python tester.py probe <provider> <model> [harness-specific flags...]
    python tester.py trace <provider> <model>
    python tester.py list
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness._fmt import TABLE_HEADER, TABLE_SEP, TESTS, format_row, score_results  # noqa: E402

KNOWN_MODELS = [
    ("infomaniak", "gemma3n",                             "T1✅ T2✅ T3❌ T4❌ T5BLK", "2026-04-28"),
    ("infomaniak", "mistral24b",                          "T1✅ T2✅ T3✅ T4✅ T5❌",  "2026-04-28"),
    ("infomaniak", "swiss-ai/Apertus-70B-Instruct-2509",  "T1✅ T2✅ T3✅ T4✅ T5❌",  "2026-04-25"),
    ("infomaniak", "openai/gpt-oss-120b",                 "T1⚠ T2? T3? T4? T5?",     "2026-04-28"),
    ("infomaniak", "google/gemma-4-31B-it",               "T1✅ T2✅ T3✅ T4✅ T5✅",  "2026-04-27"),
    ("greenpt",    "mistral-small-3.2-24b-instruct-2506", "T1✅ T2✅ T3✅ T4✅ T5✅",  "2026-04-25"),
    ("greenpt",    "gemma-3-27b-it",                      "T1✅ T2✅ T3✅ T4✅ T5⚠",  "2026-04-25"),
    ("greenpt",    "gpt-oss-120b",                        "T1✅ T2✅ T3✅ T4✅ T5✅",  "2026-04-25"),
    ("greenpt",    "green-l-raw",                         "T1✅ T2✅ T3✅ T4✅ T5✅",  "2026-04-25"),
    ("greenpt",    "green-r-raw",                         "T1✅ T2✅ T3✅ T4❌ T5BLK", "2026-04-25"),
]

KNOWN_PROVIDERS = {row[0] for row in KNOWN_MODELS}


def cmd_list() -> int:
    print(f"{'Provider':<14} {'Model':<44} {'T1-T5':<24} {'Last tested'}")
    print("-" * 95)
    for provider, model, scores, date in KNOWN_MODELS:
        print(f"{provider:<14} {model:<44} {scores:<24} {date}")
    return 0


def _write_archive(provider: str, model: str, content: str, date: str) -> Path:
    safe = model.replace("/", "-")
    path = HERE / "archive" / f"{date}-{provider}-{safe}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    title = f"# {date} — {provider} / {model}"
    path.write_text(f"{title}\n\n{content}\n", encoding="utf-8")
    return path


def cmd_probe(args: list[str]) -> int:
    if len(args) < 2:
        print("usage: tester.py probe <provider> <model> [flags...]", file=sys.stderr)
        return 1
    provider, model, *rest = args
    if provider not in KNOWN_PROVIDERS:
        print(f"unknown provider {provider!r}; known: {sorted(KNOWN_PROVIDERS)}", file=sys.stderr)
        return 1
    result = subprocess.run(
        [sys.executable, "-m", f"harness.{provider}", "--model", model, *rest],
        cwd=HERE,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.returncode
    try:
        scores = score_results(data)
        date = datetime.date.today().isoformat()
        row = format_row(provider, model, scores, date)
        table = f"{TABLE_HEADER}\n{TABLE_SEP}\n{row}"
        print(f"\n{TABLE_HEADER}", file=sys.stderr)
        print(TABLE_SEP, file=sys.stderr)
        print(row, file=sys.stderr)
        archive_path = _write_archive(provider, model, table, date)
        print(f"→ {archive_path.relative_to(HERE)}", file=sys.stderr)
    except Exception as e:
        print(f"warning: post-processing failed: {e}", file=sys.stderr)
    return result.returncode


def cmd_trace(args: list[str]) -> int:
    if len(args) < 2:
        print("usage: tester.py trace <provider> <model>", file=sys.stderr)
        return 1
    provider, model = args[0], args[1]
    if provider != "infomaniak":
        print(f"trace only implemented for infomaniak; got {provider!r}", file=sys.stderr)
        return 1
    tracer = HERE / "trace" / "infomaniak.py"
    return subprocess.run([sys.executable, str(tracer), model]).returncode


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv
    if cmd == "list":
        return cmd_list()
    if cmd == "probe":
        return cmd_probe(rest)
    if cmd == "trace":
        return cmd_trace(rest)
    print(f"unknown subcommand {cmd!r}; use: probe, trace, list", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
