from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolResumeRisk(str, Enum):
    SAFE_TO_SKIP = "SAFE_TO_SKIP"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    UNSAFE_DUPLICATE_RISK = "UNSAFE_DUPLICATE_RISK"
    INSUFFICIENT_METADATA = "INSUFFICIENT_METADATA"


@dataclass(frozen=True)
class ToolResumeDecision:
    """工具边界恢复准备判断。"""

    allowed: bool
    reason: str
    risk: ToolResumeRisk


def can_resume_tool_boundary(snapshot: dict[str, Any]) -> ToolResumeDecision:
    """判断工具边界是否具备恢复条件。

    当前函数只做协议判断，不调用 ToolGateway，不查询 tool_call_logs。
    """
    if not snapshot.get("action_plan"):
        return _deny("缺少 action_plan", ToolResumeRisk.INSUFFICIENT_METADATA)
    policy_decision = snapshot.get("policy_decision") or {}
    if policy_decision.get("decision") != "ALLOW":
        return _deny("工具边界恢复需要 policy_decision=ALLOW", ToolResumeRisk.UNSAFE_DUPLICATE_RISK)
    tool_result = snapshot.get("tool_result")
    if not tool_result:
        return _deny("缺少 tool_result，无法判断工具是否已执行", ToolResumeRisk.INSUFFICIENT_METADATA)

    has_idempotency_metadata = bool(
        snapshot.get("tool_call_id")
        or snapshot.get("idempotency_key")
        or tool_result.get("tool_call_id")
        or tool_result.get("idempotency_key")
    )
    if tool_result.get("success") is True:
        if not has_idempotency_metadata:
            return _deny(
                "工具已成功但缺少 tool_call_id/idempotency_key，拒绝真实恢复",
                ToolResumeRisk.INSUFFICIENT_METADATA,
            )
        return ToolResumeDecision(
            allowed=True,
            reason="工具已成功且具备幂等元数据，可跳过重复工具执行",
            risk=ToolResumeRisk.SAFE_TO_SKIP,
        )

    failure_result = snapshot.get("failure_result")
    if not failure_result:
        return _deny("工具失败但缺少 failure_result", ToolResumeRisk.RETRY_REQUIRED)
    if "attempt_no" not in failure_result or "retryable" not in failure_result:
        return _deny(
            "failure_result 缺少 attempt_no/retryable 元数据",
            ToolResumeRisk.INSUFFICIENT_METADATA,
        )
    if not has_idempotency_metadata:
        return _deny(
            "缺少 tool_call_id/idempotency_key，拒绝真实恢复",
            ToolResumeRisk.INSUFFICIENT_METADATA,
        )
    return ToolResumeDecision(
        allowed=True,
        reason="工具失败且具备重试元数据，可交由后续恢复策略判断",
        risk=ToolResumeRisk.RETRY_REQUIRED,
    )


def _deny(reason: str, risk: ToolResumeRisk) -> ToolResumeDecision:
    return ToolResumeDecision(allowed=False, reason=reason, risk=risk)
