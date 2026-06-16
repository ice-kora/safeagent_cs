from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.constants import PolicyDecisionType
from app.core.ids import generate_request_id
from app.services.pending_action_service import (
    PendingActionError,
    PendingActionPermissionError,
    PendingActionService,
)
from app.services.policy_service import PolicyService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService


router = APIRouter()


class ConfirmRequest(BaseModel):
    pending_action_id: str
    user_id: str
    session_id: str
    confirm: bool


def get_pending_action_service() -> PendingActionService:
    return PendingActionService()


def get_trace_service() -> TraceService:
    return TraceService()


def get_policy_service() -> PolicyService:
    return PolicyService()


def get_tool_gateway() -> ToolGateway:
    return ToolGateway()


@router.post("/confirm")
def confirm_pending_action(
    request: ConfirmRequest,
    pending_action_service: PendingActionService = Depends(get_pending_action_service),
    trace_service: TraceService = Depends(get_trace_service),
    policy_service: PolicyService = Depends(get_policy_service),
    tool_gateway: ToolGateway = Depends(get_tool_gateway),
) -> dict[str, Any]:
    """确认或取消 pending_action。

    /api/confirm 是新的用户输入，所以会创建新的 request_id 和 run_id。
    这里不复用原始 run，而是用 parent_run_id 关联触发 CONFIRM_REQUIRED 的
    source_run_id。确认执行前必须重新经过 PolicyService 复核，工具调用也必须
    经过 ToolGateway。
    """
    # 先校验 pending_action 是否存在、是否属于当前用户、是否仍处于 PENDING。
    pending_action = _validate_pending_action(
        pending_action_service=pending_action_service,
        pending_action_id=request.pending_action_id,
        user_id=request.user_id,
    )
    # session_id 也必须匹配，避免同一用户在不同会话里确认不属于当前上下文的动作。
    if pending_action["session_id"] != request.session_id:
        raise HTTPException(status_code=403, detail="pending_action session 不匹配")

    # /api/confirm 是新的用户输入，因此创建新的 request_id/run_id；
    # parent_run_id 用来关联原始触发 CONFIRM_REQUIRED 的 run。
    request_id = generate_request_id()
    parent_run_id = pending_action["source_run_id"]
    run_id = trace_service.start_run(
        session_id=request.session_id,
        user_id=request.user_id,
        request_id=request_id,
        parent_run_id=parent_run_id,
        pending_action_id=request.pending_action_id,
    )

    if not request.confirm:
        # 用户取消时只更新状态和 Trace，不复核策略，也不调用 ToolGateway。
        return _cancel_pending_action(
            request=request,
            pending_action=pending_action,
            request_id=request_id,
            run_id=run_id,
            parent_run_id=parent_run_id,
            pending_action_service=pending_action_service,
            trace_service=trace_service,
        )

    # 用户确认后仍不能直接执行，必须重新走 PolicyService 复核。
    return _execute_confirmed_action(
        request=request,
        pending_action=pending_action,
        request_id=request_id,
        run_id=run_id,
        parent_run_id=parent_run_id,
        pending_action_service=pending_action_service,
        trace_service=trace_service,
        policy_service=policy_service,
        tool_gateway=tool_gateway,
    )


def _validate_pending_action(
    pending_action_service: PendingActionService,
    pending_action_id: str,
    user_id: str,
) -> dict[str, Any]:
    try:
        return pending_action_service.validate_pending_action(
            pending_action_id=pending_action_id,
            user_id=user_id,
        )
    except PendingActionPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PendingActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _cancel_pending_action(
    request: ConfirmRequest,
    pending_action: dict[str, Any],
    request_id: str,
    run_id: str,
    parent_run_id: str,
    pending_action_service: PendingActionService,
    trace_service: TraceService,
) -> dict[str, Any]:
    # 取消分支是一个完整 run，也需要留下 Trace，便于审计用户主动取消动作。
    trace_service.append_trace(
        run_id=run_id,
        node_name="confirm_cancelled",
        input_json=_request_to_dict(request),
        output_json={
            "pending_action_id": request.pending_action_id,
            "source_run_id": pending_action["source_run_id"],
            "status": PendingActionService.STATUS_CANCELLED,
        },
    )
    pending_action_service.mark_cancelled(request.pending_action_id)
    trace_service.finish_run(run_id)
    return {
        "request_id": request_id,
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "pending_action_id": request.pending_action_id,
        "status": PendingActionService.STATUS_CANCELLED,
        "message": "已取消该操作",
    }


