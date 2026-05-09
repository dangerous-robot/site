"""Analyst agent: assesses evidence and renders verdicts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from common.instructions import common, load_instructions
from common.models import Category, Confidence, EntityType, Independence, SubQuestion, Verdict, VerificationLevel
from common.utils import slugify

if TYPE_CHECKING:
    from orchestrator.entity_resolution import ResolvedEntity


_LIST_MARKER_RE = re.compile(r"^(?:[-*+]\s|\d+\.\s)")
_FENCE_RE = re.compile(r"^(?:```|~~~)")


def _surround_lists_with_blanks(text: str) -> str:
    """Insert blank lines around contiguous list blocks (markdownlint MD032).

    The analyst instructions already require this, but the LLM occasionally
    forgets and the result fails `markdownlint`. Indented list-item
    continuations and fenced code blocks (where `- ` is content, not a
    marker) are passed through unchanged.
    """
    out: list[str] = []
    in_list = False
    in_fence = False
    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        is_marker = bool(_LIST_MARKER_RE.match(line))
        is_indented = bool(line) and line[0] in (" ", "\t")

        if is_marker:
            if not in_list and out and out[-1].strip():
                out.append("")
            in_list = True
        elif in_list and not is_indented:
            if line.strip():
                out.append("")
            in_list = False

        out.append(line)
    return "\n".join(out)


_DANGLING_TRAILING_WORDS = frozenset({
    "a", "an", "the",
    "of", "for", "to", "in", "on", "at", "with", "by", "from", "as",
    "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but",
})


def _reject_if_truncated(value: str, *, require_sentence_end: bool) -> None:
    """Heuristically reject values that look clipped at a length limit.

    Pydantic's `max_length` is a hard cap, but the analyst LLM has been
    observed to fill the cap with content and clip mid-phrase. These checks
    surface common truncation shapes so PydanticAI can ask for a retry.
    Pydantic wraps the raised `ValueError` with the offending field path.
    """
    s = value.strip()
    if not s:
        return

    if s.count("(") != s.count(")"):
        raise ValueError("unbalanced parentheses (likely truncated)")
    if s.count("[") != s.count("]"):
        raise ValueError("unbalanced brackets (likely truncated)")

    last = s[-1]
    if last in "(,;:":
        raise ValueError(f"ends with {last!r} (likely truncated)")
    if last in ("'", '"'):
        # Possessive `'s` makes parity alone unreliable; a trailing quote
        # after a space (e.g. "...Impact: A '") is the surer signal.
        if len(s) >= 2 and s[-2] == " ":
            raise ValueError(f"ends with standalone {last!r} (likely truncated)")
        if s.count(last) % 2 != 0:
            raise ValueError(f"ends with unpaired {last!r} (likely truncated)")

    last_token = s.rsplit(maxsplit=1)[-1].rstrip(".,;:!?\"')]")
    if last_token.lower() in _DANGLING_TRAILING_WORDS:
        raise ValueError(f"ends with dangling word {last_token!r} (likely truncated)")

    if require_sentence_end and last not in ".!?":
        raise ValueError("must end with '.', '!', or '?' (or omit field)")


class EntityResolution(BaseModel):
    """Entity identified from the claim context."""

    entity_name: str = Field(description="Primary entity name (e.g. 'Apple', 'OpenAI')")
    entity_type: EntityType = Field(description="One of: company, product, topic")
    entity_description: str = Field(description="One-sentence description of the entity")
    aliases: list[str] = Field(
        default_factory=list,
        description="Common alternate names, abbreviations, or product lines (e.g. ['Claude'] for Anthropic). Omit if none apply.",
    )


class SourceOverride(BaseModel):
    """Per-claim override of a source-level field, recorded on the claim.

    See docs/architecture/source-quality.md § Source overrides on claims.
    """

    source: str = Field(description='Source id like "2025/some-slug" — must reference one of the claim\'s sources.')
    independence: Independence | None = Field(
        default=None,
        description=(
            "Override value for `independence` on this source for this claim only. "
            "Set to `first-party` when a source classified `independent` is actually "
            "restating a primary disclosure without conducting original analysis."
        ),
    )
    reason: str = Field(
        description="One short sentence explaining why the override was applied (cited in the architecture doc).",
        max_length=300,
    )


class VerdictAssessment(BaseModel):
    """Verdict and narrative produced from source analysis."""

    title: str = Field(description="Concise claim title (e.g. 'Ecosia runs AI chat on non-renewable infrastructure')")
    verdict: Verdict
    confidence: Confidence
    narrative: str = Field(description="2-5 sentence assessment. Cite sources by title. Factual, not evaluative.")
    topics: list[Category] = Field(
        min_length=1,
        max_length=3,
        description="One to three topic slugs that classify the claim. Mirror the source criterion's topics by default.",
    )
    verification_level: VerificationLevel = Field(
        description=(
            "Source-pool diversity signal, derived from the effective `independence` "
            "and `kind` of sources on this claim (after `source_overrides` are "
            "applied). See docs/architecture/source-quality.md § Verification scale."
        ),
    )
    cap_rationale: str | None = Field(
        default=None,
        description=(
            "Required when `verification_level` is `claimed` or `self-reported`. "
            "One sentence matching one of the templates in "
            "docs/architecture/source-quality.md § Rationale templates. "
            "Surfaced verbatim under the verdict on the claim page."
        ),
        max_length=400,
    )
    source_overrides: list[SourceOverride] | None = Field(
        default=None,
        description=(
            "Optional per-claim overrides of source-level fields. Use when a "
            "source classified `independent` is actually restating a primary "
            "disclosure for this claim. Omit when no overrides apply."
        ),
    )
    seo_title: str = Field(
        description=(
            "Short page title for search results. Always provide; "
            "max 42 chars; must be a complete phrase that ends on a word "
            "boundary (no mid-word truncation). When `title` already fits in "
            "42 chars it can be copied verbatim; longer titles must be "
            "compressed while preserving the core finding."
        ),
        min_length=1,
        max_length=42,
    )
    takeaway: str | None = Field(
        default=None,
        description=(
            "One sentence a reader would want to repeat (max 200 chars). Only "
            "include when the finding is striking, counterintuitive, or unusually "
            "significant — e.g., an industry-wide failure or direct contradiction "
            "of public claims. Do not paraphrase the title. Default: omit."
        ),
        max_length=200,
    )

    @field_validator("narrative")
    @classmethod
    def _normalize_narrative_lists(cls, v: str) -> str:
        return _surround_lists_with_blanks(v)

    @field_validator("seo_title")
    @classmethod
    def _seo_title_complete_phrase(cls, v: str) -> str:
        _reject_if_truncated(v, require_sentence_end=False)
        return v

    @field_validator("takeaway")
    @classmethod
    def _takeaway_complete_sentence(cls, v: str | None) -> str | None:
        if v is None:
            return v
        _reject_if_truncated(v, require_sentence_end=True)
        return v


class AnalystOutput(BaseModel):
    """Full output of the analyst agent."""

    entity: EntityResolution
    verdict: VerdictAssessment


_INSTRUCTIONS = load_instructions(Path(__file__).resolve().parent, common("verdict-scale.md"))

analyst_agent = Agent(
    "test",
    output_type=AnalystOutput,
    system_prompt=_INSTRUCTIONS,
    retries=2,
)

verdict_only_agent = Agent(
    "test",
    output_type=VerdictAssessment,
    system_prompt=_INSTRUCTIONS,
    retries=2,
)


def build_analyst_prompt(
    entity_name: str | None,
    claim_text: str,
    sources: list[dict],
    resolved_entity: "ResolvedEntity | None" = None,
    sub_questions: list[SubQuestion] | None = None,
) -> str:
    """Build the user prompt for the analyst agent."""
    parts: list[str] = []

    if resolved_entity is not None:
        aliases_str = ", ".join(resolved_entity.aliases) if resolved_entity.aliases else "none"
        parent_str = resolved_entity.parent_company or "none"
        parts.append("## Entity (pre-resolved — do not infer)")
        parts.append("")
        parts.append(f"Name: {resolved_entity.entity_name}")
        parts.append(f"Type: {resolved_entity.entity_type.value}")
        parts.append(f"Description: {resolved_entity.entity_description}")
        parts.append(f"Aliases: {aliases_str}")
        if resolved_entity.legal_name:
            parts.append(f"Legal name: {resolved_entity.legal_name}")
        if resolved_entity.founded is not None:
            parts.append(f"Founded: {resolved_entity.founded}")
        parts.append(f"Parent company: {parent_str}")
        if resolved_entity.verification_status:
            parts.append(f"Verification: {resolved_entity.verification_status}")
        parts.append("")
        parts.append("The entity above is authoritative. Produce only a VerdictAssessment.")
    elif entity_name:
        parts.append(f"## Entity: {entity_name}")

    parts.append("")
    parts.append(f"## Claim to evaluate: {claim_text}")
    parts.append("")

    if sub_questions:
        parts.append("## Sub-questions")
        for sq in sub_questions:
            parts.append(f"- {sq.id}: {sq.question}")
            parts.append(f"  Rationale: {sq.rationale}")
        parts.append("")

    if sources:
        parts.append("## Source materials")
        for i, src in enumerate(sources, 1):
            parts.append(f"### Source {i}: {src['title']}")
            if src.get("source_id"):
                parts.append(f"Source id: {src['source_id']}")
            parts.append(f"Publisher: {src['publisher']}")
            if src.get("kind"):
                parts.append(f"Kind: {src['kind']}")
            if src.get("independence"):
                parts.append(f"Independence: {src['independence']}")
            if src.get("addresses") is not None:
                addresses = ", ".join(src["addresses"]) if src["addresses"] else "(none)"
                parts.append(f"Addresses: {addresses}")
            parts.append(f"Summary: {src['summary']}")
            if src.get("key_quotes"):
                parts.append("Key quotes:")
                for q in src["key_quotes"]:
                    parts.append(f'  - "{q}"')
            if src.get("body"):
                parts.append(f"Full text:\n{src['body'].strip()}")
            parts.append("")
    else:
        parts.append("## Source materials")
        parts.append("No sources were found.")
        parts.append("")

    parts.append(
        "Based on the sources above, draft a structured claim assessment."
    )

    return "\n".join(parts)
