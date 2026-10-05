"""A source id always names the file for that URL.

Slugs come from the last URL path segment, so different pages collide
(``aws.amazon.com/sustainability`` and Microsoft's ``.../sustainability/``
both give ``sustainability``). Collisions are resolved by URL before the
id is used anywhere, and the write path never cites another URL's file.
"""

from __future__ import annotations

import asyncio
import datetime
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from click.testing import CliRunner
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from common.frontmatter import parse_frontmatter
from ingestor.agent import ingestor_agent
from ingestor.models import SourceFile
from orchestrator.cli import main
from orchestrator.persistence import _write_source_files, resolve_source_slugs
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
    resolve_source_slugs([sf], tmp_path)
    assert sf.slug == "aws-amazon-sustainability"
    assert ms_path.read_bytes() == before


def test_same_canonical_url_reuses_id(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", AWS_URL)
    new_url = "https://www.aws.amazon.com/sustainability#top"
    sf = _sf(new_url)
    resolve_source_slugs([sf], tmp_path)
    assert sf.slug == "sustainability"


def test_same_run_duplicates_get_distinct_ids(tmp_path: Path) -> None:
    a, b = _sf(AWS_URL), _sf(AWS_UTIL_URL)
    resolve_source_slugs([a, b], tmp_path)
    assert a.slug == "sustainability"
    assert b.slug == "aws-amazon-sustainability"


def test_numeric_suffix_when_host_prefix_taken(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", MS_URL)
    _write_existing(tmp_path, "2026/aws-amazon-sustainability", AWS_UTIL_URL)
    sf = _sf(AWS_URL)
    resolve_source_slugs([sf], tmp_path)
    assert sf.slug == "aws-amazon-sustainability-2"


def test_existing_files_never_renamed(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", MS_URL)
    _write_existing(tmp_path, "2026/aws-amazon-sustainability", AWS_UTIL_URL)
    before = _listing(tmp_path)
    resolve_source_slugs([_sf(AWS_URL), _sf(MS_URL)], tmp_path)
    after = _listing(tmp_path)
    assert before <= after


def test_unparseable_existing_url_counts_as_different(tmp_path: Path) -> None:
    _write_existing(tmp_path, "2026/sustainability", "not a url")
    sf = _sf(AWS_URL)
    resolve_source_slugs([sf], tmp_path)
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


# --- C3: write guard --------------------------------------------------------


def test_write_source_files_never_returns_other_urls_id(tmp_path: Path) -> None:
    ms_path = _write_existing(tmp_path, "2026/sustainability", MS_URL)
    before = ms_path.read_bytes()
    items = [(AWS_URL, _sf(AWS_URL)), (AWS_UTIL_URL, _sf(AWS_UTIL_URL))]

    ids = _write_source_files(items, tmp_path)

    assert len(ids) == 2
    assert len(set(ids)) == 2
    for source_id, (url, sf) in zip(ids, items):
        fm, _ = parse_frontmatter(
            (tmp_path / "research" / "sources" / f"{source_id}.md").read_text()
        )
        assert fm["url"] == url
        assert source_id == f"{sf.year}/{sf.slug}"
    assert ms_path.read_bytes() == before


def test_write_source_files_same_url_keeps_existing_id(tmp_path: Path) -> None:
    existing = _write_existing(tmp_path, "2026/sustainability", AWS_URL)
    before = existing.read_bytes()
    ids = _write_source_files([(AWS_URL, _sf(AWS_URL))], tmp_path)
    assert ids == ["2026/sustainability"]
    assert existing.read_bytes() == before


# --- C4: dr step-ingest write path ------------------------------------------


@contextmanager
def _noop_ctx():
    yield


def _fetch_then_return(url: str, source: dict) -> FunctionModel:
    called = False

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        nonlocal called
        if not called:
            called = True
            return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})])
        return ModelResponse(
            parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)]
        )

    return FunctionModel(_fn)


def _invoke_step_ingest(tmp_path: Path, url: str, *flags: str):
    source = _sf(url).model_dump(mode="json")
    html = "<html><head><title>AWS</title></head><body><p>AWS sustainability.</p></body></html>"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, html=html))
        with ingestor_agent.override(model=_fetch_then_return(url, source)):
            with patch(
                "ingestor.agent.ingestor_agent.override",
                side_effect=lambda **kw: _noop_ctx(),
            ):
                return CliRunner().invoke(
                    main,
                    [
                        "--model", "test", "--ingestor-model", "test",
                        "step-ingest", url, *flags, "--skip-wayback",
                        "--repo-root", str(tmp_path),
                    ],
                )


def test_step_ingest_force_does_not_overwrite_other_url(tmp_path: Path) -> None:
    ms_path = _write_existing(tmp_path, "2026/sustainability", MS_URL)
    before = ms_path.read_bytes()

    result = _invoke_step_ingest(tmp_path, AWS_URL, "--force")

    assert result.exit_code == 0, result.output
    assert ms_path.read_bytes() == before
    new_path = tmp_path / "research" / "sources" / "2026" / "aws-amazon-sustainability.md"
    fm, _ = parse_frontmatter(new_path.read_text())
    assert fm["url"] == AWS_URL


def test_step_ingest_force_overwrites_same_url(tmp_path: Path) -> None:
    existing = _write_existing(tmp_path, "2026/sustainability", AWS_URL)

    result = _invoke_step_ingest(tmp_path, AWS_URL, "--force")

    assert result.exit_code == 0, result.output
    fm, _ = parse_frontmatter(existing.read_text())
    assert fm["title"] == "AWS Sustainability"
    assert not (tmp_path / "research" / "sources" / "2026" / "aws-amazon-sustainability.md").exists()
