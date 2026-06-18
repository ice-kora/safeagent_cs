from pathlib import Path

from app.core.tool_result import ToolResult
from app.services.tool_gateway import ToolGateway
from app.tools.adapter import ToolCapability, ToolRequest
from app.tools.registry import ToolAdapterRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


class ForbiddenExportAdapter:
    """已注册但不在 ALLOWED_TOOL_NAMES 的 adapter，用于验证 fail-closed。

    它故意实现一个“危险”导出动作，但因为不在白名单内，ToolGateway 必须在
    到达 execute 之前就拒绝，calls 永远为 0。
    """

    name = "dangerous_tool.export_all_users"
    capability = ToolCapability(
        tool_name=name,
        read_only=False,
        side_effect=True,
        requires_idempotency=True,
        safe_for_llm=False,
    )

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: ToolRequest) -> ToolResult:
        self.calls += 1
        return ToolResult(
            success=True,
            tool_name=self.name,
            data={"leaked": True},
            summary="不应被调用。",
        )


def test_gateway_executes_allowed_and_registered_tool(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"user_id": "u_1001", "tenant_id": "t_001", "query": "退款政策"},
    )

    assert result.success is True
    assert result.tool_name == "knowledge_tool.query_policy"


def test_gateway_rejects_registered_but_not_allowed_tool(tmp_path: Path) -> None:
    """已注册但不在白名单的工具必须被拒绝，adapter.execute 不能被调用。"""
    adapter = ForbiddenExportAdapter()
    registry = ToolAdapterRegistry([adapter])
    gateway = ToolGateway(
        db_path=tmp_path / "test.db", mock_dir=MOCK_DIR, adapter_registry=registry
    )

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="dangerous_tool.export_all_users",
        tool_args={"user_id": "u_1001", "tenant_id": "t_001"},
    )

    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"
    assert adapter.calls == 0  # 白名单在 execute 之前拦截


def test_gateway_rejects_unknown_tool(tmp_path: Path) -> None:
    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="totally_made_up_tool",
        tool_args={"user_id": "u_1001"},
    )

    # 不在白名单也不在 registry → 白名单先拦截
    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"


def test_gateway_rejects_allowed_but_not_registered_tool(tmp_path: Path) -> None:
    """工具名在 ALLOWED_TOOL_NAMES 中，但 registry 未注册该 adapter → TOOL_NOT_REGISTERED。"""
    empty_registry = ToolAdapterRegistry([])
    gateway = ToolGateway(
        db_path=tmp_path / "test.db", mock_dir=MOCK_DIR, adapter_registry=empty_registry
    )

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"user_id": "u_1001", "tenant_id": "t_001", "query": "退款"},
    )

    # 白名单通过，但 registry 查不到 → TOOL_NOT_REGISTERED
    assert result.success is False
    assert result.error_type == "TOOL_NOT_REGISTERED"


def test_gateway_rejects_registered_but_not_allowed_tool_writes_failed_log(
    tmp_path: Path,
) -> None:
    """白名单拒绝的调用仍需写入 tool_call_logs，便于审计。"""
    import json

    from app.storage.db import get_connection

    db_path = tmp_path / "test.db"
    adapter = ForbiddenExportAdapter()
    registry = ToolAdapterRegistry([adapter])
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR, adapter_registry=registry)

    gateway.call_tool(
        run_id="run_audit",
        session_id="sess_001",
        tool_name="dangerous_tool.export_all_users",
        tool_args={"user_id": "u_1001", "tenant_id": "t_001"},
    )

    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT status, failure_type FROM tool_call_logs WHERE run_id = ?",
            ("run_audit",),
        ).fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_type"] == "TOOL_NOT_IN_ALLOWLIST"
    json.dumps(dict(row))  # smoke: row is JSON-serializable
