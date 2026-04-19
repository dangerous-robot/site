"""Tests for ingestor tools: web_fetch and wayback."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from ingestor.tools.wayback import check_wayback, save_to_wayback
from ingestor.tools.web_fetch import extract_page_data

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestExtractPageData:
    def test_title_from_og_tag(self):
        html = (
            '<html><head>'
            '<meta property="og:title" content="OG Title">'
            '<title>Fallback Title - SiteName</title>'
            '</head><body><p>Hello</p></body></html>'
        )
        data = extract_page_data(html, "https://example.com")
        assert data["title"] == "OG Title"

    def test_title_from_title_tag(self):
        html = "<html><head><title>Page Title</title></head><body><p>Hello</p></body></html>"
        data = extract_page_data(html, "https://example.com")
        assert data["title"] == "Page Title"

    def test_strips_nav_footer_script(self):
        html = (
            "<html><body>"
            "<nav>Navigation</nav>"
            "<p>Main content</p>"
            "<footer>Footer</footer>"
            "<script>var x = 1;</script>"
            "</body></html>"
        )
        data = extract_page_data(html, "https://example.com")
        assert "Navigation" not in data["text"]
        assert "Footer" not in data["text"]
        assert "var x" not in data["text"]
        assert "Main content" in data["text"]

    def test_truncates_long_text(self):
        long_body = "<p>" + "x" * 60_000 + "</p>"
        html = f"<html><body>{long_body}</body></html>"
        data = extract_page_data(html, "https://example.com")
        assert len(data["text"]) <= 50_100  # 50k + truncation marker
        assert data["text"].endswith("[truncated]")

    def test_extracts_meta_description(self):
        html = (
            '<html><head>'
            '<meta name="description" content="A page description.">'
            '</head><body><p>Content</p></body></html>'
        )
        data = extract_page_data(html, "https://example.com")
        assert data["description"] == "A page description."

    def test_extracts_published_time(self):
        html = (
            '<html><head>'
            '<meta property="article:published_time" content="2025-03-15">'
            '</head><body><p>Content</p></body></html>'
        )
        data = extract_page_data(html, "https://example.com")
        assert data["published_time"] == "2025-03-15"

    def test_url_passthrough(self):
        html = "<html><body><p>Content</p></body></html>"
        data = extract_page_data(html, "https://example.com/page")
        assert data["url"] == "https://example.com/page"

    def test_sample_fixture(self):
        html = (FIXTURES_DIR / "sample_page.html").read_text()
        data = extract_page_data(html, "https://example.com/ai-water-usage-2025")
        assert data["title"] == "AI Water Usage Report 2025"
        assert data["author"] == "Jane Smith"
        assert data["published_time"] == "2025-03-15"
        assert "1.7 billion gallons" in data["text"]
        # Nav/footer/script should be stripped
        assert "analytics" not in data["text"]
        assert "Copyright" not in data["text"]


class TestCheckWayback:
    @pytest.mark.asyncio
    async def test_available(self):
        with respx.mock:
            respx.get("https://archive.org/wayback/available").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "archived_snapshots": {
                            "closest": {
                                "available": True,
                                "url": "https://web.archive.org/web/2025/https://example.com",
                                "timestamp": "20250315",
                            }
                        }
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await check_wayback(client, "https://example.com")
            assert result["available"] is True
            assert result["archived_url"] == "https://web.archive.org/web/2025/https://example.com"

    @pytest.mark.asyncio
    async def test_not_available(self):
        with respx.mock:
            respx.get("https://archive.org/wayback/available").mock(
                return_value=httpx.Response(
                    200,
                    json={"archived_snapshots": {}},
                )
            )
            async with httpx.AsyncClient() as client:
                result = await check_wayback(client, "https://example.com")
            assert result["available"] is False
            assert result["archived_url"] is None

    @pytest.mark.asyncio
    async def test_api_error(self):
        with respx.mock:
            respx.get("https://archive.org/wayback/available").mock(
                return_value=httpx.Response(500)
            )
            async with httpx.AsyncClient() as client:
                result = await check_wayback(client, "https://example.com")
            assert result["available"] is False


class TestSaveToWayback:
    @pytest.mark.asyncio
    async def test_save_success_with_location(self):
        with respx.mock:
            respx.post("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(
                    200,
                    headers={
                        "content-location": "/web/20250315/https://example.com"
                    },
                )
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result == "https://web.archive.org/web/20250315/https://example.com"

    @pytest.mark.asyncio
    async def test_save_rate_limited(self):
        with respx.mock:
            respx.post("https://web.archive.org/save/https://example.com").mock(
                return_value=httpx.Response(429)
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_save_network_error(self):
        with respx.mock:
            respx.post("https://web.archive.org/save/https://example.com").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            async with httpx.AsyncClient() as client:
                result = await save_to_wayback(client, "https://example.com")
            assert result is None
