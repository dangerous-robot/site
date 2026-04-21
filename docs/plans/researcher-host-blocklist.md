# Plan: Researcher host blocklist

## Goal

Drop URLs from known-403/paywall hosts immediately after the researcher returns, before the ingestor spends ~30s fetching + an LLM call per URL. Keep the mechanism tiny, data-driven, transparent (every filtered URL is logged and surfaced), and easy for operators to edit.

## Approach

### 1. Where the blocklist lives

**Decision**: `research/blocklist.yaml` -- operator-editable, sibling to the existing `research/templates.yaml` convention (`common/templates.py` already loads YAML from `research/`). PyYAML is already a dependency.

Schema:

```yaml
# research/blocklist.yaml
# Hosts whose URLs are dropped from researcher output before ingestion.
# Matching is suffix-based on dot boundary after stripping leading "www."
# (so linkedin.com matches www.linkedin.com AND uk.linkedin.com, but NOT notlinkedin.com).
hosts:
  - host: linkedin.com
    reason: "403s on anonymous fetch"
  - host: wsj.com
    reason: "paywall"
  - host: ft.com
    reason: "paywall"
  - host: bloomberg.com
    reason: "paywall / bot wall"
  - host: nytimes.com
    reason: "metered paywall"
  - host: economist.com
    reason: "paywall"
  - host: hbr.org
    reason: "Harvard Business Review paywall"
  # Candidates to review later: medium.com (intermittent), reuters.com (geo-gated)
```

### 2. New module: `pipeline/common/blocklist.py`

Tiny, no third-party deps.

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import logging
import yaml

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class BlocklistEntry:
    host: str
    reason: str

@dataclass(frozen=True)
class FilterDecision:
    url: str
    host: str
    reason: str

def load_blocklist(repo_root: Path) -> list[BlocklistEntry]:
    path = repo_root / "research" / "blocklist.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [BlocklistEntry(host=e["host"].lower(), reason=e.get("reason", ""))
            for e in data.get("hosts", [])]

