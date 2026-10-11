"""Unit tests for classify_source_type in common.source_classification."""

from __future__ import annotations

import pytest

from common.source_classification import classify_source_type as _classify_source_type


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


# --- Corporate lab named in an arXiv author block ---------------------------

from common.source_classification import (  # noqa: E402
    EntityIdentity,
    corporate_lab_publisher,
    profile_url_names_entity,
)


class TestCorporateLabPublisher:
    def test_google_deepmind_affiliation(self) -> None:
        assert corporate_lab_publisher("Jane Doe Google DeepMind, London") == "Google"

    def test_lab_email_domain(self) -> None:
        assert corporate_lab_publisher("Alice Smith alice@anthropic.com") == "Anthropic"

    def test_university_only(self) -> None:
        assert corporate_lab_publisher("Affiliation: University of Rhode Island") is None

    def test_meta_substring_is_not_meta(self) -> None:
        assert corporate_lab_publisher("Metacritic") is None
        assert corporate_lab_publisher("a meta-analysis of fair results") is None

    def test_fair_is_case_sensitive(self) -> None:
        assert corporate_lab_publisher("FAIR, Paris") == "Meta"

    def test_first_lab_in_author_order_wins(self) -> None:
        text = "Bob (OpenAI) Carol (Microsoft Research) Dan (Google)"
        assert corporate_lab_publisher(text) == "OpenAI"
        assert corporate_lab_publisher("Carol microsoft.com x@microsoft.com Bob OpenAI") == "Microsoft"

    def test_academic_first_affiliation_is_not_a_lab_paper(self) -> None:
        universities = " ".join(
            f"Author{i} Department of Computer Science, Stanford University" for i in range(8)
        )
        assert corporate_lab_publisher(f"{universities} Zed Google Research") is None
        assert corporate_lab_publisher("Ann ann@cs.cmu.edu Bob bob@google.com") is None
        assert corporate_lab_publisher("Ann (ETH Zurich) Bob (Anthropic)") is None

    def test_lab_first_affiliation_with_academic_coauthors(self) -> None:
        text = "Jane Doe Google DeepMind Bob Smith University of Oxford"
        assert corporate_lab_publisher(text) == "Google"


# --- The entity's own account on a profile platform --------------------------

EARTHLY = EntityIdentity.from_parts(["Earthly Insight"], ["https://earthlyinsight.com"])


class TestProfileUrlNamesEntity:
    def test_linkedin_post_handle_before_underscore(self) -> None:
        url = "https://www.linkedin.com/posts/earthly-insight_responsibility-activity-1"
        assert profile_url_names_entity(url, EARTHLY)

    def test_linkedin_company_page(self) -> None:
        assert profile_url_names_entity("https://linkedin.com/company/earthlyinsight/", EARTHLY)

    def test_at_handle_forms(self) -> None:
        assert profile_url_names_entity("https://www.youtube.com/@earthly_insight", EARTHLY)
        assert profile_url_names_entity("https://x.com/@EarthlyInsight/status/1", EARTHLY)

    def test_lookalike_handle_does_not_match(self) -> None:
        assert not profile_url_names_entity(
            "https://www.linkedin.com/posts/earth-insight_other-activity-2", EARTHLY
        )
        assert not profile_url_names_entity("https://x.com/earthlyinsightfan", EARTHLY)

    def test_no_match_off_profile_hosts(self) -> None:
        assert not profile_url_names_entity("https://apps.apple.com/earthly-insight", EARTHLY)
        assert not profile_url_names_entity("https://example.com/earthly-insight", EARTHLY)
