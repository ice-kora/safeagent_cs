from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SafetyRegressionObservation:
    """单条 case 在某个模式下的执行观测。"""

    mode: str
    status: str
    tool_call_count: int
    pending_action_count: int
    trace_count: int
    status_code: int = 200
    response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "status_code": self.status_code,
            "tool_call_count": self.tool_call_count,
            "pending_action_count": self.pending_action_count,
            "trace_count": self.trace_count,
            "response": self.response,
        }


@dataclass(frozen=True)
class SafetyRegressionResult:
    """manual/workflow 对照结果。"""

    case_id: str
    manual_status: str
    workflow_status: str
    manual_tool_call_count: int
    workflow_tool_call_count: int
    manual_pending_action_count: int
    workflow_pending_action_count: int
    manual_trace_count: int
    workflow_trace_count: int
    passed: bool
    intentional_difference: bool
    difference_reason: str | None = None
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "manual_status": self.manual_status,
            "workflow_status": self.workflow_status,
            "manual_tool_call_count": self.manual_tool_call_count,
            "workflow_tool_call_count": self.workflow_tool_call_count,
            "manual_pending_action_count": self.manual_pending_action_count,
            "workflow_pending_action_count": self.workflow_pending_action_count,
            "manual_trace_count": self.manual_trace_count,
            "workflow_trace_count": self.workflow_trace_count,
            "passed": self.passed,
            "intentional_difference": self.intentional_difference,
            "difference_reason": self.difference_reason,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class SafetyRegressionReport:
    """安全回归评测报告。"""

    results: list[SafetyRegressionResult]

    @property
    def total_cases(self) -> int:
        return len(self.results)

    @property
    def passed_cases(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed_cases(self) -> int:
        return sum(1 for result in self.results if not result.passed)

    @property
    def intentional_differences(self) -> int:
        return sum(1 for result in self.results if result.intentional_difference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "intentional_differences": self.intentional_differences,
            "results": [result.to_dict() for result in self.results],
        }
