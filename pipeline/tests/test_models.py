"""Tests for shared model enums."""

from __future__ import annotations

import pytest

from common.models import (
    Category,
    Confidence,
    EntityType,
    SourceKind,
    Verdict,
    _model_needs_reasoning_strip,
    resolve_model,
)


class TestVerdict:
    def test_values(self) -> None:
        expected = {
            "true",
            "mostly-true",
            "mixed",
            "mostly-false",
            "false",
            "unverified",
            "not-applicable",
        }
        actual = {v.value for v in Verdict}
        assert actual == expected

    def test_string_access(self) -> None:
        assert Verdict("true") is Verdict.TRUE
        assert Verdict("mostly-false") is Verdict.MOSTLY_FALSE

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            Verdict("invalid")

    def test_str_behavior(self) -> None:
        assert Verdict.FALSE.value == "false"


class TestConfidence:
    def test_values(self) -> None:
        expected = {"high", "medium", "low"}
        actual = {c.value for c in Confidence}
        assert actual == expected

    def test_string_access(self) -> None:
        assert Confidence("high") is Confidence.HIGH

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            Confidence("very-high")


class TestCategory:
    def test_values(self) -> None:
        expected = {
            "ai-safety",
            "environmental-impact",
            "product-comparison",
            "consumer-guide",
            "ai-literacy",
            "data-privacy",
            "industry-analysis",
            "regulation-policy",
        }
        actual = {c.value for c in Category}
        assert actual == expected

    def test_count(self) -> None:
        assert len(Category) == 8

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            Category("unknown-category")


class TestSourceKind:
    def test_values(self) -> None:
        expected = {"report", "article", "documentation", "dataset", "blog", "video", "index"}
        actual = {k.value for k in SourceKind}
        assert actual == expected

    def test_string_access(self) -> None:
        assert SourceKind("index") is SourceKind.INDEX

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceKind("podcast")


class TestEntityType:
    def test_values(self) -> None:
        expected = {"company", "product", "topic", "sector"}
        actual = {e.value for e in EntityType}
        assert actual == expected

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            EntityType("person")


class TestResolveModel:
    """`resolve_model` builds OpenAIModel instances for `infomaniak:...` specs
    and passes everything else through unchanged so PydanticAI's native string
    handling continues to work.
    """

    def test_passthrough_anthropic(self) -> None:
        assert resolve_model("anthropic:claude-haiku-4-5-20251001") == "anthropic:claude-haiku-4-5-20251001"

    def test_passthrough_test_model(self) -> None:
        assert resolve_model("test") == "test"

    def test_passthrough_bare(self) -> None:
        assert resolve_model("gpt-4o-mini") == "gpt-4o-mini"

    def test_infomaniak_builds_openai_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFOMANIAK_API_KEY", "test-key")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "test-pid")
        resolve_model.cache_clear()
        from pydantic_ai.models.openai import OpenAIModel

        model = resolve_model("infomaniak:openai/gpt-oss-120b")
        assert isinstance(model, OpenAIModel)
        assert model.model_name == "openai/gpt-oss-120b"

    def test_infomaniak_missing_keys_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INFOMANIAK_API_KEY", raising=False)
        monkeypatch.delenv("INFOMANIAK_PRODUCT_ID", raising=False)
        resolve_model.cache_clear()
        with pytest.raises(RuntimeError, match="INFOMANIAK"):
            resolve_model("infomaniak:openai/gpt-oss-120b")

    def test_mistral_gets_thinking_strip_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mistral specs must have ``openai_chat_send_back_thinking_parts=False``
        so PydanticAI drops thinking parts from outgoing assistant messages.
        Without this, Mistral 400s on the second tool turn.
        """
        monkeypatch.setenv("INFOMANIAK_API_KEY", "test-key")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "test-pid")
        resolve_model.cache_clear()
        from pydantic_ai.profiles.openai import OpenAIModelProfile

        model = resolve_model("infomaniak:mistralai/Mistral-Small-3.2-24B-Instruct-2506")
        profile = OpenAIModelProfile.from_profile(model.profile)
        assert profile.openai_chat_send_back_thinking_parts is False

    def test_non_mistral_keeps_default_thinking_handling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFOMANIAK_API_KEY", "test-key")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "test-pid")
        resolve_model.cache_clear()
        from pydantic_ai.profiles.openai import OpenAIModelProfile

        model = resolve_model("infomaniak:openai/gpt-oss-120b")
        profile = OpenAIModelProfile.from_profile(model.profile)
        # Default is "auto"; the scrubber only fires for Mistral.
        assert profile.openai_chat_send_back_thinking_parts != False  # noqa: E712


class TestModelNeedsReasoningStrip:
    @pytest.mark.parametrize(
        "model_id",
        [
            "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
            "mistral24b",
            "MISTRAL-large",
        ],
    )
    def test_mistral_variants(self, model_id: str) -> None:
        assert _model_needs_reasoning_strip(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "openai/gpt-oss-120b",
            "gemma3n",
            "google/gemma-3n-E4B-it",
            "claude-haiku-4-5-20251001",
        ],
    )
    def test_non_mistral(self, model_id: str) -> None:
        assert _model_needs_reasoning_strip(model_id) is False
