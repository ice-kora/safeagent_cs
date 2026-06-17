from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.workflows.langgraph_state_schema import CHECKPOINT_SNAPSHOT_SCHEMA_VERSION


class CheckpointNodeRisk(str, Enum):
    SAFE = "SAFE"
    SIDE_EFFECT = "SIDE_EFFECT"
    TERMINAL = "TERMINAL"
    UNSAFE_TO_RESUME = "UNSAFE_TO_RESUME"


@dataclass(frozen=True)
class CheckpointResumeDecision:
    """从 checkpoint 恢复到某个节点前的协议判断结果。"""

    allowed: bool
    reason: str
    node_name: str
    risk: CheckpointNodeRisk


@dataclass(frozen=True)
class CheckpointResumeMatrixEntry:
    """单个节点的 checkpoint/resume 能力矩阵条目。"""

    node_name: str
    risk: CheckpointNodeRisk
    checkpoint_allowed: bool
    dry_run_allowed: bool
    real_resume_allowed_now: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_name": self.node_name,
            "risk": self.risk.value,
            "checkpoint_allowed": self.checkpoint_allowed,
            "dry_run_allowed": self.dry_run_allowed,
            "real_resume_allowed_now": self.real_resume_allowed_now,
            "reason": self.reason,
        }


SAFE_NODES = {
    "workflow_start_node",
    "intent_node",
    "planner_node",
    "llm_output_guard_node",
    "action_plan_validator_node",
    "policy_node",
    "route_by_policy_node",
    "human_required_node",
    "deny_node",
    "response_generation_node",
    "llm_response_guard_node",
}

SIDE_EFFECT_NODES = {
    "tool_gateway_node",
    "pending_action_node",
    "failure_handler_node",
}

TERMINAL_NODES = {
    "finish_node",
}

CHECKPOINT_MATRIX_NODES = (
    "workflow_start_node",
    "intent_node",
    "planner_node",
    "llm_output_guard_node",
    "action_plan_validator_node",
    "policy_node",
    "route_by_policy_node",
    "tool_gateway_node",
    "pending_action_node",
    "human_required_node",
    "deny_node",
    "failure_handler_node",
    "response_generation_node",
    "llm_response_guard_node",
    "finish_node",
    "unknown_node",
)


def classify_checkpoint_node(node_name: str) -> CheckpointNodeRisk:
    """按恢复风险给 LangGraph 节点分类。"""
    if node_name in SAFE_NODES:
        return CheckpointNodeRisk.SAFE
    if node_name in SIDE_EFFECT_NODES:
        return CheckpointNodeRisk.SIDE_EFFECT
    if node_name in TERMINAL_NODES:
        return CheckpointNodeRisk.TERMINAL
    return CheckpointNodeRisk.UNSAFE_TO_RESUME


def can_resume_from_snapshot(
    snapshot: dict[str, Any],
    next_node: str,
) -> CheckpointResumeDecision:
    """判断是否允许从 snapshot 恢复到 next_node。

    本函数只做协议校验，不执行恢复、不调用工具、不修改数据库。
    副作用节点当前默认禁止直接 resume，避免重复工具调用或重复创建
    pending_action。
    """
    risk = classify_checkpoint_node(next_node)
    if risk == CheckpointNodeRisk.UNSAFE_TO_RESUME:
        return _deny(next_node, risk, "未知节点不允许恢复")

    schema_result = _validate_schema_version(snapshot)
    if schema_result:
        return _deny(next_node, risk, schema_result)

    if risk == CheckpointNodeRisk.SIDE_EFFECT:
        precondition_failure = _side_effect_precondition_failure(snapshot, next_node)
        if precondition_failure:
            return _deny(next_node, risk, precondition_failure)
        return _deny(next_node, risk, "副作用节点默认不允许直接恢复执行")

    failure = _safe_node_precondition_failure(snapshot, next_node)
    if failure:
        return _deny(next_node, risk, failure)
    return CheckpointResumeDecision(
        allowed=True,
        reason="允许恢复",
        node_name=next_node,
        risk=risk,
    )


def build_checkpoint_resume_matrix() -> list[CheckpointResumeMatrixEntry]:
    """生成当前 checkpoint/resume readiness 矩阵。

    当前阶段不启用真实 resume，所以 real_resume_allowed_now 全部为 False。
    """
    return [_build_matrix_entry(node_name) for node_name in CHECKPOINT_MATRIX_NODES]


