"""Onboarding, light research and entity enrichment around the claim loop.

The claim run itself (research, ingest, analyse, evaluate) lives in
``pipeline/loop/``; the one writer lives in ``orchestrator/persistence.py``.
``onboard_entity`` runs the loop once per criterion and calls the writer only
for a run that produced an analysis: a blocked or failed run writes nothing.

See ``AGENTS.md`` ``## How the system works`` for the canonical narrative.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from common.blocklist import normalised_host
from common.content_loader import resolve_repo_root
from common.logging_setup import bind_run_id, hr, new_run_id, progress
from common.models import BlockedReason, EntityType, FailureInfo, resolve_model
from common.source_classification import SHARED_PLATFORM_HOSTS
from common.templates import blocked_title_message, get_template, load_templates, render_claim_text, templates_for_entity_type, validate_analyst_title
from common.utils import host_matches, slugify
from loop import ClaimSpec, StepError, VerifyConfig, run
from loop import ingest_urls as _ingest_urls
from loop.run import _NO_URLS_ERR
# Light research's own researcher call: a private loop name, imported here
# only until light research is deleted with onboard.
from loop.research import _research
from orchestrator.checkpoints import AutoApproveCheckpointHandler, CheckpointHandler
from orchestrator.entity_resolution import ResolvedEntity, SearchHints, parse_entity_ref
from orchestrator.persistence import build_source_url_index

logger = logging.getLogger(__name__)


def blocked_reason_label(
    reason_value: str,
    vr_errors: list[str],
    extra: str | None = None,
    failure: FailureInfo | None = None,
) -> str:
    """Format a BlockedReason value with the most informative upstream cause.

    When a structured ``failure`` is available it dominates, producing a
    triage-friendly label that names the error class, the model that ran,
    and the timeout budget it was given:

        analyst_error: TimeoutError on infomaniak:openai/gpt-oss-120b after 120.0s

    Otherwise prefers ``extra`` if provided, then the first non-noise
    message from ``vr_errors``, then the first error, then the bare
    reason. The "no relevant URLs" string is treated as noise because it
    is downstream of the real cause (planner timeout, search failure,
    etc.) and obscures it.
    """
    if failure is not None:
        parts = [failure.error_class]
        if failure.model:
            parts.append(f"on {failure.model}")
        if failure.timeout_s is not None and failure.error_class == "TimeoutError":
            parts.append(f"after {failure.timeout_s:g}s")
        return f"{reason_value}: " + " ".join(parts)
    cause = extra
    if cause is None:
        non_noise = [e for e in vr_errors if not e.startswith(_NO_URLS_ERR)]
        cause = non_noise[0] if non_noise else (vr_errors[0] if vr_errors else None)
    return f"{reason_value}: {cause}" if cause else reason_value


@dataclass
class OnboardResult:
    """Summary of an entity onboarding run."""

    entity_name: str
    entity_type: str
    status: Literal["accepted", "rejected"]
    entity_ref: str | None
    claims_created: list[str] = field(default_factory=list)
    claims_skipped: list[str] = field(default_factory=list)
    claims_failed: list[str] = field(default_factory=list)
    # Each entry is (criterion_slug, reason_label); a blocked claim writes no
    # file. reason_label is the BlockedReason value plus the upstream cause
    # when available, e.g. "analyst_error: research planner timed out".
    claims_blocked: list[tuple[str, str]] = field(default_factory=list)
    templates_applied: list[str] = field(default_factory=list)
    templates_excluded: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Non-fatal advisories surfaced in the report without halting the
    # run. Currently used for "subject onboarded, no template
    # subjects: hit"; reserved for similar advisory rows.
    warnings: list[str] = field(default_factory=list)


@dataclass
class EnrichmentResult:
    """Outcome of running the enricher against one entity.

    ``status``:
        - ``"accepted"``  – operator accepted the draft; entity file updated.
        - ``"rejected"``  – operator rejected the draft; nothing written.
        - ``"failed"``    – no page summary to enrich from, or the enricher
          agent or write step raised; see ``errors``.

    ``founded`` / ``description`` / ``history_markdown`` capture the
    fields that were actually persisted (only populated for ``accepted``).
    """

    entity_ref: str
    entity_name: str
    status: Literal["accepted", "rejected", "failed"]
    founded: int | None = None
    description: str | None = None
    history_markdown: str | None = None
    errors: list[str] = field(default_factory=list)


def _screen_templates(
    entity_description: str,
    templates: list,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Screen templates for applicability. MVP: all core templates pass."""
    applicable = [t.slug for t in templates]
    excluded: list[tuple[str, str]] = []
    return applicable, excluded


