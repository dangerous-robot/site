# Open Issues — Architecture Review

**Created**: 2026-04-23
**Source**: Agent architecture review of `docs/architecture/` and `pipeline/`

Issues surfaced by the architecture review that still need design decisions before implementation. They are not covered by existing implementation plans.

Resolved and moved to plans:
- Claim promotion / `dr review` -> [`docs/plans/completed/claim-promotion-audit-rename-verdicts.md`](../plans/completed/claim-promotion-audit-rename-verdicts.md) §1
- `dr audit` rename (to `dr reassess`) -> same plan §2
- Verdict definitions -> same plan §3

---

## 1. Template screening: what makes a template "applicable"?

**Where**: `pipeline/orchestrator/pipeline.py` `_screen_templates()` (locate by function name; line numbers drift)

`_screen_templates()` is a pass-through stub that marks every core template as applicable for any entity. The architecture doc describes this as a real filtering step: "load templates for entity type -- filter to applicable slugs."

The stub is labeled "MVP" but there is no design for what applicability means. Some concrete cases:

- A hardware company has no "data retention policy" template result to evaluate
- A product entity has no "existential safety score" because that concept applies at the subject or company level
- A topic entity might not have pricing claims

**The question**: What rule determines whether a template applies to a given entity? Options include:
- Entity-type restrictions defined statically in `templates.yaml` (e.g., `applies_to: [company]`)
- LLM-based screening (ask an agent whether the claim text makes sense for this entity's description)
- Operator-driven: `dr onboard --only slug1,slug2` is the escape hatch today; maybe screening stays manual

Until this is decided, `_screen_templates` should stay a stub and the `--only` flag is the workaround for operators who need selective onboarding.

---

## 2. Recheck operational ownership

**Where**: `research-workflow.md` "Maintain" step, `research-flow.md` recheck section

Every claim has a `recheck_cadence_days` field. The docs acknowledge that staleness detection is manual and automated scheduling is a backlog item. However, neither doc defines:

- Who is responsible for checking (`dr lint` flags stale `next_recheck_due`, but who runs `dr lint`?)
- At what cadence the check should happen (weekly? on every PR?)
- Whether stale claims should block merges, generate issues, or just appear in a report

The recheck loop is described architecturally but has no operational owner. Without one, claims will go stale without anyone noticing. The `dr lint` CI integration item in v1.0.0 (shipped as the `lint-content` job) would catch this at merge time, but only for claims that already have a `next_recheck_due` date set. Claims without that field are invisible to the staleness check.

**The question**: Is the intended model (a) cron-based scheduled automation, (b) CI gate that fails on overdue claims, (c) a periodic manual review practice, or (d) something else? This should be documented in `research-workflow.md` even before it is automated.

---

## 3. Pipeline deduplication: coupling tradeoff (resolved)

**Where**: `pipeline/loop/` (the run) and `pipeline/orchestrator/persistence.py` (the writer)

Resolved by RE-AR (One loop, one writer). `dr draft`, `dr claim-refresh` and the per-template loop in `onboard_entity()` all call `loop.run`, which writes nothing, and then the one write function `write_claim_run`. No module under `pipeline/loop/` imports a writer, so a dry run cannot write by a flipped conditional.

Two tests pin the dry-run guarantee in `pipeline/tests/test_loop_probe_safety.py`: `test_dry_run_reaches_no_writer_and_no_archive_save` (no `_write_*` function, no `persist_sources`, no archive save is reached, and `allow_save` is `False`) and `test_dry_run_with_wayback_on_never_asks_for_a_capture`. `test_loop_package_imports_no_writer` in the same file pins the import rule.
