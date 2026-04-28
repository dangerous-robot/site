"""Wire-level tracer for Infomaniak gemma3n calls.

Captures full request/response details using httpx event hooks for three
variants: gemma3n non-streaming, gemma3n streaming, and a sibling control
(google/gemma-4-31B-it). Goal: diff production's wire shape against our
earlier POC's wire shape and verify whether gemma3n is still degraded.

Usage:
    uv run python scripts/poc-multi-provider/trace_infomaniak.py

Output:
    trace-gemma3n-<timestamp>-<n>-<variant>.json (one per attempt)

Import path:
    Faithful replica of parallax-ai's _build_payload + InfomaniakAdapter
    client construction. The production import path was attempted but
    requires sqlalchemy and other transitive deps that aren't installed
    in this POC env. The replica below is a verbatim copy of the 5
    payload lines from _openai_compat.py:_build_payload and the client
    construction from _infomaniak.py:__init__.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from harness._env import load_env  # noqa: E402

RUN_TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_base_url(product_id: str, api_version: str) -> str:
    """Verbatim from parallax-ai _infomaniak.py:_build_base_url."""
    if api_version == "1":
        return f"https://api.infomaniak.com/1/ai/{product_id}/openai/chat/completions"
    return f"https://api.infomaniak.com/2/ai/{product_id}/openai/v1/chat/completions"


def build_payload(model: str, messages: list[dict], max_tokens: int,
                  temperature: float | None, stream: bool) -> dict:
    """Verbatim from _openai_compat.py:_build_payload (system=None case)."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def redact_headers(h: dict) -> dict:
    out = {}
    for k, v in h.items():
        if k.lower() == "authorization":
            out[k] = "Bearer <REDACTED>"
        else:
            out[k] = v
    return out


async def trace_attempt(client: httpx.AsyncClient, base_url: str, payload: dict,
                        is_stream: bool, idx: int, label: str) -> dict:
    """Run one request, capturing wire details via event hooks."""
    captured: dict = {"variant": label, "idx": idx, "wall_clock_utc": datetime.now(timezone.utc).isoformat()}
    t_start = {"v": 0.0}

    async def req_hook(req: httpx.Request) -> None:
        t_start["v"] = time.monotonic()
        body_text = req.content.decode("utf-8", errors="replace") if req.content else ""
        try:
            body_json = json.loads(body_text) if body_text else None
        except json.JSONDecodeError:
            body_json = None
        captured["request"] = {
            "url": str(req.url),
            "method": req.method,
            "headers": redact_headers(dict(req.headers)),
            "body_text": body_text,
            "body_json": body_json,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

    async def resp_hook(resp: httpx.Response) -> None:
        captured["response_pre_read"] = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "http_version": resp.http_version,
            "elapsed_ms_to_headers": int((time.monotonic() - t_start["v"]) * 1000),
        }

    # Mutate event hooks post-construction (httpx supports this)
    client.event_hooks = {"request": [req_hook], "response": [resp_hook]}

    try:
        if is_stream:
            async with client.stream("POST", base_url, json=payload) as resp:
                chunks: list[str] = []
                total = 0
                async for line in resp.aiter_lines():
                    chunks.append(line)
                    total += len(line)
                    if total > 4096:
                        break
                body_text = "\n".join(chunks)
                captured["response"] = {
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                    "body_first_4kb": body_text[:4096],
                    "body_truncated": total > 4096,
                }
        else:
            resp = await client.post(base_url, json=payload)
            captured["response"] = {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body_first_4kb": resp.text[:4096],
                "body_truncated": len(resp.text) > 4096,
            }
        captured["elapsed_ms"] = int((time.monotonic() - t_start["v"]) * 1000)
    except Exception as e:
        captured["error"] = f"{type(e).__name__}: {e}"
        captured["elapsed_ms"] = int((time.monotonic() - t_start["v"]) * 1000)

    out_path = HERE / f"trace-gemma3n-{RUN_TS}-{idx}-{label}.json"
    out_path.write_text(json.dumps(captured, indent=2))
    print(f"[{label}] -> status={captured.get('response', {}).get('status_code', 'ERR')} "
          f"in {captured.get('elapsed_ms', '?')}ms -> {out_path.name}", flush=True)
    return captured


async def main() -> None:
    env = load_env(HERE / ".env.poc")
    api_key = env["INFOMANIAK_API_KEY"]
    product_id = env["INFOMANIAK_PRODUCT_ID"]
    api_version = env.get("INFOMANIAK_API_VERSION", "2")
    base_url = build_base_url(product_id, api_version)

    # Verbatim from _infomaniak.py:__init__
    client = httpx.AsyncClient(
        timeout=60.0,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    messages = [{"role": "user", "content": "ping"}]

    variants = [
        # 1. gemma3n non-streaming, production payload shape (no temperature)
        ("gemma3n-nonstream",
         build_payload("gemma3n", messages, max_tokens=8, temperature=None, stream=False),
         False),
        # 2. gemma3n streaming, same payload but stream=true
        ("gemma3n-stream",
         build_payload("gemma3n", messages, max_tokens=8, temperature=None, stream=True),
         True),
        # 3. sibling control: gemma-4-31B-it, non-streaming, same shape as #1
        ("sibling-gemma4-31B",
         build_payload("google/gemma-4-31B-it", messages, max_tokens=8, temperature=None, stream=False),
         False),
    ]

    results = []
    try:
        for i, (label, payload, is_stream) in enumerate(variants, start=1):
            row = await trace_attempt(client, base_url, payload, is_stream, i, label)
            results.append(row)
    finally:
        await client.aclose()

    # Summary
    print("\n=== SUMMARY ===")
    for r in results:
        st = r.get("response", {}).get("status_code") or r.get("error", "ERR")
        print(f"  {r['variant']}: status={st}, elapsed={r.get('elapsed_ms','?')}ms")

    summary_path = HERE / f"trace-gemma3n-{RUN_TS}-summary.json"
    summary_path.write_text(json.dumps({"run_ts": RUN_TS, "results": results}, indent=2))
    print(f"\nSummary written to {summary_path.name}")


if __name__ == "__main__":
    asyncio.run(main())
