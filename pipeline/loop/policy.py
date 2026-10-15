"""The error policy: which rule each step failure follows.

Every failure of a claim run has a ``StepError`` vocabulary literal (see
``loop/errors.py``). ``ERROR_POLICY`` maps each to a rule:

- flaw-retry: the pipeline produced something unusable; re-run the step
  ``VerifyConfig.flaw_retries`` times with no delay.
- transport-retry: the network or a provider failed; re-run the step
  ``VerifyConfig.transport_retries`` times with backoff.
- config-fatal: a missing key or a setting no retry can fix; stop at once.
- half-claim: the writer failed part-way; nothing is retried or deleted.
- tiebreaker: the analyst and the Evaluator disagreed; settled by the
  tie-breaker, not retried.

``STEP_ON_EXHAUSTION`` names the outcome a step's failure records once its
retries run out.
"""

from __future__ import annotations

import asyncio
from enum import Enum

import httpx
import openai
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior


class Rule(str, Enum):
    FLAW_RETRY = "flaw-retry"
    TRANSPORT_RETRY = "transport-retry"
    CONFIG_FATAL = "config-fatal"
    HALF_CLAIM = "half-claim"
    TIEBREAKER = "tiebreaker"


ERROR_POLICY: dict[str, Rule] = {
    # Flaws
    "no_queries": Rule.FLAW_RETRY,
    "no_results": Rule.FLAW_RETRY,
    "scorer_dropped_all": Rule.FLAW_RETRY,
    "model_error": Rule.FLAW_RETRY,
    "invalid_output": Rule.FLAW_RETRY,
    "insufficient_sources": Rule.FLAW_RETRY,
    "terminal_fetch_error": Rule.FLAW_RETRY,
    "fetch_failed": Rule.FLAW_RETRY,
    "invalid_source": Rule.FLAW_RETRY,
    "blocked_host": Rule.FLAW_RETRY,
    # ``http_{status}``: a terminal status is a flaw of the candidate list;
    # ``http_429`` is the one transport status (``rule_for``).
    "http_": Rule.FLAW_RETRY,
    # Transport
    "timeout": Rule.TRANSPORT_RETRY,
    "http_error": Rule.TRANSPORT_RETRY,
    "rate_limited": Rule.TRANSPORT_RETRY,
    "null_body": Rule.TRANSPORT_RETRY,
    "sources_unreachable": Rule.TRANSPORT_RETRY,
    "tavily_rate_limited": Rule.TRANSPORT_RETRY,
    "wayback_unavailable": Rule.TRANSPORT_RETRY,
    "edgar_rate_limited": Rule.TRANSPORT_RETRY,
    # Configuration
    "api_key_missing": Rule.CONFIG_FATAL,
    "all_blocked": Rule.CONFIG_FATAL,
    "edgar_ua_missing": Rule.CONFIG_FATAL,
    # dr recheck: a claim the batch cannot start, or a run that raised
    # outside the loop's steps; recorded by the command, never retried.
    "not_started": Rule.CONFIG_FATAL,
    "run_failed": Rule.CONFIG_FATAL,
    # Writer and disagreement
    "write_failed": Rule.HALF_CLAIM,
    "verdict_split": Rule.TIEBREAKER,
}

# The outcome a failed step records once its retries run out. A restater
# failure keeps the settled verdict (the claim is written without a
# restatement); a writer failure is a half-claim.
STEP_ON_EXHAUSTION: dict[str, str] = {
    "research": "abandoned",
    "ingest": "abandoned",
    "analyse": "abandoned",
    "evaluate": "abandoned",
    "tiebreak": "abandoned",
    "restate": "partial",
    "write": "half-claim",
}

# What ``resolve_model`` raises when a provider's key is not set.
_KEY_MISSING_MSG = "provider requires"
# What PydanticAI raises on an empty or null response body (Infomaniak).
_NULL_RESPONSE_MSG = "Invalid response from"


def rule_for(error_type: str) -> Rule:
    """The rule for a vocabulary literal; ``KeyError`` for one not in the table."""
    if error_type in ERROR_POLICY:
        return ERROR_POLICY[error_type]
    if error_type.startswith("http_") and error_type[5:].isdigit():
        return Rule.TRANSPORT_RETRY if error_type == "http_429" else ERROR_POLICY["http_"]
    raise KeyError(error_type)


def classify_exception(exc: BaseException) -> tuple[str, Rule]:
    """The vocabulary literal and rule for an exception raised inside a step."""
    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
        return "timeout", Rule.TRANSPORT_RETRY
    # An agent run never lets a raw openai error out: PydanticAI turns a 4xx or
    # 5xx reply into ModelHTTPError and a dropped connection into ModelAPIError.
    # The openai arms below catch only a direct client call.
    if isinstance(exc, ModelHTTPError):
        status = exc.status_code
        if status == 429:
            return "rate_limited", Rule.TRANSPORT_RETRY
        if status >= 500:
            return "http_error", Rule.TRANSPORT_RETRY
        if status in (401, 403):
            return "api_key_missing", Rule.CONFIG_FATAL
        return "model_error", Rule.FLAW_RETRY
    if isinstance(exc, ModelAPIError):
        return "http_error", Rule.TRANSPORT_RETRY
    if isinstance(exc, openai.RateLimitError):
        return "rate_limited", Rule.TRANSPORT_RETRY
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "api_key_missing", Rule.CONFIG_FATAL
    if isinstance(exc, (httpx.TransportError, openai.APIConnectionError, openai.InternalServerError)):
        return "http_error", Rule.TRANSPORT_RETRY
    if isinstance(exc, UnexpectedModelBehavior):
        if _NULL_RESPONSE_MSG in str(exc):
            return "null_body", Rule.TRANSPORT_RETRY
        return "invalid_output", Rule.FLAW_RETRY
    if isinstance(exc, RuntimeError) and _KEY_MISSING_MSG in str(exc):
        return "api_key_missing", Rule.CONFIG_FATAL
    return "model_error", Rule.FLAW_RETRY


def retry_after_s(exc: BaseException) -> float | None:
    """Seconds a rate-limited provider asked to wait, from its ``retry-after`` header."""
    # A ModelHTTPError carries no response; the openai error it wraps does.
    response = getattr(exc, "response", None) or getattr(exc.__cause__, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("retry-after")
        return float(value) if value else None
    except (TypeError, ValueError):
        return None
