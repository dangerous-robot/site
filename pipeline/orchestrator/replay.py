"""``dr findings --replay``: run an open finding's recorded claim again and close it or link a new one.

A finding records the claim spec, the config and the command of a run that
was abandoned or left a half-claim. A replay runs that claim through the loop
(for ``dr recheck``, the live claim's current spec) with the recorded config
under a new run id and writes what the original command would have written:
a draft for ``dr draft``, a pending draft for ``dr recheck``. A success closes the finding (``closed: {date, by: replay,
note}``); a failure leaves it open and the replay's own finding carries
``replays: <old run id>``. Every replay in one command shares one LLM
semaphore and one source URL index (``orchestrator.recheck.run_batch``).

The CLI helpers are imported inside the functions: ``orchestrator.cli``
imports this module lazily in ``dr findings``.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import click

from common.findings import CONFIG_KEYS, Finding

if TYPE_CHECKING:
    from loop import ClaimSpec, VerifyConfig

# What a replay can reproduce. A recovered, split or partial run wrote its
# claim; a step-analyze or step-audit run re-ran one agent, which a full loop
# run would not reproduce.
REPLAYED_COMMANDS: tuple[str, ...] = ("dr draft", "dr recheck")
REPLAYED_OUTCOMES: tuple[str, ...] = ("abandoned", "half-claim")
_ONE_AGENT_COMMANDS = ("dr step-analyze", "dr step-audit")


class ReplayNotStarted(Exception):
    """A finding whose replay cannot start; the message is the reason printed after ``not replayed:``."""


@dataclass
class ReplayTarget:
    """Where a replay writes.

    ``draft``: ``write_claim_run`` at ``claim_path`` (in place, forced) or,
    when None, at the entity's planned path for ``claim_slug``. ``pending``:
    ``write_pending_recheck`` beside the live claim at ``live_path``.
    """

    kind: Literal["draft", "pending"]
    spec: ClaimSpec
    claim_slug: str
    claim_path: Path | None = None
    create_entity: bool = False
    live_path: Path | None = None
    live_ref: str | None = None
    cadence: int | None = None


def skip_reason(finding: Finding) -> str | None:
    """None when a replay can reproduce the finding's run, else why it is skipped."""
    if finding.command not in REPLAYED_COMMANDS:
        if finding.command in _ONE_AGENT_COMMANDS:
            return f"command {finding.command} runs one agent; not replayed"
        return f"command {finding.command or '-'} is not replayed"
    if finding.outcome not in REPLAYED_OUTCOMES:
        return f"outcome {finding.outcome}: the run wrote its claim; close it with dr findings --close"
    return None


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def replay_target(finding: Finding, repo_root: Path) -> ReplayTarget:
    """The claim spec to replay, and where its replay writes.

    A ``dr draft`` finding replays the spec it recorded. A ``dr recheck``
    finding replays the live claim's spec as ``dr recheck --claim`` builds it
    (``_claim_spec_for``): its current statement and its criterion's topics
    and grading rule, which a run that never started did not record.

    Raises ``ReplayNotStarted`` when the original command would refuse the
    run today: the entity is a company or does not load (a ``dr draft``
    finding), the entity does not load (a ``dr recheck`` finding), the claim
    the finding names is missing or now live (a ``dr draft`` finding), not
    live (a ``dr recheck`` finding), or sits off its entity's path, or a new
    draft's file now exists.
    """
    from common.frontmatter import parse_frontmatter
    from common.models import EntityType
    from common.utils import slugify
    from loop import ClaimSpec
    from orchestrator.cli import _COMPANY_REFUSAL, _claim_spec_for, _live_status, _names_company
    from orchestrator.entity_resolution import ResolvedEntity, parse_entity_ref
    from orchestrator.persistence import planned_claim_path
    from orchestrator.recheck import cadence_days

    record = finding.claim_spec
    statement = record.get("statement")
    entity_ref = record.get("entity")
    if not statement or not entity_ref:
        raise ReplayNotStarted("the finding records no statement or entity")
    if finding.command == "dr draft" and _names_company(entity_ref, repo_root):
        # dr draft refuses a company in every mode; dr recheck does not, so its findings still replay.
        raise ReplayNotStarted(_COMPANY_REFUSAL)

    create_entity = False
    try:
        entity = parse_entity_ref(entity_ref, repo_root)
    except ValueError as exc:
        if (
            finding.command == "dr draft"
            and entity_ref.startswith("subjects/")
            and not (repo_root / "research" / "entities" / f"{entity_ref}.md").exists()
        ):
            # Only dr draft --subject runs on a subject with no file; it writes
            # this minimal record with the claim, as the replay does.
            subject_slug = entity_ref.split("/", 1)[1]
            entity = ResolvedEntity(
                entity_ref=entity_ref,
                entity_name=subject_slug.replace("-", " ").title(),
                entity_type=EntityType.SUBJECT,
                entity_description=statement.strip(),
            )
            create_entity = True
        else:
            raise ReplayNotStarted(f"could not load entity {entity_ref}: {exc}") from exc

    spec = ClaimSpec(
        statement=statement,
        entity=entity,
        criteria_slug=record.get("criteria_slug"),
        topics=list(record.get("topics") or []),
        grading_rule=record.get("grading_rule"),
    )
    claims_root = repo_root / "research" / "claims"
    ref = finding.claim_ref

    def _on_entity_path(path: Path, entity: ResolvedEntity) -> None:
        planned = planned_claim_path(entity.entity_ref, entity.entity_name, path.stem, repo_root)
        if planned.resolve() != path.resolve():
            raise ReplayNotStarted(
                f"{ref} is at {_rel(path, repo_root)}, but its entity {entity.entity_ref} "
                f"writes to {_rel(planned, repo_root)}"
            )

    if finding.command == "dr recheck":
        if not ref:
            raise ReplayNotStarted("the finding records no claim")
        live_path = claims_root / f"{ref}.md"
        if not live_path.exists():
            raise ReplayNotStarted(f"claim file not found: {_rel(live_path, repo_root)}")
        if _live_status(live_path) is None:
            raise ReplayNotStarted(
                f"{ref} is not published or archived; a draft or blocked claim reruns in place "
                f"with dr draft --claim {ref} --force"
            )
        try:
            live_spec = _claim_spec_for(live_path, ref, repo_root)
        except click.UsageError as exc:
            raise ReplayNotStarted(exc.message) from exc
        _on_entity_path(live_path, live_spec.entity)
        fm, _ = parse_frontmatter(live_path.read_text(encoding="utf-8"))
        return ReplayTarget(
            kind="pending", spec=live_spec, claim_slug=live_path.stem,
            live_path=live_path, live_ref=ref, cadence=cadence_days(fm),
        )

    if finding.outcome == "half-claim" or ref:
        # The dr draft --claim <ref> --force path: back to the file the run
        # named. A half-claim records the planned path whether or not its
        # claim file was written, so a missing file is written fresh.
        if not ref:
            raise ReplayNotStarted("the finding records no claim")
        claim_path = claims_root / f"{ref}.md"
        if finding.outcome != "half-claim" and not claim_path.exists():
            raise ReplayNotStarted(f"claim file not found: {_rel(claim_path, repo_root)}")
        status = _live_status(claim_path)
        if status is not None:
            raise ReplayNotStarted(f"{ref} is {status}; dr recheck --claim {ref} writes a pending draft")
        _on_entity_path(claim_path, entity)
        return ReplayTarget(
            kind="draft", spec=spec, claim_slug=claim_path.stem, claim_path=claim_path,
            create_entity=create_entity,
        )

    if spec.criteria_slug:
        _check_criterion(spec, repo_root)
    claim_slug = spec.criteria_slug or slugify(statement)
    planned = planned_claim_path(entity.entity_ref, entity.entity_name, claim_slug, repo_root)
    if planned.exists():
        raise ReplayNotStarted(f"claim file already exists: {_rel(planned, repo_root)}")
    return ReplayTarget(kind="draft", spec=spec, claim_slug=claim_slug, create_entity=create_entity)


