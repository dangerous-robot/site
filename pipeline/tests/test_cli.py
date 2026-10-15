"""Tests for the dr CLI: provider key checks, per-agent model options, removed commands and dr recheck --sources."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

import click

from orchestrator.cli import (
    _check_provider_api_keys,
    _required_env_for_model,
    main,
)


class TestRequiredEnvForModel:
    def test_test_model_skipped(self) -> None:
        assert _required_env_for_model("test") == ()

    def test_anthropic_prefix(self) -> None:
        assert _required_env_for_model("anthropic:claude-haiku-4-5-20251001") == ("ANTHROPIC_API_KEY",)

    def test_openai_prefix(self) -> None:
        assert _required_env_for_model("openai:gpt-4o-mini") == ("OPENAI_API_KEY",)

    def test_infomaniak_requires_both_keys(self) -> None:
        assert _required_env_for_model("infomaniak:swiss-ai/Apertus-70B-Instruct-2509") == (
            "INFOMANIAK_API_KEY",
            "INFOMANIAK_PRODUCT_ID",
        )

    def test_greenpt_requires_api_key(self) -> None:
        assert _required_env_for_model("greenpt:gpt-oss-120b") == ("GREENPT_API_KEY",)

    def test_chained_spec_returns_union(self) -> None:
        """``a||b`` returns the stable-ordered union of both legs' required env vars."""
        result = _required_env_for_model(
            "anthropic:claude-haiku-4-5-20251001||greenpt:gpt-oss-120b"
        )
        assert result == ("ANTHROPIC_API_KEY", "GREENPT_API_KEY")

    def test_chained_spec_dedupes_repeated_vars(self) -> None:
        """Two Infomaniak legs union to a single pair of Infomaniak vars."""
        result = _required_env_for_model(
            "infomaniak:openai/gpt-oss-120b||infomaniak:mistral24b"
        )
        assert result == ("INFOMANIAK_API_KEY", "INFOMANIAK_PRODUCT_ID")

    def test_chained_spec_does_not_short_circuit_on_test_leg(self) -> None:
        result = _required_env_for_model("anthropic:claude-haiku-4-5-20251001||test")
        assert result == ("ANTHROPIC_API_KEY",)

    def test_single_test_spec_still_short_circuits(self) -> None:
        """The ``"test" in model`` branch still applies to non-chained specs."""
        assert _required_env_for_model("test") == ()

    def test_bare_string_rejected_with_usage_error(self) -> None:
        with pytest.raises(click.UsageError) as exc:
            _required_env_for_model("gpt-oss-120b")
        assert "no recognized provider prefix" in str(exc.value)
        assert "infomaniak" in str(exc.value)

    def test_unknown_prefix_rejected(self) -> None:
        with pytest.raises(click.UsageError):
            _required_env_for_model("acme:something")


class TestCheckProviderApiKeys:
    def test_single_anthropic_passes_with_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        _check_provider_api_keys("anthropic:claude")

    def test_mixed_providers_require_union_of_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A run with anthropic baseline + infomaniak override must require BOTH providers' keys."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.delenv("INFOMANIAK_API_KEY", raising=False)
        monkeypatch.delenv("INFOMANIAK_PRODUCT_ID", raising=False)
        with pytest.raises(SystemExit) as exc:
            _check_provider_api_keys(["anthropic:claude", "infomaniak:swiss-ai/Apertus-70B-Instruct-2509"])
        assert exc.value.code == 2

    def test_mixed_providers_pass_when_all_keys_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
        monkeypatch.setenv("INFOMANIAK_API_KEY", "y")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "z")
        _check_provider_api_keys(["anthropic:claude", "infomaniak:swiss-ai/Apertus-70B-Instruct-2509"])

    def test_test_model_skips_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        _check_provider_api_keys("test")


