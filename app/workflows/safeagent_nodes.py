from typing import Any

from app.core.constants import PolicyDecisionType
from app.core.failure_result import FailureHandlingStatus
from app.core.tool_result import ToolResult
from app.services.checkpoint_service import CheckpointService
from app.services.logging_service import LoggingService
from app.services.policy_service import PolicyAuditContext, evaluate_policy
from app.workflows.safeagent_state import SafeAgentWorkflowState
from app.workflows.service_adapters import (
    SafeAgentWorkflowServices,
    build_workflow_tool_args,
)


SENSITIVE_TRACE_MARKERS = (
    "api_key",
    "api key",
    "token",
    "system prompt",
    "系统 prompt",
    "系统提示词",
    "详细地址",
    "traceback",
    "stack trace",
)


def append_node_trace(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
    node_name: str,
    event_type: str,
    input_json: dict[str, Any],
    output_json: dict[str, Any],
    status: str = "SUCCESS",
    error_type: str | None = None,
    summary: str = "",
) -> None:
    """同时写数据库 Trace 和内存 trace_events。

    这样 Workflow 独立测试可以直接看 state.trace_events，真实排障仍可
    通过 TraceService 查询 agent_traces。
    """
    safe_input_json = _sanitize_workflow_trace_payload(input_json)
    safe_output_json = _sanitize_workflow_trace_payload(output_json)
    services.trace_service.append_trace(
        run_id=state.run_id,
        node_name=node_name,
        input_json=safe_input_json,
        output_json=safe_output_json,
        status=status,
        error_type=error_type,
    )
    state.add_trace_event(
        node_name=node_name,
        event_type=event_type,
        status=status,
        summary=_sanitize_workflow_trace_payload(summary),
        extra={"error_type": error_type} if error_type else None,
    )


def _sanitize_workflow_trace_payload(value: Any) -> Any:
    """Workflow 写 Trace 前的显式脱敏。

    TraceService 本身也会脱敏。这里在 Workflow 层再做一次，是为了保证
    未来替换真实 LangGraph 后，节点输出在进入 TraceService 前已经是安全摘要。
    """
    sanitized = LoggingService.sanitize_payload(value)
    return _redact_sensitive_trace_markers(sanitized)


