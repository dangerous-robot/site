# Phase 4.2: Narrative-Verdict Consistency Check -- Implementation Plan

**Phase**: 4.2
**Status**: not started
**Depends on**: Phase 4.1 (shared `pipeline/` infrastructure)
**Parent plan**: [agent-pipeline.md](agent-pipeline.md)

## Goal

LLM-assisted validation: feed claim body + sources (without frontmatter verdict/confidence) to an LLM, compare its independent assessment against the actual values. Disagreements surface claims for human review.

---

## 1. Approach

Four stages: **extract**, **bundle**, **assess**, **compare**.

**Extract**: Parse YAML frontmatter separately from Markdown body. The frontmatter contains the "actual" verdict and confidence. The body is the narrative.

**Bundle**: Resolve source slugs from the claim's `sources` array to files under `research/sources/`. Include each source's title, publisher, summary, key quotes, and body. Resolve the entity file for context. The bundle does NOT include the claim's verdict or confidence -- these are withheld from the LLM.

**Assess**: Send the bundle to an LLM via PydanticAI. The LLM returns a structured response: verdict, confidence, reasoning, evidence gaps.

**Compare**: Compare the LLM's assessment against the actual frontmatter values. Flag disagreements by severity.

The key principle is **information asymmetry**: the LLM never sees the actual verdict/confidence.

---

## 2. Directory Structure

Extends the `pipeline/` layout from Phase 4.1:

```
pipeline/
  pyproject.toml          # Shared with 4.1
  common/
    __init__.py
    frontmatter.py        # YAML parse/strip utilities (shared)
    content_loader.py     # Load claim, source, entity files (shared)
  consistency/
    __init__.py
    agent.py              # PydanticAI agent definition
    models.py             # Pydantic input/output models
    compare.py            # Comparison logic
    report.py             # Report generation (text + JSON)
    cli.py                # CLI entry point
  tests/
    test_consistency_models.py
    test_compare.py
    test_content_loader.py
    test_consistency_agent.py
    fixtures/
      known_good/         # Claims where verdict clearly matches narrative
      known_bad/          # Deliberately mismatched claims
```

---

## 3. Pydantic Models

```python
# pipeline/consistency/models.py

from enum import Enum
from pydantic import BaseModel, Field


class Verdict(str, Enum):
    TRUE = "true"
    MOSTLY_TRUE = "mostly-true"
    MIXED = "mixed"
    MOSTLY_FALSE = "mostly-false"
    FALSE = "false"
    UNVERIFIED = "unverified"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    AI_SAFETY = "ai-safety"
    ENVIRONMENTAL_IMPACT = "environmental-impact"
    PRODUCT_COMPARISON = "product-comparison"
    CONSUMER_GUIDE = "consumer-guide"
    AI_LITERACY = "ai-literacy"
    DATA_PRIVACY = "data-privacy"
    INDUSTRY_ANALYSIS = "industry-analysis"
    REGULATION_POLICY = "regulation-policy"


class SourceContext(BaseModel):
    """Projection of source data for LLM context -- NOT a full mirror of the Zod schema.
    Omits url, archived_url, published_date, accessed_date, kind (not needed for
    consistency assessment). Includes body (Markdown below frontmatter) which is
    not part of the Zod frontmatter schema but is needed for analysis."""
    id: str
    title: str
    publisher: str
    summary: str
    key_quotes: list[str] = Field(default_factory=list)  # Zod has Optional; loader converts None -> []
    body: str


class EntityContext(BaseModel):
    """Entity context provided to the LLM."""
    name: str
    type: str
    description: str


class ClaimBundle(BaseModel):
    """Everything the LLM sees -- no verdict, confidence, or title."""
    claim_id: str
    entity: EntityContext
    category: Category
    narrative: str  # Markdown body stripped of frontmatter
    sources: list[SourceContext]
    # NOTE: `title` is deliberately excluded. Claim titles often encode the verdict
    # (e.g., "Ecosia's renewable energy claim does not cover its AI chat backend")
    # which would undermine information asymmetry.


class IndependentAssessment(BaseModel):
    """Structured output from the LLM."""
    verdict: Verdict = Field(
        description="Your independent verdict based solely on the narrative and source evidence."
    )
    confidence: Confidence = Field(
        description="How confident you are in the evidence supporting this verdict."
    )
    reasoning: str = Field(
        description="2-4 sentences explaining your verdict. Reference specific sources."
    )
    evidence_gaps: list[str] = Field(
        default_factory=list,
        description="Gaps in the evidence that limit your confidence."
    )


class ComparisonResult(BaseModel):
    """Result of comparing LLM assessment vs actual claim values."""
    claim_id: str
    claim_file: str
    actual_verdict: Verdict
    assessed_verdict: Verdict
    actual_confidence: Confidence
    assessed_confidence: Confidence
    reasoning: str
    evidence_gaps: list[str]
    verdict_agrees: bool
    confidence_agrees: bool
    verdict_severity: str  # "match", "adjacent", "major", "opposite"
    needs_review: bool
```

