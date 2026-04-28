# Open Issues — Architecture Review

**Created**: 2026-04-23
**Source**: Agent architecture review of `docs/architecture/` and `pipeline/`

Issues surfaced by the architecture review that still need design decisions before implementation. They are not covered by the improvement plan in [`docs/plans/arch-docs-pipeline-improvements.md`](../plans/arch-docs-pipeline-improvements.md).

Resolved and moved to plans:
- Claim promotion / `dr review` -> [`docs/plans/claim-promotion-audit-rename-verdicts.md`](../plans/claim-promotion-audit-rename-verdicts.md) §1
- `dr audit` rename (to `dr reassess`) -> same plan §2
- Verdict definitions -> same plan §3

---

## 1. Template screening: what makes a template "applicable"?

**Where**: `pipeline/orchestrator/pipeline.py` `_screen_templates()` (lines ~513-520)

`_screen_templates()` is a pass-through stub that marks every core template as applicable for any entity. The architecture doc describes this as a real filtering step: "load templates for entity type -- filter to applicable slugs."

The stub is labeled "MVP" but there is no design for what applicability means. Some concrete cases:

- A hardware company has no "data retention policy" template result to evaluate
- A product entity has no "existential safety score" because that concept applies at the sector or company level
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

The recheck loop is described architecturally but has no operational owner. Without one, claims will go stale without anyone noticing. The `dr lint` CI integration item in v0.1.0 would catch this at merge time, but only for claims that already have a `next_recheck_due` date set. Claims without that field are invisible to the staleness check.

**The question**: Is the intended model (a) cron-based scheduled automation, (b) CI gate that fails on overdue claims, (c) a periodic manual review practice, or (d) something else? This should be documented in `research-workflow.md` even before it is automated.

---

## 3. Pipeline deduplication: coupling tradeoff

**Where**: `pipeline/orchestrator/pipeline.py`

`verify_claim()`, `research_claim()`, and the per-template loop in `onboard_entity()` implement the same four-step pipeline (researcher, ingestor, checkpoint, analyst, evaluator) with small variations. The primary variation is whether files are written to disk.

A shared pipeline core with a `persist: bool` flag (or persistence callback) would reduce duplication. The risk is that `dr verify` (no writes, safe for dry-run use) and `dr verify-claim` (file-writing) would share a code path where a single conditional separates the two behaviors. A bug in the conditional could cause `dr verify` to write files unexpectedly.

This is not a blocker for any current work. The existing structure is redundant but safe. Refactoring here should happen only after the v0.1.0 milestone is stable, when the behavior of all three paths is well-tested and the refactor risk is lower.

**The question**: Is there appetite to refactor this before or after v0.1.0? If before, a clear test harness verifying `dr verify` produces zero file writes is a prerequisite.
