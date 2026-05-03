# Plan: Source URL deduplication

**Status**: Completed
**Last updated**: 2026-05-03

## Goal

Skip re-ingesting URLs that already have a source file on disk. Before `_ingest_urls` is called, build an index of existing sources by scanning `research/sources/**/*.md` frontmatter and mapping `url -> source_id`. Any URL the researcher returned that already appears in the index is routed directly into `result.sources` with no HTTP fetch and no LLM call. The analyst cannot tell the difference between a freshly ingested source and a deduplicated one.

This is a narrower, more focused scope than `pipeline-dedup-detection_stub.md`, which covers URL canonicalization, claim dedup, and precomputed index files. This plan addresses only the in-pipeline ingest dedup path.

---

## Approach

### 1. Index builder in `persistence.py`

Add `build_source_url_index(repo_root: Path) -> dict[str, str]` to `pipeline/orchestrator/persistence.py`.

- Scans `research/sources/*/*.md` using `glob("*/*.md")` on the sources directory (one level for year, one for slug). This matches the `{year}/{slug}.md` layout exactly and avoids producing a wrong source_id for any stray nested file.
- Reads each file with `parse_frontmatter()` (already imported in `persistence.py`).
- Extracts `url` from frontmatter. Skips files with no `url` field or a parse error.
- Derives `source_id` from the file path: `"{year}/{stem}"` where `year` is the immediate parent directory name and `stem` is the filename without `.md`. This matches the `"{sf.year}/{sf.slug}"` format returned by `_write_source_files()`.
- Returns `dict[str, str]` mapping `url -> source_id`.

Exceptions to catch: `ValueError` (no frontmatter delimiters found), `yaml.YAMLError` (malformed YAML inside frontmatter), and `OSError` (unreadable file). `parse_frontmatter` calls `yaml.safe_load` which raises `yaml.YAMLError`, not `ValueError`, so all three must be listed.

Sketch:

```python
def build_source_url_index(repo_root: Path) -> dict[str, str]:
    sources_dir = repo_root / "research" / "sources"
    index: dict[str, str] = {}
    if not sources_dir.exists():
        return index
    for path in sources_dir.glob("*/*.md"):
        try:
            fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (ValueError, yaml.YAMLError, OSError):
            continue
        url = fm.get("url")
        if not url:
            continue
        source_id = f"{path.parent.name}/{path.stem}"
        index[url] = source_id
    return index
```

The index is built once per pipeline run (once per `verify_claim` / `research_claim` call) and passed into a filter function. It is not a module-level global.

### 2. Source dict reconstruction from disk

When a URL hits the index, its `source_id` must flow into `result.sources` in the same shape as `_build_source_dict(sf)` (see `pipeline.py:492`):

```python
{
    "title": ...,
    "publisher": ...,
    "summary": ...,
    "key_quotes": [...],
    "body": ...,
    "slug": ...,
    "url": ...,
}
```

Add a companion helper `load_source_dict(source_id: str, repo_root: Path) -> dict | None` to `persistence.py`. It reads the on-disk file at `research/sources/{source_id}.md`, parses frontmatter and body, and returns the dict in the same shape. Returns `None` if the file cannot be read or parsed (dedup falls back to normal ingestion in that case).

Same exception surface as `build_source_url_index`: catch `(ValueError, yaml.YAMLError, OSError)`.

Sketch:

```python
def load_source_dict(source_id: str, repo_root: Path) -> dict | None:
    path = repo_root / "research" / "sources" / f"{source_id}.md"
    try:
        fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (ValueError, yaml.YAMLError, OSError):
        return None
    slug = path.stem
    return {
        "title": fm.get("title", ""),
        "publisher": fm.get("publisher", ""),
        "summary": fm.get("summary", ""),
        "key_quotes": fm.get("key_quotes") or [],
        "body": body,
        "slug": slug,
        "url": fm.get("url", ""),
    }
```

### 3. Dedup filter in `pipeline.py`

