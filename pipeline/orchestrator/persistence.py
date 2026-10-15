"""File I/O for persisting research artifacts to disk."""

from __future__ import annotations

import dataclasses
import datetime
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from auditor.compare import needs_review_reasons
from auditor.models import ComparisonResult
from common.frontmatter import FlowList, parse_frontmatter, serialize_frontmatter
from common.markdown_links import wrap_bare_links
from common.sidecar import read_sidecar, sidecar_path_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from analyst.agent import VerdictAssessment
    from common.findings import Finding
    from common.models import SubQuestion
    from loop import ClaimSpec, VerificationResult, VerifyConfig
    from orchestrator.entity_resolution import ResolvedEntity, SearchHints
from common.models import (
    BlockedReason,
    ClaimStatus,
    Category,
    Confidence,
    EntityType,
    FailureInfo,
    Verdict,
    VerificationLevel,
)
from common.source_classification import (
    classify_source_type,
    independence_for_source_type,
    newswire_origin,
)
from common.canonical_url import canonical_host, canonical_key, same_resource
from common.templates import normalize_title
from common.utils import host_token, slugify
from ingestor.models import SourceFile

logger = logging.getLogger(__name__)


_ENTITY_TYPE_DIR = {
    EntityType.COMPANY: "companies",
    EntityType.PRODUCT: "products",
    EntityType.SUBJECT: "subjects",
}


# Every frontmatter key an entity file may carry: the keys
# ``_entity_frontmatter`` writes plus the hand-written ``parent_company`` and
# ``sec_cik``. The linter's ``CANONICAL_ENTITY_KEYS`` is this set.
ENTITY_FRONTMATTER_KEYS: tuple[str, ...] = (
    "name", "type", "website", "aliases", "description", "parent_company",
    "search_hints", "sec_cik", "legal_name", "verification_status", "founded",
)


def _entity_frontmatter(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    website: str | None = None,
    aliases: list[str] | None = None,
    search_hints: "SearchHints | None" = None,
    legal_name: str | None = None,
    verification_status: str | None = None,
    founded: int | None = None,
) -> dict:
    # Ensure description is never empty -- the linter rejects blank required strings.
    description = entity_description.strip() or f"{entity_name} ({entity_type.value})."
    return {
        "name": entity_name,
        "type": entity_type,
        "verification_status": verification_status,
        "website": website,
        "aliases": aliases or None,
        "legal_name": legal_name,
        "description": description,
        "founded": founded,
        "search_hints": _search_hints_dict(search_hints),
    }


def _search_hints_dict(search_hints: "SearchHints | None") -> dict[str, list[str]] | None:
    if search_hints is None:
        return None
    out: dict[str, list[str]] = {}
    if search_hints.include:
        out["include"] = list(search_hints.include)
    if search_hints.exclude:
        out["exclude"] = list(search_hints.exclude)
    return out or None


def build_source_url_index(repo_root: Path) -> dict[str, str]:
    """Scan research/sources/*/*.md and return a canonical url -> source_id mapping.

    Keys are ``canonical_key(url)``, so look up with the same function.
    source_id is in the format "{year}/{slug}" matching what _write_source_files
    returns. Files that are unreadable, lack frontmatter, or have no url field
    are silently skipped.
    """
    sources_dir = repo_root / "research" / "sources"
    index: dict[str, str] = {}
    if not sources_dir.exists():
        return index
    for path in sources_dir.glob("*/*.md"):
        try:
            fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError, OSError):
            continue
        url = fm.get("url")
        if not url:
            continue
        source_id = f"{path.parent.name}/{path.stem}"
        index[canonical_key(str(url))] = source_id
    return index


def load_source_dict(source_id: str, repo_root: Path) -> dict | None:
    """Read a source file from disk and return a dict in _build_source_dict shape.

    The returned dict keys must stay in sync with _build_source_dict in pipeline.py.
    Returns None if the file cannot be read or parsed, so callers can fall back
    to normal ingestion.
    """
    path = repo_root / "research" / "sources" / f"{source_id}.md"
    try:
        fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (ValueError, yaml.YAMLError, OSError):
        return None
    slug = path.stem
    publisher = fm.get("publisher", "") or ""
    kind = fm.get("kind", "") or ""
    source_type = fm.get("source_type") or classify_source_type(publisher, kind)
    independence = fm.get("independence") or independence_for_source_type(source_type)
    return {
        "title": fm.get("title", ""),
        "publisher": publisher,
        "summary": fm.get("summary", ""),
        "key_quotes": fm.get("key_quotes") or [],
        "body": body,
        "slug": slug,
        "url": fm.get("url", ""),
        "source_id": source_id,
        "kind": kind,
        "independence": independence,
    }


def _url_on_disk(path: Path) -> str | None:
    try:
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (ValueError, yaml.YAMLError, OSError):
        return None
    url = fm.get("url")
    return str(url) if url else None


def _slug_candidates(slug: str, url: str):
    yield slug
    token = host_token(url)
    base = f"{token}-{slug}" if token and not slug.startswith(f"{token}-") else slug
    if base != slug:
        yield base
    n = 2
    while True:
        yield f"{base}-{n}"
        n += 1


def _resolve_one_slug(
    sf: SourceFile, repo_root: Path, assigned: dict[str, str]
) -> str:
    """Pick the first candidate slug that is free or already names this URL.

    ``assigned`` maps source ids handed out earlier in the same batch to
    their URLs, so two new pages in one run never share an id.
    """
    url = sf.frontmatter.url
    sources_dir = repo_root / "research" / "sources" / str(sf.year)
    for candidate in _slug_candidates(sf.slug, url):
        source_id = f"{sf.year}/{candidate}"
        if source_id in assigned:
            if same_resource(assigned[source_id], url):
                return candidate
            continue
        path = sources_dir / f"{candidate}.md"
        if not path.exists():
            return candidate
        if same_resource(_url_on_disk(path), url):
            return candidate
    raise AssertionError("unreachable: candidate generator is infinite")


def resolve_source_slugs(source_files: list[SourceFile], repo_root: Path) -> None:
    """Set each ``sf.slug`` so its source id names a file for that URL.

    Per item, against files on disk and ids already assigned in this batch:
    a free slug is kept; a slug whose file has the same canonical URL is
    reused (same page); otherwise ``<host>-<slug>`` is tried, then
    ``<host>-<slug>-2``, ``-3`` and so on. Existing files are never touched.
    """
    assigned: dict[str, str] = {}
    for sf in source_files:
        resolved = _resolve_one_slug(sf, repo_root, assigned)
        if resolved != sf.slug:
            logger.info(
                "Source slug %s/%s is taken by a different URL; using %s for %s",
                sf.year, sf.slug, resolved, sf.frontmatter.url,
            )
            sf.slug = resolved
        assigned[f"{sf.year}/{sf.slug}"] = sf.frontmatter.url


