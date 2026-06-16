from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.action_plan_validator import ActionPlanValidator
from app.core.constants import PolicyDecisionType
from app.core.failure_result import FailureHandlingStatus
from app.core.ids import generate_request_id
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.pending_action_service import PendingActionService
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService


router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str


def get_trace_service() -> TraceService:
    return TraceService()


def get_intent_classifier() -> RuleBasedIntentClassifier:
    return RuleBasedIntentClassifier()


def get_action_planner() -> RuleBasedActionPlanner:
    return RuleBasedActionPlanner()


def get_action_plan_validator() -> ActionPlanValidator:
    return ActionPlanValidator()


def get_policy_service() -> PolicyService:
    return PolicyService()


def get_tool_gateway() -> ToolGateway:
    return ToolGateway()


def get_failure_handler() -> FailureHandler:
    return FailureHandler()


def get_pending_action_service() -> PendingActionService:
    return PendingActionService()


@router.post("/chat")
def chat(
    request: ChatRequest,
    trace_service: TraceService = Depends(get_trace_service),
    intent_classifier: RuleBasedIntentClassifier = Depends(get_intent_classifier),
    action_planner: RuleBasedActionPlanner = Depends(get_action_planner),
    action_plan_validator: ActionPlanValidator = Depends(get_action_plan_validator),
    policy_service: PolicyService = Depends(get_policy_service),
    tool_gateway: ToolGateway = Depends(get_tool_gateway),
    failure_handler: FailureHandler = Depends(get_failure_handler),
    pending_action_service: PendingActionService = Depends(get_pending_action_service),
) -> dict[str, Any]:
    """P0 Rule Mode 的最小 Agent 主闭环。

    本接口只串联已有确定性模块:Intent -> Planner -> Validator -> Policy ->
    ToolGateway/PendingAction。它不使用 LangGraph、不调用 LLM、不做真实 RAG，
    也不直接调用任何 Mock Tool。
    """
    # 每次用户请求都创建独立 run，后续所有 Trace、工具日志和失败日志都挂到该 run。
    request_id = generate_request_id()
    run_id = trace_service.start_run(
        session_id=request.session_id,
        user_id=request.user_id,
        request_id=request_id,
    )

    # 1. 意图识别只做文本分类，不做权限判断，也不决定是否执行动作。
    intent = intent_classifier.classify(request.message)
    trace_service.append_trace(
        run_id=run_id,
        node_name="intent_classification",
        input_json={"message": request.message},
        output_json={"intent": intent},
    )

    # 2. Planner 生成候选 ActionPlan。此时计划仍不可信，后续必须经过 Validator。
    action_plan = action_planner.plan(intent=intent, message=request.message)
    trace_service.append_trace(
        run_id=run_id,
        node_name="action_planning",
        input_json={"intent": intent, "message": request.message},
        output_json={"action_plan": action_plan.to_dict()},
    )

    # 3. Validator 只校验计划结构；失败时必须在 PolicyService 之前截断链路。
    validation_result = action_plan_validator.validate(action_plan)
    trace_service.append_trace(
        run_id=run_id,
        node_name="action_plan_validation",
        input_json={"action_plan": action_plan.to_dict()},
        output_json={
            "status": validation_result.status.value,
            "reason": validation_result.reason,
        },
        status="SUCCESS" if validation_result.is_valid else "FAILED",
        error_type=None if validation_result.is_valid else validation_result.status.value,
    )
    if not validation_result.is_valid:
        # 结构非法不进入权限裁决，也不允许调用任何业务工具。
        trace_service.finish_run(run_id)
        return _base_response(
            request_id=request_id,
            run_id=run_id,
            status="PLAN_INVALID",
            intent=intent,
            action=action_plan.action,
            message="计划结构校验失败，无法继续处理",
            validation_result={
                "status": validation_result.status.value,
                "reason": validation_result.reason,
            },
        )

    # 4. PolicyService 是权限与风险的可信裁决边界，LLM/Planner 不能绕过它。
    policy_decision = policy_service.evaluate(
        action_plan,
        customer_user_id=request.user_id,
    )
    trace_service.append_trace(
        run_id=run_id,
        node_name="policy_decision",
        input_json={"action_plan": action_plan.to_dict(), "user_id": request.user_id},
        output_json=policy_decision.to_dict(),
    )

    if policy_decision.decision == PolicyDecisionType.DENY:
        # DENY 表示明确禁止执行，必须直接返回，不能再触碰 ToolGateway。
        trace_service.finish_run(run_id)
        return _base_response(
            request_id=request_id,
            run_id=run_id,
            status=PolicyDecisionType.DENY.value,
            intent=intent,
            action=action_plan.action,
            policy_decision=policy_decision.to_dict(),
            message=policy_decision.reason,
        )

    if policy_decision.decision == PolicyDecisionType.CONFIRM_REQUIRED:
        # 中风险动作先固化为 pending_action，等待 /api/confirm 创建新的 run 继续执行。
        pending_action_id = pending_action_service.create_pending_action(
            session_id=request.session_id,
            source_run_id=run_id,
            user_id=request.user_id,
            action_plan=action_plan,
            risk_level=policy_decision.risk_level.value,
        )
        trace_service.append_trace(
            run_id=run_id,
            node_name="pending_action_created",
            input_json={"action_plan": action_plan.to_dict()},
            output_json={
                "pending_action_id": pending_action_id,
                "risk_level": policy_decision.risk_level.value,
            },
        )
        trace_service.finish_run(run_id)
        return _base_response(
            request_id=request_id,
            run_id=run_id,
            status=PolicyDecisionType.CONFIRM_REQUIRED.value,
            intent=intent,
            action=action_plan.action,
            policy_decision=policy_decision.to_dict(),
            pending_action_id=pending_action_id,
            message="该操作需要二次确认",
        )

    if policy_decision.decision == PolicyDecisionType.HUMAN_REQUIRED:
        # P0 暂不自动创建人工工单，先返回人工处理结果，避免扩大工单流转范围。
        trace_service.append_trace(
            run_id=run_id,
            node_name="human_required",
            input_json={"action_plan": action_plan.to_dict()},
            output_json=policy_decision.to_dict(),
        )
        trace_service.finish_run(run_id)
        return _base_response(
            request_id=request_id,
            run_id=run_id,
            status=PolicyDecisionType.HUMAN_REQUIRED.value,
            intent=intent,
            action=action_plan.action,
            policy_decision=policy_decision.to_dict(),
            message="该请求需要人工处理",
        )

    if policy_decision.decision == PolicyDecisionType.ALLOW:
        # 低风险 ALLOW 分支才进入工具网关；具体工具仍由 ToolGateway 白名单路由控制。
        return _execute_allowed_action(
            request=request,
            request_id=request_id,
            run_id=run_id,
            intent=intent,
            action_plan=action_plan,
            policy_decision=policy_decision,
            trace_service=trace_service,
            tool_gateway=tool_gateway,
            failure_handler=failure_handler,
        )

    # 防御式分支：如果后续扩展引入了未知策略值，默认安全失败，不进入工具执行。
    trace_service.append_trace(
        run_id=run_id,
        node_name="policy_decision_invalid",
        input_json={"action_plan": action_plan.to_dict()},
        output_json=policy_decision.to_dict(),
        status="FAILED",
        error_type="POLICY_DECISION_INVALID",
    )
    trace_service.fail_run(run_id, "POLICY_DECISION_INVALID")
    return _base_response(
        request_id=request_id,
        run_id=run_id,
        status="POLICY_DECISION_INVALID",
        intent=intent,
        action=action_plan.action,
        policy_decision=policy_decision.to_dict(),
        message="策略裁决结果异常，已安全停止处理",
    )


