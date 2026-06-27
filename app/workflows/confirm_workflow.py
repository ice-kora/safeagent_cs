from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.action_plan import ActionPlan
from app.core.constants import PolicyDecisionType
from app.core.failure_result import FailureHandlingResult, FailureHandlingStatus
from app.core.ids import generate_request_id
from app.core.policy import PolicyDecision
from app.core.tool_result import ToolResult
from app.services.failure_handler import FailureHandler
from app.services.pending_action_service import (
    PendingActionError,
    PendingActionPermissionError,
    PendingActionService,
)
from app.services.policy_service import (
    PolicyAuditContext,
    PolicyService,
    evaluate_policy,
)
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService
from app.workflows.safeagent_nodes import append_node_trace
from app.workflows.service_adapters import build_workflow_tool_args


@dataclass
class ConfirmWorkflowServices:
    """confirm_workflow 依赖集合。

    确认流程不需要 IntentClassifier 或 ActionPlanner。它只恢复已经保存的
    pending_action，重新复核 PolicyService，并通过 ToolGateway 执行工具。
    """

    pending_action_service: PendingActionService
    trace_service: TraceService
    policy_service: PolicyService
    tool_gateway: ToolGateway
    failure_handler: FailureHandler


@dataclass
class ConfirmWorkflowState:
    """二次确认 Workflow 的流程上下文。"""

    request_id: str
    run_id: str
    session_id: str
    user_id: str
    pending_action_id: str
    confirm: bool
    parent_run_id: str | None = None

    pending_action_record: dict[str, Any] | None = None
    validated_pending_action: dict[str, Any] | None = None
    action_plan: ActionPlan | None = None
    policy_decision: PolicyDecision | None = None
    tool_result: ToolResult | None = None
    failure_result: FailureHandlingResult | None = None

    final_status: str | None = None
    final_response: str | None = None
    error_message: str | None = None
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
        self.trace_events.append(event)

    def add_error(
        self,
        error_type: str,
        message: str,
        node_name: str | None = None,
    ) -> None:
        self.error_message = message
        self.errors.append(
            {
                "error_type": error_type,
                "message": message,
                "node_name": node_name,
            }
        )


class ConfirmWorkflow:
    """LangGraph-style 二次确认独立 Workflow。

    它不重新识别意图、不重新规划 ActionPlan，只恢复 pending_action 中保存的
    action_plan_json，并在执行前重新复核策略。
    """

    def __init__(self, services: ConfirmWorkflowServices) -> None:
        self.services = services

    def run(
        self,
        pending_action_id: str,
        user_id: str,
        session_id: str,
        confirm: bool,
    ) -> ConfirmWorkflowState:
        request_id = generate_request_id()
        preloaded = self.services.pending_action_service.get_pending_action(
            pending_action_id
        )
        parent_run_id = preloaded["source_run_id"] if preloaded else None
        run_id = self.services.trace_service.start_run(
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            parent_run_id=parent_run_id,
            pending_action_id=pending_action_id,
        )
        state = ConfirmWorkflowState(
            request_id=request_id,
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            pending_action_id=pending_action_id,
            confirm=confirm,
            parent_run_id=parent_run_id,
            pending_action_record=preloaded,
        )
        append_node_trace(
            state,
            self.services,
            node_name="confirm_workflow_start_node",
            event_type="confirm_workflow_started",
            input_json={
                "pending_action_id": pending_action_id,
                "user_id": user_id,
                "session_id": session_id,
                "confirm": confirm,
            },
            output_json={"run_id": run_id, "parent_run_id": parent_run_id},
            summary="confirm workflow started",
        )
        try:
            return self._run_nodes(state)
        except Exception as exc:
            state.final_status = "WORKFLOW_FAILED"
            state.final_response = "确认流程已安全停止处理"
            state.add_error("WORKFLOW_FAILED", str(exc), "confirm_workflow")
            append_node_trace(
                state,
                self.services,
                node_name="confirm_workflow_exception_node",
                event_type="confirm_workflow_failed",
                input_json={"pending_action_id": pending_action_id},
                output_json={"error_type": "WORKFLOW_FAILED"},
                status="FAILED",
                error_type="WORKFLOW_FAILED",
                summary="confirm workflow failed",
            )
            self.services.trace_service.fail_run(state.run_id, "WORKFLOW_FAILED")
            return state

    def _run_nodes(self, state: ConfirmWorkflowState) -> ConfirmWorkflowState:
        load_pending_action_node(state, self.services)
        if _is_terminal_validation_status(state):
            return _finish_after_response(state, self.services)

        validate_pending_action_node(state, self.services)
        if _is_terminal_validation_status(state):
            return _finish_after_response(state, self.services)

        if not state.confirm:
            confirm_cancel_node(state, self.services)
            return _finish_after_response(state, self.services)

        restore_action_plan_node(state, self.services)
        policy_recheck_node(state, self.services)
        route = route_after_policy_recheck_node(state, self.services)

        if route == PolicyDecisionType.ALLOW.value:
            confirm_tool_gateway_node(state, self.services)
            confirm_failure_handler_node(state, self.services)
        elif route == PolicyDecisionType.DENY.value:
            confirm_deny_node(state, self.services)
        elif route == PolicyDecisionType.HUMAN_REQUIRED.value:
            confirm_human_required_node(state, self.services)
        elif route == PolicyDecisionType.CONFIRM_REQUIRED.value:
            confirm_safe_stop_node(state, self.services)
        else:
            state.final_status = "WORKFLOW_FAILED"
            state.add_error("WORKFLOW_FAILED", f"未知确认路由: {route}", "route_after_policy_recheck_node")

        return _finish_after_response(state, self.services)