def _check_criterion(spec: ClaimSpec, repo_root: Path) -> None:
    """The checks ``dr draft --criterion <slug> --entity <ref>`` makes before any model call.

    A new draft for a criterion runs only while the criterion is still active
    in ``research/templates.yaml`` (not ``inactive: true``), for this kind of entity and, for a subject,
    with this subject listed.
    """
    from common.templates import get_template, load_templates

    slug = spec.criteria_slug
    try:
        template = get_template(load_templates(repo_root), slug)
    except Exception as exc:
        raise ReplayNotStarted(f"criterion {slug}: could not read research/templates.yaml: {exc}") from exc
    if template is None or template.inactive:
        raise ReplayNotStarted(f"criterion {slug}: no active criterion with that slug in research/templates.yaml")
    entity_type = spec.entity.entity_type.value
    if template.entity_type != entity_type:
        raise ReplayNotStarted(
            f"criterion {slug} is a {template.entity_type} criterion; {spec.entity.entity_ref} is a {entity_type}"
        )
    if template.entity_type == "subject" and spec.entity.entity_ref not in template.subjects:
        raise ReplayNotStarted(f"criterion {slug} does not list {spec.entity.entity_ref} in its subjects")


def replay_config(
    finding: Finding, repo_root: Path, agent_models: dict[str, str | None], *, cadence: int | None = None,
) -> VerifyConfig:
    """The recorded config under a new run id; a key the finding lacks keeps the ``VerifyConfig`` default.

    The run id is new every time: a finding written under the old one would
    replace the old finding's file. The per-agent model slots are today's
    (``agent_models``); the default model is the recorded one.
    """
    from common.logging_setup import new_run_id
    from loop import VerifyConfig

    recorded = {key: finding.config[key] for key in CONFIG_KEYS if finding.config.get(key) is not None}
    if "research_origins" in recorded:
        recorded["research_origins"] = list(recorded["research_origins"])
    return VerifyConfig(
        **recorded,
        repo_root=str(repo_root),
        run_id=new_run_id(),
        allow_save=True,
        show_progress=True,
        refetch_cached_older_than_days=cadence,
        **agent_models,
    )