@dataclass(frozen=True)
class LightResearchBundle:
    """Shared input for the entity verifier and enricher agents.

    ``raw_description`` is the untightened webpage summary; the enricher
    produces the tightened one-sentence ``description``. ``fetch_errors``
    says why no summary was collected (fetch, search or ingest failures),
    so callers that refuse to enrich can report the reason.
    """

    entity_name: str
    entity_type: EntityType
    raw_description: str
    entity_website: str | None
    probe_excludes: list[str]
    fetch_errors: list[str] = field(default_factory=list)

    @property
    def has_page_summary(self) -> bool:
        """Whether a page summary was collected. Without one the enricher
        could only write from model memory, so callers skip it."""
        return bool(self.raw_description.strip())


def _describe_step_error(e: StepError) -> str:
    return f"{e.url or '-'}: {e.error_type}: {e.message}"


async def gather_light_research(
    entity_name: str,
    entity_type: EntityType,
    cfg: "VerifyConfig",
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    seed_url: str | None = None,
) -> LightResearchBundle:
    """Run the orchestrator's light-research pass and return a bundle.

    Errors during search/fetch/probe are non-fatal so onboarding can still
    proceed with whatever signals were collected; search and fetch errors
    are returned in ``fetch_errors``. Returns the raw webpage summary; the
    enricher produces the tightened one-sentence ``description``.
    """
    raw_description = ""
    entity_website: str | None = None
    probe_excludes: list[str] = []
    fetch_errors: list[str] = []

    try:
        if seed_url:
            url = seed_url if seed_url.startswith(("http://", "https://")) else f"https://{seed_url}"
            entity_website = url
            logger.info("Light research: ingesting seed URL %s", url)
            source_files, ingest_errors = await _ingest_urls(
                client, [url], cfg, sem, archive=False,
            )
            fetch_errors.extend(_describe_step_error(e) for e in ingest_errors)
        else:
            query = f"{entity_name} official website"
            light_ro = await _research(client, entity_name, query, cfg, sem)
            # Only an http(s) URL may become the entity's website link on the site.
            urls = [u for u in light_ro.urls if u.startswith(("http://", "https://"))]
            if urls:
                entity_website = urls[0]
                source_files, ingest_errors = await _ingest_urls(
                    client, urls[:1], cfg, sem,
                    prefetched_bodies=light_ro.prefetched_bodies,
                    archive=False,
                )
                fetch_errors.extend(_describe_step_error(e) for e in ingest_errors)
            else:
                source_files = []
                fetch_errors.extend(
                    _describe_step_error(e) for e in light_ro.errors
                )
                if not fetch_errors:
                    fetch_errors.append("search found no website")
        if source_files:
            _src_url, sf = source_files[0]
            raw_description = sf.frontmatter.summary or ""
        # A blank summary with no recorded error happens when the page was
        # ingested with an empty summary, or when an ingest worker raised
        # (``_ingest_urls`` gathers with ``return_exceptions=True``).
        if not raw_description.strip() and not fetch_errors:
            fetch_errors.append(
                f"{entity_website or '-'}: empty_summary: "
                + ("page fetched but summary empty" if source_files
                   else "page not ingested and no error recorded")
            )
        probe_excludes = await _probe_collision_suggestions(
            client, entity_name, entity_website
        )
    except Exception as exc:
        logger.warning("Light research failed: %s", exc)
        fetch_errors.append(f"light research failed: {exc}")

    return LightResearchBundle(
        entity_name=entity_name,
        entity_type=entity_type,
        raw_description=raw_description,
        entity_website=entity_website,
        probe_excludes=probe_excludes,
        fetch_errors=fetch_errors,
    )


