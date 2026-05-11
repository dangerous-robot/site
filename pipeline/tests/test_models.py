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
        expected = {"report", "article", "documentation", "dataset", "blog", "video", "index", "paper"}
        actual = {k.value for k in SourceKind}
        assert actual == expected

    def test_string_access(self) -> None:
        assert SourceKind("index") is SourceKind.INDEX

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceKind("podcast")


class TestEntityType:
    def test_values(self) -> None:
        expected = {"company", "product", "subject"}
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
        from pydantic_ai.models.openai import OpenAIChatModel

        model = resolve_model("infomaniak:swiss-ai/Apertus-70B-Instruct-2509")
        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "swiss-ai/Apertus-70B-Instruct-2509"

    def test_infomaniak_missing_keys_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INFOMANIAK_API_KEY", raising=False)
        monkeypatch.delenv("INFOMANIAK_PRODUCT_ID", raising=False)
        resolve_model.cache_clear()
        with pytest.raises(RuntimeError, match="INFOMANIAK"):
            resolve_model("infomaniak:swiss-ai/Apertus-70B-Instruct-2509")

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

        model = resolve_model("infomaniak:swiss-ai/Apertus-70B-Instruct-2509")
        profile = OpenAIModelProfile.from_profile(model.profile)
        # Default is "auto"; the scrubber only fires for Mistral.
        assert profile.openai_chat_send_back_thinking_parts != False  # noqa: E712

    def test_greenpt_builds_openai_chat_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GREENPT_API_KEY", "test-key")
        resolve_model.cache_clear()
        from pydantic_ai.models.openai import OpenAIChatModel

        model = resolve_model("greenpt:gpt-oss-120b")
        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "gpt-oss-120b"

    def test_greenpt_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GREENPT_API_KEY", raising=False)
        resolve_model.cache_clear()
        with pytest.raises(RuntimeError, match="GREENPT"):
            resolve_model("greenpt:gpt-oss-120b")

    def test_fallback_spec_returns_fallback_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mixes an Infomaniak leg (Model instance) with an Anthropic leg
        (passthrough string) to cover both shapes the splitter produces."""
        monkeypatch.setenv("INFOMANIAK_API_KEY", "test-key")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "test-pid")
        resolve_model.cache_clear()
        from pydantic_ai.models.fallback import FallbackModel
        from pydantic_ai.models.openai import OpenAIChatModel

        model = resolve_model(
            "infomaniak:openai/gpt-oss-120b||anthropic:claude-haiku-4-5-20251001"
        )
        assert isinstance(model, FallbackModel)
        assert len(model.models) == 2
        # First leg is the resolved Infomaniak model.
        assert isinstance(model.models[0], OpenAIChatModel)
        # Second leg goes through ``infer_model`` inside ``FallbackModel.__init__``
        # which turns the bare string into a concrete Anthropic model.
        assert "claude" in model.models[1].model_name.lower()

    def test_fallback_spec_trims_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFOMANIAK_API_KEY", "test-key")
        monkeypatch.setenv("INFOMANIAK_PRODUCT_ID", "test-pid")
        resolve_model.cache_clear()
        from pydantic_ai.models.fallback import FallbackModel

        model = resolve_model(
            "infomaniak:openai/gpt-oss-120b  ||  anthropic:claude-haiku-4-5-20251001"
        )
        assert isinstance(model, FallbackModel)
        assert model.models[0].model_name == "openai/gpt-oss-120b"


class TestModelNeedsReasoningStrip:
    @pytest.mark.parametrize(
        "model_id",
        [
            "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
            "mistralai/Ministral-3-14B-Instruct-2512",
            "mistral24b",
            "MISTRAL-large",
        ],
    )
    def test_mistral_variants(self, model_id: str) -> None:
        assert _model_needs_reasoning_strip(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "swiss-ai/Apertus-70B-Instruct-2509",
            "claude-haiku-4-5-20251001",
        ],
    )
    def test_non_mistral(self, model_id: str) -> None:
        assert _model_needs_reasoning_strip(model_id) is False
