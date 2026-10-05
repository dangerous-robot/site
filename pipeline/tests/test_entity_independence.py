"""The claim entity's own pages are first-party for its claims.

A source's file-level ``independence`` is entity-agnostic; a brave.com
page is first-party on a Brave claim. The match is applied per claim and
recorded as ``source_overrides``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyst.agent import AnalystOutput, EntityResolution, SourceOverride, VerdictAssessment
from common.frontmatter import parse_frontmatter
from common.models import EntityType, Independence
from common.source_classification import EntityIdentity, entity_first_party_reason
from ingestor.models import SourceFile
from orchestrator.entity_resolution import ResolvedEntity, entity_identity_for
from orchestrator.pipeline import VerifyConfig, research_claim, verify_claim
from researcher.decomposed import ResearchOutput

FORUM_URL = "https://community.brave.app/t/brave-sync-servers-location/631793"

BRAVE_WITH_PARENT = EntityIdentity.from_parts(
    names=["Brave Browser", "Brave Software"],
    websites=["https://brave.com", "https://brave.com/about/#company-info"],
)
BRAVE_NO_PARENT = EntityIdentity.from_parts(
    names=["Brave Browser"], websites=["https://brave.com"]
)


# --- E1: match helper (pure) ------------------------------------------------


def test_entity_host_match() -> None:
    reason = entity_first_party_reason(
        "Brave Software", "https://brave.com/transparency/", BRAVE_WITH_PARENT
    )
    assert reason is not None
    assert "brave.com" in reason


def test_parent_publisher_match() -> None:
    reason = entity_first_party_reason("Brave Software", FORUM_URL, BRAVE_WITH_PARENT)
    assert reason is not None
    assert "Brave Software" in reason


def test_no_parent_no_forum_match() -> None:
    # Why E3 links Brave Browser to Brave Software: without the parent the
    # forum thread on community.brave.app stays unmatched.
    assert entity_first_party_reason("Brave Software", FORUM_URL, BRAVE_NO_PARENT) is None


def test_unrelated_publisher_no_match() -> None:
    assert (
        entity_first_party_reason("AWS", "https://aws.amazon.com/sustainability", BRAVE_WITH_PARENT)
        is None
    )


def test_lookalike_hosts_no_match() -> None:
    assert entity_first_party_reason("Someone", "https://notbrave.com/x", BRAVE_WITH_PARENT) is None
    assert (
        entity_first_party_reason("Someone", "https://brave.com.example.net/x", BRAVE_WITH_PARENT)
        is None
    )
    assert (
        entity_first_party_reason("Someone", "https://search.brave.com/x", BRAVE_WITH_PARENT)
        is not None
    )


def test_www_and_case_ignored_on_host() -> None:
    assert (
        entity_first_party_reason("Someone", "https://WWW.Brave.com/x", BRAVE_NO_PARENT)
        is not None
    )


def test_substring_publisher_no_match() -> None:
    meta = EntityIdentity.from_parts(names=["Meta"], websites=[])
    assert entity_first_party_reason("Metacritic", "https://metacritic.com/x", meta) is None


def test_publisher_suffix_and_punctuation_ignored() -> None:
    brave_sw = EntityIdentity.from_parts(names=["Brave Software"], websites=[])
    assert entity_first_party_reason("Brave Software, Inc.", "https://x.org/a", brave_sw) is not None


def test_short_publisher_needs_alias() -> None:
    assert entity_first_party_reason("Brave", FORUM_URL, BRAVE_WITH_PARENT) is None
    with_alias = EntityIdentity.from_parts(
        names=["Brave Browser", "Brave Software", "Brave"],
        websites=["https://brave.com"],
    )
    assert entity_first_party_reason("Brave", FORUM_URL, with_alias) is not None


# --- E1: identity from a resolved entity ------------------------------------


def _resolved(parent: str | None) -> ResolvedEntity:
    return ResolvedEntity(
        entity_ref="products/brave-browser",
        entity_name="Brave Browser",
        entity_type=EntityType.PRODUCT,
        entity_description="",
        website="https://brave.com",
        parent_company=parent,
    )


def test_identity_loads_parent_file(tmp_path: Path) -> None:
    parent = tmp_path / "research" / "entities" / "companies" / "brave-software.md"
    parent.parent.mkdir(parents=True)
    parent.write_text(
        "---\nname: Brave Software\ntype: company\n"
        "website: https://brave.com/about/#company-info\n"
        "aliases:\n- Brave\n---\n",
        encoding="utf-8",
    )
    identity = entity_identity_for(_resolved("companies/brave-software"), tmp_path)
    assert {"brave browser", "brave software", "brave"} <= identity.names
    assert identity.hosts == frozenset({"brave.com"})


def test_identity_falls_back_to_parent_name_when_file_missing(tmp_path: Path) -> None:
    identity = entity_identity_for(_resolved("companies/brave-software"), tmp_path)
    assert "brave software" in identity.names


# --- E2: verify_claim relabels the analyst's pool and records overrides -----

TRANSPARENCY_URL = "https://brave.com/transparency/"
OTHER_URLS = [
    "https://aws.amazon.com/sustainability",
    "https://sustainability.google/reports/",
    "https://aws.amazon.com/blogs/renewable",
]


def _write_parent(repo_root: Path) -> None:
    path = repo_root / "research" / "entities" / "companies" / "brave-software.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nname: Brave Software\ntype: company\n"
        "website: https://brave.com/about/#company-info\n---\n",
        encoding="utf-8",
    )


def _write_cached_transparency(repo_root: Path) -> None:
    path = repo_root / "research" / "sources" / "2025" / "transparency.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"url: {TRANSPARENCY_URL}\n"
        "title: Brave transparency report\n"
        "publisher: Brave Software\n"
        "accessed_date: 2026-01-01\n"
        "kind: report\n"
        "independence: independent\n"
        "summary: Brave publishes a transparency report.\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )


def _fresh(url: str, slug: str, publisher: str, independence: str | None) -> SourceFile:
    fm = {
        "url": url,
        "title": f"{publisher} page {slug}",
        "publisher": publisher,
        "accessed_date": "2026-10-04",
        "kind": "article",
        "summary": "A page.",
    }
    if independence:
        fm["independence"] = independence
    return SourceFile.model_validate(
        {"frontmatter": fm, "body": "Body.", "slug": slug, "year": 2026}
    )


def _verdict(overrides: list[SourceOverride] | None) -> AnalystOutput:
    return AnalystOutput(
        entity=EntityResolution(
            entity_name="Brave Browser", entity_type="product", entity_description="A browser."
        ),
        verdict=VerdictAssessment(
            title="Brave hosts on renewable energy",
            verdict="unverified",
            confidence="low",
            narrative="No third party links Brave to renewable hosting.",
            topics=["environmental-impact"],
            verification_level="claimed",
            cap_rationale="Only Brave's own pages address the claim.",
            source_overrides=overrides,
            seo_title="Brave renewable hosting claim",
        ),
    )


def _patch_pipeline(monkeypatch, analyst_overrides=None) -> dict:
    captured: dict = {}
    urls = [TRANSPARENCY_URL, FORUM_URL, *OTHER_URLS]

    async def _fake_research(client, entity, claim, cfg, sem, **kwargs):
        return ResearchOutput(urls=list(urls), trace={"mode": "decomposed"})

    async def _fake_ingest(client, urls_in, cfg, sem, **kwargs):
        files = [
            (FORUM_URL, _fresh(FORUM_URL, "631793", "Brave Software", "independent")),
            (OTHER_URLS[0], _fresh(OTHER_URLS[0], "sustainability", "AWS", None)),
            (OTHER_URLS[1], _fresh(OTHER_URLS[1], "reports", "Google", None)),
            (OTHER_URLS[2], _fresh(OTHER_URLS[2], "renewable", "AWS", "independent")),
        ]
        return [f for f in files if f[0] in urls_in], []

    async def _fake_analyse(entity_name, claim_text, sources, cfg, **kwargs):
        captured["sources"] = [dict(s) for s in sources]
        return _verdict(analyst_overrides), None

    async def _fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
    monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
    monkeypatch.setattr("orchestrator.pipeline._analyse_claim", _fake_analyse)
    monkeypatch.setattr("orchestrator.pipeline._audit_claim", _fake_audit)
    return captured


def _brave_resolved() -> ResolvedEntity:
    return _resolved("companies/brave-software")


@pytest.mark.asyncio
async def test_verify_claim_marks_entity_sources_first_party(tmp_path: Path, monkeypatch) -> None:
    _write_parent(tmp_path)
    _write_cached_transparency(tmp_path)
    captured = _patch_pipeline(monkeypatch)
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=8)

    result = await verify_claim(
        "Brave Browser", "Brave is hosted on renewable energy", cfg,
        resolved_entity=_brave_resolved(),
    )

    labels = {s["url"]: s["independence"] for s in captured["sources"]}
    assert labels[TRANSPARENCY_URL] == "first-party"  # cached hit
    assert labels[FORUM_URL] == "first-party"  # model said independent
    assert labels[OTHER_URLS[0]] == "independent"
    assert labels[OTHER_URLS[2]] == "independent"

    overrides = result.analyst_output.verdict.source_overrides
    by_source = {o.source: o for o in overrides}
    assert set(by_source) == {"2025/transparency", "2026/631793"}
    for o in overrides:
        assert o.independence == Independence.FIRST_PARTY
    assert "brave.com" in by_source["2025/transparency"].reason
    assert "Brave Software" in by_source["2026/631793"].reason


@pytest.mark.asyncio
async def test_verify_claim_does_not_duplicate_analyst_override(tmp_path: Path, monkeypatch) -> None:
    _write_parent(tmp_path)
    _write_cached_transparency(tmp_path)
    analyst_override = SourceOverride(
        source="2025/transparency",
        independence=Independence.FIRST_PARTY,
        reason="Brave's own report.",
    )
    _patch_pipeline(monkeypatch, analyst_overrides=[analyst_override])
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=8)

    result = await verify_claim(
        "Brave Browser", "Brave is hosted on renewable energy", cfg,
        resolved_entity=_brave_resolved(),
    )

    sources = [o.source for o in result.analyst_output.verdict.source_overrides]
    assert sorted(sources) == ["2025/transparency", "2026/631793"]
    kept = next(o for o in result.analyst_output.verdict.source_overrides if o.source == "2025/transparency")
    assert kept.reason == "Brave's own report."


@pytest.mark.asyncio
async def test_verify_claim_without_resolved_entity_leaves_labels(tmp_path: Path, monkeypatch) -> None:
    _write_cached_transparency(tmp_path)
    captured = _patch_pipeline(monkeypatch)
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=8)

    result = await verify_claim("Brave Browser", "Brave is hosted on renewable energy", cfg)

    labels = {s["url"]: s["independence"] for s in captured["sources"]}
    assert labels[TRANSPARENCY_URL] == "independent"
    assert result.analyst_output.verdict.source_overrides is None


@pytest.mark.asyncio
async def test_research_claim_writes_entity_overrides(tmp_path: Path, monkeypatch) -> None:
    _write_parent(tmp_path)
    _write_cached_transparency(tmp_path)
    captured = _patch_pipeline(monkeypatch)
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=8)

    result = await research_claim(
        "Brave is hosted on renewable energy", cfg, resolved_entity=_brave_resolved()
    )

    labels = {s["url"]: s["independence"] for s in captured["sources"]}
    assert labels[FORUM_URL] == "first-party"
    claim_fm, _ = parse_frontmatter((tmp_path / result.claim_path).read_text())
    written = {o["source"]: o["independence"] for o in claim_fm["source_overrides"]}
    assert written == {"2025/transparency": "first-party", "2026/631793": "first-party"}
    # The source file keeps its entity-agnostic label.
    forum_fm, _ = parse_frontmatter(
        (tmp_path / "research" / "sources" / "2026" / "631793.md").read_text()
    )
    assert forum_fm["independence"] == "independent"
