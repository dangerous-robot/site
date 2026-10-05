"""The claim entity's own pages are first-party for its claims.

A source's file-level ``independence`` is entity-agnostic; a brave.com
page is first-party on a Brave claim. The match is applied per claim and
recorded as ``source_overrides``.
"""

from __future__ import annotations

from pathlib import Path

from common.models import EntityType
from common.source_classification import EntityIdentity, entity_first_party_reason
from orchestrator.entity_resolution import ResolvedEntity, entity_identity_for

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