Add `_apply_url_dedup(urls, url_index, repo_root)` in `pipeline.py`, called after the blocklist filter and before `_ingest_urls`. It partitions URLs into those to ingest and those already on disk.

The return type is `tuple[list[str], list[tuple[str, str, dict]]]`: `to_ingest` URLs and a list of `(url, source_id, source_dict)` triples for cache hits. Carrying `source_id` in the triple avoids re-querying `url_index` in the caller.

Sketch:

```python
def _apply_url_dedup(
    urls: list[str],
    url_index: dict[str, str],
    repo_root: Path,
) -> tuple[list[str], list[tuple[str, str, dict]]]:
    to_ingest: list[str] = []
    cached: list[tuple[str, str, dict]] = []
    for url in urls:
        source_id = url_index.get(url)
        if source_id:
            sd = load_source_dict(source_id, repo_root)
            if sd is not None:
                logger.info("dedup-hit: %s -> %s", url, source_id)
                cached.append((url, source_id, sd))
                continue
        to_ingest.append(url)
    return to_ingest, cached
```

Returns:
- `to_ingest`: URLs to pass to `_ingest_urls` as normal.
- `cached`: `(url, source_id, source_dict)` triples ready to merge into `result.sources`.

### 4. Target cap after dedup

`_ingest_urls` internally caps at `cfg.max_sources` successes (waterfall stops at `target`). If N URLs are already cached, passing all remaining URLs to `_ingest_urls` unchanged could yield up to `N + cfg.max_sources` total sources.

Fix: compute `remaining = max(0, cfg.max_sources - len(cached_sources))` before calling `_ingest_urls`, and add an optional `target: int | None = None` parameter to `_ingest_urls`. When `target` is supplied it overrides the internal `cfg.max_sources` cap. When `remaining == 0`, skip `_ingest_urls` entirely.

```python
remaining = max(0, cfg.max_sources - len(cached_sources))
if remaining > 0:
    source_files, ingest_errors = await _ingest_urls(client, urls_to_ingest, cfg, _sem, target=remaining)
else:
    source_files, ingest_errors = [], []
```

This requires a one-line signature change to `_ingest_urls`:

```python
async def _ingest_urls(
    client, urls, cfg, sem, *, target: int | None = None
) -> ...:
    target = target if target is not None else cfg.max_sources
    ...
```

### 5. Hook in `verify_claim`

`verify_claim` does not call `_write_source_files` (it is a pure in-memory pipeline). The dedup filter still applies: it saves HTTP fetches and LLM calls for URLs that have already been ingested in a previous run.

`verify_claim` does not set `cfg.repo_root` (unlike `research_claim`). Use the same fallback idiom already established in `_apply_blocklist_cap` (line 318): `cfg.repo_root or str(resolve_repo_root())`.

Changes in `verify_claim` (around line 257), replacing the current ingest block:

```python
repo_root = Path(cfg.repo_root or str(resolve_repo_root()))
url_index = build_source_url_index(repo_root)
urls_to_ingest, cached_sources = _apply_url_dedup(urls, url_index, repo_root)

remaining = max(0, cfg.max_sources - len(cached_sources))
if remaining > 0:
    source_files, ingest_errors = await _ingest_urls(client, urls_to_ingest, cfg, _sem, target=remaining)
else:
    source_files, ingest_errors = [], []

for url, _sid, sd in cached_sources:
    result.urls_ingested.append(url)
    result.sources.append(sd)

for url, sf in source_files:
    result.urls_ingested.append(url)
    result.sources.append(_build_source_dict(sf))
    result.source_files.append((url, sf))
```

Cached sources are added to `result.sources` before the `below_threshold` check fires, so dedup hits count toward the minimum source threshold. This is correct: a cached source is a usable source.

### 6. Hook in `research_claim`

`research_claim` writes sources to disk (line 706) and also ingests. The same filter applies before `_ingest_urls`. Cached sources contribute to `result.sources` and `result.urls_ingested` but do not produce `SourceFile` objects, so they are not passed to `_write_source_files`.

