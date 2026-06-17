from typing import Any

from app.workflows.safeagent_state import SafeAgentWorkflowState
from app.workflows.safeagent_workflow import build_safeagent_workflow
from app.workflows.service_adapters import SafeAgentWorkflowServices


def handle_workflow_chat(
    request: Any,
    services: SafeAgentWorkflowServices,
) -> dict[str, Any]:
    """把 /api/chat 请求映射到 Workflow runner。

    Adapter 只做请求/响应格式转换，不重新实现 PolicyService、ToolGateway、
    PendingActionService 或 FailureHandler 的业务规则。
    """
    workflow = build_safeagent_workflow(services)
    state = workflow.run(
        session_id=request.session_id,
        user_id=request.user_id,
        message=request.message,
    )
    return workflow_state_to_chat_response(state)


def workflow_state_to_chat_response(
    state: SafeAgentWorkflowState,
) -> dict[str, Any]:
    """将 Workflow State 转回现有 /api/chat 兼容响应结构。"""
    return {
        "request_id": state.request_id,
        "run_id": state.run_id,
        "status": state.final_status or "WORKFLOW_FAILED",
        "intent": state.intent_result,
        "action": state.action_plan.action if state.action_plan else None,
        "policy_decision": (
            state.policy_decision.to_dict() if state.policy_decision else None
        ),
        "tool_result": state.tool_result.to_dict() if state.tool_result else None,
        "pending_action_id": state.pending_action_id,
        "validation_result": _validation_to_dict(state),
        "failure_result": (
            state.failure_result.to_dict() if state.failure_result else None
        ),
        "message": state.final_response or "Workflow 已安全停止处理",
    }


def _validation_to_dict(state: SafeAgentWorkflowState) -> dict[str, str] | None:
    if not state.validation_result:
        return None
    return {
        "status": state.validation_result.status.value,
        "reason": state.validation_result.reason,
    }

