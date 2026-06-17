from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.constants import PolicyDecisionType
from app.core.ids import generate_request_id
from app.workflows.safeagent_nodes import (
    action_plan_validator_node,
    append_node_trace,
    deny_node,
    failure_handler_node,
    finish_node,
    human_required_node,
    intent_node,
    llm_output_guard_node,
    llm_response_guard_node,
    pending_action_node,
    planner_node,
    policy_node,
    response_generation_node,
    route_by_policy_node,
    tool_gateway_node,
)
from app.workflows.safeagent_state import SafeAgentWorkflowState
from app.workflows.service_adapters import SafeAgentWorkflowServices


class LangGraphChatState(TypedDict, total=False):
    """真实 LangGraph 内部状态包装。

    业务状态仍复用 SafeAgentWorkflowState。route 只服务于 LangGraph
    条件边，不作为权限裁决或审计事实来源。
    """

    state: SafeAgentWorkflowState
    route: str


def build_langgraph_chat_workflow(services: SafeAgentWorkflowServices):
    """构建真实 LangGraph chat workflow。

    LangGraph 只负责编排节点顺序和条件路由；节点内部仍复用当前
    safeagent_nodes 的确定性服务调用，不复制 PolicyService、ToolGateway
    或 FailureHandler 业务逻辑。
    """
    graph = StateGraph(LangGraphChatState)

    graph.add_node("workflow_start_node", _workflow_start_wrapper(services))
    graph.add_node("intent_node", _wrap_state_node(intent_node, services))
    graph.add_node("planner_node", _wrap_state_node(planner_node, services))
    graph.add_node(
        "llm_output_guard_node",
        _wrap_state_node(llm_output_guard_node, services),
    )
    graph.add_node(
        "action_plan_validator_node",
        _wrap_state_node(action_plan_validator_node, services),
    )
    graph.add_node("policy_node", _wrap_state_node(policy_node, services))
    graph.add_node("route_by_policy_node", _route_by_policy_wrapper(services))
    graph.add_node("tool_gateway_node", _wrap_state_node(tool_gateway_node, services))
    graph.add_node(
        "failure_handler_node",
        _wrap_state_node(failure_handler_node, services),
    )
    graph.add_node(
        "pending_action_node",
        _wrap_state_node(pending_action_node, services),
    )
    graph.add_node(
        "human_required_node",
        _wrap_state_node(human_required_node, services),
    )
    graph.add_node("deny_node", _wrap_state_node(deny_node, services))
    graph.add_node("workflow_failed_node", _workflow_failed_wrapper(services))
    graph.add_node(
        "response_generation_node",
        _wrap_state_node(response_generation_node, services),
    )
    graph.add_node(
        "llm_response_guard_node",
        _wrap_state_node(llm_response_guard_node, services),
    )
    graph.add_node("finish_node", _wrap_state_node(finish_node, services))

    graph.add_edge(START, "workflow_start_node")
    graph.add_edge("workflow_start_node", "intent_node")
    graph.add_edge("intent_node", "planner_node")
    graph.add_edge("planner_node", "llm_output_guard_node")
    graph.add_edge("llm_output_guard_node", "action_plan_validator_node")
    graph.add_conditional_edges(
        "action_plan_validator_node",
        _route_after_validation,
        {
            "PLAN_INVALID": "response_generation_node",
            "VALID": "policy_node",
        },
    )
    graph.add_edge("policy_node", "route_by_policy_node")
    graph.add_conditional_edges(
        "route_by_policy_node",
        _route_after_policy,
        {
            PolicyDecisionType.ALLOW.value: "tool_gateway_node",
            PolicyDecisionType.CONFIRM_REQUIRED.value: "pending_action_node",
            PolicyDecisionType.HUMAN_REQUIRED.value: "human_required_node",
            PolicyDecisionType.DENY.value: "deny_node",
            "WORKFLOW_FAILED": "workflow_failed_node",
        },
    )
    graph.add_edge("tool_gateway_node", "failure_handler_node")
    graph.add_edge("failure_handler_node", "response_generation_node")
    graph.add_edge("pending_action_node", "response_generation_node")
    graph.add_edge("human_required_node", "response_generation_node")
    graph.add_edge("deny_node", "response_generation_node")
    graph.add_edge("workflow_failed_node", "response_generation_node")
    graph.add_edge("response_generation_node", "llm_response_guard_node")
    graph.add_edge("llm_response_guard_node", "finish_node")
    graph.add_edge("finish_node", END)

    return graph.compile()


def run_langgraph_chat_workflow(
    *,
    session_id: str,
    user_id: str,
    message: str,
    services: SafeAgentWorkflowServices,
    tenant_id: str | None = None,
    parent_run_id: str | None = None,
) -> SafeAgentWorkflowState:
    """运行一次真实 LangGraph chat workflow。"""
    request_id = generate_request_id()
    run_id = services.trace_service.start_run(
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        parent_run_id=parent_run_id,
    )
    state = SafeAgentWorkflowState(
        request_id=request_id,
        run_id=run_id,
        parent_run_id=parent_run_id,
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        message=message,
    )
    workflow = build_langgraph_chat_workflow(services)
    result: LangGraphChatState = workflow.invoke({"state": state})
    return result["state"]


def _workflow_start_wrapper(services: SafeAgentWorkflowServices):
    def wrapped(payload: LangGraphChatState) -> LangGraphChatState:
        state = payload["state"]
        append_node_trace(
            state,
            services,
            node_name="workflow_start_node",
            event_type="workflow_started",
            input_json={
                "session_id": state.session_id,
                "user_id": state.user_id,
                "message": state.message,
                "engine": "langgraph",
            },
            output_json={"run_id": state.run_id, "request_id": state.request_id},
            summary="langgraph workflow started",
        )
        return {"state": state}

    return wrapped


def _wrap_state_node(node_func, services: SafeAgentWorkflowServices):
    def wrapped(payload: LangGraphChatState) -> LangGraphChatState:
        state = payload["state"]
        node_func(state, services)
        return {"state": state}

    return wrapped


def _route_by_policy_wrapper(services: SafeAgentWorkflowServices):
    def wrapped(payload: LangGraphChatState) -> LangGraphChatState:
        state = payload["state"]
        route = route_by_policy_node(state, services)
        if route not in {
            PolicyDecisionType.ALLOW.value,
            PolicyDecisionType.CONFIRM_REQUIRED.value,
            PolicyDecisionType.HUMAN_REQUIRED.value,
            PolicyDecisionType.DENY.value,
        }:
            route = "WORKFLOW_FAILED"
        return {"state": state, "route": route}

    return wrapped


def _workflow_failed_wrapper(services: SafeAgentWorkflowServices):
    def wrapped(payload: LangGraphChatState) -> LangGraphChatState:
        state = payload["state"]
        state.final_status = "WORKFLOW_FAILED"
        state.add_error(
            "WORKFLOW_FAILED",
            "LangGraph policy route failed",
            "workflow_failed_node",
        )
        append_node_trace(
            state,
            services,
            node_name="workflow_failed_node",
            event_type="workflow_failed",
            input_json={"route": payload.get("route")},
            output_json={"final_status": state.final_status},
            status="FAILED",
            error_type="WORKFLOW_FAILED",
            summary="langgraph workflow failed",
        )
        return {"state": state}

    return wrapped


def _route_after_validation(payload: LangGraphChatState) -> str:
    state = payload["state"]
    if state.final_status == "PLAN_INVALID":
        return "PLAN_INVALID"
    return "VALID"


def _route_after_policy(payload: LangGraphChatState) -> str:
    return payload.get("route") or "WORKFLOW_FAILED"
