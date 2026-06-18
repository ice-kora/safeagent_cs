import pytest

from app.core.tool_allowlist import ALLOWED_TOOL_NAMES
from app.tools.adapter import ToolCapability, ToolRequest
from app.tools.registry import ToolAdapterNotFoundError, ToolAdapterRegistry


def test_adapter_registry_defaults_to_mock_adapters() -> None:
    registry = ToolAdapterRegistry()

    assert registry.names() == [
        "knowledge_tool.query_policy",
        "order_tool.change_address",
        "order_tool.query_order",
        "ticket_tool.create_ticket",
    ]


def test_adapter_registry_unknown_tool_raises_clear_error() -> None:
    registry = ToolAdapterRegistry()

    with pytest.raises(ToolAdapterNotFoundError, match="Tool adapter not found"):
        registry.get("unknown_tool.export_all_users")


def test_adapter_registry_capabilities_are_auditable() -> None:
    registry = ToolAdapterRegistry()
    capabilities = registry.capabilities()

    assert capabilities["order_tool.query_order"].read_only is True
    assert capabilities["ticket_tool.create_ticket"].requires_idempotency is True


def test_adapter_registry_names_not_equivalent_to_security_allowlist() -> None:
    """registry.names() 表示已注册目录，不再是最终安全白名单。

    手动注册一个不在 ALLOWED_TOOL_NAMES 中的 adapter 后，它应出现在
    registry.names()，但不应出现在 ALLOWED_TOOL_NAMES 中——这证明两个集合
    已解耦，ToolGateway 需要同时校验两者。
    """

    class ExtraAdapter:
        name = "extra_tool.debug_dump"
        capability = ToolCapability(
            tool_name="extra_tool.debug_dump",
            read_only=False,
            side_effect=True,
            requires_idempotency=False,
            safe_for_llm=False,
        )

        def execute(self, request: ToolRequest):  # pragma: no cover - 不会被执行
            ...

    registry = ToolAdapterRegistry([ExtraAdapter()])

    assert "extra_tool.debug_dump" in registry.names()
    assert "extra_tool.debug_dump" not in ALLOWED_TOOL_NAMES