def source_markdown(sf: SourceFile) -> str:
    """The text of a source file as written under ``research/sources/``."""
    fm_dict = sf.frontmatter.model_dump(mode="python")
    source_type = classify_source_type(
        sf.frontmatter.publisher, sf.frontmatter.kind.value
    )
    fm_dict["source_type"] = source_type
    if not fm_dict.get("independence"):
        fm_dict["independence"] = independence_for_source_type(source_type)
    # The ingest model copies addresses from the page; a bare one fails
    # markdownlint MD034 in the pre-commit hook.
    return serialize_frontmatter(fm_dict, wrap_bare_links(sf.body.rstrip()) + "\n")


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

        markdown = source_markdown(sf)

        # Callers normally resolve slugs first (``resolve_source_slugs``);
        # this guard covers callers that skip it, so an id returned here
        # always names a file for this URL.
        while True:
            try:
                with target_path.open("x", encoding="utf-8") as f:
                    f.write(markdown)
                logger.info("Wrote source: %s", target_path)
                break
            except FileExistsError:
                existing_url = _url_on_disk(target_path)
                if same_resource(existing_url, sf.frontmatter.url):
                    logger.info("Source already exists, skipping: %s", target_path)
                    break
                resolved = _resolve_one_slug(sf, repo_root, {})
                logger.warning(
                    "Source %s/%s already holds %s; writing %s as %s/%s",
                    sf.year, sf.slug, existing_url, sf.frontmatter.url, sf.year, resolved,
                )
                sf.slug = resolved
                target_path = target_dir / f"{sf.slug}.md"

        source_ids.append(f"{sf.year}/{sf.slug}")

    return source_ids


def entity_ref_for(entity_name: str, entity_type: EntityType) -> str:
    """The ref ``_write_entity_file`` writes for a name, like 'companies/slug'."""
    type_dir = _ENTITY_TYPE_DIR.get(entity_type, f"{entity_type.value}s")
    return f"{type_dir}/{slugify(entity_name)}"


def _write_entity_file(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    repo_root: Path,
    website: str | None = None,
    aliases: list[str] | None = None,
    search_hints: "SearchHints | None" = None,
    legal_name: str | None = None,
    verification_status: str = "verified",
    founded: int | None = None,
    history_markdown: str | None = None,
) -> str:
    """Write entity file if it doesn't exist. Returns entity path like 'companies/slug'."""
    entity_ref = entity_ref_for(entity_name, entity_type)
    entity_path = repo_root / "research" / "entities" / f"{entity_ref}.md"
    entity_path.parent.mkdir(parents=True, exist_ok=True)

    if entity_path.exists():
        logger.info("Entity already exists: %s", entity_path)
        return entity_ref

    fm = _entity_frontmatter(
        entity_name, entity_type, entity_description, website, aliases,
        search_hints=search_hints,
        legal_name=legal_name,
        verification_status=verification_status,
        founded=founded,
    )
    body = _entity_body(history_markdown)
    entity_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")
    logger.info("Wrote entity: %s", entity_path)
    return entity_ref


def write_subject_record(entity: "ResolvedEntity", repo_root: Path) -> Path | None:
    """Write ``research/entities/<entity_ref>.md`` (name, type, description) when it is missing.

    Returns the written path, or None when the file exists: an existing
    record is never rewritten, so an operator's edits survive.
    """
    entity_path = repo_root / "research" / "entities" / f"{entity.entity_ref}.md"
    if entity_path.exists():
        return None
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    fm = _entity_frontmatter(entity.entity_name, entity.entity_type, entity.entity_description)
    entity_path.write_text(serialize_frontmatter(fm, ""), encoding="utf-8")
    logger.info("Wrote subject record: %s", entity_path)
    return entity_path


def _claim_dir_for(entity_ref: str | None, entity_name: str, repo_root: Path) -> Path:
    """Return the claims directory for an entity.

    Companies and products use a flat layout (research/claims/<slug>/) for
    backward compat; all other types (subjects, …) include the type prefix.
    """
    if entity_ref and "/" in entity_ref:
        ref_parts = entity_ref.split("/")
        slug = ref_parts[-1]
        if ref_parts[0] in ("companies", "products") and len(ref_parts) == 2:
            return repo_root / "research" / "claims" / slug
        return repo_root / "research" / "claims" / Path(*ref_parts)
    return repo_root / "research" / "claims" / slugify(entity_name)


def planned_claim_path(entity_ref: str | None, entity_name: str, claim_slug: str, repo_root: Path) -> Path:
    """Return the path ``_write_claim_file`` writes for these arguments, creating nothing."""
    return _claim_dir_for(entity_ref, entity_name, repo_root) / f"{slugify(claim_slug)}.md"


def _claim_path_for(entity_ref: str | None, entity_name: str, claim_slug: str, repo_root: Path) -> Path:
    """Return the path ``_write_claim_file`` writes for these arguments, creating its directory."""
    claim_path = planned_claim_path(entity_ref, entity_name, claim_slug, repo_root)
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    return claim_path


def verdict_write_kwargs(verdict: "VerdictAssessment") -> dict:
    """Pull source-quality fields off a VerdictAssessment in the shape expected
    by `_write_claim_file`. Centralizes the enum unwrap and override dump so
    each call site can spread `**verdict_write_kwargs(ao.verdict)`.
    """
    level = verdict.verification_level
    overrides = verdict.source_overrides
    return {
        "verification_level": level.value if level is not None else None,
        "cap_rationale": verdict.cap_rationale,
        "cap_rationale_fitted": getattr(verdict, "cap_rationale_fitted", False),
        "source_overrides": (
            [o.model_dump(mode="python", exclude_none=True) for o in overrides]
            if overrides else None
        ),
    }


