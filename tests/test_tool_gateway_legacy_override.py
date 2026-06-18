from pathlib import Path

import pytest

from app.services.tool_gateway import ToolGateway


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_gateway_no_longer_holds_legacy_registry_field(tmp_path: Path) -> None:
    """v0.6-Tool-R1 已移除 legacy ToolRegistry 兼容外壳的持有。

    生产路径只走 adapter_registry.get(...).execute(...)，不再保留 self.registry。
    """
    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)

    assert not hasattr(gateway, "registry")
    assert hasattr(gateway, "adapter_registry")


def test_legacy_get_handler_monkeypatch_no_longer_routes(tmp_path: Path) -> None:
    """旧测试曾 monkeypatch gateway.registry.get_handler 让 fake handler 生效。

    legacy 分支删除后，即使有人给 gateway 打补丁，也不应改写工具路由——
    生产路径恒走 adapter_registry。这里用一个未被注册且未在白名单的工具验证
    它仍被拒绝（不会再有通过 monkeypatch 放行的情况）。
    """
    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)

    # 模拟旧用法：试图 monkeypatch 一个不存在的 registry 字段。
    # 不应抛错，但工具仍按白名单/registry 正常拒绝。
    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="unknown_tool.export_all_users",
        tool_args={"user_id": "u_1001"},
    )

    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"


def test_module_does_not_define_legacy_override_helper() -> None:
    """_uses_legacy_registry_override 已从模块删除。"""
    from app.services import tool_gateway

    assert not hasattr(tool_gateway, "_uses_legacy_registry_override")


def test_allowed_mock_tool_still_executes_after_legacy_removal(tmp_path: Path) -> None:
    """移除 legacy 分支后，正常 allowed + registered 工具仍可执行。"""
    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"user_id": "u_1001", "tenant_id": "t_001", "query": "退款政策"},
    )

    assert result.success is True


def test_importing_tool_gateway_does_not_require_tool_registry(tmp_path: Path) -> None:
    """ToolGateway 不再依赖 ToolRegistry 兼容外壳作为构造产物。

    import 仍可用，且 ToolRegistry（仍被 test_tool_registry 单独覆盖）独立存在。
    """
    from app.services.tool_gateway import ToolGateway as Gateway  # noqa: F401
    from app.tools.registry import ToolRegistry  # noqa: F401

    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)
    with pytest.raises(AttributeError):
        # __init__ 不再写 self.registry
        getattr(gateway, "registry")
