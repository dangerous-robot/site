# Router and Orchestrator (Item 3 (a) split)

**Status**: Ready
**v1.0.0 surface**: docstring-only naming + threshold-in-Orchestrator (operator confirmed 2026-04-26). Full Router deferred to post-v1.
**Last updated**: 2026-04-26

Implementation of the Router (`pipeline/router/`, new) and explicit naming of the Orchestrator (`pipeline/orchestrator/`, exists implicitly today) per Item 3 (a) of `v0.1.0-vocab-workflow-landing.md`. That plan locked the vocabulary and role split; this stub specifies the code and module-level documentation work.

Filename: `triage-agent.md` (preserves git history; the file documents both the Orchestrator-naming v1 work and the post-v1 Router implementation).

---

## Path correction

The parent landing plan and earlier drafts of this stub referred to `pipeline/audit/`. The actual module is `pipeline/auditor/` (verified 2026-04-26). All references corrected below.

---

## Cross-stub structural decisions (operator + advisor 2026-04-26)

Mirrored from `docs/plans/claim-lifecycle-states.md`:

1. **Threshold check (`>= 2 usable sources`) lives in the Orchestrator**, not the Router. Removes the Router from the v1.0.0 critical path for threshold enforcement.
2. **`phase` is a top-level claim frontmatter field in v1.0.0** (operator BF decision 2026-04-26, reversing the earlier "in-memory only" recommendation). The Router has no role in `phase` writes; the Orchestrator advances `phase` per pipeline step. Schema and Pydantic mirror work is owned by `docs/plans/claim-lifecycle-states.md`.

These structural decisions still allow Router *implementation* to defer cleanly: the Router does not own `phase` or threshold writes regardless of which v1 surface (docstring-only vs full Router) is chosen for this stub.

---

> **Operator-confirmed 2026-04-26**: V1.0.0 surface is docstring-only naming + threshold-in-Orchestrator. Full Router (matching, classification, host sniff, dedup, stale flagging) is deferred to post-v1. The "open scoping question" below is resolved in favor of the docstring-only minimum.

---

## V1.0.0 minimum scope (recommended under stability priority)

The advisor's recommended v1 minimum: name the roles in code, no Router code. The landing plan (line 39, 154) acknowledges the Orchestrator is "implicit in `pipeline/orchestrator/` today" — naming it is a docstring touch.

### Code changes

1. **Orchestrator naming** (`pipeline/orchestrator/__init__.py`): expand the existing one-line docstring to explicitly state the role:

   - Today (`__init__.py:1`): `"Orchestrator: pipeline routing, checkpoints, persistence, CLIs."`
   - Replace with a longer module docstring naming the role and its responsibilities (claim lifecycle, `phase` transitions where they exist, threshold-trigger to halt, queue management). Keep it factual; reference `AGENTS.md` / `glossary.md` for the canonical paragraphs.
2. **`pipeline/orchestrator/pipeline.py:1` docstring update**: today says `"Pipeline: chains researcher -> ingestor -> analyst -> auditor."`. Update to reflect the Orchestrator's role and use current vocabulary (Evaluator instead of auditor, after the vocab + role landing PR lands; before that PR, leave as-is).
3. **Threshold check implementation** lives here per Cross-stub decision 1, but the implementation work is owned by `docs/plans/claim-lifecycle-states.md` § Pipeline. This stub does not duplicate it.

### Documentation alignment (lands via the vocab + role landing PR, not here)

- AGENTS.md `## Agent Roles` table adds Orchestrator + Router rows.
- `docs/architecture/glossary.md` adds Orchestrator + Router to `## Roles`, `## Workflow`, and `## Agent tasks` tables.
- These edits belong to the vocab + role landing PR (see `v0.1.0-vocab-workflow-landing.md` § Files to modify), not to this stub's implementation work. Cross-referenced here so reviewers know where the doc surface lives.

### What v1.0.0 does NOT ship

- No `pipeline/router/` directory.
- No source-to-criterion or source-to-claim matching code.
- No host sniff via the Router (existing blocklist at `pipeline/common/blocklist.py` continues to do its limited host-filter job; see `researcher-host-blocklist.md`).
- No duplicate detection.
- No stale-claim flagging cycle.
- No model-class enforcement runtime check.

The Router as a named role is documented (in the vocab + role landing PR) without shipping Router code. This is consistent with the landing plan's own framing: Router "Documented; implementation deferred via `triage-agent_stub.md`" (line 155).

---

## Full implementation (post-v1)

When the operator schedules Router implementation. Each item below is a self-contained piece of work.

### Router module skeleton

- Create `pipeline/router/` package.
- Module-level docstring naming the role and its responsibilities (small-decision dispatch tier).
- Internal structure: small functions over a single PydanticAI agent. Per the design principle "Small decisions, small models," each Router responsibility runs on the smallest model class; treating each as a function (potentially calling Haiku once) is cheaper and more testable than a long-running agent.

### Router responsibilities (functions, in order of reliability impact)