def shorten(text: str, limit: int = 80) -> str:
    """``text`` cut to ``limit`` characters with a trailing "...", so it fits a
    length-limited field such as ``SourceOverride.reason``."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _enum_value(value: object) -> object:
    # Callers pass enums; a parsed file holds their string values.
    return getattr(value, "value", value)


_CAPPED_LEVELS = frozenset({VerificationLevel.CLAIMED.value, VerificationLevel.SELF_REPORTED.value})


# Every frontmatter key a claim file may carry: the keys ``_write_claim_file``
# writes, plus ``phase`` (``set_claim_status``) and the recheck and audit keys
# the site schema declares. The linter's ``CANONICAL_CLAIM_KEYS`` is this set,
# so a key the writer starts writing cannot be flagged as unknown.
CLAIM_FRONTMATTER_KEYS: tuple[str, ...] = (
    "title", "statement", "entity", "topics", "verdict", "confidence",
    "verification_level", "cap_rationale", "takeaway", "seo_title",
    "criteria_slug", "status", "phase", "blocked_reason", "as_of", "sources",
    "source_overrides", "corrections", "tags",
    "recheck_cadence_days", "next_recheck_due", "audit",
)


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
    seo_title: str | None = None,
    takeaway: str | None = None,
    verification_level: str | None = None,
    cap_rationale: str | None = None,
    source_overrides: list[dict] | None = None,
    cap_rationale_fitted: bool = False,
    statement: str | None = None,
    uncited_by_title: list[str] | None = None,
) -> Path:
    """Write the claim file to disk. Returns the file path.

    Refuses to overwrite an existing claim file unless ``force=True``.
    Overwriting silently would clobber operator edits and any
    ``status: published`` flip made by ``dr review --approve``.

    ``claim_slug`` becomes the filename stem; ``criteria_slug`` is the
    optional criterion back-reference written into frontmatter. A claim
    drafted from a criterion passes the same value for both; an ad hoc
    claim passes only ``claim_slug`` (the slugified statement).
    ``statement`` is the sentence the loop re-runs; the pipeline passes the
    same text as ``title``.

    Pass ``status='blocked'`` plus a ``blocked_reason`` for the
    threshold-blocked variant; the caller supplies a placeholder
    ``narrative`` and ``verdict``/``confidence`` since the Analyst did
    not run.

    On a forced overwrite, the existing ``seo_title`` wins when an operator
    wrote it (it differs from the analyst's last one, recorded as
    ``analyst_record`` in the audit sidecar) and the title is unchanged from
    the analyst's last title (ignoring case and spacing). The existing
    ``takeaway`` wins when the analyst gives none, and when an operator wrote
    it (it differs from the analyst's last one in the record) while the
    verdict is the analyst's last verdict. The existing ``cap_rationale``
    wins when an operator wrote it (it differs from the pipeline's last one in
    the record), whatever the new level or confidence, and on a blocked
    write. With no recorded ``cap_rationale``, the existing one wins only on
    a capped level (``claimed`` or ``self-reported``) while
    ``verification_level`` and ``confidence`` are both unchanged, and not
    when ``cap_rationale_fitted`` says the level fit wrote the passed one.
    Otherwise the passed values are written.
    """
    claim_path = _claim_path_for(entity_ref, entity_name, claim_slug, repo_root)

    if claim_path.exists() and not force:
        raise FileExistsError(
            f"claim file already exists: {claim_path} (pass force=True to overwrite)"
        )

    # On a forced overwrite, an operator may have edited these fields since
    # the last run. The analyst always writes a seo_title, so an operator's
    # seo_title is kept while the title it shortens is unchanged. An operator's
    # cap_rationale is kept until the operator edits it. A takeaway is kept when the analyst gives
    # none, and an operator's while the analyst's verdict is unchanged: it sits
    # under the verdict badge. Corrections (the public record of what changed) and tags (homepage
    # card picks) are operator-owned and always kept.
    existing_fm: dict = {}
    if claim_path.exists() and force:
        try:
            existing_fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
        except Exception as exc:
            # Overwriting would silently drop operator-owned fields.
            raise ValueError(
                f"cannot parse existing claim {claim_path}; fix its frontmatter before re-running: {exc}"
            ) from exc
    analyst_seo_title = seo_title
    analyst_takeaway = takeaway
    analyst_cap_rationale = cap_rationale
    existing_takeaway = existing_fm.get("takeaway", "") or ""
    existing_seo_title = existing_fm.get("seo_title", "") or ""
    existing_corrections = existing_fm.get("corrections") or None
    existing_tags = existing_fm.get("tags") or []

    # Compared against the analyst's last title, not the file's: a blocked
    # write in between replaces the title with a placeholder.
    record = _read_analyst_record(claim_path, existing_fm)
    recorded_title = record.get("title")
    if (
        existing_seo_title
        and existing_seo_title != record.get("seo_title")
        and isinstance(recorded_title, str)
        and normalize_title(recorded_title) == normalize_title(title)
    ):
        seo_title = existing_seo_title
    elif seo_title is None:
        seo_title = existing_seo_title

    # A takeaway with no record counts as the operator's (record.get gives None).
    if takeaway is None or (
        existing_takeaway
        and existing_takeaway != record.get("takeaway")
        and record.get("verdict") == _enum_value(verdict)
    ):
        takeaway = existing_takeaway

    existing_cap_rationale = existing_fm.get("cap_rationale") or ""
    # With a record, a rationale that differs from the pipeline's last one is
    # the operator's and wins over any new one until the operator edits it,
    # on every write: the claim page shows it only on a capped level, so on an
    # uncapped or blocked claim it waits unseen for the next capped run.
    # Without a record the text on disk may be a stale analyst one, so it is
    # kept only on a capped level while the level and confidence it explains
    # hold, and never over the level fit's.
    if "cap_rationale" in record:
        keep_cap_rationale = existing_cap_rationale != record["cap_rationale"]
    else:
        keep_cap_rationale = (
            not cap_rationale_fitted
            and _enum_value(verification_level) in _CAPPED_LEVELS
            and _enum_value(verification_level) == _enum_value(existing_fm.get("verification_level"))
            and _enum_value(confidence) == _enum_value(existing_fm.get("confidence"))
        )
    if existing_cap_rationale and keep_cap_rationale:
        cap_rationale = existing_cap_rationale

    fm = {
        "title": title,
        "statement": statement,
        "entity": entity_ref,
        "topics": FlowList(topics),
        "verdict": verdict,
        "confidence": confidence,
        "verification_level": verification_level,
        "cap_rationale": cap_rationale,
        "takeaway": takeaway,
        "seo_title": seo_title,
        "criteria_slug": criteria_slug,
        "status": status,
        "blocked_reason": blocked_reason,
        "as_of": datetime.date.today(),
        "sources": source_ids,
        "source_overrides": source_overrides,
        "corrections": existing_corrections,
        "tags": existing_tags,
    }
    claim_path.write_text(
        serialize_frontmatter(fm, narrative.rstrip() + "\n"),
        encoding="utf-8",
    )
    logger.info("Wrote claim: %s (status=%s)", claim_path, status)

    # Only an analyst's proposal updates the record; a blocked write keeps it.
    if _enum_value(status) != ClaimStatus.BLOCKED.value:
        record = updated_analyst_record(
            title, analyst_seo_title, verdict=verdict, takeaway=analyst_takeaway,
            cap_rationale=analyst_cap_rationale, previous=record,
            uncited_by_title=uncited_by_title,
        )
    if record:
        _store_analyst_record(claim_path, record)
    return claim_path


def updated_analyst_record(
    title: str,
    seo_title: str | None,
    *,
    verdict: object = None,
    takeaway: str | None = None,
    cap_rationale: str | None = None,
    previous: dict | None = None,
    uncited_by_title: list[str] | None = None,
) -> dict:
    """The sidecar ``analyst_record`` block after an analyst's write.

    It holds what the analyst proposed, never a value a keep rule left on
    disk, so the next write can tell the operator's text from the analyst's.
    The one exception is ``verdict``: it is the verdict as written (the
    pipeline verdict, which a tie-breaker can set against the analyst), since
    the takeaway keep rule compares it with the next written verdict.
    A field the analyst left out keeps its ``previous`` value: title and
    seo_title change together, since the seo_title shortens that title.
    ``cap_rationale`` is the value after the level fit, and None is recorded
    too: on a capped level a claim then has no pipeline rationale to match.
    ``uncited_by_title`` (the cited source ids the narrative never names by
    title) is written when given.
    """
    record = dict(previous or {})
    if seo_title is not None:
        record["title"] = title
        record["seo_title"] = seo_title
    if verdict is not None:
        record["verdict"] = _enum_value(verdict)
    if takeaway is not None:
        record["takeaway"] = takeaway
    record["cap_rationale"] = cap_rationale
    if uncited_by_title is not None:
        record["uncited_by_title"] = list(uncited_by_title)
    return record


def analyst_record_for(verdict: "VerdictAssessment", uncited_by_title: list[str] | None = None) -> dict:
    """``updated_analyst_record`` for a verdict as written, for a claim's first sidecar."""
    return updated_analyst_record(
        verdict.title, verdict.seo_title, verdict=verdict.verdict, takeaway=verdict.takeaway,
        cap_rationale=verdict.cap_rationale, uncited_by_title=uncited_by_title,
    )


def _read_analyst_record(claim_path: Path, existing_fm: dict) -> dict:
    """What the analyst last wrote to this claim (``updated_analyst_record``).

    Read from the audit sidecar. A claim written before the record existed
    gets its file title and verdict with no seo_title or takeaway, so any
    seo_title or takeaway on disk counts as the operator's; a blocked file
    gives neither, since it holds placeholders.
    """
    recorded = (read_sidecar(claim_path) or {}).get("analyst_record")
    if isinstance(recorded, dict):
        return recorded
    existing_title = existing_fm.get("title")
    if isinstance(existing_title, str) and existing_fm.get("status") != ClaimStatus.BLOCKED.value:
        return {
            "title": existing_title,
            "seo_title": None,
            "verdict": _enum_value(existing_fm.get("verdict")),
        }
    return {}


def _store_analyst_record(claim_path: Path, record: dict) -> None:
    # Only an existing sidecar is updated: one holding just this block would
    # fail the sidecar schema. Callers that write the claim before its first
    # sidecar pass the record to _write_audit_sidecar instead.
    sidecar_path = sidecar_path_for(claim_path)
    if not sidecar_path.exists():
        return
    try:
        data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("Could not parse sidecar %s to record the analyst record: %s", sidecar_path, exc)
        return
    if not isinstance(data, dict) or data.get("analyst_record") == record:
        return
    data["analyst_record"] = record
    sidecar_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _build_sources_consulted(
    source_files: list[tuple[str, SourceFile]] | None,
    cached_sources: list[tuple[str, str, dict]] | None = None,
    archive: dict[str, dict] | None = None,
    quote_checks: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Build the sources_consulted list for an audit sidecar.

    Combines freshly-ingested ``source_files`` (``(url, SourceFile)`` tuples)
    with ``cached_sources`` reused via URL dedup
    (``(url, source_id, source_dict)`` tuples). Cached entries are listed
    first to mirror the order in which the pipeline appends them to
    ``VerificationResult.sources``. If a source_id appears in both lists
    the cached entry wins. Returns ``[]`` when both inputs are empty.

    ``archive`` (requested URL -> ``{status, error?}``) adds the archive
    lookup record to fresh entries; cached entries were not looked up.

    Every entry carries ``quotes``: a fresh source's key quote checks from
    ``quote_checks`` (requested URL -> records), a cached source's stored
    key quotes marked ``not-rechecked``. ``shared_with`` names the other
    entries on the same canonical host or from the same newswire origin,
    and is left out when there are none.
    """
    result: list[dict] = []
    publishers: list[str] = []
    seen_ids: set[str] = set()

    for url, source_id, sd in cached_sources or []:
        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        result.append(
            {
                "id": source_id,
                "url": url,
                "title": sd.get("title", ""),
                "ingested": True,
                "quotes": [
                    {"text": q, "found": None, "checked_against": "not-rechecked", "passage": None}
                    for q in sd.get("key_quotes") or [] if isinstance(q, str)
                ],
            }
        )
        publishers.append(str(sd.get("publisher") or ""))

    for url, sf in source_files or []:
        source_id = f"{sf.year}/{sf.slug}"
        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        entry = {
            "id": source_id,
            "url": url,
            "title": sf.frontmatter.title,
            "ingested": True,
        }
        if archive and url in archive:
            entry["archive"] = dict(archive[url])
        entry["quotes"] = [dict(q) for q in (quote_checks or {}).get(url, [])]
        result.append(entry)
        publishers.append(sf.frontmatter.publisher or "")

    hosts = [canonical_host(e["url"]) for e in result]
    origins = [newswire_origin(p) for p in publishers]
    for i, entry in enumerate(result):
        shared = [
            other["id"] for k, other in enumerate(result)
            if k != i and ((hosts[i] and hosts[k] == hosts[i]) or (origins[i] and origins[k] == origins[i]))
        ]
        if shared:
            entry["shared_with"] = shared
    return result


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def _read_published_snapshot(claim_path: Path) -> dict | None:
    """Return the reader-visible state of a published claim, or None if it is not published.

    A refresh overwrites the claim and resets ``human_review``, so this must be
    read before the overwrite to keep the prior verdict and sign-off on record.
    """
    try:
        fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    if fm.get("status") != "published":
        return None
    sidecar = read_sidecar(claim_path) or {}
    review = sidecar.get("human_review") or {}
    run = sidecar.get("pipeline_run") or {}
    return {
        "status": "published",
        "verdict": _iso(fm.get("verdict")),
        "confidence": _iso(fm.get("confidence")),
        "title": fm.get("title"),
        "as_of": _iso(fm.get("as_of")),
        "sources": list(fm.get("sources") or []),
        "reviewed_at": _iso(review.get("reviewed_at")),
        "reviewer": review.get("reviewer"),
        "ran_at": _iso(run.get("ran_at")),
    }


def _refresh_block(
    existing: dict,
    previous_publication: dict | None,
    current_source_ids: list[str] | None,
    ran_at: datetime.datetime,
) -> dict | None:
    """Build the sidecar ``refresh`` block, or None when no refresh awaits re-approval.

    A pending block carries forward unchanged, so a second refresh before
    re-approval does not replace the published state with the unapproved one.
    It also wins over a new snapshot: approval and archiving never leave a
    block on a published claim, so a published claim with one
    is a refresh that wrote its sidecar and then failed to write the claim,
    and that sidecar's ``human_review`` is already reset.
    """
    if isinstance(existing.get("refresh"), dict):
        block = dict(existing["refresh"])
    elif previous_publication is not None:
        block = {"refreshed_at": ran_at.isoformat(), "previous": previous_publication}
    else:
        return None
    if current_source_ids is not None:
        current = set(current_source_ids)
        previous_sources = (block.get("previous") or {}).get("sources") or []
        block["dropped_sources"] = [s for s in previous_sources if s not in current]
    return block


def _edit_sidecar(claim_path: Path, edit: Callable[[dict], bool]) -> None:
    """Apply ``edit`` to the claim's existing sidecar, writing it back when
    ``edit`` returns True. A claim with no sidecar is left alone; an
    unparseable sidecar raises, so the claim write after it does not run."""
    sidecar_path = sidecar_path_for(claim_path)
    if not sidecar_path.exists():
        return
    data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"cannot parse sidecar {sidecar_path}")
    if edit(data):
        sidecar_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def clear_audit(claim_path: Path) -> None:
    """Set the sidecar's ``audit`` block to null for a new analysis of the claim.

    For a rewrite that runs the analyst but not the Evaluator (``dr
    step-analyze --write``): the Evaluator's verdict and reasoning describe
    the old analysis, so comparing them with the new verdict would show an
    agreement nobody checked, and ``dr review --approve`` would read the old
    analyst verdict as a reviewer's override. The claim page shows the
    Evaluator check as unavailable until ``dr step-audit --write``, as for a
    blocked claim. Call it before the claim write.
    """
    def edit(data: dict) -> bool:
        if data.get("audit") is None:
            return False
        data["audit"] = None
        return True

    _edit_sidecar(claim_path, edit)


def record_restatement_pick(claim_path: Path, n: int) -> None:
    """Set ``restatement.picked`` to ``n`` in the claim's sidecar.

    Raises ``ValueError`` when the sidecar has no ``restatement`` block or no
    candidate has rank ``n``; the sidecar is then left unchanged.
    """
    def edit(data: dict) -> bool:
        block = data.get("restatement")
        if not isinstance(block, dict):
            raise ValueError(f"no restatement block in {sidecar_path_for(claim_path)}")
        ranks = [c.get("rank") for c in block.get("candidates") or [] if isinstance(c, dict)]
        if n not in ranks:
            raise ValueError(f"no candidate {n} in {sidecar_path_for(claim_path)} ({len(ranks)} candidates)")
        block["picked"] = n
        return True

    if not sidecar_path_for(claim_path).exists():
        raise ValueError(f"no sidecar for {claim_path}")
    _edit_sidecar(claim_path, edit)


def mark_forced_rewrite(
    claim_path: Path,
    current_source_ids: list[str] | None,
    ran_at: datetime.datetime,
) -> bool:
    """Prepare a forced rewrite of a claim on disk that is not a draft.

    A rewrite must not go live without review (production builds archived
    claims as well as published ones), and a blocked claim with a verdict is
    no longer blocked, so a published, archived or blocked claim is written
    back as a draft (or blocked) and its sidecar's ``human_review`` is reset.
    For a published claim the sidecar also starts or carries forward the
    ``refresh`` block, as ``_write_audit_sidecar`` does for ``dr draft
    --claim --force``, so ``dr review --approve`` asks for a correction when
    the verdict changed. Call it before the claim write: the sidecar is
    written first, so a failed claim write leaves the claim unchanged with
    the snapshot pending.

    Returns True when the claim was not a draft. A missing claim or a draft
    is left alone, and so is an unparseable claim, which the forced claim
    write then refuses with its own message.
    """
    try:
        fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, yaml.YAMLError):
        return False
    if fm.get("status", ClaimStatus.DRAFT.value) == ClaimStatus.DRAFT.value:
        return False
    previous_publication = _read_published_snapshot(claim_path)

    def edit(data: dict) -> bool:
        data["human_review"] = {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None}
        refresh = _refresh_block(data, previous_publication, current_source_ids, ran_at)
        if refresh is not None:
            data["refresh"] = refresh
        return True

    _edit_sidecar(claim_path, edit)
    return True


# The top-level keys ``_write_audit_sidecar`` owns; any other key on an
# existing sidecar is carried forward unchanged.
_SIDECAR_KEYS = frozenset({
    "schema_version", "pipeline_run", "models_used", "research", "sub_questions",
    "sources_consulted", "refresh", "audit", "human_review", "analyst_record",
    "restatement",
})


def _write_audit_sidecar(
    claim_path: Path,
    comparison: ComparisonResult | None,
    model: str,
    ran_at: datetime.datetime,
    sources_consulted: list[dict],
    agents_run: list[str],
    models_used: dict[str, str] | None = None,
    research_trace: dict | None = None,
    sub_questions_block: list[dict] | None = None,
    failure: FailureInfo | None = None,
    previous_publication: dict | None = None,
    current_source_ids: list[str] | None = None,
    analyst_record: dict | None = None,
    level_clamp: str | None = None,
    keep_other_models: bool = False,
    run_id: str | None = None,
    restatement: dict | None = None,
    restates: str | None = None,
) -> Path:
    """Write the .audit.yaml sidecar alongside a claim file.

    ``ran_at`` is passed in by the caller (not computed here) so that tests can
    inject a fixed timestamp for reproducible assertions.

    ``previous_publication`` (from ``_read_published_snapshot``) starts a
    ``refresh`` block; ``current_source_ids`` recomputes its ``dropped_sources``.

    The ``analyst_record`` block is carried over from the existing sidecar;
    ``_write_claim_file`` owns it. A passed ``analyst_record`` is written only
    when the existing sidecar has none, as for a claim written before its
    first sidecar existed.

    ``level_clamp`` is the note from the loop's level fit (``loop/fit.py``);
    it explains why the claim's level differs from the analyst's.

    ``keep_other_models`` keeps the existing ``models_used`` entries of agents
    this run did not invoke, for a run that rewrites the sidecar without
    rewriting what those agents produced (``dr step-audit --write``).

    ``run_id`` is written as ``pipeline_run.run_id``, so the sidecar names the
    run that wrote it.

    ``restatement`` is the run's ``restatement`` block, written after
    ``analyst_record``. The key is this function's, so a write that passes
    none drops an existing block: a caller that rewrites the sidecar without
    a new full run passes the existing block to keep it.

    ``restates`` (the ref of the claim this one restates) is not this
    function's key: it is carried forward like any other, and a passed value
    replaces the carried one.

    Every other top-level key of the existing sidecar (one this function does
    not write, such as a key a later tool added, or ``restates``) is carried
    forward after ``analyst_record`` and ``restatement``.

    Returns the sidecar path.
    """
    sidecar_path = claim_path.with_name(claim_path.stem + ".audit.yaml")

    existing: dict = {}
    if sidecar_path.exists():
        try:
            loaded = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
            existing = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError as exc:
            logger.warning("Could not parse existing sidecar %s: %s", sidecar_path, exc)

    # The existing record wins: the claim write just merged this run into it,
    # and a passed record holds only this run's fields.
    if isinstance(existing.get("analyst_record"), dict):
        analyst_record = existing["analyst_record"]
    carried = {k: v for k, v in existing.items() if k not in _SIDECAR_KEYS}

    if comparison is not None:
        audit_block = {
            "analyst_verdict": comparison.primary_verdict.value,
            "auditor_verdict": comparison.assessed_verdict.value,
            "analyst_confidence": comparison.primary_confidence.value,
            "auditor_confidence": comparison.assessed_confidence.value,
            "verdict_agrees": comparison.verdict_agrees,
            "confidence_agrees": comparison.confidence_agrees,
            "needs_review": comparison.needs_review,
            "auditor_reasoning": comparison.reasoning,
            "evidence_gaps": list(comparison.evidence_gaps),
            "needs_review_reasons": needs_review_reasons(comparison),
            "pipeline_verdict": _enum_value(comparison.pipeline_verdict),
            "pipeline_confidence": _enum_value(comparison.pipeline_confidence),
            "rule_applied": comparison.rule_applied,
        }
        if comparison.tiebreaker_verdict is not None:
            audit_block["tiebreaker_verdict"] = _enum_value(comparison.tiebreaker_verdict)
            audit_block["tiebreaker_confidence"] = _enum_value(comparison.tiebreaker_confidence)
            audit_block["tiebreaker_reasoning"] = comparison.tiebreaker_reasoning
    else:
        audit_block = None

    # Preserve human_review across mid-pipeline reruns. A forced rewrite
    # resets sign-off through ``mark_forced_rewrite`` before this write.
    human_review = {
        "reviewed_at": None,
        "reviewer": None,
        "notes": None,
        "pr_url": None,
    }
    existing_review = existing.get("human_review")
    if isinstance(existing_review, dict):
        # verdict_override is written only at approval, so it is kept
        # only where present rather than added as null to every sidecar.
        for key in (*human_review, "verdict_override"):
            if key in existing_review:
                human_review[key] = existing_review[key]

    refresh = _refresh_block(existing, previous_publication, current_source_ids, ran_at)

    if models_used is None:
        models_used = {agent: model for agent in agents_run}
    else:
        # Defensive: ensure every agent that ran has an entry, falling back to
        # the default model. Drop any extras so the recorded dict mirrors the
        # agents this run actually invoked.
        models_used = {agent: models_used.get(agent, model) for agent in agents_run}
    # Off by default: a blocked write runs fewer agents and replaces the
    # claim with a placeholder, so an older analyst model would name output
    # that is no longer on disk.
    prior_models = existing.get("models_used")
    if keep_other_models and isinstance(prior_models, dict):
        models_used = {
            **{a: m for a, m in prior_models.items() if a not in models_used},
            **models_used,
        }

    # Graft `research_trace["acquisition"]` (url -> dict) onto matching
    # `sources_consulted[]` entries where the schema declares `acquisition`,
    # then strip from `research:` to avoid duplication. Copy first so the
    # auditor-refresh path (which reads research_trace from an existing
    # sidecar) isn't aliased.
    research_block = dict(research_trace) if research_trace else research_trace
    acquisition_by_url: dict = {}
    if isinstance(research_block, dict):
        raw_acquisition = research_block.pop("acquisition", None)
        if isinstance(raw_acquisition, dict):
            acquisition_by_url = raw_acquisition

    if acquisition_by_url:
        decorated_sources: list[dict] = []
        for entry in sources_consulted:
            url = entry.get("url")
            acquisition = acquisition_by_url.get(url) if url else None
            if isinstance(acquisition, dict) and acquisition:
                # Shallow-copy the entry so the caller's list isn't mutated.
                new_entry = dict(entry)
                # Merge with any pre-existing ``acquisition`` so research-stage
                # fields (origin, query) survive an ingest-stage overlay.
                existing = entry.get("acquisition")
                if isinstance(existing, dict):
                    new_entry["acquisition"] = {**existing, **acquisition}
                else:
                    new_entry["acquisition"] = acquisition
                decorated_sources.append(new_entry)
            else:
                decorated_sources.append(entry)
        sources_consulted = decorated_sources

    pipeline_run_block: dict = {
        "ran_at": ran_at.isoformat(),
        "model": model,
        "agents": agents_run,
    }
    if run_id:
        pipeline_run_block["run_id"] = run_id
    if level_clamp:
        pipeline_run_block["level_clamp"] = level_clamp
    if failure is not None:
        pipeline_run_block["failure"] = {
            k: v for k, v in dataclasses.asdict(failure).items() if v is not None
        }
    sidecar_data: dict = {
        "schema_version": 1,
        "pipeline_run": pipeline_run_block,
        "models_used": models_used,
        "research": research_block,
    }
    if sub_questions_block is not None:
        sidecar_data["sub_questions"] = sub_questions_block
    sidecar_data["sources_consulted"] = sources_consulted
    if refresh is not None:
        sidecar_data["refresh"] = refresh
    sidecar_data["audit"] = audit_block
    sidecar_data["human_review"] = human_review
    if analyst_record is not None:
        sidecar_data["analyst_record"] = analyst_record
    if restatement is not None:
        sidecar_data["restatement"] = restatement
    sidecar_data.update(carried)
    if restates is not None:
        sidecar_data["restates"] = restates

    sidecar_path.write_text(
        yaml.safe_dump(sidecar_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Wrote audit sidecar: %s", sidecar_path)
    return sidecar_path


def build_sub_questions_block(
    sub_questions: list[SubQuestion],
    coverage: dict[str, list[str]],
    queries_by_sub_question: dict[str, list[str]],
    snippet_only: dict[str, list[str]] | None = None,
) -> list[dict] | None:
    """Render the sidecar's ``sub_questions:`` block, or None if empty.

    Each entry has ``id``, ``question``, ``rationale``, ``kind``
    (``coverage`` or ``counter-evidence``), ``queries``, ``citations`` (the
    source ids whose fetched text confirmed the scorer's tag) and
    ``snippet_only`` (the source ids the scorer tagged but whose text never
    mentions the sub-question's terms). Returns None when the planner
    emitted no sub-questions, so the sidecar writer can omit the key.
    """
    if not sub_questions:
        return None
    snippet_only = snippet_only or {}
    block: list[dict] = []
    for sq in sub_questions:
        block.append({
            "id": sq.id,
            "question": sq.question,
            "rationale": sq.rationale,
            "kind": sq.kind,
            "queries": list(queries_by_sub_question.get(sq.id, [])),
            "citations": list(coverage.get(sq.id, [])),
            "snippet_only": list(snippet_only.get(sq.id, [])),
        })
    return block


def _source_ids_in_research_order(
    result: VerificationResult, fresh_ids_by_url: dict[str, str]
) -> list[str]:
    """The claim's source ids in the researcher's URL order, each once.

    ``fresh_ids_by_url`` maps each cited fresh source's requested URL to its
    id. Cached sources the analyst did not cite are left out. An id whose URL
    the researcher did not list (none today) follows the ordered ones, so no
    cited source is dropped.
    """
    id_by_url = {
        url: sid for url, sid, _sd in result.cached_sources if url not in result.uncited_urls
    }
    id_by_url.update(fresh_ids_by_url)
    reached = (result.url_aliases.get(url, url) for url in result.urls_found)
    ordered = [id_by_url[u] for u in reached if u in id_by_url]
    return list(dict.fromkeys(ordered + list(id_by_url.values())))


def persist_sources(
    result: VerificationResult, repo_root: Path, url_index: dict[str, str] | None = None
) -> list[str]:
    """Write the fresh sources and return every source id for the claim.

    Sources in ``uncited_urls`` are neither written nor returned. The ids
    come in the researcher's URL order (``urls_found``, each alias mapped
    to the URL it reached), cached and fresh alike. A cached and a fresh
    source can still name the same file, so each id appears once.
    ``url_index`` gains the written sources under the requested, stored
    and redirect-target URLs, so later claims in the same run reuse them
    instead of fetching again.
    """
    to_write = [(url, sf) for url, sf in result.source_files if url not in result.uncited_urls]
    fresh_ids = _write_source_files(to_write, repo_root)
    if url_index is not None:
        for (url, sf), sid in zip(to_write, fresh_ids):
            url_index.setdefault(canonical_key(url), sid)
            url_index.setdefault(canonical_key(sf.frontmatter.url), sid)
            if url in result.final_urls:
                url_index.setdefault(canonical_key(result.final_urls[url]), sid)
    return _source_ids_in_research_order(
        result, {url: sid for (url, _sf), sid in zip(to_write, fresh_ids)}
    )


def write_claim_run(
    result: VerificationResult,
    spec: ClaimSpec,
    config: VerifyConfig,
    *,
    repo_root: Path,
    claim_slug: str,
    force: bool = False,
    target: Path | None = None,
    url_index: dict[str, str] | None = None,
    ran_at: datetime.datetime | None = None,
    status: str = "draft",
    create_entity: bool = False,
    restates: str | None = None,
) -> Path:
    """Write one claim run to disk, in the one write order; return the claim path.

    The order is the same on every path: ``mark_forced_rewrite`` when
    ``force`` (the source ids are known before any write, because ingest
    settled every slug), then the subject record when ``create_entity`` and
    none exists (``write_subject_record``), then the cited source files
    (``persist_sources``), then the claim, then the full sidecar. A run that
    never reaches the writer leaves no record, no source and no claim.

    The claim's ``verdict`` and ``confidence`` are the pipeline's: the
    analyst's, or the side the tie-breaker settled on
    (``result.consistency.pipeline_verdict``). When the fit lowered the
    level to a capped one, the confidence is capped at low whichever side
    won; a capped level the analyst chose keeps its confidence, and
    ``dr lint`` warns.

    The claim's ``title`` and ``statement`` are both ``spec.statement``, and
    the sidecar's ``analyst_record.title`` records it, so the ``seo_title``
    keep rule compares like with like on the next write. The level fit ran
    inside the loop, after the cited filter and before the Evaluator; its
    note (``result.level_clamp``) is recorded here in
    ``pipeline_run.level_clamp``.

    The sidecar's ``restatement`` block is the run's (``result.restatement``):
    a run that did not restate drops an older block, and the restater is
    listed among the agents only when its block is written. ``restates`` is
    the ref of the claim this run restates (``dr draft --restates``).

    ``target`` is the claim file path; it defaults to the entity's claim
    directory plus ``claim_slug``. Raises ``ValueError`` for a run with no
    analyst output or a ``blocked_reason``: callers decide not to write.

    The forced-rewrite snapshot uses the planned ids (``year/slug`` from
    ingest). If ``persist_sources`` renames a slug on a write-time collision,
    the snapshot's ``dropped_sources`` can differ from the written
    ``sources:``; rare, and accepted.
    """
    ao = result.analyst_output
    if ao is None or result.blocked_reason is not None:
        raise ValueError("write_claim_run needs a run with an analyst output and no blocked_reason")
    entity_ref = spec.entity.entity_ref
    entity_name = spec.entity.entity_name
    ran_at = ran_at or datetime.datetime.now(datetime.timezone.utc)
    claim_path = _claim_path_for(entity_ref, entity_name, claim_slug, repo_root)
    if target is not None and Path(target) != claim_path:
        raise ValueError(f"target {target} is not the claim path {claim_path} for slug {claim_slug!r}")
    # Refused before any write, so a refused run leaves no orphan source file.
    if claim_path.exists() and not force:
        raise FileExistsError(
            f"claim file already exists: {claim_path} (pass force=True to overwrite)"
        )

    if force:
        planned_ids = _source_ids_in_research_order(result, {
            url: f"{sf.year}/{sf.slug}"
            for url, sf in result.source_files if url not in result.uncited_urls
        })
        mark_forced_rewrite(claim_path, planned_ids, ran_at)
    if create_entity:
        write_subject_record(spec.entity, repo_root)
    source_ids = persist_sources(result, repo_root, url_index)

    topics = list(ao.verdict.topics)
    if spec.topics:
        # A criterion-backed claim carries the criterion's full topic set.
        try:
            topics = [Category(t) for t in spec.topics]
        except ValueError as exc:
            logger.warning("Criterion %s has an invalid topic; using the analyst's topics: %s",
                           spec.criteria_slug, exc)
    level_clamp = result.level_clamp
    verdict, confidence = ao.verdict.verdict, ao.verdict.confidence
    settled = result.consistency
    if settled is not None and settled.pipeline_verdict is not None:
        verdict = settled.pipeline_verdict
        confidence = settled.pipeline_confidence or confidence
    if level_clamp and _enum_value(ao.verdict.verification_level) in _CAPPED_LEVELS:
        # The fit lowered the level to a capped one: confidence is capped
        # whichever side's verdict won. A capped level the analyst chose
        # keeps its confidence, and lint's confidence-cap-violation flags it.
        confidence = Confidence.LOW
    written = _write_claim_file(
        title=spec.statement,
        statement=spec.statement,
        entity_name=entity_name,
        entity_ref=entity_ref,
        topics=topics,
        verdict=verdict,
        confidence=confidence,
        narrative=ao.verdict.narrative,
        claim_slug=claim_slug,
        source_ids=source_ids,
        repo_root=repo_root,
        force=force,
        status=status,
        criteria_slug=spec.criteria_slug,
        seo_title=ao.verdict.seo_title,
        takeaway=ao.verdict.takeaway,
        uncited_by_title=result.uncited_by_title,
        **verdict_write_kwargs(ao.verdict),
    )
    agents_run = ["researcher", "ingestor", "analyst", "auditor"]
    if settled is not None and settled.tiebreaker_verdict is not None:
        agents_run.append("tiebreaker")
    if result.restatement is not None:
        agents_run.append("restater")
    _write_audit_sidecar(
        claim_path=written,
        comparison=result.consistency,
        model=config.model,
        ran_at=ran_at,
        sources_consulted=result.sources_consulted(),
        agents_run=agents_run,
        models_used={a: config.model_for(a) for a in agents_run},
        research_trace=result.research_trace,
        sub_questions_block=build_sub_questions_block(
            result.sub_questions,
            result.sub_question_coverage,
            result.queries_by_sub_question,
            snippet_only=result.snippet_only,
        ),
        # The verdict recorded is the one written, as later writes record it,
        # so a tie-broken claim's operator takeaway survives a forced rerun.
        analyst_record={
            **analyst_record_for(ao.verdict, uncited_by_title=result.uncited_by_title),
            "title": spec.statement,
            "verdict": _enum_value(verdict),
        },
        level_clamp=level_clamp,
        run_id=config.run_id,
        restatement=result.restatement,
        restates=restates,
    )
    return written


def write_evaluator_rerun(
    claim_path: Path,
    result: VerificationResult,
    config: VerifyConfig,
    *,
    ran_at: datetime.datetime | None = None,
) -> Path:
    """Rewrite a claim's sidecar after an Evaluator-only rerun; return the sidecar path.

    The claim file is not rewritten, so the research trace, the
    ``sub_questions`` block, each ``sources_consulted`` entry (with its
    ``acquisition`` and ``archive`` records), the level fit's note and the
    other agents' ``models_used`` are carried forward from the existing
    sidecar. A source the existing sidecar does not list gets a minimal
    entry. When the rerun's disagreement went to the tie-breaker, it is
    recorded beside the Evaluator. The ``restatement`` block, pick included,
    is carried unchanged: a rerun never restates.
    """
    sidecar_path = sidecar_path_for(claim_path)
    existing: dict = {}
    if sidecar_path.exists():
        try:
            loaded = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
            existing = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError:
            pass
    prior_entries = {
        s["id"]: s
        for s in existing.get("sources_consulted") or []
        if isinstance(s, dict) and s.get("id")
    }
    sources_consulted = [
        dict(prior_entries[sd["source_id"]]) if sd["source_id"] in prior_entries else
        {"id": sd["source_id"], "url": sd.get("url", ""), "title": sd.get("title", ""), "ingested": True}
        for sd in result.sources
        if sd.get("source_id")
    ]
    agents_run = ["auditor"]
    if result.consistency is not None and result.consistency.tiebreaker_verdict is not None:
        agents_run.append("tiebreaker")
    auditor_model = config.model_for("auditor")
    return _write_audit_sidecar(
        claim_path=claim_path,
        comparison=result.consistency,
        model=auditor_model,
        ran_at=ran_at or datetime.datetime.now(tz=datetime.timezone.utc),
        sources_consulted=sources_consulted,
        agents_run=agents_run,
        models_used={a: config.model_for(a) for a in agents_run},
        research_trace=existing.get("research"),
        sub_questions_block=existing.get("sub_questions"),
        # The claim is not rewritten, so the level fit's note on it still holds.
        level_clamp=(existing.get("pipeline_run") or {}).get("level_clamp"),
        keep_other_models=True,
        run_id=config.run_id,
        restatement=existing.get("restatement"),
    )


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


def set_claim_corrections(claim_path: Path, entries: list[dict]) -> None:
    """Replace the ``corrections`` list in a claim's frontmatter, keeping everything else."""
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    fm["corrections"] = entries or None
    claim_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")


# The claim fields a reviewer edits in the ``dr review`` walkthrough (``e`` key).
REVIEW_EDITABLE_FIELDS = ("title", "takeaway", "seo_title", "tags", "verdict")


def set_claim_fields(claim_path: Path, edits: dict) -> None:
    """Write the reviewer's edits to the fields in ``REVIEW_EDITABLE_FIELDS``, keeping everything else.

    Raises ``ValueError`` before any write when ``edits`` names another key.
    ``tags`` is written as a flow list.
    """
    unknown = sorted(set(edits) - set(REVIEW_EDITABLE_FIELDS))
    if unknown:
        raise ValueError(f"not a review-editable claim field: {unknown}; editable: {list(REVIEW_EDITABLE_FIELDS)}")
    text = claim_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    for key in REVIEW_EDITABLE_FIELDS:
        if key not in edits:
            continue
        if key == "tags":
            fm[key] = FlowList(edits[key])
        else:
            fm[key] = edits[key]
    claim_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")


def set_claim_criterion(claim_path: Path, slug: str) -> None:
    """Add a ``criteria_slug`` line to a claim's frontmatter; every other byte is unchanged.

    The line goes before ``status:`` (the writer's key order), else at the end
    of the frontmatter. Inserting text rather than re-serialising keeps the
    operator's formatting (flow lists, quoting) as it was.
    """
    text = claim_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{claim_path} has no frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError(f"{claim_path} has no closing frontmatter fence")
    at = next((i for i in range(1, end) if lines[i].startswith("status:")), end)
    lines.insert(at, yaml.safe_dump({"criteria_slug": slug}, sort_keys=False, allow_unicode=True))
    claim_path.write_text("".join(lines), encoding="utf-8")


_TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z_][\w-]*:")


def append_template_entry(repo_root: Path, entry: dict) -> None:
    """Add ``entry`` as the last item of the ``templates:`` list in ``research/templates.yaml``.

    Raises ``ValueError`` when the slug is already in ``templates:`` or
    ``inactive_templates:``. The entry is inserted as indented text after the
    last active entry and before the comment block that opens the next
    top-level key, so the file's comments and every existing entry keep
    their bytes. Appending at the end of the file would put the entry under
    ``inactive_templates:``, where the pipeline and the site never read it.
    """
    path = repo_root / "research" / "templates.yaml"
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    slug = entry["slug"]
    for key in ("templates", "inactive_templates"):
        if any(isinstance(e, dict) and e.get("slug") == slug for e in data.get(key) or []):
            raise ValueError(f"criterion slug {slug!r} already exists in {key}: of {path}")

    dumped = yaml.safe_dump(
        [entry], sort_keys=False, default_flow_style=None, allow_unicode=True, width=10**6,
    )
    fragment = "".join(f"  {line}" for line in dumped.splitlines(keepends=True))

    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith("templates:")), None)
    if start is None:
        raise ValueError(f"{path} has no top-level templates: key")
    next_key = next(
        (i for i in range(start + 1, len(lines)) if _TOP_LEVEL_KEY_RE.match(lines[i])), len(lines),
    )
    # Back over the blank lines and column-0 comments that introduce the next key.
    insert_at = next_key
    while insert_at > start + 1 and (not lines[insert_at - 1].strip() or lines[insert_at - 1].startswith("#")):
        insert_at -= 1
    head = "".join(lines[:insert_at])
    if head and not head.endswith("\n"):
        head += "\n"
    # One blank line goes between the new entry and the comment block after it.
    tail_lines = lines[insert_at:]
    while tail_lines and not tail_lines[0].strip():
        tail_lines.pop(0)
    tail = "\n" + "".join(tail_lines) if tail_lines else ""
    path.write_text(f"{head}\n{fragment}{tail}", encoding="utf-8")
    logger.info("Appended criterion %s to %s", slug, path)


