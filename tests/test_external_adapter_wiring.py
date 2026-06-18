from pathlib import Path

from app.core.config import (
    TOOL_BACKEND_EXTERNAL_STUB,
    TOOL_BACKEND_MOCK,
    get_settings,
)
from app.services.tool_gateway import ToolGateway
from app.tools.registry import build_adapter_registry


class FakeHttpClient:
    """测试用 fake client，记录请求但不发真实网络。"""

    def __init__(self) -> None:
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


# --- config 默认值 ---


def test_default_tool_backend_is_mock(monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_TOOL_BACKEND", raising=False)

    settings = get_settings()

    assert settings.tool_backend == TOOL_BACKEND_MOCK


def test_invalid_tool_backend_falls_back_to_mock(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_TOOL_BACKEND", "definitely_not_a_backend")

    settings = get_settings()

    assert settings.tool_backend == TOOL_BACKEND_MOCK


# --- build_adapter_registry ---


def test_build_adapter_registry_mock_registers_four_mock_adapters() -> None:
    registry = build_adapter_registry(TOOL_BACKEND_MOCK)

    assert registry.names() == [
        "knowledge_tool.query_policy",
        "order_tool.change_address",
        "order_tool.query_order",
        "ticket_tool.create_ticket",
    ]


def test_build_adapter_registry_external_stub_not_registered_to_mock_by_default() -> None:
    """mock 默认 registry 不应包含 external stub adapter。"""
    registry = build_adapter_registry(TOOL_BACKEND_MOCK)

    assert "external_order_tool" not in registry.names()
    assert "external_ticket_tool" not in registry.names()


def test_build_adapter_registry_external_stub_registers_stubs_disabled_by_default() -> None:
    """external_stub 注册 stub adapter，但没有 client/base_url 时 disabled。"""
    registry = build_adapter_registry(TOOL_BACKEND_EXTERNAL_STUB)

    assert "external_order_tool" in registry.names()
    assert "external_ticket_tool" in registry.names()
    # stub 默认 fail-closed：无 client / base_url
    order_stub = registry.get("external_order_tool")
    assert order_stub.enabled is False
    assert order_stub.base_url is None


def test_build_adapter_registry_external_stub_enables_with_client_and_base_url() -> None:
    client = FakeHttpClient()
    registry = build_adapter_registry(
        TOOL_BACKEND_EXTERNAL_STUB,
        stub_base_url="https://example.invalid",
        stub_client=client,
    )

    order_stub = registry.get("external_order_tool")
    assert order_stub.enabled is True
    assert order_stub.base_url == "https://example.invalid"
    assert order_stub.client is client


def test_build_adapter_registry_invalid_backend_falls_back_to_mock() -> None:
    registry = build_adapter_registry("bogus")

    assert registry.names() == [
        "knowledge_tool.query_policy",
        "order_tool.change_address",
        "order_tool.query_order",
        "ticket_tool.create_ticket",
    ]


# --- ToolGateway 与 config 联动（external stub 默认 fail-closed） ---


def test_external_stub_tool_rejected_by_allowlist_even_if_registered(
    tmp_path: Path,
) -> None:
    """external stub adapter 即使注册并 enabled，也不在 ALLOWED_TOOL_NAMES 中，
    ToolGateway 必须拒绝（两步 fail-closed）。"""
    client = FakeHttpClient()
    registry = build_adapter_registry(
        TOOL_BACKEND_EXTERNAL_STUB,
        stub_base_url="https://example.invalid",
        stub_client=client,
    )
    gateway = ToolGateway(
        db_path=tmp_path / "test.db", mock_dir=None, adapter_registry=registry
    )

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="external_order_tool",
        tool_args={"user_id": "u_1001", "order_id": "O10086"},
    )

    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"
    assert client.calls == []  # 白名单在调用前拦截，未触达 fake client


def test_external_stub_does_not_send_real_network_request(tmp_path: Path) -> None:
    """external_stub 模式必须使用注入的 fake client，绝不发真实网络请求。"""
    client = FakeHttpClient()
    registry = build_adapter_registry(
        TOOL_BACKEND_EXTERNAL_STUB,
        stub_base_url="https://example.invalid",
        stub_client=client,
    )

    # 直接执行 stub adapter，验证它只通过注入的 client 模拟，不触达网络层。
    from app.tools.adapter import ToolExecutionContext, ToolRequest

    adapter = registry.get("external_order_tool")
    request = ToolRequest(
        tool_name=adapter.name,
        tool_args={"order_id": "O10086"},
        context=ToolExecutionContext(
            run_id="run_001",
            session_id="sess_001",
            user_id="u_1001",
            tenant_id="t_001",
            action_plan=None,
            tool_call_id="tc_001",
            idempotency_key="idem_001",
            action_fingerprint="af_001",
        ),
    )
    result = adapter.execute(request)

    assert result.success is True
    assert client.calls
    assert client.calls[0]["base_url"] == "https://example.invalid"