class TestDraftBraveKeyCheck:
    """``dr draft`` refuses a Brave backend with no Brave key before any model call."""

    class _Reached(Exception):
        pass

    def _invoke(self, monkeypatch, tmp_path, backend: str):
        path = tmp_path / "research" / "entities" / "products" / "acme.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\nname: Acme\ntype: product\ndescription: A test entity.\n---\n",
            encoding="utf-8",
        )
        reached = self._Reached

        async def _fake_run(*_args, **_kwargs):
            raise reached("loop.run was called")

        monkeypatch.setattr("loop.run", _fake_run)
        monkeypatch.setenv("RESEARCH_SEARCH_BACKEND", backend)
        monkeypatch.delenv("BRAVE_WEB_SEARCH_API_KEY", raising=False)
        return CliRunner().invoke(main, [
            "--model", "test", "draft", "--entity", "products/acme", "x",
            "--repo-root", str(tmp_path),
        ])

    def test_brave_backend_without_key_is_a_usage_error(self, monkeypatch, tmp_path) -> None:
        result = self._invoke(monkeypatch, tmp_path, "brave")
        assert result.exit_code == 2, result.output
        assert "BRAVE_WEB_SEARCH_API_KEY" in result.output
        assert not isinstance(result.exception, self._Reached)

    def test_tavily_backend_without_brave_key_reaches_the_loop(self, monkeypatch, tmp_path) -> None:
        result = self._invoke(monkeypatch, tmp_path, "tavily")
        assert isinstance(result.exception, self._Reached), result.output


