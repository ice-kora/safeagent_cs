from pathlib import Path

from fastapi.testclient import TestClient

from app.api.confirm import (
    get_pending_action_service,
    get_policy_service,
    get_tool_gateway,
    get_trace_service,
)
from app.core.action_plan import ActionPlan
from app.main import app
from app.services.logging_service import LoggingService
from app.services.pending_action_service import PendingActionService
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService
from app.storage.db import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


class SpyPolicyService:
    def __init__(self, inner: PolicyService) -> None:
        self.inner = inner
        self.evaluate_calls = 0

    def evaluate(self, action_plan: ActionPlan, customer_user_id: str):
        self.evaluate_calls += 1
        return self.inner.evaluate(action_plan, customer_user_id)


class SpyToolGateway:
    def __init__(self, inner: ToolGateway) -> None:
        self.inner = inner
        self.calls = 0

    def call_tool(self, *args, **kwargs):
        self.calls += 1
        return self.inner.call_tool(*args, **kwargs)

    @property
    def db_path(self):
        return self.inner.db_path


def _change_address_plan(order_id: str = "O10086") -> ActionPlan:
    return ActionPlan(
        intent="address_change",
        action="change_address",
        target_type="order",
        target_id=order_id,
        tool_name="order_tool.change_address",
        tool_args={"order_id": order_id, "raw_message": f"订单 {order_id} 地址填错了"},
        reason="用户请求修改地址，需要二次确认。",
    )


def _query_order_plan(order_id: str) -> ActionPlan:
    return ActionPlan(
        intent="order_query",
        action="query_order",
        target_type="order",
        target_id=order_id,
        tool_name="order_tool.query_order",
        tool_args={"order_id": order_id},
        reason="测试确认流程恢复已保存 ActionPlan。",
    )


def _build_client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    pending_action_service = PendingActionService(db_path=db_path)
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    policy_service = SpyPolicyService(PolicyService(repository=repository))
    tool_gateway = SpyToolGateway(ToolGateway(db_path=db_path, mock_dir=MOCK_DIR))

    app.dependency_overrides[get_pending_action_service] = lambda: pending_action_service
    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_policy_service] = lambda: policy_service
    app.dependency_overrides[get_tool_gateway] = lambda: tool_gateway
    return (
        TestClient(app),
        pending_action_service,
        trace_service,
        policy_service,
        tool_gateway,
        db_path,
    )


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def _create_pending_action(
    pending_action_service: PendingActionService,
    action_plan: ActionPlan | None = None,
    user_id: str = "u_1001",
    session_id: str = "sess_001",
    ttl_minutes: int = 10,
) -> str:
    return pending_action_service.create_pending_action(
        session_id=session_id,
        source_run_id="run_original",
        user_id=user_id,
        action_plan=action_plan or _change_address_plan(),
        risk_level="L3",
        ttl_minutes=ttl_minutes,
    )


def _post_confirm(
    client: TestClient,
    pending_action_id: str,
    user_id: str = "u_1001",
    session_id: str = "sess_001",
    confirm: bool = True,
):
    return client.post(
        "/api/confirm",
        json={
            "pending_action_id": pending_action_id,
            "user_id": user_id,
            "session_id": session_id,
            "confirm": confirm,
        },
    )


def _count_rows(db_path: Path, table_name: str) -> int:
    with get_connection(db_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def _tool_logs(db_path: Path) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT tool_name, attempt_no, status
            FROM tool_call_logs
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _trace_node_names(trace_service: TraceService, run_id: str) -> list[str]:
    return [trace["node_name"] for trace in trace_service.get_traces(run_id)]


def _run_row(db_path: Path, run_id: str) -> dict[str, object]:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT run_id, parent_run_id, pending_action_id, status
            FROM agent_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    return dict(row)


def test_confirm_defaults_to_manual_when_workflow_mode_unset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("SAFEAGENT_WORKFLOW_MODE", raising=False)
    client, pending_action_service, trace_service, _, _, _ = _build_client(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)
        response = _post_confirm(client, pending_action_id, confirm=False)
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "CANCELLED"
        assert trace_service.get_traces(body["run_id"])[0]["node_name"] == "confirm_cancelled"
    finally:
        _clear_overrides()


def test_confirm_workflow_mode_uses_confirm_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, trace_service, _, _, _ = _build_client(tmp_path)
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            action_plan=_query_order_plan("O10086"),
        )
        response = _post_confirm(client, pending_action_id)
        body = response.json()
        trace_nodes = _trace_node_names(trace_service, body["run_id"])

        assert response.status_code == 200
        assert body["status"] == "EXECUTED"
        assert "confirm_workflow_start_node" in trace_nodes
        assert "load_pending_action_node" in trace_nodes
        assert "confirm_request_received" not in trace_nodes
    finally:
        _clear_overrides()


