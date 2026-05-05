# Source quality robust roadmap

**Status**: Active  
**Created**: 2026-05-05  
**Supersedes**: [`source-quality-roadmap.md`](source-quality-roadmap.md)  
**Driven by**: [`source-quality-agent-review.md`](source-quality-agent-review.md) — strategic critique from three specialized agents  
**Survey**: [`source-quality_survey.md`](source-quality_survey.md) — full signal inventory

This plan defines the minimum, highest-leverage v1 changes that produce verdicts users can trust and understand. The central goal is not metadata coverage — it is verdict quality, reader trust, and honest communication of what the evidence shows. Every item that does not directly serve a reader's ability to evaluate a verdict is a candidate for demotion.

---

## Design decisions

| # | Decision |
|---|----------|
| 1 | **The verification scale measures source-type diversity, not claim validity.** "Independently verified" means independent-origin sources exist — not that independent analysis confirmed the underlying claim. This limitation must be stated explicitly in the architecture doc and analyst instructions. It is not a flaw to paper over; it is a bounded representation of what the system can actually determine. |
| 2 | **The confidence cap requires visible reasoning.** When the cap fires, the analyst writes a one-sentence explanation from a defined template. This rationale appears in the claim narrative and on the display page. A label alone is not sufficient. |
| 3 | **"Original reporting" is a classification threshold, not a category.** Analyst instructions define the test: does this source conduct original analysis of the claim, or does it restate a published number? A secondary source that restates a primary disclosure does not qualify as independent corroboration, regardless of its `source_type` label. The analyst overrides the proxy when this case is detected. |
| 4 | **Display is a user communication task.** The display layer must answer: what is the verdict, what evidence underlies it, and why is confidence what it is. Plain language. No unexplained labels. |
| 5 | **Low confidence with visible rationale serves the reader.** The confidence cap is not lifted based on self-report comprehensiveness. What distinguishes a high-quality self-report from a weak one is the rationale, not the cap level. Publishing "low confidence" with an honest rationale is correct behavior. Amplifying doubt about something true is a display problem, not a cap problem — and is solved by clear rationale, not by loosening the cap. |
| 6 | **`site_trust` and `publisher_group` are deferred to v1.x.** The publisher-groups registry is v1.x scope; without the registry, auto-populating those fields is inconsistent. `independence` is the only new source field in v1. |
| 7 | **`article` first-party defaults to `claimed`, not `self-reported`.** First-party articles are not formal documentation; the analyst may upgrade to `self-reported` only when the piece contains methodology, data, or signed commitments — not marketing framing or announcements. This resolves the open question deferred by the original plan. |
| 8 | **v1 backfill is partial.** Only v1 launch sources (~20–50). Full backfill of 146+ sources is v1.x. |
| 9 | **`docs/architecture/source-quality.md` is the single documentation location** for source ranking methodology, scale definitions, and the independence proxy and its known failure modes. All plans cross-reference it. |

---

## v1 implementation

### 1. Architecture doc

Create `docs/architecture/source-quality.md`. This is the reference that every other v1 item depends on for consistent behavior.

Required content:
- The verification scale: definitions, derivation rules, and explicit statement that the scale measures source-type diversity, not claim corroboration
- Known failure modes of the `source_type → independence` proxy: specifically, secondary sources that restate primary disclosures are classified as independent but add no epistemic weight; the analyst must correct for this case manually when detected
- Derivation rules for `claimed` vs `self-reported` (first-party + kind mapping, including the article default from decision 7)
- Confidence cap rule: fires on `claimed` or `self-reported`; analyst supplies rationale from defined template; lint enforcement
- Publisher registry: what `site_trust` means and what `unknown` means; why `unknown` is not a negative signal (even though registry itself is v1.x)
- Plain-language definitions of all verification scale levels, suitable for reader display

**Files**: `docs/architecture/source-quality.md` (new)

**Rationale for v1**: every other item in this plan depends on a single canonical description of how the system works. Without it, analyst instructions, lint rules, and display copy will drift from each other. Must exist before implementation begins.

