"""Factory for building ClaimBundle inputs to the auditor."""

from __future__ import annotations

from common.models import Category

from .models import ClaimBundle, EntityContext, SourceContext


def build_bundle(
    entity_name: str,
    entity_type: str,
    description: str,
    category: Category,
    narrative: str,
    sources: list[dict],
) -> ClaimBundle:
    """Build a ClaimBundle from primitive values.

    The orchestrator passes primitives; the auditor owns the mapping to its internal types.
    """
    entity = EntityContext(
        name=entity_name,
        type=entity_type,
        description=description,
    )

    source_contexts = [
        SourceContext(
            id=src["slug"],
            title=src["title"],
            publisher=src["publisher"],
            summary=src["summary"],
            key_quotes=src.get("key_quotes", []),
            body=src.get("body", ""),
        )
        for src in sources
    ]

    return ClaimBundle(
        claim_id=f"verify/{entity_name.lower().replace(' ', '-')}",
        entity=entity,
        category=category,
        narrative=narrative,
        sources=source_contexts,
    )
