from dataclasses import dataclass

from app.core.constants import PolicyDecisionType
from app.core.risk import RiskLevel


@dataclass
class PolicyDecision:
    """后端策略裁决结果。

    与 ActionPlan 不同，PolicyDecision 是系统可信边界的一部分。
    它用于表达当前用户是否能执行某个计划、风险等级是多少，以及原因。
    """

    decision: PolicyDecisionType
    risk_level: RiskLevel
    reason: str

    def to_dict(self) -> dict[str, str]:
        """返回 API、Trace 和日志都能复用的序列化结构。"""
        return {
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "reason": self.reason,
        }
