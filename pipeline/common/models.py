"""Shared enums mirroring the Zod schemas in src/content.config.ts.

Also exposes `resolve_model` for mapping provider-prefixed spec strings to
PydanticAI Model instances when needed.
"""

import os
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai.models import Model


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


class Category(str, Enum):
    AI_SAFETY = "ai-safety"
    ENVIRONMENTAL_IMPACT = "environmental-impact"
    PRODUCT_COMPARISON = "product-comparison"
    CONSUMER_GUIDE = "consumer-guide"
    AI_LITERACY = "ai-literacy"
    DATA_PRIVACY = "data-privacy"
    INDUSTRY_ANALYSIS = "industry-analysis"
    REGULATION_POLICY = "regulation-policy"


class SourceKind(str, Enum):
    REPORT = "report"
    ARTICLE = "article"
    DOCUMENTATION = "documentation"
    DATASET = "dataset"
    BLOG = "blog"
    VIDEO = "video"
    INDEX = "index"


class EntityType(str, Enum):
    COMPANY = "company"
    PRODUCT = "product"
    TOPIC = "topic"
    SECTOR = "sector"


class VerdictSeverity(str, Enum):
    MATCH = "match"
    ADJACENT = "adjacent"
    MAJOR = "major"
    OPPOSITE = "opposite"


DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"


@lru_cache(maxsize=None)
def resolve_model(spec: str) -> "Model | str":
    """Map a model spec string to a PydanticAI Model or pass it through.

    `infomaniak:<model_id>` builds an OpenAI-compatible client against the
    Infomaniak gateway. Anything else (including `anthropic:...` and bare
    model names) is returned unchanged so PydanticAI's native string
    handling continues to work.

    Cached per-spec so a process reuses one provider/httpx client across
    overrides; `Agent.override` is a sync context manager that does not
    enter the provider, so a fresh `OpenAIProvider` per call would leak
    its underlying `httpx.AsyncClient`. Call `resolve_model.cache_clear()`
    if env vars change at runtime (e.g. between tests).
    """
    if spec.startswith("infomaniak:"):
        from pydantic_ai.models.openai import OpenAIModel
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
        return OpenAIModel(model_id, provider=OpenAIProvider(base_url=base, api_key=api_key))
    return spec
