import pytest

from app.llm import (
    LLMProviderError,
    LLMProviderNotFoundError,
    LLMProviderRegistry,
    LLMRequest,
    LLMResponse,
    MockLLMProvider,
)


def test_llm_request_can_be_created() -> None:
    request = LLMRequest(
        system_prompt="你是安全客服 Agent。",
        user_prompt="帮我查订单",
        task_type="intent",
        temperature=0.1,
        max_tokens=128,
        metadata={"run_id": "run_001"},
    )

    assert request.task_type == "intent"
    assert request.temperature == 0.1
    assert request.max_tokens == 128
    assert request.metadata["run_id"] == "run_001"


def test_llm_response_can_be_created() -> None:
    response = LLMResponse(
        text='{"intent": "order_query"}',
        provider_name="mock",
        model_name="mock-model",
        usage={"input_tokens": 10, "output_tokens": 5},
        raw_response={"status": "ok"},
    )

    assert response.text == '{"intent": "order_query"}'
    assert response.provider_name == "mock"
    assert response.model_name == "mock-model"
    assert response.usage["input_tokens"] == 10


def test_request_rejects_secret_metadata_keys() -> None:
    with pytest.raises(LLMProviderError):
        LLMRequest(
            system_prompt="system",
            user_prompt="user",
            task_type="intent",
            metadata={"api_key": "should_not_be_here"},
        )


def test_response_rejects_secret_raw_response_keys() -> None:
    with pytest.raises(LLMProviderError):
        LLMResponse(
            text="ok",
            provider_name="mock",
            raw_response={"token": "should_not_be_here"},
        )


def test_registry_can_register_provider() -> None:
    registry = LLMProviderRegistry(register_mock=False)
    provider = MockLLMProvider()

    registry.register(provider)

    assert registry.get("mock") is provider


def test_registry_can_get_provider_by_name() -> None:
    registry = LLMProviderRegistry()

    provider = registry.get("mock")

    assert provider.name == "mock"


def test_registry_raises_clear_error_for_missing_provider() -> None:
    registry = LLMProviderRegistry(register_mock=False)

    with pytest.raises(LLMProviderNotFoundError) as exc_info:
        registry.get("missing")

    assert "LLM provider not found: missing" in str(exc_info.value)


def test_registry_names_returns_provider_names() -> None:
    registry = LLMProviderRegistry()

    assert registry.names() == ["mock"]


def test_registry_duplicate_name_overwrites_provider() -> None:
    registry = LLMProviderRegistry(register_mock=False)
    first = MockLLMProvider(default_text="first")
    second = MockLLMProvider(default_text="second")

    registry.register(first)
    registry.register(second)

    assert registry.get("mock") is second
