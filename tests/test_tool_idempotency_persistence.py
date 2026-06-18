import json
from pathlib import Path

from app.core.action_plan import ActionPlan
from app.core.idempotency import (
    build_action_fingerprint,
    build_idempotency_key,
    generate_tool_call_id,
)
from app.core.tool_result import ToolError, ToolResult
from app.services.failure_handler import FailureHandler
from app.services.tool_gateway import ToolGateway
from app.storage.db import get_connection
from app.tools.adapter import ToolCapability, ToolRequest
from app.tools.registry import ToolAdapterRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


class RetryablePolicyAdapter:
    """测试用 fake adapter：第一次执行返回可重试的 TOOL_TIMEOUT，第二次成功。

    用于验证 FailureHandler 重试链路经 ToolGateway 时，attempt_no 递增而
    idempotency_key / action_fingerprint 保持稳定。通过 adapter_registry=
    注入，避免再依赖已移除的 legacy monkeypatch get_handler 路径。
    """

    name = "knowledge_tool.query_policy"
    capability = ToolCapability(
        tool_name=name,
        read_only=True,
        side_effect=False,
        requires_idempotency=False,
        safe_for_llm=True,
    )

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: ToolRequest) -> ToolResult:
        self.calls += 1
        if self.calls == 1:
            return ToolResult(
                success=False,
                tool_name=self.name,
                data={},
                summary="临时失败。",
                error_type="TOOL_TIMEOUT",
                error=ToolError(
                    failure_type="TOOL_TIMEOUT",
                    message="timeout",
                    retryable=True,
                ),
            )
        return ToolResult(
            success=True,
            tool_name=self.name,
            data={"answer": "ok", "sources": []},
            summary="重试成功。",
        )


def test_same_action_plan_generates_same_action_fingerprint() -> None:
    first = _query_order_plan("O10086")
    second = _query_order_plan("O10086")

    assert build_action_fingerprint(first) == build_action_fingerprint(second)


def test_action_plan_dict_order_does_not_change_fingerprint() -> None:
    first = {
        "action": "query_order",
        "target_type": "order",
        "target_id": "O10086",
        "tool_name": "order_tool.query_order",
        "tool_args": {"order_id": "O10086", "action": "query_order"},
    }
    second = {
        "tool_args": {"action": "query_order", "order_id": "O10086"},
        "tool_name": "order_tool.query_order",
        "target_id": "O10086",
        "target_type": "order",
        "action": "query_order",
    }

    assert build_action_fingerprint(first) == build_action_fingerprint(second)


def test_target_id_change_changes_fingerprint() -> None:
    assert build_action_fingerprint(_query_order_plan("O10086")) != build_action_fingerprint(
        _query_order_plan("O10087")
    )


def test_tool_call_id_is_unique() -> None:
    assert generate_tool_call_id() != generate_tool_call_id()
    assert generate_tool_call_id().startswith("tc_")


def test_idempotency_key_is_stable_for_same_logical_action() -> None:
    fingerprint = build_action_fingerprint(_query_order_plan("O10086"))

    first = build_idempotency_key(
        tenant_id="t_001",
        user_id="u_1001",
        tool_name="order_tool.query_order",
        action_fingerprint=fingerprint,
    )
    second = build_idempotency_key(
        tenant_id="t_001",
        user_id="u_1001",
        tool_name="order_tool.query_order",
        action_fingerprint=fingerprint,
    )

    assert first == second
    assert first.startswith("idem_")


def test_fingerprint_does_not_expose_sensitive_values() -> None:
    fingerprint = build_action_fingerprint(
        {
            "action": "change_address",
            "target_type": "order",
            "target_id": "O10086",
            "tool_name": "order_tool.change_address",
            "tool_args": {
                "raw_message": "手机号 13812345678 token=secret",
                "new_address": "Very Sensitive Full Address 999",
                "api_key": "key_secret",
            },
        }
    )

    assert "13812345678" not in fingerprint
    assert "Very Sensitive Full Address 999" not in fingerprint
    assert "key_secret" not in fingerprint


def test_tool_gateway_writes_idempotency_facts(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    result = gateway.call_tool(
        run_id="run_001",
        session_id="sess_001",
        tool_name="order_tool.query_order",
        tool_args=_tool_args(),
    )
    log = _tool_logs(db_path)[0]

    assert result.success is True
    assert log["tool_call_id"].startswith("tc_")
    assert log["idempotency_key"].startswith("idem_")
    assert log["action_fingerprint"].startswith("af_")
    assert log["attempt_no"] == 1


def test_tool_gateway_duplicate_idempotency_key_does_not_skip_execution(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    gateway.call_tool(
        run_id="run_002",
        session_id="sess_001",
        tool_name="order_tool.query_order",
        tool_args=_tool_args(),
    )
    gateway.call_tool(
        run_id="run_002",
        session_id="sess_001",
        tool_name="order_tool.query_order",
        tool_args=_tool_args(),
    )
    logs = _tool_logs(db_path)

    assert len(logs) == 2
    assert logs[0]["idempotency_key"] == logs[1]["idempotency_key"]
    assert logs[0]["action_fingerprint"] == logs[1]["action_fingerprint"]
    assert logs[0]["tool_call_id"] != logs[1]["tool_call_id"]


def test_failure_handler_retry_keeps_idempotency_key_and_changes_tool_call_id(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    adapter = RetryablePolicyAdapter()
    registry = ToolAdapterRegistry([adapter])
    gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR, adapter_registry=registry)
    handler = FailureHandler(db_path=db_path)

    first_result = gateway.call_tool(
        run_id="run_retry",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args=_policy_tool_args(),
        attempt_no=1,
    )

    failure_result = handler.handle_with_retry(
        run_id="run_retry",
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args=_policy_tool_args(),
        first_result=first_result,
        tool_gateway=gateway,
        current_attempt_no=1,
    )
    logs = _tool_logs(db_path)

    assert failure_result.final_tool_result.success is True
    assert adapter.calls == 2
    assert [log["attempt_no"] for log in logs] == [1, 2]
    assert logs[0]["tool_call_id"] != logs[1]["tool_call_id"]
    assert logs[0]["idempotency_key"] == logs[1]["idempotency_key"]
    assert logs[0]["action_fingerprint"] == logs[1]["action_fingerprint"]


def _query_order_plan(order_id: str) -> ActionPlan:
    return ActionPlan(
        intent="order_query",
        action="query_order",
        target_type="order",
        target_id=order_id,
        tool_name="order_tool.query_order",
        tool_args={"order_id": order_id},
        reason="用户查询订单。",
    )


def _tool_args() -> dict:
    return {
        "user_id": "u_1001",
        "customer_user_id": "u_1001",
        "tenant_id": "t_001",
        "action": "query_order",
        "target_type": "order",
        "target_id": "O10086",
        "order_id": "O10086",
        "risk_level": "L2",
        "source_run_id": "run_ignored_for_fingerprint",
    }


def _policy_tool_args() -> dict:
    return {
        "user_id": "u_1001",
        "customer_user_id": "u_1001",
        "tenant_id": "t_001",
        "action": "query_policy",
        "target_type": "policy",
        "target_id": None,
        "query": "退款政策",
        "risk_level": "L1",
        "source_run_id": "run_ignored_for_fingerprint",
    }


def _tool_logs(db_path: Path) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT tool_call_id, idempotency_key, action_fingerprint,
                   tool_name, attempt_no, status
            FROM tool_call_logs
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    logs = [dict(row) for row in rows]
    json.dumps(logs, ensure_ascii=False)
    return logs
