"""T1-T5 harness against GreenPT (router + direct), OpenAI-compatible.

Run via tester.py:
    python tester.py probe greenpt <model> [--t1-only] [--t5-mode raw|stripped|both|skip]

Or directly:
    uv run python scripts/llm-tester/harness/greenpt.py --model mistral-small-3.2-24b-instruct-2506
    uv run python scripts/llm-tester/harness/greenpt.py --model green-l-raw --t5-mode raw
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from ._env import load_env

GREENPT_URL = "https://api.greenpt.ai/v1/chat/completions"


def _post(client: httpx.Client, api_key: str, payload: dict) -> tuple[int, dict | str, float]:
    t0 = time.time()
    try:
        r = client.post(
            GREENPT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60.0,
        )
    except httpx.HTTPError as e:
        return -1, f"transport_error: {e!r}", time.time() - t0
    elapsed = time.time() - t0
    body: dict | str
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, body, elapsed


def _excerpt(body, n: int = 500) -> str:
    s = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
    return s[:n]


def _content(body):
    try: return body["choices"][0]["message"].get("content")
    except Exception: return None


def _tcs(body):
    try: return body["choices"][0]["message"].get("tool_calls")
    except Exception: return None


def _impact(body):
    return body.get("impact") if isinstance(body, dict) else None


def t1(client, api_key, model, max_tokens: int = 200):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: Pong"}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    s, b, e = _post(client, api_key, payload)
    c = _content(b) if isinstance(b, dict) else None
    return {
        "name": "T1 plain",
        "status": s, "elapsed": round(e, 2),
        "pass": s == 200 and bool(c and c.strip()),
        "content": c,
        "impact": _impact(b),
        "raw_excerpt": _excerpt(b),
    }


def t2(client, api_key, model):
    sys_p = (
        "You are a strict JSON emitter. Reply with ONLY a valid JSON object on a single line, "
        'with shape: {"verdict": "supported|refuted|inconclusive", "reasoning": "<short>"}. '
        "No code fences. No prose."
    )
    user = "Claim: 'The Eiffel Tower is in Paris.' Return your verdict and a short reasoning string."
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user},
        ],
        "max_tokens": 200,
        "temperature": 0,
    }
    s, b, e = _post(client, api_key, payload)
    c = _content(b) if isinstance(b, dict) else None
    parsed = None
    parse_ok = False
    shape_ok = False
    if c:
        cands = [c.strip()]
        if "```" in c:
            sc = c.strip().strip("`")
            if sc.startswith("json"): sc = sc[4:]
            cands.append(sc.strip())
        for cc in cands:
            try:
                parsed = json.loads(cc)
                parse_ok = True
                break
            except Exception:
                continue
        if parse_ok and isinstance(parsed, dict):
            shape_ok = "verdict" in parsed and "reasoning" in parsed
    return {
        "name": "T2 structured",
        "status": s, "elapsed": round(e, 2),
        "pass": s == 200 and parse_ok and shape_ok,
        "content": c, "parsed": parsed,
        "raw_excerpt": _excerpt(b),
    }


def _tool_def():
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web and return results with title, url, and snippet.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "search query"}},
                "required": ["query"],
            },
        },
    }


def t3(client, api_key, model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say hi briefly."}],
        "tools": [_tool_def()],
        "max_tokens": 50,
        "temperature": 0,
    }
    s, b, e = _post(client, api_key, payload)
    err_msg = ""
    if isinstance(b, dict) and "error" in b:
        err_msg = json.dumps(b["error"])[:200]
    fmt_err = "tool" in err_msg.lower() and s >= 400
    return {
        "name": "T3 tool def",
        "status": s, "elapsed": round(e, 2),
        "pass": s == 200 and not fmt_err,
        "raw_excerpt": _excerpt(b),
    }


def t4(client, api_key, model):
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": (
                "Use the web_search tool to search for 'Anthropic Claude transparency report 2024'. "
                "Call the tool; do not answer from memory."
            ),
        }],
        "tools": [_tool_def()],
        "tool_choice": "auto",
        "max_tokens": 300,
        "temperature": 0,
    }
    s, b, e = _post(client, api_key, payload)
    tcs = _tcs(b) if isinstance(b, dict) else None
    name_ok = args_ok = False
    raw_call = None
    if tcs:
        raw_call = tcs[0]
        fn = (raw_call or {}).get("function") or {}
        name_ok = fn.get("name") == "web_search"
        args_str = fn.get("arguments")
        if isinstance(args_str, str):
            try:
                pa = json.loads(args_str)
                args_ok = isinstance(pa, dict) and "query" in pa
            except Exception:
                args_ok = False
    return {
        "name": "T4 tool call",
        "status": s, "elapsed": round(e, 2),
        "pass": s == 200 and bool(tcs) and name_ok and args_ok,
        "tool_calls": tcs,
        "raw_excerpt": _excerpt(b),
        "_raw_call": raw_call,
        "_assistant_msg": b["choices"][0]["message"] if isinstance(b, dict) and "choices" in b else None,
    }


def _strip_assistant(msg: dict) -> dict:
    """mistral24b workaround: keep only role/content/tool_calls."""
    out = {"role": "assistant"}
    if "content" in msg: out["content"] = msg["content"]
    if msg.get("tool_calls"): out["tool_calls"] = msg["tool_calls"]
    return out


def t5(client, api_key, model, t4_result, mode="raw"):
    raw_call = t4_result.get("_raw_call")
    asst = t4_result.get("_assistant_msg")
    if not raw_call or not asst:
        return {
            "name": f"T5 multi-turn ({mode})",
            "status": -1, "elapsed": 0.0, "pass": False,
            "raw_excerpt": "skipped: no T4 tool_call",
        }
    tool_call_id = raw_call.get("id") or "call_synthetic_0"
    fake_result = json.dumps([{
        "url": "https://www.anthropic.com/news/claude-3-family",
        "title": "Anthropic transparency report 2024",
        "snippet": "Anthropic's 2024 transparency report covers enforcement, research disclosures, and policy guidance for Claude models.",
    }])
    asst_to_send = asst if mode == "raw" else _strip_assistant(asst)
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": (
                "Use the web_search tool to search for 'Anthropic Claude transparency report 2024'. "
                "Call the tool; do not answer from memory."
            )},
            asst_to_send,
            {"role": "tool", "tool_call_id": tool_call_id, "content": fake_result},
        ],
        "tools": [_tool_def()],
        "max_tokens": 300,
        "temperature": 0,
    }
    s, b, e = _post(client, api_key, payload)
    c = _content(b) if isinstance(b, dict) else None
    return {
        "name": f"T5 multi-turn ({mode})",
        "status": s, "elapsed": round(e, 2),
        "pass": s == 200 and bool(c and c.strip()),
        "content": c,
        "raw_excerpt": _excerpt(b),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--t1-only", action="store_true")
    ap.add_argument("--skip-after-t2", action="store_true", help="if T1/T2 fail, skip rest")
    ap.add_argument("--t5-mode", choices=["raw", "stripped", "both", "skip"], default="raw")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent.parent
    env = load_env(here / ".env.poc")
    api_key = env["GREENPT_API_KEY"]

    results = []
    with httpx.Client() as client:
        r1 = t1(client, api_key, args.model)
        results.append(r1)
        if args.t1_only:
            print(json.dumps(_clean(results), indent=2, default=str))
            return 0
        if r1["status"] != 200:
            print("[abort] T1 failed", file=sys.stderr)
            print(json.dumps(_clean(results), indent=2, default=str)); return 0

        r2 = t2(client, api_key, args.model)
        results.append(r2)
        if args.skip_after_t2 and not r2["pass"]:
            print(json.dumps(_clean(results), indent=2, default=str)); return 0

        r3 = t3(client, api_key, args.model)
        results.append(r3)
        r4 = t4(client, api_key, args.model)
        results.append(r4)
        if r4["status"] == 200 and r4.get("_raw_call"):
            if args.t5_mode in ("raw", "both"):
                results.append(t5(client, api_key, args.model, r4, mode="raw"))
            if args.t5_mode in ("stripped", "both"):
                results.append(t5(client, api_key, args.model, r4, mode="stripped"))
        else:
            results.append({
                "name": "T5 multi-turn",
                "status": -1, "elapsed": 0.0, "pass": False,
                "raw_excerpt": f"skipped: T4 status={r4['status']}",
            })

    print(json.dumps(_clean(results), indent=2, default=str))
    return 0


def _clean(results):
    out = []
    for r in results:
        rr = {k: v for k, v in r.items() if not k.startswith("_")}
        out.append(rr)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
