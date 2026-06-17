from copy import deepcopy

from app.workflows.tool_resume_policy import (
    ToolResumeRisk,
    can_resume_tool_boundary,
)


def test_tool_resume_rejects_missing_action_plan() -> None:
    snapshot = _without("action_plan")

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == ToolResumeRisk.INSUFFICIENT_METADATA
    assert "action_plan" in decision.reason


def test_tool_resume_rejects_non_allow_policy() -> None:
    snapshot = _base_snapshot()
    snapshot["policy_decision"]["decision"] = "DENY"

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == ToolResumeRisk.UNSAFE_DUPLICATE_RISK
    assert "ALLOW" in decision.reason


def test_tool_resume_rejects_missing_tool_result() -> None:
    snapshot = _without("tool_result")

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == ToolResumeRisk.INSUFFICIENT_METADATA
    assert "tool_result" in decision.reason


def test_tool_resume_allows_success_result_with_tool_call_id() -> None:
    snapshot = _base_snapshot()
    snapshot["tool_result"]["tool_call_id"] = "tc_001"

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is True
    assert decision.risk == ToolResumeRisk.SAFE_TO_SKIP
    assert "跳过" in decision.reason


def test_tool_resume_allows_success_result_with_idempotency_key() -> None:
    snapshot = _base_snapshot()
    snapshot["idempotency_key"] = "u_1001:query_order:order:O10086"

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is True
    assert decision.risk == ToolResumeRisk.SAFE_TO_SKIP


def test_tool_resume_rejects_success_result_without_idempotency_metadata() -> None:
    snapshot = _base_snapshot()

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == ToolResumeRisk.INSUFFICIENT_METADATA
    assert "tool_call_id/idempotency_key" in decision.reason


def test_tool_resume_rejects_failed_tool_result_without_failure_result() -> None:
    snapshot = _base_snapshot()
    snapshot["tool_result"]["success"] = False

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == ToolResumeRisk.RETRY_REQUIRED
    assert "failure_result" in decision.reason


def test_tool_resume_rejects_failure_result_without_attempt_metadata() -> None:
    snapshot = _base_snapshot()
    snapshot["tool_result"]["success"] = False
    snapshot["failure_result"] = {"status": "FAILED"}
    snapshot["tool_call_id"] = "tc_001"

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == ToolResumeRisk.INSUFFICIENT_METADATA
    assert "attempt_no/retryable" in decision.reason


def test_tool_resume_rejects_failed_result_without_idempotency_metadata() -> None:
    snapshot = _base_snapshot()
    snapshot["tool_result"]["success"] = False
    snapshot["failure_result"] = {
        "status": "FAILED",
        "attempt_no": 1,
        "retryable": True,
    }

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is False
    assert decision.risk == ToolResumeRisk.INSUFFICIENT_METADATA
    assert "tool_call_id/idempotency_key" in decision.reason


def test_tool_resume_allows_failed_result_with_retry_metadata() -> None:
    snapshot = _base_snapshot()
    snapshot["tool_result"]["success"] = False
    snapshot["tool_call_id"] = "tc_001"
    snapshot["failure_result"] = {
        "status": "FAILED",
        "attempt_no": 1,
        "retryable": True,
    }

    decision = can_resume_tool_boundary(snapshot)

    assert decision.allowed is True
    assert decision.risk == ToolResumeRisk.RETRY_REQUIRED


def _base_snapshot() -> dict:
    return {
        "action_plan": {
            "action": "query_order",
            "target_type": "order",
            "target_id": "O10086",
            "tool_name": "order_tool.query_order",
        },
        "policy_decision": {
            "decision": "ALLOW",
            "risk_level": "L2",
            "reason": "unit test",
        },
        "tool_result": {
            "success": True,
            "tool_name": "order_tool.query_order",
            "summary": "已查询订单。",
        },
    }


def _without(*keys: str) -> dict:
    snapshot = deepcopy(_base_snapshot())
    for key in keys:
        snapshot.pop(key, None)
    return snapshot
