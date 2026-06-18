from pathlib import Path

from app.services.tool_gateway import ToolGateway
from app.storage.db import get_connection
from app.storage.seed_data import seed_sqlite_users_orders


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_gateway_executes_query_policy_through_adapter(tmp_path: Path) -> None:
    gateway = ToolGateway(db_path=tmp_path / "test.db", mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "发票"},
    )

    assert result.success is True
    assert result.tool_name == "knowledge_tool.query_policy"


def test_gateway_executes_order_query_through_adapter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    seed_sqlite_users_orders(db_path)
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_002",
        session_id="sess_001",
        tool_name="order_tool.query_order",
        tool_args={"order_id": "O10086"},
    )

    assert result.success is True
    assert result.data["order_id"] == "O10086"


def test_gateway_executes_change_address_through_adapter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    seed_sqlite_users_orders(db_path)
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_003",
        session_id="sess_001",
        tool_name="order_tool.change_address",
        tool_args={
            "user_id": "u_1001",
            "tenant_id": "t_001",
            "action": "change_address",
            "target_type": "order",
            "target_id": "O10086",
            "order_id": "O10086",
            "new_address": "敏感详细地址",
        },
    )

    assert result.success is True
    assert result.data["request_status"] == "RECEIVED"


def test_gateway_executes_create_ticket_through_adapter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_004",
        session_id="sess_001",
        tool_name="ticket_tool.create_ticket",
        tool_args={
            "user_id": "u_1001",
            "action": "request_refund",
            "target_type": "order",
            "target_id": "O10086",
            "ticket_type": "refund",
            "risk_level": "L4",
        },
    )

    assert result.success is True
    assert result.data["ticket_id"].startswith("tk_")


def test_gateway_unknown_tool_still_rejects_and_logs(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_005",
        session_id="sess_001",
        tool_name="unknown_tool.export_all_users",
        tool_args={},
    )
    log = _tool_logs(db_path)[0]

    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"
    assert log["status"] == "FAILED"


def test_gateway_writes_idempotency_facts_with_adapter(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    gateway.call_tool(
        run_id="run_006",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "退款政策"},
    )
    log = _tool_logs(db_path)[0]

    assert log["tool_call_id"].startswith("tc_")
    assert log["idempotency_key"].startswith("idem_")
    assert log["action_fingerprint"].startswith("af_")


def test_gateway_rejects_registered_but_not_allowed_tool(tmp_path: Path) -> None:
    """adapter 已注册但不在 ALLOWED_TOOL_NAMES 中，必须拒绝且不执行。"""
    from app.tools.adapter import ToolCapability, ToolRequest
    from app.tools.registry import ToolAdapterRegistry

    class SpyAdapter:
        name = "extra_tool.debug_dump"
        capability = ToolCapability(
            tool_name="extra_tool.debug_dump",
            read_only=False,
            side_effect=True,
            requires_idempotency=False,
            safe_for_llm=False,
        )

        def __init__(self) -> None:
            self.calls = 0

        def execute(self, request: ToolRequest):  # pragma: no cover - 不应执行
            self.calls += 1
            ...

    spy = SpyAdapter()
    registry = ToolAdapterRegistry([spy])
    gateway = ToolGateway(
        db_path=tmp_path / "test.db", mock_dir=MOCK_DIR, adapter_registry=registry
    )

    result = gateway.call_tool(
        run_id="run_007",
        session_id="sess_001",
        tool_name="extra_tool.debug_dump",
        tool_args={"user_id": "u_1001"},
    )

    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"
    assert spy.calls == 0


def _tool_logs(db_path: Path) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT tool_call_id, idempotency_key, action_fingerprint, status
            FROM tool_call_logs
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]