def _findings_dir(repo_root: Path) -> Path:
    return repo_root / "research" / "findings"


def write_finding(finding: "Finding", repo_root: Path, command: str | None = None) -> Path:
    """Write ``research/findings/<yyyy>/<run_id>.yaml`` and return its path.

    ``command`` fills the record's ``command`` when the finding has none. A
    second write for the same run id replaces the first: one record per run.
    """
    if finding.command is None and command is not None:
        finding.command = command
    path = _findings_dir(repo_root) / f"{finding.date.year:04d}" / f"{finding.run_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(finding.to_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Wrote finding: %s", path)
    return path


def _finding_files(repo_root: Path) -> list[Path]:
    root = _findings_dir(repo_root)
    return sorted(root.rglob("*.yaml")) if root.is_dir() else []


def load_findings(repo_root: Path, include_closed: bool = False) -> list["Finding"]:
    """Every finding under ``research/findings/``, in path order; closed ones only when asked."""
    from common.findings import Finding

    out: list[Finding] = []
    for path in _finding_files(repo_root):
        # One bad file must not stop `dr findings` or `dr review`.
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            finding = Finding.from_dict(data) if isinstance(data, dict) else None
        except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipped unreadable finding: %s (%s)", path, exc)
            continue
        if finding is None:
            logger.warning("Skipped unreadable finding: %s", path)
            continue
        if finding.closed is None or include_closed:
            out.append(finding)
    return out


