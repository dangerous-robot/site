"""Acceptance tests for `dr draft --source <url>` (RE-AX, Fold side tools).

Written before the implementation (plan ``docs/plans/pipeline-rebuild.md``
§ SP7 (Fold side tools), "Tests that prove it"; Q-B7 (standalone source
ingest) default; design ``handoff/2026-10-15-re-ax-design.md``). One-URL
ingest for editorial pages moves from ``dr step-ingest`` (and the hidden
``dr ingest``) to ``dr draft --source``. The cases are mined from
``test_ingest_fetch_failure.py`` (step-ingest writes nothing on failure,
keeps the requested URL, drops a paraphrased quote),
``test_source_id_collision.py`` (``--force`` overwrites only the same URL),
``test_source_bare_links.py`` (bare links wrapped) and ``test_cli.py``
``TestStepIngestArchive`` and ``TestIngestCli`` (captures only when writing).

Shapes pinned here (the design's § 2):

- ``--source URL`` is a mode of ``dr draft``: no SENTENCE, no other mode
  flag, no ``--rerun``; it runs no loop and writes no claim, sidecar or finding;
- it writes one file at ``research/sources/<year>/<slug>.md`` and prints
  ``Wrote <path>``; ``--dry-run`` prints the Markdown and writes nothing;
- ``--force`` overwrites an existing file only when it holds the same URL;
- archive.org is asked to capture only when the command writes
  (``--dry-run`` checks TimeGate only); ``--skip-wayback`` makes no archive request.
"""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import patch

import httpx
import pytest
import respx
from click.testing import CliRunner
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from common.frontmatter import parse_frontmatter, serialize_frontmatter
from ingestor.agent import ingestor_agent

URL = "https://brave.com/transparency/"
_DNS_ERROR = "[Errno 8] nodename nor servname provided, or not known"
_HTML = (
    "<html><head><title>Transparency</title></head>"
    "<body><p>Brave publishes a transparency report. Write to mail@example.org for help.</p></body></html>"
)
_VERBATIM = "Brave publishes a transparency report."
_PARAPHRASE = "Brave releases a yearly transparency document."

_PAGE_URL = "https://example.org/page"
_PAGE = "<html><head><title>Page</title></head><body><p>The stored page.</p></body></html>"


def _source_args(url: str, *, body: str = "Brave publishes a transparency report.", **overrides) -> dict:
    frontmatter = {
        "url": url,
        "title": "Brave transparency report",
        "publisher": "Brave Software",
        "accessed_date": "2026-10-04",
        "kind": "report",
        "summary": "Brave publishes a transparency report.",
    }
    frontmatter.update(overrides)
    return {"frontmatter": frontmatter, "body": body, "slug": "transparency", "year": 2025}


def _scripted_model(fetch_urls: list[str], source: dict) -> FunctionModel:
    """Call ``web_fetch`` once per URL in order, then return ``source``."""
    step = 0

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        nonlocal step
        if step < len(fetch_urls):
            url = fetch_urls[step]
            step += 1
            return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})])
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])

    return FunctionModel(_fn)


def _dr(root, *args: str):
    from orchestrator.cli import main

    return CliRunner().invoke(main, ["--model", "test", "--ingestor-model", "test", *args, "--repo-root", str(root)])


def _source_run(root, url: str, mock_kwargs: dict, source: dict, *flags: str, fetch: list[str] | None = None):
    (root / "research" / "sources").mkdir(parents=True, exist_ok=True)
    with respx.mock:
        respx.get(url).mock(**mock_kwargs)
        with ingestor_agent.override(model=_scripted_model(fetch or [url], source)):
            with patch("ingestor.agent.ingestor_agent.override", side_effect=lambda **kw: nullcontext()):
                return _dr(root, "draft", "--source", url, "--skip-wayback", *flags)


def _snapshot(root) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _sources(root) -> list:
    return sorted((root / "research" / "sources").rglob("*.md"))


# --------------------------------------------------------------------------- #
# One source file and nothing else                                             #
# --------------------------------------------------------------------------- #


def test_source_writes_one_source_file_and_nothing_else(tmp_path, monkeypatch) -> None:
    import loop

    def _no_loop(*args, **kwargs):
        raise AssertionError("dr draft --source runs no loop")

    monkeypatch.setattr(loop, "run", _no_loop)
    monkeypatch.setattr(loop, "rerun", _no_loop)
    (tmp_path / "research" / "sources").mkdir(parents=True)
    before = _snapshot(tmp_path)

    result = _source_run(tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)}, _source_args(URL))

    assert result.exit_code == 0, result.output
    added = sorted(set(_snapshot(tmp_path)) - set(before))
    assert added == ["research/sources/2025/transparency.md"]
    assert "Wrote " in result.output
    assert not (tmp_path / "research" / "claims").exists()
    assert not (tmp_path / "research" / "findings").exists()


