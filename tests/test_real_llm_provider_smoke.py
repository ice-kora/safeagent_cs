import pytest

from app.llm import LLMProviderError, LLMRequest, OpenAICompatibleLLMProvider


def test_provider_from_env_fails_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("SAFEAGENT_LLM_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("SAFEAGENT_LLM_MODEL", "unit-test-model")

    with pytest.raises(LLMProviderError) as exc_info:
        OpenAICompatibleLLMProvider.from_env()

    assert "API key is missing" in str(exc_info.value)


def test_provider_timeout_is_configurable() -> None:
    provider = OpenAICompatibleLLMProvider(
        base_url="https://example.invalid",
        api_key="placeholder-value",
        model="unit-test-model",
        timeout_seconds=3.5,
        http_post=_fake_successful_post,
    )

    assert provider.timeout_seconds == 3.5


def test_provider_does_not_put_api_key_into_raw_response() -> None:
    provider = OpenAICompatibleLLMProvider(
        base_url="https://example.invalid",
        api_key="placeholder-value",
        model="unit-test-model",
        http_post=_fake_successful_post,
    )

    response = provider.complete(_request())

    serialized_raw = str(response.raw_response).lower()
    assert response.text == '{"schema_version": "1.0", "intent": "order_query"}'
    assert "placeholder-value" not in serialized_raw
    assert "api_key" not in serialized_raw
    assert "authorization" not in serialized_raw


def test_provider_error_is_converted_to_llm_provider_error() -> None:
    provider = OpenAICompatibleLLMProvider(
        base_url="https://example.invalid",
        api_key="placeholder-value",
        model="unit-test-model",
        http_post=_fake_failed_post,
    )

    with pytest.raises(LLMProviderError):
        provider.complete(_request())


def test_provider_uses_deepseek_env_names(monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SAFEAGENT_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SAFEAGENT_LLM_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-value")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.example")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")

    provider = OpenAICompatibleLLMProvider.from_env()

    assert provider.base_url == "https://api.deepseek.example"
    assert provider.model == "deepseek-chat"


def _request() -> LLMRequest:
    return LLMRequest(
        system_prompt="只输出 JSON。",
        user_prompt="帮我查一下订单 O10086",
        task_type="intent",
    )


def _fake_successful_post(endpoint, headers, payload, timeout_seconds):
    assert endpoint == "https://example.invalid/v1/chat/completions"
    assert headers["Authorization"].startswith("Bearer ")
    assert timeout_seconds > 0
    assert payload["model"] == "unit-test-model"
    return {
        "choices": [
            {
                "message": {
                    "content": '{"schema_version": "1.0", "intent": "order_query"}'
                }
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


def _fake_failed_post(endpoint, headers, payload, timeout_seconds):
    raise RuntimeError("network failed")