---

### 2. Source schema — `independence` field only

Add `independence` to source frontmatter.

**Source frontmatter** (`pipeline/ingestor/models.py`, `src/content.config.ts`):
```yaml
independence: first-party | independent | unknown
```

**Auto-determination** (ingestor, proxied from existing classification):
- `source_type: primary` → `independence: first-party`
- `source_type: secondary` → `independence: independent`
- `source_type: tertiary` → `independence: unknown`

The proxy is a starting classification only. Analyst instructions (item 5) explicitly override it when a secondary source is restating a primary disclosure without conducting original analysis.

**Claim frontmatter** (new field):
```yaml
verification_level: claimed | self-reported | partially-verified | independently-verified | multiply-verified
```

Set by the analyst at verdict time. Added to the Zod schema in `src/content.config.ts`.

`site_trust` and `publisher_group` are not added in v1 (see decision 6).

**Files**: `pipeline/ingestor/models.py`, `src/content.config.ts`

**Rationale for v1**: `independence` is the raw material for `verification_level`, which is the raw material for the confidence cap and display. Nothing downstream works without it.

---

### 3. Partial backfill — `independence` on v1 launch sources

Add `independence` to all v1 launch sources. Use `source_type` as the starting point — mostly mechanical. Spot-check secondary sources for the restatement failure mode (decision 3) and correct misclassifications.

`site_trust` and `publisher_group` are not backfilled in v1.

**Files**: `research/sources/` (per `research/v1-launch-set.md`)

**Rationale for v1**: claims cannot have a valid `verification_level` until their sources have `independence`. Backfill must complete before claim-level work (items 5 and 6) can proceed.

---

### 4. Blocklist extension

Extend `research/blocklist.yaml` with:
- PR wire services: prnewswire.com, businesswire.com, globenewswire.com, accesswire.com
- Known content farms and aggregators that republish without original reporting

The blocklist handles hard drops. Low-trust domains that should score down but not be hard-dropped are a v1.x concern (publisher-groups registry).

**Files**: `research/blocklist.yaml`

**Rationale for v1**: PR wire content is the primary vector for the restatement failure mode described in decision 3. Blocking it at the source reduces the frequency of misclassified "independent" sources that analysts must manually correct.

---

### 5. Analyst instructions and confidence cap

This is the highest-weight v1 item. It is where the constraints from the agent review become executable.

**Update analyst instructions** (`pipeline/analyst/instructions.md`) to:

**Derive `verification_level`**: from the source pool, using `independence` + `kind` per the scale in `docs/architecture/source-quality.md`. First-party `article` defaults to `claimed` (decision 7); upgrade only when the piece contains methodology, data, or signed commitments.

**Apply the restatement test** (constraint C from agent review): for each source classified `independence: independent`, ask: does this source conduct original analysis of the claim, or does it restate a published number? Secondary sources that restate primary disclosures do not count as independent corroboration. Override the auto-assigned `independence` in the verdict reasoning when this is detected. Document the override in the narrative.

**Apply the confidence cap**: when `verification_level` is `claimed` or `self-reported`, cap `confidence` at `low`. The cap is not lifted on the basis of self-report quality or comprehensiveness (decision 5).

**Write cap rationale**: when the cap fires, the analyst writes a one-sentence explanation using one of these templates:
- "Confidence is capped at low — all sources originate from entity documentation; no independent source was found that conducts original analysis of this claim."
- "Confidence is capped at low — the independent sources found restate entity-published numbers without conducting original analysis; no source independently confirms this claim."
- "Confidence is capped at low — sources are informal entity communications (blog posts, announcements); no formal documentation or independent source was found."

The rationale appears in the claim narrative and is surfaced by the display layer (item 7).

**Editorial policy**: when the evidence is absence-of-contradiction (no breach disclosures, no regulatory findings), the analyst notes this explicitly in the narrative: "No contradicting evidence was found; this does not constitute independent confirmation." Claims where absence of evidence is the primary epistemic basis should use `verdict: unverifiable` rather than forcing a positive or negative verdict.

