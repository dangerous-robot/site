"""Unit tests for the canonical-URL helper used as a dedup key."""

from __future__ import annotations

import pytest

from common.canonical_url import canonicalize


class TestCanonicalize:
    # --- Scheme ---

    def test_scheme_lowered(self) -> None:
        assert canonicalize("HTTPS://example.com/path") == "https://example.com/path"

    def test_http_and_https_not_collapsed(self) -> None:
        """http and https are distinct origins; canonicaliser must not merge them."""
        http = canonicalize("http://example.com/path")
        https = canonicalize("https://example.com/path")
        assert http != https

    # --- Host ---

    def test_host_lowered(self) -> None:
        assert canonicalize("https://EXAMPLE.com/path") == "https://example.com/path"

    def test_www_stripped(self) -> None:
        assert canonicalize("https://www.example.com/path") == "https://example.com/path"

    def test_www_only_stripped_at_start(self) -> None:
        """A host like 'www.foo.com' loses the www; 'foo.www.com' does not."""
        assert canonicalize("https://foo.www.com/x") == "https://foo.www.com/x"

    def test_subdomain_preserved(self) -> None:
        assert canonicalize("https://api.example.com/v1") == "https://api.example.com/v1"

    # --- Ports ---

    def test_default_http_port_stripped(self) -> None:
        assert canonicalize("http://example.com:80/path") == "http://example.com/path"

    def test_default_https_port_stripped(self) -> None:
        assert canonicalize("https://example.com:443/path") == "https://example.com/path"

    def test_non_default_port_preserved(self) -> None:
        assert canonicalize("https://example.com:8080/path") == "https://example.com:8080/path"

    def test_non_default_port_on_http(self) -> None:
        assert canonicalize("http://example.com:8000/x") == "http://example.com:8000/x"

    # --- Path ---

    def test_trailing_slash_stripped(self) -> None:
        assert canonicalize("https://example.com/path/") == "https://example.com/path"

    def test_root_slash_preserved(self) -> None:
        assert canonicalize("https://example.com/") == "https://example.com/"

    def test_no_path_normalises_to_root(self) -> None:
        assert canonicalize("https://example.com") == "https://example.com/"

    def test_path_case_preserved(self) -> None:
        """Paths are case-sensitive on most servers; do not lowercase."""
        assert canonicalize("https://example.com/CamelPath") == "https://example.com/CamelPath"

    def test_dot_segments_resolved(self) -> None:
        assert canonicalize("https://example.com/a/./b/../c") == "https://example.com/a/c"

    def test_dot_dot_clamped_at_root(self) -> None:
        """`..` above root does not escape the origin."""
        assert canonicalize("https://example.com/../etc") == "https://example.com/etc"

    # --- Query: tracking params ---

    @pytest.mark.parametrize(
        "param",
        [
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "gclid",
            "fbclid",
            "mc_cid",
            "mc_eid",
            "_ga",
            "ref",
            "ref_src",
        ],
    )
    def test_tracking_param_dropped(self, param: str) -> None:
        url = f"https://example.com/p?keep=1&{param}=drop"
        assert canonicalize(url) == "https://example.com/p?keep=1"

    def test_tracking_param_drop_is_case_insensitive(self) -> None:
        """Real-world URLs use mixed case for query keys; drop regardless."""
        url = "https://example.com/p?UTM_Source=newsletter&keep=1"
        assert canonicalize(url) == "https://example.com/p?keep=1"

    def test_only_tracking_params_yields_empty_query(self) -> None:
        assert (
            canonicalize("https://example.com/p?utm_source=x&utm_medium=y")
            == "https://example.com/p"
        )

    # --- Query: ordering ---

    def test_query_keys_sorted(self) -> None:
        """?b=1&a=2 and ?a=2&b=1 produce the same canonical form."""
        a = canonicalize("https://example.com/p?b=1&a=2")
        b = canonicalize("https://example.com/p?a=2&b=1")
        assert a == b == "https://example.com/p?a=2&b=1"

    def test_duplicate_keys_preserve_value_order(self) -> None:
        """Stable sort: duplicate-key values keep their original order."""
        url = "https://example.com/p?k=2&k=1"
        # Stable sort on key keeps "2" before "1" because that's how they
        # appeared in the input.
        assert canonicalize(url) == "https://example.com/p?k=2&k=1"

    def test_blank_value_preserved(self) -> None:
        assert canonicalize("https://example.com/p?a=") == "https://example.com/p?a="

    # --- Fragment ---

    def test_fragment_dropped(self) -> None:
        assert canonicalize("https://example.com/p#section") == "https://example.com/p"

    def test_fragment_dropped_with_query(self) -> None:
        assert (
            canonicalize("https://example.com/p?a=1#section")
            == "https://example.com/p?a=1"
        )

    # --- Userinfo (preserved) ---

    def test_userinfo_preserved(self) -> None:
        assert (
            canonicalize("https://user@example.com/p")
            == "https://user@example.com/p"
        )

    # --- Idempotency ---

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/",
            "https://example.com",
            "HTTPS://Example.com/Path/",
            "http://www.example.com:80/x/./y/../z?b=1&a=2#frag",
            "https://example.com:8080/p?utm_source=newsletter&q=1",
            "https://example.com/p?b=1&a=2&utm_campaign=c",
            "https://api.example.com/v1/items?id=42",
            "https://EXAMPLE.com/CamelCase",
            "https://example.com/p?k=2&k=1",
            "https://user@example.com/p#frag",
        ],
    )
    def test_idempotent(self, url: str) -> None:
        once = canonicalize(url)
        assert canonicalize(once) == once

    # --- Cross-input equivalence ---

    def test_equivalent_inputs_collapse(self) -> None:
        """A battery of differing-but-equivalent inputs share one canonical form."""
        canonical = canonicalize("https://example.com/path")
        equivalents = [
            "HTTPS://example.com/path",
            "https://EXAMPLE.com/path",
            "https://www.example.com/path",
            "https://example.com:443/path",
            "https://example.com/path/",
            "https://example.com/path#anchor",
            "https://example.com/path?utm_source=x",
            "https://example.com/./path",
        ]
        for url in equivalents:
            assert canonicalize(url) == canonical, (
                f"{url!r} did not canonicalise to {canonical!r}"
            )

    # --- Malformed input ---

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            canonicalize("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError):
            canonicalize("   ")

    def test_no_scheme_raises(self) -> None:
        with pytest.raises(ValueError):
            canonicalize("example.com/path")

    def test_no_host_raises(self) -> None:
        with pytest.raises(ValueError):
            canonicalize("https:///path")

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError):
            canonicalize(None)  # type: ignore[arg-type]