def test_confirm_workflow_does_not_use_intent_or_planner() -> None:
    workflow_source = (PROJECT_ROOT / "app" / "workflows" / "confirm_workflow.py").read_text(
        encoding="utf-8"
    )

    assert "app.services.intent_service" not in workflow_source
    assert "app.services.planner_service" not in workflow_source
    assert "RuleBasedIntentClassifier(" not in workflow_source
    assert "RuleBasedActionPlanner(" not in workflow_source


def test_confirm_workflow_restores_saved_action_plan_and_rechecks_policy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, _, policy_service, _, db_path = _build_client(tmp_path)
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            action_plan=_query_order_plan("O10086"),
        )
        response = _post_confirm(client, pending_action_id)
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "EXECUTED"
        assert body["tool_result"]["tool_name"] == "order_tool.query_order"
        assert policy_service.evaluate_calls == 1
        assert _tool_logs(db_path)[0]["tool_name"] == "order_tool.query_order"
    finally:
        _clear_overrides()


def test_confirm_workflow_policy_deny_skips_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, _, policy_service, tool_gateway, db_path = _build_client(
        tmp_path
    )
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            action_plan=_query_order_plan("O10087"),
        )
        response = _post_confirm(client, pending_action_id)
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "DENY"
        assert policy_service.evaluate_calls == 1
        assert tool_gateway.calls == 0
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_confirm_workflow_confirm_false_cancels_without_tool_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, _, policy_service, tool_gateway, db_path = _build_client(
        tmp_path
    )
    try:
        pending_action_id = _create_pending_action(pending_action_service)
        response = _post_confirm(client, pending_action_id, confirm=False)
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "CANCELLED"
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "CANCELLED"
        assert policy_service.evaluate_calls == 0
        assert tool_gateway.calls == 0
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_confirm_workflow_missing_pending_action_skips_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, _, _, _, tool_gateway, db_path = _build_client(tmp_path)
    try:
        response = _post_confirm(client, "pa_missing")

        assert response.status_code == 400
        assert "pending_action 不存在" in response.json()["detail"]
        assert tool_gateway.calls == 0
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_confirm_workflow_expired_pending_action_skips_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, _, _, tool_gateway, db_path = _build_client(tmp_path)
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            ttl_minutes=-1,
        )
        response = _post_confirm(client, pending_action_id)

        assert response.status_code == 400
        assert "已过期" in response.json()["detail"]
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "EXPIRED"
        assert tool_gateway.calls == 0
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_confirm_workflow_user_mismatch_skips_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, _, _, tool_gateway, db_path = _build_client(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)
        response = _post_confirm(client, pending_action_id, user_id="u_9999")

        assert response.status_code == 403
        assert "不属于当前用户" in response.json()["detail"]
        assert tool_gateway.calls == 0
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_confirm_workflow_session_mismatch_skips_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, _, _, tool_gateway, db_path = _build_client(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)
        response = _post_confirm(client, pending_action_id, session_id="sess_other")

        assert response.status_code == 403
        assert "session 不匹配" in response.json()["detail"]
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "PENDING"
        assert tool_gateway.calls == 0
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_confirm_workflow_confirm_required_recheck_does_not_create_new_pending_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, _, policy_service, tool_gateway, db_path = _build_client(
        tmp_path
    )
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            action_plan=_change_address_plan("O10086"),
        )
        response = _post_confirm(client, pending_action_id)
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "HUMAN_REQUIRED"
        assert body["policy_decision"]["decision"] == "CONFIRM_REQUIRED"
        assert policy_service.evaluate_calls == 1
        assert tool_gateway.calls == 0
        assert _count_rows(db_path, "pending_actions") == 1
        assert _count_rows(db_path, "tool_call_logs") == 0
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "CONFIRMED"
    finally:
        _clear_overrides()


def test_confirm_workflow_writes_trace_for_success_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, pending_action_service, trace_service, _, _, db_path = _build_client(tmp_path)
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            action_plan=_query_order_plan("O10086"),
        )
        response = _post_confirm(client, pending_action_id)
        body = response.json()
        trace_nodes = _trace_node_names(trace_service, body["run_id"])
        run = _run_row(db_path, body["run_id"])

        assert {
            "confirm_workflow_start_node",
            "load_pending_action_node",
            "validate_pending_action_node",
            "restore_action_plan_node",
            "policy_recheck_node",
            "route_after_policy_recheck_node",
            "confirm_tool_gateway_node",
            "confirm_failure_handler_node",
            "confirm_response_generation_node",
            "confirm_finish_node",
        }.issubset(set(trace_nodes))
        assert run["parent_run_id"] == "run_original"
        assert run["pending_action_id"] == pending_action_id
        assert run["status"] == "SUCCESS"
    finally:
        _clear_overrides()