**Pass source context to analyst**: pass `source_type` (primary/secondary/tertiary) into analyst context; note when verdict relies predominantly on secondary or tertiary sources.

**Lint rule**: warn if `confidence: medium|high` and `verification_level: claimed|self-reported`.

**Risk**: this changes existing verdicts. Re-run all v1 claims and review verdict deltas before proceeding to display work (item 7).

**Files**: `pipeline/analyst/instructions.md`, `pipeline/linter/checks.py`

**Rationale for v1**: verdict quality and cap enforcement are the core purpose of this plan. Without explicit analyst instructions, the verification scale is metadata without meaning and the cap is a rule without rationale.

---

### 6. Backfill `verification_level` on v1 launch claims

After item 5, re-run all v1 launch claims to populate `verification_level` and produce cap rationale where needed. Set manually on any that cannot be re-run.

Review verdict deltas against prior state before proceeding.

**Files**: `research/claims/` (v1 launch set)

**Rationale for v1**: the display layer (item 7) requires `verification_level` to be populated on all claims before launch. This must complete before display work can be validated.

---

### 7. Display — claim page, expanded

No panels, no expand/collapse. The display must answer three questions: what is the verdict, what evidence underlies it, and why is confidence what it is.

**Additions to the claim page**:
- **Verification level label with plain-language gloss**: not just the label but a one-line plain-English description of what it means. Example: "Self-reported — the company has published formal documentation; no independent source was found to corroborate this claim."
- **Source count line**: "N sources (X company-published, Y independent)" — computed from `independence` values
- **Cap rationale block**: when `confidence` is capped, display the rationale sentence from the claim narrative. This answers "why does this say low confidence?" in the reader's language.

The gloss text for each verification level comes from `docs/architecture/source-quality.md` (item 1), ensuring the display and architecture doc stay in sync.

Source detail pages unchanged in v1.

**Files**: claim page component(s) in `src/`

**Rationale for v1**: display is where backend investment produces reader-facing value. Without the gloss and cap rationale, the labels are jargon and the confidence signal is uninterpretable. A claims site that doesn't explain its reasoning has not earned reader trust.

---

### 8. Lint for new sources

`dr lint` warns on missing `independence` for sources with `accessed_date` >= 2026-05-01. Grace period exempts older sources.

**Files**: `pipeline/linter/checks.py`

**Rationale for v1**: without a lint gate, `independence` will be omitted on new sources and the verification scale will silently degrade. Lint is cheap enforcement.

---

## v1.x

| Item | Original ref | Notes |
|------|--------------|-------|
| Publisher groups registry | Original item 4 | Maps domains to group name + trust level; bootstraps with v1 launch set + PR wire services; enables `site_trust` and `publisher_group` fields |
| `site_trust` + `publisher_group` fields | Original item 2 (partial) | Depends on registry; omitted from v1 source schema |
| Pre-ingest publisher classification | Original item 6 | Inject `publisher_quality` label into scorer prompt at candidate stage; pairs with existing scorer signals |
| Planner angle guidance | Original item 7 | Add independent coverage angle to planner prompt; cheap but not blocking for launch |
| Ingestor quality signals (`thin_content`, `soft_paywall`) | Original item 8 | Optional fields; adds signal without changing filtering behavior |
| Threshold check improvements | Original item 10 | `low_quality_sources` blocked-reason enum; non-blocking quality warnings in claim sidecar |
| Full source backfill (146+ sources) | Original item 3 (remainder) | Add `independence`, `site_trust`, `publisher_group` to all sources not in v1 launch set |
| `document_type` field on sources | Original design decision 6 | Formalizes the `kind`-to-claimed/self-reported mapping as an explicit schema field |
| `coi_with_subject` + `coi_notes` | `source-trust-metadata.md` | Explicit COI badge; currently implicit from `first-party` |
| `authority` field + author/byline | `source-trust-metadata.md`, do-now 4c | Ingestor schema addition; pairs with authority scoring |
| Agent classifier for trust fields | `source-trust-metadata.md` Phase 6 | Full backfill via agent; manual backfill used in v1 |
| State machine quality gates | `pipeline-state-machine_stub.md` | Block on `verification_level`, not just source count |

