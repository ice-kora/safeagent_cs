from dataclasses import dataclass
from enum import Enum

from app.core.tool_result import ToolResult


class FailureHandlingStatus(str, Enum):
    NO_FAILURE = "NO_FAILURE"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    RECOVERED = "RECOVERED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    FAILED = "FAILED"


class FailureNextAction(str, Enum):
    NO_FAILURE = "NO_FAILURE"
    RETRY = "RETRY"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    FAILED = "FAILED"


@dataclass
class FailureHandlingResult:
    """失败处理结果。

    FailureHandler 不直接重试、不调用工具、不生成用户回复；它只把当前失败
    归一化成主链路后续能理解的结构化决策。
    """

    status: FailureHandlingStatus
    retryable: bool
    next_action: FailureNextAction
    reason: str
    final_tool_result: ToolResult

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "retryable": self.retryable,
            "next_action": self.next_action.value,
            "reason": self.reason,
            "final_tool_result": self.final_tool_result.to_dict(),
        }
