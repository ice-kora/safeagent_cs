from app.core.action_plan import ActionPlan
from app.core.extractors import extract_order_id


class RuleBasedActionPlanner:
    """规则型 ActionPlan 生成器。

    Planner 只把 intent 转成候选执行计划，不判断计划是否安全。
    例如订单号缺失时仍会生成 target_id=None 的计划，下一阶段由
    ActionPlanValidator 识别参数缺失。
    """

    def plan(self, intent: str, message: str) -> ActionPlan:
        order_id = extract_order_id(message)
        if intent == "policy_query":
            return self._plan_policy_query(message)
        if intent == "order_query":
            return self._plan_order_query(order_id)
        if intent == "address_change":
            return self._plan_address_change(order_id, message)
        if intent == "refund_request":
            return self._plan_refund_request(order_id, message)
        if intent == "complaint":
            return self._plan_complaint(message)
        if intent == "prompt_injection":
            return self._plan_prompt_injection(message)
        return self._plan_unknown(intent, message)

    @staticmethod
    def _plan_policy_query(message: str) -> ActionPlan:
        return ActionPlan(
            intent="policy_query",
            action="query_policy",
            target_type="policy",
            target_id=None,
            tool_name="knowledge_tool.query_policy",
            tool_args={"query": message},
            reason="用户询问公开政策，进入静态知识库查询。",
        )

    @staticmethod
    def _plan_order_query(order_id: str | None) -> ActionPlan:
        return ActionPlan(
            intent="order_query",
            action="query_order",
            target_type="order",
            target_id=order_id,
            tool_name="order_tool.query_order",
            tool_args={"order_id": order_id},
            reason="用户查询订单状态，需要后续校验订单归属。",
        )

    @staticmethod
    def _plan_address_change(order_id: str | None, message: str) -> ActionPlan:
        return ActionPlan(
            intent="address_change",
            action="change_address",
            target_type="order",
            target_id=order_id,
            tool_name="order_tool.change_address",
            tool_args={
                "order_id": order_id,
                "raw_message": message,
            },
            reason="用户请求修改地址，后续应走中风险二次确认。",
        )

    @staticmethod
    def _plan_refund_request(order_id: str | None, message: str) -> ActionPlan:
        return ActionPlan(
            intent="refund_request",
            action="request_refund",
            target_type="order",
            target_id=order_id,
            tool_name="ticket_tool.create_ticket",
            tool_args={
                "ticket_type": "refund",
                "order_id": order_id,
                "description": message,
            },
            reason="用户申请退款，后续应由策略层转人工工单。",
        )

    @staticmethod
    def _plan_complaint(message: str) -> ActionPlan:
        return ActionPlan(
            intent="complaint",
            action="create_complaint_ticket",
            target_type="ticket",
            target_id=None,
            tool_name="ticket_tool.create_ticket",
            tool_args={
                "ticket_type": "complaint",
                "description": message,
            },
            reason="用户发起投诉，后续应创建高风险投诉工单。",
        )

    @staticmethod
    def _plan_prompt_injection(message: str) -> ActionPlan:
        return ActionPlan(
            intent="prompt_injection",
            action="security_risk",
            target_type="security",
            target_id=None,
            tool_name=None,
            tool_args={"raw_message": message},
            reason="用户输入包含安全攻击特征，不应调用业务工具。",
        )

    @staticmethod
    def _plan_unknown(intent: str, message: str) -> ActionPlan:
        return ActionPlan(
            intent=intent if intent else "unknown",
            action="unknown_action",
            target_type=None,
            target_id=None,
            tool_name=None,
            tool_args={"raw_message": message},
            reason="规则无法识别用户意图，交由后续 Validator 或回复层处理。",
        )