def _normalised_host(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    return host[4:] if host.startswith("www.") else host

def _host_matches(url_host: str, blocked_host: str) -> bool:
    return url_host == blocked_host or url_host.endswith("." + blocked_host)

def filter_urls(
    urls: list[str], entries: list[BlocklistEntry]
) -> tuple[list[str], list[FilterDecision]]:
    kept: list[str] = []
    dropped: list[FilterDecision] = []
    for url in urls:
        host = _normalised_host(url)
        if not host:
            kept.append(url)
            continue
        match = next((e for e in entries if _host_matches(host, e.host)), None)
        if match:
            dropped.append(FilterDecision(url=url, host=match.host, reason=match.reason))
            logger.info("Blocklist drop: %s (host=%s, reason=%s)", url, match.host, match.reason)
        else:
            kept.append(url)
    return kept, dropped
```

**Matching semantics**: lowercase, strip leading `www.`, suffix-match on a dot boundary. Rejects `notlinkedin.com` matching `linkedin.com`. No `tldextract` dependency -- registered-domain semantics need the public suffix list, which is overkill for a curated static list.

### 3. Wire into `_research` in `pipeline/orchestrator/pipeline.py:148`

Apply the filter **before** `urls[:cfg.max_sources]` so we slice from the deduped-clean list.

```python
from common.blocklist import load_blocklist, filter_urls

async def _research(client, entity_name, claim_text, cfg):
    ...
    raw_urls = res.output.urls
    entries = load_blocklist(Path(cfg.repo_root)) if cfg.repo_root else []
    kept, dropped = filter_urls(raw_urls, entries)
    urls = kept[:cfg.max_sources]

    errors: list[StepError] = []
    for d in dropped:
        errors.append(StepError(
            step="research",
            url=d.url,
            error_type="blocked_host",
            message=f"Dropped by blocklist (host={d.host}): {d.reason}",
            retryable=False,
        ))
    logger.info("Research: %d raw, %d blocked, %d kept (cap=%d)",
                len(raw_urls), len(dropped), len(urls), cfg.max_sources)
    return urls, errors
```

`StepError` already has `url`, `error_type`, `message`, `retryable` (see `orchestrator/checkpoints.py:12-31`). `"blocked_host"` and `"all_blocked"` become new canonical `error_type` values.

`cfg.repo_root` may be empty for `verify_claim`; fall back via `resolve_repo_root()` from `common.content_loader` (same pattern used at line 310). Cache loaded list per call.

### 4. Empty-result fallback

**Decision**: accept the shortfall. Do NOT re-invoke the researcher with a broader prompt.

Existing path handles empty `urls` cleanly (`VerificationResult.errors.append("Researcher agent found no relevant URLs")` at line 94); analyst produces `unverified` when no sources land. When `kept` is empty and `dropped` is non-empty, prepend a clarifying error:

```python
if not urls and dropped:
    errors.insert(0, StepError(
        step="research", error_type="all_blocked",
        message=f"All {len(dropped)} researcher URLs matched blocklist; returning empty.",
    ))
```

This distinguishes "researcher returned nothing" from "researcher returned only blocked sources".

### 5. Surfacing filtered URLs to the operator

- **Existing `review_sources` checkpoint** (`checkpoints.py:67`) already prints `StepError`s. Blocklist drops flow through `StepError(error_type="blocked_host")` and appear with no code changes.
- **Onboard summary**: `OnboardResult.errors` already captures `vr.errors` (pipeline.py:579), so blocklist messages appear in the final onboard report. Operator sees what was skipped and why.
- Optional polish (deferred): a dedicated `result.urls_blocked` field on `VerificationResult` for structured consumers.

### 6. Tests

`pipeline/tests/test_blocklist.py`:

- `test_exact_host_match` -- `https://linkedin.com/x` blocked.
- `test_www_stripped` -- `https://www.linkedin.com/x` blocked.
- `test_subdomain_suffix_match` -- `https://uk.linkedin.com/x` blocked.
- `test_no_false_positive_substring` -- `https://notlinkedin.com` NOT blocked.
- `test_no_false_positive_different_tld` -- `https://linkedin.io` NOT blocked.
- `test_unparseable_url_kept` -- `"not a url"` passes through.
- `test_empty_blocklist` -- all URLs pass through.
- `test_case_insensitive` -- `https://WWW.LinkedIn.com` blocked.
- `test_load_missing_file` -- returns empty list when file absent (don't crash fresh clones).
- `test_load_parses_reasons` -- reasons round-trip correctly.

`pipeline/tests/test_orchestrator.py` integration:

- Monkeypatch `research_agent.run` to return `ResearchResult(urls=["https://linkedin.com/a", "https://example.com/b"], reasoning="...")`. Call `_research`. Assert `kept == ["https://example.com/b"]` and one `StepError(error_type="blocked_host")`.
- Test `all_blocked` error added when every URL filtered.

### 7. Docs

- Add header comment in `research/blocklist.yaml` explaining matching semantics.
- One-paragraph note in `pipeline/README.md` under the researcher section.

## Sequencing

1. Create `research/blocklist.yaml` with seven starter hosts + reasons.
2. Add `pipeline/common/blocklist.py` + unit tests (pass standalone).
3. Wire into `_research`; add `"all_blocked"` / `"blocked_host"` to canonical error-type lexicon.
4. Integration test for `_research`.
5. Smoke-run `dr onboard` on an entity known to surface LinkedIn; confirm drop in checkpoint and summary.
6. Update `pipeline/README.md`.

## Risks / Trade-offs

- **False negatives** (paywall host not in list): no regression vs. today.
- **False positives** (host on list actually works for this URL): operator removes from YAML.
- **`max_sources` semantics shift slightly**: filtering before slicing means a run that previously got 4 URLs with 2 LinkedIn duds now gets up to 4 *ingestible* URLs -- the intended improvement.

## Done when

- `research/blocklist.yaml` exists with seven starter hosts + reasons.
- `common/blocklist.py` exists; unit tests cover www-stripping, suffix-on-dot-boundary, no false positives.
- `_research` applies filter before `max_sources` slicing; each drop becomes `StepError(error_type="blocked_host")`.
- Integration test proves a fake LinkedIn URL is dropped from `_research` output and appears in the error list.
- Live `dr verify` / `dr onboard` run surfaces blocked URLs in `review_sources` checkpoint and in `OnboardResult.errors`.
- `pipeline/README.md` documents the file and matching rule.
- `"blocked_host"` and `"all_blocked"` added to canonical `error_type` vocabulary.

## Critical files

- `pipeline/orchestrator/pipeline.py`
- `pipeline/common/blocklist.py` (new)
- `research/blocklist.yaml` (new)
- `pipeline/tests/test_blocklist.py` (new)
- `pipeline/orchestrator/checkpoints.py`
