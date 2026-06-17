from copy import deepcopy

from app.workflows.checkpoint_policy import (
    CheckpointNodeRisk,
    can_resume_from_snapshot,
    classify_checkpoint_node,
)
from app.workflows.langgraph_state_schema import CHECKPOINT_SNAPSHOT_SCHEMA_VERSION


def _base_snapshot() -> dict:
    return {
        "schema_version": CHECKPOINT_SNAPSHOT_SCHEMA_VERSION,
        "request_id": "req_test",
        "run_id": "run_test",
        "session_id": "sess_001",
        "user_id": "u_1001",
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
        "final_status": "SUCCESS",
        "final_response": "请求已处理完成。",
        "tool_result": {
            "success": True,
            "tool_name": "order_tool.query_order",
        },
        "failure_result": {
            "status": "NO_FAILURE",
            "retryable": False,
        },
    }


def test_safe_node_classification() -> None:
    assert classify_checkpoint_node("workflow_start_node") == CheckpointNodeRisk.SAFE
    assert classify_checkpoint_node("policy_node") == CheckpointNodeRisk.SAFE
    assert classify_checkpoint_node("route_by_policy_node") == CheckpointNodeRisk.SAFE
    assert classify_checkpoint_node("response_generation_node") == CheckpointNodeRisk.SAFE


def test_terminal_node_classification() -> None:
    assert classify_checkpoint_node("finish_node") == CheckpointNodeRisk.TERMINAL


def test_side_effect_node_classification() -> None:
    assert classify_checkpoint_node("tool_gateway_node") == CheckpointNodeRisk.SIDE_EFFECT
    assert classify_checkpoint_node("pending_action_node") == CheckpointNodeRisk.SIDE_EFFECT
    assert classify_checkpoint_node("failure_handler_node") == CheckpointNodeRisk.SIDE_EFFECT


def test_unknown_node_classification() -> None:
    assert (
        classify_checkpoint_node("unknown_node")
        == CheckpointNodeRisk.UNSAFE_TO_RESUME
    )


def test_policy_node_requires_action_plan() -> None:
    allowed = can_resume_from_snapshot(_base_snapshot(), "policy_node")
    missing = _without("action_plan")
    denied = can_resume_from_snapshot(missing, "policy_node")

    assert allowed.allowed is True
    assert denied.allowed is False
    assert "action_plan" in denied.reason


def test_tool_gateway_precondition_passes_but_direct_resume_is_denied() -> None:
    decision = can_resume_from_snapshot(_base_snapshot(), "tool_gateway_node")

    assert decision.allowed is False
    assert decision.risk == CheckpointNodeRisk.SIDE_EFFECT
    assert "副作用节点" in decision.reason


def test_tool_gateway_rejects_missing_or_non_allow_policy() -> None:
    missing_action_plan = _without("action_plan")
    denied_policy = _with_policy_decision("DENY")

    assert can_resume_from_snapshot(
        missing_action_plan,
        "tool_gateway_node",
    ).allowed is False
    denied = can_resume_from_snapshot(denied_policy, "tool_gateway_node")
    assert denied.allowed is False
    assert "ALLOW" in denied.reason


def test_deny_node_requires_deny_policy_decision() -> None:
    allowed = can_resume_from_snapshot(_with_policy_decision("DENY"), "deny_node")
    denied = can_resume_from_snapshot(_with_policy_decision("ALLOW"), "deny_node")

    assert allowed.allowed is True
    assert denied.allowed is False
    assert "DENY" in denied.reason


def test_pending_action_precondition_passes_but_direct_resume_is_denied() -> None:
    snapshot = _with_policy_decision("CONFIRM_REQUIRED")

    decision = can_resume_from_snapshot(snapshot, "pending_action_node")

    assert decision.allowed is False
    assert decision.risk == CheckpointNodeRisk.SIDE_EFFECT
    assert "副作用节点" in decision.reason


def test_human_required_node_requires_human_required_decision() -> None:
    allowed = can_resume_from_snapshot(
        _with_policy_decision("HUMAN_REQUIRED"),
        "human_required_node",
    )
    denied = can_resume_from_snapshot(_with_policy_decision("DENY"), "human_required_node")

    assert allowed.allowed is True
    assert denied.allowed is False
    assert "HUMAN_REQUIRED" in denied.reason


def test_finish_node_requires_final_status() -> None:
    allowed = can_resume_from_snapshot(_base_snapshot(), "finish_node")
    missing = _without("final_status")
    denied = can_resume_from_snapshot(missing, "finish_node")

    assert allowed.allowed is True
    assert allowed.risk == CheckpointNodeRisk.TERMINAL
    assert denied.allowed is False
    assert "final_status" in denied.reason


def test_response_generation_requires_status_or_decision_context() -> None:
    allowed = can_resume_from_snapshot(_base_snapshot(), "response_generation_node")
    missing = _without("final_status", "policy_decision", "validation_result")
    denied = can_resume_from_snapshot(missing, "response_generation_node")

    assert allowed.allowed is True
    assert denied.allowed is False
    assert "response_generation_node" in denied.reason


def test_missing_schema_version_rejects_resume() -> None:
    snapshot = _without("schema_version")

    decision = can_resume_from_snapshot(snapshot, "policy_node")

    assert decision.allowed is False
    assert "schema_version" in decision.reason


def test_unsupported_schema_version_rejects_resume() -> None:
    snapshot = _base_snapshot()
    snapshot["schema_version"] = "checkpoint.snapshot.v0"

    decision = can_resume_from_snapshot(snapshot, "policy_node")

    assert decision.allowed is False
    assert "不支持" in decision.reason


def test_unknown_node_rejects_resume() -> None:
    decision = can_resume_from_snapshot(_base_snapshot(), "unknown_node")

    assert decision.allowed is False
    assert decision.risk == CheckpointNodeRisk.UNSAFE_TO_RESUME


def test_failure_handler_direct_resume_is_denied_without_attempt_metadata() -> None:
    decision = can_resume_from_snapshot(_base_snapshot(), "failure_handler_node")

    assert decision.allowed is False
    assert decision.risk == CheckpointNodeRisk.SIDE_EFFECT
    assert "副作用节点" in decision.reason


def _without(*keys: str) -> dict:
    snapshot = deepcopy(_base_snapshot())
    for key in keys:
        snapshot.pop(key, None)
    return snapshot


def _with_policy_decision(decision: str) -> dict:
    snapshot = deepcopy(_base_snapshot())
    snapshot["policy_decision"] = {
        "decision": decision,
        "risk_level": "L3",
        "reason": "unit test",
    }
    return snapshot
