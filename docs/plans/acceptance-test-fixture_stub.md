# Acceptance test fixture: Anthropic / Claude

**Status**: Stub
**Priority**: v1 (prerequisite for vocab rename pass and for confidence in pipeline-touching work)
**Last updated**: 2026-04-24

A real-LLM, real-entity end-to-end test that verifies the `dr` pipeline produces stable, expected outputs for a known case. Operator selection (Q8): Anthropic / Claude.

## Why now

- The pipeline is approaching maturity but has no known-good regression case.
- Vocab rename pass ([`vocab-rename-pass_stub.md`](vocab-rename-pass_stub.md)) needs this as its safety net.
- Multi-provider POC ([`multi-provider-poc.md`](multi-provider-poc.md)) needs a baseline to compare drift against.

## Goal

A repeatable test that: (1) takes a fixed claim text + Anthropic-or-Claude entity context, (2) runs the full pipeline (researcher → ingestor → analyst → auditor), (3) asserts the output verdict + confidence + sidecar fields fall within an acceptable range. Real LLM calls, real web fetches, real schema validation.

## Open design questions

- **Which claim?** Candidates: `anthropic/publishes-sustainability-report`, `anthropic/existential-safety-score`, `claude/discloses-models-used`. Pick one with stable sources and a clear verdict.
- **Determinism vs tolerance**: LLMs are non-deterministic. What does "passing" mean — exact verdict match, verdict ∈ {true, mostly-true}, or audit-sidecar disagreement-rate within a band? Strictest version is brittle; loosest version doesn't catch much.
- **When does the test break?** Sources update upstream (Anthropic publishes a new sustainability report; the verdict legitimately changes). Is that a test failure or a test refresh? Suggest: failure flags a manual review, not a CI block.
- **Which models?** Test runs against current default (Claude Haiku 4.5). Should it also run against Infomaniak Mistral-Small per multi-provider POC? Probably yes once POC passes.
- **Where in CI?** Manual `inv test.acceptance`? Nightly? Operator-triggered before vocab-rename-pass execution?
- **Cost ceiling?** Each full pipeline run hits real APIs. Cap monthly runs?

## Scope (sketch)

### Stage 1 — Pick and freeze the fixture

- Operator chooses one Anthropic-or-Claude claim.
- Freeze the input: claim text, entity, sources-on-disk-or-discoverable.
- Capture the current verdict, confidence, and audit sidecar as the baseline.

### Stage 2 — Build the test runner

- A pytest test under `pipeline/tests/acceptance/` that loads the fixture, runs the pipeline, and asserts within tolerance.
- Skip-marker so unit-test runs don't trigger it; runs via `inv test.acceptance` or a dedicated invocation.

### Stage 3 — Tolerances

- Decide acceptable verdict range (e.g., {`true`, `mostly-true`} for an Anthropic sustainability claim).
- Confidence band (e.g., not `low`).
- Sidecar invariants (e.g., source count >= 2; `models_used` populated; no error fields).

## Out of scope

- Multi-claim fixture suite. One claim is enough to start; expand if it pays off.
- Performance benchmarking. This catches correctness, not speed.

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-24 | agent (claude-opus-4-7) | initial stub from triage | Scaffolded; entity choice (Anthropic/Claude) per operator answer to Q8 |
