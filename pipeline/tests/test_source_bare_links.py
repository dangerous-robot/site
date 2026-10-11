"""Source bodies are written without bare emails or URLs (markdownlint MD034).

The pre-commit hook lints ``research/**/*.md``; one ingested body with a bare
address blocks every commit in the checkout.
"""

from __future__ import annotations

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
from orchestrator.persistence import _write_source_files

URL = "https://greentest.example/contact"


def _sf(body: str) -> SourceFile:
    return SourceFile.model_validate(
        {
            "frontmatter": {
                "url": URL,
                "title": "Contact",
                "publisher": "GreenTest",
                "accessed_date": datetime.date(2026, 10, 10).isoformat(),
                "kind": "index",
                "summary": "Contact page.",
            },
            "body": body,
            "slug": "contact",
            "year": 2026,
        }
    )


def _written(tmp_path: Path, body: str) -> tuple[dict, str]:
    _write_source_files([(URL, _sf(body))], tmp_path)
    path = tmp_path / "research" / "sources" / "2026" / "contact.md"
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def test_bare_email_and_url_are_wrapped(tmp_path: Path) -> None:
    fm, body = _written(
        tmp_path,
        "Reach us by email (mail@example.org) or at https://example.org/help.",
    )
    assert "(<mail@example.org>)" in body
    assert "<https://example.org/help>." in body
    assert fm["url"] == URL


def test_wrapped_linked_and_code_addresses_are_unchanged(tmp_path: Path) -> None:
    original = (
        "Wrapped <mail@example.org> and <https://example.org/a>.\n\n"
        "Linked [mail@example.org](mailto:mail@example.org) and "
        "[the site](https://example.org/b) and ![logo](https://example.org/l.png).\n\n"
        "Code `mail@example.org` and `https://example.org/c`.\n\n"
        '<a href="https://example.org/d">d</a>\n\n'
        "```\nhttps://example.org/e mail@example.org\n```"
    )
    _, body = _written(tmp_path, original)
    assert body.rstrip("\n") == original


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


def test_step_ingest_write_wraps_bare_email(tmp_path: Path) -> None:
    source = _sf("Write to mail@example.org for help.").model_dump(mode="json")
    html = "<html><head><title>Contact</title></head><body><p>mail@example.org</p></body></html>"
    with respx.mock:
        respx.get(URL).mock(return_value=httpx.Response(200, html=html))
        with ingestor_agent.override(model=_fetch_then_return(URL, source)):
            with patch(
                "ingestor.agent.ingestor_agent.override",
                side_effect=lambda **kw: _noop_ctx(),
            ):
                result = CliRunner().invoke(
                    main,
                    [
                        "--model", "test", "--ingestor-model", "test",
                        "step-ingest", URL, "--write", "--skip-wayback",
                        "--repo-root", str(tmp_path),
                    ],
                )
    assert result.exit_code == 0, result.output
    written = list((tmp_path / "research" / "sources" / "2026").glob("*.md"))
    assert len(written) == 1
    _, body = parse_frontmatter(written[0].read_text(encoding="utf-8"))
    assert "Write to <mail@example.org> for help." in body


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see https://example.org/a_(b) now", "see <https://example.org/a_(b)> now"),
        ("(https://example.org/x)", "(<https://example.org/x>)"),
        ("go to https://example.org/x, then", "go to <https://example.org/x>, then"),
        ("https://example.org/u@v.org", "<https://example.org/u@v.org>"),
        ("a.b+c@sub.example.org.", "<a.b+c@sub.example.org>."),
        ("no address here", "no address here"),
    ],
)
def test_wrap_bare_links_extents(text: str, expected: str) -> None:
    from common.markdown_links import wrap_bare_links

    assert wrap_bare_links(text) == expected
    assert wrap_bare_links(expected) == expected
