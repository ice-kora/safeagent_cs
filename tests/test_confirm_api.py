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
        reason="用户查询订单，需要复核归属。",
    )


def _client_with_services(tmp_path: Path):
    db_path = tmp_path / "test.db"
    pending_action_service = PendingActionService(db_path=db_path)
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    policy_service = PolicyService(repository=repository)
    tool_gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    app.dependency_overrides[get_pending_action_service] = lambda: pending_action_service
    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_policy_service] = lambda: policy_service
    app.dependency_overrides[get_tool_gateway] = lambda: tool_gateway
    return TestClient(app), pending_action_service, trace_service, db_path


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def _create_pending_action(
    pending_action_service: PendingActionService,
    action_plan: ActionPlan | None = None,
    user_id: str = "u_1001",
    ttl_minutes: int = 10,
) -> str:
    return pending_action_service.create_pending_action(
        session_id="sess_001",
        source_run_id="run_original",
        user_id=user_id,
        action_plan=action_plan or _change_address_plan(),
        risk_level="L3",
        ttl_minutes=ttl_minutes,
    )


def _run_row(db_path: Path, run_id: str) -> dict[str, object]:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT run_id, request_id, parent_run_id, pending_action_id, status
            FROM agent_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    return dict(row)


def _tool_call_count(db_path: Path) -> int:
    with get_connection(db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM tool_call_logs").fetchone()[0]


def test_confirm_false_cancels_pending_action(tmp_path: Path) -> None:
    client, pending_action_service, trace_service, db_path = _client_with_services(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)

        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_1001",
                "session_id": "sess_001",
                "confirm": False,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "CANCELLED"
        assert body["run_id"].startswith("run_")
        assert body["parent_run_id"] == "run_original"
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "CANCELLED"
        assert trace_service.get_traces(body["run_id"])[0]["node_name"] == "confirm_cancelled"
        assert _run_row(db_path, body["run_id"])["status"] == "SUCCESS"
    finally:
        _clear_overrides()


def test_confirm_true_creates_new_run_with_parent_run_id(tmp_path: Path) -> None:
    client, pending_action_service, _, db_path = _client_with_services(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)

        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_1001",
                "session_id": "sess_001",
                "confirm": True,
            },
        )

        assert response.status_code == 200
        body = response.json()
        run = _run_row(db_path, body["run_id"])
        assert body["request_id"].startswith("req_")
        assert body["run_id"].startswith("run_")
        assert body["parent_run_id"] == "run_original"
        assert run["parent_run_id"] == "run_original"
        assert run["pending_action_id"] == pending_action_id
    finally:
        _clear_overrides()


def test_confirm_rejects_pending_action_owned_by_other_user(tmp_path: Path) -> None:
    client, pending_action_service, _, _ = _client_with_services(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)

        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_9999",
                "session_id": "sess_001",
                "confirm": True,
            },
        )

        assert response.status_code == 403
        assert "不属于当前用户" in response.json()["detail"]
    finally:
        _clear_overrides()


def test_confirm_rejects_session_mismatch_without_tool_call(
    tmp_path: Path,
) -> None:
    client, pending_action_service, _, db_path = _client_with_services(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)

        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_1001",
                "session_id": "sess_other",
                "confirm": True,
            },
        )

        assert response.status_code == 403
        assert "session 不匹配" in response.json()["detail"]
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "PENDING"
        assert _tool_call_count(db_path) == 0
    finally:
        _clear_overrides()


def test_confirm_rejects_expired_pending_action(tmp_path: Path) -> None:
    client, pending_action_service, _, _ = _client_with_services(tmp_path)
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            ttl_minutes=-1,
        )

        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_1001",
                "session_id": "sess_001",
                "confirm": True,
            },
        )

        assert response.status_code == 400
        assert "已过期" in response.json()["detail"]
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "EXPIRED"
    finally:
        _clear_overrides()


def test_confirm_policy_denied_does_not_call_tool_gateway(tmp_path: Path) -> None:
    client, pending_action_service, trace_service, db_path = _client_with_services(tmp_path)
    try:
        pending_action_id = _create_pending_action(
            pending_action_service,
            action_plan=_query_order_plan("O10087"),
        )

        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_1001",
                "session_id": "sess_001",
                "confirm": True,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "DENY"
        assert _tool_call_count(db_path) == 0
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "CONFIRMED"
        assert [trace["node_name"] for trace in trace_service.get_traces(body["run_id"])] == [
            "confirm_request_received",
            "policy_review_result",
        ]
    finally:
        _clear_overrides()


def test_confirm_success_calls_tool_gateway_and_marks_executed(
    tmp_path: Path,
) -> None:
    client, pending_action_service, trace_service, db_path = _client_with_services(tmp_path)
    try:
        pending_action_id = _create_pending_action(pending_action_service)

        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_1001",
                "session_id": "sess_001",
                "confirm": True,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "EXECUTED"
        assert body["tool_result"]["success"] is True
        assert pending_action_service.get_pending_action(pending_action_id)["status"] == "EXECUTED"
        assert _tool_call_count(db_path) == 1
        assert [trace["node_name"] for trace in trace_service.get_traces(body["run_id"])] == [
            "confirm_request_received",
            "policy_review_result",
            "tool_gateway_result",
        ]
    finally:
        _clear_overrides()