def _redact_sensitive_trace_markers(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_sensitive_trace_markers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_sensitive_trace_markers(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive_trace_markers(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in SENSITIVE_TRACE_MARKERS):
            return "***"
    return value


def intent_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """识别用户意图，不做权限判断。"""
    intent = services.intent_classifier.classify(state.message)
    state.intent_result = intent
    append_node_trace(
        state,
        services,
        node_name="intent_node",
        event_type="intent_classified",
        input_json={"message": state.message},
        output_json={"intent": intent, "llm": _llm_debug_info(services.intent_classifier)},
        summary=f"intent={intent}",
    )
    return state


def planner_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """生成候选 ActionPlan，后续仍必须经过 Validator。"""
    action_plan = services.action_planner.plan(
        intent=state.intent_result or "unknown",
        message=state.message,
    )
    state.action_plan = action_plan
    append_node_trace(
        state,
        services,
        node_name="planner_node",
        event_type="plan_generated",
        input_json={"intent": state.intent_result, "message": state.message},
        output_json={
            "action_plan": action_plan.to_dict(),
            "llm": _llm_debug_info(services.action_planner),
        },
        summary=f"action={action_plan.action}",
    )
    return state


def action_plan_validator_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """调用现有 ActionPlanValidator，不在 Workflow 中重写校验规则。"""
    if state.action_plan is None:
        state.final_status = "PLAN_INVALID"
        state.add_error("PLAN_INVALID", "缺少 ActionPlan", "action_plan_validator_node")
        return state

    validation_result = services.action_plan_validator.validate(state.action_plan)
    state.validation_result = validation_result
    status = "SUCCESS" if validation_result.is_valid else "FAILED"
    append_node_trace(
        state,
        services,
        node_name="action_plan_validator_node",
        event_type="action_plan_validated",
        input_json={"action_plan": state.action_plan.to_dict()},
        output_json={
            "status": validation_result.status.value,
            "reason": validation_result.reason,
        },
        status=status,
        error_type=None if validation_result.is_valid else validation_result.status.value,
        summary=validation_result.status.value,
    )
    if not validation_result.is_valid:
        state.final_status = "PLAN_INVALID"
        state.final_response = "计划结构校验失败，无法继续处理"
    return state


def policy_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """调用现有 PolicyService 做权限与风险裁决。"""
    if state.action_plan is None:
        state.final_status = "PLAN_INVALID"
        state.add_error("PLAN_INVALID", "缺少 ActionPlan", "policy_node")
        return state

    policy_decision = evaluate_policy(
        services.policy_service,
        state.action_plan,
        customer_user_id=state.user_id,
        audit_context=PolicyAuditContext(
            run_id=state.run_id,
            request_id=state.request_id,
            session_id=state.session_id,
            user_id=state.user_id,
            tenant_id=state.tenant_id,
        ),
    )
    state.policy_decision = policy_decision
    append_node_trace(
        state,
        services,
        node_name="policy_node",
        event_type="policy_decided",
        input_json={"action_plan": state.action_plan.to_dict(), "user_id": state.user_id},
        output_json=policy_decision.to_dict(),
        summary=policy_decision.decision.value,
    )
    return state


def route_by_policy_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> str:
    """只读取 PolicyDecision 并返回路由，不修改裁决结果。"""
    if state.policy_decision is None:
        route = "WORKFLOW_FAILED"
    else:
        route = state.policy_decision.decision.value
    append_node_trace(
        state,
        services,
        node_name="route_by_policy_node",
        event_type="route_selected",
        input_json={
            "policy_decision": (
                state.policy_decision.to_dict() if state.policy_decision else None
            )
        },
        output_json={"route": route},
        summary=f"route={route}",
    )
    return route


def tool_gateway_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """通过 ToolGateway 执行工具，禁止直接调用具体 Mock Tool。"""
    if state.action_plan is None or state.policy_decision is None:
        state.final_status = "WORKFLOW_FAILED"
        state.add_error("WORKFLOW_FAILED", "工具节点缺少必要上下文", "tool_gateway_node")
        return state

    tool_args = build_workflow_tool_args(
        action_plan=state.action_plan,
        customer_user_id=state.user_id,
        risk_level=state.policy_decision.risk_level.value,
        source_run_id=state.run_id,
    )
    tool_result = services.tool_gateway.call_tool(
        run_id=state.run_id,
        session_id=state.session_id,
        tool_name=state.action_plan.tool_name or "",
        tool_args=tool_args,
    )
    state.tool_result = tool_result
    append_node_trace(
        state,
        services,
        node_name="tool_gateway_node",
        event_type="tool_called",
        input_json={
            "tool_name": state.action_plan.tool_name,
            "tool_args": tool_args,
        },
        output_json=tool_result.to_dict(),
        status="SUCCESS" if tool_result.success else "FAILED",
        error_type=tool_result.error_type,
        summary=tool_result.summary,
    )
    return state


def failure_handler_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """工具失败后由 FailureHandler 收口；重试仍通过 ToolGateway。"""
    if state.tool_result is None:
        state.final_status = "WORKFLOW_FAILED"
        state.add_error("WORKFLOW_FAILED", "缺少 ToolResult", "failure_handler_node")
        return state

    if state.tool_result.error_type == "POLICY_NOT_FOUND":
        state.final_status = "POLICY_NOT_FOUND"
        append_node_trace(
            state,
            services,
            node_name="failure_handler_node",
            event_type="rag_no_answer",
            input_json={"tool_result": state.tool_result.to_dict()},
            output_json={"final_status": state.final_status},
            status="SUCCESS",
            summary="RAG 未找到足够可靠的知识依据",
        )
        return state

    if state.tool_result.success:
        failure_result = services.failure_handler.handle_tool_result(
            run_id=state.run_id,
            session_id=state.session_id,
            tool_result=state.tool_result,
        )
    else:
        retry_tool_args = {}
        if state.action_plan and state.policy_decision:
            retry_tool_args = build_workflow_tool_args(
                action_plan=state.action_plan,
                customer_user_id=state.user_id,
                risk_level=state.policy_decision.risk_level.value,
                source_run_id=state.run_id,
            )
        failure_result = services.failure_handler.handle_with_retry(
            run_id=state.run_id,
            session_id=state.session_id,
            tool_name=state.tool_result.tool_name,
            tool_args=retry_tool_args,
            first_result=state.tool_result,
            tool_gateway=services.tool_gateway,
        )

    state.failure_result = failure_result
    if failure_result.status == FailureHandlingStatus.NO_FAILURE:
        state.final_status = "SUCCESS"
    elif failure_result.status == FailureHandlingStatus.RECOVERED:
        state.final_status = "RECOVERED"
        state.tool_result = failure_result.final_tool_result
    else:
        state.final_status = "TOOL_FAILED"
        state.tool_result = failure_result.final_tool_result

    append_node_trace(
        state,
        services,
        node_name="failure_handler_node",
        event_type="failure_handled",
        input_json={"tool_result": state.tool_result.to_dict()},
        output_json=failure_result.to_dict(),
        status="SUCCESS" if state.final_status in {"SUCCESS", "RECOVERED"} else "FAILED",
        error_type=None if state.final_status in {"SUCCESS", "RECOVERED"} else state.final_status,
        summary=failure_result.status.value,
    )
    return state


def pending_action_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """只创建 pending_action，不执行工具。"""
    if state.action_plan is None or state.policy_decision is None:
        state.final_status = "WORKFLOW_FAILED"
        state.add_error("WORKFLOW_FAILED", "待确认节点缺少必要上下文", "pending_action_node")
        return state

    pending_action_id = services.pending_action_service.create_pending_action(
        session_id=state.session_id,
        source_run_id=state.run_id,
        user_id=state.user_id,
        action_plan=state.action_plan,
        risk_level=state.policy_decision.risk_level.value,
    )
    state.pending_action_id = pending_action_id
    state.checkpoint_id = _create_confirmation_checkpoint(state, services)
    state.final_status = PolicyDecisionType.CONFIRM_REQUIRED.value
    append_node_trace(
        state,
        services,
        node_name="pending_action_node",
        event_type="pending_action_created",
        input_json={"action_plan": state.action_plan.to_dict()},
        output_json={
            "pending_action_id": pending_action_id,
            "checkpoint_id": state.checkpoint_id,
        },
        summary=pending_action_id,
    )
    return state


def human_required_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """人工处理分支不自动调用工具。"""
    state.final_status = PolicyDecisionType.HUMAN_REQUIRED.value
    append_node_trace(
        state,
        services,
        node_name="human_required_node",
        event_type="human_required",
        input_json={
            "policy_decision": (
                state.policy_decision.to_dict() if state.policy_decision else None
            )
        },
        output_json={"status": state.final_status},
        summary="需要人工处理",
    )
    return state


def deny_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """拒绝分支直接终止，不进入 ToolGateway。"""
    state.final_status = PolicyDecisionType.DENY.value
    append_node_trace(
        state,
        services,
        node_name="deny_node",
        event_type="denied",
        input_json={
            "policy_decision": (
                state.policy_decision.to_dict() if state.policy_decision else None
            )
        },
        output_json={"status": state.final_status},
        summary="策略拒绝",
    )
    return state


def response_generation_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """生成 P0 规则回复，不声明未发生的工具成功。"""
    state.final_response = _build_rule_response(state)
    append_node_trace(
        state,
        services,
        node_name="response_generation_node",
        event_type="response_generated",
        input_json={"final_status": state.final_status},
        output_json={"final_response": state.final_response},
        summary=state.final_status or "UNKNOWN",
    )
    return state


def finish_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """关闭 run 生命周期。"""
    failed_statuses = {"PLAN_INVALID", "TOOL_FAILED", "WORKFLOW_FAILED"}
    event_type = "workflow_failed" if state.final_status in failed_statuses else "workflow_finished"
    append_node_trace(
        state,
        services,
        node_name="finish_node",
        event_type=event_type,
        input_json={"final_status": state.final_status},
        output_json={"final_response": state.final_response},
        status="FAILED" if state.final_status in failed_statuses else "SUCCESS",
        error_type=state.final_status if state.final_status in failed_statuses else None,
        summary=state.final_status or "UNKNOWN",
    )
    if state.final_status in failed_statuses:
        services.trace_service.fail_run(state.run_id, state.final_status or "WORKFLOW_FAILED")
    else:
        services.trace_service.finish_run(state.run_id)
    return state


def _build_rule_response(state: SafeAgentWorkflowState) -> str:
    if state.final_status in {"SUCCESS", "RECOVERED"}:
        return state.tool_result.summary if state.tool_result else "请求已处理完成。"
    if state.final_status == PolicyDecisionType.CONFIRM_REQUIRED.value:
        return "该操作需要二次确认"
    if state.final_status == PolicyDecisionType.HUMAN_REQUIRED.value:
        return "该请求需要人工处理"
    if state.final_status == PolicyDecisionType.DENY.value:
        return state.policy_decision.reason if state.policy_decision else "请求已被拒绝"
    if state.final_status == "POLICY_NOT_FOUND":
        return (
            state.tool_result.summary
            if state.tool_result
            else "暂未找到相关政策，建议转人工客服。"
        )
    if state.final_status == "PLAN_INVALID":
        return "计划结构校验失败，无法继续处理"
    if state.final_status == "TOOL_FAILED":
        if state.tool_result and state.tool_result.error_type == "POLICY_NOT_FOUND":
            return state.tool_result.summary
        return "工具调用失败"
    return "Workflow 已安全停止处理"


def _llm_debug_info(component: Any) -> dict[str, Any] | None:
    debug_info = getattr(component, "last_debug_info", None)
    if not isinstance(debug_info, dict) or not debug_info:
        return None
    return LoggingService.sanitize_payload(debug_info)


def _create_confirmation_checkpoint(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> str:
    checkpoint_service = CheckpointService(
        db_path=services.pending_action_service.db_path
    )
    return checkpoint_service.create_checkpoint(
        run_id=state.run_id,
        parent_run_id=state.parent_run_id,
        session_id=state.session_id,
        user_id=state.user_id,
        current_node="pending_action_node",
        checkpoint_type=CheckpointService.TYPE_WAITING_CONFIRMATION,
        status=CheckpointService.STATUS_WAITING_CONFIRMATION,
        state_snapshot={
            "pending_action_id": state.pending_action_id,
            "action_plan": state.action_plan.to_dict() if state.action_plan else None,
            "risk_level": (
                state.policy_decision.risk_level.value
                if state.policy_decision
                else None
            ),
        },
        resume_policy={
            "resume_api": "/api/checkpoints/{checkpoint_id}/resume",
            "next_api": "/api/confirm",
            "requires_validator": True,
            "requires_policy": True,
            "tool_execution_on_resume": False,
        },
    )


def llm_output_guard_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """预留节点：未来 LLM Planner 输出必须先经过 Guard。"""
    append_node_trace(
        state,
        services,
        node_name="llm_output_guard_node",
        event_type="llm_output_guarded",
        input_json={},
        output_json={"enabled": False},
        summary="LLM OutputGuard 未启用",
    )
    return state


def llm_response_guard_node(
    state: SafeAgentWorkflowState,
    services: SafeAgentWorkflowServices,
) -> SafeAgentWorkflowState:
    """预留节点：未来 LLM 回复草稿必须先经过 Guard。"""
    append_node_trace(
        state,
        services,
        node_name="llm_response_guard_node",
        event_type="response_guarded",
        input_json={},
        output_json={"enabled": False},
        summary="LLM ResponseGuard 未启用",
    )
    return state
