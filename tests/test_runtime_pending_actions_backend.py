from pathlib import Path

from app.core.action_plan import ActionPlan
from app.services.pending_action_event_service import PendingActionEventService
from app.services.pending_action_service import PendingActionService


def test_pending_action_service_uses_runtime_store(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "runtime.db")

    pending_action_id = service.create_pending_action(
        session_id="sess_001",
        source_run_id="run_001",
        user_id="u_1001",
        action_plan=_change_address_plan(),
        risk_level="L3",
    )
    service.mark_confirmed(pending_action_id, run_id="run_002")
    service.mark_executed(pending_action_id, run_id="run_002")

    record = service.get_pending_action(pending_action_id)
    events = PendingActionEventService(db_path=tmp_path / "runtime.db").list_events(
        pending_action_id
    )

    assert record["status"] == "EXECUTED"
    assert [event.event_type for event in events] == [
        "CREATED",
        "CONFIRMED",
        "EXECUTED",
    ]


def test_pending_action_cancel_and_expire_statuses(tmp_path: Path) -> None:
    service = PendingActionService(db_path=tmp_path / "runtime.db")
    first = service.create_pending_action(
        session_id="sess_001",
        source_run_id="run_001",
        user_id="u_1001",
        action_plan=_change_address_plan(),
        risk_level="L3",
    )
    second = service.create_pending_action(
        session_id="sess_001",
        source_run_id="run_001",
        user_id="u_1001",
        action_plan=_change_address_plan(),
        risk_level="L3",
    )

    service.mark_cancelled(first)
    service.mark_expired(second)

    assert service.get_pending_action(first)["status"] == "CANCELLED"
    assert service.get_pending_action(second)["status"] == "EXPIRED"


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
