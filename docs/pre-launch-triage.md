# Pre-launch triage — dispatch ledger

Status: dispatch in progress, 2026-04-24

This file replaces an earlier longer triage synthesis with a slim ledger. Goal: delete this file once every row below has a non-empty destination AND the destinations are reachable (plan files exist, roadmap references them, questions are recorded).

---

## Site weaknesses (reader-surface)

| ID | Item | Destination |
|---|---|---|
| S1 | ALPHA banner | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| S2 | Curated launch set, ~20 claims (random; Q10) | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| S3 | COI disclosure | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md); already on v0.1.0-roadmap §7 |
| S4 | `/values` editorial page (Q9) | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| S5 | Surface pipeline diagram on-site | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| S6 | Audit sidecar `models_used` schema + display | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| S7 | Inputs taxonomy on FAQ | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| S8 | Reader-takeaway line under verdict badge | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| S9 | Footer links to `/values` and `/methodology` | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| ST1 | Source trust metadata (4 axes) | [source-trust-metadata_stub.md](plans/source-trust-metadata_stub.md) |
| ST2 | Polarity normalization | [pre-launch-questions.md](pre-launch-questions.md) Q2 |
| ST3 | In-page feedback affordance | [public-feedback.md](plans/public-feedback.md) (v2) |
| ST4 | Page Builder removal (operator: causing confusion) | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| ST5 | Confidence rubric on `/methodology` | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |

## Structural and process problems (operator-process)

| ID | Item | Destination |
|---|---|---|
| P1 | Rename Citation Auditor → citation check | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| P2 | Rename `dr research` → `dr verify-claim` | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| P3 | Document model-tier discipline | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| P4 | Acceptance test fixture (Anthropic/Claude per Q8) | [acceptance-test-fixture_stub.md](plans/acceptance-test-fixture_stub.md) |
| P5 | Roadmap cleanup | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| P6 | Vocab layers reader summary | [pre-launch-quick-fixes.md](plans/pre-launch-quick-fixes.md) |
| PT1 | Operator queue + batch workflow | [operator-queue-batch-workflow_stub.md](plans/operator-queue-batch-workflow_stub.md) (v2) |
| PT2 | Data lifecycle policy | [data-lifecycle-policy_stub.md](plans/data-lifecycle-policy_stub.md) (v2) |
| PT3 | Source-triggered reassessment | UNSCHEDULED.md (v2; operator confirmed v2) |
| PT4 | Vocabulary cohesion deeper pass | [vocab-rename-pass_stub.md](plans/vocab-rename-pass_stub.md) (v1, urgent; prereqs identified) |
| PT5 | Plan sprawl cleanup | rolled into P5 |
| PT6 | Onboarding queue → batch | covered by PT1 stub |

## Future opportunities

| Item | Destination |
|---|---|
| Public feedback backend | [public-feedback.md](plans/public-feedback.md) |
| Public participation forms | [public-participation-forms.md](plans/public-participation-forms.md) |
| Source-triggered reassessment | UNSCHEDULED.md |
| Selective reprocessing | [data-lifecycle-policy_stub.md](plans/data-lifecycle-policy_stub.md) |
| Show-your-work full panel (Q11) | in flight per operator |
| Multi-provider plan (Infomaniak first; GreenPT considered) | [multi-provider.md](plans/multi-provider.md) (Part 1 = v1 urgent; later parts post-v1) |

## Open questions

| ID | Topic | Destination |
|---|---|---|
| Q1 | Reader test scope | [pre-launch-questions.md](pre-launch-questions.md) |
| Q2 | Polarity normalization | [pre-launch-questions.md](pre-launch-questions.md) |
| Q3 | Trust metadata scoring | [pre-launch-questions.md](pre-launch-questions.md) |
| Q4 | Model-tier rubric | [pre-launch-questions.md](pre-launch-questions.md) |
| Q5–Q10 | Closed (operator answered 2026-04-24) | [pre-launch-questions.md](pre-launch-questions.md) §Closed |
| Q11 | Show-your-work scope | [pre-launch-questions.md](pre-launch-questions.md) §Open in long term |
| Q12 | v1 feedback channel | [pre-launch-questions.md](pre-launch-questions.md) |

---

## Deletion criteria

Delete this file when:

- Every row above has a non-empty destination (currently true for all).
- Each linked plan / stub / question doc exists.
- `docs/v1.0.0-roadmap.md` references the v1-bound plans.

Once those conditions are met, this dispatch ledger has served its purpose.