# Second-level labels under which country-code domains are registered
# (example.co.uk). No public-suffix list is installed; where this guess is
# wrong (shared hosts such as github.io), two sites look like one, so the
# probe suggests one exclude fewer rather than dropping first-party pages.
_CC_SECOND_LEVEL = frozenset({"ac", "co", "com", "edu", "go", "gov", "ne", "net", "or", "org"})


def _site_domain(host: str) -> str:
    """The registered domain of ``host``, guessed: ``help.viro.app`` gives
    ``viro.app``, ``shop.example.co.uk`` gives ``example.co.uk``."""
    labels = host.split(".")
    keep = 2
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _CC_SECOND_LEVEL:
        keep = 3
    return ".".join(labels[-keep:])


async def _probe_collision_suggestions(
    client: httpx.AsyncClient,
    entity_name: str,
    entity_website: str | None,
) -> list[str]:
    """Probe Brave for the bare entity name; suggest exclude domains on collision.

    Skipped (returns []) when there is no canonical website to compare against.
    Returns up to 3 distinct registered domains that appear in the top results
    and are not under the canonical host's own site domain (``_site_domain``)
    or a shared platform (``SHARED_PLATFORM_HOSTS``).
    Failures are non-fatal: the probe is best-
    effort disambiguation, not a gate.
    """
    if not entity_website:
        return []
    canon = normalised_host(entity_website)
    if not canon:
        return []
    try:
        from researcher.agent import search_brave
        results = await search_brave(client, entity_name, max_results=8)
    except Exception as exc:
        logger.warning("Collision probe failed: %s", exc)
        return []
    counts: Counter[str] = Counter()
    for r in results[:5]:
        host = normalised_host(r.get("url", "") or "")
        if not host:
            continue
        # Anything under the entity's own site domain (viro.app, help.viro.app
        # for ai.viro.app): excluding one would drop first-party pages, since
        # the blocklist also matches subdomains.
        if _site_domain(host) == _site_domain(canon):
            continue
        # LinkedIn, the App Store and the like host the entity's own account
        # as readily as a collider's, so a whole-host exclude is never right.
        if any(host_matches(host, shared) for shared in SHARED_PLATFORM_HOSTS):
            continue
        counts[host] += 1
    suggestions = [host for host, _ in counts.most_common(3)]
    if suggestions:
        logger.info(
            "Collision probe for %r: canonical=%s, suggesting excludes=%s",
            entity_name, canon, suggestions,
        )
    return suggestions


def _merge_search_hints(
    cli_include: list[str] | None,
    cli_exclude: list[str] | None,
    probe_excludes: list[str],
) -> SearchHints | None:
    """Combine operator-supplied + probe-suggested hints.

    Returns None when nothing is set so the entity frontmatter can omit the key.
    Order is preserved per source; duplicates dropped.
    """
    include = _dedup(cli_include or [])
    exclude = _dedup((cli_exclude or []) + list(probe_excludes))
    if not include and not exclude:
        return None
    return SearchHints(include=include, exclude=exclude)


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        s = item.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


