from dataclasses import dataclass, field
from typing import Any

from app.core.action_plan import ActionPlan
from app.core.action_plan_validator import ValidationResult
from app.core.failure_result import FailureHandlingResult
from app.core.policy import PolicyDecision
from app.core.tool_result import ToolResult
from app.services.logging_service import LoggingService


@dataclass
class SafeAgentWorkflowState:
    """Workflow 执行上下文。

    State 只服务于流程编排，不是数据库实体，也不是审计事实源。
    它可以保存节点之间传递的最小必要上下文，但导出的 safe_snapshot
    必须避免泄漏完整订单、完整地址、手机号、支付信息、token 等敏感内容。
    """

    request_id: str
    run_id: str
    session_id: str
    user_id: str
    message: str
    parent_run_id: str | None = None
    tenant_id: str | None = None

    intent_result: str | None = None
    action_plan: ActionPlan | None = None
    validation_result: ValidationResult | None = None
    policy_decision: PolicyDecision | None = None

    pending_action_id: str | None = None
    checkpoint_id: str | None = None
    tool_result: ToolResult | None = None
    failure_result: FailureHandlingResult | None = None

    final_status: str | None = None
    final_response: str | None = None
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def add_trace_event(
        self,
        node_name: str,
        event_type: str,
        status: str = "SUCCESS",
        summary: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录内存态 trace event。

        数据库 Trace 由 TraceService 写入；这里保留轻量事件，便于独立
        Workflow 测试直接判断节点路径。
        """
        event = {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "node_name": node_name,
            "event_type": event_type,
            "status": status,
            "summary": summary,
        }
        if extra:
            event.update(extra)
        self.trace_events.append(LoggingService.sanitize_payload(event))

    def add_error(
        self,
        error_type: str,
        message: str,
        node_name: str | None = None,
    ) -> None:
        """记录安全错误摘要，不保存异常栈。"""
        self.errors.append(
            LoggingService.sanitize_payload(
                {
                    "error_type": error_type,
                    "message": message,
                    "node_name": node_name,
                }
            )
        )

    def safe_snapshot(self) -> dict[str, Any]:
        """返回可用于测试、日志或后续 LLM 安全摘要的快照。"""
        snapshot = {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "message_length": len(self.message or ""),
            "intent_result": self.intent_result,
            "action_plan": self._action_plan_to_safe_dict(),
            "validation_result": self._validation_to_dict(),
            "policy_decision": (
                self.policy_decision.to_dict() if self.policy_decision else None
            ),
            "pending_action_id": self.pending_action_id,
            "checkpoint_id": self.checkpoint_id,
            "tool_result": self._tool_result_to_safe_dict(),
            "failure_result": self._failure_result_to_safe_dict(),
            "final_status": self.final_status,
            "final_response": self.final_response,
            "trace_events": self.trace_events,
            "errors": self.errors,
        }
        return LoggingService.sanitize_payload(snapshot)

    def to_safe_dict(self) -> dict[str, Any]:
        """兼容文档中的 to_safe_dict 命名。"""
        return self.safe_snapshot()

    def _validation_to_dict(self) -> dict[str, str] | None:
        if not self.validation_result:
            return None
        return {
            "status": self.validation_result.status.value,
            "reason": self.validation_result.reason,
        }

    def _action_plan_to_safe_dict(self) -> dict[str, Any] | None:
        if not self.action_plan:
            return None
        return {
            "intent": self.action_plan.intent,
            "action": self.action_plan.action,
            "target_type": self.action_plan.target_type,
            "target_id": self.action_plan.target_id,
            "tool_name": self.action_plan.tool_name,
            "reason": self.action_plan.reason,
        }

    def _tool_result_to_safe_dict(self) -> dict[str, Any] | None:
        if not self.tool_result:
            return None
        return {
            "success": self.tool_result.success,
            "tool_name": self.tool_result.tool_name,
            "summary": self.tool_result.summary,
            "error_type": self.tool_result.error_type,
            "safe_for_llm": self.tool_result.safe_for_llm,
        }

    def _failure_result_to_safe_dict(self) -> dict[str, Any] | None:
        if not self.failure_result:
            return None
        return {
            "status": self.failure_result.status.value,
            "retryable": self.failure_result.retryable,
            "next_action": self.failure_result.next_action.value,
            "reason": self.failure_result.reason,
        }
