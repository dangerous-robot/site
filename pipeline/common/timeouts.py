"""Centralized HTTP and agent timeout constants for the ingestor pipeline.

These constants live in one place so operators and future plans can tune them
without hunting across files. Values were chosen for a fail-fast POC:

- Legitimate pages respond well under 5s; a 5s connect cap catches dead hosts.
- 15s read is a generous ceiling for live HTML.
- Wayback availability and save endpoints keep their pre-existing budgets.
- A capture check is one HEAD per redirect hop, so 10s covers the usual
  sub-second replay with room for a slow hop; the CDX index is slow
  (7 to 30s seen), so its fallback gets 30s and a timeout records no link.

The four user-facing wall-clock budgets (ingest/research/analyst/auditor) are
NOT defined here; they live as fields on ``VerifyConfig`` in
``loop/spec.py`` so callers can override them per-run.
"""

from __future__ import annotations

import httpx

HTTP_CONNECT_S = 5.0
HTTP_READ_S = 15.0
HTTP_WRITE_S = 5.0
HTTP_POOL_S = 5.0

WAYBACK_CHECK_S = 15.0
WAYBACK_SAVE_S = 30.0
WAYBACK_VERIFY_S = 10.0
WAYBACK_CDX_S = 30.0

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
    the model's recovery ``wayback_check`` (one full archive lookup, see
    ``archive_lookup_cost_s``), and LLM tool-dispatch turns. The archive
    lookup run in code after the ingest has its own limit,
    ``archive_lookup_budget_s``.
    """
    return (
        HTTP_CONNECT_S + HTTP_READ_S
        + RATE_LIMIT_RETRY_S + HTTP_CONNECT_S + HTTP_READ_S
        + archive_lookup_cost_s()
        + LLM_BUDGET_S
    )


def archive_lookup_cost_s() -> float:
    """Worst-case time of one archive lookup.

    The TimeGate check, a check of the capture it names, the CDX fallback,
    Save Page Now and a check of the saved capture, plus one 429 wait for
    each of the three requests that retry outside a capture check (a 429
    answers fast, so the retried request fits in the same allowance; a
    capture check retries within its own limit).
    """
    return (
        WAYBACK_CHECK_S + 2 * WAYBACK_VERIFY_S + WAYBACK_CDX_S
        + WAYBACK_SAVE_S + 3 * RATE_LIMIT_RETRY_S
    )


def archive_lookup_budget_s() -> float:
    """Wall-clock limit for the archive lookup run in code after each ingest."""
    return archive_lookup_cost_s()
