from copy import deepcopy

from app.workflows.pending_resume_policy import (
    PendingResumeRisk,
    can_resume_pending_boundary,
)


def test_pending_resume_rejects_non_confirm_required_policy() -> None:
    snapshot = _base_snapshot()
    snapshot["policy_decision"]["decision"] = "ALLOW"

    decision = can_resume_pending_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == PendingResumeRisk.UNSUPPORTED_STATUS
    assert "CONFIRM_REQUIRED" in decision.reason


def test_pending_resume_rejects_missing_action_plan() -> None:
    snapshot = _without("action_plan")

    decision = can_resume_pending_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == PendingResumeRisk.DUPLICATE_CREATE_RISK
    assert "action_plan" in decision.reason


def test_pending_resume_rejects_missing_pending_action_id() -> None:
    snapshot = _without("pending_action_id")

    decision = can_resume_pending_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == PendingResumeRisk.MISSING_PENDING_ACTION_ID
    assert "pending_action_id" in decision.reason


def test_pending_resume_allows_existing_pending_action_id() -> None:
    decision = can_resume_pending_boundary(_base_snapshot())

    assert decision.allowed is True
    assert decision.risk == PendingResumeRisk.READY_FOR_CONFIRM_WAIT
    assert "等待用户确认" in decision.reason


def test_pending_resume_uses_snapshot_only_without_database_access() -> None:
    snapshot = _base_snapshot()
    snapshot["pending_action_id"] = "pa_not_in_database"

    decision = can_resume_pending_boundary(snapshot)

    assert decision.allowed is True
    assert decision.risk == PendingResumeRisk.READY_FOR_CONFIRM_WAIT


def _base_snapshot() -> dict:
    return {
        "action_plan": {
            "action": "change_address",
            "target_type": "order",
            "target_id": "O10086",
            "tool_name": "order_tool.change_address",
        },
        "policy_decision": {
            "decision": "CONFIRM_REQUIRED",
            "risk_level": "L3",
            "reason": "unit test",
        },
        "pending_action_id": "pa_001",
    }


def _without(*keys: str) -> dict:
    snapshot = deepcopy(_base_snapshot())
    for key in keys:
        snapshot.pop(key, None)
    return snapshot
