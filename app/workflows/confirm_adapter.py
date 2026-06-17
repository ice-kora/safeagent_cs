from typing import Any

from fastapi import HTTPException

from app.workflows.confirm_workflow import (
    ConfirmWorkflowServices,
    ConfirmWorkflowState,
    build_confirm_workflow,
    build_default_failure_handler_from_tool_gateway,
)


def handle_workflow_confirm(
    request: Any,
    services: ConfirmWorkflowServices,
) -> dict[str, Any]:
    """把 /api/confirm 请求映射到 confirm_workflow。"""
    workflow = build_confirm_workflow(services)
    state = workflow.run(
        pending_action_id=request.pending_action_id,
        user_id=request.user_id,
        session_id=request.session_id,
        confirm=request.confirm,
    )
    _raise_for_invalid_pending_action(state)
    return confirm_state_to_response(state)


def build_confirm_workflow_services(
    pending_action_service,
    trace_service,
    policy_service,
    tool_gateway,
) -> ConfirmWorkflowServices:
    return ConfirmWorkflowServices(
        pending_action_service=pending_action_service,
        trace_service=trace_service,
        policy_service=policy_service,
        tool_gateway=tool_gateway,
        failure_handler=build_default_failure_handler_from_tool_gateway(tool_gateway),
    )


def confirm_state_to_response(state: ConfirmWorkflowState) -> dict[str, Any]:
    response = {
        "request_id": state.request_id,
        "run_id": state.run_id,
        "parent_run_id": state.parent_run_id,
        "pending_action_id": state.pending_action_id,
        "status": state.final_status,
        "message": state.final_response or "确认流程已安全停止处理",
    }
    if state.policy_decision:
        response["policy_decision"] = state.policy_decision.to_dict()
    if state.tool_result:
        response["tool_result"] = state.tool_result.to_dict()
    if state.failure_result:
        response["failure_result"] = state.failure_result.to_dict()
    return response


def _raise_for_invalid_pending_action(state: ConfirmWorkflowState) -> None:
    if state.final_status == "PENDING_ACTION_PERMISSION_DENIED":
        raise HTTPException(status_code=403, detail=state.error_message)
    if state.final_status == "PENDING_ACTION_SESSION_MISMATCH":
        raise HTTPException(status_code=403, detail=state.error_message)
    if state.final_status in {
        "PENDING_ACTION_NOT_FOUND",
        "PENDING_ACTION_INVALID",
        "PENDING_ACTION_EXPIRED",
    }:
        raise HTTPException(status_code=400, detail=state.error_message)

