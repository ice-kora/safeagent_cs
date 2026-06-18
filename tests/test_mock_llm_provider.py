import socket

from app.llm import LLMRequest, MockLLMProvider


def test_mock_llm_provider_does_not_access_external_network(monkeypatch) -> None:
    def fail_connect(*args, **kwargs):
        raise AssertionError("MockLLMProvider must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    provider = MockLLMProvider(response_map={"intent": '{"intent": "order_query"}'})

    response = provider.complete(_request("intent"))

    assert response.text == '{"intent": "order_query"}'
    assert response.provider_name == "mock"


def test_mock_llm_provider_returns_text_by_task_type() -> None:
    provider = MockLLMProvider(
        response_map={
            "intent": '{"intent": "order_query"}',
            "planner": '{"action": "query_order"}',
            "response": "请求已处理完成。",
        }
    )

    assert provider.complete(_request("intent")).text == '{"intent": "order_query"}'
    assert provider.complete(_request("planner")).text == '{"action": "query_order"}'
    assert provider.complete(_request("response")).text == "请求已处理完成。"


def test_mock_llm_provider_returns_default_text_for_unknown_task() -> None:
    provider = MockLLMProvider(
        response_map={"intent": '{"intent": "order_query"}'},
        default_text="默认 mock 响应",
    )

    response = provider.complete(_request("unknown"))

    assert response.text == "默认 mock 响应"
    assert response.raw_response == {
        "provider": "mock",
        "task_type": "unknown",
        "matched": False,
    }


def test_mock_llm_provider_uses_provider_name_mock() -> None:
    provider = MockLLMProvider()

    response = provider.complete(_request("response"))

    assert response.provider_name == "mock"
    assert response.model_name == "mock-model"


def test_mock_llm_provider_response_has_no_secret_fields() -> None:
    provider = MockLLMProvider()

    response = provider.complete(_request("intent"))
    serialized = str(response.__dict__).lower()

    assert "api_key" not in serialized
    assert "token" not in serialized
    assert "secret" not in serialized


def _request(task_type: str) -> LLMRequest:
    return LLMRequest(
        system_prompt="你是安全客服 Agent。",
        user_prompt="用户请求",
        task_type=task_type,
    )
