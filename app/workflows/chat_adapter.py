from typing import Any

from dataclasses import replace

from app.core.config import (
    LLM_MODE_MOCK_LLM,
    LLM_MODE_REAL_LLM,
    WORKFLOW_ENGINE_LANGGRAPH,
    get_settings,
)
from app.llm import (
    LLMActionPlanner,
    LLMIntentClassifier,
    MockLLMProvider,
    OpenAICompatibleLLMProvider,
)
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.llm_output_guard import LLMOutputGuard
from app.services.planner_service import RuleBasedActionPlanner
from app.workflows.langgraph_chat_workflow import run_langgraph_chat_workflow
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
    settings = get_settings()
    services = _apply_llm_mode(services, settings.llm_mode)
    if settings.workflow_engine == WORKFLOW_ENGINE_LANGGRAPH:
        state = run_langgraph_chat_workflow(
            session_id=request.session_id,
            user_id=request.user_id,
            message=request.message,
            services=services,
        )
    else:
        workflow = build_safeagent_workflow(services)
        state = workflow.run(
            session_id=request.session_id,
            user_id=request.user_id,
            message=request.message,
        )
    return workflow_state_to_chat_response(state)


def _apply_llm_mode(
    services: SafeAgentWorkflowServices,
    llm_mode: str,
) -> SafeAgentWorkflowServices:
    """根据配置替换理解层和计划层。

    mock_llm 模式只影响候选 intent / ActionPlan 生成；后续仍必须经过
    ActionPlanValidator、PolicyService 和 ToolGateway。这里故意使用非法
    JSON 的 MockLLMProvider 作为默认集成路径，验证 LLM 失败时可稳定
    fallback 到 Rule Mode。
    """
    if llm_mode != LLM_MODE_MOCK_LLM:
        if llm_mode != LLM_MODE_REAL_LLM:
            return services
        return _apply_real_llm_mode(services)

    provider = MockLLMProvider(
        response_map={
            "intent": "not-json",
            "planner": "not-json",
        },
    )
    return replace(
        services,
        intent_classifier=LLMIntentClassifier(
            provider=provider,
            fallback_classifier=RuleBasedIntentClassifier(),
        ),
        action_planner=LLMActionPlanner(
            provider=provider,
            fallback_planner=RuleBasedActionPlanner(),
        ),
    )


def _apply_real_llm_mode(
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowServices:
    try:
        provider = OpenAICompatibleLLMProvider.from_env()
    except Exception:
        return services

    output_guard = LLMOutputGuard()
    return replace(
        services,
        intent_classifier=LLMIntentClassifier(
            provider=provider,
            fallback_classifier=RuleBasedIntentClassifier(),
            output_guard=output_guard,
        ),
        action_planner=LLMActionPlanner(
            provider=provider,
            fallback_planner=RuleBasedActionPlanner(),
            output_guard=output_guard,
        ),
    )


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
