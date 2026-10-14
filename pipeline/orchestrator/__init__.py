"""Orchestrator: owns the claim lifecycle from queue to drafted or blocked.

This package implements the **Orchestrator** role. It advances each claim's
``phase`` through ``researching`` -> ``ingesting`` -> ``analyzing`` ->
``evaluating`` and manages the work queue. The claim run itself lives in
``pipeline/loop/``; a run stopped by the post-ingest threshold (fewer than 4
usable sources, ``below_threshold`` in ``pipeline/loop/run.py``) writes nothing.

It also owns checkpoints, persistence (frontmatter writes for ``status``,
``phase``, ``blocked_reason``), and the ``dr`` CLIs.

See ``AGENTS.md`` ``## How the system works`` for the canonical narrative
covering all roles (Orchestrator, Router, Researcher, Ingestor, Analyst,
Evaluator).

Note: the sibling ``pipeline/auditor/`` package implements the **Evaluator**
role; the directory keeps its old name for v1 (rename deferred per
``docs/plans/v0.1.0-vocab-workflow-landing.md``).
"""
