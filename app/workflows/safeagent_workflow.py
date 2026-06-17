from collections.abc import Sequence

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
    pending_action_node,
    planner_node,
    policy_node,
    response_generation_node,
    route_by_policy_node,
    tool_gateway_node,
)
from app.workflows.safeagent_state import SafeAgentWorkflowState
from app.workflows.service_adapters import SafeAgentWorkflowServices


class SafeAgentWorkflow:
    """LangGraph-style 轻量 Workflow 执行器。

    当前阶段不引入真实 LangGraph 依赖，只把 P0 主流程拆成可独立测试的
    节点闭环。后续接入 LangGraph 时，应保留这些节点的 service 边界。
    """

    NODE_NAMES: Sequence[str] = (
        "mode_router_node",
        "intent_node",
        "planner_node",
        "llm_output_guard_node",
        "action_plan_validator_node",
        "policy_node",
        "route_by_policy_node",
        "tool_gateway_node",
        "pending_action_node",
        "human_required_node",
        "deny_node",
        "failure_handler_node",
        "response_generation_node",
        "llm_response_guard_node",
        "finish_node",
    )

    def __init__(self, services: SafeAgentWorkflowServices) -> None:
        self.services = services

    @property
    def node_names(self) -> list[str]:
        return list(self.NODE_NAMES)

    def run(
        self,
        session_id: str,
        user_id: str,
        message: str,
        parent_run_id: str | None = None,
        tenant_id: str | None = None,
    ) -> SafeAgentWorkflowState:
        """独立运行一次 workflow，不接入 /api/chat。"""
        request_id = generate_request_id()
        run_id = self.services.trace_service.start_run(
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
        append_node_trace(
            state,
            self.services,
            node_name="workflow_start_node",
            event_type="workflow_started",
            input_json={
                "session_id": session_id,
                "user_id": user_id,
                "message": message,
            },
            output_json={"run_id": run_id, "request_id": request_id},
            summary="workflow started",
        )
        try:
            return self._run_nodes(state)
        except Exception as exc:
            # Workflow 层只记录安全错误摘要，不保存异常栈。
            state.final_status = "WORKFLOW_FAILED"
            state.final_response = "Workflow 已安全停止处理"
            state.add_error("WORKFLOW_FAILED", str(exc), "safeagent_workflow")
            append_node_trace(
                state,
                self.services,
                node_name="workflow_exception_node",
                event_type="workflow_failed",
                input_json={"final_status": state.final_status},
                output_json={"error_type": "WORKFLOW_FAILED"},
                status="FAILED",
                error_type="WORKFLOW_FAILED",
                summary="workflow failed",
            )
            self.services.trace_service.fail_run(state.run_id, "WORKFLOW_FAILED")
            return state

    def _run_nodes(self, state: SafeAgentWorkflowState) -> SafeAgentWorkflowState:
        intent_node(state, self.services)
        planner_node(state, self.services)
        action_plan_validator_node(state, self.services)
        if state.final_status == "PLAN_INVALID":
            response_generation_node(state, self.services)
            return finish_node(state, self.services)

        policy_node(state, self.services)
        route = route_by_policy_node(state, self.services)

        if route == PolicyDecisionType.ALLOW.value:
            tool_gateway_node(state, self.services)
            failure_handler_node(state, self.services)
        elif route == PolicyDecisionType.CONFIRM_REQUIRED.value:
            pending_action_node(state, self.services)
        elif route == PolicyDecisionType.HUMAN_REQUIRED.value:
            human_required_node(state, self.services)
        elif route == PolicyDecisionType.DENY.value:
            deny_node(state, self.services)
        else:
            state.final_status = "WORKFLOW_FAILED"
            state.add_error("WORKFLOW_FAILED", f"未知策略路由: {route}", "route_by_policy_node")

        response_generation_node(state, self.services)
        return finish_node(state, self.services)


def build_safeagent_workflow(
    services: SafeAgentWorkflowServices | None = None,
) -> SafeAgentWorkflow:
    """创建独立 Workflow runner。"""
    return SafeAgentWorkflow(services or SafeAgentWorkflowServices.create_default())