def build_confirm_workflow(services: ConfirmWorkflowServices) -> ConfirmWorkflow:
    return ConfirmWorkflow(services)


def load_pending_action_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    record = services.pending_action_service.get_pending_action(state.pending_action_id)
    state.pending_action_record = record
    if record is None:
        state.final_status = "PENDING_ACTION_NOT_FOUND"
        state.add_error(
            "PENDING_ACTION_NOT_FOUND",
            f"pending_action 不存在: {state.pending_action_id}",
            "load_pending_action_node",
        )
    append_node_trace(
        state,
        services,
        node_name="load_pending_action_node",
        event_type="pending_action_loaded",
        input_json={"pending_action_id": state.pending_action_id},
        output_json={"found": record is not None},
        status="FAILED" if record is None else "SUCCESS",
        error_type="PENDING_ACTION_NOT_FOUND" if record is None else None,
        summary="pending action loaded" if record else "pending action not found",
    )
    return state


def validate_pending_action_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    try:
        pending_action = services.pending_action_service.validate_pending_action(
            pending_action_id=state.pending_action_id,
            user_id=state.user_id,
        )
    except PendingActionPermissionError as exc:
        state.final_status = "PENDING_ACTION_PERMISSION_DENIED"
        state.add_error(
            "PENDING_ACTION_PERMISSION_DENIED",
            str(exc),
            "validate_pending_action_node",
        )
        return _trace_pending_validation(state, services, "FAILED", "PENDING_ACTION_PERMISSION_DENIED")
    except PendingActionError as exc:
        error_type = (
            "PENDING_ACTION_EXPIRED"
            if "已过期" in str(exc)
            else "PENDING_ACTION_INVALID"
        )
        state.final_status = error_type
        state.add_error(error_type, str(exc), "validate_pending_action_node")
        return _trace_pending_validation(state, services, "FAILED", error_type)

    if pending_action["session_id"] != state.session_id:
        state.final_status = "PENDING_ACTION_SESSION_MISMATCH"
        state.add_error(
            "PENDING_ACTION_SESSION_MISMATCH",
            "pending_action session 不匹配",
            "validate_pending_action_node",
        )
        return _trace_pending_validation(
            state,
            services,
            "FAILED",
            "PENDING_ACTION_SESSION_MISMATCH",
        )

    state.validated_pending_action = pending_action
    state.parent_run_id = pending_action["source_run_id"]
    return _trace_pending_validation(state, services, "SUCCESS", None)


def restore_action_plan_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    if state.validated_pending_action is None:
        state.final_status = "PENDING_ACTION_INVALID"
        state.add_error("PENDING_ACTION_INVALID", "缺少已校验 pending_action", "restore_action_plan_node")
        return state
    state.action_plan = state.validated_pending_action["action_plan"]
    append_node_trace(
        state,
        services,
        node_name="restore_action_plan_node",
        event_type="action_plan_restored",
        input_json={"pending_action_id": state.pending_action_id},
        output_json={"action_plan": state.action_plan.to_dict()},
        summary=f"action={state.action_plan.action}",
    )
    return state


