"""Shared enums mirroring the Zod schemas in src/content.config.ts.

Also exposes `resolve_model` for mapping provider-prefixed spec strings to
PydanticAI Model instances when needed.
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pydantic_ai.models import Model

logger = logging.getLogger(__name__)


class SubQuestion(BaseModel):
    id: str = Field(
        pattern=r"^sq\d+$",
        description="Stable id within a claim. Format: 'sq1', 'sq2', ... (sequential within a ResearchPlan).",
    )
    question: str = Field(description="An independently answerable factual question.")
    rationale: str = Field(
        description="One-sentence justification for why this sub-question belongs in the decomposition; surfaced in the audit sidecar.",
    )


async def _log_infomaniak_response(response: httpx.Response) -> None:
    """Log Infomaniak response bodies for diagnostics.

    Only safe for non-streaming completions; aread() buffers before the SDK reads.
    Null/empty bodies log at WARNING regardless of log level so gateway blips
    are always visible. Full bodies log at DEBUG only.
    """
    req_id = response.headers.get("x-request-id", "-")
    try:
        await response.aread()
        body = response.content.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning(
            "infomaniak raw response [%s] status=%d body=<aread error: %s>",
            req_id,
            response.status_code,
            exc,
        )
        return
    if not body or body.strip() in ("null", "{}"):
        logger.warning(
            "infomaniak raw response [%s] status=%d null/empty body",
            req_id,
            response.status_code,
        )
    elif logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "infomaniak raw response [%s] status=%d body=%s",
            req_id,
            response.status_code,
            body,
        )


AgentName = Literal["researcher", "analyst", "auditor", "ingestor"]
# Canonical iteration order for the four agents that participate in a
# single claim verification. Used by VerifyConfig.model_for and CLI
# helpers that enumerate per-agent overrides; adding an agent means
# editing this tuple and the matching VerifyConfig fields.
AGENT_NAMES: tuple[AgentName, ...] = ("researcher", "analyst", "auditor", "ingestor")


class Verdict(str, Enum):
    TRUE = "true"
    MOSTLY_TRUE = "mostly-true"
    MIXED = "mixed"
    MOSTLY_FALSE = "mostly-false"
    FALSE = "false"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not-applicable"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ClaimStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class Phase(str, Enum):
    RESEARCHING = "researching"
    INGESTING = "ingesting"
    ANALYZING = "analyzing"
    EVALUATING = "evaluating"


class BlockedReason(str, Enum):
    INSUFFICIENT_SOURCES = "insufficient_sources"
    TERMINAL_FETCH_ERROR = "terminal_fetch_error"
    ANALYST_ERROR = "analyst_error"


class Category(str, Enum):
    AI_SAFETY = "ai-safety"
    ENVIRONMENTAL_IMPACT = "environmental-impact"
    PRODUCT_COMPARISON = "product-comparison"
    CONSUMER_GUIDE = "consumer-guide"
    AI_LITERACY = "ai-literacy"
    DATA_PRIVACY = "data-privacy"
    INDUSTRY_ANALYSIS = "industry-analysis"
    REGULATION_POLICY = "regulation-policy"


# Topics that activate academic-API dispatch (Path 2 selector + dr stats
# academic-coverage aggregate). Single source of truth so a Category
# rename doesn't drift the two consumers out of sync.
ACADEMIC_TOPICS: frozenset[str] = frozenset({
    Category.AI_SAFETY.value,
    Category.ENVIRONMENTAL_IMPACT.value,
    Category.INDUSTRY_ANALYSIS.value,
})

# Origins counted as academic by the selector and the coverage aggregate.
# Tier 2 will extend with ``s2`` and ``openalex``.
ACADEMIC_ORIGINS: frozenset[str] = frozenset({"arxiv"})


class SourceKind(str, Enum):
    REPORT = "report"
    ARTICLE = "article"
    DOCUMENTATION = "documentation"
    DATASET = "dataset"
    BLOG = "blog"
    VIDEO = "video"
    INDEX = "index"
    PAPER = "paper"


class Independence(str, Enum):
    """Source-pool independence signal; mirrors the Zod enum in content.config.ts.

    See docs/architecture/source-quality.md for derivation rules and the
    restatement failure mode.
    """

    FIRST_PARTY = "first-party"
    INDEPENDENT = "independent"
    UNKNOWN = "unknown"


class VerificationLevel(str, Enum):
    """Per-claim source-pool diversity signal.

    Derived from the `independence` + `kind` of sources on a claim.
    See docs/architecture/source-quality.md.
    """

    CLAIMED = "claimed"
    SELF_REPORTED = "self-reported"
    PARTIALLY_VERIFIED = "partially-verified"
    INDEPENDENTLY_VERIFIED = "independently-verified"
    MULTIPLY_VERIFIED = "multiply-verified"


class EntityType(str, Enum):
    COMPANY = "company"
    PRODUCT = "product"
    SUBJECT = "subject"


class VerdictSeverity(str, Enum):
    MATCH = "match"
    ADJACENT = "adjacent"
    MAJOR = "major"
    OPPOSITE = "opposite"


DEFAULT_MODEL = "infomaniak:openai/gpt-oss-120b"


FailureStep = Literal["research", "ingest", "analyst", "auditor"]


@dataclass
class FailureInfo:
    """Structured description of the first fatal error in a pipeline run.

    Populated when an agent call returns None (timeout, null body past
    retries, schema/validation error). Persisted under ``pipeline_run.failure``
    in the audit sidecar so triage can happen without log access.
    """

    step: FailureStep
    agent: str | None
    model: str | None
    error_class: str
    error_message: str
    timeout_s: float | None = None
    traceback_head: str | None = None


def _model_needs_reasoning_strip(model_id: str) -> bool:
    """True for models that reject ``reasoning_content`` on input messages.

    Mistral-Small-3.2 emits ``reasoning_content`` on assistant turns and 400s
    when it appears in conversation history. By default PydanticAI's
    auto-detect path puts the field back on outgoing messages, which breaks
    multi-turn tool loops on Infomaniak. Forcing
    ``openai_chat_send_back_thinking_parts=False`` drops thinking parts from
    history entirely, which is the smallest behavior change that keeps the
    tool loop alive.

    Keyed on the lowercased model_id substring so future Mistral tiers and
    HF-style slugs stay covered without a registry rewrite.
    """
    return "mistral" in model_id.lower()


def _model_needs_native_output(model_id: str) -> bool:
    """True for Infomaniak-hosted models that don't support tool calling at the gateway.

    These models fail T3/T4 (tool definition / tool call) but pass T2b
    (response_format: json_schema). PydanticAI's default structured-output
    mode uses tool calling; switching to 'native' tells it to use
    response_format: json_schema instead.

    gemma3n (google/gemma-3n-E4B-it): tool use not enabled at Infomaniak gateway.
    gpt-oss-120b (openai/gpt-oss-120b): returns markdown prose instead of JSON
      when using tool-calling mode; native json_schema mode resolves this.
    """
    lower = model_id.lower()
    return "gemma3n" in lower or "gpt-oss-120b" in lower


@lru_cache(maxsize=None)
def resolve_model(spec: str) -> "Model | str":
    """Map a model spec string to a PydanticAI Model or pass it through.

    `infomaniak:<model_id>` builds an OpenAI-compatible client against the
    Infomaniak gateway. Anything else (including `anthropic:...` and bare
    model names) is returned unchanged so PydanticAI's native string
    handling continues to work.

    For Mistral variants on Infomaniak, applies a thinking-parts scrubber
    via the model profile (see ``_model_needs_reasoning_strip``).

    Cached per-spec so a process reuses one provider/httpx client across
    overrides; `Agent.override` is a sync context manager that does not
    enter the provider, so a fresh `OpenAIProvider` per call would leak
    its underlying `httpx.AsyncClient`. Call `resolve_model.cache_clear()`
    if env vars change at runtime (e.g. between tests).

    A spec containing ``||`` is split into legs (trimmed) and wrapped in
    PydanticAI's ``FallbackModel``: ``a||b`` tries ``a`` first and falls
    back to ``b`` on ``ModelAPIError`` (PydanticAI's default catch
    surface). The ``||`` branch must run before the prefix-startswith
    branches so a chained spec is not mistakenly treated as a bare model
    id with the literal "||" in the name.
    """
    if "||" in spec:
        from pydantic_ai.models.fallback import FallbackModel

        legs = [resolve_model(leg.strip()) for leg in spec.split("||")]
        return FallbackModel(*legs)
    if spec.startswith("greenpt:"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        model_id = spec.split(":", 1)[1]
        try:
            api_key = os.environ["GREENPT_API_KEY"]
        except KeyError as e:
            raise RuntimeError(f"GreenPT provider requires {e.args[0]}") from e
        provider = OpenAIProvider(base_url="https://api.greenpt.ai/v1", api_key=api_key)
        return OpenAIChatModel(model_id, provider=provider)
    if spec.startswith("infomaniak:"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.profiles.openai import OpenAIModelProfile
        from pydantic_ai.providers.openai import OpenAIProvider

        model_id = spec.split(":", 1)[1]
        try:
            pid = os.environ["INFOMANIAK_PRODUCT_ID"]
            api_key = os.environ["INFOMANIAK_API_KEY"]
        except KeyError as e:
            # Translate KeyError to RuntimeError so the CLI surfaces a
            # readable message rather than a bare missing-env-var traceback
            # from deep in the agent call stack.
            raise RuntimeError(f"Infomaniak provider requires {e.args[0]}") from e
        ver = os.environ.get("INFOMANIAK_API_VERSION", "2")
        base = f"https://api.infomaniak.com/{ver}/ai/{pid}/openai/v1"
        provider = OpenAIProvider(
            base_url=base,
            api_key=api_key,
            http_client=httpx.AsyncClient(event_hooks={"response": [_log_infomaniak_response]}),
        )
        profile_kwargs: dict = {}
        if _model_needs_reasoning_strip(model_id):
            profile_kwargs["openai_chat_send_back_thinking_parts"] = False
        if _model_needs_native_output(model_id):
            profile_kwargs["default_structured_output_mode"] = "native"
            profile_kwargs["supports_json_schema_output"] = True
        profile: "OpenAIModelProfile | None" = OpenAIModelProfile(**profile_kwargs) if profile_kwargs else None
        return OpenAIChatModel(model_id, provider=provider, profile=profile)
    return spec