async def enrich_entity(
    entity_ref: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
) -> EnrichmentResult:
    """Re-run the enricher against an existing entity file.

    Loads the entity, runs ``gather_light_research``, calls the
    enricher agent, surfaces the draft via the ``review_entity_enrichment``
    checkpoint, and on accept splices ``founded`` / ``description`` /
    ``history_markdown`` into the file in place. Other fields
    (aliases, parent_company, search_hints, etc.) are preserved untouched.

    Refuses (status ``failed``, nothing written) when light research
    collected no page summary. Only ``dr entity-enrich`` calls this
    helper; ``onboard_entity`` runs its own enricher step with the same
    refusal.
    """
    from common.models import resolve_model
    from orchestrator.entity_resolution import parse_entity_ref
    from orchestrator.persistence import update_entity_enrichment
    from researcher.entity_enricher import (
        build_entity_enricher_prompt,
        entity_enricher_agent,
    )

    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        cfg.repo_root = str(resolve_repo_root())
    repo_root = Path(cfg.repo_root)
    gate = checkpoint or AutoApproveCheckpointHandler()

    try:
        resolved = parse_entity_ref(entity_ref, repo_root)
    except ValueError as exc:
        return EnrichmentResult(
            entity_ref=entity_ref,
            entity_name=entity_ref,
            status="failed",
            errors=[f"could not load entity: {exc}"],
        )

    entity_path = (
        repo_root / "research" / "entities" / f"{entity_ref}.md"
    )

    sem = asyncio.Semaphore(cfg.llm_concurrency)
    with bind_run_id(cfg.run_id):
        logger.info("enrich_entity entry: ref=%s", entity_ref)

        # Phase A (shared with onboard_entity): light research.
        async with httpx.AsyncClient() as client:
            bundle = await gather_light_research(
                resolved.entity_name,
                resolved.entity_type,
                cfg,
                sem,
                client,
                seed_url=resolved.website,
            )

        # Auto-approve would persist a model-memory guess as fact.
        if not bundle.has_page_summary:
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="failed",
                errors=[
                    "not enriched: light research collected no page summary",
                    *bundle.fetch_errors,
                ],
            )

        # Phase C: enricher agent.
        prompt = build_entity_enricher_prompt(bundle)
        try:
            with entity_enricher_agent.override(
                model=resolve_model(cfg.model_for("researcher")),
            ):
                run_res = await asyncio.wait_for(
                    entity_enricher_agent.run(prompt),
                    timeout=cfg.research_timeout_s,
                )
            draft = run_res.output
        except Exception as exc:
            logger.warning("Enricher failed: %s", exc)
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="failed",
                errors=[f"enricher failed: {exc}"],
            )

        decision = await gate.review_entity_enrichment(
            resolved.entity_name, draft,
        )
        if decision == "reject":
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="rejected",
            )

        try:
            update_entity_enrichment(
                entity_path,
                description=draft.description,
                founded=draft.founded,
                history_markdown=draft.history_markdown,
            )
        except Exception as exc:
            logger.warning("Entity write failed: %s", exc)
            return EnrichmentResult(
                entity_ref=entity_ref,
                entity_name=resolved.entity_name,
                status="failed",
                errors=[f"write failed: {exc}"],
            )

    return EnrichmentResult(
        entity_ref=entity_ref,
        entity_name=resolved.entity_name,
        status="accepted",
        founded=draft.founded,
        description=draft.description,
        history_markdown=draft.history_markdown,
    )