class TestPerAgentModelOptions:
    def test_top_level_help_lists_per_agent_options(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for opt in ("--researcher-model", "--analyst-model", "--auditor-model", "--ingestor-model"):
            assert opt in result.output


class TestRemovedCommands:
    """Explicit coverage asserting that hard-removed commands no longer exist in the CLI."""

    def test_verify_removed(self) -> None:
        """dr verify should no longer be registered."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["verify", "--help"])
        assert result.exit_code != 0

    def test_verify_claim_removed(self) -> None:
        """dr verify-claim should no longer be registered."""
        from click.testing import CliRunner
        from orchestrator.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["verify-claim", "--help"])
        assert result.exit_code != 0



# --------------------------------------------------------------------------- #
# Archive links in code: dr recheck --sources                                  #
# --------------------------------------------------------------------------- #

_ARCHIVE_PAGE_URL = "https://example.org/page"
_ARCHIVE_PAGE = "<html><head><title>Page</title></head><body><p>The stored page.</p></body></html>"


def _archive_ts(days_ago: float) -> str:
    import datetime

    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return when.strftime("%Y%m%d%H%M%S")


# A recent capture, so the freshness refresh after a live fetch leaves it alone.
_ARCHIVE_SNAPSHOT = f"https://web.archive.org/web/{_archive_ts(1)}/https://example.org/page"
_DONE_SNAPSHOT = f"https://web.archive.org/web/{_archive_ts(1)}/https://example.org/done"


def _timegate_re():
    import re

    return re.compile(r"https://web\.archive\.org/web/\d{14}/.+")


def _save_re():
    import re

    return re.compile(r"https://web\.archive\.org/save/.+")


def _live_page(mock, url: str = _ARCHIVE_PAGE_URL):
    """Mock the live fetch `dr recheck --sources` makes before each lookup."""
    import httpx

    return mock.get(url).mock(return_value=httpx.Response(200, text=_ARCHIVE_PAGE))


@pytest.fixture
def no_archive_wait(monkeypatch):
    async def _no_wait(seconds: float) -> None:
        return None

    monkeypatch.setattr("ingestor.tools.wayback._wait", _no_wait)


class TestRecheckSourcesBackfill:
    _SOURCE = (
        "---\n"
        "url: https://example.org/page\n"
        "title: Page\n"
        "publisher: Example\n"
        "accessed_date: '2026-05-04'\n"
        "kind: article\n"
        "summary: A long summary that a YAML round trip could re-wrap differently from how\n"
        "  it is stored now.\n"
        "---\n"
        "Body.\n"
    )

    def _repo(self, tmp_path):
        sources = tmp_path / "research" / "sources" / "2026"
        sources.mkdir(parents=True)
        (sources / "page.md").write_text(self._SOURCE, encoding="utf-8")
        (sources / "done.md").write_text(
            self._SOURCE.replace(
                "url: https://example.org/page\n",
                f"url: https://example.org/done\narchived_url: {_DONE_SNAPSHOT}\n",
            ),
            encoding="utf-8",
        )
        return sources

    def _invoke(self, tmp_path, *ids: str):
        return CliRunner().invoke(
            main, ["recheck", "--sources", *ids, "--repo-root", str(tmp_path)]
        )

    def test_adds_only_the_archived_url_line(self, tmp_path, mock_capture_replay) -> None:
        import httpx
        import respx

        sources = self._repo(tmp_path)
        with respx.mock as mock:
            mock_capture_replay()
            _live_page(mock)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": _ARCHIVE_SNAPSHOT})
            )
            _live_page(mock, "https://example.org/done")
            done_before = (sources / "done.md").read_bytes()
            result = self._invoke(tmp_path, "2026/page", "2026/done")

        assert result.exit_code == 0, result.output
        expected = self._SOURCE.replace(
            "url: https://example.org/page\n",
            f"url: https://example.org/page\narchived_url: {_ARCHIVE_SNAPSHOT}\n",
        )
        assert (sources / "page.md").read_text() == expected
        # A source that already has a good link is rechecked and left byte for byte.
        assert any(line.startswith("2026/done:") for line in result.output.splitlines()), result.output
        assert (sources / "done.md").read_bytes() == done_before

    def test_failure_prints_the_reason_and_exits_nonzero(self, tmp_path, no_archive_wait) -> None:
        import httpx
        import respx

        sources = self._repo(tmp_path)
        with respx.mock as mock:
            _live_page(mock)
            mock.get(_timegate_re()).mock(return_value=httpx.Response(429))
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path, "2026/page")

        assert result.exit_code == 1
        assert "2026/page: archive lookup failed" in result.output
        assert "429" in result.output
        assert (sources / "page.md").read_text() == self._SOURCE
        assert save.called is False

    def test_unknown_source_id_fails(self, tmp_path) -> None:
        self._repo(tmp_path)
        result = self._invoke(tmp_path, "2026/missing")
        assert result.exit_code == 1
        assert "2026/missing: not found" in result.output

    def test_backfill_passes_no_freshness(self, tmp_path, mock_capture_replay) -> None:
        """Only the ingest refreshes, so an old good capture is recorded without a save."""
        import httpx
        import respx

        old = f"https://web.archive.org/web/{_archive_ts(300)}/https://example.org/page"
        sources = self._repo(tmp_path)
        with respx.mock as mock:
            mock_capture_replay()
            _live_page(mock)
            mock.get(_timegate_re()).mock(return_value=httpx.Response(302, headers={"location": old}))
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path, "2026/page")

        assert result.exit_code == 0, result.output
        assert f"archived_url: {old}\n" in (sources / "page.md").read_text()
        assert save.called is False


class TestRecheckSources:
    _URL = "https://example.org/page"
    _BAD = f"https://web.archive.org/web/{_archive_ts(2)}/https://example.org/page"

    def _source(self, archived_url: str | None) -> str:
        link = f"archived_url: {archived_url}\n" if archived_url else ""
        return (
            "---\n"
            f"url: {self._URL}\n"
            f"{link}"
            "title: Page\n"
            "publisher: Example\n"
            "published_date: '2025-12-09'\n"
            "accessed_date: '2026-05-04'\n"
            "kind: article\n"
            "summary: A long summary that a YAML round trip could re-wrap differently from how\n"
            "  it is stored now.\n"
            "---\n"
            "Body.\n"
        )

    def _write(self, tmp_path, archived_url: str | None):
        path = tmp_path / "research" / "sources" / "2026" / "page.md"
        path.parent.mkdir(parents=True)
        path.write_text(self._source(archived_url), encoding="utf-8")
        return path

    def _invoke(self, tmp_path):
        return CliRunner().invoke(
            main, ["recheck", "--sources", "2026/page", "--repo-root", str(tmp_path)]
        )

    @staticmethod
    def _replay(link: str) -> str:
        return link.replace("/https://", "id_/https://", 1)

    @staticmethod
    def _replayed(status: int):
        import httpx

        return httpx.Response(status, headers={"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT"})

    def test_recheck_sources_replaces_error_capture(self, tmp_path) -> None:
        import re

        import httpx
        import respx

        good_ts = _archive_ts(30)
        good = f"https://web.archive.org/web/{good_ts}/{self._URL}"
        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(404))
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            mock.get(re.compile(r"https://web\.archive\.org/cdx/search/cdx.*")).mock(
                return_value=httpx.Response(
                    200, json=[["timestamp", "original", "statuscode"], [good_ts, self._URL, "200"]]
                )
            )
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert path.read_text() == self._source(good)
        assert f"2026/page: {self._BAD} -> {good}" in result.output
        assert save.called is False

    def test_recheck_unchanged(self, tmp_path) -> None:
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(200))
            timegate = mock.get(_timegate_re())
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert "2026/page: unchanged" in result.output
        assert path.read_text() == self._source(self._BAD)
        assert timegate.called is False

    def test_recheck_keeps_the_link_when_no_good_capture(self, tmp_path) -> None:
        """Closes the backlog row "`--recheck` removes a bad link before another
        capture is found": the old link stays until a replacement passes its check."""
        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(404))
            mock.get(_timegate_re()).mock(return_value=httpx.Response(404))
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert "removed" not in result.output
        assert "archive.org capture is an error page (HTTP 404)" in result.output
        assert "no other 200 capture found" in result.output
        assert save.called is False

    def test_recheck_unverified_leaves_file(self, tmp_path) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(side_effect=httpx.ConnectError("down"))
            timegate = mock.get(_timegate_re())
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert "ConnectError" in result.output
        assert timegate.called is False

    def test_recheck_after_timegate_429_keeps_the_link_and_says_the_search_did_not_finish(
        self, tmp_path, no_archive_wait
    ) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            _live_page(mock)
            mock.head(self._replay(self._BAD)).mock(return_value=self._replayed(404))
            mock.get(_timegate_re()).mock(return_value=httpx.Response(429))
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert "archive.org TimeGate check failed (HTTP 429)" in result.output
        assert "no other 200 capture found" not in result.output
        assert "rerun `dr recheck --sources 2026/page` later" in result.output

    _MOVED = "https://example.org/moved"

    def _captured_redirect(self, mock, link: str) -> None:
        """The capture ``link`` of the page replays a 301 to a 200 capture of ``_MOVED``."""
        import httpx

        ts = link.split("/web/", 1)[1].split("/", 1)[0]
        moved = f"https://web.archive.org/web/{ts}id_/{self._MOVED}"
        mock.head(self._replay(link)).mock(
            return_value=httpx.Response(
                301,
                headers={"memento-datetime": "Sat, 10 Oct 2026 00:00:00 GMT", "location": moved},
            )
        )
        mock.head(moved).mock(return_value=self._replayed(200))

    def _live_redirect(self, mock) -> None:
        import httpx

        mock.get(self._URL).mock(
            return_value=httpx.Response(301, headers={"location": self._MOVED})
        )
        _live_page(mock, self._MOVED)

    def test_recheck_keeps_capture_that_redirects_where_the_live_page_ends(
        self, tmp_path
    ) -> None:
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            self._live_redirect(mock)
            self._captured_redirect(mock, self._BAD)
            timegate = mock.get(_timegate_re())
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert "2026/page: unchanged" in result.output
        assert path.read_text() == self._source(self._BAD)
        assert timegate.called is False

    def test_recheck_rejects_captured_redirect_when_live_page_does_not_load(
        self, tmp_path
    ) -> None:
        import re

        import httpx
        import respx

        path = self._write(tmp_path, self._BAD)
        with respx.mock as mock:
            mock.get(self._URL).mock(side_effect=httpx.ConnectError("down"))
            self._captured_redirect(mock, self._BAD)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            mock.get(re.compile(r"https://web\.archive\.org/cdx/search/cdx.*")).mock(
                return_value=httpx.Response(200, json=[["timestamp", "original", "statuscode"]])
            )
            result = self._invoke(tmp_path)

        assert result.exit_code == 1
        assert path.read_text() == self._source(self._BAD)
        assert f"archive.org capture redirects to {self._MOVED}" in result.output
        assert "no other 200 capture found" in result.output

    def test_backfill_records_capture_that_redirects_where_the_live_page_ends(
        self, tmp_path
    ) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, None)
        with respx.mock as mock:
            self._live_redirect(mock)
            self._captured_redirect(mock, self._BAD)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            save = mock.get(_save_re()).mock(return_value=httpx.Response(200))
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert path.read_text() == self._source(self._BAD)
        assert save.called is False

    def test_recheck_without_a_link_backfills(self, tmp_path, mock_capture_replay) -> None:
        import httpx
        import respx

        path = self._write(tmp_path, None)
        with respx.mock as mock:
            mock_capture_replay()
            _live_page(mock)
            mock.get(_timegate_re()).mock(
                return_value=httpx.Response(302, headers={"location": self._BAD})
            )
            result = self._invoke(tmp_path)

        assert result.exit_code == 0, result.output
        assert path.read_text() == self._source(self._BAD)