def _chain_from(finding: Finding, by_id: dict[str, Finding]) -> list[Finding]:
    """``finding`` and the open findings it replays, followed transitively; oldest first."""
    chain = [finding]
    seen = {finding.run_id}
    parent = finding.replays
    while parent and parent in by_id and parent not in seen:
        seen.add(parent)
        chain.append(by_id[parent])
        parent = by_id[parent].replays
    return list(reversed(chain))


def replay_order(findings: list[Finding]) -> list[list[Finding]]:
    """Open findings grouped into ``replays:`` chains, each oldest first; chains by their newest finding's date.

    A finding is superseded when another open finding replays it; each chain
    ends at a finding nothing replays (its head). A finding two chains share
    goes with the first.
    """
    open_findings = [f for f in findings if f.closed is None]
    by_id = {f.run_id: f for f in open_findings}
    replayed = {f.replays for f in open_findings if f.replays}
    heads = sorted((f for f in open_findings if f.run_id not in replayed), key=lambda f: (f.date, f.run_id))
    chains: list[list[Finding]] = []
    taken: set[str] = set()
    for head in heads:
        chain = [f for f in _chain_from(head, by_id) if f.run_id not in taken]
        taken.update(f.run_id for f in chain)
        chains.append(chain)
    return chains


def _match(findings: list[Finding], finding_id: str) -> Finding:
    """The finding whose run id is or starts with ``finding_id`` (the same matching as ``close_finding``)."""
    matches = [f for f in findings if f.run_id.startswith(finding_id)]
    exact = [f for f in matches if f.run_id == finding_id]
    if exact:
        matches = exact
    if not matches:
        raise KeyError(finding_id)
    if len(matches) > 1:
        raise ValueError(f"{finding_id} matches {len(matches)} findings: {', '.join(f.run_id for f in matches)}")
    return matches[0]


def _finding_path(root: Path, run_id: str) -> Path | None:
    found = sorted((root / "research" / "findings").glob(f"*/{run_id}.yaml"))
    return found[0] if found else None


def _link(root: Path, old: Finding, config: VerifyConfig, *, failed: bool, step: str) -> str:
    """Point the replay's finding at ``old``; a failed replay that recorded none gets one at ``step``.

    Return the run id of the replay's finding.
    """
    import yaml

    from orchestrator.persistence import write_finding

    path = _finding_path(root, config.run_id)
    if path is not None:
        new = Finding.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))
        if new.replays is None:
            new.replays = old.run_id
            write_finding(new, root)
        return new.run_id
    if failed:
        _write_replay_finding(
            root, old, config, message="the replay wrote nothing and recorded no finding",
            error_class=None, step=step,
        )
    return config.run_id


