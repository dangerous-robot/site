"""T1-T5 harness against an Infomaniak OpenAI-compatible chat-completions endpoint.

Run via tester.py:
    python tester.py probe infomaniak <model> [--t1-only] [--retries N]

Or directly:
    uv run python scripts/llm-tester/harness/infomaniak.py --model mistral24b
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from ._env import load_env


def _post(client: httpx.Client, base_url: str, api_key: str, payload: dict) -> tuple[int, dict | str, float]:
    url = f"{base_url}/chat/completions"
    t0 = time.time()
    try:
        r = client.post(
            url,
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


def _excerpt(body: dict | str, n: int = 500) -> str:
    if isinstance(body, dict):
        s = json.dumps(body, ensure_ascii=False)
    else:
        s = str(body)
    return s[:n]


def _content_of(body: dict) -> str | None:
    try:
        return body["choices"][0]["message"].get("content")
    except Exception:
        return None


def _tool_calls_of(body: dict) -> list[dict] | None:
    try:
        return body["choices"][0]["message"].get("tool_calls")
    except Exception:
        return None


def t1_plain(client, base_url, api_key, model, max_tokens: int = 200) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: Pong"}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    status, body, elapsed = _post(client, base_url, api_key, payload)
    content = _content_of(body) if isinstance(body, dict) else None
    pass_ = status == 200 and bool(content and content.strip())
    return {
        "name": "T1 plain completion",
        "status": status,
        "elapsed": round(elapsed, 2),
        "pass": pass_,
        "content": content,
        "raw_excerpt": _excerpt(body),
    }


def t2_structured(client, base_url, api_key, model) -> dict:
    sys_prompt = (
        "You are a strict JSON emitter. Reply with ONLY a valid JSON object on a single line, "
        'with shape: {"verdict": "supported|refuted|inconclusive", "reasoning": "<short>"}. '
        "No code fences. No prose."
    )
    user = (
        "Claim: 'The Eiffel Tower is in Paris.' "
        "Return your verdict and a short reasoning string."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ],
        "max_tokens": 200,
        "temperature": 0,
    }
    status, body, elapsed = _post(client, base_url, api_key, payload)
    content = _content_of(body) if isinstance(body, dict) else None
    parsed = None
    parse_ok = False
    shape_ok = False
    if content:
        # try direct, then strip code fences
        candidates = [content.strip()]
        if "```" in content:
            stripped = content.strip().strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:]
            candidates.append(stripped.strip())
        for c in candidates:
            try:
                parsed = json.loads(c)
                parse_ok = True
                break
            except Exception:
                continue
        if parse_ok and isinstance(parsed, dict):
            shape_ok = "verdict" in parsed and "reasoning" in parsed
    return {
        "name": "T2 structured output",
        "status": status,
        "elapsed": round(elapsed, 2),
        "pass": status == 200 and parse_ok and shape_ok,
        "content": content,
        "parsed": parsed,
        "parse_ok": parse_ok,
        "shape_ok": shape_ok,
        "raw_excerpt": _excerpt(body),
    }


def _web_search_tool_def() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web and return results with title, url, and snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string.",
                    }
                },
                "required": ["query"],
            },
        },
    }


def t3_tool_def(client, base_url, api_key, model) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say hi briefly."}],
        "tools": [_web_search_tool_def()],
        "max_tokens": 30,
        "temperature": 0,
    }
    status, body, elapsed = _post(client, base_url, api_key, payload)
    err_msg = ""
    if isinstance(body, dict) and "error" in body:
        err_msg = json.dumps(body["error"])[:200]
    fmt_err = "tool" in err_msg.lower() and status >= 400
    return {
        "name": "T3 tool definition acceptance",
        "status": status,
        "elapsed": round(elapsed, 2),
        "pass": status == 200 and not fmt_err,
        "raw_excerpt": _excerpt(body),
    }


def t4_tool_call(client, base_url, api_key, model) -> dict:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Use the web_search tool to search for 'Anthropic Claude transparency report 2024'. "
                    "Call the tool; do not answer from memory."
                ),
            }
        ],
        "tools": [_web_search_tool_def()],
        "tool_choice": "auto",
        "max_tokens": 200,
        "temperature": 0,
    }
    status, body, elapsed = _post(client, base_url, api_key, payload)
    tcs = _tool_calls_of(body) if isinstance(body, dict) else None
    name_ok = False
    args_ok = False
    raw_call = None
    if tcs:
        raw_call = tcs[0]
        fn = (raw_call or {}).get("function") or {}
        name_ok = fn.get("name") == "web_search"
        args_str = fn.get("arguments")
        if isinstance(args_str, str):
            try:
                parsed_args = json.loads(args_str)
                args_ok = isinstance(parsed_args, dict) and "query" in parsed_args
            except Exception:
                args_ok = False
        elif isinstance(args_str, dict):
            args_ok = "query" in args_str
    return {
        "name": "T4 single-turn tool call",
        "status": status,
        "elapsed": round(elapsed, 2),
        "pass": status == 200 and bool(tcs) and name_ok and args_ok,
        "tool_calls": tcs,
        "raw_excerpt": _excerpt(body),
        "_raw_call_for_t5": raw_call,
        "_t4_assistant_message": body["choices"][0]["message"] if isinstance(body, dict) and "choices" in body else None,
    }


def t5_multi_turn(client, base_url, api_key, model, t4_result: dict) -> dict:
    raw_call = t4_result.get("_raw_call_for_t5")
    assistant_msg = t4_result.get("_t4_assistant_message")
    if not raw_call or not assistant_msg:
        return {
            "name": "T5 multi-turn tool result handling",
            "status": -1,
            "elapsed": 0.0,
            "pass": False,
            "raw_excerpt": "skipped: T4 produced no tool_call to follow up on",
        }
    tool_call_id = raw_call.get("id") or "call_synthetic_0"
    fake_tool_result = json.dumps([
        {
            "url": "https://www.anthropic.com/news/claude-3-family",
            "title": "Anthropic transparency report 2024",
            "snippet": "Anthropic's 2024 transparency report covers enforcement, "
                       "research disclosures, and policy guidance for Claude models.",
        }
    ])
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Use the web_search tool to search for 'Anthropic Claude transparency report 2024'. "
                    "Call the tool; do not answer from memory."
                ),
            },
            assistant_msg,  # assistant turn that contains tool_calls
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": fake_tool_result,
            },
        ],
        "tools": [_web_search_tool_def()],
        "max_tokens": 200,
        "temperature": 0,
    }
    status, body, elapsed = _post(client, base_url, api_key, payload)
    content = _content_of(body) if isinstance(body, dict) else None
    return {
        "name": "T5 multi-turn tool result handling",
        "status": status,
        "elapsed": round(elapsed, 2),
        "pass": status == 200 and bool(content and content.strip()),
        "content": content,
        "raw_excerpt": _excerpt(body),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--t1-only", action="store_true", help="run only T1 (single shot)")
    ap.add_argument("--retries", type=int, default=1, help="retries on 5xx for T1 ping")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent.parent
    env = load_env(here / ".env.poc")
    api_key = env["INFOMANIAK_API_KEY"]
    product_id = env["INFOMANIAK_PRODUCT_ID"]
    base_url = f"https://api.infomaniak.com/2/ai/{product_id}/openai/v1"

    results: list[dict] = []

    with httpx.Client() as client:
        # T1 with retry semantics if requested
        last_t1 = None
        for attempt in range(1, args.retries + 1):
            r = t1_plain(client, base_url, api_key, args.model)
            r["attempt"] = attempt
            last_t1 = r
            if r["status"] == 200 or (r["status"] != -1 and not (500 <= r["status"] < 600)):
                break
            print(f"[T1 attempt {attempt}] status={r['status']} elapsed={r['elapsed']}s", file=sys.stderr)
        results.append(last_t1)

        if args.t1_only:
            print(json.dumps(results, indent=2, default=str))
            return 0

        if last_t1["status"] != 200:
            print("[abort] T1 did not return 200; not running T2-T5", file=sys.stderr)
            print(json.dumps(results, indent=2, default=str))
            return 0

        results.append(t2_structured(client, base_url, api_key, args.model))
        results.append(t3_tool_def(client, base_url, api_key, args.model))
        t4 = t4_tool_call(client, base_url, api_key, args.model)
        results.append(t4)
        if t4["status"] == 200 and t4.get("_raw_call_for_t5"):
            results.append(t5_multi_turn(client, base_url, api_key, args.model, t4))
        else:
            results.append({
                "name": "T5 multi-turn tool result handling",
                "status": -1,
                "elapsed": 0.0,
                "pass": False,
                "raw_excerpt": f"skipped: T4 status={t4['status']}, tool_calls present={bool(t4.get('_raw_call_for_t5'))}",
            })

    # strip private keys before printing
    for r in results:
        for k in list(r.keys()):
            if k.startswith("_"):
                r.pop(k, None)

    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
