"""Run T1-T5 against all known models and write a matrix MD file.

Usage:
    python scan.py [--t1-only] [--providers infomaniak,greenpt]

Output:
    matrix-<YYYY-MM-DD>.md  in the llm-tester root directory
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness._fmt import TABLE_HEADER, TABLE_SEP, TESTS, format_row, score_results  # noqa: E402
from tester import KNOWN_MODELS  # noqa: E402

_TESTER = str(HERE / "tester.py")


def probe_model(provider: str, model: str, t1_only: bool) -> dict[str, str] | None:
    extra = ["--t1-only"] if t1_only else []
    result = subprocess.run(
        [sys.executable, _TESTER, "probe", provider, model, *extra],
        cwd=HERE,
        capture_output=True,
        text=True,
    )
    try:
        return score_results(json.loads(result.stdout))
    except Exception as e:
        print(f"  parse error for {provider} {model}: {e}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t1-only", action="store_true", help="run only T1 per model")
    ap.add_argument("--providers", help="comma-separated provider filter, e.g. infomaniak")
    args = ap.parse_args()

    provider_filter = set(args.providers.split(",")) if args.providers else None
    models = [
        (provider, model)
        for provider, model, _, _ in KNOWN_MODELS
        if not provider_filter or provider in provider_filter
    ]

    date = datetime.date.today().isoformat()
    results_map: dict[tuple[str, str], dict[str, str] | None] = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(probe_model, provider, model, args.t1_only): (provider, model)
            for provider, model in models
        }
        for fut in as_completed(futures):
            provider, model = futures[fut]
            scores = fut.result()
            results_map[(provider, model)] = scores
            if scores is None:
                print(f"probing {provider} {model} ... ERROR", file=sys.stderr)
            else:
                summary = " ".join(f"{t}{scores[t]}" for t in TESTS)
                print(f"probing {provider} {model} ... {summary}", file=sys.stderr)

    rows = [
        format_row(provider, model, results_map.get((provider, model)) or {t: "ERR" for t in TESTS}, date)
        for provider, model in models
    ]

    matrix = "\n".join([f"# LLM tester matrix — {date}", "", TABLE_HEADER, TABLE_SEP, *rows])
    out_path = HERE / f"matrix-{date}.md"
    out_path.write_text(matrix + "\n", encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