def _execute_confirmed_action(
    request: ConfirmRequest,
    pending_action: dict[str, Any],
    request_id: str,
    run_id: str,
    parent_run_id: str,
    pending_action_service: PendingActionService,
    trace_service: TraceService,
    policy_service: PolicyService,
    tool_gateway: ToolGateway,
) -> dict[str, Any]:
    action_plan = pending_action["action_plan"]
    # 记录确认请求进入执行路径，同时保留待执行 ActionPlan 的安全摘要。
    trace_service.append_trace(
        run_id=run_id,
        node_name="confirm_request_received",
        input_json=_request_to_dict(request),
        output_json={
            "pending_action_id": request.pending_action_id,
            "source_run_id": pending_action["source_run_id"],
            "action_plan": action_plan.to_dict(),
        },
    )
    # CONFIRMED 只表示用户确认过，不代表业务动作已经执行成功。
    pending_action_service.mark_confirmed(request.pending_action_id)

    # 二次确认后必须重新复核策略，防止订单状态或权限在等待期间发生变化。
    policy_decision = policy_service.evaluate(
        action_plan,
        customer_user_id=request.user_id,
    )
    trace_service.append_trace(
        run_id=run_id,
        node_name="policy_review_result",
        input_json={"action_plan": action_plan.to_dict(), "user_id": request.user_id},
        output_json=policy_decision.to_dict(),
    )
    if policy_decision.decision not in {
        PolicyDecisionType.ALLOW,
        PolicyDecisionType.CONFIRM_REQUIRED,
    }:
        # 复核未通过时不调用 ToolGateway，pending_action 保持 CONFIRMED 便于审计。
        trace_service.finish_run(run_id)
        return {
            "request_id": request_id,
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "pending_action_id": request.pending_action_id,
            "status": policy_decision.decision.value,
            "policy_decision": policy_decision.to_dict(),
            "message": "策略复核未通过，未执行该操作",
        }

    # 工具调用前补齐系统上下文，避免只依赖 Planner 生成的候选 tool_args。
    tool_args = _build_confirm_tool_args(
        action_plan=action_plan,
        user_id=request.user_id,
        risk_level=policy_decision.risk_level.value,
        source_run_id=run_id,
    )
    # 确认流程也必须经过 ToolGateway，不能直接调用 order_tool/ticket_tool。
    tool_result = tool_gateway.call_tool(
        run_id=run_id,
        session_id=request.session_id,
        tool_name=action_plan.tool_name or "",
        tool_args=tool_args,
    )
    trace_service.append_trace(
        run_id=run_id,
        node_name="tool_gateway_result",
        input_json={
            "tool_name": action_plan.tool_name,
            "tool_args": tool_args,
        },
        output_json=tool_result.to_dict(),
        status="SUCCESS" if tool_result.success else "FAILED",
        error_type=tool_result.error_type,
    )

    if tool_result.success:
        # 只有工具执行成功后，pending_action 才能进入 EXECUTED。
        pending_action_service.mark_executed(request.pending_action_id)
        trace_service.finish_run(run_id)
        status = PendingActionService.STATUS_EXECUTED
        message = "确认动作已执行"
    else:
        # 工具失败时先标记 run 失败；后续可接入 FailureHandler 做降级。
        trace_service.fail_run(run_id, tool_result.error_type or "TOOL_FAILED")
        status = "TOOL_FAILED"
        message = "确认动作执行失败"

    return {
        "request_id": request_id,
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "pending_action_id": request.pending_action_id,
        "status": status,
        "tool_result": tool_result.to_dict(),
        "message": message,
    }


def _build_confirm_tool_args(
    action_plan,
    user_id: str,
    risk_level: str,
    source_run_id: str,
) -> dict[str, Any]:
    # pending action 中的 tool_args 是历史候选参数；确认时补当前 run 的可信上下文。
    tool_args = dict(action_plan.tool_args)
    tool_args.update(
        {
            "user_id": user_id,
            "customer_user_id": user_id,
            "action": action_plan.action,
            "target_type": action_plan.target_type,
            "target_id": action_plan.target_id,
            "risk_level": risk_level,
            "source_run_id": source_run_id,
        }
    )
    return tool_args


def _request_to_dict(request: ConfirmRequest) -> dict[str, Any]:
    return {
        "pending_action_id": request.pending_action_id,
        "user_id": request.user_id,
        "session_id": request.session_id,
        "confirm": request.confirm,
    }