def _execute_allowed_action(
    request: ChatRequest,
    request_id: str,
    run_id: str,
    intent: str,
    action_plan,
    policy_decision,
    trace_service: TraceService,
    tool_gateway: ToolGateway,
    failure_handler: FailureHandler,
) -> dict[str, Any]:
    # 主链路必须补齐系统上下文，不能只把 Planner 生成的 tool_args 原样交给工具。
    tool_args = _build_chat_tool_args(
        action_plan=action_plan,
        user_id=request.user_id,
        risk_level=policy_decision.risk_level.value,
        source_run_id=run_id,
    )
    # 所有业务工具调用都必须经过 ToolGateway，以便统一白名单、脱敏和 tool_call_logs。
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
        # 成功结果也交给 FailureHandler 归一化判断；当前不会写 failure_logs。
        failure_handler.handle_tool_result(
            run_id=run_id,
            session_id=request.session_id,
            tool_result=tool_result,
        )
        trace_service.finish_run(run_id)
        return _base_response(
            request_id=request_id,
            run_id=run_id,
            status="SUCCESS",
            intent=intent,
            action=action_plan.action,
            policy_decision=policy_decision.to_dict(),
            tool_result=tool_result.to_dict(),
            message=tool_result.summary,
        )

    # 工具失败时只允许 FailureHandler 通过 ToolGateway 重试，不能直接调用 Mock Tool。
    failure_result = failure_handler.handle_with_retry(
        run_id=run_id,
        session_id=request.session_id,
        tool_name=action_plan.tool_name or "",
        tool_args=tool_args,
        first_result=tool_result,
        tool_gateway=tool_gateway,
    )
    if failure_result.status == FailureHandlingStatus.RECOVERED:
        # 重试恢复成功仍属于同一个 run，不创建新的 run_id。
        trace_service.finish_run(run_id)
        return _base_response(
            request_id=request_id,
            run_id=run_id,
            status="RECOVERED",
            intent=intent,
            action=action_plan.action,
            policy_decision=policy_decision.to_dict(),
            tool_result=failure_result.final_tool_result.to_dict(),
            failure_result=failure_result.to_dict(),
            message=failure_result.final_tool_result.summary,
        )

    # 重试后仍失败，关闭 run 生命周期并返回工具失败结果。
    trace_service.fail_run(run_id, failure_result.final_tool_result.error_type or "TOOL_FAILED")
    return _base_response(
        request_id=request_id,
        run_id=run_id,
        status="TOOL_FAILED",
        intent=intent,
        action=action_plan.action,
        policy_decision=policy_decision.to_dict(),
        tool_result=failure_result.final_tool_result.to_dict(),
        failure_result=failure_result.to_dict(),
        message="工具调用失败",
    )


def _build_chat_tool_args(
    action_plan,
    user_id: str,
    risk_level: str,
    source_run_id: str,
) -> dict[str, Any]:
    # action_plan.tool_args 来自 Planner，只能作为候选参数；这里补系统可信上下文。
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


def _base_response(
    request_id: str,
    run_id: str,
    status: str,
    intent: str,
    action: str,
    message: str,
    policy_decision: dict[str, Any] | None = None,
    tool_result: dict[str, Any] | None = None,
    pending_action_id: str | None = None,
    validation_result: dict[str, Any] | None = None,
    failure_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "run_id": run_id,
        "status": status,
        "intent": intent,
        "action": action,
        "policy_decision": policy_decision,
        "tool_result": tool_result,
        "pending_action_id": pending_action_id,
        "validation_result": validation_result,
        "failure_result": failure_result,
        "message": message,
    }
