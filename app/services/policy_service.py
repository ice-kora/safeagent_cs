from app.core.action_plan import ActionPlan
from app.core.constants import PolicyDecisionType
from app.core.policy import PolicyDecision
from app.core.risk import RiskLevel
from app.services.repository_service import RepositoryService


class PolicyService:
    """权限与风险裁决服务。

    PolicyService 是 ActionPlan 之后的可信边界：它可以读取只读权限上下文，
    判断当前用户能不能继续这个计划，但不能调用业务工具、修改订单或创建工单。

    P0 阶段是客户自助客服入口，customer_user_id 表示当前登录客户 ID，
    不是客服人员 ID。本阶段只做客户本人资源归属校验，防止 A 客户访问
    B 客户订单。

    身份语义：
    - customer_user_id：当前发起咨询的客户/买家 ID。
    - merchant_tenant_id：订单所属商家/租户 ID。
    - session_tenant_id：当前客服入口所属商家/租户 ID。
    - support_agent_id / actor_id / actor_role：客服后台操作身份，P0 不实现。

    TODO: 当策略规则超过 8~10 个，或引入客服/主管/管理员角色权限时，
    将当前 if/elif 裁决拆成 PolicyRuleRegistry + BasePolicyRule +
    独立规则类。PolicyRule 仍是确定性代码规则，不是 MCP Tool，
    也不是 LLM Agent。
    """

    SHIPPED_DELIVERY_STATUSES = {"SHIPPED", "DELIVERED"}

    def __init__(self, repository: RepositoryService | None = None) -> None:
        self.repository = repository or RepositoryService()

    def evaluate(
        self,
        action_plan: ActionPlan,
        customer_user_id: str,
    ) -> PolicyDecision:
        """对候选计划做真实权限与风险裁决。"""
        action = action_plan.action
        if action == "query_policy":
            return self._allow(RiskLevel.L1, "公开政策查询允许执行")
        if action == "query_order":
            return self._evaluate_query_order(action_plan, customer_user_id)
        if action == "change_address":
            return self._evaluate_change_address(action_plan, customer_user_id)
        if action == "request_refund":
            return self._evaluate_request_refund(action_plan, customer_user_id)
        if action == "create_complaint_ticket":
            return self._human_required(RiskLevel.L4, "投诉属于高风险诉求，需要人工处理")
        if action == "security_risk" or action_plan.intent == "prompt_injection":
            return self._deny(RiskLevel.L5, "检测到安全风险请求，拒绝执行")
        return self._deny(RiskLevel.L5, "未知动作默认拒绝")

    def _evaluate_query_order(
        self,
        action_plan: ActionPlan,
        customer_user_id: str,
    ) -> PolicyDecision:
        auth_result = self._load_order_auth_context(action_plan, customer_user_id)
        if isinstance(auth_result, PolicyDecision):
            return auth_result
        return self._allow(RiskLevel.L2, "订单属于当前用户，允许查询")

    def _evaluate_change_address(
        self,
        action_plan: ActionPlan,
        customer_user_id: str,
    ) -> PolicyDecision:
        auth_result = self._load_order_auth_context(action_plan, customer_user_id)
        if isinstance(auth_result, PolicyDecision):
            return auth_result

        delivery_status = auth_result.get("delivery_status")
        if delivery_status in self.SHIPPED_DELIVERY_STATUSES:
            return self._human_required(
                RiskLevel.L4,
                "订单已发货或已签收，地址修改需要人工处理",
            )
        return self._confirm_required(RiskLevel.L3, "订单未发货，修改地址需要用户二次确认")

    def _evaluate_request_refund(
        self,
        action_plan: ActionPlan,
        customer_user_id: str,
    ) -> PolicyDecision:
        auth_result = self._load_order_auth_context(action_plan, customer_user_id)
        if isinstance(auth_result, PolicyDecision):
            return auth_result

        idempotency_key = self._build_idempotency_key(action_plan, customer_user_id)
        open_ticket = self.repository.get_open_ticket_by_idempotency_key(idempotency_key)
        if open_ticket:
            return self._human_required(
                RiskLevel.L4,
                f"退款必须人工处理，且已存在未关闭工单: {open_ticket['id']}",
            )
        return self._human_required(RiskLevel.L4, "退款请求必须转人工处理，不能自动执行")

    def _load_order_auth_context(
        self,
        action_plan: ActionPlan,
        customer_user_id: str,
    ) -> dict[str, str] | PolicyDecision:
        """读取订单权限上下文并做归属校验。

        这里只读取 RepositoryService 的最小字段，避免 PolicyService 拿到完整订单。
        customer_user_id 是当前登录客户 ID，不是客服人员 ID。
        P0 判断的是“这个订单是否属于当前客户，且是否在当前商家入口下”。
        """
        order_id = action_plan.target_id or action_plan.tool_args.get("order_id")
        if not order_id:
            return self._deny(RiskLevel.L5, "缺少订单号，拒绝执行")

        user_context = self.repository.get_user_context(customer_user_id)
        if not user_context:
            return self._deny(RiskLevel.L5, "当前用户不存在或无有效上下文")

        order_context = self.repository.get_order_auth_context(order_id)
        if not order_context:
            return self._deny(RiskLevel.L5, "订单不存在，拒绝执行")

        order_customer_user_id = order_context.get("user_id")
        merchant_tenant_id = order_context.get("tenant_id")
        session_tenant_id = user_context.get("tenant_id")

        if order_customer_user_id != customer_user_id:
            return self._deny(RiskLevel.L5, "订单不属于当前用户，拒绝执行")

        # 多租户安全边界必须显式存在，不能让 None == None 被误判为租户一致。
        if not merchant_tenant_id or not session_tenant_id:
            return self._deny(RiskLevel.L5, "租户上下文缺失，拒绝执行")

        if merchant_tenant_id != session_tenant_id:
            return self._deny(RiskLevel.L5, "订单租户与当前用户不一致，拒绝执行")

        return order_context

    @staticmethod
    def _build_idempotency_key(
        action_plan: ActionPlan,
        customer_user_id: str,
    ) -> str:
        return (
            f"{customer_user_id}:{action_plan.action}:"
            f"{action_plan.target_type}:{action_plan.target_id}"
        )

    @staticmethod
    def _allow(risk_level: RiskLevel, reason: str) -> PolicyDecision:
        return PolicyDecision(PolicyDecisionType.ALLOW, risk_level, reason)

    @staticmethod
    def _deny(risk_level: RiskLevel, reason: str) -> PolicyDecision:
        return PolicyDecision(PolicyDecisionType.DENY, risk_level, reason)

    @staticmethod
    def _confirm_required(risk_level: RiskLevel, reason: str) -> PolicyDecision:
        return PolicyDecision(PolicyDecisionType.CONFIRM_REQUIRED, risk_level, reason)

    @staticmethod
    def _human_required(risk_level: RiskLevel, reason: str) -> PolicyDecision:
        return PolicyDecision(PolicyDecisionType.HUMAN_REQUIRED, risk_level, reason)