def _write_replay_finding(
    root: Path, old: Finding, config: VerifyConfig, *, message: str, error_class: str | None, step: str,
) -> None:
    """The finding of a replay whose run raised or that failed without recording one (rule ``replay``)."""
    from common.findings import config_record
    from orchestrator.cli import _record_finding

    error = {"error_type": "run_failed", "message": message}
    if error_class is not None:
        error["error_class"] = error_class
    finding = Finding(
        run_id=config.run_id,
        date=datetime.date.today(),
        command=old.command,
        claim_spec=dict(old.claim_spec),
        claim_ref=old.claim_ref,
        config=config_record(config),
        step=step,
        rule="replay",
        error=error,
        attempts=1,
        outcome="abandoned",
        replays=old.run_id,
    )
    _record_finding(finding, root, command=old.command or "dr draft")


def _failed_step(result) -> str:
    """The step a replay's own finding names: ``research`` when the loop raised or blocked (no step is known), else ``write``."""
    if result is None or getattr(result, "blocked_reason", None) is not None:
        return "research"
    return "write"


def _write_draft(result, target: ReplayTarget, config: VerifyConfig, root: Path, url_index: dict,
                 command: str) -> Path | None:
    """The tail of ``dr draft`` without its report: the claim path written, or None."""
    from orchestrator.cli import _claim_ref, _record_finding, _record_half_claim, _report_unwritable_run
    from orchestrator.persistence import planned_claim_path, write_claim_run

    spec = target.spec
    claim_path = target.claim_path
    existing_ref = _claim_ref(claim_path, root) if claim_path is not None else None
    if result.finding is not None and result.finding.outcome == "abandoned":
        _record_finding(result.finding, root, command=command, claim_ref=existing_ref)
    if not _report_unwritable_run(result):
        return None
    planned = claim_path or planned_claim_path(
        spec.entity.entity_ref, spec.entity.entity_name, target.claim_slug, root,
    )
    try:
        written_path = write_claim_run(
            result, spec, config,
            repo_root=root,
            claim_slug=target.claim_slug,
            force=claim_path is not None,
            target=claim_path,
            url_index=url_index,
            create_entity=target.create_entity,
        )
    except FileExistsError as exc:
        # Another replay in this batch wrote the same path first.
        click.echo(f"Error: {exc}", err=True)
        return None
    except Exception as exc:
        click.echo(f"Error: the claim was not written: {exc}", err=True)
        _record_half_claim(result, spec, config, root, _claim_ref(planned, root), exc, command=command)
        return None
    if result.finding is not None:
        _record_finding(result.finding, root, command=command, claim_ref=_claim_ref(written_path, root))
    return written_path


