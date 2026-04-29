from __future__ import annotations


TESTS = ("T1", "T2", "T2b", "T3", "T4", "T5")

TABLE_HEADER = "| Provider | Model | T1 | T2 | T2b | T3 | T4 | T5 | Last tested |"
TABLE_SEP    = "|---|---|---|---|---|---|---|---|---|"


def score_results(results: list[dict]) -> dict[str, str]:
    """Map T1-T5 to ✅ / ❌ / BLK / — from a harness result list."""
    seen: dict[str, str] = {}
    for r in results:
        name = r.get("name", "")
        for t in TESTS:
            if t in seen:
                continue
            if name.startswith(t):
                if r.get("pass"):
                    seen[t] = "✅"
                elif r.get("status") == -1:
                    seen[t] = "BLK"
                else:
                    seen[t] = "❌"
    return {t: seen.get(t, "—") for t in TESTS}


def format_row(provider: str, model: str, scores: dict[str, str], date: str) -> str:
    cols = " | ".join(scores[t] for t in TESTS)
    return f"| {provider} | {model} | {cols} | {date} |"