def test_source_fetch_failure_writes_nothing(tmp_path) -> None:
    """Mined from test_ingest_fetch_failure.py test_step_ingest_fetch_failure_writes_nothing."""
    url = "https://builder.aws.amazon.com/renewable"
    result = _source_run(tmp_path, url, {"side_effect": httpx.ConnectError(_DNS_ERROR)}, _source_args(url))

    assert result.exit_code == 1, result.output
    error_lines = [ln for ln in result.output.splitlines() if ln.startswith("Error:")]
    assert len(error_lines) == 1
    assert "fetch failed" in error_lines[0]
    assert "nodename" in error_lines[0]
    assert _sources(tmp_path) == []


def test_source_keeps_the_requested_url_when_the_model_echoes_a_redirect(tmp_path) -> None:
    """Mined from test_ingest_fetch_failure.py test_step_ingest_keeps_requested_url_when_model_echoes_redirect."""
    result = _source_run(
        tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)},
        _source_args("https://brave.com/transparency-report/"),
    )

    assert result.exit_code == 0, result.output
    [written] = _sources(tmp_path)
    assert f"url: {URL}" in written.read_text()


def test_source_drops_a_paraphrased_quote(tmp_path) -> None:
    """Mined from test_ingest_fetch_failure.py test_step_ingest_drops_paraphrased_quote (RE-AH)."""
    result = _source_run(
        tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)},
        _source_args(URL, key_quotes=[_VERBATIM, _PARAPHRASE]),
    )

    assert result.exit_code == 0, result.output
    [written] = _sources(tmp_path)
    text = written.read_text()
    assert _VERBATIM in text
    assert _PARAPHRASE not in text


def test_source_wraps_a_bare_email(tmp_path) -> None:
    """Mined from test_source_bare_links.py test_step_ingest_write_wraps_bare_email."""
    result = _source_run(
        tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)},
        _source_args(URL, body="Write to mail@example.org for help."),
    )

    assert result.exit_code == 0, result.output
    [written] = _sources(tmp_path)
    _, body = parse_frontmatter(written.read_text(encoding="utf-8"))
    assert "Write to <mail@example.org> for help." in body


def test_source_dry_run_prints_the_markdown_and_writes_nothing(tmp_path) -> None:
    (tmp_path / "research" / "sources").mkdir(parents=True)
    before = _snapshot(tmp_path)

    result = _source_run(tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)}, _source_args(URL),
                         "--dry-run")

    assert result.exit_code == 0, result.output
    assert f"url: {URL}" in result.output
    assert _snapshot(tmp_path) == before


# --------------------------------------------------------------------------- #
# --force overwrites only the same URL                                         #
# --------------------------------------------------------------------------- #


def _existing(root, sid: str, url: str):
    path = root / "research" / "sources" / f"{sid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_frontmatter(
        {"url": url, "title": "Existing", "publisher": "Someone", "accessed_date": "2026-01-01",
         "kind": "article", "summary": "An existing source."}, "Existing.\n"), encoding="utf-8")
    return path


def test_source_without_force_refuses_an_existing_file_for_the_same_url(tmp_path) -> None:
    existing = _existing(tmp_path, "2025/transparency", URL)
    before = existing.read_bytes()

    result = _source_run(tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)}, _source_args(URL))

    assert result.exit_code == 1, result.output
    assert existing.read_bytes() == before
    assert "--force" in result.output


def test_source_force_overwrites_the_same_url(tmp_path) -> None:
    """Mined from test_source_id_collision.py test_step_ingest_force_overwrites_same_url."""
    existing = _existing(tmp_path, "2025/transparency", URL)

    result = _source_run(tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)}, _source_args(URL),
                         "--force")

    assert result.exit_code == 0, result.output
    assert _sources(tmp_path) == [existing]
    assert parse_frontmatter(existing.read_text())[0]["title"] == "Brave transparency report"


def test_source_force_does_not_overwrite_another_url(tmp_path) -> None:
    """Mined from test_source_id_collision.py test_step_ingest_force_does_not_overwrite_other_url."""
    other = _existing(tmp_path, "2025/transparency", "https://example.com/another-transparency")
    before = other.read_bytes()

    result = _source_run(tmp_path, URL, {"return_value": httpx.Response(200, html=_HTML)}, _source_args(URL),
                         "--force")

    assert result.exit_code == 0, result.output
    assert other.read_bytes() == before
    new = [p for p in _sources(tmp_path) if p != other]
    assert len(new) == 1
    assert parse_frontmatter(new[0].read_text())[0]["url"] == URL


# --------------------------------------------------------------------------- #
# Captures only when writing (RE-AI, Archive snapshot correctness)              #
# --------------------------------------------------------------------------- #


def _ts(days_ago: float) -> str:
    import datetime

    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return when.strftime("%Y%m%d%H%M%S")


_SNAPSHOT = f"https://web.archive.org/web/{_ts(1)}/{_PAGE_URL}"


def _timegate_re():
    import re

    return re.compile(r"https://web\.archive\.org/web/\d{14}/.+")


def _save_re():
    import re

    return re.compile(r"https://web\.archive\.org/save/.+")


