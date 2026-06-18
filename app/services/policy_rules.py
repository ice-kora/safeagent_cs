from dataclasses import dataclass
from typing import Any, Protocol

from app.core.action_plan import ActionPlan
from app.core.constants import PolicyDecisionType
from app.core.policy import PolicyDecision
from app.core.risk import RiskLevel
from app.core.security_context import (
    SecurityContext,
    build_customer_self_service_context,
)
from app.services.repository_service import RepositoryService


@dataclass(frozen=True)
class PolicyEvaluationContext:
    """策略规则执行上下文。

    这个对象只承载规则裁决需要的最小上下文。规则类可以读取只读
    RepositoryService，但不能执行工具、修改订单或产生业务副作用。
    """

    action_plan: ActionPlan
    customer_user_id: str
    repository: RepositoryService
    security_context: SecurityContext | None = None


class PolicyRule(Protocol):
    """单个确定性策略规则的协议。

    PolicyRule 是普通 Python 规则，不是 Tool、MCP 或 LLM Agent。
    """

    name: str

    def matches(self, context: PolicyEvaluationContext) -> bool:
        ...

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        ...


class BasePolicyRule:
    """策略规则公共基类。

    订单类规则共享同一套资源归属与租户校验，避免每个 action 重复实现
    安全边界。真实权限判断仍然来自 RepositoryService 的只读上下文。
    """

    SHIPPED_DELIVERY_STATUSES = {"SHIPPED", "DELIVERED"}

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

    def _load_order_auth_context(
        self,
        context: PolicyEvaluationContext,
    ) -> dict[str, Any] | PolicyDecision:
        """读取订单权限上下文并完成客户归属、租户归属校验。"""
        action_plan = context.action_plan
        order_id = action_plan.target_id or action_plan.tool_args.get("order_id")
        if not order_id:
            return self._deny(RiskLevel.L5, "缺少订单号，拒绝执行")

        effective_customer_user_id = self._effective_customer_user_id(context)
        user_context = context.repository.get_user_context(effective_customer_user_id)
        if not user_context:
            return self._deny(RiskLevel.L5, "当前用户不存在或无有效上下文")

        security_context = context.security_context or build_customer_self_service_context(
            user_id=effective_customer_user_id,
            tenant_id=user_context.get("tenant_id"),
            session_id=None,
        )
        if not security_context.is_self_service():
            return self._deny(RiskLevel.L5, "当前仅支持客户本人自助操作，拒绝执行")

        order_context = context.repository.get_order_auth_context(order_id)
        if not order_context:
            return self._deny(RiskLevel.L5, "订单不存在，拒绝执行")

        order_customer_user_id = order_context.get("user_id")
        merchant_tenant_id = order_context.get("tenant_id")
        session_tenant_id = security_context.tenant_id

        if order_customer_user_id != security_context.subject_user_id:
            return self._deny(RiskLevel.L5, "订单不属于当前用户，拒绝执行")

        # 多租户安全边界必须显式存在，不能让 None == None 被误判为租户一致。
        if not merchant_tenant_id or not session_tenant_id:
            return self._deny(RiskLevel.L5, "租户上下文缺失，拒绝执行")

        if merchant_tenant_id != session_tenant_id:
            return self._deny(RiskLevel.L5, "订单租户与当前用户不一致，拒绝执行")

        return order_context

    @staticmethod
    def _effective_customer_user_id(context: PolicyEvaluationContext) -> str:
        if context.security_context:
            return context.security_context.subject_user_id
        return context.customer_user_id

    @staticmethod
    def _build_idempotency_key(context: PolicyEvaluationContext) -> str:
        action_plan = context.action_plan
        customer_user_id = BasePolicyRule._effective_customer_user_id(context)
        return (
            f"{customer_user_id}:{action_plan.action}:"
            f"{action_plan.target_type}:{action_plan.target_id}"
        )


class QueryPolicyRule(BasePolicyRule):
    name = "query_policy"

    def matches(self, context: PolicyEvaluationContext) -> bool:
        return context.action_plan.action == "query_policy"

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        return self._allow(RiskLevel.L1, "公开政策查询允许执行")


class QueryOrderRule(BasePolicyRule):
    name = "query_order"

    def matches(self, context: PolicyEvaluationContext) -> bool:
        return context.action_plan.action == "query_order"

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        auth_result = self._load_order_auth_context(context)
        if isinstance(auth_result, PolicyDecision):
            return auth_result
        return self._allow(RiskLevel.L2, "订单属于当前用户，允许查询")


class ChangeAddressRule(BasePolicyRule):
    name = "change_address"

    def matches(self, context: PolicyEvaluationContext) -> bool:
        return context.action_plan.action == "change_address"

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        auth_result = self._load_order_auth_context(context)
        if isinstance(auth_result, PolicyDecision):
            return auth_result

        delivery_status = auth_result.get("delivery_status")
        if delivery_status in self.SHIPPED_DELIVERY_STATUSES:
            return self._human_required(
                RiskLevel.L4,
                "订单已发货或已签收，地址修改需要人工处理",
            )
        return self._confirm_required(RiskLevel.L3, "订单未发货，修改地址需要用户二次确认")


class RequestRefundRule(BasePolicyRule):
    name = "request_refund"

    def matches(self, context: PolicyEvaluationContext) -> bool:
        return context.action_plan.action == "request_refund"

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        auth_result = self._load_order_auth_context(context)
        if isinstance(auth_result, PolicyDecision):
            return auth_result

        idempotency_key = self._build_idempotency_key(context)
        open_ticket = context.repository.get_open_ticket_by_idempotency_key(
            idempotency_key,
        )
        if open_ticket:
            return self._human_required(
                RiskLevel.L4,
                f"退款必须人工处理，且已存在未关闭工单: {open_ticket['id']}",
            )
        return self._human_required(RiskLevel.L4, "退款请求必须转人工处理，不能自动执行")


class CreateComplaintTicketRule(BasePolicyRule):
    name = "create_complaint_ticket"

    def matches(self, context: PolicyEvaluationContext) -> bool:
        return context.action_plan.action == "create_complaint_ticket"

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        return self._human_required(RiskLevel.L4, "投诉属于高风险诉求，需要人工处理")


class SecurityRiskRule(BasePolicyRule):
    name = "security_risk"

    def matches(self, context: PolicyEvaluationContext) -> bool:
        action_plan = context.action_plan
        return (
            action_plan.action == "security_risk"
            or action_plan.intent == "prompt_injection"
        )

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        return self._deny(RiskLevel.L5, "检测到安全风险请求，拒绝执行")


class UnknownActionRule(BasePolicyRule):
    name = "unknown_action"

    def matches(self, context: PolicyEvaluationContext) -> bool:
        return True

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        return self._deny(RiskLevel.L5, "未知动作默认拒绝")


class PolicyRuleRegistry:
    """按 action 匹配并执行确定性策略规则。"""

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self.rules = rules if rules is not None else default_policy_rules()

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecision:
        for rule in self.rules:
            if rule.matches(context):
                return rule.evaluate(context)
        return UnknownActionRule().evaluate(context)


def default_policy_rules() -> list[PolicyRule]:
    """返回默认规则顺序，UnknownActionRule 必须保持最后兜底。"""
    return [
        SecurityRiskRule(),
        QueryPolicyRule(),
        QueryOrderRule(),
        ChangeAddressRule(),
        RequestRefundRule(),
        CreateComplaintTicketRule(),
        UnknownActionRule(),
    ]