def _build_matrix_entry(node_name: str) -> CheckpointResumeMatrixEntry:
    risk = classify_checkpoint_node(node_name)
    if risk == CheckpointNodeRisk.SAFE:
        return CheckpointResumeMatrixEntry(
            node_name=node_name,
            risk=risk,
            checkpoint_allowed=True,
            dry_run_allowed=True,
            real_resume_allowed_now=False,
            reason="安全节点可保存 checkpoint，可做 dry-run，真实恢复暂未启用",
        )
    if risk == CheckpointNodeRisk.SIDE_EFFECT:
        return CheckpointResumeMatrixEntry(
            node_name=node_name,
            risk=risk,
            checkpoint_allowed=True,
            dry_run_allowed=True,
            real_resume_allowed_now=False,
            reason="副作用节点只能谨慎 checkpoint，真实恢复需幂等元数据",
        )
    if risk == CheckpointNodeRisk.TERMINAL:
        return CheckpointResumeMatrixEntry(
            node_name=node_name,
            risk=risk,
            checkpoint_allowed=True,
            dry_run_allowed=True,
            real_resume_allowed_now=False,
            reason="终止节点可记录最终状态，真实恢复暂未启用",
        )
    return CheckpointResumeMatrixEntry(
        node_name=node_name,
        risk=risk,
        checkpoint_allowed=False,
        dry_run_allowed=False,
        real_resume_allowed_now=False,
        reason="未知节点不允许 checkpoint 或 resume",
    )


def _validate_schema_version(snapshot: dict[str, Any]) -> str | None:
    schema_version = snapshot.get("schema_version")
    if not schema_version:
        return "snapshot 缺少 schema_version"
    if schema_version != CHECKPOINT_SNAPSHOT_SCHEMA_VERSION:
        return f"不支持的 schema_version: {schema_version}"
    return None


def _safe_node_precondition_failure(
    snapshot: dict[str, Any],
    next_node: str,
) -> str | None:
    if next_node == "policy_node" and not snapshot.get("action_plan"):
        return "恢复到 policy_node 需要 action_plan"
    if next_node == "route_by_policy_node" and not snapshot.get("policy_decision"):
        return "恢复到 route_by_policy_node 需要 policy_decision"
    if next_node == "human_required_node":
        return _require_policy_decision(snapshot, "HUMAN_REQUIRED", next_node)
    if next_node == "deny_node":
        return _require_policy_decision(snapshot, "DENY", next_node)
    if next_node == "response_generation_node" and not _can_generate_response(snapshot):
        return "恢复到 response_generation_node 需要 final_status 或可生成响应的决策信息"
    if next_node == "llm_response_guard_node" and not snapshot.get("final_response"):
        return "恢复到 llm_response_guard_node 需要 final_response"
    if next_node == "finish_node" and not snapshot.get("final_status"):
        return "恢复到 finish_node 需要 final_status"
    return None


def _side_effect_precondition_failure(
    snapshot: dict[str, Any],
    next_node: str,
) -> str | None:
    if next_node == "tool_gateway_node":
        if not snapshot.get("action_plan"):
            return "恢复到 tool_gateway_node 需要 action_plan"
        return _require_policy_decision(snapshot, "ALLOW", next_node)
    if next_node == "pending_action_node":
        if not snapshot.get("action_plan"):
            return "恢复到 pending_action_node 需要 action_plan"
        return _require_policy_decision(snapshot, "CONFIRM_REQUIRED", next_node)
    if next_node == "failure_handler_node" and not snapshot.get("failure_result"):
        return "恢复到 failure_handler_node 需要 failure_result 和 attempt 元数据"
    return None


def _require_policy_decision(
    snapshot: dict[str, Any],
    expected_decision: str,
    next_node: str,
) -> str | None:
    policy_decision = snapshot.get("policy_decision") or {}
    actual_decision = policy_decision.get("decision")
    if actual_decision != expected_decision:
        return (
            f"恢复到 {next_node} 需要 policy_decision={expected_decision}, "
            f"actual={actual_decision}"
        )
    return None


def _can_generate_response(snapshot: dict[str, Any]) -> bool:
    if snapshot.get("final_status"):
        return True
    policy_decision = snapshot.get("policy_decision") or {}
    return bool(policy_decision.get("decision") or snapshot.get("validation_result"))


def _deny(
    node_name: str,
    risk: CheckpointNodeRisk,
    reason: str,
) -> CheckpointResumeDecision:
    return CheckpointResumeDecision(
        allowed=False,
        reason=reason,
        node_name=node_name,
        risk=risk,
    )