---

## Deferred

| Item | Original ref | Notes |
|------|--------------|-------|
| `site_trust` beyond registry | `source-trust-metadata.md` | Manual or agent-classified for unknown publishers; registry must exist first |
| Research trace quality signals | do-now Groups 5a, 5b | Per-query overlap + source type distribution; operator-facing; no direct reader-trust value |
| Full COI detection | `source-trust-metadata.md` | Flagging competitor-funded publications, author financial relationships; requires author/byline data and external lookup |
| Claim stakes / severity signal | Agent review (newspaper editor) | Reader-facing signal for claim importance (trivial vs safety-critical); design not scoped |

---

## Discouraged

| Item | Original ref | Why discouraged |
|------|--------------|-----------------|
| Renaming verification scale levels | Not in original plan | The labels ("independently-verified," "self-reported") are internal derivations; the agent review critique is that they lack plain-language explanation, not that the names are wrong. Decision 4 and item 7 address this by adding gloss text. Renaming the schema values would require backfill across all claims and sources without improving reader comprehension beyond what the gloss achieves. |

---

## Verification

End-to-end checklist for confirming v1 is working:

- [ ] `docs/architecture/source-quality.md` exists and covers: scale definitions, the "diversity not validity" caveat, known proxy failure modes, cap rule and rationale templates, publisher registry intent, plain-language level descriptions
- [ ] Source files accept `independence`; existing files pass validation unchanged; `site_trust` and `publisher_group` are not required
- [ ] `dr lint` warns on missing `independence` for sources accessed after 2026-05-01
- [ ] `dr lint` warns on `confidence: medium|high` when `verification_level` is `claimed` or `self-reported`
- [ ] All v1 launch sources have `independence` populated
- [ ] All v1 launch claims have `verification_level` populated and confidence consistent with the cap rule
- [ ] Claims with capped confidence have a one-sentence rationale in the narrative, matching one of the defined templates
- [ ] Claim pages show: verification level label, plain-language gloss, source count breakdown, cap rationale (when applicable)
- [ ] At least one v1 claim with a secondary source that restates a primary disclosure has a documented analyst override in its narrative
- [ ] PR wire domains are in `research/blocklist.yaml` and are blocked by the ingestor

---

## Plan management

On approval:
- **Create** `docs/architecture/source-quality.md` (item 1)
- **Update** `docs/plans/source-quality-roadmap.md` — add superseded notice pointing here
- **Update** `docs/plans/source-trust-metadata.md` — status to `superseded (v1 scope)`; v1 schema is defined here; full trust block (document_type, authority, coi_with_subject) moves to v1.x
- **Move** `docs/plans/drafts/source-quality-do-now.md` to `docs/plans/completed/` with note: Groups 1+3a shipped in `scorer-quality-signals.md`; Groups 2a, 2b, 3b, 4a, 4b, 6a, 6b, 7a, 8 incorporated here; Groups 5a, 5b deferred to v1.x

Leave unchanged:
- `source-quality_survey.md` — reference doc, not a plan
- `research-quality-ideas.md` — idea backlog, not a plan

---

## Review history

| Date | Reviewer | Scope |
|------|----------|-------|
| 2026-05-05 | human (Brandon) | Original plan: verification scale, confidence cap, publisher registry, schema simplification |
| 2026-05-05 | agents (product advisor, research director, newspaper editor) | Strategic critique: identified three structural gaps and five additions; see `source-quality-agent-review.md` |
| 2026-05-05 | agent (claude-sonnet-4-6) | Rewrite: tightened v1 scope to trust/communication goals; folded A-E recommendations into parent items; resolved article/claimed open question; added editorial policy and restatement-override instructions |