---

## 4. Agent Design

### System prompt

```
You are an independent fact-check reviewer for a research site that evaluates
claims about AI companies and products. You will be given:

1. A claim narrative (the text of the claim as written)
2. Source materials that the claim cites
3. Basic information about the entity the claim is about

Your job is to determine what verdict and confidence level the evidence supports.
You must form your own independent judgment.

VERDICT SCALE (ordered from positive to negative):
- true: The claim is well-supported by the cited evidence
- mostly-true: Largely supported but has minor qualifications
- mixed: Evidence partially supports and partially contradicts
- mostly-false: Largely unsupported by the cited evidence
- false: The cited evidence contradicts the claim
- unverified: Insufficient evidence to render a verdict

CONFIDENCE SCALE:
- high: Multiple independent sources strongly support the verdict; evidence is direct
- medium: Evidence supports the verdict but has limitations (single source,
  self-reported data, indirect evidence)
- low: Evidence is thin, contradictory, or primarily anecdotal

RULES:
- Base your verdict ONLY on the narrative text and the provided source materials.
- Do not rely on your own knowledge about the entities or topics.
- If the narrative makes claims that the sources do not support, that should
  lower your verdict and/or confidence.
- If the narrative is cautious but sources strongly support the conclusion,
  your verdict may be stronger than the narrative implies.
- Pay attention to whether the narrative accurately represents what the sources say.
- Note any evidence gaps -- things the narrative claims that no source backs up.
- Be genuinely critical. Do not default to agreement. Disagreement is valuable.
```

### Agent definition

```python
from dataclasses import dataclass

@dataclass
class ConsistencyDeps:
    """Dependencies injected into the agent -- swappable for testing."""
    repo_root: str

consistency_agent = Agent(
    "anthropic:claude-sonnet-4-20250514",
    system_prompt=SYSTEM_PROMPT,
    result_type=IndependentAssessment,
    deps_type=ConsistencyDeps,
    retries=2,
)
```

**Note**: Uses `result_type` (not `output_type`). Verify against pinned PydanticAI version at implementation time -- see parent plan open question #2.

### User prompt construction

Built from `ClaimBundle`:
- Entity name, type, description
- Category
- Claim narrative (full Markdown body)
- Each source: title, publisher, summary, key quotes, body
- Final instruction: "Based on the narrative and sources above, provide your independent verdict and confidence assessment."

---

## 5. Comparison Logic

### Verdict ordering

```python
VERDICT_ORDER = {
    "true": 0, "mostly-true": 1, "mixed": 2, "mostly-false": 3, "false": 4,
}
# "unverified" is handled separately -- not on the ordinal scale.

CONFIDENCE_ORDER = { "high": 0, "medium": 1, "low": 2 }
```

### Severity levels

| Severity | Definition | Example |
|----------|-----------|---------|
| `match` | Identical verdicts (including both `unverified`) | true = true |
| `adjacent` | One step apart on the ordinal scale | true vs mostly-true |
| `major` | Two steps apart, OR one is `unverified` and the other is ordinal | true vs mixed, unverified vs true |
| `opposite` | Three+ steps apart | true vs false |

**`unverified` handling**: `unverified` is not on the ordinal scale. When one side is `unverified` and the other is any ordinal verdict, classify as `major` -- the LLM either lacks evidence the editorial team found, or vice versa. Both sides `unverified` is a `match`.

### `needs_review` trigger

A claim needs review when:
- Verdict severity is `major` or `opposite`, OR
- Verdict severity is `adjacent` AND confidence disagrees by 2+ steps, OR
- LLM's `evidence_gaps` list has more than one gap

---

## 6. Output Format

### Text output (default)