def policy_recheck_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    if state.action_plan is None:
        state.final_status = "PENDING_ACTION_INVALID"
        state.add_error("PENDING_ACTION_INVALID", "缺少 ActionPlan", "policy_recheck_node")
        return state
    services.pending_action_service.mark_confirmed(state.pending_action_id)
    policy_decision = evaluate_policy(
        services.policy_service,
        state.action_plan,
        customer_user_id=state.user_id,
        audit_context=PolicyAuditContext(
            run_id=state.run_id,
            request_id=state.request_id,
            session_id=state.session_id,
            user_id=state.user_id,
        ),
    )
    state.policy_decision = policy_decision
    append_node_trace(
        state,
        services,
        node_name="policy_recheck_node",
        event_type="policy_rechecked",
        input_json={"action_plan": state.action_plan.to_dict(), "user_id": state.user_id},
        output_json=policy_decision.to_dict(),
        summary=policy_decision.decision.value,
    )
    return state


def route_after_policy_recheck_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> str:
    route = (
        state.policy_decision.decision.value
        if state.policy_decision
        else "WORKFLOW_FAILED"
    )
    append_node_trace(
        state,
        services,
        node_name="route_after_policy_recheck_node",
        event_type="confirm_route_selected",
        input_json={
            "policy_decision": (
                state.policy_decision.to_dict() if state.policy_decision else None
            )
        },
        output_json={"route": route},
        summary=f"route={route}",
    )
    return route


def confirm_tool_gateway_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    if state.action_plan is None or state.policy_decision is None:
        state.final_status = "WORKFLOW_FAILED"
        state.add_error("WORKFLOW_FAILED", "确认工具节点缺少必要上下文", "confirm_tool_gateway_node")
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
        node_name="confirm_tool_gateway_node",
        event_type="confirm_tool_called",
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


def confirm_failure_handler_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    if state.tool_result is None:
        state.final_status = "WORKFLOW_FAILED"
        state.add_error("WORKFLOW_FAILED", "缺少 ToolResult", "confirm_failure_handler_node")
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
    if failure_result.status in {
        FailureHandlingStatus.NO_FAILURE,
        FailureHandlingStatus.RECOVERED,
    }:
        state.tool_result = failure_result.final_tool_result
        services.pending_action_service.mark_executed(state.pending_action_id)
        state.final_status = PendingActionService.STATUS_EXECUTED
    else:
        state.tool_result = failure_result.final_tool_result
        state.final_status = "TOOL_FAILED"

    append_node_trace(
        state,
        services,
        node_name="confirm_failure_handler_node",
        event_type="confirm_failure_handled",
        input_json={"tool_result": state.tool_result.to_dict()},
        output_json=failure_result.to_dict(),
        status="SUCCESS" if state.final_status == PendingActionService.STATUS_EXECUTED else "FAILED",
        error_type=None if state.final_status == PendingActionService.STATUS_EXECUTED else state.final_status,
        summary=failure_result.status.value,
    )
    return state


def confirm_cancel_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    services.pending_action_service.mark_cancelled(state.pending_action_id)
    state.final_status = PendingActionService.STATUS_CANCELLED
    append_node_trace(
        state,
        services,
        node_name="confirm_cancel_node",
        event_type="confirm_cancelled",
        input_json={"pending_action_id": state.pending_action_id},
        output_json={"status": state.final_status},
        summary="confirm cancelled",
    )
    return state


def confirm_deny_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    state.final_status = PolicyDecisionType.DENY.value
    append_node_trace(
        state,
        services,
        node_name="confirm_deny_node",
        event_type="confirm_denied",
        input_json={
            "policy_decision": (
                state.policy_decision.to_dict() if state.policy_decision else None
            )
        },
        output_json={"status": state.final_status},
        summary="confirm denied",
    )
    return state


def confirm_human_required_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    state.final_status = PolicyDecisionType.HUMAN_REQUIRED.value
    append_node_trace(
        state,
        services,
        node_name="confirm_human_required_node",
        event_type="confirm_human_required",
        input_json={
            "policy_decision": (
                state.policy_decision.to_dict() if state.policy_decision else None
            )
        },
        output_json={"status": state.final_status},
        summary="confirm human required",
    )
    return state