async def onboard_entity(
    entity_name: str,
    entity_type: str,
    config: VerifyConfig | None = None,
    checkpoint: CheckpointHandler | None = None,
    seed_url: str | None = None,
    only: list[str] | None = None,
    entity_ref: str | None = None,
    search_hints_include: list[str] | None = None,
    search_hints_exclude: list[str] | None = None,
) -> OnboardResult:
    """Onboard an entity by running claim templates through the research pipeline.

    1. Light research to gather entity context
    2. Screen templates (deterministic MVP, LLM screening TBD)
    3. Checkpoint for operator review
    4. Per-template research pipeline (sequential; parallelism TBD per orchestrator config)
    5. Write entity file
    6. Return OnboardResult summary
    """
    from orchestrator.persistence import (
        _claim_dir_for,
        _write_draft_entity_file,
        _write_entity_file,
        entity_ref_for,
        write_claim_run,
    )

    cfg = config or VerifyConfig()
    if not cfg.repo_root:
        cfg.repo_root = str(resolve_repo_root())

    gate = checkpoint or AutoApproveCheckpointHandler()
    repo_root = Path(cfg.repo_root)
    et = EntityType(entity_type)
    # One semaphore shared across light research AND all per-template loop runs.
    sem = asyncio.Semaphore(cfg.llm_concurrency)

    result = OnboardResult(
        entity_name=entity_name,
        entity_type=entity_type,
        status="accepted",
        entity_ref=None,
    )

    # A ref names a hand-written entity file. That file, not the enricher's
    # draft, is what the analyst and auditor are told is authoritative, and
    # its website seeds light research so the collision probe compares
    # against the entity's real domain rather than a search hit.
    file_entity: ResolvedEntity | None = None
    if entity_ref is not None:
        try:
            file_entity = parse_entity_ref(entity_ref, repo_root)
        except ValueError as exc:
            result.status = "rejected"
            result.errors.append(f"could not load entity: {exc}")
            return result
        if seed_url is None:
            seed_url = file_entity.website

    with bind_run_id(cfg.run_id):
        logger.info(
            "onboard_entity entry: name=%s type=%s seed_url=%s",
            entity_name,
            entity_type,
            seed_url,
        )

        # Phase A: Light research for entity context
        hr()
        logger.info("Onboard phase A: light research for %s", entity_name)
        async with httpx.AsyncClient() as client:
            bundle = await gather_light_research(
                entity_name, et, cfg, sem, client, seed_url=seed_url,
            )
        entity_website = bundle.entity_website
        probe_excludes = bundle.probe_excludes

        # Phase B: verifier — gate against name collisions before the
        # enricher burns compute on the wrong entity.
        # ``verified`` proceeds to Phase C with the default
        # ``verification_status`` (verified). ``needs-disambiguation``
        # surfaces candidates to the operator; ``reject`` halts the run
        # with the candidates in errors, ``accept`` uses the first
        # candidate, a free-text ``str`` renames to that pick. The
        # ``unverified`` outcome reuses the same checkpoint with the
        # two ``verification_status`` enum values as candidates; the
        # operator's pick becomes the persisted status.
        from researcher.entity_verifier import (
            build_entity_verifier_prompt,
            entity_verifier_agent,
        )

        verification_status: str | None = None
        try:
            prompt = build_entity_verifier_prompt(bundle)
            with entity_verifier_agent.override(
                model=resolve_model(cfg.model_for("researcher")),
            ):
                vr_run = await asyncio.wait_for(
                    entity_verifier_agent.run(prompt),
                    timeout=cfg.research_timeout_s,
                )
            outcome = vr_run.output
        except Exception as exc:
            logger.warning(
                "Verifier failed; proceeding without disambiguation gate: %s",
                exc,
            )
            outcome = None

        if outcome is not None and outcome.status == "needs-disambiguation":
            decision = await gate.review_entity_disambiguation(
                entity_name, list(outcome.candidates),
            )
            if decision == "reject":
                result.status = "rejected"
                cands = ", ".join(outcome.candidates) or "(none)"
                result.errors.append(
                    f"verifier flagged needs-disambiguation; candidates: {cands}"
                )
                return result
            if decision == "accept":
                if outcome.candidates:
                    entity_name = outcome.candidates[0]
                    result.entity_name = entity_name
            elif isinstance(decision, str):
                entity_name = decision
                result.entity_name = entity_name
            # Re-run light research under the operator-picked name so
            # downstream prompts (enricher, scorer, analyst) align with
            # the resolved entity rather than the original ambiguous one.
            async with httpx.AsyncClient() as client:
                bundle = await gather_light_research(
                    entity_name, et, cfg, sem, client, seed_url=seed_url,
                )
            entity_website = bundle.entity_website
            probe_excludes = bundle.probe_excludes
        elif outcome is not None and outcome.status == "unverified":
            statuses = ["unverified-startup", "unverified-other"]
            decision = await gate.review_verification_status(
                entity_name, entity_website, outcome.reasoning, statuses,
            )
            if decision in statuses:
                verification_status = decision
            else:
                # "reject", or a value outside the schema enum: never
                # write a non-schema verification_status.
                result.status = "rejected"
                result.errors.append(
                    "verifier flagged unverified; operator declined to "
                    "pick a verification_status"
                    if decision == "reject"
                    else f"verifier flagged unverified; operator pick "
                    f"{decision!r} is not a valid verification_status"
                )
                return result

        # Phase C: enricher (operator-review checkpoint)
        # The enricher subsumes the previous standalone tightening agent:
        # ``EnrichmentDraft.description`` is the new one-sentence
        # description; ``founded`` and ``history_markdown`` populate
        # surfaces the renderer learned about in Step 2.
        from researcher.entity_enricher import (
            build_entity_enricher_prompt,
            entity_enricher_agent,
        )

        enrichment_draft = None
        entity_description = (
            file_entity.entity_description if file_entity is not None
            else bundle.raw_description
        )
        founded_year: int | None = None
        history_markdown: str | None = None
        # Without --force nothing would use a draft for an entity file on disk.
        # Without a page summary the draft could only come from model memory.
        wants_draft = file_entity is None or cfg.force_overwrite
        run_enricher = wants_draft and bundle.has_page_summary
        if wants_draft and not run_enricher:
            progress(
                "Enricher skipped: light research collected no page summary%s",
                "".join(f"\n  ! {e}" for e in bundle.fetch_errors),
            )
        try:
            if run_enricher:
                prompt = build_entity_enricher_prompt(bundle)
                with entity_enricher_agent.override(
                    model=resolve_model(cfg.model_for("researcher")),
                ):
                    run_res = await asyncio.wait_for(
                        entity_enricher_agent.run(prompt),
                        timeout=cfg.research_timeout_s,
                    )
                enrichment_draft = run_res.output
        except Exception as exc:
            logger.warning(
                "Enricher failed; falling back to raw page summary: %s", exc
            )

        if enrichment_draft is not None:
            decision = await gate.review_entity_enrichment(
                entity_name, enrichment_draft,
            )
            if decision == "accept":
                # Empty description means the enricher judged the inputs
                # not to describe the entity — keep the raw summary
                # rather than ship a blank field through the writer.
                if enrichment_draft.description.strip():
                    entity_description = enrichment_draft.description.strip()
                founded_year = enrichment_draft.founded
                history_markdown = (
                    enrichment_draft.history_markdown
                    if enrichment_draft.history_markdown
                    and enrichment_draft.history_markdown.strip()
                    else None
                )
            else:
                logger.info("Enricher draft rejected; keeping raw summary")

        # A name-based run over an entity file on disk has no file_entity;
        # with no page summary, the file's description stands in for the
        # blank one in screening, the checkpoint and the analyst.
        if file_entity is None and not bundle.has_page_summary:
            try:
                entity_description = parse_entity_ref(
                    entity_ref_for(entity_name, et), repo_root,
                ).entity_description or ""
            except ValueError:
                pass

        merged_search_hints = _merge_search_hints(
            search_hints_include, search_hints_exclude, probe_excludes,
        )
        if probe_excludes:
            progress(
                "Name-collision probe suggested excludes: %s",
                ", ".join(probe_excludes),
            )

        # Step 2: Template screening
        hr()
        logger.info("Onboard step 2: screening templates")
        all_templates = load_templates(repo_root)
        onboard_entity_slug: str | None = None
        if entity_type == "subject" and entity_ref and "/" in entity_ref:
            onboard_entity_slug = entity_ref.split("/", 1)[1]
        elif entity_type == "subject":
            from common.utils import slugify as _slugify
            onboard_entity_slug = _slugify(entity_name)
        typed_templates = templates_for_entity_type(
            all_templates, entity_type, entity_slug=onboard_entity_slug
        )

        if not typed_templates:
            # Subjects without a matching ``subjects:`` entry are
            # legitimate first-class onboards — the entity file should
            # still land. Emit a warning row and fall through so the
            # entity gets verified, enriched, and persisted with zero
            # claims fanned out. Company / product have no per-entity
            # template gating, so an empty set there is still an error.
            if entity_type == "subject":
                slug_for_warning = onboard_entity_slug or slugify(entity_name)
                result.warnings.append(
                    f"No template's subjects: list references "
                    f"subjects/{slug_for_warning}; "
                    f"entity will be onboarded with zero claims."
                )
            else:
                result.errors.append(
                    f"No core templates found for entity_type={entity_type}"
                )
                result.status = "rejected"
                return result

        applicable_slugs, excluded = _screen_templates(entity_description, typed_templates)

        if only:
            unknown = [s for s in only if s not in {t.slug for t in typed_templates}]
            if unknown:
                result.errors.append(
                    f"Unknown template slug(s) for entity_type={entity_type}: {', '.join(unknown)}"
                )
                result.status = "rejected"
                return result
            applicable_slugs = [s for s in applicable_slugs if s in set(only)]

        result.templates_excluded = excluded

        # Step 3: Checkpoint
        hr()
        logger.info("Onboard step 3: checkpoint review")
        decision = await gate.review_onboard(
            entity_name, entity_type, applicable_slugs, excluded,
            entity_description=entity_description,
        )

        # Per-call ``verification_status`` only flows through when the
        # verifier returned ``unverified`` and the operator picked an
        # enum value. ``verified`` (the default) leaves frontmatter
        # absent of the field, matching ``entity-metadata-surface``.
        write_kwargs: dict = {}
        if verification_status is not None:
            write_kwargs["verification_status"] = verification_status

        if decision == "reject":
            result.status = "rejected"
            draft_ref = _write_draft_entity_file(
                entity_name=entity_name,
                entity_type=et,
                entity_description=entity_description,
                repo_root=repo_root,
                website=entity_website,
                search_hints=merged_search_hints,
                founded=founded_year,
                history_markdown=history_markdown,
                **write_kwargs,
            )
            result.entity_ref = draft_ref
            return result

        if isinstance(decision, list):
            applicable_slugs = decision

        result.templates_applied = applicable_slugs

        if entity_ref is None:
            entity_ref = _write_entity_file(
                entity_name=entity_name,
                entity_type=et,
                entity_description=entity_description,
                repo_root=repo_root,
                website=entity_website,
                search_hints=merged_search_hints,
                founded=founded_year,
                history_markdown=history_markdown,
                **write_kwargs,
            )
        result.entity_ref = entity_ref

        # _write_entity_file early-returns on existing files. When --force
        # is in play and the enricher produced a draft this run, splice
        # it into the existing file so onboard --force actually persists
        # the new founded / description / history rather than dropping
        # them on the floor. Spares a redundant Phase A + Phase C in the
        # CLI's `enrich_entity` follow-up.
        if cfg.force_overwrite and enrichment_draft is not None:
            from orchestrator.persistence import update_entity_enrichment
            entity_path = (
                repo_root / "research" / "entities" / f"{entity_ref}.md"
            )
            if entity_path.exists():
                update_entity_enrichment(
                    entity_path,
                    description=entity_description,
                    founded=founded_year,
                    history_markdown=history_markdown,
                )

        # Without this resolved entity, the just-persisted search_hints,
        # founded year, and verification_status would not reach the
        # per-template researcher on the run that wrote them.
        if file_entity is not None:
            # Re-read: --force may have just spliced an enrichment into it.
            on_disk = parse_entity_ref(entity_ref, repo_root)
            file_hints = on_disk.search_hints or SearchHints()
            onboard_resolved_entity = dataclasses.replace(
                on_disk,
                search_hints=_merge_search_hints(
                    list(file_hints.include) + list(search_hints_include or []),
                    list(file_hints.exclude) + list(search_hints_exclude or []),
                    probe_excludes,
                ),
                verification_status=verification_status or on_disk.verification_status,
            )
        else:
            onboard_resolved_entity = ResolvedEntity(
                entity_ref=entity_ref,
                entity_name=entity_name,
                entity_type=et,
                entity_description=entity_description,
                website=entity_website,
                search_hints=merged_search_hints,
                founded=founded_year,
                verification_status=verification_status,
            )

        # Step 5: Per-template research pipeline. Each template gets its own
        # run_id so the per-claim agent runs (researcher/ingestor/analyst/
        # auditor) in the loop run group cleanly under one id. Token-usage
        # records inherit this id via cfg.run_id.
        onboard_url_index = build_source_url_index(repo_root)
        total = len(applicable_slugs)
        hr()
        logger.info("Onboard step 4: per-template research (%d templates)", total)
        for idx, slug in enumerate(applicable_slugs, 1):
            iter_cfg = dataclasses.replace(cfg, run_id=new_run_id())
            with bind_run_id(iter_cfg.run_id):
                progress("[%d/%d] Researching: %s ...", idx, total, slug, glyph="▶")
                template = get_template(all_templates, slug)
                if not template:
                    progress("[%d/%d] ERROR: template not found: %s", idx, total, slug)
                    # Invariant: every entry in result.claims_failed must
                    # have at least one matching entry in result.errors of
                    # the form f"{slug}: <reason>". The CLI renders them as
                    # a unified "Failed:" block; an unattributed failure
                    # would silently disappear from operator output.
                    result.errors.append(f"{slug}: template not found")
                    result.claims_failed.append(slug)
                    continue

                claim_text = render_claim_text(template, entity_name)
                logger.info("Onboard: researching template %s -> %s", slug, claim_text)

                # Skip before running the pipeline if a claim file already
                # exists for this entity + criterion. Avoids duplicate claims
                # and wasted pipeline compute on re-onboards.
                existing_claim_path = (
                    _claim_dir_for(entity_ref, entity_name, repo_root) / f"{slugify(slug)}.md"
                )
                if existing_claim_path.exists() and not iter_cfg.force_overwrite:
                    progress("[%d/%d] Skipped (exists): %s", idx, total, slug)
                    result.claims_skipped.append(str(existing_claim_path.relative_to(repo_root)))
                    continue

                try:
                    spec = ClaimSpec(
                        statement=claim_text,
                        entity=onboard_resolved_entity,
                        criteria_slug=slug,
                        topics=list(template.topics or []),
                        grading_rule=template.notes,
                        template=template,
                    )
                    vr = await run(
                        spec, iter_cfg, checkpoint=gate, sem=sem, url_index=onboard_url_index,
                    )

                    if vr.errors:
                        result.errors.extend(f"{slug}: {e}" for e in vr.errors)

                    # A blocked or failed run writes nothing: no placeholder
                    # claim and no source file.
                    reason_label = None
                    if vr.blocked_reason is not None:
                        reason_label = blocked_reason_label(vr.blocked_reason.value, vr.errors, failure=vr.failure)
                    elif vr.analyst_output is None:
                        reason_label = blocked_reason_label(BlockedReason.ANALYST_ERROR.value, vr.errors, failure=vr.failure)
                    else:
                        title = vr.analyst_output.verdict.title
                        title_ok, title_reason = validate_analyst_title(template, entity_name, title)
                        if not title_ok:
                            _body, extra_label = blocked_title_message(
                                template, title, title_reason, BlockedReason.ANALYST_ERROR.value
                            )
                            reason_label = blocked_reason_label(
                                BlockedReason.ANALYST_ERROR.value, vr.errors, extra=extra_label
                            )
                    if reason_label is not None:
                        result.claims_blocked.append((slug, reason_label))
                        progress("[%d/%d] Blocked: %s (%s)", idx, total, slug, reason_label)
                        continue

                    claim_path = write_claim_run(
                        vr, spec, iter_cfg,
                        repo_root=repo_root,
                        claim_slug=slug,
                        force=iter_cfg.force_overwrite,
                        url_index=onboard_url_index,
                    )
                    result.claims_created.append(str(claim_path.relative_to(repo_root)))
                    progress("[%d/%d] Done: %s", idx, total, slug)
                except Exception as exc:
                    progress("[%d/%d] FAILED: %s: %s", idx, total, slug, exc)
                    logger.error("Template %s failed: %s", slug, exc)
                    result.errors.append(f"{slug}: {exc}")
                    result.claims_failed.append(slug)

    return result
