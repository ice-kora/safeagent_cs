import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.logging_service import LoggingService
from app.workflows.safeagent_state import SafeAgentWorkflowState


CHECKPOINT_SNAPSHOT_SCHEMA_VERSION = "checkpoint.snapshot.v1"

SENSITIVE_CHECKPOINT_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|token|secret)\s*[:=]?\s*[\w.-]*"),
    re.compile(r"(?i)system prompt"),
    re.compile(r"系统提示词"),
    re.compile(r"(?i)traceback"),
    re.compile(r"(?i)stack trace"),
    re.compile(r"内部异常栈"),
    re.compile(r"详细地址"),
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b\d{17}[\dXx]\b"),
    re.compile(r"\b\d{16,19}\b"),
)


@dataclass(frozen=True)
class LangGraphCheckpointSnapshot:
    """可序列化的 LangGraph checkpoint 候选快照。

    当前真实 workflow 仍使用 SafeAgentWorkflowState 可变对象运行。
    这个结构只用于后续 checkpoint/resume 设计准备，保证可 JSON 序列化、
    可脱敏、且不携带原始 service 或复杂对象。
    """

    request_id: str
    run_id: str
    parent_run_id: str | None
    session_id: str
    user_id: str
    tenant_id: str | None
    message: str
    intent_result: str | None
    final_status: str | None
    final_response: str | None
    pending_action_id: str | None
    route: str | None
    action_plan: dict[str, Any] | None
    validation_result: dict[str, Any] | None
    policy_decision: dict[str, Any] | None
    tool_result: dict[str, Any] | None
    failure_result: dict[str, Any] | None
    errors: list[dict[str, Any]] = field(default_factory=list)
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = CHECKPOINT_SNAPSHOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON-safe 且脱敏的普通字典。"""
        return _sanitize_checkpoint_payload(asdict(self))


def state_to_checkpoint_snapshot(
    state: SafeAgentWorkflowState,
    route: str | None = None,
) -> LangGraphCheckpointSnapshot:
    """把当前 Workflow State 转成 checkpoint-ready 快照。

    这里不改变运行态 state，也不启用真实 checkpointer。转换时会把
    ActionPlan、PolicyDecision、ToolResult 等复杂对象全部降级为 dict。
    """
    return LangGraphCheckpointSnapshot(
        request_id=state.request_id,
        run_id=state.run_id,
        parent_run_id=state.parent_run_id,
        session_id=state.session_id,
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        message=_sanitize_checkpoint_payload(state.message),
        intent_result=state.intent_result,
        final_status=state.final_status,
        final_response=_sanitize_checkpoint_payload(state.final_response),
        pending_action_id=state.pending_action_id,
        route=route,
        action_plan=_action_plan_to_dict(state),
        validation_result=_validation_result_to_dict(state),
        policy_decision=_policy_decision_to_dict(state),
        tool_result=_tool_result_to_dict(state),
        failure_result=_failure_result_to_dict(state),
        errors=_sanitize_checkpoint_payload(state.errors or []),
        trace_events=_sanitize_checkpoint_payload(state.trace_events or []),
    )


def snapshot_to_dict(snapshot: LangGraphCheckpointSnapshot) -> dict[str, Any]:
    """显式转换函数，便于后续 checkpoint 写入层复用。"""
    return snapshot.to_dict()


def state_to_json_safe_dict(
    state: SafeAgentWorkflowState,
    route: str | None = None,
) -> dict[str, Any]:
    """一步生成 JSON-safe checkpoint 字典。"""
    return snapshot_to_dict(state_to_checkpoint_snapshot(state, route=route))


def _action_plan_to_dict(state: SafeAgentWorkflowState) -> dict[str, Any] | None:
    if not state.action_plan:
        return None
    return _sanitize_checkpoint_payload(state.action_plan.to_dict())


def _validation_result_to_dict(
    state: SafeAgentWorkflowState,
) -> dict[str, Any] | None:
    if not state.validation_result:
        return None
    return {
        "status": state.validation_result.status.value,
        "reason": _sanitize_checkpoint_payload(state.validation_result.reason),
    }


def _policy_decision_to_dict(state: SafeAgentWorkflowState) -> dict[str, Any] | None:
    if not state.policy_decision:
        return None
    return _sanitize_checkpoint_payload(state.policy_decision.to_dict())


def _tool_result_to_dict(state: SafeAgentWorkflowState) -> dict[str, Any] | None:
    if not state.tool_result:
        return None
    return _sanitize_checkpoint_payload(state.tool_result.to_dict())


def _failure_result_to_dict(state: SafeAgentWorkflowState) -> dict[str, Any] | None:
    if not state.failure_result:
        return None
    return _sanitize_checkpoint_payload(state.failure_result.to_dict())


def _sanitize_checkpoint_payload(value: Any) -> Any:
    sanitized = LoggingService.sanitize_payload(value)
    return _sanitize_sensitive_text(sanitized)


def _sanitize_sensitive_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_sensitive_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_sensitive_text(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_sensitive_text(item) for item in value]
    if isinstance(value, str):
        result = value
        for pattern in SENSITIVE_CHECKPOINT_PATTERNS:
            result = pattern.sub("***", result)
        return result
    return value