Their `source_id` values must appear in the claim's `sources` frontmatter. Build `source_ids` by walking the original `urls` list in order (the researcher orders by relevance score) and resolving each URL to either a cached source_id or the freshly written source_id, preserving researcher ranking in the frontmatter.

`_write_source_files` iterates its input list in order and appends source_ids in the same order (confirmed in `persistence.py:62-80`), so `zip(source_files, _write_source_files(...))` is safe.

Replacing the ingest block in `research_claim` (around line 675):

```python
url_index = build_source_url_index(repo_root)
urls_to_ingest, cached_sources = _apply_url_dedup(urls, url_index, repo_root)

remaining = max(0, cfg.max_sources - len(cached_sources))
if remaining > 0:
    source_files, ingest_errors = await _ingest_urls(client, urls_to_ingest, cfg, _sem, target=remaining)
else:
    source_files, ingest_errors = [], []

cached_map = {url: sid for url, sid, _ in cached_sources}

for url, _sid, sd in cached_sources:
    result.urls_ingested.append(url)
    result.sources.append(sd)

for url, sf in source_files:
    result.urls_ingested.append(url)
    result.sources.append(_build_source_dict(sf))
    result.source_files.append((url, sf))

...

fresh_map = {url: sid for (url, _), sid in zip(source_files, _write_source_files(source_files, repo_root))}
source_ids = [
    cached_map[url] if url in cached_map else fresh_map[url]
    for url in urls
    if url in cached_map or url in fresh_map
]
```

Walking `urls` (the original researcher-ordered list) as the loop driver ensures the claim's `sources` field reflects relevance order rather than the arbitrary split between cached and freshly ingested.

**Threshold block path**: `research_claim` has an early-return threshold block (line 698-702) that calls `_write_source_files(source_files, repo_root)` for any fresh sources before returning. The `source_files` variable there holds only freshly ingested sources, so this path is unaffected by the dedup change.

**Sidecar completeness**: `_build_sources_consulted` takes `result.source_files`, which holds only freshly ingested sources. Cached sources are absent from the audit sidecar's `sources_consulted` list. This is acceptable for v1: the sidecar will show fewer sources than the analyst received, but the claim frontmatter's `sources` list is complete.

---

## Secondary improvement: URL-derived slug (optional)

When the Ingestor invents a `slug` from the document title, re-running on the same URL can produce a different slug and a different filename, defeating path-based collision detection in `_write_source_files`. Making the slug deterministic from the URL path closes this gap.

**Where**: add `slug_from_url(url: str) -> str | None` in `pipeline/common/utils.py` (alongside existing `slugify`). It takes the last non-empty path segment, runs it through `slugify`, and returns `None` for root-only URLs (let the Ingestor fall back in that case).

**When it runs**: in `_ingest_one`, immediately after the agent returns a `SourceFile` and before it is returned to `_ingest_urls`. Override `sf.slug` with the URL-derived value when non-None. `SourceFile` is a plain `BaseModel` with no `frozen=True` config, so direct attribute assignment works.

Sketch:

```python
def slug_from_url(url: str) -> str | None:
    from urllib.parse import urlparse
    path = urlparse(url).path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if "/" in path else path
    if not segment:
        return None
    return slugify(segment)
```

This does not change the Ingestor agent or its instructions; the override happens in the orchestrator after the agent returns its output.

---

## Testing

### Unit tests (`pipeline/tests/test_source_url_dedup.py`)

- `test_index_builder_maps_url_to_source_id`: fixture with two source files; assert index has correct `url -> {year}/{slug}` entries.
- `test_index_builder_skips_missing_url_field`: source file with no `url` in frontmatter; assert not in index.
- `test_index_builder_skips_bad_frontmatter`: malformed YAML; assert no crash, file skipped.
- `test_index_builder_skips_yaml_error`: valid delimiters but invalid YAML content (`yaml.YAMLError`); assert no crash, file skipped.
- `test_index_builder_missing_sources_dir`: `research/sources/` does not exist; returns empty dict.
- `test_load_source_dict_roundtrip`: write a source file, call `load_source_dict`, assert all fields match.
- `test_load_source_dict_missing_file`: returns `None` without raising.
- `test_apply_url_dedup_splits_correctly`: two URLs; one in index with valid on-disk file, one not. Assert `to_ingest` has one URL, `cached` has one `(url, source_id, dict)` triple.
- `test_apply_url_dedup_falls_back_on_bad_file`: URL in index but file unreadable; URL goes to `to_ingest` instead of `cached`.
- `test_apply_url_dedup_returns_source_id_in_triple`: cached entry's source_id matches `url_index[url]` without re-querying the index.