def confirm_safe_stop_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    state.final_status = PolicyDecisionType.HUMAN_REQUIRED.value
    append_node_trace(
        state,
        services,
        node_name="confirm_safe_stop_node",
        event_type="confirm_safe_stopped",
        input_json={
            "policy_decision": (
                state.policy_decision.to_dict() if state.policy_decision else None
            )
        },
        output_json={
            "status": state.final_status,
            "reason": "二次复核仍需确认，已安全停止并转人工处理",
        },
        summary="confirm safe stopped",
    )
    return state


def confirm_response_generation_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    state.final_response = _build_confirm_response(state)
    append_node_trace(
        state,
        services,
        node_name="confirm_response_generation_node",
        event_type="confirm_response_generated",
        input_json={"final_status": state.final_status},
        output_json={"final_response": state.final_response},
        summary=state.final_status or "UNKNOWN",
    )
    return state


def confirm_finish_node(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    failed_statuses = {
        "PENDING_ACTION_NOT_FOUND",
        "PENDING_ACTION_INVALID",
        "PENDING_ACTION_EXPIRED",
        "PENDING_ACTION_PERMISSION_DENIED",
        "PENDING_ACTION_SESSION_MISMATCH",
        "TOOL_FAILED",
        "WORKFLOW_FAILED",
    }
    is_failed = state.final_status in failed_statuses
    append_node_trace(
        state,
        services,
        node_name="confirm_finish_node",
        event_type="confirm_workflow_failed" if is_failed else "confirm_workflow_finished",
        input_json={"final_status": state.final_status},
        output_json={"final_response": state.final_response},
        status="FAILED" if is_failed else "SUCCESS",
        error_type=state.final_status if is_failed else None,
        summary=state.final_status or "UNKNOWN",
    )
    if is_failed:
        services.trace_service.fail_run(state.run_id, state.final_status or "WORKFLOW_FAILED")
    else:
        services.trace_service.finish_run(state.run_id)
    return state


def _trace_pending_validation(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
    status: str,
    error_type: str | None,
) -> ConfirmWorkflowState:
    append_node_trace(
        state,
        services,
        node_name="validate_pending_action_node",
        event_type="pending_action_validated",
        input_json={
            "pending_action_id": state.pending_action_id,
            "user_id": state.user_id,
            "session_id": state.session_id,
        },
        output_json={
            "status": state.final_status or "VALID",
            "source_run_id": (
                state.validated_pending_action.get("source_run_id")
                if state.validated_pending_action
                else None
            ),
        },
        status=status,
        error_type=error_type,
        summary=state.final_status or "VALID",
    )
    return state


def _finish_after_response(
    state: ConfirmWorkflowState,
    services: ConfirmWorkflowServices,
) -> ConfirmWorkflowState:
    confirm_response_generation_node(state, services)
    return confirm_finish_node(state, services)


def _is_terminal_validation_status(state: ConfirmWorkflowState) -> bool:
    return state.final_status in {
        "PENDING_ACTION_NOT_FOUND",
        "PENDING_ACTION_INVALID",
        "PENDING_ACTION_EXPIRED",
        "PENDING_ACTION_PERMISSION_DENIED",
        "PENDING_ACTION_SESSION_MISMATCH",
    }


def _build_confirm_response(state: ConfirmWorkflowState) -> str:
    if state.final_status == PendingActionService.STATUS_EXECUTED:
        return "确认动作已执行"
    if state.final_status == PendingActionService.STATUS_CANCELLED:
        return "已取消该操作"
    if state.final_status == PolicyDecisionType.DENY.value:
        return "策略复核未通过，未执行该操作"
    if state.final_status == PolicyDecisionType.HUMAN_REQUIRED.value:
        return "该确认动作需要人工处理，未自动执行"
    if state.final_status == "TOOL_FAILED":
        return "确认动作执行失败"
    if state.error_message:
        return state.error_message
    return "确认流程已安全停止处理"


def build_default_failure_handler_from_tool_gateway(
    tool_gateway: ToolGateway,
) -> FailureHandler:
    db_path = getattr(tool_gateway, "db_path", None)
    return FailureHandler(db_path=Path(db_path) if db_path else None)