```
Narrative-Verdict Consistency Check
====================================
Claims checked: 3
Agreements:     2
Disagreements:  1 (0 major, 1 adjacent)
Needs review:   0

CLAIM                                    VERDICT          CONFIDENCE       SEVERITY
anthropic/existential-safety-score       true = true      high = high      match
ecosia/renewable-energy-hosting          false ~ mostly-f medium = medium  adjacent
greenpt/renewable-energy-hosting         true = true      medium = medium  match

--- Details for disagreements ---

ecosia/renewable-energy-hosting
  File:       research/claims/ecosia/renewable-energy-hosting.md
  Actual:     verdict=false  confidence=medium
  Assessed:   verdict=mostly-false  confidence=medium
  Severity:   adjacent
  Reasoning:  [LLM reasoning here]
  Evidence gaps:
    - [gap description]
  Needs review: No
```

### JSON output (`--format json`)

```json
{
  "timestamp": "2026-04-18T12:00:00Z",
  "summary": {
    "claims_checked": 3,
    "agreements": 2,
    "disagreements": 1,
    "needs_review": 0,
    "by_severity": {"match": 2, "adjacent": 1, "major": 0, "opposite": 0}
  },
  "results": [...]
}
```

---

## 7. CLI Interface

```
Usage: python -m pipeline.consistency [OPTIONS]

Options:
  --claim PATH        Check a single claim file (relative to research/claims/)
  --entity SLUG       Check all claims for an entity
  --category SLUG     Check all claims in a category
  --format TEXT        Output format: text (default), json
  --model TEXT         Override LLM model
  --dry-run           Show what would be checked without calling the LLM
  --verbose           Show full reasoning for all claims, not just disagreements
  --help              Show this message
```

Examples:

```bash
python -m pipeline.consistency
python -m pipeline.consistency --claim anthropic/existential-safety-score
python -m pipeline.consistency --category environmental-impact --format json
python -m pipeline.consistency --entity ecosia --dry-run
```

---

## 8. CI Integration

**Cost analysis** (current scale: 3 claims): ~$0.01-0.03 per run with Sonnet. Negligible.

**At scale**: 50 claims ~$0.50-1.00, 200 claims ~$2-4, 1000 claims ~$10-20.

**Recommendation**: Do NOT run in standard PR CI. Instead:

1. **Manual invocation** -- primary mode. Run locally before/after updating claims.
2. **Scheduled weekly workflow** -- alongside stale claim detection (Phase 5).
3. **Label-gated PR workflow** -- add `check-consistency` label to trigger.

```yaml
# .github/workflows/consistency-check.yml
name: Narrative-Verdict Consistency
on:
  workflow_dispatch:
  pull_request:
    types: [labeled]

jobs:
  check:
    if: >
      github.event_name == 'workflow_dispatch' ||
      contains(github.event.pull_request.labels.*.name, 'check-consistency')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: astral-sh/setup-uv@v4
      - run: cd pipeline && uv sync
      - run: cd pipeline && uv run python -m pipeline.consistency --format json > consistency-report.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: actions/upload-artifact@v4
        with: { name: consistency-report, path: consistency-report.json }
```

**Secret management**: `ANTHROPIC_API_KEY` in GitHub repository secrets (shared with 4.1 Ingestor).

**Exit code policy**: Report-only (exit 0). The check surfaces claims for human review, not automated rejection.

---

## 9. Testing Strategy

### Unit tests (no LLM calls)

**Content loader tests**: `split_frontmatter` correctness, `load_claim_bundle` source/entity resolution, missing source handling (skip with warning), missing entity file handling.

**Comparison logic tests** (pure functions):
- `test_exact_match`: true/true -> match, no review
- `test_adjacent_same_confidence`: true/mostly-true, both high -> adjacent, no review
- `test_adjacent_confidence_gap`: true+high / mostly-true+low -> review (adjacent + 2-step gap)
- `test_major_disagreement`: true/mixed -> major, review
- `test_opposite_disagreement`: true/false -> opposite, review
- `test_unverified_vs_ordinal`: true/unverified -> major, review
- `test_both_unverified`: match, no review
- `test_evidence_gaps_trigger_review`: match verdict but >1 gap -> review

**Prompt construction tests**: Verify prompt includes entity, category, narrative, sources.