### Unit tests: target cap

- `test_ingest_urls_respects_target_param`: pass `target=1` with two ingestable URLs; assert only one `SourceFile` returned.
- `test_dedup_skips_ingest_when_all_cached`: all URLs cache-hit; assert `_ingest_one` never called.
- `test_dedup_reduces_target_by_cache_count`: 2 cached, `max_sources=4`; assert `_ingest_urls` called with `target=2`.

### Unit test: URL-derived slug (if secondary improvement is implemented)

- `test_slug_from_url_last_segment`: `https://example.com/reports/annual-2024` -> `annual-2024`.
- `test_slug_from_url_root_path`: `https://example.com/` -> `None`.
- `test_slug_from_url_slugifies_segment`: `https://example.com/Annual_Report_2024.pdf` -> `annual-report-2024-pdf` (or similar, depends on `slugify` behavior).

### Integration sketch

Monkeypatch `_ingest_one` to assert it is called only for non-deduplicated URLs. Pre-populate a fixture `research/sources/2024/some-report.md` with a known URL. Pass that URL plus a new URL through `verify_claim`. Assert: `_ingest_one` called once (not twice), `result.sources` has two entries, `result.urls_ingested` has both URLs.

---

## Acceptance bar

- `build_source_url_index` exists in `persistence.py`; unit tests pass.
- `load_source_dict` exists in `persistence.py`; returns a dict in the same shape as `_build_source_dict(sf)`.
- `_apply_url_dedup` exists in `pipeline.py`; returns `(to_ingest, [(url, source_id, sd), ...])`.
- `_ingest_urls` accepts an optional `target` parameter; behavior is unchanged when `target` is omitted.
- Both `verify_claim` and `research_claim` build the index once per call, apply the filter, and pass `target=remaining` to `_ingest_urls`.
- Total sources in `result.sources` never exceeds `cfg.max_sources`.
- A URL that already has a source file on disk does not trigger an HTTP fetch or an LLM call.
- Deduplicated source dicts appear in `result.sources` alongside freshly ingested ones; the analyst receives no indication of the difference.
- In `research_claim`, deduplicated `source_id` values appear in the claim's `sources` frontmatter in researcher-ranked order.
- Exception coverage: `(ValueError, yaml.YAMLError, OSError)` in both index builder and source dict loader.

---

## Open questions

1. **URL normalization**: this plan matches on exact URL string equality. A URL the researcher returns with a trailing slash, a `utm_*` param, or an `http://` vs `https://` variant will miss the index. The `pipeline-dedup-detection_stub.md` covers canonicalization in depth; that work is a prerequisite for high-fidelity dedup. For now, exact match catches the most common case (same URL re-returned across runs).

---

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-05-03 | agent | initial draft | Initial draft covering index builder, source dict reconstruction, filter function, pipeline hooks for both verify_claim and research_claim, optional URL-derived slug, tests, acceptance bar |
| 2026-05-03 | agent | cross-review + promote | Fixed exception coverage (add yaml.YAMLError); changed verify_claim repo_root fallback to use established idiom (resolve_repo_root()) instead of skipping dedup when cfg.repo_root unset; resolved target cap interaction (add optional target param to _ingest_urls, compute remaining before calling); changed _apply_url_dedup return type to include source_id in triples; promoted sidecar completeness from open question to explicit v1 constraint; resolved open question 3 (repo_root) by adopting existing fallback pattern; added target cap unit tests to acceptance bar |
