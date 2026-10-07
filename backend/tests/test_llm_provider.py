"""LLM provider tests (mocked — no network, no real key)."""
from unittest.mock import Mock

import pytest

from app.core import config
from app.agents.llm_provider import (
    DemoProvider,
    LLMProviderError,
    OpenAICompatibleProvider,
    get_llm_provider,
)


# ============================================================
# Factory selection
# ============================================================

def test_factory_demo_when_provider_is_demo(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "demo")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "sk-test")
    assert isinstance(get_llm_provider(), DemoProvider)


def test_factory_demo_when_key_empty(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "")
    assert isinstance(get_llm_provider(), DemoProvider)


def test_factory_openai_compatible(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "sk-test-key")
    monkeypatch.setattr(
        config.settings, "LLM_BASE_URL", "https://openrouter.ai/api/v1"
    )
    assert isinstance(get_llm_provider(), OpenAICompatibleProvider)


def test_factory_ollama(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "sk-test-key")
    monkeypatch.setattr(config.settings, "LLM_BASE_URL", "http://localhost:11434")
    provider = get_llm_provider()
    assert type(provider).__name__ == "OllamaProvider"


def test_factory_unknown_provider_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "nonsense-provider")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "sk-test-key")
    assert isinstance(get_llm_provider(), DemoProvider)


# ============================================================
# DemoProvider
# ============================================================

def test_demo_provider_is_demo():
    assert DemoProvider().is_demo() is True


def test_demo_provider_returns_json_message():
    import json
    result = json.loads(DemoProvider().chat("sys", "user"))
    assert result["demo_mode"] is True


# ============================================================
# OpenAICompatibleProvider error handling
# ============================================================

def _provider_with_fake_client(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "sk-test-key")
    monkeypatch.setattr(config.settings, "LLM_BASE_URL", "")
    provider = OpenAICompatibleProvider()
    provider._client = Mock()
    return provider


def test_chat_raises_llm_provider_error_on_failure(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch)
    provider._client.chat.completions.create.side_effect = Exception("API down")
    with pytest.raises(LLMProviderError):
        provider.chat("sys", "user")


def test_chat_returns_content_and_tracks_usage(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch)
    provider._client.chat.completions.create.return_value = Mock(
        usage=Mock(prompt_tokens=11, completion_tokens=22, total_tokens=33),
        choices=[Mock(message=Mock(content="hi"))],
    )
    out = provider.chat("sys", "user")
    assert out == "hi"
    assert provider.last_usage["total_tokens"] == 33
    assert provider.last_usage["latency_s"] >= 0


def test_client_uses_timeout_and_retries(monkeypatch):
    """The OpenAI client must be constructed with timeout=60 and max_retries=2."""
    from unittest.mock import patch
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "sk-test-key")
    monkeypatch.setattr(config.settings, "LLM_BASE_URL", "")
    with patch("openai.OpenAI") as mock_openai:
        OpenAICompatibleProvider()
        kwargs = mock_openai.call_args.kwargs
        assert kwargs["timeout"] == 60.0
        assert kwargs["max_retries"] == 2


def test_openrouter_default_headers(monkeypatch):
    """OpenRouter requests carry HTTP-Referer and X-Title headers."""
    from unittest.mock import patch
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(config.settings, "LLM_API_KEY", "sk-test-key")
    monkeypatch.setattr(
        config.settings, "LLM_BASE_URL", "https://openrouter.ai/api/v1"
    )
    with patch("openai.OpenAI") as mock_openai:
        OpenAICompatibleProvider()
        headers = mock_openai.call_args.kwargs["default_headers"]
        assert headers["HTTP-Referer"] == "http://localhost:5173"
        assert headers["X-Title"] == "AI Data Engineering Copilot"
