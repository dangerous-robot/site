"""Archive links are looked up in code after each ingest, and the outcome is recorded.

The ingest model is stubbed (it never calls ``wayback_check``) and archive.org
is mocked with respx, so these tests make no network calls.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
import respx
import yaml

from common.frontmatter import parse_frontmatter
from common.sidecar import sidecar_path_for
from orchestrator.pipeline import VerifyConfig, research_claim
from researcher.decomposed import ResearchOutput

_PAGE_URL = "https://example.org/page"
_PAGE = "<html><head><title>Page</title></head><body><p>The stored page.</p></body></html>"
_SNAPSHOT = "https://web.archive.org/web/20260101000000/https://example.org/page"
_TIMEGATE = re.compile(r"https://web\.archive\.org/web/\d{14}/.+")
_SAVE = re.compile(r"https://web\.archive\.org/save/.+")
_CACHED = [f"https://example.com/cached-{i}" for i in range(3)]


def _write_cached_sources(root: Path) -> None:
    for i, url in enumerate(_CACHED):
        path = root / "research" / "sources" / "2025" / f"cached-{i}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nurl: {url}\ntitle: Cached {i}\npublisher: Example\n"
            f"accessed_date: 2026-01-01\nkind: article\nsummary: Cached.\n---\nBody.\n",
            encoding="utf-8",
        )


def _analyst_output():
    from analyst.agent import AnalystOutput, EntityResolution, VerdictAssessment

    return AnalystOutput(
        entity=EntityResolution(
            entity_name="Example", entity_type="company", entity_description="A company."
        ),
        verdict=VerdictAssessment(
            title="Example claim",
            verdict="unverified",
            confidence="low",
            narrative="Not enough evidence.",
            topics=["environmental-impact"],
            verification_level="claimed",
            cap_rationale="Only one kind of source.",
            seo_title="Example claim",
        ),
    )


@pytest.fixture
def pipeline_without_models(monkeypatch):
    """Stub research, analyst and auditor; the ingest model is left to the test."""

    async def _fake_research(*args, **kwargs):
        return ResearchOutput(urls=[*_CACHED, _PAGE_URL], trace={"mode": "decomposed"})

    async def _fake_run(agent, prompt, timeout_s, **kwargs):
        return _analyst_output(), [], None

    async def _fake_audit(*args, **kwargs):
        return None

    async def _no_wait(seconds: float) -> None:
        return None

    monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
    monkeypatch.setattr("orchestrator.pipeline.build_analyst_prompt", lambda *a, **k: "prompt")
    monkeypatch.setattr("orchestrator.pipeline._run_with_null_retry", _fake_run)
    monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)
    monkeypatch.setattr("ingestor.tools.wayback._wait", _no_wait)


@pytest.fixture
def stubbed_pipeline(pipeline_without_models, stub_ingest_model):
    return stub_ingest_model


async def _run(tmp_path: Path, *, skip_wayback: bool = False) -> tuple[dict, dict]:
    """Run research_claim; return the fresh source's frontmatter and the sidecar."""
    _write_cached_sources(tmp_path)
    cfg = VerifyConfig(
        model="test", max_sources=8, skip_wayback=skip_wayback, repo_root=str(tmp_path)
    )
    result = await research_claim("claim text", cfg)
    source_fm, _ = parse_frontmatter(
        (tmp_path / "research" / "sources" / "2026" / "page.md").read_text()
    )
    sidecar = yaml.safe_load(sidecar_path_for(tmp_path / result.claim_path).read_text())
    return source_fm, sidecar


def _entries(sidecar: dict) -> dict[str, dict]:
    return {e["id"]: e for e in sidecar["sources_consulted"]}