def _page_source(root, *flags: str):
    (root / "research" / "sources").mkdir(parents=True, exist_ok=True)
    return _dr(root, "draft", "--source", _PAGE_URL, *flags)


def test_source_dry_run_prints_the_snapshot_and_never_saves(tmp_path, stub_ingest_model, mock_capture_replay) -> None:
    """Mined from test_cli.py TestStepIngestArchive.test_read_only_prints_the_snapshot_and_never_saves."""
    with respx.mock as mock:
        mock_capture_replay()
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        mock.get(_timegate_re()).mock(return_value=httpx.Response(302, headers={"location": _SNAPSHOT}))
        save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
        result = _page_source(tmp_path, "--dry-run", "--wayback")

    assert result.exit_code == 0, result.output
    assert f"archived_url: {_SNAPSHOT}" in result.output
    assert save.called is False


def test_source_dry_run_model_wayback_check_makes_no_capture(tmp_path, stub_ingest_model_calling_wayback) -> None:
    """Mined from test_cli.py TestStepIngestArchive.test_read_only_model_wayback_check_makes_no_capture
    and test_deprecated_ingest_dry_run_makes_no_capture."""
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        timegate = mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
        save = mock.get(_save_re()).mock(return_value=httpx.Response(302, headers={"location": _SNAPSHOT}))
        result = _page_source(tmp_path, "--dry-run", "--wayback")

    assert result.exit_code == 0, result.output
    assert timegate.call_count == 2
    assert save.called is False


def test_source_dry_run_miss_reports_it_without_a_capture(tmp_path, stub_ingest_model) -> None:
    """Mined from test_cli.py TestStepIngestArchive.test_read_only_miss_reports_it_without_a_capture."""
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
        save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
        result = _page_source(tmp_path, "--dry-run", "--wayback")

    assert result.exit_code == 0, result.output
    assert "archived_url" not in result.output
    assert "Archive lookup failed" in result.output
    assert save.called is False


def test_source_write_records_a_rate_limit_as_one_error_line(tmp_path, stub_ingest_model) -> None:
    """Mined from test_cli.py TestStepIngestArchive.test_write_records_a_rate_limit_as_an_error_line."""
    async def _no_wait(seconds: float) -> None:
        return None

    with patch("ingestor.tools.wayback._wait", _no_wait), respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        mock.get(_timegate_re()).mock(return_value=httpx.Response(429))
        result = _page_source(tmp_path, "--wayback")

    assert result.exit_code == 0, result.output
    error_lines = [ln for ln in result.output.splitlines() if "Archive lookup failed" in ln]
    assert len(error_lines) == 1 and "429" in error_lines[0]
    written = (tmp_path / "research" / "sources" / "2026" / "page.md").read_text()
    assert "archived_url" not in written


def test_source_write_saves_on_a_miss(tmp_path, stub_ingest_model, mock_capture_replay) -> None:
    """Mined from test_cli.py TestStepIngestArchive.test_write_saves_on_a_miss."""
    with respx.mock as mock:
        mock_capture_replay()
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
        mock.get(_save_re()).mock(return_value=httpx.Response(200, headers={"content-location": _SNAPSHOT}))
        result = _page_source(tmp_path, "--wayback")

    assert result.exit_code == 0, result.output
    written = (tmp_path / "research" / "sources" / "2026" / "page.md").read_text()
    assert f"archived_url: {_SNAPSHOT}" in written


def test_source_skip_wayback_makes_no_archive_request(tmp_path, stub_ingest_model) -> None:
    """Mined from test_cli.py TestStepIngestArchive.test_skip_wayback_makes_no_archive_request."""
    with respx.mock as mock:
        mock.get(_PAGE_URL).mock(return_value=httpx.Response(200, html=_PAGE))
        timegate = mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
        result = _page_source(tmp_path, "--skip-wayback")

    assert result.exit_code == 0, result.output
    assert timegate.called is False


# --------------------------------------------------------------------------- #
# Grammar                                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "args",
    [
        ["draft", "--source", "not-a-url"],
        ["draft", "--source", URL, "A sentence."],
        ["draft", "--source", URL, "--entity", "subjects/probe-subject"],
        ["draft", "--source", URL, "--claim", "subjects/probe-subject/x"],
        ["draft", "--source", URL, "--criterion", "some-slug"],
    ],
    ids=["not-a-url", "sentence", "entity", "claim", "criterion"],
)
def test_source_grammar_is_a_usage_error_before_any_model_call(tmp_path, args) -> None:
    """Mined from test_cli.py TestIngestCli.test_invalid_url."""
    from pydantic_ai.models.function import FunctionModel

    calls: list = []

    async def _fn(messages, info):
        calls.append(messages)
        raise AssertionError("no model call on a usage error")

    (tmp_path / "research" / "sources").mkdir(parents=True)
    with ingestor_agent.override(model=FunctionModel(_fn)):
        result = _dr(tmp_path, *args)

    assert result.exit_code == 2, result.output
    assert calls == []
    assert _sources(tmp_path) == []