1. **Source-to-criterion matching**: when a new source enters, match it against active criteria; queue new claim work for matching `entity × criterion` pairs that don't have an existing claim.
2. **Source-to-claim matching**: when a new source enters, match it against existing claims; queue reassessment for affected claims.
3. **Source kind classification (replaces `pipeline/common/source_classification.py` if/when promoted)**: primary / secondary / tertiary classification. Today this lives at `pipeline/common/source_classification.py:1–5` and runs deterministically on publisher + kind. Promoting to a Router function only buys flexibility if the classification needs LLM input; otherwise leave it where it is.
4. **Host sniff (origin classification)**: classify a URL's origin (corporate, news, academic, regulatory, etc.). Today the only origin-aware code is `pipeline/common/blocklist.py` which only filters; classification doesn't exist.
5. **Duplicate detection**: fingerprint (e.g., normalized URL + content hash) to avoid re-ingesting the same source under different URLs. Today no explicit dedup; URL dedup is implicit via `max_sources` cap.
6. **Threshold-trigger to `blocked`**: per Cross-stub decision 1, this stays in the Orchestrator. If the operator decides to move it to the Router, this becomes a Router responsibility and the corresponding code in `docs/plans/claim-lifecycle-states.md` § Pipeline moves accordingly.
7. **Stale-claim flagging**: cadence-based. Whether the Router proactively scans or another scheduled job feeds it candidates is an implementation choice. Today claims have `recheck_cadence_days` and `next_recheck_due` fields but no scanner.

### Small-model discipline

- Model class per Router function: smallest available (current default is Haiku 4.5 per `pipeline/common/models.py:62`).
- Add a runtime assertion or a test that fails if any Router function is configured to use Sonnet/Opus.
- Cross-reference: `AGENTS.md` `## Design principle` (lands via the vocab + role landing PR) is the authority.

### Wiring

- Orchestrator imports from Router for dispatch decisions.
- Existing pipeline (researcher → ingestor → analyst → evaluator) is unchanged; the Router is a control-plane addition, not a pipeline step.

### Pipeline diagram update

- `docs/plans/pipeline-diagram_stub.md` (currently line 14, not 17 as the parent plan states) gets updated to show Router + Orchestrator visually distinct from the linear pipeline (control-plane lanes around the pipeline rather than steps inside it).
- Update belongs to the vocab + role landing PR's edit set (parent plan § Files to modify → `pipeline-diagram_stub.md`).

### `pipeline/auditor/` → `pipeline/evaluator/` rename

- Separate follow-on, not part of this stub.
- Touches code paths and tests; non-trivial. Track via its own plan when scheduled.

---

## Resolved scoping question (operator 2026-04-26)

**Q: V1.0.0 surface — docstring-only (recommended) or full Router?**

**Resolution: docstring-only**, per advisor and operator's stability priority.

- The Orchestrator is implicit today; naming it is cheap (a docstring change).
- Router code is greenfield and adds risk surface.
- The threshold check (the only Router responsibility tied to a v1 reliability requirement) can live in the Orchestrator without architectural compromise (Cross-stub decision 1).
- Deferring Router implementation does not block multi-topic or claim-lifecycle (`blocked` + threshold).

If the operator chooses the full Router instead, scope balloons substantially (six new responsibilities, model-class enforcement, wiring, tests). The landing plan's `../v1.0.0-roadmap.md` checklist additions (line 234) treat full implementation as v1.0.0 scope — that line should be revised to "Orchestrator named; Router documented" if the operator confirms the docstring-only minimum.

---

## Ordering and dependencies

**Must precede this work**:

- Vocab + role landing PR settles the names "Orchestrator", "Router", "Evaluator" in the canonical docs. Before that PR lands, code docstrings would still use "Triage" / "Auditor" terminology.

**This work blocks**:

- Nothing in v1.0.0 if the docstring-only minimum is chosen.
- If the operator chooses full Router: blocks any feature that wants to dispatch on incoming sources (none in v1.0.0 today).

**Independence**:

- `docs/plans/claim-lifecycle-states.md` (`blocked` + threshold): independent if Cross-stub decision 1 holds (Orchestrator owns threshold). Becomes coupled if the operator overrides.
- `docs/plans/multi-topic.md`: completely independent.

---

## Rollback

V1.0.0 minimum (docstring-only):

- Revert the merge commit. Docstrings revert. No behavioral change.

Full Router (post-v1):

- Revert the merge commit. Router module disappears. Existing pipeline runs unchanged because Router was a control-plane addition, not a step.
- Any new module imports added to Orchestrator must be paired-revert-safe (i.e., the Orchestrator code that calls Router must be self-contained in the same merge unit so reverting both together leaves a consistent state).

---

## Verification

V1.0.0 minimum:

