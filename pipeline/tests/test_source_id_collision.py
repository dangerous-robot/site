"""A source id always names the file for that URL.

Slugs come from the last URL path segment, so different pages collide
(``aws.amazon.com/sustainability`` and Microsoft's ``.../sustainability/``
both give ``sustainability``). Collisions are resolved by URL before the
id is used anywhere, and the write path never cites another URL's file.
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from common.frontmatter import parse_frontmatter
from ingestor.models import SourceFile
from orchestrator.persistence import resolve_source_slugs
from orchestrator.pipeline import VerifyConfig, _ingest_urls

MS_URL = "https://datacenters.microsoft.com/sustainability/"
AWS_URL = "https://aws.amazon.com/sustainability"
AWS_UTIL_URL = "https://aws.amazon.com/energy-utilities/sustainability"


def _sf(url: str, slug: str = "sustainability", year: int = 2026, title: str = "AWS Sustainability") -> SourceFile:
    return SourceFile.model_validate(
        {
            "frontmatter": {
                "url": url,
                "title": title,
                "publisher": "AWS",
                "accessed_date": datetime.date(2026, 10, 4).isoformat(),
                "kind": "index",
                "summary": "Sustainability page.",
            },
            "body": "Sustainability page.",
            "slug": slug,
            "year": year,
        }
    )


def _write_existing(repo_root: Path, source_id: str, url: str) -> Path:
    path = repo_root / "research" / "sources" / f"{source_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"url: {url}\n"
        "title: Existing page\n"
        "publisher: Someone\n"
        "accessed_date: 2026-01-01\n"
        "kind: index\n"
        "summary: Existing page.\n"
        "---\n\nExisting body.\n",
        encoding="utf-8",
    )
    return path


def _listing(repo_root: Path) -> set[str]:
    return {str(p.relative_to(repo_root)) for p in (repo_root / "research").rglob("*.md")}


# --- C1: resolver ---------------------------------------------------------


def test_cross_run_collision_gets_host_prefixed_id(tmp_path: Path) -> None:
    ms_path = _write_existing(tmp_path, "2026/sustainability", MS_URL)
    before = ms_path.read_bytes()
    sf = _sf(AWS_URL)
    resolve_source_slugs([(AWS_URL, sf)], tmp_path)
    assert sf.slug == "aws-amazon-sustainability"
    assert ms_path.read_bytes() == before


def test_same_canonical_url_reuses_id(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", AWS_URL)
    new_url = "https://www.aws.amazon.com/sustainability#top"
    sf = _sf(new_url)
    resolve_source_slugs([(new_url, sf)], tmp_path)
    assert sf.slug == "sustainability"


def test_same_run_duplicates_get_distinct_ids(tmp_path: Path) -> None:
    a, b = _sf(AWS_URL), _sf(AWS_UTIL_URL)
    resolve_source_slugs([(AWS_URL, a), (AWS_UTIL_URL, b)], tmp_path)
    assert a.slug == "sustainability"
    assert b.slug == "aws-amazon-sustainability"


def test_numeric_suffix_when_host_prefix_taken(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", MS_URL)
    _write_existing(tmp_path, "2026/aws-amazon-sustainability", AWS_UTIL_URL)
    sf = _sf(AWS_URL)
    resolve_source_slugs([(AWS_URL, sf)], tmp_path)
    assert sf.slug == "aws-amazon-sustainability-2"


def test_existing_files_never_renamed(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", MS_URL)
    _write_existing(tmp_path, "2026/aws-amazon-sustainability", AWS_UTIL_URL)
    before = _listing(tmp_path)
    resolve_source_slugs([(AWS_URL, _sf(AWS_URL)), (MS_URL, _sf(MS_URL))], tmp_path)
    after = _listing(tmp_path)
    assert before <= after


def test_unparseable_existing_url_counts_as_different(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", "not a url")
    sf = _sf(AWS_URL)
    resolve_source_slugs([(AWS_URL, sf)], tmp_path)
    assert sf.slug == "aws-amazon-sustainability"


# --- C2: _ingest_urls assigns ids before analysis ---------------------------


@pytest.mark.asyncio
async def test_ingest_urls_assigns_unique_ids(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", MS_URL)
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=6)

    async def _fake_ingest_one(client, url, cfg, today, sem, prefetched_body=None, **_):
        return (url, _sf(url))

    with patch("orchestrator.pipeline._ingest_one", side_effect=_fake_ingest_one):
        results, errors = await _ingest_urls(
            None, [AWS_URL, AWS_UTIL_URL], cfg, asyncio.Semaphore(8)
        )

    assert errors == []
    slugs = [sf.slug for _url, sf in results]
    assert len(set(slugs)) == 2
    assert "sustainability" not in slugs
