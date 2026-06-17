from dataclasses import dataclass
from enum import Enum
from typing import Any


class PendingResumeRisk(str, Enum):
    READY_FOR_CONFIRM_WAIT = "READY_FOR_CONFIRM_WAIT"
    MISSING_PENDING_ACTION_ID = "MISSING_PENDING_ACTION_ID"
    DUPLICATE_CREATE_RISK = "DUPLICATE_CREATE_RISK"
    UNSUPPORTED_STATUS = "UNSUPPORTED_STATUS"


@dataclass(frozen=True)
class PendingResumeDecision:
    """pending_action 边界恢复准备判断。"""

    allowed: bool
    reason: str
    risk: PendingResumeRisk


def can_resume_pending_boundary(snapshot: dict[str, Any]) -> PendingResumeDecision:
    """判断 pending_action 边界是否可恢复到等待确认状态。

    当前函数只读 snapshot，不执行 /api/confirm，不创建 pending_action，也不查库。
    """
    policy_decision = snapshot.get("policy_decision") or {}
    if policy_decision.get("decision") != "CONFIRM_REQUIRED":
        return PendingResumeDecision(
            allowed=False,
            reason="pending_action 恢复需要 policy_decision=CONFIRM_REQUIRED",
            risk=PendingResumeRisk.UNSUPPORTED_STATUS,
        )
    if not snapshot.get("action_plan"):
        return PendingResumeDecision(
            allowed=False,
            reason="缺少 action_plan",
            risk=PendingResumeRisk.DUPLICATE_CREATE_RISK,
        )
    if not snapshot.get("pending_action_id"):
        return PendingResumeDecision(
            allowed=False,
            reason="缺少 pending_action_id，直接恢复可能重复创建 pending_action",
            risk=PendingResumeRisk.MISSING_PENDING_ACTION_ID,
        )
    return PendingResumeDecision(
        allowed=True,
        reason="已有 pending_action_id，可恢复到等待用户确认状态",
        risk=PendingResumeRisk.READY_FOR_CONFIRM_WAIT,
    )
