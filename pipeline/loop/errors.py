"""Typed errors from the steps of a claim run, and the vocabulary every failure uses."""

from __future__ import annotations


class StepError:
    """Typed error from a pipeline step.

    The ``error_type`` attribute is intentionally a free-form ``str``, not a
    closed enum or ``Literal``. This is a deliberate design choice: the field
    is a coarse classifier for log filtering and the error policy, and
    new categories should be cheap to add. The trade-off is drift -- so the
    smoke test in ``pipeline/tests/test_step_error_vocab.py`` scans
    production code and fails if a new literal lands without an entry below.

    Currently in-use values
    -----------------------

    Fetch / network (``step="ingest"``):
        - ``timeout``                  -- ingest deadline exceeded
        - ``blocked_host``             -- URL host on the blocklist
        - ``all_blocked``              -- every candidate URL was blocked
        - ``http_{status}``            -- terminal HTTP status (format pattern,
          not a literal; e.g. ``http_404``, ``http_410``)
        - ``http_error``               -- non-terminal HTTP failure
          (exception class name contains ``"HTTP"``)
        - ``fetch_failed``             -- the ingest model returned a source
          but no ``web_fetch`` call returned page text
        - ``invalid_source``           -- the ingested source failed
          ``validate_source_file`` (slug, year, archived_url domain)

    Model (``step="research"`` or ``step="ingest"``):
        - ``model_error``              -- agent run raised an unexpected exception
        - ``api_key_missing``          -- model invocation failed because an
          API key wasn't configured

    Researcher (``step="research"``):
        - ``no_queries``               -- query planner returned an empty plan
        - ``no_results``               -- search returned zero candidates
        - ``scorer_dropped_all``       -- URL scorer rejected every candidate

    Run rules (step-level; ``pipeline/loop/policy.py`` maps each to a rule)
    ------------------------------------------------------------------------
    A whole step's failure, recorded on the run's finding rather than per URL:

        - ``insufficient_sources``     -- fewer than four usable sources after ingest
        - ``sources_unreachable``      -- below four, and every failed page failed in transit
        - ``terminal_fetch_error``     -- below four, and every failed page refused (``http_{status}``)
        - ``rate_limited``             -- a provider answered with a rate limit
        - ``null_body``                -- a provider answered with an empty body
        - ``invalid_output``           -- an agent's output failed validation after its own retries
        - ``write_failed``             -- the writer failed part-way (a half-claim)
        - ``verdict_split``            -- the analyst and the Evaluator disagreed; the tie-breaker settled it
        - ``not_started``              -- ``dr recheck --due`` could not start a claim's run
          (its entity file does not load, or the claim is not where its entity writes)
        - ``run_failed``               -- a ``dr recheck`` or ``dr findings --replay`` run raised
          outside the loop's steps

    Archive, search and SEC EDGAR literals
    --------------------------------------
    No code emits the two EDGAR literals yet; they are listed so the error
    policy already has a rule for each:

        - ``wayback_unavailable``      -- archive.org TimeGate API down
        - ``edgar_ua_missing``         -- SEC EDGAR User-Agent header
          not configured
        - ``edgar_rate_limited``       -- SEC EDGAR rate limit hit
        - ``tavily_rate_limited``      -- search backend: Tavily rate limit hit

    What does NOT belong on this channel
    ------------------------------------
    Two adjacent concepts ride on different channels and must not leak here:

        - **Tool fired but found nothing** (e.g. an arXiv query returning zero
          hits) is a normal outcome, not an error. It rides on
          ``research_trace["tool_outcomes"]`` -- do not add literals like
          ``arxiv_no_results`` to ``StepError``.
        - **Per-URL acquisition outcomes** (``recovered``, ``matched``, etc.)
          live on ``sources_consulted[].acquisition.outcome`` in the audit
          trail, not on the error stream.

    Keeping the error channel narrow keeps log dashboards and the findings
    file readable; the trace and audit channels carry the per-tool / per-URL
    detail.
    """

    def __init__(
        self,
        step: str,
        error_type: str,
        message: str,
        url: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.step = step
        self.url = url
        self.error_type = error_type
        self.message = message
        self.retryable = retryable

    def __repr__(self) -> str:
        loc = f" url={self.url}" if self.url else ""
        return f"StepError(step={self.step!r}{loc}, type={self.error_type!r})"
