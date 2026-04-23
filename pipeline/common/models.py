"""Shared enums mirroring the Zod schemas in src/content.config.ts."""

from enum import Enum


class Verdict(str, Enum):
    TRUE = "true"
    MOSTLY_TRUE = "mostly-true"
    MIXED = "mixed"
    MOSTLY_FALSE = "mostly-false"
    FALSE = "false"
    UNVERIFIED = "unverified"


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


class VerdictSeverity(str, Enum):
    MATCH = "match"
    ADJACENT = "adjacent"
    MAJOR = "major"
    OPPOSITE = "opposite"


DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"
