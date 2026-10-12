"""File I/O for persisting research artifacts to disk."""

from __future__ import annotations

import dataclasses
import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from auditor.compare import needs_review_reasons
from auditor.models import ComparisonResult
from common.frontmatter import FlowList, parse_frontmatter, serialize_frontmatter
from common.markdown_links import wrap_bare_links
from common.sidecar import read_sidecar, sidecar_path_for

if TYPE_CHECKING:
    from analyst.agent import VerdictAssessment
    from orchestrator.entity_resolution import SearchHints
from common.models import (
    INDEPENDENT_SOURCES_REQUIRED,
    SELF_REPORT_KINDS,
    SELF_REPORTED_BASIS_KINDS,
    BlockedReason,
    ClaimStatus,
    Category,
    Confidence,
    EntityType,
    FailureInfo,
    Independence,
    Verdict,
    VerificationLevel,
)
from common.source_classification import (
    classify_source_type,
    effective_independence,
    independence_for_source_type,
)
from common.canonical_url import canonical_key, same_resource
from common.templates import normalize_title
from common.utils import host_token, slugify
from ingestor.models import SourceFile

logger = logging.getLogger(__name__)


_ENTITY_TYPE_DIR = {
    EntityType.COMPANY: "companies",
    EntityType.PRODUCT: "products",
    EntityType.SUBJECT: "subjects",
}


def _entity_frontmatter(
    entity_name: str,
    entity_type: EntityType,
    entity_description: str,
    website: str | None = None,
    aliases: list[str] | None = None,
    status: str | None = None,
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
        "status": status,
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


def _claim_path_for(entity_ref: str | None, entity_name: str, claim_slug: str, repo_root: Path) -> Path:
    """Return the path ``_write_claim_file`` writes for these arguments, creating its directory."""
    claim_dir = _claim_dir_for(entity_ref, entity_name, repo_root)
    claim_dir.mkdir(parents=True, exist_ok=True)
    return claim_dir / f"{slugify(claim_slug)}.md"


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
        "cap_rationale_fitted": getattr(verdict, "_cap_rationale_fitted", False),
        "source_overrides": (
            [o.model_dump(mode="python", exclude_none=True) for o in overrides]
            if overrides else None
        ),
    }


def fit_verdict_to_written_pool(
    verdict: "VerdictAssessment",
    sources: list[dict],
    source_ids: list[str],
    entity_name: str,
    log: bool = True,
) -> str | None:
    """Lower ``verification_level`` to what the written source list supports.

    The analyst picks the level from every source it was shown, but the claim
    cites only ``source_ids``, and the site counts that list. Overrides for
    sources not in the list are dropped. Independence per source is its
    override, else the label in ``sources`` (already relabelled for the
    entity). A level short of independent sources falls to
    ``independently-verified`` with one, else to ``self-reported`` (a
    first-party report, documentation or dataset is written) or ``claimed``.
    ``self-reported`` falls to ``claimed`` when no independent source and no
    first-party report, documentation, dataset or article is written; an
    article is kept because the analyst may judge one with methodology or
    data self-reported.
    A capped result gets ``confidence: low`` and, when the verdict has none,
    a template ``cap_rationale``. A ``self-reported`` verdict lowered to
    ``claimed`` always gets the template: its own rationale describes the
    first-party report that is no longer written. Either way, a rationale the
    operator wrote on the claim is kept at write time (``_write_claim_file``).

    Returns a one-line note when the level changed, else None. Call it just
    before the claim (and its sidecar) is written, after the final
    ``source_ids`` exist. ``log=False`` is for trial runs on a copy.
    """
    written = set(source_ids)
    if verdict.source_overrides:
        verdict.source_overrides = [
            o for o in verdict.source_overrides if o.source in written
        ] or None

    level = _enum_value(verdict.verification_level)
    required = INDEPENDENT_SOURCES_REQUIRED.get(level)
    if required is None and level != VerificationLevel.SELF_REPORTED.value:
        return None
    by_id = {sd.get("source_id"): sd for sd in sources}
    overrides = {
        o.source: o.independence.value
        for o in verdict.source_overrides or []
        if o.independence is not None
    }
    labels = effective_independence(
        source_ids,
        {sid: by_id.get(sid, {}).get("independence") for sid in source_ids},
        overrides,
    )

    def first_party_of(kinds: frozenset[str]) -> bool:
        return any(
            label == Independence.FIRST_PARTY.value and by_id.get(sid, {}).get("kind") in kinds
            for sid, label in labels
        )

    independent = sum(1 for _, v in labels if v == Independence.INDEPENDENT.value)
    if required is None:
        # self-reported. With an independent source the pool supports more,
        # and the fit only lowers.
        if independent or first_party_of(SELF_REPORTED_BASIS_KINDS):
            return None
        new_level = VerificationLevel.CLAIMED
        reason = "include no first-party report, documentation, dataset or article"
    elif independent >= required:
        return None
    else:
        reason = (
            f"include {independent} independent source(s), and {level} needs {required}"
        )
        if independent >= 1:
            new_level = VerificationLevel.INDEPENDENTLY_VERIFIED
        elif first_party_of(SELF_REPORT_KINDS):
            new_level = VerificationLevel.SELF_REPORTED
        else:
            new_level = VerificationLevel.CLAIMED
    verdict.verification_level = new_level
    if new_level in (VerificationLevel.SELF_REPORTED, VerificationLevel.CLAIMED):
        verdict.confidence = Confidence.LOW
        if not verdict.cap_rationale or required is None:
            # Marked fitted only when the analyst gave no rationale: then the
            # template is all this run proposes. Otherwise a rationale the
            # operator wrote on the claim still wins at write time.
            verdict._cap_rationale_fitted = not verdict.cap_rationale
            verdict.cap_rationale = (
                "Confidence is capped at low: no source on this claim independently "
                f"addresses {shorten(entity_name, 200)}."
            )
    note = f"verification_level {level} lowered to {new_level.value}: the written sources {reason}"
    if log:
        logger.info("Level fit: %s", note)
    return note


