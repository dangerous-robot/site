"""Unit tests for _classify_source_type in orchestrator.persistence."""

from __future__ import annotations

import pytest

from orchestrator.persistence import _classify_source_type


class TestPrimary:
    def test_anthropic_article(self) -> None:
        assert _classify_source_type("Anthropic", "article") == "primary"

    def test_openai_report(self) -> None:
        assert _classify_source_type("OpenAI", "report") == "primary"

    def test_google_blog(self) -> None:
        # Google is a known primary publisher, overrides the blog-is-tertiary rule.
        assert _classify_source_type("Google DeepMind", "blog") == "primary"

    def test_microsoft_dataset(self) -> None:
        assert _classify_source_type("Microsoft", "dataset") == "primary"

    def test_edgar_filing(self) -> None:
        assert _classify_source_type("SEC EDGAR", "report") == "primary"

    def test_sec_gov_substring(self) -> None:
        assert _classify_source_type("sec.gov", "dataset") == "primary"

    def test_documentation_kind_unknown_publisher(self) -> None:
        # Any documentation kind → primary regardless of publisher
        assert _classify_source_type("Some Random Docs Site", "documentation") == "primary"

    def test_case_insensitive(self) -> None:
        assert _classify_source_type("ANTHROPIC", "article") == "primary"
        assert _classify_source_type("anthropic", "article") == "primary"


class TestSecondary:
    def test_arxiv(self) -> None:
        assert _classify_source_type("arXiv", "report") == "secondary"

    def test_ieee(self) -> None:
        assert _classify_source_type("IEEE", "article") == "secondary"

    def test_university(self) -> None:
        assert _classify_source_type("MIT University Press", "report") == "secondary"

    def test_b_lab(self) -> None:
        assert _classify_source_type("B Lab", "report") == "secondary"

    def test_ditchcarbon(self) -> None:
        assert _classify_source_type("DitchCarbon", "dataset") == "secondary"

    def test_crunchbase(self) -> None:
        assert _classify_source_type("Crunchbase", "article") == "secondary"

    def test_unesco(self) -> None:
        assert _classify_source_type("UNESCO", "report") == "secondary"

    def test_unknown_publisher_report_defaults_secondary(self) -> None:
        assert _classify_source_type("Unknown News Outlet", "report") == "secondary"

    def test_unknown_publisher_dataset_defaults_secondary(self) -> None:
        assert _classify_source_type("Unknown Data Provider", "dataset") == "secondary"

    def test_unknown_publisher_article_defaults_secondary(self) -> None:
        assert _classify_source_type("Random Media", "article") == "secondary"

    def test_sec_false_positive_avoided(self) -> None:
        # "section" and "secretary" must NOT match as primary (sec.gov check)
        assert _classify_source_type("The Secretary of State", "report") == "secondary"

    def test_sec_false_positive_section(self) -> None:
        assert _classify_source_type("Section 9 Media", "article") == "secondary"


class TestTertiary:
    def test_blog_kind(self) -> None:
        assert _classify_source_type("Unknown Blogger", "blog") == "tertiary"

    def test_future_of_life(self) -> None:
        assert _classify_source_type("Future of Life Institute", "article") == "tertiary"

    def test_earth_day(self) -> None:
        assert _classify_source_type("Earth Day Network", "report") == "tertiary"

    def test_center_for_ai_safety(self) -> None:
        assert _classify_source_type("Center for AI Safety", "article") == "tertiary"

    def test_nerdwallet(self) -> None:
        assert _classify_source_type("NerdWallet", "article") == "tertiary"

    def test_zenbusiness(self) -> None:
        assert _classify_source_type("ZenBusiness", "article") == "tertiary"

    def test_substack(self) -> None:
        assert _classify_source_type("My Substack", "article") == "tertiary"
