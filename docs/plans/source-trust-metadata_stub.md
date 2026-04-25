# Source trust metadata

**Status**: Stub
**Priority**: v1 (minimum subset for launch sources); v1.x (full backfill of all sources)
**Last updated**: 2026-04-24

Add structured trust metadata to source files so a skeptical reader can judge source quality without leaving the page.

## Why now

- The skeptical-reader test requires per-source signals beyond the current `kind` enum and `source_type` (primary/secondary/tertiary).
- The current schema doesn't capture authority (subject-matter or institutional), conflicts of interest, or marketing-vs-research disambiguation. These are the four axes operator flagged.
- v1 launch surface is ~20 claims, ~20-50 sources; backfilling that subset is feasible. Full backfill of all 146+ sources is v1.x.

## The four axes

1. **Site trustworthiness** — is the publisher itself trustworthy as a venue? Distinct from authority on the topic.
2. **Document type when from the subject** — marketing post, sustainability report, technical document, regulatory filing, blog.
3. **Authority** — institutional (journalism, academic research, science publishing, tech industry analysis) and topical (authority on this specific claim's subject).
4. **Conflicts of interest** — financial relationships, ownership stakes, paid partnerships, employees writing about employer.

## Open design questions

- **Schema shape**: one composite `trust:` block in source frontmatter with sub-fields, or four flat fields? Composite is more legible; flat is easier to grep. (Existing source schema lives in `pipeline/common/models.py` as `SourceFrontmatter` and in `src/content.config.ts`; both must update in lockstep.)
- **Scoring origin** (Q3 in `docs/pre-launch-questions.md`): operator-only, agent-classified, or hybrid? Each axis has a different best-scorer.
- **Range**: numeric (1-5), categorical (low/medium/high), boolean per axis, or free-text annotations?
- **Backfill strategy**: full backfill before launch, or fill only the launch sources and let `dr lint` warn on missing trust metadata for new sources?
- **Display**: full panel, badge cluster, or expand-on-click? Panel is heavy; badges might be too dense.
- **Effect on verdicts**: should trust metadata weight analyst reasoning (low-trust source carries less weight) or stay informational only? Recommend informational only for v1.

## Scope (sketch)

### Stage 1 — Schema decision

- Pick the four-axis representation (Q3 dependency).
- Add to `SourceFrontmatter` Pydantic model and Zod source schema in lockstep.
- Keep all fields optional initially to avoid breaking existing 146 source files.

### Stage 2 — Display

- Render trust metadata on source detail pages and inline (compact) on claim pages.
- Visual hierarchy: COI flag is the highest-signal axis for skeptics; surface it most prominently.

### Stage 3 — Backfill launch subset

- Manual scoring of ~20-50 sources backing v1 claims.
- Document the scoring criteria as you go; that becomes the v1.x agent classifier's training data.

### Stage 4 — Lint and ongoing capture

- `dr lint` warns on missing trust metadata for newly-added sources.
- Ingestor agent emits a draft classification; operator reviews.

## Out of scope

- Trust metadata on entities (could come later).
- Aggregate trust scores at the claim level (derive on the fly if needed; don't store).

## Cross-references

- Open question Q1 (reader test scope) — confirm trust metadata is part of the launch reader experience.
- Open question Q3 (scoring origin) — must answer before Stage 2.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-24 | agent (claude-opus-4-7) | initial stub from triage | Four-axis structure scaffolded |
