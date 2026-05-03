"""File I/O for persisting research artifacts to disk."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import yaml

from auditor.models import ComparisonResult
from common.frontmatter import FlowList, parse_frontmatter, serialize_frontmatter
from common.models import (
    BlockedReason,
    Category,
    Confidence,
    EntityType,
    Verdict,
)
from common.source_classification import classify_source_type
from common.utils import slugify
from ingestor.models import SourceFile

logger = logging.getLogger(__name__)


_ENTITY_TYPE_DIR = {
    EntityType.COMPANY: "companies",
    EntityType.PRODUCT: "products",
    EntityType.TOPIC: "topics",
    EntityType.SECTOR: "sectors",
}


def _entity_frontmatter(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    website: str | None = None,
    aliases: list[str] | None = None,
    status: str | None = None,
) -> dict:
    # Ensure description is never empty -- the linter rejects blank required strings.
    description = entity_description.strip() or f"{entity_name} ({entity_type.value})."
    return {
        "name": entity_name,
        "type": entity_type,
        "website": website,
        "aliases": aliases or None,
        "description": description,
        "status": status,
    }


def _write_source_files(
    source_files: list[tuple[str, SourceFile]],
    repo_root: Path,
) -> list[str]:
    """Write ingested source files to disk. Returns list of source IDs."""
    source_ids: list[str] = []

    for _url, sf in source_files:
        target_dir = repo_root / "research" / "sources" / str(sf.year)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{sf.slug}.md"

        fm_dict = sf.frontmatter.model_dump(mode="python")
        fm_dict["source_type"] = classify_source_type(
            sf.frontmatter.publisher, sf.frontmatter.kind.value
        )
        markdown = serialize_frontmatter(fm_dict, sf.body.rstrip() + "\n")

        try:
            with target_path.open("x", encoding="utf-8") as f:
                f.write(markdown)
            logger.info("Wrote source: %s", target_path)
        except FileExistsError:
            logger.info("Source already exists, skipping: %s", target_path)

        source_ids.append(f"{sf.year}/{sf.slug}")

    return source_ids


def _write_entity_file(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    repo_root: Path,
    website: str | None = None,
    aliases: list[str] | None = None,
) -> str:
    """Write entity file if it doesn't exist. Returns entity path like 'companies/slug'."""
    entity_slug = slugify(entity_name)
    type_dir = _ENTITY_TYPE_DIR.get(entity_type, f"{entity_type.value}s")

    entity_dir = repo_root / "research" / "entities" / type_dir
    entity_dir.mkdir(parents=True, exist_ok=True)
    entity_path = entity_dir / f"{entity_slug}.md"
    entity_ref = f"{type_dir}/{entity_slug}"

    if entity_path.exists():
        logger.info("Entity already exists: %s", entity_path)
        return entity_ref

    fm = _entity_frontmatter(entity_name, entity_type, entity_description, website, aliases)
    entity_path.write_text(serialize_frontmatter(fm, ""), encoding="utf-8")
    logger.info("Wrote entity: %s", entity_path)
    return entity_ref


def _claim_dir_for(entity_ref: str | None, entity_name: str, repo_root: Path) -> Path:
    """Return the claims directory for an entity.

    Companies and products use a flat layout (research/claims/<slug>/) for
    backward compat; all other types (sectors, …) include the type prefix.
    """
    if entity_ref and "/" in entity_ref:
        ref_parts = entity_ref.split("/")
        slug = ref_parts[-1]
        if ref_parts[0] in ("companies", "products") and len(ref_parts) == 2:
            return repo_root / "research" / "claims" / slug
        return repo_root / "research" / "claims" / Path(*ref_parts)
    return repo_root / "research" / "claims" / slugify(entity_name)