def replay_findings(ctx: click.Context, repo_root: Path, finding_id: str | None) -> int:
    """Replay one finding (``finding_id``) or every open one; print one line per finding; return the exit code.

    A batch returns 0 unless it failed to start; one finding returns 0 only
    when its replay closed it.
    """
    from common.logging_setup import progress
    from common.models import AGENT_NAMES
    from orchestrator.cli import (
        _check_provider_api_keys,
        _check_search_key,
        _ctx_per_agent_kwargs,
        _write_recheck,
    )
    from orchestrator.persistence import close_finding, load_findings, pending_path_for
    from orchestrator.recheck import run_batch

    root = repo_root
    everything = load_findings(root, include_closed=True)
    open_by_id = {f.run_id: f for f in everything if f.closed is None}

    if finding_id is not None:
        try:
            named = _match(everything, finding_id)
        except KeyError:
            click.echo(f"Error: no finding with id {finding_id}", err=True)
            return 1
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            return 1
        if named.closed is not None:
            click.echo(f"Error: finding {named.run_id} is already closed ({named.closed.get('note')})", err=True)
            return 1
        # A finding an open finding replays is replayed through the newest
        # one, so a success closes the whole chain and leaves none open.
        replayed_by = {f.replays: f for f in open_by_id.values() if f.replays}
        head = named
        seen = {head.run_id}
        while head.run_id in replayed_by and replayed_by[head.run_id].run_id not in seen:
            head = replayed_by[head.run_id]
            seen.add(head.run_id)
        reason = skip_reason(head)
        if reason is not None:
            click.echo(f"{head.run_id}: skipped: {reason}")
            return 1
        chains = [_chain_from(head, open_by_id)]
    else:
        chains = replay_order(list(open_by_id.values()))
        if not chains:
            click.echo("No open findings.")
            return 0

    def _superseded(chain: list[Finding], head: Finding) -> None:
        for f in chain[:-1]:
            click.echo(f"{f.run_id}: skipped: superseded by {head.run_id}")

    agent_models = _ctx_per_agent_kwargs(ctx)
    runnable: list[tuple[list[Finding], ReplayTarget, VerifyConfig]] = []
    for chain in chains:
        head = chain[-1]
        reason = skip_reason(head)
        if reason is not None:
            click.echo(f"{head.run_id}: skipped: {reason}")
            _superseded(chain, head)
            continue
        try:
            target = replay_target(head, root)
        except ReplayNotStarted as exc:
            click.echo(f"{head.run_id}: not replayed: {exc}")
            _superseded(chain, head)
            continue
        runnable.append((chain, target, replay_config(head, root, agent_models, cadence=target.cadence)))

    if not runnable:
        return 1 if finding_id is not None else 0

    # Before any model call: a missing key fails the command, not one replay.
    _check_provider_api_keys({config.model_for(a) for _c, _t, config in runnable for a in AGENT_NAMES})
    for _c, _t, config in runnable:
        _check_search_key(config)

    def _job(chain: list[Finding], target: ReplayTarget, config: VerifyConfig):
        head = chain[-1]
        command = head.command or "dr draft"

        async def _one(sem, url_index: dict) -> str:
            # Looked up at call time, so a test's spy on loop.run sees the call.
            from loop import run

            progress("Replaying finding %s: %s", head.run_id, target.spec.statement)
            # What the replay wrote, as the close note and the summary line name it.
            written: str | None = None
            result = None
            try:
                result = await run(target.spec, config, sem=sem, url_index=url_index)
                if target.kind == "draft":
                    path = _write_draft(result, target, config, root, url_index, command)
                    if path is not None:
                        written = f"wrote {_rel(path, root)}"
                elif _write_recheck(
                    result, target.spec, config, target.live_ref, target.live_path, root, url_index, batch=True,
                ) == "ran":
                    written = f"pending draft {_rel(pending_path_for(target.live_path, root), root)}"
            except Exception as exc:
                # An error outside the loop's steps has no finding of its own,
                # and the next replay still runs.
                click.echo(f"Error: {head.run_id}: the replay failed: {type(exc).__name__}: {exc}", err=True)
                if _finding_path(root, config.run_id) is None:
                    _write_replay_finding(
                        root, head, config, message=str(exc) or type(exc).__name__,
                        error_class=type(exc).__name__, step=_failed_step(result),
                    )
            try:
                new_id = _link(root, head, config, failed=written is None, step=_failed_step(result))
                if written is not None:
                    note = f"replayed as {config.run_id}: {written}"
                    for f in chain:
                        try:
                            close_finding(root, f.run_id, note, by="replay")
                        except (KeyError, ValueError) as exc:
                            click.echo(f"Warning: finding {f.run_id} was not closed: {exc}", err=True)
            except OSError as exc:
                # A findings file that cannot be read or written ends this
                # replay, not the batch: run_batch does not guard its jobs.
                click.echo(f"Error: {head.run_id}: could not update the findings: {exc}", err=True)
                click.echo(f"{head.run_id}: failed (findings not updated: {type(exc).__name__})")
                _superseded(chain, head)
                return "failed"
            if written is None:
                click.echo(f"{head.run_id}: failed (finding {new_id})")
                _superseded(chain, head)
                return "failed"
            line_written = written if written.startswith("wrote ") else f"wrote {written}"
            click.echo(f"{head.run_id}: closed (replay {config.run_id} {line_written})")
            for f in chain[:-1]:
                click.echo(f"{f.run_id}: closed (through {head.run_id})")
            return "closed"

        return _one

    from loop import VerifyConfig

    outcomes = run_batch(
        [_job(chain, target, config) for chain, target, config in runnable],
        llm_concurrency=VerifyConfig.llm_concurrency, repo_root=root,
    )
    if finding_id is not None:
        return 0 if outcomes == ["closed"] else 1
    return 0
