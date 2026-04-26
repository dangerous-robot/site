"""Orchestrator: owns the claim lifecycle from queue to drafted or blocked.

This package implements the **Orchestrator** role. It advances each claim's
``phase`` through ``researching`` -> ``ingesting`` -> ``analyzing`` ->
``evaluating``, manages the work queue, and routes claims to ``status:
blocked`` when the post-ingest threshold (`< 2` usable sources) is breached
via the ``below_threshold`` helper in ``pipeline/orchestrator/pipeline.py``.

It also owns checkpoints, persistence (frontmatter writes for ``status``,
``phase``, ``blocked_reason``), and the ``dr`` CLIs.

See ``AGENTS.md`` ``## How the system works`` for the canonical narrative
covering all roles (Orchestrator, Router, Researcher, Ingestor, Analyst,
Evaluator).

Note: the sibling ``pipeline/auditor/`` package implements the **Evaluator**
role; the directory keeps its old name for v1 (rename deferred per
``docs/plans/v0.1.0-vocab-workflow-landing.md``).
"""
