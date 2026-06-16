import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.action_plan import ActionPlan
from app.services.pending_action_service import (
    PendingActionError,
    PendingActionPermissionError,
    PendingActionService,
)
from app.storage.db import get_connection


def _action_plan() -> ActionPlan:
    return ActionPlan(
        intent="address_change",
        action="change_address",
        target_type="order",
        target_id="O10086",
        tool_name="order_tool.change_address",
        tool_args={"order_id": "O10086", "raw_message": "订单 O10086 地址填错了"},
        reason="用户请求修改地址，需要二次确认。",
    )


def _create_pending_action(
    service: PendingActionService,
    ttl_minutes: int = 10,
) -> str:
    return service.create_pending_action(
        session_id="sess_001",
        source_run_id="run_001",
        user_id="u_1001",
        action_plan=_action_plan(),
        risk_level="L3",
        ttl_minutes=ttl_minutes,
    )


def _status(db_path: Path, pending_action_id: str) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM pending_actions WHERE pending_action_id = ?",
            (pending_action_id,),
        ).fetchone()
    return row["status"]


def test_create_pending_action_success(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    service = PendingActionService(db_path=db_path)

    pending_action_id = _create_pending_action(service)
    record = service.get_pending_action(pending_action_id)

    assert pending_action_id.startswith("pa_")
    assert record is not None
    assert record["session_id"] == "sess_001"
    assert record["source_run_id"] == "run_001"
    assert record["user_id"] == "u_1001"
    assert record["risk_level"] == "L3"
    assert record["status"] == PendingActionService.STATUS_PENDING


def test_action_plan_json_can_be_deserialized(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")
    pending_action_id = _create_pending_action(service)

    record = service.get_pending_action(pending_action_id)
    action_plan_dict = json.loads(record["action_plan_json"])
    validated = service.validate_pending_action(
        pending_action_id=pending_action_id,
        user_id="u_1001",
    )

    assert action_plan_dict["action"] == "change_address"
    assert validated["action_plan"] == _action_plan()
    assert validated["source_run_id"] == "run_001"


def test_create_pending_action_default_expires_in_ten_minutes(
    tmp_path: Path,
) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")
    before = datetime.now(timezone.utc)

    pending_action_id = _create_pending_action(service)
    record = service.get_pending_action(pending_action_id)

    expires_at = datetime.fromisoformat(record["expires_at"])
    expected_expires_at = before + timedelta(minutes=10)
    assert expected_expires_at - timedelta(seconds=2) <= expires_at
    assert expires_at <= expected_expires_at + timedelta(seconds=2)


def test_validate_pending_action_rejects_user_mismatch(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")
    pending_action_id = _create_pending_action(service)

    with pytest.raises(PendingActionPermissionError, match="不属于当前用户"):
        service.validate_pending_action(
            pending_action_id=pending_action_id,
            user_id="u_9999",
        )


def test_validate_pending_action_rejects_missing_record(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")

    with pytest.raises(PendingActionError, match="pending_action 不存在"):
        service.validate_pending_action(
            pending_action_id="pa_missing",
            user_id="u_1001",
        )


def test_validate_expired_pending_action_marks_expired(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    service = PendingActionService(db_path=db_path)
    pending_action_id = _create_pending_action(service, ttl_minutes=-1)

    with pytest.raises(PendingActionError, match="已过期"):
        service.validate_pending_action(
            pending_action_id=pending_action_id,
            user_id="u_1001",
        )

    assert _status(db_path, pending_action_id) == PendingActionService.STATUS_EXPIRED


def test_validate_rejects_non_pending_status(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "test.db")
    pending_action_id = _create_pending_action(service)
    service.mark_confirmed(pending_action_id)

    with pytest.raises(PendingActionError, match="状态不是 PENDING"):
        service.validate_pending_action(
            pending_action_id=pending_action_id,
            user_id="u_1001",
        )


def test_mark_confirmed_updates_status(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    service = PendingActionService(db_path=db_path)
    pending_action_id = _create_pending_action(service)

    service.mark_confirmed(pending_action_id)

    assert _status(db_path, pending_action_id) == PendingActionService.STATUS_CONFIRMED


def test_mark_executed_updates_status(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    service = PendingActionService(db_path=db_path)
    pending_action_id = _create_pending_action(service)

    service.mark_executed(pending_action_id)

    assert _status(db_path, pending_action_id) == PendingActionService.STATUS_EXECUTED


def test_mark_cancelled_updates_status(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    service = PendingActionService(db_path=db_path)
    pending_action_id = _create_pending_action(service)

    service.mark_cancelled(pending_action_id)

    assert _status(db_path, pending_action_id) == PendingActionService.STATUS_CANCELLED