@pytest.mark.asyncio
async def test_snapshot_found_sets_archived_url_and_records_found(tmp_path, stubbed_pipeline) -> None:
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        mock.get(_TIMEGATE).mock(
            return_value=httpx.Response(302, headers={"location": _SNAPSHOT})
        )
        source_fm, sidecar = await _run(tmp_path)

    assert source_fm["archived_url"] == _SNAPSHOT
    entries = _entries(sidecar)
    assert entries["2026/page"]["archive"] == {"status": "found"}
    # A lookup in code is not a recovery of a lost page.
    assert "acquisition" not in entries["2026/page"]
    # Dedup hits were not looked up.
    for i in range(3):
        assert "archive" not in entries[f"2025/cached-{i}"]


@pytest.mark.asyncio
async def test_rate_limited_lookup_records_failed_and_clears_model_link(
    tmp_path, stubbed_pipeline
) -> None:
    stubbed_pipeline["archived_url"] = "https://web.archive.org/web/2020/https://example.org/page"
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(429))
        save = mock.get(_SAVE).mock(return_value=httpx.Response(200))
        source_fm, sidecar = await _run(tmp_path)

    assert "archived_url" not in source_fm
    archive = _entries(sidecar)["2026/page"]["archive"]
    assert archive["status"] == "failed"
    assert "429" in archive["error"]
    assert timegate.call_count == 2
    assert save.called is False


@pytest.mark.asyncio
async def test_skip_wayback_records_not_attempted(tmp_path, stubbed_pipeline) -> None:
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(404))
        _source_fm, sidecar = await _run(tmp_path, skip_wayback=True)

    assert _entries(sidecar)["2026/page"]["archive"] == {"status": "not-attempted"}
    assert timegate.called is False


@pytest.mark.asyncio
async def test_lookup_time_limit_records_failed(tmp_path, stubbed_pipeline, monkeypatch) -> None:
    import asyncio

    async def _slow(request):
        await asyncio.sleep(1)
        return httpx.Response(404)

    monkeypatch.setattr("ingestor.tools.wayback.archive_lookup_budget_s", lambda: 0.01)
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        mock.get(_TIMEGATE).mock(side_effect=_slow)
        source_fm, sidecar = await _run(tmp_path)

    assert "archived_url" not in source_fm
    archive = _entries(sidecar)["2026/page"]["archive"]
    assert archive["status"] == "failed"
    assert "timed out" in archive["error"]


@pytest.mark.asyncio
async def test_light_research_does_not_archive_the_page_it_discards(
    stub_ingest_model, monkeypatch
) -> None:
    """Onboard light research keeps only the summary, so it makes no archive request."""
    import asyncio

    from common.models import EntityType
    from orchestrator.pipeline import gather_light_research

    async def _no_probe(*args, **kwargs):
        return []

    monkeypatch.setattr("orchestrator.pipeline._probe_collision_suggestions", _no_probe)
    cfg = VerifyConfig(model="test", skip_wayback=False, repo_root="/tmp")
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(404))
        save = mock.get(_SAVE).mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient() as client:
            bundle = await gather_light_research(
                "Example", EntityType.COMPANY, cfg, asyncio.Semaphore(2), client,
                seed_url=_PAGE_URL,
            )

    assert bundle.raw_description == "The stored page."
    assert timegate.called is False
    assert save.called is False


@pytest.mark.asyncio
async def test_no_capture_when_saves_are_off(
    tmp_path, pipeline_without_models, stub_ingest_model_calling_wayback
) -> None:
    """``allow_save=False`` (dr claim-probe) keeps both the model's tool and the lookup in code to TimeGate."""
    from orchestrator.pipeline import verify_claim

    _write_cached_sources(tmp_path)
    cfg = VerifyConfig(model="test", max_sources=8, allow_save=False, repo_root=str(tmp_path))
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        timegate = mock.get(_TIMEGATE).mock(return_value=httpx.Response(404))
        save = mock.get(_SAVE).mock(
            return_value=httpx.Response(302, headers={"location": _SNAPSHOT})
        )
        result = await verify_claim("Example", "claim text", cfg)

    assert [url for url, _sf in result.source_files] == [_PAGE_URL]
    assert timegate.call_count == 2
    assert save.called is False
    assert result.archive[_PAGE_URL]["status"] == "failed"