**Information-asymmetry guarantee** (`test_bundle_never_leaks_verdict`): This is the most critical test in the plan -- it validates the core design principle. Assert that the serialized prompt string does NOT contain:
- The claim's `verdict` value
- The claim's `confidence` value
- The claim's `title` (which often encodes the verdict)
Run against every claim fixture. If this test fails, the entire consistency check is compromised.

### Integration tests (PydanticAI `TestModel`)

Agent round-trip: canned `IndependentAssessment` -> full pipeline from file load to comparison result.

### Evaluation tests (real LLM, manual only)

**Known-good fixtures**: Claims where verdict clearly matches narrative/sources. LLM should agree.

**Known-bad fixtures**: Deliberately mismatched claims:
- Narrative describes harm but verdict is "true" for a positive claim -> LLM should flag
- High confidence with one weak source -> LLM should assess lower confidence

**Edge cases**: Zero sources, very short narrative, `unverified` verdict.

---

## 10. Anti-Gaming Measures

| Measure | How it works |
|---|---|
| **Information asymmetry** | Verdict/confidence stripped from input. LLM cannot "agree" with what it doesn't see. |
| **System prompt framing** | Explicitly instructs critical assessment. "Disagreement is valuable." |
| **Evidence gap detection** | Forces analytical engagement with sources. |
| **Source-narrative cross-check** | Checks whether narrative accurately represents sources. |
| **Known-bad calibration** | Test suite includes mismatched claims. If LLM agrees, prompt needs work. |
| **Model selection** | Sonnet or better. Weaker models are more prone to sycophancy. |
| **Single-shot** | No multi-turn conversation. One prompt in, one assessment out. |
| **Low temperature** | Set temperature explicitly via PydanticAI model settings (Anthropic's default is 1.0, not 0). Use 0.0-0.2 for deterministic analytical assessment. |

---

## 11. Open Decisions

| # | Decision | Recommendation | Notes |
|---|---|---|---|
| 1 | Sequencing with 4.1 | Could implement 4.2 first | Read-only, lower risk. Good for shaking out PydanticAI scaffolding. |
| 2 | CI failure threshold | Report-only (exit 0) | Blocking PRs on LLM opinions feels wrong for a research site. |
| 3 | Caching / incremental runs | Defer | At 3 claims, re-checking everything is trivial. Optimize at 100+. |
| 4 | Separate narrative-accuracy field | Defer | `evidence_gaps` + `reasoning` capture this well enough for v1. |
| 5 | Re-assessment stability | Include timestamp in JSON | Do not add retry/consensus logic in v1. |
| 6 | Model choice | Sonnet default, configurable | PydanticAI is model-agnostic. Could test with other providers. |

---

## Implementation Sequence

| Step | Task |
|---|---|
| 1 | Scaffold shared infrastructure in `pipeline/common/` (frontmatter, content_loader, shared models) |
| 2 | Implement `consistency/models.py` |
| 3 | Implement `consistency/compare.py` + unit tests |
| 4 | Implement `consistency/agent.py` with system prompt |
| 5 | Implement `consistency/report.py` (text + JSON formatters) |
| 6 | Implement `consistency/cli.py` + exit code test |
| 7 | Write integration tests with PydanticAI `TestModel` |
| 8 | Create known-bad fixtures, run evaluation runs |
| 9 | Add `docs/architecture/consistency-check.md` |

### If implementing 4.2 before 4.1

Step 1 expands to include scaffolding normally done by 4.1:
- Create `pipeline/pyproject.toml` with dependencies (omit `beautifulsoup4` and `click` if 4.2 uses `argparse` or `click` independently)
- Create `pipeline/.gitignore`
- Run `uv sync`
- Implement `common/frontmatter.py` (read-only parsing; write support deferred to 4.1)
- Implement `common/content_loader.py`
- Implement `common/models.py` (shared enums)

This is viable because 4.2 is read-only and needs no file writing. The ingestor (4.1) would then add write support to `common/frontmatter.py` and its own `ingestor/` package.

---

## Critical Files

- `src/content.config.ts` -- Zod schemas (verdict/confidence enums must match)
- `plans/agent-pipeline.md` -- Parent plan
- `research/claims/` -- Existing claims (structure to parse and split)
- `scripts/check-citations.ts` -- Existing validation pattern (frontmatter parsing, exit codes)
- `docs/architecture/research-workflow.md` -- Documents quality gate gaps this plan addresses
