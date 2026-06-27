import os

import pytest
from fastapi.testclient import TestClient

from app.core.action_plan import ActionPlan
from app.main import app
from app.services.pending_action_service import PendingActionService
from app.storage.runtime_config import RUNTIME_BACKEND_POSTGRES
from app.storage.runtime_store import get_runtime_store


def test_chat_api_protocol_shape_is_unchanged() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "session_id": "sess_runtime_boundary",
            "user_id": "u_1001",
            "message": "你们支持七天无理由退货吗？",
        },
    )
    body = response.json()

    assert response.status_code == 200
    for field in (
        "request_id",
        "run_id",
        "status",
        "intent",
        "action",
        "policy_decision",
        "tool_result",
        "pending_action_id",
        "message",
    ):
        assert field in body


def test_confirm_api_protocol_shape_is_unchanged(tmp_path) -> None:
    service = PendingActionService(db_path=tmp_path / "runtime.db")
    pending_action_id = service.create_pending_action(
        session_id="sess_runtime_boundary",
        source_run_id="run_source",
        user_id="u_1001",
        action_plan=_change_address_plan(),
        risk_level="L3",
    )
    client = TestClient(app)
    app.dependency_overrides.clear()

    from app.api.confirm import get_pending_action_service

    app.dependency_overrides[get_pending_action_service] = lambda: service
    try:
        response = client.post(
            "/api/confirm",
            json={
                "pending_action_id": pending_action_id,
                "user_id": "u_1001",
                "session_id": "sess_runtime_boundary",
                "confirm": False,
            },
        )
    finally:
        app.dependency_overrides.clear()
    body = response.json()

    assert response.status_code == 200
    for field in (
        "request_id",
        "run_id",
        "pending_action_id",
        "status",
        "message",
    ):
        assert field in body


def test_runtime_postgres_chat_and_confirm_smoke(monkeypatch) -> None:
    database_url = os.getenv("SAFEAGENT_RUNTIME_DATABASE_URL") or os.getenv(
        "DATABASE_URL"
    )
    if not database_url:
        pytest.skip("runtime PostgreSQL URL is not configured")
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", RUNTIME_BACKEND_POSTGRES)
    try:
        get_runtime_store(backend=RUNTIME_BACKEND_POSTGRES, database_url=database_url)
    except RuntimeError as exc:
        pytest.skip(str(exc))

    client = TestClient(app)
    chat_response = client.post(
        "/api/chat",
        json={
            "session_id": "sess_pg_runtime",
            "user_id": "u_1001",
            "message": "订单 O10086 的地址填错了，帮我改一下",
        },
    )
    chat_body = chat_response.json()
    assert chat_response.status_code == 200
    assert chat_body["status"] == "CONFIRM_REQUIRED"

    confirm_response = client.post(
        "/api/confirm",
        json={
            "pending_action_id": chat_body["pending_action_id"],
            "user_id": "u_1001",
            "session_id": "sess_pg_runtime",
            "confirm": False,
        },
    )
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "CANCELLED"


def _change_address_plan() -> ActionPlan:
    return ActionPlan(
        intent="address_change",
        action="change_address",
        target_type="order",
        target_id="O10086",
        tool_name="order_tool.change_address",
        tool_args={"order_id": "O10086"},
        reason="test",
    )
