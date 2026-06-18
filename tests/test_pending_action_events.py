import json
from pathlib import Path

import pytest
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
from app.services.pending_action_event_service import PendingActionEventService
from app.services.pending_action_service import PendingActionService
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_create_pending_action_records_created_event(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")

    pending_action_id = _create_pending_action(service)
    events = service.event_service.list_events(pending_action_id)

    assert [event.event_type for event in events] == ["CREATED"]
    assert events[0].old_status is None
    assert events[0].new_status == "PENDING"
    assert events[0].session_id == "sess_001"
    assert events[0].user_id == "u_1001"


def test_confirm_true_records_confirmed_and_executed_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, pending_action_service = _client_with_services(tmp_path, monkeypatch)
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
    events = pending_action_service.event_service.list_events(pending_action_id)

    assert response.status_code == 200
    assert response.json()["status"] == "EXECUTED"
    assert [event.event_type for event in events] == ["CREATED", "CONFIRMED", "EXECUTED"]
    assert [event.new_status for event in events] == ["PENDING", "CONFIRMED", "EXECUTED"]


def test_confirm_false_records_cancelled_event(tmp_path: Path, monkeypatch) -> None:
    client, pending_action_service = _client_with_services(tmp_path, monkeypatch)
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
    events = pending_action_service.event_service.list_events(pending_action_id)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert [event.event_type for event in events] == ["CREATED", "CANCELLED"]
    assert events[-1].old_status == "PENDING"
    assert events[-1].new_status == "CANCELLED"


def test_expired_pending_action_records_expired_event(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")
    pending_action_id = _create_pending_action(service, ttl_minutes=-1)

    try:
        service.validate_pending_action(
            pending_action_id=pending_action_id,
            user_id="u_1001",
        )
    except Exception:
        pass
    events = service.event_service.list_events(pending_action_id)

    assert [event.event_type for event in events] == ["CREATED", "EXPIRED"]
    assert events[-1].old_status == "PENDING"
    assert events[-1].new_status == "EXPIRED"


def test_list_events_returns_created_time_order(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")
    pending_action_id = _create_pending_action(service)

    service.mark_confirmed(pending_action_id)
    service.mark_executed(pending_action_id)
    events = service.event_service.list_events(pending_action_id)

    assert [event.event_type for event in events] == ["CREATED", "CONFIRMED", "EXECUTED"]
    assert [event.created_at for event in events] == sorted(
        event.created_at for event in events
    )


def test_event_metadata_is_json_safe_and_sanitized(tmp_path: Path) -> None:
    event_service = PendingActionEventService(db_path=tmp_path / "test.db")

    event_service.record_event(
        pending_action_id="pa_sensitive",
        event_type="CREATED",
        metadata={
            "phone": "13812345678",
            "token": "secret-token",
            "secret": "secret-value",
            "nested": {"api_key": "key_secret"},
        },
    )
    event = event_service.list_events("pa_sensitive")[0]
    event_json = json.dumps(event.metadata, ensure_ascii=False)

    assert "13812345678" not in event_json
    assert "secret-token" not in event_json
    assert "secret-value" not in event_json
    assert "key_secret" not in event_json
    assert event.metadata["phone"] == "***"


def test_session_mismatch_does_not_create_status_change_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, pending_action_service = _client_with_services(tmp_path, monkeypatch)
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
    events = pending_action_service.event_service.list_events(pending_action_id)

    assert response.status_code == 403
    assert [event.event_type for event in events] == ["CREATED"]
    assert pending_action_service.get_pending_action(pending_action_id)["status"] == "PENDING"


def test_pending_action_id_can_query_full_event_history(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")
    first_id = _create_pending_action(service)
    second_id = _create_pending_action(service)

    service.mark_cancelled(first_id)
    first_events = service.event_service.list_events(first_id)
    second_events = service.event_service.list_events(second_id)

    assert [event.event_type for event in first_events] == ["CREATED", "CANCELLED"]
    assert [event.event_type for event in second_events] == ["CREATED"]


def _client_with_services(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "test.db"
    pending_action_service = PendingActionService(db_path=db_path)
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    policy_service = PolicyService(repository=repository)
    tool_gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)
    monkeypatch.delenv("SAFEAGENT_WORKFLOW_MODE", raising=False)

    app.dependency_overrides[get_pending_action_service] = lambda: pending_action_service
    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_policy_service] = lambda: policy_service
    app.dependency_overrides[get_tool_gateway] = lambda: tool_gateway

    client = TestClient(app)
    return client, pending_action_service


def _create_pending_action(
    service: PendingActionService,
    ttl_minutes: int = 10,
) -> str:
    return service.create_pending_action(
        session_id="sess_001",
        source_run_id="run_original",
        user_id="u_1001",
        action_plan=_change_address_plan(),
        risk_level="L3",
        ttl_minutes=ttl_minutes,
    )


def _change_address_plan() -> ActionPlan:
    return ActionPlan(
        intent="address_change",
        action="change_address",
        target_type="order",
        target_id="O10086",
        tool_name="order_tool.change_address",
        tool_args={
            "order_id": "O10086",
            "raw_message": "订单 O10086 地址填错了，手机号 13812345678",
        },
        reason="用户请求修改地址，需要二次确认。",
    )
