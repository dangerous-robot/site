"""The claim entity's own pages are first-party for its claims, and sources
about someone else do not count for or against the entity.

A source's file-level ``independence`` is entity-agnostic; a brave.com
page is first-party on a Brave claim. The match is applied per claim and
recorded as ``source_overrides``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyst.agent import (
    AnalystOutput,
    EntityResolution,
    SourceOverride,
    VerdictAssessment,
    verdict_only_agent,
)
import yaml

from common.frontmatter import parse_frontmatter
from common.models import Confidence, EntityType, Independence, VerificationLevel
from common.source_classification import (
    EntityIdentity,
    entity_affiliated,
    entity_first_party_reason,
    publisher_named_in_claim,
    source_engages_entity,
)
from ingestor.models import SourceFile
from orchestrator.entity_resolution import ResolvedEntity, entity_identity_for, parse_entity_ref
from orchestrator.persistence import fit_verdict_to_written_pool, verdict_write_kwargs
from orchestrator.pipeline import VerifyConfig, _apply_entity_match, research_claim, verify_claim
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


# --- E3: the real Brave entities --------------------------------------------


def test_brave_entity_has_parent(repo_root: Path) -> None:
    resolved = parse_entity_ref("products/brave-browser", repo_root)
    identity = entity_identity_for(resolved, repo_root)
    assert "brave software" in identity.names
    assert "brave" in identity.names  # alias on companies/brave-software
    assert entity_first_party_reason("Brave Software", FORUM_URL, identity) is not None


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


def _fresh(
    url: str,
    slug: str,
    publisher: str,
    independence: str | None,
    *,
    body: str = "Body.",
    summary: str = "A page.",
    kind: str = "article",
) -> SourceFile:
    fm = {
        "url": url,
        "title": f"{publisher} page {slug}",
        "publisher": publisher,
        "accessed_date": "2026-10-04",
        "kind": kind,
        "summary": summary,
    }
    if independence:
        fm["independence"] = independence
    return SourceFile.model_validate(
        {"frontmatter": fm, "body": body, "slug": slug, "year": 2026}
    )


def _verdict(
    overrides: list[SourceOverride] | None,
    level: str = "claimed",
    confidence: str = "low",
    cap_rationale: str | None = "Only Brave's own pages address the claim.",
) -> AnalystOutput:
    return AnalystOutput(
        entity=EntityResolution(
            entity_name="Brave Browser", entity_type="product", entity_description="A browser."
        ),
        verdict=VerdictAssessment(
            title="Brave hosts on renewable energy",
            verdict="unverified",
            confidence=confidence,
            narrative="No third party links Brave to renewable hosting.",
            topics=["environmental-impact"],
            verification_level=level,
            cap_rationale=cap_rationale,
            source_overrides=overrides,
            seo_title="Brave renewable hosting claim",
        ),
    )


def _default_files() -> list[tuple[str, SourceFile]]:
    return [
        (FORUM_URL, _fresh(FORUM_URL, "631793", "Brave Software", "independent")),
        (OTHER_URLS[0], _fresh(OTHER_URLS[0], "sustainability", "AWS", None)),
        (OTHER_URLS[1], _fresh(OTHER_URLS[1], "reports", "Google", None)),
        (
            OTHER_URLS[2],
            _fresh(
                OTHER_URLS[2], "renewable", "AWS", "independent",
                body="AWS hosts Brave Browser on renewable power.",
            ),
        ),
    ]


def _patch_pipeline(monkeypatch, analyst_overrides=None, files=None, verdict_kwargs=None) -> dict:
    captured: dict = {}
    files = files if files is not None else _default_files()
    urls = [TRANSPARENCY_URL, *[u for u, _ in files]]

    async def _fake_research(client, entity, claim, cfg, sem, **kwargs):
        return ResearchOutput(urls=list(urls), trace={"mode": "decomposed"})

    async def _fake_ingest(client, urls_in, cfg, sem, **kwargs):
        return [f for f in files if f[0] in urls_in], []

    # The entity match runs inside _analyse_claim, so the analyst is faked one
    # layer down: capture what the prompt is built from, stub the model run.
    def _fake_prompt(entity_name, claim_text, sources, **kwargs):
        captured["sources"] = [dict(s) for s in sources]
        return "prompt"

    async def _fake_run(agent, prompt, timeout_s, **kwargs):
        out = _verdict(analyst_overrides, **(verdict_kwargs or {}))
        return (out.verdict if agent is verdict_only_agent else out), [], None

    async def _fake_audit(*args, **kwargs):
        return None

    monkeypatch.setattr("orchestrator.pipeline._research", _fake_research)
    monkeypatch.setattr("orchestrator.pipeline._ingest_urls", _fake_ingest)
    monkeypatch.setattr("orchestrator.pipeline.build_analyst_prompt", _fake_prompt)
    monkeypatch.setattr("orchestrator.pipeline._run_with_null_retry", _fake_run)
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
    assert labels[OTHER_URLS[0]] == "unknown"  # says nothing about Brave
    assert labels[OTHER_URLS[1]] == "unknown"  # Google's own page, not Brave's
    assert labels[OTHER_URLS[2]] == "independent"  # names Brave Browser

    overrides = result.analyst_output.verdict.source_overrides
    by_source = {o.source: o for o in overrides}
    assert set(by_source) == {
        "2025/transparency", "2026/631793", "2026/sustainability", "2026/reports",
    }
    assert by_source["2025/transparency"].independence == Independence.FIRST_PARTY
    assert by_source["2026/631793"].independence == Independence.FIRST_PARTY
    assert "brave.com" in by_source["2025/transparency"].reason
    assert "Brave Software" in by_source["2026/631793"].reason
    for sid in ("2026/sustainability", "2026/reports"):
        assert by_source[sid].independence == Independence.UNKNOWN
        assert by_source[sid].reason.startswith("Off-entity")


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
    assert sorted(sources) == [
        "2025/transparency", "2026/631793", "2026/reports", "2026/sustainability",
    ]
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
    assert written == {
        "2025/transparency": "first-party",
        "2026/631793": "first-party",
        "2026/sustainability": "unknown",
        "2026/reports": "unknown",
    }
    # The source file keeps its entity-agnostic label.
    forum_fm, _ = parse_frontmatter(
        (tmp_path / "research" / "sources" / "2026" / "631793.md").read_text()
    )
    assert forum_fm["independence"] == "independent"


# --- Off-entity sources: neither independent nor first-party ----------------


def test_source_engages_entity_whole_word_and_host() -> None:
    chatgptree = EntityIdentity.from_parts(["ChatGPTree"], ["https://chatgptree.com"])
    assert not source_engages_entity({"body": "ChatGPT runs on Azure."}, chatgptree)
    assert source_engages_entity({"summary": "A review of ChatGPTree."}, chatgptree)
    assert source_engages_entity({"key_quotes": ["See chatgptree.com/green."]}, chatgptree)
    assert not source_engages_entity({"body": "notchatgptree.com is a parody."}, chatgptree)
    assert source_engages_entity({"title": "Brave Browser, reviewed"}, BRAVE_NO_PARENT)
    assert not source_engages_entity({"title": "Bravebrowser fans"}, BRAVE_NO_PARENT)


def test_publisher_named_in_claim() -> None:
    claim = "Euria is hosted on renewable energy by Infomaniak"
    assert publisher_named_in_claim("Infomaniak", claim)
    assert publisher_named_in_claim("Infomaniak, Inc.", claim)
    assert not publisher_named_in_claim("Google", claim)
    assert not publisher_named_in_claim("Info", claim)
    assert not publisher_named_in_claim("", claim)


def test_entity_linkedin_post_is_first_party() -> None:
    reason = entity_first_party_reason(
        "LinkedIn", "https://www.linkedin.com/posts/brave-browser_x-activity-1", BRAVE_NO_PARENT
    )
    assert reason is not None
    assert "linkedin.com" in reason
    assert (
        entity_first_party_reason(
            "LinkedIn", "https://www.linkedin.com/posts/brave-browsers-fan_x", BRAVE_NO_PARENT
        )
        is None
    )


def _sd(source_id: str, url: str, publisher: str, independence: str, **text) -> dict:
    return {
        "source_id": source_id,
        "url": url,
        "publisher": publisher,
        "independence": independence,
        "kind": text.pop("kind", "article"),
        "title": text.pop("title", f"{publisher} page"),
        "summary": text.pop("summary", "A page."),
        "key_quotes": text.pop("key_quotes", []),
        "body": text.pop("body", "Body."),
    }


def test_entity_matched_first_party_page_is_left_alone(tmp_path: Path) -> None:
    # The entity's own page already labelled first-party stays first-party
    # with no override; only pages from other organizations are relabelled.
    sources = [_sd("2025/transparency", TRANSPARENCY_URL, "Brave Software", "first-party")]
    overrides = _apply_entity_match(
        sources, _brave_resolved(), tmp_path, "Brave is hosted on renewable energy"
    )
    assert overrides == []
    assert sources[0]["independence"] == "first-party"


def test_google_paper_on_chatgpt_claim_is_unknown(tmp_path: Path) -> None:
    chatgpt = ResolvedEntity(
        entity_ref="products/chatgpt",
        entity_name="ChatGPT",
        entity_type=EntityType.PRODUCT,
        entity_description="",
        website="https://chatgpt.com",
    )
    sources = [
        _sd(
            "2025/gemini-paper", "https://arxiv.org/abs/2508.15734", "Google", "first-party",
            body="We compare Gemini with ChatGPT on energy per prompt.",
        )
    ]
    overrides = _apply_entity_match(
        sources, chatgpt, tmp_path, "ChatGPT is hosted on renewable energy"
    )
    assert sources[0]["independence"] == "unknown"
    assert [o.source for o in overrides] == ["2025/gemini-paper"]
    assert overrides[0].independence == Independence.UNKNOWN
    assert overrides[0].reason.startswith("Off-entity: first-party for Google")


def test_off_entity_note_says_what_was_checked(tmp_path: Path) -> None:
    # The independent rule checks the entity mention and the publisher, not
    # providers the source mentions, and the note says only that.
    sources = [
        _sd(
            "2026/scaleway-news", "https://news.example.com/scaleway", "Daily News", "independent",
            body="Scaleway's data centers run on renewable power.",
        )
    ]
    overrides = _apply_entity_match(
        sources, _brave_resolved(), tmp_path, "Brave runs on Scaleway's renewable data centers"
    )
    assert overrides[0].reason == (
        "Off-entity: the source does not mention Brave Browser, "
        "and the claim does not name its publisher."
    )


def test_off_entity_reason_fits_override_limit(tmp_path: Path) -> None:
    sources = [_sd("2026/long", "https://x.org/a", "P" * 500, "first-party")]
    overrides = _apply_entity_match(sources, _brave_resolved(), tmp_path, "Brave is green")
    assert len(overrides[0].reason) <= 300


def test_subject_entity_skips_off_entity_rule(tmp_path: Path) -> None:
    subject = ResolvedEntity(
        entity_ref="subjects/data-centers",
        entity_name="Data centers",
        entity_type=EntityType.SUBJECT,
        entity_description="",
    )
    sources = [
        _sd("2026/aws", OTHER_URLS[0], "AWS", "independent"),
        _sd("2026/google", OTHER_URLS[1], "Google", "first-party"),
    ]
    overrides = _apply_entity_match(sources, subject, tmp_path, "Data centers use water")
    assert overrides == []
    assert [s["independence"] for s in sources] == ["independent", "first-party"]


INFOMANIAK_URL = "https://www.infomaniak.com/en/ecology"
GOOGLE_DOCS_URL = "https://cloud.google.com/sustainability/brave"
AWS_DOCS_URL = "https://docs.aws.amazon.com/customers/brave"
REVIEW_URL = "https://www.example-news.com/brave-review"


def _off_entity_files() -> list[tuple[str, SourceFile]]:
    return [
        (OTHER_URLS[1], _fresh(OTHER_URLS[1], "reports", "Google", "first-party")),
        (OTHER_URLS[0], _fresh(OTHER_URLS[0], "sustainability", "AWS", "independent")),
        (
            AWS_DOCS_URL,
            _fresh(
                AWS_DOCS_URL, "brave", "Amazon Web Services", "first-party",
                body="Brave Browser is an AWS customer.", kind="documentation",
            ),
        ),
        (
            REVIEW_URL,
            _fresh(
                REVIEW_URL, "brave-review", "Example News", "independent",
                summary="A look at how Brave Browser powers its servers.",
            ),
        ),
        (INFOMANIAK_URL, _fresh(INFOMANIAK_URL, "ecology", "Infomaniak", "first-party")),
    ]


@pytest.mark.asyncio
async def test_verify_claim_marks_off_entity_sources_unknown(tmp_path: Path, monkeypatch) -> None:
    _write_parent(tmp_path)
    _write_cached_transparency(tmp_path)
    captured = _patch_pipeline(monkeypatch, files=_off_entity_files())
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=8)

    result = await verify_claim(
        "Brave Browser", "Brave is hosted on renewable energy by Infomaniak", cfg,
        resolved_entity=_brave_resolved(),
    )

    labels = {s["url"]: s["independence"] for s in captured["sources"]}
    assert labels[OTHER_URLS[1]] == "unknown"  # Google first-party, no Brave mention
    assert labels[OTHER_URLS[0]] == "unknown"  # AWS independent, no Brave mention
    assert labels[AWS_DOCS_URL] == "unknown"  # another organization's own docs naming Brave
    assert labels[REVIEW_URL] == "independent"  # names Brave Browser
    assert labels[INFOMANIAK_URL] == "first-party"  # the claim names Infomaniak

    by_source = {o.source: o for o in result.analyst_output.verdict.source_overrides}
    for sid in ("2026/reports", "2026/sustainability", "2026/brave"):
        assert by_source[sid].independence == Independence.UNKNOWN
        assert by_source[sid].reason.startswith("Off-entity")
    assert "2026/brave-review" not in by_source
    assert "2026/ecology" not in by_source


@pytest.mark.asyncio
async def test_off_entity_override_beats_analyst_first_party(tmp_path: Path, monkeypatch) -> None:
    _write_parent(tmp_path)
    _write_cached_transparency(tmp_path)
    analyst_override = SourceOverride(
        source="2026/reports",
        independence=Independence.FIRST_PARTY,
        reason="Google restates its own numbers.",
    )
    _patch_pipeline(monkeypatch, analyst_overrides=[analyst_override])
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=8)

    result = await verify_claim(
        "Brave Browser", "Brave is hosted on renewable energy", cfg,
        resolved_entity=_brave_resolved(),
    )

    reports = [o for o in result.analyst_output.verdict.source_overrides if o.source == "2026/reports"]
    assert len(reports) == 1
    assert reports[0].independence == Independence.UNKNOWN
    assert reports[0].reason.startswith("Off-entity")


# --- The written level fits the written source list -------------------------


def _assessment(level: str, confidence: str = "medium", cap: str | None = None, overrides=None):
    return _verdict(overrides, level=level, confidence=confidence, cap_rationale=cap).verdict


def _pool(*labels: tuple[str, str, str]) -> list[dict]:
    return [
        {"source_id": sid, "independence": ind, "kind": kind}
        for sid, ind, kind in labels
    ]


def test_fit_multiply_with_no_independent_and_first_party_docs_is_self_reported() -> None:
    verdict = _assessment("multiply-verified")
    sources = _pool(("a", "first-party", "documentation"), ("b", "unknown", "article"))
    note = fit_verdict_to_written_pool(verdict, sources, ["a", "b"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.SELF_REPORTED
    assert verdict.confidence == Confidence.LOW
    assert verdict.cap_rationale == (
        "Confidence is capped at low: no source on this claim independently addresses Brave Browser."
    )
    assert note and "multiply-verified" in note and "self-reported" in note


def test_fit_only_unknown_sources_is_claimed() -> None:
    verdict = _assessment("independently-verified")
    sources = _pool(("a", "unknown", "report"), ("b", "unknown", "article"))
    fit_verdict_to_written_pool(verdict, sources, ["a", "b"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.CLAIMED
    assert verdict.confidence == Confidence.LOW


def test_fit_multiply_with_one_independent_is_independently_verified() -> None:
    verdict = _assessment("multiply-verified")
    sources = _pool(("a", "independent", "article"), ("b", "first-party", "report"))
    fit_verdict_to_written_pool(verdict, sources, ["a", "b"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.INDEPENDENTLY_VERIFIED
    assert verdict.confidence == Confidence.MEDIUM
    assert verdict.cap_rationale is None


def test_fit_partially_verified_needs_one_independent() -> None:
    verdict = _assessment("partially-verified")
    sources = _pool(("a", "first-party", "blog"))
    fit_verdict_to_written_pool(verdict, sources, ["a"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.CLAIMED

    kept = _assessment("partially-verified")
    sources = _pool(("a", "first-party", "report"), ("b", "independent", "article"))
    assert fit_verdict_to_written_pool(kept, sources, ["a", "b"], "Brave Browser") is None
    assert kept.verification_level == VerificationLevel.PARTIALLY_VERIFIED


def test_fit_counts_only_written_sources() -> None:
    # The analyst saw two independents; the written list keeps one.
    verdict = _assessment("multiply-verified")
    sources = _pool(("a", "independent", "article"), ("b", "independent", "article"))
    fit_verdict_to_written_pool(verdict, sources, ["a"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.INDEPENDENTLY_VERIFIED


def test_fit_prunes_overrides_for_unwritten_sources() -> None:
    overrides = [
        SourceOverride(source="gone", independence=Independence.INDEPENDENT, reason="x"),
        SourceOverride(source="a", independence=Independence.INDEPENDENT, reason="y"),
    ]
    verdict = _assessment("multiply-verified", overrides=overrides)
    sources = _pool(("a", "unknown", "article"), ("b", "first-party", "blog"))
    fit_verdict_to_written_pool(verdict, sources, ["a", "b"], "Brave Browser")
    assert [o.source for o in verdict.source_overrides] == ["a"]
    assert verdict.verification_level == VerificationLevel.INDEPENDENTLY_VERIFIED


def test_fit_override_without_independence_keeps_the_source_label() -> None:
    overrides = [SourceOverride(source="a", reason="a note only")]
    verdict = _assessment("independently-verified", overrides=overrides)
    sources = _pool(("a", "independent", "article"))
    assert fit_verdict_to_written_pool(verdict, sources, ["a"], "Brave Browser") is None


def test_fit_keeps_existing_cap_rationale() -> None:
    verdict = _assessment("multiply-verified", cap="The analyst's own words.")
    sources = _pool(("a", "first-party", "blog"))
    fit_verdict_to_written_pool(verdict, sources, ["a"], "Brave Browser")
    assert verdict.cap_rationale == "The analyst's own words."


def test_fit_leaves_a_supported_level_alone() -> None:
    verdict = _assessment("multiply-verified")
    sources = _pool(("a", "independent", "article"), ("b", "independent", "report"))
    assert fit_verdict_to_written_pool(verdict, sources, ["a", "b"], "Brave Browser") is None
    assert verdict.verification_level == VerificationLevel.MULTIPLY_VERIFIED
    assert verdict.confidence == Confidence.MEDIUM


@pytest.mark.asyncio
async def test_research_claim_writes_the_fitted_level(tmp_path: Path, monkeypatch) -> None:
    _write_parent(tmp_path)
    _write_cached_transparency(tmp_path)
    _patch_pipeline(
        monkeypatch,
        verdict_kwargs={"level": "multiply-verified", "confidence": "medium", "cap_rationale": None},
    )
    cfg = VerifyConfig(model="test", repo_root=str(tmp_path), max_sources=8)

    result = await research_claim(
        "Brave is hosted on renewable energy", cfg, resolved_entity=_brave_resolved()
    )

    claim_path = tmp_path / result.claim_path
    claim_fm, _ = parse_frontmatter(claim_path.read_text())
    # One written source (the AWS page naming Brave) is independent.
    assert claim_fm["verification_level"] == "independently-verified"
    assert claim_fm["confidence"] == "medium"
    sidecar = yaml.safe_load(claim_path.with_name(claim_path.stem + ".audit.yaml").read_text())
    assert "multiply-verified" in sidecar["pipeline_run"]["level_clamp"]


# --- The entity's own pages on a sibling host or under a publisher variant ---


@pytest.mark.parametrize(
    ("entity_ref", "source_id", "url", "publisher", "body"),
    [
        (
            "products/claude", "2026/anthropic-claude-models-overview",
            "https://platform.claude.com/docs/en/about-claude/models/overview",
            "Anthropic (Claude Platform)", "Claude is a family of models.",
        ),
        (
            "products/gemini", "2026/google-gemini-api-models",
            "https://ai.google.dev/gemini-api/docs/models",
            "Google AI for Developers", "Gemini models in the API.",
        ),
        (
            "products/gemini", "2026/cloud-blog",
            "https://cloud.google.com/blog/products/ai/gemini-energy",
            "Google Cloud Blog", "Measuring Gemini's energy per prompt.",
        ),
    ],
)
def test_entity_docs_on_a_sibling_host_stay_first_party(
    repo_root: Path, entity_ref: str, source_id: str, url: str, publisher: str, body: str
) -> None:
    resolved = parse_entity_ref(entity_ref, repo_root)
    sources = [_sd(source_id, url, publisher, "first-party", kind="documentation", body=body)]
    overrides = _apply_entity_match(sources, resolved, repo_root, "It is hosted on renewable energy")
    assert overrides == []
    assert sources[0]["independence"] == "first-party"


def test_affiliated_first_party_that_never_names_the_entity_is_unknown(repo_root: Path) -> None:
    resolved = parse_entity_ref("products/claude", repo_root)
    sources = [_sd(
        "2026/platform-status", "https://status.claude.com/history", "",
        "first-party", title="Status history", body="Incidents by region.",
    )]
    overrides = _apply_entity_match(sources, resolved, repo_root, "Claude is green")
    assert sources[0]["independence"] == "unknown"
    assert [o.source for o in overrides] == ["2026/platform-status"]


def test_unaffiliated_first_party_naming_the_entity_is_still_unknown(repo_root: Path) -> None:
    # Another organization's self-report stays unknown even when it names the entity.
    resolved = parse_entity_ref("products/claude", repo_root)
    sources = [_sd(
        "2026/greenpt-compare", "https://greenpt.ai/compare", "GreenPT",
        "first-party", body="GreenPT uses less energy than Claude.",
    )]
    _apply_entity_match(sources, resolved, repo_root, "Claude is green")
    assert sources[0]["independence"] == "unknown"


def test_publisher_containing_an_entity_word_needs_the_word_whole(tmp_path: Path) -> None:
    # "Brave New World Press" names "brave" only through an alias the entity lacks.
    sources = [_sd(
        "2026/press", "https://bravenewworld.example/a", "Brave New World Press",
        "first-party", body="Brave Browser is reviewed here.",
    )]
    _apply_entity_match(sources, _brave_resolved(), tmp_path, "Brave is green")
    assert sources[0]["independence"] == "unknown"


def test_off_entity_note_names_the_host_when_publisher_is_empty(tmp_path: Path) -> None:
    sources = [_sd("2026/anon", "https://www.greenpt.ai/energy", "", "first-party")]
    overrides = _apply_entity_match(sources, _brave_resolved(), tmp_path, "Brave is green")
    assert overrides[0].reason.startswith("Off-entity: first-party for greenpt.ai, not Brave Browser")


def test_source_engages_entity_counts_www_and_subdomain_mentions() -> None:
    le_chat = EntityIdentity.from_parts(["Le Chat"], ["https://mistral.ai"])
    for body in ("see www.mistral.ai", "https://www.mistral.ai/news", "docs.mistral.ai", "see mistral.ai"):
        assert source_engages_entity({"body": body}, le_chat), body
    for body in ("notmistral.ai", "evil-mistral.ai", "mistral.aix"):
        assert not source_engages_entity({"body": body}, le_chat), body


def test_fit_self_reported_without_first_party_report_is_claimed() -> None:
    verdict = _assessment("self-reported", confidence="low")
    sources = _pool(("a", "unknown", "report"), ("b", "first-party", "blog"))
    note = fit_verdict_to_written_pool(verdict, sources, ["a", "b"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.CLAIMED
    assert note and "self-reported lowered to claimed" in note


def test_fit_self_reported_when_the_only_report_is_unwritten_is_claimed() -> None:
    verdict = _assessment("self-reported", confidence="low")
    sources = _pool(("a", "first-party", "report"), ("b", "first-party", "blog"))
    fit_verdict_to_written_pool(verdict, sources, ["b"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.CLAIMED


@pytest.mark.parametrize("kind", ["report", "documentation", "dataset", "article"])
def test_fit_self_reported_with_first_party_basis_is_kept(kind: str) -> None:
    # A first-party article may back self-reported (the analyst's article boundary call).
    verdict = _assessment("self-reported", confidence="low")
    sources = _pool(("a", "first-party", kind))
    assert fit_verdict_to_written_pool(verdict, sources, ["a"], "Brave Browser") is None
    assert verdict.verification_level == VerificationLevel.SELF_REPORTED


def test_fit_self_reported_with_an_independent_source_is_kept() -> None:
    verdict = _assessment("self-reported", confidence="low")
    sources = _pool(("a", "independent", "article"))
    assert fit_verdict_to_written_pool(verdict, sources, ["a"], "Brave Browser") is None


def test_fit_counts_a_repeated_ref_each_time() -> None:
    # Matches countSourcesByIndependence in src/lib/sourceQuality.ts.
    verdict = _assessment("multiply-verified")
    sources = _pool(("a", "independent", "article"))
    assert fit_verdict_to_written_pool(verdict, sources, ["a", "a"], "Brave Browser") is None


def test_entity_affiliated_ignores_shared_site_hosts() -> None:
    hosted = EntityIdentity.from_parts(["Tiny Bot"], ["https://tinybot.github.io"])
    assert not entity_affiliated("GitHub", "https://github.com/other/repo", hosted)
    assert not entity_affiliated("", "https://someone.github.io/post", hosted)
    claude = EntityIdentity.from_parts(["Claude"], ["https://claude.ai"])
    assert entity_affiliated("", "https://platform.claude.com/docs", claude)
    assert entity_affiliated("", "https://www.claude.co.uk/a", claude)
    assert not entity_affiliated("Claudette Media", "https://claudette.ai/a", claude)


def test_fit_self_reported_lowered_to_claimed_replaces_the_stale_rationale() -> None:
    verdict = _assessment(
        "self-reported", confidence="low",
        cap="Confidence is capped at low -- all sources originate from entity documentation.",
    )
    sources = _pool(("a", "unknown", "documentation"))
    fit_verdict_to_written_pool(verdict, sources, ["a"], "Brave Browser")
    assert verdict.verification_level == VerificationLevel.CLAIMED
    assert verdict.cap_rationale == (
        "Confidence is capped at low: no source on this claim independently addresses Brave Browser."
    )
    assert verdict_write_kwargs(verdict)["cap_rationale_fitted"] is True


def test_fit_keeping_the_analyst_rationale_is_not_marked_fitted() -> None:
    verdict = _assessment("multiply-verified", cap="The analyst's own words.")
    fit_verdict_to_written_pool(verdict, _pool(("a", "first-party", "blog")), ["a"], "Brave Browser")
    assert verdict_write_kwargs(verdict)["cap_rationale_fitted"] is False