def _write_claim_file(
    title: str,
    entity_name: str,
    entity_ref: str,
    topics: list[Category],
    verdict: Verdict,
    confidence: Confidence,
    narrative: str,
    claim_slug: str,
    source_ids: list[str],
    repo_root: Path,
    force: bool = False,
    status: str = "draft",
    blocked_reason: BlockedReason | None = None,
    criteria_slug: str | None = None,
) -> Path:
    """Write the claim file to disk. Returns the file path.

    Refuses to overwrite an existing claim file unless ``force=True``.
    Overwriting silently would clobber operator edits and any
    ``status: published`` flip made by ``dr review --approve``.

    ``claim_slug`` becomes the filename stem; ``criteria_slug`` is the
    optional template back-reference written into frontmatter. Onboard
    passes the same value for both (filename derives from the template
    slug); the standalone verify path passes only ``claim_slug`` (a
    slugified verdict title with no template association).

    Pass ``status='blocked'`` plus a ``blocked_reason`` for the
    threshold-blocked variant; the caller supplies a placeholder
    ``narrative`` and ``verdict``/``confidence`` since the Analyst did
    not run.
    """
    claim_slug_clean = slugify(claim_slug)

    claim_dir = _claim_dir_for(entity_ref, entity_name, repo_root)
    claim_dir.mkdir(parents=True, exist_ok=True)
    claim_path = claim_dir / f"{claim_slug_clean}.md"

    if claim_path.exists() and not force:
        raise FileExistsError(
            f"claim file already exists: {claim_path} (pass force=True to overwrite)"
        )

    fm = {
        "title": title,
        "entity": entity_ref,
        "topics": FlowList(topics),
        "verdict": verdict,
        "confidence": confidence,
        "takeaway": "",
        "seo_title": "",
        "criteria_slug": criteria_slug,
        "status": status,
        "blocked_reason": blocked_reason,
        "as_of": datetime.date.today(),
        "sources": source_ids,
        "tags": [],
    }
    claim_path.write_text(
        serialize_frontmatter(fm, narrative.rstrip() + "\n"),
        encoding="utf-8",
    )
    logger.info("Wrote claim: %s (status=%s)", claim_path, status)
    return claim_path


def _build_sources_consulted(
    source_files: list[tuple[str, SourceFile]] | None,
) -> list[dict]:
    """Build the sources_consulted list for an audit sidecar.

    Takes the raw (url, SourceFile) pairs from a verification run and returns
    a flat list of dicts suitable for YAML serialisation.  Returns an empty
    list if the input is None or empty.
    """
    if not source_files:
        return []
    result = []
    for url, sf in source_files:
        result.append(
            {
                "id": f"{sf.year}/{sf.slug}",
                "url": url,
                "title": sf.frontmatter.title,
                "ingested": True,
            }
        )
    return result


