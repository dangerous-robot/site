"""Source bodies are written without bare emails or URLs (markdownlint MD034).

The pre-commit hook lints ``research/**/*.md``; one ingested body with a bare
address blocks every commit in the checkout.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from common.frontmatter import parse_frontmatter
from ingestor.models import SourceFile
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
