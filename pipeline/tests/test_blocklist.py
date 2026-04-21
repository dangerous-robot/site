"""Unit tests for common.blocklist."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.blocklist import (
    BlocklistEntry,
    FilterDecision,
    filter_urls,
    load_blocklist,
)


@pytest.fixture
def linkedin_entries() -> list[BlocklistEntry]:
    return [BlocklistEntry(host="linkedin.com", reason="403s on anonymous fetch")]


class TestFilterUrls:
    def test_exact_host_match(self, linkedin_entries: list[BlocklistEntry]) -> None:
        kept, dropped = filter_urls(["https://linkedin.com/x"], linkedin_entries)
        assert kept == []
        assert len(dropped) == 1
        assert dropped[0].host == "linkedin.com"

    def test_www_stripped(self, linkedin_entries: list[BlocklistEntry]) -> None:
        kept, dropped = filter_urls(["https://www.linkedin.com/x"], linkedin_entries)
        assert kept == []
        assert len(dropped) == 1

    def test_subdomain_suffix_match(
        self, linkedin_entries: list[BlocklistEntry]
    ) -> None:
        kept, dropped = filter_urls(["https://uk.linkedin.com/x"], linkedin_entries)
        assert kept == []
        assert len(dropped) == 1

    def test_no_false_positive_substring(
        self, linkedin_entries: list[BlocklistEntry]
    ) -> None:
        kept, dropped = filter_urls(["https://notlinkedin.com"], linkedin_entries)
        assert kept == ["https://notlinkedin.com"]
        assert dropped == []

    def test_no_false_positive_different_tld(
        self, linkedin_entries: list[BlocklistEntry]
    ) -> None:
        kept, dropped = filter_urls(["https://linkedin.io"], linkedin_entries)
        assert kept == ["https://linkedin.io"]
        assert dropped == []

    def test_unparseable_url_kept(
        self, linkedin_entries: list[BlocklistEntry]
    ) -> None:
        kept, dropped = filter_urls(["not a url"], linkedin_entries)
        assert kept == ["not a url"]
        assert dropped == []

    def test_empty_blocklist(self) -> None:
        urls = ["https://linkedin.com/x", "https://example.com"]
        kept, dropped = filter_urls(urls, [])
        assert kept == urls
        assert dropped == []

    def test_case_insensitive(
        self, linkedin_entries: list[BlocklistEntry]
    ) -> None:
        kept, dropped = filter_urls(["https://WWW.LinkedIn.com/x"], linkedin_entries)
        assert kept == []
        assert len(dropped) == 1

    def test_preserves_order_and_reason(
        self, linkedin_entries: list[BlocklistEntry]
    ) -> None:
        urls = [
            "https://example.com/a",
            "https://linkedin.com/b",
            "https://example.com/c",
        ]
        kept, dropped = filter_urls(urls, linkedin_entries)
        assert kept == ["https://example.com/a", "https://example.com/c"]
        assert len(dropped) == 1
        d: FilterDecision = dropped[0]
        assert d.url == "https://linkedin.com/b"
        assert d.reason == "403s on anonymous fetch"


class TestLoadBlocklist:
    def test_load_missing_file(self, tmp_path: Path) -> None:
        # No research/blocklist.yaml at all
        assert load_blocklist(tmp_path) == []

    def test_load_parses_reasons(self, tmp_path: Path) -> None:
        research = tmp_path / "research"
        research.mkdir()
        (research / "blocklist.yaml").write_text(
            """
hosts:
  - host: LinkedIn.com
    reason: "403s on anonymous fetch"
  - host: wsj.com
    reason: "paywall"
""",
            encoding="utf-8",
        )
        entries = load_blocklist(tmp_path)
        assert len(entries) == 2
        # Lowercased on load
        assert entries[0].host == "linkedin.com"
        assert entries[0].reason == "403s on anonymous fetch"
        assert entries[1].host == "wsj.com"
        assert entries[1].reason == "paywall"

    def test_load_empty_file(self, tmp_path: Path) -> None:
        research = tmp_path / "research"
        research.mkdir()
        (research / "blocklist.yaml").write_text("", encoding="utf-8")
        assert load_blocklist(tmp_path) == []

    def test_load_skips_entries_without_host(self, tmp_path: Path) -> None:
        research = tmp_path / "research"
        research.mkdir()
        (research / "blocklist.yaml").write_text(
            """
hosts:
  - reason: "missing host key"
  - host: linkedin.com
    reason: "ok"
""",
            encoding="utf-8",
        )
        entries = load_blocklist(tmp_path)
        assert len(entries) == 1
        assert entries[0].host == "linkedin.com"