def shorten(text: str, limit: int = 80) -> str:
    """``text`` cut to ``limit`` characters with a trailing "...", so it fits a
    length-limited field such as ``SourceOverride.reason``."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _enum_value(value: object) -> object:
    # Callers pass enums; a parsed file holds their string values.
    return getattr(value, "value", value)


_CAPPED_LEVELS = frozenset({VerificationLevel.CLAIMED.value, VerificationLevel.SELF_REPORTED.value})


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

    On a forced overwrite, the existing ``seo_title`` wins when an operator
    wrote it (it differs from the analyst's last one, recorded as
    ``analyst_record`` in the audit sidecar) and the title is unchanged from
    the analyst's last title (ignoring case and spacing). The existing
    ``takeaway`` wins when the analyst gives none, and when an operator wrote
    it (it differs from the analyst's last one in the record) while the
    verdict is the analyst's last verdict. The existing ``cap_rationale``
    wins when an operator wrote it (it differs from the pipeline's last one in
    the record) while ``verification_level`` and ``confidence`` are both
    unchanged and the level is a capped one (``claimed`` or
    ``self-reported``). With no recorded ``cap_rationale``, the existing one
    wins under the same conditions unless ``cap_rationale_fitted`` says the
    level fit wrote the passed one. Otherwise the passed values are written.
    """
    claim_path = _claim_path_for(entity_ref, entity_name, claim_slug, repo_root)

    if claim_path.exists() and not force:
        raise FileExistsError(
            f"claim file already exists: {claim_path} (pass force=True to overwrite)"
        )

    # On a forced overwrite, an operator may have edited these fields since
    # the last run. The analyst always writes a seo_title, so an operator's
    # seo_title is kept while the title it shortens is unchanged. A cap_rationale names
    # the confidence cap, so an operator's is kept only on a capped level, while the
    # level and confidence it explains are both unchanged. A takeaway is kept when the analyst gives
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
    # the operator's and wins even over the level fit's. Without one, the fit's
    # rationale wins, since the text on disk may be a stale analyst one.
    if "cap_rationale" in record:
        operator_cap_rationale = existing_cap_rationale != record["cap_rationale"]
    else:
        operator_cap_rationale = not cap_rationale_fitted
    if (
        existing_cap_rationale
        and operator_cap_rationale
        and _enum_value(verification_level) in _CAPPED_LEVELS
        and _enum_value(verification_level) == _enum_value(existing_fm.get("verification_level"))
        and _enum_value(confidence) == _enum_value(existing_fm.get("confidence"))
    ):
        cap_rationale = existing_cap_rationale

    fm = {
        "title": title,
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
) -> dict:
    """The sidecar ``analyst_record`` block after an analyst's write.

    It holds what the analyst proposed, never a value a keep rule left on
    disk, so the next write can tell the operator's text from the analyst's.
    A field the analyst left out keeps its ``previous`` value: title and
    seo_title change together, since the seo_title shortens that title.
    ``cap_rationale`` is the value after the level fit, and None is recorded
    too: on a capped level a claim then has no pipeline rationale to match.
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
    return record


def analyst_record_for(verdict: "VerdictAssessment") -> dict:
    """``updated_analyst_record`` for a verdict as written, for a claim's first sidecar."""
    return updated_analyst_record(
        verdict.title, verdict.seo_title, verdict=verdict.verdict, takeaway=verdict.takeaway,
        cap_rationale=verdict.cap_rationale,
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
    """
    result: list[dict] = []
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
            }
        )

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
        result.append(entry)
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
    It also wins over a new snapshot: approval, archiving and ``dr publish``
    never leave a block on a published claim, so a published claim with one
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


def mark_refreshed(
    claim_path: Path,
    previous_publication: dict | None,
    current_source_ids: list[str] | None,
    ran_at: datetime.datetime,
) -> None:
    """Record in the sidecar that a claim is rewritten and awaits re-approval.

    For a rewrite that leaves the rest of the sidecar alone (``dr
    step-analyze --write``): resets ``human_review`` and, for a published
    claim (``previous_publication``), starts or carries forward the
    ``refresh`` block, as ``_write_audit_sidecar`` does for ``dr
    claim-refresh``, so ``dr review --approve`` asks for a correction when the
    verdict changed. Call it before the claim write.
    """
    sidecar_path = sidecar_path_for(claim_path)
    if not sidecar_path.exists():
        return
    data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"cannot parse sidecar {sidecar_path}")
    data["human_review"] = {"reviewed_at": None, "reviewer": None, "notes": None, "pr_url": None}
    refresh = _refresh_block(data, previous_publication, current_source_ids, ran_at)
    if refresh is not None:
        data["refresh"] = refresh
    sidecar_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


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
    reset_review: bool = False,
    failure: FailureInfo | None = None,
    previous_publication: dict | None = None,
    current_source_ids: list[str] | None = None,
    analyst_record: dict | None = None,
    level_clamp: str | None = None,
    keep_other_models: bool = False,
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

    ``level_clamp`` is the note from ``fit_verdict_to_written_pool``; it
    explains why the claim's level differs from the analyst's.

    ``keep_other_models`` keeps the existing ``models_used`` entries of agents
    this run did not invoke, for a run that rewrites the sidecar without
    rewriting what those agents produced (``dr step-audit --write``).

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
        }
    else:
        audit_block = None

    # Preserve human_review across mid-pipeline reruns, but reset it when the
    # operator explicitly refreshes a claim (reset_review=True). The claim-refresh
    # command sets reset_review=True because a full re-run invalidates prior signoff.
    human_review = {
        "reviewed_at": None,
        "reviewer": None,
        "notes": None,
        "pr_url": None,
    }
    if not reset_review:
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


def set_claim_corrections(claim_path: Path, entries: list[dict]) -> None:
    """Replace the ``corrections`` list in a claim's frontmatter, keeping everything else."""
    fm, body = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    fm["corrections"] = entries or None
    claim_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")


def _write_draft_entity_file(
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
    """Write entity file to research/entities/drafts/{type-dir}/{slug}.md."""
    entity_slug = slugify(entity_name)
    type_dir = _ENTITY_TYPE_DIR.get(entity_type, f"{entity_type.value}s")

    draft_dir = repo_root / "research" / "entities" / "drafts" / type_dir
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"{entity_slug}.md"
    entity_ref = f"drafts/{type_dir}/{entity_slug}"

    fm = _entity_frontmatter(
        entity_name, entity_type, entity_description, website, aliases,
        status="draft", search_hints=search_hints,
        legal_name=legal_name,
        verification_status=verification_status,
        founded=founded,
    )
    body = _entity_body(history_markdown)
    draft_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")
    logger.info("Wrote draft entity: %s", draft_path)
    return entity_ref


def _entity_body(history_markdown: str | None) -> str:
    """Normalize the history markdown to a body string with a trailing newline.

    Strips trailing whitespace per-line so markdownlint MD009 doesn't fire on
    stray spaces the enricher LLM sometimes emits at paragraph ends.
    """
    if not history_markdown:
        return ""
    cleaned = "\n".join(line.rstrip() for line in history_markdown.splitlines())
    return cleaned.rstrip() + "\n"


def update_entity_enrichment(
    entity_path: Path,
    description: str | None = None,
    founded: int | None = None,
    history_markdown: str | None = None,
) -> None:
    """Splice enricher output into an existing entity file in place.

    Preserves every other frontmatter field. ``description`` is overwritten
    only when a non-empty value is supplied — an empty string from the
    enricher means "the inputs did not describe the entity," in which case
    the prior description should win over a worse rewrite. The body is
    overwritten when ``history_markdown`` is non-empty; an empty value
    leaves the existing body alone.
    """
    has_description = bool(description and description.strip())
    has_history = bool(history_markdown and history_markdown.strip())
    if not has_description and founded is None and not has_history:
        return

    text = entity_path.read_text(encoding="utf-8")
    fm, existing_body = parse_frontmatter(text)
    if has_description:
        fm["description"] = description.strip()
    if founded is not None:
        fm["founded"] = founded
    body = _entity_body(history_markdown) if has_history else existing_body
    entity_path.write_text(serialize_frontmatter(fm, body), encoding="utf-8")
    logger.info("Updated entity enrichment: %s", entity_path)
