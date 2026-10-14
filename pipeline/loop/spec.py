"""The claim run's input (``ClaimSpec``), configuration and result."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, computed_field

from analyst.agent import AnalystOutput
from auditor.models import ComparisonResult
from common.content_loader import resolve_repo_root
from common.logging_setup import new_run_id, run_id_var
from common.models import DEFAULT_MODEL, AgentName, BlockedReason, FailureInfo, SubQuestion
from common.templates import TemplateRecord
from common.timeouts import ingest_budget_with_wayback_s
from ingestor.models import SourceFile
from orchestrator.entity_resolution import ResolvedEntity


@dataclass
class ClaimSpec:
    """What one claim run checks: a sentence about an entity.

    ``statement`` is the sentence the Analyst assesses and the Evaluator
    grades (through ``_graded_statement`` while ``template`` is set).
    ``criteria_slug``, ``topics`` and ``grading_rule`` come from a criterion
    when the claim has one; ``grading_rule`` reaches both agents.
    ``template`` is the criterion record the statement was rendered from.
    """

    statement: str
    entity: ResolvedEntity
    criteria_slug: str | None = None
    topics: list[str] = field(default_factory=list)
    grading_rule: str | None = None
    template: TemplateRecord | None = None


# Timeout chain invariant: the ingestor agent wrapper (``ingest_timeout_s``)
# must cover HTTP fetch + optional 429 retry + optional wayback endpoints +
# LLM tool-dispatch turns. With ``skip_wayback=False`` the budget is derived
# from ``common.timeouts.ingest_budget_with_wayback_s`` so tuning the
# HTTP/wayback constants flows through automatically.
@dataclass
class VerifyConfig:
    model: str = DEFAULT_MODEL
    # Per-agent overrides; each falls back to ``model`` when None. Keeps the
    # single-model path unchanged while letting `dr` mix providers per agent.
    researcher_model: str | None = None
    analyst_model: str | None = None
    auditor_model: str | None = None
    ingestor_model: str | None = None
    # target successes to pass to the analyst
    max_sources: int = 8
    candidate_pool_size: int = 32
    # Interim default: wayback ON. The wayback-archive-job plan envisions
    # archival as a background job with skip_wayback=True in-pipeline, but
    # until that job lands we want primary sources behind paywalls/blocks
    # rescued via web.archive.org during the synchronous run.
    skip_wayback: bool = False
    # False when the run writes nothing (``dr claim-probe``): archive lookups
    # check TimeGate only and never ask Save Page Now to capture a page.
    allow_save: bool = True
    # Per-claim list of acquisition origins to attempt during research.
    # Default ['tavily', 'arxiv']; Brave remains available via search_backend
    # for per-query fallback. arXiv only fires when the claim's topics
    # intersect ACADEMIC_TOPICS (see _select_research_origins). Values mirror
    # the schema enum on audit.sources_consulted[].acquisition.origin.
    research_origins: list[str] = field(default_factory=lambda: ["tavily", "arxiv"])
    # Search backend used by the decomposed researcher's `execute_searches`
    # step. Today: 'tavily' (default) or 'brave'. Read once from
    # RESEARCH_SEARCH_BACKEND at construction time; tests can override by
    # passing `search_backend=...` directly. Unknown values fall back to
    # 'brave' with a warning logged in `execute_searches`.
    search_backend: str = field(
        default_factory=lambda: os.environ.get("RESEARCH_SEARCH_BACKEND", "tavily")
    )
    repo_root: str = ""
    # ``ingest_timeout_s`` is ``None`` when the caller hasn't set it, so
    # ``__post_init__`` can pick a default based on ``skip_wayback``. Callers
    # that pass any float (including 60.0) keep that value verbatim.
    ingest_timeout_s: float | None = None
    research_timeout_s: float = 120.0
    analyst_timeout_s: float = 120.0
    auditor_timeout_s: float = 120.0
    force_overwrite: bool = False
    # Effort lever for decomposed researcher: more queries = wider net.
    max_initial_queries: int = 7
    # Integer cap for the shared asyncio.Semaphore created at each call site.
    # Never store the Semaphore itself here — it is loop-bound.
    llm_concurrency: int = 8
    # When True, verify_claim emits stderr progress lines at step boundaries
    # via progress(). Off for onboard (which has its own per-claim progress);
    # on for single-claim CLI paths (claim-refresh, claim-probe) where the
    # run otherwise looks hung.
    show_progress: bool = False
    # Correlates every log record (and future token-usage record) emitted
    # during one top-level pipeline invocation. Inherits a CLI-bound id if
    # set; onboard's per-template loop overrides via dataclasses.replace.
    run_id: str = field(default_factory=lambda: run_id_var.get() or new_run_id())

    def __post_init__(self) -> None:
        if self.ingest_timeout_s is None:
            self.ingest_timeout_s = (
                ingest_budget_with_wayback_s() if not self.skip_wayback else 60.0
            )
        if self.candidate_pool_size < self.max_sources:
            raise ValueError(
                f"candidate_pool_size ({self.candidate_pool_size}) must be >= max_sources ({self.max_sources})"
            )

    def model_for(self, agent: AgentName) -> str:
        """Resolve the model spec for a given agent, falling back to ``model``."""
        return getattr(self, f"{agent}_model") or self.model


def _cfg_repo_root(cfg: VerifyConfig) -> Path:
    return Path(cfg.repo_root) if cfg.repo_root else resolve_repo_root()


class VerificationResult(BaseModel):
    """Full output of an end-to-end claim verification."""

    entity: str
    claim_text: str
    urls_found: list[str]
    urls_ingested: list[str]
    urls_failed: list[str]
    sources: list[dict]
    analyst_output: AnalystOutput | None = None
    consistency: ComparisonResult | None = None
    errors: list[str] = field(default_factory=list)
    # Set when the Orchestrator halts the claim post-ingest because fewer
    # than two usable sources were obtained. Callers that persist claim
    # files (research_claim, onboard_entity) inspect this to write a
    # blocked claim file instead of skipping.
    blocked_reason: BlockedReason | None = None
    # Repo-relative path of the written claim file (e.g.
    # "research/claims/microsoft/renewable-energy-pledges.md"). Set by
    # research_claim after the claim file lands; left None for in-memory
    # verify_claim runs that don't persist.
    claim_path: str | None = None
    source_files: list[tuple[str, SourceFile]] = Field(default_factory=list, exclude=True)
    # Cache-hit sources reused via URL dedup; without these the audit sidecar's
    # sources_consulted is empty when every URL was already on disk.
    cached_sources: list[tuple[str, str, dict]] = Field(default_factory=list, exclude=True)
    # Researcher-step trace: planner queries+rationale and scorer rationale.
    # Persisted to the audit sidecar so reviewers can see how the source set
    # was assembled.
    research_trace: dict | None = None
    # Sub-question decomposition the planner emitted for this claim.
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    # Map SubQuestion.id -> list of source_ids that addressed it after ingest
    # (sources whose ScoredCandidate.addresses included this id AND that
    # ingested successfully). An empty list signals an uncovered axis.
    sub_question_coverage: dict[str, list[str]] = Field(default_factory=dict)
    # Per-sub-question queries from the planner. Used to render the audit
    # sidecar's `sub_questions:` block; not part of the on-disk claim file.
    queries_by_sub_question: dict[str, list[str]] = Field(default_factory=dict, exclude=True)
    # First fatal agent failure observed during the run, if any. Persisted to
    # the audit sidecar (pipeline_run.failure) so blocked runs can be triaged
    # without grepping logs.
    failure: FailureInfo | None = Field(default=None, exclude=True)
    # Requested URL -> URL its live fetch ended on, for fresh sources.
    final_urls: dict[str, str] = Field(default_factory=dict, exclude=True)
    # Requested URL -> archive lookup record, for fresh sources.
    archive: dict[str, dict] = Field(default_factory=dict, exclude=True)
    # Ingested URLs (cached or fresh) of sources the analyst did not cite;
    # kept out of the claim's ``sources:`` and not written. Keyed by URL so
    # a slug renamed at write time cannot desync it.
    uncited_urls: set[str] = Field(default_factory=set, exclude=True)
    # Requested URL dropped because it reached a page already kept -> the
    # kept URL. The writer lists ``sources:`` in the researcher's URL order
    # through it.
    url_aliases: dict[str, str] = Field(default_factory=dict, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @computed_field
    @property
    def cached_source_ids(self) -> list[str]:
        return [sid for _url, sid, _sd in self.cached_sources]

    def sources_consulted(self) -> list[dict]:
        """The audit sidecar's ``sources_consulted`` block for this run."""
        from orchestrator.persistence import _build_sources_consulted

        return _build_sources_consulted(
            self.source_files, cached_sources=self.cached_sources, archive=self.archive
        )
