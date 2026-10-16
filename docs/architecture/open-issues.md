# Open Issues — Architecture Review

**Created**: 2026-04-23
**Source**: Agent architecture review of `docs/architecture/` and `pipeline/`

Issues surfaced by the architecture review that still need design decisions before implementation. They are not covered by existing implementation plans.

Resolved and moved to plans:
- Claim promotion / `dr review` -> [`docs/plans/completed/claim-promotion-audit-rename-verdicts.md`](../plans/completed/claim-promotion-audit-rename-verdicts.md) §1
- `dr audit` rename -> same plan §2; the standalone Evaluator run is `dr draft --claim <ref> --rerun evaluator` (resolved)
- Verdict definitions -> same plan §3

---

## 1. Template screening: what makes a template "applicable"?

**Where**: `dr draft --criterion <slug> --entity <ref>` (`pipeline/orchestrator/cli.py`)

No step screens criteria: the operator chooses which criterion to draft for which entity, one `dr draft --criterion` per claim. The command refuses a criterion whose entity type does not match the entity, but nothing yet decides whether an applicable criterion makes sense for a given entity. Some concrete cases:

- A hardware company has no "data retention policy" template result to evaluate
- A product entity has no "existential safety score" because that concept applies at the subject or company level
- A topic entity might not have pricing claims

**The question**: What rule determines whether a template applies to a given entity? Options include:
- Entity-type restrictions defined statically in `templates.yaml` (e.g., `applies_to: [company]`)
- LLM-based screening (ask an agent whether the claim text makes sense for this entity's description)
- Operator-driven: screening stays manual, `dr draft --criterion` per criterion (today's behaviour)

Until this is decided, screening is the operator's call.

---

## 2. Recheck operational ownership (resolved)

**Where**: `research-workflow.md` "Maintain" step, `research-flow.md` claim lifecycle, `docs/runbook.md`

Resolved by RE-AW (Recheck). `dr recheck --due` re-runs every published claim whose `next_recheck_due` has passed (or, without one, whose `as_of` plus `recheck_cadence_days` has passed) into a pending draft under `research/pending/`, one summary line per claim, and `dr recheck --due --dry-run` lists the due claims with their due dates. The writer sets `next_recheck_due` on every claim write, so the staleness check no longer misses claims that lack it. The live claim stays up until a person promotes the pending draft with `dr review --approve`. The owner is the operator who runs `dr recheck --due`; the procedure for a scheduled job to run it is in `docs/runbook.md` § Scheduled rechecks, and building that job is a backlog item in `docs/UNSCHEDULED.md`.

---

## 3. Pipeline deduplication: coupling tradeoff (resolved)

**Where**: `pipeline/loop/` (the run) and `pipeline/orchestrator/persistence.py` (the writer)

Resolved by RE-AR (One loop, one writer). `dr draft` in every form (including `--claim --force`) calls `loop.run`, which writes nothing, and then the one write function `write_claim_run`. No module under `pipeline/loop/` imports a writer, so a paid dry run (`dr draft --paid-dry-run`) cannot write by a flipped conditional.

Two tests pin the paid dry-run guarantee in `pipeline/tests/test_loop_probe_safety.py`: `test_dry_run_reaches_no_writer_and_no_archive_save` (no `_write_*` function, no `persist_sources`, no archive save is reached, and `allow_save` is `False`) and `test_dry_run_with_wayback_on_never_asks_for_a_capture`. `test_loop_package_imports_no_writer` in the same file pins the import rule.