def close_finding(repo_root: Path, finding_id: str, note: str, by: str = "hand") -> Path:
    """Record ``closed: {date, by, note}`` on the finding whose run id is or starts with ``finding_id``.

    Raises ``KeyError`` when no finding matches, ``ValueError`` when the
    prefix matches more than one or the finding is already closed.
    """
    from common.findings import Finding

    matches = [p for p in _finding_files(repo_root) if p.stem.startswith(finding_id)]
    exact = [p for p in matches if p.stem == finding_id]
    if exact:
        matches = exact
    if not matches:
        raise KeyError(finding_id)
    if len(matches) > 1:
        raise ValueError(f"{finding_id} matches {len(matches)} findings: {', '.join(p.stem for p in matches)}")
    path = matches[0]
    finding = Finding.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))
    if finding.closed is not None:
        raise ValueError(f"finding {finding.run_id} is already closed ({finding.closed.get('note')})")
    finding.closed = {"date": datetime.date.today(), "by": by, "note": note}
    path.write_text(
        yaml.safe_dump(finding.to_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info("Closed finding: %s", path)
    return path


def half_claims(repo_root: Path) -> dict[str, list[str]]:
    """What a writer crash can leave behind; nothing is deleted.

    ``claims_without_sidecar`` lists claim refs (the path under
    ``research/claims/`` without ``.md``) that have no ``.audit.yaml``.
    ``subjects_without_claim`` lists subject records (``subjects/<slug>``)
    whose claim directory holds no claim.
    """
    claims_root = repo_root / "research" / "claims"
    without_sidecar: list[str] = []
    if claims_root.is_dir():
        for claim in sorted(claims_root.rglob("*.md")):
            if not sidecar_path_for(claim).exists():
                without_sidecar.append(claim.relative_to(claims_root).with_suffix("").as_posix())
    subjects_root = repo_root / "research" / "entities" / "subjects"
    without_claim: list[str] = []
    if subjects_root.is_dir():
        for record in sorted(subjects_root.glob("*.md")):
            claim_dir = claims_root / "subjects" / record.stem
            if not (claim_dir.is_dir() and any(claim_dir.glob("*.md"))):
                without_claim.append(f"subjects/{record.stem}")
    return {"claims_without_sidecar": without_sidecar, "subjects_without_claim": without_claim}


def _entity_body(history_markdown: str | None) -> str:
    """Normalize the history markdown to a body string with a trailing newline.

    Strips trailing whitespace per-line so markdownlint MD009 doesn't fire on
    stray spaces at paragraph ends.
    """
    if not history_markdown:
        return ""
    cleaned = "\n".join(line.rstrip() for line in history_markdown.splitlines())
    return cleaned.rstrip() + "\n"