def _write_audit_sidecar(
    claim_path: Path,
    comparison: ComparisonResult | None,
    model: str,
    ran_at: datetime.datetime,
    sources_consulted: list[dict],
    agents_run: list[str],
    models_used: dict[str, str] | None = None,
    research_trace: dict | None = None,
) -> Path:
    """Write the .audit.yaml sidecar alongside a claim file.

    ``ran_at`` is passed in by the caller (not computed here) so that tests can
    inject a fixed timestamp for reproducible assertions.

    Returns the sidecar path.
    """
    sidecar_path = claim_path.with_name(claim_path.stem + ".audit.yaml")

    if comparison is not None:
        audit_block = {
            "analyst_verdict": comparison.primary_verdict.value,
            "auditor_verdict": comparison.assessed_verdict.value,
            "analyst_confidence": comparison.primary_confidence.value,
            "auditor_confidence": comparison.assessed_confidence.value,
            "verdict_agrees": comparison.verdict_agrees,
            "confidence_agrees": comparison.confidence_agrees,
            "needs_review": comparison.needs_review,
        }
    else:
        audit_block = None

    # Preserve human_review across reruns. The pipeline re-runs analyst/auditor
    # but must not wipe an operator's review decision. Staleness between the new
    # audit block and the preserved review is surfaced by the build-time staleness
    # check (see docs/plans/audit-trail.md), not by clobbering here.
    human_review = {
        "reviewed_at": None,
        "reviewer": None,
        "notes": None,
        "pr_url": None,
    }
    if sidecar_path.exists():
        try:
            existing = yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or {}
            existing_review = existing.get("human_review")
            if isinstance(existing_review, dict):
                for key in human_review:
                    if key in existing_review:
                        human_review[key] = existing_review[key]
        except yaml.YAMLError as exc:
            logger.warning("Could not parse existing sidecar %s: %s", sidecar_path, exc)

    if models_used is None:
        models_used = {agent: model for agent in agents_run}
    else:
        # Defensive: ensure every agent that ran has an entry, falling back to
        # the default model. Drop any extras so the recorded dict mirrors the
        # agents this run actually invoked.
        models_used = {agent: models_used.get(agent, model) for agent in agents_run}

    sidecar_data = {
        "schema_version": 1,
        "pipeline_run": {
            "ran_at": ran_at.isoformat(),
            "model": model,
            "agents": agents_run,
        },
        "models_used": models_used,
        "research": research_trace,
        "sources_consulted": sources_consulted,
        "audit": audit_block,
        "human_review": human_review,
    }

    sidecar_path.write_text(
        yaml.safe_dump(sidecar_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Wrote audit sidecar: %s", sidecar_path)
    return sidecar_path


_UNSET = object()


def set_claim_status(
    claim_path: Path,
    new_status: str,
    expected_current: str | None,
    *,
    phase: object = _UNSET,
    blocked_reason: object = _UNSET,
) -> None:
    """Flip the ``status`` field in a claim's frontmatter.

    Parses the claim file, verifies the current status matches
    ``expected_current`` (if provided), and writes the file back with the
    new status. Passing ``expected_current=None`` skips the status check.

    Optional kwargs:
        phase: When provided, sets the ``phase`` field. Pass ``None`` to
            clear it (e.g. on transition to a terminal state). Omitting
            the argument leaves the existing value untouched.
        blocked_reason: Same semantics as ``phase`` for ``blocked_reason``.
            Both kwargs default to a sentinel that means "do not touch",
            so existing draft → published / published → archived callers
            are unchanged.

    Raises:
        ValueError: If current status does not match ``expected_current``,
            or if frontmatter cannot be parsed.
    """
    text = claim_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    if expected_current is not None:
        current = fm.get("status")
        if current != expected_current:
            raise ValueError(
                f"status mismatch: expected {expected_current!r}, "
                f"got {current!r} in {claim_path}"
            )

    fm["status"] = new_status
    # _clean_for_serialize drops None-valued keys (so passing None clears
    # the field on disk); the FrontmatterDumper enum representer handles
    # enum-to-scalar conversion, so callers can pass Phase / BlockedReason
    # values directly without a `.value` unwrap.
    if phase is not _UNSET:
        fm["phase"] = phase
    if blocked_reason is not _UNSET:
        fm["blocked_reason"] = blocked_reason
    claim_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")


def _write_draft_entity_file(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    repo_root: Path,
    website: str | None = None,
    aliases: list[str] | None = None,
) -> str:
    """Write entity file to research/entities/drafts/{type-dir}/{slug}.md."""
    entity_slug = slugify(entity_name)
    type_dir = _ENTITY_TYPE_DIR.get(entity_type, f"{entity_type.value}s")

    draft_dir = repo_root / "research" / "entities" / "drafts" / type_dir
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"{entity_slug}.md"
    entity_ref = f"drafts/{type_dir}/{entity_slug}"

    fm = _entity_frontmatter(
        entity_name, entity_type, entity_description, website, aliases, status="draft"
    )
    draft_path.write_text(serialize_frontmatter(fm, ""), encoding="utf-8")
    logger.info("Wrote draft entity: %s", draft_path)
    return entity_ref
