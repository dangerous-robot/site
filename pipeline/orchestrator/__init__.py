"""Orchestrator: owns the claim lifecycle from a draft run to sign-off.

This package implements the **Orchestrator** role. The claim run itself
lives in ``pipeline/loop/``; a run stopped by the post-ingest threshold
(fewer than 4 usable sources, ``below_threshold`` in ``pipeline/loop/run.py``)
writes nothing.

It also owns persistence (claim, sidecar, source, finding and pending-draft
writes, and the ``status`` and ``phase`` frontmatter), review, and the ``dr``
CLI.

See ``AGENTS.md`` ``## How the system works`` for the canonical narrative
covering all roles (Orchestrator, Router, Researcher, Ingestor, Analyst,
Evaluator).

Note: the sibling ``pipeline/auditor/`` package implements the **Evaluator**
role; the directory keeps its old name for v1 (rename deferred per
``docs/plans/v0.1.0-vocab-workflow-landing.md``).
"""
