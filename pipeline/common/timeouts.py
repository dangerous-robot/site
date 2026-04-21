"""Centralized HTTP and agent timeout constants for the ingestor pipeline.

These constants live in one place so operators and future plans can tune them
without hunting across files. Values were chosen for a fail-fast POC:

- Legitimate pages respond well under 5s; a 5s connect cap catches dead hosts.
- 15s read is a generous ceiling for live HTML.
- Wayback availability and save endpoints keep their pre-existing budgets.

The four user-facing wall-clock budgets (ingest/research/analyst/auditor) are
NOT defined here; they live as fields on ``VerifyConfig`` in
``orchestrator/pipeline.py`` so callers can override them per-run.
"""

from __future__ import annotations

import httpx

HTTP_CONNECT_S = 5.0
HTTP_READ_S = 15.0
HTTP_WRITE_S = 5.0
HTTP_POOL_S = 5.0

WAYBACK_CHECK_S = 15.0
WAYBACK_SAVE_S = 30.0

RATE_LIMIT_RETRY_S = 2.0
LLM_BUDGET_S = 25.0


def default_httpx_timeout() -> httpx.Timeout:
    """Return the standard per-phase httpx timeout used by ``web_fetch``."""
    return httpx.Timeout(
        connect=HTTP_CONNECT_S,
        read=HTTP_READ_S,
        write=HTTP_WRITE_S,
        pool=HTTP_POOL_S,
    )


def ingest_budget_with_wayback_s() -> float:
    """Ingest wall-clock budget when ``skip_wayback=False``.

    Covers: initial fetch, the 429 retry arm (one extra connect+read plus sleep),
    wayback availability + save, and LLM tool-dispatch turns.
    """
    return (
        HTTP_CONNECT_S + HTTP_READ_S
        + RATE_LIMIT_RETRY_S + HTTP_CONNECT_S + HTTP_READ_S
        + WAYBACK_CHECK_S + WAYBACK_SAVE_S
        + LLM_BUDGET_S
    )