```bash
# Module-level docstrings name the roles
rg -n "Orchestrator" pipeline/orchestrator/__init__.py             # at least one hit (currently zero — only "orchestrator" lowercase)
rg -n "claim lifecycle|phase|threshold" pipeline/orchestrator/__init__.py   # at least one hit (the docstring describes responsibilities)

# Threshold check is in Orchestrator (per Cross-stub decision 1)
rg -n "usable_sources|< 2" pipeline/orchestrator/                  # at least one hit (implementation owned by claim-lifecycle stub)

# No premature Router code
test ! -d pipeline/router/                                          # exit 0 (directory does not exist in v1)

# Path corrections (auditor, not audit)
rg -n "pipeline/audit\\b" docs/plans/                               # zero hits or only in completed/historical plans
rg -n "pipeline/auditor" pipeline/                                  # at least one hit (the actual module path)
```

Full Router (post-v1):

```bash
# Module exists
test -d pipeline/router/                                            # exit 0

# Module-level docstrings name the role
rg -n "Router" pipeline/router/__init__.py                          # at least one hit

# Small-model discipline enforced (no frontier models in router source)
rg -n "sonnet|opus" pipeline/router/                                # zero hits in router source (or only in tests)

# Wiring: Orchestrator calls Router for dispatch
rg -n "from .*router import|from pipeline.router" pipeline/orchestrator/   # at least one hit

# Old "Triage" name is gone from code
rg -n "[Tt]riage" pipeline/                                         # zero hits (or only in deprecation comments)
```

---

## Acceptance criteria

V1.0.0 minimum:

1. `pipeline/orchestrator/__init__.py` docstring names the Orchestrator and describes its responsibilities (lifecycle, threshold trigger, queue management).
2. `pipeline/orchestrator/pipeline.py` docstring uses current vocabulary (after the vocab + role landing PR lands).
3. No `pipeline/router/` directory in v1.0.0.
4. Threshold check from `claim-lifecycle-states_stub.md` lands in `pipeline/orchestrator/`, not in `pipeline/router/`.
5. AGENTS.md and glossary.md (after vocab + role landing PR) describe Router as "documented; implementation deferred."

Full Router (post-v1) — covered when scheduled.

---

## Out of scope

- `pipeline/auditor/` → `pipeline/evaluator/` directory rename. Separate follow-on; flagged in vocab item B of the parent plan.
- Model-class enforcement runtime check (depends on full Router; deferred).
- Pipeline diagram SVG/Mermaid render. Owned by `pipeline-diagram_stub.md` itself.

---

## Cross-references

- Parent plan: `docs/plans/v0.1.0-vocab-workflow-landing.md` (Item 3 (a) split, Router/Orchestrator decisions, vocabulary).
- Sibling plan: `docs/plans/claim-lifecycle-states.md`. Cross-stub decision 1 places the threshold check in the Orchestrator; this stub references it but does not own its implementation. Cross-stub decision 2 (`phase` as frontmatter field) is owned there.
- Sibling plan: `docs/plans/multi-topic.md` (independent of this work).
- Deferred-to-post-v1 stub: `docs/plans/drafts/pipeline-to-workflow-rename_stub.md`. If that rename lands first, every `pipeline/...` path in this stub becomes `workflow/...` (including `pipeline/orchestrator/` → `workflow/orchestrator/` and the planned `pipeline/router/` → `workflow/router/`).
- Pipeline diagram: `docs/plans/pipeline-diagram_stub.md` (flow update is part of the vocab + role landing PR; SVG render is owned by the diagram stub itself).
- Source classification today: `pipeline/common/source_classification.py:1–5`.
- Host blocklist today: `pipeline/common/blocklist.py:1–8`.
- Default model: `pipeline/common/models.py:62` (`anthropic:claude-haiku-4-5-20251001`).

---

## Review history


| Date       | Reviewer                | Scope        | Changes                                                                                                                                                                                                                                                                                                                                            |
| ------------ | ------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-25 | agent (stub creation)   | initial      | Stub scaffolded with Router/Orchestrator scope per Item 3 (a) of`v0.1.0-vocab-workflow-landing.md`                                                                                                                                                                                                                                                 |
| 2026-04-26 | agent (claude-opus-4-7) | finalization | Adopted advisor's v1-minimum/full-implementation split: v1 = docstring-only naming + threshold in Orchestrator (per Cross-stub decision 1). Full Router deferred to post-v1. Corrected`pipeline/audit/` → `pipeline/auditor/` path. Surfaced operator decision (docstring-only vs full Router) as the only blocker for an implementation session. |
| 2026-04-26 | brandon                 | partial review | BF annotation on Cross-stub decision 2 (`phase` becomes frontmatter field, not in-memory). Rest of stub flagged as awaiting review. |
| 2026-04-26 | agent (claude-opus-4-7) | applied BF (partial) | Updated Cross-stub decision 2 to reflect `phase` as frontmatter field; added review-pending banner; added cross-reference to `pipeline-to-workflow-rename_stub.md`. V1.0.0 surface (docstring-only vs full Router) remains operator's open decision. |
| 2026-04-26 | agent (light corrections + promotion) | promotion | Ready; moved from drafts/triage-agent_stub.md to docs/plans/triage-agent.md; resolved scoping question to docstring-only minimum per operator BF Q4; cross-references updated to point at promoted siblings (multi-topic.md, claim-lifecycle-states.md). |
