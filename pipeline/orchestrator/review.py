"""Shared `approve_claim` helper used by `dr review` and `dr review-queue`."""
from __future__ import annotations

import datetime
import subprocess
from pathlib import Path
from typing import Literal

import click
import yaml

from common.frontmatter import has_criterion, parse_frontmatter
from common.sidecar import sidecar_path_for
from orchestrator.persistence import set_claim_status

ReviewMode = Literal["review", "approve", "archive"]


def _resolve_reviewer(reviewer: str | None) -> str:
    if reviewer:
        return reviewer
    proc = subprocess.run(
        ["git", "config", "user.email"],
        capture_output=True,
        text=True,
        check=False,
    )
    git_email = proc.stdout.strip()
    if git_email:
        return git_email
    raise click.ClickException(
        "reviewer not provided and git config user.email is empty"
    )


def _preflight_status(claim_path: Path, mode: ReviewMode) -> tuple[str | None, str | None]:
    """Validate the requested transition; return (expected_current, new_status)."""
    if mode == "review":
        return None, None

    try:
        fm, _ = parse_frontmatter(claim_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise click.ClickException(f"claim file not found: {claim_path}") from exc
    except ValueError as exc:
        raise click.ClickException(
            f"malformed frontmatter in {claim_path}: {exc}"
        ) from exc

    current_status = fm.get("status")

    if mode == "approve":
        effective_current = current_status if current_status is not None else "draft"
        if effective_current == "archived":
            raise click.ClickException("cannot approve an archived claim")
        if effective_current == "blocked":
            blocked_reason = fm.get("blocked_reason", "<unset>")
            raise click.ClickException(
                f"Cannot approve blocked claim {claim_path}; "
                f"address blocked_reason={blocked_reason!r} first."
            )
        if effective_current != "draft":
            raise click.ClickException(
                f"claim already {effective_current}; use --archive to retire"
            )
        if not has_criterion(fm):
            raise click.ClickException(
                f"cannot approve {claim_path}: missing `criteria_slug`. "
                "Set it in the claim frontmatter (a slug from research/templates.yaml) "
                "before publishing."
            )
        return current_status, "published"

    # archive
    if current_status is None:
        raise click.ClickException(
            "cannot archive: claim has no status field; publish first or edit the file manually"
        )
    if current_status not in ("published", "blocked"):
        raise click.ClickException(
            f"cannot archive a claim with status {current_status!r}; "
            f"only published or blocked claims can be archived"
        )
    return current_status, "archived"


def approve_claim(
    claim_path: Path,
    *,
    reviewer: str | None = None,
    notes: str | None = None,
    pr_url: str | None = None,
    mode: ReviewMode = "review",
) -> None:
    """Write human-review sidecar; optionally flip claim status.

    ``mode="review"`` updates the sidecar only.
    ``mode="approve"`` additionally flips status ``draft`` → ``published``.
    ``mode="archive"`` additionally flips status ``published|blocked`` → ``archived``.

    The audit sidecar at ``<claim>.audit.yaml`` must already exist. If
    ``reviewer`` is None, falls back to ``git config user.email``. Raises
    ``click.ClickException`` on validation errors so CLI callers surface a
    clean message.
    """
    sidecar_path = sidecar_path_for(claim_path)
    if not claim_path.exists():
        raise click.ClickException(f"claim file not found: {claim_path}")
    if not sidecar_path.exists():
        raise click.ClickException(
            f"no audit sidecar at {sidecar_path}; run the pipeline first"
        )

    expected_current, new_status = _preflight_status(claim_path, mode)
    effective_reviewer = _resolve_reviewer(reviewer)

    sidecar_data = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    sidecar_data["human_review"]["reviewed_at"] = datetime.date.today().isoformat()
    sidecar_data["human_review"]["reviewer"] = effective_reviewer
    sidecar_data["human_review"]["notes"] = notes or ("archived" if mode == "archive" else None)
    sidecar_data["human_review"]["pr_url"] = pr_url

    sidecar_path.write_text(
        yaml.safe_dump(sidecar_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Sidecar is the commit point: if the .md flip raises, the sidecar is
    # already updated and rerunning the same flag re-detects the pre-flip
    # status to complete the transition.
    if new_status is not None:
        try:
            set_claim_status(claim_path, new_status, expected_current)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
